# SDK Event Name Label Migration: `unified_cpe.v1_lc`

## Background

The pinpointer `SDKEventNamePreprocessor` enriches each install row with two columns that
let the model predict per-campaign-event conversion probabilities, not just "any level
complete". This document describes how that logic was migrated to the UL framework.

---

## Final Architecture

| Column | Type | Where | Description |
|---|---|---|---|
| `prob_sdk_event_name` | `str` | parquet, feature | Bare event name (e.g. `"onlinetime_60m"`, `"*"`). Game-id prefix stripped by datagen. Feature transformer reconstructs `{target_game_id}_{event_name}` at runtime. |
| `prob_sdk_event_name_label` | `float` | parquet, label | `1.0` if user fired the targeted SDK event AND `app_event_w1 > 0`, else `0.0`. |

**Row expansion**: each install becomes N rows (one per game-event target). Most games
map to 1 row (`"*"` wildcard); games with specific custom event campaigns get ≥1 rows.

**Multi-task**: the model has two BCE task heads — `level_complete` (label `label`)
and `prob_sdk_event_name_label` (label `prob_sdk_event_name_label`). Both share the
same shared-bottom MLP and sparse embeddings.

---

## Source Logic (Pinpointer → UL Mapping)

### Stage 1 — BigQuery Campaign Lookup

**Tables queried:**
- `unity-ads-bi-prd.dimension_data.campaign_audiences` — maps `game_id → audience_id`
- `unity-ads-bi-prd.dimension_data.campaign_pricing` — maps `audience_id → sdk_event_names`
  filtered on `app_event_conversion_type = 'level_complete'`

Returns one row per `(target_game_id, audience_id)` with `sdk_event_name_set` (array).

### Stage 2 — Aggregate Targeted Events per Game

Per-campaign rule: if `size(sdk_event_name_set) > 1` OR `size == 0` → `"*"` (wildcard).
Otherwise use the single event string.

Then `groupBy(target_game_id)` + `collect_set(sdk_event_targeted)` collapses all
campaigns for a game into one row. A game with two specific campaigns (e.g. `lvl5` and
`lvl10`) ends up with `sdk_event_targeted = ["lvl5", "lvl10"]`.

### Stage 3 — Join + Label/Feature Column Creation

Left-outer join on `target_game_id`. Games with no active LC campaigns → `["*"]`.

`prob_sdk_event_name_labels[i]`:
```sql
IF (array_contains(sdk_event_name_array, sdk_event) OR sdk_event='*' OR sdk_event='')
   AND label = 1
THEN 1.0 ELSE 0.0
```

`prob_sdk_event_name_array[i]` = `concat(target_game_id, '_', sdk_event_targeted[i])`

### Stage 4 — `remove_game_id_from_tokens`

Strip the `{game_id}_` prefix via `regexp_extract(element, '_(.*)', 1)`.

Output: `prob_sdk_event_name_array = ["onlinetime_60m", "daily_quest"]`

At inference, `oecpm_features.prob_sdk_event_name` reconstructs `{target_game_id}_{event_name}` before hashing to the embedding table.

### Stage 5 — `filter_min_dates_by_game_and_event` (SKIPPED)

**TODO**: Re-enable after the first end-to-end test passes.

This filter removes training rows that predate the first positive conversion for each
`(target_game_id, event_name)` pair, preventing the model from seeing data before a
campaign went live. Uses `ad_request_timestamp` (unix seconds) for the date comparison.

Cold-start reason for skipping: if no positives exist yet for a new event, the filter
would remove all rows for that event.

### Stage 6 — Row Expansion (UL-specific)

Explode `(prob_sdk_event_name_array, prob_sdk_event_name_labels)` into one row per
game-event target. Produces scalar `prob_sdk_event_name` and `prob_sdk_event_name_label`.

`bucket` is preserved so all expanded rows from the same install land in the same
train/val split (no leakage).

---

## Files Changed

### `unified_cpe_datagen.py`
- Added BQ query `_BQ_CAMPAIGN_QUERY` (Stages 1–2).
- Added campaign join, `prob_sdk_event_name_labels`/`prob_sdk_event_name_array` columns (Stage 3).
- Added `remove_game_id_from_tokens` regex (Stage 4).
- Commented out `filter_min_dates_by_game_and_event` with TODO (Stage 5).
- Added row expansion via `arrays_zip` + `explode` (Stage 6).
- Spark property `spark.datasource.bigquery.project` added in `workflow.py`.

### `oecpm_features.py`
- Added `prob_sdk_event_name` transformer: reads bare event name, reconstructs
  `{target_game_id}_{event_name}`, hashes to sparse index.

### `label.py`
- Added `prob_sdk_event_name_label` transformer: returns scalar float label.

### `v1_lc/features.py`
- Added `sdk_event_features` FeatureSet with `prob_sdk_event_name` (hash_size=1M, list_len=1).
- Added `prob_sdk_event_name_label` to the `labels` FeatureSet.
- Added `sdk_event_features` to `model_features.sparse_features`.

### `v1_lc/config.json`
- `shared_bottom_mlp[0]`: 216 → 224 (19 → 20 sparse embs × compress_dim 8 + 64).
- Added `prob_sdk_event_name_label` task (BCE, loss_weight=1.0, same MLP shape as `level_complete`).

### `v1_lc/workflow.py`
- Added `spark.datasource.bigquery.project: unity-ads-bi-prd` to `spark_properties`.

---

## Dimension Accounting

```
num_embs = 17 (individual_sparse, repeat=1)
         + 1  (sdk_event_features)
         + 2  (dense_embedding_dim 64 // sparse_embedding_dim 32)
         = 20

shared_bottom_mlp[0] = 20 × dot_product_compress_dim (8) + dense_tower_mlp[-1] (64)
                     = 160 + 64 = 224
```

---

## Remaining TODOs

| # | Item |
|---|---|
| 1 | Re-enable `filter_min_dates_by_game_and_event` once initial test passes (use `ad_request_timestamp`). |
| 2 | Validate hash_size=1M for `prob_sdk_event_name` — run `SELECT COUNT(DISTINCT concat(target_game_id, '_', event)) FROM ...` on the first datagen output. |
| 3 | Tune `num_partitions` after row expansion — empirically measure final row count and adjust (current formula: `train_duration × 80`; may need `× 150+` if average events-per-game > 1.5). |
| 4 | Confirm `sdk_event_names` column name in `campaign_pricing` BQ table matches the query alias `sdk_event_name_set`. |
