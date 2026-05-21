# Label Distribution Deep-Dive: Legacy (BHV/CTX) vs New UL Dataset

**Date**: 2026-05-21
**Author**: Yabo Ling
**Datasets**:
- Legacy BHV: `gs://unity-ads-dd-ds-prd-app-training-data/level_complete/bhv_level_complete_data_v2p/20260520132632/`
- Legacy CTX: `gs://unity-ads-dd-ds-prd-app-training-data/level_complete/ctx_level_complete_data_v2p/20260520132525/`
- New UL: `gs://unity-ads-dd-ds-prd-incremental-training-data/user_value/unified_user_value.v11_cpe_lc/preprocessed_combined/date=2026-05-11/`

**Sample size**: 153,092 BHV rows (10 shards), 209,719 CTX rows (10 shards), 877,366 UL rows (20 shards).

See companion HTML for interactive visualizations: `label_distribution_analysis.html`

---

## TL;DR

The datasets have the **same base label semantics** (`label` = any level_complete event, ~36–38% positive in all three). The difference is **not** in the `label` column. The difference is in:

1. **How per-event training targets are computed** (array vs single field)
2. **How wildcard `*` rows contaminate the training distribution** (unmitigated in UL, calibrated in legacy)
3. **Missing post-hoc calibration in UL**

---

## 1. Schema Architecture Differences

### Legacy BHV / CTX

| Column | Type | Value |
|---|---|---|
| `sdk_event_name` | string | **`"placeholder"` for 100% of rows** |
| `label` | float | 36.06% positive — any level_complete fired |
| `prob_sdk_event_name_array` | list[string] | `["gameId_event1", "gameId_event2", ...]` |
| `prob_sdk_event_name_labels` | list[float] | Per-event binary labels — **the actual training target** |

- Every training row contains an **array** of all campaign-targeted events for that game.
- The model is trained on the per-event label from this array (multi-task style).
- `sdk_event_name = "placeholder"` means **the event name is NOT an online feature** — it is baked into the per-event embedding key only.
- Overall per-event positive rate: **23.52%** (mean across all (game, event) pairs in the array).
- Post-hoc calibration (`trained_game_sdk_combo_multipliers.json`) applied at deploy time.

### New UL (v11-cpe-lc)

| Column | Type | Value |
|---|---|---|
| `sdk_event_name` | string | Actual event name or `"*"` (12.29% of sample rows) |
| `label` | int32 | 38.16% positive — `app_event_w1 > 0` (any event) — **100% match** |
| `prob_sdk_event_name` | string | `"gameId_event"` composite offline embedding key |
| `prob_sdk_event_name_label` | float | **14.25% positive overall** — the per-event training target |
| `app_event_w1` | int64 | Raw event count week 1 (determines `label`) |

- `label` perfectly equals `(app_event_w1 > 0)` — confirmed, 100% match.
- `prob_sdk_event_name_label` is the actual per-event label the model trains on.
- **No post-hoc calibration.**

---

## 2. Overall Positive Rate Comparison

| Metric | BHV | CTX | UL |
|---|---|---|---|
| `label` (any event) | **36.06%** | **35.98%** | **38.16%** |
| Per-event label (mean) | 23.52% | 23.96% | 15.60% (`prob_sdk_event_name_label`) |
| Specific event rate | 14.04% | — | 14.30% |
| Wildcard `*` rate | 37.75% | — | 26.10% |

**Key observation**: The per-event label mean (14–16%) is similar across legacy and UL for specific events. The difference is that wildcard rows in UL add a higher-positive-rate contamination signal that has no calibration layer to correct it.

---

## 3. The Wildcard `*` Problem

Wildcard rows exist in both legacy and UL. But they differ in volume and mitigation:

| | Legacy BHV | New UL |
|---|---|---|
| Wildcard `*` share (game,event pairs) | **39.99%** of unique pairs | **11.04%** of unique pairs |
| Wildcard `*` share (training rows volume) | ~20–40% | **~44% of total rows** (BQ analysis) |
| Wildcard positive rate | **37.75%** | **26.10%** |
| Specific event positive rate | **14.04%** | **14.30%** |
| Wildcard/specific ratio | **2.7x** | **1.8x** |
| Calibration applied | ✅ Yes | ❌ No |

**Mechanics in UL**: When `sdk_event = '*'`, the label assignment in `unified_cpe_datagen.py` fires:

```python
prob_sdk_event_name_label = IF(
    (array_contains(sdk_event_name_array, sdk_event)
     OR sdk_event = '*'      # ← fires for ALL level_complete events
     OR sdk_event = '') AND label = 1,
    1.0, 0.0
)
```

This makes `prob_sdk_event_name_label = label = (app_event_w1 > 0)` for wildcard rows.
The model is trained to predict the game's overall level_complete conversion rate (~21–38%) for these
rows, instead of the specific event rate.

**Confirmed**: `prob_sdk_event_name_label == label` for 100% of wildcard rows in the UL sample.

---

## 4. UL Internal Label Mismatch: `label=1` but `prob_label=0`

| label | prob_sdk_event_name_label | Count | Share |
|---|---|---|---|
| 0 | 0 | 542,562 | 61.84% |
| 0 | 1 | 0 | 0.00% |
| **1** | **0** | **209,816** | **23.91%** |
| 1 | 1 | 124,988 | 14.25% |

**23.91% of all UL rows** have `label=1` (user completed some event) but `prob_sdk_event_name_label=0` (not the targeted event). These rows provide zero positive signal for the per-event training target. In legacy, this case cannot occur because the per-event label is derived directly from the per-event conversion, not the overall label.

---

## 5. Per-(game, event) Label Comparison — Overlapping Pairs

Of the **2,673 BHV unique (game, event) pairs** and **1,323 UL pairs**, **1,286 overlap** in both datasets.

### Top 15 Most Inflated (UL prob_label / BHV per-event rate)

| target_game_id | sdk_event | BHV pos_rate | UL prob_label | UL base_label | UL/BHV Ratio |
|---|---|---|---|---|---|
| `500211291` | `af_add_to_cart` | 0.0000 | 0.4762 | 0.4762 | **476.2x** |
| `500172655` | `*` | 0.0000 | 0.4286 | 0.4286 | **428.6x** |
| `500052123` | `level15` | 0.0000 | 0.3778 | 0.8000 | **377.8x** |
| `500218398` | `complete_level_20` | 0.0000 | 0.3500 | 0.7000 | **350.0x** |
| `500204268` | `d7_puzzle15_bingo` | 0.0000 | 0.3333 | 0.3333 | **333.3x** |
| `500198758` | `stage_clear_80` | 0.0000 | 0.3333 | 0.3333 | **333.3x** |
| `500064746` | `stageclear_50` | 0.0000 | 0.3077 | 0.3077 | **307.7x** |
| `500243840` | `registration_successful` | 0.0000 | 0.3000 | 0.3000 | **300.0x** |
| `500190914` | `*` | 0.0000 | 0.2941 | 0.2941 | **294.1x** |
| `500027274` | `paid_imp_20` | 0.0000 | 0.2857 | 0.3810 | **285.7x** |
| `500261085` | `first deposit` | 0.0000 | 0.2500 | 0.2500 | **250.0x** |
| `500030337` | `paid_imp_75` | 0.0000 | 0.2432 | 0.3784 | **243.2x** |
| `500245525` | `player_level_10` | 0.0000 | 0.2414 | 0.9655 | **241.4x** |
| `500219697` | `s_day7` | 0.0000 | 0.2353 | 0.7059 | **235.3x** |
| `500030337` | `imp_57` | 0.0000 | 0.2264 | 0.3962 | **226.4x** |

**Pattern**: The most inflated pairs are games where BHV records near-zero positives (the game barely had any users completing that event in legacy training data), while UL records a high positive rate because wildcard rows pull the prediction up.

---

## 6. Why Legacy Models Are Better Calibrated

Despite having similar per-event specific-event positive rates, legacy models predict correctly because:

1. **Post-hoc calibration** (`trained_game_sdk_combo_multipliers.json`): applies a per-(game, sdk_event) multiplier at deploy time to scale down predictions to match observed conversion rates. This corrects for any training label inflation.

2. **`sdk_event_name = "placeholder"`**: The model does NOT use the event name as an online input feature. It uses the per-event embedding from `prob_sdk_event_name_array` only during training. At serving, the calibration multipliers handle the per-event scaling.

3. **Multi-task label array**: Legacy training rows contain labels for ALL campaign events simultaneously. The model learns to distinguish between events via the `prob_sdk_event_name_labels` array rather than relying on a single label. This means rare events are still represented in training data for games that also have common events.

---

## 7. Root Cause Table

| Issue | Legacy | UL | Impact on Serving |
|---|---|---|---|
| Wildcard `*` rows positive rate | 37.75% | 26.10% | Pulls model toward game overall rate |
| Wildcard % of training rows | ~20% pairs | **~44% by volume** | Dominates gradient signal |
| Post-hoc calibration | ✅ Applied | ❌ Not applied | No correction for label bias |
| `label=1, prob_label=0` rows | Not present | **23.91%** of rows | Training noise |
| Archived campaign rows | Not applicable | ~27.5% of campaigns | Generate dead wildcard rows |
| Event name as online feature | No (placeholder) | Yes | Requires correct event embeddings |

---

## 8. Recommended Fixes

| Priority | Fix | Expected Impact |
|---|---|---|
| 1 | Enable `calibration: true` in `config.json` | Immediate correction without retraining |
| 2 | Migrate BQ query to `campaigns_v3`, filter `archived_at IS NULL` | Removes 27.5% of archived campaigns generating dead wildcard rows |
| 3 | Explode multi-event campaigns (Path B) | Per-event correct labels for 28 multi-event campaigns |
| 4 | Re-enable Stage 5 filter (`filter_min_dates_by_game_and_event`) | Removes cold-start noise |
| 5 | Add data quality assertions in datagen | Catch wildcard contamination before training |

---

## 9. Files Referenced

| File | Relevance |
|---|---|
| `doc/label_distribution_analysis.html` | Interactive visualizations (this report) |
| `doc/PREDICTION_INFLATION_ANALYSIS_05_14.md` | Serving-side inflation analysis |
| `doc/PREDICTION_INFLATION_ANALYSIS_05_20.md` | v11-cpe-lc-3 serving analysis |
| `src/unity_learner/data/spark/user_value/unified_cpe_datagen.py` | Datagen label logic |
| `src/unity_learner/experiment_repo/unified_user_value/v11_cpe_lc/config.json` | `enable_calibration: false` |
