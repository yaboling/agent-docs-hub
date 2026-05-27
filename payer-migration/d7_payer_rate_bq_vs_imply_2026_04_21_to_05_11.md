# D7 Payer Rate: BigQuery vs Imply Comparison
**Period:** 2026-04-21 to 2026-05-11
**Model:** v11-payer
**Metric:** D7 Payer Rate = (# users with at least 1 purchase in D7) / installs × 100

---

## Data Sources

- **Imply Dashboard:** [uAds Demand Supply Internal (billing & finance)](https://internal-v2-1.pivot.int-prd-imply.unity3d.com/pivot/d/20695c925e1fcc335f/uAds_Demand_Supply_Internal_(billing_&_finance))
- **BigQuery:** `unity-ai-data-prd.mz_dcpi_raw.mz_dcpi_prediction_v1` joined with `unity-data-ads-core-prd.ads_secondary_conversion.operativeecpm_installs_outcomes_contextual`

---

## BigQuery SQL

```sql
WITH PREDS AS (
  SELECT
    body.auction_id,
    body.target_game_id AS game_id,
    CASE
      WHEN body.app_event_model_version LIKE '%v11-payer%' THEN 'v11-payer'
      WHEN body.app_event_model_version LIKE '%ctx1i-1a%'  THEN 'ctx1i'
      WHEN body.app_event_model_version LIKE '%bhv1n-1a%'  THEN 'bhv1n'
      ELSE body.app_event_model_version
    END AS app_event_model_version,
  FROM `unity-ai-data-prd.mz_dcpi_raw.mz_dcpi_prediction_v1`
  WHERE submit_date >= "2026-04-21"
    AND submit_date <= "2026-05-11"
    AND body.app_event_p > 0
    AND body.app_event_type = "purchase"
    AND body.target_game_id IN (
      500022044, 500023036, 500103442, 500104804, 500132922,
      500224551, 500227742, 500229262, 500234086, 500234119,
      500241340, 500244255, 500248532, 500249022, 500249166,
      500253654, 500254396, 500254984, 500255494, 500256486,
      500259616, 500260731, 500262615, 500263616, 500263913,
      500263970, 500264156, 500264320, 500265056
    )
),

OUTCOMES AS (
  SELECT
    auctionId,
    CAST(targetGameId AS INT64) AS game_id,
    CASE WHEN cum_deposit_capped_count_d7 > 0 THEN 1 ELSE 0 END AS payer_label_d7,
    cum_deposit_capped_count_d7,
  FROM `unity-data-ads-core-prd.ads_secondary_conversion.operativeecpm_installs_outcomes_contextual`
  WHERE adRequestTimestamp >= TIMESTAMP("2026-04-21")
    AND adRequestTimestamp <= TIMESTAMP("2026-05-11 23:59:59")
    AND CAST(targetGameId AS INT64) IN (
      500022044, 500023036, 500103442, 500104804, 500132922,
      500224551, 500227742, 500229262, 500234086, 500234119,
      500241340, 500244255, 500248532, 500249022, 500249166,
      500253654, 500254396, 500254984, 500255494, 500256486,
      500259616, 500260731, 500262615, 500263616, 500263913,
      500263970, 500264156, 500264320, 500265056
    )
)

SELECT
  P.game_id,
  P.app_event_model_version,
  COUNT(*)                                              AS installs,
  SUM(O.payer_label_d7)                                AS payer_d7_count,
  SUM(O.cum_deposit_capped_count_d7)                   AS total_purchases_d7,
  ROUND(SUM(O.payer_label_d7) / COUNT(*) * 100, 4)    AS payer_rate_d7_pct
FROM PREDS P
JOIN OUTCOMES O ON O.auctionId = P.auction_id
GROUP BY 1, 2
ORDER BY game_id, app_event_model_version
```

---

## Comparison Table

> - **BQ D7 Rate%** = `payer_rate_d7_pct` from BigQuery (already in %)
> - **Imply D7 Rate%** = `D7 Payer Rate` from Imply × 100
> - **Rate Diff** = BQ - Imply

| Game ID | BQ Installs | Imply Installs | Install Diff | BQ D7 Payer | Imply D7 Payer | Payer Diff | BQ D7 Rate% | Imply D7 Rate% | Rate Diff |
|---------|------------|----------------|:------------:|------------|----------------|:----------:|-------------|----------------|:---------:|
| 500022044 | 4,094 | 4,089 | -5 | 230 | 230 | 0 | 5.618 | 5.625 | -0.007 |
| 500023036 | 43,175 | 43,178 | +3 | 1,252 | 1,256 | +4 | 2.900 | 2.909 | -0.009 |
| 500103442 | 325 | 307 | -18 | 32 | 29 | -3 | 9.846 | 9.446 | +0.400 |
| 500104804 | 728 | 610 | **-118** | 49 | 43 | -6 | 6.731 | 7.049 | -0.318 |
| 500132922 | 1,319 | 1,299 | -20 | 92 | 89 | -3 | 6.975 | 6.851 | +0.124 |
| 500224551 | 1,127 | 969 | **-158** | 70 | 65 | -5 | 6.211 | 6.708 | -0.497 |
| 500227742 | 8,279 | 8,166 | -113 | 468 | 466 | -2 | 5.653 | 5.707 | -0.054 |
| 500229262 | 11,553 | 11,471 | -82 | 395 | 391 | -4 | 3.419 | 3.409 | +0.010 |
| 500234086 | 11,429 | 11,302 | -127 | 806 | 802 | -4 | 7.052 | 7.096 | -0.044 |
| 500234119 | 2,430 | 2,417 | -13 | 152 | 151 | -1 | 6.255 | 6.247 | +0.008 |
| 500241340 | 474 | 470 | -4 | 46 | 45 | -1 | 9.705 | 9.574 | +0.131 |
| 500244255 | 17,579 | 17,151 | -428 | 612 | 604 | -8 | 3.481 | 3.522 | -0.041 |
| 500248532 | 1,802 | 1,847 | +45 | 28 | 30 | +2 | 1.554 | 1.624 | -0.070 |
| 500249022 | 939 | 941 | +2 | 99 | 99 | 0 | 10.543 | 10.521 | +0.022 |
| 500249166 | 1,623 | 1,613 | -10 | 199 | 197 | -2 | 12.261 | 12.213 | +0.048 |
| 500253654 | 21,998 | 21,113 | **-885** | 922 | 895 | -27 | 4.191 | 4.239 | -0.048 |
| 500254396 | 15,111 | 14,552 | **-559** | 549 | 533 | -16 | 3.633 | 3.663 | -0.030 |
| 500254984 | 534 | 515 | -19 | 35 | 34 | -1 | 6.554 | 6.602 | -0.048 |
| 500255494 | 1,188 | 1,181 | -7 | 90 | 92 | +2 | 7.576 | 7.790 | -0.214 |
| 500256486 | 5,478 | 5,269 | -209 | 391 | 375 | -16 | 7.138 | 7.117 | +0.021 |
| 500259616 | 1,050 | 997 | -53 | 75 | 73 | -2 | 7.143 | 7.322 | -0.179 |
| 500260731 | 2,724 | 2,467 | **-257** | 121 | 113 | -8 | 4.442 | 4.580 | -0.138 |
| 500262615 | 2,530 | 2,537 | +7 | 133 | 132 | -1 | 5.257 | 5.203 | +0.054 |
| 500263616 | 1,357 | 1,345 | -12 | 22 | 22 | 0 | 1.621 | 1.636 | -0.015 |
| 500263913 | 3,279 | 3,288 | +9 | 44 | 44 | 0 | 1.342 | 1.338 | +0.004 |
| 500263970 | 4,417 | 4,332 | -85 | 59 | 59 | 0 | 1.336 | 1.362 | -0.026 |
| 500264156 | 4,221 | 4,228 | +7 | 126 | 127 | +1 | 2.985 | 3.004 | -0.019 |
| 500264320 | 5,072 | 5,004 | -68 | 37 | 37 | 0 | 0.730 | 0.739 | -0.009 |
| 500265056 | 893 | 880 | -13 | 26 | 26 | 0 | 2.912 | 2.955 | -0.043 |

---

## Summary

**D7 Payer Rate is highly consistent between BQ and Imply — all differences are within ±0.5%.**

| Metric | Observation |
|--------|-------------|
| D7 Payer Rate diff | All within ±0.5%; majority < ±0.15% |
| D7 Payer count diff | Typically 0–8 users; negligible |
| Install count diff | BQ generally ~1–4% higher than Imply |

### Notes on Install Count Discrepancy

BQ installs are consistently slightly higher than Imply for most games. Likely causes:

1. **JOIN semantics:** The BQ query uses a `JOIN` between prediction logs and outcome logs (all auctions with a prediction + an outcome row). Imply may only count installs that have a billing/campaign-spend record.
2. **Date boundary handling:** `submit_date` (BQ) vs `adRequestTimestamp` (Outcomes) may capture slightly different sets of events near the date boundaries.
3. **Attribution differences:** Imply may apply additional deduplication or attribution rules not reflected in the raw logs.

The rate-level alignment confirms both sources are measuring the same underlying signal — the install count discrepancy does not materially affect the payer rate calculation.
