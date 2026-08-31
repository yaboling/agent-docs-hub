# CE v1 vs LC v3: Deep Dive Comparison Report

**Date**: 2026-08-19
**Analysis**: `lc_v3_vs_ce_v1`
**Tool**: `compare-dataset-stats` skill

---

## Datasets

| | LC v3 | CE v1 |
|---|---|---|
| **GCS path** | `gs://unity-ads-dd-ds-prd-incremental-training-data/user_value/unified_user_value.v11_cpe_lc_v3/preprocessed_combined/date=2026-08-09` | `gs://unity-ads-dd-ds-prd-incremental-training-data/user_value/unified_user_value.v11_cpe_ce_v1/preprocessed_combined/date=2026-08-09` |
| **Population** | Attributed installs only | Attributed + unattributed installs |
| **Training window** | 88 days | 88 days |
| **Row count** | ~46M | ~5.8B |
| **Schema fields** | 87 | 74 |

---

## 1. Data Volume

CE v1 is **~126x larger** than LC v3 (5.8B vs 46M rows), driven almost entirely by unattributed installs:

| Metric | LC v3 | CE v1 |
|---|---|---|
| Total rows | ~46M | ~5.8B |
| Size ratio | 1x | ~126x |
| Attributed fraction | 100% | ~1.7% (derived from counter positive_rate) |

The `is_attributed` column exists only in CE v1 (not in LC v3), confirming that LC v3 was generated from an already-filtered attributed-only source.

---

## 2. Schema Differences

### Fields in CE v1 only (5)
These are columns added specifically for CE tracking:

| Field | Meaning |
|---|---|
| `cum_has_event_d7` | Cumulative event occurrence within 7 days |
| `cum_has_event_d14` | Cumulative event occurrence within 14 days |
| `cum_has_event_d28` | Cumulative event occurrence within 28 days |
| `cum_has_lc_event_d7` | Level complete event within 7 days |
| `is_attributed` | Whether the install is attributed (0/1) |

### Fields in LC v3 only (18)
These are retained events / app-event horizon features from LC data that CE does not produce:

| Field | Notes |
|---|---|
| `app_event_d0`, `d1`, `d3`, `d7` | App event occurrence by day horizon |
| `app_event_w1`, `w2`, `w3`, `w4` | App event occurrence by week horizon |
| `app_event_count_w1`, `w2`, `w3`, `w4` | App event count by week horizon |
| `cum_app_event_count_d0`, `d1`, `d3`, `d7`, `d14` | Cumulative app event counts |
| `date` | Training date partition column (inferred from GCS path) |

**Implication**: CE v1 has fewer label/event features. The CE-style labels (`cum_has_event_*`) replace LC's `app_event_*` and `cum_app_event_count_*` columns.

---

## 3. Label Analysis

### Label Rate

| Metric | LC v3 | CE v1 | Diff |
|---|---|---|---|
| `label` mean | 0.2826 | 0.2075 | **26.6% relative drop** |
| `label=1` rate | 28.3% | 20.8% | -7.5 pp |
| `label=0` rate | 71.7% | 79.3% | +7.5 pp |

**Interpretation**: LC v3 has a 28.3% positive label rate (attributed installs who converted). CE v1 has a 20.8% positive label rate — a 26.6% relative decrease. This is expected: CE v1 includes a large volume of unattributed installs, most of which have no downstream event signals, dragging the label rate down. The conversion rate for attributed installs in CE v1 alone is likely similar to LC v3.

### `prob_sdk_event_name_label`

| Metric | LC v3 | CE v1 | Diff |
|---|---|---|---|
| mean | 0.1274 | 0.1061 | **16.8% drop** |
| positive_rate | 12.7% | 10.6% | -2.1 pp |

The soft label for SDK event probability also drops — consistent with the lower attributed fraction in CE v1.

---

## 4. Feature Statistics

### Gamer Activity Counters (All ~98% lower in CE v1)

All gamer behavioral counters are dramatically lower in CE v1 because ~98.3% of CE installs are unattributed and have no gamer history:

| Feature | LC v3 mean | CE v1 mean | Relative diff |
|---|---|---|---|
| `gamer_start_count` | 157.9 | 2.684 | **98.3%** |
| `gamer_view_count` | 82.5 | 1.403 | **98.3%** |
| `gamer_click_count` | 26.64 | 0.4517 | **98.3%** |
| `gamer_install_count` | 4.014 | 0.06833 | **98.3%** |
| `gamer_start_count_in_last_7_days` | 17.3 | 0.2936 | **98.3%** |
| `gamer_start_count_in_last_24_hours` | 4.523 | 0.07704 | **98.3%** |
| `target_game_start_count` | 3.427 | 0.05761 | **98.3%** |
| `target_game_view_count` | 1.927 | 0.03243 | **98.3%** |
| `target_game_click_count` | 0.7756 | 0.01293 | **98.3%** |

The consistent ~98.3% reduction aligns exactly with the ~1.7% attributed fraction in CE v1. The positive_rate in CE v1 (~1.7%) matches the positive_rate in LC v3 (~55–95%) scaled by ~0.017 — confirming the counter values are correct for the attributed subset; unattributed installs simply have 0.

### Session Counters — Entirely Zero in CE v1

All 9 `gamer_session_counters_*` features are 0.0 for every row in CE v1:

| Feature | LC v3 mean | CE v1 mean |
|---|---|---|
| `gamer_session_counters_adrequests` | 2.163 | 0.0 |
| `gamer_session_counters_start_count` | 1.134 | 0.0 |
| `gamer_session_counters_view_count` | 0.498 | 0.0 |
| `gamer_session_counters_performance_starts_count` | 0.919 | 0.0 |
| `gamer_session_counters_performance_views_count` | 0.454 | 0.0 |
| `gamer_session_counters_has_tgtg_started` | 0.016 | 0.0 |
| `gamer_session_counters_has_tgtg_viewed` | 0.048 | 0.0 |
| `gamer_session_counters_brand_starts_count` | 0.215 | 0.0 |
| `gamer_session_counters_brand_views_count` | 0.043 | 0.0 |

**CE v1 has zero values for all 9 session counters.** CE data has no `gamerSessions` struct; these columns are correctly defaulted to 0 in the datagen script but provide zero training signal.

### Hardware Stats (~98% lower in CE v1)

| Feature | LC v3 positive_rate | CE v1 positive_rate |
|---|---|---|
| `hardware_stats_cpu_count` | 3.4% | 0.06% |
| `hardware_stats_dpi` | 3.4% | 0.06% |
| `hardware_stats_ram` | 3.4% | 0.06% |

Hardware stats are nearly absent in CE v1. Only attributed installs tend to have device hardware data.

### Privacy / Attribution Signals

| Feature | LC v3 | CE v1 |
|---|---|---|
| `fingerprinted` | 28.9% positive | **0% positive** |
| `gamer_has_fingerprinted_identity` | 28.9% positive | **0% positive** |
| `gamer_has_opted_out` | 30.5% positive | 0.5% positive |
| `gamer_limited_tracking` | 28.3% positive | 0.5% positive |
| `limited` | 28.3% positive | 0.5% positive |
| `coppa` | 2.7% positive | 0.05% positive |

`fingerprinted` is completely absent in CE v1. Fingerprinting is an attribution-only signal unavailable for unattributed installs.

### Timestamps (Zero-inflated in CE v1)

| Feature | LC v3 positive_rate | CE v1 positive_rate |
|---|---|---|
| `ad_request_timestamp` | 100% | **1.7%** |
| `gamer_creation_timestamp` | 100% | **1.7%** |
| `gamer_creation_delay` | 99.7% | **1.7%** |

Timestamps default to 0 for unattributed installs. In LC v3, all rows have valid unix-second timestamps. In CE v1, only the ~1.7% attributed rows have non-zero timestamps.

---

## 5. Feature Drift

### Distribution Shifts (key fields)

| Feature | LC v3 | CE v1 | Finding |
|---|---|---|---|
| `bucket` | mean 0.495 | mean 0.421 | **14.9% drop** — CE v1 model scores lower on average |
| `label` | 28.3% positive | 20.8% positive | **26.6% drop** — population dilution |
| `platform` | entropy 0.621 | entropy 0.690 | 9.9% shift, 14.5% distribution diff |
| `geolocation_country` | 228 countries | 245 countries | 8.4% entropy drop |
| `install_date` | entropy 4.464 | entropy 4.240 | 5% difference |
| `sdk_event_name` | 829 unique | 1,269 unique | **34.7% more events in CE v1** |
| `prob_sdk_event_name` | 1,318 unique | 2,130 unique | **38.1% more values in CE v1** |
| `counters_source` | entropy 0.673 | entropy 0.690 | 2.4% (minor) |

### Publisher / Advertiser ID Collapse

| Feature | LC v3 entropy | CE v1 entropy | Diff |
|---|---|---|---|
| `publisher_developer_id` | 4.032 | 0.106 | **97.4% collapse** |
| `publisher_game_id` | 4.206 | 0.058 | **98.6% collapse** |
| `publisher_store_id` | 4.208 | 0.058 | **98.6% collapse** |
| `target_store_id` | 4.263 | 0.123 | **97.1% collapse** |
| `target_developer_id` | 3.734 | 0.145 | **96.1% collapse** |
| `audience_id` | 4.290 | ~0 | **99.98% collapse** — cardinality=1 |
| `campaign_id` | 4.290 | ~0 | **99.98% collapse** — cardinality=1 |

**Critical finding**: Publisher and advertiser ID diversity completely collapses in CE v1. `audience_id` and `campaign_id` have cardinality=1 — a single "null"-equivalent value for all rows. Unattributed installs don't have specific campaign or audience assignments.

`model_name` has 16% more unique values in CE v1 (106 vs 89) but much lower entropy (0.12 vs 2.19), dominated by a few model names.

### Device / Connection / Traffic

| Feature | LC v3 entropy | CE v1 entropy | Diff |
|---|---|---|---|
| `device_connection_type` | 0.553 | 0.095 | **82.8% drop** |
| `device_orientation` | 0.374 | 0.092 | **75.4% drop** |
| `device_type` | 4.275 | 0.072 | **98.3% drop** |
| `gamer_id_scope` | 0.616 | 0.096 | **84.4% drop** |
| `traffic_type` | 0.615 | 0.096 | **84.4% drop** (3 vs 2 categories) |

All device/connection features show dramatic diversity collapse. Unattributed installs have limited device metadata enrichment, and CE v1 has an extra `traffic_type` category for unattributed traffic.

### `sdk_event_name_array` Null Rate

| | LC v3 | CE v1 |
|---|---|---|
| null_rate | 71.7% | **0%** |

CE v1 populates `sdk_event_name_array` for all rows. LC v3 leaves it null for ~72% of rows. This significant difference suggests CE v1 produces non-null arrays (possibly empty) even for unattributed installs.

---

## 6. Anomalies

| # | Anomaly | Impact |
|---|---|---|
| 1 | **Session counters all-zero in CE v1** | 9 features carry zero training signal; safe to drop |
| 2 | **`audience_id`, `campaign_id` cardinality=1** | Features meaningless in CE v1; safe to exclude |
| 3 | **`fingerprinted` always 0 in CE v1** | No signal; safe to exclude |
| 4 | **Timestamps 0 for 98.3% of CE v1 rows** | Models may learn zero as the "normal" value; consider exclusion or interaction with `is_attributed` |
| 5 | **Publisher/game ID entropy near-zero** | These ID lookups are effectively useless for CE v1 |
| 6 | **Label dilution 26.6% relative drop** | Post-training calibration required |
| 7 | **`sdk_event_name_array` 0% null in CE v1 vs 72% in LC v3** | Different construction logic; verify CE arrays are semantically correct for unattributed installs |

---

## 7. Summary

| Category | LC v3 | CE v1 | Verdict |
|---|---|---|---|
| Volume | ~46M rows | ~5.8B rows | CE is 126x larger |
| Label rate | 28.3% | 20.8% | 26.6% relative drop (expected) |
| Counter coverage | 55–95% non-zero | 1.7% non-zero | 98.3% dilution from unattributed |
| Session counters | Rich signal | All zero | Dead features in CE v1 |
| Timestamps | 100% valid | 1.7% valid | Zero-inflated in CE v1 |
| Publisher/audience IDs | High diversity | Collapsed to 1 value | Meaningless in CE v1 |
| fingerprinted | 28.9% positive | 0% | No signal in CE v1 |
| SDK event diversity | 829 names | 1,269 names | Broader in CE v1 |
| Geographic coverage | 228 countries | 245 countries | Slightly broader in CE v1 |

---

## 8. Recommendations

1. **Drop zero-signal features for CE v1 model**: Remove `gamer_session_counters_*` (9 features), `fingerprinted`, `gamer_has_fingerprinted_identity`, `audience_id`, `campaign_id` from the CE v1 feature config.

2. **Handle zero-inflated timestamps**: Exclude `ad_request_timestamp`, `gamer_creation_timestamp`, `gamer_creation_delay` from CE v1 features, or gate them with an `is_attributed` interaction to separate the two populations.

3. **Include `is_attributed` as a feature**: CE v1 contains two distinct populations with very different feature distributions. Making `is_attributed` explicit lets the model separate them cleanly.

4. **Post-training calibration**: After training, verify CE v1 model calibration separately on attributed vs unattributed slices. The 26.6% label dilution means raw scores will need recalibration.

5. **Offline evaluation on attributed slice only**: When comparing CE v1 model quality against LC v3, compute offline metrics on `is_attributed=1` rows only for apples-to-apples comparison.

6. **Investigate `sdk_event_name_array` null rate**: Verify that the 0% null rate in CE v1 is intentional and arrays are semantically correct for unattributed installs.

---

## Output Files

| File | Description |
|---|---|
| `ads-unified-learner/analysis/lc_v3_vs_ce_v1/sql_lc_v3_clean.sql` | BQ SQL for LC v3 stats (date=2026-08-09 filter) |
| `ads-unified-learner/analysis/lc_v3_vs_ce_v1/sql_ce_v1_clean.sql` | BQ SQL for CE v1 stats |
| `ads-unified-learner/analysis/lc_v3_vs_ce_v1/results_lc_v3.json` | Raw BQ results for LC v3 (87 fields) |
| `ads-unified-learner/analysis/lc_v3_vs_ce_v1/results_ce_v1.json` | Raw BQ results for CE v1 (74 fields) |
| `ads-unified-learner/analysis/lc_v3_vs_ce_v1/stats_lc_v3.parquet` | Per-field stats parquet for LC v3 |
| `ads-unified-learner/analysis/lc_v3_vs_ce_v1/stats_ce_v1.parquet` | Per-field stats parquet for CE v1 |
| `ads-unified-learner/analysis/lc_v3_vs_ce_v1/comparison.html` | Self-contained HTML comparison report |
