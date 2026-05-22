# UUPS Feature Addition Plan: v11_cpe_lc

**Date**: 2026-05-22
**Author**: yabo.ling
**Scope**: Add UUPS features available in the Legacy BHV model to `unified_user_value.v11_cpe_lc`

---

## 1. Background and Gap Analysis

### Legacy BHV UUPS Features (32 total)

`ads-audience-pinpointer/cpi-model/configs/prd/features_level_complete_bhv.yaml` contains three categories of UUPS signals:

#### IAP Purchase (24 features)
Three attribution groups (`attributed`, `unattributed`, `uasdk`) × two time windows (`d7`, `d30`) × four metrics:

| Metric | Legacy Feature Name | Type | Clip |
|--------|--------------------|----|------|
| IAP done flag | `uups_{group}_iap_done_{window}` | categorical (bool string) | - |
| Non-zero log avg value | `uups_{group}_iap_nonzero_log_avg_value_{window}` | scalar | 18.4 |
| Total IAP count | `uups_{group}_iap_total_count_{window}` | scalar | 1000 |
| Unique games with IAPs | `uups_{group}_unique_games_with_iaps_count_{window}` | scalar | 25 |

#### AdRev (8 features)
Two ad types (`oecpm_rewarded`, `oecpm_interstitial`) × two time windows (`d7`, `d30`) × two metrics:

| Metric | Legacy Feature Name | Type |
|--------|--------------------|----|
| Total exposure count | `uups_adrev_oecpm_{type}_total_count_{window}` | scalar |
| Total revenue sum | `uups_adrev_oecpm_{type}_total_sum_{window}` | scalar |

### Legacy CTX Model
No UUPS features — the CTX model (`features_level_complete_ctx.yaml`) does not contain any `uups_*` entries.

### Current UL Model (v11_cpe_lc)
No UUPS features. The `features.py` uses `dense_agc_features` (15 gamer/target-game engagement scalars) + `dense_lc_features` (1 scalar: `gamer_creation_delay`) = 16 dense inputs total.

---

## 2. Feature Mapping: Legacy → UL Format

The UL framework uses a **per-game sequential format** (top-N games sorted by `lastUpdated DESC`) rather than pre-aggregated user-level scalars. Each raw UUPS feature is an `array<float>` of length `list_len`.

The correspondence between legacy aggregate scalars and UL sequential arrays:

| Legacy Feature | UL Raw Column | Relationship |
|----------------|--------------|-------------|
| `uups_attributed_iap_total_count_d7` | `raw_uups_purchase_attributed_v3_count_d7` | `sum(array)` |
| `uups_attributed_iap_nonzero_log_avg_value_d7` | `raw_uups_purchase_attributed_v3_{sum,count}_d7` | `sum(sum_arr) / sum(count_arr)` (derived) |
| `uups_attributed_iap_done_d7` | `raw_uups_purchase_attributed_v3_count_d7` | `any(array > 0)` |
| `uups_attributed_unique_games_with_iaps_count_d7` | `raw_uups_purchase_attributed_v3_count_d7` | `count(array > 0)` |
| `uups_adrev_oecpm_rewarded_total_count_d7` | `raw_uups_adrev_oecpm_rewarded_v2_count_d7` | `sum(array)` |
| `uups_adrev_oecpm_rewarded_total_sum_d7` | `raw_uups_adrev_oecpm_rewarded_v2_sum_d7` | `sum(array) / 1e6` |
| _(same pattern for d30 and interstitial)_ | | |

**Recommendation**: Use the richer per-game sequential format (rather than re-implementing flat aggregates). Per-game sequences preserve which apps drove a user's IAP / adrev behavior, giving DLRM's dot-product attention mechanism game-level context that aggregates discard. Legacy flat scalars are a strict information subset of the UL sequential representation.

**Signal sources to include** (strict parity with legacy BHV; sources NOT in legacy BHV are excluded from Phase 1):

| UL Source Column Prefix | Legacy BHV Equivalent | Include in Phase 1 |
|------------------------|----------------------|-------------------|
| `raw_uups_purchase_attributed_v3_*` | `uups_attributed_iap_*` | Yes |
| `raw_uups_purchase_unattributed_v3_*` | `uups_unattributed_iap_*` | Yes |
| `raw_uups_purchase_uasdk_v3_*` | `uups_uasdk_iap_*` | Yes |
| `raw_uups_adrev_oecpm_rewarded_v2_*` | `uups_adrev_oecpm_rewarded_*` | Yes |
| `raw_uups_adrev_oecpm_interstitial_v2_*` | `uups_adrev_oecpm_interstitial_*` | Yes |
| `raw_uups_adrev_levelplay_v2_*` | _(none in legacy BHV)_ | Phase 2 (optional) |
| `raw_uups_adrev_s2s_attributed_v2_*` | _(none in legacy BHV)_ | Phase 2 (optional) |
| `raw_uups_adrev_s2s_unattributed_v2_*` | _(none in legacy BHV)_ | Phase 2 (optional) |

---

## 3. Implementation Plan

### Step 0: Prerequisite — Verify Source Data Schema

**Before any code changes**, confirm the `v2/level_complete/d7` parquet contains the UUPS struct columns.

```python
# Quick schema probe — run from a notebook or Spark shell
df = spark.read.parquet(
    "gs://unity-ads-dd-ds-prd-data-anon/app-events/data/"
    "ads.events.operativeecpm.installs.outcomes.v2/level_complete/d7/"
    "installDate=2026-05-01"
)
uups_cols = [f.name for f in df.schema if "uups" in f.name.lower()]
print(uups_cols)
# Expected: ["uups_purchase", "uups_adrev", ...]
# Each should be a StructType with bhv_profiles, advctx_profiles, thumbs_up_profiles sub-fields
```

**If the structs are absent**: The UUPS data was not embedded in the LC source at ETL time. Options:
- (a) Ask data-eng to add UUPS struct embedding to the `v2/level_complete/d7` ETL pipeline.
- (b) Do a Spark join at datagen time against a separate UUPS snapshot table.
- (c) Keep the legacy flat aggregates and add new scalar transformers (see Appendix A).

The rest of this plan assumes option (a) — the structs exist.

---

### Step 1: Datagen (`unified_cpe_datagen.py`)

**File**: `src/unity_learner/data/spark/user_value/unified_cpe_datagen.py`

The datagen already has a "Phase 2 note" at line 865 pointing to exactly this work. The `enrich_raw_uups_purchase_data` and `enrich_raw_uups_adrev_data` functions in `common/raw_uups_enrichment.py` are already written and tested by the UV datagen.

#### 1a. Import enrichment functions

```python
from unity_learner.data.spark.user_value.common.raw_uups_enrichment import (
    enrich_raw_uups_purchase_data,
    enrich_raw_uups_adrev_data,
)
```

#### 1b. Call enrichment after counter column extraction, before the final select

```python
# ---------------------------------------------------------------------------
# UUPS enrichment: extract per-game purchase and adrev arrays from UUPS structs.
# enrich_raw_uups_purchase_data adds raw_uups_purchase_{source}_* columns.
# enrich_raw_uups_adrev_data    adds raw_uups_adrev_{source}_* columns.
# Matches the Phase 2 note at line 865.
# ---------------------------------------------------------------------------
if _get_nested_field(df.schema, ["uups_purchase"]) is not None:
    df = enrich_raw_uups_purchase_data(df)
    print("UUPS purchase enrichment applied.")
else:
    print("[WARN] uups_purchase struct not found — UUPS purchase features will be zeros.")
    # Null-fill all expected raw_uups_purchase_* columns so _OUTPUT_COLS select succeeds.
    for col_name in _UUPS_PURCHASE_COLS:
        df = df.withColumn(col_name, F.array().cast("array<float>"))

if _get_nested_field(df.schema, ["uups_adrev"]) is not None:
    df = enrich_raw_uups_adrev_data(df)
    print("UUPS adrev enrichment applied.")
else:
    print("[WARN] uups_adrev struct not found — UUPS adrev features will be zeros.")
    for col_name in _UUPS_ADREV_COLS:
        df = df.withColumn(col_name, F.array().cast("array<float>"))
```

#### 1c. Define `_UUPS_PURCHASE_COLS` and `_UUPS_ADREV_COLS` constants

Add at the top of the file alongside `_OUTPUT_COLS`:

```python
# UUPS columns produced by enrich_raw_uups_purchase_data (Phase 1: attributed/unattributed/uasdk).
_UUPS_PURCHASE_COLS = [
    # Purchase attributed v3
    "raw_uups_purchase_attributed_v3_store_id",
    "raw_uups_purchase_attributed_v3_channel",
    "raw_uups_purchase_attributed_v3_last_updated",
    "raw_uups_purchase_attributed_v3_count_d7",
    "raw_uups_purchase_attributed_v3_count_d30",
    "raw_uups_purchase_attributed_v3_sum_d7",
    "raw_uups_purchase_attributed_v3_sum_d30",
    # Purchase unattributed v3
    "raw_uups_purchase_unattributed_v3_store_id",
    "raw_uups_purchase_unattributed_v3_channel",
    "raw_uups_purchase_unattributed_v3_last_updated",
    "raw_uups_purchase_unattributed_v3_count_d7",
    "raw_uups_purchase_unattributed_v3_count_d30",
    "raw_uups_purchase_unattributed_v3_sum_d7",
    "raw_uups_purchase_unattributed_v3_sum_d30",
    # Purchase UASDK v3
    "raw_uups_purchase_uasdk_v3_store_id",
    "raw_uups_purchase_uasdk_v3_channel",
    "raw_uups_purchase_uasdk_v3_last_updated",
    "raw_uups_purchase_uasdk_v3_count_d7",
    "raw_uups_purchase_uasdk_v3_count_d30",
    "raw_uups_purchase_uasdk_v3_sum_d7",
    "raw_uups_purchase_uasdk_v3_sum_d30",
]

# UUPS columns produced by enrich_raw_uups_adrev_data (Phase 1: oecpm_rewarded/interstitial only).
_UUPS_ADREV_COLS = [
    # AdRev OECPM rewarded v2
    "raw_uups_adrev_oecpm_rewarded_v2_store_id",
    "raw_uups_adrev_oecpm_rewarded_v2_channel",
    "raw_uups_adrev_oecpm_rewarded_v2_last_updated",
    "raw_uups_adrev_oecpm_rewarded_v2_count_d7",
    "raw_uups_adrev_oecpm_rewarded_v2_count_d30",
    "raw_uups_adrev_oecpm_rewarded_v2_sum_d7",
    "raw_uups_adrev_oecpm_rewarded_v2_sum_d30",
    # AdRev OECPM interstitial v2
    "raw_uups_adrev_oecpm_interstitial_v2_store_id",
    "raw_uups_adrev_oecpm_interstitial_v2_channel",
    "raw_uups_adrev_oecpm_interstitial_v2_last_updated",
    "raw_uups_adrev_oecpm_interstitial_v2_count_d7",
    "raw_uups_adrev_oecpm_interstitial_v2_count_d30",
    "raw_uups_adrev_oecpm_interstitial_v2_sum_d7",
    "raw_uups_adrev_oecpm_interstitial_v2_sum_d30",
]
```

#### 1d. Append to `_OUTPUT_COLS`

```python
# ---- UUPS purchase per-game arrays (Phase 1: attributed / unattributed / uasdk) ----
*_UUPS_PURCHASE_COLS,
# ---- UUPS adrev per-game arrays (Phase 1: oecpm_rewarded / oecpm_interstitial) ----
*_UUPS_ADREV_COLS,
```

#### 1e. Spark resource note

The UUPS enrichment flattens per-game struct arrays. For 88-day training windows with ~130M rows, expect:
- ~20% increase in executor memory pressure (array serialization overhead)
- Add `"spark.executor.memoryOverhead": "16g"` and `"spark.executor.memory": "45g"` (up from 38g/12g)
- Consider reducing `num_partitions` multiplier from 40 → 50 per day to keep partition size manageable

---

### Step 2: Preprocessor (Already Implemented — No New Code Required)

All necessary transformer functions already exist in:
- `src/unity_learner/data/preprocessor_v2/features/uups_features.py`
- `src/unity_learner/data/preprocessor_v2/user_value/uups_featureset.py`
- `src/unity_learner/data/preprocessor_v2/features/data_source_schema.py` (lines 905–960, all raw_uups_* columns registered)

The `data_source_schema.py` already declares types for all raw UUPS columns (e.g., `raw_uups_purchase_attributed_v3_count_d7: np.float32`), so schema validation will pass once the datagen writes these columns.

**No changes required to the preprocessor layer.**

---

### Step 3: Model Features (`features.py`)

**File**: `src/unity_learner/experiment_repo/unified_user_value/v11_cpe_lc/features.py`

Create a new `dense_uups_lc_features` featureset (a targeted subset of the full `static_shape_dense_uups_features`, limited to the 5 legacy BHV signal sources and only d7/d30 windows):

```python
import unity_learner.data.preprocessor_v2.features.uups_features as uups_features
from unity_learner.data.preprocessor_v2.feature_set import FeatureSet, FeatureSetType

# Targeted UUPS dense features for LC migration.
# Includes only the 5 signal sources present in the legacy level_complete_bhv.yaml:
#   - Purchase attributed/unattributed/uasdk (→ legacy uups_{group}_iap_*)
#   - AdRev OECPM rewarded/interstitial     (→ legacy uups_adrev_oecpm_*_total_*)
# Time windows d7 and d30 only (matching legacy; d180 excluded for Phase 1).
# list_len=5: top-5 most recently updated games; each feature contributes 5 dense scalars.
#
# Total new dense inputs: 5 sources × 4 metrics (count_d7, count_d30, sum_d7, sum_d30) × 5 = 100
# New dense_tower_mlp[0] = 16 (current) + 100 = 116
_LIST_LEN = 5
_CAP = 50.0

dense_uups_lc_features = FeatureSet(
    name="dense_uups_lc_features",
    type=FeatureSetType.ONLINE_AND_OFFLINE,
    features=[
        # Purchase attributed
        uups_features.raw_uups_purchase_attributed_v3_count_d7.set_dense_params(
            cap=_CAP, list_len=_LIST_LEN, in_model_transforms=["log1p"]
        ),
        uups_features.raw_uups_purchase_attributed_v3_count_d30.set_dense_params(
            cap=_CAP, list_len=_LIST_LEN, in_model_transforms=["log1p"]
        ),
        uups_features.raw_uups_purchase_attributed_v3_sum_d7.set_dense_params(
            cap=_CAP, list_len=_LIST_LEN, in_model_transforms=["log1p"]
        ),
        uups_features.raw_uups_purchase_attributed_v3_sum_d30.set_dense_params(
            cap=_CAP, list_len=_LIST_LEN, in_model_transforms=["log1p"]
        ),
        # Purchase unattributed
        uups_features.raw_uups_purchase_unattributed_v3_count_d7.set_dense_params(
            cap=_CAP, list_len=_LIST_LEN, in_model_transforms=["log1p"]
        ),
        uups_features.raw_uups_purchase_unattributed_v3_count_d30.set_dense_params(
            cap=_CAP, list_len=_LIST_LEN, in_model_transforms=["log1p"]
        ),
        uups_features.raw_uups_purchase_unattributed_v3_sum_d7.set_dense_params(
            cap=_CAP, list_len=_LIST_LEN, in_model_transforms=["log1p"]
        ),
        uups_features.raw_uups_purchase_unattributed_v3_sum_d30.set_dense_params(
            cap=_CAP, list_len=_LIST_LEN, in_model_transforms=["log1p"]
        ),
        # Purchase UASDK
        uups_features.raw_uups_purchase_uasdk_v3_count_d7.set_dense_params(
            cap=_CAP, list_len=_LIST_LEN, in_model_transforms=["log1p"]
        ),
        uups_features.raw_uups_purchase_uasdk_v3_count_d30.set_dense_params(
            cap=_CAP, list_len=_LIST_LEN, in_model_transforms=["log1p"]
        ),
        uups_features.raw_uups_purchase_uasdk_v3_sum_d7.set_dense_params(
            cap=_CAP, list_len=_LIST_LEN, in_model_transforms=["log1p"]
        ),
        uups_features.raw_uups_purchase_uasdk_v3_sum_d30.set_dense_params(
            cap=_CAP, list_len=_LIST_LEN, in_model_transforms=["log1p"]
        ),
        # AdRev OECPM rewarded
        uups_features.raw_uups_adrev_oecpm_rewarded_v2_count_d7.set_dense_params(
            cap=_CAP, list_len=_LIST_LEN, in_model_transforms=["log1p"]
        ),
        uups_features.raw_uups_adrev_oecpm_rewarded_v2_count_d30.set_dense_params(
            cap=_CAP, list_len=_LIST_LEN, in_model_transforms=["log1p"]
        ),
        uups_features.raw_uups_adrev_oecpm_rewarded_v2_sum_d7.set_dense_params(
            cap=_CAP, list_len=_LIST_LEN, in_model_transforms=["log1p"]
        ),
        uups_features.raw_uups_adrev_oecpm_rewarded_v2_sum_d30.set_dense_params(
            cap=_CAP, list_len=_LIST_LEN, in_model_transforms=["log1p"]
        ),
        # AdRev OECPM interstitial
        uups_features.raw_uups_adrev_oecpm_interstitial_v2_count_d7.set_dense_params(
            cap=_CAP, list_len=_LIST_LEN, in_model_transforms=["log1p"]
        ),
        uups_features.raw_uups_adrev_oecpm_interstitial_v2_count_d30.set_dense_params(
            cap=_CAP, list_len=_LIST_LEN, in_model_transforms=["log1p"]
        ),
        uups_features.raw_uups_adrev_oecpm_interstitial_v2_sum_d7.set_dense_params(
            cap=_CAP, list_len=_LIST_LEN, in_model_transforms=["log1p"]
        ),
        uups_features.raw_uups_adrev_oecpm_interstitial_v2_sum_d30.set_dense_params(
            cap=_CAP, list_len=_LIST_LEN, in_model_transforms=["log1p"]
        ),
    ],
)
```

Then add to `model_features`:

```python
model_features = ModelFeatures(
    combined_dense_features=[
        dense_lc_features,
        dense_agc_features,
        dense_uups_lc_features,    # <-- ADD
    ],
    sparse_features=[individual_sparse_features],
    offline_only_features=[offline_only_features],
    online_only_features=[cpe_online_only_features],
    labels=[labels],
)
```

**Phase 2 (optional)**: Also add sparse UUPS features (per-game store_id and channel) to `individual_sparse_features` using `agg_mode="mean"` so each contributes one embedding to the DLRM interaction matrix:

```python
# Phase 2: sparse UUPS store_id and channel per source (mean-pooled)
uups_features.raw_uups_purchase_attributed_v3_store_id.set_sparse_params(
    hash_size=110000, list_len=_LIST_LEN, agg_mode="mean", repeat=1
),
# ... etc for all 5 sources × {store_id, channel}
```

---

### Step 4: Model Config (`config.json`)

**File**: `src/unity_learner/experiment_repo/unified_user_value/v11_cpe_lc/config.json`

#### 4a. Dense tower input dimension

Adding 20 dense UUPS features × `list_len=5` = 100 new dense scalars:
```
New dense_tower_mlp[0] = 16 (current) + 100 = 116
```

```json
"dense_tower_mlp": [116, 128]
```

The tower output (128) is unchanged, so `shared_bottom_mlp[0]` = 448 stays the same.

#### 4b. `shared_bottom_mlp[0]` — only changes if sparse UUPS features are added (Phase 2)

If 10 new sparse UUPS features (5 sources × store_id + channel) are added with `agg_mode="mean"`:
```
num_embs = 18 (current) + 10 (new UUPS sparse) + 2 (dense bridge) = 30
shared_bottom_mlp[0] = 30 × 16 + 128 = 608
```

```json
"shared_bottom_mlp": [608, 512, 256]   // Phase 2 only
```

#### 4c. Dynamic hash size entries (if sparse UUPS added)

Add to `datagen_config.dynamic_hash_size_features` for any new sparse categorical columns whose vocabulary is built at mapping time. The UUPS `store_id` and `channel` columns are sequence arrays, so vocabulary is built from all elements.

---

### Step 5: Serving Integration

UUPS features are `FeatureSetType.ONLINE_AND_OFFLINE`, meaning the serving layer (Go / Triton) must populate them at inference time using the user's UUPS profile from the feature store.

#### 5a. OOC validation

Run an OOC check after deploying to staging. The new UUPS dense features will appear in the preprocessed batch. The OOC test should verify:
- All `raw_uups_purchase_*` and `raw_uups_adrev_*` columns are populated (non-zero for users with purchase/adrev history)
- Feature distributions match training data

```bash
ul-cli ooc_check --experiment unified_user_value.v11_cpe_lc
```

#### 5b. Go serving layer — feature mapping

The Go serving layer needs to read UUPS profile data and populate the new feature columns. Verify that the following keys are present in the Go feature mapping:
- `raw_uups_purchase_attributed_v3_count_d7` → populated from `uups_purchase.attributed_v3` profile
- `raw_uups_adrev_oecpm_rewarded_v2_count_d7` → populated from `uups_adrev.oecpm_rewarded_v2` profile

Check `ads-conversion-model-service/pkg/triton/mapping.go` for existing UUPS feature mappings from other models (e.g., `v8_mmp_v2a` uses the same UUPS featuresets). If already mapped, v11_cpe_lc will inherit them automatically via the shared preprocessor. If not yet mapped, coordinate with the serving team.

#### 5c. Triton model config

After running `ul-cli deploy`, verify the Triton input tensor shape reflects the new dense dimension. The input tensor for dense features changes from `[batch, 16]` to `[batch, 116]`. This is handled automatically by the deploy pipeline when `use_static_shape=true`.

#### 5d. Cold-start / missing UUPS data

Users without any UUPS data will have all arrays empty. The `sanitize_sequential_feature` transformer in `uups_features.py` already handles empty arrays by returning zero-padded vectors. No additional null handling is required.

---

## 4. Architecture Summary

### Before (v11_cpe_lc current)

```
Dense inputs: 16 (1 gamer_creation_delay + 15 dense_agc_features)
Sparse embs:  18 individual sparse features (repeat=1, agg_mode="mean")
Dense bridge: 64 // 32 = 2 additional embs from dense_embedding_dim/sparse_embedding_dim

dense_tower_mlp[0]:    16
shared_bottom_mlp[0]:  (18 + 2) × 16 + 128 = 448
```

### After Phase 1 (dense UUPS only)

```
Dense inputs: 116 (16 + 100 new UUPS dense scalars)
Sparse embs:  18 (unchanged)
Dense bridge: 2 (unchanged)

dense_tower_mlp[0]:    116   <-- CHANGE
shared_bottom_mlp[0]:  448   <-- unchanged
```

### After Phase 2 (dense + sparse UUPS)

```
Dense inputs: 116
Sparse embs:  18 + 10 UUPS sparse = 28
Dense bridge: 2

dense_tower_mlp[0]:    116   <-- CHANGE
shared_bottom_mlp[0]:  (28 + 2) × 16 + 128 = 608   <-- CHANGE
```

---

## 5. Recommended Experiment Version

Create a new experiment `v12_cpe_lc` rather than modifying `v11_cpe_lc` in-place. This ensures:
- `v11_cpe_lc` continues serving during development
- Clean AB test comparison: v11 (no UUPS) vs v12 (with UUPS)
- No risk of breaking the existing trained model artifact

```bash
ul-cli create_experiment --experiment unified_user_value.v12_cpe_lc
# Copy v11 config.json and features.py → v12, then apply changes above
```

---

## 6. Work Breakdown

| Step | Task | Owner | Blocker |
|------|------|-------|---------|
| 0 | Verify `uups_purchase` / `uups_adrev` structs in v2/level_complete/d7 | Data scientist | None |
| 0b | If structs absent: request data-eng to embed UUPS in LC ETL | Data eng | Step 0 |
| 1 | Create `v12_cpe_lc` experiment skeleton | Data scientist | None |
| 2 | Update `unified_cpe_datagen.py`: add UUPS enrichment calls + output cols | Data scientist | Step 0 |
| 3 | Update `features.py`: add `dense_uups_lc_features`, wire into `model_features` | Data scientist | None |
| 4 | Update `config.json`: `dense_tower_mlp[0]` 16 → 116 | Data scientist | Step 3 |
| 5 | Run full datagen for v12 experiment | Data scientist | Steps 2, 3 |
| 6 | Train v12 model; compare offline AUC/NE vs v11 baseline | Data scientist | Step 5 |
| 7 | Verify serving layer populates UUPS features; run OOC check | Serving team + data scientist | Step 6 |
| 8 | Deploy v12 to staging; run AB test vs v11 | Data scientist | Step 7 |

---

## Appendix A: Alternative — Legacy Scalar Parity (Flat Aggregates)

If the sequential per-game format is undesirable (e.g., to minimize serving changes), the 32 legacy scalar features can be re-implemented as flat aggregations. This requires:

1. New transformer functions in `uups_features.py` that sum/count array outputs:
   ```python
   @transformer(inputs=[raw_features], feature_type=FeatureType.Context, output_type=OutputType.DENSE)
   def uups_attributed_iap_total_count_d7(raw_features, **kwargs):
       arr = raw_features.get("raw_uups_purchase_attributed_v3_count_d7", np.array([]))
       return np.array([arr.sum() if len(arr) > 0 else 0.0], dtype=np.float32)
   ```

2. 32 new scalar features added to `dense_uups_lc_features` (each producing 1 value, not 5)
3. `dense_tower_mlp[0]` = 16 + 32 = 48 (smaller architecture change than the sequential approach)

**Trade-off**: Scalars are simpler and have a smaller architecture footprint, but discard game-level context. The sequential approach (recommended) is a strict superset of what the legacy model can represent.

---

## Appendix B: Files Changed Summary

| File | Change |
|------|--------|
| `src/unity_learner/data/spark/user_value/unified_cpe_datagen.py` | Import `enrich_raw_uups_*`, add UUPS enrichment call, append `_UUPS_*_COLS` to `_OUTPUT_COLS` |
| `src/unity_learner/experiment_repo/unified_user_value/v12_cpe_lc/features.py` | Add `dense_uups_lc_features` featureset, add to `model_features.combined_dense_features` |
| `src/unity_learner/experiment_repo/unified_user_value/v12_cpe_lc/config.json` | `dense_tower_mlp[0]`: 16 → 116 |
| `src/unity_learner/experiment_repo/unified_user_value/v12_cpe_lc/model.py` | No change required (inherits from DLRM base; dimension change is self-consistent) |
| `src/unity_learner/experiment_repo/unified_user_value/v12_cpe_lc/workflow.py` | Update experiment name reference; optionally increase Spark memory |
| _(Phase 2 only)_ `config.json` | `shared_bottom_mlp[0]`: 448 → 608 |
| _(Phase 2 only)_ `features.py` | Add sparse UUPS features to `individual_sparse_features` |
