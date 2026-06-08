# Skill: UV Model Prediction Report

Generate an interactive HTML report of Unity UV model predictions over time, broken down by campaign type (IAP, AdRev, CPE) and `post_install_window`. The report shows prediction trends per model version as interactive Plotly charts, with SQL queries and their raw results embedded at the bottom.

---

## Prerequisites

- BigQuery access to `unity-ai-data-prd.mz_dcpi_raw.mz_dcpi_prediction_v1`
- `bq` CLI authenticated, or results exported as CSV manually
- Python 3 (stdlib only, no extra dependencies)

---

## Step 1: Gather Required Parameters

If the user has not provided the following, ask before proceeding:

| Parameter | Required | Description |
|---|---|---|
| `start_date` | **Yes** | Start of submit_date range, e.g. `2026-05-15` |
| `end_date` | **Yes** | End of submit_date range, e.g. `2026-06-04` |
| `target_game_id` | Optional | Filter to a specific game, e.g. `500265950`. Omit for all games. |
| `campaign_id` | Optional | Filter to a specific campaign. Omit for all campaigns. |

---

## Step 1b: List Campaigns for a Game (when `target_game_id` is provided)

If the user provided a `target_game_id`, run this query first to show all campaigns and their types. Present the results to the user as a table and ask if they want to filter to a specific campaign before proceeding.

### Query 0 — Campaign List

```sql
SELECT
  body.campaign_id,
  body.valuation_metadata[SAFE_OFFSET(0)].model_type  AS campaign_type,
  body.post_install_window,
  MIN(submit_date)                                     AS first_seen,
  MAX(submit_date)                                     AS last_seen,
  COUNT(DISTINCT submit_date)                          AS active_days,
  COUNT(*)                                             AS total_predictions
FROM `unity-ai-data-prd.mz_dcpi_raw.mz_dcpi_prediction_v1`
WHERE submit_date BETWEEN "{start_date}" AND "{end_date}"
  AND body.ar_ts >= "{start_date} 00:00:00"
  AND body.target_game_id IN ({target_game_id})
GROUP BY body.campaign_id, campaign_type, body.post_install_window
ORDER BY total_predictions DESC
```

Save result as: `campaigns_list.csv`

After running, present the table to the user. Ask:
> "Found N campaigns for game {target_game_id}. Do you want to analyze all of them, or filter to a specific campaign_id?"

If the user picks a specific campaign, set `campaign_id` for all subsequent queries.

---

## Step 2: Run SQL Queries

Run **four separate queries** and save each result as a CSV. Strip any `bq` status lines — keep only lines starting with the header or a date (`20XX-`).

### Query A — IAP Predictions (D7 & D28, by `model_versions.dep.version`)

```sql
SELECT
  submit_date,
  body.post_install_window,
  body.model_versions.dep.version   AS dep_model_version,
  MAX(body.target_game_id)          AS target_game_id,
  COUNT(*)                          AS start_count,
  -- D7 IAP
  AVG(body.dep_d7_prob)             AS avg_dep_d7_prob,
  AVG(body.dep_d7_value)            AS avg_dep_d7_value,
  AVG(body.dep_d7_final)            AS avg_dep_d7_final,
  -- D28 IAP
  AVG(body.dep_d28_prob)            AS avg_dep_d28_prob,
  AVG(body.dep_d28_value)           AS avg_dep_d28_value,
  AVG(body.dep_d28_final)           AS avg_dep_d28_final
FROM `unity-ai-data-prd.mz_dcpi_raw.mz_dcpi_prediction_v1`
WHERE submit_date BETWEEN "{start_date}" AND "{end_date}"
  AND body.ar_ts >= "{start_date} 00:00:00"
  AND body.dep_p > 0
  -- AND body.target_game_id IN ({target_game_id})
  -- AND body.campaign_id = "{campaign_id}"
GROUP BY submit_date, body.post_install_window, body.model_versions.dep.version
ORDER BY submit_date
```

Save result as: `iap_predictions.csv`

### Query B — AdRev Predictions (D0, D7, D28, by `model_versions.adrev.version`)

```sql
SELECT
  submit_date,
  body.post_install_window,
  body.model_versions.adrev.version  AS adrev_model_version,
  MAX(body.target_game_id)           AS target_game_id,
  COUNT(*)                           AS start_count,
  -- AdRev by window
  AVG(body.adrev_d0_non_log_value)   AS avg_adrev_d0_value,
  AVG(body.adrev_d7_non_log_value)   AS avg_adrev_d7_value,
  AVG(body.adrev_adj)                AS avg_adrev_adj,
  AVG(body.adrev_value)              AS avg_adrev_value
FROM `unity-ai-data-prd.mz_dcpi_raw.mz_dcpi_prediction_v1`
WHERE submit_date BETWEEN "{start_date}" AND "{end_date}"
  AND body.ar_ts >= "{start_date} 00:00:00"
  AND body.adrev_p > 0
  -- AND body.target_game_id IN ({target_game_id})
  -- AND body.campaign_id = "{campaign_id}"
GROUP BY submit_date, body.post_install_window, body.model_versions.adrev.version
ORDER BY submit_date
```

Save result as: `adrev_predictions.csv`

### Query C — CPE Predictions (by `model_versions.<type>.version`)

```sql
SELECT
  submit_date,
  body.app_event_type,
  CASE body.app_event_type
    WHEN 'level_complete' THEN body.model_versions.level_complete.version
    WHEN 'purchase'       THEN body.model_versions.purchase.version
    WHEN 'retention'      THEN body.model_versions.retention.version
  END AS cpe_model_version,
  MAX(body.target_game_id)  AS target_game_id,
  COUNT(*)                  AS start_count,
  AVG(body.app_event_p)     AS avg_cpe_pred,
  AVG(body.app_event_adj)   AS avg_cpe_adj
FROM `unity-ai-data-prd.mz_dcpi_raw.mz_dcpi_prediction_v1`
WHERE submit_date BETWEEN "{start_date}" AND "{end_date}"
  AND body.ar_ts >= "{start_date} 00:00:00"
  AND body.app_event_type IN ('level_complete', 'purchase', 'retention')
  AND body.app_event_p > 0
  -- AND body.target_game_id IN ({target_game_id})
  -- AND body.campaign_id = "{campaign_id}"
GROUP BY submit_date, body.app_event_type, cpe_model_version
ORDER BY submit_date
```

Save result as: `cpe_predictions.csv`

### Query D — Avg Cost by `valuation_metadata.model_type`

```sql
SELECT
  submit_date,
  body.valuation_metadata[SAFE_OFFSET(0)].model_type  AS model_type,
  body.post_install_window,
  MAX(body.target_game_id)                            AS target_game_id,
  COUNT(*)                                            AS start_count,
  AVG(body.cst)                                       AS avg_cost,
  AVG(body.max_cost)                                  AS avg_max_cost,
  AVG(body.actual_max_cost)                           AS avg_actual_max_cst
FROM `unity-ai-data-prd.mz_dcpi_raw.mz_dcpi_prediction_v1`
WHERE submit_date BETWEEN "{start_date}" AND "{end_date}"
  AND body.ar_ts >= "{start_date} 00:00:00"
  -- AND body.target_game_id IN ({target_game_id})
  -- AND body.campaign_id = "{campaign_id}"
GROUP BY submit_date, model_type, body.post_install_window
ORDER BY submit_date
```

Save result as: `cost_by_model_type.csv`

### Query E — All Valuations (dcpi_valuation_v1alpha1) *(campaign_id required)*

> **When to use**: Queries A–D come from `mz_dcpi_prediction_v1`, which contains **winning bids only**. Use Query E when you need to see all valuations (including non-winning bids) to understand what the model was predicting across all auctions, not just the ones Unity won. This is useful when comparing against BI team analyses.
>
> **Requires**: a specific `campaign_id`. The table is very large — always use `TABLESAMPLE SYSTEM (5 PERCENT)` unless you need exact counts.
> **Billing project**: `unity-ads-ai-tools-prd`

```sql
WITH campaigns_roas AS (
  SELECT
    id,
    (SELECT STRING_AGG(t, ',' ORDER BY t) FROM UNNEST(roas_types.types) t) AS roas_type
  FROM `unity-data-ads-core-prd.ads_dimension_data.campaigns_v3`
  WHERE ARRAY_LENGTH(roas_types.types) > 0
  QUALIFY ROW_NUMBER() OVER (PARTITION BY id ORDER BY _lapio_submit_time DESC) = 1
),
base AS (
  SELECT
    _lapio_submit_time,
    valuation_id,
    model_version,
    valuations,
    (SELECT f.string_array_value FROM UNNEST(features) f WHERE f.name = 'audience_id')     AS feat_audience_id,
    (SELECT f.float_array_value  FROM UNNEST(features) f WHERE f.name = 'discount_factor') AS feat_discount_factor
  FROM `unity-ads-cpi-direct-prd.dcpi_valuation.dcpi_valuation_v1alpha1`
       TABLESAMPLE SYSTEM (5 PERCENT)
  WHERE _lapio_submit_time >= TIMESTAMP("{start_date}")
    AND _lapio_submit_time <  TIMESTAMP("{end_date}")
    AND valuation_type IN ('VALUATION_TYPE_DEPOSITOR', 'VALUATION_TYPE_DEPOSITOR_D28')
)
SELECT
  TIMESTAMP_TRUNC(_lapio_submit_time, DAY) AS date,
  model_version,
  cr.roas_type,
  APPROX_COUNT_DISTINCT(valuation_id)                AS n,
  AVG(v.value.value)                                 AS value_raw,
  AVG(v.value.p)                                     AS p,
  AVG(v.value.dep_d7_prob)                           AS dep_d7_prob,
  AVG(v.value.dep_d7_value)                          AS dep_d7_value,
  AVG(v.value.dep_d7_final)                          AS dep_d7_final,
  AVG(v.value.dep_d28_prob)                          AS dep_d28_prob,
  AVG(v.value.dep_d28_value)                         AS dep_d28_value,
  AVG(v.value.dep_d28_final)                         AS dep_d28_final,
  AVG(v.value.adrev_d0_non_log_value)                AS adrev_d0_non_log_value,
  AVG(v.value.adrev_d7_non_log_value)                AS adrev_d7,
  AVG(v.value.ret_d7_prob)                           AS ret_d7_prob,
  AVG(v.value.adjustment)                            AS adjustment,
  AVG(v.value.unadjusted_prob)                       AS unadjusted_prob,
  AVG(v.value.cost / 1e6)                            AS cost,
  AVG(v.value.raw_cost / 1e6)                        AS raw_cost,
  AVG(v.value.smart_max_cost / 1e6)                  AS smart_max_cost,
  AVG(v.value.actual_max_cost / 1e6)                 AS actual_max_cost,
  AVG(feat_discount_factor[SAFE_OFFSET(
      (SELECT off FROM UNNEST(feat_audience_id) a WITH OFFSET off WHERE a = v.key))]) AS discount_factor
FROM base,
  UNNEST(valuations) v WITH OFFSET v_offset
JOIN campaigns_roas cr ON cr.id = v.key
WHERE v.key = "{campaign_id}"
GROUP BY ALL
ORDER BY date, model_version, roas_type
```

Save result as: `all_valuations.csv`

Key differences from Query A–D results:

| | Query A–D (`mz_dcpi_prediction_v1`) | Query E (`dcpi_valuation_v1alpha1`) |
|---|---|---|
| Scope | Winning bids only | All valuations (wins + losses) |
| Volume | Lower | Much higher (use TABLESAMPLE) |
| Cost field | `body.cst` (raw units) | `v.value.cost / 1e6` (USD) |
| Model version | `body.model_versions.<type>.version` | `model_version` (top-level field) |
| Campaign filter | `body.campaign_id` | `v.key` (campaign is a key in the valuations array) |

---

## Step 3: Generate HTML Report

Save and run the script below. Set the variables at the top to match your context.

```python
import csv, json
from collections import defaultdict

# ── Configuration — edit these ─────────────────────────────────────────────────
CAMPAIGNS_CSV = "campaigns_list.csv"   # leave "" if not run
IAP_CSV       = "iap_predictions.csv"
ADREV_CSV     = "adrev_predictions.csv"
CPE_CSV       = "cpe_predictions.csv"
COST_CSV      = "cost_by_model_type.csv"
ALL_VAL_CSV   = "all_valuations.csv"     # leave "" if Query E was not run
OUT_HTML      = "uv_prediction_report.html"
START_DATE    = "YYYY-MM-DD"
END_DATE      = "YYYY-MM-DD"
GAME_ID       = "all games"
CAMPAIGN_ID   = "all campaigns"

SQL_0 = """\
SELECT
  body.campaign_id,
  body.valuation_metadata[SAFE_OFFSET(0)].model_type AS campaign_type,
  body.post_install_window,
  MIN(submit_date) AS first_seen, MAX(submit_date) AS last_seen,
  COUNT(DISTINCT submit_date) AS active_days, COUNT(*) AS total_predictions
FROM `unity-ai-data-prd.mz_dcpi_raw.mz_dcpi_prediction_v1`
WHERE submit_date BETWEEN "{start}" AND "{end}"
  AND body.ar_ts >= "{start} 00:00:00"
  AND body.target_game_id IN ({game})
GROUP BY body.campaign_id, campaign_type, body.post_install_window
ORDER BY total_predictions DESC""".format(start=START_DATE, end=END_DATE, game=GAME_ID)

SQL_A = """\
SELECT
  submit_date, body.post_install_window,
  body.model_versions.dep.version AS dep_model_version,
  MAX(body.target_game_id) AS target_game_id, COUNT(*) AS start_count,
  AVG(body.dep_d7_prob)  AS avg_dep_d7_prob,  AVG(body.dep_d7_value)  AS avg_dep_d7_value,  AVG(body.dep_d7_final)  AS avg_dep_d7_final,
  AVG(body.dep_d28_prob) AS avg_dep_d28_prob, AVG(body.dep_d28_value) AS avg_dep_d28_value, AVG(body.dep_d28_final) AS avg_dep_d28_final
FROM `unity-ai-data-prd.mz_dcpi_raw.mz_dcpi_prediction_v1`
WHERE submit_date BETWEEN "{start}" AND "{end}"
  AND body.ar_ts >= "{start} 00:00:00" AND body.dep_p > 0
GROUP BY submit_date, body.post_install_window, body.model_versions.dep.version
ORDER BY submit_date""".format(start=START_DATE, end=END_DATE)

SQL_B = """\
SELECT
  submit_date, body.post_install_window,
  body.model_versions.adrev.version AS adrev_model_version,
  MAX(body.target_game_id) AS target_game_id, COUNT(*) AS start_count,
  AVG(body.adrev_d0_non_log_value) AS avg_adrev_d0_value,
  AVG(body.adrev_d7_non_log_value) AS avg_adrev_d7_value,
  AVG(body.adrev_adj) AS avg_adrev_adj, AVG(body.adrev_value) AS avg_adrev_value
FROM `unity-ai-data-prd.mz_dcpi_raw.mz_dcpi_prediction_v1`
WHERE submit_date BETWEEN "{start}" AND "{end}"
  AND body.ar_ts >= "{start} 00:00:00" AND body.adrev_p > 0
GROUP BY submit_date, body.post_install_window, body.model_versions.adrev.version
ORDER BY submit_date""".format(start=START_DATE, end=END_DATE)

SQL_C = """\
SELECT
  submit_date, body.app_event_type,
  CASE body.app_event_type
    WHEN 'level_complete' THEN body.model_versions.level_complete.version
    WHEN 'purchase'       THEN body.model_versions.purchase.version
    WHEN 'retention'      THEN body.model_versions.retention.version
  END AS cpe_model_version,
  MAX(body.target_game_id) AS target_game_id, COUNT(*) AS start_count,
  AVG(body.app_event_p) AS avg_cpe_pred, AVG(body.app_event_adj) AS avg_cpe_adj
FROM `unity-ai-data-prd.mz_dcpi_raw.mz_dcpi_prediction_v1`
WHERE submit_date BETWEEN "{start}" AND "{end}"
  AND body.ar_ts >= "{start} 00:00:00"
  AND body.app_event_type IN ('level_complete', 'purchase', 'retention')
  AND body.app_event_p > 0
GROUP BY submit_date, body.app_event_type, cpe_model_version
ORDER BY submit_date""".format(start=START_DATE, end=END_DATE)

SQL_D = """\
SELECT
  submit_date,
  body.valuation_metadata[SAFE_OFFSET(0)].model_type AS model_type,
  body.post_install_window,
  MAX(body.target_game_id) AS target_game_id, COUNT(*) AS start_count,
  AVG(body.cst) AS avg_cost, AVG(body.max_cost) AS avg_max_cost,
  AVG(body.actual_max_cost) AS avg_actual_max_cst
FROM `unity-ai-data-prd.mz_dcpi_raw.mz_dcpi_prediction_v1`
WHERE submit_date BETWEEN "{start}" AND "{end}"
  AND body.ar_ts >= "{start} 00:00:00"
GROUP BY submit_date, model_type, body.post_install_window
ORDER BY submit_date""".format(start=START_DATE, end=END_DATE)

SQL_E = """\
WITH campaigns_roas AS (
  SELECT id,
    (SELECT STRING_AGG(t, ',' ORDER BY t) FROM UNNEST(roas_types.types) t) AS roas_type
  FROM `unity-data-ads-core-prd.ads_dimension_data.campaigns_v3`
  WHERE ARRAY_LENGTH(roas_types.types) > 0
  QUALIFY ROW_NUMBER() OVER (PARTITION BY id ORDER BY _lapio_submit_time DESC) = 1
),
base AS (
  SELECT _lapio_submit_time, valuation_id, model_version, valuations,
    (SELECT f.string_array_value FROM UNNEST(features) f WHERE f.name = 'audience_id')     AS feat_audience_id,
    (SELECT f.float_array_value  FROM UNNEST(features) f WHERE f.name = 'discount_factor') AS feat_discount_factor
  FROM `unity-ads-cpi-direct-prd.dcpi_valuation.dcpi_valuation_v1alpha1`
       TABLESAMPLE SYSTEM (5 PERCENT)
  WHERE _lapio_submit_time >= TIMESTAMP("{start}")
    AND _lapio_submit_time <  TIMESTAMP("{end}")
    AND valuation_type IN ('VALUATION_TYPE_DEPOSITOR', 'VALUATION_TYPE_DEPOSITOR_D28')
)
SELECT
  TIMESTAMP_TRUNC(_lapio_submit_time, DAY) AS date,
  model_version, cr.roas_type,
  APPROX_COUNT_DISTINCT(valuation_id)                AS n,
  AVG(v.value.value)                                 AS value_raw,
  AVG(v.value.p)                                     AS p,
  AVG(v.value.dep_d7_prob)                           AS dep_d7_prob,
  AVG(v.value.dep_d7_value)                          AS dep_d7_value,
  AVG(v.value.dep_d7_final)                          AS dep_d7_final,
  AVG(v.value.dep_d28_prob)                          AS dep_d28_prob,
  AVG(v.value.dep_d28_value)                         AS dep_d28_value,
  AVG(v.value.dep_d28_final)                         AS dep_d28_final,
  AVG(v.value.adrev_d0_non_log_value)                AS adrev_d0_non_log_value,
  AVG(v.value.adrev_d7_non_log_value)                AS adrev_d7,
  AVG(v.value.ret_d7_prob)                           AS ret_d7_prob,
  AVG(v.value.adjustment)                            AS adjustment,
  AVG(v.value.unadjusted_prob)                       AS unadjusted_prob,
  AVG(v.value.cost / 1e6)                            AS cost,
  AVG(v.value.raw_cost / 1e6)                        AS raw_cost,
  AVG(v.value.smart_max_cost / 1e6)                  AS smart_max_cost,
  AVG(v.value.actual_max_cost / 1e6)                 AS actual_max_cost,
  AVG(feat_discount_factor[SAFE_OFFSET(
      (SELECT off FROM UNNEST(feat_audience_id) a WITH OFFSET off WHERE a = v.key))]) AS discount_factor
FROM base, UNNEST(valuations) v WITH OFFSET v_offset
JOIN campaigns_roas cr ON cr.id = v.key
WHERE v.key = "{campaign}"
GROUP BY ALL
ORDER BY date, model_version, roas_type""".format(start=START_DATE, end=END_DATE, campaign=CAMPAIGN_ID)

# ── Color palette ──────────────────────────────────────────────────────────────
COLORS = [
    "#636EFA","#EF553B","#00CC96","#AB63FA","#FFA15A","#19D3F3","#FF6692","#B6E880",
    "#FF97FF","#FECB52","#1F77B4","#FF7F0E","#2CA02C","#D62728","#9467BD","#8C564B",
    "#E377C2","#7F7F7F","#BCBD22","#17BECF","#AEC7E8","#FFBB78","#98DF8A","#FF9896",
    "#C5B0D5","#C49C94",
]

def make_color_map(keys):
    return {k: COLORS[i % len(COLORS)] for i, k in enumerate(sorted(keys))}

def load_csv(path):
    try:
        with open(path) as f:
            return list(csv.DictReader(f))
    except Exception:
        return []

def csv_to_html_table(rows):
    if not rows:
        return '<p style="color:#7a8aaa;font-style:italic">No data returned.</p>'
    headers = list(rows[0].keys())
    th = "".join(f"<th>{h}</th>" for h in headers)
    body = "".join(
        "<tr>" + "".join(f"<td>{r.get(h,'')}</td>" for h in headers) + "</tr>"
        for r in rows
    )
    return f"<div style='overflow-x:auto'><table><thead><tr>{th}</tr></thead><tbody>{body}</tbody></table></div>"

def build_windowed(rows, model_col, window_col="post_install_window", window_val=None):
    """Build model -> date -> metrics dict, optionally filtered to a specific window value."""
    d = defaultdict(lambda: defaultdict(dict))
    for r in rows:
        if window_val is not None and r.get(window_col, "").strip() != window_val:
            continue
        model = r.get(model_col, "").replace("unified-user-value-", "") or "(no version)"
        date  = r.get("submit_date", "")
        for k, v in r.items():
            if k in (model_col, "submit_date", window_col):
                continue
            try:
                d[model][date][k] = float(v) if str(v).strip() else None
            except (ValueError, AttributeError):
                d[model][date][k] = None
    return d

def build_cost_windowed(rows, window_val=None):
    """Build model_type+window -> date -> metrics. model_type is the legend key."""
    d = defaultdict(lambda: defaultdict(dict))
    for r in rows:
        window = r.get("post_install_window", "").strip() or "?"
        mtype  = r.get("model_type", "").strip() or "(blank)"
        key    = f"{mtype} [{window}]"
        date   = r.get("submit_date", "")
        try:
            d[key][date]["avg_cost"] = float(r.get("avg_cost", "") or 0)
        except ValueError:
            pass
    return d

def build_valuation(rows):
    """Build legend_key -> date -> metrics for Query E (dcpi_valuation_v1alpha1).
    Legend key = model_version / roas_type (strips unified-user-value- prefix).
    Date column is 'date' (not 'submit_date').
    """
    d = defaultdict(lambda: defaultdict(dict))
    for r in rows:
        model = r.get("model_version", "").replace("unified-user-value-", "") or "(no version)"
        rtype = r.get("roas_type", "").strip() or "(no roas_type)"
        key   = f"{model} / {rtype}"
        date  = r.get("date", "")
        for col, val in r.items():
            if col in ("model_version", "roas_type", "date"):
                continue
            try:
                d[key][date][col] = float(val) if str(val).strip() else None
            except (ValueError, AttributeError):
                d[key][date][col] = None
    return d

def build_traces(model_date_data, metric, label, cmap):
    traces = []
    for model in sorted(model_date_data):
        pts = sorted(
            (d, v[metric]) for d, v in model_date_data[model].items()
            if v.get(metric) is not None
        )
        if not pts:
            continue
        xs, ys = zip(*pts)
        texts = [f"{model}<br>Date: {d}<br>{label}: {y:,.6g}" for d, y in pts]
        traces.append({
            "type": "scatter", "mode": "lines+markers", "name": model,
            "x": list(xs), "y": list(ys), "text": texts,
            "hovertemplate": "%{text}<extra></extra>",
            "line": {"color": cmap.get(model, COLORS[0]), "width": 2},
            "marker": {"size": 7, "color": cmap.get(model, COLORS[0])},
        })
    return traces

def make_layout(title, y_title, tick_fmt=".5f"):
    return {
        "title": {"text": title, "font": {"color": "#e8eaf0", "size": 14}},
        "paper_bgcolor": "#1a1f2e", "plot_bgcolor": "#12172a",
        "font": {"color": "#e8eaf0", "size": 12},
        "xaxis": {"title": "Submit Date", "type": "date", "tickformat": "%b %d",
                  "tickangle": -40, "gridcolor": "#2a3550", "zerolinecolor": "#3a4a7a"},
        "yaxis": {"title": y_title, "tickformat": tick_fmt,
                  "gridcolor": "#2a3550", "zerolinecolor": "#3a4a7a"},
        "margin": {"t": 50, "b": 70, "l": 90, "r": 30},
        "hovermode": "closest",
        "legend": {"bgcolor": "#1a1f2e", "bordercolor": "#2a3550",
                   "borderwidth": 1, "font": {"size": 10}},
        "showlegend": True,
    }

def newplot(div_id, traces, layout):
    return f"Plotly.newPlot('{div_id}', {json.dumps(traces)}, {json.dumps(layout)}, {{responsive:true}});\n"

# ── Load all CSVs ──────────────────────────────────────────────────────────────
campaign_rows = load_csv(CAMPAIGNS_CSV) if CAMPAIGNS_CSV else []
iap_rows      = load_csv(IAP_CSV)
adrev_rows    = load_csv(ADREV_CSV)
cpe_rows      = load_csv(CPE_CSV)
cost_rows     = load_csv(COST_CSV)
allval_rows   = load_csv(ALL_VAL_CSV) if ALL_VAL_CSV else []

# IAP — split by post_install_window
iap_d7_data  = build_windowed(iap_rows,   "dep_model_version",   window_val="d7")
iap_d28_data = build_windowed(iap_rows,   "dep_model_version",   window_val="d28")

# AdRev — split by post_install_window
adrev_d0_data  = build_windowed(adrev_rows, "adrev_model_version", window_val="d0")
adrev_d7_data  = build_windowed(adrev_rows, "adrev_model_version", window_val="d7")
adrev_d28_data = build_windowed(adrev_rows, "adrev_model_version", window_val="d28")

# CPE
cpe_data = {t: defaultdict(lambda: defaultdict(dict))
            for t in ("level_complete", "purchase", "retention")}
for r in cpe_rows:
    etype = r.get("app_event_type", "").strip()
    if etype not in cpe_data:
        continue
    model = r.get("cpe_model_version", "").replace("unified-user-value-", "") or "(no version)"
    d     = r.get("submit_date", "")
    v     = r.get("avg_cpe_pred", "").strip()
    try:
        cpe_data[etype][model][d]["avg_cpe_pred"] = float(v) if v else None
    except ValueError:
        pass

# Cost — model_type + window as legend key
cost_data = build_cost_windowed(cost_rows)

# All Valuations (Query E)
allval_data = build_valuation(allval_rows)

# Color maps
iap_models   = set(iap_d7_data) | set(iap_d28_data)
adrev_models = set(adrev_d0_data) | set(adrev_d7_data) | set(adrev_d28_data)
iap_cmap     = make_color_map(iap_models)
adrev_cmap   = make_color_map(adrev_models)
cost_cmap    = make_color_map(cost_data.keys())
cpe_cmaps    = {t: make_color_map(cpe_data[t].keys()) for t in cpe_data}
allval_cmap  = make_color_map(allval_data.keys())

# ── Plot specs ─────────────────────────────────────────────────────────────────
plot_specs = [
    # IAP D7
    ("plot_iap_d7_prob",  "1a. IAP D7 — Probability (dep_d7_prob)",
     iap_d7_data,  "avg_dep_d7_prob",  "Avg dep_d7_prob",  ".5f",  iap_cmap),
    ("plot_iap_d7_value", "1b. IAP D7 — Value (dep_d7_value)",
     iap_d7_data,  "avg_dep_d7_value", "Avg dep_d7_value", ",.4f", iap_cmap),
    ("plot_iap_d7_final", "1c. IAP D7 — Final Prediction (dep_d7_final)",
     iap_d7_data,  "avg_dep_d7_final", "Avg dep_d7_final", ",.4f", iap_cmap),
    # IAP D28
    ("plot_iap_d28_prob",  "2a. IAP D28 — Probability (dep_d28_prob)",
     iap_d28_data, "avg_dep_d28_prob",  "Avg dep_d28_prob",  ".5f",  iap_cmap),
    ("plot_iap_d28_value", "2b. IAP D28 — Value (dep_d28_value)",
     iap_d28_data, "avg_dep_d28_value", "Avg dep_d28_value", ",.4f", iap_cmap),
    ("plot_iap_d28_final", "2c. IAP D28 — Final Prediction (dep_d28_final)",
     iap_d28_data, "avg_dep_d28_final", "Avg dep_d28_final", ",.4f", iap_cmap),
    # AdRev
    ("plot_adrev_d0",  "3a. AdRev D0 — Value (adrev_d0_non_log_value)",
     adrev_d0_data,  "avg_adrev_d0_value", "Avg adrev_d0_non_log_value", ",.4f", adrev_cmap),
    ("plot_adrev_d7",  "3b. AdRev D7 — Value (adrev_d7_non_log_value)",
     adrev_d7_data,  "avg_adrev_d7_value", "Avg adrev_d7_non_log_value", ",.4f", adrev_cmap),
    ("plot_adrev_d28", "3c. AdRev D28 — Value (adrev_value)",
     adrev_d28_data, "avg_adrev_value",    "Avg adrev_value (D28)",      ",.4f", adrev_cmap),
    # Cost
    ("plot_avg_cost", "4. Avg Cost by model_type + post_install_window",
     cost_data,  "avg_cost", "Avg Cost", ",.0f", cost_cmap),
    # CPE
    ("plot_cpe_lc",       "5. CPE — Level Complete Probability",
     cpe_data["level_complete"], "avg_cpe_pred", "Avg app_event_p (level_complete)", ".5f", cpe_cmaps["level_complete"]),
    ("plot_cpe_purchase",  "6. CPE — Purchase Probability",
     cpe_data["purchase"],       "avg_cpe_pred", "Avg app_event_p (purchase)",       ".5f", cpe_cmaps["purchase"]),
    ("plot_cpe_retention", "7. CPE — Retention Probability",
     cpe_data["retention"],      "avg_cpe_pred", "Avg app_event_p (retention)",      ".5f", cpe_cmaps["retention"]),
    # All Valuations — Query E (dcpi_valuation_v1alpha1, wins + losses)
    ("plot_val_n",         "E1. All Valuations — n (count)",
     allval_data, "n",                      "n (valuations)",          ",.0f", allval_cmap),
    ("plot_val_value_raw", "E2. All Valuations — value_raw",
     allval_data, "value_raw",              "value_raw",               ",.4f", allval_cmap),
    ("plot_val_p",         "E3. All Valuations — p (payer prob)",
     allval_data, "p",                      "p",                       ".5f",  allval_cmap),
    ("plot_val_d7_prob",   "E4. All Valuations — dep_d7_prob",
     allval_data, "dep_d7_prob",            "dep_d7_prob",             ".5f",  allval_cmap),
    ("plot_val_d7_value",  "E5. All Valuations — dep_d7_value",
     allval_data, "dep_d7_value",           "dep_d7_value",            ",.4f", allval_cmap),
    ("plot_val_d7_final",  "E6. All Valuations — dep_d7_final",
     allval_data, "dep_d7_final",           "dep_d7_final",            ",.4f", allval_cmap),
    ("plot_val_d28_prob",  "E7. All Valuations — dep_d28_prob",
     allval_data, "dep_d28_prob",           "dep_d28_prob",            ".5f",  allval_cmap),
    ("plot_val_d28_value", "E8. All Valuations — dep_d28_value",
     allval_data, "dep_d28_value",          "dep_d28_value",           ",.4f", allval_cmap),
    ("plot_val_d28_final", "E9. All Valuations — dep_d28_final",
     allval_data, "dep_d28_final",          "dep_d28_final",           ",.4f", allval_cmap),
    ("plot_val_adrev_d0",  "E10. All Valuations — adrev_d0_non_log_value",
     allval_data, "adrev_d0_non_log_value", "adrev_d0_non_log_value",  ",.4f", allval_cmap),
    ("plot_val_adrev_d7",  "E11. All Valuations — adrev_d7",
     allval_data, "adrev_d7",               "adrev_d7",                ",.4f", allval_cmap),
    ("plot_val_ret_d7",    "E12. All Valuations — ret_d7_prob",
     allval_data, "ret_d7_prob",            "ret_d7_prob",             ".5f",  allval_cmap),
    ("plot_val_adj",       "E13. All Valuations — adjustment",
     allval_data, "adjustment",             "adjustment",              ",.4f", allval_cmap),
    ("plot_val_cost",      "E14. All Valuations — cost (USD)",
     allval_data, "cost",                   "cost (USD)",              ",.4f", allval_cmap),
    ("plot_val_raw_cost",  "E15. All Valuations — raw_cost (USD)",
     allval_data, "raw_cost",               "raw_cost (USD)",          ",.4f", allval_cmap),
    ("plot_val_max_cost",  "E16. All Valuations — actual_max_cost (USD)",
     allval_data, "actual_max_cost",        "actual_max_cost (USD)",   ",.4f", allval_cmap),
    ("plot_val_discount",  "E17. All Valuations — discount_factor",
     allval_data, "discount_factor",        "discount_factor",         ",.4f", allval_cmap),
]

# ── Campaign summary section ───────────────────────────────────────────────────
campaign_section = ""
if campaign_rows:
    campaign_section = f"""
<h2>Campaigns for Game {GAME_ID}</h2>
<div class="card">{csv_to_html_table(campaign_rows)}</div>
"""

sections_html = campaign_section
plots_js = ""
for div_id, section_title, data_dict, metric, y_label, tick_fmt, cmap in plot_specs:
    traces = build_traces(data_dict, metric, y_label, cmap)
    layout = make_layout(section_title, y_label, tick_fmt)
    no_data = ' <span style="color:#7a8aaa;font-size:0.85rem">(no data)</span>' if not traces else ""
    sections_html += f"\n<h2>{section_title}{no_data}</h2>\n"
    if traces:
        sections_html += f'<div class="plot-wrap"><div id="{div_id}" style="height:460px"></div></div>\n'
        plots_js += newplot(div_id, traces, layout)
    else:
        sections_html += '<div class="plot-wrap empty-plot">No data for this campaign type / window.</div>\n'

# ── SQL + results section ──────────────────────────────────────────────────────
campaign_sql_block = ""
if campaign_rows:
    campaign_sql_block = f"""
<div class="card">
<h3>Query 0 — Campaign List for Game {GAME_ID}</h3>
<pre><code>{SQL_0}</code></pre>
<h4>Results</h4>
{csv_to_html_table(campaign_rows)}
</div>"""

sql_section = f"""
<h2>SQL Queries &amp; Results</h2>
{campaign_sql_block}
<div class="card">
<h3>Query A — IAP Predictions (D7 &amp; D28)</h3>
<pre><code>{SQL_A}</code></pre>
<h4>Results</h4>
{csv_to_html_table(iap_rows)}
</div>
<div class="card">
<h3>Query B — AdRev Predictions (D0, D7, D28)</h3>
<pre><code>{SQL_B}</code></pre>
<h4>Results</h4>
{csv_to_html_table(adrev_rows)}
</div>
<div class="card">
<h3>Query C — CPE Predictions</h3>
<pre><code>{SQL_C}</code></pre>
<h4>Results</h4>
{csv_to_html_table(cpe_rows)}
</div>
<div class="card">
<h3>Query D — Avg Cost by model_type &amp; post_install_window</h3>
<pre><code>{SQL_D}</code></pre>
<h4>Results</h4>
{csv_to_html_table(cost_rows)}
</div>
{"" if not allval_rows else f"""
<div class="card">
<h3>Query E — All Valuations (dcpi_valuation_v1alpha1, wins + losses)</h3>
<pre><code>{SQL_E}</code></pre>
<h4>Results</h4>
{csv_to_html_table(allval_rows)}
</div>"""}"""

# ── Assemble HTML ──────────────────────────────────────────────────────────────
html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>UV Prediction Report</title>
<script src="https://cdn.plot.ly/plotly-2.27.0.min.js"></script>
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #0f1117; color: #e8eaf0; margin: 0; padding: 0; }}
  .container {{ max-width: 1400px; margin: 0 auto; padding: 24px; }}
  h1 {{ font-size: 1.8rem; color: #f0f4ff; border-bottom: 2px solid #3a4a7a; padding-bottom: 12px; margin-bottom: 4px; }}
  .meta {{ color: #7a8aaa; font-size: 0.9rem; margin-bottom: 28px; }}
  h2 {{ font-size: 1.2rem; color: #aac4ff; margin-top: 36px; border-left: 4px solid #4a6fa5; padding-left: 12px; }}
  h3 {{ font-size: 1rem; color: #8bb4e8; margin-top: 20px; }}
  h4 {{ font-size: 0.85rem; color: #7a8aaa; margin: 16px 0 6px; text-transform: uppercase; letter-spacing: 0.05em; }}
  .plot-wrap {{ background: #1a1f2e; border: 1px solid #2a3550; border-radius: 10px; padding: 12px; margin: 16px 0; }}
  .empty-plot {{ color: #7a8aaa; font-size: 0.9rem; padding: 20px; font-style: italic; }}
  .card {{ background: #1a1f2e; border: 1px solid #2a3550; border-radius: 10px; padding: 20px; margin: 16px 0; }}
  pre {{ background: #12172a; border: 1px solid #2a3550; border-radius: 8px; padding: 16px; overflow-x: auto; margin: 8px 0; }}
  code {{ font-family: 'JetBrains Mono', 'Fira Code', monospace; font-size: 0.82em; color: #a8c7fa; white-space: pre; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 0.8rem; margin-top: 4px; }}
  th {{ background: #2a3550; color: #aac4ff; padding: 7px 10px; text-align: left; white-space: nowrap; }}
  td {{ padding: 6px 10px; border-bottom: 1px solid #2a3550; white-space: nowrap; }}
  tr:hover td {{ background: #1f2840; }}
</style>
</head>
<body>
<div class="container">
<h1>UV Model Prediction Report</h1>
<div class="meta">
  Date range: <strong>{START_DATE} → {END_DATE}</strong> &nbsp;|&nbsp;
  Game: <strong>{GAME_ID}</strong> &nbsp;|&nbsp;
  Campaign: <strong>{CAMPAIGN_ID}</strong>
</div>
{sections_html}
{sql_section}
</div>
<script>
{plots_js}
</script>
</body>
</html>"""

with open(OUT_HTML, "w") as f:
    f.write(html)
print(f"Report saved: {OUT_HTML}")
```

---

## Output

A single HTML file with campaign summary table + **13 interactive plots** (+ 17 more if Query E was run) + SQL and raw result tables:

| Section | Content | Window | Source |
|---|---|---|---|
| Campaigns for Game X | campaign_id, type, **post_install_window**, date range, volume | — | Query 0 |
| 1a. IAP D7 Probability | `dep_d7_prob` by `model_versions.dep.version` | d7 | Query A |
| 1b. IAP D7 Value | `dep_d7_value` | d7 | Query A |
| 1c. IAP D7 Final | `dep_d7_final` | d7 | Query A |
| 2a. IAP D28 Probability | `dep_d28_prob` | d28 | Query A |
| 2b. IAP D28 Value | `dep_d28_value` | d28 | Query A |
| 2c. IAP D28 Final | `dep_d28_final` | d28 | Query A |
| 3a. AdRev D0 Value | `adrev_d0_non_log_value` | d0 | Query B |
| 3b. AdRev D7 Value | `adrev_d7_non_log_value` | d7 | Query B |
| 3c. AdRev D28 Value | `adrev_value` | d28 | Query B |
| 4. Avg Cost | `cst` by `model_type + post_install_window` | all | Query D |
| 5. CPE Level Complete | `app_event_p` by `model_versions.level_complete.version` | — | Query C |
| 6. CPE Purchase | `app_event_p` by `model_versions.purchase.version` | — | Query C |
| 7. CPE Retention | `app_event_p` by `model_versions.retention.version` | — | Query C |
| E1–E17. All Valuations | n, value_raw, p, dep_d7/d28 prob/value/final, adrev_d0/d7, ret_d7_prob, adjustment, cost, raw_cost, actual_max_cost, discount_factor — by `model_version / roas_type` | — | Query E |

---

## Notes

- **Hosting**: Use a public repo + `htmlpreview.github.io`, or GitHub Pages. CDN (`cdn.plot.ly`) will not load from `file://`.
- **bq CLI tip**: `bq query --project_id=unity-ads-ai-tools-prd --use_legacy_sql=false --format=csv --max_rows=5000 '...' 2>&1 | grep -E '^(submit_date|20[0-9]{2}-)' > clean.csv`
- **Window values**: Typical values are `d7` and `d28` for IAP/AdRev; `d0` also appears for AdRev. Rows with no window value default to `(no window)` in the legend.
- **Campaign drill-down**: Uncomment `AND body.campaign_id = "..."` in all queries.
- **Traffic type filter**: Add `AND body.\`valuation_metadata\`[SAFE_OFFSET(0)].model_type IN (...)` to filter by type.
- **Winning vs. all bids**: `mz_dcpi_prediction_v1` = winning bids only. Use Query E (`dcpi_valuation_v1alpha1`) to see all valuations including losses — this matches what BI team dashboards typically show and will have lower avg cost/predictions since losses are included.
- **Query E sampling**: `TABLESAMPLE SYSTEM (5 PERCENT)` is applied for cost control. Results are approximate; remove it for exact counts on short date ranges.
