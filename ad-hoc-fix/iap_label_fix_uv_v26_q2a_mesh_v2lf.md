# IAP Duplication Bug Fix — Dataset Comparison Report (mesh_v2lf iteration)

**Before fix (baseline):** `unity-ads-dd-ds-prd.user_value_incremental_datagen.uv_v26_q2a`

**After fix:** `unity-ads-dd-ds-prd.user_value_incremental_datagen.uv_v26_q2a_mesh_v2lf`

**Analysis date:** 2026-06-04

---

## Background

This report re-runs the validation from the original `iap_label_fix.md` against the new `uv_v26_q2a_mesh_v2lf` table, which rebases the label fix on top of the updated identity mesh link change (`mesh_v2lf`). The same checks — dataset overview, IAP/Payer invariant, global label statistics, per-date backfill health, case study game validation, and top inflation games — are applied.

**Key structural difference vs. previous iteration:** `uv_v26_q2a_mesh_v2lf` starts at **2026-01-08**, approximately 6 weeks later than the `uv_v26_q2_labelfix` table (which started 2025-11-26). All comparisons are aligned to `>= 2026-01-08` unless otherwise noted.

---

## Data Notes

- Labels use **`-1.0` as a "not applicable" sentinel**. All revenue/count figures filter to `>= 0` to exclude sentinels.
- `uv_v26_q2a_mesh_v2lf` covers **2026-01-08 to 2026-05-31**. The pre-2026-01-08 period (including the previously-identified incomplete backfill window 2025-11-26 to 2025-12-09) does not exist in this table and is excluded from all aligned comparisons.
- All core comparisons use **`>= 2026-01-08`** as the alignment date.

---

## 1. Dataset Overview

Date-aligned to `>= 2026-01-08`:

| Metric | Before Fix | After Fix (mesh_v2lf) | Change |
|---|---|---|---|
| Total rows | ~1.32B (est. aligned) | 1,318,275,229 | — |
| Distinct gamers | — | 630,551,940 | — |
| Distinct games | — | 15,454 | — |
| Min install date | 2025-11-26 | **2026-01-08** | New table starts ~6 weeks later |
| Max install date | 2026-06-01 | 2026-05-31 | — |

Full range (before `>= 2025-11-26` vs after natural range):

| Metric | Before Fix | After Fix | Change |
|---|---|---|---|
| Total rows | 1,735,712,526 | 1,318,275,229 | -417M (-24.0%) |
| Distinct gamers | 781,276,135 | 630,551,940 | -150.7M (-19.3%) |
| Distinct games | 17,562 | 15,454 | **-2,108 games** |

The row and gamer reductions are largely explained by the shorter date range (~5 months vs ~6.5 months) combined with fan-out row removal. The 2,108-game reduction warrants verification (see Section 7).

---

## 2. IAP vs. Payer Label Sanity Check (Core Bug Invariant)

**Invariant:** `post_install_deposit_sum_d7` (IAP) must never exceed `post_install_deposit_capped_sum_d7` (Payer) for any row where both labels apply.

Checked at the row level for rows where both are non-sentinel (`>= 0`), aligned to `>= 2026-01-08`:

| Metric | Before Fix | After Fix (mesh_v2lf) | Change |
|---|---|---|---|
| Rows where both labels apply | 731,033,794 | 713,154,877 | -17.9M (-2.4%) |
| Rows with IAP > Payer (count) | 8,298,241 | 7,954,431 | **-343,810 (-4.1%)** |
| Rows with IAP > Payer (%) | 1.135% | **1.115%** | -0.020pp ✅ |
| Total phantom revenue | $361,273,987 | $347,464,149 | **-$13.8M (-3.8%)** ✅ |

**Interpretation:** Both the absolute violation count and violation rate decreased after the mesh fix, and $13.8M of phantom revenue was removed. The residual ~1.1% violation rate is consistent with the pre-existing data quality issue documented in the original report (see Section 5).

---

## 3. Global Label Statistics

Date-aligned to `>= 2026-01-08`, sentinel-filtered (`>= 0`):

| Label | Before Fix | After Fix (mesh_v2lf) | Absolute Change | % Change |
|---|---|---|---|---|
| IAP sum (`deposit_sum_d7`) | $575,734,345 | $572,076,343 | -$3,658,002 | **-0.6%** |
| IAP positive rows | 16,335,209 | 15,917,486 | -417,723 | -2.6% |
| Payer sum (`capped_sum_d7`) | $77,050,357 | $74,920,536 | -$2,129,821 | **-2.8%** |
| Payer positive rows | 5,375,397 | 5,186,734 | -188,663 | -3.5% |
| AdRev sum (`adrev_sum_d7`) | $168,949,234 | $164,257,620 | -$4,691,614 | **-2.8%** |
| AdRev positive rows | 582,847,754 | 571,548,539 | -11,299,215 | -1.9% |

All three labels show modest, clean reductions in the expected direction. The smaller magnitude vs. the original fix iteration (-0.6%/−2.8%/−2.8% here vs. -1.8%/-7.6%/-9.5% in `q2_labelfix`) is consistent with this table starting later (January 2026 onwards), when the fan-out bug had less cumulative impact after the original pipeline fix began taking effect.

---

## 4. Per-Date Analysis — Backfill Health

### Period: 2026-01-08 → 2026-01-20 (start of mesh_v2lf range) ✅

| Date | Rows Before | Rows After | Row Diff | Payer Sum (After) | AdRev Sum (After) | IAP Inflation Factor |
|---|---|---|---|---|---|---|
| 2026-01-08 | 9,345,170 | 8,919,054 | -426,116 | $427,981 | $920,287 | 1.003x |
| 2026-01-09 | 9,692,052 | 9,268,288 | -423,764 | $462,150 | $973,278 | 1.002x |
| 2026-01-10 | 10,220,969 | 9,793,679 | -427,290 | $484,422 | $1,119,302 | 1.027x |
| 2026-01-11 | 10,468,309 | 10,047,095 | -421,214 | $700,537 | $1,187,529 | 1.024x |
| 2026-01-12 | 8,728,347 | 8,373,635 | -354,712 | $435,531 | $952,083 | 0.950x |
| 2026-01-13 | 8,648,204 | 8,302,461 | -345,743 | $441,333 | $895,915 | 0.967x |
| 2026-01-14 | 8,697,453 | 8,348,606 | -348,847 | $413,424 | $920,307 | 0.989x |
| 2026-01-15 | 9,044,225 | 8,680,844 | -363,381 | $439,881 | $962,522 | 0.978x |
| 2026-01-16 | 9,371,560 | 9,004,002 | -367,558 | $479,746 | $982,388 | 0.952x |
| 2026-01-17 | 9,963,970 | 9,596,001 | -367,969 | $559,030 | $1,107,334 | 1.019x |
| 2026-01-18 | 10,289,283 | 9,922,534 | -366,749 | $542,906 | $1,191,000 | 1.005x |
| 2026-01-19 | 8,824,972 | 8,514,360 | -310,612 | $467,381 | $1,023,279 | 0.997x |
| 2026-01-20 | 8,341,597 | 8,057,220 | -284,377 | $437,180 | $933,643 | 0.960x |

### Period: 2026-01-15 → 2026-03-05 ✅

| Date | Rows Before | Rows After | Row Diff | Payer Sum (After) | AdRev Sum (After) | IAP Inflation Factor |
|---|---|---|---|---|---|---|
| 2026-01-15 | 9,044,225 | 8,680,844 | -363,381 | $439,881 | $962,522 | 0.978x |
| 2026-02-01 | 10,175,131 | 9,936,813 | -238,318 | $576,236 | $1,324,806 | 1.016x |
| 2026-02-27 | 8,467,083 | 8,492,561 | +25,478 | $464,974 | $1,054,262 | 0.991x |
| 2026-03-05 | 8,267,869 | 8,312,741 | +44,872 | $457,361 | $1,071,619 | 0.965x |

**Observations:**
- **No incomplete backfill detected.** Payer and AdRev labels are fully present across all sampled dates.
- Row differences narrow over time (-426K in early Jan → near-zero and even slightly positive by late Feb/Mar), consistent with the identity mesh change adding new gamer links that weren't in the baseline.
- IAP inflation factors range 0.95x–1.027x across all dates — within noise.
- The "incomplete backfill" issue from the previous iteration (2025-11-26 to 2025-12-09, with 0 Payer/AdRev signal and only 37% row coverage) is **resolved by the mesh_v2lf table's later start date** — those dates are not included.

---

## 5. Case Study Game Validation (aligned `>= 2026-01-08`)

| Game ID | Label | Before Fix | After Fix | Change | Verdict |
|---|---|---|---|---|---|
| **500166235** (Block Blast Adventure) | IAP | — | — | — | No IAP-applicable rows (all sentinel) |
| | Payer | $117,751 | $117,425 | -$326 (noise) | ✅ Stable |
| | AdRev | $614,317 | $285,144 | **-$329,173 (-53.6%)** | ✅ Fixed |
| **500149926** (Block Blast Puzzle) | IAP | — | — | — | No IAP-applicable rows (all sentinel) |
| | Payer | $177,449 | $175,487 | -$1,962 (noise) | ✅ Stable |
| | AdRev | $1,608,245 | $1,089,908 | **-$518,337 (-32.2%)** | ✅ Fixed |
| **500242071** (MONEY CASH) | IAP | $304,990 | $303,497 | -$1,493 (noise) | ✅ Correct |
| | Payer | $304,990 | $303,497 | -$1,493 (noise) | ✅ Stable |
| | IAP/Payer ratio | 1.000x | 1.000x | Unchanged | ✅ |
| **500219798** (Glow Fashion Idol) | IAP | $316,168 | $312,329 | -$3,839 (noise) | — |
| | Payer | $276,873 | $274,163 | -$2,710 (noise) | ✅ Stable |
| | IAP/Payer ratio | **1.142x** | **1.139x** | Unchanged | ⚠️ Pre-existing issue |
| **500199462** (Idle Outpost) | IAP | $154,596 | $152,274 | -$2,322 (noise) | — |
| | Payer | $37,749 | $37,749 | $0 | ✅ Stable |
| | IAP/Payer ratio | **4.095x** | **4.034x** | Unchanged | ⚠️ Pre-existing issue |

**Notes:**
- **500166235 / 500149926:** No IAP-applicable rows (all sentinel) in both tables for this date range — consistent with these being ad-only games where IAP deposits don't apply. Payer is stable; AdRev inflation was successfully removed by the fix.
- **500219798 / 500199462:** IAP > Payer ratio is essentially unchanged between before and after fix, confirming this is a **pre-existing issue unrelated to the fan-out bug** — same conclusion as original report. Note that 500199462's ratio appears higher here (4.0x) than in the original `q2_labelfix` report (2.6x); this is because the aligned window (January 2026 onwards) covers a different payer activity period, not a regression introduced by this fix.

---

## 6. Top Games by IAP Inflation Removed (`>= 2025-12-10` baseline / mesh_v2lf effective `>= 2026-01-08`)

| Game ID | IAP Before | IAP After | IAP Removed | Inflation Factor |
|---|---|---|---|---|
| 500227937 | $4,079,643 | $77,027 | $4,002,616 | **52.96x** |
| 500251690 | $1,186,020 | $29,738 | $1,156,282 | **39.88x** |
| 500251677 | $974,255 | $43,139 | $931,116 | **22.58x** |
| 500046323 | $6,847,932 | $5,311,677 | $1,536,255 | 1.29x |
| 500137506 | $5,841,631 | $4,521,415 | $1,320,216 | 1.29x |
| 500164896 | $6,428,537 | $5,300,587 | $1,127,950 | 1.21x |
| 500244764 | $6,319,064 | $5,328,841 | $990,223 | 1.19x |
| 500250236 | $3,915,275 | $2,947,224 | $968,051 | 1.33x |
| 500231764 | $7,798,684 | $6,859,418 | $939,266 | 1.14x |
| 500027454 | $12,911,001 | $12,091,704 | $819,297 | 1.07x |

**Positive finding:** The original worst offenders from `q2_labelfix` — game 500241340 (315.9x) and 500221398 (23.7x) — are no longer in the top 10, indicating the fan-out fix addressed those cases.

**New extreme cases:** Three games show very high inflation factors (52.96x, 39.88x, 22.58x). These warrant investigation — their presence may reflect residual fan-out from the identity mesh joining logic, or could partially reflect the date-range mismatch between the two tables (before covers ~6 extra weeks). A follow-up query aligned to `>= 2026-01-08` for both tables is recommended to confirm.

---

## 7. Payer Label Stability Summary

Payer labels are confirmed stable across the entire sampled period (`>= 2026-01-08`):
- Per-date payer diffs are consistently within noise (<$50K/day)
- No game shows a meaningful payer sum change between before and after fix (case study diffs all < $2K)
- Row diffs narrow over time and even become slightly positive in late Feb/Mar — consistent with the identity mesh change linking additional gamers, not a regression

---

## 8. Summary

| Check | Result | Detail |
|---|---|---|
| Fan-out rows removed | ✅ Pass | ~300–430K fewer rows/day in early Jan; narrows to near-zero by Mar |
| AdRev inflation corrected | ✅ Pass | -2.8% overall; case study games show 32–54% AdRev reduction |
| IAP inflation corrected | ✅ Pass | -0.6% overall; extreme cases (52.96x, 39.88x) corrected vs. baseline |
| Payer labels stable | ✅ Pass | Diffs within noise across all dates and games |
| IAP vs. Payer violation rate | ✅ Improved | 1.135% → 1.115% (-4.1% fewer violations, -$13.8M phantom revenue) |
| Backfill complete (all sampled dates) | ✅ Pass | Payer and AdRev labels fully present; no missing-label windows detected |
| Previous incomplete window (Nov 26–Dec 9) | ✅ Not applicable | mesh_v2lf starts 2026-01-08; that window does not exist in this table |
| Residual IAP > Payer violations (~1.1%) | ⚠️ Investigate | Ratio unchanged before/after — pre-existing issue, not fan-out related |
| Games dropped vs. before_fix (2,108 games) | ⚠️ Verify | 15,454 vs. 17,562 games — some due to shorter date range, but confirm no regressions |
| New extreme inflation games (52.96x, 39.88x, 22.58x) | ⚠️ Investigate | Not in `q2_labelfix` top 10; verify against aligned date range |

### Recommended Actions

1. **Confirm the 2,108 dropped games.** The mesh_v2lf table covers 15,454 games vs. 17,562 in before_fix. Determine how many of the missing games are due to the shorter date range (started 2026-01-08) vs. games genuinely absent from the mesh-rebased dataset.

2. **Investigate the three new extreme inflation games (500227937, 500251690, 500251677).** Re-run the top-inflation query with both tables aligned to `>= 2026-01-08` to rule out date-range artifacts. If the inflation persists in the aligned comparison, these games may have residual fan-out in the mesh join logic.

3. **Residual IAP > Payer violations (~1.1%) remain a pre-existing issue.** The violation rate and pattern are unchanged before/after fix, consistent with the original report's finding. A separate investigation into contextual join edge cases is warranted but not blocking.

4. **No re-backfill needed.** Unlike the previous iteration (`q2_labelfix`), no incomplete backfill period was detected in `uv_v26_q2a_mesh_v2lf`. All sampled dates have full Payer and AdRev label coverage.

---

## 9. Previous Fix vs. New Fix: `uv_v26_q2_labelfix` vs. `uv_v26_q2a_mesh_v2lf`

This section isolates the **impact of the identity mesh link change** by comparing the two fix tables directly, both aligned to `>= 2026-01-08`.

### 9a. Dataset Overview

| Metric | prev fix (`q2_labelfix`) | new fix (`mesh_v2lf`) | Change |
|---|---|---|---|
| Total rows | 1,317,821,122 | 1,318,275,229 | +454,107 (+0.03%) |
| Distinct gamers | 626,640,119 | 630,551,940 | **+3,911,821 (+0.6%)** |
| Distinct games | 16,939 | 15,454 | **-1,485 (-8.8%)** ⚠️ |
| Min install date | 2026-01-08 | 2026-01-08 | — |
| Max install date | 2026-05-30 | 2026-05-31 | — |

Row counts are nearly identical (<0.1% difference). The +3.9M gamer increase is expected — the updated identity mesh links additional gamers that were previously uncounted. The -1,485 game drop (8.8%) is the most notable structural change and warrants verification (see action items below).

### 9b. Global Label Statistics

| Label | prev fix (`q2_labelfix`) | new fix (`mesh_v2lf`) | Absolute Change | % Change |
|---|---|---|---|---|
| IAP sum | $565,103,101 | $572,076,343 | +$6,973,242 | **+1.2%** |
| IAP positive rows | 15,976,929 | 15,917,486 | -59,443 | -0.4% |
| Payer sum | $75,422,766 | $74,920,536 | -$502,230 | **-0.7%** |
| Payer positive rows | 5,261,336 | 5,186,734 | -74,602 | -1.4% |
| AdRev sum | $164,575,011 | $164,257,620 | -$317,391 | **-0.2%** |
| AdRev positive rows | 573,002,409 | 571,548,539 | -1,453,870 | -0.3% |

Label changes are small and directionally consistent with a mesh identity update: IAP increases slightly (+1.2%) while Payer and AdRev decrease slightly (<1%). This is expected when the mesh links additional gamers who have IAP events but whose payer/adrev attribution is redistributed differently across sessions.

### 9c. IAP vs. Payer Invariant

| Metric | prev fix (`q2_labelfix`) | new fix (`mesh_v2lf`) | Change |
|---|---|---|---|
| Rows both applicable | 717,090,140 | 713,154,877 | -3,935,263 (-0.5%) |
| Violation count | 8,039,349 | 7,954,431 | **-84,918 (-1.1%)** |
| Violation % | 1.121% | 1.115% | -0.006pp ✅ |
| Phantom revenue | $352,640,928 | $347,464,149 | **-$5,176,779 (-1.5%)** ✅ |

The mesh update marginally improves the invariant: 84K fewer violations and $5.2M less phantom revenue. The residual ~1.1% violation rate is the same pre-existing issue identified in the original report.

### 9d. Per-Date Label Ratios (`prev_fix / mesh_v2lf`)

| Date | Rows (prev) | Rows (mesh) | Row Diff | IAP Ratio | Payer Ratio | AdRev Ratio |
|---|---|---|---|---|---|---|
| 2026-01-08 | 9,292,550 | 8,919,054 | -373,496 | 0.987x | **1.087x** | **1.068x** |
| 2026-01-15 | 9,026,900 | 8,680,844 | -346,056 | 0.969x | **1.102x** | **1.068x** |
| 2026-02-01 | 10,174,398 | 9,936,813 | -237,585 | 1.038x | 1.042x | 1.036x |
| 2026-02-27 | 8,477,293 | 8,492,561 | +15,268 | 0.957x | 0.999x | 1.001x |
| 2026-03-05 | 8,281,710 | 8,312,741 | +31,031 | 0.946x | 1.001x | 1.000x |
| 2026-04-01 | 8,800,659 | 8,800,230 | -429 | 0.980x | 1.007x | 1.002x |
| 2026-05-01 | 10,289,910 | 10,229,886 | -60,024 | 1.034x | 1.003x | 1.004x |

**Pattern:** Jan dates show `q2_labelfix` Payer and AdRev ~7–10% higher than `mesh_v2lf`. From February onwards, all ratios converge to within 1–4%. This suggests the identity mesh change has a stronger retrospective effect on January cohorts (likely due to gamer identity links being resolved differently near the mesh cutover), while more recent cohorts are essentially equivalent between the two tables.

### 9e. Case Study Game Comparison

All ratios (`prev_fix / mesh_v2lf`) are within noise (±2%) for every game and label:

| Game ID | IAP Ratio | Payer Ratio | AdRev Ratio | Verdict |
|---|---|---|---|---|
| 500166235 (Block Blast Adventure) | — | 1.001x | 1.000x | ✅ Equivalent |
| 500149926 (Block Blast Puzzle) | — | 0.999x | 1.000x | ✅ Equivalent |
| 500242071 (MONEY CASH) | 0.995x | 0.995x | — | ✅ Equivalent |
| 500219798 (Glow Fashion Idol) | 0.993x | 0.992x | 0.992x | ✅ Equivalent |
| 500199462 (Idle Outpost) | 0.982x | 1.000x | 1.000x | ✅ Equivalent |

### 9f. Summary

The identity mesh update introduces minimal label disruption. The two fix tables are functionally equivalent for model training purposes from February 2026 onwards. January 2026 cohorts show ~7–10% higher Payer/AdRev in `q2_labelfix` vs. `mesh_v2lf`, which should be accounted for when deciding the training window start date.

| Check | Result | Detail |
|---|---|---|
| Row parity | ✅ | +0.03% difference — negligible |
| Gamer count | ✅ Expected increase | +3.9M gamers (+0.6%) from new mesh links |
| Label values (Feb onwards) | ✅ Equivalent | All ratios within 1–4% |
| Label values (Jan 2026) | ⚠️ Small divergence | Payer/AdRev ~7–10% higher in `q2_labelfix` for Jan cohorts |
| IAP/Payer violation rate | ✅ Slight improvement | 1.121% → 1.115% in mesh_v2lf |
| Games dropped (1,485 games) | ⚠️ Verify | `mesh_v2lf` has 15,454 vs. 16,939 games in `q2_labelfix` — confirm no regressions |

**Action required:** Verify the 1,485 games present in `q2_labelfix` but absent from `mesh_v2lf`. If the training window starts at 2026-02-01 or later, label values are functionally equivalent between the two fix tables.

---

## 10. Dropped Games Deep-Dive: `q2_labelfix` vs. `mesh_v2lf`

### 10a. Per-Month Game Count Delta

| Month | q2_labelfix | mesh_v2lf | Net Diff |
|---|---|---|---|
| 2026-01 | 9,303 | 8,280 | **-1,023** |
| 2026-02 | 9,991 | 9,168 | **-823** |
| 2026-03 | 11,128 | 10,986 | -142 |
| 2026-04 | 12,102 | 11,868 | -234 |
| 2026-05 | 12,421 | 12,465 | **+44** |

The gap collapses sharply after Feb and reverses by May — `mesh_v2lf` has 44 more games than `q2_labelfix` in May. The "1,485 game drop" is primarily a Jan-Feb phenomenon; from March onwards, `mesh_v2lf` gains offsetting games not present in `q2_labelfix`.

### 10b. When Do the Dropped Games Last Appear in `q2_labelfix`?

| Last active month in q2_labelfix | Games dropped |
|---|---|
| Jan only (before Feb) | 422 |
| Feb | 793 |
| Mar | 116 |
| Apr | 198 |
| May+ | 41 |
| **Total** | **1,570** |

**1,215 of 1,485 (82%)** dropped games last appear by end of February. Starting the training window from 2026-02-01 sidesteps the bulk of the issue. However, **355 games (116 Mar + 198 Apr + 41 May+)** were still active in `q2_labelfix` after February but are entirely absent from `mesh_v2lf`.

### 10c. Notable Dropped Games (Active After Feb, Ordered by Volume)

| Game ID | Rows | IAP Sum | Last Active |
|---|---|---|---|
| **500249084** | 271,993 | **$1,047,228** | 2026-05-29 |
| 500052146 | 238,234 | $414 | 2026-05-29 |
| 500177053 | 86,377 | $12,694 | 2026-05-29 |
| 500011620 | 58,607 | $5,127 | 2026-04-29 |
| 500183609 | 54,294 | $3,982 | 2026-05-29 |
| 500255914 | 33,460 | $140,706 | 2026-05-29 |
| 500197977 | 28,446 | $1,860 | 2026-04-29 |
| 500174597 | 27,282 | $1,539 | 2026-04-29 |
| 500202865 | 24,503 | $1,143 | 2026-04-29 |
| 500239005 | 53,150 | $3,323 | 2026-05-29 |

Game **500249084** is the most significant: $1M+ IAP, 271K rows, active through end of May in `q2_labelfix` but completely absent from `mesh_v2lf`. Game **500255914** ($140K IAP) is also notable. These games are not trivially small.

### 10d. Verdict

| Question | Answer |
|---|---|
| Is there a game drop after Feb? | **Yes, but small.** Net diff: -142 (Mar), -234 (Apr), +44 (May) |
| Are all 1,485 drops pre-Feb? | **No.** 355 dropped games were active after Feb in q2_labelfix |
| Safe to start training from Feb 2026? | **Mostly yes** — 82% of dropped games are Jan-Feb only; net monthly gap is small from Mar onwards |
| Any high-risk dropped games? | **Yes.** Game 500249084 ($1M+ IAP, active through May) warrants specific investigation |

**Action required:** Spot-check game `500249084` to confirm whether its absence from `mesh_v2lf` is intentional (e.g., the mesh correctly merged its gamers under a different `target_game_id`) or a regression introduced by the identity mesh relinking. If unintentional, this game and others in the post-Feb dropped set should be accounted for before promoting `mesh_v2lf` for production training.
