# CPE Level Complete UL Migration — Manager Meeting Summary

**Model**: `unified_user_value.v11_cpe_lc`
**Date**: 2026-05-29
**Author**: Yabo Ling

---

## 1. Why We Are Doing This

The production CPE Level Complete model predicts `P(user fires the campaign-targeted SDK event within 7 days of install)` and drives bidding on CPE Level Complete campaigns. Today it runs as **two separate TensorFlow models** in `ads-audience-pinpointer`:

| Model | Traffic | Limitation |
|---|---|---|
| `level_complete_bhv` | IDFA-identified users only | BHV-only; misses IDFI/unspecified |
| `level_complete_ctx` | IDFI + unspecified users | Weaker model; no UUPS signals |

**Motivation for migration to ads-unified-learner (UL)**:

1. **Split traffic**: Two models cannot learn cross-segment patterns.
2. **External TF Hub sub-models**: Training depends on two pre-trained embeddings (`ibt_embedding` 128d + `install_ibt_embedding` 80d), creating a fragile external dependency.
3. **Non-deterministic training**: Legacy samples one SDK event per step from a ragged label array — results are not reproducible.
4. **Fragmented infra**: Two Kubeflow pipelines, two TFRecord pipelines, two Firestore deployments replaced by one Metaflow workflow + one Triton deployment.
5. **Framework alignment**: The rest of the UV model family has already migrated to PyTorch + UL. Keeping LC in TensorFlow creates maintenance overhead.

**Success criteria**:
- Neutral-to-positive CPE Level Complete campaign performance vs. legacy BHV + CTX combined
- Correct per-SDK-event prediction calibration (no systematic overbidding)
- Broader coverage: 13,321 target games vs. 1,512 in legacy (~8.8x)
- Infrastructure simplification: one pipeline, one model, one serving endpoint

---

## 2. Data

### 2.1 Data Source

| Property | Value |
|---|---|
| Source | `gs://unity-ads-dd-ds-prd-data-anon/app-events/.../level_complete/d7/` |
| Training window | 60 days |
| Label window | 7 days (`app_event_w1 > 0`) |
| Pipeline delay | 9 days (7d label + 2d ETL buffer) |

### 2.2 Label Design — Key Change

Legacy models use one row per install and store all targeted SDK events as a **parallel array**. A single row holds labels for every campaign event simultaneously.

The new model uses **row expansion**: each install is exploded into one row per `(install × targeted SDK event)`. This converts ragged array labels into scalar per-row labels that fit natively into the UL/DLRM framework without custom loss logic.

| Label | Definition | Positive Rate |
|---|---|---|
| `prob_sdk_event_name_label` | 1 if user fired the specific targeted SDK event AND `app_event_w1 > 0` | ~7% (post-fix dataset) |
| `label` | `app_event_w1 > 0` — any level complete (present in data but not used in training) | ~38% |

**Joint distribution** (504M-row dataset):
- 80.4% — non-converters
- 12.5% — converted but did not fire the specific targeted event
- 7.1% — converted AND fired the targeted event (positive training signal)

### 2.3 Data Issues Found and Resolved

**Issue 1 — Wildcard Label Inflation (root cause of v1/v2 over-prediction)**

The BigQuery campaign lookup queried deprecated tables with no status filter, pulling in 7,997 historical campaigns including 2,202 archived ones. Campaigns with 0 or >1 targeted SDK events were collapsed to a wildcard `"*"` row with a positive rate of **35–86%** — far above the true per-event rate of ~7%. This caused the model to anchor predictions at ~19.5% (the blended base rate), massively overbidding rare-event campaigns.

| Metric | Old (v0) | Fixed (v3) |
|---|---|---|
| Wildcard row positive rate | 35.3% | 21.3% |
| Wildcard/specific ratio | 3.5x | 1.6x |
| Dead-signal event types | 58 | 7 |

**Fix**: Migrated campaign lookup to `campaigns_v3` with `archived_at IS NULL`, dropping 2,202 permanently archived campaigns.

**Issue 2 — Categorical Encoding Bug** (resolved April 26): Features were pre-hashed to integers; reverted to raw strings matching legacy representation.

**Issue 3 — Missing Columns** (resolved April 26): Session counters (9 columns) and privacy/identity signals (9 columns) were absent from early snapshots.

**Open issues** (minor, to fix post-launch):
- `campaign_id` maps to `audienceId` instead of `campaignset_id` (Stage 5 filter disabled)

### 2.4 Legacy vs. New Dataset Comparison

| Dimension | Legacy BHV | New UL |
|---|---|---|
| Row granularity | 1 row per install | 1 row per (install × target SDK event) |
| Identity scope | IDFA only | IDFA + IDFI + unspecified |
| Distinct target games | 1,512 | 13,321 |
| UUPS IAP/adrev features | 27 features | Planned (Phase 2) |
| IBT embeddings | 208-dim (TF Hub) | Dropped — replaced by AGC scalars |
| Per-event positive rate | ~14% (specific events) | ~14% (after fix) |

---

## 3. Model Architecture

### 3.1 Side-by-Side Comparison

| Dimension | Legacy BHV + CTX | v11_cpe_lc (new) |
|---|---|---|
| **Framework** | TensorFlow 2.11 + Keras | PyTorch 2.x + Lightning |
| **Architecture** | FC MLP (3 layers: 1024→512→256) | DLRM (dense tower + DotProductPlus interaction + DeepCrossNet + task head) |
| **Number of models** | 2 (BHV + CTX, separate) | 1 unified |
| **Traffic scope** | BHV: IDFA only; CTX: IDFI/unspecified | All (IDFA + IDFI + unspecified) |
| **Training label** | Single binary `label` (any level complete) | Single-task PSN: `prob_sdk_event_name_label` (specific event) |
| **SDK event handling** | Stochastic per-element array sampling | Deterministic row-expansion + scalar label |
| **External embeddings** | IBT 128d + install_ibt 80d | Dropped; replaced by 15 AGC dense scalars |
| **Training rows** | BHV: ~44M, CTX: ~60M | ~107M (post-fix) |
| **Training compute** | 1× T4 GPU | 8× RTX PRO 6000 Blackwell (DDP) |
| **Serving format** | TF Hub SavedModel → Firestore | Triton (packed input, static shape, CPU) |

### 3.2 Architecture Diagram

```
[19 sparse features × 32-dim]      [16 dense scalars]
         |                                  |
  EmbeddingBag                    Dense Tower MLP: 16→64
         |                                  |
         |                       Dense Emb Proj: 64→512→64
         |                                  |
         +------------- concat [21 embeddings × 32-dim] ------+
                                    |
                           DotProductPlus (attention + residual)
                           compress: 21×32 → 21×8 = 168-dim
                                    |
                    concat(cross[168], dense_repr[64]) = 232-dim
                                    |
                           DeepCrossNet (2 layers, rank=128)
                           + MLP projection: 232→256→128
                                    |
                              PSN Task Head
                              128→256→1, Sigmoid
                                    |
                          P(user fires targeted SDK event)
```

### 3.3 Bidding Logic

```python
p    = clamp(psn_pred, 0.0, 1.0)
cost = clamp(max_cost × p × discount_factor, 0.0, 1e18)  # microdollars
```

### 3.4 Offline Results

Trained on a 60-day dataset (install dates 2026-02-26 → 2026-04-26, 486M train / 18.7M val rows). Model artifact: `vny2xtis3e`.

| Metric | v11_cpe_lc (train) | Legacy BHV (val) | Legacy CTX (val) |
|---|---|---|---|
| AUC | **0.9483** | 0.8997 | 0.8991 |
| BCE | **0.2047** | 0.3308 | 0.3313 |
| NE (window) | **0.4119** | ~0.505 | ~0.506 |
| Calibration ratio | **0.9993** | — | — |

**Note**: AUC numbers are train-set metrics; legacy numbers are val-set. Not directly comparable. A held-out time-based evaluation is required for go/no-go. The strong AUC gain (+5.4pp) is indicative but not conclusive.

**Known limitation**: A LR schedule misconfiguration (`total_step=88` instead of ~23,719) caused dense-layer LR to decay to `1e-6` after <1% of training. This has been fixed — `workflow.py` now computes `total_step` dynamically from a BQ `COUNT(*)` query.

### 3.5 Feature Gaps vs. Legacy (Planned Phase 2/3)

| Missing Feature Group | Legacy Source | Priority |
|---|---|---|
| UUPS IAP/adrev signals (27 features) | UUPS pipeline (BHV only) | High — strong purchase intent signal |
| IBT embeddings (128d + 80d) | External TF Hub sub-models | High — cross-game behavioral signal |
| Hardware stats (cpu, ram, dpi) | DeviceAtlas enrichment | Medium — partially covered at serving |

---

## 4. Online Testing — A/B Test History (V1 → V4)

### V1 — Over-predicting (Initial version)

First deployment of the CPE Level Complete UL model. The model was systematically overbidding across nearly all campaigns.

- **Root cause**: Wildcard label contamination from archived campaigns (see Section 2.3). Wildcard `"*"` rows constituted **44% of all training rows** at a positive rate of **36.4%**, vs. 6.0% for specific-event rows — a **6.1x inflation ratio**. BCE minimization drives outputs toward the blended base rate (~19.5%) rather than the true per-event rate.
- **Median overbid ratio vs. legacy**: **2.33x**. Worst campaign (`star5_hero_received`): **36.7x**.

| Overbid range | Campaigns | % |
|---|---|---|
| <1x | 1 | 0.3% |
| 1–2x | 131 | 36.8% |
| 2–3x | 108 | 30.3% |
| 3–5x | 89 | 25.0% |
| >5x | 27 | 7.6% |

**Pattern**: Inflation ratio is inversely proportional to base event rate. Rare events (e.g. `star5_hero_received` at 0.2% natural rate) are most severely inflated; near-ceiling events show no inflation.

### V2 — Over-predicting (Updated campaign management table to `campaigns_v3`)

Updated the BQ campaign lookup to `campaigns_v3` with `archived_at IS NULL` (the wildcard inflation fix). Retrained on the cleaned v3 dataset.

- **Result**: Structurally unchanged inflation. The overall mean prediction was 0.675 (v2: 0.672) and median overbid ratio remained **2.15x** (v2: 2.33x) — within day-to-day traffic variance.
- **Why it didn't help**: The `campaigns_v3` migration dropped archived campaigns but did not fix a second residual wildcard inflation from live 0-event campaigns. The model also lacked any post-hoc calibration layer (legacy uses a per-campaign product-accuracy feedback loop that is not replicated in UL).
- New regressions introduced: `aj_vip` went from 1.43x (v2) to 10.07x (v3); `af_level_up_20` worsened across 3 campaigns.

**GCS model artifacts**:
- `gs://unity-ads-dd-ds-prd-app-trained-models/training/level_complete/bhv1p/20260521132425_hub/bid_eligibility_multipliers_info.json`
- `gs://unity-ads-dd-ds-prd-app-trained-models/training/level_complete/bhv1p/20260521132425_hub/trained_game_sdk_combo_multipliers.json`

### V3 — Partial improvement with gating

Added per-(game, SDK event) **eligibility gating** logic, mirroring the legacy `trained_game_sdk_combo_multipliers.json` mechanism. This gates out `(game, event)` combinations never seen in training with a positive label.

- **What gating does**: Zeroes out bids for game-event pairs that had no positive training signal, preventing bids on completely unseen events.
- **What gating does NOT do**: Does not reduce prediction magnitude for seen-but-inflated events (e.g. `ajvip` at 15x still passes through at full inflation).
- Status: Marginal improvement on worst outliers; structural inflation remained.

### V4 — Added gating and calibration logic (current)

Added both the eligibility gate **and** a per-campaign product-accuracy calibration layer equivalent to the legacy `LevelCompleteCostWrapper` feedback loop.

**Traffic ramp timeline**:

| Date | Traffic % |
|---|---|
| 2026-05-22T20:42:34Z | 1% |
| 2026-05-25T18:14:31Z | 10% |
| 2026-05-27T15:38:17Z | 50% |

**Current status (as of 2026-05-29)**:

The model is now **under-predicting** rather than over-predicting. Accuracy metric (Actual CPE / Target CPE − 1) is negative across all days, indicating the model bids too conservatively by approximately **40%**.

- Under-prediction is a sign the calibration correction is over-correcting, or the eligibility gating is too aggressive (zeroing out bids that should be non-zero).
- This is a better failure mode than over-predicting (no overspend risk), but means the model is leaving spend on the table and may underperform legacy on volume metrics.

**Next steps**:
1. Diagnose whether under-prediction is from calibration over-correction or excessive gating.
2. Tune calibration factors / gating thresholds.
3. Run full AB test comparison vs. legacy at 50% traffic with revenue/CPI/CPE metrics.

---

## 5. Key Risks and Open Items

| Item | Status | Priority |
|---|---|---|
| V4 under-predicting ~40% | Under investigation | Critical |
| UUPS IAP/adrev features missing | Planned as v12_cpe_lc (Phase 2) | High |
| IBT embeddings not replaced | Phase 3 | High |
| `campaign_id` → `campaignset_id` fix | TODO | Low |
| Stage 5 filter (`filter_min_dates_by_game_and_event`) disabled | TODO post-E2E | Low |
| `sdk_event_name` online serving population verified | TODO with serving team | Medium |

---

## 6. Summary

| Milestone | Status |
|---|---|
| Framework migration (TF → PyTorch/UL) | Done |
| Unified BHV+CTX traffic | Done |
| Wildcard label contamination fix | Done (v3 dataset) |
| Eligibility gating | Done (v3 online) |
| Calibration layer | Done (v4) |
| Prediction inflation resolved | Done (v4 not over-predicting) |
| Under-prediction in v4 | **In progress** |
| UUPS feature addition | Planned (v12) |
| Full AB test decision | Pending v4 calibration tuning |
