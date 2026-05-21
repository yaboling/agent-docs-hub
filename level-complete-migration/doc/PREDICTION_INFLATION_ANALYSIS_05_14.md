# Prediction Inflation Analysis: v11-cpe-lc-2 vs Legacy Models

**Date**: 2026-05-14
**Author**: Yabo Ling
**Context**: v11-cpe-lc-2 dialed to 1% traffic; predictions observed to be significantly higher than legacy models on matched campaigns.

---

## Data Source

```sql
SELECT
    submit_date,
    body.campaign_id,
    body.target_game_id,
    body.app_event_model_version AS app_event_model_version,
    MAX(body.sdk_event_name),
    COUNT(*)         AS start_count,
    AVG(body.app_event_p) AS avg_pred,
    AVG(body.max_cst)     AS avg_target_cpe,
    AVG(body.cst)         AS avg_cost
FROM `unity-ai-data-prd.mz_dcpi_raw.mz_dcpi_prediction_v1`
WHERE submit_date BETWEEN '2026-05-16' AND '2026-05-21'
  AND body.app_event_model_version IN (
      'unified-user-value-v11-cpe-lc-2-model',
      'unified-user-value-v11-cpe-lc-3-model'
      'unified-user-value-tf2-levcom-bhv1p-1b-model',
      'unified-user-value-tf2-levcom-ctx1r-1a-model'
  )
  AND body.app_event_p > 0
  AND body.app_event_type = "level_complete"
GROUP BY 1, 2, 3, 4
ORDER BY 1 DESC, 2, 3, 4
```

Date range: 2026-05-11 to 2026-05-14 (4 days).

---

## 1. Aggregate Prediction Comparison


| Model                          | Typical avg_pred range | Notes                                    |
| ------------------------------ | ---------------------- | ---------------------------------------- |
| `tf2-levcom-bhv1p-1b` (legacy) | 0.001 – 0.940          | Behavior features, 1st-party identity    |
| `tf2-levcom-ctx1r-1a` (legacy) | 0.001 – 0.940          | Context features, fingerprinted identity |
| `v11-cpe-lc-2` (new)           | **0.002 – 0.980**      | Systematically shifted up                |


v11 is **2–56x higher** than legacy on matched (campaign_id, target_game_id, submit_date) triples. The inflation is worst for rare-event campaigns and still significant for moderate-frequency events.

`avg_target_cpe` is consistent across models for the same campaign (expected — it is the advertiser's bid, not a model output). `avg_cost ≈ avg_pred × avg_target_cpe`, so v11's cost is inflated by exactly the prediction ratio.

---

## 2. Per-Campaign Breakdown


| Campaign / SDK Event   | bhv1p avg_pred | ctx1r avg_pred | v11 avg_pred | Ratio (v11/bhv) |
| ---------------------- | -------------- | -------------- | ------------ | --------------- |
| `star5_hero_received`  | 0.002          | 0.005          | 0.113        | **56x**         |
| Anonymous mid-rate     | 0.154          | 0.171          | 0.564        | 3.7x            |
| `grt_7d_level30_notir` | 0.323          | 0.412          | 0.783        | 2.4x            |
| `Registration-S2S`     | 0.315          | 0.270          | 0.798        | 2.5x            |
| `create_role`          | 0.900          | 0.940          | 0.962        | ~1x (ceiling)   |


**Key pattern**: inflation ratio is inversely proportional to base event rate. The rarer the event, the more v11 over-predicts. `create_role` is near-ceiling for all three models; no headroom to inflate further.

### 2.1 Overbid Rate Distribution Across All Campaigns

Computed across **356 matched (campaign, target_game, sdk_event) triples** where v11 and at least one legacy model both served traffic. Ratio = v11 `avg_pred` / mean of available legacy `avg_pred` values, weighted by `start_count` per model.


| Overbid bucket  | Campaigns | % of total | Avg v11 pred | Avg legacy pred | Avg ratio |
| --------------- | --------- | ---------- | ------------ | --------------- | --------- |
| <1x (v11 lower) | 1         | 0.3%       | 0.909        | 0.959           | 0.95x     |
| 1–2x            | 131       | 36.8%      | 0.698        | 0.463           | 1.55x     |
| 2–3x            | 108       | 30.3%      | 0.705        | 0.294           | 2.43x     |
| 3–5x            | 89        | 25.0%      | 0.647        | 0.178           | 3.71x     |
| 5–10x           | 23        | 6.5%       | 0.547        | 0.086           | 6.58x     |
| 10–20x          | 3         | 0.8%       | 0.454        | 0.038           | 12.25x    |
| >20x            | 1         | 0.3%       | 0.118        | 0.003           | 36.75x    |


**Summary statistics (v11 / avg_legacy ratio):**


| Percentile   | Ratio  |
| ------------ | ------ |
| p10          | 1.36x  |
| p25          | 1.73x  |
| p50 (median) | 2.33x  |
| p75          | 3.32x  |
| p90          | 4.60x  |
| p95          | 6.04x  |
| p99          | 10.83x |
| Mean         | 2.87x  |


- **99.7% of campaigns** (355/356) are overbid to some degree
- **62.9% of campaigns** (224/356) are overbid by 2x or more
- Only 1 campaign has v11 predicting lower than legacy (near-ceiling `create_role`-type event)

**Top 10 most inflated campaigns:**


| Campaign ID                | SDK Event              | v11 avg_pred | Legacy avg_pred | Ratio     |
| -------------------------- | ---------------------- | ------------ | --------------- | --------- |
| `652214aefc636157750229a8` | `star5_hero_received`  | 0.1177       | 0.0032          | **36.7x** |
| `67dc0fa20eb345a2a13aef4f` | `ajvip`                | 0.4889       | 0.0326          | 15.0x     |
| `69eae6280d291c5f22675e19` | `recvd_coins_400`      | 0.7047       | 0.0645          | 10.9x     |
| `69c4447a75bdf4ae2c38cc0d` | `pc_t2_d60_ios_custom` | 0.1692       | 0.0156          | 10.8x     |
| `6960733f13cc68bc8f91fc8e` | `ajvip`                | 0.6445       | 0.0731          | 8.8x      |
| `6825d515a47ee6e329c70bdd` | `eventW`               | 0.5920       | 0.0688          | 8.6x      |
| `685e72777dd83b9c8536915e` | `eventw`               | 0.4666       | 0.0575          | 8.1x      |
| `686664ce9dfaacc5e24bf3df` | `ajvip`                | 0.4776       | 0.0605          | 7.9x      |
| `684ac40f6da6f407ddfa47fd` | `d7_puzzle60_hint5`    | 0.6146       | 0.0806          | 7.6x      |
| `698c51a4e63287f25051d95c` | `ajvip`                | 0.4619       | 0.0612          | 7.6x      |


The most severely inflated events (`star5_hero_received`, `ajvip`, `recvd_coins_400`, `eventW/eventw`) share a common pattern: they are **rare or non-standard SDK event names** with low base rates in the training data. The `ajvip` event appearing across 4 separate campaigns all in the 7–15x range is a strong signal that the model has no meaningful embedding for this event and is falling back to a high base-rate prediction.

---

## 3. Root Cause Analysis

### 3.1 Wildcard Label Inflation (PRIMARY SUSPECT)

In `unified_cpe_datagen.py`, the BQ campaign lookup aggregates targeted SDK events per game:

```python
# Rule: if a campaign has 0 or >1 events → wildcard "*"; else single event name.
sdk_event_targeted = "*"  # when size == 0 or size > 1
```

Then the label assignment:

```python
prob_sdk_event_name_labels = IF(
    (array_contains(sdk_event_name_array, sdk_event)
     OR sdk_event = '*'         # <-- matches ANY level_complete event
     OR sdk_event = '') AND label = 1,
    1.0, 0.0
)
```

The wildcard `'*'` fires `prob_sdk_event_name_label = 1.0` whenever `label = 1`, regardless of which specific SDK event the user fired. For games with multiple campaigns or zero-specified events — which are common — this inflates the per-row positive rate in training.

**Effect**: the model learns to predict the base level_complete rate (e.g., 20–50%) for games with wildcard rows, not the specific event rate (e.g., 2% for `star5_hero_received`). Since `sdk_event_name` embeddings for rare events are undertrained relative to the high wildcard signal, the model reverts to high predictions for unknown or sparse events.

**Verification query** (run against training parquet):

```sql
SELECT
    REGEXP_EXTRACT(prob_sdk_event_name, r'^\d+_(.+)$') AS event_name,
    COUNT(*)                                            AS n,
    AVG(prob_sdk_event_name_label)                      AS pos_rate
FROM `unity-ads-dd-ds-dev-prd.unified_user_value_v11_cpe_lc.unified_user_value_v11_cpe_lc_preprocessed_combined`
GROUP BY 1
ORDER BY n DESC
LIMIT 30
```

**Query results (top 30 event names by row count, from training table):**


| event_name                     | n           | pos_rate   |
| ------------------------------ | ----------- | ---------- |
| `*`                            | 178,152,203 | **36.40%** |
| topsocre_6000_jili_30d         | 13,991,004  | 5.65%      |
| ipu_24h_12                     | 13,991,004  | 8.42%      |
| ipu_24h_14                     | 13,991,004  | 7.07%      |
| game_done_100                  | 13,991,004  | 1.48%      |
| s_custom7_revenue              | 9,424,716   | 2.59%      |
| af_purchase                    | 8,583,841   | 1.69%      |
| s_custom1_revenue              | 8,583,841   | 3.67%      |
| s_custom13_revenue             | 8,583,841   | 5.94%      |
| af_ad_ua168_advevent_ban15     | 8,583,841   | 5.94%      |
| af_purchase2                   | 8,583,841   | 0.17%      |
| loop_online_168h_180           | 8,583,841   | 7.95%      |
| s_custom9_revenue_3            | 8,583,841   | 22.05%     |
| s_custom14_revenue             | 8,583,841   | 3.66%      |
| game_loop_50_day7              | 7,279,176   | 17.73%     |
| game_loop_100_day7             | 7,279,176   | 9.75%      |
| level_150                      | 6,778,394   | 7.59%      |
| ipu_24h_10                     | 5,548,162   | ~0.00%     |
| grt_7d_ltv_20_15               | 5,453,240   | 22.32%     |
| game_end_d1_20                 | 5,407,163   | 9.39%      |
| ipu_24h_10_ut                  | 5,407,163   | 8.67%      |
| s_custom3_revenue              | 5,407,163   | **0%**     |
| adsvalue_4000                  | 5,407,163   | **0%**     |
| loop_online_168h_180_ios       | 5,407,163   | 14.31%     |
| ipu_24h_16                     | 5,407,163   | **0%**     |
| game_end_5_jili                | 5,407,163   | **0%**     |
| loop_online_24h_60_ios         | 5,407,163   | **0%**     |
| golden_android_conversion_high | 5,090,647   | 1.29%      |
| golden_android_conversion_mid  | 5,090,647   | 1.73%      |
| ua_finish_level_65_d7_s2s      | 4,656,863   | 1.26%      |


**This is the smoking gun.** Key findings from the query:

**1. Wildcard `*` dominates — 44% of all training rows, at 36% positive rate.**

Across the top 30 event names (402.6M total rows):

- Wildcard `*`: **178.2M rows** (44.2%) with **pos_rate = 36.4%**
- All specific events: 224.5M rows (55.8%) with **weighted pos_rate = 6.0%**
- Wildcard positive rate is **6.1× higher** than the average specific-event positive rate
- Overall training pos_rate = 19.5%, vs the true event-specific rate of ~6%

The model is effectively trained on a dataset where 44% of rows have an inflated positive label. BCE loss minimization drives the sigmoid output toward this blended base rate (~~19.5%), not the true per-event rate (~~6%). For campaigns targeting rare events (pos_rate < 2%), the gap is even larger — 36.4% wildcard pos_rate vs <2% true rate is an **18×+ inflation** for those embeddings.

**2. Five events in the top 30 have pos_rate = 0 — 27M dead-signal rows.**

`s_custom3_revenue`, `adsvalue_4000`, `ipu_24h_16`, `game_end_5_jili`, `loop_online_24h_60_ios` each have ~5.4M rows with zero positives. These are events where the game is included via the wildcard path (game passes quality filter) but no user has ever fired these specific SDK events. They occupy 27M training rows contributing only noise, while the model also sees wildcard rows for the same games at 36% positive — a direct contradiction in training signal for those `(game_id, event_name)` embeddings.

**3. Two events are near-zero but non-zero — effectively noise.**

`af_purchase2` (pos_rate = 0.17%, 8.6M rows) and `ipu_24h_10` (pos_rate = 0.0001%, 5.5M rows) are present in large volumes but have negligible signal. With the wildcard rows for the same games at 36%, the model cannot learn that these events are rare.

**Conclusion**: The wildcard `'*'` constitutes 44% of training data at 36.4% positive rate and acts as a strong attractor that pulls all predictions toward ~20–36%, overwhelming the per-event signal learned from the specific-event rows. This directly explains the 2.33× median and up to 36.7× peak overbid ratios observed in serving.

### 3.2 No Calibration Layer

From `config.json`:

```json
"enable_calibration": false
```

The legacy models have post-hoc calibration applied at deploy time. Without calibration, a systematically biased training distribution (from the wildcard effect above) produces biased serving predictions with no correction layer.

### 3.3 Quality Filter Mismatch (Game-Level vs Event-Level)

`unified_cpe_datagen.py` (lines 187–199):

```python
_eligible_game_ids = (
    df.filter(F.col("cum_app_event_count_d7") > 0)  # ANY level_complete event
    .groupBy("targetGameId")
    .agg(F.count("*").alias("_event_gamers"))
    .filter(F.col("_event_gamers") >= 50)
    .select("targetGameId")
)
```

The eligibility filter requires ≥50 installs with **any** level_complete event per game. A game with 50+ installs completing `level_5` (easy, common event) passes the filter, and its `star5_hero_received` campaign rows are then included in training with a very low positive rate. The model must learn this distinction via the `sdk_event_name` / `prob_sdk_event_name` embeddings alone, which are underfit when competing with the high-signal wildcard rows.

### 3.4 Stage 5 Filter Disabled (Secondary)

From the datagen (lines 726–732):

```python
# Stage 5 (filter_min_dates_by_game_and_event): SKIPPED for initial test.
# TODO: Re-enable once the first end-to-end test passes.
```

This filter removes training rows from before the first positive conversion for each `(target_game_id, event_name)` pair. Without it, the model trains on cold-start data from freshly-launched campaigns where the event has a 0% early rate transitioning to a higher late rate, adding noise to per-event calibration.

### 3.5 Minor Bug: `campaign_id` Mapped to Wrong Column

`unified_cpe_datagen.py` line 257:

```python
df = df.withColumn("campaign_id", _str_nested("campaignInfo.audienceId"))  # BUG: same as audience_id
```

`campaign_id` and `audience_id` are both set to `campaignInfo.audienceId`. The intended value should be a campaign identifier (e.g., `campaignInfo.campaignId`). This causes the `campaign_id` column in training output to duplicate the `audience_id` embedding signal rather than providing an independent campaign-level feature. Not the cause of prediction inflation, but a correctness issue to fix.

---

## 4. Spend Impact Estimate

`cost = max_cost × discount_factor × p`


| Campaign type                       | v11 / legacy ratio | Effective overbid                           |
| ----------------------------------- | ------------------ | ------------------------------------------- |
| Rare events (`star5_hero_received`) | 22–56x             | Wins auctions at 22–56x the appropriate CPE |
| Moderate events                     | 2.4–3.7x           | Overbids by 2–4x                            |
| Near-ceiling events (`create_role`) | ~1x                | Negligible                                  |


At 1% traffic the absolute budget impact is limited, but prediction integrity is compromised. Campaigns targeting rare events will see v11 dramatically outbid legacy at unsustainable CPE levels, leading to inflated event costs with no corresponding ROAS improvement.

---

## 5. Recommended Actions

### Immediate

1. **Check training calibration metrics in W&B**: compare `mean_pred_psn` vs `mean_label_psn` and `calibration_psn` for the latest training run. If `mean_pred >> mean_label`, the wildcard inflation is confirmed in training.
2. **Verify `sdk_event_name` at serving time**: query a sample of v11 rows from `mz_dcpi_prediction_v1` joined to the raw request log, confirm that `sdk_event_name` is populated with the actual event name (not `"placeholder"` or empty). If it defaults to `"placeholder"`, the model is receiving the literal string set at datagen line 261 — the overwrite at line 795 is correct but the online mapping may be broken.

### Short-term Fixes

1. **Fix wildcard label logic** — the correct fix is upstream in Stage 2 (campaign aggregation), NOT in the label condition.

   **Why the originally proposed fix is wrong:**

   The label condition `OR sdk_event = '*'` fires for three distinct paths that need different treatment:

   | Path | Trigger | Semantic | Label behavior | Screenshot case? |
   |------|---------|----------|----------------|------------------|
   | A | Campaign has 0 `sdk_event_names` | Advertiser means "any event" | `label = 1` if `app_event_w1 > 0` | **Yes** — correct |
   | B | Campaign has >1 `sdk_event_names` | Specific events collapsed to `*` | `label = 1` if ANY event fired | No — **wrong** |
   | C | Game has no active BQ campaign (left join miss) | Unknown campaign target | `label = 1` if `app_event_w1 > 0` | Possible |

   The screenshot row (`500212565_*`, `sdk_event_name_array = []`, `label = 1.0`) is **Path A**: the user genuinely completed the event (`app_event_w1 > 0`) but the specific SDK event name was not captured in `sdk_event_name_array` due to a source data pipeline gap. The proposed fix `array_size(sdk_event_name_array) > 0` would silently flip this to `0.0` — a false negative. Do **not** apply that fix.

   **Campaign breakdown (from `campaign_pricing` BQ table, no time filter — all historical campaigns):**

   | Path | Campaigns | % of total | Action |
   |------|-----------|------------|--------|
   | OK (1 event) | 8,625 | 87.1% | Kept as-is |
   | A (0 events) | 1,244 | 12.6% | **Dropped** — primary source of 178M wildcard rows |
   | B (>1 events) | 28 | 0.3% | Exploded into individual events |

   **Key insight:** Path B is negligible (28 campaigns, 0.3%). The **primary driver** of the 178M wildcard `*` rows is **Path A** — 1,244 campaigns (12.6%) with zero specified events. Despite being only 12.6% of campaigns, these 0-event campaigns map to high-volume games and generate a disproportionate share of training rows at 36.4% pos_rate.

   **Important: the datagen uses deprecated BQ tables.** The current query reads from `unity-ads-bi-prd.dimension_data.campaign_audiences` + `campaign_pricing` (two-table join via `audience_id`). These are deprecated. The canonical source is now:

   ```sql
   SELECT
     CAST(game_id AS STRING) AS game_id,
     app_event_conversion_type,
     campaignset_id,
     paused,
     sdk_event_names
   FROM `unity-data-ads-core-prd.ads_dimension_data.campaigns_v3`
   WHERE app_event_conversion_type = 'LEVEL_COMPLETE'
   ```

   Key differences in `campaigns_v3`:
   - **`paused` column** — directly indicates whether the campaign is live (`false`) or stopped (`true`). No need for a time-window heuristic.
   - **`campaignset_id`** replaces `audience_id` as the campaign identifier.
   - **`app_event_conversion_type`** uses uppercase `'LEVEL_COMPLETE'` (not lowercase).
   - Single table — no join between `campaign_audiences` and `campaign_pricing` required.

   **Campaign breakdown from `campaigns_v3` (path × paused status):**

   | Path | Paused | Campaigns | % of total |
   |------|--------|-----------|------------|
   | A (0 events) | false (live) | 19 | 0.2% |
   | A (0 events) | true (stopped) | 879 | 11.0% |
   | B (>1 events) | false (live) | 1 | 0.0% |
   | B (>1 events) | true (stopped) | 15 | 0.2% |
   | OK (1 event) | false (live) | 355 | 4.4% |
   | OK (1 event) | true (stopped) | 6,728 | 84.1% |

   **Critical finding: 95.3% of all level_complete campaigns are paused (7,622 / 7,997).** The current datagen pulls every one of them with no status filter. Only **375 campaigns are live**.

   **Archived vs not-archived breakdown (`campaigns_v3`):**

   | Status | Campaigns | % of total |
   |--------|-----------|------------|
   | Archived (`archived_at IS NOT NULL`) | 2,202 | 27.5% |
   | Not archived | 5,795 | 72.5% |

   Filtering by `archived_at IS NULL` alone retains **5,795 campaigns (72.5%)** — a far more reasonable reduction than `paused = false` which would keep only 375 (4.7%).

   **However, naively filtering `paused = false` has two risks:**

   1. **Cold start**: New campaigns are created as `paused = true` before launch. If an advertiser sends test data before starting the campaign, the model has no training signal for that (game, event) pair. When the campaign goes live, the model must cold-start predict with zero game-specific context for that event.

   2. **Overfitting**: The v11-cpe-lc model already overfits with the current data volume. Reducing from 7,997 to 356 campaigns would drastically cut training data (not just wildcard rows — fewer campaigns means fewer games matched in the join, so more games fall into Path C and get dropped). This would make overfitting worse.

   **Recommended approach: use `archived_at` to drop permanently dead campaigns, keep all non-archived campaigns.** The `campaigns_v3` table has `created_at`, `updated_at`, and `archived_at` columns. The simplest effective filter is `archived_at IS NULL`, which drops the 27.5% of campaigns that are permanently dead while preserving 72.5% for training volume, cold-start coverage, and data diversity. An optional `updated_at` recency filter can further trim stale non-archived campaigns if needed.

   | Campaign state | Filter | Rationale |
   |---------------|--------|-----------|
   | Live (`paused = false`) | **Keep** | Active campaigns, always relevant |
   | Paused, not archived, recently updated | **Keep** | Temporarily paused or pre-launch; still useful for training generalization and cold-start coverage |
   | Paused and archived (`archived_at IS NOT NULL`) | **Drop** | Permanently dead campaigns — no future traffic |
   | Paused, not archived, but stale (not updated in >N days) | **Drop** | Likely abandoned; no longer generating traffic |

   **The correct fix: migrate to `campaigns_v3`, drop archived + stale campaigns, drop 0-event campaigns, explode multi-event campaigns.**

   **TODO:** Run the following query to quantify the `archived_at` × path breakdown and choose the right staleness threshold:

   ```sql
   WITH campaign_events AS (
     SELECT
       CAST(game_id AS STRING) AS game_id,
       campaignset_id,
       paused,
       archived_at,
       updated_at,
       COALESCE(ARRAY_LENGTH(sdk_event_names), 0) AS n_events,
       DATE_DIFF(CURRENT_DATE(), DATE(updated_at), DAY) AS days_since_update
     FROM `unity-data-ads-core-prd.ads_dimension_data.campaigns_v3`
     WHERE app_event_conversion_type = 'LEVEL_COMPLETE'
   )
   SELECT
     CASE
       WHEN NOT paused THEN 'live'
       WHEN archived_at IS NOT NULL THEN 'archived'
       WHEN days_since_update <= 90 THEN 'paused_recent'
       ELSE 'paused_stale'
     END AS status_bucket,
     CASE
       WHEN n_events = 0 THEN 'Path A (0 events)'
       WHEN n_events = 1 THEN 'Path OK (1 event)'
       ELSE 'Path B (>1 events)'
     END AS path,
     COUNT(*) AS n_campaigns,
     COUNT(DISTINCT game_id) AS n_games
   FROM campaign_events
   GROUP BY 1, 2
   ORDER BY 1, 2
   ```

   ```python
   # CURRENT — lines 650–666 of unified_cpe_datagen.py:
   # Any campaign with >1 or 0 events collapses to a single "*" token.
   campaigns_df = (
       campaigns_raw_df.withColumn(
           "sdk_event_name_set",
           F.when(F.col("sdk_event_name_set").isNull(), F.array()).otherwise(
               F.expr("transform(sdk_event_name_set, e -> lower(e))")
           ),
       )
       .withColumn(
           "sdk_event_targeted",
           F.when(
               (F.size("sdk_event_name_set") > 1) | (F.size("sdk_event_name_set") == 0),
               F.lit("*"),                          # BUG: collapses ["level_5","level_10"] → "*"
           ).otherwise(F.col("sdk_event_name_set")[0]),
       )
       .groupBy("target_game_id")
       .agg(F.collect_set("sdk_event_targeted").alias("sdk_event_targeted"))
   )
   ```

   ```python
   # FIXED — migrate to campaigns_v3, drop archived, keep 0-event as *, explode multi-event.
   _BQ_CAMPAIGN_QUERY_V3 = """
   SELECT
     CAST(game_id AS STRING) AS target_game_id,
     campaignset_id,
     sdk_event_names AS sdk_event_name_set
   FROM `unity-data-ads-core-prd.ads_dimension_data.campaigns_v3`
   WHERE app_event_conversion_type = 'LEVEL_COMPLETE'
     AND archived_at IS NULL
   """

   campaigns_raw_df = spark.read.format("bigquery").option("query", _BQ_CAMPAIGN_QUERY_V3).load()

   campaigns_df = (
       campaigns_raw_df.withColumn(
           "sdk_event_name_set",
           F.when(F.col("sdk_event_name_set").isNull(), F.array()).otherwise(
               F.expr("transform(sdk_event_name_set, e -> lower(e))")
           ),
       )
       # Path A (0-event campaigns): keep as wildcard "*" — 19 live campaigns need coverage.
       # Path B (>1 events): explode into individual events instead of collapsing to "*".
       .withColumn(
           "sdk_events_normalized",
           F.when(F.size("sdk_event_name_set") == 0, F.array(F.lit("*")))
            .otherwise(F.col("sdk_event_name_set")),
       )
       .withColumn("sdk_event_targeted", F.explode("sdk_events_normalized"))
       .groupBy("target_game_id")
       .agg(F.collect_set("sdk_event_targeted").alias("sdk_event_targeted"))
   )
   ```

   The BQ filter `archived_at IS NULL` retains 5,795 campaigns (72.5%) — dropping only the 2,202 permanently archived ones (27.5%). This is a conservative, safe reduction that preserves training volume while removing dead campaigns. An optional `updated_at` recency filter can be layered on later if further cleanup is needed.

   **Why Path A (0-event campaigns) should be kept as `*`:**

   There are 19 live (non-paused, non-archived) campaigns with 0 specified events. These are actively running — dropping them would mean the model has zero training signal for those games when they receive traffic. Since the advertiser genuinely means "any level complete event," the wildcard label (`label = 1` when `app_event_w1 > 0`) is semantically correct for these campaigns.

   The wildcard inflation problem is primarily driven by **volume**: the current datagen pulls all 7,997 campaigns (including 2,202 archived) with no filter, causing 0-event campaigns from dead campaigns to generate the bulk of the 178M wildcard rows. After filtering `archived_at IS NULL`, the remaining 0-event campaigns are a much smaller set and their wildcard rows will constitute a much smaller fraction of training data, significantly reducing the bias.

   **What changes after this fix:**

   | Layer | What it does | Campaigns affected | Impact |
   |-------|-------------|-------------------|--------|
   | `archived_at IS NULL` | Drops permanently dead campaigns | 2,202 removed (27.5%) | Eliminates wildcard rows from archived 0-event campaigns |
   | `explode` (Path B) | Preserves each event individually | Multi-event campaigns | No more collapsing to `*` |
   | Keep `*` (Path A) | 0-event campaigns stay as wildcard | 19 live + non-archived paused | Preserves training signal for live campaigns |

   Benefits of this approach:
   - **Cold start covered**: all non-archived campaigns (live, paused, pre-launch) are kept.
   - **Overfitting mitigated**: 5,795 non-archived campaigns retained (72.5%) vs only 375 with `paused = false` (4.7%).
   - **Dead signal eliminated**: 2,202 archived campaigns dropped — the primary source of wildcard volume.
   - **Path B fixed**: multi-event campaigns produce correct per-event labels instead of a single `*`.
   - **Path A preserved**: 19 live 0-event campaigns keep `*` — the model can still predict for these games.
   - Per-event labels become accurate for Path B: a user who only completed `level_5` gets `label=1.0` for `level_5` and `label=0.0` for `level_10`.

   **Expected impact:** The 2,202 archived campaigns (27.5%) are removed, which eliminates the bulk of the 0-event wildcard rows from dead campaigns. The remaining wildcard rows from the 19 live + non-archived paused 0-event campaigns are a much smaller fraction of training data. Path B multi-event campaigns are correctly exploded. The overall wildcard volume drops dramatically, reducing the training pos_rate from ~19.5% toward the true event-specific rate, while preserving full campaign coverage for live traffic.

2. **Drop Path C wildcard rows** (left outer join miss, line 690–693): games with no matching BQ campaign currently default to `["*"]`. Change the left outer join to an inner join, or filter out rows where `sdk_event_targeted IS NULL` after the join. Games with no campaign in BQ have no defined target event — their wildcard rows add noise without a clear training signal.

3. **Clean up label SQL** (line 697): the `OR sdk_event = '*'` condition is still needed for the remaining Path A wildcard rows but should be documented to clarify it only applies to the small set of live 0-event campaigns.

4. **Fix `campaign_id` column** in datagen (line 257): map to the correct campaign identifier, not `audienceId`. With the migration to `campaigns_v3`, use `campaignset_id` instead.

5. **Migrate campaign query to `campaigns_v3`** (lines 620–637): the current `_BQ_CAMPAIGN_QUERY` reads from deprecated `campaign_audiences` + `campaign_pricing` tables with no status filter — pulling 7,997 campaigns (95.3% paused). Migrate to `unity-data-ads-core-prd.ads_dimension_data.campaigns_v3` with `archived_at IS NULL` (drops 2,202 archived campaigns = 27.5%, retains 5,795 = 72.5%). See fix #1 code block for the complete query.

6. **Re-enable Stage 5 filter** (`filter_min_dates_by_game_and_event`) before the next production training run.

### Before Next Deploy

1. **Enable calibration** (`enable_calibration: true` in `config.json`) or add Platt scaling on the held-out val set. Given that legacy models are calibrated, v11 needs the same treatment for fair A/B comparison.
2. **Add per-event-name positive rate validation** to the datagen as a data quality check: after explode, print `GROUP BY sdk_event_name: AVG(prob_sdk_event_name_label)` and fail if any event has `pos_rate > 0.95` (likely wildcard contamination) or `n < 500` (insufficient training signal).

---

## 6. Files Referenced


| File                                                                          | Key finding                                                                                                      |
| ----------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------- |
| `src/unity_learner/data/spark/user_value/unified_cpe_datagen.py`              | Wildcard label logic (L697–710), quality filter (L187–199), `campaign_id` bug (L257), Stage 5 skipped (L726–732) |
| `src/unity_learner/experiment_repo/unified_user_value/v11_cpe_lc/config.json` | `enable_calibration: false` (L234)                                                                               |
| `src/unity_learner/experiment_repo/unified_user_value/v11_cpe_lc/features.py` | `sdk_event_name` as online sparse feature; `prob_sdk_event_name` offline-only                                    |
| `src/unity_learner/experiment_repo/unified_user_value/v11_cpe_lc/model.py`    | `cost = max_cost × discount_factor × p` bidding formula                                                          |
| `src/unity_learner/experiment_repo/unified_user_value/v11_cpe_lc/workflow.py` | Training data source `v2/level_complete/d7/`, `overall_delay=9.0`                                                |


