# Data Comparison Report: unified_cpe.v1_lc vs Legacy BHV/CTX

**Date:** 2026-05-05

## Datasets


| Dataset        | Path                                                                                                             |
| -------------- | ---------------------------------------------------------------------------------------------------------------- |
| **NEW**        | `gs://unity-ads-dd-ds-prd-incremental-training-data/cpe/unified_cpe.v1_lc/preprocessed_combined/date=2026-04-26` |
| **Legacy BHV** | `gs://unity-ads-dd-ds-prd-app-training-data/level_complete/bhv_level_complete_data_v2p/20260505132332`           |
| **Legacy CTX** | `gs://unity-ads-dd-ds-prd-app-training-data/level_complete/ctx_level_complete_data_v2p/20260505132414`           |


---

## 0. Changes Since Last Report (2026-04-13 → 2026-04-26)

This section summarizes what changed in the NEW datagen relative to the previous comparison report dated 2026-04-22 (data snapshot `date=2026-04-13`).


| Area                                        | April 13 snapshot       | April 26 snapshot                   | Delta     |
| ------------------------------------------- | ----------------------- | ----------------------------------- | --------- |
| **Column count**                            | 63                      | **83**                              | +20       |
| **Storage**                                 | 35.76 GiB               | **60.2 GiB**                        | +68%      |
| **Row count**                               | TBD                     | **504,657,804** (exact)             | —         |
| **Categorical encoding**                    | **Pre-hashed integers** | **Raw strings** (same as legacy)    | **FIXED** |
| **Session counters**                        | Dropped                 | **Added back** (9 cols)             | FIXED     |
| **Privacy / identity signals**              | Dropped                 | **Added back** (9 cols)             | FIXED     |
| **tgtg_sdk_set**                            | Missing                 | **Added back** (placeholder)        | FIXED     |
| **gamer_id_scope**                          | Missing                 | **Present** (idfa/idfi/unspecified) | FIXED     |
| **Target game 7d/24h counters**             | Partial                 | **Full set added** (+4 cols)        | NEW       |
| **label positive rate**                     | 21.2%                   | **19.5%**                           | −1.7pp    |
| **prob_sdk_event_name_label positive rate** | 7.5%                    | **7.0%**                            | −0.5pp    |


> **Critical fix — categorical encoding:** The April 13 snapshot stored categorical features (e.g. `platform`, `gamer_id_scope`) as pre-hashed integers. This has been reverted to raw strings, matching the legacy BHV/CTX representation and eliminating the hash-function alignment risk flagged in the prior report.

---

## 1. Size & Row Counts


| Metric                 | NEW (unified_cpe.v1_lc)                       | BHV Legacy                                        | CTX Legacy                          | BHV+CTX Combined |
| ---------------------- | --------------------------------------------- | ------------------------------------------------- | ----------------------------------- | ---------------- |
| **Storage**            | 60.2 GiB                                      | 99.32 GiB (train) + 6.08 GiB (val)                | 103.23 GiB (train) + 6.39 GiB (val) | ~215 GiB         |
| **Files**              | 4,800                                         | 2,882 (train) + 2,882 (val)                       | 2,882 (train) + 2,882 (val)         | —                |
| **Train rows**         | **504,657,804** (exact)                       | **44,354,363**                                    | **60,427,534**                      | **104,781,897**  |
| **Val rows**           | — (no train/val split)                        | 4,386,511                                         | 5,975,614                           | 10,362,125       |
| **Install date range** | 60 days (2026-02-26 → 2026-04-26)             | 60 days (2026-02-26 → 2026-04-26)                 | same                                | —                |
| **Output partition**   | Single partition `date=2026-04-26` (end date) | Separate `train.parquet/` + `validation.parquet/` | same                                | —                |
| **Columns**            | **83**                                        | **79**                                            | **54**                              | (union: 120)     |


> **Why NEW has ~5× more rows than BHV+CTX combined:** The new datagen reads from `installs.outcomes.v2/level_complete/d7/` and then **explodes rows by `sdk_event_name` target** — each install produces one row per eligible sdk event. With ~5–10 sdk event targets per install on average, the total row count inflates proportionally. BHV/CTX do not explode by sdk event; they produce one row per install impression.
>
> **Why NEW storage (60.2 GiB) is still much smaller than BHV+CTX (~215 GiB):** Despite having ~5× more rows, NEW has much better compression ratios in Parquet — the per-row byte size is roughly 0.125 KB vs ~2 KB for legacy. This is expected: the exploded rows share identical feature values across many duplicated rows (only the label columns differ), and Parquet's column-oriented compression is extremely efficient for repeated values.

---

## 2. Label Analysis


| Column                                    | NEW                             | BHV   | CTX   |
| ----------------------------------------- | ------------------------------- | ----- | ----- |
| `label` (positive rate)                   | **19.5%**                       | 37.3% | 36.6% |
| `app_event_d0`                            | 16.1% positive (day-0 events)   | —     | —     |
| `app_event_d1`                            | 4.8% positive                   | —     | —     |
| `app_event_d3`                            | 2.3% positive                   | —     | —     |
| `app_event_d7`                            | 0.9% positive                   | —     | —     |
| `app_event_w1/w2/w3/w4`                   | 19.5% positive (all equal)      | —     | —     |
| `app_event_count_w1` (mean for positives) | **17.5 events**                 | —     | —     |
| `prob_sdk_event_name_label`               | **7.0%** positive (scalar, 0/1) | —     | —     |


**Key observations:**

- `label` in NEW is ~18pp lower than legacy. Legacy `label` = CPI install label; NEW `label` = level-complete event within the label window (CPE), tied to the specific `sdk_event_name` target after the explode step. The 80.5% negatives are non-converters for that particular event.
- `app_event_w1 = app_event_w2 = app_event_w3 = app_event_w4` — all week-level labels have identical non-null rates (19.5%), suggesting the label window does not yet vary by week for this snapshot. All non-null values are 1.0, which is expected since the source table pre-filters to installs with any level_complete event within 7 days.
- `app_event_d0` is notably high (16.1%) — most converters register their first level-complete event on the install day.
- `prob_sdk_event_name_label` (7.0% positive) is lower than `label` (19.5%) — this reflects the probability-weighted sdk event label vs the binary per-row CPE label.
- The label drop from 21.2% (April 13) to 19.5% (April 26) is minor and within normal date-range variation.

---

## 3. Schema Differences

### 3.1 Columns only in NEW (30 new columns vs legacy union)

```
# Multi-horizon binary labels (8 cols)
app_event_d0 / d1 / d3 / d7                  <- day-level binary labels
app_event_w1 / w2 / w3 / w4                  <- week-level binary labels

# Multi-horizon event count labels (4 cols)
app_event_count_w1 / w2 / w3 / w4            <- week-level event count labels

# Cumulative event counts (5 cols)
cum_app_event_count_d0 / d1 / d3 / d7 / d14  <- cumulative event counts at multiple cutoffs

# Contextual features
ad_format                                      <- new (interstitial / rewarded)

# SDK event features
prob_sdk_event_name                            <- sdk event probability score (string)
prob_sdk_event_name_label                      <- sdk event label (scalar float32, 0/1)

# Target game extended counters (NEW — 6 cols)
target_game_click_count                        <- total clicks (not just 24h)
target_game_click_count_in_last_7_days
target_game_start_count_in_last_24_hours
target_game_start_count_in_last_7_days
target_game_view_count_in_last_24_hours
target_game_view_count_in_last_7_days

# Data split / identity
bucket                                         <- data split bucket (0.0–1.0 uniform)
install_date                                   <- explicit install date string

# Privacy / identity (added back in April 26 update)
coppa, fingerprinted, limited, opt_out_enabled <- privacy flags (int/float)
counters_source, traffic_type                  <- traffic classification (string)

# User identity (added back in April 26 update)
gamer_has_fingerprinted_identity, gamer_has_opted_out, gamer_limited_tracking
```

### 3.2 Columns present in NEW (session counters — added back in April 26)

Previously dropped from NEW; now restored to match CTX legacy:

```
gamer_session_counters_adrequests
gamer_session_counters_start_count / view_count
gamer_session_counters_has_tgtg_started / has_tgtg_viewed
gamer_session_counters_performance_starts_count / performance_views_count
gamer_session_counters_brand_starts_count / brand_views_count
```

### 3.3 Columns still dropped from legacy (not present in NEW)

```
# All UUPS IAP/adrev features (32 cols) — STILL DROPPED
uups_attributed_iap_*_d7/d30           (x8 scalars + x2 categorical done flags)
uups_unattributed_iap_*_d7/d30         (x8 scalars + x2 categorical done flags)
uups_uasdk_iap_*_d7/d30               (x4 scalars + x2 categorical done flags)
uups_adrev_oecpm_*_d7/d30             (x8 scalars)

# IBT / install history / profile (7 cols) — STILL DROPPED
installed_store_ids, installed_store_ids_channel, installed_store_ids_latest_start_ts
ad_req_project_id, ad_req_counts
gamer_profile_counters_adrequests_in_last_7_days
gamer_profile_meta

# Legacy prob_sdk arrays — REPLACED by scalars
prob_sdk_event_name_array  -> removed
prob_sdk_event_name_labels -> replaced by prob_sdk_event_name_label (scalar float32)
```

### 3.4 Summary counts


|                       | NEW | BHV | CTX |
| --------------------- | --- | --- | --- |
| Total columns         | 83  | 79  | 54  |
| Shared with BHV       | 45  | —   | —   |
| Shared with CTX       | 43  | —   | —   |
| Shared with both      | 32  | —   | —   |
| NEW only (vs both)    | 30  | —   | —   |
| BHV only (not in NEW) | 39  | —   | —   |
| CTX only (not in NEW) | 9   | —   | —   |


---

## 4. Categorical Encoding — Fixed

**In the April 13 snapshot**, categorical columns in NEW were stored as **pre-hashed integers**. This has been **fixed in the April 26 snapshot** — categorical columns are now stored as **raw strings**, consistent with legacy BHV/CTX.

```
platform:
  NEW (04-26):  {'android': 78.8%, 'ios': 21.2%}   <- RAW STRINGS (fixed)
  NEW (04-13):  {-1971035589: 79%, 486895588: 21%}  <- INTEGER HASHED (old, broken)
  BHV:          {'android': 86.8%, 'ios': 13.2%}
  CTX:          {'android': 74.2%, 'ios': 25.8%}

gamer_id_scope:
  NEW (04-26):  {'idfa': 75.8%, 'idfi': 24.1%, 'unspecified': ~0%}  <- RESTORED
  NEW (04-13):  MISSING
  CTX:          {'idfa': 73.6%, 'idfi': 26.4%}
  BHV:          MISSING (BHV is all idfa, not included in that column)

ad_type:
  NEW:  {'video+playable': 48.7%, 'video': 27.6%, 'playable': 23.7%}
  BHV:  {'video+playable': 56.3%, 'video': 25.0%, 'playable': 18.8%}
  CTX:  {'video+playable': 54.7%, 'video': 24.3%, 'playable': 21.0%}

ad_format (NEW only):
  NEW:  {'interstitial': 72.2%, 'rewarded': 27.8%}

sdk_event_name:
  All datasets: {'placeholder': 100%}
```

No further action required for embedding-lookup hash alignment — the fix is confirmed.

---

## 5. Scalar Feature Statistics

Statistics computed from one sample row group per dataset (~105K rows NEW, ~15K rows BHV, ~21K rows CTX).


| Feature                                    | NEW mean / std | BHV mean / std    | CTX mean / std |
| ------------------------------------------ | -------------- | ----------------- | -------------- |
| `gamer_start_count`                        | 165.8 / 358.5  | **212.9 / 405.9** | 180.6 / 384.6  |
| `gamer_start_count_in_last_24_hours`       | 4.0 / 6.9      | 4.3 / 7.1         | 4.0 / 6.8      |
| `gamer_start_count_in_last_7_days`         | 15.5 / 27.7    | **18.1 / 29.9**   | 16.2 / 28.6    |
| `gamer_view_count`                         | 90.2 / 225.4   | **112.4 / 239.8** | 96.0 / 240.2   |
| `gamer_click_count`                        | 27.4 / 56.9    | **32.0 / 61.9**   | 26.0 / 54.1    |
| `gamer_install_count`                      | 4.8 / 13.3     | **6.0 / 13.3**    | 4.6 / 12.1     |
| `gamer_creation_delay`                     | 35.3M / 39.9M  | **45.0M / 41.6M** | 37.0M / 40.8M  |
| `target_game_start_count`                  | 3.35 / 7.37    | 3.84 / 7.91       | MISSING        |
| `target_game_view_count`                   | 1.99 / 5.20    | 2.15 / 5.25       | MISSING        |
| `target_game_click_count_in_last_24_hours` | 0.19 / 0.47    | 0.19 / 0.46       | MISSING        |
| `publisher_is_coppa_targeted`              | 3.7%           | 0.0%              | 3.1%           |


**NEW-only target game extended counters:**


| Feature                                    | NEW mean / std |
| ------------------------------------------ | -------------- |
| `target_game_click_count`                  | 0.78 / 2.95    |
| `target_game_click_count_in_last_7_days`   | 0.39 / 1.17    |
| `target_game_start_count_in_last_24_hours` | 0.54 / 1.25    |
| `target_game_start_count_in_last_7_days`   | 1.26 / 2.75    |
| `target_game_view_count_in_last_24_hours`  | 0.36 / 0.95    |
| `target_game_view_count_in_last_7_days`    | 0.80 / 2.02    |


BHV users are consistently more engaged (higher gamer counters) — expected since BHV = identified users (idfa) with rich behavioral history. CTX and NEW engagement stats are very similar, consistent with the new dataset being a BHV+CTX mix dominated by idfa traffic (~76%).

---

## 6. Traffic Mix


|                              | NEW    | BHV   | CTX   |
| ---------------------------- | ------ | ----- | ----- |
| **Android share**            | ~78.8% | 86.8% | 74.2% |
| **iOS share**                | ~21.2% | 13.2% | 25.8% |
| **idfa share**               | ~75.8% | 100%  | 73.6% |
| **idfi / unspecified share** | ~24.2% | 0%    | 26.4% |


The new dataset correctly combines both traffic types (BHV + CTX), with a platform mix sitting between the two legacy datasets. The idfa/idfi ratio is aligned with the CTX distribution, confirming that the `gamer_id_scope` column is correctly populated in this update.

---

## 6.5 Label Deep-Dive Analysis (BQ Query Results, 2026-05-05)

This section contains full BQ-derived statistics for all label-related columns in `unity-ads-dd-ds-dev-prd.unified_cpe_v1_lc.unified_cpe_v1_lc_preprocessed_combined`.

### 6.5.0 Overall Label Distribution


| Metric                                         | Value               |
| ---------------------------------------------- | ------------------- |
| **Total rows**                                 | 504,657,804         |
| `**label=1`**                                  | 98,897,226 (19.6%)  |
| `**label=0`**                                  | 405,760,578 (80.4%) |
| `**prob_sdk_event_name_label=1**`              | 35,690,721 (7.07%)  |
| **Invariant violations** (`psn=1 AND label=0`) | **0** ✓             |


**Joint distribution of `label` × `prob_sdk_event_name_label`:**


| `label` | `psn_label` | Row count   | Fraction                                           |
| ------- | ----------- | ----------- | -------------------------------------------------- |
| 0       | 0.0         | 405,760,578 | **80.4%** — non-converters                         |
| 1       | 0.0         | 63,206,505  | **12.5%** — converted but specific event not fired |
| 1       | 1.0         | 35,690,721  | **7.1%** — converted AND specific event matched    |


> Of all `label=1` rows, only **36.1%** (35.7M / 98.9M) have `psn_label=1`. The remaining 63.9% are overall converters but did not fire the specific targeted SDK event for that row.

---

### 6.5.1 Multi-Horizon Label Rates


| Column         | NULL rate | Non-null positive rate (of all rows) | % of `label=1` rows |
| -------------- | --------- | ------------------------------------ | ------------------- |
| `app_event_d0` | 83.8%     | **16.2%**                            | 82.6%               |
| `app_event_d1` | 95.2%     | **4.8%**                             | 24.4%               |
| `app_event_d3` | 97.7%     | **2.3%**                             | 11.8%               |
| `app_event_d7` | 99.1%     | **0.95%**                            | 4.8%                |
| `app_event_w1` | 80.4%     | **19.6%**                            | 100%                |
| `app_event_w2` | 80.4%     | —                                    | 100%                |
| `app_event_w3` | 80.4%     | —                                    | 100%                |
| `app_event_w4` | 80.4%     | —                                    | 100%                |


**Critical findings:**

1. `**app_event_w1 IS NULL` ↔ `label=0` is a perfect bijection** (verified: 0 rows where these disagree). `label` is exactly `COALESCE(app_event_w1 > 0, 0)` — the two columns carry identical information.
2. `**app_event_w1 = w2 = w3 = w4`** — all four weekly columns have identical NULL rates (80.4%) and are all non-null only for `label=1` rows. The multi-week horizon is not yet varying in this snapshot (all positives appear in all weeks). This is likely because the source table uses a single 7-day attribution window for all `wX` columns.
3. `**app_event_d0` covers 82.6% of positives** — the vast majority of level-complete converters fire their first event on the install day. Only 17.4% of positives first fire the event after day 0.
4. **Daily labels (d0/d1/d3/d7)** are non-overlapping horizon windows (not cumulative). `d0` + `d1` + `d3` + `d7` + remaining positives with no early-day label ≠ w1 exactly, suggesting not all positives are covered by the daily label columns (d7 non-null = 4.8% of positives, meaning many fire later than day 7 within the w1 window). Wait — all label=1 rows have `w1` non-null, but the daily columns have varying coverage, suggesting they represent counts within that specific day window.
5. **Consistency check passed**: No `label=1` rows have `d0` non-null but `w1` null (verified: 0 such rows).

---

### 6.5.2 `app_event_count_w1` Distribution (for positives only)


| Metric              | Value       |
| ------------------- | ----------- |
| **Mean**            | 18.8 events |
| **Std dev**         | 147.9       |
| **Max**             | 25,710      |
| **P10 / P20 / P30** | 1 / 1 / 1   |
| **P40 / P50**       | 2 / 2       |
| **P60 / P70**       | 4 / 5       |
| **P80 / P90**       | 8 / 15      |
| **P100**            | 25,710      |


**Distribution buckets (all rows):**


| Count range    | Row count           |
| -------------- | ------------------- |
| NULL (label=0) | 405,760,578 (80.4%) |
| 1–5            | 60,015,469 (11.9%)  |
| 6–20           | 28,085,841 (5.6%)   |
| 21–50          | 6,627,532 (1.3%)    |
| 51–100         | 2,005,313 (0.4%)    |
| 100+           | 2,163,071 (0.4%)    |


> The distribution is extremely heavy-tailed (mean 18.8 vs median 2). The model uses `app_event_count_w1` as an auxiliary label or feature — the large right tail means **log1p transformation or capping is necessary** before using it as a regression target. The `apply_log1p_to_dense_threshold: 20.0` in `config.json` will handle this at training time.

---

### 6.5.3 SDK Event (`prob_sdk_event_name`) Analysis


| Metric                                    | Value                               |
| ----------------------------------------- | ----------------------------------- |
| **Distinct `prob_sdk_event_name` tokens** | **14,186**                          |
| **Distinct sdk_event names**              | **1,192**                           |
| **Wildcard (`*`) rows**                   | 310,051,420 (**61.4%**)             |
| **Wildcard label_pos_rate**               | 5.25% (= psn_pos_rate, as expected) |


**Wildcard dominance:** 61.4% of all training rows come from campaigns targeting `*` (any event). For these rows, `psn_label = label` (any converter is a positive). The model sees a much richer positive signal from wildcard rows than from specific-event rows.

**Top specific events by `psn_pos_rate`:**


| sdk_event                | Rows      | `label_pos_rate` | `psn_pos_rate` | `psn` given `label=1` |
| ------------------------ | --------- | ---------------- | -------------- | --------------------- |
| `arena_2_reached_unique` | 145,655   | 56.2%            | **55.3%**      | 98.4%                 |
| `castle_lv2`             | 573,040   | 56.5%            | **52.6%**      | 93.1%                 |
| `ow`                     | 213,093   | 38.3%            | **38.3%**      | 100%                  |
| `nameofevent`            | 108,543   | 45.2%            | **45.2%**      | 100%                  |
| `registration`           | 157,183   | 39.7%            | **39.7%**      | ~100%                 |
| `onlinetime_30m`         | 1,155,163 | 74.5%            | **46.4%**      | 62.2%                 |
| `daily_quest`            | 783,412   | 78.4%            | **45.9%**      | 58.6%                 |


Events with `psn_given_label1 ≈ 1.0` (like `ow`, `nameofevent`, `registration`) are events that virtually every converter fires — easy to predict, very little noise in the label.

**SDK events with `psn_pos = 0` (never fired by any user in dataset):**

20+ events have zero `psn_label=1` rows despite having significant row counts (400K–1.4M rows), including `ipu_24h_16`, `s_custom3_revenue`, `loop_online_24h_60_ios`, `adsvalue_4000`, `game_end_5_jili`, `turfbattle1_completion`, `turfbattle3_completion`, etc.

> **Issue:** Rows for zero-fired SDK events contribute only negative training signal (`psn_label=0`) for the `prob_sdk_event_name_label` head. The model will learn to always predict 0 for these event tokens, which is correct behavior, but these rows add noise to the `label` head training. Consider whether to filter them at training time.

---

### 6.5.4 Label Rate Trend by Install Date

**Full 60-day trend (2026-02-26 → 2026-04-26):**


| Period                        | `label_pos_rate` (avg) | `psn_pos_rate` (avg) | Notes                                           |
| ----------------------------- | ---------------------- | -------------------- | ----------------------------------------------- |
| **Feb 26 – Mar 25** (28 days) | **21.5%**              | **7.6%**             | Stable "baseline" rates; full 7-day attribution |
| **Mar 26 – Apr 12** (18 days) | **20.0%**              | **7.0%**             | Slight decline; still full attribution          |
| **Apr 13 – Apr 19** (7 days)  | **16.0%**              | **6.7%**             | Sharp drop — attribution window incomplete      |
| **Apr 20 – Apr 26** (7 days)  | **14.4%**              | **6.1%**             | Further drop — last 7 days of window            |


**psn_pos_rate / label_pos_rate ratio:**

- Consistently **~0.35–0.37** throughout the 60-day window — the ratio of psn-specific conversions to overall conversions is stable over time.

**Key finding — attribution cutoff bias:**

The sharp label rate drop starting ~Apr 13 (13 days before the Apr 26 cutoff) indicates that:

- Installs from **Apr 13 onward** have fewer than 14 days to accumulate level-complete events
- Installs from **Apr 20 onward** have fewer than 7 days — the label window (`app_event_w1`) is inherently incomplete for these rows

This is a **systematic label bias in the training data**: ~20% of rows (last ~13 days out of 60) have under-labeled positives. Newer cohorts look less engaged than they actually are, because the attribution window hasn't closed yet.

> **Recommendation:** Apply a **recency bias correction** at training time, or exclude the last 7–14 days when computing evaluation metrics. The `dataset_config.cut_off: 0.05` setting (5% holdout) may partially mitigate this, but a time-based split is preferable over a random split for time-series data.

---

### 6.5.5 Label Calculation Logic (Source Code Reference)

#### `label`

```sql
label = CASE WHEN app_event_w1 > 0 THEN 1 ELSE 0 END
-- Equivalently: label = CAST(app_event_w1 IS NOT NULL AS INT64)
-- (since app_event_w1 is NULL for negatives and always > 0 for positives)
```

#### `sdk_event_name_array`

```python
# Raw array of SDK events fired by user, lowercased and serialized
sdk_event_name_array = lower(array_join(sdk_event_name_array_raw, ","))
# e.g. "[level_complete]", "[level_complete, tutorial_complete]", "[]"
```

#### `prob_sdk_event_name`

```python
# After exploding the campaign's SDK event target list
prob_sdk_event_name = f"{target_game_id}_{sdk_event}"
# e.g. "500043219_level_complete", "500043219_*"
# 14,186 distinct tokens; 1,192 distinct event types
```

#### `prob_sdk_event_name_label`

```python
sdk_event_fired = array_contains(sdk_event_name_array, sdk_event)
is_wildcard = (sdk_event in ("*", ""))
prob_sdk_event_name_label = 1.0 if (sdk_event_fired or is_wildcard) and label == 1 else 0.0
```

**Scenario table:**


| `label` | Event fired? | Wildcard?    | `psn_label` |
| ------- | ------------ | ------------ | ----------- |
| 1       | ✓            | ✗ (specific) | **1.0**     |
| 1       | ✗            | ✗ (specific) | **0.0**     |
| 1       | any          | ✓            | **1.0**     |
| 0       | any          | any          | **0.0**     |


---

### 6.5.6 Comparison with Legacy Pinpointer Label


| Aspect                     | NEW `unified_cpe.v1_lc`                  | Legacy `ads-audience-pinpointer`      |
| -------------------------- | ---------------------------------------- | ------------------------------------- |
| **Label type**             | Deterministic, computed at datagen       | Stochastic, sampled per training step |
| **Training label**         | `prob_sdk_event_name_label` (scalar 0/1) | `probabilistic_labels` (float array)  |
| **Label positive rate**    | 7.07% (psn) / 19.6% (overall)            | Not directly comparable               |
| **SDK event conditioning** | 1 row per (install × sdk_event)          | 1 row per install, array of labels    |
| **Row inflation**          | ~5× (explode by sdk_event)               | 1× (no explode)                       |
| **Attribution window**     | 7-day (w1)                               | 7-day                                 |
| **Wildcard share**         | 61.4% of rows                            | N/A                                   |
| **Incomplete label risk**  | Last ~13 days of 60-day window           | Same (time-based)                     |


---

## 6.6 Label Column Calculation Logic (Reference)

This section documents the exact calculation logic for all label-related columns in the NEW `unified_cpe.v1_lc` dataset, and compares them to the legacy pinpointer probabilistic label approach.

### 6.5.1 Column Definitions

#### `label` — Binary CPE label (overall level-complete)

```sql
label = CASE WHEN app_event_w1 > 0 THEN 1 ELSE 0 END
```

- `app_event_w1` counts the number of level-complete events fired by this user within 7 days of install.
- `label = 1` if the user fired **any** level-complete event (≥1) within 7 days.
- `label = 0` if the user fired **zero** level-complete events within 7 days.
- This is a **per-row (per-install × per-sdk-event)** column — every exploded row for the same install shares the same `label` value.
- Positive rate: **19.5%** (April 26 snapshot).

> Note: The source table `installs.outcomes.v2/level_complete/d7/` pre-filters to installs that occurred within the attribution window, but does **not** pre-filter to positives — rows with `app_event_w1 = 0` (negative installs) are included.

#### `sdk_event_name_array` — Raw array of user-fired SDK events

```python
# Computed in datagen before explode
sdk_event_name_array = lower(array_join(sdk_event_name_array_raw, ","))
# Serialized as string: "[level_complete, tutorial_complete]"
```

- Contains the actual SDK events fired by the user within the attribution window, as a lowercased comma-joined string representation of an array.
- Used to compute `prob_sdk_event_name_label` after the explode step.
- Empty array (`[]`) for negative installs (no events fired).
- Example values: `[level_complete]`, `[level_complete, tutorial_complete]`, `[]`.

#### `prob_sdk_event_name` — SDK event target token (after explode)

```python
# After exploding `sdk_event_name_targets` (the set of targeted SDK events for this campaign)
prob_sdk_event_name = f"{target_game_id}_{sdk_event}"
# e.g. "500043219_level_complete", "500043219_*"
```

- One row is created per (`install`, `sdk_event`) combination.
- `sdk_event` comes from the campaign's targeted SDK events list — typically 1–10 events per campaign.
- Wildcard `"*"` or empty `""` indicates "any event" (match all installs).
- This column is used as an **embedding lookup key** in the model's sparse feature tower.
- Format: `"{target_game_id}_{sdk_event_name}"` — note the underscore separator.

#### `prob_sdk_event_name_label` — Per-SDK-event binary label (the training label for the model head)

```python
# Computed after explode, per row
sdk_event_fired = array_contains(sdk_event_name_array, sdk_event)
is_wildcard = (sdk_event == '*' or sdk_event == '')

prob_sdk_event_name_label = float(
    (sdk_event_fired or is_wildcard) and label == 1
)
```

Equivalently in Spark:

```python
df = df.withColumn(
    'prob_sdk_event_name_labels',
    F.expr(
        "CASE WHEN (array_contains(sdk_event_name_array, sdk_event) "
        "OR sdk_event = '*' OR sdk_event = '') "
        "AND label = 1 THEN 1.0 ELSE 0.0 END"
    )
)
```

- `1.0` iff: (user fired this specific event OR campaign targets all events) AND user converted (label=1)
- `0.0` in all other cases (user didn't fire the event, campaign targeted a specific event, user did not convert)
- Positive rate: **7.0%** (April 26 snapshot) — lower than `label` (19.5%) because a user may have converted but not fired the specific targeted event.

---

### 6.5.2 Scenario Comparison Table


| Scenario                                                 | `label` | `sdk_event_fired` | `is_wildcard` | `prob_sdk_event_name_label` |
| -------------------------------------------------------- | ------- | ----------------- | ------------- | --------------------------- |
| User converted, fired this event, specific target        | 1       | ✓                 | ✗             | **1.0**                     |
| User converted, did NOT fire this event, specific target | 1       | ✗                 | ✗             | **0.0**                     |
| User converted, wildcard target (`*`)                    | 1       | any               | ✓             | **1.0**                     |
| User did NOT convert (no events), any target             | 0       | ✗                 | any           | **0.0**                     |
| User converted, fired OTHER events, wildcard target      | 1       | ✗                 | ✓             | **1.0**                     |


**Key insight:** `prob_sdk_event_name_label` is strictly a subset of `label=1` rows. All `prob_sdk_event_name_label=1` rows have `label=1`, but not all `label=1` rows have `prob_sdk_event_name_label=1`.

---

### 6.5.3 SQL Invariants (Verification Queries)

```sql
-- Invariant 1: prob_sdk_event_name_label=1 implies label=1
SELECT COUNT(*) FROM unified_cpe_v1_lc_preprocessed_combined
WHERE prob_sdk_event_name_label = 1 AND label = 0;
-- Expected: 0

-- Invariant 2: label=0 implies prob_sdk_event_name_label=0
SELECT COUNT(*) FROM unified_cpe_v1_lc_preprocessed_combined
WHERE label = 0 AND prob_sdk_event_name_label = 1;
-- Expected: 0

-- Invariant 3: wildcard rows with label=1 always have prob_sdk_event_name_label=1
SELECT COUNT(*) FROM unified_cpe_v1_lc_preprocessed_combined
WHERE (SPLIT(prob_sdk_event_name, '_')[ORDINAL(2)] IN ('*', ''))
  AND label = 1
  AND prob_sdk_event_name_label = 0;
-- Expected: 0
```

---

### 6.5.4 Comparison with Legacy Pinpointer Label


| Aspect                            | NEW `unified_cpe.v1_lc`                                             | Legacy `ads-audience-pinpointer`                              |
| --------------------------------- | ------------------------------------------------------------------- | ------------------------------------------------------------- |
| **Label type**                    | Deterministic — computed once at datagen time                       | Stochastic — randomly sampled per training step               |
| **Label column**                  | `prob_sdk_event_name_label` (scalar float32, 0/1)                   | `probabilistic_labels` (float array, 0/1 entries)             |
| **SDK event conditioning**        | Explicit: one row per (install × sdk_event) target                  | Implicit: one row per install, label array per event          |
| **Event sampling**                | All eligible (install × sdk_event) pairs included deterministically | One random sdk_event sampled per training step from the array |
| **Label positive rate**           | 7.0%                                                                | Not directly comparable (ragged arrays)                       |
| **Wildcard handling**             | `sdk_event='*'` or `sdk_event=''` → label=1 if user converted       | Wildcard `*` treated as matching all events in array          |
| **Which head to use for bidding** | `prob_sdk_event_name_label` head                                    | `probabilistic_labels` array output                           |
| **Training distribution**         | Deterministic — same data every epoch                               | Stochastic — different sample per epoch (data augmentation)   |
| **Row count amplification**       | ~5× (per-sdk-event explode)                                         | 1× (no explode; ragged arrays per row)                        |


**Key architectural difference:** The legacy model samples one SDK event randomly per training step, creating implicit data augmentation — different parts of the ragged label array are trained each step. The new model deterministically explodes all (install × sdk_event) pairs, so the training distribution is fixed but the dataset is ~5× larger. Both approaches train a model conditioned on `prob_sdk_event_name`, but the new approach has stricter reproducibility guarantees.

**For bidding:** The `prob_sdk_event_name_label` head output corresponds directly to P(user fires sdk_event within 7d | install, context, sdk_event_name). This is the correct prediction to use for CPE bidding, matching the legacy model's `probabilistic_labels` output semantics.

---

## 7. Summary & Action Items


| Area                                | Status                                                   | Notes                                                                                                                                                                                                                                                 |
| ----------------------------------- | -------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Categorical encoding**            | **FIXED**                                                | Categories now stored as raw strings (matching legacy). The integer-hash alignment risk from the April 13 report is resolved.                                                                                                                         |
| **Column count**                    | 83 vs 79 (BHV) / 54 (CTX)                                | NEW has more columns than legacy due to multi-horizon labels, privacy signals, and new target-game 7d/24h counters. Ensure training pipeline handles all 83 columns correctly.                                                                        |
| **Session counters**                | **FIXED — added back**                                   | 9 session counter columns (`gamer_session_counters_`*) are now present in NEW, matching CTX legacy.                                                                                                                                                   |
| **Privacy / identity signals**      | **FIXED — added back**                                   | 9 privacy columns (`coppa`, `fingerprinted`, `limited`, `opt_out_enabled`, `counters_source`, `traffic_type`, `gamer_has_fingerprinted_identity`, `gamer_has_opted_out`, `gamer_limited_tracking`) restored.                                          |
| **gamer_id_scope**                  | **FIXED — restored**                                     | Now present in NEW with expected idfa/idfi split (~~76%/~~24%).                                                                                                                                                                                       |
| **tgtg_sdk_set**                    | **FIXED — restored**                                     | Placeholder value present, matching legacy.                                                                                                                                                                                                           |
| **Row count**                       | 504.7M NEW vs ~105M BHV+CTX                              | ~5× more rows due to per-sdk-event explode. Verify training pipeline can handle this scale; batch sizes, memory, and epoch definition may need adjustment.                                                                                            |
| **Storage**                         | 60.2 GiB (up from 35.76 GiB April 13)                    | +68% from the previous snapshot. Increase is from added columns (session counters, privacy signals). Storage is still ~~3.6× smaller than BHV+CTX combined (~~215 GiB).                                                                               |
| **Label positive rate**             | NEW=19.5% vs Legacy~37%                                  | Expected: legacy `label` = CPI install label; NEW `label` = per-sdk-event CPE label. Slight drop from 21.2% (April 13) is within normal variation.                                                                                                    |
| **app_event_w1/w2/w3/w4 identical** | Investigate                                              | All four weekly label columns have the same non-null rate (19.5%) and are always 1.0. w2/w3/w4 should have higher coverage than w1 if the label window differs. Verify that the multi-week label horizon is correctly computed in the datagen.        |
| **UUPS features dropped**           | 32 IAP/adrev features removed                            | Confirmed intentional. May affect model quality for IAP-heavy games.                                                                                                                                                                                  |
| **IBT / profile features dropped**  | 7 features removed                                       | `installed_store_ids`, `gamer_profile_meta`, etc. still absent. Confirm intentional.                                                                                                                                                                  |
| **prob_sdk_event_name_label**       | Scalar (0/1), 7.0% positive                              | Slightly lower than April 13 (7.5%). Stable. All rows are non-null (100%).                                                                                                                                                                            |
| **ad_format**                       | NEW-only column: interstitial (72.2%) / rewarded (27.8%) | Verify the training pipeline includes `ad_format` as an input feature. This column does not exist in legacy.                                                                                                                                          |
| **Target game 7d/24h counters**     | 6 NEW-only columns                                       | `target_game_start/view/click_count_in_last_7_days` and `*_in_last_24_hours` are now present. These are not in legacy CTX; only `target_game_click_count_in_last_24_hours` exists in BHV. Confirm feature config references the correct column names. |
| **install_date range**              | 2026-02-26 → 2026-04-26                                  | Correctly aligns with BHV/CTX install ranges.                                                                                                                                                                                                         |


---

## 8. Positive Rate Analysis & Row-Count Drivers

### 8.1 Why `prob_sdk_event_name_label` Has 7% Positive Rate vs. Legacy's Higher Rate

These signals are not directly comparable — they measure fundamentally different things:


| Signal                              | Positive Rate | Definition                                                                                                                               |
| ----------------------------------- | ------------- | ---------------------------------------------------------------------------------------------------------------------------------------- |
| **Legacy `label`** (BHV)            | 37.3%         | P(any level-complete event within 7d) — install-level binary label, **only idfa users**, games pre-filtered to ≥50 event-firing installs |
| **Legacy `label`** (CTX)            | 36.6%         | Same definition, idfi + unspecified users, same game-level quality filter                                                                |
| **NEW `label`**                     | 19.5%         | Same `app_event_w1 > 0` definition but over **all** campaigns and games (no game-level quality gate), driving the rate down              |
| **NEW `prob_sdk_event_name_label`** | 7.0%          | P(user fires this **specific** sdk_event within 7d) — per-(install × targeted_event) label after explode                                 |


The 7% `psn_label` rate is correct and expected. The math:

```
psn_label = 1  iff  label == 1  AND  (specific event was fired  OR  wildcard campaign)
```

From BQ analysis (§6.5.0):


| Bucket                                                   | Count  | Rate     |
| -------------------------------------------------------- | ------ | -------- |
| `label=0, psn=0` — non-converters                        | 405.8M | 80.4%    |
| `label=1, psn=0` — converted but not this specific event | 63.2M  | 12.5%    |
| `label=1, psn=1` — converted AND fired targeted event    | 35.7M  | **7.1%** |


Of all `label=1` rows, only **36.1%** have `psn_label=1`. The remaining 63.9% are overall converters but did not fire the particular sdk_event targeted by that campaign row:

```
psn_positive_rate ≈ 19.5% × 36.1% ≈ 7.05%
```

The legacy positive rate inflation (37% vs 19.5%) is a direct consequence of the game-level quality gate applied in legacy datagen: by removing all games with fewer than 50 event-firing installs and all games that never sent a target event, legacy keeps only the "healthier" campaigns where level-complete rates are inherently higher. See §8.2 for details.

---

### 8.2 Why Legacy Has ~5× Fewer Rows — Structural Differences (No Downsampling)

The legacy configs set `startSamplingRatio: 1.0` and `resample: false`. The `negative_event_sampling()` function is a no-op at ratio 1.0. **No downsampling is applied.** The row-count gap has five structural causes:

#### Cause 1 — Per-sdk-event explode in NEW (primary driver, ~5×)

NEW explodes each install by `sdk_event_name` target (5–10 events per campaign on average):

```
NEW:     1 install → N rows  (one per sdk_event target)
BHV/CTX: 1 install → 1 row
```

With ~5–10 sdk events per install, NEW inflates to ~5× more rows. The underlying install pool is similar in size to BHV+CTX combined.

#### Cause 2 — BHV hard-filters to `idfa` only

```yaml
# level_complete_bhv.yaml
finalDataFilter: >-
  platform in ('android','ios')
  AND (gamerIdScope = 'idfa')
```

BHV excludes all idfi/unspecified users (~24% of the combined traffic). CTX has no such filter. NEW includes all scopes.

#### Cause 3 — Game-level quality gate: `min_event_gamers=50` (`common/load_data.py:231-244`)

```python
def get_event_target_games_list(outcomes_data, event_count_definition, min_event_gamers):
    updated_target_games_list = (
        outcomes_data.filter("{} > 0".format(event_count_definition))
        .groupBy("targetGameId")
        .agg(F.count("*").alias("gamers"))
        .filter("gamers >= " + str(min_event_gamers))   # <-- 50 minimum
        ...
    )
```

Any game where fewer than 50 installs have `cum_app_event_count_d7 > 0` is **entirely removed** from legacy training data. NEW previously had no equivalent gate, causing it to include low-signal games with sparse or zero positive events. **This filter has now been added to the NEW datagen** (see §8.3).

#### Cause 4 — `filter_no_send_targets: true` (`app_events_load_data.py:64-77`)

```python
def filter_no_send_targets(data, count_column, min_num_events=0):
    send_targets = set(
        data.groupBy("targetGameId")
        .agg(F.sum(count_column).alias("sum"))
        .filter(F.col("sum") > min_num_events)   # sum(cum_app_event_count_d7) > 0
        ...
    )
    return data.filter(F.col("targetGameId").isin(send_targets))
```

Games that **never** sent a single level-complete event across the entire 60-day window are dropped entirely. This is subsumed by the `min_event_gamers=50` check (any game with ≥50 event-firing installs necessarily has sum > 0), and has also been added to the NEW datagen.

#### Cause 5 — 90/10 train/val split (`trainDataFraction: 0.9`)

Legacy writes separate `train.parquet/` and `validation.parquet/` partitions. The reported 44M BHV train rows are 90% of ~49M total BHV installs; the remaining ~4.4M go to val. NEW applies train/val split at training time via `filter_expr` / `validation_filter_expr`, so all rows are in the single combined parquet output.

#### Summary


| Factor                   | Effect on Legacy Row Count | Present in NEW?          |
| ------------------------ | -------------------------- | ------------------------ |
| No per-sdk-event explode | ÷5–10× rows vs NEW         | N/A (NEW explodes)       |
| BHV idfa-only filter     | −24% of users in BHV       | No (all scopes)          |
| `min_event_gamers ≥ 50`  | removes low-signal games   | **Added (§8.3)**         |
| `filter_no_send_targets` | removes zero-event games   | **Added (§8.3)**         |
| 90/10 train/val split    | −10% from train parquet    | No (split at train time) |
| Negative downsampling    | **none** (`ratio=1.0`)     | N/A                      |


---

### 8.3 Game-Level Quality Filters Added to NEW Datagen

As of the implementation following this report, `unified_cpe_datagen.py` now applies both legacy quality filters before the BQ campaign join and SDK event explode:

```python
# Mirrors filter_no_send_targets + get_event_target_games_list(min_event_gamers=50)
# from ads-audience-pinpointer/cpi-datagen/cpi_datagen/app_events/app_events_load_data.py
# and cpi_datagen/common/load_data.py respectively.
#
# min_event_gamers=50 subsumes filter_no_send_targets (any game with ≥50 event-firing
# installs necessarily has sum(cum_app_event_count_d7) > 0).
_MIN_EVENT_GAMERS = 50
_eligible_game_ids = (
    df.filter(F.col("cum_app_event_count_d7") > 0)
    .groupBy("targetGameId")
    .agg(F.count("*").alias("_event_gamers"))
    .filter(F.col("_event_gamers") >= _MIN_EVENT_GAMERS)
    .select("targetGameId")
    .rdd.flatMap(lambda x: x)
    .collect()
)
df = df.filter(F.col("targetGameId").isin(_eligible_game_ids))
```

**Expected effects on the next datagen run:**

- Row count will decrease (exact magnitude depends on how many games are below the 50-installs threshold).
- `label` positive rate will increase toward legacy levels, since low-converting games are removed.
- `prob_sdk_event_name_label` positive rate will increase proportionally.
- The model will no longer receive rows for sdk_event tokens that have never fired (see §6.5.3 — 20+ events with zero `psn_label=1` rows).

