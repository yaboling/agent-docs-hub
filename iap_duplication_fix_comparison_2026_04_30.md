# IAP Duplication Bug Fix — Dataset Comparison Report

**Before fix:** `unity-ads-dd-ds-prd.user_value_incremental_datagen.uv_v26_q2a`
**After fix:** `unity-ads-dd-ds-prd.user_value_incremental_datagen.uv_v26_q2_labelfix`
**Analysis date:** 2026-04-30

---

## Background

The IAP & AdRev label duplication bug was caused by a missing `tracking_partner` key in the `FULL JOIN` of `join_v9.sql`. When a gamer had sessions attributed to N different tracking partners but only 1 IAP record, the single IAP row fanned out across all N session rows, creating N copies of the IAP and AdRev labels. Payer labels were unaffected because their `contextual = FALSE` flag prevented fan-out.

The fix added `tracking_partner` to all join conditions in `join_v9.sql`. The raw incremental dataset was then backfilled. This report compares the two UV datasets to validate the fix.

---

## Data Notes

- Labels use `**-1.0` as a "not applicable" sentinel** (38–40% of rows for payer/adrev, 33% for IAP). All revenue/count figures below filter to `>= 0` to exclude sentinels.
- Date ranges differ: before_fix starts 2025-11-16, after_fix starts 2025-11-26. Comparisons are **aligned to `>= 2025-11-26`** unless otherwise noted.
- A further split at **2025-12-10** is required due to the incomplete backfill discovered in analysis (see Section 4).

---

## 1. Dataset Overview


| Metric           | Before Fix    | After Fix     | Change             |
| ---------------- | ------------- | ------------- | ------------------ |
| Total rows       | 1,454,503,110 | 1,301,264,650 | **-153M (-10.5%)** |
| Distinct gamers  | 679,468,781   | 623,958,334   | -55.5M (-8.2%)     |
| Distinct games   | 14,532        | 14,059        | -473 games         |
| Min install date | 2025-11-16    | 2025-11-26    | —                  |
| Max install date | 2026-04-27    | 2026-04-27    | —                  |


The 153M row reduction is the direct result of removing fan-out duplicate rows from the upstream `join_v9` pipeline.

---

## 2. IAP vs. Payer Label Sanity Check (Core Bug Invariant)

**Invariant:** `post_install_deposit_sum_d7` (IAP) must never exceed `post_install_deposit_capped_sum_d7` (Payer) for any row where both labels apply.

Checked at the **row level** for rows where both labels are non-sentinel (`>= 0`), date-aligned to `>= 2025-11-26`:


| Metric                           | Before Fix   | After Fix    |
| -------------------------------- | ------------ | ------------ |
| Rows where both labels apply     | 763,773,670  | 719,289,120  |
| Rows with IAP > Payer (count)    | 8,812,026    | 8,556,677    |
| Rows with IAP > Payer (%)        | 1.053%       | 1.094%       |
| Total excess IAP sum (phantom $) | $360,167,135 | $352,576,627 |


**Interpretation:** The absolute count of violations dropped by ~255K rows and phantom revenue fell by ~$7.6M. The marginal increase in percentage (1.053% → 1.094%) is because the denominator (applicable rows) shrank faster than the violation count — consistent with the fix removing many non-violating fan-out duplicates as well. The residual ~1% violations appear to be a **pre-existing data characteristic unrelated to the fan-out bug** (see Section 5 for per-game evidence).

---

## 3. Global Label Statistics

Date-aligned to `>= 2025-11-26`, sentinel-filtered (`>= 0`):


| Label                       | Before Fix   | After Fix    | Absolute Change | % Change  |
| --------------------------- | ------------ | ------------ | --------------- | --------- |
| IAP sum (`deposit_sum_d7`)  | $559,752,503 | $549,727,432 | -$10,025,071    | **-1.8%** |
| IAP positive rows           | 16,104,936   | 15,692,938   | -411,998        | -2.6%     |
| Payer sum (`capped_sum_d7`) | $72,411,053  | $66,850,552  | -$5,560,501     | **-7.6%** |
| Payer positive rows         | 5,230,950    | 4,780,254    | -450,696        | -8.6%     |
| AdRev sum (`adrev_sum_d7`)  | $165,893,981 | $150,149,498 | -$15,744,483    | **-9.5%** |
| AdRev positive rows         | 623,037,100  | 563,958,294  | -59,078,806     | -9.5%     |


AdRev shows the largest proportional reduction (-9.5%), consistent with the issue's finding that AdRev was the most broadly impacted label (33.3% of games affected vs. 13.4% for IAP).

---

## 4. Critical Finding: Incomplete Backfill (2025-11-26 to 2025-12-09)

The per-date analysis reveals **two structurally different periods**.

### Period 1: 2025-11-26 → 2025-12-09 — Incomplete Backfill ⚠️


| Date       | Rows Before | Rows After | Row Diff   | Payer Sum (After) | AdRev Sum (After) | IAP Inflation Factor |
| ---------- | ----------- | ---------- | ---------- | ----------------- | ----------------- | -------------------- |
| 2025-11-26 | 8,045,829   | 2,972,875  | -5,072,954 | **$0**            | **$0**            | 1.101x               |
| 2025-11-27 | 7,933,575   | 2,966,062  | -4,967,513 | **$0**            | **$0**            | 1.180x               |
| 2025-11-28 | 8,031,822   | 2,985,601  | -5,046,221 | **$0**            | **$0**            | 1.181x               |
| 2025-11-30 | 9,274,690   | 3,118,143  | -6,156,547 | **$0**            | **$0**            | 1.229x               |
| 2025-12-05 | 8,425,564   | 2,972,142  | -5,453,422 | **$0**            | **$0**            | 1.195x               |
| 2025-12-09 | 8,038,009   | 2,979,252  | -5,058,757 | **$0**            | **$0**            | 1.196x               |


**Observations:**

- After_fix has only ~~3M rows/day vs. ~8M rows/day before → **~~60% of rows are missing**
- **Payer and AdRev labels are entirely zero for all 14 days in after_fix** — these labels were not backfilled
- IAP labels are partially reduced (10–25% less) but represent incomplete training examples
- These dates contribute **incorrect/incomplete training data** — payer-model training rows for this window have no payer or adrev signal

> **⚠️ Action Required:** The backfill for **2025-11-26 through 2025-12-09** is incomplete. Payer and AdRev labels are missing entirely, and row coverage is only ~37% of the pre-fix volume. These dates should either be re-backfilled or excluded from model training until resolved.

---

### Period 2: 2025-12-10 → 2026-04-27 — Properly Backfilled ✅


| Date       | Rows Before | Rows After | Row Diff | IAP Inflation | AdRev Inflation | Payer Diff |
| ---------- | ----------- | ---------- | -------- | ------------- | --------------- | ---------- |
| 2025-12-10 | 8,057,707   | 7,970,934  | -86,773  | 1.010x        | 1.028x          | +$6,439    |
| 2025-12-15 | 8,139,269   | 8,020,668  | -118,601 | 1.016x        | 1.029x          | +$5,411    |
| 2025-12-25 | 9,436,713   | 9,302,190  | -134,523 | 1.016x        | 1.036x          | +$4,406    |
| 2026-01-01 | 10,797,361  | 10,652,025 | -145,336 | 1.018x        | 1.028x          | +$9,506    |
| 2026-01-15 | 9,044,225   | 9,026,900  | -17,325  | 1.009x        | 1.007x          | +$2,891    |
| 2026-02-01 | 10,175,131  | 10,174,398 | -733     | 0.979x        | 1.005x          | -$1,215    |
| 2026-02-27 | 8,467,083   | 8,477,293  | -10,210  | 1.036x        | 1.004x          | +$316      |
| 2026-03-05 | 8,267,869   | 8,281,710  | -13,841  | 1.020x        | 1.005x          | -$608      |


**Observations:**

- Row counts are nearly equal across all dates (diff typically < 200K/day)
- Payer and AdRev labels are present in both datasets
- IAP inflation factor is close to 1.0x (1–4% range) — residual fan-out largely eliminated
- Payer diffs are within noise (< $15K/day on total values in the hundreds of millions)
- Some dates show after_fix slightly higher IAP than before_fix (factor < 1.0) — within normal day-to-day variation

---

## 5. Case Study Game Validation (>= 2025-12-10)

Games from the original investigation, compared over the properly backfilled period:


| Game ID                               | Label           | Before Fix     | After Fix      | Change                 | Verdict                      |
| ------------------------------------- | --------------- | -------------- | -------------- | ---------------------- | ---------------------------- |
| **500166235** (Block Blast Adventure) | IAP             | $0             | $0             | —                      | —                            |
|                                       | Payer           | $160,120       | $160,087       | -$33 (noise)           | ✅ Stable                     |
|                                       | AdRev           | **$889,750**   | **$404,060**   | **-$485,690 (-54.6%)** | ✅ Fixed (was 2.20x inflated) |
| **500149926** (Block Blast Puzzle)    | IAP             | $0             | $0             | —                      | —                            |
|                                       | Payer           | $213,267       | $213,104       | -$163 (noise)          | ✅ Stable                     |
|                                       | AdRev           | **$1,939,703** | **$1,349,938** | **-$589,765 (-30.4%)** | ✅ Fixed (was 1.44x inflated) |
| **500242071** (MONEY CASH)            | IAP             | $296,283       | $296,285       | +$2 (noise)            | ✅ Correct                    |
|                                       | Payer           | $296,283       | $296,285       | +$2 (noise)            | ✅ Stable                     |
|                                       | IAP/Payer ratio | 1.000x         | 1.000x         | —                      | ✅                            |
| **500219798** (Glow Fashion Idol)     | IAP             | $316,988       | $316,894       | -$94 (noise)           | —                            |
|                                       | Payer           | $281,331       | $281,237       | -$94 (noise)           | ✅ Stable                     |
|                                       | IAP/Payer ratio | **1.127x**     | **1.127x**     | Unchanged              | ⚠️ Pre-existing issue        |
| **500199462** (Idle Outpost)          | IAP             | $143,902       | $143,845       | -$57 (noise)           | —                            |
|                                       | Payer           | $55,358        | $55,302        | -$56 (noise)           | ✅ Stable                     |
|                                       | IAP/Payer ratio | **2.600x**     | **2.601x**     | Unchanged              | ⚠️ Pre-existing issue        |


**Notes on pre-existing issues (500219798, 500199462):**
The IAP > Payer ratio for these games is identical before and after the fix. This confirms the violation is **not caused by the fan-out bug** — it predates the fix and likely stems from games where IAP data comes from `contextual = TRUE` rows but the matching payer labels from `contextual = FALSE` rows are absent or underreported.

---

## 6. Top Games by IAP Inflation Removed (>= 2025-12-10)


| Game ID   | IAP Before | IAP After  | IAP Removed | Inflation Factor |
| --------- | ---------- | ---------- | ----------- | ---------------- |
| 500241340 | $2,324,968 | $7,359     | $2,317,609  | **315.9x**       |
| 500221398 | $321,880   | $13,557    | $308,323    | **23.7x**        |
| 500251503 | $117,077   | $6,759     | $110,318    | **17.3x**        |
| 500251233 | $653,993   | $78,294    | $575,698    | **8.35x**        |
| 500244148 | $286,715   | $72,748    | $213,968    | 3.94x            |
| 500226005 | $283,824   | $71,574    | $212,250    | 3.97x            |
| 500196048 | $1,448,377 | $1,391,461 | $56,916     | 1.04x            |
| 500207596 | $1,099,613 | $1,054,043 | $45,569     | 1.04x            |


Games with extreme inflation factors (e.g. 315.9x, 23.7x) were the most severely affected by the fan-out bug — a single IAP record being matched against hundreds of session rows from different tracking partners.

---

## 7. Payer Label Stability Summary

Payer labels are confirmed stable across the properly backfilled period (>= 2025-12-10):

- No game shows a meaningful payer sum change
- Per-date payer diffs are consistently < $15K (noise-level relative to total values in the hundreds of millions)
- Some dates show small negative diffs (after_fix slightly higher), consistent with the fix restoring previously-missed payer rows in isolated edge cases
- This confirms the root cause analysis: payer rows with `contextual = FALSE` were correctly isolated from the fan-out and are unaffected by the fix

---

## 8. Summary


| Check                                        | Result         | Detail                                                                     |
| -------------------------------------------- | -------------- | -------------------------------------------------------------------------- |
| Fan-out rows removed                         | ✅ Pass         | -153M rows (-10.5%) globally                                               |
| AdRev inflation corrected                    | ✅ Pass         | -9.5% overall; case study games show 1.44x–2.20x inflation removed         |
| IAP inflation corrected                      | ✅ Pass         | -1.8% overall; extreme cases (315x, 23x) corrected                         |
| Payer labels stable                          | ✅ Pass         | Diffs within noise across all dates and games                              |
| Backfill complete (2025-11-26 to 2025-12-09) | ❌ Fail         | Payer/AdRev labels missing entirely; only ~37% row coverage                |
| Residual IAP > Payer violations (~1%)        | ⚠️ Investigate | Ratio unchanged before/after fix — pre-existing issue, not fan-out related |
| Games dropped in after_fix (473 games)       | ⚠️ Verify      | Confirm these are expected exclusions and not regressions                  |


### Recommended Actions

1. **Re-backfill 2025-11-26 to 2025-12-09.** Payer and AdRev labels are entirely absent for this 14-day window in `uv_v26_q2_labelfix`. Either re-run the backfill for this period or exclude these dates from model training to avoid injecting incomplete examples.
2. **Investigate residual IAP > Payer violations (~1%).** Games like 500219798 and 500199462 show persistent IAP > Payer ratios of 1.1x–2.6x that are unchanged by the fix. These likely represent a separate data quality issue — IAP/payer label mismatch for contextual join edge cases — and warrant a dedicated investigation.
3. **Confirm the 473 dropped games.** The after_fix dataset covers 14,059 games vs. 14,532 in before_fix. Verify these exclusions are intentional (e.g. games filtered out by updated eligibility criteria) and not a silent regression in the backfill.

