# CPE Metrics Gap Analysis — ROAS Query Extension

Analysis of the existing ROAS experiment metrics query to identify what CPE-related metrics are already available vs. what needs to be added.

Source table: `unity-data-ads-core-prd.ads_demand_supply_unity.ads_operativeecpm_post_installs_ep_daily_enriched`

---

## What's Already Available

### Common Metrics (all CPE types)

| Metric | Source Column | Status |
|--------|--------------|--------|
| Starts | `op.starts` | direct |
| Installs | `op.outcomes_installs` | direct |
| Spend | `op.spend_sum` | direct |
| Net Revenue | `spend_sum - publisher_revenue` | computed |
| Publisher Revenue | `op.publisher_revenue` | direct |
| CPI | `spend / installs` | derivable |
| CVR | `installs / starts` | derivable |
| Margin | `(spend - publisher_revenue) / spend` | derivable |

---

### CPE - D7 Retention

| Metric | Source Column | Status |
|--------|--------------|--------|
| Retained D1/D3/D7 counts | `op.retained_d1/d3/d7` | already selected |
| Retention Rate D1/D3/D7 | `retained_dx / installs` | derivable |
| Observed CPE | `spend / retained_d7` | derivable |
| Model Bias D7 | Needs `predicted_ret_rate_d7` | NOT in query |
| Product Bias D1/D3/D7 | Needs `target_cpe` equivalent | NOT in query |

Product Bias (CPE) formula: `(Observed CPE / Target CPE) - 1`
Note: Opposite sign convention to ROAS Product Bias so that positive = over-valuation consistently.

---

### CPE - D7 Payer

| Metric | Source Column | Status | Note |
|--------|--------------|--------|------|
| Payer Count D1/D3/D7 | `CASE WHEN op.payer_conversions_dx > 0 THEN 1 ELSE 0 END` → alias `payer_dx` | confirmed — replace `iap_deposits_dx` | Binary: did install make any purchase within Dx window |
| Payer Rate D1/D3/D7 | `payer_dx / installs` | derivable | |
| Observed CPE | `spend / payer_dx` | derivable | |
| Purchase Count D1/D3/D7 | `op.payer_conversions_d1/d3/d7` → alias `purchase_count_dx` | confirmed | Raw transaction count; one payer can have multiple purchases |
| Purchase Rate D1/D3/D7 | `purchase_count_dx / installs` | derivable | |
| Model Bias D7 | Needs predicted payer column (e.g. `dep_adj_payer_dx`) | NOT in query | |
| Product Bias D1/D3/D7 | Needs `target_cpe` | NOT in query | |

---

### CPE - D7 Level Complete

| Metric | Source Column | Status |
|--------|--------------|--------|
| Level Complete Count D1/D3/D7 | `op.cum_app_event_level_complete_count_dx` | confirmed — NOT in query yet |
| Level Complete Rate D1/D3/D7 | `cum_app_event_level_complete_count_dx / installs` | derivable once column added |
| Observed CPE | `spend / cum_app_event_level_complete_count_d7` | derivable once column added |
| Model Bias D7 | Needs predicted LC column (e.g. `dep_adj_lc_dx`) | NOT in query |
| Product Bias D1/D3/D7 | Needs `target_cpe` | NOT in query |

---

## How IAP Model Bias Works (and Why It's Available)

IAP Model Bias does NOT require a separate "predicted IAP value" column — the prediction is already in the source table as **`dep_adj_value_installs`** (deposit-adjusted model-predicted IAP value per install). The formula is:

```
iap_model_bias_dx = (dep_adj_value_installs_dx / iap_revenue_dx) - 1
                  = (Model Predicted IAP Value / Observed IAP Revenue) - 1
```

`dep_adj_value_installs` is a model output stored at the row level, gated by day maturity in the query (e.g. `>= 3 days` for d1, `>= 5 days` for d3, etc.).

**Implication for CPE Model Bias:** The same pattern likely applies. The model's predicted values for CPE events should already be stored as columns in the source table (model outputs at install time), not computed on the fly. The column names are just unknown until the schema is inspected.

---

## Key Gaps to Investigate in the Source Table

The current query was built entirely for ROAS campaigns. For CPE the following columns need to be confirmed in the source table:

1. **`target_cpe`** (or equivalent like `max_cpe_target`) — denominator for Product Bias, analogous to `max_roas_target_undiscounted` for ROAS
2. **`dep_adj_retained_dx`** (or similar) — model-predicted retained count, analogous to `dep_adj_value_installs` for IAP; used to compute Retention Model Bias
3. **`dep_adj_payer_dx`** (or similar) — model-predicted payer count for Payer Model Bias
4. **`dep_adj_lc_dx`** (or similar) — model-predicted level complete count for LC Model Bias
5. ~~`lc_conversions_d1/d3/d7`~~ — **Resolved:** confirmed column is `cum_app_event_level_complete_count_dx` in the source table. Needs to be added to the query.
6. ~~`iap_purchase_count_dx` vs `iap_conversions_dx`~~ — **Resolved:** `op.payer_conversions_dx` is the confirmed column. Raw value = purchase count; `CASE WHEN > 0 THEN 1` = payer count (binary).

---

## Structural Notes

- The current query filters `campaign_type IN ('roas')`. For CPE, use `campaign_type = 'appEventConversion'` (confirmed).
- The `roas_types` dimension (`iap`, `adRevenue`, `adRevenue,iap`) is ROAS-specific. CPE campaigns likely have an **event type** dimension (retention / payer / level_complete) that would replace or supplement it — the column name for this is not visible in the current query.
- The outer query's `GROUP BY` and `SELECT` dimensions (`roas_types`, `post_install_window`, `treatment_name`) would need to be extended or replaced with the CPE event type equivalent.

---

## Recommended Next Step

Run a schema inspection on the source table to confirm which missing columns exist:

```sql
SELECT column_name, data_type
FROM `unity-data-ads-core-prd.ads_demand_supply_unity.INFORMATION_SCHEMA.COLUMNS`
WHERE table_name = 'ads_operativeecpm_post_installs_ep_daily_enriched'
ORDER BY ordinal_position
```

---

## Extended Query with CPE Metrics

One item still needs schema verification before running:

| Placeholder | What it is | Status |
|-------------|-----------|--------|
| `op.cum_app_event_level_complete_count_d1/d3/d7` | Suffix `_d1/d3/d7` assumed — confirm naming | needs verification |

`target_cpe` is **confirmed not in the source table** — all `tcpe_*` columns and Product Bias formulas are commented out pending a future solution. Three Model Bias blocks are also left as `TODO` comments pending predicted-value column names.

```sql
WITH experiment_revisions_raw AS (
  SELECT
    experiment_id,
    experiment_revision,
    experiment_name,
    t.treatment_id,
    t.treatment_revisional_id,
    t.treatment_name,
    t.allocation_ratio,
    t.is_control,
    DATE(revision_start_date)                                AS revision_start_date,
    COALESCE(DATE(revision_end_date), CURRENT_DATE())        AS revision_end_date,
    exp_group.name AS experimentation_group,
    exp_group.id   AS experimentation_group_id,
    CASE WHEN t.is_control = True then 0 else t.treatment_revisional_id END AS treatment_order
  FROM `unity-ads-experimentation-prd.experiment_definitions.experiment_revisions_v3` AS erv3,
  UNNEST(treatments) AS t
  WHERE 1 = 1
  and owner != '#ep-restricted-experiments-notifications'
  GROUP BY ALL
),

-- Diemnsion data for game_profiles and developers
game_dev_dimensions AS (
  SELECT
    game_id,
    project_name as game_name,
    platform,
    st_game_genre,
    st_game_subgenre,
    gp.developer_id,
    dev.name as developer_name
  FROM `unity-data-ads-core-prd.ads_dimension_data.game_profiles` AS gp
  LEFT JOIN `unity-data-ads-core-prd.ads_dimension_data.developers` AS dev
  ON gp.developer_id = dev.developer_id
  GROUP BY ALL
),

-- Based on CVR team's definition
country_tier_map AS (
  SELECT country_code, country_tier FROM UNNEST([
    STRUCT('US' AS country_code, 'Tier 0' AS country_tier)
  ])
  UNION ALL
  SELECT country_code, 'Tier 1' FROM UNNEST([
    'JP','RU','GB','DE','CA','KR','AU','FR'
  ]) AS country_code
  UNION ALL
  SELECT country_code, 'Tier 2' FROM UNNEST([
    'TW','SA','IT','NL','ES','CH','HK','NZ','SE','AT','AE','BE','DK','SG','NO',
    'KW','FI','QA','MO','IS','MC','BR','MX','PL','TR','ID','IN'
  ]) AS country_code
),

-- Aggregate additive post-install signals by treatment arm
metrics AS (
  SELECT
    op.submit_date,
    op.experiment_id,
    er.experiment_revision,
    er.experimentation_group,
    er.experiment_name,
    op.platform,
    er.treatment_name,
    er.is_control,
    er.treatment_order,

    -- Additional Dimensions for Breakdowns
    op.model_type,
    op.ad_format,
    op.campaign_type,
    COALESCE(ct.country_tier, 'Tier 3') as cvr_country_tier,
    CASE WHEN op.roas_types IS NULL THEN 'unknown' ELSE op.roas_types END as roas_types,
    CASE WHEN op.app_events_campaign_type IS NULL THEN 'unknown' ELSE op.app_events_campaign_type END AS cpe_types,
    CASE WHEN ct.country_tier IN ('Tier 0', 'Tier 1', 'Tier 2') THEN op.country ELSE 'Tier 3+ countries' END AS country,
    op.target_developer_id,
    op.target_game_id,
    op.post_install_window,

    MAX(er.allocation_ratio)                             AS allocation_ratio,
    MIN(op.submit_date)                                  AS first_date,
    MAX(op.submit_date)                                  AS last_date,

    -- Business Metrics
    SUM(COALESCE(op.starts, 0))                          AS starts,
    SUM(COALESCE(op.spend_sum, 0))                       AS advertiser_spend,
    SUM(COALESCE(op.publisher_revenue, 0))               AS publisher_revenue,
    SUM(COALESCE(op.spend_sum, 0) - COALESCE(op.publisher_revenue, 0)) AS net_revenue,

    -- Total installs attributed to the arm (all campaign types)
    SUM(COALESCE(op.outcomes_installs, 0))               AS installs,

    -- ROAS-campaign installs with day-maturity gates (for denominators)
    COALESCE(SUM(CASE WHEN op.campaign_type = 'roas' THEN IF(DATE_DIFF(CURRENT_DATE(), DATE(op.start_hour), DAY) >= 2,  op.outcomes_installs, 0) ELSE NULL END), 0) AS roas_installs_d0,
    COALESCE(SUM(CASE WHEN op.campaign_type = 'roas' THEN IF(DATE_DIFF(CURRENT_DATE(), DATE(op.start_hour), DAY) >= 3,  op.outcomes_installs, 0) ELSE NULL END), 0) AS roas_installs_d1,
    COALESCE(SUM(CASE WHEN op.campaign_type = 'roas' THEN IF(DATE_DIFF(CURRENT_DATE(), DATE(op.start_hour), DAY) >= 5,  op.outcomes_installs, 0) ELSE NULL END), 0) AS roas_installs_d3,
    COALESCE(SUM(CASE WHEN op.campaign_type = 'roas' THEN IF(DATE_DIFF(CURRENT_DATE(), DATE(op.start_hour), DAY) >= 9,  op.outcomes_installs, 0) ELSE NULL END), 0) AS roas_installs_d7,
    COALESCE(SUM(CASE WHEN op.campaign_type = 'roas' THEN IF(DATE_DIFF(CURRENT_DATE(), DATE(op.start_hour), DAY) >= 16, op.outcomes_installs, 0) ELSE NULL END), 0) AS roas_installs_d14,
    COALESCE(SUM(CASE WHEN op.campaign_type = 'roas' THEN IF(DATE_DIFF(CURRENT_DATE(), DATE(op.start_hour), DAY) >= 30, op.outcomes_installs, 0) ELSE NULL END), 0) AS roas_installs_d28,

    -- Actual spend (ROAS campaigns) filtered by day maturity gate
    COALESCE(SUM(CASE WHEN op.campaign_type = 'roas' THEN IF(DATE_DIFF(CURRENT_DATE(), DATE(op.start_hour), DAY) >= 2,  op.spend_sum, 0) ELSE NULL END), 0) AS roas_spend_d0,
    COALESCE(SUM(CASE WHEN op.campaign_type = 'roas' THEN IF(DATE_DIFF(CURRENT_DATE(), DATE(op.start_hour), DAY) >= 3,  op.spend_sum, 0) ELSE NULL END), 0) AS roas_spend_d1,
    COALESCE(SUM(CASE WHEN op.campaign_type = 'roas' THEN IF(DATE_DIFF(CURRENT_DATE(), DATE(op.start_hour), DAY) >= 5,  op.spend_sum, 0) ELSE NULL END), 0) AS roas_spend_d3,
    COALESCE(SUM(CASE WHEN op.campaign_type = 'roas' THEN IF(DATE_DIFF(CURRENT_DATE(), DATE(op.start_hour), DAY) >= 9,  op.spend_sum, 0) ELSE NULL END), 0) AS roas_spend_d7,
    COALESCE(SUM(CASE WHEN op.campaign_type = 'roas' THEN IF(DATE_DIFF(CURRENT_DATE(), DATE(op.start_hour), DAY) >= 16, op.spend_sum, 0) ELSE NULL END), 0) AS roas_spend_d14,
    COALESCE(SUM(CASE WHEN op.campaign_type = 'roas' THEN IF(DATE_DIFF(CURRENT_DATE(), DATE(op.start_hour), DAY) >= 30, op.spend_sum, 0) ELSE NULL END), 0) AS roas_spend_d28,

    -- Composite user value (iap / adrev / both, depending on roas_types)
    SUM(CASE WHEN op.roas_types = 'iap'          THEN IFNULL(op.iap_revenue_by_d0, 0)
             WHEN op.roas_types = 'adRevenue'    THEN IFNULL(op.adrev_revenue_by_d0, 0)
             WHEN op.roas_types = 'adRevenue,iap' THEN IFNULL(op.iap_revenue_by_d0, 0) + IFNULL(op.adrev_revenue_by_d0, 0)
             ELSE 0 END) AS user_value_d0,
    SUM(CASE WHEN op.roas_types = 'iap'          THEN IFNULL(op.iap_revenue_by_d1, 0)
             WHEN op.roas_types = 'adRevenue'    THEN IFNULL(op.adrev_revenue_by_d1, 0)
             WHEN op.roas_types = 'adRevenue,iap' THEN IFNULL(op.iap_revenue_by_d1, 0) + IFNULL(op.adrev_revenue_by_d1, 0)
             ELSE 0 END) AS user_value_d1,
    SUM(CASE WHEN op.roas_types = 'iap'          THEN IFNULL(op.iap_revenue_by_d3, 0)
             WHEN op.roas_types = 'adRevenue'    THEN IFNULL(op.adrev_revenue_by_d3, 0)
             WHEN op.roas_types = 'adRevenue,iap' THEN IFNULL(op.iap_revenue_by_d3, 0) + IFNULL(op.adrev_revenue_by_d3, 0)
             ELSE 0 END) AS user_value_d3,
    SUM(CASE WHEN op.roas_types = 'iap'          THEN IFNULL(op.iap_revenue_by_d7, 0)
             WHEN op.roas_types = 'adRevenue'    THEN IFNULL(op.adrev_revenue_by_d7, 0)
             WHEN op.roas_types = 'adRevenue,iap' THEN IFNULL(op.iap_revenue_by_d7, 0) + IFNULL(op.adrev_revenue_by_d7, 0)
             ELSE 0 END) AS user_value_d7,
    SUM(CASE WHEN op.roas_types = 'iap'          THEN IFNULL(op.iap_revenue_by_d14, 0)
             WHEN op.roas_types = 'adRevenue'    THEN IFNULL(op.adrev_revenue_by_d14, 0)
             WHEN op.roas_types = 'adRevenue,iap' THEN IFNULL(op.iap_revenue_by_d14, 0) + IFNULL(op.adrev_revenue_by_d14, 0)
             ELSE 0 END) AS user_value_d14,
    SUM(CASE WHEN op.roas_types = 'iap'          THEN IFNULL(op.iap_revenue_by_d28, 0)
             WHEN op.roas_types = 'adRevenue'    THEN IFNULL(op.adrev_revenue_by_d28, 0)
             WHEN op.roas_types = 'adRevenue,iap' THEN IFNULL(op.iap_revenue_by_d28, 0) + IFNULL(op.adrev_revenue_by_d28, 0)
             ELSE 0 END) AS user_value_d28,

    -- Target ROAS × spend (proxy for expected revenue at each day)
    COALESCE(SUM(CASE WHEN op.campaign_type = 'roas' THEN CASE WHEN DATE_DIFF(CURRENT_DATE(), DATE(op.start_hour), DAY) >= 2  THEN IFNULL(op.spend_sum, 0) * IFNULL(op.max_roas_target_undiscounted, 0) END ELSE NULL END), 0) AS troas_spend_d0,
    COALESCE(SUM(CASE WHEN op.campaign_type = 'roas' THEN CASE WHEN DATE_DIFF(CURRENT_DATE(), DATE(op.start_hour), DAY) >= 3  THEN IFNULL(op.spend_sum, 0) * IFNULL(op.max_roas_target_undiscounted, 0) END ELSE NULL END), 0) AS troas_spend_d1,
    COALESCE(SUM(CASE WHEN op.campaign_type = 'roas' THEN CASE WHEN DATE_DIFF(CURRENT_DATE(), DATE(op.start_hour), DAY) >= 5  THEN IFNULL(op.spend_sum, 0) * IFNULL(op.max_roas_target_undiscounted, 0) END ELSE NULL END), 0) AS troas_spend_d3,
    COALESCE(SUM(CASE WHEN op.campaign_type = 'roas' THEN CASE WHEN DATE_DIFF(CURRENT_DATE(), DATE(op.start_hour), DAY) >= 9  THEN IFNULL(op.spend_sum, 0) * IFNULL(op.max_roas_target_undiscounted, 0) END ELSE NULL END), 0) AS troas_spend_d7,
    COALESCE(SUM(CASE WHEN op.campaign_type = 'roas' THEN CASE WHEN DATE_DIFF(CURRENT_DATE(), DATE(op.start_hour), DAY) >= 16 THEN IFNULL(op.spend_sum, 0) * IFNULL(op.max_roas_target_undiscounted, 0) END ELSE NULL END), 0) AS troas_spend_d14,
    COALESCE(SUM(CASE WHEN op.campaign_type = 'roas' THEN CASE WHEN DATE_DIFF(CURRENT_DATE(), DATE(op.start_hour), DAY) >= 30 THEN IFNULL(op.spend_sum, 0) * IFNULL(op.max_roas_target_undiscounted, 0) END ELSE NULL END), 0) AS troas_spend_d28,

    -- IAP depositors (iap or combined roas_types only)
    COALESCE(SUM(CASE WHEN op.roas_types IN ('iap', 'adRevenue,iap') THEN IFNULL(op.iap_conversions_d0, 0) ELSE 0 END), 0)  AS iap_deposits_d0,
    COALESCE(SUM(CASE WHEN op.roas_types IN ('iap', 'adRevenue,iap') THEN IFNULL(op.iap_conversions_d1, 0) ELSE 0 END), 0)  AS iap_deposits_d1,
    COALESCE(SUM(CASE WHEN op.roas_types IN ('iap', 'adRevenue,iap') THEN IFNULL(op.iap_conversions_d3, 0) ELSE 0 END), 0)  AS iap_deposits_d3,
    COALESCE(SUM(CASE WHEN op.roas_types IN ('iap', 'adRevenue,iap') THEN IFNULL(op.iap_conversions_d7, 0) ELSE 0 END), 0)  AS iap_deposits_d7,
    COALESCE(SUM(CASE WHEN op.roas_types IN ('iap', 'adRevenue,iap') THEN IFNULL(op.iap_conversions_d14, 0) ELSE 0 END), 0) AS iap_deposits_d14,
    COALESCE(SUM(CASE WHEN op.roas_types IN ('iap', 'adRevenue,iap') THEN IFNULL(op.iap_conversions_d28, 0) ELSE 0 END), 0) AS iap_deposits_d28,

    -- Retention
    COALESCE(SUM(op.retained_d0),  0) AS retained_d0,
    COALESCE(SUM(op.retained_d1),  0) AS retained_d1,
    COALESCE(SUM(op.retained_d3),  0) AS retained_d3,
    COALESCE(SUM(op.retained_d7),  0) AS retained_d7,
    COALESCE(SUM(op.retained_d14), 0) AS retained_d14,
    COALESCE(SUM(op.retained_d28), 0) AS retained_d28,

    -- For iap_product_model_adj_bias
    COALESCE(SUM(CASE WHEN DATE_DIFF(CURRENT_DATE(), submit_date, DAY) >= 3  THEN dep_adj_value_installs ELSE NULL END), 0) AS dep_adj_value_installs_d1,
    COALESCE(SUM(CASE WHEN DATE_DIFF(CURRENT_DATE(), submit_date, DAY) >= 5  THEN dep_adj_value_installs ELSE NULL END), 0) AS dep_adj_value_installs_d3,
    COALESCE(SUM(CASE WHEN DATE_DIFF(CURRENT_DATE(), submit_date, DAY) >= 9  THEN dep_adj_value_installs ELSE NULL END), 0) AS dep_adj_value_installs_d7,
    COALESCE(SUM(CASE WHEN DATE_DIFF(CURRENT_DATE(), submit_date, DAY) >= 16 THEN dep_adj_value_installs ELSE NULL END), 0) AS dep_adj_value_installs_d14,
    COALESCE(SUM(CASE WHEN DATE_DIFF(CURRENT_DATE(), submit_date, DAY) >= 30 THEN dep_adj_value_installs ELSE NULL END), 0) AS dep_adj_value_installs_d28,
    COALESCE(SUM(CASE WHEN op.roas_types IN ('iap', 'adRevenue,iap') THEN IFNULL(op.iap_revenue_by_d1, 0) ELSE 0 END), 0) AS iap_revenue_d1,
    COALESCE(SUM(CASE WHEN op.roas_types IN ('iap', 'adRevenue,iap') THEN IFNULL(op.iap_revenue_by_d3, 0) ELSE 0 END), 0) AS iap_revenue_d3,
    COALESCE(SUM(CASE WHEN op.roas_types IN ('iap', 'adRevenue,iap') THEN IFNULL(op.iap_revenue_by_d7, 0) ELSE 0 END), 0) AS iap_revenue_d7,
    COALESCE(SUM(CASE WHEN op.roas_types IN ('iap', 'adRevenue,iap') THEN IFNULL(op.iap_revenue_by_d14, 0) ELSE 0 END), 0) AS iap_revenue_d14,
    COALESCE(SUM(CASE WHEN op.roas_types IN ('iap', 'adRevenue,iap') THEN IFNULL(op.iap_revenue_by_d28, 0) ELSE 0 END), 0) AS iap_revenue_d28,

    -- For adrev_product_model_adj_bias_d0 / d7
    COALESCE(SUM(CASE WHEN DATE_DIFF(CURRENT_DATE(), op.submit_date, DAY) >= 2  THEN IF(op.installs_adjusted_adrev_value = 0, op.installs_predicted_adrev_value, op.installs_adjusted_adrev_value) ELSE NULL END), 0) AS adrev_model_value_d0,
    COALESCE(SUM(CASE WHEN DATE_DIFF(CURRENT_DATE(), op.submit_date, DAY) >= 3  THEN IF(op.installs_adjusted_adrev_value = 0, op.installs_predicted_adrev_value, op.installs_adjusted_adrev_value) ELSE NULL END), 0) AS adrev_model_value_d1,
    COALESCE(SUM(CASE WHEN DATE_DIFF(CURRENT_DATE(), op.submit_date, DAY) >= 5  THEN IF(op.installs_adjusted_adrev_value = 0, op.installs_predicted_adrev_value, op.installs_adjusted_adrev_value) ELSE NULL END), 0) AS adrev_model_value_d3,
    COALESCE(SUM(CASE WHEN DATE_DIFF(CURRENT_DATE(), op.submit_date, DAY) >= 9  THEN IF(op.installs_adjusted_adrev_value = 0, op.installs_predicted_adrev_value, op.installs_adjusted_adrev_value) ELSE NULL END), 0) AS adrev_model_value_d7,
    COALESCE(SUM(CASE WHEN DATE_DIFF(CURRENT_DATE(), op.submit_date, DAY) >= 16 THEN IF(op.installs_adjusted_adrev_value = 0, op.installs_predicted_adrev_value, op.installs_adjusted_adrev_value) ELSE NULL END), 0) AS adrev_model_value_d14,
    COALESCE(SUM(CASE WHEN DATE_DIFF(CURRENT_DATE(), op.submit_date, DAY) >= 30 THEN IF(op.installs_adjusted_adrev_value = 0, op.installs_predicted_adrev_value, op.installs_adjusted_adrev_value) ELSE NULL END), 0) AS adrev_model_value_d28,

    COALESCE(SUM(CASE WHEN op.roas_types IN ('adRevenue', 'adRevenue,iap') THEN IFNULL(op.adrev_revenue_by_d0, 0) ELSE 0 END), 0) AS adrev_revenue_d0,
    COALESCE(SUM(CASE WHEN op.roas_types IN ('adRevenue', 'adRevenue,iap') THEN IFNULL(op.adrev_revenue_by_d1, 0) ELSE 0 END), 0) AS adrev_revenue_d1,
    COALESCE(SUM(CASE WHEN op.roas_types IN ('adRevenue', 'adRevenue,iap') THEN IFNULL(op.adrev_revenue_by_d3, 0) ELSE 0 END), 0) AS adrev_revenue_d3,
    COALESCE(SUM(CASE WHEN op.roas_types IN ('adRevenue', 'adRevenue,iap') THEN IFNULL(op.adrev_revenue_by_d7, 0) ELSE 0 END), 0) AS adrev_revenue_d7,
    COALESCE(SUM(CASE WHEN op.roas_types IN ('adRevenue', 'adRevenue,iap') THEN IFNULL(op.adrev_revenue_by_d14, 0) ELSE 0 END), 0) AS adrev_revenue_d14,
    COALESCE(SUM(CASE WHEN op.roas_types IN ('adRevenue', 'adRevenue,iap') THEN IFNULL(op.adrev_revenue_by_d28, 0) ELSE 0 END), 0) AS adrev_revenue_d28,

    -- For negative_gap_d0 / d7  (pre-aggregate the clamped shortfall × spend)
    COALESCE(SUM(CASE WHEN op.campaign_type = 'roas' AND DATE_DIFF(CURRENT_DATE, DATE(op.start_hour), DAY) >= 2
      THEN IFNULL(op.spend_sum, 0) * GREATEST(0, 1 - SAFE_DIVIDE(
        CASE WHEN op.roas_types = 'iap'           THEN IFNULL(op.iap_revenue_by_d0, 0)
             WHEN op.roas_types = 'adRevenue'     THEN IFNULL(op.adrev_revenue_by_d0, 0)
             WHEN op.roas_types = 'adRevenue,iap' THEN IFNULL(op.iap_revenue_by_d0, 0) + IFNULL(op.adrev_revenue_by_d0, 0)
             ELSE 0 END,
        IFNULL(op.spend_sum, 0) * IFNULL(op.max_roas_target_undiscounted, 0)))
      ELSE NULL END), 0) AS negative_gap_spend_d0,

    COALESCE(SUM(CASE WHEN op.campaign_type = 'roas' AND DATE_DIFF(CURRENT_DATE, DATE(op.start_hour), DAY) >= 9
      THEN IFNULL(op.spend_sum, 0) * GREATEST(0, 1 - SAFE_DIVIDE(
        CASE WHEN op.roas_types = 'iap'           THEN IFNULL(op.iap_revenue_by_d7, 0)
             WHEN op.roas_types = 'adRevenue'     THEN IFNULL(op.adrev_revenue_by_d7, 0)
             WHEN op.roas_types = 'adRevenue,iap' THEN IFNULL(op.iap_revenue_by_d7, 0) + IFNULL(op.adrev_revenue_by_d7, 0)
             ELSE 0 END,
        IFNULL(op.spend_sum, 0) * IFNULL(op.max_roas_target_undiscounted, 0)))
      ELSE NULL END), 0) AS negative_gap_spend_d7,

    -- -------------------------------------------------------------------------
    -- CPE metrics (campaign_type = 'appEventConversion')
    -- -------------------------------------------------------------------------

    -- CPE installs with day-maturity gates (denominators for CPE rates)
    COALESCE(SUM(CASE WHEN op.campaign_type = 'appEventConversion' THEN IF(DATE_DIFF(CURRENT_DATE(), DATE(op.start_hour), DAY) >= 3, op.outcomes_installs, 0) ELSE NULL END), 0) AS cpe_installs_d1,
    COALESCE(SUM(CASE WHEN op.campaign_type = 'appEventConversion' THEN IF(DATE_DIFF(CURRENT_DATE(), DATE(op.start_hour), DAY) >= 5, op.outcomes_installs, 0) ELSE NULL END), 0) AS cpe_installs_d3,
    COALESCE(SUM(CASE WHEN op.campaign_type = 'appEventConversion' THEN IF(DATE_DIFF(CURRENT_DATE(), DATE(op.start_hour), DAY) >= 9, op.outcomes_installs, 0) ELSE NULL END), 0) AS cpe_installs_d7,

    -- CPE actual spend filtered by day maturity gate
    COALESCE(SUM(CASE WHEN op.campaign_type = 'appEventConversion' THEN IF(DATE_DIFF(CURRENT_DATE(), DATE(op.start_hour), DAY) >= 3, op.spend_sum, 0) ELSE NULL END), 0) AS cpe_spend_d1,
    COALESCE(SUM(CASE WHEN op.campaign_type = 'appEventConversion' THEN IF(DATE_DIFF(CURRENT_DATE(), DATE(op.start_hour), DAY) >= 5, op.spend_sum, 0) ELSE NULL END), 0) AS cpe_spend_d3,
    COALESCE(SUM(CASE WHEN op.campaign_type = 'appEventConversion' THEN IF(DATE_DIFF(CURRENT_DATE(), DATE(op.start_hour), DAY) >= 9, op.spend_sum, 0) ELSE NULL END), 0) AS cpe_spend_d7,

    -- CPE Retention: maturity-gated retained counts
    -- Superset metrics: retention_rate_dx = cpe_retained_dx / cpe_installs_dx
    --                   observed_cpe      = cpe_spend_d7 / cpe_retained_d7
    COALESCE(SUM(CASE WHEN op.campaign_type = 'appEventConversion' AND DATE_DIFF(CURRENT_DATE(), DATE(op.start_hour), DAY) >= 3 THEN IFNULL(op.retained_d1, 0) ELSE NULL END), 0) AS cpe_retained_d1,
    COALESCE(SUM(CASE WHEN op.campaign_type = 'appEventConversion' AND DATE_DIFF(CURRENT_DATE(), DATE(op.start_hour), DAY) >= 5 THEN IFNULL(op.retained_d3, 0) ELSE NULL END), 0) AS cpe_retained_d3,
    COALESCE(SUM(CASE WHEN op.campaign_type = 'appEventConversion' AND DATE_DIFF(CURRENT_DATE(), DATE(op.start_hour), DAY) >= 9 THEN IFNULL(op.retained_d7, 0) ELSE NULL END), 0) AS cpe_retained_d7,

    -- TODO: Target CPE × retained count — target_cpe not in source table, enable when available
    -- Superset metric when available: product_bias_dx = cpe_spend_dx / tcpe_retained_dx - 1
    -- COALESCE(SUM(CASE WHEN op.campaign_type = 'appEventConversion' AND DATE_DIFF(CURRENT_DATE(), DATE(op.start_hour), DAY) >= 3 THEN IFNULL(op.retained_d1, 0) * IFNULL(op.target_cpe, 0) ELSE NULL END), 0) AS tcpe_retained_d1,
    -- COALESCE(SUM(CASE WHEN op.campaign_type = 'appEventConversion' AND DATE_DIFF(CURRENT_DATE(), DATE(op.start_hour), DAY) >= 5 THEN IFNULL(op.retained_d3, 0) * IFNULL(op.target_cpe, 0) ELSE NULL END), 0) AS tcpe_retained_d3,
    -- COALESCE(SUM(CASE WHEN op.campaign_type = 'appEventConversion' AND DATE_DIFF(CURRENT_DATE(), DATE(op.start_hour), DAY) >= 9 THEN IFNULL(op.retained_d7, 0) * IFNULL(op.target_cpe, 0) ELSE NULL END), 0) AS tcpe_retained_d7,

    -- TODO: Retention Model Bias — add once predicted column name confirmed
    --   dep_adj_retained_dx  (model-predicted retained count, analogous to dep_adj_value_installs for IAP)
    --   Superset metric: model_bias_d7 = dep_adj_retained_d7 / cpe_retained_d7 - 1

    -- CPE Payer: binary payer count (did install make any purchase?) and total purchase count
    -- Superset metrics: payer_rate_dx     = cpe_payer_count_dx / cpe_installs_dx
    --                   purchase_rate_dx  = cpe_purchase_count_dx / cpe_installs_dx
    --                   observed_cpe      = cpe_spend_d7 / cpe_payer_count_d7
    COALESCE(SUM(CASE WHEN op.campaign_type = 'appEventConversion' AND DATE_DIFF(CURRENT_DATE(), DATE(op.start_hour), DAY) >= 3 THEN IF(IFNULL(op.payer_conversions_d1, 0) > 0, 1, 0) ELSE NULL END), 0) AS cpe_payer_count_d1,
    COALESCE(SUM(CASE WHEN op.campaign_type = 'appEventConversion' AND DATE_DIFF(CURRENT_DATE(), DATE(op.start_hour), DAY) >= 5 THEN IF(IFNULL(op.payer_conversions_d3, 0) > 0, 1, 0) ELSE NULL END), 0) AS cpe_payer_count_d3,
    COALESCE(SUM(CASE WHEN op.campaign_type = 'appEventConversion' AND DATE_DIFF(CURRENT_DATE(), DATE(op.start_hour), DAY) >= 9 THEN IF(IFNULL(op.payer_conversions_d7, 0) > 0, 1, 0) ELSE NULL END), 0) AS cpe_payer_count_d7,

    COALESCE(SUM(CASE WHEN op.campaign_type = 'appEventConversion' AND DATE_DIFF(CURRENT_DATE(), DATE(op.start_hour), DAY) >= 3 THEN IFNULL(op.payer_conversions_d1, 0) ELSE NULL END), 0) AS cpe_purchase_count_d1,
    COALESCE(SUM(CASE WHEN op.campaign_type = 'appEventConversion' AND DATE_DIFF(CURRENT_DATE(), DATE(op.start_hour), DAY) >= 5 THEN IFNULL(op.payer_conversions_d3, 0) ELSE NULL END), 0) AS cpe_purchase_count_d3,
    COALESCE(SUM(CASE WHEN op.campaign_type = 'appEventConversion' AND DATE_DIFF(CURRENT_DATE(), DATE(op.start_hour), DAY) >= 9 THEN IFNULL(op.payer_conversions_d7, 0) ELSE NULL END), 0) AS cpe_purchase_count_d7,

    -- TODO: Target CPE × payer count — target_cpe not in source table, enable when available
    -- Superset metric when available: product_bias_dx = cpe_spend_dx / tcpe_payer_dx - 1
    -- COALESCE(SUM(CASE WHEN op.campaign_type = 'appEventConversion' AND DATE_DIFF(CURRENT_DATE(), DATE(op.start_hour), DAY) >= 3 THEN IF(IFNULL(op.payer_conversions_d1, 0) > 0, 1, 0) * IFNULL(op.target_cpe, 0) ELSE NULL END), 0) AS tcpe_payer_d1,
    -- COALESCE(SUM(CASE WHEN op.campaign_type = 'appEventConversion' AND DATE_DIFF(CURRENT_DATE(), DATE(op.start_hour), DAY) >= 5 THEN IF(IFNULL(op.payer_conversions_d3, 0) > 0, 1, 0) * IFNULL(op.target_cpe, 0) ELSE NULL END), 0) AS tcpe_payer_d3,
    -- COALESCE(SUM(CASE WHEN op.campaign_type = 'appEventConversion' AND DATE_DIFF(CURRENT_DATE(), DATE(op.start_hour), DAY) >= 9 THEN IF(IFNULL(op.payer_conversions_d7, 0) > 0, 1, 0) * IFNULL(op.target_cpe, 0) ELSE NULL END), 0) AS tcpe_payer_d7,

    -- TODO: Payer Model Bias — add once predicted column name confirmed
    --   dep_adj_payer_dx  (model-predicted payer count)
    --   Superset metric: model_bias_d7 = dep_adj_payer_d7 / cpe_payer_count_d7 - 1

    -- CPE Level Complete: cumulative level complete counts with maturity gates
    -- Superset metrics: lc_rate_dx   = cpe_lc_count_dx / cpe_installs_dx
    --                   observed_cpe = cpe_spend_d7 / cpe_lc_count_d7
    COALESCE(SUM(CASE WHEN op.campaign_type = 'appEventConversion' AND DATE_DIFF(CURRENT_DATE(), DATE(op.start_hour), DAY) >= 3 THEN IFNULL(op.cum_app_event_level_complete_count_d1, 0) ELSE NULL END), 0) AS cpe_lc_count_d1,
    COALESCE(SUM(CASE WHEN op.campaign_type = 'appEventConversion' AND DATE_DIFF(CURRENT_DATE(), DATE(op.start_hour), DAY) >= 5 THEN IFNULL(op.cum_app_event_level_complete_count_d3, 0) ELSE NULL END), 0) AS cpe_lc_count_d3,
    COALESCE(SUM(CASE WHEN op.campaign_type = 'appEventConversion' AND DATE_DIFF(CURRENT_DATE(), DATE(op.start_hour), DAY) >= 9 THEN IFNULL(op.cum_app_event_level_complete_count_d7, 0) ELSE NULL END), 0) AS cpe_lc_count_d7

    -- TODO: Target CPE × LC count — target_cpe not in source table, enable when available
    -- Superset metric when available: product_bias_dx = cpe_spend_dx / tcpe_lc_dx - 1
    -- COALESCE(SUM(CASE WHEN op.campaign_type = 'appEventConversion' AND DATE_DIFF(CURRENT_DATE(), DATE(op.start_hour), DAY) >= 3 THEN IFNULL(op.cum_app_event_level_complete_count_d1, 0) * IFNULL(op.target_cpe, 0) ELSE NULL END), 0) AS tcpe_lc_d1,
    -- COALESCE(SUM(CASE WHEN op.campaign_type = 'appEventConversion' AND DATE_DIFF(CURRENT_DATE(), DATE(op.start_hour), DAY) >= 5 THEN IFNULL(op.cum_app_event_level_complete_count_d3, 0) * IFNULL(op.target_cpe, 0) ELSE NULL END), 0) AS tcpe_lc_d3,
    -- COALESCE(SUM(CASE WHEN op.campaign_type = 'appEventConversion' AND DATE_DIFF(CURRENT_DATE(), DATE(op.start_hour), DAY) >= 9 THEN IFNULL(op.cum_app_event_level_complete_count_d7, 0) * IFNULL(op.target_cpe, 0) ELSE NULL END), 0) AS tcpe_lc_d7

    -- TODO: LC Model Bias — add once predicted column name confirmed
    --   dep_adj_lc_dx  (model-predicted LC count)
    --   Superset metric: model_bias_d7 = dep_adj_lc_d7 / cpe_lc_count_d7 - 1

  FROM `unity-data-ads-core-prd.ads_demand_supply_unity.ads_operativeecpm_post_installs_ep_daily_enriched` AS op
  INNER JOIN experiment_revisions_raw AS er
    ON  op.experiment_id           = er.experiment_id
    AND op.treatment_revisional_id = er.treatment_revisional_id
    AND op.submit_date BETWEEN er.revision_start_date AND DATE_ADD(er.revision_end_date, INTERVAL 30 DAY)
  LEFT JOIN country_tier_map AS ct ON ct.country_code = op.country
  WHERE TRUE
  GROUP BY ALL
)

SELECT
  submit_date as event_date,
  experiment_id,
  experiment_revision,
  experimentation_group,
  experiment_name,
  metrics.platform,
  treatment_name,
  CASE WHEN is_control THEN 'Control' ELSE 'Treatment' END AS group_type,
  allocation_ratio,
  treatment_order,

  -- Additional Dimensions for Breakdowns
  model_type,
  ad_format,
  campaign_type,
  cvr_country_tier,
  roas_types,
  cpe_types,
  country,
  target_developer_id,
  target_game_id,
  post_install_window,

  -- Dimension data
  dev.developer_name as target_developer_name,
  dev.game_name as target_game_name,
  dev.st_game_genre as target_game_genre,

  -- Business Metrics
  starts, advertiser_spend, publisher_revenue, net_revenue,

  -- Installs
  installs,
  roas_installs_d0, roas_installs_d1, roas_installs_d3,
  roas_installs_d7, roas_installs_d14, roas_installs_d28,

  -- Spend
  roas_spend_d0, roas_spend_d1, roas_spend_d3,
  roas_spend_d7, roas_spend_d14, roas_spend_d28,

  -- User value (revenue earned by cohort)
  user_value_d0, user_value_d1, user_value_d3,
  user_value_d7, user_value_d14, user_value_d28,

  -- tROAS × spend
  troas_spend_d0, troas_spend_d1, troas_spend_d3,
  troas_spend_d7, troas_spend_d14, troas_spend_d28,

  -- IAP depositors
  iap_deposits_d0, iap_deposits_d1, iap_deposits_d3,
  iap_deposits_d7, iap_deposits_d14, iap_deposits_d28,

  -- Retention counts
  retained_d0, retained_d1, retained_d3,
  retained_d7, retained_d14, retained_d28,

  -- For iap_product_model_adj_bias
  dep_adj_value_installs_d1, iap_revenue_d1,
  dep_adj_value_installs_d3, iap_revenue_d3,
  dep_adj_value_installs_d7, iap_revenue_d7,
  dep_adj_value_installs_d14, iap_revenue_d14,
  dep_adj_value_installs_d28, iap_revenue_d28,

  -- For adrev_product_model_adj_bias_d0 / d7
  adrev_model_value_d0, adrev_model_value_d1, adrev_model_value_d3,
  adrev_model_value_d7, adrev_model_value_d14, adrev_model_value_d28,
  adrev_revenue_d0, adrev_revenue_d1, adrev_revenue_d3,
  adrev_revenue_d7, adrev_revenue_d14, adrev_revenue_d28,

  -- For negative_gap_d0 / d7  (pre-aggregate the clamped shortfall × spend)
  negative_gap_spend_d0, negative_gap_spend_d7,

  -- -------------------------------------------------------------------------
  -- CPE metrics
  -- -------------------------------------------------------------------------

  -- CPE installs/spend (maturity-gated denominators)
  cpe_installs_d1, cpe_installs_d3, cpe_installs_d7,
  cpe_spend_d1,    cpe_spend_d3,    cpe_spend_d7,

  -- CPE Retention
  -- Superset: retention_rate_dx = cpe_retained_dx / cpe_installs_dx
  --           observed_cpe      = cpe_spend_d7 / cpe_retained_d7
  --           product_bias_dx (TODO): requires target_cpe — enable tcpe_retained_dx when available
  cpe_retained_d1, cpe_retained_d3, cpe_retained_d7,
  -- tcpe_retained_d1, tcpe_retained_d3, tcpe_retained_d7,  -- TODO: enable when target_cpe available

  -- CPE Payer
  -- Superset: payer_rate_dx    = cpe_payer_count_dx / cpe_installs_dx
  --           purchase_rate_dx = cpe_purchase_count_dx / cpe_installs_dx
  --           observed_cpe     = cpe_spend_d7 / cpe_payer_count_d7
  --           product_bias_dx (TODO): requires target_cpe — enable tcpe_payer_dx when available
  cpe_payer_count_d1,    cpe_payer_count_d3,    cpe_payer_count_d7,
  cpe_purchase_count_d1, cpe_purchase_count_d3, cpe_purchase_count_d7,
  -- tcpe_payer_d1, tcpe_payer_d3, tcpe_payer_d7,  -- TODO: enable when target_cpe available

  -- CPE Level Complete
  -- Superset: lc_rate_dx      = cpe_lc_count_dx / cpe_installs_dx
  --           observed_cpe    = cpe_spend_d7 / cpe_lc_count_d7
  --           product_bias_dx (TODO): requires target_cpe — enable tcpe_lc_dx when available
  cpe_lc_count_d1, cpe_lc_count_d3, cpe_lc_count_d7,
  -- tcpe_lc_d1, tcpe_lc_d3, tcpe_lc_d7,  -- TODO: enable when target_cpe available

  -- Observation window (for data freshness awareness)
  DATE_DIFF(last_date, first_date, DAY) + 1 AS post_install_days,
  FORMAT_DATE('%F', first_date)             AS min_date,
  FORMAT_DATE('%F', last_date)              AS max_date

FROM metrics
LEFT JOIN `game_dev_dimensions` dev
  ON metrics.target_game_id = dev.game_id AND metrics.target_developer_id = dev.developer_id
WHERE TRUE
{% if url_param('experiment_id') %}
  AND experiment_id = '{{ url_param('experiment_id') }}'
{% endif %}
{% if url_param('experiment_revision') %}
  AND experiment_revision = CAST('{{ url_param('experiment_revision') }}' AS INT64)
{% endif %}
{% if not filter_values('experiment_id') and not url_param('experiment_id') %}
  AND submit_date = CURRENT_DATE() - 3  -- safety filter min 1d if no experimentId is present
{% endif %}

ORDER BY experiment_id, experiment_name, experiment_revision, treatment_order, platform
```
