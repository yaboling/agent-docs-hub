# LC → CE Data Migration & Model Expansion Plan

**Scope**: Upgrade `unified_user_value.v11_cpe_lc_v2` (Level Complete) to `unified_user_value.v11_cpe_ce_v1` (Custom Event)
**Date**: 2026-08-04
**Author**: Investigation via Claude Code

---

## 1. Current State vs Target State

| Dimension | v11_cpe_lc_v2 (LC, current) | v11_cpe_ce_v1 (CE, target) |
|-----------|------------------------------|------------------------------|
| Data path | `unity-ads-dd-ds-prd-data-anon/.../level_complete/d7/` | `data-ads-app-prd/.../primary_conversion_enriched_profiles_v2` |
| Horizons | Single: `d7/` only | Multi: `d0, d1, d3, d7, d14, d21, d28` |
| Installs | Attributed only | Attributed **and** unattributed (`is_attributed` column) |
| Partition key | `installDate=YYYY-MM-DD` | `install_date=YYYY-MM-DD` per horizon subfolder |
| General label | `app_event_w1 > 0` (null → 0) | `cum_has_event_d7 == 1` (INT 0/1/null: any custom or LC event in 7d; ~83% null = no MMP tracking) |
| Event array | `sdk_event_name_array` (pre-built string array) | `sdk_event_name_first_seen_arr` (array of {name, timestamp} structs) |
| Campaign filter | `app_event_conversion_type = 'LEVEL_COMPLETE'` | `app_event_conversion_type = 'LEVEL_COMPLETE'` (unchanged — `CUSTOM` not yet available, see TODO #1) |
| LC-specific columns | Primary signal | Available separately as `sdk_event_name_first_seen_arr_lc` / `cum_has_lc_event_d7` |

---

## 2. What Is Broken in `v11_cpe_ce_v1` Right Now

The experiment was copied from `v11_cpe_lc_v2` and only superficially renamed. The following are concrete bugs:

### `workflow.py`

| Line | Problem |
|------|---------|
| 15 | `_CE_DATA_PATH` still points to the **old LC GCS path** (`unity-ads-dd-ds-prd-data-anon/...level_complete/d7/`) |
| 19 | `_PREPROCESSED_COMBINED_PATH` still uses `v11_cpe_lc_v2` namespace |
| 28-53 | `_get_latest_lc_install_date` lists `installDate=` partitions from a flat path — CE data is structured as `{base}/{horizon}/install_date={date}`, requiring horizon-aware discovery |
| 66 | Schedule name still says `user-value-v11-cpe-lc-v2-...` |
| 352-356 | `refresh_calibration` imports from `v11_cpe_lc_v2.scripts` — will fail at runtime |

### `config.json`

All of the following still reference `v11_cpe_lc_v2`:
- `experiment`
- `dataset_config.dataset_id`
- `dataset_config.table_id`
- `datagen_config.raw_data_path`
- `datagen_config.mapping_path`
- `description`

### `unified_cpe_datagen.py`

No CE-specific Spark script exists yet. The LC script (`unified_cpe_datagen.py`) is currently what the workflow references via `spark_script_path`, and it has `--lc_data_path` as an argument — incompatible with the CE data layout.

---

## 3. Change 1: Data Path & Horizon Logic

### 3.1 Correct `_CE_DATA_PATH`

```python
_CE_DATA_PATH = "gs://data-ads-app-prd/roas/ads.events.operativeecpm.installs.outcomes.profile.join.primary_conversion_enriched_profiles_v2"
```

### 3.2 Horizon Selection Logic

The CE data is partitioned as:
```
{_CE_DATA_PATH}/{horizon}/install_date={YYYY-MM-DD}/
```

Each horizon folder only contains install dates where the label is fully settled:
- `d7/` contains installs from at least 7+2=9 days ago
- `d14/` contains installs from at least 14+2=16 days ago
- etc.

The function `get_outcome_paths()` in
`src/unity_learner/data/spark/user_value/filters/utils.py:117` already implements
the correct greedy assignment: for `base_horizon="d7"`, installs are assigned to the
deepest available horizon (d28 > d21 > d14 > d7).

The per-horizon install date cutoff formula is:
```
earliest_allowed_install_date_for_horizon_H = train_end - (H_days - base_horizon_days)
```

Example with `train_end = 2026-07-26` (today=2026-08-04 minus 9 days):

| Horizon | Cutoff | Install date range |
|---------|--------|--------------------|
| d28 | train_end - 21 = 2026-07-05 | Up to 2026-07-05 |
| d21 | train_end - 14 = 2026-07-12 | 2026-07-06 to 2026-07-12 |
| d14 | train_end - 7  = 2026-07-19 | 2026-07-13 to 2026-07-19 |
| d7  | train_end - 0  = 2026-07-26 | 2026-07-20 to 2026-07-26 |

**Do NOT include d0/d1/d3** — `cum_has_event_d7` is not yet settled for those installs.

### 3.3 Workflow `_get_latest_ce_install_date`

Replace `_get_latest_lc_install_date` with a function that lists the `d7/` subfolder:

```python
def _get_latest_ce_install_date(ce_data_path: str) -> str:
    """Return the latest install_date= partition available in the CE d7 subfolder."""
    from google.cloud import storage as gcs_storage
    import re

    d7_path = ce_data_path.rstrip("/") + "/d7/"
    assert d7_path.startswith("gs://")
    gcs_path = d7_path[5:]
    bucket_name, prefix = gcs_path.split("/", 1)
    client = gcs_storage.Client()
    bucket = client.bucket(bucket_name)
    blobs = bucket.list_blobs(prefix=prefix, delimiter="/")
    for _ in blobs:
        pass
    dates = []
    for p in blobs.prefixes:
        m = re.search(r"install_date=(\d{4}-\d{2}-\d{2})", p)
        if m:
            dates.append(m.group(1))
    if not dates:
        raise RuntimeError(f"No install_date= partitions found under {d7_path}")
    return max(dates)
```

Note: CE uses `install_date=` (snake_case), not `installDate=` (camelCase) as in LC.

---

## 4. Change 2: Attributed vs Unattributed Data

### How UV datagen handles this

The standard UV incremental datagen (`user_value_incremental_datagen.yaml`) uses **completely separate pipelines**:
- `mmp_attributed.py` — separate schema normalization (BQ AGC features, attribution partner, etc.)
- `mmp_unattributed.py` — separate normalization (deviceType lookup from BQ, derived gamerIdScope, etc.)

These are then unioned after independent processing.

### How CE data handles this

The CE path already unifies attributed and unattributed into a **single consistent schema** with `is_attributed: bool` as a discriminator column. This is a major simplification:

- **No separate pipeline needed** — both live under the same `{horizon}/install_date=` partition
- The upstream CE enrichment pipeline already normalized the schema
- `is_attributed = True` → Unity-attributed installs (full gamer counter data available)
- `is_attributed = False` → Unattributed/organic installs (some counter fields may be null)

### Plan for CE datagen

1. Read all horizon paths together with `mergeSchema=true` (same as LC)
2. Apply `add_counter_col(..., default=0.0)` guards for all nullable struct fields (same pattern already in LC datagen)
3. Add `is_attributed` as a pass-through feature — can optionally be added to the model as a dense scalar signal (attributed installs are higher quality targets for custom events)
4. **No is_attributed filtering** — train on both; label correctness is guaranteed by CE ETL

---

## 5. Change 3: General Label

### Old (LC)

```python
# app_event_w1 is a cumulative count; null = LEFT JOIN miss = no event
df = df.withColumn(
    "label",
    F.when(F.col("app_event_w1") > 0, F.lit(1)).otherwise(F.lit(0)),
)
```

### New (CE)

`cum_has_event_d7` is a boolean column — `True` if any custom event (LC or CE) occurred on or before day 7 after install.

```python
# cum_has_event_d7 is bool; null treated as 0
df = df.withColumn(
    "label",
    F.when(F.col("cum_has_event_d7").isNotNull() & F.col("cum_has_event_d7"), F.lit(1)).otherwise(F.lit(0)),
)
```

### Quality filter change

Old: `df.filter(F.col("cum_app_event_count_d7") > 0)`

New: `df.filter(F.col("cum_has_event_d7") == True)`

The minimum event gamers threshold (_MIN_EVENT_GAMERS = 50) remains unchanged.

---

## 6. Change 4: PSN Label

This is the most significant change.

### 6.1 Old Approach (LC)

```
Source:   sdk_event_name_array — Array<String> of all SDK event names fired by user
Campaign: app_event_conversion_type = 'LEVEL_COMPLETE'
Check:    array_contains(sdk_event_name_array, sdk_event) OR sdk_event = '*'
```

### 6.2 New Approach (CE)

```
Source:   sdk_event_name_first_seen_arr — Array<Struct<sdk_event_name: STRING, first_seen_at: TIMESTAMP>>
Filter:   only entries where TIMESTAMP_DIFF(first_seen_at, install_time, SECOND) <= 7 * 86400
Campaign: app_event_conversion_type = 'LEVEL_COMPLETE' (unchanged for now — CUSTOM not yet available, see TODO #1)
Check:    array_contains(filtered_event_names, sdk_event) OR sdk_event = '*'
```

### 6.3 Step-by-Step PSN Label Pipeline

**Step 1**: Parse `sdk_event_name_first_seen_arr` into a filtered event name set:

```python
_SEVEN_DAYS_SECONDS = 7 * 24 * 3600

@F.udf(ArrayType(StringType()))
def _udf_events_within_7d(event_arr, install_time):
    """Extract CE event names fired within 7d of install from sdk_event_name_first_seen_arr.

    event_arr: list of Row(sdk_event_name=str, first_seen_at=datetime)
    install_time: datetime (TIMESTAMP from CE parquet)
    first_seen_at is TIMESTAMP (not unix seconds), so subtract directly as datetime objects.
    """
    if not event_arr or install_time is None:
        return []
    result = []
    for entry in event_arr:
        name = entry["sdk_event_name"]
        ts = entry["first_seen_at"]
        if name and ts is not None:
            diff_seconds = (ts - install_time).total_seconds()
            if 0 <= diff_seconds <= _SEVEN_DAYS_SECONDS:
                result.append(name.lower())
    return result

df = df.withColumn(
    "sdk_event_name_array",  # reuse column name — downstream PSN stages unchanged
    _udf_events_within_7d(F.col("sdk_event_name_first_seen_arr"), F.col("install_time")),
)
```

**Step 2**: BQ campaign query — **keep `LEVEL_COMPLETE` filter unchanged for now**.

`CUSTOM` as an `app_event_conversion_type` value does not exist yet in `campaigns_v3`. The CE model continues to use the same `LEVEL_COMPLETE` campaign filter as the LC model for the initial launch. Adding `CUSTOM` to this filter is deferred until that conversion type is available (see TODO #1).

```python
_BQ_CAMPAIGN_QUERY = """
SELECT
  CAST(game_id AS STRING) AS target_game_id,
  campaignset_id,
  sdk_event_names AS sdk_event_name_set
FROM `unity-data-ads-core-prd.ads_dimension_data.campaigns_v3`
WHERE app_event_conversion_type = 'LEVEL_COMPLETE'
  AND archived_at IS NULL
"""
```

**Steps 3–5**: Structurally identical to LC:
- Aggregate targeted events per game (collect_set, wildcard '*' for 0-event campaigns)
- Join installs with campaign targets; create `prob_sdk_event_name_labels` array
- Probabilistic sampling: one (event_token, label) pair per install
- Filter installs predating first positive conversion for each game

### 6.4 LC-only Labels (for reference / future use)

The CE data also provides LC-specific arrays:
- `sdk_event_name_first_seen_arr_lc` — same structure as `sdk_event_name_first_seen_arr` but only LC events
- `cum_has_lc_event_d7` — boolean, only LC events within 7d

These are available if a future model variant wants to separate LC and CE PSN signals.

---

## 7. Files That Need Changes

| File | Changes Required | Priority |
|------|-----------------|----------|
| `v11_cpe_ce_v1/config.json` | Fix experiment, dataset_id, table_id, raw_data_path, mapping_path, description | P0 |
| `v11_cpe_ce_v1/workflow.py` | Fix `_CE_DATA_PATH`, `_PREPROCESSED_COMBINED_PATH`, implement `_get_latest_ce_install_date`, pass horizons to Spark, fix schedule name, fix refresh_calibration import | P0 |
| `data/spark/user_value/unified_cpe_ce_datagen.py` | **New file**: horizon paths, new label, new PSN from `sdk_event_name_first_seen_arr`, CUSTOM campaigns | P0 |
| `v11_cpe_ce_v1/features.py` | Optionally add `is_attributed` as dense scalar; rename `dense_lc_features` → `dense_ce_features` | P1 |
| `v11_cpe_ce_v1/model.py` | No functional changes needed; update docstrings | P2 |

---

## 8. `config.json` Changes (v11_cpe_ce_v1)

Every `v11_cpe_lc_v2` reference must be replaced with `v11_cpe_ce_v1`:

```json
{
  "experiment": "unified_user_value.v11_cpe_ce_v1",
  "dataset_config": {
    "dataset_id": "unified_user_value_v11_cpe_ce_v1",
    "table_id": "unified_user_value_v11_cpe_ce_v1_preprocessed_combined"
  },
  "datagen_config": {
    "raw_data_path": "gs://unity-ads-dd-ds-prd-incremental-training-data/user_value/unified_user_value.v11_cpe_ce_v1/preprocessed_combined/",
    "mapping_path": "gs://unity-ads-dd-ds-prd-incremental-training-data/user_value/unified_user_value.v11_cpe_ce_v1/feature_mapping.json"
  },
  "description": "Custom event binary classifier (P(any custom SDK event within 7d of install)). Extends v11_cpe_lc_v2 to cover both Level Complete and Custom Event campaigns."
}
```

Also update `trainer_config.callbacks` from `"cpe_lc_v2_metrics_callback"` to `"cpe_ce_v1_metrics_callback"` (or keep LC callback if CE metrics are identical).

---

## 9. `workflow.py` Changes (v11_cpe_ce_v1)

### Constants block

```python
# New correct CE data path
_CE_DATA_PATH = "gs://data-ads-app-prd/roas/ads.events.operativeecpm.installs.outcomes.profile.join.primary_conversion_enriched_profiles_v2"

# Updated namespace
_PREPROCESSED_COMBINED_PATH = "gs://unity-ads-dd-ds-prd-incremental-training-data/user_value/unified_user_value.v11_cpe_ce_v1/preprocessed_combined/"
```

### Schedule decorator

```python
@schedule(
    cron="0 15 * * *",
    timezone="Etc/UTC",
    schedule_run_name="user-value-v11-cpe-ce-v1-workflow-scheduled-15-utc"
)
```

### `run_datagen` — Spark args

```python
args={
    "working_dir": self.working_dir,
    "train_end_date": train_end,
    "train_start_date": train_start,
    "ce_data_path": _CE_DATA_PATH,
    "horizons": "d7,d14,d21,d28",  # new: tells datagen which horizon folders to read
    "output_path": output_path,
    "num_partitions": str(num_partitions),
},
```

### `refresh_calibration` import

```python
from unity_learner.experiment_repo.unified_user_value.v11_cpe_ce_v1.scripts.refresh_product_accuracy_calibration import (
    run as refresh_run,
)
```

---

## 10. New Spark Script Outline (`unified_cpe_ce_datagen.py`)

```
Arguments:
  --train_end_date      YYYY-MM-DD  last install date (= latest in d7 folder)
  --train_start_date    YYYY-MM-DD  first install date (train_end minus train_duration - 1)
  --ce_data_path        gs://...    base CE GCS path (no horizon suffix)
  --horizons            d7,d14,d21,d28  comma-separated list
  --output_path         gs://...    preprocessed_combined output
  --num_partitions      int

Step 1 — Enumerate install dates per horizon
  For each horizon H (sorted desc by days):
    cutoff = train_end - (H_days - 7)
    assign install dates <= cutoff that aren't yet assigned to a deeper horizon
  Build list of gs:// paths: {ce_data_path}/{horizon}/install_date={date}/

Step 2 — Read CE data
  spark.read.option("mergeSchema", "true").parquet(*ce_paths)
  Note: partition key is install_date= (snake_case), not installDate=

Step 3 — Label
  cum_has_event_d7 is INT (0/1/null), NOT bool — do not use truthiness directly.
  label = WHEN cum_has_event_d7 = 1 THEN 1 ELSE 0
  (null → 0, meaning "no MMP event tracking configured" → treated as negative)

Step 4 — Quality filter
  eligible games: targetGameId with ≥50 installs where cum_has_event_d7 = 1

Step 5 — Bucket
  (same pattern: hash of auctionId / valuationId / gamer_id — verify available column in CE schema)

Step 6 — PSN label
  6a. Parse sdk_event_name_first_seen_arr → filter to ≤7d from installTimestamp
      → sdk_event_name_array (reuse column name)
  6b. BQ query: keep app_event_conversion_type = 'LEVEL_COMPLETE' (CUSTOM not yet available — see TODO #1)
  6c. Stages 2-5 identical to LC: aggregate targets, join, create labels array,
      probabilistic sampling, filter pre-first-positive

Step 7 — All other feature extraction unchanged
  (gamer counters, session counters, sparse categorical, hw_stats, timestamps,
   privacy/identity signals, etc.)

Step 8 — Add is_attributed passthrough
  df = df.withColumn("is_attributed", F.coalesce(F.col("is_attributed").cast("int"), F.lit(0)))

Step 9 — Output column selection
  Replace old app_event columns (app_event_w1, cum_app_event_count_d7, etc.)
  with CE equivalents: cum_has_event_d7, cum_event_count_d7, has_event_d7, etc.
```

---

## 11. LC → CE Column Mapping

**Status legend:**
- ✅ **Confirmed** — field name/type verified from agent-docs-hub schema analysis
- ⚠️ **Inferred** — reasonable assumption based on naming conventions; must verify via `printSchema()` before coding
- ❌ **Dropped** — LC column has no CE equivalent; remove from output schema
- ✨ **New** — CE-only column; no LC counterpart

**CE schema confirmed from:**
- `mmp_post_install_optimization_training_v2_analysis.md` (BQ table analysis)
- `sdk_event_name_first_seen_arr_analysis.md` (struct fields)
- `label_quality.md` (`cum_has_event_d7` type, `install_time`, `partition_date`, `is_attributed`)

**To inspect full CE parquet schema:**
```python
spark.read.parquet("gs://data-ads-app-prd/roas/.../primary_conversion_enriched_profiles_v2/d7/").limit(1).printSchema()
```

---

### 11.1 Partition / Date

| LC output col | LC source | CE output col | CE source | Status | Notes |
|---|---|---|---|---|---|
| `install_date` | derived from `installTimestamp` | `install_date` | partition key `install_date=YYYY-MM-DD` (snake_case) | ✅ | Key naming change: LC uses `installDate=` (camelCase), CE uses `install_date=` (snake_case) |

---

### 11.2 Labels

| LC output col | LC source | CE output col | CE source | Status | Notes |
|---|---|---|---|---|---|
| `label` | `app_event_w1 > 0 → 1, else 0` (null → 0) | `label` | `cum_has_event_d7 == 1 → 1, else 0` (null → 0) | ✅ | Source column changes entirely; derivation logic is same pattern |
| `prob_sdk_event_name` | sampled `{game_id}_{event_name}` token | `prob_sdk_event_name` | same — BQ campaigns join, unchanged | ✅ | PSN Stages 2–5 are identical; only Stage 1 event source changes |
| `prob_sdk_event_name_label` | 0.0/1.0 per sampled (install × event) | `prob_sdk_event_name_label` | same derivation | ✅ | |

---

### 11.3 Train/Val Split

| LC output col | LC source | CE output col | CE source | Status | Notes |
|---|---|---|---|---|---|
| `bucket` | `abs(hash(auctionId)) % 100 / 100.0` | `bucket` | same pattern — hash key TBD | ⚠️ | LC checks `mediation_auction_id`, `auctionId`, `gamer_id` in order. CE may use a different column name. Verify via `printSchema()`. |

---

### 11.4 Game Quality Filter (not an output column — determines row inclusion)

| LC filter | LC column | CE filter | CE column | Status |
|---|---|---|---|---|
| `cum_app_event_count_d7 > 0` → eligible game | `cum_app_event_count_d7` (Long) | `cum_has_event_d7 == 1` → eligible game | `cum_has_event_d7` (INT 0/1/null) | ✅ |

---

### 11.5 Sparse Categorical Features

These come from the install/auction log and are expected to carry over, but CE may use snake_case source names throughout (no nested `campaignInfo.*` struct). **All marked ⚠️ until `printSchema()` confirms.**

| LC output col | LC source field | CE output col | CE source field (expected) | Status |
|---|---|---|---|---|
| `geolocation_country` | `country` | `geolocation_country` | `country` or `geolocation_country` | ⚠️ |
| `platform` | `platform` | `platform` | `platform` | ⚠️ |
| `gamer_id_scope` | `gamerIdScope` | `gamer_id_scope` | `gamer_id_scope` (snake_case in CE?) | ⚠️ |
| `device_connection_type` | `connectionType` | `device_connection_type` | `connection_type` or `device_connection_type` | ⚠️ |
| `device_type` | `deviceType` | `device_type` | `device_type` | ⚠️ |
| `device_orientation` | `deviceOrientation` | `device_orientation` | `device_orientation` | ⚠️ |
| `audience_id` | `campaignInfo.audienceId` | `audience_id` | `audience_id` (flat, no nested struct?) | ⚠️ |
| `campaign_id` | `campaignInfo.audienceId` | `campaign_id` | TBD | ⚠️ |
| `publisher_developer_id` | `developerId` | `publisher_developer_id` | `publisher_developer_id` or `developer_id` | ⚠️ |
| `publisher_game_id` | `sourceGameId` | `publisher_game_id` | `publisher_game_id` or `source_game_id` | ⚠️ |
| `publisher_store_id` | `sourceStoreId` | `publisher_store_id` | `publisher_store_id` or `source_store_id` | ⚠️ |
| `target_game_id` | `targetGameId` (cast to string) | `target_game_id` | `target_game_id` | ⚠️ Critical — used as join key in PSN pipeline |
| `target_store_id` | `targetStoreId` | `target_store_id` | `target_store_id` | ⚠️ |
| `target_developer_id` | `campaignDeveloperId` | `target_developer_id` | `target_developer_id` or `campaign_developer_id` | ⚠️ |
| `model_name` | `modelName` | `model_name` | `model_name` | ⚠️ |
| `counters_source` | derived from `gamer_profile_meta`, `installed_store_ids_channel` | `counters_source` | same derivation if source cols exist | ⚠️ Source cols (`gamer_profile_meta`, `installed_store_ids_channel`) may not exist in CE |
| `traffic_type` | derived from `gamerIdScope` (`idfa`→`bhv`, `idfi`→`ctx`) | `traffic_type` | same derivation from `gamer_id_scope` | ⚠️ |

---

### 11.6 Dense Gamer-Level Engagement Counters (AGC features)

Source in LC: `gamerCounters.total.*` nested struct. CE may flatten these or keep the struct — **verify with `printSchema()`**.

| LC output col | LC source path | CE output col | CE source (expected) | Status |
|---|---|---|---|---|
| `gamer_start_count` | `gamerCounters.total.startCount` | `gamer_start_count` | `gamer_counters.total.start_count` or flat `gamer_start_count` | ⚠️ |
| `gamer_start_count_in_last_24_hours` | `gamerCounters.total.startCount1d` | `gamer_start_count_in_last_24_hours` | same or `gamer_counters.total.start_count_1d` | ⚠️ |
| `gamer_start_count_in_last_7_days` | `gamerCounters.total.startCount7d` | `gamer_start_count_in_last_7_days` | same or struct | ⚠️ |
| `gamer_view_count` | `gamerCounters.total.viewCount` | `gamer_view_count` | same or struct | ⚠️ |
| `gamer_click_count` | `gamerCounters.total.clickCount` | `gamer_click_count` | same or struct | ⚠️ |
| `gamer_install_count` | `gamerCounters.total.installCount` | `gamer_install_count` | same or struct | ⚠️ |

---

### 11.7 Dense Target-Game Engagement Counters

Source in LC: `gamerCounters.targetGame.*` nested struct.

| LC output col | LC source path | CE output col | CE source (expected) | Status |
|---|---|---|---|---|
| `target_game_start_count` | `gamerCounters.targetGame.startCount` | `target_game_start_count` | flat or struct | ⚠️ |
| `target_game_start_count_in_last_24_hours` | `gamerCounters.targetGame.startCount1d` | same | same or struct | ⚠️ |
| `target_game_start_count_in_last_7_days` | `gamerCounters.targetGame.startCount7d` | same | same or struct | ⚠️ |
| `target_game_view_count` | `gamerCounters.targetGame.viewCount` | same | same or struct | ⚠️ |
| `target_game_view_count_in_last_24_hours` | `gamerCounters.targetGame.viewCount1d` | same | same or struct | ⚠️ |
| `target_game_view_count_in_last_7_days` | `gamerCounters.targetGame.viewCount7d` | same | same or struct | ⚠️ |
| `target_game_click_count_in_last_24_hours` | `gamerCounters.targetGame.clickCount1d` | same | same or struct | ⚠️ |
| `target_game_click_count` | `gamerCounters.targetGame.clickCount` | same | same or struct | ⚠️ |
| `target_game_click_count_in_last_7_days` | `gamerCounters.targetGame.clickCount7d` | same | same or struct | ⚠️ |

---

### 11.8 Dense Session Counters

Source in LC: `gamerSessions.*` nested struct. May or may not exist in CE data for unattributed installs.

| LC output col | LC source | CE output col | CE source | Status |
|---|---|---|---|---|
| `gamer_session_counters_adrequests` | `gamerSessions.adRequests` | same | TBD | ⚠️ May not exist for unattributed; default to 1 if absent |
| `gamer_session_counters_start_count` | `gamerSessions.starts` | same | TBD | ⚠️ |
| `gamer_session_counters_view_count` | `gamerSessions.views` | same | TBD | ⚠️ |
| `gamer_session_counters_has_tgtg_started` | UDF over `gamerSessions.startsPerTarget` | same | TBD | ⚠️ |
| `gamer_session_counters_has_tgtg_viewed` | UDF over `gamerSessions.viewsPerTarget` | same | TBD | ⚠️ |
| `gamer_session_counters_performance_starts_count` | UDF over `startsPerTarget` (excl. brand IDs) | same | TBD | ⚠️ |
| `gamer_session_counters_performance_views_count` | UDF over `viewsPerTarget` (excl. brand IDs) | same | TBD | ⚠️ |
| `gamer_session_counters_brand_starts_count` | derived: total starts − perf starts | same | TBD | ⚠️ |
| `gamer_session_counters_brand_views_count` | derived: total views − perf views | same | TBD | ⚠️ |

---

### 11.9 Hardware Stats (Pre-Joined from GCS JSON)

Computed at datagen time from `hardware_stats.json` keyed by `device_type`. Unchanged in CE.

| LC output col | Source | CE output col | Status |
|---|---|---|---|
| `hardware_stats_cpu_count` | hw_stats.json lookup, clipped to ±16 | `hardware_stats_cpu_count` | ✅ Identical logic |
| `hardware_stats_ram` | hw_stats.json lookup, clipped to ±16384 | `hardware_stats_ram` | ✅ |
| `hardware_stats_dpi` | hw_stats.json lookup, clipped to ±640 | `hardware_stats_dpi` | ✅ |
| `hardware_stats_cpu` | hw_stats.json lookup | `hardware_stats_cpu` | ✅ |
| `hardware_stats_gpu` | hw_stats.json lookup | `hardware_stats_gpu` | ✅ |
| `hardware_stats_res` | hw_stats.json lookup | `hardware_stats_res` | ✅ |

---

### 11.10 App Event Passthrough Columns — BIGGEST SCHEMA CHANGE

This is the most disruptive part of the migration. LC has 17 LC-specific event count columns; CE replaces them with a completely different set.

| LC output col | LC description | CE output col | CE description | Status |
|---|---|---|---|---|
| `app_event_w1` | Cumulative LC count D0–D7 (null = no event); raw label source | ❌ dropped | → replaced by `cum_has_event_d7` as label source | ❌ |
| `app_event_d0` | LC events on install day | ❌ dropped | No per-day flag equivalent in CE | ❌ |
| `app_event_d1` | LC events D0–D1 | ❌ dropped | — | ❌ |
| `app_event_d3` | LC events D0–D3 | ❌ dropped | — | ❌ |
| `app_event_d7` | LC events D0–D7 | ❌ dropped | — | ❌ |
| `app_event_w2` | LC events D7–D14 | ❌ dropped | — | ❌ |
| `app_event_w3` | LC events D14–D21 | ❌ dropped | — | ❌ |
| `app_event_w4` | LC events D21–D28 | ❌ dropped | — | ❌ |
| `app_event_count_w1` | Per-week LC event count, week 1 | ❌ dropped | — | ❌ |
| `app_event_count_w2` | Per-week LC event count, week 2 | ❌ dropped | — | ❌ |
| `app_event_count_w3` | Per-week LC event count, week 3 | ❌ dropped | — | ❌ |
| `app_event_count_w4` | Per-week LC event count, week 4 | ❌ dropped | — | ❌ |
| `cum_app_event_count_d0` | Cumulative LC count by D0 | `cum_event_count_d1` | Cumulative CE event count by D1 (closest analog) | ⚠️ Different horizon; verify CE has `cum_event_count_d1` |
| `cum_app_event_count_d1` | Cumulative LC count by D1 | `cum_event_count_d1` | Cumulative CE count by D1 | ⚠️ |
| `cum_app_event_count_d3` | Cumulative LC count by D3 | `cum_event_count_d3` | Cumulative CE count by D3 | ⚠️ |
| `cum_app_event_count_d7` | Cumulative LC count by D7 (quality filter col) | `cum_event_count_d7` | Cumulative CE count by D7 | ⚠️ Name confirmed from mmp_analysis.md avg stats; verify exact column name |
| `cum_app_event_count_d14` | Cumulative LC count by D14 | `cum_event_count_d14` | Cumulative CE count by D14 | ⚠️ |

**New CE event label columns (no LC equivalent):**

| ✨ CE column | CE description | Status |
|---|---|---|
| `cum_has_event_d7` | Binary INT (0/1/null): any CE event in D0–D7. Primary label source. ~17% fill rate. | ✅ |
| `cum_has_event_d1` | Binary INT: any CE event by D1 | ✅ (confirmed from mmp_analysis.md) |
| `cum_has_event_d3` | Binary INT: any CE event by D3 | ✅ |
| `cum_has_event_d14` | Binary INT: any CE event by D14 | ✅ |
| `cum_has_event_d28` | Binary INT: any CE event by D28 | ✅ |
| `cum_has_lc_event_d7` | Binary INT: any LC event in D0–D7. Future multi-task use. | ✅ |
| `cum_has_lc_event_d14` | Binary INT: any LC event by D14 | ✅ |
| `cum_has_lc_event_d28` | Binary INT: any LC event by D28 | ✅ |

---

### 11.11 SDK Event Name Columns

| LC output col | LC source | CE output col | CE source | Status | Notes |
|---|---|---|---|---|---|
| `sdk_event_name_array` | `sdk_event_name_array` — pre-built `Array<String>` in LC parquet | `sdk_event_name_array` | **derived** via UDF from `sdk_event_name_first_seen_arr` filtered to ≤7d | ⚠️ Same output column name; completely different source |
| `sdk_event_name` | split from sampled `prob_sdk_event_name` token | `sdk_event_name` | same derivation — unchanged | ✅ |
| `tgtg_sdk_set` | literal `'placeholder'` | `tgtg_sdk_set` | literal `'placeholder'` | ✅ |
| `eventId` | `sdkEventId` (camelCase) | `eventId` | TBD — CE may use `sdk_event_id` (snake_case) | ⚠️ Verify column name |

**New CE array columns (raw source; not in output schema — used in UDF only):**

| ✨ CE source col | Description | Status |
|---|---|---|
| `sdk_event_name_first_seen_arr` | `Array<Struct<sdk_event_name: STRING, first_seen_at: TIMESTAMP>>` — all CE events | ✅ Confirmed |
| `sdk_event_name_first_seen_arr_lc` | Same struct — LC-only subset. Available for future multi-task labels. | ✅ Confirmed |

---

### 11.12 Timestamps and Metadata

**Critical change**: LC stores timestamps as unix-second `Long` (string→`unix_timestamp()` conversion). CE stores `install_time` as an actual `TIMESTAMP` column. The PSN UDF and `gamer_creation_delay` derivation must be updated accordingly.

| LC output col | LC source | CE output col | CE source | Status | Notes |
|---|---|---|---|---|---|
| `installTimestamp` | `installTimestamp` string → `unix_timestamp()` as Long | `install_time` | `install_time` TIMESTAMP (confirmed from label_quality.md) | ✅ | Name changes AND type changes. PSN UDF must use datetime arithmetic, not int subtraction |
| `ad_request_timestamp` | `adRequestTimestamp` string → `unix_timestamp()` as Long | `ad_request_timestamp` | TBD (may be pre-converted in CE) | ⚠️ |
| `gamer_creation_timestamp` | `gamerCreationTimestamp` string → `unix_timestamp()` as Long | `gamer_creation_timestamp` | TBD | ⚠️ |
| `gamer_creation_delay` | derived: `min(max(ad_req_ts − gamer_creation_ts, 0), 150_000_000)` | `gamer_creation_delay` | same derivation (after resolving timestamp types) | ⚠️ |
| `valuation_id` | `valuationId` cast to string | `valuation_id` | TBD (`valuation_id` or `valuationId` in CE?) | ⚠️ Candidate for bucket hash key |
| — | — | `partition_date` | CE-specific partition column | ✅ CE-only; not written to output parquet |

---

### 11.13 Privacy / Identity Signals

| LC output col | LC source | CE output col | CE source | Status |
|---|---|---|---|---|
| `publisher_is_coppa_targeted` | derived from `coppa` boolean | `publisher_is_coppa_targeted` | TBD (`coppa` field in CE?) | ⚠️ |
| `gamer_has_fingerprinted_identity` | derived from `fingerprinted` boolean | `gamer_has_fingerprinted_identity` | TBD | ⚠️ |
| `gamer_has_opted_out` | derived from `gamerIdScope`, `limited` | `gamer_has_opted_out` | TBD | ⚠️ |
| `gamer_limited_tracking` | derived from `limited`, `gamerIdScope` | `gamer_limited_tracking` | TBD | ⚠️ |
| `limited` | alias = `gamer_limited_tracking` | `limited` | same alias | ⚠️ |
| `coppa` | alias = `publisher_is_coppa_targeted` | `coppa` | same alias | ⚠️ |
| `fingerprinted` | alias = `gamer_has_fingerprinted_identity` | `fingerprinted` | same alias | ⚠️ |
| `opt_out_enabled` | alias = `gamer_has_opted_out` | `opt_out_enabled` | same alias | ⚠️ |

---

### 11.14 New CE-Only Output Columns

| ✨ CE output col | CE source | Description | Notes |
|---|---|---|---|
| `is_attributed` | `is_attributed` BOOLEAN in CE parquet | Attribution flag (True = Unity campaign attributed) | Cast to INT (0/1) for dense feature use. ~5.4% of rows are attributed. |

---

### 11.15 Summary: Change Scope by Category

| Category | LC cols | CE cols | Change type |
|---|---|---|---|
| Partition / date | `install_date` | `install_date` | Partition key format changes (`installDate=` → `install_date=`) |
| General label | `app_event_w1` | `cum_has_event_d7` | Column rename + different type (Long count vs INT flag) |
| PSN label | `sdk_event_name_array` (pre-built) | derived from `sdk_event_name_first_seen_arr` | UDF needed + TIMESTAMP arithmetic (not int subtraction) |
| Sparse categoricals | 17 cols | 17 cols | Same output names; source field naming may change (camel→snake) |
| Dense gamer counters | 15 cols | 15 cols | Same output names; nested struct naming may change |
| Dense session counters | 9 cols | 9 cols | Same output names; struct may not exist for unattributed |
| Hardware stats | 6 cols | 6 cols | ✅ Unchanged (pre-joined at datagen time) |
| App event passthroughs | **17 cols** | **5+ cols** | **Biggest structural break** — 12 LC-specific cols dropped, CE substitutes different column set |
| Timestamps | `installTimestamp` (Long) | `install_time` (TIMESTAMP) | Type change — all timestamp arithmetic must be updated |
| Privacy / identity | 8 cols | 8 cols | Same outputs; source col names TBD |
| New CE-only | — | `is_attributed` | New feature; add to output schema |
| Dropped LC-only | `was_conversion_attributed` | — | Not in CE schema (replaced by `is_attributed`) |

---

## 12. Implementation Order

1. Fix `config.json` — all `v11_cpe_lc_v2` → `v11_cpe_ce_v1` references
2. Inspect CE parquet schema (answer open questions above)
3. Implement `unified_cpe_ce_datagen.py` with horizon path logic + new label + new PSN
4. Update `workflow.py`: correct paths, `_get_latest_ce_install_date`, schedule name, Spark args, refresh_calibration import
5. Smoke-test datagen on 3-day window before full 88-day run
6. Update `features.py` if adding `is_attributed` as model feature

---

## 13. Label Semantics Comparison

| | LC model (`v11_cpe_lc_v2`) | CE model (`v11_cpe_ce_v1`) |
|--|---------------------------|---------------------------|
| What `label=1` means | User completed a level within 7d | User fired **any** custom SDK event within 7d (including LC) |
| Positive rate | Lower (LC is a specific event type) | Higher (any CE qualifies) |
| PSN label scope | LC campaigns only | CUSTOM campaigns (broader set) |
| Event matching | Exact SDK event name match or wildcard '*' | Same, but events sourced from `sdk_event_name_first_seen_arr` filtered to 7d |
| Model use case | Level Complete campaign bidding | Custom Event campaign bidding (superset of LC) |

The CE model is a **strict superset** of the LC model in terms of campaign coverage. Games running both LC and CE campaigns will have their CE campaigns served by this model. LC-specific training signal is preserved via `sdk_event_name_first_seen_arr_lc` for potential future multi-task extensions.

---

## 14. TODO / Future Work

| # | Item | Notes |
|---|------|-------|
| 1 | **Add CUSTOM to campaign type filter** | `CUSTOM` does not yet exist as a value in `app_event_conversion_type` in `campaigns_v3`. For now the BQ campaign query keeps `WHERE app_event_conversion_type = 'LEVEL_COMPLETE'`. Once `CUSTOM` campaigns are available, extend to `WHERE app_event_conversion_type IN ('LEVEL_COMPLETE', 'CUSTOM')`. |
