# v11_cpe_ce_v1 Datagen Debugging Report

**Date**: 2026-08-19
**Script**: `src/unity_learner/data/spark/user_value/unified_cpe_ce_datagen.py`
**Output**: `gs://unity-ads-dd-ds-prd-incremental-training-data/user_value/unified_user_value.v11_cpe_ce_v1/preprocessed_combined/date=2026-08-09`

---

## Summary

The `run_datagen` step for `unified_user_value.v11_cpe_ce_v1` failed on its first run due to a cascade of schema mismatches between the CE parquet data (`primary_conversion_enriched_profiles_v2`) and the assumptions baked into the datagen script. Six distinct bugs were identified and fixed across five iterations. The job ultimately succeeded, writing **400,537,434 rows** across 400 files (~19.4 GiB).

---

## Bug 1 — GCS SSL Handshake Failure (`mergeSchema=true`)

**Error**
```
javax.net.ssl.SSLHandshakeException: Remote host terminated the handshake
java.io.EOFException: SSL peer shut down incorrectly
```

**Root cause**
`spark.read.option("mergeSchema", "true").parquet(*ce_paths)` triggers `readParquetFootersInParallel`, which opens hundreds of concurrent GCS SSL connections simultaneously (10 dates × 4 horizons × many files). GCS terminates the connections under this load.

**Fix**
Removed `mergeSchema=true`. CE data from the same upstream pipeline has a consistent schema across all horizon/date partitions, so schema merging was unnecessary.

---

## Bug 2 — `install_date` Column Not Found

**Error**
```
RuntimeError: install_date column not found in CE parquet.
```

**Root cause**
When passing explicit partition paths like `spark.read.parquet(path1, path2, ...)`, Spark does not automatically infer partition columns from directory names (`install_date=YYYY-MM-DD`) without a `basePath` hint.

**Fix**
Read per-horizon with `basePath` set to the horizon-level root, then union:
```python
for h in requested_horizons:
    h_paths = [p for p in ce_paths if f"/{h}/" in p]
    h_base = f"{args.ce_data_path.rstrip('/')}/{h}"
    _horizon_dfs.append(spark.read.option("basePath", h_base).parquet(*h_paths))
df = _horizon_dfs[0]
for _hdf in _horizon_dfs[1:]:
    df = df.unionByName(_hdf, allowMissingColumns=True)
```

Setting `basePath=ce_data_path` directly caused a "Conflicting directory structures" error because `d7` and `d14` are not in `key=value` format at the basePath level. Per-horizon basePaths resolve this.

---

## Bug 3 — CE Schema Uses `installTimestamp` (TIMESTAMP), Not `install_time`

**Error**
```
AnalysisException: column 'install_time' cannot be resolved.
Did you mean: install_date, installTimestamp, model_name, device_type, fillId
```

**Root cause**
The script was written assuming `install_time` (TIMESTAMP) as the CE column name. The actual CE schema has `installTimestamp: timestamp[ns]`.

Additionally, a second reference to `install_time` existed in the UDF call:
```python
_udf_events_within_7d(F.col("sdk_event_name_first_seen_arr"), F.col("install_time"))
```

**Fix**
Save the original `installTimestamp` TIMESTAMP to a temp column `_install_time_ts` before overwriting with unix-seconds Long, then reference the temp column in the UDF:
```python
df = df.withColumn("_install_time_ts", F.col("installTimestamp"))
_install_time_expr = F.col("_install_time_ts")
df = df.withColumn(
    "installTimestamp",
    F.coalesce(F.unix_timestamp(F.col("_install_time_ts")), F.lit(0)).cast("long"),
)
```

`_install_time_ts` is automatically dropped by `_select_output_cols` since it's not in `_OUTPUT_COLS`.

**Important**: `F.col("installTimestamp")` is a **lazy name reference**. After `withColumn` overwrites the column with a Long, any later reference to `F.col("installTimestamp")` resolves to the Long — not the original TIMESTAMP. This caused the UDF to receive an `int` instead of `datetime.datetime`, leading to:
```
TypeError: unsupported operand type(s) for -: 'datetime.datetime' and 'int'
```

---

## Bug 4 — `isAttributed` vs `is_attributed`

**Error**
```
AnalysisException: column 'is_attributed' cannot be resolved.
Did you mean: isAttributed, isReattributed, isContributed, attributionId, install_date
```

**Root cause**
CE data uses camelCase `isAttributed: bool`, not snake_case `is_attributed`.

**Fix**
```python
df = df.withColumn(
    "is_attributed",
    F.when(F.col("isAttributed").isNotNull() & F.col("isAttributed"), F.lit(1))
    .otherwise(F.lit(0))
    .cast("int"),
)
```

---

## Bug 5 — Gamer Counters Under Wrong Struct Path

**Error**
All 15 counter columns logged:
```
[WARN] Struct path 'gamerCounters.total.startCount' not found in schema, defaulting gamer_start_count=0
[WARN] Struct path 'gamerCounters.targetGame.startCount' not found in schema, ...
```

**Root cause**
The script assumed LC-style `gamerCounters.total.*` / `gamerCounters.targetGame.*` nested structs. Confirmed from the actual CE parquet schema: counters live under `agc_ad_request_based_features.total.*` and `agc_ad_request_based_features.targetGame.*`.

**Fix** — updated all 15 `add_counter_col` calls:
```python
# Before
df = add_counter_col(df, "gamer_start_count", "gamerCounters.total.startCount")
# After
df = add_counter_col(df, "gamer_start_count", "agc_ad_request_based_features.total.startCount")
```

---

## Additional Schema Fixes (from full parquet schema inspection)

The full CE parquet schema was read via `pyarrow` to eliminate remaining guesswork:

| Column in script | Assumed source | Actual CE source |
|---|---|---|
| `device_type` | `deviceType` (missing) | `normalized_device_type: string` |
| `device_orientation` | `deviceOrientation` (missing) | `normalized_device_orientation: string` |
| `eventId` | `sdk_event_id` / `sdkEventId` / `event_id` (all missing) | `eventId: string` (already top-level — was being overwritten with "null") |
| `ad_request_timestamp` | generic fallback | `adRequestTimestamp: timestamp[ns]` → `F.unix_timestamp()` |
| `gamer_creation_timestamp` | generic fallback | `gamerCreationTimestamp: timestamp[ns]` → `F.unix_timestamp()` |

**No `gamerSessions` struct** exists in CE data → all 9 session counter columns correctly default to 0.0.

---

## Confirmed CE Parquet Schema (relevant fields)

| Field | Type | Notes |
|---|---|---|
| `installTimestamp` | `timestamp[ns]` | Not Long; convert with `unix_timestamp()` |
| `isAttributed` | `bool` | camelCase |
| `agc_ad_request_based_features` | struct | Contains `.total.*` and `.targetGame.*` counter sub-structs |
| `adRequestTimestamp` | `timestamp[ns]` | camelCase |
| `gamerCreationTimestamp` | `timestamp[ns]` | camelCase |
| `gamerIdScope` | `string` | camelCase |
| `connectionType` | `string` | camelCase |
| `normalized_device_type` | `string` | snake_case with `normalized_` prefix |
| `normalized_device_orientation` | `string` | snake_case with `normalized_` prefix |
| `country` | `string` | Plain |
| `coppa` | `bool` | Plain |
| `limited` | `bool` | Plain |
| `sdk_event_name_first_seen_arr` | `list<struct<sdk_event_name: string, first_seen_at: timestamp[ns]>>` | CE event array |

---

## Output Validation

**Path**: `gs://unity-ads-dd-ds-prd-incremental-training-data/user_value/unified_user_value.v11_cpe_ce_v1/preprocessed_combined/date=2026-08-09`

| Metric | Value |
|---|---|
| Total files | 402 (400 data + 2 metadata) |
| Total size | ~19.4 GiB |
| Total rows | **400,537,434** |
| `label=1` rate | 16.0% |
| `label=0` rate | 84.0% |
| `bucket` range | [0.000, 0.990] |
| `prob_sdk_event_name` nulls | 0 |
| `install_date` unique values | 10 (`2026-07-31` → `2026-08-09`) |
| `installTimestamp` range | 1,785,456,001 – 1,786,319,996 (valid Aug 2026 unix seconds) |
| `gamer_start_count > 0` | 1.3% |
| `device_type != null` | 1.4% |

The low counter/device coverage is expected: CE data combines attributed (~1–5%) and unattributed installs, and unattributed installs lack AGC features by design.

---

## Data Volume Comparison: CE v1 vs LC v3

**LC baseline**: `unified_user_value.v11_cpe_lc_v3/preprocessed_combined/date=2026-08-09`
- 88 days, **attributed installs only**

**CE current**: `unified_user_value.v11_cpe_ce_v1/preprocessed_combined/date=2026-08-09`
- 10 days, **attributed + unattributed installs**

| | LC v3 | CE v1 |
|---|---|---|
| Training days | 88 | 10 |
| Population | Attributed only | Attributed + unattributed |
| Files | 3,520 | 400 |
| Total size | 6.83 GiB | 19.4 GiB |
| Total rows | ~46M | 400.5M |
| **Rows / day** | **~523K** | **~40M** |
| Per-day ratio | 1x | **~77x more** |

CE data is ~77x denser per day than LC, almost entirely driven by unattributed installs. Based on the output validation above (`gamer_start_count > 0` at 1.3%, `device_type != null` at 1.4%), attributed installs comprise roughly 1–2% of CE rows, consistent with the known CE data composition.

### Projection: full 88-day CE run

At 40M rows/day, a full 88-day CE window would produce approximately **3.5 billion rows** — roughly 75× the LC training dataset.

### Options

| Option | Rows (88d est.) | Tradeoff |
|---|---|---|
| Keep as-is (attr + unattr) | ~3.5B | Full CE population; very large training cost |
| Filter to attributed only | ~49M | Comparable to LC volume; loses unattributed signal |
| Subsample unattributed | configurable | Balance between coverage and cost |

**Decision needed**: whether CE campaigns serve unattributed users (justifying including them in training) or attributed users only (in which case filtering to `isAttributed = true` brings volume in line with LC).
