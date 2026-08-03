# CPE Models Science Oncall SOP

**Point of contacts:** @UV devs
**Public channel:** #ads-ml-science-oncall
**Private channel:** [#vector-user-value-dev](https://unity.enterprise.slack.com/archives/C06Q5D269DZ), [#vector-cpe](https://unity.enterprise.slack.com/archives/C09M1ESSNMT)
**Alert channel:** [#ads-ul-alerts-general](https://unity.enterprise.slack.com/archives/C050WP149S8)
**Incident channel tracker:** [#sre-announce](https://unity.enterprise.slack.com/archives/C8ZHSNSAY)

**Related SOPs:**
- [User Value Model Science On-Call SOP](https://docs.google.com/document/d/1GTlMIGKidVmWXOUEb5s_6gecjDa0bJjMP1IUEnGz_xM/edit?usp=sharing) — Retention and Payer share the same model as UV; most UV SOP procedures apply directly
- [Understanding Event Optimization Models](https://docs.google.com/document/d/1AI_HzvMuilbOz5kynasjk1IJpn7h2MIlZYbxVVh17Vg/edit?usp=sharing)
- [Blocklist usage SOP](https://github.com/Unity-Technologies/ads-event-blocklist/blob/master/usage.md)
- [Blocklist sample queries](https://docs.google.com/document/d/10plHDewMOrOS5c4w4THBWesBljsDoDTFA4MZDl12gSA/edit?usp=sharing)

---

# 1. Purpose

This SOP covers oncall procedures for CPE (Cost-Per-Engagement) models, which support three campaign types:

- **CPE - Retention**: predict P(user retained at Day 7 after install)
- **CPE - Purchase/Payer**: predict P(user makes a purchase within first week after install)
- **CPE - Level Complete**: predict P(user completes a targeted SDK event within first week after install)

Retention and Payer share the same model artifact as UV (`v3_q3a`). Level Complete has its own dedicated model (`v11_cpe_lc_v2`). This SOP assumes familiarity with the UV Model Oncall SOP and focuses on CPE-specific differences.

---

# 2. Model Quick Reference

| | CPE-Retention | CPE-Payer | CPE-Level Complete |
|---|---|---|---|
| **Experiment** | `unified_user_value.v3_q3a` | `unified_user_value.v3_q3a` | `unified_user_value.v11_cpe_lc_v2` |
| **Serving head** | `main_retention_d7` | `main_payer_d7` | `prob_sdk_event_name_label` |
| **Production pipeline** | [unified-user-value-v3-q3a-10-workflow-scheduled](https://console.cloud.google.com/agent-platform/pipelines/locations/us-central1/schedules/5183187973289541632?project=unity-applied-research-ml-test) | same as Retention | [user-value-v11-cpe-lc-v2-1-workflow-scheduled-15-utc](https://console.cloud.google.com/agent-platform/pipelines/locations/us-central1/schedules/75050464688734208?project=unity-applied-research-ml-test) |
| **Schedule (UTC)** | 22:00 UTC daily | same as Retention | 15:00 UTC daily |
| **Code branch** | [prd-v3-twr-q3a](https://github.com/Unity-Technologies/vector-ai-unity-learner/tree/prd-v3-twr-q3a) | same as Retention | [level_complete-migration-v2](https://github.com/Unity-Technologies/vector-ai-unity-learner/pull/4955) |
| **Deploy device** | CUDA (GPU) | CUDA (GPU) | CPU only |
| **Training data** | Same as UV (`uv_v26_q2a_mesh_v2lf`) | Same as UV | Standalone LC source ([`v11_cpe_lc_v2`](https://console.cloud.google.com/bigquery?project=unity-ads-dd-ds-dev-prd&ws=!1m6!1m5!4m3!1sunity-ads-dd-ds-dev-prd!2sunified_user_value_v11_cpe_lc_v2!3sunified_user_value_v11_cpe_lc_v2_preprocessed_combined!23sRESOURCE_LIST))|

---

# 3. Daily Monitoring

## 3.1 CPE Business Performance

Use [Imply - Demand Supply Internal](https://internal-v2-1.pivot.int-prd-imply.unity3d.com/pivot/d/a3852db2088cad946e/uAds_Demand_Supply_Internal_(billing_&_finance)) to monitor CPE performance:
- Filter: **Campaign Type == `appEventConversion`**
- Sub-CPE breakdown (Retention / Payer / Level Complete) is under the **`App Events Campaign`** dimension

Check WoW trends. If there is a drop or spike, confirm with Wo2W and Wo3W before triggering a larger investigation (WoW can be misleading around holidays or prior incidents).

## 3.2 Model Prediction Health

Use this BQ query to check CPE model predictions (average predicted probability and average adjusted bid), broken down by event type and model version:

```sql
SELECT
  submit_date,
  body.app_event_type,
  CASE body.app_event_type
    WHEN 'level_complete' THEN body.model_versions.level_complete.version
    WHEN 'purchase'       THEN body.model_versions.purchase.version
    WHEN 'retention'      THEN body.model_versions.retention.version
  END AS cpe_model_version,
  MAX(body.target_game_id)  AS target_game_id,
  COUNT(*)                  AS start_count,
  AVG(body.app_event_p)     AS avg_cpe_pred,
  AVG(body.app_event_adj)   AS avg_cpe_adj
FROM `unity-ai-data-prd.mz_dcpi_raw.mz_dcpi_prediction_v1`
WHERE submit_date BETWEEN "{start_date}" AND "{end_date}"
  AND body.ar_ts >= "{start_date} 00:00:00"
  AND body.app_event_type IN ('level_complete', 'purchase', 'retention')
  AND body.app_event_p > 0
  -- AND body.target_game_id IN ({target_game_id})
  -- AND body.campaign_id = "{campaign_id}"
GROUP BY submit_date, body.app_event_type, cpe_model_version
ORDER BY submit_date
```

Use the [UV prediction skill](https://github.com/Unity-Technologies/vector-ai-unity-learner/blob/uv-prediction-doc/.claude/skills/uv-prediction-check/uv-prediction-report.md) to generate a full UV model prediction report (covering both ROAS and CPE) for a target game or campaign ID across any timeframe.

## 3.3 Production Pipeline Failures

Check [#ads-ul-alerts-general](https://unity.enterprise.slack.com/archives/C050WP149S8) for pipeline failure alerts.

- Single failure: common, not cause for concern.
- Same pipeline failing **2+ times in a row**: investigate.
- Failures interlaced with successes: likely infra instability — escalate to MLEs (@vector-offline-oncall).

---


# 4. CPE-Retention and CPE-Payer

## 4.1 Overview

Retention and Payer are served by the **same model artifact as UV** (`unified_user_value.v3_q3a`). The model produces predictions from multiple task heads simultaneously:

- `main_retention_d7` → CPE-Retention bid
- `main_payer_d7` → CPE-Payer bid
- `main_iap_d7/d28`, `main_adrev_d0/d7/d28` → UV (ROAS) bids

**Any issue with the v3_q3a pipeline affects UV, Retention, and Payer together.**

## 4.2 Data

- **Training label (Retention):** `post_install_retention_d7`
- **Training label (Payer):** `post_install_deposit_capped_count_d7`
- **Incremental dataset:** [unity-ads-dd-ds-prd.user_value_incremental_datagen.uv_v26_q2a_mesh_v2lf](https://console.cloud.google.com/bigquery?project=unity-ads-dd-ds-dev-prd&ws=!1m6!1m5!4m3!1sunity-ads-dd-ds-prd!2suser_value_incremental_datagen!3suv_v26_q2a_mesh_v2lf)

### Check Retention label distribution

```sql
SELECT
  date,
  source,
  COUNT(date) AS installs,
  AVG(IF(post_install_retention_d7 > 0, 1, 0)) AS retention_rate_d7
FROM `unity-ads-dd-ds-prd.user_value_incremental_datagen.uv_v26_q2a_mesh_v2lf`
WHERE date >= '2026-01-01'
  AND target_game_id = '{target_game_id}'
GROUP BY date, source
ORDER BY date, source
```

### Check Payer label distribution

```sql
SELECT
  date,
  source,
  COUNT(date) AS installs,
  SUM(post_install_deposit_capped_count_d7) AS purchase_count,
  SUM(IF(post_install_deposit_capped_count_d7 > 0, 1, 0)) AS payer_count,
  AVG(IF(post_install_deposit_capped_count_d7 > 0, 1, 0)) AS payer_rate
FROM `unity-ads-dd-ds-prd.user_value_incremental_datagen.unified_user_value_latest_prd`
WHERE date >= '{start_date}' AND date <= '{end_date}'
  AND audience_id IN ('{audience_id}')
GROUP BY date, source
ORDER BY date, source
```

## 4.3 Workflow Failures

Since v3_q3a uses `UserValueWorkflow` (identical to UV), **follow the UV SOP** for all pipeline issues. The workflow steps are:

```
check_raw_data → update_mappings → datagen → combine → semantic_store_id_embedding → train → publish → ooc → deploy
```

Key CPE-specific notes:
- **OOC step** is enabled with `model_variants=["10"]`. OOC failures block deployment.
- **Combine memory** is bumped (`executor.memory=14g`, `driver.memory=16g`) to handle backfill scale.

To rerun:
```bash
ul-cli workflow --experiment=unified_user_value.v3_q3a --wandb-key="{key}"
```

Or use the `/rerun-uv-workflow` skill.

## 4.4 Blocklisting

CPE-Retention and CPE-Payer **share the same blocklist table as UV**, but use different `event_type` values:

```
event_type in blocklist table  →  traffic type in UV model
"Purchase"                     →  "iap"
"AdRev"                        →  "adrev"
"Retention"                    →  "retention"
"Payer"                        →  "payer"
```

Follow the [blocklist SOP](https://github.com/Unity-Technologies/ads-event-blocklist/blob/master/usage.md) and use the [sample queries doc](https://docs.google.com/document/d/10plHDewMOrOS5c4w4THBWesBljsDoDTFA4MZDl12gSA/edit?usp=sharing) to block any game.

To check if a game is already blocked:
```sql
SELECT *
FROM `unity-ads-dd-ds-prd.app_datagen.blacklist_control`
WHERE target_game_id = {target_game_id}
```

---

# 5. CPE-Level Complete (`v11_cpe_lc_v2`)

## 5.1 Overview

The Level Complete model predicts P(user completes a specific campaign-targeted SDK event within 7 days of install). It was migrated from `ads-audience-pinpointer` (legacy TF `level_complete_bhv` + `level_complete_ctx`).

**Key differences from UV/v3_q3a:**
- Standalone data pipeline (not shared with UV)
- CPU-only deployment (no GPU)
- Single-task binary classifier (plain BCE loss)
- Custom workflow (not `UserValueWorkflow`)
- Contains two serving mechanisms: eligibility gate + product accuracy calibration
- **3–8% zero valuation rate** is expected due to the eligibility gate (see Section 7.5)

## 5.2 Data

| Property | Value |
|---|---|
| **Source path** | `gs://unity-ads-dd-ds-prd-data-anon/app-events/data/ads.events.operativeecpm.installs.outcomes.v2/level_complete/d7/` |
| **Partition key** | `installDate=YYYY-MM-DD` |
| **Training window** | 88 days |
| **Label** | `prob_sdk_event_name_label` = 1 if user fired the targeted SDK event AND `app_event_w1 > 0`, else 0 |
| **Positive rate** | ~14% |
| **Preprocessed output** | `gs://unity-ads-dd-ds-prd-incremental-training-data/user_value/unified_user_value.v11_cpe_lc_v2/preprocessed_combined/` |
| **Feature mapping** | `gs://unity-ads-dd-ds-prd-incremental-training-data/user_value/unified_user_value.v11_cpe_lc_v2/feature_mapping.json` |

**Row design:** Each install is expanded to one row per `(install × targeted SDK event)`. Wildcard campaigns (no specific target event) get `sdk_event_name = "*"`.

**Game-level quality gate:** Only games with ≥ 50 positive `psn_label` rows within the training window are included. This mirrors the legacy eligibility filter.

### Check training label distribution for a specific game/campaign

```sql
SELECT
  install_date,
  sdk_event_name,
  AVG(prob_sdk_event_name_label) AS avg_psn_label
FROM `unity-ads-dd-ds-dev-prd.unified_user_value_v11_cpe_lc_v2.unified_user_value_v11_cpe_lc_v2_preprocessed_combined`
WHERE target_game_id = '{target_game_id}'
  -- AND campaign_id = '{campaign_id}'
GROUP BY install_date, sdk_event_name
ORDER BY install_date
```

## 5.3 Workflow Steps

```
run_datagen → update_mappings → create_bq_table → model_train → model_publish → [refresh_calibration — SKIPPED] → model_deploy
```

| Step | Description | Timeout | Notes |
|---|---|---|---|
| **run_datagen** | Spark job reading 88-day LC source, writes `preprocessed_combined/date={train_end}/` | 8 hours | Detects latest `installDate=` partition automatically |
| **update_mappings** | Builds `feature_mapping.json` and `trained_game_sdk_combo.json` (eligibility gate) | 1 hour | Lightweight Spark; reads only categorical columns |
| **create_bq_table** | Creates BQ external table pointing at preprocessed_combined | ~2 min | Idempotent — safe to rerun |
| **model_train** | Trains on 8×G4, up to 50 epochs with early stopping (`patience=3` on `val_loss`) | 18 hours | `total_step` for LR schedule computed dynamically from row count |
| **model_publish** | Publishes trained model to model store | ~5 min | Standard step |
| **refresh_calibration** | Refreshes `product_accuracy_calibration.json` | — | Currently `@skip_step` (disabled) |
| **model_deploy** | CPU-only deploy (`device=cpu`, `model_variant=1`) | ~30 min | No GPU node needed; enrichment: `hardware_stats` only |

To rerun:
```bash
ul-cli workflow --experiment=unified_user_value.v11_cpe_lc_v2 --wandb-key="{key}"
```

## 5.4 Training Metrics

Monitored via `cpe_lc_v2_metrics_callback` in W&B ([wandb.ai/unity-labs-ai-research/ads-unified-learner](https://wandb.ai/unity-labs-ai-research/ads-unified-learner)):

| Metric | Healthy range | Notes |
|---|---|---|
| `val_loss` | Decreasing | Early stopping trigger; stops at patience=3 |
| `val_auc` | > 0.90 (reference: 0.9483 at launch) | AUC for PSN label |
| `val_ne` | < 1.0 | NE < 1.0 = model beats base rate |
| `val_pred_bias` | Near 0 | `mean(pred) − mean(label)`; positive = over-predicting |
| `calibration_psn` | Near 1.0 | Online calibration ratio |

## 5.5 Serving Mechanisms

### Mechanism 1: Eligibility Gate

The model **only bids on `(target_game_id, sdk_event_name)` pairs** it was trained on with at least one positive PSN label. All other combinations produce `cost = 0`.

**How it works:**
- Built during `update_mappings` step → written to `trained_game_sdk_combo.json`
- At serving time: `gate_tensor[target_game_id_idx, sdk_event_name_idx]` = 1.0 (allowed) or 0.0 (gated)
- **Wildcard campaigns** (`sdk_event_name = ""`): Go layer sends empty string → preprocessor maps to `UNKNOWN_INT=5` → model remaps index 5 to `"*"` vocab entry. If `"*"` is missing from the vocab, wildcard campaigns are gated to zero.

Example `trained_game_sdk_combo.json`:
```json
"500037794_af_level14": 1.0,
"500037795_af_level11": 1.0,
"500037795_af_level30": 1.0,
"500035432_*": 1.0  // wildcard: game has empty or multiple target events
```

GCS path: [trained_game_sdk_combo.json](https://console.cloud.google.com/storage/browser/_details/unity-ads-dd-ds-prd-incremental-training-data/user_value/unified_user_value.v11_cpe_lc_v2/trained_game_sdk_combo.json)

**Expected behavior:** 3–8% zero valuation rate from gated combos is normal.

### Mechanism 2: Product Accuracy Calibration

Per-campaign correction factor: `observed_rate / predicted_rate`, clamped to `[0.05, 1.0]` (only shrinks predictions, never inflates; max 20× suppression).

- Controlled by `deploy_config.enable_product_accuracy_calibration` (currently `false`)
- When disabled: factor = 1.0 for all campaigns
- GCS path: `product_accuracy_calibration.json` (same prefix as `feature_mapping.json`)

### Bidding formula

```
p_raw        = sigmoid(model output)
calib_factor = calibration_tensor[audience_id]   # 1.0 when calibration disabled
gate         = gate_tensor[target_game_id, sdk_event_name]   # 0.0 or 1.0
p            = clamp(p_raw × calib_factor, 0, 1)
cost         = clamp(max_cost × discount_factor × p × gate, 0, MAX_MICRODOLLARS)
```

`max_cost` = advertiser's target CPE; `discount_factor` = BBB budget discount (1.0 = no discount).

---

# Appendix 0 — Investigation Scenarios

## A. Campaign spend dropped (Retention / Payer)

**Step 1:** Check if the game is blocklisted:
```sql
SELECT * FROM `unity-ads-dd-ds-prd.app_datagen.blacklist_control`
WHERE target_game_id = {target_game_id}
```

**Step 2:** Check model prediction stability:
```sql
SELECT
  submit_date,
  body.app_event_model_version,
  AVG(body.app_event_p) AS pred,
  AVG(body.max_cst) AS target_cpe,
  AVG(body.cst) AS cost,
  AVG(body.discount_factor) AS discount_factor
FROM `unity-ai-data-prd.mz_dcpi_raw.mz_dcpi_prediction_v1`
WHERE submit_date BETWEEN '{start_date}' AND '{end_date}'
  AND body.target_game_id = {target_game_id}
  AND body.app_event_p > 0
  AND body.app_event_type IN ('retention', 'purchase')  -- pick one
GROUP BY submit_date, body.app_event_model_version
ORDER BY submit_date
```

**Step 3:** Check training label distribution (Section 6.2 queries).

**Key insight from past cases:**
- If `avg_cpe_pred` is stable but `avg_cost` dropped → check if advertiser lowered their `tCPE` (max_cost). Cost = max_cost × discount_factor × p × gate; if max_cost drops, so does cost. This is **expected behavior, not a model issue**.
- If both prediction and cost are stable → the issue is likely advertiser-side (budget cap, campaign pause, tCPE change).

**Real examples:**
- **Big Win Pick (800084221):** Cost dropped on July 14 — aligned with advertiser reducing tCPE on July 13. Payer model prediction was stable throughout. Cost recovered when advertiser raised tCPE on July 19.
- **Egypt Path (800078681):** Cost dropped on July 11 — aligned with advertiser reducing tCPE on July 11. Payer model prediction was stable.

## B. Retention rate dropping over time (Retention)

**Symptom:** Advertiser reports declining D7 retention rate post-install.

**Check model accuracy:** Use the [IAP/Retention Accuracy Looker](https://unitytech.looker.com/dashboards/8317) to verify model bias is within tolerance (±20% for IAP, ±10% for AdRev; similar bands for retention).

**Check training label distribution:**
```sql
SELECT
  date,
  source,
  COUNT(date) AS installs,
  AVG(IF(post_install_retention_d7 > 0, 1, 0)) AS retention_rate_d7
FROM `unity-ads-dd-ds-prd.user_value_incremental_datagen.uv_v26_q2a_mesh_v2lf`
WHERE date >= '2026-01-01'
  AND target_game_id = '{target_game_id}'
GROUP BY date, source
ORDER BY date, source
```

**Key insight:** Early in a campaign, D7 retention rate may appear very high (e.g., >30%) due to small sample size (a few hundred installs). As the campaign scales, the rate converges to the true population average (typically 18–20%). This is **not a model degradation** — the model is stable.

**Real example:**
- **Matrix4Games (500237245):** Retention D7 started at >30% (unreliable — small sample) and declined as campaign scaled to 18–20%. Model bias was stable throughout (confirmed via Looker). The decline was a regression-to-mean artifact of campaign scaling, not a model issue.

## C. Campaign spend dropped sharply (Retention — cannot scale)

**Real example:**
- **500137583:** Cannot scale CPE-Retention. [Slack thread](https://unity.slack.com/archives/C0A5161FFGB/p1777996825412319)
- **500197520:** Spend dropped sharply on 2026-04-16.

**Investigation checklist:**
1. Check blocklist (see query above)
2. Check if game data exists in UV datagen:
```sql
SELECT
  date,
  COUNT(date) AS installs,
  AVG(IF(post_install_retention_d7 > 0, 1, 0)) AS retention_rate_d7
FROM `unity-ads-dd-ds-prd.user_value_incremental_datagen.uv_v26_q2a_mesh_v2lf`
WHERE date >= '2026-01-01'
  AND target_game_id = '{target_game_id}'
GROUP BY date
ORDER BY date
```
3. Check if the game has no unattributed data (some games only send MMP-attributed data)
4. Check model prediction using the dCPI prediction query in Section 3.2

## D. Level Complete campaign with zero bids / zero starts

**Symptom:** Campaign shows 0 starts or near-zero spend.

**Step 1:** Check blocklist:
```sql
SELECT * FROM `unity-ads-dd-ds-prd.app_datagen.blacklist_control`
WHERE target_game_id = {target_game_id}
```

**Step 2:** Check if the `(target_game_id, sdk_event_name)` combo is in the eligibility gate:
```bash
gsutil cat gs://unity-ads-dd-ds-prd-incremental-training-data/user_value/unified_user_value.v11_cpe_lc_v2/trained_game_sdk_combo.json \
  | python3 -c "
import json, sys
d = json.load(sys.stdin)
# Check a specific combo
game_id = '500256947'
event = 'af_level_10'
key = f'{game_id}_{event}'
wildcard = f'{game_id}_*'
print(f'{key}: {d.get(key, \"NOT FOUND\")}')
print(f'{wildcard}: {d.get(wildcard, \"NOT FOUND\")}')
print(f'Total trained combos: {len(d)}')
"
```

**Step 3:** Check if training data exists:
```sql
SELECT
  install_date,
  sdk_event_name,
  COUNT(*) AS rows,
  AVG(prob_sdk_event_name_label) AS avg_psn_label
FROM `unity-ads-dd-ds-dev-prd.unified_user_value_v11_cpe_lc_v2.unified_user_value_v11_cpe_lc_v2_preprocessed_combined`
WHERE target_game_id = '{target_game_id}'
GROUP BY install_date, sdk_event_name
ORDER BY install_date
```

**Root cause analysis:**
- If the combo is **not in `trained_game_sdk_combo.json`**: the model has never seen a positive label for this game+event. Zero bids are expected and correct. The game must accumulate ≥50 positive events in the 88-day window before the next training run can include it.
- If the combo **is in the gate** but bids are still zero: check prediction stability using the dCPI query (Section 3.2, filter `app_event_type = 'level_complete'`).
- If the game has **no data at all in training**: the game likely hasn't sent LC events to Unity, or they were filtered by the quality gate.

**Real example:**
- **500256947:** Campaign `69cd714e3954837fd906785f` had 0 starts. First check was the blocklist.

## E. Level Complete sudden spend spike

**Symptom:** Unexpected large increase in LC campaign spend.

**Real example:**
- **Perfect365 (500234783):** Campaign `6849e59e8f6aee71c3ef980b` had a sudden spend spike. [Imply link](https://internal-v2-1.pivot.int-prd-imply.unity3d.com/pivot/d/280b4491c576c9e133/uAds_Demand_Supply_Internal_(billing_&_finance))

**Investigation:** Check model prediction and label distribution for the specific game:
```sql
SELECT
  submit_date,
  body.app_event_model_version,
  COUNT(*) AS start_count,
  AVG(body.app_event_p) AS avg_pred,
  AVG(body.max_cst) AS avg_target_cpe,
  AVG(body.cst) AS avg_cost
FROM `unity-ai-data-prd.mz_dcpi_raw.mz_dcpi_prediction_v1`
WHERE submit_date BETWEEN '{start_date}' AND '{end_date}'
  AND body.target_game_id = {target_game_id}
  AND body.app_event_p > 0
  AND body.app_event_type = 'level_complete'
GROUP BY submit_date, body.app_event_model_version
ORDER BY submit_date
```

Also check training label:
```sql
SELECT
  install_date,
  sdk_event_name,
  AVG(prob_sdk_event_name_label) AS avg_psn_label
FROM `unity-ads-dd-ds-dev-prd.unified_user_value_v11_cpe_lc_v2.unified_user_value_v11_cpe_lc_v2_preprocessed_combined`
WHERE target_game_id = '{target_game_id}'
GROUP BY install_date, sdk_event_name
ORDER BY install_date
```

## F. LC Workflow — `run_datagen` fails

**Most common cause:** Source GCS path has no new `installDate=` partitions (upstream data delayed).

**Check latest available date:**
```bash
gsutil ls gs://unity-ads-dd-ds-prd-data-anon/app-events/data/ads.events.operativeecpm.installs.outcomes.v2/level_complete/d7/ \
  | grep installDate | sort | tail -5
```

**Action:** If upstream data is late, wait and rerun. The job auto-detects the latest available date on each run — no data is lost.

**If Spark OOM:** Current config is `executor.memory=38g`, `driver.memory=60g`. If OOM persists, escalate to @vector-offline-oncall to increase Dataproc resources.

## G. LC Workflow — `update_mappings` fails

Reads only categorical columns from parquet — 1-hour timeout.

**Common cause:** `preprocessed_combined/date={train_end}/` output from `run_datagen` is missing or corrupt.

**Verify parquet exists:**
```bash
gsutil ls gs://unity-ads-dd-ds-prd-incremental-training-data/user_value/unified_user_value.v11_cpe_lc_v2/preprocessed_combined/ | tail -5
```

**Impact if gate file is missing:** `trained_game_sdk_combo.json` is not written → at deploy time, gate defaults to all-allowed (no gating). This is degraded but not broken. The next successful `update_mappings` will restore the gate.

## H. LC Workflow — `model_train` fails or times out

- **18-hour timeout** on 8×G4.
- Runs up to 50 epochs with early stopping (patience=3 on `val_loss`, min_delta=0.0001). Typical runs stop at 10–20 epochs.
- If training runs all 50 epochs without improving: check data quality; check if val_pred_bias is very large (model may be stuck).
- If `total_step=0` error: the BQ row count query in the `model_train` step failed (BQ permissions or table not found). Verify `create_bq_table` succeeded.
- If NCCL timeout: use `/diagnose-faulty-gpu-node` to check for hardware faults.

## I. LC Workflow — `model_deploy` fails

- Deploy is CPU-only (`device=cpu`). No GPU node needed; nodepool = `cpu-n4-highmem-8`.
- If deploy fails with AOT error: check `config.json` `deploy_config.device = "cpu"`. AOT should not be triggered for CPU models.
- If calibration or gate tensor fails to load at deploy: harmless — defaults used (factor=1.0, gate disabled). Check that `feature_mapping.json` and `trained_game_sdk_combo.json` exist in GCS.

## J. Wildcard campaigns bidding zero (Level Complete specific)

**Symptom:** LC campaign targeting all SDK events (no specific target event configured) reports zero spend.

**Diagnosis:**
1. Confirm `sdk_event_name = ""` or `"*"` for this campaign in the dCPI prediction table.
2. Check that `"*"` exists in the `sdk_event_name` vocab in `feature_mapping.json`:
```bash
gsutil cat gs://unity-ads-dd-ds-prd-incremental-training-data/user_value/unified_user_value.v11_cpe_lc_v2/feature_mapping.json \
  | python3 -c "import json,sys; d=json.load(sys.stdin); print('wildcard idx:', d.get('sdk_event_name',{}).get('*','NOT FOUND'))"
```
3. Check that `"{game_id}_*"` is in `trained_game_sdk_combo.json`.

**If `"*"` is missing:** The game's wildcard campaigns were never seen in training with a positive label. The next training run will add it once sufficient events accumulate.

---

# Appendix 1 — Key Dashboards and Links

## Business Performance
- [Imply — Demand Supply Internal](https://internal-v2-1.pivot.int-prd-imply.unity3d.com/pivot/d/a3852db2088cad946e/uAds_Demand_Supply_Internal_(billing_&_finance)) — filter Campaign Type = `appEventConversion`
- [Imply — Direct Demand (event_ts)](https://internal-v2-1.pivot.int-prd-imply.unity3d.com/pivot/i/e2ddc3d81dc11ed11b/uAds_Direct_Demand_ML_(event_ts_timestamp))

## Online Metrics (Grafana)
- [CPI Valuation Metrics](https://grafana.internal.unity3d.com/d/qMQ8n3rGk/cpi-valuation-metrics) — mean dCPI, zero valuation rate, overall online metrics
- [Triton panel](https://grafana.internal.unity3d.com/d/WFpzgk6Vk/triton) — model deployment history
- [UV Model Grafana Dashboard](https://grafana.internal.unity3d.com/goto/dfc9a16m7vp4wa?orgId=1)
- [Unity Ads ML Status](https://grafana.internal.unity3d.com/d/b8ef6a78-0b4d-458c-b20a-87123781bace/unity-ads-ml-status)

## Accuracy (Looker)
- [IAP Accuracy Looker](https://unitytech.looker.com/dashboards/8317)
- [AdRev Accuracy Looker](https://unitytech.looker.com/dashboards/7617)
- [CPE Looker Dashboard](https://unitytech.looker.com/dashboards/14031) — Level Complete A/B test + CPE campaign performance

## Offline (Training)
- [W&B — ads-unified-learner](https://wandb.ai/unity-labs-ai-research/ads-unified-learner)
- [LC Offline Eval Notebook](https://colab.research.google.com/drive/1hr7y1Svc9xVsJMzibGfpe3Z2Zop-cA8Z?usp=sharing)

## Production Pipelines (Vertex AI)
- [v3_q3a pipeline schedule](https://console.cloud.google.com/agent-platform/pipelines/locations/us-central1/schedules/5183187973289541632?project=unity-applied-research-ml-test) — Retention + Payer (and UV)
- [v11_cpe_lc_v2 pipeline schedule](https://console.cloud.google.com/agent-platform/pipelines/locations/us-central1/schedules/75050464688734208?project=unity-applied-research-ml-test) — Level Complete
- [All Vertex pipelines](https://console.cloud.google.com/vertex-ai/pipelines/schedules?project=unity-applied-research-ml-test)

## GCS Artifacts (Level Complete)
- [trained_game_sdk_combo.json](https://console.cloud.google.com/storage/browser/_details/unity-ads-dd-ds-prd-incremental-training-data/user_value/unified_user_value.v11_cpe_lc_v2/trained_game_sdk_combo.json)
- [product_accuracy_calibration.json](https://console.cloud.google.com/storage/browser/_details/unity-ads-dd-ds-prd-incremental-training-data/user_value/unified_user_value.v11_cpe_lc_v2/product_accuracy_calibration.json)
- [feature_mapping.json](https://console.cloud.google.com/storage/browser/_details/unity-ads-dd-ds-prd-incremental-training-data/user_value/unified_user_value.v11_cpe_lc_v2/feature_mapping.json)

---

# Appendix 2 — Model Recovery

## Rollback (v3_q3a — Retention / Payer)

Follows UV rollback procedure — see [UV SOP Appendix 2](https://docs.google.com/document/d/1GTlMIGKidVmWXOUEb5s_6gecjDa0bJjMP1IUEnGz_xM/edit#heading=h.appendix-2):

1. [Rollback process for UL common inference](https://docs.google.com/document/d/1TlYRfXw-YHvlls16AAgQCbbIBeXH2NM8VviieKtYPhU/edit)
2. [Pause model updates for UL common inference](https://unity.slack.com/archives/C06Q5D269DZ/p1765914096672439)

## Rollback (v11_cpe_lc_v2 — Level Complete)

1. Find the last known working model artifact in the model store
2. Redeploy it manually: `ul-cli deploy --experiment=unified_user_value.v11_cpe_lc_v2 --upload_to_stg=True`
3. Pause the workflow schedule in Vertex AI console to prevent it from overwriting the rollback
4. After root cause is resolved, re-enable the schedule

## Backfill (v3_q3a — Retention / Payer)

Follows UV backfill procedure (identical workflow):
1. Backfill UV incremental raw datagen
2. Backfill preprocessed data
3. Combine and train

## Backfill (v11_cpe_lc_v2 — Level Complete)

Since data comes from a single GCS source (not incremental raw datagen), backfill is simpler:
1. Rerun `run_datagen` — it reads all 88 days from the source path up to the latest available date
2. Rerun `update_mappings`
3. Rerun `model_train`

No incremental raw datagen backfill needed (LC uses the pre-processed `level_complete/d7/` source directly).

## Blocklist a date's data (Level Complete)

If training data for a specific date is contaminated, exclude it by blacklisting:
```python
from unity_learner.db_manager.data_pipeline_status_manager import DataPipelineStatusManager

dm = DataPipelineStatusManager()
dm.blacklist_dates(
    platform="unified",
    model_type="user_value",
    dates=["2026-05-27"],
    blacklist_reason="#incident-2026-05-27-1"
)
```

---

# Appendix 3 — Past Case Checks

| Date | Game | Type | Issue | Resolution |
|---|---|---|---|---|
| July 2026 | Big Win Pick (800084221) | Payer | Avg cost dropped July 14 | Advertiser reduced tCPE July 13; model stable; cost recovered July 19 when tCPE raised |
| July 2026 | Egypt Path (800078681) | Payer | Avg cost dropped July 11 | Advertiser reduced tCPE July 11; model stable |
| June 2026 | Matrix4Games (500237245) | Retention | Retention D7 declining | D7 at 30%+ early was noisy (small sample); true avg D7 is 18–20%; model stable |
| April 2026 | 500197520 | Retention | Spend dropped sharply April 16 | Under investigation; check blocklist + label availability |
| 2026 | 500137583 | Retention | Cannot scale | Under investigation; check label distribution |
| 2026 | 500256947 | Level Complete | 0 starts (campaign `69cd714e3954837fd906785f`) | First check: blocklist |
| June 2026 | Perfect365 (500234783) | Level Complete | Sudden spend spike | Check prediction table + training label distribution |
| May 2026 | Lingokids (500023036) | Payer/AdRev | Payer model stable; blocked by ROAS head | Model prediction stable; issue was ROAS head, not payer head |
