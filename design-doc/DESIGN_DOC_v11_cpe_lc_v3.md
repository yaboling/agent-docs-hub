# [v11_cpe_lc_v3] Design Doc — CPE Level Complete Serving Fix

> **Lineage:** `unified_user_value.v11_cpe_lc_v2`
> **Change type:** Hotfix — serving correctness
> **Owner:** Yabo Ling
> **Date:** 2026-08-07

---

## 1. Introduction

### 1.1 Problem Statement

`v11_cpe_lc_v2` uses `dynamic_hash_size_features` in `datagen_config` to size the model's sparse embedding tables dynamically from the live `feature_mapping.json` at training time, rather than using fixed hash sizes. In theory this eliminates hash collisions — in practice it creates a hard incompatibility between the model and the preprocessor at serving time.

**Root cause:**

```
Training time
─────────────────────────────────────────────────────────────────────
  FeatureSet.__post_init__ reads live GCS feature_mapping.json
  → audience_id has N unique values → embedding table size = N

  Model saved with embedding tables of size N (baked into .pt artifact)

Serving time
─────────────────────────────────────────────────────────────────────
  Incremental training runs update feature_mapping.json continuously.
  New audience_ids, creative_ids, etc. get sequential indices > N.

  Online preprocessor reads the CURRENT (live) feature_mapping.json
  (deploy_config.use_train_lookups = false, no bundled_feature_mapping_path)

  CategoricalLookup("new_audience") → index N+k  (k > 0)
  torch.embedding(weight, input=N+k)
    weight.shape[0] == N
    → RuntimeError: index out of range in self
─────────────────────────────────────────────────────────────────────
```

The model's `_checkpoint_hash_sizes` mechanism only patches the **model's embedding table init** — it does not cap the indices the preprocessor emits. The comment in `feature_set.py` that "ModelContainer.from_folder patches these from the checkpoint" is incorrect for the online preprocessor path; `_checkpoint_hash_sizes` is absent from all `data/preprocessor_v2/` code.

**Observed failure** (Triton inference error, production serving):

```
rpc error: code = Internal desc = failed to predict: chained inference failed at model
"unified-user-value-v11-cpe-lc-v2-1-model": ...
  File "code/__torch__/unity_learner/model/common/sparse_embedding.py", line 79, in forward
    _15 = torch.unsqueeze((_014).forward(input, ), 1)
  File "code/__torch__/torch/nn/modules/sparse.py", line 10, in forward
    return torch.embedding(weight, input)
           ~~~~~~~~~~~~~~~ <--- HERE
RuntimeError: index out of range in self
```

The crash is triggered any time the live `feature_mapping.json` grows beyond the training-time table size — guaranteed to happen on any active incremental training run.

**Why `dynamic_hash_size_features` cannot work safely with a live mapping path:**

```
Static hash (all other UV models)          Dynamic hash (v11_cpe_lc_v2)
──────────────────────────────────         ──────────────────────────────
Table size = fixed (e.g. 35,000)           Table size = N at training time
Mapping index > table size → CategoricalLookup returns UNKNOWN_INT (safe)
                                            Mapping index = N+k → sent to model
                                            → index out of range (crash)
```

### 1.2 Success Criteria

| Criterion | Target |
| --- | --- |
| **Serving correctness** | No `index out of range` errors from sparse embedding lookup after deploy |
| **Model quality parity** | AUC / NE / calibration within ±1pp of v11_cpe_lc_v2 on the same held-out eval set |
| **Business metric parity** | Neutral-to-positive vs. v11_cpe_lc_v2 in online A/B test |
| **Long-term stability** | Model survives incremental mapping updates without redeployment of preprocessor |

---

## 2. Data Overview

### 2.1 Data Source

v11_cpe_lc_v3 uses the same data pipeline as v11_cpe_lc_v2 with a new GCS prefix for the v3 artifacts.

```
Data Pipeline at a Glance
───────────────────────────────────────────────────────────────────────
  Source
  gs://unity-ads-dd-ds-prd-data-anon/
    app-events/data/ads.events.operativeecpm.installs.outcomes.v2/
    level_complete/d7/

  Partition Key: installDate=YYYY-MM-DD
  Training Window: 88 days
  Label Window: 7 days (app_event_w1 > 0)

  Output (v3 paths)
  gs://unity-ads-dd-ds-prd-incremental-training-data/
    user_value/unified_user_value.v11_cpe_lc_v3/preprocessed_combined/

  Feature Mapping (v3 path)
  gs://unity-ads-dd-ds-prd-incremental-training-data/
    user_value/unified_user_value.v11_cpe_lc_v3/feature_mapping.json
───────────────────────────────────────────────────────────────────────
```

**Row expansion design** (unchanged from v11_cpe_lc_v2): each install is exploded by `sdk_event_name` target — one row per `(install × targeted SDK event)`.

### 2.2 Label Design

Identical to v11_cpe_lc_v2. Two labels per row:

| Label | Definition | Positive Rate |
| --- | --- | --- |
| `label` | `app_event_w1 > 0` — any level complete within 7 days. Present in parquet but **not used** as training target. | ~38% |
| `prob_sdk_event_name_label` | `1.0` if user fired the specific campaign-targeted SDK event AND `app_event_w1 > 0`, else `0.0`. **Primary training target.** | ~14% (specific events) / ~26% (wildcard `*`) |

### 2.3 Game-Level Quality Gate

Unchanged from v11_cpe_lc_v2. Mirrors the legacy `ads-audience-pinpointer` eligibility filter:

```python
# Keep only games with >= 50 installs having cum_app_event_count_d7 > 0
eligible_game_ids = (
    df.filter(col("cum_app_event_count_d7") > 0)
      .groupBy("targetGameId")
      .agg(count("*").alias("_event_gamers"))
      .filter(col("_event_gamers") >= 50)
)
```

The eligibility gate at serving time (`_gate_tensor[target_game_id, sdk_event_name]`) is also unchanged — only trained `(game, sdk_event)` combinations with at least one positive PSN label receive a non-zero bid.

### 2.4 Label Distribution

Same as v11_cpe_lc_v2 (v3 dataset, post-quality-gate):

```
Row composition by label combination
───────────────────────────────────────────────────────────────────────
                                    0%          25%         50%
 label=0, psn=0  (non-converters)   █████████████████████████████████  61.84%
 label=1, psn=0  (LC but wrong SDK) ████████████  23.91%
 label=1, psn=1  (target event hit) ███████  14.25%
───────────────────────────────────────────────────────────────────────
  label positive rate     = 38.16%  (any level complete within 7d)
  psn_label positive rate = 14.25%  (specific targeted SDK event fired)
```

> **Note:** The training positive rate (~14%) is approximately 2× the true population rate (~7.5%) due to the game quality gate survivorship bias. Online calibration monitoring is required post-launch.

---

## 3. Model Overview

### 3.1 Model Card

**The only change from v11_cpe_lc_v2 is the removal of `dynamic_hash_size_features`.**

All other architecture, feature, and training hyperparameters are identical.

**Key configuration (v11_cpe_lc_v3 vs v11_cpe_lc_v2):**

| Parameter | v11_cpe_lc_v2 | v11_cpe_lc_v3 | Note |
| --- | --- | --- | --- |
| `datagen_config.dynamic_hash_size_features` | 21 features listed | `{}` (empty) | **The fix** |
| `datagen_config.mapping_path` | `.../v11_cpe_lc_v2/feature_mapping.json` | `.../v11_cpe_lc_v3/feature_mapping.json` | New GCS path |
| `dataset_config.dataset_id` | `unified_user_value_v11_cpe_lc_v2` | `unified_user_value_v11_cpe_lc_v3` | New BQ dataset |
| Architecture | DLRM + DCN, 36.3M params | Same | Unchanged |
| Sparse embedding hash sizes | Dynamic (from live mapping) | **Static (from features.py)** | Core change |
| Training window | 88 days | 88 days | Unchanged |

**Static hash sizes (features.py) restored as source of truth:**

| Feature | Hash Size | Headroom vs. typical cardinality |
| --- | --- | --- |
| `audience_id` | 35,000 | ~10–20× current cardinality |
| `device_type` | 60,000 | Large headroom |
| `publisher_store_id` / `target_store_id` | 87,000 | Large headroom |
| `publisher_developer_id` / `target_developer_id` | 70,000 | Large headroom |
| `publisher_game_id` / `target_game_id` | 46,000 | Large headroom |
| `sdk_event_name` | 10,000 | Large headroom |
| `geolocation_country` | 350 | Stable (ISO countries) |
| `platform` | 10 | Stable |
| `gamer_id_scope` | 12 | Stable |

With static hash sizes, `CategoricalLookup` maps unknown/new values to `UNKNOWN_INT` (index 5) — the standard handling used by all other UV and conversion models. No index-out-of-range is possible as long as the mapping values stay within the static bound, which is guaranteed because the mapping assigns sequential indices (new values never exceed existing count + 1).

**Architecture (unchanged):**

```
Dense features (19 total)                    Sparse features (16 total)
  ├─ gamer_creation_delay (1)                  ├─ geolocation_country, platform
  └─ AGC counters (15)                         ├─ gamer_id_scope
  └─ HW stats: cpu_count, ram, dpi (3)         ├─ device_connection_type, device_type
                                               ├─ audience_id
        │                                      ├─ publisher_{store/dev/game}_id
        ▼                                      ├─ target_{store/game/dev}_id
  Dense Tower MLP                              ├─ sdk_event_name
  [19 → 128]                                   └─ hw_stats: cpu, gpu, res
  BatchNorm + Dropout(0.1)
        │                                              │
        └──────────────────────────────────────────►  │
                                                       ▼
                                            DotProductPlus + DCN (2 layers)
                                            compress_dim=16
                                                       │
                                                       ▼
                                            Shared Bottom MLP
                                            [416 → 512 → 256]
                                            BatchNorm + Dropout(0.3)
                                                       │
                                                       ▼
                                            PSN Head: [256 → 512 → 1]
                                            Dropout(0.3) + Sigmoid
                                                       │
                                                       ▼
                                              P(user fires targeted
                                               SDK event within 7d)
```

**Bidding logic (unchanged from v11_cpe_lc_v2):**

```
1. psn_pred  = model sigmoid output
2. p_raw     = clamp(psn_pred, 0.0, 1.0)
3. calib     = _calib_tensor[audience_id_idx]        ← product accuracy calibration
4. gate      = _gate_tensor[target_game_id, sdk_event_name]  ← eligibility
5. p         = clamp(p_raw × calib, 0.0, 1.0)
6. cost      = clamp(max_cost × discount_factor × p × gate, 0.0, MAX_MICRODOLLARS)
```

**Workflow (simplified from v11_cpe_lc_v2):**

The `refresh_calibration` step is removed from the Vertex AI DAG (was `@skip_step` in v2, which caused `model_deploy` to render disconnected from the pipeline graph). The step can be re-added as a non-skipped step once calibration is enabled.

```
Daily Automated Workflow  (cron: 0 15 * * *)
─────────────────────────────────────────────────────────────────────────────
  run_datagen
    │  Spark batch: reads latest 88-day window from v2/level_complete/d7
    │  Writes to preprocessed_combined/date={train_end}/
    │  Timeout: 8 hours
    ▼
  update_mappings
    │  Spark: builds feature_mapping.json + trained_game_sdk_combo.json
    │  Timeout: 1 hour
    ▼
  create_bq_table
    │  Creates BQ external table over GCS parquet for schema inference
    ▼
  model_train
    │  K8s job, 8× RTX PRO 6000 Blackwell (8xg4 nodepool)
    │  Computes total_step dynamically from BQ COUNT(*)
    │  Train: bucket < 0.9 / Val: bucket >= 0.9
    │  Timeout: 18 hours
    ▼
  model_publish
    │  Publishes artifact to model store
    ▼
  model_deploy
     Triton deploy (CPU, packed input, static shape)
     Uploads to staging + production
─────────────────────────────────────────────────────────────────────────────
```

### 3.2 Offline Results

> **TBD** — first training run in progress. To be filled in after the initial training completes.

Expected metrics (based on v11_cpe_lc_v2 as baseline):

| Metric | v11_cpe_lc_v2 (reference) | v11_cpe_lc_v3 (expected) |
| --- | --- | --- |
| AUC | TBD | ≈ v2 (same architecture, larger static tables only change unknown-value handling) |
| NE | TBD | ≈ v2 |
| Calibration ratio | TBD | ≈ v2 |
| Prediction bias | TBD | ≈ v2 |

> **Note on expected impact of static vs. dynamic hash sizes:** Dynamic hash sizing prevented hash collisions at the cost of serving instability. Static hash sizes introduce a small probability of collision for the rarest values (those beyond the static cap), but the affected features (`audience_id` cap=35k, etc.) have generous headroom well above current cardinality. The quality impact is expected to be negligible.

---

## 4. Online Test

> EP links: TBD

### 4.1 Executive Summary

> **TBD** — online A/B test has not yet been run. v11_cpe_lc_v3 is a serving correctness fix; the primary online hypothesis is metric parity with v11_cpe_lc_v2 (no regression), not lift over legacy.

**Test design (planned):**

```
Experiment Setup
─────────────────────────────────────────────────────────────────────
  Test     v11_cpe_lc_v3   50%   Static hash sizes (serving fix)
  Control  v11_cpe_lc_v2   50%   Dynamic hash sizes (current production)
─────────────────────────────────────────────────────────────────────
  Primary metric: Net Revenue (Level Complete traffic)
  Guard rails:    Installs, Publisher Revenue, Advertiser Spend
  Quality:        Product bias on target events (D0/D1/D3/D7)
  Serving:        Zero valuation rate, error rate (serving logs)
─────────────────────────────────────────────────────────────────────
```

**Go/no-go criteria:**

| Signal | Threshold |
| --- | --- |
| Net Revenue (LC traffic) | Within ±5% of control |
| `index out of range` errors | Zero in v3 arm |
| Product bias (target event, D3) | Within ±10pp of v2 |

### 4.2 Performance Breakdown

> **TBD** — to be filled in after online test completes.

---

## 5. Code Changes

| File | Change |
| --- | --- |
| `config.json` | `dynamic_hash_size_features` set to `{}` (was 21 features); GCS paths → v3; `dataset_id` / `table_id` → v3; `lineage` set to `v11_cpe_lc_v2`; description updated |
| `workflow.py` | GCS paths → v3; Spark job labels → v3; `refresh_calibration` step removed from DAG (fixes disconnected `model_deploy` in Vertex UI); `skip_step` import removed |
| `features.py` | Identical to v11_cpe_lc_v2 (static hash sizes were always defined here; dynamic override is now gone) |
| `model.py` | Comment updated v2 → v3; logic unchanged |
| `metrics_callback.py` | Docstring updated v2 → v3; logic unchanged |
| `scripts/refresh_product_accuracy_calibration.py` | `_CALIB_OUTPUT_PATH` → v3 GCS path; `_MODEL_NAME_PREFIX` → `unified-user-value-v11-cpe-lc-v3` |

---

## 6. Open Items

| Item | Status | Owner |
| --- | --- | --- |
| First training run | In progress | Yabo Ling |
| Offline evaluation vs. v11_cpe_lc_v2 | TODO (post-training) | Yabo Ling |
| Online A/B test vs. v11_cpe_lc_v2 | TODO | Yabo Ling |
| Enable `enable_product_accuracy_calibration: true` (post-serving traffic accumulation) | Deferred | Yabo Ling |
| Fix `_checkpoint_hash_sizes` comment in `feature_set.py:61` (misleading — does not patch preprocessor) | TODO | Yabo Ling |
| Evaluate whether `dynamic_hash_size_features` should be removed from the framework entirely | TODO | Yabo Ling |
