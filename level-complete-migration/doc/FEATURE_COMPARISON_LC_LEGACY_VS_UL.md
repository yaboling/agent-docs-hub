# Level Complete Model Feature Comparison: Legacy BHV / CTX vs New UL v11_cpe_lc

**Generated:** 2026-06-11
**Sources:**
- Legacy BHV: `ads-audience-pinpointer/cpi-model/configs/prd/features_level_complete_bhv.yaml`
- Legacy CTX: `ads-audience-pinpointer/cpi-model/configs/prd/features_level_complete_ctx.yaml`
- New UL LC: `ads-unified-learner/src/unity_learner/experiment_repo/unified_user_value/v11_cpe_lc/features.py`

---

## 1. Architecture Overview

| Dimension | Legacy BHV | Legacy CTX | New UL v11_cpe_lc |
|---|---|---|---|
| **Model type** | YAML-driven flat network | YAML-driven flat network | DLRM (dense tower + sparse embeddings) |
| **Feature definition format** | YAML | YAML | Python `FeatureSet` / `ModelFeatures` |
| **Total active features** | ~67 | ~70 | ~34 defined in file + `dense_agc_features` (15) + `cpe_online_only_features` |
| **Dense feature count** | Multiple scalars flat | Multiple scalars flat | 16 (1 LC-specific + 15 AGC) |
| **Sparse embedding count** | N/A (flat lookup) | N/A (flat lookup) | 18 `individual_sparse_features` |
| **Online/offline split** | `is_serving_feature` / `load_to_network` flags | Same | `FeatureSetType.ONLINE_AND_OFFLINE` / `OFFLINE_ONLY` |
| **Label** | `label` (binary) | `label` (binary) | `label` (binary) + `prob_sdk_event_name_label` (per-event) |

---

## 2. Full Feature Lists

### 2.1 Legacy BHV — Active Features

All features unless marked `disabled: true`.

#### 2.1.1 Gamer Counters

| Feature | Type | Preprocessor | Clip |
|---|---|---|---|
| `gamer_click_count` | scalar | `ScalarPreprocessor` / log1p_normalize | 1,000 |
| `gamer_install_count` | scalar | `ScalarPreprocessor` / log1p_normalize | 100 |
| `gamer_start_count` | scalar | `ScalarPreprocessor` / log1p_normalize | 6,000 |
| `gamer_view_count` | scalar | `ScalarPreprocessor` / log1p_normalize | 6,000 |
| `gamer_start_count_in_last_24_hours` | scalar | `ScalarPreprocessor` / log1p_normalize | 100 |
| `gamer_start_count_in_last_7_days` | scalar | `ScalarPreprocessor` / log1p_normalize | 400 |

#### 2.1.2 Context / Identity

| Feature | Type | Preprocessor | Campaign Feature |
|---|---|---|---|
| `audience_id` | categorical | `CategoricalPreprocessor` | Yes |
| `device_connection_type` | categorical | `CategoricalPreprocessor` | No |
| `device_type` | categorical | `CategoricalPreprocessor` | No |
| `geolocation_country` | categorical | `CategoricalPreprocessor` | No |
| `platform` | categorical | `CategoricalPreprocessor` | No |
| `publisher_is_coppa_targeted` | raw-int | None | No |
| `publisher_developer_id` | categorical | `CategoricalPreprocessor` | No |
| `publisher_game_id` | categorical | `CategoricalPreprocessor` | No |
| `publisher_store_id` | categorical | `CategoricalPreprocessor` | No |

#### 2.1.3 Target Game Features

| Feature | Type | Preprocessor | Campaign Feature |
|---|---|---|---|
| `target_game_id` | categorical | `CategoricalPreprocessor` | Yes |
| `target_store_id` | categorical | `CategoricalPreprocessor` | Yes |
| `target_game_click_count_in_last_24_hours` | scalar | `ScalarPreprocessor` / normalize | Yes |
| `target_game_start_count` | scalar | `ScalarPreprocessor` / normalize | Yes |
| `target_game_start_count_in_last_24_hours` | scalar | `ScalarPreprocessor` / normalize | Yes |
| `target_game_start_count_in_last_7_days` | scalar | `ScalarPreprocessor` / normalize | Yes |
| `target_game_view_count` | scalar | `ScalarPreprocessor` / normalize | Yes |
| `target_game_view_count_in_last_24_hours` | scalar | `ScalarPreprocessor` / normalize | Yes |
| `target_game_view_count_in_last_7_days` | scalar | `ScalarPreprocessor` / normalize | Yes |

#### 2.1.4 Hardware Stats (enriched, keyed by `device_type`)

| Feature | Type | Preprocessor | Clip |
|---|---|---|---|
| `hardware_stats_cpu_count` | enriched-scalar | `EnrichedScalarPreprocessor` / normalize | 16 |
| `hardware_stats_ram` | enriched-scalar | `EnrichedScalarPreprocessor` / normalize | 16,384 |
| `hardware_stats_dpi` | enriched-scalar | `EnrichedScalarPreprocessor` / normalize | 640 |
| `hardware_stats_cpu` | enriched-categorical | `EnrichedCategoricalPreprocessor` | — |
| `hardware_stats_gpu` | enriched-categorical | `EnrichedCategoricalPreprocessor` | — |
| `hardware_stats_res` | enriched-categorical | `EnrichedCategoricalPreprocessor` | — |

#### 2.1.5 UUPS IAP Features (attributed / unattributed / uasdk, d7 and d30)

| Feature | Type | Clip |
|---|---|---|
| `uups_attributed_iap_done_d7` | categorical | — |
| `uups_attributed_iap_nonzero_log_avg_value_d7` | scalar (normalize) | 18.4 |
| `uups_attributed_iap_total_count_d7` | scalar (normalize) | 1,000 |
| `uups_attributed_unique_games_with_iaps_count_d7` | scalar (normalize) | 25 |
| `uups_attributed_iap_done_d30` | categorical | — |
| `uups_attributed_iap_nonzero_log_avg_value_d30` | scalar (normalize) | 18.4 |
| `uups_attributed_iap_total_count_d30` | scalar (normalize) | 1,000 |
| `uups_attributed_unique_games_with_iaps_count_d30` | scalar (normalize) | 25 |
| `uups_unattributed_iap_done_d7` | categorical | — |
| `uups_unattributed_iap_nonzero_log_avg_value_d7` | scalar (normalize) | 18.4 |
| `uups_unattributed_iap_total_count_d7` | scalar (normalize) | 1,000 |
| `uups_unattributed_unique_games_with_iaps_count_d7` | scalar (normalize) | 25 |
| `uups_unattributed_iap_done_d30` | categorical | — |
| `uups_unattributed_iap_nonzero_log_avg_value_d30` | scalar (normalize) | 18.4 |
| `uups_unattributed_iap_total_count_d30` | scalar (normalize) | 1,000 |
| `uups_unattributed_unique_games_with_iaps_count_d30` | scalar (normalize) | 25 |
| `uups_uasdk_iap_done_d7` | categorical | — |
| `uups_uasdk_iap_nonzero_log_avg_value_d7` | scalar (normalize) | 18.4 |
| `uups_uasdk_iap_total_count_d7` | scalar (normalize) | 1,000 |
| `uups_uasdk_unique_games_with_iaps_count_d7` | scalar (normalize) | 25 |
| `uups_uasdk_iap_done_d30` | categorical | — |
| `uups_uasdk_iap_nonzero_log_avg_value_d30` | scalar (normalize) | 18.4 |
| `uups_uasdk_iap_total_count_d30` | scalar (normalize) | 1,000 |
| `uups_uasdk_unique_games_with_iaps_count_d30` | scalar (normalize) | 25 |

#### 2.1.6 UUPS Ad Revenue Features

| Feature | Type |
|---|---|
| `uups_adrev_oecpm_rewarded_total_count_d7` | scalar (normalize) |
| `uups_adrev_oecpm_rewarded_total_sum_d7` | scalar (normalize) |
| `uups_adrev_oecpm_rewarded_total_count_d30` | scalar (normalize) |
| `uups_adrev_oecpm_rewarded_total_sum_d30` | scalar (normalize) |
| `uups_adrev_oecpm_interstitial_total_count_d7` | scalar (normalize) |
| `uups_adrev_oecpm_interstitial_total_sum_d7` | scalar (normalize) |
| `uups_adrev_oecpm_interstitial_total_count_d30` | scalar (normalize) |
| `uups_adrev_oecpm_interstitial_total_sum_d30` | scalar (normalize) |

#### 2.1.7 IBT / Install Behavior Tree

| Feature | Type | Details |
|---|---|---|
| `ad_req_project_id` | ibt (string) | `load_to_network: false` |
| `ad_req_counts` | ibt (int) | `load_to_network: false` |
| `ibt_embedding` | tf_embedding | size = 128 |
| `installed_store_ids` | ibt (string) | `load_to_network: false` |
| `installed_store_ids_latest_start_ts` | ibt (int) | `load_to_network: false` |
| `install_ibt_embedding` | tf_embedding | size = 80 |

#### 2.1.8 Campaign / Event

| Feature | Type | Notes |
|---|---|---|
| `tgtg_sdk_set` | categorical (`SdkSetPreprocessor`) | campaign feature, not serving |
| `sdk_event_name` | categorical (None) | campaign + serving; `load_to_network: false` |
| `prob_sdk_event_name_array` | sdk_event_name (string) | train only |
| `prob_sdk_event_name_labels` | sdk_event_name (float) | train only |

#### 2.1.9 Disabled Features in BHV

| Feature | Reason |
|---|---|
| `gamer_creation_delay` | `disabled: true` |
| `ad_request_timestamp` | `disabled: true` |
| `gamer_creation_timestamp` | `disabled: true` |

---

### 2.2 Legacy CTX — Active Features

CTX shares most BHV features. Differences are highlighted below.

#### 2.2.1 CTX-Only Features (not present in BHV)

| Feature | Type | Notes |
|---|---|---|
| `gamer_profile_meta` | array[2] (string) | `load_to_network: false` |
| `installed_store_ids_channel` | array (string) | `load_to_network: false`, variable length |
| `counters_source` | categorical | `CountersSourcePreprocessor`; used for imputation logic |
| `gamer_creation_delay` | scalar | **Enabled** (disabled in BHV); `GamerAgePreprocessor` / normalize |
| `ad_request_timestamp` | raw-int | **Enabled** (disabled in BHV); `load_to_network: false` |
| `gamer_creation_timestamp` | raw-int | **Enabled** (disabled in BHV); `load_to_network: false` |
| `gamer_limited_tracking` | raw-int | `load_to_network: false` |
| `limited` | int_embedding | base: `gamer_limited_tracking`; `IntEmbeddingPreprocessor` |
| `gamer_has_opted_out` | raw-int | `load_to_network: false` |
| `opt_out_enabled` | int_embedding | base: `gamer_has_opted_out`; `IntEmbeddingPreprocessor` |
| `coppa` | int_embedding | base: `publisher_is_coppa_targeted`; `IntEmbeddingPreprocessor` |

#### 2.2.2 Gamer Counters with Conditional Imputation

CTX adds `impute_if: {counters_source: "null"}` to all six gamer counter features:

- `gamer_click_count`
- `gamer_install_count`
- `gamer_view_count`
- `gamer_start_count`
- `gamer_start_count_in_last_24_hours`
- `gamer_start_count_in_last_7_days`

Otherwise identical to BHV (same type, preprocessor, clips).

#### 2.2.3 Apptopia Store Info (CTX-only, absent from BHV)

| Feature | Type | Base Feature | Campaign Feature |
|---|---|---|---|
| `apptopia_storeinfo_source_category` | enriched-categorical | `publisher_store_id` | No |
| `apptopia_storeinfo_source_subcategory` | enriched-categorical | `publisher_store_id` | No |
| `apptopia_storeinfo_source_iap` | enriched-categorical | `publisher_store_id` | No |
| `apptopia_storeinfo_source_price` | enriched-scalar (normalize) | `publisher_store_id` | No, clip=1,000 |
| `apptopia_storeinfo_source_size` | enriched-scalar (normalize) | `publisher_store_id` | No, clip=1,000,000,000 |
| `apptopia_storeinfo_source_rating` | enriched-scalar (normalize) | `publisher_store_id` | No, clip=5.0 |
| `apptopia_storeinfo_target_category` | enriched-categorical | `target_store_id` | Yes |
| `apptopia_storeinfo_target_subcategory` | enriched-categorical | `target_store_id` | Yes |
| `apptopia_storeinfo_target_iap` | enriched-categorical | `target_store_id` | Yes |
| `apptopia_storeinfo_target_price` | enriched-scalar (normalize) | `target_store_id` | Yes, clip=1,000 |
| `apptopia_storeinfo_target_size` | enriched-scalar (normalize) | `target_store_id` | Yes, clip=1,000,000,000 |
| `apptopia_storeinfo_target_rating` | enriched-scalar (normalize) | `target_store_id` | Yes, clip=5.0 |

#### 2.2.4 Features in BHV but ABSENT from CTX

| Feature Group | Features |
|---|---|
| Target game scalars | `target_game_click_count_in_last_24_hours`, `target_game_start_count`, `target_game_start_count_in_last_24_hours`, `target_game_start_count_in_last_7_days`, `target_game_view_count`, `target_game_view_count_in_last_24_hours`, `target_game_view_count_in_last_7_days` |
| UUPS IAP (all 24) | All `uups_attributed_*`, `uups_unattributed_*`, `uups_uasdk_*` features |
| UUPS Ad Revenue (all 8) | All `uups_adrev_oecpm_*` features |

#### 2.2.5 Disabled Features in CTX (unique to CTX)

| Feature |
|---|
| `gamer_session_counters_adrequests` |
| `gamer_session_counters_performance_starts_count` |
| `gamer_session_counters_performance_views_count` |
| `gamer_session_counters_brand_views_count` |
| `gamer_session_counters_brand_starts_count` |

---

### 2.3 New UL v11_cpe_lc — Features

Defined in `features.py` using the `FeatureSet` / `ModelFeatures` SDK.

#### 2.3.1 Labels (`FeatureSetType.OFFLINE_ONLY`)

| Feature | Label Name | Mapping |
|---|---|---|
| `label` | `label` | identity (binary app_event_w1) |
| `prob_sdk_event_name_label` | `prob_sdk_event_name_label` | identity (per-event SDK label) |

#### 2.3.2 Offline-Only Features (`FeatureSetType.OFFLINE_ONLY`)

| Feature | Type | Hash Size | Notes |
|---|---|---|---|
| `bucket` | utility | — | train/val split column |
| `prob_sdk_event_name` | sparse (`oecpm_features`) | 1,000,000 | list_len=1, agg=mean; Go serving does not populate |
| `model_name` | sparse (`oecpm_features`) | 1,000 | list_len=1, agg=mean; Go serving does not populate |

#### 2.3.3 Dense LC Features (`FeatureSetType.ONLINE_AND_OFFLINE`)

`dense_lc_features` — 1 feature:

| Feature | Source | Transform | soft_clip_cap |
|---|---|---|---|
| `gamer_creation_delay` | `oecpm_features` | log1p | 1.5 × 10^8 |

#### 2.3.4 Dense AGC Features (`dense_agc_features`)

15 features imported from `unity_learner.data.preprocessor_v2.user_value.agc_featureset`.
These are shared AGC (Audience Growth Campaign) dense features (content defined in that module).
Combined with `dense_lc_features` → **16 total dense inputs** → `dense_tower_mlp[0] = 16`.

#### 2.3.5 Sparse Features — `individual_sparse_features` (`FeatureSetType.ONLINE_AND_OFFLINE`)

18 features; all `list_len=1`, `agg_mode="mean"`, `repeat=1`:

| Feature | Source Module | Hash Size |
|---|---|---|
| `ad_format` | `oecpm_features` | 11 |
| `geolocation_country` | `oecpm_features` | 350 |
| `platform` | `oecpm_features` | 10 |
| `gamer_id_scope` | `oecpm_features` | 12 |
| `video_orientation` | `oecpm_features` | 10 |
| `device_connection_type` | `device_features` | 11 |
| `device_type` | `device_features` | 60,000 |
| `device_orientation` | `device_features` | 11 |
| `audience_id` | `oecpm_features` | 35,000 |
| `publisher_store_id` | `oecpm_features` | 87,000 |
| `publisher_developer_id` | `oecpm_features` | 70,000 |
| `publisher_game_id` | `oecpm_features` | 46,000 |
| `target_store_id` | `oecpm_features` | 87,000 |
| `target_game_id` | `oecpm_features` | 46,000 |
| `creative_id` | `oecpm_features` | 1,000,000 |
| `creative_pack_id` | `oecpm_features` | 651,011 |
| `ad_type` | `oecpm_features` | 110 |
| `sdk_event_name` | `oecpm_features` | 10,000 |

#### 2.3.6 Online-Only Features

From `cpe_online_only_features` (imported from `unity_learner.data.preprocessor_v2.user_value.cpe_online_only_featureset`).
Content defined in that module — not inlined in `features.py`.

#### 2.3.7 DLRM Dimension Math

```
num_embs = 18 (all repeat=1)
         + dense_embedding_dim // sparse_embedding_dim  (64 // 32 = 2)
         = 20

shared_bottom_mlp[0] = 20 × dot_product_compress_dim (16) + dense_tower_mlp[-1] (128)
                     = 320 + 128
                     = 448
```

---

## 3. Cross-Model Feature Comparison

### 3.1 Feature Coverage Matrix

| Feature / Feature Group | Legacy BHV | Legacy CTX | New UL v11_cpe_lc |
|---|:---:|:---:|:---:|
| **Gamer counters** (click/install/start/view) | Yes | Yes (+ imputation) | Via `dense_agc_features` |
| **gamer_creation_delay** | Disabled | Yes | Yes (log1p dense) |
| **Target game scalars** (7 features) | Yes | No | No |
| **UUPS IAP features** (24 features) | Yes | No | No |
| **UUPS adrev features** (8 features) | Yes | No | No |
| **Hardware stats** (6 features) | Yes | Yes | No |
| **Apptopia store info** (12 features) | No | Yes | Pending (datagen join needed) |
| **IBT embeddings** (ibt + tf_embedding) | Yes | Yes | Via `dense_agc_features` |
| **audience_id** | Yes | Yes | Yes |
| **geolocation_country** | Yes | Yes | Yes |
| **platform** | Yes | Yes | Yes |
| **device_type** | Yes | Yes | Yes |
| **device_connection_type** | Yes | Yes | Yes |
| **publisher_store/developer/game_id** | Yes | Yes | Yes |
| **target_store_id / target_game_id** | Yes | Yes | Yes |
| **sdk_event_name** | Yes | Yes | Yes (hash=10,000) |
| **prob_sdk_event_name** | Train only | Train only | Offline-only (hash=1M) |
| **tgtg_sdk_set** | Yes | Yes | No |
| **installed_store_ids** | Yes | Yes | Via `dense_agc_features` |
| **publisher_is_coppa_targeted** | Yes (raw) | Yes (raw + int_embedding) | No |
| **Privacy signals** (limited_tracking, opted_out) | No | Yes | No |
| **gamer_profile_meta** | No | Yes | No |
| **installed_store_ids_channel** | No | Yes | No |
| **counters_source** | No | Yes (imputation control) | No |
| **Ad creative signals** (creative_id, creative_pack_id) | No | No | Yes |
| **Ad format/type/orientation** | No | No | Yes (ad_format, ad_type, video_orientation, device_orientation) |
| **gamer_id_scope** | No | No | Yes |
| **model_name** | No | No | Offline-only |

### 3.2 Features Dropped Going from Legacy to UL

| Feature | Present in | Reason / Notes |
|---|---|---|
| All UUPS IAP features (24) | BHV only | Not available in CPE datagen; would require datagen enrichment |
| All UUPS adrev features (8) | BHV only | Same |
| Target game scalar features (7) | BHV only | Not in CPE datagen output |
| Hardware stats (6) | BHV + CTX | Not included in UL feature set |
| Apptopia features (12) | CTX only | Datagen join not yet implemented in `unified_cpe_datagen.py` |
| `tgtg_sdk_set` | BHV + CTX | Not in UL feature set |
| `publisher_is_coppa_targeted` | BHV + CTX (raw) | Not included; `coppa` int_embedding CTX-only |
| Privacy signals (limited, opted_out) | CTX only | Not included |
| `gamer_profile_meta` | CTX only | Not included |
| `installed_store_ids_channel` | CTX only | Not included |

### 3.3 Features Added in UL (new, not in any legacy model)

| Feature | Notes |
|---|---|
| `ad_format` | Ad creative format signal |
| `ad_type` | Ad type categorization |
| `video_orientation` | Creative orientation signal |
| `device_orientation` | Device orientation at request time |
| `creative_id` | Per-creative embedding (hash=1M) |
| `creative_pack_id` | Per-creative-pack embedding (hash=651,011) |
| `gamer_id_scope` | Scope of gamer identifier |
| `model_name` | Offline-only training signal |
| `prob_sdk_event_name_label` | Per-event SDK label (multi-task training) |

---

## 4. Key Architectural Differences

### 4.1 Feature Representation

| Aspect | Legacy (BHV/CTX) | New UL v11_cpe_lc |
|---|---|---|
| Categorical encoding | Preprocessor looks up embedding tables per feature | Sparse `FeatureSet` with explicit `hash_size`; DLRM dot-product attention |
| Scalar encoding | `normalize` or `log1p_normalize` with clip | Dense tower MLP; `gamer_creation_delay` uses `log1p` in-model transform |
| Enriched features | `EnrichedScalarPreprocessor` / `EnrichedCategoricalPreprocessor` | Not used; enriched lookups done upstream in datagen |
| IBT / install history | Separate `ibt` type → `TFEmbeddingPreprocessor` generates tf_embedding | Handled inside `dense_agc_features` |

### 4.2 Label Design

| | Legacy BHV/CTX | New UL v11_cpe_lc |
|---|---|---|
| Primary label | `label` (binary) | `label` (binary, app_event_w1) |
| Secondary label | None | `prob_sdk_event_name_label` (per-event, multi-task) |
| Datagen explode | Not applicable | One row per (install × targeted_sdk_event) |

### 4.3 Campaign Feature Handling

Legacy models annotate features with `is_campaign_feature: true/false`. The UL model uses `FeatureSetType` and the `individual_sparse_features` name (hardcoded in `dlrm.py:45`) to separate campaign-side vs gamer-side signals.

### 4.4 Apptopia — Pending Work

Apptopia features were introduced in CTX and carry target/source store metadata (category, subcategory, IAP type, price, size, rating). The UL `v11_cpe_lc/features.py` includes a Phase 2 note:

> Apptopia features require the CPE datagen to pre-join Apptopia data into the parquet output before they can be added here. The `v8_mmp_v2a` experiment's UV datagen already does this join; the CPE datagen (`unified_cpe_datagen.py`) does not. Until that join is added, Apptopia features are unavailable.

---

## 5. Summary

The migration from Legacy BHV/CTX to UL v11_cpe_lc involves:

1. **Architectural upgrade**: Flat network → DLRM with sparse embeddings and dense tower.
2. **Feature consolidation**: 67–70 legacy features reduced to ~34 explicitly defined (plus shared AGC dense features), with richer sparse hash sizes.
3. **Significant feature drops**: UUPS IAP/adrev (32 features), target game scalars (7), hardware stats (6), Apptopia (12 — CTX only), and privacy signals are not present in the UL model.
4. **New ad creative signals**: `creative_id`, `creative_pack_id`, `ad_format`, `ad_type`, `video_orientation`, `device_orientation` are new in UL.
5. **Multi-task label**: UL adds a per-event `prob_sdk_event_name_label` alongside the binary `label`.
6. **`gamer_creation_delay` restored**: Was disabled in BHV, enabled in CTX — now a first-class dense feature in UL with a `log1p` transform.
7. **Apptopia pending**: Requires datagen-side join in `unified_cpe_datagen.py` before it can be added to the UL feature set.
