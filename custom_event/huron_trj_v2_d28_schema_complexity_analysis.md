# Schema Complexity Analysis: `huron_trj_v2_d28_20260719`

**Table**: `unity-ads-dd-ds-dev-prd.yabo.huron_trj_v2_d28_20260719`
**Analysis date**: 2026-08-21
**Purpose**: Demonstrate downstream usability issues for schema review with manager

---

## Total Column Count

| Level | Count |
|---|---|
| Top-level columns | **1,136** |
| RECORD structs (nested) | 47 |
| Total columns including all nested fields | **8,095** |

---

## Problem 1: `normalized_xxx` Duplication — 19 columns

Every `normalized_xxx` column is a derived copy of a source column with a different encoding (e.g., `CONNECTION_TYPE_CELLULAR` → `cellular`). A downstream user must figure out which version to use and whether they agree — and they sometimes **don't** (see divergence findings below).

| `normalized_xxx` | Source column |
|---|---|
| `normalized_connection_type` | `bid_request_device_connection_type` |
| `normalized_platform` | `platform` |
| `normalized_campaign_type` | `campaign_info_campaign_type` |
| `normalized_os_version` | `bid_request_device_os_version` |
| `normalized_privacy_method` | `bid_request_user_privacy_method` ⚠️ **has divergence** |
| `normalized_battery_status` | `bid_request_device_battery_status` |
| `normalized_network_type` | `bid_request_device_network_type` |
| `normalized_tracking_auth_status` | `bid_request_tracking_att_status` |
| `normalized_ad_unit_type` | `valuation_composer_metadata_ad_unit_type` |
| `normalized_valuation_type` | `valuation_composer_metadata_valuation_type` |
| `normalized_advertising_id` | `bid_request_tracking_advertising_id` |
| `normalized_ip_address` | `bid_request_device_ip_address` |
| `normalized_device_make` | `bid_request_device_make` |
| `normalized_device_type` | source unclear |
| `normalized_device_orientation` | inferred from screen dimensions (not labeled) |
| `normalized_screen_density` | `bid_request_device_screen_android_density` |
| `normalized_screen_size` | `bid_request_device_screen_height` / `_width` |
| `normalized_profile_meta` | RECORD duplicate |
| `normalized_roas_types` | `campaign_info_roas_types` |

### Known divergences between `normalized_xxx` and source

| Column pair | Divergence | Row count |
|---|---|---|
| `normalized_privacy_method` vs `bid_request_user_privacy_method` | `USER_PRIVACY_METHOD_DEFAULT` → `"legitimate_interest"` (expected `"default"`) | 5,242 |
| `normalized_privacy_method` vs `bid_request_user_privacy_method` | `USER_PRIVACY_METHOD_DEVELOPER_CONSENT` → `"default"` (expected `"developer_consent"`) | 7 |
| `normalized_privacy_method` vs `bid_request_user_privacy_method` | `USER_PRIVACY_METHOD_LEGITIMATE_INTEREST` → `"default"` (expected `"legitimate_interest"`) | 2 |
| `normalized_platform` | Only populated for ~8.2M of 185M rows; source `platform` has value for all 185M | 176.8M gap |

Coverage gaps (source non-null but normalized is null) — not divergences per se, but adds confusion:

| Column | Rows with source populated but normalized = NULL |
|---|---|
| `normalized_platform` | 176,768,122 |
| `normalized_battery_status` | 6,740,363 |
| `normalized_network_type` | 6,472,221 |
| `normalized_tracking_auth_status` | 6,238,968 |
| others | ~333–448 each |

---

## Problem 2: Same Concept, Multiple Source Prefixes — 34 redundant columns across 28 groups

Data from different pipeline stages (bid request, gamer token, valuation composer, attribution) is all joined into one flat table, creating multiple copies of the same concept with no clear canonical version:

| Concept | Duplicate columns |
|---|---|
| Legal framework | `bid_request_legal_framework`, `bid_request_user_privacy_legal_framework`, `gamer_token_legal_framework`, `privacyLegalFramework` (**4 copies**) |
| UGID | `bid_request_tracking_ugid`, `gamer_token_ugid` |
| UGID aka | `bid_request_tracking_ugid_aka`, `gamer_token_ugid_aka` |
| Country | `country`, `gamer_token_country` |
| Privacy: permissions_ads | `bid_request_user_privacy_permissions_ads`, `gamer_token_permissions_ads` |
| Privacy: permissions_data_leaves_territory | `bid_request_user_privacy_permissions_data_leaves_territory`, `gamer_token_permissions_data_leaves_territory` |
| Features (ad-request-based) | `agc_ad_request_based_features`, `feature_store_ad_request_based_features` |
| Features (install-based) | `agc_install_based_features`, `feature_store_install_based_features` |
| IDFA gamer id | `gamer_token_idfa_gamer_id`, `idfaGamerId` |
| IDFI gamer id | `gamer_token_idfi_gamer_id`, `idfi_gamer_id` |
| Opt-out enabled | `valuation_composer_metadata_opt_out_enabled`, `optOutEnabled` |
| Opt-out recorded | `valuation_composer_metadata_opt_out_recorded`, `optOutRecorded` |
| Auction (mediation vs unity) | `bid_request_mediation_auction_{id,name,type,timestamp}` vs `bid_request_unity_auction_{id,name,type,timestamp}` (8 cols) |
| + 15 more groups | see cross-prefix analysis |

---

## Problem 3: Mixed Naming Convention — 70 camelCase + 1,061 snake_case

The table mixes two naming conventions with no consistent rule. This makes it impossible to discover related columns by name pattern, and creates hidden semantic twins that a user might not realize refer to the same concept.

**Convention breakdown:**
- `snake_case` columns: **1,061**
- `camelCase` columns: **70**
- other (all lowercase / mixed): 5

**Confirmed semantic twins (same concept, different convention):**

| camelCase | snake_case equivalent |
|---|---|
| `campaignType` | `campaign_info_campaign_type` |
| `connectionType` | `bid_request_device_connection_type` |
| `deviceOsVersion` | `bid_request_device_os_version` |
| `deviceModel` | `bid_request_device_model` |
| `deviceType` | `normalized_device_type` |
| `privacyLegalFramework` | `bid_request_user_privacy_legal_framework` |
| `optOutEnabled` | `valuation_composer_metadata_opt_out_enabled` |
| `optOutRecorded` | `valuation_composer_metadata_opt_out_recorded` |
| `idfaGamerId` | `gamer_token_idfa_gamer_id` |
| `developerId` | `bid_request_app_developer_id` |
| `coppa` | `bid_request_user_privacy_is_coppa_compliant` |
| `limited` | `bid_request_tracking_is_limited` |
| `adFormat` | `normalized_ad_unit_type` |
| `sourceGamerId` | `gamer_token_gamer_id` |

---

## Problem 4: Time-Series Column Explosion — 464 columns

16 metrics are each tracked for 29 days (`_d0` through `_d28`), stored as **464 separate flat columns** rather than arrays or a separate time-series table. This makes the schema unwieldy and any query touching these metrics verbose.

| Family | Columns |
|---|---|
| `cum_deposit_count` | 29 (`cum_deposit_count_d0` … `cum_deposit_count_d28`) |
| `cum_deposit_sum` | 29 |
| `cum_depositor` | 29 |
| `cum_nonzero_depositor` | 29 |
| `cum_nonzero_deposit_count` | 29 |
| `cum_event_count` | 29 |
| `cum_has_event` | 29 |
| `cum_has_lc_event` | 29 |
| `cum_lc_event_count` | 29 |
| `deposit_count` | 29 |
| `deposit_sum` | 29 |
| `event_count` | 29 |
| `has_event` | 29 |
| `has_lc_event` | 29 |
| `lc_event_count` | 29 |
| `nonzero_deposit_count` | 29 |
| **Total** | **464** |

A downstream user wanting to query "which day did the user first make a deposit?" must write a 29-branch `CASE` statement or manually scan 29 columns, instead of a simple `UNNEST` on an array.

---

## Summary for Manager

| Problem category | Redundant / problematic columns | % of 1,136 total |
|---|---|---|
| `normalized_xxx` duplicates | 19 | 1.7% |
| Cross-system prefix duplicates | 34 | 3.0% |
| camelCase / snake_case semantic twins | ~14 confirmed | 1.2% |
| Time-series explosion (16 families × 29 days) | 464 | **40.8%** |
| **Total clearly redundant / problematic** | **~531** | **~46.7%** |

Nearly half the columns are either duplicates, format variants of the same field, or a time-series stored as 464 flat columns.

### Downstream user pain points

1. **No single source of truth**: For key fields like `legal_framework`, there are 4 different column copies with no documentation on which is authoritative.
2. **Silent divergences**: `normalized_xxx` and raw columns sometimes disagree (e.g., 5K rows where `privacy_method` diverges) with no warning to the user.
3. **Inconsistent naming makes discovery impossible**: A user searching for `connection_type` must know to check `connectionType`, `bid_request_device_connection_type`, and `normalized_connection_type` — all present simultaneously.
4. **Time-series as flat columns**: Any analysis across multiple days requires either 29-column scans or complex `UNPIVOT` logic, instead of a simple `UNNEST`.
5. **8,095 total fields when nested RECORDs are expanded**: Tooling like autocomplete or schema browsers become unusable at this scale.
