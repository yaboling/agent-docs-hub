## 11. Label Quality Deep Dive: `cum_has_event_d7` (2026-06-01 to 2026-06-05)

**Investigation date:** 2026-07-13
**Trigger:** Anomalously high null rate (~98%) and zero labeled rows for `is_attributed = true` observed on a single-day query (`partition_date = "2026-06-01"`).

### Queries Used

**Query 1 — Cross-tab: is_attributed × cum_has_event_d7**
```sql
SELECT
  is_attributed,
  cum_has_event_d7,
  COUNT(*) AS row_count,
  ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (PARTITION BY is_attributed), 2) AS pct_within_group
FROM `unity-feature-platform-prd.ads_feature_platform_paimon.mmp_post_install_optimization_training_v2`
WHERE partition_date BETWEEN "2026-06-01" AND "2026-06-05"
GROUP BY 1, 2
ORDER BY 1, 2
```

**Query 2 — Label fill rate by install_time**
```sql
SELECT
  install_time,
  COUNT(*) AS total_rows,
  COUNTIF(cum_has_event_d7 IS NOT NULL) AS labeled_rows,
  ROUND(100.0 * COUNTIF(cum_has_event_d7 IS NOT NULL) / COUNT(*), 2) AS label_fill_rate,
  COUNTIF(cum_has_event_d7 = 1) AS positive_count,
  ROUND(100.0 * COUNTIF(cum_has_event_d7 = 1) / NULLIF(COUNTIF(cum_has_event_d7 IS NOT NULL), 0), 2) AS positive_rate_among_labeled
FROM `unity-feature-platform-prd.ads_feature_platform_paimon.mmp_post_install_optimization_training_v2`
WHERE partition_date BETWEEN "2026-06-01" AND "2026-06-05"
GROUP BY 1
ORDER BY 1
```

**Query 3 — Attributed rows breakdown by partition_date**
```sql
SELECT
  partition_date,
  COUNT(*) AS attributed_rows,
  COUNTIF(cum_has_event_d7 IS NULL) AS null_label,
  COUNTIF(cum_has_event_d7 = 1) AS positive,
  COUNTIF(cum_has_event_d7 = 0) AS negative
FROM `unity-feature-platform-prd.ads_feature_platform_paimon.mmp_post_install_optimization_training_v2`
WHERE partition_date BETWEEN "2026-06-01" AND "2026-06-05"
  AND is_attributed = True
GROUP BY 1
ORDER BY 1
```

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
