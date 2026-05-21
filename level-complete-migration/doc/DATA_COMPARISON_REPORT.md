# Level Complete Table Comparison Report

**Legacy:** `unity-ads-dd-ds-dev-prd.yabo.bhv_level_complete_data_v2p_20260401133230`
**New (UL):** `unity-ads-dd-ds-dev-prd.yabo.unified_cpe_v1_lc_preprocessed_combined_03_29`

Generated: 2026-04-08

---

## 1. Overview


| Metric              | Legacy (bhv)                       | New (UL v1_lc)                                         |
| ------------------- | ---------------------------------- | ------------------------------------------------------ |
| **Total rows**      | 48,003,212                         | 813,863,306                                            |
| **Row structure**   | One row per install                | Row-expanded: one row per (install × target SDK event) |
| **Date range**      | 2026-01-15 → 2026-03-23 (~67 days) | 2025-12-24 → 2026-03-29 (~95 days)                     |
| **Platform filter** | Android + iOS, **IDFA only**       | Android + iOS, **IDFA + IDFI + unspecified**           |
| **nDays config**    | 60 days                            | ~96 days coverage                                      |


---

## 2. Install Counts


|                          | Legacy                    | New (UL)                                                                  |
| ------------------------ | ------------------------- | ------------------------------------------------------------------------- |
| **Distinct installs**    | 48,003,210 (≈ total rows) | ~435,910,462 (via wildcard `*` rows, de-duped by ad_req_ts + target_game) |
| **Positive installs**    | 17,138,808                | 25,119,483 (via `*` wildcard label)                                       |
| **Negative installs**    | 30,864,404                | 442,321,796 (via `*` wildcard label)                                      |
| **Approx. installs/day** | ~716K                     | ~4.6M                                                                     |


The new table has **~9x more installs** due to:

- Broader gamerIdScope coverage (IDFA + IDFI vs IDFA-only)
- Longer time window (~95 vs ~67 days)
- No `filter_no_send_targets` filtering (legacy removes targets with < 50 gamers)

---

## 3. Label Comparison

### Overall Label Rate


| Scope                    | Legacy    | New (UL)                    |
| ------------------------ | --------- | --------------------------- |
| Overall                  | **35.7%** | **22.2%** (across all rows) |
| Wildcard `*` rows only   | n/a       | 5.4%                        |
| Specific-event rows only | n/a       | ~45.0%                      |


**Critical difference:** Legacy uses a **single binary label** per install — whether the install's target game SDK event fired. The new table uses **two labels per row**:

- `label` — install-level level_complete indicator (app_event_w1)
- `prob_sdk_event_name_label` — whether the specific SDK event in `prob_sdk_event_name` was triggered

In the legacy table, label=1 **only when the install matched a specific SDK target event** (14.99M installs) + label=1 for empty arrays (2.15M). The 30.8M `UNMATCHED_INSTALL` rows are all label=0. This means the legacy label=1 means "install + triggered a level-complete SDK event in target game."

In the new table, the `*` wildcard row's `label` captures overall level-complete rate (5.4%), which is the natural rate across all installs regardless of matching.

### Legacy label breakdown


| Event type                                        | Count      | Label rate |
| ------------------------------------------------- | ---------- | ---------- |
| `UNMATCHED_INSTALL`                               | 30,864,404 | 0.0%       |
| `has_event` (specific SDK event matched)          | 14,987,105 | 100.0%     |
| `empty_array` (level complete, no specific event) | 2,151,703  | 100.0%     |


### By Platform


| Platform    | Legacy rows | Legacy label rate | New (wildcard) rows | New label rate |
| ----------- | ----------- | ----------------- | ------------------- | -------------- |
| **android** | 41,860,848  | 36.4%             | 378,571,851         | 5.1%           |
| **ios**     | 6,142,364   | 30.9%             | 88,869,428          | 6.5%           |


---

## 4. SDK Event Name Comparison

### Legacy table structure

- `**sdk_event_name`**: always `'placeholder'` (not used, set by categorical config)
- `**sdk_event_name_array**`: string-encoded array like `[af_level_achieved]` or `[10, 20]`; `[unmatched_install]` for negatives
- `**prob_sdk_event_name_array**`: RECORD — stores `{target_game_id}_{event_name}` pairs (e.g. `500247161_*`)
- `**prob_sdk_event_name_labels**`: RECORD — parallel float list of labels for each event in `prob_sdk_event_name_array`
- `**tgtg_sdk_set**`: always `'placeholder'`

Top SDK event names in legacy (positive installs only):


| Event Name               | Positive Installs |
| ------------------------ | ----------------- |
| `10`                     | 648K              |
| `af_level_achieved`      | 578K              |
| `20`                     | 414K              |
| `10_games_played`        | 440K              |
| `level_passed8`          | 372K              |
| `complete_mini_game1–10` | ~350–387K each    |


### New table structure

- `**prob_sdk_event_name**`: scalar string — one event per row (post row-expansion)
- `**prob_sdk_event_name_label**`: scalar float — label for that specific event
- `*` is the wildcard event (install-level row) — **467M / 814M = 57% of all rows**


| Row type                       | Count       | label=1 rate | avg prob_label |
| ------------------------------ | ----------- | ------------ | -------------- |
| `*` (wildcard)                 | 467,441,279 | 5.37%        | 5.37%          |
| Specific events (1,219 unique) | 346,422,027 | ~45.0%       | varies         |


Top specific events in new table:


| Event Name               | Count | label rate | avg prob_label |
| ------------------------ | ----- | ---------- | -------------- |
| `topsocre_6000_jili_30d` | 5.77M | 36.2%      | 5.1%           |
| `game_done_100`          | 5.77M | 36.2%      | 1.9%           |
| `ipu_24h_14`             | 5.77M | 36.2%      | 9.5%           |
| `ipu_24h_12`             | 5.77M | 36.2%      | 11.0%          |
| `s_custom7_revenue`      | 3.80M | 41.3%      | 2.8%           |
| `af_purchase`            | 3.36M | 34.5%      | 5.5%           |
| `level_150`              | 3.13M | 15.9%      | 8.4%           |


---

## 5. Column Comparison

### Columns in BOTH tables (shared features)


| Feature                                    | Legacy type      | New type         | Notes                                           |
| ------------------------------------------ | ---------------- | ---------------- | ----------------------------------------------- |
| `label`                                    | FLOAT NULLABLE   | INTEGER REQUIRED | Same semantic (level complete), different types |
| `gamer_start_count`                        | FLOAT NULLABLE   | FLOAT REQUIRED   |                                                 |
| `gamer_start_count_in_last_24_hours`       | FLOAT NULLABLE   | FLOAT REQUIRED   |                                                 |
| `gamer_start_count_in_last_7_days`         | FLOAT NULLABLE   | FLOAT REQUIRED   |                                                 |
| `gamer_view_count`                         | FLOAT NULLABLE   | FLOAT REQUIRED   |                                                 |
| `gamer_click_count`                        | FLOAT NULLABLE   | FLOAT REQUIRED   |                                                 |
| `gamer_install_count`                      | FLOAT NULLABLE   | FLOAT REQUIRED   |                                                 |
| `target_game_start_count`                  | FLOAT NULLABLE   | FLOAT REQUIRED   |                                                 |
| `target_game_start_count_in_last_24_hours` | FLOAT NULLABLE   | FLOAT REQUIRED   |                                                 |
| `target_game_start_count_in_last_7_days`   | FLOAT NULLABLE   | FLOAT REQUIRED   |                                                 |
| `target_game_view_count`                   | FLOAT NULLABLE   | FLOAT REQUIRED   |                                                 |
| `target_game_view_count_in_last_24_hours`  | FLOAT NULLABLE   | FLOAT REQUIRED   |                                                 |
| `target_game_view_count_in_last_7_days`    | FLOAT NULLABLE   | FLOAT REQUIRED   |                                                 |
| `target_game_click_count_in_last_24_hours` | FLOAT NULLABLE   | FLOAT REQUIRED   |                                                 |
| `platform`                                 | STRING NULLABLE  | STRING REQUIRED  |                                                 |
| `geolocation_country`                      | STRING NULLABLE  | STRING NULLABLE  |                                                 |
| `publisher_developer_id`                   | STRING NULLABLE  | STRING NULLABLE  |                                                 |
| `publisher_game_id`                        | STRING NULLABLE  | STRING NULLABLE  |                                                 |
| `publisher_store_id`                       | STRING NULLABLE  | STRING NULLABLE  |                                                 |
| `device_connection_type`                   | STRING NULLABLE  | STRING REQUIRED  |                                                 |
| `device_type`                              | STRING NULLABLE  | STRING REQUIRED  |                                                 |
| `creative_id`                              | STRING NULLABLE  | STRING REQUIRED  |                                                 |
| `campaign_id`                              | STRING NULLABLE  | STRING REQUIRED  |                                                 |
| `audience_id`                              | STRING NULLABLE  | STRING REQUIRED  |                                                 |
| `model_name`                               | STRING NULLABLE  | STRING REQUIRED  |                                                 |
| `target_game_id`                           | STRING NULLABLE  | STRING NULLABLE  |                                                 |
| `target_store_id`                          | STRING NULLABLE  | STRING NULLABLE  |                                                 |
| `creative_pack_id`                         | STRING NULLABLE  | STRING REQUIRED  |                                                 |
| `device_orientation`                       | STRING NULLABLE  | STRING REQUIRED  |                                                 |
| `video_orientation`                        | STRING NULLABLE  | STRING REQUIRED  |                                                 |
| `ad_type`                                  | STRING NULLABLE  | STRING REQUIRED  |                                                 |
| `publisher_is_coppa_targeted`              | INTEGER NULLABLE | INTEGER REQUIRED |                                                 |
| `ad_request_timestamp`                     | INTEGER NULLABLE | INTEGER REQUIRED |                                                 |
| `gamer_creation_timestamp`                 | INTEGER NULLABLE | INTEGER REQUIRED |                                                 |
| `installTimestamp`                         | INTEGER NULLABLE | INTEGER REQUIRED |                                                 |


**Nullability pattern:** New table uses `REQUIRED` for most features (no nulls), while legacy uses `NULLABLE` throughout.

---

### Columns ONLY in Legacy table


| Column                                                | Type         | Notes                                                                                                     |
| ----------------------------------------------------- | ------------ | --------------------------------------------------------------------------------------------------------- |
| `gamer_creation_delay`                                | FLOAT        | Pre-computed `min(max(ad_req_ts - gamer_creation_ts, 0), 150M)`. New table computes this at training time |
| `sdk_event_name`                                      | STRING       | Always `'placeholder'`                                                                                    |
| `tgtg_sdk_set`                                        | STRING       | Always `'placeholder'`                                                                                    |
| `sdk_event_name_array`                                | STRING       | Stringified list of matched SDK events                                                                    |
| `eventId`                                             | STRING       | Install event ID                                                                                          |
| `uups_attributed_iap_done_d7/d30`                     | STRING       | UUPS IAP done flag (categorical)                                                                          |
| `uups_unattributed_iap_done_d7/d30`                   | STRING       | UUPS IAP done flag (categorical)                                                                          |
| `uups_uasdk_iap_done_d7/d30`                          | STRING       | UUPS IAP done flag (categorical)                                                                          |
| `uups_attributed_iap_nonzero_log_avg_value_d7/d30`    | FLOAT        | UUPS IAP value features                                                                                   |
| `uups_attributed_unique_games_with_iaps_count_d7/d30` | FLOAT        |                                                                                                           |
| `uups_attributed_iap_total_count_d7/d30`              | FLOAT        |                                                                                                           |
| `uups_unattributed_iap_*_d7/d30`                      | FLOAT        | 9 UUPS unattributed scalar features                                                                       |
| `uups_uasdk_iap_*_d7/d30`                             | FLOAT        | 9 UUPS uasdk scalar features                                                                              |
| `uups_adrev_oecpm_rewarded_total_count_d7/d30`        | FLOAT        | Ad revenue features (default -1 for null)                                                                 |
| `uups_adrev_oecpm_rewarded_total_sum_d7/d30`          | FLOAT        |                                                                                                           |
| `uups_adrev_oecpm_interstitial_total_count_d7/d30`    | FLOAT        |                                                                                                           |
| `uups_adrev_oecpm_interstitial_total_sum_d7/d30`      | FLOAT        |                                                                                                           |
| `ad_req_project_id`                                   | RECORD (IBT) | IBT column                                                                                                |
| `ad_req_counts`                                       | RECORD (IBT) | IBT column                                                                                                |
| `gamer_profile_counters_adrequests_in_last_7_days`    | RECORD (IBT) | IBT column                                                                                                |
| `installed_store_ids`                                 | RECORD (IBT) | Install IBT column                                                                                        |
| `installed_store_ids_latest_start_ts`                 | RECORD (IBT) | Install IBT column                                                                                        |
| `prob_sdk_event_name_labels`                          | RECORD       | Parallel list of per-event labels                                                                         |
| `prob_sdk_event_name_array`                           | RECORD       | List of `{target_game_id}_{event_name}` strings                                                           |


---

### Columns ONLY in New table


| Column                                   | Type   | Notes                                                               |
| ---------------------------------------- | ------ | ------------------------------------------------------------------- |
| `bucket`                                 | FLOAT  | Train/val split bucket (0–1). Train: `<= 0.9`, val: `> 0.9`         |
| `gamer_id_scope`                         | STRING | `idfa` / `idfi` / `unspecified` (legacy was IDFA-only)              |
| `ad_format`                              | STRING | `interstitial` (72%) / `rewarded` (28%) — new feature not in legacy |
| `target_game_click_count`                | FLOAT  | New feature (no 24h/7d suffix version)                              |
| `target_game_click_count_in_last_7_days` | FLOAT  | New 7-day click feature                                             |
| `prob_sdk_event_name`                    | STRING | Scalar SDK event name per row (after row expansion)                 |
| `prob_sdk_event_name_label`              | FLOAT  | Per-event label (did this specific SDK event fire?)                 |


---

## 6. Shared Numeric Feature Stats (install-level comparison)


| Feature                   | Legacy avg                  | New (wildcard `*`) avg      | Notes                                      |
| ------------------------- | --------------------------- | --------------------------- | ------------------------------------------ |
| `gamer_start_count`       | 210.83                      | 162.41                      | Legacy is higher (older/more active users) |
| `gamer_view_count`        | 110.61                      | 89.33                       |                                            |
| `gamer_install_count`     | 5.59                        | 4.96                        |                                            |
| `target_game_start_count` | 3.89                        | 2.23                        | Capped at 50 in both                       |
| `gamer_creation_delay`    | avg=45.1M s, median=32.4M s | avg=35.5M s, median=20.5M s | New has lower median (younger accounts)    |


---

## 7. Key Structural Differences Summary


| Aspect                       | Legacy                                           | New (UL)                                                                |
| ---------------------------- | ------------------------------------------------ | ----------------------------------------------------------------------- |
| **Row granularity**          | 1 row per install                                | 1 row per (install x target SDK event) + 1 wildcard row                 |
| **SDK event representation** | Array stored as string; parallel label record    | Scalar string per row; scalar label per row                             |
| **gamerIdScope filter**      | IDFA only                                        | IDFA + IDFI + unspecified                                               |
| **Label type**               | Float NULLABLE                                   | Integer REQUIRED                                                        |
| **UUPS features**            | 27 UUPS scalar/categorical features              | None — UUPS features dropped                                            |
| **IBT features**             | 5 RECORD IBT columns                             | None — IBT columns dropped                                              |
| **Ad revenue features**      | 8 adrev OECPM features (rewarded + interstitial) | None                                                                    |
| **New features added**       | —                                                | `gamer_id_scope`, `ad_format`, `bucket`, `target_game_click_count[_7d]` |
| **Pre-computed delay**       | `gamer_creation_delay` stored                    | Computed at training from ts columns                                    |
| **Train/val split**          | Not stored in table                              | `bucket` column (0.9/0.1 split)                                         |
| **Distinct target games**    | 1,512                                            | 13,321                                                                  |
| **Distinct SDK events**      | ~500+ (from array)                               | 1,220 specific + `*` wildcard                                           |


---

## 8. Notable Issues / Watch Points

1. **Label rate discrepancy**: Legacy 35.7% vs new `*`-wildcard 5.4%. The semantics are different — legacy label=1 is biased toward installs that matched level-complete SDK events. The new table's `*` label is the natural install-level rate. Use `prob_sdk_event_name_label` for per-event training signal and `label` (on specific-event rows) for level-complete signal.
2. **UUPS features removed**: All 27 UUPS features (IAP signals, ad revenue signals) are absent from the new table. This is a significant feature set change that may impact model quality.
3. **IBT columns removed**: The 5 RECORD IBT columns (`ad_req_project_id`, `ad_req_counts`, etc.) are gone.
4. **Scale change**: New table is ~17x larger (814M vs 48M rows), partly from row expansion and partly from broader scope.
5. **Target game coverage**: 13,321 distinct games in new vs 1,512 in legacy — ~8.8x more game coverage, likely due to relaxed `event_based_min_event_gamers` threshold or broader data sourcing.
6. **Platform distribution shift**: Legacy was 87% android / 13% iOS. New is 80% android / 20% iOS.
7. `**gamer_creation_delay` not pre-computed**: New table requires compute at training time from `ad_request_timestamp - gamer_creation_timestamp`. The new median (20.5M s ~ 237 days) is lower than legacy (32.4M s ~ 375 days), suggesting younger gamer accounts in the broader population.

