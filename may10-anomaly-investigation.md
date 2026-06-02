# May 10, 2026 — Anomaly Investigation Report

**Table:** `unity-ads-dd-ds-prd.user_value_incremental_datagen.v26_q2a_mesh_v2`
**Investigated:** 2026-06-01
**Status:** Root cause identified. Systemic pattern also found across full dataset.

---

## TL;DR

The May 10 spike in `avg_iap_d1` ($95.56 vs normal ~$18) was caused by **a single row** with a corrupted IAP value of **$8,739,904** from game `500227161`, Brazil, Android, `mmp_unattributed`. Removing this one row restores the average to $18.12 (normal). A broader systemic pattern was also found: `mmp_unattributed` installs are not subject to the IAP capping pipeline, allowing extreme values to flow through silently on other dates too.

---

## Anomaly 1 (Primary) — $8.74M Single Transaction, May 10

### What happened


| Field                                  | Value                              |
| -------------------------------------- | ---------------------------------- |
| date                                   | 2026-05-10                         |
| target_game_id                         | **500227161**                      |
| platform                               | android                            |
| source                                 | **mmp_unattributed**               |
| geolocation_country                    | **BR** (Brazil)                    |
| gamer_id_scope                         | idfa                               |
| `post_install_deposit_sum_d1`          | **$8,739,904.00**                  |
| `post_install_deposit_sum_d7`          | **$8,739,904.00**                  |
| `post_install_deposit_count_d7`        | 1.0 (single transaction)           |
| `post_install_deposit_capped_sum_d7`   | **-1.0 (sentinel — not computed)** |
| `post_install_deposit_uncapped_sum_d7` | **-1.0 (sentinel)**                |
| `post_install_adrev_sum_d1`            | -1.0 (sentinel)                    |
| `post_install_retention_d1`            | -1.0 (sentinel)                    |
| `cost_usd`                             | **0.0**                            |


### Why this is erroneous

- Game 500227161's typical max IAP per day is **$20–$250**. The $8.74M value is **~50,000x** higher than its normal maximum.
- `cost_usd = 0.0` — zero acquisition cost for an install that supposedly generated $8.74M. This is a strong indicator the row is a test record or a data ingestion error.
- The capping fields (`capped_sum_d7`, `uncapped_sum_d7`) are both `-1` (sentinel), meaning the **IAP capping pipeline was never applied to this row**. The raw corrupted value flowed through unchecked.
- A single $8.74M IAP in a mobile game is not a plausible real-world transaction.

### Impact on metrics


| Metric                 | With corrupt row | Without game 500227161 | Normal?                 |
| ---------------------- | ---------------- | ---------------------- | ----------------------- |
| avg_iap_d1 (May 10)    | **$95.57**       | $18.12                 | Yes                     |
| avg_iap_d7 (May 10)    | **$84.38**       | ~$18                   | Yes                     |
| iap_rate_d1 (May 10)   | 1.039%           | 1.039%                 | Yes (unaffected)        |
| payer_rate_d7 (May 10) | normal           | normal                 | Yes (uses capped_count) |
| adrev_rate_d1 (May 10) | normal           | normal                 | Yes (unaffected)        |
| ret_rate_d1 (May 10)   | normal           | normal                 | Yes (unaffected)        |


Only `avg_iap_d1` and `avg_iap_d7` (which average the raw, uncapped deposit sum) are affected. `iap_rate`, `payer_rate`, and all other label metrics are unaffected.

### Game 500227161 — daily context (May 2026)

The game enters exactly ~2,000 rows per day — very uniform, consistent with a fixed-budget campaign:


| Date           | Rows      | Max IAP D1        |
| -------------- | --------- | ----------------- |
| 2026-05-01     | 2,000     | $22.95            |
| 2026-05-02     | 2,000     | $42.92            |
| 2026-05-05     | 1,999     | $180.37           |
| 2026-05-08     | 2,000     | $37.95            |
| 2026-05-09     | 2,000     | $71.88            |
| **2026-05-10** | **2,000** | **$8,739,904.00** |
| *(data ends)*  |           |                   |


The anomaly is isolated to a single row on May 10. All surrounding days are normal.

---

## Anomaly 2 (Systemic) — Uncapped Extreme IAP Values in mmp_unattributed

### Pattern

Across the full April–May 2026 dataset, all rows with `post_install_deposit_sum_d1 > $10,000` share a common signature:

- **All are `mmp_unattributed`** — not a single extreme outlier comes from `mmp_attributed`
- `**post_install_deposit_capped_sum_d7 = -1.0**` (sentinel) in almost all cases
- `**post_install_deposit_uncapped_sum_d7 = -1.0**` (sentinel) in almost all cases

This means the IAP capping pipeline does not process `mmp_unattributed` rows, allowing raw extreme values to pass through into `post_install_deposit_sum_d1/d7`.

### Full list of extreme IAP rows (> $10,000) across Apr–May 2026


| Date           | Game ID       | Platform | Source           | Country | IAP D1         | Count D7 | Capped D7    |
| -------------- | ------------- | -------- | ---------------- | ------- | -------------- | -------- | ------------ |
| **2026-05-10** | **500227161** | android  | mmp_unattributed | BR      | **$8,739,904** | 1        | -1 (missing) |
| 2026-05-22     | 500181993     | ios      | mmp_unattributed | AE      | $534,761       | 1        | -1 (missing) |
| 2026-05-29     | 500139080     | android  | mmp_unattributed | null    | $439,308       | 4,340    | 0.0          |
| 2026-04-08     | 500137507     | ios      | mmp_unattributed | CA      | $300,451       | 5        | -1 (missing) |
| 2026-04-08     | 500137506     | android  | mmp_unattributed | US      | $217,650       | 3        | -1 (missing) |
| 2026-05-06     | 500027454     | android  | mmp_unattributed | RU      | $173,908       | 2        | -1 (missing) |
| 2026-05-20     | 500027454     | android  | mmp_unattributed | RU      | $140,555       | 1        | -1 (missing) |
| 2026-05-29     | 500027454     | android  | mmp_unattributed | RU      | $138,763       | 1        | -1 (missing) |
| 2026-04-30     | 500027454     | android  | mmp_unattributed | RU      | $133,781       | 1        | -1 (missing) |
| 2026-04-19     | 500181993     | android  | mmp_unattributed | VN      | $131,509       | 29       | -1 (missing) |
| 2026-04-23     | 500027454     | android  | mmp_unattributed | RU      | $112,180       | 1        | -1 (missing) |
| 2026-04-06     | 500027454     | android  | mmp_unattributed | RU      | $102,011       | 1        | -1 (missing) |
| 2026-04-11     | 500181993     | ios      | mmp_unattributed | AE      | $100,452       | 2        | -1 (missing) |
| 2026-04-23     | 500238446     | ios      | mmp_unattributed | MX      | $100,137       | 2,145    | -1 (missing) |
| 2026-05-12     | 500027454     | android  | mmp_unattributed | RU      | $93,820        | 1        | -1 (missing) |
| 2026-04-01     | 500027454     | android  | mmp_unattributed | RU      | $92,162        | 1        | -1 (missing) |
| 2026-05-14     | 500027454     | android  | mmp_unattributed | RU      | $79,836        | 1        | -1 (missing) |
| 2026-04-02     | 500027454     | android  | mmp_unattributed | RU      | $79,224        | 4        | -1 (missing) |
| 2026-04-09     | 500027454     | android  | mmp_unattributed | RU      | $77,096        | 1        | -1 (missing) |
| 2026-05-19     | 500027454     | android  | mmp_unattributed | RU      | $68,442        | 1        | -1 (missing) |


### Notable sub-patterns

**Game 500027454 (Android, Russia)** is a recurring offender, appearing **almost daily** with IAP values of $68k–$174k. This is likely a real high-value Russian user or whale cluster that generates genuinely large IAP (e.g., a gacha game with expensive bundles), but the absence of capping means it disproportionately inflates avg_iap metrics. Presence is consistent enough that it may be real data.

**Game 500181993** appears multiple times across different countries (AE, VN) with high IAP, again exclusively in `mmp_unattributed`.

**May 29 anomaly (500139080):** `count_d7 = 4,340` with a $439k total — this is 4,340 transactions summed, not a single $439k purchase. Also has `null` country, suggesting a pipeline aggregation artifact.

**April 8 minor spike** in overall `avg_iap_d1` ($25.42 vs ~$18 normal): caused by two extreme rows — game 500137507 ($300k, iOS, CA) and 500137506 ($217k, Android, US).

---

## Anomaly 3 — "April 10 Spike" — Chart Data Error (Not a Real Event)

**Finding:** The apparent spike around April 10 visible in the `memorial-day-label-analysis.html` chart was **not a real data event**. It was caused by a bug in the HTML chart's embedded data arrays.

**Root cause of chart bug:** Three data arrays in the OV (Overall) JavaScript object had May 10–29 values spliced in starting at the April 10 position (index 9), overwriting the real April data:
- `avg_iap_d1[9]` showed `95.56` (May 10's value) instead of the correct `18.74`
- `ret_d1[9..28]` showed May 10–29 retention values instead of April 10–29 values
- `n_rows[9..28]` showed May 10–29 row counts instead of April 10–29 row counts

**Actual April 10 avg_iap_d1: $18.74 — completely normal.**

**Fix applied:** All three arrays were corrected in `memorial-day-label-analysis.html` with verified BQ values for April 10–30.

The only real avg_iap spikes in the Apr–May 2026 dataset are:
| Date | avg_iap_d1 | Cause |
|------|-----------|-------|
| 2026-04-08 | $25.42 | Games 500137507 ($300k, iOS, CA) + 500137506 ($217k, Android, US) — `mmp_unattributed`, capping missing |
| **2026-05-10** | **$95.56** | Game 500227161, single $8.74M corrupt row — `mmp_unattributed`, `cost_usd=0` |
| 2026-05-22 | $23.55 | Game 500181993 ($534k, iOS, AE) — `mmp_unattributed`, capping missing |
| 2026-05-29 | $25.23 | Game 500139080 ($439k, Android, null country, 4,340 transactions) |

---

## Anomaly 4 — May 22 avg_iap_d1 Spike ($23.55)

The overall average IAP on May 22 was $23.55 vs ~$18 baseline. Root cause: game 500181993 (iOS, AE/UAE) recorded a $534,761 transaction on May 22. Same pattern — `mmp_unattributed`, capped_sum = -1.

Also notable: May 29 shows $25.23 due to game 500139080 (Android, null country) with $439k total spread across 4,340 transactions — a pipeline aggregation artifact with null country, not a single whale transaction.

---

## Root Cause Summary


| Issue                  | Root Cause                                                                                                              |
| ---------------------- | ----------------------------------------------------------------------------------------------------------------------- |
| May 10 avg_iap spike   | Single row, game 500227161, $8.74M corrupt IAP, `cost_usd=0`, all sentinel fields                                       |
| Systemic avg_iap noise | `mmp_unattributed` rows are not processed by the IAP capping pipeline; extreme raw values flow into `deposit_sum_d1/d7` |
| Affected metric        | `avg_iap_d1`, `avg_iap_d7` only. `iap_rate`, `payer_rate`, `adrev_rate`, `ret_rate` are unaffected                      |
| Not affected           | All attributed installs — no extreme outlier comes from `mmp_attributed`                                                |


---

## Recommendations

1. **Exclude game 500227161, May 10 row** from any avg_iap analysis — it is clearly corrupt (`cost_usd=0`, $8.74M IAP, all other labels are -1 sentinels).
2. **Apply capping to mmp_unattributed IAP values.** Currently `deposit_capped_sum_d7` and `deposit_uncapped_sum_d7` are not computed for unattributed rows (both = -1). The raw `deposit_sum_d1/d7` fields should either be capped or excluded from average calculations when the capped fields are missing.
3. **Use `post_install_deposit_capped_count_d7 > 0` (payer_rate) as the primary IAP signal** in downstream models — it is robust to this issue since it uses the capped count, not the raw sum. Avoid using raw `avg_iap_d1/d7` as a training label without filtering out uncapped outlier rows.
4. **Investigate game 500027454 (Android, RU)** — this game has recurring $68k–$174k daily IAP values throughout the entire date range. Determine if these represent real high-LTV users (whale cluster) or a systematic MMP mis-attribution issue.
5. **Flag `cost_usd = 0` rows with `deposit_sum > 0`** as a quality filter — zero-cost installs with large IAP are a reliable signal of test records or pipeline errors.
6. **Add alerting** on `MAX(post_install_deposit_sum_d1) > 10,000` per game per day to catch future outliers before they enter model training.

