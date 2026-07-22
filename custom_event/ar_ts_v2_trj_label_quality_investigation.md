# ar_ts v2 TRJ — Label Quality Investigation

**Dataset:** `gs://data-ads-app-prd/roas/ads.events.operativeecpm.installs.outcomes.profile.join.primary_conversion_enriched_profiles_v2/d28/`
**BQ exploration table (pre-normalization, Huron naming):** `unity-feature-platform-prd.ads_feature_platform_paimon.mmp_post_install_optimization_training_v2`
**Install dates validated:** 2026-06-01 to 2026-06-06 (d28 gamer_age only)
**Investigation date:** 2026-07-20
**Reference doc:** `FP ar_ts v2 → TRJ_ Data, Schema, Transformations & Validation — FINAL (Modeling).md`

---

## 0. Context and Scope

This document investigates label quality in the first TRJ delivery of the `ar_ts v2` pipeline. The TRJ is the **Parquet export** (Snappy-compressed) produced by the Spark export job. The BQ table `mmp_post_install_optimization_training_v2` contains the same rows but with **Huron naming** (pre-normalization) and is used only for SQL exploration.

### What is new vs previous BQ analysis

Previous label quality work (see `mmp_post_install_optimization_training_v2_analysis.md` and `label_quality.md`) analyzed the BQ table directly. The ar_ts v2 TRJ introduces four structural differences that require fresh label quality checks:

| Dimension | Previous BQ analysis | ar_ts v2 TRJ (Parquet) |
|---|---|---|
| **Label naming** | Huron: `cum_purchaser_dx`, `purchase_count_dx` | Legacy: `cum_depositor_dx`, `deposit_count_dx` (55 renames + 232 metric renames) |
| **Population scope** | Both attributed and unattributed rows | Effectively attributed-only (ad-request features exist only for attributed installs; §A method note) |
| **Gamer age** | All gamer ages (d0–d28) | d28 only in this delivery; d0–d21 not populated for 2026-06-01 to 2026-06-06 |
| **Dropped columns** | `partition_date`, `process_date` present | Dropped in Parquet; replaced by `gamer_age` + `install_date` partition keys |

### Label block layout (1,100 total columns)

| Block | Cols | Location | Naming in Parquet |
|---|---|---|---|
| Prejoin features | 634 | Both anchors (install + ad-request) × FSGW / AGC / UUPS | Symmetric `*_install_based_*` ∥ `*_ad_request_based_*` structs |
| IOJ labels | 232 | Top-level columns | Legacy: `cum_depositor_d{0..28}`, `deposit_count_d{0..28}`, etc. |
| Custom-event outcomes | 234 | Top-level columns | Consistent with BQ `cum_has_event_dx`, `cum_has_lc_event_dx`, etc. |

---

## 1. IOJ Label Block (232 columns)

### 1A. Column mapping: Huron → Legacy rename

The Spark export job renames all purchase/depositor columns at write time (§6B). When writing BQ exploration queries, use the **Huron (source) names**; the Parquet files contain the **legacy (target) names**.

| Pattern | BQ / Huron name | Parquet / Legacy name | Count |
|---|---|---|---|
| 1 | `cum_purchaser_d{0..28}` | `cum_depositor_d{0..28}` | 29 |
| 2 | `cum_nonzero_purchaser_d{0..28}` | `cum_nonzero_depositor_d{0..28}` | 29 |
| 3 | `purchase_count_d{0..28}` | `deposit_count_d{0..28}` | 29 |
| 4 | `cum_purchase_count_d{0..28}` | `cum_deposit_count_d{0..28}` | 29 |
| 5 | `nonzero_purchase_count_d{0..28}` | `nonzero_deposit_count_d{0..28}` | 29 |
| 6 | `cum_nonzero_purchase_count_d{0..28}` | `cum_nonzero_deposit_count_d{0..28}` | 29 |
| 7 | `purchase_sum_d{0..28}` | `deposit_sum_d{0..28}` | 29 |
| 8 | `cum_purchase_revenue_d{0..28}` | `cum_deposit_sum_d{0..28}` | 29 |

**Modeling implication:** Any existing code referencing `cum_purchaser_d7` or `purchase_sum_d28` will silently produce all-null features when applied to the TRJ Parquet. Column names must be updated before ingestion.

### 1B. Expected label completeness at d28

Since this delivery contains only `gamer_age = d28` with install dates 2026-06-01 to 2026-06-06, **all install observation windows have fully elapsed** at the time of data production (≥28 days past install by pipeline run date). This eliminates the pipeline-lag concern identified in the earlier BQ analysis (Section 11 of `mmp_post_install_optimization_training_v2_analysis.md`).

Expected properties for IOJ labels in this delivery:
- `cum_depositor_d28` should have the same or better fill rate than the BQ ~17% event-configured population
- `cum_purchaser_d{0..27}` (intermediate days) should show monotonically non-decreasing cumulative counts
- No structural nulls due to observation window lag (unlike early BQ partitions which showed 99.96% null for attributed rows)

### 1C. Queries — IOJ label fill rate and monotonicity (BQ, Huron naming)

**Query 1 — IOJ label fill rate by install date**
```sql
SELECT
  DATE(install_time) AS install_date,
  COUNT(*) AS total_rows,
  COUNTIF(is_attributed = TRUE) AS attributed_rows,
  COUNTIF(cum_purchaser_d28 IS NOT NULL) AS depositor_d28_labeled,
  ROUND(100.0 * COUNTIF(cum_purchaser_d28 IS NOT NULL) / COUNT(*), 2) AS d28_fill_rate,
  COUNTIF(cum_purchaser_d28 = 1) AS depositor_d28_positive,
  ROUND(
    100.0 * COUNTIF(cum_purchaser_d28 = 1) /
    NULLIF(COUNTIF(cum_purchaser_d28 IS NOT NULL), 0), 2
  ) AS conditional_positive_rate
FROM `unity-feature-platform-prd.ads_feature_platform_paimon.mmp_post_install_optimization_training_v2`
WHERE DATE(install_time) BETWEEN "2026-06-01" AND "2026-06-06"
GROUP BY 1
ORDER BY 1
```

**Query 2 — IOJ label fill rate across all d0–d28 windows (monotonicity check)**
```sql
SELECT
  COUNTIF(cum_purchaser_d0 IS NOT NULL) AS fill_d0,
  COUNTIF(cum_purchaser_d1 IS NOT NULL) AS fill_d1,
  COUNTIF(cum_purchaser_d3 IS NOT NULL) AS fill_d3,
  COUNTIF(cum_purchaser_d7 IS NOT NULL) AS fill_d7,
  COUNTIF(cum_purchaser_d14 IS NOT NULL) AS fill_d14,
  COUNTIF(cum_purchaser_d21 IS NOT NULL) AS fill_d21,
  COUNTIF(cum_purchaser_d28 IS NOT NULL) AS fill_d28,
  COUNT(*) AS total_rows
FROM `unity-feature-platform-prd.ads_feature_platform_paimon.mmp_post_install_optimization_training_v2`
WHERE DATE(install_time) BETWEEN "2026-06-01" AND "2026-06-06"
  AND is_attributed = TRUE
```

Expected: fill counts should be equal across all windows (the same advertiser-configured population has all windows populated or none; cumulative counts should be non-decreasing).

**Query 3 — Monotonicity violation check (cumulative purchaser flags)**
```sql
SELECT COUNT(*) AS monotonicity_violations
FROM `unity-feature-platform-prd.ads_feature_platform_paimon.mmp_post_install_optimization_training_v2`
WHERE DATE(install_time) BETWEEN "2026-06-01" AND "2026-06-06"
  AND is_attributed = TRUE
  AND (
    cum_purchaser_d1 < cum_purchaser_d0
    OR cum_purchaser_d3 < cum_purchaser_d1
    OR cum_purchaser_d7 < cum_purchaser_d3
    OR cum_purchaser_d14 < cum_purchaser_d7
    OR cum_purchaser_d21 < cum_purchaser_d14
    OR cum_purchaser_d28 < cum_purchaser_d21
  )
```

Expected: 0 violations. A non-zero result indicates a label ordering defect.

**Query 4 — Revenue sum monotonicity (cum_purchase_revenue)**
```sql
SELECT COUNT(*) AS revenue_monotonicity_violations
FROM `unity-feature-platform-prd.ads_feature_platform_paimon.mmp_post_install_optimization_training_v2`
WHERE DATE(install_time) BETWEEN "2026-06-01" AND "2026-06-06"
  AND is_attributed = TRUE
  AND (
    cum_purchase_revenue_d7 < cum_purchase_revenue_d3
    OR cum_purchase_revenue_d14 < cum_purchase_revenue_d7
    OR cum_purchase_revenue_d28 < cum_purchase_revenue_d14
  )
```

---

## 2. Custom-Event Outcomes Block (234 columns)

### 2A. What is in this block

The 234 custom-event outcome columns capture per-install post-install behavioral signals tied to custom MMP-tracked events. Based on the BQ analysis, the key columns in this block include:

| Column family | Description |
|---|---|
| `cum_has_event_d{0..28}` | Binary flag: had any custom event within dx days |
| `cum_has_lc_event_d{0..28}` | Binary flag: had any level-complete (LC) event within dx days |
| `cum_event_count_d{0..28}` | Cumulative count of custom events by dx |
| `cum_lc_event_count_d{0..28}` | Cumulative count of LC events by dx |
| `sdk_event_name_first_seen_arr` | Array of named custom events with first-seen timestamps |
| `sdk_event_name_first_seen_arr_lc` | Array of named LC events with first-seen timestamps |

### 2B. Inherited structural properties (from prior BQ analysis)

From `mmp_post_install_optimization_training_v2_analysis.md` (partition dates 2026-06-30 to 2026-07-06):

| Property | Value | Notes |
|---|---|---|
| Overall null rate (custom event cols) | ~83% | Installs where advertiser did not configure MMP event tracking |
| Conditional positive rate `cum_has_event_d7` (attributed, non-null) | **96.95%** | Near-universal among event-configured rows |
| Conditional positive rate `cum_has_lc_event_d7` (attributed, non-null) | **33.10%** | Meaningful discriminative label |
| Null rate consistency across d1–d28 | null_d1 ≈ null_d28 | Structural property, not recency lag |

For the ar_ts v2 d28 delivery (install dates 2026-06-01 to 2026-06-06), the same structural properties apply. The null rate should remain ~83% for the attributed install cohort; all observation windows are fully elapsed.

### 2C. Attribution scope in ar_ts v2 vs prior BQ analysis

The prior BQ analysis compared attributed (5.4%) vs unattributed (94.6%) rows. The ar_ts v2 TRJ is structured differently:

- **Ad-request-based feature structs exist only for attributed installs** — this is by design (`is_attributed = TRUE` is a precondition for having a valuation_id and ad-request features).
- The Parquet may still contain rows where `is_attributed = FALSE` (e.g., rows carried through for label purposes), but the feature blocks `feature_store_ad_request_based_features`, `agc_ad_request_based_features`, and `uups_ad_request_based_features_*` will be NULL for non-attributed rows.
- **For label quality purposes, the effective training population is attributed installs.** Check that the conditional label rates in this population match prior BQ analysis.

### 2D. Queries — Custom-event outcomes (BQ, Huron naming)

**Query 5 — Custom event fill rate and positive rate for attributed installs**
```sql
SELECT
  DATE(install_time) AS install_date,
  COUNT(*) AS attributed_rows,
  COUNTIF(cum_has_event_d7 IS NOT NULL) AS custom_event_labeled,
  ROUND(100.0 * COUNTIF(cum_has_event_d7 IS NOT NULL) / COUNT(*), 2) AS custom_event_fill_rate,
  COUNTIF(cum_has_event_d7 = 1) AS custom_event_positive,
  ROUND(
    100.0 * COUNTIF(cum_has_event_d7 = 1) /
    NULLIF(COUNTIF(cum_has_event_d7 IS NOT NULL), 0), 2
  ) AS conditional_positive_rate,
  COUNTIF(cum_has_lc_event_d7 IS NOT NULL) AS lc_event_labeled,
  ROUND(
    100.0 * COUNTIF(cum_has_lc_event_d7 = 1) /
    NULLIF(COUNTIF(cum_has_lc_event_d7 IS NOT NULL), 0), 2
  ) AS lc_conditional_positive_rate
FROM `unity-feature-platform-prd.ads_feature_platform_paimon.mmp_post_install_optimization_training_v2`
WHERE DATE(install_time) BETWEEN "2026-06-01" AND "2026-06-06"
  AND is_attributed = TRUE
GROUP BY 1
ORDER BY 1
```

Expected: ~17% fill rate, ~97% conditional positive for `cum_has_event_d7`, ~32–33% for `cum_has_lc_event_d7`.

**Query 6 — Label consistency: custom event ⊆ LC event ordering check**
```sql
SELECT COUNT(*) AS impossible_lc_without_event
FROM `unity-feature-platform-prd.ads_feature_platform_paimon.mmp_post_install_optimization_training_v2`
WHERE DATE(install_time) BETWEEN "2026-06-01" AND "2026-06-06"
  AND is_attributed = TRUE
  AND cum_has_event_d7 = 0
  AND cum_has_lc_event_d7 = 1
```

Expected: 0. `cum_has_lc_event_d7 = 1` is a strict subset of `cum_has_event_d7 = 1`; any non-zero result is a label integrity defect.

**Query 7 — LC/event count consistency**
```sql
SELECT COUNT(*) AS impossible_count_without_flag
FROM `unity-feature-platform-prd.ads_feature_platform_paimon.mmp_post_install_optimization_training_v2`
WHERE DATE(install_time) BETWEEN "2026-06-01" AND "2026-06-06"
  AND is_attributed = TRUE
  AND (
    (cum_has_event_d7 = 1 AND cum_event_count_d7 = 0)
    OR (cum_has_lc_event_d7 = 1 AND cum_lc_event_count_d7 = 0)
  )
```

Expected: 0. Flag = 1 with count = 0 is internally inconsistent.

**Query 8 — Full label coverage cross-tab (attributed d28 installs)**
```sql
SELECT
  CASE WHEN cum_has_event_d28 IS NULL THEN 'null' ELSE CAST(cum_has_event_d28 AS STRING) END AS event_d28,
  CASE WHEN cum_has_lc_event_d28 IS NULL THEN 'null' ELSE CAST(cum_has_lc_event_d28 AS STRING) END AS lc_d28,
  CASE WHEN cum_purchaser_d28 IS NULL THEN 'null' ELSE CAST(cum_purchaser_d28 AS STRING) END AS depositor_d28,
  COUNT(*) AS row_count
FROM `unity-feature-platform-prd.ads_feature_platform_paimon.mmp_post_install_optimization_training_v2`
WHERE DATE(install_time) BETWEEN "2026-06-01" AND "2026-06-06"
  AND is_attributed = TRUE
GROUP BY 1, 2, 3
ORDER BY 4 DESC
LIMIT 20
```

This reveals whether the IOJ label population (depositor) is a subset of the custom-event population, or if they are independently configured tracking systems with partial overlap.

---

## 3. UUPS / Feature Struct Label-Adjacency Issues

### 3A. advctx_profiles is NULL in Parquet (by design)

Per §6C of the validation doc, the Spark export job explicitly sets `advctx_profiles = NULL` in the Parquet output (typed like `bhv_profiles`). The pre-normalization BQ table carries real advctx data; the TRJ does not.

The post-export UUPS struct layout is:
```
uups_*_ad_request_based_features_* = STRUCT<
  bhv_profiles,            -- populated
  advctx_profiles,         -- NULL (set to NULL by export job)
  thumbs_up_profiles       -- populated (renamed from lig_profiles)
>
```

**Implication for modeling:** Any feature that reads `advctx_profiles` from the TRJ Parquet will receive NULL for all rows. If prior models used advctx features from the BQ table, they cannot be used from this Parquet without a re-join against the BQ table.

### 3B. UUPS parity summary (from Appendix B)

| Profile type | Android match | iOS match | Notes |
|---|---|---|---|
| `advctx_profiles` | 100% | 100% | NULL in Parquet — present in BQ only |
| `bhv_profiles` | 99.5% | 99.9% | At parity |
| `lig_profiles` (→ `thumbs_up_profiles`) | 24.2% | 95.9% | Android by design (slot-level LIG); iOS residual = UUPS-v5 window + IPJ 100-input cap |

Android `lig`/`thumbs_up` 24.2% is **expected and by design** — Android uses slot/placement-level LIG, not gamer_token_lig, so it shares no LIG stores with IPJ. Do not raise as a defect.

### 3C. lig_profiles → thumbs_up_profiles rename

The column rename (`lig_profiles` → `thumbs_up_profiles`) in the Parquet output means:
- BQ exploration: query `lig_profiles` within the UUPS struct
- Parquet/TRJ: the field is `thumbs_up_profiles`

Any code that references `lig_profiles` by name when reading the Parquet will silently get NULL.

---

## 4. Partition and Population Scope

### 4A. d28 only — other gamer ages not populated

This delivery contains only `gamer_age = d28`. The d0/d1/d3/d7/d14/d21 paths for install dates 2026-06-01 to 2026-06-06 are **not populated**. Per the validation doc:

> "The other gamer ages (d0/d1/d3/d7/d14/d21) are not populated for the same install_dates since the installs date we are targeting are older than 28 days."

**Implication:** This sample cannot be used to validate intermediate-window label quality (e.g., d7 vs d28 label accumulation curves). All label quality checks in this doc are scoped to the d28 label block only. Future deliveries covering earlier gamer ages will be needed for full label-curve validation.

### 4B. Expected row counts

The validation was run on 2026-06-05 install date for Appendix A. At that point:
- idfa ar_ts populated: 3,745,913 (vs 3,810,886 in v10, -1.70%)
- idfi ar_ts populated: 1,443,086 (vs 1,447,999 in v10, -0.34%)
- idfm ar_ts populated: 895,364 (vs 861,299 in v10, +3.96%)

For a rough row count sanity check across all 6 install dates, expect ~20–25M total rows per install date (consistent with the BQ analysis showing 118–131M rows per install date across all gamer ages).

**Query 9 — Row count by install date**
```sql
SELECT
  DATE(install_time) AS install_date,
  COUNT(*) AS total_rows,
  COUNTIF(is_attributed = TRUE) AS attributed_rows,
  ROUND(100.0 * COUNTIF(is_attributed = TRUE) / COUNT(*), 2) AS attributed_pct
FROM `unity-feature-platform-prd.ads_feature_platform_paimon.mmp_post_install_optimization_training_v2`
WHERE DATE(install_time) BETWEEN "2026-06-01" AND "2026-06-06"
GROUP BY 1
ORDER BY 1
```

---

## 5. Dimension Rename Validation

The 55 dimension renames (§6A) affect join key columns. Two are especially critical for label quality checks:

| Rename | BQ / Huron name | Parquet / Legacy name |
|---|---|---|
| Attribution event time | `event_time` | `eventTimestamp` |
| Install time | `install_time` | `installTimestamp` |
| Campaign payment model | `campaign_payment_model` | `campaignType` |
| Attribution partner | `attribution_partner` | `tracking_partner` |
| Advertiser game id | `advertiser_game_id` | `targetGameId` (STRING cast) |

Note: `advertiser_game_id` is cast to STRING in the Parquet (`targetGameId`). Any downstream join on this column must handle the type change.

**Query 10 — Verify key dimension presence and non-null rates (BQ, Huron naming)**
```sql
SELECT
  COUNTIF(event_time IS NULL) AS null_event_time,
  COUNTIF(install_time IS NULL) AS null_install_time,
  COUNTIF(valuation_id IS NULL) AS null_valuation_id,
  COUNTIF(auction_id IS NULL) AS null_auction_id,
  COUNTIF(campaign_id IS NULL) AS null_campaign_id,
  COUNTIF(attribution_partner IS NULL) AS null_attribution_partner,
  COUNTIF(source_gamer_id IS NULL) AS null_source_gamer_id,
  COUNT(*) AS total
FROM `unity-feature-platform-prd.ads_feature_platform_paimon.mmp_post_install_optimization_training_v2`
WHERE DATE(install_time) BETWEEN "2026-06-01" AND "2026-06-06"
  AND is_attributed = TRUE
```

---

## 6. Parity Validation Summary (from Appendix A — FP Feature Quality)

This section summarises the parity results from the validation doc to establish the expected quality baseline for feature completeness adjacent to labels.

| Identity | ar_ts populated | v10 populated | Coverage vs v10 | Value match (median 234 fields) |
|---|---|---|---|---|
| idfa | 3,745,913 | 3,810,886 | -1.70% | **100.0%** |
| idfi | 1,443,086 | 1,447,999 | -0.34% | **100.0%** |
| idfm | 895,364 | 861,299 | +3.96% | **99.5%** (99.6% headline) |

idfm mismatch breakdown (29,337 of 1,296,707 — 2.26%):
- 90.1% — target-idfi fold on no-LIG installs (expected: same value in idfi_profile)
- 9.7% — both>0 but differ (large LIG member selection, >100 members)
- 0.2% — ar_ts=0, v10>0 (residual)

This is a **known, explained, small residual**. The 99.6% headline match is within acceptable tolerance for modeling.

---

## 7. Key Findings and Risks

### Finding 1: Column name break between BQ and Parquet is a hard migration requirement

The 55 dimension renames + 232 metric renames are not optional aliases — the Parquet files contain only the legacy names. Any DataGen pipeline or training code that reads from the TRJ Parquet using Huron column names (e.g., `cum_purchaser_d7`, `purchase_sum_d28`, `event_time`, `install_time`) will silently receive NULL for all rows. This is the highest-priority risk for the modeling team.

Recommended: run a schema validation step at ingestion that asserts expected column names are present.

### Finding 2: advctx_profiles is NULL in TRJ — BQ is the only source

The Spark export job nulls out `advctx_profiles` in the Parquet (§6C). The BQ exploration table carries real advctx data. Any model feature depending on `advctx_profiles` must be sourced from the BQ table (`mmp_post_install_optimization_training_v2`) with the Huron struct path, not from the TRJ Parquet. Validate that the parity result (100% advctx match in Appendix B) was tested against BQ, not against the already-nulled Parquet.

### Finding 3: d28-only delivery means no label-curve validation possible in this sample

All installs in this delivery have fully elapsed 28-day observation windows. This is ideal for d28 label completeness but provides no signal on d0/d7/d14 label accumulation curves. Label quality for intermediate gamer ages must wait for d0–d21 paths to be populated.

### Finding 4: IOJ and custom-event labels are independently tracked populations

Based on the BQ analysis, the IOJ deposit/purchase labels and the custom-event `cum_has_event_dx` labels come from different tracking configurations. An install can have:
- Custom event labels only (advertiser configured MMP events, no purchase tracking)
- IOJ labels only (advertiser configured purchase/deposit tracking, no custom event SDK)
- Both (rare)
- Neither (~83% null for both)

This means the effective training population for a joint "has event AND has deposit" label is smaller than either individual population. Query 8 (cross-tab) will reveal the true population overlap.

### Finding 5: Android lig/thumbs_up 24.2% match is by design — do not filter

Android's low `thumbs_up_profiles` (formerly `lig_profiles`) match vs IPJ is not a data quality defect. Android uses slot/placement-level LIG which does not overlap with the gamer_token_lig used by IPJ. The 24.2% represents structural divergence, not pipeline failure. Do not apply quality filters on this column for Android rows.

### Finding 6: idfm +3.96% coverage overage is explained and acceptable

ar_ts has more idfm-populated rows than v10 (+3.96%). This is explained by the target-idfi fold in MERGE_IDFI_GAMER_IDS (see §7 of the validation doc): ar_ts folds the target idfi into idfm_profile for installs with no LIG, while v10 leaves idfm_profile empty. The value parity where both have data is 99.75%. The additional rows are not spurious — they represent a serving-aligned behavior (matches AVC).

---

## 8. Checklist for DataGen Ingestion

Before using the TRJ Parquet in training, verify:

- [ ] Column names match legacy schema (depositor not purchaser; eventTimestamp not event_time; etc.)
- [ ] IOJ label fill rate ~17% for attributed rows on these install dates
- [ ] No monotonicity violations in cumulative deposit/event count columns (Queries 2–4)
- [ ] `cum_has_event_dx` ⊆ `cum_has_lc_event_dx = 0` is respected (Query 6) — confirmed 0 violations in prior BQ analysis
- [ ] `advctx_profiles` is NULL in Parquet (expected); confirm downstream feature code does not read it from Parquet
- [ ] `thumbs_up_profiles` (not `lig_profiles`) in Parquet UUPS structs
- [ ] `targetGameId` is STRING type (not INT) in Parquet
- [ ] Row counts per install date are consistent with the BQ table (±2% tolerance)
- [ ] `partition_date` and `process_date` are absent (dropped by export job); use `install_date` partition key instead

---

*Queries above target `unity-feature-platform-prd.ads_feature_platform_paimon.mmp_post_install_optimization_training_v2` with `DATE(install_time) BETWEEN "2026-06-01" AND "2026-06-06"` to align with the d28 Parquet delivery. For Parquet-level schema checks, use PySpark against the GCS paths in §1 of the validation doc.*
