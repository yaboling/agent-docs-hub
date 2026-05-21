# Legacy Level Complete Calibration: How It Works End-to-End

**Date**: 2026-05-21
**Author**: Yabo Ling
**Context**: Explains the post-hoc calibration stack in `ads-audience-pinpointer` for the level_complete BHV/CTX model, and why `enable_calibration: false` in the UL experiment leaves a structural gap.

---

## Overview

The legacy serving stack applies **two independent calibration mechanisms** at inference time. They operate at different granularities and serve different purposes. Neither is a statistical technique baked into the model artifact — both are post-hoc corrections applied in the `LevelCompleteCostWrapper` Python class, which runs every time the serving model is loaded.

**Key files:**
- `serving/serving/app_events/cost_wrappers.py` — `LevelCompleteCostWrapper.call()`
- `serving/serving/app_events/levcom_prod_acc.py` — BQ query + campaign selection
- `serving/serving/app_events/configs.py` — config schema

---

## Mechanism 1: Per-(game, sdk_event) Eligibility Gate — `trained_game_sdk_combo`

### Purpose

Not calibration in the statistical sense — it is a **binary gating multiplier** that silences bids for `(target_game_id, sdk_event_name)` combinations that the model was never trained on.

### How it works

```
At model load time:
  trained_game_sdk_combo_multipliers.json loaded from GCS model dir
  e.g. {
    "500043219_solved_puzzles_count_10": 1.0,
    "500071743_ajvip":                   1.0,
    "500000057_level_101":               1.0,
    ...
  }
  default_value = 0.0   ← anything not in the JSON bids 0

At each inference call (cost_wrappers.py:502–515):
  key = lower(target_game_id) + "_" + lower(sdk_event_name)
  multiplier = hash_table.lookup(key)   # 1.0 if trained, 0.0 if not
  cost = cost * multiplier
```

The JSON is written during training by a step that collects every `(game_id, event_name)` pair seen in the training data with at least one positive label. If a campaign requests a bid for `500012345_new_event` and that combo never appeared in training, the bid is zeroed out.

### What it does NOT fix

This gate prevents bids on *completely unseen* events, but does nothing to reduce prediction magnitude for *seen-but-inflated* events. If the model has seen `500071743_ajvip` but assigns it `p = 0.49` (true rate: `0.033`), the multiplier is `1.0` and the inflated prediction passes through unchanged.

---

## Mechanism 2: Per-Campaign Product Accuracy Calibration

### Purpose

Correct inflated predictions per campaign by measuring the ratio of **actual outcomes to predicted outcomes** in recent live traffic, then applying that ratio as a multiplicative factor at bid time.

This is a feedback loop: measure how wrong you were, and correct by that exact factor at the next model load.

### Phase A — BQ query to measure campaign-level bias

Source: `levcom_prod_acc.py:QUERY`

```sql
-- For each level_complete campaign over the last N days, compute:
--   spend            = actual money spent
--   uncalibrated_expected_spend = sum(unadjusted_pred × tCPE_micro)
--   level_complete_d7           = actual conversions within postback window
--   oCPE             = actual_conversions × tCPE  (observed cost-per-event)

-- Per-campaign product accuracy ratio:
uncalib_outcome_ovr_spend_product_accuracy
  = oCPE / uncalibrated_expected_spend
  = (observed_rate × tCPE) / (predicted_rate × tCPE × n_starts / n_installs)
  ≈ observed_rate / predicted_rate
```

A campaign with true rate `0.033` predicted at `0.49` gets a ratio of `≈ 0.067`.

The query joins:
- `ads_events_raw.ads_events_operativeecpm_v1` (starts + installs)
- `mz_dcpi_raw.mz_dcpi_prediction_v1` (unadjusted predictions, pulled from `valuation_metadata`)
- `rawevents.ads_secondaryconversion_postInstallAppEventContextual_bhvctx` (actual level_complete events)

The join on `sdk_event_name` uses `'*'` for wildcard campaigns — a copy of every level_complete event is unioned with `sdk_event_name = '*'` so wildcard campaigns match correctly.

### Phase B — Select campaigns to calibrate

Source: `levcom_prod_acc.py:select_campaigns`

```python
# Only calibrate campaigns that are ALL of:
#  1. Large enough:      n_installs >= min_installs
#  2. Low true rate:     event_rate <= max_event_rate   # targets rare, inflated events
#  3. Meaningfully over: ratio < 1 / min_overvaluation  # e.g. ratio < 0.5 means 2x over

idx = (event_rate <= max_event_rate) & (ratio < 1 / min_overvaluation)
selected = df[idx][df[idx].n_installs >= min_installs]
```

Well-calibrated campaigns and high-volume, high-rate campaigns are deliberately excluded — they don't need correction and have enough traffic to self-regulate via the ROI threshold.

### Phase C — Build calibration lookup table

Source: `levcom_prod_acc.py:create_calibration_lookup_table`

```python
# Per selected campaign:
calibration_factor = clip(observed_rate / predicted_rate, min_factor, max_factor)
hash_table[audience_id] = calibration_factor

# Example:
# campaign ajvip:      ratio = 0.033 / 0.49 ≈ 0.067  → factor = 0.067
# campaign eventw:     ratio = 0.054 / 0.664 ≈ 0.081 → factor = 0.081
# unknown campaign:    default = -1.0  (no correction applied)
```

### Phase D — Apply at inference time

Source: `cost_wrappers.py:calibrate_predictions` (lines 292–308)

```python
def calibrate_predictions(self, probabilities_levcom, audience_id):
    calibration_factors = self.calibration_tbl.lookup(audience_id)
    calibrated_p = tf.where(
        calibration_factors >= 0,          # -1.0 means "not selected"
        calibration_factors * probabilities_levcom,
        probabilities_levcom               # pass through if not in table
    )
    return calibrated_p, calibration_factors
```

Applied **before** clipping and before the ROI threshold gate:

```
raw p = 0.49  (model sigmoid output for ajvip)
× calibration_factor = 0.067
= calibrated p ≈ 0.033   ← now matches observed rate
```

---

## Full Inference Pipeline

```
Raw model output:  p = sigmoid(logit)
                   e.g. p = 0.49 for "ajvip"
        │
        ▼
[1] trained_game_sdk_combo multiplier
    × 1.0  if (game, event) seen in training
    × 0.0  if (game, event) never seen
        │
        ▼
[2] product_accuracy calibration_factor       ← per-campaign BQ feedback loop
    × 0.067  if campaign overvalued (ratio < threshold)
    × 1.0    if not selected (well-calibrated or too small)
        │
        ▼
[3] clip_predictions (optional)
    min(p, observed_event_rate × evt_rate_factor)
        │
        ▼
[4] ROI threshold + exploration mask
    × 0  if predicted_ROI < threshold AND not in exploration fraction
        │
        ▼
Served bid:  cost = calibrated_p × tCPE_micro
```

---

## Why UL Does Not Have Equivalent Calibration

UL's `enable_calibration` flag in `config.json` refers to a **different mechanism** in `ads-unified-learner/src/unity_learner/deploy/conversion/calibration.py`:

- It is a **Platt-scaling layer** trained on ROAS/spend aggregates, baked into the model artifact at deploy time.
- It is **global** (not per-campaign or per-event).
- It requires a `calibration_config` dict with a dedicated BQ query and feature list — which has not been configured for `unified_user_value.v11_cpe_lc`. Setting `enable_calibration: true` without `calibration_config` causes an assert failure at deploy time.
- Even if enabled, it corrects aggregate bias (e.g. "this model predicts 20% too high on average") — it cannot selectively correct the `ajvip` family at 15x while leaving `ipu_72h_10` untouched.

The legacy calibration is demand-side and per-campaign. It can target precisely the campaigns whose predictions are wrong, clamping factors between `min_factor` and `max_factor` to avoid over-correction. The UL calibration layer has no equivalent mechanism.

---

## Implications for the UL Inflation Problem

Even after the probabilistic sampling fix (Stage 6), which reduced the wildcard row fraction from 44% → 23% and narrowed the wildcard/specific ratio from 1.8x → 1.33x, residual inflation remains:

| Source of residual inflation | Legacy mitigation | UL status |
|---|---|---|
| Wildcard rows inflate training distribution | Calibration corrects per-campaign | Partially mitigated by sampling; no calibration |
| Rare events have few training examples → high variance | Calibration floor/ceiling via `min_factor`/`max_factor` | None |
| New campaigns with no feedback data | `default = -1.0` (no correction) | Same — model output used directly |
| `label=1 but prob=0` noise rows (18.55%) | Coherent per-event labels prevent this | Structural; reduced but not eliminated |

The most actionable next step is setting up per-campaign product accuracy calibration in the UL serving path, equivalent to `LevelCompleteCostWrapper`'s Phase A–D above, rather than relying on the model-internal Platt scaling layer.

---

## Files Referenced

| File | Role |
|---|---|
| `serving/serving/app_events/cost_wrappers.py` | `LevelCompleteCostWrapper`: applies calibration + gating at inference |
| `serving/serving/app_events/levcom_prod_acc.py` | BQ query, campaign selection, lookup table construction |
| `serving/serving/app_events/payer_calibration.py` | Analogous mechanism for purchase model (different query, same pattern) |
| `serving/serving/common/adjustments/adjustments.py` | Generic `RoasFallbackAdjustment` used by other model types |
| `src/unity_learner/deploy/conversion/calibration.py` | UL Platt-scaling layer (different, global, requires `calibration_config`) |
| `src/unity_learner/experiment_repo/unified_user_value/v11_cpe_lc/config.json` | `enable_calibration: false` |
