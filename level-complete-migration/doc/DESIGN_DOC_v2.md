# [v11_cpe_lc] Design Doc — CPE Level Complete UL Migration

---

## 1. Introduction

### 1.1 Problem Statement

**Why:** The CPE Level Complete model predicts `P(user fires the campaign-targeted SDK event within 7 days of install)` and is used to bid on CPE Level Complete campaigns. The current production system runs **two separate TensorFlow models** in `ads-audience-pinpointer`:


| Model                | Traffic Covered | Identity Type              |
| -------------------- | --------------- | -------------------------- |
| `level_complete_bhv` | Behavioral      | IDFA-identified users only |
| `level_complete_ctx` | Contextual      | IDFI + unspecified users   |


These legacy models have five key limitations:

```
Legacy System Pain Points
─────────────────────────────────────────────────────────────────────
 1. No active         CPE LC is the ONLY remaining model in ads-audience-pinpointer
    maintainance      running TensorFlow. The rest of the UV model family has fully
                      migrated to PyTorch + ads-unified-learner — keeping CPE LC in
                      TF creates an isolated maintenance burden with no dedicated resource.

 2. Split traffic     BHV handles IDFA only; CTX handles IDFI/unspecified.
                      A unified model trained on all segments can learn
                      cross-segment patterns and simplify serving.

 3. External TF Hub   Training calls 2 pre-trained TF Hub sub-models:
    dependencies      ibt_embedding (128d) + install_ibt_embedding (80d).
                      Creates external dependency, complicates training & serving.

 4. Stochastic labels Legacy samples one SDK event per training step from a
                      ragged label array → non-deterministic, non-reproducible.

 5. Fragmented        2 Kubeflow pipelines  +  2 TFRecord pipelines
    infrastructure    +  2 TF Hub SavedModel deployments
                      → replaced by 1 Metaflow workflow, 1 Spark datagen,
                        1 Triton deployment.
─────────────────────────────────────────────────────────────────────
```

For more details on CPE campaigns, please refer to Understanding Event Optimization Models.

### 1.2 Success Criteria

The `v11_cpe_lc` model unifies BHV+CTX traffic and replaces the TensorFlow framework. Beyond key business metrics, we expect:


| Criterion                           | Target                                                                                                                           |
| ----------------------------------- | -------------------------------------------------------------------------------------------------------------------------------- |
| **Performance on CPE LC campaigns** | Neutral-to-positive business metrics vs. legacy BHV + CTX combined                                                               |
| **Per-SDK-event Bias**              | `prob_sdk_event_name_label` predictions match observed event-specific conversion rates. Model bias and Product Bias are improved |
| **Broader game coverage**           | 13,321 distinct target games vs. 1,512 in legacy (~8.8x), including IDFI/unspecified traffic excluded from BHV                   |
| **Infrastructure simplification**   | One pipeline, one model, one Triton deployment replaces two TF Hub deployments                                                   |


---

## 2. Data Overview

### 2.1 Data Source

```
Data Pipeline at a Glance
───────────────────────────────────────────────────────────────────────
  Source
  gs://unity-ads-dd-ds-prd-data-anon/
    app-events/data/ads.events.operativeecpm.installs.outcomes.v2/
    level_complete/d7/

  Partition Key: installDate=YYYY-MM-DD
  Training Window: 60 days
  Label Window: 7 days (app_event_w1 > 0)
  Pipeline Delay: 9 days (7-day label + 2-day ETL buffer)

  Output
  gs://unity-ads-dd-ds-prd-incremental-training-data/
    user_value/unified_user_value.v11_cpe_lc/preprocessed_combined/
───────────────────────────────────────────────────────────────────────
```

**Row expansion design:** Unlike legacy models (one row per install), the new datagen **explodes each install by `sdk_event_name` target** — one row per `(install × targeted SDK event)`:

```
install_A  targeting [level_5, level_10]
  └─► Row 1: install_A × level_5
  └─► Row 2: install_A × level_10

install_B  no specific target  →  "*" wildcard
  └─► Row 1: install_B × "*"
```

This converts ragged array labels into scalar per-row labels, enabling native DLRM compatibility.

### 2.2 Label Design

Two labels are produced per row:


| Label                       | Definition                                                                                                                                       | Positive Rate                                                          |
| --------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------ | ---------------------------------------------------------------------- |
| `label`                     | `app_event_w1 > 0` — any level complete within 7 days. Present in parquet but **not used** as training target (LC auxiliary task removed).       | **38.16%** (post-quality-gate, v3 dataset)                             |
| `prob_sdk_event_name_label` | `1.0` if user fired the specific campaign-targeted SDK event AND `app_event_w1 > 0`, else `0.0`. **Primary training target and bidding signal.** | **14.25%** overall (14.30% specific events / 26.10% wildcard `*` rows) |


> Source: Label distribution analysis (2026-05-21), 877,366 rows sampled from `preprocessed_combined/date=2026-05-11`. See `LABEL_DISTRIBUTION_ANALYSIS.md` for full details.

**Joint distribution** (post-quality-gate preprocessed data, v3 dataset):

```
                        app_event_w1=0    app_event_w1=1
psn_label=0          │    61.84%         │    23.91%      │  Non-converters / converted but wrong SDK event
psn_label=1          │     0.00%         │    14.25%      │  Converted AND fired the targeted event
```

Three key observations from the joint distribution:

1. **23.91% of all rows** have `label=1` (user did level-complete) but `prob_sdk_event_name_label=0` (not the campaign-targeted event). These rows contribute **zero positive signal** for the per-event training target — they are "right game, wrong event" installs.
2. `**psn_label=1` is impossible when `label=0`** by construction — a user cannot fire a specific event without also having `app_event_w1 > 0`.
3. **Wildcard `*` rows** (12.3% of rows by volume) have `psn_label = label` by definition — they match any level-complete — driving their positive rate to 26.10% vs 14.30% for specific-event rows. This 1.8× gap is the residual wildcard inflation after the v3 dataset fix.

**Comparison with legacy BHV/CTX per-event label:**


| Dataset                           | Per-event positive rate | Calibration applied                                    |
| --------------------------------- | ----------------------- | ------------------------------------------------------ |
| Legacy BHV                        | 23.52%                  | ✅ Post-hoc (`trained_game_sdk_combo_multipliers.json`) |
| Legacy CTX                        | 23.96%                  | ✅ Post-hoc                                             |
| UL v11_cpe_lc (specific events)   | **14.30%**              | ❌ Not yet enabled                                      |
| UL v11_cpe_lc (wildcard `*` rows) | **26.10%**              | ❌ Not yet enabled                                      |


Legacy appears to have higher per-event rates because its `sdk_event_name = "placeholder"` architecture trains on an array of all campaign events per install, making rare events co-train with common events. The UL approach (one row per targeted event) isolates each event — producing a more honest label rate for specific events, but also exposing the wildcard inflation more directly.

### 2.3 Data Quality Validation

**Label validation documents:**

- Data Comparison Report (2026-04-22): Initial schema, row count, and label analysis
- Data Comparison Report (2026-05-05): Post-fix schema — categorical encoding correction, session counter restoration, privacy signal restoration
- Prediction Inflation Analysis (2026-05-14): Root cause of prediction inflation — wildcard label contamination
- Dataset Comparison v3 vs v0 (2026-05-14): Quantification of fix impact

---

**Issue 1 — Wildcard Label Inflation** `RESOLVED in v3 dataset`

> **Root cause:** The BQ campaign lookup (`campaign_audiences` + `campaign_pricing`, deprecated tables) pulled all 7,997 historical level_complete campaigns with **no status filter**. 95.3% of campaigns were paused and 2,202 were archived. Archived campaigns with 0 specified SDK events collapsed to `"*"` wildcard rows at **35–86% positive rate** — far above the true per-event rate of ~7%.

**Fix:** Migrated campaign lookup to `unity-data-ads-core-prd.ads_dimension_data.campaigns_v3` with `archived_at IS NULL` filter.

**Effect (v0 → v3 dataset):**


| Metric                                 | Old (v0)  | Fixed (v3) | Change                |
| -------------------------------------- | --------- | ---------- | --------------------- |
| Total rows (est.)                      | ~228M     | ~107M      | −53%                  |
| Wildcard row fraction                  | 19.6%     | 12.3%      | −7.3pp                |
| Wildcard `psn_label` pos_rate          | **35.3%** | **21.3%**  | −14pp                 |
| Specific-event pos_rate                | 10.1%     | 13.2%      | +3.1pp                |
| Dead-signal events (n>100, pos_rate=0) | **58**    | **7**      | −51                   |
| Overbid ratio (wildcard/specific)      | 3.5x      | **1.6x**   | Significantly reduced |


```
Residual 1.6x wildcard inflation is expected:
  Path A — 19 live 0-event campaigns targeting ANY level-complete event.
           Wildcard "*" is semantically correct for these advertisers.
```

---

**Issue 2 — Categorical Encoding Bug** `RESOLVED (April 26 datagen)`

Categorical features were pre-hashed to integers. Reverted to raw strings, matching legacy BHV/CTX representation.

---

**Issue 3 — Missing Columns** `RESOLVED (April 26 datagen)`

Session counters (9 columns), privacy/identity signals (9 columns), `gamer_id_scope`, and `tgtg_sdk_set` restored.

---

**Issue 4 — `campaign_id` Column Duplication** `OPEN`

`campaign_id` is mapped to `campaignInfo.audienceId` (same as `audience_id`), duplicating the `audience_id` embedding signal. Fix: use `campaignset_id` from `campaigns_v3`. Minor impact — scheduled for next datagen version.

---

**Issue 5 — Stage 5 Filter Disabled** `OPEN`

`filter_min_dates_by_game_and_event` (removes rows predating the first positive conversion per `(game, event)` pair) is commented out. Minor impact for a 60-day window. Re-enable post-E2E stabilization.

### 2.4 Online Bidding Gate — Eligibility Requirement

**Before a game can run a Level Complete campaign, it must have sent us level complete events.** The model only bids on `(target_game_id, sdk_event_name)` combinations it was trained on with at least one positive PSN label. Combinations never seen in training produce a zero bid.

#### How the gate works

```
Training time (update_mappings step in workflow)
───────────────────────────────────────────────────────────────────────
  For every (target_game_id, sdk_event_name) pair in the preprocessed
  parquet that has >= 1 row with psn_label=1:
    → write "{target_game_id}_{sdk_event_name}": 1.0
      to trained_game_sdk_combo.json (GCS)

Serving time (DeployModel.forward)
───────────────────────────────────────────────────────────────────────
  _gate_tensor[target_game_id_idx, sdk_event_name_idx]
    = 1.0  if combo seen in training with a positive PSN label
    = 0.0  otherwise  →  cost = 0  (no bid placed)

  cost = max_cost × discount_factor × p × gate
                                          ^^^^
                                    zeroes out unseen combos
───────────────────────────────────────────────────────────────────────
```

This mirrors **Mechanism 1** of the legacy `LevelCompleteCostWrapper` (`trained_game_sdk_combo_multipliers`).

#### Implication for advertisers and campaign setup

```
Game eligibility lifecycle
───────────────────────────────────────────────────────────────────────
  Step 1 — SDK integration
           Game integrates Unity Ads SDK and fires level complete events
           (e.g. "level_5", "level_10") back to Unity.

  Step 2 — Data accumulation
           Level complete events flow into the LC data pipeline:
           gs://.../app-events/.../level_complete/d7/

  Step 3 — Training window coverage
           The game must appear in the 60-day training window with
           >= 1 install that fired the targeted SDK event (psn_label=1).
           Games with only 0-positive rows are gated out at serving time.

  Step 4 — Quality gate (Section 2.5)
           Additionally requires >= 50 installs with cum_app_event_count_d7 > 0
           to be included in training data at all.

  Step 5 — Gate tensor baked into model artifact
           After each daily training run, trained_game_sdk_combo.json
           is refreshed and the new gate tensor is deployed with the model.
           New eligible games become biddable within ~24 hours of the
           next successful workflow run.
───────────────────────────────────────────────────────────────────────
```

**Wildcard campaigns** (`sdk_event_name = ""`): The Go serving layer sends an empty string for campaigns that target any level complete event. The preprocessor maps `""` → `UNKNOWN_INT` (5). `DeployModel` remaps index-5 → the `"*"` vocab entry so that wildcard campaigns correctly hit the gate and embedding for `"*"`, rather than being silently zeroed out.


| Combo type                       | Example                                            | Gate behaviour                 |
| -------------------------------- | -------------------------------------------------- | ------------------------------ |
| Specific, seen in training       | `(game_A, "level_5")` with psn_label=1 rows        | gate = 1.0 → bids normally     |
| Specific, never seen             | `(game_B, "star5_hero")` absent from training data | gate = 0.0 → zero bid          |
| Wildcard, game has any LC events | `(game_A, "")` → remapped to `(game_A, "*")`       | gate = 1.0 if `"*"` row exists |
| Wildcard, game has no LC data    | `(game_C, "")`                                     | gate = 0.0 → zero bid          |


> **Operational note:** If a game's LC campaign is unexpectedly getting zero bids, the first thing to check is whether `(target_game_id, sdk_event_name)` appears in `trained_game_sdk_combo.json`. If it is absent, the game either has no positive LC events in the 60-day training window, or it failed the quality gate (< 50 converting installs). The fix is to wait for sufficient event data to accumulate and for the next daily workflow to complete.

### 2.5 Game-Level Quality Gate

Mirrors the legacy `ads-audience-pinpointer` eligibility filter:

```python
# Keep only games with >= 50 installs having cum_app_event_count_d7 > 0
eligible_game_ids = (
    df.filter(col("cum_app_event_count_d7") > 0)
      .groupBy("targetGameId")
      .agg(count("*").alias("_event_gamers"))
      .filter(col("_event_gamers") >= 50)
)
```

#### Label Distributions

**Plot 1 — Joint distribution of `label` × `psn_label` (post-quality-gate, v3 dataset sample 877K rows)**

```
Row composition by label combination
───────────────────────────────────────────────────────────────────────
                                    0%          25%         50%         75%        100%
                                    │           │           │           │           │
 label=0, psn=0  (non-converters)   █████████████████████████████████  61.84%
 label=1, psn=0  (LC but wrong SDK) ████████████  23.91%
 label=1, psn=1  (target event hit) ███████  14.25%
───────────────────────────────────────────────────────────────────────
  label positive rate     = 38.16%  (any level complete within 7d)
  psn_label positive rate = 14.25%  (specific targeted SDK event fired)
```

**Plot 2 — `label` vs `psn_label` positive rates, and wildcard vs specific split (post-quality-gate)**

```
Positive label rate comparison
───────────────────────────────────────────────────────────────────────
  label                  38.16%  ██████████████████████████████████████
  psn_label (overall)    14.25%  ██████████████
  psn_label (specific)   14.30%  ██████████████
  psn_label (wildcard*)  26.10%  ██████████████████████████
                          0%     10%     20%     30%     40%
───────────────────────────────────────────────────────────────────────
  label is 2.7× higher than psn_label (specific events).
  Wildcard rows inflate the per-event rate by 1.8× vs specific events —
  residual contamination after the campaigns_v3 + archived_at IS NULL fix.
  A user can "level complete" any event (label=1) but fail to fire
  the specific SDK event the campaign is targeting (psn=0).
```

**Plot 3 — `psn_label` positive rate: pre-filter vs post-filter**

```
psn_label positive rate — effect of game quality gate (>= 50 installs with LC event)
───────────────────────────────────────────────────────────────────────
  Pre-filter   ~7.5%  ███████
  Post-filter  14.25% ██████████████
                0%    5%   10%   15%   20%
───────────────────────────────────────────────────────────────────────
  +6.75 pp lift  (~+90%)
  Cause: survivorship bias — games with <50 converting installs are
  dropped, leaving only high-converting games in the training set.
  This inflates the observed positive rate vs. the true population rate.
  Confirmed by label distribution analysis (2026-05-21).
```

> **Implication for online monitoring:** The training data positive rate (~~14%) is approximately 2× higher than the true population rate (~~7.5%). The model will be calibrated to a higher base rate than it sees in production. **Online calibration must be monitored post-launch** — model bias should be tracked per campaign and compared to observed conversion rates in `mz_dcpi_prediction_v1`.

---

## 3. Model Overview

### 3.1 Model Card

The technical specifications and configuration for the `unified_user_value.v11_cpe_lc` model can be found in the [Model Card](model_card_unified_cpe_v1_lc.md).

**Summary of changes from legacy:**


| Dimension               | Legacy BHV + CTX                        | v11_cpe_lc                                      |
| ----------------------- | --------------------------------------- | ----------------------------------------------- |
| **Framework**           | TensorFlow 2.11 + Keras                 | PyTorch 2.x + Lightning                         |
| **Architecture**        | FC MLP (3 layers)                       | DLRM (dense tower + DotProductPlus + DCN)       |
| **Models**              | 2 separate (BHV + CTX)                  | 1 unified                                       |
| **Traffic scope**       | BHV: IDFA only; CTX: IDFI + unspecified | All traffic (IDFA + IDFI + unspecified)         |
| **Task heads**          | Single (`label`)                        | Single-task PSN (`prob_sdk_event_name_label`)   |
| **SDK event label**     | Stochastic per-element array sampling   | Deterministic row-expansion + scalar label      |
| **External embeddings** | IBT 128d + install_ibt 80d (TF Hub)     | Dropped → 15 AGC dense scalar features          |
| **Train rows**          | BHV: ~44M, CTX: ~60M                    | ~107M (post-fix dataset)                        |
| **Training compute**    | 1× T4 GPU                               | 8× RTX PRO 6000 Blackwell (DDP, `strategy=ddp`) |
| **Serving format**      | TF Hub SavedModel → Firestore           | Triton (packed input, static shape, CPU)        |


**Architecture at a glance:**

```
Dense features (16 total)                    Sparse features (18 total)
  ├─ gamer_creation_delay (1)                  ├─ ad_format, platform, gamer_id_scope
  └─ AGC counters (15)                         ├─ geo, device_*, video/ad orientation
                                               ├─ audience_id, publisher_*/target_*
        │                                      ├─ creative_id, creative_pack_id
        ▼                                      └─ sdk_event_name  ◄─ NEW (online feature)
  Dense Tower MLP
  [16 → 128]                                         │
  BatchNorm + Dropout(0.1)                           ▼
        │                                    Sparse Embeddings
        │                                    dim=32, 18 tables
        │                                           │
        └──────────────────────────────────────────►│
                                                     ▼
                                          DotProductPlus  +  DCN (2 layers)
                                          compress_dim=16
                                          cross_dense_sparse = 20 × 16 = 320
                                          + dense_repr (128) = 448
                                                     │
                                                     ▼
                                          Shared Bottom MLP
                                          [448 → 512 → 256]
                                          BatchNorm + Dropout(0.3)
                                                     │
                                                     ▼
                                          PSN Task Head
                                          [256 → 512 → 1]
                                          Dropout(0.3) + Sigmoid
                                                     │
                                                     ▼
                                            P(user fires targeted
                                             SDK event within 7d)
```

**Bidding logic in `DeployModel.forward`:**

```
1. psn_pred      = model sigmoid output
2. p_raw         = clamp(psn_pred, 0.0, 1.0)
3. calib         = _calib_tensor[audience_id_idx]     ← per-campaign product accuracy calibration
4. gate          = _gate_tensor[target_game_id, sdk_event_name]  ← eligibility (1.0 trained / 0.0 not)
5. p             = clamp(p_raw × calib, 0.0, 1.0)
6. cost          = clamp(max_cost × discount_factor × p × gate, 0.0, MAX_MICRODOLLARS)
```

**Serving mechanisms (both mirror legacy `LevelCompleteCostWrapper`):**


| Mechanism                                      | Description                                                                                                                                                                            | Source File                         |
| ---------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------- |
| **Mechanism 1 — Eligibility gate**             | Zeros cost for `(target_game_id, sdk_event_name)` combos the model was never trained on with a positive PSN label.                                                                     | `trained_game_sdk_combo.json`       |
| **Mechanism 2 — Product accuracy calibration** | Per-campaign correction factor (`observed_rate / predicted_rate`) baked into model artifact at deploy time. Factors clamped to [0.05, 1.0] — only shrinks predictions, never inflates. | `product_accuracy_calibration.json` |


**Feature engineering highlights:**

- **Dropped**: UUPS IAP/adrev signals (27 features), IBT embeddings (208-dim), hardware stats scalars/categoricals
- **Added**: `ad_format` (interstitial vs. rewarded), `creative_id`, `creative_pack_id`, `device_orientation`, `video_orientation`, `sdk_event_name` as sparse embedding
- **Unified**: `gamer_id_scope` as a sparse feature lets one model serve both BHV (IDFA) and CTX (IDFI) traffic without separate models

**Training setup:**


| Parameter           | Value                                                                         |
| ------------------- | ----------------------------------------------------------------------------- |
| Optimizer           | AdamW, lr=0.001, weight_decay=0.05                                            |
| Embedding optimizer | AdamW, lr=0.0008                                                              |
| Batch size          | 25,600 (× 8 GPUs = 204,800 effective)                                         |
| LR scheduler        | Warmup 30% → Steady 0.001 → Decay 30% → end_lr=1e-6                           |
| `total_step`        | Computed dynamically from BQ `COUNT(*)` at runtime                            |
| Max epochs          | 50 (early stopping: patience=3, monitor=val_loss)                             |
| Train/val split     | bucket < 0.9 → train, bucket >= 0.9 → val (deterministic hash of `auctionId`) |
| Loss                | Plain BCE (not uncertainty-weighted; single-task, no balancing needed)        |


### 3.2 Offline Results

Offline evaluation was conducted on a 60-day dataset (install dates 2026-02-26 → 2026-04-26, **486M train rows / 18.7M val rows**). Model artifact: `vny2xtis3e`.

> **Note on metric comparability:** Direct loss comparison with legacy is not valid — different label definitions (CPE ~19.75% positive vs. CPI ~37%), different loss formulations (uncertainty-weighted multi-task vs. single-task BCE), different train/val splits.

**Offline performance (v11_cpe_lc train metrics at epoch 5):**


| Metric                  | v11_cpe_lc (train)            | Legacy BHV (val) | Legacy CTX (val) |
| ----------------------- | ----------------------------- | ---------------- | ---------------- |
| AUC                     | **0.9483**                    | 0.8997           | 0.8991           |
| BCE                     | **0.2047**                    | 0.3308           | 0.3313           |
| NE (window)             | **0.4119**                    | ~0.505           | ~0.506           |
| Calibration ratio       | **0.9993**                    | —                | —                |
| mean_pred vs mean_label | 0.1976 vs 0.1975 (Δ < 0.0001) | bias=0.0025      | bias=0.0031      |


**Key takeaways:**

- Strong AUC gain (+5.4pp vs. legacy) and near-perfect calibration on training data.
- Train-only AUC is not directly comparable to legacy val AUC — separate held-out time-based evaluation is required for production go/no-go.

**Known limitation — LR schedule mismatch (FIXED for subsequent runs):**

```
Root cause: lr_scheduler.total_step was hardcoded to 88 (= train_duration)
            instead of actual step count (~23,719).

Effect:     Dense-layer LR decayed to end_lr=1e-6 after only ~0.4% of training.
            Only sparse embeddings (35.3M / 36.3M params) trained at intended LR.

Fix:        workflow.py now computes total_step dynamically:
              count_rows (from BQ COUNT(*)) / (batch_size × devices) × max_epochs
```

**Key feature gaps vs. legacy (Phase 2/3 roadmap):**


| Missing Feature Group                      | Legacy Source                     | Priority                                  |
| ------------------------------------------ | --------------------------------- | ----------------------------------------- |
| UUPS IAP/adrev signals (27 features)       | UUPS pipeline (BHV only)          | High — strong purchase intent signal      |
| IBT embeddings (128d + 80d)                | External TF Hub sub-models        | High — cross-game behavioral signal       |
| Hardware stats (cpu, ram, dpi)             | DeviceAtlas enrichment at serving | Medium — partially covered by DeviceAtlas |
| Target game base counters (no time window) | BHV legacy                        | Low — 7d/24h variants present in v1_lc    |


---

## 4. Online Test

EP links:

- Shared Control (Level Complete): [EP Link] — TBD
- CPE Level Complete UL Migration (v11_cpe_lc): [EP Link] — TBD

### 4.1 Executive Summary

**Phase 1 (v11-cpe-lc-2, original dataset, 1% traffic — 2026-05-11 to 2026-05-14):**

A prediction inflation issue was discovered. The new model's average predictions were **2–56x higher** than legacy on matched campaigns:

```
Overbid distribution across 356 matched (campaign, target_game, sdk_event) triples
──────────────────────────────────────────────────────────────────────────────────
  v11 < legacy (under-bid)    |  1 campaign  (  0.3%)
  1x – 2x overbid             | 131 campaigns ( 36.8%)  ████████████████
  2x – 3x overbid             | 108 campaigns ( 30.3%)  █████████████
  3x – 5x overbid             |  89 campaigns ( 25.0%)  ███████████
  > 5x overbid                |  27 campaigns (  7.6%)  ███
──────────────────────────────────────────────────────────────────────────────────
  Median overbid: 2.33x   |   Most extreme: star5_hero_received event = 36.7x
```

**Root cause — wildcard label contamination (training data):**

```
sdk_event | Rows   | psn_label pos_rate | Ratio
──────────────────────────────────────────────────────
"*"       | 178.2M |     36.4%          |  6.1x  ← wildcard = 44% of all rows at 6x higher rate
Specific  | 224.5M |      6.0%          |  1.0x
──────────────────────────────────────────────────────
BCE minimisation drives sigmoid toward ~19.5% (blended base rate),
not the true per-event rate of ~6%.
```

**Fix:** Migrated campaign lookup to `campaigns_v3` with `archived_at IS NULL`. Wildcard positive rate dropped 35.3% → 21.3%, 51 dead-signal event types removed. Model retrained on v3 dataset as `v11-cpe-lc-4`.

---

**Phase 2 (v11-cpe-lc-4, v3 dataset, 50% traffic — 2026-05-28 to 2026-06-09):**

```
Experiment Setup
─────────────────────────────────────────────────────────
  Test     v11-cpe-lc-4   50%   Unified DLRM (BHV + CTX)
  Control  bhv1p + ctx1r  50%   Legacy BHV + CTX separate TF2 models
─────────────────────────────────────────────────────────
```

`v11-cpe-lc-4` passes all scale guardrails and delivers clear wins on both scale and quality. **Net Revenue nearly doubles (+99.4%) on Level Complete campaigns**. All-traffic Net Revenue is up +0.71% with a statistically significant positive CI.

### 4.2 Additional Insights

#### 4.2.1 Phase 1 — Prediction Inflation Analysis (v11-cpe-lc-2)

**Pattern:** Inflation ratio is inversely proportional to base event rate — rare events most severely inflated; near-ceiling events show no inflation.


| Campaign                             | SDK Event              | v11 avg_pred | Legacy avg_pred | Ratio              |
| ------------------------------------ | ---------------------- | ------------ | --------------- | ------------------ |
| `652214aefc636157750229a8`           | `star5_hero_received`  | 0.1177       | 0.0032          | **36.7x**          |
| `67dc0fa20eb345a2a13aef4f`           | `ajvip`                | 0.4889       | 0.0326          | 15.0x              |
| `69eae6280d291c5f22675e19`           | `recvd_coins_400`      | 0.7047       | 0.0645          | 10.9x              |
| `69c4447a75bdf4ae2c38cc0d`           | `pc_t2_d60_ios_custom` | 0.1692       | 0.0156          | 10.8x              |
| `create_role` event (high base rate) | `create_role`          | 0.962        | 0.940           | ~1x (no inflation) |


#### 4.2.2 Phase 2 — Scale Metrics (All Traffic)

> Source: DI Business Metrics dashboard (Statsig / DI experiment platform)


| Metric            | Lift       | 95% CI               | Significance        |
| ----------------- | ---------- | -------------------- | ------------------- |
| Impressions       | +0.14%     | (+0.08%, +0.20%)     | ✅ Positive          |
| Clicks            | +0.13%     | (+0.04%, +0.22%)     | ✅ Positive          |
| Installs          | −0.11%     | (−0.17%, −0.05%)     | ⚠ Slightly negative |
| Publisher Revenue | +0.30%     | (+0.23%, +0.37%)     | ✅ Positive          |
| Advertiser Spend  | +0.44%     | (+0.23%, +0.66%)     | ✅ Positive          |
| **Net Revenue**   | **+0.71%** | **(+0.15%, +1.29%)** | ✅ **Positive**      |


The slight install dip (−0.11%) reflects the model redistributing budget toward higher-CPE Level Complete campaigns rather than maximizing raw install volume — consistent with the LC optimization objective.

#### 4.2.3 Phase 2 — Scale Metrics (Level Complete Traffic Only)

> Source: `unity-ads-bi-prd` BigQuery — `mz_dcpi_prediction_v1` joined to `operativeecpm_installs_outcomes_contextual`

**Absolute metrics (normalized to 100% traffic):**


| Metric      | Control (bhv1p + ctx1r) | Test (v11-cpe-lc-4) | Delta      |
| ----------- | ----------------------- | ------------------- | ---------- |
| Starts      | 112,344,030             | 144,719,720         | **+28.8%** |
| Installs    | 531,098                 | 768,770             | **+44.8%** |
| Spend       | $742,042                | $1,305,386          | **+75.9%** |
| Net Revenue | $270,153                | $538,731            | **+99.4%** |
| eCPI        | $1.40                   | $1.70               | +21.5%     |


The eCPI increase (+21.5%) is expected: the test model serves higher-CPE campaigns and a broader user population (IDFA + IDFI + unspecified), so cost per install is naturally higher while delivering far greater absolute value.

#### 4.2.4 Phase 2 — Post-Install Metrics

> D0/D1 fully mature. D3 mature through 2026-06-05. D7 mature through 2026-05-31 only.

**Level Complete rate — any event** (`sum_lc_label_dx / installs`):


| Window | Control | Test   | Delta    | Verdict                        |
| ------ | ------- | ------ | -------- | ------------------------------ |
| D0     | 33.06%  | 28.48% | −4.58 pp | Expected — broader segment mix |
| D1     | 34.69%  | 29.38% | −5.31 pp | Expected                       |
| D3     | 35.96%  | 30.22% | −5.74 pp | Expected                       |
| D7     | 36.35%  | 31.01% | −5.34 pp | Expected                       |


The per-install LC rate is lower for the test model. However, per-install rate is not the right quality signal for a CPE product — what matters is whether the model delivers the **specific event the advertiser paid for, at the price they set**. The product bias on target events tells that story directly: the test model sits at −2% to +5% across D0–D7, essentially at parity with the advertiser's target CPE, while the legacy control chronically underspends at −18% to −26%. The test model is more precisely targeting the advertiser's goal, not merely acquiring users who happen to level-complete.

**Level Complete rate — target event** (`sum_target_lc_label_dx / installs`):


| Window | Control | Test   | Delta    |
| ------ | ------- | ------ | -------- |
| D0     | 22.79%  | 16.10% | −6.69 pp |
| D1     | 22.49%  | 15.88% | −6.61 pp |
| D3     | 21.84%  | 15.36% | −6.48 pp |
| D7     | 20.71%  | 14.30% | −6.41 pp |


Gap is **stable across D0–D7**, confirming this is a composition effect, not a declining quality trend.

**Model bias — any event** (`sum_pred / sum_lc_label_dx − 1`):


| Window | Control | Test       | Verdict                  |
| ------ | ------- | ---------- | ------------------------ |
| D0     | −19.0%  | **−11.7%** | ✅ Test 38% less biased   |
| D1     | −22.3%  | **−14.5%** | ✅ Test better calibrated |
| D3     | −24.1%  | **−17.0%** | ✅ Test better calibrated |
| D7     | −24.6%  | **−17.7%** | ✅ Test better calibrated |


**Model bias — target event** (`sum_pred / sum_target_lc_label_dx − 1`):


| Window | Control | Test   | Note                                                                    |
| ------ | ------- | ------ | ----------------------------------------------------------------------- |
| D0     | +17.5%  | +56.2% | Model over-predicts vs. specific-event observed rate                    |
| D1     | +19.1%  | +58.4% | Known area for improvement                                              |
| D3     | +22.6%  | +63.8% | Does NOT translate to poor advertiser outcomes (see product bias below) |
| D7     | +29.3%  | +75.9% | Calibration improvement planned for next iteration                      |


**Product bias — any event** (`(sum_cost / sum_lc_label_dx) / avg_tcpe − 1`):


| Window | Control | Test  | Verdict      |
| ------ | ------- | ----- | ------------ |
| D0     | −0.49   | −0.47 | ≈ Comparable |
| D1     | −0.50   | −0.49 | ≈ Comparable |
| D3     | −0.50   | −0.51 | ≈ Comparable |
| D7     | −0.48   | −0.49 | ≈ Comparable |


**Product bias — target event** (`(sum_cost / sum_target_lc_label_dx) / avg_tcpe − 1`):


| Window | Control | Test      | Verdict                      |
| ------ | ------- | --------- | ---------------------------- |
| D0     | −0.26   | **−0.07** | ✅ Test 3.5× closer to target |
| D1     | −0.25   | **−0.06** | ✅ Test 4× closer to target   |
| D3     | −0.23   | **−0.02** | ✅ Test near parity           |
| D7     | −0.18   | **+0.05** | ✅ Test at parity             |


This is the **strongest signal in the experiment**. The test model delivers the campaign-specific target event at a cost almost exactly matching the advertiser's target CPE (−7% to +5% across D0–D7), while the legacy control consistently underspends by 18–26%. The legacy models' persistent underspend indicates they were systematically under-delivering for advertisers even while appearing efficient on paper.

#### 4.2.5 Monitoring Plan

**Short-term:**


| Signal                            | Target                                                    | How to Check                                                                            |
| --------------------------------- | --------------------------------------------------------- | --------------------------------------------------------------------------------------- |
| Prediction calibration            | Median overbid ratio < 1.5x                               | `avg(app_event_p)` vs. observed conversion rate in `mz_dcpi_prediction_v1` per campaign |
| Per-event prediction distribution | `avg_pred` within 2x of observed `psn_pos_rate` per event | Track top-20 SDK events by row count                                                    |
| Scale guardrails                  | Spend/installs/net revenue in line with baseline          | Monitor vs. legacy bhv1p/ctx1r                                                          |
| Zero valuation rate               | Consistent with legacy (legacy: 2–32% per campaign)       | Compare v11-cpe-lc zero-val rate to legacy                                              |


**Long-term:**


| Item                                                               | ETA                    |
| ------------------------------------------------------------------ | ---------------------- |
| UUPS IAP/adrev signal integration (27 signals)                     | Phase 2 (Q3)           |
| Stage 5 filter re-enablement                                       | Post-E2E stabilization |
| Enable calibration (`enable_calibration: true`) or Platt scaling   | Post-E2E stabilization |
| `campaign_id` → `campaignset_id` fix                               | Next datagen version   |
| Target event model bias reduction (specific SDK event calibration) | Next model iteration   |


---

## 5. Launch Preparation

### 5.1 Automated Workflow

The model runs daily via Metaflow on Vertex AI, scheduled at **21:00 UTC**:

```
Daily Automated Workflow  (cron: 0 21 * * *)
─────────────────────────────────────────────────────────────────────────────
  run_datagen
    │  Spark batch: reads latest 60-day window from v2/level_complete/d7
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
    │  K8s job, 8× RTX PRO 6000 Blackwell
    │  Computes total_step dynamically from BQ COUNT(*)
    │  Train: bucket < 0.9 / Val: bucket >= 0.9
    │  Timeout: 18 hours
    ▼
  model_publish
    │  Publishes artifact to model store
    ▼
  refresh_calibration
    │  Queries last 14 days of live traffic from BQ
    │  Writes product_accuracy_calibration.json to GCS
    │  (no-op on first deploy — factor=1.0 for all campaigns)
    ▼
  model_deploy
     Triton deploy (CPU, packed input, static shape)
     Uploads to staging + production
─────────────────────────────────────────────────────────────────────────────
```

### 5.2 Code Changes Merged to Main


| File                     | Change                                                                                                                                             |
| ------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------- |
| `unified_cpe_datagen.py` | Campaign lookup → `campaigns_v3`, `archived_at IS NULL` filter, multi-event explode (Path B fix)                                                   |
| `workflow.py`            | Dynamic `lr_scheduler.total_step` from BQ `COUNT(*)`; Spark BigQuery project property added; `refresh_calibration` step added                      |
| `features.py`            | `sdk_event_name` as online sparse embedding; `prob_sdk_event_name` + `model_name` moved to offline-only                                            |
| `model.py`               | `DeployModel` with eligibility gate (Mechanism 1) + product accuracy calibration (Mechanism 2); plain BCE loss; BatchNorm + Dropout regularization |
| `config.json`            | Single-task PSN configuration; `model_variant: 4`                                                                                                  |


### 5.3 Open Items Before Wider Rollout


| Item                                                                                     | Status                                | Owner        |
| ---------------------------------------------------------------------------------------- | ------------------------------------- | ------------ |
| Retrain on v3 (fixed) dataset                                                            | **DONE** — deployed as `v11-cpe-lc-4` | Yabo Ling    |
| Verify `sdk_event_name` online feature population in Go serving layer                    | TODO                                  | Serving team |
| Enable calibration (`enable_calibration: true` or Platt scaling)                         | TODO                                  | Yabo Ling    |
| Fix `campaign_id` → `campaignset_id`                                                     | TODO                                  | Yabo Ling    |
| Re-enable `filter_min_dates_by_game_and_event` (Stage 5)                                 | TODO                                  | Yabo Ling    |
| Migrate experiment from `unified_cpe/` to `unified_user_value/` (aligned with UV family) | Planned (post-E2E)                    | Yabo Ling    |


---

## 6. Next Steps and Meeting Notes

**AIs:**

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


|                      | Option 1: Row expansion (chosen)       | Option 2: Per-element array loss           |
| -------------------- | -------------------------------------- | ------------------------------------------ |
| **Data format**      | One row per (install × targeted event) | One row per install, array labels          |
| **Label format**     | Scalar float per row                   | `array<float>` per row                     |
| **Architecture fit** | Perfect (list_len=1 scalar)            | Requires EmbeddingBag → attention redesign |
| **Data size**        | ~5× (1–5 events per game average)      | 1×                                         |
| **Risk**             | Low                                    | High                                       |


**Decision: Option 1 (row expansion).** The `bucket` column (deterministic hash of `auctionId`) ensures all expanded rows from the same install land in the same train/val split partition — no data leakage.

### A.2 Legacy vs. New Label Semantics


| Aspect                 | NEW `unified_user_value.v11_cpe_lc`           | Legacy `ads-audience-pinpointer`            |
| ---------------------- | --------------------------------------------- | ------------------------------------------- |
| Label type             | Deterministic, computed at datagen time       | Stochastic, sampled per training step       |
| Training label         | `prob_sdk_event_name_label` (scalar 0/1)      | `probabilistic_labels` (float array)        |
| SDK event conditioning | 1 row per (install × sdk_event)               | 1 row per install, array of labels          |
| Row inflation          | ~5× (explode by sdk_event)                    | 1× (no explode)                             |
| Wildcard handling      | `sdk_event='*'` → label=1 if `app_event_w1=1` | Wildcard `*` treated as matching all events |
| Reproducibility        | Deterministic — same data every epoch         | Stochastic — different sample per epoch     |


### A.3 Architecture Dimension Derivation

```
num_sparse_embs   = 18 (individual_sparse, repeat=1)
dense_to_sparse   = dense_embedding_dim(64) // sparse_embedding_dim(32) = 2
total_embs        = 18 + 2 = 20

cross_dense_sparse = 20 × dot_product_compress_dim(16) = 320
dense_repr        = dense_tower_mlp[-1] = 128
shared_bottom_in  = 320 + 128 = 448  ← matches config shared_bottom_mlp[0] = 448  ✓

shared_bottom_out = shared_bottom_mlp[-1] = 256
PSN head input    = 256
PSN head layers   = [256 → 512 → 1]
Total params      = ~36.3M (35.3M sparse embeddings + 1.0M dense)
```

### A.4 Feature Comparison: Legacy BHV + CTX vs. v11_cpe_lc

#### Summary Counts


| Category                    | BHV (`bhv1p`)  | CTX (`ctx1r`)  | UL `v11_cpe_lc`                   |
| --------------------------- | -------------- | -------------- | --------------------------------- |
| Sparse/categorical (active) | ~17            | ~9             | **18**                            |
| Dense scalars (active)      | 13             | 15             | **16** (1 LC + 15 AGC)            |
| UUPS IAP features           | **30+**        | **100+**       | None                              |
| Hardware enrichments        | 6              | 6              | None                              |
| SensorTower enrichments     | None           | **30+**        | None                              |
| Apptopia enrichments        | None           | **12**         | None                              |
| IBT sub-network embeddings  | 2 (128+80 dim) | 2 (128+80 dim) | None                              |
| Online bidding features     | None           | None           | **2** (max_cost, discount_factor) |


#### Shared Features (in all three models)


| Feature                                    | Type   |
| ------------------------------------------ | ------ |
| `geolocation_country`                      | sparse |
| `platform`                                 | sparse |
| `device_connection_type`                   | sparse |
| `device_type`                              | sparse |
| `publisher_store_id`                       | sparse |
| `publisher_developer_id`                   | sparse |
| `gamer_click_count`                        | dense  |
| `gamer_install_count`                      | dense  |
| `gamer_start_count`                        | dense  |
| `gamer_view_count`                         | dense  |
| `gamer_start_count_in_last_24_hours`       | dense  |
| `gamer_start_count_in_last_7_days`         | dense  |
| `target_game_start_count`                  | dense  |
| `target_game_start_count_in_last_24_hours` | dense  |
| `target_game_view_count`                   | dense  |
| `target_game_start_count_in_last_7_days`   | dense  |
| `target_game_view_count_in_last_24_hours`  | dense  |
| `target_game_view_count_in_last_7_days`    | dense  |


#### Features Re-activated or Promoted in UL


| Feature                | BHV                            | CTX      | UL                           | Note                                    |
| ---------------------- | ------------------------------ | -------- | ---------------------------- | --------------------------------------- |
| `audience_id`          | active                         | disabled | active                       | Re-enabled in UL                        |
| `target_game_id`       | active                         | disabled | active                       | Re-enabled in UL                        |
| `publisher_game_id`    | active                         | disabled | active                       | Re-enabled in UL                        |
| `creative_id`          | N/A                            | disabled | active                       | New in UL                               |
| `ad_type`              | N/A                            | disabled | active                       | New in UL                               |
| `gamer_creation_delay` | disabled                       | active   | active                       | Was disabled in BHV                     |
| `sdk_event_name`       | metadata only (not in network) | absent   | **active sparse (hash=10k)** | Key new feature — first-class embedding |


#### New Features in UL (not in legacy)


| Feature               | Type                          | Purpose                                                                 |
| --------------------- | ----------------------------- | ----------------------------------------------------------------------- |
| `gamer_id_scope`      | sparse                        | IDFA / IDFI / unspecified — enables unified model to serve all segments |
| `ad_format`           | sparse                        | Richer creative context                                                 |
| `video_orientation`   | sparse                        | Richer creative context                                                 |
| `device_orientation`  | sparse                        | Richer creative context                                                 |
| `creative_pack_id`    | sparse                        | Creative-level signal                                                   |
| `target_store_id`     | sparse                        | Was offline/metadata in legacy; now active embedding                    |
| `max_cost`            | online-only                   | Bidding formula: `cost = max_cost × discount_factor × p × gate`         |
| `discount_factor`     | online-only                   | Bidding formula                                                         |
| `prob_sdk_event_name` | offline-only sparse (hash=1M) | `"{target_game_id}_{sdk_event_name}"` composite game+event-level signal |


#### Features Dropped in UL

**UUPS IAP User Value Features**

BHV had d7/d30 windows (attributed + unattributed + uasdk) = 30+ features. CTX had d7→d180 across 7 windows with rate_of_purchase, hours_since_last_purchase = 100+ features. UL has none — the UUPS pipeline is not joined into the CPE datagen.


| UUPS group                            | BHV     | CTX     | UL   |
| ------------------------------------- | ------- | ------- | ---- |
| `uups_*_iap_done_dx` (binary flags)   | d7, d30 | d7→d180 | None |
| `uups_*_iap_total_count_dx`           | d7, d30 | d7→d180 | None |
| `uups_*_iap_nonzero_log_avg_value_dx` | d7, d30 | d7→d180 | None |
| `uups_*_unique_games_with_iaps_dx`    | d7, d30 | d7→d180 | None |
| `uups_*_rate_of_purchase_dx`          | None    | d7→d180 | None |
| `uups_*_hours_since_last_purchase_dx` | None    | d180    | None |
| `uups_adrev_oecpm_`* (ad revenue)     | d7, d30 | None    | None |


**Device Hardware Enrichments**


| Feature                                    | BHV    | CTX    | UL   |
| ------------------------------------------ | ------ | ------ | ---- |
| `hardware_stats_cpu_count`                 | active | active | None |
| `hardware_stats_ram`                       | active | active | None |
| `hardware_stats_dpi`                       | active | active | None |
| `hardware_stats_cpu/gpu/res` (categorical) | active | active | None |


> `deploy_config` includes `"enrichments": ["device_atlas"]` — raw `device_type` is available but hardware lookup features are not used by the model.

**SensorTower Store Intelligence (CTX only → dropped)**

CTX had 30+ SensorTower enrichments: source/target demographics (age, gender), game profiles (category, genre, contains_ads), retention (D1/D3/D7/D14/D90), session engagement (count/duration/time-spent per day/week/month). None are in UL.

**Apptopia Store Intelligence (CTX only → deferred to Phase 2)**

CTX had 12 Apptopia features: source/target category, subcategory, iap flag, price, size, rating. The CPE datagen does not yet join Apptopia data — noted as Phase 2 work in `features.py`.

**IBT Sub-Network Embeddings (both models → dropped)**


| Embedding                                                   | BHV    | CTX    | UL   |
| ----------------------------------------------------------- | ------ | ------ | ---- |
| `ibt_embedding` (128-dim) — ad request install history      | active | active | None |
| `install_ibt_embedding` (80-dim) — installed store sequence | active | active | None |


These were learned TF sub-networks encoding a user's install sequence. Replaced in UL by the DLRM dot-product attention mechanism over individual sparse embeddings.

**Privacy / Consent Features (CTX only → dropped)**


| Feature                                             | BHV                  | CTX               | UL   |
| --------------------------------------------------- | -------------------- | ----------------- | ---- |
| `gamer_limited_tracking` → `limited` embedding      | None                 | active            | None |
| `gamer_has_opted_out` → `opt_out_enabled` embedding | None                 | active            | None |
| `publisher_is_coppa_targeted`                       | raw (not in network) | `coppa` embedding | None |


**Other CTX-specific Features Dropped**


| Feature                                           | Note                                               |
| ------------------------------------------------- | -------------------------------------------------- |
| `target_developer_id`                             | CTX had this; UL only has `publisher_developer_id` |
| `counters_source`                                 | CTX-specific imputation routing flag               |
| `device_sdk_version` / `device_sdk_major_version` | CTX only                                           |
| `target_game_click_count` / `_in_last_7_days`     | CTX had all-time + 7d; UL/BHV only have 24h        |


#### Key Observations

1. **UUPS is the biggest feature gap.** BHV and CTX both relied heavily on UUPS IAP signals to characterize user LTV propensity. UL v11_cpe_lc has none — it optimizes directly on the LC label without user purchase history. Adding UUPS to the CPE datagen is a clear next-iteration opportunity.
2. `**sdk_event_name` is the critical upgrade.** Legacy BHV passed it as routing metadata but never embedded it. UL makes it a first-class sparse feature (hash=10k), letting the model learn per-event-type propensity. This is the primary enabler of the +99.4% LC net revenue gain.
3. `**gamer_id_scope` enables segment unification.** BHV served only IDFA; CTX served IDFI/unspecified. The new `gamer_id_scope` embedding teaches the unified model the difference, replacing the hard segment split.
4. **Apptopia and SensorTower are deferred, not forgotten.** CTX had rich third-party game store intelligence. The CPE datagen does not yet join these — noted as Phase 2 work in `features.py`.
5. **IBT sequence embeddings traded for architectural simplicity.** The 128+80 dim TF sub-networks (encoding user install history) are absent. DLRM's dot-product attention over `publisher_game_id`, `creative_id`, `target_game_id` etc. provides related cross-feature signal via a different mechanism.

---

### A.5 Top 10 Most Inflated Campaigns (Phase 1 Online Test)


| Campaign ID                | SDK Event              | v11 avg_pred | Legacy avg_pred | Ratio     |
| -------------------------- | ---------------------- | ------------ | --------------- | --------- |
| `652214aefc636157750229a8` | `star5_hero_received`  | 0.1177       | 0.0032          | **36.7x** |
| `67dc0fa20eb345a2a13aef4f` | `ajvip`                | 0.4889       | 0.0326          | 15.0x     |
| `69eae6280d291c5f22675e19` | `recvd_coins_400`      | 0.7047       | 0.0645          | 10.9x     |
| `69c4447a75bdf4ae2c38cc0d` | `pc_t2_d60_ios_custom` | 0.1692       | 0.0156          | 10.8x     |
| `6960733f13cc68bc8f91fc8e` | `ajvip`                | 0.6445       | 0.0731          | 8.8x      |
| `6825d515a47ee6e329c70bdd` | `eventW`               | 0.5920       | 0.0688          | 8.6x      |
| `685e72777dd83b9c8536915e` | `eventw`               | 0.4666       | 0.0575          | 8.1x      |
| `686664ce9dfaacc5e24bf3df` | `ajvip`                | 0.4776       | 0.0605          | 7.9x      |
| `684ac40f6da6f407ddfa47fd` | `d7_puzzle60_hint5`    | 0.6146       | 0.0806          | 7.6x      |
| `698c51a4e63287f25051d95c` | `ajvip`                | 0.4619       | 0.0612          | 7.6x      |


