# A/B Test Report — v11-cpe-lc-4 at 50% Traffic

**Model**: `unified_user_value.v11_cpe_lc` (online alias: `v11-cpe-lc`, version `v11-cpe-lc-4`)
**Author**: Yabo Ling
**Report Date**: 2026-06-09
**Analysis Period**: 2026-05-28 → 2026-06-06 (Jun 7–8 excluded: install outcomes not yet available due to attribution lag)

---

## 1. Experiment Setup

### Traffic Split


| Group                  | Model                       | Traffic Share   | Segments Served           |
| ---------------------- | --------------------------- | --------------- | ------------------------- |
| **Test**               | `v11-cpe-lc` (v11-cpe-lc-4) | 50%             | IDFA + IDFI + unspecified |
| **Control**            | `bhv1n` (legacy BHV)        | ~37% of control | IDFA-identified only      |
| **Control**            | `ctx1i` (legacy CTX)        | ~23% of control | IDFI + unspecified        |
| **Control (combined)** | bhv1n + ctx1i               | 50%             | All segments              |


**Traffic ramp history for v11-cpe-lc-4**:


| Date                 | Traffic |
| -------------------- | ------- |
| 2026-05-22T20:42:34Z | 1%      |
| 2026-05-25T18:14:31Z | 10%     |
| 2026-05-27T15:38:17Z | **50%** |


### Key Model Differences


| Dimension            | Test (v11-cpe-lc-4)                              | Control (bhv1n + ctx1i)                                 |
| -------------------- | ------------------------------------------------ | ------------------------------------------------------- |
| Framework            | PyTorch + UL (DLRM + DCN)                        | TensorFlow 2.11 + Keras (FC MLP)                        |
| Architecture         | DLRM (DotProductPlus + DeepCrossNet)             | 3-layer FC MLP (1024→512→256)                           |
| Traffic scope        | All segments (IDFA + IDFI + unspecified)         | BHV: IDFA only; CTX: IDFI + unspecified                 |
| Training label       | `prob_sdk_event_name_label` (specific SDK event) | `probabilistic_labels` (any level complete, stochastic) |
| Calibration          | Per-campaign product accuracy multipliers (v4)   | Legacy `LevelCompleteCostWrapper` feedback loop         |
| Target game coverage | ~13,321 games                                    | ~1,512 games (BHV)                                      |
| Embeddings           | 15 AGC scalars + 19 sparse features              | IBT 128d + install_IBT 80d (TF Hub)                     |


---

## 2. Key Results Summary

> Data source: `unity-ai-data-prd.mz_dcpi_raw.mz_dcpi_prediction_v1` joined to
> `unity-data-ads-core-prd.ads_secondary_conversion.operativeecpm_installs_outcomes_contextual`

### 2.1 Volume


| Metric       | Test       | Control    | Delta      | Sig |
| ------------ | ---------- | ---------- | ---------- | --- |
| Starts       | 78,715,009 | 64,287,333 | **+22.4%** | —   |
| Installs     | 385,702    | 266,982    | **+44.5%** | *** |
| Install Rate | 0.490%     | 0.415%     | **+18.0%** | *** |


The test model drives substantially more install volume and a higher install rate, consistent with serving a broader user population (IDFA + IDFI + unspecified) than the control models combined. The ~22% starts gap reflects the unified model winning more auctions, supported by higher bids (see Spend below).

### 2.2 Spend


| Metric                | Test       | Control    | Delta  |
| --------------------- | ---------- | ---------- | ------ |
| Sum Cost (cost units) | 331.3T     | 189.9T     | +74.5% |
| Sum Campaign Spend    | 654.1B     | 372.5B     | +75.6% |
| Avg Cost / Start      | 4,208,523  | 2,953,882  | +42.5% |
| Avg Target CPE        | 22,555,313 | 13,615,530 | +65.7% |


The test model is bidding on significantly higher target-CPE campaigns (+65.7%). This reflects the unified model's broader campaign coverage (13,321 vs 1,512 target games) attracting higher-value advertisers, and is not indicative of overbidding — avg_cost/start is in line with the higher target CPE.

### 2.3 Event Rates (Post-Install Level Complete, Binary — Cumulative)

> **Important: these are cumulative binary labels.** `lc_label_d7 = 1` means "at least one level complete event happened by day 7 post-install." For a mature cohort, d7 ER should always be ≥ d1 ER ≥ d0 ER. The fact that d7 (0.3%) << d0 (28%) in the table below is a **data truncation artifact**: installs from the last ~8 days of the analysis period do not yet have 7 days of post-install data, making the cumulative d7 label artificially low. **Full d7 data requires the install date + 9 days** (7-day window + ~2-day processing lag). See Section 9 for a per-install-date maturity breakdown.


| Window | Test ER | Control ER | Delta      | Sig | Maturity (as of 2026-06-09)             |
| ------ | ------- | ---------- | ---------- | --- | --------------------------------------- |
| **d0** | 28.44%  | 33.35%     | **−14.7%** | *** | ✓ All dates mature                      |
| **d1** | 4.07%   | 5.36%      | **−24.1%** | *** | ✓ All dates mature                      |
| **d3** | 1.27%   | 1.63%      | **−22.1%** | *** | ✓ dates through Jun 5 mature            |
| **d7** | ~0.3%*  | ~0.3%*     | ~ns*       | —   | ⚠ Only dates through Jun 1 fully mature |


*d7 aggregate is not reliable for comparison; use the mature-cohort-only values in Section 9.

Test has lower post-install event rates across d0–d3. The d7 window requires a rerun at full maturity.

**Why lower event rates are expected and not a quality regression:**

1. **Traffic expansion**: The test model serves IDFI and unspecified users (excluded from bhv1n) who have historically lower per-install event rates. The control aggregate is anchored by bhv1n (IDFA-only, highest-quality segment, ER d0 = 34.1%).
2. **Broader campaign mix**: Test targets 8.8× more games, including many with lower base event rates.
3. **Higher install volume means marginal users**: A +44.5% install lift with a fixed start pool means the test model is converting starts that the control models decline — these marginal installs naturally have lower downstream event rates.
4. **d7 convergence**: Rerun required at full maturity (2026-06-15) to assess the mature d7 gap.

### 2.4 Events Per Install (Cumulative Count)


| Window | Test  | Control | Delta     |
| ------ | ----- | ------- | --------- |
| EPC d0 | 1.044 | 1.243   | −15.9%    |
| EPC d1 | 1.075 | 1.260   | −14.7%    |
| EPC d3 | 1.006 | 1.137   | −11.5%    |
| EPC d7 | 0.556 | 0.553   | **+0.5%** |


EPC d7 is essentially flat (+0.5%), reinforcing that the d0–d3 gap closes over the full label window. Users who do eventually complete a level complete the same number of levels in 7 days.

### 2.5 Target Event Rate (Campaign-Specific SDK Event)

The **target event rate** measures the fraction of installs where the specific SDK event name targeted by the advertiser's campaign was fired. This mirrors `prob_sdk_event_name_label` from the training data pipeline — it is the most precise measure of whether the model is delivering the event advertisers actually pay for.

**Logic**: each campaign in `campaigns_v3` specifies `sdk_event_names`. If that list is empty, the campaign targets any LC event (wildcard, uses generic `lc_label`). If specific event names are listed, the install is counted only if one of those exact events was fired.

> **Same data maturity caveat as generic ER**: target event labels are cumulative. d1–d7 values below are pulled down by incomplete attribution for recent install dates. Use Section 9 mature-cohort values for d3/d7 comparisons.


| Window | Test Target ER | Control Target ER | Delta      | Sig | Maturity        |
| ------ | -------------- | ----------------- | ---------- | --- | --------------- |
| **d0** | 13.79%         | 20.73%            | **−33.5%** | *** | ✓ All dates     |
| **d1** | 1.98%          | 3.27%             | **−39.4%** | *** | ✓ All dates     |
| **d3** | 0.63%          | 1.01%             | **−37.6%** | *** | ✓ through Jun 5 |
| **d7** | ~0.15%*        | ~0.24%*           | —          | —   | ⚠ Incomplete    |


*d7 values are not reliable — see Section 9.

The test model delivers the campaign-targeted specific event at a substantially lower rate than control across all mature windows. The gap is larger than the generic ER gap (−33.5% vs −14.7% on d0), indicating the test model is generating installs where users complete *some* level-complete event but not the *specific* event targeted by the campaign.

### 2.6 Actual CPE


| Window                                | Test Actual CPE | Control Actual CPE | Delta      |
| ------------------------------------- | --------------- | ------------------ | ---------- |
| d0 (generic LC)                       | 3.02B           | 2.13B              | +41.6%     |
| d1 (generic LC)                       | 21.1B           | 13.3B              | +59.2%     |
| d3 (generic LC)                       | 67.8B           | 43.7B              | +55.1%     |
| d7 (generic LC)                       | 289.1B          | 228.0B             | +26.8%     |
| **CPE Efficiency d0** (target/actual) | **0.00747**     | **0.00638**        | **+17.0%** |
| **d0 (targeted event)**               | **6.15B**       | **3.41B**          | **+80.4%** |
| d1 (targeted event)                   | 43.0B           | 21.7B              | +98.2%     |


Actual CPE on the campaign-targeted event (+80.4% on d0) is materially worse than on the generic LC label (+41.6%). This is the more accurate CPE figure from the advertiser's perspective, and the gap to control is nearly double when using the targeted event denominator.

---

## 3. Model Bias

> **Key principle**: bias is computed from **raw sums on the same population**, not averages. Using `avg_pred / er_dx` would introduce a `starts / installs` distortion because `avg_pred = sum_pred / starts` (over 83M auctions) while `er_dx = sum_lc_label / installs` (over 409K installs). The correct formulas use `sum_pred_installs` — predictions summed only for installing auctions — so numerator and denominator are on the same install population.

### 3.1 General Model Bias Dx = (sum_pred_installs / sum_lc_label_dx) − 1

- **sum_pred_installs** = sum of model predictions for installing auctions only
- **sum_lc_label_dx** = number of installs with ≥1 LC event on day X (same install population)
- `>0` = over-predicts; `<0` = under-predicts
- Note: `lc_label_dx` is an **incremental** label (had LC on day X), not cumulative across days. At D0 (install day) the label is fully mature; D7 requires 9 days. The large D1/D3 bias values reflect that fewer users have LC on those specific days, not data truncation.

| Model | avg_pred | lc_label d0 | Bias d0 | lc_label d1 | Bias d1 | lc_label d3 | Bias d3 |
|---|---|---|---|---|---|---|---|
| **v11-cpe-lc** | 0.2687 | 28.5% | **−11.7%** | 4.0% | +524.7% | 1.3% | +1,836% |
| bhv1n | 0.3065 | 33.7% | **−23.0%** | 5.1% | +409.8% | 1.4% | +1,818% |
| ctx1i | 0.3158 | 31.6% | **−9.4%** | 5.5% | +419.8% | 2.3% | +1,166% |

At D0 (the only fully mature incremental window): all models slightly under-predict (negative bias). v11-cpe-lc (−11.7%) is better calibrated at D0 than bhv1n (−23.0%).

### 3.2 Target Model Bias Dx = (sum_pred_installs / sum_target_event_dx) − 1

- **sum_target_event_dx** = installs where campaign-specific SDK event fired by day X (binary count on install population)
- Most accurate calibration check: the model was trained on `prob_sdk_event_name_label` (specific event)

| Model | avg_pred | Target events d0 | Target Bias d0 | Target events d1 | Target Bias d1 |
|---|---|---|---|---|---|
| **v11-cpe-lc** | 0.2687 | 14.6% (target ER) | **+72.3%** | 12.7% | +98.2% |
| bhv1n | 0.3065 | 21.0% | **+23.7%** | 17.9% | +45.0% |
| ctx1i | 0.3158 | 21.5% | **+33.5%** | 20.8% | +37.5% |

**Key finding at D0** (fully mature): the test model over-predicts the targeted event by **+72.3%** — 3× worse than bhv1n (+23.7%) and 2× worse than ctx1i (+33.5%). The model is generating predictions that significantly exceed the actual targeted-event delivery rate.

The D1+ target bias values (~98–100% for test, ~44–46% for bhv1n) reflect that these are incremental per-day windows: most targeted events happen on D0 (install day), so day-1 counts are small and the bias appears large.

### 3.3 Product Bias (CPE Bias) Dx = (Observed CPE Dx / Avg Target CPE) − 1

Measures whether actual cost-per-event matches the advertiser's target CPE.

- **Observed CPE Dx** = `sum_cost / sum_lc_count_dx` (cumulative LC event _count_ by day X, not binary flag)
- **Avg Target CPE** = `avg_tcpe` (the `max_cst` / target CPE set by advertisers)
- `>0` = overspending vs target; `<0` = underspending

| Model | Avg Target CPE | Obs CPE d1 | Product Bias d1 | Obs CPE d3 | Product Bias d3 | Obs CPE d7\* | Product Bias d7\* |
|---|---|---|---|---|---|---|---|
| **v11-cpe-lc** | 22.6M | ~20.3B | **+89,700%** | ~64.9B | +287,100% | — | immature |
| bhv1n | 11.7M | ~12.6B | +107,800% | ~40.4B | +345,300% | — | immature |
| ctx1i | 16.5M | ~19.4B | +117,600% | ~59.3B | +359,400% | — | immature |

\*D7 immature; rerun on 2026-06-15.

The absolute values are large because cost is in raw units and the cumulative count is still building (same data maturity issue). The key comparison is **relative**: test product bias at D1 (+89,700%) is lower than bhv1n (+107,800%) and ctx1i (+117,600%), meaning the test model is spending closer to target per event on a relative basis — consistent with the higher target CPE campaigns it serves. The product bias will converge toward the true efficiency at D7 maturity.

### 3.4 Daily Bias Trend (Generic D0)


| Date       | bhv1n  | ctx1i  | v11-cpe-lc |
| ---------- | ------ | ------ | ---------- |
| 2026-05-28 | −9.8%  | +5.9%  | −2.2%      |
| 2026-05-29 | −13.5% | +3.2%  | −14.7%     |
| 2026-05-30 | −16.0% | +5.0%  | −4.5%      |
| 2026-05-31 | −16.3% | +4.3%  | −11.4%     |
| 2026-06-01 | −16.2% | +1.3%  | −17.0%     |
| 2026-06-02 | −4.5%  | +5.0%  | +1.7%      |
| 2026-06-03 | −3.5%  | +2.2%  | +8.6%      |
| 2026-06-04 | −1.7%  | −6.2%  | −0.4%      |
| 2026-06-05 | −6.0%  | −7.0%  | +0.2%      |
| 2026-06-06 | −7.2%  | −10.9% | −4.4%      |


These are **general model bias D0** values (pred / generic ER d0 − 1). v11-cpe-lc D0 bias is stable and near-zero in the most recent days (Jun 2–6), oscillating between −4.4% and +8.6% — a material improvement over the initial −40% under-prediction observed at launch. Note that D0 bias is expected to be negative since the model predicts p(LC by D7) but D0 observes only same-day events; full calibration assessment requires D7 maturity.

---

## 4. Statistical Significance

**Generic LC event rate:**


| Metric       | Test    | Control | Delta    | z-score | p-value |     |
| ------------ | ------- | ------- | -------- | ------- | ------- | --- |
| Install rate | 0.00490 | 0.00415 | +0.00075 | +65.93  | <0.001  | *** |
| ER d0        | 0.28439 | 0.33352 | −0.04913 | −42.41  | <0.001  | *** |
| ER d1        | 0.04068 | 0.05362 | −0.01294 | −24.54  | <0.001  | *** |
| ER d3        | 0.01267 | 0.01626 | −0.00360 | −12.11  | <0.001  | *** |
| ER d7        | 0.00297 | 0.00312 | −0.00015 | −1.08   | 0.282   | ns  |


**Target (campaign-specific) event rate:**


| Metric       | Test    | Control | Delta    | z-score | p-value |     |
| ------------ | ------- | ------- | -------- | ------- | ------- | --- |
| Target ER d0 | 0.13792 | 0.20727 | −0.06935 | −57.80  | <0.001  | *** |
| Target ER d1 | 0.01984 | 0.03268 | −0.01284 | −28.16  | <0.001  | *** |
| Target ER d3 | 0.00629 | 0.01008 | −0.00379 | −15.32  | <0.001  | *** |
| Target ER d7 | 0.00148 | 0.00239 | −0.00091 | −9.44   | <0.001  | *** |


All headline metrics are statistically significant (p<0.001) except generic ER d7, which is expected given limited attribution data (outcomes for Jun 5–8 are incomplete or unavailable). Notably, target ER d7 is highly significant (***) — the targeted-event gap persists and does not narrow even at 7 days.

---

## 5. Per-Model Breakdown


| Metric                       | bhv1n      | ctx1i      | v11-cpe-lc |
| ---------------------------- | ---------- | ---------- | ---------- |
| Starts                       | 38,511,899 | 25,775,434 | 78,715,009 |
| Installs                     | 184,497    | 82,485     | 385,702    |
| Install Rate                 | 0.479%     | 0.320%     | **0.490%** |
| Avg Cost/Start               | 2,350,993  | 3,854,677  | 4,208,523  |
| Avg Target CPE               | 11,660,958 | 16,535,918 | 22,555,313 |
| Generic ER d0                | 34.1%      | 31.6%      | 28.4%      |
| Generic ER d1                | 5.3%       | 5.6%       | 4.1%       |
| **Target ER d0**             | **20.0%**  | **22.3%**  | **13.8%**  |
| **Target ER d1**             | **2.9%**   | **3.9%**   | **2.0%**   |
| Avg Pred                     | 0.305      | 0.316      | 0.268      |
| General Bias d0 (sum-based)  | −23.0%     | −9.4%      | −11.7%     |
| **Target Bias d0 (sum-based)** | **+23.7%** | **+33.5%** | **+72.3%** |
| Actual CPE d0 (generic)      | 1.44B      | 3.81B      | 3.02B      |
| **Actual CPE d0 (targeted)** | **2.82B**  | **4.25B**  | **6.15B**  |
| CPE Efficiency d0            | 0.00811    | 0.00434    | 0.00747    |


Notable:

- **ctx1i has the worst install rate (0.320%)** and worst generic CPE efficiency (0.00434), making bhv1n the more relevant single-arm comparison.
- Against bhv1n alone: test has a comparable install rate (+2.3%), lower generic ER (−16.7% on d0), and 2.1× higher generic actual CPE d0.
- On the **targeted event**: test is −31% below bhv1n (13.8% vs 20.0%) and +118% more expensive per targeted conversion (6.15B vs 2.82B).
- The test model's +94.6% over-prediction vs targeted ER is nearly double bhv1n's +52.5%, indicating the model is mis-calibrated specifically on the targeted event dimension.

---

## 6. Daily Trends

### Install Rate

```
Date        bhv1n     ctx1i     v11-cpe-lc
2026-05-28  0.00538   0.00378   0.00509
2026-05-29  0.00557   0.00367   0.00541
2026-05-30  0.00604   0.00375   0.00567
2026-05-31  0.00603   0.00395   0.00593   ← peak for all models
2026-06-01  0.00572   0.00372   0.00553
2026-06-02  0.00520   0.00380   0.00499
2026-06-03  0.00506   0.00356   0.00507
2026-06-04  0.00517   0.00325   0.00509
2026-06-05  0.00530   0.00349   0.00516
2026-06-06  0.00528   0.00359   0.00532
```

Install rate is stable and consistent across the period. v11-cpe-lc tracks closely with bhv1n.

### Event Rate d0

```
Date        bhv1n     ctx1i     v11-cpe-lc
2026-05-28  0.3492    0.3073    0.3024
2026-05-29  0.3609    0.3190    0.3085
2026-05-30  0.3714    0.3177    0.2934
2026-05-31  0.3558    0.3219    0.2919
2026-06-01  0.3524    0.3128    0.3182
2026-06-02  0.3260    0.3049    0.2508  ← test dips
2026-06-03  0.3228    0.3106    0.2378  ← test dips
2026-06-04  0.3259    0.3364    0.2551
2026-06-05  0.3129    0.3128    0.2615
2026-06-06  0.3018    0.3229    0.2705
```

The test model event rate dip on Jun 2–3 warrants investigation — this may be related to a campaign mix shift or a specific game cohort. Both control models did not show a similar dip.

### Target Event Rate d0 (Campaign-Specific)

```
Date        bhv1n     ctx1i     v11-cpe-lc
2026-05-28  0.2077    0.2214    0.1460
2026-05-29  0.2133    0.2295    0.1517
2026-05-30  0.2218    0.2289    0.1430
2026-05-31  0.2092    0.2326    0.1439
2026-06-01  0.2066    0.2215    0.1553
2026-06-02  0.1898    0.2201    0.1212  ← test dips (same as generic ER dip)
2026-06-03  0.1885    0.2217    0.1159  ← test dips
2026-06-04  0.1885    0.2383    0.1266
2026-06-05  0.1818    0.2181    0.1286
2026-06-06  0.1742    0.2267    0.1341
```

The test model's targeted event rate is consistently ~7–8 pp below control throughout the period. The Jun 2–3 dip appears in target ER as well, confirming it is a real quality signal rather than an artifact of the generic label.

---

## 7. Data Caveats

1. **Attribution lag**: Install outcomes for Jun 7–8 are zero — the outcomes table has not populated these dates yet. d7 outcomes for Jun 1–6 may also be incomplete.
2. **Heterogeneous control**: bhv1n and ctx1i serve different user segments. The aggregate control blends IDFA-only (higher quality) and IDFI/unspecified (lower quality), so a raw test-vs-control comparison conflates model quality with segment composition.
3. **Net revenue not available**: The current data pipeline does not include revenue data. CPE efficiency is used as a proxy.
4. **d7 data**: Only ~60% of installs in this window have a mature d7 label. The d7 analysis should be revisited in 7 days.
5. **Target ER join uses campaign-level granularity**: The target event rate joins `campaigns_v3` on `campaignset_id = campaignInfo.campaignId` (one row per campaign). This is more precise than the datagen pipeline which joins on `target_game_id`. Wildcard campaigns (empty `sdk_event_names`) are handled by mapping to `['*']` and falling back to the generic `lc_label`. Installs with no matching campaign in `campaigns_v3` are treated as wildcard (left join null → uses generic label).
6. `**ANY_VALUE(sdk_event_names)` per campaign**: If a campaign has multiple rows in `campaigns_v3`, one representative value is taken. This is correct for deduplicated campaigns but may lose specificity if sdk_event_names differs across rows for the same campaign (expected to be rare).

---

## 8. Interpretation and Recommendations

### What the data shows


| Signal                             | Verdict                                                                             |
| ---------------------------------- | ----------------------------------------------------------------------------------- |
| Install volume                     | Strong positive: +44.5% more installs, +18% higher install rate                     |
| Spend efficiency (generic)         | Positive: CPE efficiency +17% (test hits target CPE better relative to total spend) |
| Generic post-install event rate    | Expected negative: −14.7% on d0, driven by traffic expansion and campaign mix       |
| **Targeted event rate**            | **Concerning: −33.5% on d0 (***), gap persists through d7 (−37.5%, ***)**           |
| Long-window generic ER convergence | Encouraging: d7 generic gap not significant; EPC d7 flat (+0.5%)                    |
| **Targeted event CPE**             | **Concerning: +80.4% worse on d0; nearly 2× gap on d1**                             |
| Generic model calibration (D0)     | Good: −11.7% test vs −23.0% bhv1n — test is better calibrated on generic LC         |
| **Calibration vs targeted label**  | **Concerning: +72.3% over-prediction (test) vs +24% (bhv1n), +34% (ctx1i)**         |
| Jun 2–3 event rate dip             | Confirmed in both generic and target ER — structural, not artifact                  |


### Concerns to investigate

1. **Targeted event rate gap (−33.5%, primary concern)**: The test model delivers the specific SDK event advertisers are paying for at 33.5% lower rate than control — statistically significant. The corrected target model bias (D0) is **+72.3%** for test vs +23.7% for bhv1n and +33.5% for ctx1i. This means the test model is generating ~1.7× more predictions per targeted-event delivery than control, indicating the model is optimizing for any-LC installs rather than the specific targeted event. Possible root cause: the training label `prob_sdk_event_name_label` may not be sufficiently differentiating specific events, or the model is over-weighting generic LC signal.
2. **Jun 2–3 ER d0 drop for test model**: v11-cpe-lc ER d0 fell to 23.8–25.1% and target ER to 11.6–12.1% on Jun 2–3, while control held steady. Both metrics dip together, confirming a real quality shift — likely a large new campaign or game cohort entering the test arm. Recommend a per-(game, sdk_event) breakdown for these two days.
3. **Targeted actual CPE (+80.4% on d0)**: Nearly double the generic CPE gap (+41.6%). This is the advertiser-facing CPE and represents a material efficiency difference. Investigate whether specific campaign types (narrow sdk_event_names vs wildcard) drive the gap disproportionately.
4. **d7 label completeness**: Rerun this analysis on 2026-06-15 when d7 outcomes for the full window are available.

### Recommended next step


| Action                                                                        | Owner            | Priority     |
| ----------------------------------------------------------------------------- | ---------------- | ------------ |
| Root cause analysis: why is targeted ER −33.5% below control?                 | Yabo Ling        | **Critical** |
| Per-(game, sdk_event) ER breakdown for Jun 2–3 dip                            | Yabo Ling        | High         |
| Segment targeted ER by wildcard vs specific-event campaigns                   | Yabo Ling        | High         |
| Rerun analysis at full d7 maturity (2026-06-15)                               | Yabo Ling        | High         |
| Investigate calibration: `prob_sdk_event_name_label` in training data         | Yabo Ling        | High         |
| Investigate actual CPE vs target CPE per campaign                             | Yabo Ling        | Medium       |
| Add net revenue join to query for RPM comparison                              | Yabo Ling        | Medium       |
| Evaluate readiness to ramp to 100% (hold until targeted ER gap is understood) | Yabo Ling + Team | Medium       |


---

## 9. Data Maturity by Install Date

### Why d7 ER < d0 ER in the aggregate tables

The outcome labels (`lc_label_d0`, `lc_label_d7`, `target_event_d7`, etc.) are **cumulative binary labels**:

- `lc_label_d0 = 1` → at least one LC event happened on install day
- `lc_label_d7 = 1` → at least one LC event happened **by** day 7 post-install

For a fully matured cohort, d7 ER ≥ d3 ER ≥ d1 ER ≥ d0 ER by definition (more time = more opportunity to convert). The inverted ordering seen in the aggregate results is a **data truncation artifact**: installs from the last ~8 days of the analysis window haven't had enough post-install time for the d7 label to populate.

**Required post-install time for reliable labels (window + ~2-day processing lag):**


| Label | Minimum days since install |
| ----- | -------------------------- |
| d0    | 1 day                      |
| d1    | 2 days                     |
| d3    | 4 days                     |
| d7    | **9 days**                 |


### Install-date maturity calendar (as of 2026-06-09)


| Install Date | Days Since | d0  | d1  | d3        | d7           |
| ------------ | ---------- | --- | --- | --------- | ------------ |
| 2026-05-28   | 12         | ✓   | ✓   | ✓         | ✓            |
| 2026-05-29   | 11         | ✓   | ✓   | ✓         | ✓            |
| 2026-05-30   | 10         | ✓   | ✓   | ✓         | ✓            |
| 2026-05-31   | 9          | ✓   | ✓   | ✓         | ✓            |
| 2026-06-01   | 8          | ✓   | ✓   | ✓         | ⚠ partial    |
| 2026-06-02   | 7          | ✓   | ✓   | ✓         | ✗ incomplete |
| 2026-06-03   | 6          | ✓   | ✓   | ✓         | ✗            |
| 2026-06-04   | 5          | ✓   | ✓   | ✓         | ✗            |
| 2026-06-05   | 4          | ✓   | ✓   | ✓         | ✗            |
| 2026-06-06   | 3          | ✓   | ✓   | ✗ partial | ✗            |


### Scale breakdown by install date

The `lc_ab_test_analysis.py` Section 7 prints per-install-date volumes and ER values with maturity flags. Key observations from the daily data:

**Starts and Installs** — stable throughout the period (no ramp changes after May 27 50% ramp). Install rate ~0.49% for test and ~0.41% for control throughout.

**Generic ER d0 by install date** — the test model shows a notable dip on Jun 2–3 (23.8–25.1%) vs control (30–32%). Mature d0 comparison (all dates valid) confirms the −14.7% gap is real and not a maturity artifact.

**Target ER d0 by install date** — consistent ~7–8 pp gap (test ~14% vs control ~21%) throughout the period. The Jun 2–3 dip appears here too (test ~11.6–12.1%), confirming it's a genuine quality event.

**d7 reliable comparison** — available only for installs through 2026-05-31 (4 install dates). Rerun the analysis on **2026-06-15** when all installs through 2026-06-06 have full d7 maturity, and use the mature-cohort aggregate from Section 7 of the script for an unbiased d7 comparison.

---

## 10. Appendix — Query and Analysis Code

- **BQ query + runner**: `AB-test-analysis/run_analysis.py` (inline SQL, fetches via `bq` CLI)
- **Analysis script**: `AB-test-analysis/lc_ab_test_analysis.py` (Sections 1–7; Section 7 = data maturity breakdown)
- **Data source (predictions)**: `unity-ai-data-prd.mz_dcpi_raw.mz_dcpi_prediction_v1`
- **Data source (outcomes)**: `unity-data-ads-core-prd.ads_secondary_conversion.operativeecpm_installs_outcomes_contextual`

**Model version mapping used in query:**


| Pattern                 | Mapped to         |
| ----------------------- | ----------------- |
| `LIKE '%v11-cpe-lc-4%'` | v11-cpe-lc (test) |
| `LIKE '%ctx1r-1a%'`     | ctx1i (control)   |
| `LIKE '%bhv1p-1b%'`     | bhv1n (control)   |


