-- ============================================================================
-- Model Bias & Accuracy Analysis
-- AB Test: v11-cpe-lc-4 (test) vs bhv1n + ctx1i (control)
-- Experiment ID: 4f4ee12f-e4c4-d53d-b77b-4a5199a9986b
-- Analysis period: 2026-05-28 → 2026-06-18
--
-- THREE BIAS TYPES:
--   1. General Model Bias Dx  = (sum_pred_installs / sum_lc_count_dx) - 1
--      Model predicts p(LC by D7 | install). Compares prediction sum vs
--      cumulative LC event count through day X on the same install population.
--
--   2. Target Model Bias Dx   = (sum_pred_installs / sum_target_event_dx) - 1
--      Same, but denominator is the campaign-specific SDK event that was
--      actually fired. Most accurate: mirrors the training label
--      prob_sdk_event_name_label.
--
--   3. Product Bias (CPE Bias) Dx = (observed_cpe_dx / avg_target_cpe) - 1
--      observed_cpe_dx = sum_cost / sum_lc_count_dx  (cumulative event count)
--      avg_target_cpe  = avg of max_cst (advertiser's target CPE)
--      >0 = overspending vs target; <0 = underspending.
--
-- NOTE: lc_label_dx are INCREMENTAL per-day windows (had LC on day X),
--       lc_count_dx are CUMULATIVE counts through day X.
--       sum_pred_installs uses only installing auctions to match denominator
--       population (avoids starts/installs ratio distortion).
-- ============================================================================

WITH

-- ── 1. Predictions (one row per auction / start) ──────────────────────────────
PREDS AS (
  SELECT
    submit_date,
    body.auction_id,
    body.app_event_p  AS pred,
    body.max_cst      AS target_cpe,   -- advertiser's target CPE
    body.cst          AS cost,         -- actual spend for this auction

    -- Treatment assignment via model version string
    CASE
      WHEN body.app_event_model_version LIKE '%v11-cpe-lc-4%' THEN 'Test'
      WHEN body.app_event_model_version LIKE '%ctx1r-1a%'     THEN 'Control'
      WHEN body.app_event_model_version LIKE '%bhv1p-1b%'     THEN 'Control'
    END AS is_control_label,

    -- Model type segment (mirrors EP table model_type column)
    CASE
      WHEN body.app_event_model_version LIKE '%bhv1p-1b%'     THEN 'Behavioural'
      WHEN body.app_event_model_version LIKE '%ctx1r-1a%'     THEN 'Advanced Contextual'
      WHEN body.app_event_model_version LIKE '%v11-cpe-lc-4%' THEN 'Unified (BHV+CTX)'
    END AS model_type,

    -- Individual model name (for per-model drill-down)
    CASE
      WHEN body.app_event_model_version LIKE '%v11-cpe-lc-4%' THEN 'v11-cpe-lc (test)'
      WHEN body.app_event_model_version LIKE '%ctx1r-1a%'     THEN 'ctx1i (control)'
      WHEN body.app_event_model_version LIKE '%bhv1p-1b%'     THEN 'bhv1n (control)'
    END AS model_name,

  FROM `unity-ai-data-prd.mz_dcpi_raw.mz_dcpi_prediction_v1`
  WHERE submit_date BETWEEN '2026-05-28' AND '2026-06-18'
    AND body.app_event_p > 0
    AND body.app_event_type = 'level_complete'
),

-- ── 2. Campaigns — targeted SDK event per campaign ────────────────────────────
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
      WHEN sdk_event_names IS NULL OR ARRAY_LENGTH(sdk_event_names) = 0 THEN ['*']
      ELSE ARRAY(SELECT DISTINCT LOWER(e) FROM UNNEST(sdk_event_names) AS e)
    END AS sdk_events_targeted
  FROM CAMPAIGNS_RAW
),

-- ── 3. Install outcomes with target-event label ───────────────────────────────
OUTCOMES_RAW AS (
  SELECT
    auctionId,
    campaignInfo.campaignId  AS campaign_id,
    -- Incremental binary labels: had LC event on day X
    app_event_level_complete_d0  AS lc_d0,
    app_event_level_complete_d1  AS lc_d1,
    app_event_level_complete_d3  AS lc_d3,
    app_event_level_complete_d7  AS lc_d7,
    -- Cumulative event counts through day X (for CPE denominator)
    cum_app_event_level_complete_count_d0 AS lc_count_d0,
    cum_app_event_level_complete_count_d1 AS lc_count_d1,
    cum_app_event_level_complete_count_d3 AS lc_count_d3,
    cum_app_event_level_complete_count_d7 AS lc_count_d7,
    -- Fired SDK event names (Avro nested struct unwrap)
    ARRAY(
      SELECT LOWER(x.element)
      FROM UNNEST(app_event_level_complete_sdk_event_name_array.list) AS x
      WHERE x.element IS NOT NULL
    ) AS fired_events_lower
  FROM `unity-data-ads-core-prd.ads_secondary_conversion.operativeecpm_installs_outcomes_contextual`
  WHERE adRequestTimestamp >= TIMESTAMP('2026-05-28')
    AND adRequestTimestamp <= TIMESTAMP('2026-06-18')
),

OUTCOMES AS (
  SELECT
    o.*,
    -- Target event cumulative count through day X:
    --   Wildcard campaigns  → use generic lc_count_dx  (cumulative LC events)
    --   Specific-event campaigns → fired_events_lower has no day breakdown,
    --     so binary 0/1 per install is the best available (no per-day counts in schema)
    (CASE
      WHEN c.sdk_events_targeted IS NULL        THEN o.lc_count_d0
      WHEN '*' IN UNNEST(c.sdk_events_targeted) THEN o.lc_count_d0
      ELSE IF(EXISTS(
        SELECT 1 FROM UNNEST(c.sdk_events_targeted) AS tgt
        WHERE tgt IN UNNEST(o.fired_events_lower)), 1, 0)
    END) AS target_d0,
    (CASE
      WHEN c.sdk_events_targeted IS NULL        THEN o.lc_count_d1
      WHEN '*' IN UNNEST(c.sdk_events_targeted) THEN o.lc_count_d1
      ELSE IF(EXISTS(
        SELECT 1 FROM UNNEST(c.sdk_events_targeted) AS tgt
        WHERE tgt IN UNNEST(o.fired_events_lower)), 1, 0)
    END) AS target_d1,
    (CASE
      WHEN c.sdk_events_targeted IS NULL        THEN o.lc_count_d3
      WHEN '*' IN UNNEST(c.sdk_events_targeted) THEN o.lc_count_d3
      ELSE IF(EXISTS(
        SELECT 1 FROM UNNEST(c.sdk_events_targeted) AS tgt
        WHERE tgt IN UNNEST(o.fired_events_lower)), 1, 0)
    END) AS target_d3,
    (CASE
      WHEN c.sdk_events_targeted IS NULL        THEN o.lc_count_d7
      WHEN '*' IN UNNEST(c.sdk_events_targeted) THEN o.lc_count_d7
      ELSE IF(EXISTS(
        SELECT 1 FROM UNNEST(c.sdk_events_targeted) AS tgt
        WHERE tgt IN UNNEST(o.fired_events_lower)), 1, 0)
    END) AS target_d7,
  FROM OUTCOMES_RAW AS o
  LEFT JOIN CAMPAIGNS AS c ON o.campaign_id = c.campaignset_id
),

-- ── 4. Join predictions with outcomes ────────────────────────────────────────
JOINED AS (
  SELECT
    p.submit_date,
    p.is_control_label,
    p.model_type,
    p.model_name,
    p.pred,
    p.target_cpe,
    p.cost,
    o.auctionId IS NOT NULL AS is_install,
    COALESCE(o.lc_d0, 0)       AS lc_d0,
    COALESCE(o.lc_d1, 0)       AS lc_d1,
    COALESCE(o.lc_d3, 0)       AS lc_d3,
    COALESCE(o.lc_d7, 0)       AS lc_d7,
    COALESCE(o.lc_count_d0, 0) AS lc_count_d0,
    COALESCE(o.lc_count_d1, 0) AS lc_count_d1,
    COALESCE(o.lc_count_d3, 0) AS lc_count_d3,
    COALESCE(o.lc_count_d7, 0) AS lc_count_d7,
    COALESCE(o.target_d0, 0)   AS target_d0,
    COALESCE(o.target_d1, 0)   AS target_d1,
    COALESCE(o.target_d3, 0)   AS target_d3,
    COALESCE(o.target_d7, 0)   AS target_d7,
  FROM PREDS p
  LEFT JOIN OUTCOMES o ON o.auctionId = p.auction_id
  WHERE p.model_name IS NOT NULL
)

-- ── 5. Final aggregation ──────────────────────────────────────────────────────
SELECT
  submit_date,
  is_control_label,
  model_type,
  model_name,

  -- ── Volume ────────────────────────────────────────────────────────────────
  COUNT(*)           AS starts,
  COUNTIF(is_install) AS installs,
  SAFE_DIVIDE(COUNTIF(is_install), COUNT(*)) AS install_rate,

  -- ── Prediction (install population only) ─────────────────────────────────
  SUM(IF(is_install, pred, 0)) AS sum_pred_installs,
  SAFE_DIVIDE(SUM(IF(is_install, pred, 0)), COUNTIF(is_install)) AS avg_pred_installs,

  -- ── Generic LC event counts & rates (cumulative through day X) ────────────
  SUM(lc_count_d0) AS lc_event_count_d0,
  SUM(lc_count_d1) AS lc_event_count_d1,
  SUM(lc_count_d3) AS lc_event_count_d3,
  SUM(lc_count_d7) AS lc_event_count_d7,
  SAFE_DIVIDE(SUM(lc_count_d0), COUNTIF(is_install)) AS er_d0,
  SAFE_DIVIDE(SUM(lc_count_d1), COUNTIF(is_install)) AS er_d1,
  SAFE_DIVIDE(SUM(lc_count_d3), COUNTIF(is_install)) AS er_d3,
  SAFE_DIVIDE(SUM(lc_count_d7), COUNTIF(is_install)) AS er_d7,

  -- ── Target event counts & rates (campaign-specific SDK event, per install) ─
  SUM(target_d0) AS target_event_count_d0,
  SUM(target_d1) AS target_event_count_d1,
  SUM(target_d3) AS target_event_count_d3,
  SUM(target_d7) AS target_event_count_d7,
  SAFE_DIVIDE(SUM(target_d0), COUNTIF(is_install)) AS target_er_d0,
  SAFE_DIVIDE(SUM(target_d1), COUNTIF(is_install)) AS target_er_d1,
  SAFE_DIVIDE(SUM(target_d3), COUNTIF(is_install)) AS target_er_d3,
  SAFE_DIVIDE(SUM(target_d7), COUNTIF(is_install)) AS target_er_d7,

  -- ── 1. General Model Bias Dx = (sum_pred_installs / sum_lc_count_dx) - 1 ──
  -- Denominator = cumulative event count through day X (not binary label)
  SAFE_DIVIDE(SUM(IF(is_install, pred, 0)), NULLIF(SUM(lc_count_d0), 0)) - 1 AS bias_generic_d0,
  SAFE_DIVIDE(SUM(IF(is_install, pred, 0)), NULLIF(SUM(lc_count_d1), 0)) - 1 AS bias_generic_d1,
  SAFE_DIVIDE(SUM(IF(is_install, pred, 0)), NULLIF(SUM(lc_count_d3), 0)) - 1 AS bias_generic_d3,
  SAFE_DIVIDE(SUM(IF(is_install, pred, 0)), NULLIF(SUM(lc_count_d7), 0)) - 1 AS bias_generic_d7,

  -- ── 2. Target Model Bias Dx = (sum_pred_installs / sum_target_event_dx) - 1 ──
  -- Denominator = campaign-specific SDK events (mirrors training label)
  SAFE_DIVIDE(SUM(IF(is_install, pred, 0)), NULLIF(SUM(target_d0), 0)) - 1 AS bias_target_d0,
  SAFE_DIVIDE(SUM(IF(is_install, pred, 0)), NULLIF(SUM(target_d1), 0)) - 1 AS bias_target_d1,
  SAFE_DIVIDE(SUM(IF(is_install, pred, 0)), NULLIF(SUM(target_d3), 0)) - 1 AS bias_target_d3,
  SAFE_DIVIDE(SUM(IF(is_install, pred, 0)), NULLIF(SUM(target_d7), 0)) - 1 AS bias_target_d7,

  -- ── Spend & Target CPE ────────────────────────────────────────────────────
  SUM(IF(is_install, cost, 0)) AS total_spend,
  SAFE_DIVIDE(SUM(IF(is_install, target_cpe, 0)), COUNTIF(is_install)) AS avg_target_cpe,

  -- ── Observed CPE Dx (cumulative event count denominator) ─────────────────
  SAFE_DIVIDE(SUM(IF(is_install, cost, 0)), NULLIF(SUM(lc_count_d1), 0)) AS observed_cpe_d1,
  SAFE_DIVIDE(SUM(IF(is_install, cost, 0)), NULLIF(SUM(lc_count_d3), 0)) AS observed_cpe_d3,
  SAFE_DIVIDE(SUM(IF(is_install, cost, 0)), NULLIF(SUM(lc_count_d7), 0)) AS observed_cpe_d7,

  -- ── 3. Product Bias (CPE Bias) Dx = SUM(cost) / SUM(target_cpe × lc_count_dx) - 1 ──
  -- Ratio of sums: actual spend vs what advertisers' targets imply given delivered events.
  -- Avoids averaging distortion when campaigns with different target CPEs are mixed.
  SAFE_DIVIDE(
    SUM(IF(is_install, cost, 0)),
    NULLIF(SUM(IF(is_install, target_cpe * lc_count_d1, 0)), 0)
  ) - 1 AS product_bias_d1,
  SAFE_DIVIDE(
    SUM(IF(is_install, cost, 0)),
    NULLIF(SUM(IF(is_install, target_cpe * lc_count_d3, 0)), 0)
  ) - 1 AS product_bias_d3,
  SAFE_DIVIDE(
    SUM(IF(is_install, cost, 0)),
    NULLIF(SUM(IF(is_install, target_cpe * lc_count_d7, 0)), 0)
  ) - 1 AS product_bias_d7,

FROM JOINED
GROUP BY 1, 2, 3, 4
ORDER BY submit_date, model_type, is_control_label DESC
