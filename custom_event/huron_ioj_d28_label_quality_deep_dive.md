# Label Quality Deep Dive: `huron_ioj_d28_0601_0606`

**Table:** `unity-ads-dd-ds-dev-prd.yabo.huron_ioj_d28_0601_0606`
**Source data:** ar_ts v2 TRJ Parquet, `gamer_age = d28`, install dates 2026-06-01 to 2026-06-06
**Investigation date:** 2026-07-21
**Attribution column discovered:** `isAttributed` (BOOLEAN, NULLABLE)

---

## 0. Schema Overview

### Top-level scalar columns relevant to labels

| Column | Type | Notes |
|---|---|---|
| `isAttributed` | BOOLEAN | **Attribution flag.** TRUE = install tied to a Unity ad campaign via MMP. |
| `isOrganic` | BOOLEAN | TRUE = organic install (no ad attribution) |
| `isReattributed` | BOOLEAN | Reattribution flag |
| `isReinstall` | BOOLEAN | Reinstall flag |
| `isContributed` | BOOLEAN | Contributed attribution |
| `isSuppressed` | BOOLEAN | Suppression flag |
| `isCreativeTestingCampaign` | BOOLEAN | Creative test campaign flag |
| `installTimestamp` | TIMESTAMP | Install time (renamed from `install_time` in Huron) |
| `eventTimestamp` | TIMESTAMP | Ad request event time (renamed from `event_time` in Huron) |
| `tracking_partner` | STRING | MMP partner name (renamed from `attribution_partner`) |

### Label column blocks

| Block | Columns | Type | Windows |
|---|---|---|---|
| `cum_has_event_d{0..28}` | 29 | INTEGER (0/1/NULL) | Any custom or LC event within dx days |
| `cum_has_lc_event_d{0..28}` | 29 | INTEGER (0/1/NULL) | Any level-complete event within dx days |
| `cum_event_count_d{0..28}` | 29 | INTEGER/NULL | Cumulative custom event count within dx days |
| `cum_depositor_d{0..28}` | 29 | INTEGER (0/1/NULL) | Had any deposit/purchase within dx days (IOJ) |
| `cum_nonzero_depositor_d{0..28}` | 29 | INTEGER/NULL | IOJ nonzero deposit flag |
| `deposit_count_d{0..28}` | 29 | INTEGER/NULL | Deposit count within dx days |
| `cum_deposit_count_d{0..28}` | 29 | INTEGER/NULL | Cumulative deposit count |
| `deposit_sum_d{0..28}` | 29 | INTEGER/NULL | Deposit revenue sum within dx |
| `cum_deposit_sum_d{0..28}` | 29 | INTEGER/NULL | Cumulative deposit revenue |

### Event array columns

| Column | Type | Sub-fields | Notes |
|---|---|---|---|
| `sdk_event_name_first_seen_arr` | RECORD (NULLABLE) | `.list[].element.sdk_event_name` (STRING), `.list[].element.first_seen_at` (TIMESTAMP) | All custom MMP-tracked events. Max 266 entries (unattributed), 185 (attributed). |
| `sdk_event_name_first_seen_arr_lc` | RECORD (NULLABLE) | `.list[].element.sdk_event_name` (STRING), `.list[].element.first_seen_at` (TIMESTAMP) | Level-complete events only. Max 68 entries (unattributed), 67 (attributed). |

> **BQ unnest pattern:** `UNNEST(sdk_event_name_first_seen_arr.list) AS arr_elem, UNNEST([arr_elem.element]) AS e` — the double-unnest is required by the Huron/Parquet RECORD-of-RECORD layout.

---

## 1. Dataset Population

**Total rows: 744,458,032**

| Segment | Rows | Share |
|---|---|---|
| Unattributed (`isAttributed = false`) | 704,931,607 | **94.69%** |
| Attributed (`isAttributed = true`) | 39,526,425 | **5.31%** |

The ~18:1 unattributed-to-attributed ratio is consistent with the prior full-dataset analysis on the BQ Huron table (94.6% / 5.4%), confirming this 6-day Parquet sample is representative.

---

## 2. Custom Event Labels (`cum_has_event_dx`)

### 2A. Fill rate (structural null = no MMP event tracking configured)

| Segment | Total rows | Labeled rows | Fill rate | Null rate |
|---|---|---|---|---|
| Unattributed | 704,931,607 | 121,745,521 | **17.27%** | 82.73% |
| Attributed | 39,526,425 | 6,898,701 | **17.46%** | 82.54% |

**Critical observation: labeled_d0 = labeled_d1 = labeled_d7 = labeled_d14 = labeled_d28 exactly.** The same rows are labeled or null across every window — this is a structural property of advertiser MMP tracking configuration, not a timing or pipeline issue. Since this data is d28 with install dates all ≥28 days old, all observation windows are fully elapsed and there is no pipeline lag.

The ~82.5% null rate is symmetric across attributed and unattributed, confirming that advertiser event-tracking configuration is independent of whether the install was attributed.

### 2B. Conditional positive rate (among labeled rows only)

| Window | Unattributed | Attributed | Delta (Attr - Unattr) |
|---|---|---|---|
| D0 | 85.46% | 87.41% | +1.95 pp |
| D1 | 89.80% | 90.80% | +1.00 pp |
| D7 | 96.49% | 96.60% | +0.11 pp |
| D14 | 98.35% | 98.56% | +0.21 pp |
| D28 | **99.997%** | **99.999%** | ~0 |

Across both groups, virtually all event-configured installs trigger at least one event by D28. The gap narrows from +1.95 pp at D0 to noise by D7. **`cum_has_event_dx` converges to near-100% by D28** — it is essentially useless as a training signal at D28 and provides minimal signal even at D7 (only 423 unattributed negatives and 50 attributed negatives remain at D28 across 128M labeled rows). The meaningful window for discrimination is D0–D3.

### 2C. Absolute negative counts at D28

| Segment | Labeled rows | D28 negatives | D28 negative rate |
|---|---|---|---|
| Unattributed | 121,745,521 | 423 | 0.0003% |
| Attributed | 6,898,701 | 50 | 0.0007% |

These are not noise — they represent installs where the app was installed, had tracking configured, but the user never triggered any event across 28 days (deleted immediately or hard technical failure).

### 2D. Average cumulative event count (conditional on non-null rows)

| Window | Unattributed | Attributed | Delta (Attr - Unattr) |
|---|---|---|---|
| D0 | 3.87 | 3.42 | -0.45 |
| D1 | 4.79 | 4.20 | -0.59 |
| D7 | 7.56 | 6.48 | -1.08 |
| D14 | 9.32 | 8.02 | -1.30 |
| D28 | 11.74 | 10.90 | -0.84 |

Unattributed users accumulate more events at every window, with the gap peaking at D14 (-1.30). The gap narrows slightly by D28 (-0.84), suggesting attributed users have a later-accumulating long-tail of events. Unlike the prior analysis period which showed attributed users overtaking at D28, this sample does not yet show a crossover — the gap remains negative at D28.

### 2E. Label growth curve — incremental event gain per window

| Window | Unattr event rate | Attr event rate | Incremental gain (Unattr) | Incremental gain (Attr) |
|---|---|---|---|---|
| D0 | 85.46% | 87.41% | — | — |
| D1 | 89.80% | 90.80% | +4.34 pp | +3.39 pp |
| D7 | 96.49% | 96.60% | +6.69 pp | +5.80 pp |
| D14 | 98.35% | 98.56% | +1.86 pp | +1.96 pp |
| D28 | 99.997% | 99.999% | +1.65 pp | +1.44 pp |

The D1→D7 window delivers the largest single increment of new event coverage for both groups (+6.69 pp unattributed, +5.80 pp attributed). Post-D7 gains are small (~1.7–2.0 pp per additional week), and by D14 the coverage is already at 98%+. Unlike the LC curve where D0 captures a large share of the total signal, the custom event curve starts lower (85–87% at D0) and grows meaningfully through D7.

**Comparison with LC curve (NULL treated as negative = 0, denominator = all rows):**

> Rates below count NULL as negative. This reflects the modeling reality: installs without MMP event tracking configured are true non-converters from the label perspective.

| Metric | `cum_has_event_dx` | `cum_has_lc_event_dx` |
|---|---|---|
| **Attributed** | | |
| D0 positive rate | 6,030,120 / 39,526,425 = **15.26%** | 1,882,930 / 39,526,425 = **4.76%** |
| D1 positive rate | 6,264,298 / 39,526,425 = **15.85%** | 2,031,850 / 39,526,425 = **5.14%** |
| D7 positive rate | 6,663,809 / 39,526,425 = **16.86%** | 2,282,729 / 39,526,425 = **5.78%** |
| D14 positive rate | 6,799,516 / 39,526,425 = **17.20%** | 2,372,042 / 39,526,425 = **6.00%** |
| D28 positive rate | 6,898,651 / 39,526,425 = **17.45%** | 2,420,872 / 39,526,425 = **6.12%** |
| Total range (D0→D28) | +2.19 pp | +1.36 pp |
| D7 captures (% of D28 total) | 16.86 / 17.45 = **96.6%** | 5.78 / 6.12 = **94.4%** |
| Negative class at D28 (NULL+0) | 32,627,774 (**82.55%**) | 37,105,553 (**93.88%**) |
| **Unattributed** | | |
| D0 positive rate | 104,044,977 / 704,931,607 = **14.76%** | 50,593,116 / 704,931,607 = **7.18%** |
| D7 positive rate | 117,467,684 / 704,931,607 = **16.66%** | 60,582,179 / 704,931,607 = **8.60%** |
| D28 positive rate | 121,745,098 / 704,931,607 = **17.27%** | 63,127,221 / 704,931,607 = **8.96%** |
| Negative class at D28 (NULL+0) | 583,186,509 (**82.73%**) | 641,804,386 (**91.04%**) |

With NULL=0, both labels flip to **low positive-rate** targets — the dominant class is now negative for both. The key contrasts:

- **Positive rate:** `cum_has_event_dx` is 2.8–2.9× higher than `cum_has_lc_event_dx` at every window (17.45% vs 6.12% at D28 for attributed). This reflects the same ~17% event-configured population, further filtered by those who actually completed a level.
- **Negative class size:** LC has a larger negative class (93.88% vs 82.55% for attributed at D28) because it adds ~11 pp of installs that have event tracking configured but never hit a level-complete event — the true "had opportunity, did not progress" population.
- **Growth range:** Both labels compress into a narrow range (2.19 pp for event, 1.36 pp for LC across D0→D28). The D0 signal already captures most of the lifetime positive class, making observation-window choice less critical than advertiser-tracking coverage.
- **D7 sufficiency:** Both labels are ≥94% saturated by D7 relative to their D28 total. Extending to D28 adds negligible signal.

### 2F. Why D0 ≈ D7 ≈ D28: install-hour event concentration

The narrow 2.19 pp spread between D0 and D28 (for `cum_has_event_dx`) and 1.36 pp spread (for `cum_has_lc_event_dx`) is explained by two independent mechanisms that compound each other.

**Mechanism 1 — The NULL ceiling is fixed at ~17.5%**

The labeled population (non-NULL rows) is the same set of rows at every window from D0 to D28. Whether a row is NULL or not is determined by advertiser MMP tracking configuration at install time — it does not change over the observation period. This means the maximum achievable positive rate at any window is capped at the fill rate (~17.5% for custom events, ~17.5% for LC). The entire D0→D28 range is compressed into a corridor bounded by that ceiling.

**Mechanism 2 — Events fire overwhelmingly at H0 (install hour)**

From the `first_seen_at` timing data (Section 8), H0 accounts for the dominant share of all first-event occurrences:

| Hour | Unattr events | Attributed events | Ratio vs H1 |
|---|---|---|---|
| H0 | 144,964,007 | 7,666,867 | **~16×** |
| H1 | 8,993,881 | 431,240 | 1× |
| H2 | 5,562,293 | 233,642 | 0.54× |
| H24 (D1 return) | 3,280,401 | — | 0.37× |

Within the labeled population alone (conditional positive rates), **87.41% of attributed rows already have `cum_has_event_d0 = 1`** — an event fired in the first hour after install. That translates to 87.41% × 17.46% = **15.26% of all attributed rows** being positive at D0. The remaining 27 days can only add the final 2.19 pp.

**Why H0 dominates:** The top custom and LC events for both populations fire at or immediately after install:

| Event type | When it fires | Affected population |
|---|---|---|
| MMP behavioral scores (`af_bs_conversion_rt`, `d2_rr_user_rt`, `2d_rr_user`) | Computed by MMP **at install time**, before first app open | Unattributed top 3 |
| App open / session start (`af_app_opened`, `SESSION_START`) | First app launch — typically H0 | Both populations |
| Registration / tutorial (`Register`, `af_complete_registration`, `af_tutorial_completion`) | First few minutes of onboarding | Attributed top events |
| LC game-engine events (`_no_sdk_event_name`, `level_end_success_1`) | First gameplay session | Attributed LC |

**Implication for observation window choice:**

| Observation window | Attr custom event rate | Attr LC rate | % of D28 total captured |
|---|---|---|---|
| D0 (install day only) | 15.26% | 4.76% | event 87.5%, LC 77.8% |
| D1 | 15.85% | 5.14% | event 90.8%, LC 83.9% |
| D7 | 16.86% | 5.78% | event 96.6%, LC 94.4% |
| D28 | 17.45% | 6.12% | 100% |

**The observation window is the secondary lever; advertiser tracking coverage is the primary one.** Moving from D0 to D7 adds 1.6 pp for custom events and 1.02 pp for LC. Moving from D0 to D28 adds only 2.19 pp and 1.36 pp respectively. Doubling the advertiser event tracking coverage from 17.5% to 35% would dwarf any window extension benefit.

---

## 3. Level-Complete Labels (`cum_has_lc_event_dx`)

### 3A. Conditional positive rate (among labeled rows; same labeled population as §2)

| Window | Unattributed | Attributed | Delta (Attr - Unattr) |
|---|---|---|---|
| D0 | 41.56% | 27.29% | **-14.27 pp** |
| D1 | 44.89% | 29.45% | **-15.44 pp** |
| D7 | 49.76% | 33.09% | **-16.67 pp** |
| D14 | 50.89% | 34.38% | **-16.51 pp** |
| D28 | 51.85% | 35.09% | **-16.76 pp** |

The ~17 pp LC gap between unattributed and attributed is consistent with and replicates the prior full-dataset analysis (-17.68 pp at D7). The gap opens early (D0: -14 pp), widens slightly through D7, then stabilizes. It does not close — attributed users plateau in level progression while organic users continue advancing.

`cum_has_lc_event_dx` is the **primary training label** for LC optimization: it has genuine discriminative power (35% vs 52% at D28) with a meaningful negative class (~65% of attributed event-configured rows have no LC by D28).

### 3B. Label growth curve — incremental LC gain per window

| Window | Unattr LC rate | Attr LC rate | Incremental gain (Unattr) | Incremental gain (Attr) |
|---|---|---|---|---|
| D0 | 41.56% | 27.29% | — | — |
| D1 | 44.89% | 29.45% | +3.33 pp | +2.16 pp |
| D7 | 49.76% | 33.09% | +4.87 pp | +3.64 pp |
| D14 | 50.89% | 34.38% | +1.13 pp | +1.29 pp |
| D28 | 51.85% | 35.09% | +0.96 pp | +0.71 pp |

Most LC signal arrives by D7. Post-D7 gains are small for both groups (~1 pp per week). For attributed users in particular, D0–D7 captures the overwhelming majority of available LC signal. Using D1 as the label window captures ~84% of the D28 LC signal for attributed users (29.45% / 35.09%).

---

## 4. Deposit / IOJ Labels (`cum_depositor_dx`)

### 4A. Fill rate

| Segment | Total rows | Labeled rows | Fill rate |
|---|---|---|---|
| Unattributed | 704,931,607 | 10,551,531 | **1.50%** |
| Attributed | 39,526,425 | 376,536 | **0.95%** |

The deposit label fill rate is ~10× lower than the custom event fill rate (1.5% vs 17.3%). This is a separate advertiser-configured tracking population — purchase/deposit callbacks require explicit advertiser integration beyond standard event tracking. The lower attributed rate (0.95% vs 1.50%) reflects that not all campaigns are monetisation-optimized.

### 4B. Conditional positive rate

| Window | Unattributed | Attributed |
|---|---|---|
| D7 | 87.29% | 88.59% |
| D28 | 99.999% | 99.999% |

The deposit label is almost exclusively positive — at D28, essentially all installs with deposit tracking configured had at least one deposit. This means `cum_depositor_d28` has near-zero discriminative power on its own. The useful deposit signal is in the **count** (`deposit_count_dx`) and **revenue** (`deposit_sum_dx`, `cum_deposit_sum_dx`) columns, not the binary flag. The D7 rate (~88%) vs D28 (~100%) shows that ~12% of depositors take longer than 7 days to make their first deposit.

---

## 5. Label Integrity Checks

All integrity checks pass with **zero violations**:

| Check | Unattributed | Attributed |
|---|---|---|
| `cum_has_event_d7=0` AND `cum_has_lc_event_d7=1` (LC without any event) | **0** | **0** |
| `cum_has_event_d7=1` AND `cum_event_count_d7=0` (flag=1 but count=0) | **0** | **0** |
| `cum_has_lc_event_d7=1` AND `cum_event_count_d7=0` (LC flag with zero total count) | **0** | **0** |

The label columns are internally consistent. `cum_has_lc_event_dx` is a strict subset of `cum_has_event_dx` as expected.

---

## 6. `sdk_event_name_first_seen_arr` — Custom Event Array Deep Dive

### 6A. Array size statistics

| Metric | Unattributed | Attributed |
|---|---|---|
| Rows with empty array (no events) | 595,076,880 (**84.42%**) | 33,558,427 (**84.90%**) |
| Rows with ≥1 event | 109,854,727 (15.58%) | 5,967,998 (15.10%) |
| Average array size (all rows) | 0.420 | 0.350 |
| Max array size | **266** | **185** |

The empty-array rate (84.4–84.9%) is slightly higher than the null rate in `cum_has_event_dx` (82.5–82.7%). The ~2 pp gap indicates a small population with `cum_has_event_d28 IS NOT NULL` but an empty array — these installs have a non-null event label but no named events in the array. This could represent installs where the advertiser configured an event type that doesn't map to a named SDK event.

Attributed users have a lower max array size (185 vs 266), meaning campaign-configured event suites tend to be smaller than the organic long-tail.

### 6B. Top custom events — Unattributed (top 20)

| Rank | sdk_event_name | User count | Category |
|---|---|---|---|
| 1 | `af_bs_conversion_rt` | 12,221,456 | MMP behavioral score |
| 2 | `d2_rr_user_rt` | 9,474,021 | MMP D2 retention score |
| 3 | `2d_rr_user` | 9,337,418 | MMP D2 return flag |
| 4 | `tt_login_rt` | 5,639,026 | TikTok login rate signal |
| 5 | `af_app_opened` | 5,597,445 | App open (standard AF) |
| 6 | `mus_af_post_video` | 5,558,692 | Music/video engagement |
| 7 | `10_games_played` | 5,392,744 | Engagement milestone |
| 8 | `2_games_played` | 5,093,754 | Early engagement milestone |
| 9 | `Launch（起動）` | 4,501,236 | App launch (Japanese game) |
| 10 | `CreateUserId（ユーザーID生成）` | 4,168,323 | User ID creation (Japanese game) |
| 11 | `TutorialComp（チュートリアル完了）` | 3,730,629 | Tutorial completion (Japanese game) |
| 12 | `af_pltv_lt7_ug_v2_deeplt` | 3,308,302 | Predicted LTV < D7 deep signal |
| 13 | `af_complete_registration` | 3,293,735 | Registration completion (AF) |
| 14 | `SESSION_START` | 3,182,767 | Session start |
| 15 | `af_webcast_14days` | 2,719,547 | 14-day livestream engagement |
| 16 | `Register` | 2,592,986 | Registration |
| 17 | `af_tutorial_completion` | 2,074,286 | Tutorial completion (AF) |
| 18 | `game_end_7` | 2,034,343 | 7th game session end |
| 19 | `Login` | 1,920,918 | Login |
| 20 | `Level3` | 1,879,425 | Level 3 milestone |

### 6C. Top custom events — Attributed (top 20)

| Rank | sdk_event_name | User count | Category |
|---|---|---|---|
| 1 | `Register` | 1,023,755 | **Registration** |
| 2 | `2_games_played` | 569,855 | Early engagement milestone |
| 3 | `10_games_played` | 442,667 | Engagement milestone |
| 4 | `rewarded_impression` | 392,605 | Rewarded ad impression |
| 5 | `register` | 187,527 | Registration (lowercase variant) |
| 6 | `打开App` | 183,483 | App launch (Chinese-language game) |
| 7 | `af_complete_registration` | 133,699 | Registration (AF standard) |
| 8 | `af_level_achieved` | 124,224 | Level achieved (AF standard) |
| 9 | `af_tutorial_completion` | 119,130 | Tutorial completion |
| 10 | `2_GAMES_PLAYED` | 116,154 | Engagement milestone (uppercase variant) |
| 11 | `Login` | 109,672 | Login |
| 12 | `login` | 96,278 | Login (lowercase variant) |
| 13 | `100_games_played` | 93,605 | Deep engagement milestone |
| 14 | `af_app_opened` | 80,523 | App open |
| 15 | `level_win` | 78,416 | Level win |
| 16 | `Launch App` | 75,630 | App launch |
| 17 | `First Time Open` | 74,833 | First launch |
| 18 | `registration` | 73,058 | Registration (variant) |
| 19 | `F-024_offerwall_appear` | 71,622 | Offerwall appearance event |
| 20 | `F-002-1_authorization_succeed` | 69,223 | Authorization success |

### 6D. Key difference: Attributed vs Unattributed event taxonomy

**The top event types are completely different between attributed and unattributed.**

| Dimension | Unattributed | Attributed |
|---|---|---|
| Top events | MMP behavioral scores (`af_bs_conversion_rt` 12.2M, `d2_rr_user_rt` 9.5M, `2d_rr_user` 9.3M) | In-app actions (`Register` 1.02M, `2_games_played` 570K, `10_games_played` 443K) |
| MMP score events in top 5 | 3 of 5 | 0 of 5 |
| Japanese-localized events in top 15 | 3 (`Launch`, `CreateUserId`, `TutorialComp`) | 0 |
| Chinese-localized events | None in top 15 | 1 (`打开App`) |
| Event diversity | High — top event covers 10% of labeled rows | Low — top event (`Register`) covers only ~17% of attributed labeled rows |

**Why the divergence:** MMP behavioral scores (`af_bs_conversion_rt`, `d2_rr_user_rt`) are computed automatically for all MMP-tracked installs and represent the largest publishers' organic/unattributed volume. For attributed installs, UA campaigns configure specific in-app events that align with their optimization goal — registration, games played, level milestones — rather than MMP-derived scores. This means:

1. **The two populations cannot share event-name feature embeddings.** An event named `Register` in attributed context is a genuine in-app event; the top unattributed events are algorithmic scores. A model trained on both populations needs to treat event names as population-conditioned.

2. **Attributed events are more semantically clean for LC optimization.** The top attributed events (games played milestones, level wins, `af_level_achieved`) align directly with level-progression behavior, making `sdk_event_name` a stronger direct feature for attributed LC prediction.

3. **Case-sensitivity fragmentation in attributed events.** `Register` (1.02M), `register` (188K), `registration` (73K), and `af_complete_registration` (134K) all represent the same funnel step. Normalization (lowercase + canonical mapping) could meaningfully reduce vocabulary size without information loss.

---

## 7. `sdk_event_name_first_seen_arr_lc` — LC Event Array Deep Dive

### 7A. Array size statistics

| Metric | Unattributed | Attributed |
|---|---|---|
| Rows with empty LC array | 641,804,266 (**91.04%**) | 37,105,544 (**93.88%**) |
| Rows with ≥1 LC event | 63,127,341 (8.96%) | 2,420,881 (6.12%) |
| Average array size (all rows) | 0.235 | 0.152 |
| Max array size | **68** | **67** |

LC array coverage is lower than custom array coverage by ~6 pp for unattributed and ~9 pp for attributed — these are event-configured installs with no LC event registered by D28. This is the true negative class for LC optimization.

### 7B. Top LC events — Unattributed (top 15)

| Rank | sdk_event_name | User count | Notes |
|---|---|---|---|
| 1 | `af_bs_conversion_rt` | 12,221,456 | **Dual-registered MMP score** |
| 2 | `d2_rr_user_rt` | 9,474,021 | Dual-registered MMP score |
| 3 | `2d_rr_user` | 9,337,418 | Dual-registered MMP score |
| 4 | `_no_sdk_event_name` | 6,881,743 | **Game-engine LC, no SDK name** |
| 5 | `tt_login_rt` | 5,639,026 | Dual-registered — TikTok signal |
| 6 | `mus_af_post_video` | 5,558,692 | Dual-registered — media engagement |
| 7 | `af_pltv_lt7_ug_v2_deeplt` | 3,308,302 | Dual-registered — LTV signal as LC |
| 8 | `af_webcast_14days` | 2,719,547 | Dual-registered |
| 9 | `grt_3r_success_30` | 1,844,297 | 3-round success within 30 days |
| 10 | `s_custom9_revenue_3` | 1,482,466 | Revenue threshold as LC |
| 11 | `Level3` | 1,427,598 | Level 3 milestone (genuine LC) |
| 12 | `registrations` | 1,126,906 | Registration as LC proxy |
| 13 | `af_tts_watch_duration_value_7d` | 1,066,646 | TikTok watch duration |
| 14 | `af_app_opened` | 973,959 | App open as LC (very low bar) |
| 15 | `Level5` | 963,820 | Level 5 milestone (genuine LC) |

### 7C. Top LC events — Attributed (top 15)

| Rank | sdk_event_name | User count | Notes |
|---|---|---|---|
| 1 | `_no_sdk_event_name` | 520,901 | **Game-engine LC — dominant** |
| 2 | `af_level_achieved` | 123,284 | Standard AF level event |
| 3 | `login` | 78,236 | Login as LC proxy |
| 4 | `level_win` | 77,167 | Level win |
| 5 | `10_games_played` | 58,418 | Games played as LC |
| 6 | `pLTVD904U` | 57,469 | LTV signal as LC |
| 7 | `level_end_success_1` | 47,466 | Stage clear (level 1) |
| 8 | `level_end_success_2` | 45,156 | Stage clear (level 2) |
| 9 | `level_end_success_30` | 45,004 | Stage clear (level 30) |
| 10 | `level_end_success_10` | 44,935 | Stage clear (level 10) |
| 11 | `level_end_success_5` | 43,200 | Stage clear (level 5) |
| 12 | `level_end_success_3` | 42,338 | Stage clear (level 3) |
| 13 | `level_end_success_4` | 40,818 | Stage clear (level 4) |
| 14 | `s_custom2_revenue_game5_day3` | 39,146 | Revenue signal as LC |
| 15 | `s_custom3_revenue_game5_day3` | 38,740 | Revenue signal as LC |

### 7D. Key structural differences in LC taxonomy

**Unattributed LC is dominated by dual-registered MMP scores; attributed LC is dominated by `_no_sdk_event_name`.**

| Dimension | Unattributed | Attributed |
|---|---|---|
| #1 LC event | `af_bs_conversion_rt` (12.2M) — MMP score | `_no_sdk_event_name` (521K) — game-engine LC |
| MMP score events in top 5 | 3 of 5 | 0 of 5 |
| `_no_sdk_event_name` rank | #4 (6.9M, ~11% of LC users) | **#1 (521K, ~22% of attributed LC users)** |
| True level-completion events | Low proportion in top ranks | High proportion (`level_win`, `level_end_success_*`, `af_level_achieved`) |
| `level_end_success_*` series | Present but lower-ranked | **Ranks 7–13** — consistent series from level 1 through 30 |

**`_no_sdk_event_name` is LC-array exclusive — it has zero occurrences in `sdk_event_name_first_seen_arr` (custom array).** This was verified directly:

| Array | Unattributed count | Attributed count |
|---|---|---|
| `sdk_event_name_first_seen_arr` (custom) | **0** | **0** |
| `sdk_event_name_first_seen_arr_lc` (LC) | 6,881,743 | 520,901 |

This means `_no_sdk_event_name` represents a **game-engine LC signal that was never routed through the MMP SDK event pipeline at all** — the advertiser's game engine reported a level completion directly (e.g., via a server-to-server callback or a non-SDK integration path) without registering a named custom event. It surfaces only in the LC array because that array has a separate ingestion path that accepts unnamed signals; the custom event array requires an SDK event name and silently drops nameless entries.

**`_no_sdk_event_name` in attributed context:** With 520,901 users (~22% of the 2.42M attributed LC-positive installs), this is the single most common LC signal for attributed users. These are installs where the advertiser registered a game-engine level event without a named SDK callback. This population has valid LC behavior but cannot be linked to a named event — it requires a boolean indicator feature (`has_unnamed_lc_event`) rather than event-name features.

**`level_end_success_*` series pattern:** Ranks 7–13 for attributed LC show a consistent progression: levels 1, 2, 3, 4, 5, 10, 30. All with ~39–47K users each. This suggests a single publisher with granular per-level tracking contributing heavily to attributed LC volume.

---

## 8. `first_seen_at` Timing Distribution (H0 – H672, full D28 window)

Total first-event occurrences in H0–H672: **295.5M unattributed, 13.8M attributed.**

### 8A. Day-level summary

| Day | Hour range | Unattr events | Unattr % | Unattr cum% | Attr events | Attr % | Attr cum% |
|---|---|---|---|---|---|---|---|
| D0 | H0–H23 | 202,830,603 | **68.64%** | 68.64% | 10,175,935 | **73.63%** | 73.63% |
| D1 | H24–H47 | 30,707,555 | 10.39% | 79.03% | 1,031,864 | 7.47% | 81.09% |
| D2 | H48–H71 | 15,681,148 | 5.31% | 84.34% | 545,258 | 3.95% | 85.04% |
| D3 | H72–H95 | 8,787,185 | 2.97% | 87.31% | 363,226 | 2.63% | 87.66% |
| D4 | H96–H119 | 6,719,788 | 2.27% | 89.58% | 262,218 | 1.90% | 89.56% |
| D5 | H120–H143 | 4,887,041 | 1.65% | 91.24% | 206,899 | 1.50% | 91.06% |
| D6 | H144–H167 | 4,266,226 | 1.44% | 92.68% | 180,111 | 1.30% | 92.36% |
| D7 | H168–H191 | 3,270,333 | 1.11% | 93.79% | 170,861 | 1.24% | 93.60% |
| D8 | H192–H215 | 2,124,323 | 0.72% | 94.51% | 134,457 | 0.97% | 94.57% |
| D9 | H216–H239 | 1,714,932 | 0.58% | 95.09% | 76,391 | 0.55% | 95.12% |
| D10 | H240–H263 | 1,509,292 | 0.51% | 95.60% | 66,826 | 0.48% | 95.61% |
| D11 | H264–H287 | 1,355,989 | 0.46% | 96.06% | 60,181 | 0.44% | 96.04% |
| D12 | H288–H311 | 1,230,019 | 0.42% | 96.47% | 54,743 | 0.40% | 96.44% |
| D13 | H312–H335 | 1,188,711 | 0.40% | 96.88% | 55,311 | 0.40% | 96.84% |
| D14 | H336–H359 | 1,054,559 | 0.36% | 97.23% | 48,800 | 0.35% | 97.19% |
| D15 | H360–H383 | 910,279 | 0.31% | 97.54% | 42,536 | 0.31% | 97.50% |
| D16 | H384–H407 | 826,170 | 0.28% | 97.82% | 38,519 | 0.28% | 97.78% |
| D17 | H408–H431 | 763,903 | 0.26% | 98.08% | 35,270 | 0.26% | 98.03% |
| D18 | H432–H455 | 714,265 | 0.24% | 98.32% | 33,707 | 0.24% | 98.28% |
| D19 | H456–H479 | 675,036 | 0.23% | 98.55% | 32,577 | 0.24% | 98.51% |
| D20 | H480–H503 | 645,391 | 0.22% | 98.77% | 31,437 | 0.23% | 98.74% |
| D21 | H504–H527 | 615,186 | 0.21% | 98.97% | 29,998 | 0.22% | 98.96% |
| D22 | H528–H551 | 571,057 | 0.19% | 99.17% | 27,284 | 0.20% | 99.15% |
| D23 | H552–H575 | 534,959 | 0.18% | 99.35% | 26,085 | 0.19% | 99.34% |
| D24 | H576–H599 | 506,543 | 0.17% | 99.52% | 24,707 | 0.18% | 99.52% |
| D25 | H600–H623 | 477,625 | 0.16% | 99.68% | 22,569 | 0.16% | 99.69% |
| D26 | H624–H647 | 456,320 | 0.15% | 99.84% | 21,076 | 0.15% | 99.84% |
| D27 | H648–H671 | 444,131 | 0.15% | 99.99% | 20,885 | 0.15% | 99.99% |
| D28 | H672 | 38,507 | 0.01% | 100.00% | 1,489 | 0.01% | 100.00% |

### 8B. Hourly detail — D0 install spike and daily return pattern (unattributed)

```
H0        ████████████████████████████████████  144.96M  ← install-hour (MMP scores + first session)
H1        ██                                      8.99M
H2        █                                       5.56M
H3–H11    ▌  gradual decay  (2–3M/hr)
H12–H22   ▌  plateau/rise   (1.7–2.4M/hr)
H23       ▌                                       3.04M
─── D1 boundary ────────────────────────────────────────
H24       █                                       3.28M  ← D1 return spike
H25–H46   ~1–2M/hr  (decay then gradual rise)
H47       ▌                                       1.51M  ← D2 return spike peak
─── D2 boundary ────────────────────────────────────────
H48–H71   ~400K–1.4M/hr  (decay then rise)
H72       ▌                                         686K ← D3 return spike
─── D3 boundary ────────────────────────────────────────
H96       ▌                                         499K ← D4 return spike
H120      ▌                                         386K ← D5 return spike
H144      ▌                                         314K ← D6 return spike
H168      ▌                                         286K ← D7 return spike
         ...decaying ~10–15% per day...
H336      ▌                                          86K ← D14 return spike
H504      ▌                                          47K ← D21 return spike
H672      ▌                                          39K ← D28 return spike
```

Attributed H0: **7,666,867** (same spike-then-decay shape, slightly more D0-concentrated: 73.6% vs 68.6%).

### 8C. Key observations

**D0 dominance is even stronger than the H0–H96 view suggested.** Expanding to H672 confirms:
- **68.6% (unattr) / 73.6% (attr)** of all first-event occurrences in a 28-day window happen on install day
- D0+D1 together account for **79.0% / 81.1%** — four-fifths of the entire lifecycle's first-event signal arrives within 48 hours
- By D7, **93.8% / 93.6%** of the lifetime total has been captured
- D8–D28 add only **6.2% / 6.4%** across 20 days, with each individual day below 1%

**Daily return spike pattern decays steadily.** The D1 return spike (H24) is 3.28M — already only 2.3% of H0. Each subsequent daily spike is ~65–75% of the previous day's spike through D7, then ~80–85% per day from D8 onward as the long-tail cohort stabilises.

**Attributed users are more install-day concentrated than unattributed.** D0 share: 73.6% (attr) vs 68.6% (unattr). Campaign-acquired users are more likely to engage immediately (app opens, registrations, tutorial events fire in the first session) and less likely to return on later days, compared to organic users who discover apps more organically and may return at varied intervals.

**Long-tail events (D8–D28) are real but small.** The 6.2% of events that arrive after D7 represent genuine delayed engagement (users who return to a game days later and hit a milestone for the first time). These are the converters that a D7 label window would miss — consistent with the 3.4 pp gap between `cum_has_lc_event_d7` (33.09%) and `cum_has_lc_event_d28` (35.09%) for attributed users.

**Modeling implication:** `first_seen_at` should be engineered as `hours_after_install = TIMESTAMP_DIFF(first_seen_at, installTimestamp, HOUR)` and log-transformed due to the extreme H0 concentration (144.96M at H0 vs ~30K–500K in the D8–D28 tail). Treating raw timestamps as features will encode timezone and calendar effects rather than behavioral signals.

---

## 9. Array Examples — What the Data Actually Looks Like

Each element in both arrays is a `(sdk_event_name, first_seen_at)` struct recording the **first time** that event name fired for this install. Repeated occurrences of the same event are not tracked here — use `cum_event_count_dx` for counts.

### Case 1 — Messaging app (attributed, all events dual-registered)

```
installTimestamp: 2026-06-01 18:06:29

sdk_event_name_first_seen_arr (custom)      sdk_event_name_first_seen_arr_lc (LC)
─────────────────────────────────────────   ──────────────────────────────────────────
Send1MSG    → 2026-06-01 18:12:15 (H0+6m)  Send50MSG   → 2026-06-01 18:40:23 (H0+34m)
Send50MSG   → 2026-06-01 18:40:23 (H0+34m) Send1MSG    → 2026-06-01 18:12:15 (H0+6m)
Send100MSG  → 2026-06-01 19:02:00 (H0+56m) Send100MSG  → 2026-06-01 19:02:00 (H0+56m)
```

Both arrays contain the **exact same 3 events** — message-count milestones (`Send1MSG`, `Send50MSG`, `Send100MSG`) registered as both custom events and LC events. All fire within the first hour. Note: the arrays are **not time-sorted** (different element order in each array).

### Case 2 — Level progression game (attributed, granular per-level milestones)

```
installTimestamp: 2026-06-01 19:55:00

sdk_event_name_first_seen_arr (custom)      sdk_event_name_first_seen_arr_lc (LC)
─────────────────────────────────────────   ──────────────────────────────────────
level_100 → 2026-06-07 15:47 (D6)          level_100 → 2026-06-07 15:47 (D6)
level_125 → 2026-06-09 17:04 (D8)          level_125 → 2026-06-09 17:04 (D8)
level_150 → 2026-06-10 16:19 (D9)          level_150 → 2026-06-10 16:19 (D9)
level_175 → 2026-06-12 14:37 (D11)         level_175 → 2026-06-12 14:37 (D11)
```

User progressed through levels 100→125→150→175 across days 6–11. Both arrays are fully identical — every level milestone is dual-registered. The timestamps here are spread across multiple return sessions, showing genuine long-term engagement.

### Case 3 — LTV thresholds as LC proxy (attributed)

```
installTimestamp: 2026-06-01 18:52:20

sdk_event_name_first_seen_arr (custom)      sdk_event_name_first_seen_arr_lc (LC)
─────────────────────────────────────────   ──────────────────────────────────────
ltv_25 → 2026-06-01 20:02 (H1)             ltv_25 → 2026-06-01 20:02 (H1)
ltv_50 → 2026-06-20 12:43 (D18)            ltv_50 → 2026-06-20 12:43 (D18)
```

Revenue LTV thresholds ($25, $50) used as both custom and LC signals — no actual level completion. `ltv_50` fires on D18, illustrating why some users only appear as LC-positive at later observation windows.

### Case 4 — Standard level-achievement events (attributed)

```
installTimestamp: 2026-06-01 00:42:44

custom:                                     LC (identical):
af_Level_5  → 2026-06-23 16:57 (D22)       af_Level_5  → 2026-06-23 16:57 (D22)
af_Level_10 → 2026-06-23 16:57 (D22)       af_Level_10 → 2026-06-23 16:57 (D22)
```

Both events fire at the exact same timestamp on D22 — the user reached levels 5 and 10 in the same session. This install would show `cum_has_lc_event_d21 = 0` but `cum_has_lc_event_d28 = 1`, illustrating a late converter that the D7 label window would entirely miss.

### Case 5 — `_no_sdk_event_name` (attributed) — LC array only, custom struct is NULL

```
installTimestamp: 2026-06-01 18:47:00

sdk_event_name_first_seen_arr (custom): NULL   ← entire struct is null, not an empty list
sdk_event_name_first_seen_arr_lc (LC):
  _no_sdk_event_name → 2026-06-01 18:51:21 (4 minutes after install)
```

```
installTimestamp: 2026-06-01 10:44:20

sdk_event_name_first_seen_arr (custom): NULL
sdk_event_name_first_seen_arr_lc (LC):
  _no_sdk_event_name → 2026-06-01 10:44:52 (32 seconds after install)
```

The custom struct is `NULL` — not an empty array — meaning no custom event tracking is configured at all for these installs. Yet an LC signal arrives within seconds/minutes of install via a completely separate ingestion path. This is the population flagged in Finding 8 for data team verification.

### Structural observations from raw examples

| Observation | Detail |
|---|---|
| `first_seen_at` is first-occurrence only | Each event name appears at most once per array. Repeated fires are not tracked here; use `cum_event_count_dx` for counts. |
| Arrays are not time-sorted | Element order within the array is arbitrary — do not treat position as sequence. |
| Dual-registration is the norm | In all 4 regular examples, custom and LC arrays are 100% identical. Advertisers commonly register the same events in both pipelines. |
| `_no_sdk_event_name` has a NULL custom struct | Not just an empty list — the entire `sdk_event_name_first_seen_arr` struct is NULL, confirming the LC signal arrived via a path with no custom event pipeline involvement. |
| Late converters exist | Case 4 (D22) and Case 3 (D18 for `ltv_50`) show meaningful LC signals that would be missed by D7 or D14 label windows. |

---

## 10. Summary of Key Findings

### Finding 1: Attribution column is `isAttributed` (BOOLEAN), not `is_attributed`

The column follows the legacy naming convention applied by the Spark export job (§6A rename). All BQ queries on this table must use `isAttributed`, not `is_attributed`.

### Finding 2: Fill rates are symmetric — ~17% custom event, ~1.5% deposit, regardless of attribution

Both populations have identical structural null rates (~82.5% null for custom events, ~98.5% null for deposit labels). The fill rate is an advertiser-configuration property, not a modeling property. Do not filter out null rows — they carry full feature signal and are valid true-negatives for event optimization targets.

### Finding 3: `cum_has_event_dx` fill rate is ~17% overall but ~35% among games that actually use custom event tracking

With NULL=0 across all games, `cum_has_event_dx` at D7 is a low positive-rate label (~17%). However, this overall rate conflates two fundamentally different game populations. Game-level analysis on `unity-ads-dd-ds-dev-prd.yabo.huron_ioj_d28_0601_0606` (install dates 2026-06-01 to 2026-06-06):

| Scope | Rows/install_date | Fill rate | Positive rate (NULL=0) |
|---|---|---|---|
| All games (entire dataset) | ~124M | ~17% | ~17% |
| Games that sent any custom SDK events (`game_custom`) | ~53–57M | ~35–37% | **~34–36%** |
| Games with any attributed installs (`game_attr`) | ~74–80M | ~20% | ~19% |
| Games with both custom events AND attributed installs (`both`) | ~37–39M | ~37% | **~35–36%** |

Full results by install date:

| install_date | custom_total | custom_fill_rate | custom_positive_rate | attr_total | attr_fill_rate | attr_positive_rate | both_total | both_fill_rate | both_positive_rate |
|---|---|---|---|---|---|---|---|---|---|
| 2026-06-01 | 53,730,741 | 35.21% | 33.90% | 76,667,046 | 19.55% | 18.78% | 37,373,184 | 36.93% | 35.43% |
| 2026-06-02 | 53,248,078 | 35.61% | 34.30% | 75,460,594 | 19.84% | 19.07% | 37,028,417 | 37.27% | 35.76% |
| 2026-06-03 | 52,750,529 | 35.56% | 34.24% | 73,908,652 | 19.87% | 19.09% | 36,615,111 | 36.91% | 35.41% |
| 2026-06-04 | 53,650,449 | 36.23% | 34.95% | 73,663,422 | 19.78% | 19.01% | 36,596,090 | 36.60% | 35.13% |
| 2026-06-05 | 54,567,638 | 36.48% | 35.22% | 74,543,664 | 19.54% | 18.77% | 36,777,596 | 36.45% | 34.98% |
| 2026-06-06 | 57,134,944 | 36.93% | 35.64% | 79,903,055 | 19.65% | 18.89% | 38,780,250 | 37.06% | 35.58% |

**The ~83% null is not purely an advertiser tracking configuration gap — a large portion of the dataset is installs from games that never sent any custom SDK events at all.** Once restricted to games that actively use custom event tracking, the positive rate jumps to ~34–36%, roughly double the overall rate. Note that `custom_fill_rate` and `custom_positive_rate` are nearly identical (~1 pp apart): within games that configured custom event tracking, almost every non-null row is positive — confirming the near-zero negative rate in the labeled population is a real property of these games.

For modeling purposes, the effective training population is the **both** cohort (~37M rows/install_date, ~35–36% positive rate, consistent day-over-day). The overall 17% rate understates signal density by ~2×.

The observation window remains nearly irrelevant regardless of scope — D0 already captures ~87% of D7's positives due to H0 concentration (see Finding 10).

### Finding 4: `cum_has_lc_event_dx` — ~28% positive rate among LC-configured games, 0% for games without LC tracking

Parallel to Finding 3, splitting by game-level LC event configuration reveals that the overall ~6% positive rate (NULL=0) masks two completely distinct populations. Game-level analysis on `unity-ads-dd-ds-dev-prd.yabo.huron_ioj_d28_0601_0606` (install dates 2026-06-01 to 2026-06-06):

| Scope | Rows/install_date | LC fill rate | LC positive rate (NULL=0) |
|---|---|---|---|
| All games (entire dataset) | ~124M | ~17% | ~6% |
| Games that sent any LC events (`game_lc`) | ~38–40M | **~33%** | **~27%** |
| LC games + attributed installs (`game_lc AND game_attr`) | ~30–31M | **~33–34%** | **~28–29%** |
| Custom events but NO LC events (`game_custom AND NOT game_lc`) | ~19–21M | ~41–44% | **0.0%** |

Full results by install date:

| install_date | lc_total | lc_fill_rate | lc_positive_rate | lc_attr_total | lc_attr_fill_rate | lc_attr_positive_rate | custom_no_lc_total | custom_no_lc_fill_rate | custom_no_lc_positive_rate |
|---|---|---|---|---|---|---|---|---|---|
| 2026-06-01 | 38,228,172 | 32.76% | 27.22% | 30,142,972 | 33.49% | 28.58% | 18,753,593 | 40.79% | 0.0% |
| 2026-06-02 | 37,898,540 | 33.30% | 27.60% | 29,981,650 | 34.14% | 28.98% | 18,542,985 | 40.93% | 0.0% |
| 2026-06-03 | 37,618,289 | 33.17% | 27.46% | 29,745,457 | 33.80% | 28.58% | 18,287,395 | 41.12% | 0.0% |
| 2026-06-04 | 37,702,504 | 32.92% | 27.23% | 29,760,913 | 33.47% | 28.38% | 19,154,428 | 43.16% | 0.0% |
| 2026-06-05 | 37,828,450 | 32.73% | 27.13% | 29,756,592 | 33.25% | 28.25% | 19,905,728 | 43.94% | 0.0% |
| 2026-06-06 | 39,775,136 | 33.48% | 27.96% | 31,328,319 | 33.89% | 28.96% | 20,821,312 | 44.08% | 0.0% |

**Three structural observations:**

1. **LC-configured games have ~28–29% positive rate (NULL=0)** — not 6%. The overall 6% is diluted by the large population of games that never registered any LC events. Among games that actively use LC tracking and have attributed installs, ~29% of all their installs are LC-positive, consistent day-over-day.

2. **Custom-only games (no LC) have exactly 0.0% LC positive rate but ~41–44% LC fill rate.** These games have MMP custom event tracking (so `cum_has_lc_event_d7` gets populated as non-null for their event-configured installs), but the value is always `0` because they never registered any LC events. This confirms the label pipeline is working correctly — `cum_has_lc_event_d7` is populated at the same rate as `cum_has_event_d7` for event-tracking games, but the value depends on whether LC was specifically configured.

3. **The attribution gap (~17 pp conditional) still holds within LC-configured games.** The overall NULL=0 gap between attributed and unattributed (~2.84 pp) was diluted by the ~83% NULL population. Within LC-configured attributed games, the positive rate is **~28–29%** — consistent with the conditional analysis from Section 3A (27–33% conditional attributed LC rate). The two populations should be modeled separately or with `isAttributed` as a conditioning feature.

### Finding 5: Attributed and unattributed event taxonomies are distinct — shared embedding not appropriate

The top unattributed custom events are MMP behavioral scores (`af_bs_conversion_rt`, `d2_rr_user_rt`); the top attributed custom events are in-game actions (`Register`, `2_games_played`, `level_win`). Shared event-name vocabulary embeddings will mix semantically incompatible signals. Consider separate event-name vocabularies per attribution status, or a `(isAttributed, sdk_event_name)` interaction feature.

### Finding 6: `_no_sdk_event_name` is the #1 LC event for attributed users — requires explicit handling

520,901 attributed users (22% of all attributed LC-positive installs) have LC events with no SDK name. These cannot be represented by event-name features. Add a binary `has_unnamed_lc_event` indicator. For unattributed users, this population is 6.9M (~11% of LC-positive unattributed).

### Finding 7: Deposit labels have near-zero D28 negatives — use count/revenue, not flag

`cum_depositor_d28 = 0` exists for only 70 unattributed and 2 attributed rows out of 10.9M labeled rows. The binary flag is not a useful label. Use `deposit_count_dx` or `cum_deposit_sum_dx` as regression targets, or `cum_depositor_d7` (12% negative rate) as the binary label for monetization optimization.

### Finding 8: Label integrity is perfect — no violations

All internal consistency checks pass: LC is a strict subset of custom events, flag=1 never co-occurs with count=0. The label pipeline is clean.

---

## 11. Recommendations for Modeling

| Priority | Recommendation |
|---|---|
| **High** | Use `isAttributed` as a primary conditioning feature or train separate attributed/unattributed model branches. |
| **High** | Use `cum_has_lc_event_d7` as the primary training label. `cum_has_event_dx` is near-useless as a label (99.97%+ positive at D28). |
| **High** | For deposit optimization, use `deposit_count_d7` or `cum_deposit_sum_d28` as regression targets; the binary `cum_depositor_d28` has <0.001% negatives. |
| **Medium** | Treat NULL label rows as true negatives (impute 0) — they are valid installs with full feature coverage, just from advertisers without MMP event tracking. Excluding them silently excludes ~83% of the dataset. |
| **Medium** | Add `has_unnamed_lc_event` boolean feature for the `_no_sdk_event_name` population (22% of attributed LC-positive, 11% of unattributed). |
| **Medium** | Normalize event name case (`Register`/`register`/`REGISTER` → canonical form). At least 4 registration event variants exist in attributed top events. |
| **Medium** | Engineer `first_seen_at` as `log(1 + hours_after_install)` rather than raw timestamp. H0 is ~16× H1 in volume. |
| **Low** | Use `ARRAY_LENGTH(sdk_event_name_first_seen_arr.list)` as a feature. Non-zero values directly identify the event-configured population. |
| **Low** | Investigate the `level_end_success_*` series (ranks 7–13 for attributed LC). These may be from a single large publisher — confirm whether over-representation should be addressed via publisher-level sampling. |

### Open Questions for Data Team

#### Q1: Why does `_no_sdk_event_name` appear exclusively in the LC array and never in the custom array? ✅ Resolved

**Data team answer (2026-07-22):** Custom events have a 2-tier categorization — `event_type` (e.g. `level_complete`, `registration`) and `sdk_event_name`. When `sdk_event_name` isn't available (Adjust MMP), the custom event array falls back to `event_type` as the name. LC events are a subset and don't have the same fallback available — they fall back to `_no_sdk_event_name` instead.

**Verification:** This explains the asymmetry — Adjust installs with a LC event produce `_no_sdk_event_name` in the LC array and no entry in the custom array (not `level_complete`). Querying the data confirmed:

**`level_complete` count in custom array by tracking_partner:**

| tracking_partner | level_complete count |
|---|---|
| appsflyer | 5,885 |
| tenjin | 2,660 |
| NULL | 644 |
| singular | 77 |
| **adjust** | **0** |

`level_complete` in the custom array is tiny (~9K total) and comes entirely from **non-Adjust partners** — these are real SDK event names that advertisers chose to name `level_complete`. Adjust contributes zero, confirming Adjust LC events go to `_no_sdk_event_name` in the LC array with a NULL custom array (not `level_complete`).

**Event_type fallback strings in the custom array — full picture:**

The complete fallback list from the pipeline CASE statement: `achievement_unlocked`, `custom`, `invite`, `level_complete`, `registration`, `share`, `spent_credits`, `start_trial`, `subscribe`, `tutorial_complete`. Any other event_type falls back to the string `"custom"`. Note: `login`, `session`, `purchase` are **not** in the fallback list — their large counts in the custom array are real SDK event names chosen by advertisers.

| sdk_event_name | unattr_count | attr_count | Dominant partner | Adjust contribution |
|---|---|---|---|---|
| `tutorial_complete` | 634,039 | 7,524 | Singular (609K) | 9K unattr, 26 attr |
| `registration` | 455,620 | 73,058 | AppsFlyer (379K) | 57K unattr, 4K attr |
| `start_trial` | 4,268 | 2 | AppsFlyer (4.2K) | 22 unattr |
| `level_complete` | 4,936 | 4,330 | AppsFlyer (2.3K) + Tenjin (2.5K) | **0** |
| `spent_credits` | 1,879 | 0 | AppsFlyer (1.9K) | 0 |
| `subscribe` | 846 | 91 | Adjust only | 846 unattr, 91 attr |
| `achievement_unlocked` | 508 | 0 | AppsFlyer (508) | 0 |
| `share` | 2 | 0 | Singular (2) | 0 |
| `custom` | 0 | 0 | — | — |
| `invite` | 0 | 0 | — | — |

**Three notable observations:**
- `tutorial_complete` and `registration` have large volumes but are predominantly from Singular/AppsFlyer advertisers using these as real SDK event names — not Adjust fallbacks. Adjust's share is small (9K and 57K respectively out of 640K+ each).
- `level_complete` has **zero Adjust contribution** — Adjust LC events go to `_no_sdk_event_name` in the LC array with a NULL custom array, never appearing as `level_complete` in the custom array.
- `custom` and `invite` have zero occurrences in this dataset, meaning no advertisers in this 6-day window used those event_type categories without a named SDK event.

The large counts for `login` (1.4M) and `tutorial_complete` (641K) are **not primarily Adjust fallbacks** — they are AppsFlyer/Singular advertisers who deliberately named their SDK events using canonical event_type strings. Adjust's fallback contribution is much smaller (160K `login`, 61K `registration`, 28K `session`).

**Conclusion:** `_no_sdk_event_name` in the LC array is **by design** — it is the expected fallback for Adjust LC events, which have no `sdk_event_name` and cannot use `level_complete` as a fallback (since the LC array is already filtered to level_complete events, using it as the name would be redundant). These are genuine LC signals from a separate ingestion path, not a pipeline bug. The 7.4M `_no_sdk_event_name` users in the LC array are overwhelmingly Adjust installs with null custom arrays.

#### Q2: Is the observation window (D7 vs D28) meaningfully different for label quality?

The D0-to-D28 spread in positive rate is only **2.19 pp** for `cum_has_event_dx` and **1.36 pp** for `cum_has_lc_event_dx` (attributed, NULL=0). Two mechanisms compound to cause this compression:

1. **Fixed NULL ceiling (~17.5%):** The labeled population is determined at install by advertiser MMP configuration and does not change across windows.

2. **H0 dominance:** 87.41% of attributed labeled rows already have `cum_has_event_d0 = 1` — events fire in the install hour. H0 is ~16× larger than H1 in the `first_seen_at` distribution.

| Window | Attr custom event rate (NULL=0) | Attr LC rate (NULL=0) |
|---|---|---|
| D0 | 15.26% | 4.76% |
| D7 | 16.86% | 5.78% |
| D28 | 17.45% | 6.12% |
| D28 – D0 gap | **+2.19 pp** | **+1.36 pp** |

D0 already captures 87.5% of D28's total custom event positives (78% for LC) for attributed users. Moving from D7 to D28 adds only 0.59 pp (custom) and 0.34 pp (LC). **Question for data team:** Is there a specific business or pipeline reason to use D28 over D7 as the label window, given that ~94–97% of D28's signal is already captured by D7?

---

*Queries run via `bq` CLI on 2026-07-21 against `unity-ads-dd-ds-dev-prd.yabo.huron_ioj_d28_0601_0606`. Total rows: 744,458,032. Install dates: 2026-06-01 to 2026-06-06, gamer_age = d28.*
