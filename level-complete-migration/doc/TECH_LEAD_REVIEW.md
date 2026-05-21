# unified_cpe.v1_lc — Tech Lead Review

**Experiment:** `unified_cpe.v1_lc`
**Task:** P(user fires the campaign-targeted SDK event within 7 days of install). Migrated from `ads-audience-pinpointer`.
**Framework:** PyTorch / ads-unified-learner (DLRM + DeepCrossNet, single-task)

---

## 1. Data Pipeline — Input

### 1.1 Data Source

| Property | Value |
|---|---|
| Source path | `gs://unity-ads-dd-ds-prd-data-anon/app-events/.../v2/level_complete/d7/` |
| Partition key | `installDate=YYYY-MM-DD` |
| Training window | 60 days |
| Overall delay | 10 days (7-day label window + 2-day ETL buffer + 1-day lag) |
| Preprocessed output | `gs://unity-ads-dd-ds-prd-incremental-training-data/cpe/unified_cpe.v1_lc/preprocessed_combined/` |

Data is read by a Spark datagen job, preprocessed into a single combined parquet partition (`date={train_end_date}`), then consumed directly by the training pod.

---

### 1.2 Labels

| Column | Type | Definition | Used for |
|---|---|---|---|
| `prob_sdk_event_name_label` | float {0, 1} | **PSN label (main task).** 1 if the user fired the campaign-targeted SDK event AND completed a level within 7d, else 0. | Training target + bidding |
| `label` | float {0, 1} | **Level complete label.** `app_event_w1 > 0` → 1, else 0. | Present in parquet but **not used** in training (LC task removed) |

Both are `OFFLINE_ONLY` — not sent to the serving model at inference time.

**How `prob_sdk_event_name_label` is constructed (datagen Stages 1–4):**

```
Stage 1: Query BigQuery campaign_audiences + campaign_pricing
         → for each target_game_id, which sdk_event is being optimized?
         → Rule: 0 or >1 events in campaign → wildcard "*"; exactly 1 → that event name.

Stage 2: Join installs with campaign targets (left outer).
         Games with no active level_complete campaign → default wildcard "*".

Stage 3: Per install, per targeted sdk_event:
         prob_sdk_event_name_label = 1.0 if (
             user fired that event  OR  event == "*"  OR  event == ""
         ) AND label == 1
         else 0.0

Stage 4: Explode — one row per (install × targeted_sdk_event).
         prob_sdk_event_name = "{target_game_id}_{event_name}"  (e.g. "500043219_onlinetime_60m")
         prob_sdk_event_name_label = scalar float {0.0, 1.0}
```

---

### 1.3 Eligibility Filter (Game-Level Quality Gate)

Applied **before** the BQ campaign join and SDK event explode to minimize compute.

```python
_MIN_EVENT_GAMERS = 50

# Keep only games with ≥50 installs having cum_app_event_count_d7 > 0
eligible_game_ids = (
    df.filter(col("cum_app_event_count_d7") > 0)
      .groupBy("targetGameId")
      .agg(count("*").alias("_event_gamers"))
      .filter(col("_event_gamers") >= 50)
      .select("targetGameId")
      .collect()
)
df = df.filter(col("targetGameId").isin(eligible_game_ids))
```

**Parity with legacy ads-audience-pinpointer:**
- `filter_no_send_targets` (removes games with `SUM(cum_app_event_count_d7) == 0`) — subsumed by the ≥50 threshold.
- `get_event_target_games_list(min_event_gamers=50)` — exact match: `COUNT(cum_app_event_count_d7 > 0) >= 50`.

---

### 1.4 Train / Validation Split

**Method:** Random bucket split based on a deterministic hash of `auctionId`, matching legacy `trainDataFraction=0.9`.

```
bucket = abs(hash(auctionId)) % 100 / 100.0   # float in [0.0, 1.0), install-level

train : bucket < 0.9   (~90% of installs)
val   : bucket >= 0.9  (~10% of installs)
```

The bucket is install-level — after the SDK event explode, all rows from the same install always land in the same partition.

---

### 1.5 Input Features

**Dense features (16 total):**

| Group | Features | Count |
|---|---|---|
| LC-specific | `gamer_creation_delay` (log1p, soft_clip=1.5e8) | 1 |
| AGC (Ads Gamer Counters) | gamer_start/view/click/install counts, 1d/7d windows, target_game start/view/click counts, 9 session counters | 15 |
| **Total** | | **16** |

**Sparse features (19 total), all `list_len=1`, `agg_mode=mean`, `sparse_embedding_dim=32`:**

| Feature | Hash size |
|---|---|
| ad_format | 11 |
| geolocation_country | 350 |
| platform | 10 |
| gamer_id_scope | 12 |
| video_orientation | 10 |
| device_connection_type | 11 |
| device_type | 60,000 |
| device_orientation | 11 |
| audience_id | 35,000 |
| publisher_store_id | 87,000 |
| publisher_developer_id | 70,000 |
| publisher_game_id | 46,000 |
| target_store_id | 87,000 |
| target_game_id | 46,000 |
| creative_id | 1,000,000 |
| creative_pack_id | 651,011 |
| ad_type | 110 |
| model_name | 1,000 |
| **prob_sdk_event_name** | **1,000,000** |

`prob_sdk_event_name` token format: `"{target_game_id}_{event_name}"`. Hash size 1M covers ~46k games × many events + wildcards.

---

## 2. Model Architecture

### 2.1 Overview

**Single-task** DLRM + DeepCrossNet. One task head (PSN), one BCE loss. The `level_complete` auxiliary task has been removed from `config.json`.

---

### 2.2 Architecture Diagram

```
[19 sparse features]                 [16 dense features]
        │                                    │
 EmbeddingBag (dim=32 each)        dense_tower_mlp [16 → 64]
 → 19 embeddings [19×32=608]                │
        │                          dense_emb_proj [64 → 512 → 64]
        │                                    │
        │                        split into 2 chunks of 32-dim
        └──────────────────┬──────────────────┘
                   [21 embeddings × 32-dim]
                            │
                      DotProductPlus
                  (attention net + residual net)
                  compress: 21×32 → 21×8 = 168
                            │
              ┌─────────────┴────────────┐
         cross_dense_sparse [168]    dense_repr [64]
              └─────────────┬────────────┘
                         cat [232]
                            │
                  DeepCrossNet (2 layers, rank=128)
                            │
                  mlp_projection [232 → 256 → 128]
                            │
                        PSN head
                    SingleTaskModule
                    hidden [128 → 256]
                            │
                  cat(256, cds=168) → [424]
                  poly: cat(x, x²)  → [848]
                  final_layer [848 → 1]
                          sigmoid
                            │
                      nn_output[:,0]
                         (serving)
```

**Dimension derivation:**
```
num_embs = 19 sparse (repeat=1) + 64 // 32 (dense_emb split) = 21
cross_dense_sparse   = 21 × compress_dim(8) = 168
dense_repr           = dense_tower_mlp[-1] = 64
shared_bottom input  = 168 + 64 = 232  ✓

task hidden output   = mlp_layers[-2] = 256
cat(256, cds=168)    = 424  →  poly cat(x, x²) = 848
task_final_layer_size = 2 × (168 + 256) = 848  ✓
```

---

### 2.3 Loss Function

**Homoscedastic uncertainty weighting** (Kendall & Gal, 2018) for a single task. A learned log-variance scalar `s_psn` scales the BCE loss:

```
L_total = BCE(psn_pred, psn_label) × exp(−s_psn) + s_psn

s_psn ∈ ℝ  — learned parameter (randomly initialized)
```

At equilibrium `s_psn → ln(BCE)`, which is **negative** when BCE < 1 (typical). A negative combined loss is mathematically correct — not a bug.

---

### 2.4 Training Configuration

| Parameter | Value |
|---|---|
| Devices | 8× RTX PRO 6000 (DDP) |
| Batch size | 25,600 per GPU → 204,800 effective |
| Max epochs | 5 |
| Dropout (PSN head) | 0.2 |
| Optimizer | AdamW (lr=0.001, weight_decay=0.05) |
| LR scheduler | LRPolicyScheduler (warmup 30% / steady / decay 30%) |
| `total_step` | Computed at runtime: BQ `COUNT(*) WHERE bucket < 0.9` |
| Gradient clip | max_norm = 1.0 |
| Train nodepool | `8xg4` |
| Train timeout | 18 hours |

---

## 3. Output — Prediction and Bidding Logic

### 3.1 Model Output Shape

```
self.model(inputs)  →  [batch, 4]

  col 0 — PSN prediction (mean)   ← used for bidding
  col 1 — PSN prediction (copy)
  col 2 — PSN prediction (copy)
  col 3 — PSN prediction (copy)
```

The base DLRM `get_flattened_output` repeats the single sigmoid output 4× for legacy serving compatibility. No Thompson sampling or calibration head is active.

---

### 3.2 Bidding Logic (`DeployModel.forward`)

```python
psn_pred = nn_output[:, 0].view(-1)        # P(user fires targeted SDK event within 7d)

p    = clamp(psn_pred, 0.0, 1.0)          # NaN/Inf replaced with 0 before clamp
cost = clamp(max_cost × p × discount_factor, 0.0, 1e18)

return p, cost                              # cost in microdollars
```

**Required runtime inputs:**
- `max_cost` — advertiser bid cap in microdollars
- `discount_factor` — BBB discount factor

---

## 4. Risks and Open Issues

### 4.1 [HIGH] PSN Label Rate Doubles After Eligibility Filter (7.5% → ~15%)

The eligibility filter selects only high-converting games, causing survivorship bias:

| Dataset | PSN positive rate |
|---|---|
| All games (raw, pre-filter) | ~7.5% |
| Eligible games only (post-filter) | ~15% |

At serving time, **all games are scored** including low-converting ones excluded from training. The model was trained on a ~15% positive rate but will be deployed into a ~7.5% environment, biasing bids upward.

**This matches legacy model behavior** (same filter applied). Online calibration should be monitored closely after launch.

---

### 4.2 [HIGH] Legacy Hybrid Model (LC × PSN blend) Not Implemented

The legacy `ads-audience-pinpointer` model used a hybrid bidding formula that blended the raw level-complete probability with the PSN prediction. The current model bids on PSN probability only.

Whether this is acceptable depends on campaign configuration: games using wildcard `"*"` targeting will have PSN ≈ LC (no loss). Games with specific SDK event targets may diverge.

---

### 4.3 [MEDIUM] Temporal Train/Validation Split Breaks — Must Use Random Bucket Split

A temporal split (older data → train, recent → val) cannot be used with the eligibility filter:

1. The eligibility filter selects historically high-converting games.
2. Older training rows capture their peak conversion rates.
3. Recent validation rows of the same games show naturally lower, declining rates.

**Observed effect:** temporal split gives train PSN label rate ~40%, val PSN label rate ~30% — a 10-point gap causing misleading val metrics and overfitting.

**Fix applied:** random bucket split (`bucket < 0.9`) equalises both splits at ~40% PSN positive rate. Val metrics are now valid, but the val set covers the same date range as train. A held-out time-based eval should be run separately for any production go/no-go decision.

---

### 4.4 [MEDIUM] Migration from `unified_cpe/` to `unified_user_value/` Will Delay Launch

The experiment lives in `src/unity_learner/experiment_repo/unified_cpe/v1_lc/`. The correct long-term home is `unified_user_value/` to align with the UV model family and shared scheduling/monitoring infrastructure.

Migration requires: new experiment name → new GCS paths → re-run datagen → re-deploy. Recommend deferring until E2E validation is complete and metrics are stable.

---

### 4.5 [LOW] `label` Column Is Unused Dead Weight in the Parquet

`features.py` still declares a `labels` featureset containing both `label` and `prob_sdk_event_name_label`. The `level_complete` task has been removed from config.json, so `label` is never used as a training target. It remains in the preprocessed parquet (written by datagen) and is still passed to the training pod, consuming memory and I/O bandwidth with no effect.

**Recommendation:** remove `label` from `features.py` labels featureset and from the datagen output columns once the migration is confirmed complete.

---

### 4.6 [LOW] `filter_min_dates_by_game_and_event` Is Skipped

The legacy pipeline removes training rows predating the first positive conversion for each `(target_game_id, event_name)` pair. This filter (Stage 5) is **commented out** in `unified_cpe_datagen.py`. Minor impact for a 60-day window where most campaigns have been running throughout. Re-enable post-E2E stabilization.

---

### 4.7 [LOW] `validate_duration` CLI Arg Is a No-Op

`--validate_duration` is parsed in the datagen for traceability but has no effect on the written parquet. The actual train/val split is applied at training time via `filter_expr` / `validation_filter_expr` in `workflow.py`. Should be removed in a cleanup pass.

---

## 5. Summary Table

| Area | Status | Notes |
|---|---|---|
| Data source | Stable | Same GCS path as legacy pinpointer |
| `prob_sdk_event_name_label` (PSN) | Correct | Full `{game_id}_{event}` token, no prefix stripping |
| `label` column | Unused | LC task removed; `label` is dead weight in parquet |
| Eligibility filter | Correct | COUNT ≥ 50 with `cum_app_event_count_d7 > 0`, parity with legacy |
| Train/val split | Correct | Random bucket 90/10, install-level deterministic |
| LR scheduler `total_step` | Fixed | Computed at runtime from BQ COUNT query |
| Val metrics callback | Fixed | `conversion_model_metrics_callback` enabled in config.json |
| Model architecture | Single-task | LC auxiliary task removed; PSN BCE only |
| PSN label rate inflation | Known risk | 7.5% → ~15% post-eligibility filter; same as legacy |
| Legacy hybrid bidding | Not implemented | PSN-only bid; no LC × PSN blend |
| `unified_cpe/` → `unified_user_value/` | Planned | Deferred until E2E validation complete |
| `filter_min_dates_by_game_and_event` | Skipped | Minor; re-enable post-E2E |
