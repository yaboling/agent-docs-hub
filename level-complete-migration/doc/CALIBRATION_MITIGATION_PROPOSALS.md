# v11-cpe-lc Calibration Mitigation Proposals

**Author**: Yabo Ling
**Date**: 2026-06-09
**Context**: Post-AB-test analysis of `unified_user_value.v11_cpe_lc` vs legacy `bhv1p + ctx1r`

---

## Background

The AB test demonstrated strong business results for `v11-cpe-lc` (Net Revenue +99.4% on LC traffic, +0.71% all-traffic). However, the post-install analysis revealed a significant target-event model bias issue:

| Window | Control (bhv1p+ctx1r) | Test (v11-cpe-lc) |
|--------|----------------------|-------------------|
| D0     | +17.5%               | +56.2%            |
| D3     | +22.6%               | +63.8%            |
| D7     | +29.3%               | +75.9%            |

The model over-predicts the campaign-specific target event by 56–76%, compared to 17–29% for the legacy control. The SDK event breakdown identified two primary drivers:

- `onlinetime_60m`: 18,148 misses at 18.7% match rate
- `day5_retention`: 10,116 misses at 3.4% match rate

Together these **retention-type events account for ~48% of all LC-target misses**, despite being classified under `app_event_conversion_type = 'LEVEL_COMPLETE'` in BigQuery.

Per-category bias at D0:

| Category         | v11 bias_any | v11 bias_tgt | Control bias_tgt |
|------------------|-------------|-------------|-----------------|
| Wildcard (`*`)   | +56.3%      | N/A         | N/A             |
| True LC          | +6.4%       | +51.7%      | +9.9%           |
| High-milestone   | +12.1%      | +152.5%     | +38.2%          |
| Retention events | +8.9%       | +65.2%      | +4.3%           |
| Non-LC events    | +14.2%      | +88.1%      | +22.4%          |

---

## Root Cause Analysis

### RC-1: Product Accuracy Calibration Disabled at Deploy

**File**: `config.json`
```json
"enable_product_accuracy_calibration": false
```

The `workflow.py` `refresh_calibration` step already runs daily: it queries 14 days of live traffic, computes `observed_rate / predicted_rate` per campaign, and writes `product_accuracy_calibration.json` to GCS. The `DeployModel._build_calibration_tensor()` in `model.py` loads and applies it at serving time — but the config flag keeps it disabled.

This means the +56% over-prediction is computed, measured, and could be corrected in real time, but the correction is not being applied.

### RC-2: Training Label Mismatch for Retention-Type Events

**File**: `features.py`
```python
LabelConfig(name="prob_sdk_event_name_label", ...)  # main_task_name
```

The model trains on "will this user fire the campaign's targeted SDK event?" but has no categorical feature to distinguish behavior types. `onlinetime_60m` and `day5_retention` require fundamentally different user signals (session duration, re-engagement) compared to `level_complete_10` (game progression). The model averages gradients across all campaign types, causing it to overfit to the dominant true-LC distribution and systematically over-predict for retention-type targets.

### RC-3: Wildcard Campaign Training Signal Mismatch

**File**: `model.py`
```python
_sdk_wildcard_idx  # remaps UNKNOWN_INT=5 → '*' vocab index at serving time
```

At serving time, wildcard campaigns use `sdk_event_name='*'`. During training, wildcard impressions were labeled with `prob_sdk_event_name_label` evaluated against whichever event fired — a mixed distribution across all 45+ event types. The `'*'` embedding learns an "average LC probability across all games" which is biased high because:
1. Wildcard campaigns are disproportionately new/unseen games with lower actual event rates
2. The mixed training label doesn't reflect the per-game reality at serving time

### RC-4: No Campaign Category Feature in the Model

**File**: `features.py` — no feature distinguishes retention vs. true LC vs. wildcard

The `sdk_event_name` sparse feature (hash_size=10000) encodes the specific event name but places all event types in a shared continuous embedding space. The model cannot learn a hard per-category policy. Without an explicit category feature, the DLRM interaction layer cannot selectively reduce predictions for retention-type targets.

---

## Mitigation Proposals

### Proposal P0 — Enable Product Accuracy Calibration (Immediate, No Retrain)

**Priority**: Critical
**Effort**: 1 hour
**Expected Impact**: −50%+ reduction in target-event model bias across all categories

**Change**: Flip one flag in `config.json`:

```json
// Before
"enable_product_accuracy_calibration": false

// After
"enable_product_accuracy_calibration": true
```

Then redeploy the existing `v11-cpe-lc-4` artifact via `ul-cli deploy`. No retraining required.

**How it works**: At model-load time, `DeployModel._build_calibration_tensor()` reads `product_accuracy_calibration.json` from GCS (written daily by `refresh_calibration` step). At serving time, the raw model prediction is multiplied by the per-campaign correction factor:

```python
# model.py DeployModel.forward()
if self._calibration_enabled:
    calib_factor = self._calib_tensor[audience_idx]  # per-campaign factor
    pred = pred * calib_factor  # factor = observed_rate / predicted_rate
```

Correction is clamped to `[_CALIB_MIN_FACTOR=0.05, _CALIB_MAX_FACTOR=1.0]` — it can only shrink over-predictions, not amplify under-predictions. This is appropriate given v11's consistent over-prediction.

**Risk**: Low. The calibration factors are already being computed and have been accumulating 14-day lookback data since the model went live. The clamp prevents runaway behavior.

**Validation**: After deploy, check D0 target-event model bias in the combined notebook — expect it to drop from +56% to near 0%.

---

### Proposal P1 — Add `campaign_event_category` Sparse Feature (Next Training Run)

**Priority**: High
**Effort**: 3–5 days
**Expected Impact**: Structural fix for per-category bias gap; reduces reliance on post-hoc calibration

**Change 1**: Add feature to `features.py`:

```python
SparseFeature(
    "campaign_event_category",
    hash_size=8,          # 5 categories + padding headroom
    embedding_dim=4,
    feature_type=FeatureType.SPARSE,
),
```

**Change 2**: Populate at datagen time via BQ categorization logic (mirrors the diagnostic notebook):

```sql
CASE
  WHEN sdk_event_names IS NULL OR TRIM(sdk_event_names) = '' THEN 'wildcard'
  WHEN LOWER(sdk_event_names) IN ('onlinetime_60m', 'day5_retention',
       'day7_retention', 'day14_retention', 'onlinetime_30m') THEN 'retention_event'
  WHEN LOWER(sdk_event_names) LIKE '%level_complete%'
    OR LOWER(sdk_event_names) LIKE '%levelcomplete%' THEN 'true_lc'
  WHEN LOWER(sdk_event_names) LIKE '%milestone%'
    OR LOWER(sdk_event_names) LIKE '%stage%'
    OR LOWER(sdk_event_names) LIKE '%chapter%' THEN 'high_milestone_lc'
  ELSE 'non_lc_event'
END AS campaign_event_category
```

**Why this helps**: The DLRM interaction layer (`dot_product_compress_dim=16`) will learn that `retention_event × user_features` predicts ~3–4% LC rate while `true_lc × user_features` predicts ~22%. The model gains an explicit categorical separation instead of averaging across the shared `sdk_event_name` embedding space.

**Validation**: Check per-category bias breakdown after retraining — expect `bias_tgt` for `retention_event` to converge to `bias_any` (since the model now knows the target event category).

---

### Proposal P2 — Route Wildcard Campaigns to Generic LC Label at Training (Next Training Run)

**Priority**: Medium
**Effort**: 2 days
**Expected Impact**: Fixes the +56% wildcard over-prediction at training time, complementing P0's runtime correction

**Problem**: Wildcard campaigns contribute to `prob_sdk_event_name_label` training with a mixed signal (any LC event that fired). But at serving time they receive `sdk_event_name='*'`, which should predict the per-game generic LC rate — not the average across all event types.

**Change**: In datagen or the loss function, route wildcard rows to a different label:

```python
# model.py _PlainBCELoss.forward() — add wildcard label routing
WILDCARD_IDX = features['sdk_event_name'].eq(self._sdk_wildcard_vocab_idx)

loss_specific = F.binary_cross_entropy(
    pred[~WILDCARD_IDX],
    labels['prob_sdk_event_name_label'][~WILDCARD_IDX],
    reduction='mean'
)
loss_wildcard = F.binary_cross_entropy(
    pred[WILDCARD_IDX],
    labels['prob_lc_label_d1'][WILDCARD_IDX],  # generic LC label for wildcards
    reduction='mean'
)
loss = loss_specific + loss_wildcard
```

This ensures the `'*'` embedding learns from the per-game generic LC distribution, not the mixed cross-event distribution.

**Note**: Requires `prob_lc_label_d1` to be available in the training dataset (it is already included as a datagen output in `features.py`).

---

### Proposal P3 — Filter or Reweight Retention-Event Campaigns (Next Training Run)

**Priority**: Medium
**Effort**: 1 day
**Expected Impact**: Eliminates the main contamination source (onlinetime_60m, day5_retention) from training distribution

Retention-type events have 3.4% target match rate vs. 22% for true LC events. Including them in the training distribution with equal weight causes the model to anchor its `sdk_event_name` embeddings toward the high-rate true-LC distribution.

**Option A — Filter (Recommended)**: Exclude retention-event campaigns from the LC model's training data. They can fall back to the generic CTR model or a future specialized retention model.

In datagen BQ query, add to `WHERE` clause:
```sql
AND NOT (
  LOWER(sdk_event_names) IN ('onlinetime_60m', 'day5_retention',
    'day7_retention', 'day14_retention', 'onlinetime_30m')
)
```

**Option B — Reweight**: Add `sample_weight=0.1` for retention-event rows, reducing their gradient contribution while preserving coverage:

```python
# In loss function
weights = torch.where(
    features['campaign_event_category'].eq(RETENTION_IDX),
    torch.tensor(0.1),
    torch.tensor(1.0)
)
loss = F.binary_cross_entropy(pred, labels, weight=weights, reduction='mean')
```

Option A is recommended for cleaner semantics. Option B is safer if retention-event campaigns represent meaningful revenue that should not be dropped.

---

## Implementation Roadmap

| Proposal | When      | Effort | Requires Retrain | Expected Bias Reduction |
|----------|-----------|--------|-----------------|------------------------|
| **P0** Enable calibration | This week | 1 hour | No | ~50%+ all categories |
| **P1** Add category feature | v12 sprint | 3–5 days | Yes | ~20% additional, structural |
| **P2** Wildcard label routing | v12 sprint | 2 days | Yes | Fixes wildcard over-pred at training |
| **P3** Filter retention events | v12 sprint | 1 day | Yes | Eliminates main contamination source |

**Recommended sequence**:
1. Deploy P0 immediately on `v11-cpe-lc-4` — flip `enable_product_accuracy_calibration: true`, redeploy artifact
2. Implement P1 + P3 together for v12 (they naturally go together in datagen)
3. Evaluate P2 after P1/P3 — if the category feature in P1 already reduces wildcard bias sufficiently, P2 may be unnecessary

---

## Acceptance Criteria

After P0 deploy:
- D0 target-event model bias for v11 < +10% (down from +56%)
- D3 target-event product bias remains near 0 (currently −2%, must not regress)

After v12 training with P1 + P3:
- Per-category target-event bias within ±15% for all categories
- Wildcard any-event bias < +20% (down from +56%)
- Overall D7 target-event product bias within ±5%

---

*Reference: `AB-test-analysis/oECPM_Table_of_Level_Complete_Migration_AB_test_2026_06_bhv_ctx_combined.ipynb` — bias-by-category section*
*Model code: `src/unity_learner/experiment_repo/unified_user_value/v11_cpe_lc/`*
