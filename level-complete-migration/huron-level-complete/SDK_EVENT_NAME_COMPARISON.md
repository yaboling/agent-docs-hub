# SDK Event Name Comparison: Huron vs Legacy

**Date**: 2026-06-03 (updated 2026-06-05 — added campaigns_v3 three-way comparison)
**Author**: Yabo Ling
**Huron table**: `unity-data-prd.attribution_l2.mmp_primary_conversion_custom_outcome_join_v1alpha14_single_table_test`
**Legacy table**: `unity-ads-dd-ds-dev-prd.yabo.ioj_v2_lc_d7_2026_03_11`
**Campaign table**: `unity-data-ads-core-prd.ads_dimension_data.campaigns_v3`

---

## 0. Three-Table Processing Summary

This section provides a side-by-side comparison of how each table handles `sdk_event_name` — the most critical thing to understand before joining them.

| Property | Huron (`sdk_event_name_first_seen_arr_lc`) | Legacy IOJ (`sdk_event_name_array`) | campaigns_v3 (`sdk_event_names`) |
|---|---|---|---|
| **Role** | Observed MMP events post-install (label source) | Observed MMP events post-install (label source) | Targeted events set by advertiser (join key) |
| **Casing** | **Original MMP casing** — no LOWER() applied | **LOWERCASED** — IOJ ETL applies `LOWER()` to all event names | **Original advertiser input** — no LOWER() applied |
| **Trimming** | Unknown — not documented; assume no trim | Unknown — not documented | Unknown — not documented |
| **Field type** | `REPEATED RECORD {sdk_event_name STRING, first_seen_at TIMESTAMP}` | `STRUCT<list ARRAY<STRUCT<element STRING>>>` (Parquet) | `ARRAY<STRING>` |
| **Unnest syntax** | `UNNEST(sdk_event_name_first_seen_arr_lc) AS lc → lc.sdk_event_name` | `CROSS JOIN UNNEST(sdk_event_name_array.list) AS item → item.element` | Direct array field |
| **Scope** | LC-classified events only (`_lc` suffix = Huron's LC taxonomy) | All targeted LC events for install | All `LEVEL_COMPLETE` campaign targets (with `archived_at IS NULL`) |
| **Placeholder** | `_no_sdk_event_name` | `_no_sdk_event_name` | No placeholder — empty array means 0-event campaign (→ wildcard `"*"`) |
| **Timestamp** | `first_seen_at` per event | None | None |
| **Multi-event handling** | Array — all LC events fired | Array — all targeted events | Array — but pipeline collapses `size > 1` OR `size == 0` to wildcard `"*"` |

### Concrete Examples: Same Game Across Three Tables

These examples use confirmed event names from §4 (Huron vs Legacy casing audit) and the DESIGN_DOC prediction inflation analysis. They illustrate what you would see for the same `(game_id, sdk_event_name)` pair across all three systems.

**Scenario A — Mixed-case event (JOIN BREAKS without normalization)**

Assume game `500029823` has a campaign targeting `1stChatConnected`:

| Table | Field | Raw value stored | After LOWER() |
|---|---|---|---|
| `campaigns_v3` | `sdk_event_names` | `["1stChatConnected"]` | `["1stchatconnected"]` |
| Legacy IOJ | `sdk_event_name_array` | `["1stchatconnected"]` | `["1stchatconnected"]` ← already lowercased |
| Huron | `sdk_event_name_first_seen_arr_lc` | `{sdk_event_name: "1stChatConnected", first_seen_at: ...}` | `"1stchatconnected"` |

**Result of `array_contains(ioj_array, campaigns_v3_event)` without normalization**: `array_contains(["1stchatconnected"], "1stChatConnected")` → **FALSE** → label silently set to 0 even though the event fired.

---

**Scenario B — Already-lowercase event (JOIN works fine without normalization)**

Assume game `500180883` has a campaign targeting `af_level_achieved`:

| Table | Field | Raw value stored | After LOWER() |
|---|---|---|---|
| `campaigns_v3` | `sdk_event_names` | `["af_level_achieved"]` | `["af_level_achieved"]` |
| Legacy IOJ | `sdk_event_name_array` | `["af_level_achieved"]` | `["af_level_achieved"]` |
| Huron | `sdk_event_name_first_seen_arr_lc` | `{sdk_event_name: "af_level_achieved", first_seen_at: ...}` | `"af_level_achieved"` |

**Result**: All three match case-insensitively AND case-sensitively — no issue. This is why the current pipeline "works" for the ~74% of events that are already all-lowercase.

---

**Scenario C — Multi-event campaign → wildcard (campaigns_v3 specifics matter)**

Assume game `500247161` has one campaign targeting `["level_5", "level_10"]` (two events):

| Table | Field | Raw value stored |
|---|---|---|
| `campaigns_v3` | `sdk_event_names` | `["level_5", "level_10"]` |
| Datagen (after Stage 2 collapse) | `sdk_event_targeted` | `"*"` (because `size > 1`) |
| Legacy IOJ | `sdk_event_name_array` | `["level_5", "level_10"]` (both stored) |
| Huron | `sdk_event_name_first_seen_arr_lc` | `{sdk_event_name: "level_5", ...}, {sdk_event_name: "level_10", ...}` (both stored separately) |

**Result**: The datagen wildcard collapse loses the distinction between `level_5` and `level_10` — the model trains as if any LC event counts for this game. The Huron and Legacy tables preserve both events individually, so a per-event label is constructable from those tables directly.

---

**Scenario D — Mixed-case campaign event (two campaigns, different advertisers)**

From DESIGN_DOC.md A.3 (real production data):

| Campaign ID | `campaigns_v3.sdk_event_names` | What appears as `prob_sdk_event_name` in training |
|---|---|---|
| `6825d515...` | `["eventW"]` | `"eventW"` |
| `685e7277...` | `["eventw"]` | `"eventw"` |

These are two different advertisers using the same base event name with different casing. The model treats them as **two different embedding lookup keys**: `{game_id}_eventW` vs `{game_id}_eventw`. Without LOWER() normalization, if a user fires `eventW` in Huron but the campaign targets `eventw`, the label join misses. And in the IOJ (which stores `eventw` after LOWER()), the `array_contains` against campaigns_v3 `"eventW"` would also fail.

---

### Casing Evidence for campaigns_v3

campaigns_v3 is **not documented** as applying any normalization. The strongest evidence it preserves original case: in the UL model's online prediction logs (DESIGN_DOC.md A.3), `eventW` (campaign `6825d515...`) and `eventw` (campaign `685e7277...`) appear as **two distinct SDK event strings** for two different campaigns. These strings ultimately derive from `campaigns_v3.sdk_event_names`, meaning the pipeline did not lowercase them before embedding them as model features.

---

## 1. Summary

SDK event names are present in both Huron and legacy with **89.5% case-insensitive overlap** for legacy events. The primary source of mismatch is **case normalization**: the legacy IOJ pipeline lowercases all event names, while Huron preserves the original MMP (AppsFlyer) casing. After accounting for casing, the residual gap is explained by the different time windows — not by naming convention changes.

**Critical implication for UL training**: If the model is trained on Huron data and compared against campaigns using legacy-style event name matching, a case-sensitive lookup will incorrectly miss ~26% of valid events (679 out of 2,587 legacy events). The training pipeline must **normalize to lowercase** when joining Huron event names with campaign targets, or use case-insensitive matching throughout.

---

## 2. Column Structure

| Property | Legacy (`sdk_event_name_array`) | Huron (`sdk_event_name_first_seen_arr_lc`) | Huron (`sdk_event_name_first_seen_arr`) |
|---|---|---|---|
| BQ type | `STRUCT<list ARRAY<STRUCT<element STRING>>>` (Parquet) | `REPEATED RECORD {sdk_event_name STRING, first_seen_at TIMESTAMP}` | Same |
| Element access | `UNNEST(col.list) AS x → x.element` | `UNNEST(col) AS x → x.sdk_event_name` | Same |
| Content | All targeted LC events for install | LC-specific events only | All custom events |
| Timestamp | None | `first_seen_at` per event | `first_seen_at` per event |
| Scope filter | Pre-filtered to LC-only games | All attributed installs, LC events flagged | All attributed installs, all custom events |
| Placeholder | `_no_sdk_event_name` | `_no_sdk_event_name` | `_no_sdk_event_name` |

**Key structural difference**: Huron adds a `first_seen_at` timestamp for each event, and separates LC-specific events (`_lc` suffix) from all custom events. Legacy stores a single flat array of all targeted event names without timestamps.

---

## 3. Vocabulary Statistics

Analysis window:
- **Huron**: `partition_date` 2026-04-25 → 2026-05-23, `is_attributed = true`
- **Legacy**: Full IOJ table (`ioj_v2_lc_d7_2026_03_11`), install dates ~2026-02-26 → 2026-04-26

| Metric | Legacy | Huron (lc) |
|---|---|---|
| Distinct SDK event names (raw) | 2,587 | 2,788 |
| Distinct SDK event names (lowercased) | 2,587 | 3,034 |
| Distinct games | 983 | N/A (no game_id in table) |
| Date window | ~60 days (Feb–Apr 2026) | ~29 days (Apr–May 2026) |

### Case-Sensitive Overlap

| Category | Count | % of Legacy | % of Huron |
|---|---|---|---|
| In both (exact match) | 1,635 | 63.2% | 58.7% |
| Only in legacy | 952 | 36.8% | — |
| Only in Huron | 1,153 | — | 41.3% |

### Case-Insensitive Overlap (after LOWER())

| Category | Count | % of Legacy | % of Huron |
|---|---|---|---|
| In both (case-insensitive) | 2,314 | **89.5%** | **76.3%** |
| Only in legacy | 273 | 10.5% | — |
| Only in Huron | 720 | — | 23.7% |

**Case-related mismatches resolved by normalization**: 679 events (26.2% of legacy vocab were case-different in Huron)

---

## 4. Root Cause: Legacy Pipeline Lowercases Event Names

The legacy IOJ pipeline applies `LOWER()` to all incoming MMP SDK event names. Huron stores the original string as received from the attribution partner (AppsFlyer, etc.).

### Confirmed Examples

| Lowercase (legacy) | Original case (Huron) | Pattern |
|---|---|---|
| `10000coins` | `10000Coins` | CamelCase suffix |
| `1000coins` | `1000Coins` | CamelCase suffix |
| `1stchatconnected` | `1stChatConnected` | CamelCase words |
| `1stparcelpurchased` | `1stParcelPurchased` | CamelCase words |
| `2nd day login` | `2nd Day Login` | Title case |
| `2ndparcelpurchased` | `2ndParcelPurchased` | CamelCase words |
| `30_puzzle_complete` | `30_Puzzle_Complete` | Title-snake hybrid |
| `30interstitialads` | `30InterstitialAds` | CamelCase |
| `30rewardedads` | `30RewardedAds` | CamelCase |
| `1d3rv` | `1D3RV` | All uppercase |

**Not all events are affected** — many event names use only lowercase in both systems (e.g., `af_level_achieved`, `level_end_success_10`, `game_loop_15_day3`). The casing difference appears for ~26% of the vocabulary.

---

## 5. Residual Mismatches (Case-Insensitive)

### 5.1 Events in Legacy Only (273 events, case-insensitive)

These are events present in legacy (Feb–Apr 2026) but absent from Huron (Apr–May 2026). Primary explanations:

1. **Campaign seasonality**: Games with LC campaigns active in Feb–Apr 2026 that have since ended or paused
2. **Smaller legacy window for these games**: These events may reappear in Huron with more data

Sample:

| Event Name | Likely Explanation |
|---|---|
| `100chats`, `20chats`, `40chats`, `50chats` | Chat app engagement events — game may have no active campaigns in Apr–May 2026 |
| `achieved_level_10`, `achieved_level_5`, `achieved_level_8` | Level achievement events — game-specific, possibly churned campaigns |
| `ad_revenue045`, `ad_revenue06`, `ad_show_20` | Ad engagement milestones — campaign may have ended |
| `af_arena_unlocked_3`, `af_complete_level_40` | AppsFlyer standard events at specific thresholds — possibly inactive campaigns |
| `10pic_end`, `15pic_end` | Photo/content app events — niche game type |

**Assessment**: These are not permanent vocabulary gaps. Most will appear in Huron when historical data coverage expands or if those campaigns resume.

### 5.2 Events in Huron Only (720 events, case-insensitive)

These are events present in Huron (Apr–May 2026) but absent from legacy (Feb–Apr 2026). Primary explanations:

1. **Newly onboarded games**: Huron covers 13,321 target games vs legacy 1,512 — 8.8x more games → many new event names
2. **Newly created campaigns**: Events from campaigns started after the legacy training window
3. **New event instrumentation**: Advertisers adding new SDK event types post-Feb 2026

Sample:

| Event Name | Likely Explanation |
|---|---|
| `2d_rr_user`, `d2_rr_user_rt`, `af_pltv_lt7_ug_v2_deeplt` | Newer AppsFlyer predictive LTV event types |
| `2Kstepsduringfirst2days`, `4Kstepsduringfirst2days` | Fitness app events — new game category |
| `mus_af_post_video` | Music/video app engagement event |
| `af_bs_conversion_rt` | AppsFlyer bidding signal event — newer campaign type |
| `373892`, `373898` | Numeric event names — likely game-internal identifiers |

**Assessment**: These events represent net-new coverage in Huron, not legacy regressions.

---

## 6. Per-Game Comparison

### 6.1 Limitation: No Game ID in Huron Test Table

The Huron table (`mmp_primary_conversion_custom_outcome_join_v1alpha14_single_table_test`) contains only `event_id` (UUID) as an identifier — no `advertiser_game_id`, `bundle_id`, or `store_id` directly. A direct per-game comparison requires joining via a bridge table.

**Bridge table availability**:
- `unity-data-ads-core-prd.mmp_unattributed.mmp_primary_conversion_outcome_join_v1`: last `process_date` = **2026-01-08** — does NOT cover the Huron test table window (Apr–May 2026)
- `unity-data-ads-core-prd.mmp_unattributed.install_outcome_join`: last `process_date` = **2025-05-29** — no overlap
- `unity-data-prd.attribution_l2.debug_d1_custom_processing_5_10`: has `advertiser_game_id` but only **297 rows** (debug snapshot on 2026-05-10) — not statistically representative

**Conclusion**: Per-game event name comparison cannot be done with the current alpha test table. The bridge table must be extended to cover the Huron test table's date range, or the data team should provide a table linking `event_id` → `advertiser_game_id` for Apr–May 2026.

### 6.2 Legacy Per-Game Statistics (from IOJ)

| Metric | Value |
|---|---|
| Games with event name data | 983 |
| Max distinct events per game | 75 (game 500180883) |
| Top-5 games by event diversity | 75, 60, 50, 50, 49 events |
| Typical range | 1–10 events/game |

Most games (>90%) have fewer than 10 distinct LC SDK event names, with a long tail of a few high-diversity games.

### 6.3 Debug Table Sample (n=297, 2026-05-10)

The debug table reveals the MMP event → Unity canonical event mapping:

| advertiser_game_id | attribution_partner_sdk_event_name | event_name (Unity canonical) |
|---|---|---|
| 500029823 | `af_level_achieved` | `level_complete` |
| 500101086 | `ads_impression_custom` | `tutorial_complete` |

**Key observation**: `attribution_partner_sdk_event_name` (stored in Huron) maps to Unity's internal `event_name` classification. The `sdk_event_name` in Huron arrays represents the **MMP-side event name** (from AppsFlyer SDK), not Unity's canonical classification.

---

## 7. Huron `sdk_event_name_first_seen_arr` vs `sdk_event_name_first_seen_arr_lc`

| Property | `sdk_event_name_first_seen_arr` (all) | `sdk_event_name_first_seen_arr_lc` (LC-only) |
|---|---|---|
| Event scope | All custom post-install events | Events classified as "level complete" by Huron |
| Distinct events (3-day sample, attributed) | 3,196 | 2,788 |
| Overlap between two arrays | ~87% of LC events also appear in all-events | — |
| Use for LC model | Not directly — contains non-LC events | Primary array for LC model training |

**Notable**: The `_lc` suffix filter is applied by Huron's classification logic — it is NOT simply a re-labeling of the same events. Huron identifies LC-class events based on Unity's internal event taxonomy. Events in `sdk_event_name_first_seen_arr` but not `sdk_event_name_first_seen_arr_lc` are genuinely non-LC custom events (e.g., tutorial_complete, login milestones).

---

## 8. Three-Way Join Risk Analysis

### 8.0 Pairwise Casing Compatibility

| Join | Left | Right | Casing compatible? | Risk |
|---|---|---|---|---|
| campaigns_v3 → Huron | original case | original case | **Yes** (both original MMP) | Low — same source string if advertiser copied from MMP correctly |
| campaigns_v3 → LC source data (current datagen) | original case (raw) | lowercased (raw) | **Yes — fixed in code** | `unified_cpe_datagen.py` lowercases campaigns_v3 events at Stage 2 AND lowercases the source array at Stage 3 before `array_contains` |
| Huron → Legacy IOJ | original case | lowercased | **No** | HIGH — ~26% of events fail (already documented in §3–4) |

### 8.1 Current UL Pipeline Behavior (campaigns_v3 → LC source data) — ALREADY CORRECT

**The current production code (`unified_cpe_datagen.py`) already applies `LOWER()` on both sides of the join.** No fix is needed for the current `campaigns_v3` → LC data pipeline.

**Stage 2** (line 653 in `unified_cpe_datagen.py`) — campaigns_v3 event names are lowercased:
```python
F.expr("transform(sdk_event_name_set, e -> lower(e))")
```

**Stage 3** (line 679–681) — the LC source `sdk_event_name_array` is also lowercased before `array_contains`:
```python
df = df.withColumn(
    "sdk_event_name_array",
    F.expr("transform(sdk_event_name_array, e -> lower(e))"),
)
```

The `array_contains(sdk_event_name_array, sdk_event)` comparison at Stage 3 is therefore **case-safe**: both sides are lowercase before the check. Events like `1stChatConnected` from campaigns_v3 are lowercased to `1stchatconnected` before matching against the `sdk_event_name_array` which is also lowercased.

**Additional correction**: the old `SDK_EVENT_NAME_MIGRATION.md` documented that multi-event campaigns (size > 1) collapse to wildcard `"*"`. The current code does NOT do this — it explodes each event as a separate entry (Path B):

| Campaign size | Old documented behavior | Actual current behavior |
|---|---|---|
| 0 events | `"*"` | `"*"` |
| 1 event | event name | event name |
| >1 events | `"*"` (collapse) | each event becomes a separate array entry (explode) |

**The casing risk remains for the Huron migration** (see §8.2 below), since Huron stores original-case events and the Huron pipeline is separate from `unified_cpe_datagen.py`.

### 8.2 Proposed Join Strategy for Huron-Based Training

When joining Huron events (original case) against campaigns_v3 targets (original case), normalization strategy:

**Option A — Normalize everything to lowercase at join time** (recommended):

```sql
-- Step 1: Build campaign target vocab (lowercase)
SELECT
  CAST(game_id AS STRING) AS target_game_id,
  campaignset_id,
  ARRAY(SELECT LOWER(e) FROM UNNEST(sdk_event_names) AS e) AS sdk_event_name_set_lc
FROM `unity-data-ads-core-prd.ads_dimension_data.campaigns_v3`
WHERE app_event_conversion_type = 'LEVEL_COMPLETE'
  AND archived_at IS NULL

-- Step 2: Join Huron events (lowercased at join time)
SELECT
  h.*,
  LOWER(lc.sdk_event_name) AS sdk_event_name_lc,
  lc.first_seen_at
FROM huron_table h,
  UNNEST(sdk_event_name_first_seen_arr_lc) AS lc
-- Then: LOWER(lc.sdk_event_name) IN UNNEST(sdk_event_name_set_lc) for label
```

**Option B — Normalize everything to lowercase at source** (alternative):

Apply `LOWER()` in the datagen BQ query on both the campaigns_v3 `sdk_event_names` array and the Huron `sdk_event_name` field before any join. This makes the normalization explicit and permanent in the parquet output.

**Option C — Use original case throughout** (not recommended):

Requires that advertiser inputs in campaigns_v3 exactly match the MMP-reported strings in Huron. In practice there will be mismatches (typos, different MMP SDKs, advertiser-side vs server-side naming). This is fragile.

### 8.3 Legacy IOJ ↔ campaigns_v3 Recommended Fix

If continuing to use legacy IOJ for training labels and joining against campaigns_v3:

```python
# In datagen Stage 3 (unified_cpe_datagen.py):
# Apply LOWER() to sdk_event_name_set before array_contains
sdk_event_lc = F.lower(F.col("sdk_event"))
sdk_event_array_lc = F.col("sdk_event_name_array")  # already lowercased in IOJ

label_col = F.when(
    (F.array_contains(sdk_event_array_lc, sdk_event_lc) | (sdk_event_lc == "*") | (sdk_event_lc == ""))
    & (F.col("label") == 1),
    1.0
).otherwise(0.0)
```

---

## 9. Implications for UL Model Training (updated)

### 8.1 Case Normalization Required

When joining Huron `sdk_event_name` against campaign target event names:
- Apply `LOWER()` to Huron event names in the training pipeline, OR
- Ensure campaign target lookup also uses original casing (consistent with Huron)

Current UL pipeline stage: `prob_sdk_event_name = f"{target_game_id}_{event_name}"` — if `event_name` from campaigns is lowercase but Huron uses original case, this join will silently drop ~26% of positive labels.

### 8.2 `_no_sdk_event_name` Placeholder

Both systems use `_no_sdk_event_name` as the placeholder when no event was fired. Frequency:
- Huron: 78,837 installs had `_no_sdk_event_name` as LC event (≈52% of attributed installs on 2026-05-20 had zero LC events)
- Legacy: Similar pattern expected

The placeholder must be excluded when computing event-specific positive rates to avoid inflating wildcard base rates (same issue as the archived campaign wildcard bug found in v1/v2).

### 8.3 `first_seen_at` Timestamp

Huron provides `first_seen_at` per event — not available in legacy. This enables:
- Time-to-event features (e.g., "user completed level within X days")
- Ordered event sequences
- More granular label cutoff logic

This is a **net new signal** not exploitable in legacy, worth leveraging in future model versions.

### 8.4 `sdk_event_name_first_seen_arr_lc` as Training Label Source

The `_lc` array is the correct field to use for LC model label construction:
- `cum_has_lc_event_d7 > 0` → binary label (any LC event within 7 days)
- `sdk_event_name_first_seen_arr_lc` → which specific LC events fired (for PSN per-event label)
- Combination: `label = 1 if event_name in sdk_event_name_first_seen_arr_lc.sdk_event_name AND cum_has_lc_event_d7 > 0`

---

## 10. Open Questions

| Question | Priority | Owner |
|---|---|---|
| Does `campaigns_v3.sdk_event_names` apply any `LOWER()` or `TRIM()` normalization internally, or does it store raw advertiser input? | **Critical** | Data/Campaign team |
| ~~Does the current UL datagen pipeline apply `LOWER()` when matching campaigns_v3 event names against LC source data?~~ **RESOLVED** — `unified_cpe_datagen.py` lowercases both campaigns_v3 (Stage 2, line 653) and the source array (Stage 3, line 679). Join is case-safe. | ~~Critical~~ CLOSED | — |
| Does the Huron migration pipeline apply `LOWER()` when matching Huron event names (original case) to campaign targets from campaigns_v3? | Critical | Modeling team |
| Are there leading/trailing spaces in `campaigns_v3.sdk_event_names` entries? (Advertiser UI inputs are prone to whitespace bugs) | High | Data/Campaign team |
| Will the bridge table (`mmp_primary_conversion_outcome_join_v1`) be extended to cover Apr–May 2026? | High | Data/Attribution team |
| Is the `_lc` classification in Huron equivalent to the legacy LC event taxonomy? Are there events legacy considers LC that Huron doesn't, or vice versa? | High | Huron/Attribution team |
| What causes 273 legacy events to be absent from Huron even case-insensitively — are these from churned campaigns or events that Huron classifies differently? | Medium | Attribution team |
| Should `sdk_event_name_first_seen_arr_lc.first_seen_at` be used to construct time-to-event features? | Medium | Modeling team |
| In production serving, how will campaign-targeted event names be matched against Huron-trained model's event vocabulary? | Medium | Serving/Infra team |

---

## 11. Query Reference

### campaigns_v3 — Active LC Campaigns with Normalized Event Names

```sql
-- Raw (original casing, as stored)
SELECT
  CAST(game_id AS STRING) AS target_game_id,
  campaignset_id,
  sdk_event_names AS sdk_event_name_set
FROM `unity-data-ads-core-prd.ads_dimension_data.campaigns_v3`
WHERE app_event_conversion_type = 'LEVEL_COMPLETE'
  AND archived_at IS NULL

-- Normalized (lowercase + trim — recommended for joins)
SELECT
  CAST(game_id AS STRING) AS target_game_id,
  campaignset_id,
  ARRAY(SELECT TRIM(LOWER(e)) FROM UNNEST(sdk_event_names) AS e WHERE e IS NOT NULL) AS sdk_event_name_set_lc
FROM `unity-data-ads-core-prd.ads_dimension_data.campaigns_v3`
WHERE app_event_conversion_type = 'LEVEL_COMPLETE'
  AND archived_at IS NULL

-- Check whether campaigns_v3 has case variation (run to confirm casing assumption)
SELECT
  e AS raw,
  LOWER(e) AS lower,
  e != LOWER(e) AS is_mixed_case,
  COUNT(*) AS campaign_count
FROM `unity-data-ads-core-prd.ads_dimension_data.campaigns_v3`,
  UNNEST(sdk_event_names) AS e
WHERE app_event_conversion_type = 'LEVEL_COMPLETE'
  AND archived_at IS NULL
  AND e IS NOT NULL
GROUP BY 1, 2, 3
HAVING is_mixed_case
ORDER BY campaign_count DESC
LIMIT 50
```

### Correct UNNEST Syntax

```sql
-- Huron: standard BQ REPEATED RECORD
SELECT lc.sdk_event_name, lc.first_seen_at
FROM `unity-data-prd.attribution_l2.mmp_primary_conversion_custom_outcome_join_v1alpha14_single_table_test`,
  UNNEST(sdk_event_name_first_seen_arr_lc) AS lc
WHERE partition_date = "2026-05-20"

-- Legacy IOJ: Parquet STRUCT<list ARRAY<STRUCT<element STRING>>>
SELECT item.element AS sdk_event_name
FROM `unity-ads-dd-ds-dev-prd.yabo.ioj_v2_lc_d7_2026_03_11`
CROSS JOIN UNNEST(sdk_event_name_array.list) AS item
```

### Three-Way Vocabulary Comparison (Huron + Legacy + campaigns_v3)

```sql
WITH huron_vocab AS (
  SELECT DISTINCT LOWER(TRIM(lc.sdk_event_name)) AS event_name_lc
  FROM `unity-data-prd.attribution_l2.mmp_primary_conversion_custom_outcome_join_v1alpha14_single_table_test`,
    UNNEST(sdk_event_name_first_seen_arr_lc) AS lc
  WHERE partition_date BETWEEN "2026-04-25" AND "2026-05-23"
    AND is_attributed = true
    AND lc.sdk_event_name != "_no_sdk_event_name"
),
legacy_vocab AS (
  SELECT DISTINCT LOWER(TRIM(item.element)) AS event_name_lc
  FROM `unity-ads-dd-ds-dev-prd.yabo.ioj_v2_lc_d7_2026_03_11`
  CROSS JOIN UNNEST(sdk_event_name_array.list) AS item
  WHERE item.element != "_no_sdk_event_name"
),
campaign_vocab AS (
  SELECT DISTINCT LOWER(TRIM(e)) AS event_name_lc
  FROM `unity-data-ads-core-prd.ads_dimension_data.campaigns_v3`,
    UNNEST(sdk_event_names) AS e
  WHERE app_event_conversion_type = 'LEVEL_COMPLETE'
    AND archived_at IS NULL
    AND e IS NOT NULL
    AND e != ''
)
SELECT
  COALESCE(h.event_name_lc, l.event_name_lc, c.event_name_lc) AS event_name_lc,
  h.event_name_lc IS NOT NULL AS in_huron,
  l.event_name_lc IS NOT NULL AS in_legacy,
  c.event_name_lc IS NOT NULL AS in_campaigns
FROM huron_vocab h
FULL OUTER JOIN legacy_vocab l ON h.event_name_lc = l.event_name_lc
FULL OUTER JOIN campaign_vocab c ON COALESCE(h.event_name_lc, l.event_name_lc) = c.event_name_lc
ORDER BY in_campaigns DESC, in_huron DESC, in_legacy DESC
```

### Case-Insensitive Vocabulary Comparison

```sql
WITH huron_vocab AS (
  SELECT DISTINCT LOWER(lc.sdk_event_name) AS event_name_lower
  FROM `unity-data-prd.attribution_l2.mmp_primary_conversion_custom_outcome_join_v1alpha14_single_table_test`,
    UNNEST(sdk_event_name_first_seen_arr_lc) AS lc
  WHERE partition_date BETWEEN "2026-04-25" AND "2026-05-23"
    AND is_attributed = true
    AND lc.sdk_event_name != "_no_sdk_event_name"
),
legacy_vocab AS (
  SELECT DISTINCT LOWER(item.element) AS event_name_lower
  FROM `unity-ads-dd-ds-dev-prd.yabo.ioj_v2_lc_d7_2026_03_11`
  CROSS JOIN UNNEST(sdk_event_name_array.list) AS item
  WHERE item.element != "_no_sdk_event_name"
)
SELECT
  (SELECT COUNT(*) FROM huron_vocab) as huron_count,
  (SELECT COUNT(*) FROM legacy_vocab) as legacy_count,
  (SELECT COUNT(*) FROM huron_vocab h JOIN legacy_vocab l ON h.event_name_lower = l.event_name_lower) as overlap
```
