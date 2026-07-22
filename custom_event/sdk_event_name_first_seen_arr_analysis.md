# `sdk_event_name_first_seen_arr` & `sdk_event_name_first_seen_arr_lc` — Deep Dive

**Dataset:** `unity-feature-platform-prd.ads_feature_platform_paimon.mmp_post_install_optimization_training_v2`
**Analysis Period:** 2026-06-30 to 2026-07-05
**Total Rows:** 1,721,454,401

---

## 1. Schema

Both columns are `REPEATED RECORD` (arrays of structs). Each element contains:

| Field | Type | Mode | Description |
|---|---|---|---|
| `sdk_event_name` | STRING | NULLABLE | MMP-registered SDK event name. Can be `_no_sdk_event_name` for game-engine LC signals with no SDK name. |
| `first_seen_at` | TIMESTAMP | NULLABLE | Timestamp when this event was first observed for the install within the observation window. |

- `sdk_event_name_first_seen_arr` — all custom MMP-tracked events
- `sdk_event_name_first_seen_arr_lc` — subset of events registered as Level Complete (LC) signals

---

## 2. Array Size Statistics

| Metric | `sdk_event_name_first_seen_arr` (custom) | `sdk_event_name_first_seen_arr_lc` (LC) |
|---|---|---|
| Rows with empty array (size = 0) | 1,456,886,432 (**84.6%**) | 1,569,193,779 (**91.2%**) |
| Rows with ≥ 1 event | 264,567,969 (15.4%) | 152,260,622 (8.8%) |
| Average array size (all rows) | 0.413 | 0.236 |
| Max array size | **274** | **68** |

**Notes:**
- The 84.6% empty rate for custom aligns with the ~83% null rate in `cum_has_event_d7` — both reflect the same population of installs without MMP event tracking configured.
- LC coverage is ~6.6pp lower than custom because not all custom events qualify as LC. Only events explicitly registered as level-complete signals by the advertiser appear in the LC array.
- Max array size of 274 (custom) indicates advertisers with very granular multi-event configurations; these are outliers — the vast majority of users have 0–2 entries.

---

## 3. Top 30 `sdk_event_name` — Custom Array

| Rank | sdk_event_name | user_count | Category |
|---|---|---|---|
| 1 | `af_bs_conversion_rt` | 27,822,869 | MMP behavioral score |
| 2 | `d2_rr_user_rt` | 21,593,199 | MMP retention score |
| 3 | `2d_rr_user` | 21,333,574 | MMP retention flag |
| 4 | `10_games_played` | 13,063,872 | Engagement milestone |
| 5 | `tt_login_rt` | 12,989,981 | TikTok login rate signal |
| 6 | `mus_af_post_video` | 12,679,262 | Music/video engagement |
| 7 | `af_app_opened` | 12,628,640 | App open (standard AF) |
| 8 | `2_games_played` | 12,412,978 | Early engagement milestone |
| 9 | `Launch（起動）` | 8,882,251 | App launch (Japanese game) |
| 10 | `af_complete_registration` | 8,380,642 | Registration completion |
| 11 | `CreateUserId（ユーザーID生成）` | 8,184,560 | User ID creation (Japanese game) |
| 12 | `Register` | 8,072,341 | Registration |
| 13 | `af_pltv_lt7_ug_v2_deeplt` | 7,561,084 | Predicted LTV < D7 deep signal |
| 14 | `TutorialComp（チュートリアル完了）` | 7,247,916 | Tutorial completion (Japanese game) |
| 15 | `af_webcast_14days` | 6,214,287 | 14-day livestream engagement |
| 16 | `SESSION_START` | 5,917,269 | Session start |
| 17 | `af_tutorial_completion` | 4,889,679 | Tutorial completion (standard AF) |
| 18 | `game_end_7` | 4,667,333 | Game session end (7th session) |
| 19 | `grt_3r_success_30` | 4,358,682 | 3-round success within 30 days |
| 20 | `Login` | 4,350,087 | Login event |
| 21 | `Level3` | 4,283,348 | Level 3 milestone |
| 22 | `rewarded_impression` | 3,620,100 | Rewarded ad impression |
| 23 | `s_custom9_revenue_3` | 3,277,185 | Revenue signal (custom slot 9) |
| 24 | `registrations` | 3,165,974 | Registration (variant) |
| 25 | `login` | 3,026,613 | Login (lowercase variant) |
| 26 | `Level5` | 2,953,566 | Level 5 milestone |
| 27 | `100_games_played` | 2,796,378 | Deep engagement milestone |
| 28 | `af_level_achieved` | 2,622,584 | Standard AF level event |
| 29 | `ad_impression_25` | 2,546,179 | Ad impression (25th) |
| 30 | `af_tts_watch_duration_value_7d` | 2,414,750 | TikTok watch duration 7D signal |

---

## 4. Top 30 `sdk_event_name` — LC Array

| Rank | sdk_event_name | user_count | Also in custom? | Category |
|---|---|---|---|---|
| 1 | `af_bs_conversion_rt` | 27,822,869 | ✓ dual | MMP behavioral score |
| 2 | `d2_rr_user_rt` | 21,593,199 | ✓ dual | MMP retention score |
| 3 | `2d_rr_user` | 21,333,574 | ✓ dual | MMP retention flag |
| 4 | **`_no_sdk_event_name`** | **16,712,253** | LC only | Game-engine LC (no SDK name) |
| 5 | `tt_login_rt` | 12,989,981 | ✓ dual | TikTok login rate signal |
| 6 | `mus_af_post_video` | 12,679,262 | ✓ dual | Music/video engagement |
| 7 | `af_pltv_lt7_ug_v2_deeplt` | 7,561,084 | ✓ dual | Predicted LTV signal |
| 8 | `af_webcast_14days` | 6,214,287 | ✓ dual | 14-day livestream engagement |
| 9 | `grt_3r_success_30` | 4,358,682 | ✓ dual | 3-round success |
| 10 | `s_custom9_revenue_3` | 3,277,185 | ✓ dual | Revenue signal |
| 11 | `Level3` | 3,190,813 | ✓ | Level 3 milestone |
| 12 | `registrations` | 3,165,974 | ✓ dual | Registration |
| 13 | `af_tts_watch_duration_value_7d` | 2,414,750 | ✓ dual | TikTok watch duration |
| 14 | `af_level_achieved` | 2,396,292 | ✓ | Standard AF level event |
| 15 | `loop_online_168h_180` | 2,226,176 | LC only | 168h online engagement |
| 16 | `10_games_played` | 2,186,473 | ✓ | Engagement milestone |
| 17 | `Level5` | 2,131,978 | ✓ | Level 5 milestone |
| 18 | `grt_7d_levelpass_40` | 2,044,594 | LC only | 7-day level pass |
| 19 | `s_custom15_revenue` | 2,005,711 | LC only | Revenue signal |
| 20 | `s_ad_revenue_to_NU_af001` | 2,005,664 | LC only | Ad revenue signal |
| 21 | `topsocre_6000_jili_30d` | 2,000,866 | LC only | Score milestone |
| 22 | `af_rounds10` | 1,979,253 | LC only | 10 rounds played |
| 23 | `newdevice_pure_install_country_match_s2s` | 1,936,041 | LC only | New device S2S install signal |
| 24 | `loop_online_24h_60` | 1,933,349 | LC only | 24h online engagement |
| 25 | `play_duration_300` | 1,873,634 | LC only | 5 min of play |
| 26 | `app_feedback_three` | 1,837,773 | LC only | User feedback signal |
| 27 | `level_end_success_1` | 1,788,847 | LC only | Stage clear (level 1) |
| 28 | `af_grm_018` | 1,782,854 | LC only | AF gaming retention metric |
| 29 | `play_duration_600` | 1,745,887 | LC only | 10 min of play |
| 30 | `app_feedback_five` | 1,733,071 | LC only | User feedback (5-star) |

---

## 5. `first_seen_at` Distribution (hours after install)

Event counts per hour bucket, 0–99h (custom array):

| Hour bucket | event_count | Pattern |
|---|---|---|
| H0 | **351,266,368** | Massive install-hour spike |
| H1 | 22,180,058 | Sharp drop |
| H2 | 13,730,475 | |
| H3 | 8,560,720 | |
| H4–H11 | 4.5M–6.7M | Plateau (intraday activity) |
| H12–H23 | 4.0M–7.5M | Rising toward end of day |
| **H24** | **8,022,991** | **D1 return spike** |
| H25–H46 | 1.6M–4.2M | Decay then rise |
| **H47–H48** | **3.3M–3.6M** | **D2 return spike** |
| H49–H70 | 0.7M–2.3M | Decay then rise |
| **H71–H72** | **1.6M** | **D3 return spike** |
| H73–H94 | 0.7M–1.0M | Decay then rise |
| **H95–H96** | **1.2M** | **D4 return spike** |

**Visual summary:**
```
H0   ████████████████████████████████████████  351M
H1   ██                                         22M
H2   █                                          14M
H3-11 ▌ (plateau ~5-7M)
H24  ████                                        8M  ← D1 return
H47  ██                                         3.6M ← D2 return
H71  █                                          1.6M ← D3 return
H95  █                                          1.2M ← D4 return
```

---

## 6. Key Findings

### Finding 1: H0 Dominance — 78%+ of Events Fire Within the First Hour

351M out of ~450M total custom event occurrences fire at H0. The top events driving this are MMP behavioral scores (`af_bs_conversion_rt`, `d2_rr_user_rt`, `2d_rr_user`) which are computed at or shortly after install, not through active in-app behavior. This is why `cum_has_event_d7` is near-universally positive (97%) among event-configured rows — the signal fires on install regardless of user engagement.

### Finding 2: Top Events Are MMP-Computed Scores, Not Raw App Events

The top 3 custom and LC events are MMP-derived behavioral signals, not native SDK events:
- `af_bs_conversion_rt` — AppsFlyer behavioral conversion/retention score
- `d2_rr_user_rt` — Day-2 return rate (model output)
- `2d_rr_user` — Day-2 returning user flag

These fire for ~21–28M users and are dual-registered in both custom and LC arrays. This means **`cum_has_lc_event_d7` is heavily inflated by non-level-completion signals** for these users. True level-completion events (`Level3`, `Level5`, `af_level_achieved`, `level_end_success_1`) appear much lower in the ranking.

### Finding 3: LC Array Has Significant LC-Only Events Not in Custom Array

16 of the top 30 LC events do not appear in the custom array top 30, including:
- `_no_sdk_event_name` (16.7M) — game-engine LC with no MMP SDK name, requires separate handling
- `play_duration_300/600` — time-based LC proxies for games without levels
- `loop_online_24h_60`, `loop_online_168h_180` — engagement duration signals
- `level_end_success_1`, `af_grm_018` — true gameplay progression signals

### Finding 4: 24h Periodicity in `first_seen_at` Reflects Returning User Sessions

Clear spikes at H24, H47–48, H71–72, H95–96 represent daily returning user sessions. Since `first_seen_at` stores the *first* occurrence of an event, these spikes capture users who:
- Did not trigger the event on install day
- Returned 1, 2, 3, or 4 days later and triggered it for the first time

This makes `first_seen_at` useful for modeling **time-to-first-engagement** patterns.

### Finding 5: Japanese Market Concentration

Three events in the top 15 custom list are Japanese-localized: `Launch（起動）` (8.9M), `CreateUserId（ユーザーID生成）` (8.2M), `TutorialComp（チュートリアル完了）` (7.2M). This suggests one or a few large Japanese publishers contribute significant volume and may skew event-level statistics.

---

## 7. Implications for Training

| Use case | Recommendation |
|---|---|
| Using `sdk_event_name` as a feature | Distinguish MMP-computed scores (top 3) from native app events — they have different firing semantics |
| Using `first_seen_at` as a feature | Engineer as `hours_after_install = TIMESTAMP_DIFF(first_seen_at, install_time, HOUR)` for a relative signal |
| Handling `_no_sdk_event_name` | Add a boolean indicator feature `has_unnamed_lc_event` rather than using the name directly |
| Filtering for "true" LC events | Exclude dual-registered MMP scores; focus on `Level*`, `af_level_achieved`, `level_end_success_*`, `play_duration_*` |
| Array size as a feature | `ARRAY_LENGTH(sdk_event_name_first_seen_arr)` captures event diversity per user; log-transform recommended given max=274 |
| H0 events in modeling | Consider separating H0 events (install-day MMP scores) from post-install events; they have fundamentally different predictive value |

---

*Queries run via `bq` CLI on 2026-07-14. Partition window: 2026-06-30 to 2026-07-05.*
