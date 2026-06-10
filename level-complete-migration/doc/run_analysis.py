"""
Runner: fetches BQ data via `bq` CLI, loads it as lc_df_all, then runs the analysis.
Usage:  python3 run_analysis.py
"""

import subprocess
import sys
import tempfile
import os
import pandas as pd
import io

BQ_PROJECT = "unity-ads-bi-prd"

QUERY = """
WITH PREDS AS (
  SELECT
    submit_date,
    CASE
      WHEN body.app_event_model_version LIKE '%v11-cpe-lc-4%' THEN 'v11-cpe-lc'
      WHEN body.app_event_model_version LIKE '%ctx1r-1a%'     THEN 'ctx1i'
      WHEN body.app_event_model_version LIKE '%bhv1p-1b%'     THEN 'bhv1n'
      ELSE null
    END AS app_event_model_version,
    body.auction_id,
    body.app_event_p  AS pred,
    body.max_cst      AS target_cpe,
    body.cst          AS cost,
  FROM `unity-ai-data-prd.mz_dcpi_raw.mz_dcpi_prediction_v1`
  WHERE submit_date >= "2026-05-28" AND submit_date <= "2026-06-18"
    AND body.app_event_p > 0
    AND body.app_event_type = "level_complete"
),

-- Deduplicate campaigns_v3 to one row per campaignset_id.
-- sdk_event_names is a plain ARRAY<STRING> here (no nested struct).
CAMPAIGNS_RAW AS (
  SELECT
    campaignset_id,
    ANY_VALUE(sdk_event_names) AS sdk_event_names
  FROM `unity-data-ads-core-prd.ads_dimension_data.campaigns_v3`
  WHERE app_event_conversion_type = 'LEVEL_COMPLETE'
    AND archived_at IS NULL
  GROUP BY campaignset_id
),

CAMPAIGNS AS (
  SELECT
    campaignset_id,
    CASE
      WHEN sdk_event_names IS NULL OR ARRAY_LENGTH(sdk_event_names) = 0
      THEN ['*']
      ELSE ARRAY(SELECT DISTINCT LOWER(e) FROM UNNEST(sdk_event_names) AS e)
    END AS sdk_events_targeted
  FROM CAMPAIGNS_RAW
),

OUTCOMES AS (
  SELECT
    auctionId,
    campaignInfo.campaignId                    AS campaign_id,
    campaignSpend,
    app_event_level_complete_d0                AS lc_label_d0,
    app_event_level_complete_d1                AS lc_label_d1,
    app_event_level_complete_d3                AS lc_label_d3,
    app_event_level_complete_d7                AS lc_label_d7,
    cum_app_event_level_complete_count_d0      AS lc_count_d0,
    cum_app_event_level_complete_count_d1      AS lc_count_d1,
    cum_app_event_level_complete_count_d3      AS lc_count_d3,
    cum_app_event_level_complete_count_d7      AS lc_count_d7,
    -- app_event_level_complete_sdk_event_name_array is an Avro nested struct:
    -- {list: [{element: "event_name"}, ...]}  — unwrap via .list[].element
    ARRAY(
      SELECT LOWER(x.element)
      FROM UNNEST(app_event_level_complete_sdk_event_name_array.list) AS x
      WHERE x.element IS NOT NULL
    ) AS fired_events_lower
  FROM `unity-data-ads-core-prd.ads_secondary_conversion.operativeecpm_installs_outcomes_contextual`
  WHERE adRequestTimestamp >= TIMESTAMP("2026-05-28") AND adRequestTimestamp <= TIMESTAMP("2026-06-18")
),

OUTCOMES_WITH_TARGET AS (
  SELECT
    o.*,
    (CASE
      WHEN c.sdk_events_targeted IS NULL        THEN o.lc_label_d0
      WHEN '*' IN UNNEST(c.sdk_events_targeted) THEN o.lc_label_d0
      ELSE IF(EXISTS(
        SELECT 1 FROM UNNEST(c.sdk_events_targeted) AS tgt
        WHERE tgt IN UNNEST(o.fired_events_lower)), 1, 0)
    END) AS target_event_fired_d0,

    (CASE
      WHEN c.sdk_events_targeted IS NULL        THEN o.lc_label_d1
      WHEN '*' IN UNNEST(c.sdk_events_targeted) THEN o.lc_label_d1
      ELSE IF(EXISTS(
        SELECT 1 FROM UNNEST(c.sdk_events_targeted) AS tgt
        WHERE tgt IN UNNEST(o.fired_events_lower)), 1, 0)
    END) AS target_event_fired_d1,

    (CASE
      WHEN c.sdk_events_targeted IS NULL        THEN o.lc_label_d3
      WHEN '*' IN UNNEST(c.sdk_events_targeted) THEN o.lc_label_d3
      ELSE IF(EXISTS(
        SELECT 1 FROM UNNEST(c.sdk_events_targeted) AS tgt
        WHERE tgt IN UNNEST(o.fired_events_lower)), 1, 0)
    END) AS target_event_fired_d3,

    (CASE
      WHEN c.sdk_events_targeted IS NULL        THEN o.lc_label_d7
      WHEN '*' IN UNNEST(c.sdk_events_targeted) THEN o.lc_label_d7
      ELSE IF(EXISTS(
        SELECT 1 FROM UNNEST(c.sdk_events_targeted) AS tgt
        WHERE tgt IN UNNEST(o.fired_events_lower)), 1, 0)
    END) AS target_event_fired_d7

  FROM OUTCOMES AS o
  LEFT JOIN CAMPAIGNS AS c ON o.campaign_id = c.campaignset_id
)

SELECT
  submit_date,
  app_event_model_version,
  COUNT(*)                                AS starts,
  COUNT(OUTCOMES_WITH_TARGET.auctionId)   AS installs,
  SUM(pred)          AS sum_pred,
  AVG(pred)          AS avg_pred,
  -- sum of predictions for installing auctions only (same population as lc_label)
  SUM(IF(OUTCOMES_WITH_TARGET.auctionId IS NOT NULL, pred, 0)) AS sum_pred_installs,
  SUM(target_cpe)    AS sum_tcpe,
  AVG(target_cpe)    AS avg_tcpe,
  SUM(cost)          AS sum_cost,
  AVG(cost)          AS avg_cost,
  SUM(campaignSpend) AS sum_campaign_spend,
  SUM(lc_label_d0)   AS sum_lc_label_d0,
  SUM(lc_label_d1)   AS sum_lc_label_d1,
  SUM(lc_label_d3)   AS sum_lc_label_d3,
  SUM(lc_label_d7)   AS sum_lc_label_d7,
  SUM(lc_count_d0)   AS sum_lc_count_d0,
  SUM(lc_count_d1)   AS sum_lc_count_d1,
  SUM(lc_count_d3)   AS sum_lc_count_d3,
  SUM(lc_count_d7)   AS sum_lc_count_d7,
  SUM(target_event_fired_d0) AS sum_target_event_d0,
  SUM(target_event_fired_d1) AS sum_target_event_d1,
  SUM(target_event_fired_d3) AS sum_target_event_d3,
  SUM(target_event_fired_d7) AS sum_target_event_d7,
FROM PREDS
LEFT JOIN OUTCOMES_WITH_TARGET ON OUTCOMES_WITH_TARGET.auctionId = PREDS.auction_id
WHERE app_event_model_version IS NOT NULL
GROUP BY 1, 2
ORDER BY 1, 2
"""

print(f"Fetching data from BigQuery (project: {BQ_PROJECT}) ...")

with tempfile.NamedTemporaryFile(mode="w", suffix=".sql", delete=False) as f:
    f.write(QUERY)
    tmpfile = f.name

try:
    with open(tmpfile) as qf:
        result = subprocess.run(
            ["bq", "query",
             f"--project_id={BQ_PROJECT}",
             "--use_legacy_sql=false",
             "--format=csv",
             "--max_rows=100000",
             "--nouse_cache"],
            stdin=qf,
            capture_output=True,
            text=True,
        )
finally:
    os.unlink(tmpfile)

if result.returncode != 0:
    print("ERROR: bq query failed.\n")
    print(result.stderr or result.stdout)
    sys.exit(1)

lc_df_all = pd.read_csv(io.StringIO(result.stdout))
print(f"Fetched {len(lc_df_all)} rows.\n")

analysis_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lc_ab_test_analysis.py")
exec(open(analysis_path).read())
