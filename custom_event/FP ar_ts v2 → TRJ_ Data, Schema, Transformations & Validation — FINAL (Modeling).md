# **Feature-Platform ar\_ts v2 → TRJ — Data Paths, Schema, Struct Layout, Full Transformations & Validation**

*Owner: Mustafa Omran · Updated: 2026-07-15 · Audience: Modeling (DataGen) \+ FP. FINAL canonical version (supersedes all earlier drafts).*

## **0\. TL;DR**

> * **Final TRJ for modeling \= the Parquet export** (full paths in §1). All Huron→legacy naming \+ normalization applied; ready for DataGen.  
> * The BigQuery table is the **same data pre-normalization** (Huron naming) — exploration only.  
> * Parity vs ipj\_d0\_v10: FP idfa **100%**, idfi **100%**, idfm **99.6%**; AGC counters \~99–100% (startCount \~96–98% superset); UUPS advctx 100%, bhv 99.5–99.9%, lig iOS 95.9% (Android 24.2% by design).  
> * §3 gives the exact v2 struct layout (one struct per type, symmetric install ∥ ad-request). §6 is the complete transformation list. Appendices A–C are the full validation detail per subsystem.

## **1\. Data locations (full paths)**

**Final TRJ (Parquet, Snappy) — consume this:**  
Base path:  
gs://data-ads-app-prd/roas/ads.events.operativeecpm.installs.outcomes.profile.join.primary\_conversion\_enriched\_profiles\_v2/  
Layout: {base}/{gamer\_age}/install\_date={YYYY-MM-DD}/part-\*.snappy.parquet, with gamer\_age ∈ {d0, d1, d3, d7, d14, d21, d28}.  
7-day validation sample — exact d28 paths that were produced:  
`gs://data-ads-app-prd/roas/ads.events.operativeecpm.installs.outcomes.profile.join.primary_conversion_enriched_profiles_v2/d28/install_date=2026-06-01/`  
`gs://data-ads-app-prd/roas/ads.events.operativeecpm.installs.outcomes.profile.join.primary_conversion_enriched_profiles_v2/d28/install_date=2026-06-02/`  
`gs://data-ads-app-prd/roas/ads.events.operativeecpm.installs.outcomes.profile.join.primary_conversion_enriched_profiles_v2/d28/install_date=2026-06-03/`  
`gs://data-ads-app-prd/roas/ads.events.operativeecpm.installs.outcomes.profile.join.primary_conversion_enriched_profiles_v2/d28/install_date=2026-06-04/`  
`gs://data-ads-app-prd/roas/ads.events.operativeecpm.installs.outcomes.profile.join.primary_conversion_enriched_profiles_v2/d28/install_date=2026-06-05/`  
`gs://data-ads-app-prd/roas/ads.events.operativeecpm.installs.outcomes.profile.join.primary_conversion_enriched_profiles_v2/d28/install_date=2026-06-06/`  
The other gamer ages (d0/d1/d3/d7/d14/d21) are not populated for the same install\_dates since the installs date we are targeting are older than 28 days.

**Exploration / SQL (same data, Huron naming, pre-normalization):**  
unity-feature-platform-prd.ads\_feature\_platform\_paimon.mmp\_post\_install\_optimization\_training\_v2

## **2\. Schema (1,100 columns)**

| Block | Cols | Contents |
| :---- | :---- | :---- |
| Prejoin features | 634 | Symmetric \*\_install\_based\_\* ∥ \*\_ad\_request\_based\_\* for AGC / Feature-Store / UUPS \+ valuation-context (valctx) |
| IOJ labels | 232 | Install-outcome-join metrics (purchase→deposit; §6B) |
| Custom-event outcomes | 234 | Custom-event outcome labels |

## **3\. v2 struct layout — exact naming (one struct per type; install ∥ ad-request)**

Verified from primary\_conversion\_feature\_enriched\_v2 field paths. Each subsystem has a symmetric pair: an \*\_install\_based\_\* struct (install-time anchor) and an \*\_ad\_request\_based\_\* struct (ar\_ts / valuation-time anchor).

### **3A. Feature Store (FSGW)**

> * feature\_store\_install\_based\_features \= STRUCT\< idfa\_profile, idfi\_profile, idfm\_profile \>  
> * feature\_store\_ad\_request\_based\_features \= STRUCT\< idfa\_profile, idfi\_profile, idfm\_profile \>

Each profile \= \~600 feature columns (446 unified-gamer \+ FL sequence windows).

### **3B. AGC (gamer counters)**

> * agc\_install\_based\_features \= STRUCT\< gamerCounters \>  
> * agc\_ad\_request\_based\_features \= STRUCT\< gamerCounters \>

Each carries the counter set: installedGames, isInstalledGames, clickedGames, qualityClickedGames, creative, interstitialTotal, ironSourceTotal, total, plus per-counter \*Timestamp / \*Scope / \*Channel / \*LatestStart.

### **3C. UUPS**

Split by profile source (adrev / purchase) and anchor (install / ad-request):

> * uups\_install\_based\_features\_adrev \= STRUCT\< bhv\_profiles, lig\_profiles \>  
> * uups\_install\_based\_features\_purchase \= STRUCT\< bhv\_profiles, lig\_profiles \>  
> * uups\_ad\_request\_based\_features\_adrev \= STRUCT\< advctx\_profiles, bhv\_profiles, lig\_profiles \>  
> * uups\_ad\_request\_based\_features\_purchase \= STRUCT\< advctx\_profiles, bhv\_profiles, lig\_profiles \>

**Asymmetry (by design):** advctx\_profiles exists only on the **ad-request** structs (advctx \= the idfi ad-request identity); the install-based structs have only bhv\_profiles \+ lig\_profiles. **Note:** the Parquet export renames lig\_profiles→thumbs\_up\_profiles and sets advctx\_profiles=NULL (see §6C).

### **3D. Other**

> * normalized\_profile\_meta \= ARRAY\<STRING\> (profile presence/normalization metadata).

## **4\. Source & intermediate tables (full names, unity-feature-platform-prd.ads\_feature\_platform\_paimon)**

> * TRJ (final): mmp\_post\_install\_optimization\_training\_v2  
> * Prejoin: primary\_conversion\_feature\_enriched\_v2  
> * AGC: primary\_conversion\_agc\_enriched\_v1, primary\_conversion\_agc\_ar\_ts\_enriched\_v2  
> * UUPS: primary\_conversion\_uups\_enriched\_v1, primary\_conversion\_uups\_ar\_ts\_enriched\_v2  
> * FP (Feature Store): primary\_conversion\_idfa\_fp\_enriched\_v1, primary\_conversion\_idfm\_fp\_enriched\_v1, primary\_conversion\_idfa\_fp\_ar\_ts\_enriched\_v1, primary\_conversion\_idfi\_fp\_ar\_ts\_enriched\_v1, primary\_conversion\_idfm\_fp\_ar\_ts\_enriched\_v1, fsgw\_idfm\_enrich\_prepare\_ar\_ts\_v1  
> * Validation reference: unity-feature-platform-prd.ads\_feature\_platform.ipj\_d0\_v10; bridge unity-data-prd.attribution.primary\_conversion\_valctx\_enriched\_v1

## **5\. Reserved (see §6 for transformations)**

## **6\. FULL transformation list (Huron → legacy / IPJ-v10)**

Applied by the Spark export job ([training\_ready\_join\_export.py](https://github.com/Unity-Technologies/data-ads-app/blob/main/transform/Spark/training_ready_join_export_v1/training_ready_join_export.py) · [README](https://github.com/Unity-Technologies/data-ads-app/blob/main/transform/Spark/training_ready_join_export_v1/README.md)) at Parquet write time. The BQ table does NOT have these.

### **6A. Dimension renames — all 55**

| \# | Source | Target |
| :---- | :---- | :---- |
| 1 | attribution\_partner | tracking\_partner |
| 2 | attribution\_partner\_event\_id | attributionPartnerEventId |
| 3 | attribution\_id | attributionId |
| 4 | attribution\_click\_time | clickAttributionTimestamp |
| 5 | attribution\_impression\_time | attributionImpressionTimestamp |
| 6 | attribution\_touch\_type | attributionTouchType |
| 7 | attribution\_engagement\_type | attributionEngagementType |
| 8 | attribution\_match\_type | attributionMatchType |
| 9 | event\_id | eventId |
| 10 | event\_time | eventTimestamp |
| 11 | install\_time | installTimestamp |
| 12 | ingestion\_time | timestamp |
| 13 | reattribution\_time | reattributionTimestamp |
| 14 | reinstall\_time | reinstallTimestamp |
| 15 | device\_language | deviceLanguage |
| 16 | device\_user\_agent | deviceUserAgent |
| 17 | device\_os\_version | deviceOsVersion |
| 18 | device\_type | deviceType |
| 19 | device\_model | deviceModel |
| 20 | advertiser\_game\_id | targetGameId (cast to string) |
| 21 | advertiser\_bundle\_id | appIdentifier |
| 22 | advertiser\_organization\_id | developerId |
| 23 | advertiser\_store\_category | gameCategory |
| 24 | advertiser\_store\_id | AdvertiserStoreId |
| 25 | advertiser\_store | advertiserStore |
| 26 | advertiser\_sensortower\_genre | advertiserSensortowerGenre |
| 27 | advertiser\_sensortower\_subgenre | advertiserSensortowerSubgenre |
| 28 | advertiser\_store\_subcategory | advertiserStoreSubcategory |
| 29 | campaign\_id | campaignId |
| 30 | campaign\_payment\_model | campaignType |
| 31 | campaign\_target\_cpe | estimatedRevenuePerInstall |
| 32 | campaign\_target\_cpi | campaignTargetCpi |
| 33 | campaign\_target\_roas | estimatedTargetRoas |
| 34 | source\_gamer\_id | sourceGamerId |
| 35 | idfa\_gamer\_id | idfaGamerId |
| 36 | auction\_id | auctionId |
| 37 | placement\_id | placementId |
| 38 | fill\_id | fillId |
| 39 | valuation\_id | valuationId |
| 40 | is\_attributed | isAttributed |
| 41 | is\_reattributed | isReattributed |
| 42 | is\_reinstall | isReinstall |
| 43 | is\_organic | isOrganic |
| 44 | is\_suppressed | isSuppressed |
| 45 | is\_contributed | isContributed |
| 46 | is\_creative\_testing\_campaign | isCreativeTestingCampaign |
| 47 | privacy\_restricted\_user | privacyRestrictedUser |
| 48 | privacy\_purposes\_ads\_product\_improvement | privacyPurposesAdsProductImprovement |
| 49 | privacy\_purposes\_ads\_contextual | privacyPurposesAdsContextual |
| 50 | privacy\_purposes\_ads\_contextual\_profiling | privacyPurposesAdsContextualProfiling |
| 51 | privacy\_purposes\_ads\_personalized\_profiling | privacyPurposesAdsPersonalizedProfiling |
| 52 | privacy\_purposes\_ads\_personalized | privacyPurposesAdsPersonalized |
| 53 | privacy\_purposes\_ads\_measure\_performance | privacyPurposesAdsMeasurePerformance |
| 54 | privacy\_purposes\_ads\_aggregate\_reporting | privacyPurposesAdsAggregateReporting |
| 55 | privacy\_legal\_framework | privacyLegalFramework |

### **6B. Metric renames — all 232 (8 patterns × d0…d28)**

| \# | Source pattern | Target pattern | Cols |
| :---- | :---- | :---- | :---- |
| 1 | cum\_purchaser\_d{0..28} | cum\_depositor\_d{0..28} | 29 |
| 2 | cum\_nonzero\_purchaser\_d{0..28} | cum\_nonzero\_depositor\_d{0..28} | 29 |
| 3 | purchase\_count\_d{0..28} | deposit\_count\_d{0..28} | 29 |
| 4 | cum\_purchase\_count\_d{0..28} | cum\_deposit\_count\_d{0..28} | 29 |
| 5 | nonzero\_purchase\_count\_d{0..28} | nonzero\_deposit\_count\_d{0..28} | 29 |
| 6 | cum\_nonzero\_purchase\_count\_d{0..28} | cum\_nonzero\_deposit\_count\_d{0..28} | 29 |
| 7 | purchase\_sum\_d{0..28} | deposit\_sum\_d{0..28} | 29 |
| 8 | cum\_purchase\_revenue\_d{0..28} | cum\_deposit\_sum\_d{0..28} | 29 |

### **6C. UUPS struct normalization**

> * Unwrap key\_value→MAP; unwrap list→array.  
> * **Rename lig\_profiles→thumbs\_up\_profiles** (applies to the adrev and purchase structs).  
> * Set advctx\_profiles \= NULL, typed like bhv\_profiles.  
> * Post-export UUPS struct: { bhv\_profiles, advctx\_profiles (NULL), thumbs\_up\_profiles }.

### **6D. Preserved / dropped / added**

> * **Preserved:** feature\_store (idfa/idfi/idfm profiles) and gamerCounters as-is; all other columns pass through.  
> * **Dropped:** partition\_date, process\_date.  
> * **Retained:** unity\_gamer\_id, idfi\_gamer\_id, list\_of\_idfi\_gamer\_ids.  
> * **Added for partitioning:** gamer\_age (e.g. "d7"), install\_date (YYYY-MM-DD), process\_gamer\_age (int).  
> * **Layout:** legacy dN/install\_date=YYYY-MM-DD/.

**gamer\_id\_scope:** legacy LC value idfi / idfa / unspecified \= request identity scope (from AGC/UUPS gamerIdScope). Additional presence/naming normalization is captured in the uv\_feature\_presence mapping shared in-channel.

## **7\. The small % difference (LIG handling) — explained, expected**

> 1. **Target-idfi fold on no-LIG installs (\~83% of the idfm mismatch):** ar\_ts folds the target idfi into idfm\_profile via [MERGE\_IDFI\_GAMER\_IDS](https://github.com/Unity-Technologies/data-flair-feature-platform/blob/4e4de121501ec024202effb27734509ef0377aff/docs/feature-enrichment/merge-idfi-gamer-ids-udf.md); ipj\_d0\_v10 leaves it empty. Data identical in idfi\_profile both sides. Matches AVC serving ([gamer\_token.go](https://github.com/Unity-Technologies/ads-valuation-composer/blob/dbd2932c083bd62f0b11ef0037bb67241a10cdde/internal/gamertoken/gamer_token.go)), which includes the target identity in its single feature-store call.  
> 2. **Very large LIGs (\>100 members, \~10%):** slightly different merged member subset (feature availability / member ordering); grows with window length. No pipeline caps at 100; LIG bounded \~150 upstream at token creation; AVC \+ offline forward it uncapped ([FSGW merge processor](https://github.com/Unity-Technologies/data-flair-feature-platform/blob/4e4de121501ec024202effb27734509ef0377aff/feature-enrichment/src/main/java/com/unity3d/ads/operator/output/operator/processor/featurestoregatewayenrichment/FeatureStoreGatewayMergeProfileEnrichmentProcessor.java)).

Treat as a known, small, explained LIG-handling residual; value parity where both sides carry the gamer ≈ 99.8%.

## **8\. Source links (GitHub — full URLs)**

> * ar\_ts v2 pipeline PR: https://github.com/Unity-Technologies/data-ads-app/pull/3271  
> * FP all-profiles validation PR: https://github.com/Unity-Technologies/mlp-huron-validation-utils/pull/43  
> * FP notebook (clean): https://github.com/Unity-Technologies/mlp-huron-validation-utils/blob/arts-all-profiles-fp-validation/notebooks/clean/enrichment/feature\_platform/ar\_ts/ar\_ts\_all\_profiles\_vs\_ipj\_validation.ipynb  
> * FP notebook (executed): https://github.com/Unity-Technologies/mlp-huron-validation-utils/blob/arts-all-profiles-fp-validation/notebooks/runs/ar\_ts\_all\_profiles\_vs\_ipj\_validation\_2026-07-15\_102658\_attributed\_executed.ipynb  
> * UUPS notebook: https://github.com/Unity-Technologies/mlp-huron-validation-utils/blob/0106a56fc61412287888d1b948e7d67f5966ebba/notebooks/clean/enrichment/feature\_platform/ar\_ts/ar\_ts\_uups\_vs\_ipj\_validation.ipynb  
> * AGC notebook: https://github.com/Unity-Technologies/data-ads-app/blob/agc-vs-ipj-validation-notebook/docs/agc\_vs\_ipj\_step\_by\_step\_validation.ipynb  
> * Export job: https://github.com/Unity-Technologies/data-ads-app/blob/main/transform/Spark/training\_ready\_join\_export\_v1/training\_ready\_join\_export.py  
> * Export README: https://github.com/Unity-Technologies/data-ads-app/blob/main/transform/Spark/training\_ready\_join\_export\_v1/README.md  
> * FP prejoin macro: https://github.com/Unity-Technologies/data-ads-app/blob/main/transform/dbt/data\_feature\_platform/macros/flair\_yaml\_generator/render\_ads\_feature\_platform\_install\_feature\_enrichment\_v1\_prejoin.sql  
> * MERGE\_IDFI\_GAMER\_IDS UDF doc: https://github.com/Unity-Technologies/data-flair-feature-platform/blob/4e4de121501ec024202effb27734509ef0377aff/docs/feature-enrichment/merge-idfi-gamer-ids-udf.md  
> * FSGW merge processor: https://github.com/Unity-Technologies/data-flair-feature-platform/blob/4e4de121501ec024202effb27734509ef0377aff/feature-enrichment/src/main/java/com/unity3d/ads/operator/output/operator/processor/featurestoregatewayenrichment/FeatureStoreGatewayMergeProfileEnrichmentProcessor.java  
> * AVC gamer\_token: https://github.com/Unity-Technologies/ads-valuation-composer/blob/dbd2932c083bd62f0b11ef0037bb67241a10cdde/internal/gamertoken/gamer\_token.go

# **Appendix A — Feature Store (FP) validation: idfa / idfi / idfm**

Notebook: [ar\_ts\_all\_profiles\_vs\_ipj\_validation.ipynb](https://github.com/Unity-Technologies/mlp-huron-validation-utils/blob/arts-all-profiles-fp-validation/notebooks/clean/enrichment/feature_platform/ar_ts/ar_ts_all_profiles_vs_ipj_validation.ipynb) (PR \#43). Install date 2026-06-05, attributed installs.

### **Method**

> * **ar\_ts source:** primary\_conversion\_feature\_enriched\_v2.feature\_store\_ad\_request\_based\_features.{idfa,idfi,idfm}\_profile.  
> * **Reference:** ipj\_d0\_v10.feature\_store.{idfa,idfi,idfm}\_profile, joined directly on valuation\_id (v2 carries valuation\_id; v10 keyed on valuationId, deduped by earliest installTimestamp).  
> * **Comparison:** per-field over the 234 common numeric fields per identity; FLOAT rounded to 2 dp, INT exact, **NULL≡0**. Scope is\_attributed \= TRUE (no-op — ad-request profiles exist only for attributed installs).

### **§1 — Coverage & overlap (population \= headline feature non-null, both sides)**

| Identity | ar\_ts populated | v10 populated | coverage vs v10 |
| :---- | :---- | :---- | :---- |
| idfa | 3,745,913 | 3,810,886 | \-1.70% |
| idfi | 1,443,086 | 1,447,999 | \-0.34% |
| idfm | 895,364 | 861,299 | \+3.96% |

### **§2 — Per-field value match (234 numeric fields)**

| Identity | Headline match (revenue\_sum\_last\_7\_days) | Median (234) | Fields ≥99% | Fields \<90% |
| :---- | :---- | :---- | :---- | :---- |
| idfa | 100.00% | 100.0% | 234/234 | 0 |
| idfi | 100.00% | 100.0% | 234/234 | 0 |
| idfm | 99.60% | 99.5% | 134/234 | 0 |

### **§3 — idfm conditioned**

> * When a real cross-game LIG exists (gamer\_token\_lig non-empty, n=1,167,457): headline **99.75%**, median **99.95%**, 212/234 fields ≥99%.  
> * When v10 has the value populated: idfm headline **99.64%**, median **99.80%**.  
> * idfm parity by LIG size: 1–100 members \= **100.0%** on every window; only 101–150 diverges (7d 98.6% / 180d 86.8%). No LIG \>150 (bounded upstream).

### **§4 — Mismatch decomposition (idfm, revenue\_sum\_last\_7\_days; 29,337 mismatches of 1,296,707)**

> * ar\_ts\>0 & v10=0 (target-idfi fold on no-LIG installs): **26,430 (90.1%)**. Same value present in v10 idfi\_profile; \~83% have lig NULL.  
> * both\>0 but differ (read-window / large-LIG member selection): **2,848 (9.7%)**.  
> * ar\_ts=0 & v10\>0: 59 (0.2%).

### **§5 — Member counts (pre- vs post-feature-join)**

> * ar\_ts pre-merge fsgw\_idfm\_enrich\_prepare\_ar\_ts\_v1.features\_array: max 149, p99 114 (avg \~10 members dropped when a member has no offline feature row).  
> * SPJ pre-join raw LIG (enrich\_start\_events\_with\_lig\_v3): max 151, p99 151\. SPJ post-join (start\_all\_profile\_joined\_v3): max 151, p99 100 — i.e. both offline pipelines drop featureless members at the join. No 100 cap anywhere in code (AVC/SPJ/ar\_ts/FSGW all confirmed uncapped; LIG bounded \~150 at token creation).

# **Appendix B — UUPS validation (adrev \+ purchase; bhv / advctx / lig)**

Notebook: [ar\_ts\_uups\_vs\_ipj\_validation.ipynb](https://github.com/Unity-Technologies/mlp-huron-validation-utils/blob/0106a56fc61412287888d1b948e7d67f5966ebba/notebooks/clean/enrichment/feature_platform/ar_ts/ar_ts_uups_vs_ipj_validation.ipynb). Value-level parity vs ipj\_d0\_v10.

### **Method**

> * Per-profile, per-platform (android \+ iOS) match; iOS LIG split ≤100 vs \>100 gamer-ids (IPJ’s 100-input cap); LIG value-match decomposed by aggregation window × profile source (uups\_adrev / uups\_purchase) × event-type key (kv.key); store-set parity per profile; COPPA gate parity.

### **Findings**

> * **advctx\_profiles: 100%.**  
> * **bhv\_profiles:** android **99.5%**, iOS **99.9%** (at parity).  
> * **lig\_profiles:** android **24.2%**, iOS **84.9%** — the only material residual.  
> * **Android lig 24.2% is by design:** Android uses slot/placement-level LIG (not gamer\_token\_lig), so it shares no LIG stores with IPJ.  
> * **iOS lig residual:** on shared LIG stores, sum\* and count\* match at identical rates per window (rules out float-order); degrades monotonically with window length (more of each linked gamer’s history accumulates). Traced to the UUPS-v5 install-anchored LIG window (±1-day step) \+ IPJ’s 100-input cap on the largest LIGs.  
> * COPPA gate: LIG stripped both sides; flags agree.

# **Appendix C — AGC validation (gamerCounters)**

Notebook: [agc\_vs\_ipj\_step\_by\_step\_validation.ipynb](https://github.com/Unity-Technologies/data-ads-app/blob/agc-vs-ipj-validation-notebook/docs/agc_vs_ipj_step_by_step_validation.ipynb). Results date 2026-06-07.

### **Method**

> * **Step 1 — match & coverage:** bridge NEW.event\_id → valctx → valuation\_id \== ipj\_d0\_v10.valuationId. Confirm (a) high coverage, (b) 1-to-1 (no valuation carries two different gamerCounters), (c) unmatched explained (new\_only small \= timing/date-edge; old\_only larger \= IPJ broader / non-attributed).  
> * **Step 2 — value compare:** on matched installs, field-by-field counter compare, strict (exact, missing=0), NEW deduped to one vector per install.  
> * **Step 3:** reconcile the startCount superset.

### **Results (2026-06-07)**

> * NEW installs with AGC: **7,273,695**; OLD/production baseline: **7,361,206**; matched 1-to-1 (both multi-vector checks \~0).  
> * Counters (clickCount, viewCount, creative\_\*): **\~99–100%** identical.  
> * startCount: **\~96–98%** — known **superset** effect (NEW counts one more start before the cutoff, never fewer).  
> * AGC cutoff \= MMP adRequestTimestamp (100% aligned, 0s variance); only value divergence is installedGamesChannel default ("" vs IPJ "init").