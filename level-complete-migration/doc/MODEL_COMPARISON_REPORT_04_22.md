# Model Comparison Report: unified_cpe.v1_lc (PyTorch) vs Legacy BHV vs Legacy CTX

**Date:** 2026-05-06 *(updated from 2026-04-22)*
**New model artifact:** `gs://unity-ads-dd-ds-dev-prd-general/users/vector/models/vny2xtis3e`
**Legacy BHV artifact:** `gs://unity-ads-dd-ds-prd-app-trained-models/training/level_complete/bhv1p/20260505192543_hub`
**Legacy CTX artifact:** `gs://unity-ads-dd-ds-prd-app-trained-models/training/level_complete/ctx1r/20260505192538_hub`

> **Previous run (2026-04-22):** New model `5axhtssifz`, BHV `20260422132512_hub`, CTX `20260422132417_hub`.

---

## 1. Framework & Infrastructure

| Dimension | New (unified_cpe.v1_lc) | Legacy BHV | Legacy CTX |
|---|---|---|---|
| **Framework** | PyTorch 2.x + PyTorch Lightning | TensorFlow 2.11.1 + Keras | TensorFlow 2.11.1 + Keras |
| **Data format** | Parquet (GCS) | TFRecord (.gz) | TFRecord (.gz) |
| **GPU hardware** | 8x NVIDIA RTX PRO 6000 Blackwell | 1x Tesla T4 | 1x Tesla T4 |
| **Distributed** | DDP (8 GPUs, NCCL) | Single GPU | Single GPU |
| **Orchestration** | Metaflow workflow + Kubernetes | Kubeflow pipeline | Kubeflow pipeline |
| **Datagen** | Spark batch job (60-day window) | TFRecord pipeline per run | TFRecord pipeline per run |
| **Serving format** | Triton (packed input, static shape) | TF Hub SavedModel | TF Hub SavedModel |

---

## 2. Model Architecture

| Dimension | New (DLRM) | Legacy BHV (FC) | Legacy CTX (FC) |
|---|---|---|---|
| **Architecture type** | DLRM (Deep Learning Recommendation Model) | Fully Connected (FC) MLP | Fully Connected (FC) MLP |
| **Hidden layers** | shared_bottom [232→256→128] + per-task [128→256→1] | [1024→512→256→1] | [512→256→128→1] |
| **Activation** | SELU | ELU | ELU |
| **Batch normalization** | No | Yes | Yes |
| **Input dropout** | 0.0 | 0.05 | 0.05 |
| **Dense tower** | [16→64] → dense_emb_proj (67.1K params) | N/A (flat concat) | N/A (flat concat) |
| **Cross interaction** | DotProductPlus (dot product w/ attention [256,256] + residual [256,256], compress_dim=8) | None | None |
| **Deep cross network** | DeepCrossNet (2 layers, rank=128) on shared_bottom | None | None |
| **Sparse embeddings** | Hash-based, dim=32 (shared table, ~35.3M params) | Vocab-lookup, multiplier x2 | Vocab-lookup, multiplier x2 |
| **External embeddings** | None (IBT replaced by scalar features) | ibt_embedding (128d) + install_ibt (80d) | ibt_embedding (128d) + install_ibt (80d) |
| **Multi-task heads** | 2 tasks: `level_complete` + `prob_sdk_event_name_label` | 1 task: `label` | 1 task: `label` |
| **Loss weighting** | Learned homoscedastic uncertainty (MultiLossModule, 2 logvars) | Fixed (weighted_log_loss_level_complete) | Fixed (BCE) |
| **Total parameters** | **36.3M** (35.3M sparse + 1.0M dense) | N/A logged | N/A logged |
| **embedding_deep_l2** | N/A | 1e-8 | None |

> **Param count change vs April 22 run (5axhtssifz: ~99.6M):** The sparse embedding table shrank from ~98.6M to 35.3M. The shared hash table now serves all sparse features with ~1.1M total rows × dim=32, rather than per-feature tables sized by their individual hash dimensions. Dense component count is unchanged.

---

## 3. Training Configuration

| Dimension | New (unified_cpe.v1_lc) | Legacy BHV | Legacy CTX |
|---|---|---|---|
| **Batch size** | 25,600 (× 8 GPUs = 204,800 effective) | 20,000 | 20,000 |
| **Optimizer** | AdamW (weight_decay=0.05) | Adam | Adam |
| **Learning rate (dense)** | 0.001 (LRPolicyScheduler: warmup 30% → steady → decay 30%, end_lr=1e-6) | 0.003 (ReduceLROnPlateau, factor=0.75) | 0.003 (ReduceLROnPlateau, factor=0.75) |
| **Learning rate (embeddings)** | 0.0008 (separate AdamW, steady throughout) | Same as dense | Same as dense |
| **Max epochs** | 5 (no early stopping) | 50 (early stop patience=10) | 50 (early stop patience=10) |
| **Actual epochs run** | **5** | **33** (stopped ep23 best) | **35** (stopped ep25 best) |
| **Total global steps** | **23,719** | ~73,000 | ~106,000 |
| **Gradient clipping** | Yes (max_norm=1.0) | clipnorm=1.0 | clipnorm=1.0 |
| **Train data size** | **486,002,034** rows (install_date < 2026-04-25) | **44,354,363** rows | **60,427,534** rows |
| **Val data size** | **18,655,770** rows (install_date ≥ 2026-04-25) | **4,386,511** rows | **5,975,614** rows |
| **Data split** | Time-based: last 1 day = val | Random 90/10 (train dirs) | Random 90/10 (train dirs) |
| **Data window** | 60 days (2026-02-26 → 2026-04-26, single Parquet partition) | 60 days (2026-02-26 → 2026-04-26) | 60 days (2026-02-26 → 2026-04-26) |
| **Label (training target)** | `label` (CPE, 19.75% positive) + `prob_sdk_event_name_label` (7.0% positive) | `label` (CPI, ~37% positive) | `label` (CPI, ~37% positive) |

---

## 4. Feature Comparison

### 4.1 Dense / Scalar Features

| Feature | New DLRM | BHV | CTX |
|---|---|---|---|
| `gamer_creation_delay` | Yes (log1p, soft_clip) | No (disabled) | Yes (normalize) |
| `gamer_click_count` | Yes | Yes (log1p, clip=1000) | Yes (log1p, clip=1000 + impute) |
| `gamer_install_count` | Yes | Yes (log1p, clip=100) | Yes (log1p, clip=100 + impute) |
| `gamer_start_count` | Yes | Yes (log1p, clip=6000) | Yes (log1p, clip=6000 + impute) |
| `gamer_view_count` | Yes | Yes (log1p, clip=6000) | Yes (log1p, clip=6000 + impute) |
| `gamer_start_count_in_last_24h` | Yes | Yes (log1p, clip=100) | Yes (log1p, clip=100 + impute) |
| `gamer_start_count_in_last_7d` | Yes | Yes (log1p, clip=400) | Yes (log1p, clip=400 + impute) |
| Session counters (9 features) | **Yes** *(added back in Apr 26 datagen)* | No | Yes |
| Target game counters (7 base scalars) | No | Yes | No |
| **Target game 7d/24h counters (6 new)** | **Yes** *(new in Apr 26 datagen)* | Partial | No |
| UUPS IAP features d7+d30 (24 scalars) | No | Yes | No |
| UUPS adrev features (8 scalars) | No | Yes | No |
| Hardware stats (cpu_count, ram, dpi) | No | Yes (enriched from device_type) | Yes (enriched from device_type) |
| Apptopia store info scalars (6 features) | No | No | Yes |

### 4.2 Categorical / Sparse Features

| Feature | New DLRM | BHV | CTX |
|---|---|---|---|
| `platform` | Yes hash=10 | Yes vocab=3 | Yes vocab=3 |
| `geolocation_country` | Yes hash=350 | Yes vocab=200 | Yes vocab=206 |
| `device_type` | Yes hash=60000 | Yes vocab=4261 | Yes vocab=4589 |
| `device_connection_type` | Yes hash=11 | Yes vocab=4 | Yes vocab=4 |
| `device_orientation` | Yes hash=11 | No | No |
| `video_orientation` | Yes hash=10 | No | No |
| `ad_format` / `ad_type` | Yes `ad_format` hash=11 | Yes `ad_type` vocab=3 | Yes `ad_type` vocab=3 |
| `audience_id` | Yes hash=35000 | Yes vocab=5521 | Yes vocab=6291 |
| `publisher_store_id` | Yes hash=87000 | Yes vocab=8992 | Yes vocab=11037 |
| `publisher_developer_id` | Yes hash=70000 | Yes vocab=2426 | Yes vocab=2777 |
| `publisher_game_id` | Yes hash=46000 | Yes vocab=9034 | Yes vocab=11091 |
| `target_store_id` | Yes hash=87000 | Yes vocab=1358 | Yes vocab=1415 |
| `target_game_id` | Yes hash=46000 | Yes vocab=1376 | Yes vocab=1437 |
| `creative_id` | Yes hash=1M | No | No |
| `creative_pack_id` | Yes hash=651k | No | No |
| `model_name` | Yes hash=1000 | Yes vocab=84 | No |
| `gamer_id_scope` | Yes hash=12 | No | Yes vocab=4 |
| `tgtg_sdk_set` | **Yes** *(added back in Apr 26 datagen)* | Yes vocab=2586 | Yes vocab=2672 |
| `prob_sdk_event_name` | Yes hash=1M (`{target_game_id}_{event_name}`) | No (label sampling) | No (label sampling) |
| Privacy flags (`limited`/`coppa`/`opt_out_enabled`) | **Yes** *(added back in Apr 26 datagen)* | No | Yes |
| `counters_source` / `traffic_type` | **Yes** *(added back in Apr 26 datagen)* | No | Yes |
| `gamer_has_fingerprinted_identity` / `gamer_has_opted_out` / `gamer_limited_tracking` | **Yes** *(added back in Apr 26 datagen)* | No | Yes |
| UUPS IAP done flags (6 categoricals) | No | Yes | No |
| Hardware stats categoricals (cpu/gpu/res) | No | Yes (enriched) | Yes (enriched) |
| Apptopia categoricals (6 features) | No | No | Yes |
| IBT embedding (external TF sub-model) | No (replaced by scalar features) | Yes 128-dim | Yes 128-dim |
| install_ibt embedding (external TF sub-model) | No (replaced by scalar features) | Yes 80-dim | Yes 80-dim |

---

## 5. Key Architectural Differences

### 5.1 DLRM vs FC MLP
The new model uses an explicit feature interaction architecture (DotProductPlus cross-product + DeepCrossNet) rather than stacking dense layers on a flat concatenation. This allows the model to learn higher-order pairwise feature interactions directly rather than relying on depth to discover them implicitly.

### 5.2 IBT Replacement with Scalar Features
Legacy models call two external pre-trained TF sub-models at training time (ibt_embedding 128d + install_ibt_embedding 80d) to encode ad-request and install history into dense vectors. The new model drops these in favor of scalar gamer/target-game counter features computed offline in Spark datagen. This eliminates the dependency on external TF Hub models and simplifies the serving graph.

### 5.3 Multi-Task vs Single-Task with Learned Loss Weighting
The new model trains two output heads jointly (`level_complete` and `prob_sdk_event_name_label`) using **homoscedastic uncertainty weighting** (Kendall & Gal 2017). The MultiLossModule learns two logvar parameters:

```
total_loss = L_lc × exp(−s_lc) + s_lc + L_psn × exp(−s_psn) + s_psn
```

At epoch 4 (vny2xtis3e): `s_lc = 0.800` → effective weight `0.449`, `s_psn = 0.315` → effective weight `0.730`. The model has autonomously decided to weight `prob_sdk_event_name_label` ~1.6× more than `level_complete`, reflecting its lower uncertainty as the direct CPE bidding signal.

Legacy models train a single `label` head and implement per-SDK-event prediction via probabilistic label sampling at the data loading layer.

### 5.4 Hash-Based vs Vocabulary-Based Embeddings
Legacy models build per-feature vocabulary mapping files at startup from static MAPPINGS/ files (capped at `start_cutoff=500`), then apply `embedding_multiplier=2` to size the embedding dimension. The new model uses a shared hash table with uniform `sparse_embedding_dim=32`. This removes vocab management overhead and handles unseen keys gracefully at the cost of hash collisions.

### 5.5 Unified vs Segmented Models
BHV and CTX are separate models targeting distinct user traffic types. The new model unifies both into a single training run on combined data, using `gamer_id_scope` as a sparse feature to let the model learn segment-specific behavior implicitly.

### 5.6 Data Scale
The new model trains on **486M rows** per run (60-day combined Parquet). Legacy BHV: **44.4M**; Legacy CTX: **60.4M**. The new model sees ~8× more data per training run, offset by far fewer total gradient updates (23,719 steps vs ~73K–106K for legacy).

### 5.7 Label Definition
Legacy `label` = CPI install indicator (~37% positive rate). New `label` = CPE level-complete event within label window (~19.75% positive rate). The new `prob_sdk_event_name_label` is the per-sdk-event CPE label (~7.0% positive) used directly for bidding — structurally equivalent to legacy's probabilistic label output but computed deterministically at datagen time.

---

## 6. Feature Gaps: Legacy Signals Not Yet in v1_lc

The following signals exist in one or both legacy models but are still absent from v1_lc.

| Feature Group | Present in BHV | Present in CTX | Notes |
|---|---|---|---|
| UUPS IAP features (d7+d30, 30 scalars) | Yes | No | Key monetization signal; high-value for payer prediction |
| UUPS adrev features (8 scalars) | Yes | No | Ad revenue engagement signals |
| Target game base counters (7 scalars) | Yes | No | `target_game_start/view_count` (total, no time window) — Note: NEW has 7d/24h variants |
| Hardware stats (cpu_count, ram, dpi, cpu/gpu/res cat) | Yes | Yes | Device capability signals |
| Apptopia store metadata (12 features) | No | Yes | App category, subcategory, IAP flag, price, size, rating |
| `gamer_profile_meta` / `installed_store_ids*` | No | Yes | Install history arrays; dropped from NEW |
| IBT/profile counters (`ad_req_counts`, `gamer_profile_counters_adrequests_in_last_7_days`) | Yes | Yes | Ad request counters; dropped from NEW |

### Features New in v1_lc (not in any legacy)
- `creative_id` (hash=1M)
- `creative_pack_id` (hash=651k)
- `device_orientation` (hash=11), `video_orientation` (hash=10)
- `ad_format` (replaces `ad_type`, hash=11; splits interstitial/rewarded)
- `prob_sdk_event_name` as sparse embedding input (hash=1M, key=`{target_game_id}_{event_name}`)
- Multi-horizon labels: `app_event_d0/d1/d3/d7`, `app_event_w1/w2/w3/w4`, `app_event_count_w1–w4`, `cum_app_event_count_d0/d1/d3/d7/d14`
- Target game extended counters: `target_game_start/view/click_count_in_last_7_days`, `target_game_start/view_count_in_last_24_hours`, `target_game_click_count` (total)
- `bucket` (data split), `install_date` (explicit)

### Features Restored in Apr 26 Datagen (were missing in Apr 13, now present)
- Session counters (9): `gamer_session_counters_*`
- Privacy / identity (9): `coppa`, `fingerprinted`, `limited`, `opt_out_enabled`, `counters_source`, `traffic_type`, `gamer_has_fingerprinted_identity`, `gamer_has_opted_out`, `gamer_limited_tracking`
- `gamer_id_scope`, `tgtg_sdk_set`

---

## 7. Training Run Summary

| | New DLRM (vny2xtis3e) | Legacy BHV (20260505192543) | Legacy CTX (20260505192538) |
|---|---|---|---|
| **Start time** | 2026-05-05 19:42 UTC | 2026-05-06 08:02 UTC | 2026-05-06 08:07 UTC |
| **Data date** | 2026-04-26 | latest_complete (20260505) | latest_complete (20260505) |
| **Install range** | 2026-02-26 → 2026-04-26 | 2026-02-26 → 2026-04-26 | 2026-02-26 → 2026-04-26 |
| **Train rows** | 486,002,034 | 44,354,363 | 60,427,534 |
| **Val rows** | 18,655,770 | 4,386,511 | 5,975,614 |
| **IBT embedding version** | N/A | — | — |
| **Best epoch** | 5 (fixed, no early stop) | **23** / 33 total | **25** / 35 total |

---

## 8. Performance Metrics

### 8.1 Metric Comparability

Direct loss comparison across models is **not valid** due to:
1. **Different label definitions:** CPE (NEW, 19.75% pos) vs CPI install (legacy, ~37% pos)
2. **Different loss formulations:** Summed multi-task uncertainty-weighted loss (NEW) vs single-task BCE (legacy)
3. **Train vs val:** WandB metrics for NEW are logged on training batches; legacy metrics are on held-out val set

Use **NE (Normalized Entropy)** and **AUC** as the most comparable signals, noting train/val split.

### 8.2 Results

| Metric | NEW v1_lc (epoch 4, train) | BHV Legacy (best val, ep23) | CTX Legacy (best val, ep25) |
|---|---|---|---|
| **AUC** | **0.9483** (train) | 0.8997 (val) | 0.8991 (val) |
| **BCE (level_complete head only)** | **0.2047** (train) | 0.3308 (val, single task) | 0.3313 (val, single task) |
| **NE (window)** | **0.4119** (train) | ~0.505 (val, est.)† | ~0.506 (val, est.)† |
| **NE (lifetime)** | 0.4406 (train) | — | — |
| **Calibration ratio** | **0.9993 / 1.0000** | — | — |
| **mean_pred vs mean_label** | 0.1976 vs 0.1975 (Δ < 0.0001) | 0.2494 (bias=0.0025) | 0.2512 (bias=0.0031) |
| **val_loss (combined)** | **1.2880** | 0.3308 (single-task BCE) | 0.3313 |
| **train_loss (combined)** | 1.2929 | — | — |
| **Train–val loss gap** | **−0.4%** (val better) | n/a | n/a |

† Estimated as val_loss / H(base_rate) where H(0.37) ≈ 0.655.

**NE breakdown for NEW:**
Window NE = `bce_level_complete` / H(mean_label) = 0.2047 / H(0.1975) ≈ 0.2047 / 0.497 = **0.412** ✓ (matches logged 0.4119)

### 8.3 Epoch 4 WandB Summary (NEW model vny2xtis3e)

| WandB key | Value |
|---|---|
| `train/AUC` | **0.9483** |
| `train/bce_level_complete` | **0.2047** |
| `train/loss_level_complete_0` | 0.2059 |
| `train/loss_prob_sdk_event_name_label_0` | 0.1172 |
| `train/loss` (combined, uncertainty-weighted) | 1.2929 |
| `val_loss` (combined) | **1.2880** |
| `train/window_ne` | **0.4119** |
| `train/lifetime_ne` | 0.4406 |
| `train/window_cali` | 0.9993 |
| `train/lifetime_cali` | 1.0000 |
| `train/mean_label` | 0.1975 |
| `train/mean_pred` | 0.1976 |
| `level_complete_loss_weight_logvar` | 0.7998 → effective weight **0.449** |
| `prob_sdk_event_name_label_loss_weight_logvar` | 0.3151 → effective weight **0.730** |
| `learning_rate/optimizer_0_param_group_0` (embeddings) | 0.0008 |
| `learning_rate/optimizer_1_param_group_0` (dense) | **0.000001 = end_lr** |
| `trainer/global_step` | 23,719 |

### 8.4 Legacy Best-Epoch Results

**BHV (epoch 23 best, val):**

| Metric | Value |
|---|---|
| val_loss | **0.33077** |
| val_mean_auc | **0.8997** |
| val_weighted_log_loss | 0.32992 |
| val_mean_pred | 0.24944 |
| val_prediction_bias | 0.00249 |

**CTX (epoch 25 best, val):**

| Metric | Value |
|---|---|
| val_loss | **0.33127** |
| val_mean_auc | **0.8991** |
| val_weighted_log_loss | 0.33127 |
| val_mean_pred | 0.25122 |
| val_prediction_bias | 0.00309 |

---

## 9. Known Issues & Action Items

| Issue | Severity | Description |
|---|---|---|
| **LR schedule mismatch (dense layers)** | **HIGH** | `lr_scheduler.total_step: 88` matches `dataset_config.train_duration: 88` but actual training ran 23,719 global steps. Dense-layer LR decayed to `end_lr=1e-6` after ~88 steps (~0.4% of training) and stayed there. Only sparse embeddings (35.3M params) continued learning at lr=0.0008 throughout. All dense components (DCN, DotProductPlus, MLP, task heads) were effectively frozen for 99.6% of training. **Fix: set `lr_scheduler.total_step` to actual training step count.** |
| **Train-only AUC logging** | Medium | `train/AUC = 0.9483` is computed on training batches only. Val AUC for `level_complete` head must be retrieved separately from WandB (`auc_level_complete` val metric). |
| **app_event_w1/w2/w3/w4 identical** | Medium | All four weekly label columns are identical in the Apr 26 datagen (same 19.75% non-null rate). Multi-week horizon is not yet varying — verify multi-week attribution logic in datagen before using wX labels as auxiliary targets. |
| **No early stopping** | Low | NEW model trains for exactly 5 epochs regardless of val_loss plateau. Legacy models stop at epoch 23–25. Consider enabling `early_stopping` in trainer_config once LR schedule is fixed. |
| **Val split mismatch** | Low | NEW uses time-based val split (last 1 install day); legacy uses random 90/10 split. Val AUC numbers are not directly comparable even within the same label definition. |
