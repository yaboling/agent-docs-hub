# [v11_cpe_lc] Design Doc - CPE Level Complete UL Migration

## 1. Introduction

### 1.1 Problem Statement

Why: The CPE Level Complete model predicts P(user fires the campaign-targeted SDK event within 7 days of install) and is used to bid on CPE Level Complete campaigns. The current production system runs two separate TensorFlow models in `ads-audience-pinpointer`:

- `level_complete_bhv` — behavioral traffic (IDFA-identified users only)
- `level_complete_ctx` — contextual traffic (IDFI + unspecified users)

These legacy models have several limitations that motivate migration to the Unified Learner framework:

1. **Split traffic coverage**: BHV handles only IDFA traffic; CTX handles IDFI/unspecified. A unified model trained on both simultaneously can learn cross-segment patterns and simplify the serving stack.
2. **External TF Hub sub-models**: Legacy models call two pre-trained TF Hub sub-models at training time (`ibt_embedding` 128d + `install_ibt_embedding` 80d), creating an external dependency that complicates training and serving.
3. **Per-SDK-event label via stochastic sampling**: Legacy models sample one SDK event per training step from a ragged label array, creating non-deterministic training that cannot be reproduced exactly.
4. **Fragmented architecture**: Two separate Kubeflow pipelines, two TFRecord pipelines, two TF Hub SavedModel serving deployments — all to be replaced by one Metaflow workflow, one Spark datagen, one Triton deployment.
5. **Framework alignment**: The rest of the UV model family has migrated to PyTorch + ads-unified-learner. Keeping the CPE LC model in TensorFlow creates maintenance overhead.

For more details on CPE campaigns, please refer to Understanding Event Optimization Models.

### 1.2 Success Criteria

Beyond key business metrics, add expected improvements from model design. The v11_cpe_lc model unifies BHV+CTX traffic and replaces the TF framework, so we expect:

- **Neutral-to-positive performance on CPE Level Complete campaigns**: Unified model should maintain or improve AUC and calibration vs. the legacy BHV + CTX models combined.
- **Correct per-SDK-event prediction calibration**: `prob_sdk_event_name_label` predictions should match observed event-specific conversion rates. The primary calibration concern (wildcard label inflation) has been identified and addressed.
- **Broader coverage**: The new model covers 13,321 distinct target games vs. 1,512 in legacy (~8.8x), and includes IDFI/unspecified traffic that was excluded from BHV.
- **Infrastructure simplification**: One pipeline, one model, one Triton deployment to replace two TF Hub deployments.

---

## 2. Data Overview

### 2.1 Data Source

The model is trained on data from the level_complete event pipeline:

| Property | Value |
|---|---|
| Source path | `gs://unity-ads-dd-ds-prd-data-anon/app-events/data/ads.events.operativeecpm.installs.outcomes.v2/level_complete/d7/` |
| Partition key | `installDate=YYYY-MM-DD` |
| Training window | 60 days |
| Label window | 7 days (`app_event_w1 > 0`) |
| Overall pipeline delay | 9 days (7-day label + 2-day ETL buffer) |
| Preprocessed output | `gs://unity-ads-dd-ds-prd-incremental-training-data/user_value/unified_user_value.v11_cpe_lc/preprocessed_combined/` |

**Row expansion design**: Unlike the legacy models (one row per install), the new datagen explodes each install by `sdk_event_name` target — one row per (install × targeted SDK event). A game with campaigns targeting `level_5` and `level_10` produces two rows per install. Games with no specific event target get a wildcard `"*"` row. This design enables native DLRM compatibility by converting ragged array labels into scalar per-row labels.

### 2.2 New Label Design

Two labels are produced per row:

| Label | Definition | Positive Rate |
|---|---|---|
| `label` | `app_event_w1 > 0` — any level complete within 7 days. Present in parquet but not used as a training target (LC auxiliary task removed). | ~38% (post-quality-filter) |
| `prob_sdk_event_name_label` | `1.0` if user fired the specific campaign-targeted SDK event AND `app_event_w1 > 0`, else `0.0`. **Primary training target and bidding signal.** | ~7% (post-fix dataset) |

**Joint distribution** (504M row dataset):

| `label` | `psn_label` | Row fraction | Interpretation |
|---|---|---|---|
| 0 | 0 | 80.4% | Non-converters |
| 1 | 0 | 12.5% | Converted but did not fire the specific targeted event |
| 1 | 1 | 7.1% | Converted AND fired the targeted event |

### 2.3 Data Quality Validation

**Label validation** has been documented in:
- Data Comparison Report (2026-04-22): Initial schema, row count, and label analysis
- Data Comparison Report (2026-05-05): Post-fix schema confirming categorical encoding correction, session counter restoration, and privacy signal restoration
- Prediction Inflation Analysis (2026-05-14): Root cause of prediction inflation traced to wildcard label contamination from archived campaigns
- Dataset Comparison v3 vs v0 (2026-05-14): Quantification of fix impact

**Key data issues identified and resolved**:

#### Issue 1 — Wildcard Label Inflation (RESOLVED in v3 dataset)

**Root cause**: The BQ campaign lookup (deprecated `campaign_audiences` + `campaign_pricing` tables) pulled all 7,997 historical level_complete campaigns with no status filter. Campaigns with 0 or >1 targeted SDK events were collapsed to a single wildcard `"*"` row. Since 95.3% of campaigns were paused and 2,202 were archived, the training data was dominated by wildcard rows from dead campaigns at 35–40% positive rate — far above the true per-event rate of ~7%.

**Fix**: Migrated campaign lookup to `unity-data-ads-core-prd.ads_dimension_data.campaigns_v3` with `archived_at IS NULL` filter. This drops 2,202 permanently archived campaigns (27.5%) while retaining all active and non-archived paused campaigns.

**Effect (v0 → v3 dataset comparison, based on partition sample)**:

| Metric | Old (v0) | Fixed (v3) | Change |
|---|---|---|---|
| Total rows (est.) | ~228M | ~107M | −53% |
| Wildcard row fraction | 19.6% | 12.3% | −7.3pp |
| Wildcard `psn_label` pos_rate | **35.3%** | **21.3%** | −14pp |
| Specific-event pos_rate | 10.1% | 13.2% | +3.1pp |
| Dead-signal events (n>100, pos_rate=0) | **58** | **7** | −51 |
| Unique target games (per partition) | 1,249 | 501 | −748 (−60%) |

The wildcard inflation ratio dropped from 3.5x (`35.3% / 10.1%`) to 1.6x (`21.3% / 13.2%`), significantly reducing the prediction floor for rare SDK events.

#### Issue 2 — Categorical Encoding Bug (RESOLVED in April 26 datagen)

Categorical features were pre-hashed to integers in the April 13 snapshot. Reverted to raw strings, matching legacy BHV/CTX representation.

#### Issue 3 — Missing Columns (RESOLVED in April 26 datagen)

Session counters (9 columns), privacy/identity signals (9 columns), `gamer_id_scope`, and `tgtg_sdk_set` were absent from early snapshots and have since been restored.

#### Issue 4 — `campaign_id` Column Duplication (OPEN)

`campaign_id` is mapped to `campaignInfo.audienceId` (same as `audience_id`) instead of the correct campaign identifier. This causes the `campaign_id` embedding to duplicate the `audience_id` signal. Fix: use `campaignset_id` from `campaigns_v3`. Not yet applied — minor impact on model quality, to be fixed in next datagen version.

#### Issue 5 — Stage 5 Filter Disabled (OPEN)

`filter_min_dates_by_game_and_event` (removes rows predating the first positive conversion per `(game, event)` pair) is commented out in `unified_cpe_datagen.py`. Minor impact for a 60-day window. Re-enable post-E2E stabilization.

### 2.4 Game-Level Quality Gate

Mirrors the legacy `ads-audience-pinpointer` eligibility filter:

```python
# Keep only games with ≥50 installs having cum_app_event_count_d7 > 0
eligible_game_ids = (
    df.filter(col("cum_app_event_count_d7") > 0)
      .groupBy("targetGameId")
      .agg(count("*").alias("_event_gamers"))
      .filter(col("_event_gamers") >= 50)
)
```

Note: The post-filter PSN positive rate (~15%) is higher than the pre-filter rate (~7.5%) due to survivorship bias — only high-converting games are kept. This matches legacy model behavior and means online calibration must be monitored post-launch.

---

## 3. Model Overview

### 3.1 Model Card

The technical specifications and configuration for the `unified_user_value.v11_cpe_lc` model can be found in the [Model Card](model_card_unified_cpe_v1_lc.md).

**Summary of changes from legacy**:

| Dimension | Legacy BHV + CTX | v11_cpe_lc |
|---|---|---|
| **Framework** | TensorFlow 2.11 + Keras | PyTorch 2.x + Lightning |
| **Architecture** | FC MLP (3 layers) | DLRM (dense tower + DotProductPlus + DCN) |
| **Models** | 2 separate (BHV + CTX) | 1 unified |
| **Traffic scope** | BHV: IDFA only; CTX: IDFI + unspecified | All (IDFA + IDFI + unspecified) |
| **Task heads** | Single (`label`) | Single-task PSN (`prob_sdk_event_name_label`) |
| **SDK event label** | Stochastic per-element array sampling | Deterministic row-expansion + scalar label |
| **External embeddings** | IBT 128d + install_ibt 80d (TF Hub) | Dropped → 15 AGC dense scalar features |
| **Data window** | ~60 days | 60 days |
| **Train rows** | BHV: ~44M, CTX: ~60M | ~107M (post-fix) |
| **Training compute** | 1× T4 GPU | 8× RTX PRO 6000 Blackwell (DDP) |
| **Serving format** | TF Hub SavedModel → Firestore | Triton (packed input, static shape, CPU) |

**Feature engineering highlights**:
- **Dropped**: UUPS IAP/adrev signals (27 features), IBT embeddings (208-dim), hardware stats scalars/categoricals
- **Added**: `ad_format` (interstitial vs. rewarded), `creative_id`, `creative_pack_id`, `device_orientation`, `video_orientation`, `sdk_event_name` as sparse embedding, 6 new target-game 7d/24h counter features
- **Unified**: `gamer_id_scope` as a sparse feature lets one model serve both BHV (IDFA) and CTX (IDFI) traffic

**Bidding logic** (`DeployModel.forward`):
```python
p    = clamp(psn_pred, 0.0, 1.0)          # P(user fires targeted SDK event within 7d)
cost = clamp(max_cost × p × discount_factor, 0.0, 1e18)  # cost in microdollars
```

### 3.2 Offline Results

Offline evaluation was conducted on a 60-day dataset (install dates 2026-02-26 → 2026-04-26, 486M train rows / 18.7M val rows). Model artifact: `vny2xtis3e`.

**Note on metric comparability**: Direct loss comparison across new and legacy models is not valid due to different label definitions (CPE ~19.75% positive vs. CPI ~37% positive), different loss formulations (uncertainty-weighted multi-task vs. single-task BCE), and train vs. val set differences. AUC and NE are the most meaningful cross-model signals.

#### Offline Performance (v11_cpe_lc train metrics at epoch 5)

| Metric | v11_cpe_lc (train) | Legacy BHV (val, best epoch) | Legacy CTX (val, best epoch) |
|---|---|---|---|
| AUC | **0.9483** | 0.8997 | 0.8991 |
| BCE (`level_complete` head) | **0.2047** | 0.3308 | 0.3313 |
| NE (window) | **0.4119** | ~0.505 | ~0.506 |
| Calibration ratio | **0.9993** | — | — |
| mean_pred vs mean_label | 0.1976 vs 0.1975 (Δ < 0.0001) | 0.2494 (bias=0.0025) | 0.2512 (bias=0.0031) |

**Key takeaways**:
- Strong AUC gain (+5.4pp vs. legacy) and calibration near-perfect on training data.
- **Known limitation — LR schedule mismatch**: The `lr_scheduler.total_step` was set to 88 (matching `train_duration`) rather than the actual training step count (~23,719). Dense-layer LR decayed to `end_lr=1e-6` after only ~0.4% of training. Only sparse embeddings (35.3M / 36.3M params) trained at the intended learning rate throughout. This issue has been identified and fixed for subsequent training runs — `workflow.py` now computes `total_step` dynamically from a BQ `COUNT(*)` query.
- Train-only AUC numbers are not directly comparable to legacy val AUC. Separate held-out time-based evaluation is required for the production go/no-go decision.

#### Key Feature Gaps vs. Legacy

| Missing Feature Group | Legacy Source | Priority |
|---|---|---|
| UUPS IAP/adrev signals (27 features) | UUPS pipeline (BHV only) | High — strong purchase intent signal |
| IBT embeddings (128d + 80d) | External TF Hub sub-models | High — cross-game behavioral signal |
| Hardware stats (cpu, ram, dpi) | DeviceAtlas enrichment at serving | Medium — partially covered by DeviceAtlas at serving |
| Target game base counters (no time window) | BHV legacy | Low — 7d/24h variants are present in v1_lc |

These are tracked as Phase 2/3 additions.

---

## 4. Online Test

EP links:
- Shared Control (Level Complete): [EP Link] — TBD
- CPE Level Complete UL Migration (v11_cpe_lc): [EP Link] — TBD

### 4.1 Executive Summary

**Phase 1 (v11-cpe-lc-2, original dataset, 1% traffic — 2026-05-11 to 2026-05-14)**:

A prediction inflation issue was discovered. The new model's average predictions were **2–56x higher** than legacy on matched campaigns, leading to systematic overbidding:

| Overbid range | Campaigns | % of total |
|---|---|---|
| <1x (v11 lower) | 1 | 0.3% |
| 1–2x | 131 | 36.8% |
| 2–3x | 108 | 30.3% |
| 3–5x | 89 | 25.0% |
| >5x | 27 | 7.6% |

Median overbid ratio: **2.33x**. The most extreme case (`star5_hero_received` event): **36.7x**.

**Root cause**: Wildcard label contamination from 2,202 archived campaigns that were included in training data with no status filter. These campaigns had 0 specified SDK events and were collapsed to `"*"` wildcards, contributing 35–86% positive rate rows that anchored model predictions far above the true per-event rate.

**Phase 2 (v3 dataset, retraining in progress)**:

The fix (migrate campaign lookup to `campaigns_v3` with `archived_at IS NULL`, drop archived campaigns) was applied and a new dataset (`date=2026-05-05-3`) was generated. The wildcard positive rate dropped from 35.3% to 21.3%, with 51 dead-signal event types removed. Model retraining on the v3 dataset is in progress. Online A/B test results with the retrained model are pending.

### 4.2 Additional Insights

#### 4.2.1 Prediction Inflation Analysis (Phase 1, v11-cpe-lc-2)

Per-campaign overbid breakdown on 356 matched (campaign, target_game, sdk_event) triples (2026-05-11 to 2026-05-14):

| Campaign / SDK Event | bhv1p avg_pred | ctx1r avg_pred | v11 avg_pred | Ratio (v11/bhv) |
|---|---|---|---|---|
| `star5_hero_received` | 0.002 | 0.005 | 0.113 | **56x** |
| Anonymous mid-rate | 0.154 | 0.171 | 0.564 | 3.7x |
| `grt_7d_level30_notir` | 0.323 | 0.412 | 0.783 | 2.4x |
| `Registration-S2S` | 0.315 | 0.270 | 0.798 | 2.5x |
| `create_role` | 0.900 | 0.940 | 0.962 | ~1x (ceiling) |

**Key pattern**: Inflation ratio is inversely proportional to base event rate. Rare events with low natural positive rates are most severely inflated; near-ceiling events show no inflation.

**Training-data root cause query** (confirmed smoking gun):

| sdk_event | Rows | psn_label pos_rate |
|---|---|---|
| `*` (wildcard) | 178.2M | **36.4%** |
| All specific events (avg) | 224.5M | **6.0%** |

The wildcard `"*"` constituted 44% of all training rows at 36.4% positive rate — 6.1x higher than the average specific-event rate. BCE minimization drives sigmoid outputs toward ~19.5% (the blended base rate), not the true per-event rate of ~6%.

#### 4.2.2 Dataset Fix Validation (v0 vs v3)

Comparison of `date=2026-05-05` (old) vs `date=2026-05-05-3` (fixed), based on partition `part-00000` (44K rows):

| Metric | Old | Fixed (v3) | Change |
|---|---|---|---|
| Wildcard pos_rate | 35.3% | 21.3% | −14pp |
| Specific-event pos_rate | 10.1% | 13.2% | +3.1pp |
| Overbid ratio (wildcard / specific) | 3.5x | **1.6x** | Better |
| Dead-signal events (pos_rate=0) | 58 | 7 | −51 |

The fix is confirmed to be working. The remaining residual inflation (1.6x) comes from 19 live 0-event campaigns (Path A) for which wildcard `"*"` is semantically correct — these are advertisers who genuinely target any level-complete event.

#### 4.2.3 Monitoring Plan

**Short-term (post v3 model launch)**:
- **Prediction calibration**: Monitor `avg(app_event_p)` vs. observed conversion rate in `mz_dcpi_prediction_v1` per campaign, comparing v11-cpe-lc vs. legacy bhv1p/ctx1r. Target: median overbid ratio < 1.5x.
- **Per-event prediction distribution**: Track top-20 SDK events by row count. Ensure `avg_pred` is within 2x of the observed `psn_pos_rate` for each event.
- **Scale guardrails**: Monitor spend, installs, and net revenue relative to legacy. Ensure no unexpected spend inflation from overbidding.
- **Zero valuation rate**: Check that v11-cpe-lc zero-valuation rate is consistent with legacy (legacy has 2–32% zero valuation rate for certain campaigns; v11 should not differ materially).

**Long-term**:
- **UUPS and IBT signal integration**: Reinstate UUPS IAP/adrev features (27 signals) and explore replacing IBT embeddings. ETA: Phase 2 (Q3).
- **Stage 5 filter re-enablement**: `filter_min_dates_by_game_and_event` to be re-enabled once E2E is stable. This removes cold-start rows predating the first positive conversion for each `(game, event)` pair.
- **Enable calibration**: Set `enable_calibration: true` in `config.json` or add Platt scaling on the held-out val set, for parity with legacy calibrated models.
- **`campaign_id` column fix**: Map to `campaignset_id` from `campaigns_v3` instead of `audienceId`.
- **Multi-week label horizon**: Verify `app_event_w1/w2/w3/w4` variation in datagen (currently all identical). Enable multi-week auxiliary targets if attribution logic is corrected.

**Dependencies**:
- v3 dataset retraining must complete before wider rollout
- Serving team alignment on Triton deployment for `sdk_event_name` online feature population (confirm Go serving layer populates `sdk_event_name` correctly, not `"placeholder"`)

---

## 5. Launch Preparation

**Code changes merged to main**:
- `unified_cpe_datagen.py`: Campaign lookup migration to `campaigns_v3`, `archived_at IS NULL` filter, multi-event campaign explode (Path B fix)
- `workflow.py`: Dynamic `lr_scheduler.total_step` computed from BQ `COUNT(*)` at training time; Spark BigQuery project property added
- `features.py`: `sdk_event_name` as online sparse embedding, `prob_sdk_event_name` as offline-only sparse feature, `model_name` moved to offline-only
- `model.py`: `DeployModel` with `cost = max_cost × discount_factor × p` bidding logic
- `config.json`: Single-task PSN configuration, `model_variant: 3`

**Open items before wider rollout**:

| Item | Status | Owner |
|---|---|---|
| Retrain on v3 (fixed) dataset | In progress | Yabo Ling |
| Verify `sdk_event_name` online feature population in Go serving layer | TODO | Serving team |
| Enable calibration (`enable_calibration: true`) | TODO | Yabo Ling |
| Fix `campaign_id` → `campaignset_id` | TODO | Yabo Ling |
| Re-enable `filter_min_dates_by_game_and_event` (Stage 5) | TODO | Yabo Ling |
| Migrate experiment from `unified_cpe/` to `unified_user_value/` (aligned with UV family) | Planned (post-E2E) | Yabo Ling |

---

## 6. Next Steps and Meeting Notes

**AIs**:
- Retrain model on v3 dataset (fixed wildcard contamination) — Yabo Ling
- Validate `sdk_event_name` online serving population (Go serving layer) — Yabo Ling + Serving team
- Run full A/B test with retrained v3 model at 1% → 5% → 50% traffic ramp — Yabo Ling
- Enable calibration and measure online bias correction — Yabo Ling
- Sync with data engineering on `campaigns_v3` table stability and `archived_at` semantics — Yabo Ling + Data Eng
- Investigate UUPS feature integration timeline (Phase 2) — Yabo Ling + Zenith Zeng
- Fix `campaign_id` column to use `campaignset_id` — Yabo Ling
- Re-enable Stage 5 filter (`filter_min_dates_by_game_and_event`) — Yabo Ling

---

## Appendix

### A.1 SDK Event Label Architecture Decision

Two options were evaluated for adapting the legacy per-SDK-event label to the PyTorch/DLRM framework:

| | Option 1: Row expansion | Option 2: Per-element array loss |
|---|---|---|
| **Data format** | One row per (install × targeted event) | One row per install, array labels |
| **Label format** | Scalar float per row | `array<float>` per row |
| **Architecture fit** | Perfect (list_len=1 scalar) | Requires EmbeddingBag → attention redesign |
| **Data size** | ~5× (1–5 events per game average) | 1× |
| **Risk** | Low | High |

**Decision: Option 1 (row expansion)**. The `bucket` column (deterministic hash of `auctionId`) ensures all expanded rows from the same install land in the same train/val split partition — no data leakage.

### A.2 Legacy vs. New Label Semantics

| Aspect | NEW `unified_user_value.v11_cpe_lc` | Legacy `ads-audience-pinpointer` |
|---|---|---|
| Label type | Deterministic, computed at datagen time | Stochastic, sampled per training step |
| Training label | `prob_sdk_event_name_label` (scalar 0/1) | `probabilistic_labels` (float array) |
| SDK event conditioning | 1 row per (install × sdk_event) | 1 row per install, array of labels |
| Row inflation | ~5× (explode by sdk_event) | 1× (no explode) |
| Wildcard handling | `sdk_event='*'` → label=1 if label=1 | Wildcard `*` treated as matching all events |
| Reproducibility | Deterministic — same data every epoch | Stochastic — different sample per epoch |

### A.3 Prediction Inflation Analysis — Top 10 Most Inflated Campaigns (Phase 1)

| Campaign ID | SDK Event | v11 avg_pred | Legacy avg_pred | Ratio |
|---|---|---|---|---|
| `652214aefc636157750229a8` | `star5_hero_received` | 0.1177 | 0.0032 | **36.7x** |
| `67dc0fa20eb345a2a13aef4f` | `ajvip` | 0.4889 | 0.0326 | 15.0x |
| `69eae6280d291c5f22675e19` | `recvd_coins_400` | 0.7047 | 0.0645 | 10.9x |
| `69c4447a75bdf4ae2c38cc0d` | `pc_t2_d60_ios_custom` | 0.1692 | 0.0156 | 10.8x |
| `6960733f13cc68bc8f91fc8e` | `ajvip` | 0.6445 | 0.0731 | 8.8x |
| `6825d515a47ee6e329c70bdd` | `eventW` | 0.5920 | 0.0688 | 8.6x |
| `685e72777dd83b9c8536915e` | `eventw` | 0.4666 | 0.0575 | 8.1x |
| `686664ce9dfaacc5e24bf3df` | `ajvip` | 0.4776 | 0.0605 | 7.9x |
| `684ac40f6da6f407ddfa47fd` | `d7_puzzle60_hint5` | 0.6146 | 0.0806 | 7.6x |
| `698c51a4e63287f25051d95c` | `ajvip` | 0.4619 | 0.0612 | 7.6x |

### A.4 Architecture Dimension Derivation

```
num_embs = 18 (individual_sparse, repeat=1) + 1 (sdk_event_name) + 2 (dense_embedding_dim 64 // sparse_embedding_dim 32) = 21

cross_dense_sparse   = 21 × dot_product_compress_dim(8) = 168
dense_repr           = dense_tower_mlp[-1] = 64
shared_bottom input  = 168 + 64 = 232

task hidden output   = mlp_layers[-2] = 256
cat(256, cds=168)    = 424
poly cat(x, x²)      = 848
task final layer     = 2 × (168 + 256) = 848  ✓
```
