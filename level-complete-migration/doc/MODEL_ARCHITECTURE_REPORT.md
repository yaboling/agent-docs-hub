# Level Complete Model Architecture Report

Comparison of the legacy `ads-audience-pinpointer` level complete model (`level_complete_bhv`) against
the new `ads-unified-learner` model (`unified_cpe.v1_lc`).

---

## 1. Legacy Model (`level_complete_bhv`)

### Framework & Files
- **Framework**: TensorFlow
- **Config**: `cpi-model/configs/prd/config_level_complete_bhv.yaml`
- **Features**: `cpi-model/configs/prd/features_level_complete_bhv.yaml`
- **Base config**: `base-configs/level_complete_base_config.yaml`

### Training Label
| Label | Definition |
|-------|-----------|
| `label` | Binary: did the user complete a level within 7 days of install? Source column `app_event_w1 >= 1`. |

### Network Architecture
```
FC (Fully Connected), 3 layers
  [input]
     │  input_dropout: 0.05
     ↓
  Dense(1024, ELU, dropout=0.40, BatchNorm)
     ↓
  Dense(512, ELU, dropout=0.20, BatchNorm)
     ↓
  Dense(256, ELU, dropout=0.10, BatchNorm)
     ↓
  [output: sigmoid probability]
```
- **Activation**: ELU throughout
- **Batch normalization**: enabled after each layer
- **Embedding multiplier**: 2× for categorical embeddings, `uniform` initializer

### Input Features

**Scalar (continuous) features — all preprocessed with `log1p_normalize` or `normalize`:**
| Feature | Clip | Preprocessor |
|---------|------|-------------|
| gamer_click_count | 1000 | log1p_normalize |
| gamer_install_count | 100 | log1p_normalize |
| gamer_start_count | 6000 | log1p_normalize |
| gamer_view_count | 6000 | log1p_normalize |
| gamer_start_count_in_last_24_hours | 100 | log1p_normalize |
| gamer_start_count_in_last_7_days | 400 | log1p_normalize |
| target_game_click_count_in_last_24_hours | — | normalize |
| target_game_start_count | — | normalize |
| target_game_start_count_in_last_24_hours | — | normalize |
| target_game_start_count_in_last_7_days | — | normalize |
| target_game_view_count | — | normalize |
| target_game_view_count_in_last_24_hours | — | normalize |
| target_game_view_count_in_last_7_days | — | normalize |

**Hardware enriched scalars (sourced from `device_type` via `hardware_stats`):**
| Feature | Clip |
|---------|------|
| hardware_stats_cpu_count | 16 |
| hardware_stats_ram | 16384 |
| hardware_stats_dpi | 640 |

**Categorical features (embedding lookup):**
- audience_id, device_connection_type, device_type, geolocation_country, platform,
  publisher_developer_id, publisher_game_id, publisher_store_id, target_game_id, target_store_id
- hardware_stats_cpu, hardware_stats_gpu, hardware_stats_res (enriched categoricals)
- uups_attributed_iap_done_d7/d30, uups_unattributed_iap_done_d7/d30, uups_uasdk_iap_done_d7/d30

**UUPS (User Purchase Signal) scalar features:**
- 12 features covering attributed/unattributed/uasdk IAP counts and log avg values at d7 and d30
- 4 ad revenue features (oecpm rewarded/interstitial count+sum at d7 and d30)

**External TF embeddings:**
| Embedding | Dim | Source |
|-----------|-----|--------|
| ibt_embedding | 128 | `adreq_ibt_single_games/v1a` (ad request IBT) |
| install_ibt_embedding | 80 | `install_ibt/v1b/temporal` (install IBT) |

**SDK event name features:**
| Feature | Role |
|---------|------|
| sdk_event_name | Campaign-level targeted event (string, passthrough) |
| prob_sdk_event_name_array | Training-only: array of `"{game_id}_{event_name}"` tokens |
| prob_sdk_event_name_labels | Training-only: parallel float labels per token |
| tgtg_sdk_set | SDK set categorical (SdkSetPreprocessor) |

**Disabled / passthrough (not fed to network):**
- gamer_creation_delay (disabled), ad_request_timestamp, gamer_creation_timestamp,
  publisher_is_coppa_targeted, ad_req_project_id, ad_req_counts, installed_store_ids,
  installed_store_ids_latest_start_ts

### Training Configuration
| Parameter | Value |
|-----------|-------|
| Batch size | 20,000 |
| Learning rate | 0.003 |
| Max iterations | 50 |
| Early stopping patience | 10 |
| Val loss limit | 0.8 |
| Log loss max | 0.4 |
| Probabilistic labels | enabled |

### Output
- Single scalar: `P(level complete within 7d of install)` — sigmoid output
- Deployed to Firestore (production collection)

---

## 2. New UL Model (`unified_cpe.v1_lc`)

### Framework & Files
- **Framework**: PyTorch + PyTorch Lightning
- **Architecture class**: `DLRM` (Deep Learning Recommendation Model variant)
- **Config**: `experiment_repo/unified_cpe/v1_lc/config.json`
- **Features**: `experiment_repo/unified_cpe/v1_lc/features.py`
- **Model**: `experiment_repo/unified_cpe/v1_lc/model.py`

### Training Labels
| Task | Label Column | Loss | Weight |
|------|-------------|------|--------|
| `level_complete` (main) | `label` | BCE | 1.0 |
| `prob_sdk_event_name_label` | `prob_sdk_event_name_label` | BCE | 1.0 |

The model is **multi-task**: it jointly trains the primary level complete prediction alongside the
SDK event label. Only `level_complete` output is used at serving.

Label source: `label = (app_event_w1 > 0) ? 1 : 0` (same 7-day definition as legacy).

### Network Architecture

```
[Dense features: 16 scalars]
        │
  Dense Tower MLP: Linear(16→64, SELU)          ← dense_tower_mlp = [16, 64]
        │
  Dense Emb Proj:  Linear(64→512→64)            ← projects to sparse embedding space
        │
[Sparse embeddings: 19 features × 32-dim]       ← sparse_embedding_dim = 32
        │
  DotProductPlus (21 embeddings):
    ├── Attention net:  MLP(672→256→256→168)     ← dot_product_attention_mlp = [256, 256]
    └── Residual net:   MLP(672→256→256→256)     ← dot_product_resnet_mlp = [256, 256]
    → compress to k=8 per embedding pair         ← dot_product_compress_dim = 8
    → output: 21 × 8 = 168-dim cross features
        │
  Shared bottom = concat(cross_dense_sparse[168], dense_repr[64]) = 232-dim
        │
  DeepCrossNet (2 layers, rank=128) in parallel with:
  MLP projection: Linear(232→256→128, SELU)     ← shared_bottom_mlp = [232, 256, 128]
        │
        ├── Task head: level_complete
        │     MLP(128→256→1, SELU, Sigmoid)     ← mlp_layers = [128, 256, 1]
        │
        └── Task head: prob_sdk_event_name_label
              MLP(128→256→1, SELU, Sigmoid)
```

- **Activation**: SELU throughout (dense tower, shared bottom, task heads)
- **Weight init**: Xavier Normal for MLPs, Uniform for embeddings
- **Gradient clipping**: max_norm=1.0

### Input Features

**Dense features (16 total, all online+offline):**

*LC-specific (1):*
| Feature | Transform |
|---------|-----------|
| gamer_creation_delay | soft_clip(1.5e8) → log1p |

*AGC features (15):*
| Feature | Transform |
|---------|-----------|
| gamer_click_count | soft_clip(10) → log1p |
| gamer_install_count | soft_clip(10) → log1p |
| gamer_start_count | soft_clip(20) → log1p |
| gamer_start_count_in_last_24_hours | soft_clip(10) → log1p |
| gamer_start_count_in_last_7_days | soft_clip(10) → log1p |
| gamer_view_count | soft_clip(10) → log1p |
| target_game_click_count | soft_clip(10) → log1p |
| target_game_click_count_in_last_24_hours | soft_clip(10) → log1p |
| target_game_click_count_in_last_7_days | soft_clip(10) → log1p |
| target_game_start_count | soft_clip(10) → log1p |
| target_game_start_count_in_last_24_hours | soft_clip(10) → log1p |
| target_game_start_count_in_last_7_days | soft_clip(10) → log1p |
| target_game_view_count | soft_clip(10) → log1p |
| target_game_view_count_in_last_24_hours | soft_clip(10) → log1p |
| target_game_view_count_in_last_7_days | soft_clip(10) → log1p |

**Sparse features (19 total, embedding_dim=32, online+offline):**

*Individual sparse (18):*
| Feature | Hash Size | list_len | agg_mode |
|---------|-----------|----------|---------|
| ad_format | 11 | 1 | mean |
| geolocation_country | 350 | 1 | mean |
| platform | 10 | 1 | mean |
| gamer_id_scope | 12 | 1 | mean |
| video_orientation | 10 | 1 | mean |
| device_connection_type | 11 | 1 | mean |
| device_type | 60,000 | 1 | mean |
| device_orientation | 11 | 1 | mean |
| audience_id | 35,000 | 1 | mean |
| publisher_store_id | 87,000 | 1 | mean |
| publisher_developer_id | 70,000 | 1 | mean |
| publisher_game_id | 46,000 | 1 | mean |
| target_store_id | 87,000 | 1 | mean |
| target_game_id | 46,000 | 1 | mean |
| creative_id | 1,000,000 | 1 | mean |
| creative_pack_id | 651,011 | 1 | mean |
| ad_type | 110 | 1 | mean |
| model_name | 1,000 | 1 | mean |

*SDK event feature (1):*
| Feature | Hash Size | list_len | agg_mode | Note |
|---------|-----------|----------|---------|------|
| prob_sdk_event_name | 1,000,000 | 10 | mean | `"{game_id}_{event_name}"` tokens |

**Dense embedding projection:**
64-dim dense representation is projected to match sparse 32-dim space, contributing
`dense_embedding_dim // sparse_embedding_dim = 64 // 32 = 2` additional "virtual" embedding slots.
Total embedding slots: 18 + 1 + 2 = **21**.

**Offline-only features (not fed to model):**
- `valuation_id`, `bucket` (train/val split)

### Training Configuration
| Parameter | Value |
|-----------|-------|
| Batch size | 25,600 |
| Main optimizer | AdamW (lr=0.001, β=(0.9,0.999), wd=0.05) |
| Embedding optimizer | AdamW (lr=0.0008, wd=0.0) |
| LR scheduler (main) | OneCycleLR (max_lr=0.001, pct_start=0.3, three_phase=True) |
| LR scheduler (emb) | LRPolicyScheduler (steady_lr=0.0008) |
| Max epochs | 5 |
| Devices | 8 × GPU (DDP) |
| Workers per GPU | 4 |
| Training window | 88 days |
| Train split | `bucket <= 0.9` |
| Val split | `bucket > 0.9` |

### Output
- 4 values repeated: `[mean, sampled, calibrated_mean, calibrated_sampled]`
  (calibration not enabled; all 4 are identical at current config)
- Primary task: `level_complete` sigmoid prediction

---

## 3. Side-by-Side Comparison

| Dimension | Legacy (`level_complete_bhv`) | New UL (`unified_cpe.v1_lc`) |
|-----------|-------------------------------|-------------------------------|
| **Framework** | TensorFlow | PyTorch + Lightning |
| **Architecture** | FC (3-layer MLP) | DLRM (dense tower + dot product + DCN + shared bottom) |
| **Tasks** | Single (level_complete) | Multi-task (level_complete + prob_sdk_event_name_label) |
| **Label** | `label` (binary, app_event_w1≥1) | Same definition |
| **Dense features** | 13 scalar + 3 hw enriched = **16** | 16 (1 LC-specific + 15 AGC) |
| **Categorical features** | ~20 + 3 hw enriched (TF hash tables) | 18 sparse embeddings (PyTorch EmbeddingBag) |
| **External embeddings** | IBT (128-dim) + install IBT (80-dim) | None in v1 (TODO) |
| **UUPS features** | 20 IAP/adrev features | None in v1 (TODO) |
| **Hardware stats** | 3 enriched scalars + 3 enriched categoricals | Absent (replaced by DeviceAtlas enrichment at serving) |
| **SDK event name** | Passthrough string + `sdk_event_name_mapping_passthrough` | `prob_sdk_event_name` EmbeddingBag (hash_size=1M, list_len=10) |
| **Embedding dim** | 2× multiplier over vocabulary size | Fixed 32-dim for all sparse |
| **Embedding init** | uniform | uniform |
| **Activation** | ELU | SELU |
| **Batch norm** | Yes | No (SELU is self-normalizing) |
| **Dropout** | Input 0.05 + per-layer 0.4/0.2/0.1 | None (dropout_rate=0.0) |
| **Gradient clipping** | None listed | max_norm=1.0 |
| **Batch size** | 20,000 | 25,600 |
| **Learning rate** | 0.003 (single) | 0.001 main / 0.0008 embedding |
| **Optimizer** | Not specified (SGD-based) | AdamW (separate for embeddings) |
| **LR schedule** | Constant (with early stopping) | OneCycleLR (3-phase) |
| **Training control** | Max 50 iterations + early stopping | Max 5 epochs, no early stopping |
| **Compute** | 1 GPU | 8 GPU DDP |

---

## 4. Key Gaps in v1_lc vs Legacy

| Missing Feature | Legacy Source | Priority |
|----------------|--------------|----------|
| **UUPS IAP/adrev signals** | 20 features from UUPS pipeline | High — strong purchase intent signal |
| **IBT embeddings** | adreq IBT (128-dim) + install IBT (80-dim) | High — cross-game behavioral signal |
| **Hardware stats** | device_type enrichment (cpu, gpu, ram, dpi, res) | Medium |
| **gamer_creation_delay** | Computed from timestamps, disabled in legacy | Already enabled in v1_lc |
| **target_game_click_count_in_last_7_days** | agc_features | Already in v1_lc AGC set |

The v1_lc model covers all scalar and categorical features from the legacy model.
The main capability gaps are UUPS and IBT embeddings, which are tracked as Phase 2/3 additions.

---

## 5. SDK Event Name Label — Architecture Decision

### Legacy approach (ads-audience-pinpointer, TensorFlow)

The legacy model used a custom `SDKEventNamePreprocessor` that kept one row per install
and treated `prob_sdk_event_name_labels` as a **parallel float array** alongside
`prob_sdk_event_name_array` (the token array). The TF training loop computed a
**per-element BCE loss** across all events in the array using `SparseTensor`/`RaggedTensor`
operations, then averaged across the bag.

```
Install row:
  prob_sdk_event_name_array  = ["500043219_solved_puzzles_10", "500043219_*"]
  prob_sdk_event_name_labels = [0.0, 1.0]
  → TF loss computed per element, then averaged
```

### UL v1_lc approach (PyTorch + DLRM)

Two options were evaluated:

| | Option 1: Expand dataset | Option 2: Per-element array loss |
|--|---|---|
| **Data format** | One row per (install × targeted_event) | One row per install, array labels |
| **Label format** | Scalar float per row | `array<float>` per row |
| **Infra changes** | None — BatchCreator native | BatchCreator + DLRM + loss refactor |
| **Architecture fit** | Perfect (list_len=1 scalar sparse feature) | Requires EmbeddingBag → attention |
| **Data size** | ~2–5× (typical: 1–5 events per game) | 1× |
| **Train/val correctness** | ✓ (bucket is install-based) | ✓ |
| **Risk** | Low | High |

**Decision: Option 1 (expand dataset)**

The UL `BatchCreator.labels()` calls `torch.tensor(inputs[label], dtype=float32)` which
requires a scalar float per row. The `DLRM` architecture uses `EmbeddingBag(agg_mode="mean")`
which collapses the event array to a single vector — making per-element predictions would
require replacing EmbeddingBag with per-embedding attention and redesigning the task head.

Option 1 fits the existing UL infrastructure with zero changes:

```
Spark datagen explodes by sdk_event_targeted:
  Install A × [event_X, event_Y, *] →
    Row 1: prob_sdk_event_name="500043219_event_X", prob_sdk_event_name_label=0.0, label=1.0
    Row 2: prob_sdk_event_name="500043219_event_Y", prob_sdk_event_name_label=1.0, label=1.0
    Row 3: prob_sdk_event_name="500043219_*",       prob_sdk_event_name_label=1.0, label=1.0
```

The `bucket` column is hashed from `auctionId` (install-level), so all expanded rows
from the same install land in the same train/val partition — no leakage.

### Impact on feature and model config

| Parameter | Before (array, list_len=10) | After (scalar, list_len=1) |
|--|--|--|
| `prob_sdk_event_name` list_len | 10 | 1 |
| `prob_sdk_event_name_label` | `array<float>` (broken) | `float` scalar ✓ |
| num_embs | 21 | 21 (unchanged — still 1 embedding slot) |
| shared_bottom_mlp[0] | 232 | 232 (unchanged) |
| Rows per install | 1 | ~1–5 (depends on targeted events) |
