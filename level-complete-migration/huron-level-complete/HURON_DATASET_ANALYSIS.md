# Huron Level Complete Dataset Analysis

**Table**: `unity-data-prd.attribution_l2.mmp_primary_conversion_custom_outcome_join_v1alpha14_single_table_test`
**Date**: 2026-06-02
**Author**: Yabo Ling
**Status**: Active investigation — this document covers the v1alpha14 test table

---

## 1. What is Huron and This Table?

**Huron** is Unity's internal MMP (Mobile Measurement Partner) data ingestion framework. Unlike the legacy pipeline which was a bespoke Unity-internal event system, Huron standardizes post-install events coming from external MMPs (e.g., AppsFlyer, Adjust) into unified Iceberg tables in BQ.

### Table identity

```
Project:   unity-data-prd
Dataset:   attribution_l2
Table:     mmp_primary_conversion_custom_outcome_join_v1alpha14_single_table_test
Storage:   Apache Iceberg (gs://unity-dws-prd/iceberg/attribution_l2/...)
BQ type:   EXTERNAL (via huron-iceberg-connection)
Label:     job_name=custom-event-ioj-single-table-test, om_layer=l2, om_team=attribution
```

The name decodes as:
- `mmp_primary_conversion` — MMP-attributed install events (the "primary conversion" = the install itself)
- `custom_outcome_join` — joined with custom post-install outcome events (level_complete, purchases, etc.)
- `v1alpha14` — version alpha 14 (still in alpha/test iteration)
- `single_table_test` — test of a **unified single-table design** that combines ALL custom event types in one table (vs legacy separate tables per event type like `level_complete/d7/`)

---

## 2. Infrastructure Differences from Legacy

| Aspect | Legacy GCS Path | Huron BQ Table |
|--------|----------------|----------------|
| **Storage format** | Parquet on GCS | Apache Iceberg on GCS, BQ external table |
| **Access** | Spark reads from GCS directly | BQ SQL or Spark via BQ connector |
| **Event scope** | Level-complete events ONLY (`level_complete/d7/`) | ALL custom event types in one table |
| **Pre-filter** | Installs with `app_event_w1 > 0` (LC positives only) | Pre-filtered to installs that fired ANY custom event |
| **Partition key** | `installDate=YYYY-MM-DD` (GCS prefix) | `partition_date` DATE column (REQUIRED filter) |
| **Partition filter** | None required | `requirePartitionFilter = true` — **must specify `partition_date`** |
| **Row structure** | One row per install | One row per install per `partition_date` |
| **Feature + label** | Self-contained (features + labels) | **Labels only** — no install features |

### Critical difference: this is a label-side table only

The legacy GCS path was a self-contained training dataset with both features and labels. The Huron L2 table contains **only outcome metrics** — no `platform`, `advertiser_game_id`, `gamer_id`, or any user/game features. Building a training dataset requires joining with install feature tables on `event_id`.

---

## 3. Schema Overview

The table has **247 columns** organized into these groups:

### 3.1 Identity & attribution (13 columns)

| Column | Type | Description |
|--------|------|-------------|
| `event_id` | STRING REQUIRED | UUID — the MMP primary conversion (install) event ID. **Primary key**. Unique per partition. |
| `partition_date` | DATE REQUIRED | Partition key ≈ install date (~98.8% of rows have `install_time` date = `partition_date`) |
| `install_time` | TIMESTAMP | When the install occurred. Always equals `event_timestamp` in this table. |
| `event_timestamp` | TIMESTAMP | Same as `install_time` — the install event time |
| `is_attributed` | BOOLEAN | **True = Unity-attributed install** (5.4–5.8% of rows). This is the population analogous to legacy BHV+CTX. |
| `attribution_id_match` | BOOLEAN | Unity attribution ID matched the MMP event |
| `attribution_partner_user_match` | BOOLEAN | MMP user ID matched (90.96% of rows — broader than Unity attribution) |
| `idfa_user_match` | BOOLEAN | IDFA matched |
| `store_id_match` | BOOLEAN | App store ID matched |
| `bundle_id_match` | BOOLEAN | Bundle ID matched |
| `install_time_match` | BOOLEAN | Install timestamp matched |
| `reattribution_time_match` | BOOLEAN | Reattribution time matched |
| `reinstall_time_match` | BOOLEAN | Reinstall time matched |
| `advertiser_game_id_match` | BOOLEAN | Advertiser game ID was present and matched |

### 3.2 Custom event metrics d0–d28 (4 × 29 = 116 columns)

Tracks **any custom event** (not LC-specific) across a 28-day attribution window:

| Pattern | Type | Semantics |
|---------|------|-----------|
| `cum_has_event_d{N}` | INTEGER NULLABLE | Cumulative binary: did user fire ANY custom event by day N since install? (0 or 1) |
| `cum_event_count_d{N}` | INTEGER NULLABLE | Cumulative count of all custom events fired by day N |
| `event_count_d{N}` | INTEGER NULLABLE | Count of custom events fired ON day N specifically (non-cumulative) |
| `has_event_d{N}` | INTEGER NULLABLE | Binary: fired any custom event ON day N specifically |

N ranges from 0 to 28.

### 3.3 Level-complete (LC) specific metrics d0–d28 (4 × 29 = 116 columns)

Same structure as above but filtered to level-complete events only:

| Pattern | Type | Semantics |
|---------|------|-----------|
| `cum_has_lc_event_d{N}` | INTEGER NULLABLE | Cumulative binary: did user fire any LC event by day N? **→ This is the training label** |
| `cum_lc_event_count_d{N}` | INTEGER NULLABLE | Cumulative count of LC events fired by day N |
| `lc_event_count_d{N}` | INTEGER NULLABLE | LC events fired ON day N |
| `has_lc_event_d{N}` | INTEGER NULLABLE | Binary: fired LC event ON day N |

### 3.4 SDK event arrays (2 REPEATED RECORD columns)

| Column | Structure | Description |
|--------|-----------|-------------|
| `sdk_event_name_first_seen_arr` | ARRAY of `{sdk_event_name STRING, first_seen_at TIMESTAMP}` | All custom events fired by the user with the first time each was seen |
| `sdk_event_name_first_seen_arr_lc` | ARRAY of `{sdk_event_name STRING, first_seen_at TIMESTAMP}` | Same but **LC events only** — the SDK event names the user actually fired |

Special value: `_no_sdk_event_name` = a level_complete fired but without a named SDK event.

---

## 4. Data Statistics (partition_date = 2026-05-20)

### 4.1 Row counts and partitions

The table has **41 continuous daily partitions** from **2026-04-19 to 2026-05-29** with no gaps.

| partition_date | row_count | Phase |
|----------------|-----------|-------|
| 2026-04-19 | 7,868 | Pipeline cold start |
| 2026-04-20 | 280,883 | |
| 2026-04-21 | 578,813 | |
| 2026-04-22 | 752,347 | |
| 2026-04-23 | 931,221 | |
| 2026-04-24 | 1,107,895 | |
| 2026-04-25 | 1,348,973 | |
| 2026-04-26 | 1,478,935 | |
| 2026-04-27 | 1,445,059 | |
| 2026-04-28 | 1,576,997 | |
| 2026-04-29 | 1,689,134 | |
| 2026-04-30 | 1,818,971 | |
| 2026-05-01 | 2,076,152 | Slow ramp (~2–3M/day) |
| 2026-05-02 | 2,175,682 | |
| 2026-05-03 | 2,259,122 | |
| 2026-05-04 | 2,064,788 | |
| 2026-05-05 | 2,369,419 | |
| 2026-05-06 | 2,430,424 | |
| 2026-05-07 | 2,461,290 | |
| 2026-05-08 | 2,670,631 | |
| 2026-05-09 | 3,049,861 | |
| 2026-05-10 | 3,254,950 | |
| 2026-05-11 | 3,195,077 | Fast ramp (3–9M/day) |
| 2026-05-12 | 3,638,912 | |
| 2026-05-13 | 4,016,465 | |
| 2026-05-14 | 4,522,033 | |
| 2026-05-15 | 4,995,030 | |
| 2026-05-16 | 5,861,617 | |
| 2026-05-17 | 7,617,175 | |
| 2026-05-18 | 8,779,170 | |
| **2026-05-19** | **18,383,549** | **Stable (~18–20M/day)** |
| 2026-05-20 | 18,174,345 | |
| 2026-05-21 | 18,501,724 | |
| 2026-05-22 | 18,863,853 | |
| 2026-05-23 | 20,133,384 | |
| 2026-05-24 | 20,522,341 | |
| 2026-05-25 | 18,531,457 | |
| 2026-05-26 | 18,484,952 | |
| 2026-05-27 | 18,115,621 | Attribution window incomplete |
| 2026-05-28 | 16,532,102 | |
| 2026-05-29 | 172 | Partial snapshot |

The progressive ramp from 7K → 20M rows/day reflects **pipeline onboarding**, not real traffic growth. Stable full-volume data starts **2026-05-19**.

**Partition structure**: ~98.8% of rows have `install_time` date = `partition_date`. A small trickle (~1.2%) from prior days appears in later partitions (late-arriving data). Always query by `partition_date`.

### 4.2 Attribution breakdown (2026-05-20)

| Population | Row count | % of total |
|-----------|-----------|------------|
| `is_attributed = true` (Unity-attributed) | 992,072 | **5.46%** |
| `attribution_partner_user_match=true, store_id_match=true` | 16,530,762 | **90.96%** |
| `idfa_user_match=true, store_id_match=true` | 643,292 | 3.54% |

The 90.96% majority with `attribution_partner_user_match` appears to be MMP-reported conversions that are associated with Unity campaigns via user ID matching but not necessarily Unity-attributed by primary attribution. The `is_attributed=true` rows (~5.46%) are the Unity-attributed population directly comparable to the legacy BHV+CTX training data.

### 4.3 Label rates (2026-05-20, full partition)

| Label | Rate | Notes |
|-------|------|-------|
| Any custom event by d7 (`cum_has_event_d7 > 0`) | **99.66%** | Table is pre-filtered to custom event firers |
| Any LC event by d0 (`cum_has_lc_event_d0 > 0`) | 43.30% | |
| Any LC event by d1 | 46.82% | |
| Any LC event by d3 | 49.52% | |
| Any LC event by d7 (`cum_has_lc_event_d7 > 0`) | **52.21%** | Primary label column |
| Any LC event by d14 | 52.42% | |
| Any LC event by d28 | 52.44% | d7 captures ~99.6% of eventual LC converters |
| 47.56% of installs have zero LC events at d28 | — | Non-LC converters (fired other custom events) |

**For Unity-attributed rows only (`is_attributed=true`)**:

| Label | Rate |
|-------|------|
| Any LC event by d0 | 28.86% |
| Any LC event by d7 | **35.75%** |
| Has LC events in `sdk_event_name_first_seen_arr_lc` | 36.31% |

**The 35.75% attributed LC rate matches the legacy BHV/CTX rate of ~36–37%.** This confirms `is_attributed=true` is the correct filter to get the population comparable to legacy training data.

### 4.4 LC SDK event name distribution (2026-05-20, arr_lc unnested)

**5,000 distinct LC SDK event names**, 25.5M total occurrences across 18.2M installs.

Top events by install reach:

| Event Name | Installs with Event | % of Total |
|-----------|---------------------|------------|
| `af_bs_conversion_rt` | 1,939,604 | 10.67% |
| `2d_rr_user` | 1,519,424 | 8.36% |
| `d2_rr_user_rt` | 1,485,631 | 8.17% |
| `_no_sdk_event_name` | 1,204,007 | 6.62% |
| `tt_login_rt` | 894,432 | 4.92% |
| `mus_af_post_video` | 701,720 | 3.86% |
| `af_pltv_lt7_ug_v2_deeplt` | 534,662 | 2.94% |
| `Level3` | 223,126 | 1.23% |
| `af_level_achieved` | 144,731 | 0.80% |
| `Level5` | 145,257 | 0.80% |
| `10_games_played` | 151,286 | 0.83% |

Avg LC events per attributed install: **0.948** (slightly less than 1 per install).

### 4.5 LC label trend over time

LC rate at d7 grows as more days pass since install (attribution window filling in):

| partition_date | Rows | Attributed % | LC rate d7 (all) | LC rate d7 (attributed only) |
|---------------|------|-------------|-----------------|------------------------------|
| 2026-05-01 | 2.1M | 3.29% | 0.41% | 0.53% |
| 2026-05-10 | 3.3M | 3.62% | 0.87% | 1.13% |
| 2026-05-11 | 3.2M | 3.80% | **16.39%** | 13.70% |
| 2026-05-19 | 18.4M | 5.60% | 51.87% | 35.28% |
| 2026-05-20 | 18.2M | 5.46% | 52.21% | 35.75% |
| 2026-05-27 | 18.1M | 5.64% | 49.60% | 31.49% |
| 2026-05-28 | 16.5M | 5.84% | 46.72% | 28.19% |

**Key insight**: The LC rate drop for May 27–28 reflects incomplete 7-day attribution windows (7 days after May 28 = June 4, which is in the future). Use **only partitions ≥ 9 days old** (7-day label + 2-day buffer) to avoid label bias — same rule as the legacy pipeline. The sharp jump on May 11 vs May 10 is a pipeline rollout artifact.

---

## 5. Label Column Mapping: Legacy → Huron

| Legacy column | Legacy semantics | Huron column | Notes |
|--------------|-----------------|--------------|-------|
| `label` | `(app_event_w1 > 0)` — any LC in 7 days | `cum_has_lc_event_d7 > 0` | Same semantics |
| `app_event_w1` (count) | LC event count in 7 days | `cum_lc_event_count_d7` | |
| `app_event_d0` | Any LC on install day | `has_lc_event_d0` (or `cum_has_lc_event_d0`) | |
| `app_event_d1` | Any LC by day 1 | `cum_has_lc_event_d1` | |
| `app_event_d3` | Any LC by day 3 | `cum_has_lc_event_d3` | |
| `app_event_d7` | Any LC by day 7 | `cum_has_lc_event_d7` | |
| `app_event_count_w1` | LC event count in 7 days | `cum_lc_event_count_d7` | |
| `cum_app_event_count_d7` | Cumulative LC count at d7 | `cum_lc_event_count_d7` | |
| `sdk_event_name_array` | Stringified array of LC events fired | `sdk_event_name_first_seen_arr_lc` | Now a proper REPEATED RECORD with timestamps |
| `installDate` partition | Install date | `partition_date` | Same concept |
| `prob_sdk_event_name_label` | 1 if user fired specific targeted SDK event | Derived from `sdk_event_name_first_seen_arr_lc` | Need to check if sdk_event in arr_lc |

### New label capabilities in Huron (not in legacy)

| New column | Description |
|-----------|-------------|
| `cum_has_lc_event_d{0..28}` | Full d0–d28 horizon (legacy only had w1/w2/w3/w4 which were all identical) |
| `lc_event_count_d{N}` | Daily (non-cumulative) LC event count per day |
| `sdk_event_name_first_seen_arr_lc` | SDK event names WITH timestamps — enables cold-start filtering (`filter_min_dates_by_game_and_event`) |
| `cum_has_event_d{N}` | Non-LC custom event metrics — enables joint multi-task training if needed |

---

## 6. Key Differences from Legacy for Model Training

### 6.1 What Huron provides (vs legacy)

| Aspect | Legacy GCS path | Huron L2 table |
|--------|----------------|----------------|
| **Label column** | Binary `label` (0/1) | `cum_has_lc_event_d7` (INTEGER 0/1) |
| **Time horizons** | d0/d1/d3/d7 + w1/w2/w3/w4 (all w's identical) | d0–d28 for both LC and non-LC events |
| **SDK event names** | String array (no timestamps) | REPEATED RECORD with `first_seen_at` timestamps |
| **Non-LC events** | Not tracked | `cum_has_event_d{N}`, `event_count_d{N}` for any custom event |
| **Attribution quality** | All rows are Unity-attributed | Mix — filter `is_attributed=true` for Unity population |
| **Pre-filter** | LC positives only | Any custom event fires |
| **Features included** | Yes — self-contained | **No** — labels only, requires join for features |

### 6.2 Training data construction workflow

The Huron table is **label-side only**. To build training data equivalent to the legacy GCS path:

```sql
-- Step 1: Get installs with labels from Huron
-- Filter: Unity-attributed, >= 9 days old for complete attribution
SELECT
  event_id,
  partition_date AS install_date,
  CAST(cum_has_lc_event_d7 > 0 AS INT64) AS label,        -- primary LC label
  cum_lc_event_count_d7                                    AS app_event_count_w1,
  cum_has_lc_event_d0, cum_has_lc_event_d1,
  cum_has_lc_event_d3, cum_has_lc_event_d7,               -- multi-horizon labels
  sdk_event_name_first_seen_arr_lc                         -- SDK events array
FROM `unity-data-prd.attribution_l2.mmp_primary_conversion_custom_outcome_join_v1alpha14_single_table_test`
WHERE partition_date = '<target_date>'
  AND is_attributed = true                                 -- Unity-attributed only

-- Step 2: Join with install features table (TBD — what replaces legacy AGC features?)
-- Expected join key: event_id = install event ID
```

### 6.3 The `prob_sdk_event_name_label` equivalent

In the current UL datagen, `prob_sdk_event_name_label` is derived per `(install × targeted_sdk_event)`. The equivalent from Huron would be:

```sql
-- Check if targeted event is in the LC event array
ARRAY_LENGTH(
  ARRAY(
    SELECT sdk_event_name
    FROM UNNEST(sdk_event_name_first_seen_arr_lc) AS e
    WHERE e.sdk_event_name = '<targeted_event_name>'
  )
) > 0 AS prob_sdk_event_name_label
```

Or equivalently using the `has_lc_event_d7` if the event tracking is aggregate (not per SDK event name).

**Note**: The `sdk_event_name_first_seen_arr_lc` contains ALL LC event names fired (not just the ones targeted by a campaign). The per-campaign targeting logic (which events to look for) still needs to come from `campaigns_v3` or equivalent.

---

## 7. Open Questions for Data Team

| # | Question | Impact |
|---|----------|--------|
| 1 | What table contains install-side features (`platform`, `advertiser_game_id`, `gamer_id_scope`, AGC counters)? What is the join key — is it `event_id`? | **Critical** — cannot build training data without this |
| 2 | What does `attribution_partner_user_match=true, is_attributed=false` mean? (90.96% of rows) — are these Unity-influenced but not attributed installs? | High |
| 3 | Why does `cum_has_event_d7 = 99.66%`? Is the table pre-filtered to custom event firers, or is this a coincidence of the test population? | High — affects positive rate interpretation |
| 4 | What is the intended `partition_date` semantics — is this the event ingestion date or the install date? (Currently ~98.8% same, but trickle of late-arriving events) | Medium |
| 5 | What is the production timeline for graduating from `v1alpha14_single_table_test` to a stable production table? | Medium |
| 6 | What event types are included in the non-`_lc_` columns? Is it ALL custom SDK events or specific types? | Medium |
| 7 | Does the `_no_sdk_event_name` (6.62% of LC events) map to the legacy `empty_array` / unnamed LC pattern? | Low |

---

## 8. Starter BQ Queries

```sql
-- 1. Row counts by partition (always specify partition_date range)
SELECT partition_date, COUNT(*) AS row_count
FROM `unity-data-prd.attribution_l2.mmp_primary_conversion_custom_outcome_join_v1alpha14_single_table_test`
WHERE partition_date BETWEEN '2026-05-01' AND '2026-05-28'
GROUP BY 1 ORDER BY 1;

-- 2. Label stats for a stable partition (use partitions >= 9 days old)
SELECT
  COUNT(*) AS total,
  COUNTIF(is_attributed) AS attributed,
  ROUND(COUNTIF(is_attributed AND cum_has_lc_event_d7 > 0) * 100.0
        / NULLIF(COUNTIF(is_attributed), 0), 2) AS lc_rate_attributed,
  ROUND(COUNTIF(cum_has_lc_event_d7 > 0) * 100.0 / COUNT(*), 2) AS lc_rate_all
FROM `unity-data-prd.attribution_l2.mmp_primary_conversion_custom_outcome_join_v1alpha14_single_table_test`
WHERE partition_date = '2026-05-20';

-- 3. SDK LC event name distribution
SELECT
  e.sdk_event_name,
  COUNT(*) AS installs,
  ROUND(COUNT(*) * 100.0 / (SELECT COUNT(*) FROM `unity-data-prd.attribution_l2.mmp_primary_conversion_custom_outcome_join_v1alpha14_single_table_test`
                              WHERE partition_date = '2026-05-20' AND is_attributed = true), 2) AS pct_attributed
FROM `unity-data-prd.attribution_l2.mmp_primary_conversion_custom_outcome_join_v1alpha14_single_table_test`,
UNNEST(sdk_event_name_first_seen_arr_lc) AS e
WHERE partition_date = '2026-05-20' AND is_attributed = true
GROUP BY 1 ORDER BY 2 DESC LIMIT 30;

-- 4. Multi-horizon label progression
SELECT
  ROUND(AVG(COALESCE(cum_has_lc_event_d0, 0)) * 100, 2) AS d0,
  ROUND(AVG(COALESCE(cum_has_lc_event_d1, 0)) * 100, 2) AS d1,
  ROUND(AVG(COALESCE(cum_has_lc_event_d3, 0)) * 100, 2) AS d3,
  ROUND(AVG(COALESCE(cum_has_lc_event_d7, 0)) * 100, 2) AS d7,
  ROUND(AVG(COALESCE(cum_has_lc_event_d14, 0)) * 100, 2) AS d14,
  ROUND(AVG(COALESCE(cum_has_lc_event_d28, 0)) * 100, 2) AS d28
FROM `unity-data-prd.attribution_l2.mmp_primary_conversion_custom_outcome_join_v1alpha14_single_table_test`
WHERE partition_date = '2026-05-20' AND is_attributed = true;

-- 5. Check if event_id matches the legacy install event ID (join test with IOJ)
-- Replace with actual join table path
SELECT h.event_id, h.install_time, h.cum_has_lc_event_d7
FROM `unity-data-prd.attribution_l2.mmp_primary_conversion_custom_outcome_join_v1alpha14_single_table_test` h
WHERE partition_date = '2026-05-20'
LIMIT 5;
```

---

## 9. Summary: What Changes for v12_cpe_lc (Next Model)

If we migrate the training data source from GCS to Huron:

| Change | Details |
|--------|---------|
| **Label column** | `label = CAST(cum_has_lc_event_d7 > 0 AS INT64)` (same semantics as current `app_event_w1 > 0`) |
| **Attribution filter** | Add `WHERE is_attributed = true` to match legacy BHV+CTX population |
| **SDK event name join** | `sdk_event_name_first_seen_arr_lc` replaces `sdk_event_name_array` — unnest and check |
| **Multi-horizon labels** | Use `cum_has_lc_event_d{0,1,3,7,14,28}` — much richer than legacy |
| **UUPS integration** | Still not present in Huron L2 — still needs separate join from UUPS pipeline |
| **Feature join** | New requirement — need to identify the install-feature table to join on `event_id` |
| **Row expansion** | Huron is pre-install-level; still need campaign join + explode by `sdk_event_targeted` in datagen |
| **Pre-filter behavior** | Remove the legacy `installs.outcomes.v2/level_complete/d7/` source path; add `is_attributed=true` filter |
| **Label bias mitigation** | Same 9-day lag rule applies (partition_date must be >= 9 days before training cutoff) |
