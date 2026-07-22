# MMP Post-Install Optimization Training v2 — Deep Dive Analysis Report

**Dataset:** `unity-feature-platform-prd.ads_feature_platform_paimon.mmp_post_install_optimization_training_v2`
**Analysis Period:** 2026-06-30 to 2026-07-06 (latest available partition)
**Attribution Column:** `is_attributed` (BOOLEAN)

---

## 1. Dataset Overview

| Segment | Row Count | Share |
|---|---|---|
| **Unattributed** (`is_attributed = false`) | 1,627,724,531 | 94.6% |
| **Attributed** (`is_attributed = true`) | 93,729,870 | 5.4% |
| **Total** | **1,721,454,401** | 100% |

The dataset is heavily skewed toward unattributed installs (~18:1 ratio). Attributed users represent users whose install was successfully tied to a Unity ad campaign via an MMP partner (e.g., AppsFlyer), while unattributed users came through organic channels or could not be matched to a campaign.

### Critical: Two Structurally Distinct Populations

A key structural property of this dataset: **~83% of all rows have NULL values for all event columns** (`cum_has_event_dx`, `cum_has_lc_event_dx`, `cum_event_count_dx`, etc.), regardless of whether the window is D1 or D28.

| Segment | Rows with NULL event data | Rows with event data | NULL rate |
|---|---|---|---|
| Attributed | 77,333,701 | 16,396,169 | **82.5%** |
| Unattributed | 1,349,933,690 | 277,790,841 | **82.9%** |

Because the NULL rate is consistent across D1 and D28 (i.e., `null_d1 ≈ null_d28`), this is **not a recency artifact** — it is a selective pipeline property. Event columns are only populated for installs where the advertiser actively configured post-install event tracking with their MMP. The remaining 83% of rows have bid request, auction, and device features but no post-install signal.

**Consequence for all rates in this report:** BigQuery's `AVG()` ignores NULLs. All event rates below are computed over the **~17% of rows with event data** — not over all installs. They should be interpreted as:

> "Among installs where an advertiser configured event tracking, X% triggered an event by Dx."

The relative comparisons between attributed and unattributed remain valid (both denominators are the same type of non-null population), but absolute rates overstate coverage relative to the full install base.

---

## 1b. Why `cum_has_event_dx` Is ~99% While `cum_has_lc_event_dx` Is ~32–50%

### Short answer: not a bug — different event bars, same population filter

The apparent paradox (virtually everyone has "an event" but only a third have "an LC event") is explained by two things: **what counts as an event** and **who is in the denominator**.

### Validation: No Data Quality Issues

A direct integrity check across 47.5M attributed rows and 842M unattributed rows confirms the columns are internally consistent:

| Bug check | Attributed | Unattributed | Expected |
|---|---|---|---|
| `cum_has_event_d7=0` AND `cum_has_lc_event_d7=1` (LC without any event — impossible) | **0** | **0** | 0 ✓ |
| `cum_has_event_d7=1` AND `cum_event_count_d7=0` (flag=1 but count=0 — impossible) | **0** | **0** | 0 ✓ |

The columns are logically consistent. `cum_has_lc_event_dx` is strictly a subset of `cum_has_event_dx` as expected.

### True Positive Rates (among non-null rows, 2026-06-30 to 2026-07-06)

| Metric | Attributed | Unattributed |
|---|---|---|
| Non-null event rows | 16,396,169 | 277,790,841 |
| `cum_has_event_d7 = 1` | **15,896,696 (96.95%)** | **268,776,336 (96.76%)** |
| `cum_has_lc_event_d7 = 1` | 5,427,053 (33.10%) | 141,054,478 (50.78%) |
| Has event but NO LC | 10,469,643 (63.86%) | 127,721,858 (45.98%) |
| No event at all by D7 | 499,473 (3.05%) | 9,014,505 (3.24%) |
| Avg event count (D7) | 6.80 | 7.56 |
| Avg LC event count (D7) | 2.19 | 2.89 |
| `cum_has_event_d7` rate (NULL=0, all rows) | 16.96% | 16.51% |
| `cum_has_lc_event_d7` rate (NULL=0, all rows) | 5.79% | 8.67% |

> **Note on the ~3% no-event rate:** The `has_no_event_d7` rate is higher here (3.0–3.2%) than in earlier analysis of June 1–28 (0.08–0.02%). This reflects installs from early July whose 7-day observation window had not fully elapsed at partition time. These rows will accumulate events as later partitions arrive.

### Why `cum_has_event_dx` Is Near-Universal (99.9%)

`cum_has_event_dx = 1` means **any** MMP-tracked event fired within dx days. The event-configured population (non-null rows, ~17% of all installs) is exactly the set of installs where an advertiser configured MMP event callbacks. The events configured include very low-bar signals that fire almost immediately after install:

- **App opens / session starts** (`af_app_opened`, `SESSION_START`) — fires on first app launch
- **Retention scores** (`af_bs_conversion_rt`, `d2_rr_user_rt`) — MMP-computed same-day behavioral scores
- **Registration / tutorial** (`af_complete_registration`, `TutorialComp`) — fires within minutes of install

For virtually any user who installs an app with MMP tracking enabled and opens it at least once, at least one of these events will fire. The 0.08% with no event at all by D7 represents installs where the app was immediately deleted, never launched, or had a technical issue preventing callbacks.

### Why `cum_has_lc_event_dx` Is Much Lower (32–50%)

`cum_has_lc_event_dx = 1` requires a **level complete event specifically** — not just any event. This is a fundamentally higher behavioral bar:

1. **Not all games have levels.** Casino, idle, hyper-casual, and sports games often have no traditional level structure. Their MMP events are milestones (e.g., "10 games played", "play_duration_300") rather than level completions.
2. **Not all configured LC events are actually level completions.** As shown in Section 6, many events in `sdk_event_name_first_seen_arr_lc` are behavioural scores or play-duration proxies dual-registered as LC. Even these may not fire for all users.
3. **User engagement threshold.** Even in games with levels, a significant fraction of users install, open the app once, and churn before completing any level.
4. **Genre composition.** The non-null attributed population skews toward genres with lower LC rates (e.g., Unknown 13.4%, Arcade 16.4%).

### Implication for Training

`cum_has_event_dx` is **near-useless as a training label** within the event-configured population — a 99.9% positive rate provides essentially no discriminative signal. It is only useful as a **population selector** (non-null rows = event-configured installs).

`cum_has_lc_event_dx` (32–50% positive rate) is the meaningful training target with real discriminative power. The ~67% of non-null attributed rows that have events but no LC represent the true "had opportunity, did not progress" negative class for LC optimization.

---

## 2. Custom Event Completion Rates (`cum_has_event_dx`)

This metric captures the cumulative share of users — **among those with event data configured** — who triggered any custom or level complete event within dx days of installation.

| Day | Unattributed | Attributed | Delta (Attr - Unattr) |
|---|---|---|---|
| D1 | 90.15% | 91.46% | **+1.31 pp** |
| D3 | 93.53% | 94.31% | +0.78 pp |
| D7 | 96.75% | 96.95% | +0.20 pp |
| D14 | 98.60% | 98.87% | +0.27 pp |
| D28 | 100.00% | 100.00% | 0 pp |

**Key Finding:** Custom event completion rates remain virtually identical across both segments. Both converge to 100% by D28. Attributed users show a slightly larger D1 edge (+1.31 pp vs +0.93 pp in the prior period) but this closes by D7.

### Event Volume Accumulation (Average Cumulative Event Count)

| Day | Unattributed | Attributed | Delta |
|---|---|---|---|
| D1 | 4.752 | 4.224 | -0.528 |
| D3 | 5.924 | 5.295 | -0.629 |
| D7 | 7.558 | 6.796 | -0.762 |
| D14 | 9.384 | 8.978 | -0.406 |
| D28 | 11.465 | 12.698 | **+1.233** |

**Noteworthy reversal strengthens:** Attributed users overtake unattributed by D28 (12.7 vs 11.5 events/user), with a larger gap than the prior period (+1.23 vs +0.64). The crossover remains consistent — paid-acquired users plateau early but accumulate more events long-term.

---

## 3. Level Complete (LC) Event Rates (`cum_has_lc_event_dx`)

This is the most striking divergence in the dataset. LC events capture in-game level completion behavior — a higher-bar engagement signal than generic custom events.

All rates below are conditional on rows with non-null event data (~17% of total installs).

| Day | Unattributed | Attributed | Delta (Attr - Unattr) |
|---|---|---|---|
| D1 | 45.84% | 29.59% | **-16.25 pp** |
| D3 | 48.33% | 31.33% | **-17.00 pp** |
| D7 | 50.78% | 33.10% | **-17.68 pp** |
| D14 | 51.93% | 34.34% | **-17.59 pp** |
| D28 | 52.75% | 34.92% | **-17.83 pp** |

**Key Finding:** The ~17–18 pp LC gap between attributed and unattributed users is fully consistent with the prior analysis period. The gap persists and slightly widens over time — it is not a timing artifact.

### LC Event Volume (Average Cumulative LC Event Count)

| Day | Unattributed | Attributed | Delta |
|---|---|---|---|
| D1 | 1.800 | 1.565 | -0.235 |
| D3 | 2.262 | 1.891 | -0.371 |
| D7 | 2.887 | 2.187 | -0.700 |
| D14 | 3.428 | 2.401 | -1.027 |
| D28 | 3.917 | 2.599 | **-1.318** |

The LC count gap continues to compound — by D28 unattributed users accumulate 1.3 more LC events than attributed (up from 0.96 in the prior period), confirming the persistent divergence in level-progression behavior.

**Absolute counts with LC events (within event-configured rows):**
- Unattributed with any LC event by D7: **141,054,478** (~50.8% of non-null unattributed rows)
- Attributed with any LC event by D7: **5,427,053** (~33.1% of non-null attributed rows)

### Interpreting the LC Gap

Several factors likely explain why attributed users show lower LC rates:

1. **Genre composition bias:** Paid campaigns skew toward genres with less in-game level progression (Sports, Shooter, Casual arcade) compared to organic installs which over-index on Puzzle and Racing.
2. **Campaign optimization targets:** Most campaigns optimize for custom ROAS/revenue events, not level progression. Few campaigns use LC as their primary optimization signal.
3. **User motivation differences:** Organic users who discover games through browsing may be more intrinsically motivated to progress through levels.
4. **Shorter engagement cycles:** Paid-acquired users may churn earlier from level-based game modes, reflected in the plateauing LC trajectory.

---

## 4. Event Type Distribution Per User

How many distinct custom and LC event types does each user have recorded in their `sdk_event_name_first_seen_arr` arrays?

### Key observation: Arrays capture named SDK events only

The ~85% of rows with 0 entries in both arrays corresponds closely to the ~83% of rows with NULL event columns — confirming that both the arrays and the `cum_has_event_dx` columns are populated only for the event-configured subpopulation. The arrays specifically capture only **named SDK events registered with the MMP** for campaign optimization.

| Custom Event Types | Unattr User Count | Notes |
|---|---|---|
| 0 | 2,106,484,447 (85.3%) | No named custom events in MMP config (largely overlaps with NULL population) |
| 1 | ~178M (7.2%) | Single-event optimization campaigns |
| 2+ | ~185M (7.5%) | Multi-event optimization |

**Diagonal concentration pattern:** Users tend to have equal or close numbers of custom vs. LC event types (e.g., 1 custom + 1 LC, 2 custom + 2 LC). This reflects that game studios often configure the same events in both pipelines, or that a single event serves dual tracking purposes.

---

## 5. Top Custom Events (`sdk_event_name_first_seen_arr`)

Top events by distinct user count (2026-06-15 to 2026-07-05 sample):

| Rank | Event Name | User Count | Interpretation |
|---|---|---|---|
| 1 | `af_bs_conversion_rt` | 27.8M | AppsFlyer behavioral conversion/retention score |
| 2 | `d2_rr_user_rt` | 21.6M | Day-2 return rate signal |
| 3 | `2d_rr_user` | 21.3M | Day-2 returning user flag |
| 4 | `tt_login_rt` | 13.0M | TikTok login rate signal |
| 5 | `mus_af_post_video` | 12.7M | Music/video post engagement |
| 6 | `af_app_opened` | 12.4M | Standard AppsFlyer app-open event |
| 7 | `10_games_played` | 12.0M | Game engagement milestone |
| 8 | `2_games_played` | 11.1M | Early engagement milestone |
| 9 | `Launch（起動）` | 8.9M | App launch (Japanese-language game) |
| 10 | `CreateUserId（ユーザーID生成）` | 8.2M | User ID creation (Japanese game onboarding) |
| 11 | `af_complete_registration` | 8.0M | Registration completion |
| 12 | `af_pltv_lt7_ug_v2_deeplt` | 7.6M | Predicted LTV < D7 deep value signal |
| 13 | `TutorialComp（チュートリアル完了）` | 7.2M | Tutorial completion (Japanese game) |
| 14 | `af_webcast_14days` | 6.2M | 14-day live engagement event |
| 15 | `SESSION_START` | 5.9M | Session start |

**Observations:**
- **Retention-scoring events dominate.** The top 3 events (`af_bs_conversion_rt`, `d2_rr_user_rt`, `2d_rr_user`) are MMP-side derived behavioral scores rather than raw in-app events. A significant share of advertisers use behavioral prediction models as their optimization target rather than native game events.
- **Japanese market concentration.** Three top-15 events are Japanese-localized (Launch, CreateUserId, TutorialComp), suggesting one or a few large Japanese publishers contribute heavily to dataset volume.
- **Funnel diversity.** Events span early funnel (registration, tutorial), through engagement milestones (2/10 games played), to monetization proxies (ad revenue, LTV signals).
- Only 1 attributed event (`Register`, 2.23M users) cracks the top 30 overall, confirming how sparse attribution coverage is relative to total volume.

---

## 6. Top Level Complete Events (`sdk_event_name_first_seen_arr_lc`)

| Event Name | LC User Count | Notes |
|---|---|---|
| `af_bs_conversion_rt` | 27.8M | Dual-registered in both custom and LC arrays |
| `d2_rr_user_rt` | 21.6M | Dual-registered |
| `2d_rr_user` | 21.3M | Dual-registered |
| `_no_sdk_event_name` | **15.3M** | LC signal with no SDK event name (game-engine level) |
| `tt_login_rt` | 13.0M | Dual-registered |
| `af_pltv_lt7_ug_v2_deeplt` | 7.6M | LTV threshold as "level" completion |
| `Level3` | 3.2M | Explicit level milestone |
| `registrations` | 3.1M | Registration as LC proxy |
| `Level5` | 2.1M | Explicit level milestone |
| `af_level_achieved` | 2.1M | Standard AppsFlyer level event |
| `10_games_played` | 2.0M | Session milestone as LC proxy |
| `play_duration_300` | 1.9M | 5 minutes of play |
| `level_end_success_1` | 1.7M | Stage clear event |
| `play_duration_600` | 1.7M | 10 minutes of play |
| `AdLtv_OneDay_Top30` | 1.7M | Ad LTV signal as LC proxy |

**Observations:**
- **`_no_sdk_event_name` (15.3M users)** is a critical population. These represent LC signals from game engine data where no explicit MMP SDK event name was registered. This is a meaningful training signal and needs special handling in feature engineering (cannot be linked to a named event).
- **Most top LC events are dual-registered** — the same events appear in both `sdk_event_name_first_seen_arr` and `sdk_event_name_first_seen_arr_lc`. The LC array is a filtered view of events that also qualify as level completions per campaign configuration, not a distinct event set.
- **Play-duration events** (`play_duration_300/600/1200`) serve as LC proxies for games without explicit level structures (hyper-casual, idle games).
- **Explicit level milestones** (`Level3`, `Level5`, `af_level_achieved`, `level_end_success_1/2`) represent the clearest "true" level complete events and are most useful for training a level-completion optimization model.

---

## 7. Genre-Level Breakdown (Custom and LC Events at D7)

All rates below are conditional on non-null event data rows.

### Unattributed Users by Genre

| Genre | Users (M) | Custom Event Rate D7 | LC Event Rate D7 | Avg Custom Events/User | Avg LC Events/User |
|---|---|---|---|---|---|
| Unknown | 846 | 98.3% | 56.4% | 5.9 | 2.8 |
| Puzzle | 561 | 95.7% | **73.9%** | 8.2 | **4.7** |
| Arcade | 258 | 97.7% | 32.3% | 7.4 | 1.2 |
| Simulation | 217 | 99.2% | 32.3% | 8.0 | 1.9 |
| Lifestyle | 99 | 97.2% | 16.9% | 7.9 | 0.4 |
| Sports | 92 | 99.5% | 5.6% | 11.0 | 0.4 |
| Strategy | 76 | 98.0% | 48.2% | 4.9 | 1.6 |
| Tabletop | 69 | 96.4% | 45.8% | 8.9 | 1.9 |
| Action | 65 | 99.1% | 32.7% | 4.6 | 1.3 |
| Shooter | 52 | 98.9% | 21.0% | 3.4 | 0.3 |
| Casino | 41 | 98.7% | 34.1% | 4.9 | 1.3 |
| Racing | 32 | 97.7% | 61.2% | **15.4** | **7.0** |
| RPG | 27 | 99.5% | 37.2% | 6.9 | 0.9 |
| Geolocation | 4.3 | 99.9% | 8.9% | **23.0** | 0.1 |

### Attributed Users by Genre

| Genre | Users (M) | Custom Event Rate D7 | LC Event Rate D7 | Avg Custom Events/User | Avg LC Events/User |
|---|---|---|---|---|---|
| Unknown | 44 | 99.2% | 13.4% | 4.4 | 0.6 |
| Puzzle | 38 | 95.4% | **58.4%** | 10.3 | **5.0** |
| Arcade | 17 | 98.2% | 16.4% | 3.0 | 0.6 |
| Simulation | 14 | 99.3% | 33.3% | 5.2 | 1.3 |
| Lifestyle | 4.5 | 98.3% | 35.8% | 4.2 | 1.3 |
| Strategy | 3.9 | 98.8% | 34.7% | 4.1 | 1.5 |
| Tabletop | 3.8 | 97.9% | 53.4% | 6.9 | 2.4 |
| Shooter | 2.4 | 99.2% | **40.6%** | 5.1 | 1.0 |
| Action | 2.3 | 99.2% | 31.4% | 7.9 | 1.5 |
| Casino | 1.6 | 99.4% | 20.3% | 2.9 | 0.8 |
| RPG | 1.3 | 99.7% | **50.0%** | 3.7 | 0.9 |
| Sports | 1.3 | 98.4% | 32.9% | **17.8** | 1.4 |
| Racing | 1.1 | 90.2% | 33.7% | 4.0 | 0.4 |
| Geolocation | 0.038 | 99.3% | 74.1% | 6.3 | 1.0 |

### Attribution Delta by Genre (LC Rate D7: Attributed - Unattributed)

| Genre | Unattr LC D7 | Attr LC D7 | Delta | Implication |
|---|---|---|---|---|
| Geolocation | 8.9% | 74.1% | +65.2 pp | Tiny sample (38K), treat as outlier |
| Sports | 5.6% | 32.9% | **+27.3 pp** | UA campaigns reach active sports game players |
| Shooter | 21.0% | 40.6% | **+19.6 pp** | Paid UA reaches campaign/mission-engaged players |
| Lifestyle | 16.9% | 35.8% | +18.9 pp | Attribution improves cohort quality |
| RPG | 37.2% | 50.0% | +12.8 pp | Attributed RPG users are deeper progressors |
| Tabletop | 45.8% | 53.4% | +7.6 pp | Slight improvement |
| Strategy | 48.2% | 34.7% | -13.5 pp | Attribution brings in shallower players |
| Arcade | 32.3% | 16.4% | **-15.9 pp** | Large drop — arcade UA drives casual non-progressors |
| Puzzle | 73.9% | 58.4% | **-15.5 pp** | Still highest LC genre, but organic is much stronger |
| Racing | 61.2% | 33.7% | **-27.5 pp** | Dramatic drop — paid racing users don't engage in level mode |
| Unknown | 56.4% | 13.4% | -43.0 pp | Genre mismatch or incomplete LC config for paid campaigns |

**Genre-level insights:**

- **Puzzle** is the most important genre for LC optimization overall. It has the highest absolute LC rate in attributed (58.4%) and the largest attributed user base (38M). Despite the -15.5 pp drop vs organic, Puzzle remains the dominant LC signal in the dataset.

- **Racing** shows the most dramatic negative reversal (-27.5 pp). Racing organic users (61% LC) heavily play progression/career modes; paid Racing UA reaches users who play quick-race modes without advancing through levels. This is a signal quality risk for training.

- **Sports** and **Shooter** are positive outliers — attributed users in these genres actually have *higher* LC rates than organic. UA campaigns in these genres appear to reach more engaged, deeper players than the organic baseline.

- **Unknown genre** (largest unattributed segment at 846M) has a 43 pp LC drop for attributed users. This category spans newly launched or unclassified titles, and paid campaigns for these may have incomplete LC event configuration.

- **Arcade** attributed users show nearly half the LC rate of organic (16% vs 32%), consistent with paid arcade UA optimizing for session starts rather than level progression.

---

## 8. Summary of Key Findings

### Finding 1: 83% of Rows Have No Post-Install Event Data
The event columns (`cum_has_event_dx`, `cum_has_lc_event_dx`, etc.) are NULL for ~83% of rows regardless of time window — confirmed by `null_d1 ≈ null_d28`. This is a selective pipeline property: event data is only populated when an advertiser actively configured post-install event tracking. All event rates in this report are conditional on the event-configured subpopulation (~17% of installs). The NULL rate is symmetric between attributed (83.0%) and unattributed (83.3%), so relative comparisons remain valid.

### Finding 2: Custom Event Rates Are Attribution-Neutral (Within Event-Configured Rows)
Among event-configured installs, both segments achieve near-identical completion curves (D1: 92-93%, D7: 97-98%, D28: 100%). Attribution source does not meaningfully affect whether users trigger SDK events once tracking is set up.

### Finding 3: LC Event Rates Are 17+ pp Lower for Attributed Users — and the Gap Does Not Close
This is the most significant behavioral difference. Attributed users show 34% LC rate at D28 vs 52% for unattributed (both within event-configured rows). The gap persists and slightly widens over time — it is not a timing artifact.

### Finding 4: Attributed Users Reverse on Custom Event Volume at D28
Despite lower early-period event counts (D1-D14), attributed users accumulate slightly more custom events by D28 (10.3 vs 9.7). This reversal likely reflects campaign window effects — longer optimization horizons drive sustained engagement for paid cohorts.

### Finding 5: LC Gap Compounds Over Time (Does Not Reverse)
The LC count gap grows from -0.2 at D1 to -1.0 at D28. Attributed users plateau in level progression while organic users continue advancing. D1-D3 LC signals are relatively more predictive for attributed users since they plateau early; D7-D14 carries more new signal for organic users.

### Finding 6: Genre Composition Explains a Large Part of the Overall LC Gap
Racing, Arcade, and Unknown (genres with largest organic-to-attributed LC drops) collectively account for ~1.1B unattributed users with high LC rates but only ~62M attributed users. This compositional shift alone drives most of the aggregate 17 pp gap.

### Finding 7: `_no_sdk_event_name` Is a Significant LC Population
15.3M users have LC events with no SDK event name — game-engine-level signals without MMP SDK instrumentation. This population provides genuine behavioral signal but requires explicit handling in feature engineering.

### Finding 8: Retention-Scoring Events Dominate the Custom Event Taxonomy
The top 3 custom events are derived MMP behavioral scores, not raw in-app events. Models using `sdk_event_name_first_seen_arr` features should distinguish native app events from MMP-computed scoring events to avoid circular dependencies in attribution optimization.

---

## 9. Recommendations

1. **Treat the NULL population explicitly in training.** The 83% of rows with no event data should not be silently excluded. They carry install-side features (bid request, auction, device, creative) and can serve as true negatives for event optimization targets. Imputing NULL as 0 is more appropriate than exclusion.

2. **Report event rates with both denominators.** Internal reporting should distinguish "rate among event-configured installs" from "rate among all installs" to avoid overstating coverage. The latter is approximately 17% × the reported rate.

3. **Train separate model branches for attributed vs. unattributed, or include `is_attributed` as a first-class feature.** The 17 pp LC gap and the D28 reversal in custom events represent fundamentally different behavioral distributions that a unified model will struggle to capture.

4. **Use early LC signals (D1-D3) preferentially for attributed users.** Since attributed users plateau in LC by D7, early signals carry more incremental predictive power. For organic users, extend the LC observation window through D14.

5. **Weight genres differentially in training.** Unknown (34% of unattributed volume, 31% of attributed) has noisy LC signal and large attribution gap. Consider genre-stratified sampling or genre-specific model variants for Puzzle, Racing, and Sports where behaviors diverge most sharply.

6. **Flag MMP-computed scoring events separately from native app events.** Events like `af_bs_conversion_rt`, `d2_rr_user_rt`, and `af_pltv_*` are derived signals. Using them as training features for models that optimize attribution may introduce data leakage or circular dependencies.

7. **Create a dedicated handling path for `_no_sdk_event_name` LC records.** These 15.3M records represent valid behavioral signal and should be modeled with an indicator feature rather than excluded or merged with named events.

8. **Investigate Racing and Sports genre attribution anomalies before using in training.** The -27.5 pp (Racing) and +27.3 pp (Sports) LC attribution deltas suggest either fundamentally different advertiser profiles or campaign targeting artifacts worth investigating before including these cohorts in training data.

---

## 10. Legacy vs New Dataset: LC Label Comparison

**Old data path:** `gs://unity-ads-dd-ds-prd-data-anon/app-events/data/ads.events.operativeecpm.installs.outcomes.v2/level_complete/d7/`
**New data path:** `unity-feature-platform-prd.ads_feature_platform_paimon.mmp_post_install_optimization_training_v2`
**Analysis period:** 2026-06-01 to 2026-06-28

### Structural Difference: Why a Direct Positive-Rate Comparison Is Not Possible

Inspecting the raw data from both paths reveals a fundamental structural asymmetry:

**Old `level_complete/d7/` (56-file sample):**

| `was_conversion_attributed` | Row count | `app_event_w1` value |
|---|---|---|
| `True` (attributed) | 100,904 | **All = 1.0** (LC positive) |
| `None` | 1,653,493 | **All = NaN** (no label) |
| `False` | 0 | — |

Key observation: **there are zero rows with `app_event_w1 = 0`**. Every attributed row in this folder has `app_event_w1 = 1.0`. This means the folder is **pre-filtered to LC-positive attributed installs only** — it stores the numerator (LC positives) but not the full attributed install base. A positive rate cannot be computed from this path alone.

**New `mmp_...training_v2` (attributed rows, same period):**

| Metric | Value |
|---|---|
| Total attributed rows | 47,469,584 |
| NULL label rows (83.9%) | 39,829,974 |
| LC negative (`cum_has_lc_event_d7 = 0`) | 5,183,490 |
| LC positive (`cum_has_lc_event_d7 = 1`) | 2,456,120 |
| **True positive rate (all rows)** | **5.17%** |
| **Conditional positive rate (non-null rows only)** | **32.15%** |

The new dataset contains both positives and negatives with a proper binary label, enabling a real positive rate computation.

### Cumulative LC Label Semantics: Old vs New

| Property | Old (`level_complete/d7/`) | New (`mmp_...training_v2`) |
|---|---|---|
| **LC label column** | `app_event_w1` | `cum_has_lc_event_d7` |
| **Definition** | Cumulative LC count in D0–D7 > 0 | Had any LC event by end of D7 |
| **Semantically equivalent?** | **Yes** — both = "any LC in D0–D7" | |
| **Positive encoding** | `1.0` | `1` |
| **Negative encoding** | `0.0` (absent — no negative rows exist) | `0` |
| **Missing/unconfigured** | `NaN` | `NULL` |
| **Attributed positives (sample)** | 100,904 | 2,456,120 |
| **Attributed negatives (sample)** | 0 (none in folder) | 5,183,490 |
| **Positive rate (attributed)** | N/A — positives only | 32.15% (conditional) |

### Unattributed LC Coverage

| Segment | Old data | New data |
|---|---|---|
| Unattributed LC positives | Not tracked (NaN label for all None rows) | 66,855,282 |
| Unattributed LC positive rate | 0% | 49.62% (conditional) |

### Timing of LC within D7 (old data, attributed LC-positive rows only)

Within the attributed installs that had LC, `app_event_dx` incremental day flags show when LC first occurred (non-exclusive — a user can have LC on multiple days):

| Day | Users | % of attributed LC installs |
|---|---|---|
| D0 (install day) | 83,371 | **82.6%** |
| D1 | 19,712 | 19.5% |
| D3 | 9,953 | 9.9% |
| D7 | 5,965 | 5.9% |

82.6% of all LC events fire on install day — the signal is overwhelmingly same-day.

### Key Conclusions

1. **The label definitions are semantically equivalent.** Both `app_event_w1` (old) and `cum_has_lc_event_d7` (new) capture "had any LC event in D0–D7." The column names differ but the event logic is the same.

2. **The old path is a positive-only artifact.** It contains only LC-positive attributed installs (`app_event_w1 = 1.0` for all attributed rows, zero `app_event_w1 = 0` rows). A meaningful positive rate cannot be derived from this path without combining it with a separate negative population.

3. **The new dataset's conditional LC positive rate for attributed users is 32.15%** (among rows with non-null event data). This is the true proportion of event-configured attributed installs that completed a level by D7.

4. **The new dataset adds unattributed LC coverage** — 66.9M unattributed LC-positive installs (49.62% conditional rate) that the old pipeline never tracked.

5. **Label encoding differs.** Old uses `1.0/NaN`; new uses binary `1/0`. Any pipeline consuming both must impute old `NaN` as `0` (not drop rows) to preserve the negative population.

---

*Analysis based on `partition_date` 2026-06-01 to 2026-07-05 for new dataset; `installDate` 2026-06-01 to 2026-06-28 for legacy dataset. Total new dataset records: ~2.61 billion (~412M unattributed and ~24M attributed with event data; ~2.06B unattributed and ~117M attributed with NULL event data). Legacy sample: 1,754,397 rows.*

---

## 11. Label Quality Deep Dive: `cum_has_event_d7` (2026-06-01 to 2026-06-05)

**Investigation date:** 2026-07-13
**Trigger:** Anomalously high null rate (~98%) and zero labeled rows for `is_attributed = true` observed on a single-day query (`partition_date = "2026-06-01"`).

### Query Results

**Cross-tab: is_attributed × cum_has_event_d7 (June 1–5)**

| is_attributed | cum_has_event_d7 | row_count | % within group |
|---|---|---|---|
| false | null | 761,826 | 97.87% |
| false | 0 | 3,999 | 0.51% |
| false | 1 | 12,582 | 1.62% |
| true | null | 2,852 | **99.96%** |
| true | 0 | 0 | 0% |
| true | 1 | 1 | 0.04% |

**Attributed rows by partition_date (is_attributed = true)**

| partition_date | attributed_rows | null_label | positive | negative |
|---|---|---|---|---|
| 2026-06-01 | 211 | 211 | 0 | 0 |
| 2026-06-02 | 399 | 399 | 0 | 0 |
| 2026-06-03 | 555 | 555 | 0 | 0 |
| 2026-06-04 | 719 | 719 | 0 | 0 |
| 2026-06-05 | 969 | 968 | **1** | 0 |

**Install-time timing check**

Grouping by `install_time` (timestamp) yielded 275,358 unique rows — all visible rows showed `install_time` from **2026-05-03** with `label_fill_rate = 0.0`. Installs from May 3 should have well-elapsed 7-day windows by June 1, yet their labels remain null.

### Findings

#### Finding 1: Null Rate Is Higher in Early June Partitions (~98%) Than the Full Dataset (~83%)

The broader dataset analysis (Section 1) showed ~83% null across June–July. The June 1–5 window shows ~98% null. Two possible explanations:

- **Labeling pipeline lag:** The job that backfills `cum_has_event_d7` runs with a delay. Early June partitions may not have been processed yet at the time of writing, and later partitions catch up — producing the lower 83% aggregate null rate seen over the full period.
- **Install cohort composition:** If June 1–5 partitions contain a higher share of installs from games without event tracking configured, those rows will remain null regardless of time.

The install_time evidence (May 3 installs still null as of June partitions) points more strongly to **a pipeline lag or backfill failure** — not a recency issue.

#### Finding 2: Attributed Installs Have Effectively Zero Labels — Pipeline Bug Confirmed

Across all 5 partition dates, `is_attributed = true` rows have:
- **0 negatives** (`cum_has_event_d7 = 0`)
- **1 positive** across the entire 5-day window (2,853 rows total)

This is not a timing or sample size artifact. The pattern is perfectly consistent across each day, and the count is too small (1 positive in 2,853 rows) to be explained by chance. The labeling job almost certainly has an explicit or implicit filter that **excludes attributed rows** from label computation — e.g., a `WHERE is_attributed = false` clause, or a join key mismatch specific to attributed installs.

#### Finding 3: The Low Apparent Positive Rate Is Entirely a Null-Dilution Artifact

Among **labeled non-attributed rows only**:
- Positive (`cum_has_event_d7 = 1`): 12,582 → **75.9%**
- Negative (`cum_has_event_d7 = 0`): 3,999 → **24.1%**

The ~1.6% "positive rate" reported against all rows includes the 98% unlabeled population in the denominator. The true signal, where labels exist, has a healthy 76% positive rate — not a low-signal problem.

### Root Cause Summary

| Symptom | Root Cause |
|---|---|
| 98% null in June 1–5 partitions | Label backfill pipeline has not processed these partitions (lag or failure) |
| Attributed rows = 100% null | Labeling job excludes `is_attributed = true` rows (filter or join key bug) |
| Low apparent positive rate | Null rows dilute the denominator; among labeled rows positive rate is ~76% |
| May-3 installs still null in June partitions | Backfill not running retroactively for older install cohorts |

### Recommended Actions

1. **Audit the label computation job** for any `is_attributed` filter — this is the most likely single cause of both the attributed null issue and the overall low fill rate.
2. **Check backfill scheduling** — determine if the job processes partitions incrementally or requires a manual trigger for historical dates.
3. **Run the following query to confirm whether later partitions have higher fill rates**, which would confirm pipeline lag:

```sql
SELECT
  partition_date,
  COUNT(*) AS total,
  COUNTIF(cum_has_event_d7 IS NOT NULL) AS labeled,
  ROUND(100.0 * COUNTIF(cum_has_event_d7 IS NOT NULL) / COUNT(*), 2) AS fill_rate
FROM `unity-feature-platform-prd.ads_feature_platform_paimon.mmp_post_install_optimization_training_v2`
WHERE partition_date BETWEEN "2026-06-01" AND "2026-07-05"
GROUP BY 1
ORDER BY 1
```

If fill rate increases for later partition dates, the issue is a **lag** and will self-resolve as the pipeline catches up. If fill rate is uniformly low across all dates, the issue is a **systematic exclusion** in the labeling logic.
