# WBR-UV Query Reference

Complete map of every BigQuery query used in the wbr-uv dashboard — business/delivery
metrics and bias metrics for all products.

---

## Tables

| Alias | Full Table Path |
|-------|-----------------|
| `BIAS_TABLE` | `unity-data-ads-core-prd.ads_secondary_conversion.operative_outcomes_dcpi_join_demand` |
| `GRID_TABLE` | `unity-data-ads-core-prd.ads_demand_supply_unity.direct_demand_daily` |
| `WHALE_TABLE` | `unity-ads-dd-ds-dev-prd.ads_market_intelligence.user_level_post_install_outcomes` |
| `PRED_TABLE` | `unity-ai-data-prd.mz_dcpi_raw.mz_dcpi_prediction_v1` |
| `OUTCOMES_TABLE` | `unity-data-ads-core-prd.ads_secondary_conversion.operativeecpm_installs_outcomes_contextual` |
| `CAMPAIGNS_TABLE` | `unity-data-ads-core-prd.ads_dimension_data.campaigns_v3` |

---

## 1. Business / Delivery Metrics

### 1a. Business Grid — `references/business_grid.sql`

**Source:** `direct_demand_daily`
**Invocations:** One query with `campaign_type, roas_types, app_event_type` in GROUP BY
**Grain:** Weekly (Mon-Sun) x platform x country_group x campaign_type x roas_types x app_event_type

**Raw sums emitted:**

| Column | Derived Metric |
|--------|---------------|
| `SUM(advertiser_spend)` | Advertiser Spend |
| `SUM(publisher_revenue)` | Publisher Revenue |
| `SUM(net_revenue)` | Net Revenue |
| `SUM(starts)` | Starts |
| `SUM(installs)` | Installs (MMP-attributed) |
| `SUM(IF(campaign_dcpi BETWEEN 0 AND 1e12, campaign_dcpi, 0))` | Avg dCPI numerator (capped at $1M, microdollars) |
| `SUM(IF(campaign_dcpi BETWEEN 0 AND @@DCPI_OUTLIER_MICROS@@, ...))` | Avg dCPI numerator (outliers removed, default cutoff $1k) |
| `SUM(IF(..., starts, 0))` | Starts denominator for outlier-removed dCPI |
| `COUNTIF(campaign_dcpi >= @@DCPI_OUTLIER_MICROS@@ AND ...)` | Count of outlier rows |
| `SUM(conversion_prediction_advertiser)` | Install overvaluation numerator |
| `SUM(value_advertiser)` | Spend overvaluation numerator |

**Python-computed ratios (phase2):**
- `MMP eCPI = Σ advertiser_spend / Σ installs`
- `Avg dCPI (capped) = Σ campaign_dcpi_micros / Σ starts / 1e6`
- `Avg dCPI (outliers removed) = Σ dcpi_no_outliers / Σ starts_no_outliers / 1e6`
- `Unity Margin % = Σ net_revenue / Σ advertiser_spend`
- `Install Overvaluation = Σ conversion_prediction_advertiser / Σ installs - 1`
- `Spend Overvaluation = Σ value_advertiser / Σ advertiser_spend - 1`

**Splits reported:**
- `overall` — ROAS + AppEventConversion
- `roas_overall`, `roas_iap`, `roas_adRevenue`, `roas_adRevenue,iap`
- `cpe_overall`, `cpe_purchase`, `cpe_level_complete`, `cpe_retention`

---

### 1b. Top Advertisers — inline `build_advertiser_sql()` (scripts/phase2_data.py)

**Source:** `direct_demand_daily`
**Grain:** Weekly x campaign_type x advertiser (target_developer_id)
**Date range:** Prior week + reporting week

```sql
SELECT
    FORMAT_DATE('%Y-%m-%d', DATE_TRUNC(event_date, WEEK(MONDAY))) AS week_start,
    campaign_type,
    CAST(target_developer_id AS STRING) AS advertiser,
    ANY_VALUE(target_developer_name) AS advertiser_name,
    SUM(advertiser_spend)                              AS spend,
    SUM(installs)                                      AS installs,
    SUM(net_revenue)                                   AS net_revenue,
    SAFE_DIVIDE(SUM(advertiser_spend * roas_target_undiscounted_max),
                SUM(advertiser_spend))                 AS troas,
    SUM(IF(campaign_type='appEventConversion',
           conversion_prediction_advertiser, value_advertiser)) AS uv_prediction
FROM direct_demand_daily
WHERE event_date BETWEEN '<prior_week_start>' AND '<reporting_week_end>'
  AND campaign_type IN ('roas','appEventConversion')
  AND target_developer_id IS NOT NULL
GROUP BY week_start, campaign_type, advertiser
```

Top-10 per campaign_type by spend; spend WoW flagged at +/-10%.

---

## 2. Bias Metrics

### 2a. ROAS Product + Model Bias — `references/bias_queries.sql`

**Source:** `operative_outcomes_dcpi_join_demand`
**Token-substituted and run once per section:**

| Section ID | `roas_types` | Window | `REV_EXPR` | `MODEL_COL` | `MAT_SPEND` | `MAT_MODEL` |
|------------|-------------|--------|-----------|------------|------------|------------|
| `iap_d7` | `iap` | 7 | `iap_revenue_by_d7` | `dep_pred_value_installs` | 9 | 8 |
| `iap_d28` | `iap` | 28 | `iap_revenue_by_d28` | `dep_pred_value_installs` | 30 | 29 |
| `adrev_d0` | `adRevenue` | 0 | `adrev_revenue_by_d0` | `installs_predicted_adrev_value` | 2 | 2 |
| `adrev_d7` | `adRevenue` | 7 | `adrev_revenue_by_d7` | `installs_predicted_adrev_value` | 9 | 8 |
| `adrev_d28` | `adRevenue` | 28 | `adrev_revenue_by_d28` | `installs_predicted_adrev_value` | 30 | 29 |
| `hybrid_d7` | `adRevenue,iap` | 7 | `(iap_revenue_by_d7 + adrev_revenue_by_d7)` | `NULL` (no model) | 9 | 8 |

**Columns emitted (ratio-of-sums at submit_date grain):**

| Column | Bias Family |
|--------|------------|
| `SUM(spend * max_roas_target_undiscounted [matured])` | `num_prod_undisc` -> Product Undiscounted |
| `SUM(spend * max_roas_target [matured])` | `num_prod_disc` -> Product Discounted |
| `SUM(spend * max_roas_target_final [matured])` | `num_prod_final` -> Product Final |
| `SUM(MODEL_COL [matured])` | `num_model` -> Model |
| `SUM(REV_EXPR)` | `den_rev` -> denominator (actual revenue, ungated) |

**Maturity gates (point-in-time as-of report Sunday, not `CURRENT_DATE`):**
- Product: `DATE_DIFF(DATE '@@ASOF@@', DATE(start_hour), DAY) >= MAT_SPEND`
- Model: `DATE_DIFF(DATE '@@ASOF@@', submit_date, DAY) > MAT_MODEL`

**Localization:** For `iap_d7` and `adrev_d7`, the query is re-run with `target_game_id,
target_developer_id` added to SELECT/GROUP BY, restricted to the latest mature week only.
Top 30 games/developers by spend are ranked.

---

### 2b. CPE (App Event) Bias — `references/appev_bias_queries.sql`

**Source:** `mz_dcpi_prediction_v1` INNER JOIN `operativeecpm_installs_outcomes_contextual` on `auction_id`
**Run once per app_event_type:** `purchase`, `level_complete`, `retention`
**Window:** d7 (maturity: MAT_SPEND=9, MAT_MODEL=8)

**Label expressions per event type:**

| `app_event_type` | `LABEL_EXPR` (on outcomes alias `o`) |
|-----------------|--------------------------------------|
| `level_complete` | `CASE WHEN o.app_event_level_complete_count_d7 > 0 THEN 1 ELSE 0 END` |
| `purchase` | `CASE WHEN o.cum_deposit_capped_count_d7 > 0 THEN 1 ELSE 0 END` |
| `retention` | `COALESCE(o.retained_d7, 0)` |

**Columns emitted:**

| Column | Use |
|--------|-----|
| `SUM(pred_matured)` | `num_model` -> Model bias numerator |
| `SUM(cost_matured)` | `num_cost` -> Product bias numerator (oCPE) |
| `SUM(target_cpe)` | `sum_target_cpe` -> for avg_tCPE denominator |
| `SUM(event_label)` | `den_events` -> denominator for both ratios |
| `COUNT(*)` | `n_installs` -> avg_tCPE denominator |

**Python-computed ratios:**
- `Model Bias = Σpred / Σevent_labels`
- `avg_tCPE = Σtarget_cpe / Σinstalls`
- `Product Bias = (Σcost / Σevent_labels) / avg_tCPE`

---

### 2c. Partial Outcomes (Horizon Diagnostics) — inline `build_horizon_sql()` (scripts/phase2_data.py)

**Source:** `operative_outcomes_dcpi_join_demand`
**Purpose:** Shows model-only bias at each dN horizon as a cohort matures. Product bias is
intentionally NOT part of Partial Outcomes (it lives in the Bias Sections).

| Series | `roas_types` | Cohort filter | Horizons |
|--------|-------------|--------------|---------|
| IAP horizon | `iap` | `post_install_window = 'd28'` | d0, d1, d3, d7 |
| adRev horizon | `adRevenue` | `post_install_window = 'd28'` | d0, d7, d28 |

For each horizon `n`:
```sql
SAFE_DIVIDE(
  SUM(CASE WHEN DATE_DIFF(DATE '<asof>', submit_date, DAY) > model_maturity(n)
      THEN <model_expr> END),
  SUM(<rev_col_dN>)
) AS model_d<n>
```

Model expression: raw `dep_pred_value_installs` / `installs_predicted_adrev_value`
(or adjusted `IF(adj=0, pred, adj)` when `model_adjusted=True`).

---

### 2d. CPE Level Complete: Target-Event Model Bias — inline `build_cpe_lc_target_event_sql()` (scripts/phase2_data.py)

**Source:** `mz_dcpi_prediction_v1` + `campaigns_v3` + `operativeecpm_installs_outcomes_contextual`
**Purpose:** Distinguishes general LC model bias (any LC event) from target-event model bias
(campaign's specific `sdk_event_names`).
**Maturity:** `DATE_DIFF(asof, submit_date, DAY) >= 8` (D7 model maturity)

**Output columns:**

| Column | Meaning |
|--------|---------|
| `model_ratio_any_lc` | `Σpred / Σlabel_any_lc` |
| `model_ratio_target_event` | `Σpred(matched) / Σlabel_target_event(matched)` |
| `installs_total` | All installs in window |
| `installs_specific` | Installs matched to a named sdk_event |
| `installs_wildcard` | Installs matched to a wildcard (no sdk_event_names) campaign |

---

### 2e. CPE Level Complete: Product Bias — inline `build_cpe_lc_product_bias_sql()` (scripts/phase2_data.py)

**Source:** Same 3-table join as 2d.
**Product Bias formula:** `Σcost / Σ(event_label x target_CPE) - 1`
**Maturity gate:** `MIN(age_days) >= 8` per submit_date

**Output columns:**

| Column | Meaning |
|--------|---------|
| `product_bias_d7_any` | Product bias against any-LC label |
| `product_bias_d7_target` | Product bias against target-event label |
| `installs` | Row count |

---

## 3. Whale / User-Value Segmentation

### 3a. Whale Cap Ratio + Value Buckets — `references/whale_capped_bias.sql`

**Source:** `user_level_post_install_outcomes`
**Run per window:** d7 and d28 (one query each, matching `iap_d7` / `iap_d28` bias sections)
**Cap:** $1,000 per device (default `@@CAP@@`)

**Output columns (per weekly install cohort x country_group):**

| Column | Meaning |
|--------|---------|
| `n_devices` | Total attributed devices |
| `n_payers` | Devices with IAP > $0 |
| `n_whales` | Devices with IAP > $CAP |
| `iap_uncapped` | Σ raw device IAP |
| `iap_capped` | Σ LEAST(device_iap, CAP) |
| `iap_low` | Revenue from devices with IAP < $10 |
| `iap_mid` | Revenue from $10-$100 devices |
| `iap_high` | Revenue from $100-$CAP devices |
| `iap_whale` | Revenue from >$CAP devices |

**Python-computed (phase2):**
- `cap_ratio r = Σ iap_capped / Σ iap_uncapped`
- `iap_product_bias_capped = uncapped_ratio / r`  (whale-adjusted product bias)
- `whale_impact = uncapped_ratio - capped_ratio`

---

## Query ID -> File Map

| Query ID (internal) | File / Function | Product(s) | Metric Family |
|---------------------|----------------|-----------|--------------|
| `bias:iap_d7` | `bias_queries.sql` | IAP | Product (undisc/disc/final) + Model |
| `bias:iap_d28` | `bias_queries.sql` | IAP | Product + Model |
| `bias:adrev_d0` | `bias_queries.sql` | adRevenue | Product + Model |
| `bias:adrev_d7` | `bias_queries.sql` | adRevenue | Product + Model |
| `bias:adrev_d28` | `bias_queries.sql` | adRevenue | Product + Model |
| `bias:hybrid_d7` | `bias_queries.sql` | Hybrid | Product only (no model) |
| `bias:cpe_purchase_d7` | `appev_bias_queries.sql` | CPE Purchase | Product + Model |
| `bias:cpe_levelcomplete_d7` | `appev_bias_queries.sql` | CPE Level Complete | Product + Model |
| `bias:cpe_retention_d7` | `appev_bias_queries.sql` | CPE Retention | Product + Model |
| `bias_loc:iap_d7` | `bias_queries.sql` + localize | IAP | Product + Model (per-game) |
| `bias_loc:adrev_d7` | `bias_queries.sql` + localize | adRevenue | Product + Model (per-game) |
| `horizon:iap_*` | `build_horizon_sql()` | IAP | Model by horizon (d0/d1/d3/d7) |
| `horizon:adrev_*` | `build_horizon_sql()` | adRevenue | Model by horizon (d0/d7/d28) |
| `cpe_lc:target_event` | `build_cpe_lc_target_event_sql()` | CPE LC | Model (any vs target-event) |
| `cpe_lc:product_bias` | `build_cpe_lc_product_bias_sql()` | CPE LC | Product (any vs target-event) |
| `grid:main` | `business_grid.sql` | All campaign types | Spend, NR, Margin, eCPI, dCPI, Starts, Installs |
| `advertiser:main` | `build_advertiser_sql()` | All | Top-10 advertisers by spend + WoW |
| `whale:d7` | `whale_capped_bias.sql` | IAP | Value buckets + cap ratio |
| `whale:d28` | `whale_capped_bias.sql` | IAP | Value buckets + cap ratio |
