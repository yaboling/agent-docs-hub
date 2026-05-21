# Prediction Inflation Analysis: v11-cpe-lc-3 vs v11-cpe-lc-2 vs Legacy

**Date**: 2026-05-20
**Author**: Yabo Ling
**Context**: v11-cpe-lc-3 deployed to traffic. This document repeats the inflation analysis from `PREDICTION_INFLATION_ANALYSIS_05_14.md` against the new model to evaluate whether the inflation problem has been resolved.

---

## Data Source

```sql
SELECT
    submit_date,
    body.campaign_id,
    body.target_game_id,
    body.app_event_model_version AS app_event_model_version,
    MAX(body.sdk_event_name),
    COUNT(*)         AS start_count,
    AVG(body.app_event_p) AS avg_pred,
    AVG(body.max_cst)     AS avg_target_cpe,
    AVG(body.cst)         AS avg_cost
FROM `unity-ai-data-prd.mz_dcpi_raw.mz_dcpi_prediction_v1`
WHERE submit_date = '2026-05-20'
  AND body.app_event_model_version IN (
      'unified-user-value-v11-cpe-lc-2-model',
      'unified-user-value-v11-cpe-lc-3-model',
      'unified-user-value-tf2-levcom-bhv1p-1b-model',
      'unified-user-value-tf2-levcom-ctx1r-1a-model'
  )
  AND body.app_event_p > 0
  AND body.app_event_type = "level_complete"
GROUP BY 1, 2, 3, 4
ORDER BY 1 DESC, 2, 3, 4
```

Date: 2026-05-20 (single day). Total rows: 6,919 across 4 models.

---

## 1. Headline Result

**v11-cpe-lc-3 has not fixed the prediction inflation.** The aggregate overbid ratio vs legacy is
statistically unchanged from v11-cpe-lc-2.


| Metric                         | v11-cpe-lc-2 | v11-cpe-lc-3 | Δ       |
| ------------------------------ | ------------ | ------------ | ------- |
| Mean avg_pred (all campaigns)  | 0.672        | 0.675        | +0.003  |
| Median avg_pred                | 0.706        | 0.711        | +0.005  |
| Mean overbid ratio vs legacy   | **2.86x**    | **2.79x**    | −0.07x  |
| Campaigns ≥ 2x legacy          | 54.4%        | 57.8%        | +3.4pp  |
| Matched campaign pairs (v3/v2) | —            | 385          | —       |
| v3 pred > v2 pred              | —            | 55.1%        | —       |
| v3 pred < v2 pred              | —            | 44.9%        | —       |

The v3/v2 ratio distribution is tightly centered on 1.0 (median 1.01x), meaning v3 produces
essentially the same inflated predictions as v2 on a campaign-by-campaign basis.

---

## 2. Overbid Bucket Distribution


| Overbid bucket  | v2 campaigns | v2 %  | v2 avg ratio | v3 campaigns | v3 %  | v3 avg ratio |
| --------------- | ------------ | ----- | ------------ | ------------ | ----- | ------------ |
| <1x (v_ lower)  | 6            | 1.6%  | 0.85x        | 6            | 1.6%  | 0.69x        |
| 1–2x            | 166          | 44.0% | 1.51x        | 154          | 40.6% | 1.56x        |
| 2–3x            | 86           | 22.8% | 2.44x        | 100          | 26.4% | 2.41x        |
| 3–5x            | 87           | 23.1% | 3.77x        | 88           | 23.2% | 3.67x        |
| 5–10x           | 26           | 6.9%  | 6.58x        | 25           | 6.6%  | 6.43x        |
| 10–20x          | 5            | 1.3%  | 12.27x       | 5            | 1.3%  | 11.98x       |
| >20x            | 1            | 0.3%  | 51.79x       | 1            | 0.3%  | 28.69x       |

The bucket shapes are nearly identical. The only notable change is the 1–2x bucket shrinks (−3.4pp) while
the 2–3x bucket grows (+3.6pp) in v3, meaning a modest shift of campaigns from moderate to higher overbid.

---

## 3. Percentile Comparison: v_/legacy Ratio


| Percentile   | v2/legacy | v3/legacy | Δ      |
| ------------ | --------- | --------- | ------ |
| p10          | 1.24x     | 1.34x     | +0.10x |
| p25          | 1.54x     | 1.62x     | +0.09x |
| p50 (median) | 2.11x     | 2.15x     | +0.03x |
| p75          | 3.40x     | 3.27x     | −0.12x |
| p90          | 4.87x     | 4.47x     | −0.40x |
| p95          | 6.02x     | 6.23x     | +0.21x |
| p99          | 10.82x    | 11.45x    | +0.64x |
| Mean         | 2.86x     | 2.79x     | −0.07x |

v3 is marginally better at p75–p90 (−0.12x to −0.40x) but worse at every other percentile.
The differences are noise-level and within the day-to-day variability expected from traffic routing.

---

## 4. Spot-Check: Previously Identified Worst Campaigns

These are the top-10 inflated campaigns flagged in the 05-14 analysis.


| Campaign                   | SDK Event              | bhv1p  | ctx1r  | v2     | v3     | v2/leg  | v3/leg  | Status           |
| -------------------------- | ---------------------- | ------ | ------ | ------ | ------ | ------- | ------- | ---------------- |
| `652214aefc636157750229a8` | `star5_hero_received`  | 0.0024 | 0.0033 | 0.1470 | 0.0814 | 51.8x   | **28.7x** | Improved (−23x) |
| `67dc0fa20eb345a2a13aef4f` | `ajvip`                | 0.0183 | 0.0476 | 0.4749 | 0.4946 | 14.4x   | **15.0x** | Worse (+0.6x)   |
| `69eae6280d291c5f22675e19` | `recvd_coins_400`      | 0.0595 | 0.0670 | 0.5008 | 0.3572 | 7.9x    | **5.6x**  | Improved (−2.3x)|
| `69c4447a75bdf4ae2c38cc0d` | `pc_t2_d60_ios_custom` | 0.0083 | 0.0221 | 0.2394 | 0.1117 | 15.8x   | **7.4x**  | Improved (−8.4x)|
| `6960733f13cc68bc8f91fc8e` | `ajvip`                | 0.0777 | 0.0682 | 0.6866 | 0.6591 | 9.4x    | **9.0x**  | Marginal        |
| `6825d515a47ee6e329c70bdd` | `eventW`               | 0.0817 | 0.0476 | 0.5876 | 0.4596 | 9.1x    | **7.1x**  | Improved (−2.0x)|
| `685e72777dd83b9c8536915e` | `eventw`               | 0.0683 | 0.0387 | 0.5786 | 0.6638 | 10.8x   | **12.4x** | Worse (+1.6x)   |
| `686664ce9dfaacc5e24bf3df` | `ajvip`                | 0.0527 | 0.0689 | 0.4732 | 0.5553 | 7.8x    | **9.1x**  | Worse (+1.3x)   |
| `684ac40f6da6f407ddfa47fd` | `d7_puzzle60_hint5`    | 0.0562 | 0.0916 | 0.5587 | 0.4671 | 7.6x    | **6.3x**  | Improved (−1.2x)|
| `698c51a4e63287f25051d95c` | `ajvip`                | 0.0587 | 0.0622 | 0.6105 | 0.6922 | 10.1x   | **11.5x** | Worse (+1.4x)   |

**Pattern:** the four `ajvip` campaigns (across two different games: `500072927` and `500071743`) show no
consistent improvement — two worsened, two are marginal. `ajvip` remains a high-signal problem event
that v3 has not learned to calibrate.

`star5_hero_received` improved most (51.8x → 28.7x) but remains 28.7x overbid — still catastrophic.
`pc_t2_d60_ios_custom` improved substantially (15.8x → 7.4x).

---

## 5. New Regressions in v3

Campaigns where v3 is materially more inflated than v2:


| Campaign                   | SDK Event                 | v2/leg  | v3/leg  | Δ          |
| -------------------------- | ------------------------- | ------- | ------- | ---------- |
| `6a018cecbe03f13e1d819343` | `aj_vip`                  | 1.43x   | 10.07x  | **+8.6x**  |
| `69c020efcd2320cc60981e68` | `af_level_up_20`          | 1.22x   | 3.42x   | **+2.2x**  |
| `69fddb9e9b6f4e87053afc76` | `af_ftd`                  | 1.79x   | 3.70x   | **+1.9x**  |
| `675fe08483020d7c80e8ea9b` | `log_city_upgrade_6`      | 2.01x   | 3.78x   | **+1.8x**  |
| `698845da025eb5a2e046e51e` | `af_level_up_20`          | 2.36x   | 3.83x   | **+1.5x**  |
| `69fc0c08670047872db52fff` | `af_xinhuciliu`           | 1.46x   | 2.70x   | **+1.2x**  |
| `696f93b9d8b5f94c1040643d` | `af_level_up_20`          | 3.44x   | 4.47x   | **+1.0x**  |

`6a018cecbe03f13e1d819343` (`aj_vip`) is the sharpest regression: v2 was well-calibrated at 1.43x,
v3 exploded to 10.07x. This is a new v3-specific failure, not present in v2. `af_level_up_20` appears
across three separate campaigns, all worsened in v3 — a systematic signal for that event name embedding.

---

## 6. Top 15 Most Inflated Campaigns (v3/legacy)


| Campaign                   | SDK Event                    | v3 pred | Legacy avg | Ratio     |
| -------------------------- | ---------------------------- | ------- | ---------- | --------- |
| `652214aefc636157750229a8` | `star5_hero_received`        | 0.081   | 0.003      | **28.7x** |
| `67dc0fa20eb345a2a13aef4f` | `ajvip`                      | 0.495   | 0.033      | **15.0x** |
| `685e72777dd83b9c8536915e` | `eventw`                     | 0.664   | 0.054      | **12.4x** |
| `698c51a4e63287f25051d95c` | `ajvip`                      | 0.692   | 0.060      | **11.5x** |
| `6a05dd5ba69b886a7e135160` | `af_lvl_100`                 | 0.763   | 0.070      | **11.0x** |
| `6a018cecbe03f13e1d819343` | `aj_vip` *(new regression)*  | 0.328   | 0.033      | **10.1x** |
| `6836f0fb989a7e70ae0f3fe1` | `ajvaildtodaypay`            | 0.527   | 0.055      | **9.5x**  |
| `686664ce9dfaacc5e24bf3df` | `ajvip`                      | 0.555   | 0.061      | **9.1x**  |
| `6960733f13cc68bc8f91fc8e` | `ajvip`                      | 0.659   | 0.073      | **9.0x**  |
| `69f9fb97ab1684660353ff1a` | `trial_started`              | 0.509   | 0.066      | **7.7x**  |
| `69f50d252e5cc8a34b740396` | `3rdparcelpurchased`         | 0.517   | 0.070      | **7.4x**  |
| `6960bf709876e4b61866aa87` | `eventa`                     | 0.688   | 0.093      | **7.4x**  |
| `69c4447a75bdf4ae2c38cc0d` | `pc_t2_d60_ios_custom`       | 0.112   | 0.015      | **7.4x**  |
| `6825d515a47ee6e329c70bdd` | `eventW`                     | 0.460   | 0.065      | **7.1x**  |
| `67d8dc3d54006837b67d6f39` | `ajvip`                      | 0.638   | 0.100      | **6.4x**  |

`ajvip` / `aj_vip` / `ajvaildtodaypay` cluster appears **5 times** in the top 15 — consistent with the
previously identified pattern that the model has no meaningful embedding for this event family.

---

## 7. Summary Statistics


| Metric                                   | v2 (05-14)  | v3 (05-20)  |
| ---------------------------------------- | ----------- | ----------- |
| Matched campaign pairs vs legacy         | 356         | 379         |
| % campaigns ≥ 1x overbid                 | 99.7%       | 98.4%       |
| % campaigns ≥ 2x overbid                 | 62.9%       | 57.8%       |
| Median overbid ratio                     | 2.33x       | 2.15x       |
| Mean overbid ratio                       | 2.87x       | 2.79x       |
| p90 overbid ratio                        | 4.60x       | 4.47x       |
| p99 overbid ratio                        | 10.83x      | 11.45x      |
| Worst single campaign                    | 36.7x       | 28.7x       |

The headline numbers show marginal improvement (median 2.33x → 2.15x), but this is within day-to-day
traffic variance for a 1% slice. The structural inflation is unchanged.

---

## 8. Conclusion

v11-cpe-lc-3 **does not fix the prediction inflation**. The root causes identified in the 05-14 analysis
are still present:

1. **Wildcard label inflation** (primary): training data still contains 44%+ wildcard `*` rows at ~36%
   positive rate. v3 shows no evidence this was changed (the overall mean prediction is unchanged at
   0.67, and the overbid distribution is structurally identical to v2).

2. **No calibration layer**: `enable_calibration: false` still applies. Without post-hoc calibration,
   the biased training distribution translates directly to biased serving predictions.

3. **New regressions introduced in v3**: `aj_vip` (1.43x → 10.07x), `af_level_up_20` across 3
   campaigns, `af_ftd`, `log_city_upgrade_6` — suggesting a data or embedding change in v3 that made
   the wildcard-attractor effect worse for some events.

**Recommended next step**: before further dialing v3, confirm whether the fixes listed in
`PREDICTION_INFLATION_ANALYSIS_05_14.md §5` (migrate to `campaigns_v3`, drop archived campaigns,
explode multi-event campaigns, re-enable Stage 5 filter, enable calibration) have been applied. If
not, v3 is a retrain of the same flawed data pipeline and further traffic dialing will only amplify
the budget impact.

---

## 9. Files Referenced

| File                                                                           | Relevance                                                              |
| ------------------------------------------------------------------------------ | ---------------------------------------------------------------------- |
| `doc/CPE LC v1 and v2 Prediction - 20260520.csv`                               | Source data for this analysis                                          |
| `doc/PREDICTION_INFLATION_ANALYSIS_05_14.md`                                   | Prior analysis; root cause and recommended fixes                       |
| `src/unity_learner/data/spark/user_value/unified_cpe_datagen.py`               | Wildcard label logic, campaign BQ query, Stage 5 filter               |
| `src/unity_learner/experiment_repo/unified_user_value/v11_cpe_lc/config.json`  | `enable_calibration: false`                                            |
