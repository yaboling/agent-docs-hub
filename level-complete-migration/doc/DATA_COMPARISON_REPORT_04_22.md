# Data Comparison Report: unified_cpe.v1_lc vs Legacy BHV/CTX

**Date:** 2026-04-22

## Datasets

| Dataset | Path |
|---|---|
| **NEW** | `gs://unity-ads-dd-ds-prd-incremental-training-data/cpe/unified_cpe.v1_lc/preprocessed_combined/date=2026-04-13` |
| **Legacy BHV** | `gs://unity-ads-dd-ds-prd-app-training-data/level_complete/bhv_level_complete_data_v2p/20260422132512` |
| **Legacy CTX** | `gs://unity-ads-dd-ds-prd-app-training-data/level_complete/ctx_level_complete_data_v2p/20260422132417` |

---

## 1. Size & Row Counts

| Metric | NEW (unified_cpe.v1_lc) | BHV Legacy | CTX Legacy | BHV+CTX Combined |
|---|---|---|---|---|
| **Storage** | 35.76 GiB | 102.08 GiB (train) | 105.93 GiB (train) | ~208 GiB |
| **Files** | 4,802 | 2,882 (train) | 2,882 (train) | — |
| **Train rows** | TBD (60 days combined) | 46,077,371 | 62,162,704 | **108,240,075** |
| **Val rows** | — (no train/val split) | 4,557,636 | 6,146,978 | 10,704,614 |
| **Install date range** | 60 days (2026-02-13 → 2026-04-13) | 60 days | 60 days | 60 days |
| **Output partition** | Single partition `date=2026-04-13` (end date) | Separate `train.parquet/` + `validation.parquet/` | same | — |
| **Columns** | **63** | **79** | **54** | (union: 102) |

> **Note on output structure:** The Spark datagen reads all 60 install dates and writes them into a single GCS partition keyed by `train_end_date` (`date=2026-04-13`). This is different from the legacy layout which separates train and validation splits into subdirectories.
>
> **Why NEW is ~6× smaller than BHV+CTX (~208 GiB) despite the same 60-day range:**
> 1. **Different source table (primary reason)** — The new datagen reads from `installs.outcomes.v2/level_complete/d7/`, which is already pre-filtered to installs that had *any* level_complete event within 7 days. Legacy BHV/CTX reads all installs regardless of whether the user ever completed a level, making it a much larger population.
> 2. **Fewer columns** — 63 columns vs 79/54 (all UUPS IAP/adrev features dropped).
>
> Note: the new datagen does **not** filter by game. The BQ join on `campaign_audiences`/`campaign_pricing` is a `left_outer` join — games with no active level_complete campaign are kept and assigned a wildcard `"*"` sdk event target. The "1,542 games with active campaigns" in the log is an informational count, not a filter.

---

## 2. Label Analysis

| Column | NEW | BHV | CTX |
|---|---|---|---|
| `label` (positive rate) | **21.2%** | 36.9% | 36.0% |
| `app_event_w1` | 100% = 1 (only in NEW) | — | — |
| `app_event_d0/d1/d3/d7` | 100% = 1 (only in NEW) | — | — |
| `app_event_count_w1` | 25.7% positive | — | — |
| `prob_sdk_event_name_label` | 7.5% positive (scalar, 0/1) | — | — |

**Key observations:**

- `label` in NEW is ~15pp lower than legacy. Legacy `label` = CPI install label; NEW `label` = level-complete event within the label window (CPE). The 78.8% negatives are non-converters.
- NEW has **multi-horizon labels** (`app_event_d0/d1/d3/d7/w1/w2/w3/w4`) — legacy only had a single label. This enables multi-task learning across time horizons.
- `app_event_w1 = 1.0` for all rows in the sample — the source table (`installs.outcomes.v2/level_complete/d7/`) is pre-filtered to installs that had any level_complete event within 7 days, so `app_event_w1` is expected to be 1 for all rows. `label` is a per-row CPE label (likely tied to the specific sdk_event_name target after the explode step).
- `prob_sdk_event_name_label` replaces the array-based `prob_sdk_event_name_labels` — it is now a scalar `float32` (0 or 1), flattened per row.

---

## 3. Schema Differences

### Columns only in NEW (24 new columns)

```
ad_format                              <- new contextual feature
app_event_d0/d1/d3/d7                  <- multi-horizon binary labels (day-level)
app_event_w1/w2/w3/w4                  <- multi-horizon binary labels (week-level)
app_event_count_w1/w2/w3/w4            <- multi-horizon event count labels
cum_app_event_count_d0/d1/d3/d7/d14    <- cumulative event counts at multiple cutoffs
bucket                                 <- data split bucket
install_date                           <- explicit install date column
prob_sdk_event_name                    <- sdk event probability score
prob_sdk_event_name_label              <- sdk event label (scalar, replaces array)
target_game_click_count                <- total clicks (not just 24h)
target_game_click_count_in_last_7_days
```

### Columns dropped from legacy (not present in NEW)

```
# All UUPS IAP/adrev features (20 cols) — DROPPED
uups_attributed_iap_*_d7/d30           (x8)
uups_unattributed_iap_*_d7/d30         (x8)
uups_uasdk_iap_*_d7/d30               (x4)
uups_adrev_oecpm_*_d7/d30             (x8)
uups_*_iap_done_d7/d30               (x6)

# Session counters (7 cols) — DROPPED - Added back
gamer_session_counters_adrequests
gamer_session_counters_start_count / view_count
gamer_session_counters_has_tgtg_started / viewed
gamer_session_counters_performance_starts / views_count
gamer_session_counters_brand_starts / views_count

# Privacy / identity signals — DROPPED - Added back
gamer_has_fingerprinted_identity, gamer_has_opted_out, gamer_limited_tracking
limited, coppa, fingerprinted, opt_out_enabled, counters_source, traffic_type

# IBT / install history — DROPPED
installed_store_ids, installed_store_ids_channel, installed_store_ids_latest_start_ts
ad_req_project_id, ad_req_counts, gamer_profile_counters_adrequests_in_last_7_days
gamer_profile_meta

# Other — DROPPED
tgtg_sdk_set(place holder in Legacy), eventId (Added back)
prob_sdk_event_name_labels (array) -> replaced by prob_sdk_event_name_label (scalar)
```

---

## 4. Categorical Encoding — Critical Difference

In the legacy datasets, categorical columns are stored as **raw strings**. In the new dataset they are **pre-hashed to integers** at datagen time.

```
platform:
  NEW:  {-1971035589: 79%, 486895588: 21%}   <- INTEGER HASHED
  BHV:  {'android': 87%, 'ios': 13%}          <- STRINGS
  CTX:  {'android': 75%, 'ios': 25%}

gamer_id_scope:
  NEW:  {-1300946649: 76%, 705192617: 24%}    <- INTEGER HASHED
  CTX:  {'idfa': 74%, 'idfi': 26%}
  BHV:  MISSING (BHV is all idfa)
```

The hash `-1971035589` maps to `android`, `486895588` maps to `ios`. Verify that the training pipeline's embedding lookup uses the same hash function.

---

## 5. Scalar Feature Statistics

Statistics computed from one sample row group per dataset.

| Feature | NEW mean / std | BHV mean / std | CTX mean / std |
|---|---|---|---|
| `gamer_start_count` | 161.6 / 352.1 | **213.7 / 417.0** | 181.0 / 372.7 |
| `gamer_start_count_in_last_24_hours` | 3.9 / 6.7 | 4.3 / 7.2 | 3.9 / 6.7 |
| `gamer_start_count_in_last_7_days` | 15.3 / 27.6 | **17.8 / 30.0** | 15.9 / 28.3 |
| `gamer_view_count` | 87.6 / 213.9 | **111.5 / 245.0** | 96.0 / 223.1 |
| `gamer_click_count` | 26.7 / 55.5 | **30.6 / 60.0** | 26.6 / 57.3 |
| `gamer_install_count` | 4.6 / 12.1 | **5.7 / 13.7** | 4.5 / 11.6 |
| `gamer_creation_delay` | 35.0M / 39.9M | **45.7M / 41.7M** | 36.9M / 40.7M |
| `target_game_start_count` | 3.49 / 7.62 | 3.89 / 8.09 | MISSING |
| `target_game_view_count` | 2.07 / 5.39 | 2.22 / 5.62 | MISSING |
| `target_game_click_count_in_last_24_hours` | 0.19 / 0.46 | 0.18 / 0.46 | MISSING |
| `publisher_is_coppa_targeted` | 3.8% | 0.0% | 2.7% |

BHV users are consistently more engaged (higher counters) — expected since BHV = identified users with rich behavioral history. CTX users are closer to NEW in engagement stats, consistent with the new dataset being a BHV+CTX mix.

---

## 6. Traffic Mix

| | NEW | BHV | CTX |
|---|---|---|---|
| Android share | ~79% | 87% | 75% |
| iOS share | ~21% | 13% | 25% |
| idfa (BHV) share | ~76% | 100% | 74% |
| idfi/unspecified (CTX) share | ~24% | 0% | 26% |

The new dataset correctly combines both traffic types (BHV + CTX), with a platform mix that sits between the two legacy datasets.

---

## 7. Summary & Action Items

| Area | Status | Notes |
|---|---|---|
| **Row count coverage** | NEW covers 60 days in a single partition | Verify total row count against BHV+CTX (108M train rows) — NEW should be lower due to CPE-game filtering (1,542 games) |
| **Label positive rate** | NEW=21.2% vs Legacy~37% | Different definition: legacy `label` = CPI install; NEW `label` = per-sdk-event CPE label — expected, not a bug |
| **app_event_w1 = 1.0 always** | Expected | Source table pre-filters to installs with any level_complete event in d7; `app_event_w1=1` is correct. `label` is the per-sdk-event target, not the raw app_event flag |
| **Categorical hashing** | NEW pre-hashes to int | Verify hash function matches the training pipeline's embedding lookup |
| **UUPS features dropped** | 20 IAP/adrev features removed | Confirm intentional; may affect model quality for IAP-heavy games |
| **Session counters dropped** | 7 features removed | CTX-specific session features gone; check if compensated by new features |
| **Multi-horizon labels** | NEW has 8 label columns | Confirm which column (`label` or `app_event_w1`) is used as the primary training target |
| **prob_sdk_event_name_label** | Scalar (0/1), 7.5% positive | Very low positive rate — verify correctness against legacy `prob_sdk_event_name_labels` |
| **sdk_event_name** | `placeholder` in all datasets | Routing still done via `prob_sdk_event_name_label`; no regression here |
