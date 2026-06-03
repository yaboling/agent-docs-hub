# v11_cpe_lc Serving Error Analysis: `index out of range in self`

**Date:** 2026-06-03
**Model:** `unified-user-value-v11-cpe-lc-4-model`
**Experiment:** `unified_user_value.v11_cpe_lc`
**Symptom:** High error rate in serving with `RuntimeError: index out of range in self` inside `torch.embedding()`

---

## Summary

The root cause is **vocabulary drift**: the `feature_mapping.json` on GCS was overwritten by a datagen refresh with new vocabulary entries, but the deployed model was not retrained or redeployed. The serving preprocessor picked up the updated mapping and began encoding new feature values to indices that exceed the frozen embedding table sizes in the deployed model artifact.

No code or model change was required to trigger this — only the GCS file needed to grow.

---

## Error Location in the Stack

```
RuntimeError: index out of range in self
  ← torch.embedding(weight, input)
  ← nn.Embedding.forward()                         [sparse/___torch_mangle_39.py:10]
  ← SparseEmbedding.forward(), argument_15         [sparse_embedding.py:115]
  ← DLRM.common_forward()                          [dlrm.py:249]
  ← DLRM.forward_before_flatten()                  [dlrm.py:294]
  ← DLRM.forward()                                 [dlrm.py:312]
```

The error is thrown by a raw `torch.embedding()` call — there is no OOV clamping in the base `SparseEmbedding` layer.

---

## Root Cause: Vocabulary Drift

### Step-by-step mechanism

1. **At training time**, `get_hash_sizes_from_feature_mapping()` reads `feature_mapping.json` from GCS:
   ```
   gs://unity-ads-dd-ds-prd-incremental-training-data/user_value/
       unified_user_value.v11_cpe_lc/feature_mapping.json
   ```
   It computes `hash_size = max(index_values) + 1` for each feature. This determines the **embedding table row count**, which is frozen into the model artifact.

2. **At serving time**, the preprocessor reads from the same live GCS path (`datagen_config.mapping_path` in `config.json`). There is no frozen snapshot — it always reads the current version.

3. **During a datagen refresh**, the pipeline overwrites `feature_mapping.json` with a larger vocabulary (new creatives, new games, new campaigns, etc.) — even without retraining or redeploying the model.

4. **After the refresh**, new string values are mapped to **new integer indices** that exceed the deployed model's embedding table size → `index out of range`.

### Key code paths

| Component | File | Behavior |
|-----------|------|----------|
| Training hash size resolution | `data/preprocessor_v2/utils.py:347` | Reads live GCS mapping, `hash_size = max(values) + 1` |
| Dynamic hash size override | `data/preprocessor_v2/feature_set.py:60-77` | Patches `feature.hash_size` from `feature_mapping.json` for all features listed under `dynamic_hash_size_features` |
| Model checkpoint restore | `container/container.py:270` | Loads `mega_config.json` from checkpoint — but `mapping_path` still points to the live GCS path, not a frozen snapshot |
| Sparse embedding forward | `model/common/sparse_embedding.py:268` | Passes raw indices to `nn.EmbeddingBag` / `F.embedding` with no OOV clamping |

---

## Affected Feature: `creative_pack_id` (position 15)

The TorchScript traceback shows the failure at `argument_15` in `sparse_embeddings.forward()`, which receives 18 positional tensors — one per feature in `individual_sparse_features` (`features.py:72-95`):

| Index | Feature | Hash Size | Dynamic |
|-------|---------|-----------|---------|
| 0 | `ad_format` | 11 | yes |
| 1 | `geolocation_country` | 350 | yes |
| 2 | `platform` | 10 | yes |
| 3 | `gamer_id_scope` | 12 | yes |
| 4 | `video_orientation` | 10 | yes |
| 5 | `device_connection_type` | 11 | yes |
| 6 | `device_type` | 60,000 | yes |
| 7 | `device_orientation` | 11 | yes |
| 8 | `audience_id` | 35,000 | yes |
| 9 | `publisher_store_id` | 87,000 | yes |
| 10 | `publisher_developer_id` | 70,000 | yes |
| 11 | `publisher_game_id` | 46,000 | yes |
| 12 | `target_store_id` | 87,000 | yes |
| 13 | `target_game_id` | 46,000 | yes |
| 14 | `creative_id` | 1,000,000 | yes |
| **15** | **`creative_pack_id`** | **651,011** | **yes** |
| 16 | `ad_type` | 110 | yes |
| 17 | `sdk_event_name` | 10,000 | yes |

**`creative_pack_id`** (pos 15) is the most likely culprit: it has a large, fast-growing vocabulary (new creative packs are created continuously), making it the first to overflow after a refresh. `creative_id` (pos 14) is the next highest risk.

### Why the existing clamping does not help

`DeployModel.forward()` in `model.py` already clamps `target_game_id` and `audience_id` before using them for the eligibility gate tensor and calibration tensor lookups. However, these clamps are only applied to the custom gate/calibration logic. The sparse feature tensors fed into `self.model(inputs)` (the DLRM base model) are passed **unclamped** — and the base `SparseEmbedding` layer has no OOV protection.

---

## Immediate Mitigation

**Option A (recommended):** Retrain and redeploy the model against the current `feature_mapping.json`. This is the correct fix — the vocabulary has legitimately grown and the model needs to accommodate it.

**Option B (stop the bleeding):** Roll back the GCS `feature_mapping.json` to the snapshot that was current when the last successful model was trained. This restores serving stability while the new model trains.

To identify the correct snapshot version, check the GCS object history:
```bash
gsutil ls -la gs://unity-ads-dd-ds-prd-incremental-training-data/user_value/unified_user_value.v11_cpe_lc/feature_mapping.json
```

---

## Fix Applied

### Root cause of zero headroom (deeper issue)

Two problems compounded to produce zero embedding table headroom:

**Problem 1** — `get_hash_sizes_from_feature_mapping` (`utils.py:366`) returns the absolute minimum:
```python
result[field] = max(int(v) for v in mapping.values()) + 1  # max_index + 1, no buffer
```

**Problem 2** — `feature_set.py:77` did a hard assignment, discarding the static value:
```python
feature.hash_size = hash_size  # silently drops the features.py declaration
```

The static `hash_size` values in `features.py` (651K for `creative_pack_id`, 1M for `creative_id`, etc.) were intended as pre-allocated capacity with headroom, but `dynamic_hash_size_features` override was replacing them with the exact vocab count at training time. Any vocabulary growth after training would immediately cause an out-of-range error.

### Code fix (`feature_set.py:77`)

```python
# Before
feature.hash_size = hash_size

# After
feature.hash_size = max(feature.hash_size, hash_size)
```

**Committed to:** `src/unity_learner/data/preprocessor_v2/feature_set.py`

The static `hash_size` from `features.py` now acts as a minimum floor. The embedding table grows if the live vocabulary exceeds the static declaration, but never shrinks below it. This gives `creative_pack_id` ~51K rows of buffer, `creative_id` up to 400K rows of buffer, etc. — absorbing vocabulary growth between model refreshes without crashing.

**Note:** This fix applies to **future-trained models**. The currently deployed model was trained with tight sizing and still needs to be redeployed to recover from the active error rate.

---

## Long-term Fix

The root issue is that the serving preprocessor reads from a live GCS path rather than a version-pinned snapshot.

**Recommended**: When saving the model container (`container.py:to_folder`), copy the current `feature_mapping.json` into the artifact folder alongside `mega_config.json`, `model.pth`, etc. At serving time (`from_folder`), load vocab from this frozen copy instead of the live GCS path. This ensures training-time and serving-time vocabularies are always identical, regardless of subsequent datagen runs.

---

## Files Referenced

| File | Role |
|------|------|
| `src/unity_learner/experiment_repo/unified_user_value/v11_cpe_lc/features.py` | Defines the 18 sparse features and their static hash sizes (intended as capacity floors) |
| `src/unity_learner/experiment_repo/unified_user_value/v11_cpe_lc/config.json` | `datagen_config.dynamic_hash_size_features` lists all dynamically-sized features; `datagen_config.mapping_path` is the live GCS path |
| `src/unity_learner/data/preprocessor_v2/utils.py:347` | `get_hash_sizes_from_feature_mapping()` — reads live GCS mapping and computes `max_index + 1` (no buffer) |
| `src/unity_learner/data/preprocessor_v2/feature_set.py:60-77` | **Fixed**: now uses `max(static, dynamic)` so static hash_size acts as a floor |
| `src/unity_learner/model/common/sparse_embedding.py` | Embedding lookup — no OOV clamping |
| `src/unity_learner/container/container.py` | `from_folder` loads `mega_config.json` but does not freeze the vocab snapshot |
| `src/unity_learner/experiment_repo/unified_user_value/v11_cpe_lc/model.py:473-484` | Existing clamps for gate/calibration only — does not protect DLRM embedding inputs |
