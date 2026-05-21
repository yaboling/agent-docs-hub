# Dataset Comparison: `date=2026-05-05-3` (new) vs `date=2026-05-05` (old)

**Date**: 2026-05-14
**Author**: Yabo Ling
**Context**: Comparing the regenerated training dataset (v3 suffix, incorporating the wildcard-inflation fix) against the original dataset for the same calendar date. Analysis is based on **partition `part-00000`** (first of 2400 shards), extrapolated where noted.

---

## Paths

| Version | GCS Path |
|---------|----------|
| **Old** | `gs://unity-ads-dd-ds-prd-incremental-training-data/user_value/unified_user_value.v11_cpe_lc/preprocessed_combined/date=2026-05-05/` |
| **New** | `gs://unity-ads-dd-ds-prd-incremental-training-data/user_value/unified_user_value.v11_cpe_lc/preprocessed_combined/date=2026-05-05-3/` |

---

## 1. Top-Level Summary

| Metric | Old (`date=2026-05-05`) | New (`date=2026-05-05-3`) | Change |
|--------|------------------------|--------------------------|--------|
| Partitions | 2,400 | 2,400 | — |
| Part-0 file size | 11.5 MiB | 5.5 MiB | **−52%** |
| Part-0 row count | 95,172 | 44,414 | **−53.3%** |
| Estimated total rows | ~228M | ~107M | **−53%** |
| Estimated total size | ~29 GB | ~14 GB | **−52%** |
| Schema (columns) | 83 | 83 | identical |
| Unique `target_game_id` | 1,249 | 501 | **−748 (−59.9%)** |
| Unique `campaign_id` | 5,052 | 2,756 | **−2,296 (−45.4%)** |

---

## 2. Wildcard Inflation: Before vs After

This is the primary metric tied to the root cause analysis in `PREDICTION_INFLATION_ANALYSIS_05_14.md`.

| Metric | Old | New | Change | Direction |
|--------|-----|-----|--------|-----------|
| Wildcard rows (`sdk_event_name = '*'`) | 19.6% | 12.3% | −7.3pp | Better |
| Wildcard `prob_sdk_event_name_label` pos_rate | **0.3526** | **0.2125** | −0.1401 | Better |
| Specific-event pos_rate | 0.1013 | 0.1320 | +0.0307 | Better |
| Overall `prob_sdk_event_name_label` pos_rate | 0.1504 | 0.1419 | −0.0085 | Better |
| Overall `label` mean (any level_complete) | 0.4090 | 0.3827 | −0.0263 | Better |
| Dead-signal events (n>100, pos_rate=0) | **58** | **7** | −51 | Better |

**Key takeaway**: The wildcard positive rate dropped from 35.3% to 21.3%, dramatically reducing the false-positive signal that drives prediction inflation. The fix is working.

However, the wildcard pos_rate is still 21%, which is still higher than the specific-event pos_rate (~13%). The remaining wildcard rows come from live 0-event campaigns (Path A) that are semantically correct but continue to contribute an elevated baseline signal.

---

## 3. Root Cause Confirmed: Archived Campaign Removal

### 3.1 Games removed

773 game IDs are present in the old dataset but absent from the new one. These correspond to campaigns that were archived and filtered out by the `archived_at IS NULL` filter on `campaigns_v3`.

Rows from removed games in the old dataset:
- **17,100 rows** (18% of old partition)
- **63.2%** of those rows were wildcard `*` rows
- Wildcard pos_rate in removed games: **40.8%** (much higher than the overall 35.3%)
- Overall pos_rate in removed games: **27.3%**

This confirms that archived campaigns were disproportionately responsible for wildcard contamination.

### 3.2 Most impactful removed games (from old dataset wildcard rows)

| `target_game_id` | Old wildcard rows | Wildcard pos_rate | Status in new |
|-----------------|-------------------|-------------------|---------------|
| `500212565` | 600 | **86.3%** | Removed |
| `500227763` | 361 | **85.6%** | Removed |
| `500237245` | 226 | **72.1%** | Removed |
| `500081539` | 279 | **56.6%** | Removed |

These four games alone contributed hundreds of rows at near-impossible positive rates (80%+), which were anchoring the wildcard embedding to an unrealistically high positive signal. All are gone in the new dataset.

### 3.3 Remaining wildcard games in new dataset

| `target_game_id` | New wildcard rows | Wildcard pos_rate |
|-----------------|-------------------|-------------------|
| `500199981` | 518 | 0.259 |
| `500156993` | 320 | 0.250 |
| `500070782` | 318 | 0.025 |
| `500065187` | 296 | 0.068 |
| `500071743` | 224 | 0.107 |

The remaining wildcard pos_rates are much more moderate (2.5%–25.9%) compared to the 56–86% outliers that were removed.

### 3.4 Case study: Game `500166235`

This game was the single largest contributor to old wildcard rows (882 rows at 32% pos_rate). It illustrates the fix precisely.

**Old dataset — 14 event types:**
```
*                        n=882,  pos_rate=0.321  ← wildcard, now gone
s_custom14_revenue       n=971,  pos_rate=0.038  ← archived campaign
loop_online_168h_180     n=956,  pos_rate=0.082  ← archived campaign
s_custom7_revenue        n=923,  pos_rate=0.024  ← archived campaign
... (7 more archived-campaign events)
af_purchase              n=903,  pos_rate=0.019  ← still active
af_purchase2             n=891,  pos_rate=0.002  ← still active
af_ad_ua168_advevent_ban15 n=948, pos_rate=0.062 ← still active
```

**New dataset — 3 event types:**
```
af_purchase              n=914,  pos_rate=0.018  ← active campaign kept
af_ad_ua168_advevent_ban15 n=882, pos_rate=0.065 ← active campaign kept
af_purchase2             n=875,  pos_rate=0.000  ← active campaign kept
```

The wildcard row and all 10 archived-campaign events are gone. Only the 3 events from live/non-archived campaigns remain. This is exactly the expected behavior.

---

## 4. Dead-Signal Events: Before vs After

Old dataset had **58 events** with >100 rows and zero positive labels — pure noise contradicting the wildcard rows for the same games.
New dataset has only **7**:

| Event | New rows | Old rows | Remaining reason |
|-------|----------|----------|-----------------|
| `af_purchase2` | 875 | 891 | Non-archived campaign, zero conversions in this window |
| `adsvalue_4000` | 552 | 543 | Non-archived campaign |
| `ipu_72h_10` | 345 | 352 | Non-archived campaign |
| `block_open_1b` | 177 | 182 | Non-archived campaign |
| `us_ad_revenue11` | 128 | 267 | Non-archived campaign |
| `ios_conversion_d60_t1` | 146 | 120 | Non-archived campaign |
| `af_purchase_5.00` | 151 | 166 | Non-archived campaign |

These 7 are from non-archived campaigns that happen to have no conversions in this particular date's data window. They are a minor issue compared to the 51 removed dead-signal events, which were from archived campaigns with no conversions across all time.

---

## 5. Still Unfixed Issues

### 5.1 `campaign_id` bug still present

```
old: campaign_id == audience_id: 100.0%  (BUG)
new: campaign_id == audience_id: 100.0%  (BUG STILL PRESENT)
```

The `campaign_id` column is still mapped to `campaignInfo.audienceId` (same as `audience_id`). The migration to `campaigns_v3` should use `campaignset_id` as the correct identifier — this fix has not been applied. Both columns carry identical values.

### 5.2 `sdk_event_name_array` is empty for all rows (both datasets)

All rows in both datasets have `sdk_event_name_array` with length 0. This is consistent with the current datagen behavior and is not a regression.

### 5.3 Remaining wildcard pos_rate still elevated

The remaining wildcards (12.3% of rows, pos_rate=21.3%) still inflate training. These come from the ~19 live 0-event campaigns (Path A). The expected residual inflation ratio is:

```
wildcard pos_rate / specific pos_rate = 21.3% / 13.2% = 1.6x
```

This is much better than the old ratio (`35.3% / 10.1% = 3.5x`) but is not zero. The model will still have a mild upward bias for unknown/rare events, just not as severe as before.

---

## 6. Estimated Impact on Model Training

| Metric | Old | New | Expected Model Effect |
|--------|-----|-----|----------------------|
| Wildcard pos_rate | 35.3% | 21.3% | Lower prediction floor for rare/unknown events |
| Specific pos_rate | 10.1% | 13.2% | Better calibration for known events |
| Dead-signal events | 58 | 7 | Less contradictory signal, sharper embeddings |
| Games (unique, per partition) | 1,249 | 501 | Less diversity per batch; mild overfitting risk |
| Campaigns (unique, per partition) | 5,052 | 2,756 | Proportional reduction |

**Main concern**: The 59.9% reduction in unique games means each partition covers fewer (game, event) pairs. With fewer games in each mini-batch, the `sdk_event_name` embedding for rare events sees fewer distinct training examples per step. Monitor per-event calibration in W&B to detect any increase in variance.

**Expected serving improvement**: If the wildcard pos_rate reduction from 35% to 21% translates proportionally to prediction levels, the median overbid ratio (previously 2.33x) should drop toward ~1.3–1.5x for moderate-frequency events. Rare-event campaigns will benefit more since their predictions were most contaminated by the wildcard baseline.

---

## 7. What Changed (Fix Summary)

| Change | Applied in new dataset? | Evidence |
|--------|------------------------|---------|
| `archived_at IS NULL` filter via `campaigns_v3` | **Yes** | 773 games and 2,296 campaigns removed |
| Drop wildcard rows from archived 0-event campaigns | **Yes** | Wildcard fraction 19.6% → 12.3%, dead-signal events 58 → 7 |
| Remove high-inflation wildcard games (500212565, 500227763, etc.) | **Yes** | Those game IDs absent from new dataset |
| Fix `campaign_id` → `campaignset_id` | **No** | `campaign_id == audience_id` 100% in new dataset |
| Path C inner join (drop no-campaign games) | Unknown | Cannot verify from parquet alone |
| Re-enable Stage 5 filter | Unknown | Cannot verify from parquet alone |
| Enable calibration (`config.json`) | Out of scope | Config change, not reflected in data |

---

## 8. Verification Query (Full Dataset)

To confirm the wildcard fraction improvement holds across the full ~107M row dataset (not just part-0):

```sql
SELECT
  REGEXP_EXTRACT(prob_sdk_event_name, r'^\d+_(.+)$') AS event_name,
  COUNT(*)                                            AS n,
  AVG(prob_sdk_event_name_label)                      AS pos_rate
FROM `unity-ads-dd-ds-dev-prd.unified_user_value_v11_cpe_lc.unified_user_value_v11_cpe_lc_preprocessed_combined`
WHERE _FILE_DATE = '2026-05-05-3'   -- adjust partition filter to your BQ table schema
GROUP BY 1
ORDER BY n DESC
LIMIT 30
```

Target outcomes vs old baseline (from inflation analysis):
- Old `*` row: 178.2M rows, pos_rate = 36.4%
- New `*` row: expect ~80–100M rows, pos_rate in 20–25% range
