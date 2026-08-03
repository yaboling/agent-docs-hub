#!/bin/bash
# Run Queries A–D for a single game_id
# Usage: ./run_queries.sh <game_id>

GAME_ID=$1
DIR=~/Repository/playrix-uv-report/game_${GAME_ID}
START="2026-07-01"
END="2026-08-03"
PROJECT="unity-ads-ai-tools-prd"

echo "[${GAME_ID}] Running Query A (IAP)..."
bq query --project_id=${PROJECT} --use_legacy_sql=false --format=csv --max_rows=10000 "
SELECT
  submit_date,
  body.post_install_window,
  body.model_versions.dep.version AS dep_model_version,
  MAX(body.target_game_id) AS target_game_id,
  COUNT(*) AS start_count,
  AVG(body.dep_d7_prob)   AS avg_dep_d7_prob,
  AVG(body.dep_d7_value)  AS avg_dep_d7_value,
  AVG(body.dep_d7_final)  AS avg_dep_d7_final,
  AVG(body.dep_d28_prob)  AS avg_dep_d28_prob,
  AVG(body.dep_d28_value) AS avg_dep_d28_value,
  AVG(body.dep_d28_final) AS avg_dep_d28_final
FROM \`unity-ai-data-prd.mz_dcpi_raw.mz_dcpi_prediction_v1\`
WHERE submit_date BETWEEN '${START}' AND '${END}'
  AND body.ar_ts >= '${START} 00:00:00'
  AND body.dep_p > 0
  AND body.target_game_id IN (${GAME_ID})
GROUP BY submit_date, body.post_install_window, body.model_versions.dep.version
ORDER BY submit_date
" 2>/dev/null > ${DIR}/iap_predictions.csv

echo "[${GAME_ID}] Running Query B (AdRev)..."
bq query --project_id=${PROJECT} --use_legacy_sql=false --format=csv --max_rows=10000 "
SELECT
  submit_date,
  body.post_install_window,
  body.model_versions.adrev.version AS adrev_model_version,
  MAX(body.target_game_id) AS target_game_id,
  COUNT(*) AS start_count,
  AVG(body.adrev_d0_non_log_value) AS avg_adrev_d0_value,
  AVG(body.adrev_d7_non_log_value) AS avg_adrev_d7_value,
  AVG(body.adrev_adj)              AS avg_adrev_adj,
  AVG(body.adrev_value)            AS avg_adrev_value
FROM \`unity-ai-data-prd.mz_dcpi_raw.mz_dcpi_prediction_v1\`
WHERE submit_date BETWEEN '${START}' AND '${END}'
  AND body.ar_ts >= '${START} 00:00:00'
  AND body.adrev_p > 0
  AND body.target_game_id IN (${GAME_ID})
GROUP BY submit_date, body.post_install_window, body.model_versions.adrev.version
ORDER BY submit_date
" 2>/dev/null > ${DIR}/adrev_predictions.csv

echo "[${GAME_ID}] Running Query C (CPE)..."
bq query --project_id=${PROJECT} --use_legacy_sql=false --format=csv --max_rows=10000 "
SELECT
  submit_date,
  body.app_event_type,
  CASE body.app_event_type
    WHEN 'level_complete' THEN body.model_versions.level_complete.version
    WHEN 'purchase'       THEN body.model_versions.purchase.version
    WHEN 'retention'      THEN body.model_versions.retention.version
  END AS cpe_model_version,
  MAX(body.target_game_id) AS target_game_id,
  COUNT(*) AS start_count,
  AVG(body.app_event_p)   AS avg_cpe_pred,
  AVG(body.app_event_adj) AS avg_cpe_adj
FROM \`unity-ai-data-prd.mz_dcpi_raw.mz_dcpi_prediction_v1\`
WHERE submit_date BETWEEN '${START}' AND '${END}'
  AND body.ar_ts >= '${START} 00:00:00'
  AND body.app_event_type IN ('level_complete', 'purchase', 'retention')
  AND body.app_event_p > 0
  AND body.target_game_id IN (${GAME_ID})
GROUP BY submit_date, body.app_event_type, cpe_model_version
ORDER BY submit_date
" 2>/dev/null > ${DIR}/cpe_predictions.csv

echo "[${GAME_ID}] Running Query D (Cost)..."
bq query --project_id=${PROJECT} --use_legacy_sql=false --format=csv --max_rows=10000 "
SELECT
  submit_date,
  body.valuation_metadata[SAFE_OFFSET(0)].model_type AS model_type,
  body.post_install_window,
  MAX(body.target_game_id) AS target_game_id,
  COUNT(*) AS start_count,
  AVG(body.cst)            AS avg_cost,
  AVG(body.max_cost)       AS avg_max_cost,
  AVG(body.actual_max_cost) AS avg_actual_max_cst
FROM \`unity-ai-data-prd.mz_dcpi_raw.mz_dcpi_prediction_v1\`
WHERE submit_date BETWEEN '${START}' AND '${END}'
  AND body.ar_ts >= '${START} 00:00:00'
  AND body.target_game_id IN (${GAME_ID})
GROUP BY submit_date, model_type, body.post_install_window
ORDER BY submit_date
" 2>/dev/null > ${DIR}/cost_by_model_type.csv

echo "[${GAME_ID}] All queries done."
