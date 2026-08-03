#!/usr/bin/env python3
"""Generate UV Prediction Report for a single game.
Usage: python3 generate_report.py <game_id> <game_name> <platform>
"""
import csv, json, sys, os
from collections import defaultdict

game_id   = sys.argv[1]
game_name = sys.argv[2] if len(sys.argv) > 2 else game_id
platform  = sys.argv[3] if len(sys.argv) > 3 else ""

BASE_DIR = os.path.join(os.path.dirname(__file__), f"game_{game_id}")

CAMPAIGNS_CSV = os.path.join(BASE_DIR, "campaigns_list.csv")
IAP_CSV       = os.path.join(BASE_DIR, "iap_predictions.csv")
ADREV_CSV     = os.path.join(BASE_DIR, "adrev_predictions.csv")
CPE_CSV       = os.path.join(BASE_DIR, "cpe_predictions.csv")
COST_CSV      = os.path.join(BASE_DIR, "cost_by_model_type.csv")
ALL_VAL_CSV   = ""
OUT_HTML      = os.path.join(BASE_DIR, "uv_prediction_report.html")

START_DATE    = "2026-07-01"
END_DATE      = "2026-08-03"
GAME_ID       = game_id
CAMPAIGN_ID   = "all campaigns"

SQL_0 = f"""SELECT
  body.campaign_id,
  body.valuation_metadata[SAFE_OFFSET(0)].model_type AS campaign_type,
  body.post_install_window,
  MIN(submit_date) AS first_seen, MAX(submit_date) AS last_seen,
  COUNT(DISTINCT submit_date) AS active_days, COUNT(*) AS total_predictions
FROM `unity-ai-data-prd.mz_dcpi_raw.mz_dcpi_prediction_v1`
WHERE submit_date BETWEEN "{START_DATE}" AND "{END_DATE}"
  AND body.ar_ts >= "{START_DATE} 00:00:00"
  AND body.target_game_id IN ({GAME_ID})
GROUP BY body.campaign_id, campaign_type, body.post_install_window
ORDER BY total_predictions DESC"""

SQL_A = f"""SELECT
  submit_date, body.post_install_window,
  body.model_versions.dep.version AS dep_model_version,
  MAX(body.target_game_id) AS target_game_id, COUNT(*) AS start_count,
  AVG(body.dep_d7_prob)  AS avg_dep_d7_prob,  AVG(body.dep_d7_value)  AS avg_dep_d7_value,  AVG(body.dep_d7_final)  AS avg_dep_d7_final,
  AVG(body.dep_d28_prob) AS avg_dep_d28_prob, AVG(body.dep_d28_value) AS avg_dep_d28_value, AVG(body.dep_d28_final) AS avg_dep_d28_final
FROM `unity-ai-data-prd.mz_dcpi_raw.mz_dcpi_prediction_v1`
WHERE submit_date BETWEEN "{START_DATE}" AND "{END_DATE}"
  AND body.ar_ts >= "{START_DATE} 00:00:00" AND body.dep_p > 0
  AND body.target_game_id IN ({GAME_ID})
GROUP BY submit_date, body.post_install_window, body.model_versions.dep.version
ORDER BY submit_date"""

SQL_B = f"""SELECT
  submit_date, body.post_install_window,
  body.model_versions.adrev.version AS adrev_model_version,
  MAX(body.target_game_id) AS target_game_id, COUNT(*) AS start_count,
  AVG(body.adrev_d0_non_log_value) AS avg_adrev_d0_value,
  AVG(body.adrev_d7_non_log_value) AS avg_adrev_d7_value,
  AVG(body.adrev_adj) AS avg_adrev_adj, AVG(body.adrev_value) AS avg_adrev_value
FROM `unity-ai-data-prd.mz_dcpi_raw.mz_dcpi_prediction_v1`
WHERE submit_date BETWEEN "{START_DATE}" AND "{END_DATE}"
  AND body.ar_ts >= "{START_DATE} 00:00:00" AND body.adrev_p > 0
  AND body.target_game_id IN ({GAME_ID})
GROUP BY submit_date, body.post_install_window, body.model_versions.adrev.version
ORDER BY submit_date"""

SQL_C = f"""SELECT
  submit_date, body.app_event_type,
  CASE body.app_event_type
    WHEN 'level_complete' THEN body.model_versions.level_complete.version
    WHEN 'purchase'       THEN body.model_versions.purchase.version
    WHEN 'retention'      THEN body.model_versions.retention.version
  END AS cpe_model_version,
  MAX(body.target_game_id) AS target_game_id, COUNT(*) AS start_count,
  AVG(body.app_event_p) AS avg_cpe_pred, AVG(body.app_event_adj) AS avg_cpe_adj
FROM `unity-ai-data-prd.mz_dcpi_raw.mz_dcpi_prediction_v1`
WHERE submit_date BETWEEN "{START_DATE}" AND "{END_DATE}"
  AND body.ar_ts >= "{START_DATE} 00:00:00"
  AND body.app_event_type IN ('level_complete', 'purchase', 'retention')
  AND body.app_event_p > 0
  AND body.target_game_id IN ({GAME_ID})
GROUP BY submit_date, body.app_event_type, cpe_model_version
ORDER BY submit_date"""

SQL_D = f"""SELECT
  submit_date,
  body.valuation_metadata[SAFE_OFFSET(0)].model_type AS model_type,
  body.post_install_window,
  MAX(body.target_game_id) AS target_game_id, COUNT(*) AS start_count,
  AVG(body.cst) AS avg_cost, AVG(body.max_cost) AS avg_max_cost,
  AVG(body.actual_max_cost) AS avg_actual_max_cst
FROM `unity-ai-data-prd.mz_dcpi_raw.mz_dcpi_prediction_v1`
WHERE submit_date BETWEEN "{START_DATE}" AND "{END_DATE}"
  AND body.ar_ts >= "{START_DATE} 00:00:00"
  AND body.target_game_id IN ({GAME_ID})
GROUP BY submit_date, model_type, body.post_install_window
ORDER BY submit_date"""

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
campaign_rows = load_csv(CAMPAIGNS_CSV)
iap_rows      = load_csv(IAP_CSV)
adrev_rows    = load_csv(ADREV_CSV)
cpe_rows      = load_csv(CPE_CSV)
cost_rows     = load_csv(COST_CSV)
allval_rows   = []

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

# Color maps
iap_models   = set(iap_d7_data) | set(iap_d28_data)
adrev_models = set(adrev_d0_data) | set(adrev_d7_data) | set(adrev_d28_data)
iap_cmap     = make_color_map(iap_models)
adrev_cmap   = make_color_map(adrev_models)
cost_cmap    = make_color_map(cost_data.keys())
cpe_cmaps    = {t: make_color_map(cpe_data[t].keys()) for t in cpe_data}

# ── Plot specs ─────────────────────────────────────────────────────────────────
plot_specs = [
    ("plot_iap_d7_prob",  "1a. IAP D7 — Probability (dep_d7_prob)",
     iap_d7_data,  "avg_dep_d7_prob",  "Avg dep_d7_prob",  ".5f",  iap_cmap),
    ("plot_iap_d7_value", "1b. IAP D7 — Value (dep_d7_value)",
     iap_d7_data,  "avg_dep_d7_value", "Avg dep_d7_value", ",.4f", iap_cmap),
    ("plot_iap_d7_final", "1c. IAP D7 — Final Prediction (dep_d7_final)",
     iap_d7_data,  "avg_dep_d7_final", "Avg dep_d7_final", ",.4f", iap_cmap),
    ("plot_iap_d28_prob",  "2a. IAP D28 — Probability (dep_d28_prob)",
     iap_d28_data, "avg_dep_d28_prob",  "Avg dep_d28_prob",  ".5f",  iap_cmap),
    ("plot_iap_d28_value", "2b. IAP D28 — Value (dep_d28_value)",
     iap_d28_data, "avg_dep_d28_value", "Avg dep_d28_value", ",.4f", iap_cmap),
    ("plot_iap_d28_final", "2c. IAP D28 — Final Prediction (dep_d28_final)",
     iap_d28_data, "avg_dep_d28_final", "Avg dep_d28_final", ",.4f", iap_cmap),
    ("plot_adrev_d0",  "3a. AdRev D0 — Value (adrev_d0_non_log_value)",
     adrev_d0_data,  "avg_adrev_d0_value", "Avg adrev_d0_non_log_value", ",.4f", adrev_cmap),
    ("plot_adrev_d7",  "3b. AdRev D7 — Value (adrev_d7_non_log_value)",
     adrev_d7_data,  "avg_adrev_d7_value", "Avg adrev_d7_non_log_value", ",.4f", adrev_cmap),
    ("plot_adrev_d28", "3c. AdRev D28 — Value (adrev_value)",
     adrev_d28_data, "avg_adrev_value",    "Avg adrev_value (D28)",      ",.4f", adrev_cmap),
    ("plot_avg_cost", "4. Avg Cost by model_type + post_install_window",
     cost_data,  "avg_cost", "Avg Cost", ",.0f", cost_cmap),
    ("plot_cpe_lc",       "5. CPE — Level Complete Probability",
     cpe_data["level_complete"], "avg_cpe_pred", "Avg app_event_p (level_complete)", ".5f", cpe_cmaps["level_complete"]),
    ("plot_cpe_purchase",  "6. CPE — Purchase Probability",
     cpe_data["purchase"],       "avg_cpe_pred", "Avg app_event_p (purchase)",       ".5f", cpe_cmaps["purchase"]),
    ("plot_cpe_retention", "7. CPE — Retention Probability",
     cpe_data["retention"],      "avg_cpe_pred", "Avg app_event_p (retention)",      ".5f", cpe_cmaps["retention"]),
]

# ── Campaign type distribution chart ──────────────────────────────────────────
def build_label_dist_section(campaign_rows):
    """Build a bar chart of total_predictions by campaign_type and post_install_window."""
    if not campaign_rows:
        return "", ""
    # Aggregate
    agg = defaultdict(int)
    for r in campaign_rows:
        ctype  = r.get("campaign_type", "").strip() or "(blank/unset)"
        window = r.get("post_install_window", "").strip() or "?"
        key    = f"{ctype} [{window}]"
        try:
            agg[key] += int(r.get("total_predictions", 0))
        except ValueError:
            pass
    if not agg:
        return "", ""

    labels = sorted(agg.keys())
    values = [agg[k] for k in labels]
    cmap   = make_color_map(labels)

    traces = [{
        "type": "bar",
        "x": labels,
        "y": values,
        "marker": {"color": [cmap.get(l, COLORS[0]) for l in labels]},
        "text": [f"{v:,}" for v in values],
        "textposition": "auto",
        "hovertemplate": "%{x}<br>Predictions: %{y:,}<extra></extra>",
    }]
    layout = {
        "title": {"text": "Label Distribution — Total Predictions by campaign_type × post_install_window",
                  "font": {"color": "#e8eaf0", "size": 14}},
        "paper_bgcolor": "#1a1f2e", "plot_bgcolor": "#12172a",
        "font": {"color": "#e8eaf0", "size": 12},
        "xaxis": {"title": "campaign_type [window]", "tickangle": -30,
                  "gridcolor": "#2a3550", "zerolinecolor": "#3a4a7a"},
        "yaxis": {"title": "Total Predictions", "tickformat": ",.0f",
                  "gridcolor": "#2a3550", "zerolinecolor": "#3a4a7a"},
        "margin": {"t": 60, "b": 120, "l": 90, "r": 30},
        "hovermode": "closest",
        "showlegend": False,
    }
    section_html = '\n<h2>0. Label Distribution — campaign_type × post_install_window</h2>\n'
    section_html += '<div class="plot-wrap"><div id="plot_label_dist" style="height:420px"></div></div>\n'
    js = newplot("plot_label_dist", traces, layout)
    return section_html, js

# ── Highlights & Analysis ─────────────────────────────────────────────────────
def build_highlights(iap_rows, adrev_rows, cpe_rows, cost_rows, campaign_rows, allval_rows):
    cards = []

    def hl_card(title, body, kind="neutral"):
        return f'<div class="hl-card hl-{kind}"><div class="hl-title">{title}</div><div class="hl-body">{body}</div></div>'

    for window, final_col, label in [
        ("d7",  "avg_dep_d7_final",  "IAP D7 Final (dep_d7_final)"),
        ("d28", "avg_dep_d28_final", "IAP D28 Final (dep_d28_final)"),
    ]:
        daily = {}
        for r in iap_rows:
            if r.get("post_install_window", "").strip() != window:
                continue
            d = r.get("submit_date", "")
            try:
                v, c = float(r[final_col]), int(r["start_count"])
                prev = daily.get(d, (0.0, 0))
                daily[d] = (prev[0] + v * c, prev[1] + c)
            except (ValueError, KeyError):
                pass
        if len(daily) < 3:
            continue
        pts = sorted((d, s / c) for d, (s, c) in daily.items() if c > 0)
        dates, vals = zip(*pts)
        peak_v, peak_d = max((v, d) for d, v in pts)
        low_v,  low_d  = min((v, d) for d, v in pts)
        first_v = vals[0]
        last_v  = vals[-1]
        pct_from_start = (last_v - first_v) / first_v * 100 if first_v else 0
        drops = [(vals[i+1] - vals[i], dates[i], dates[i+1]) for i in range(len(vals)-1)]
        worst_drop, d_from, d_to = min(drops, key=lambda x: x[0])
        worst_drop_pct = worst_drop / vals[list(dates).index(d_from)] * 100 if vals[list(dates).index(d_from)] else 0
        kind = "warn" if abs(worst_drop_pct) > 10 or abs(pct_from_start) > 15 else "info"
        lines = [
            f"Range: <strong>{first_v:.3f}</strong> ({dates[0]}) → <strong>{last_v:.3f}</strong> ({dates[-1]}) "
            f"(<strong>{'%+.1f' % pct_from_start}%</strong> overall).",
            f"Peak: <strong>{peak_v:.3f}</strong> on {peak_d}. Low: <strong>{low_v:.3f}</strong> on {low_d}.",
        ]
        if abs(worst_drop_pct) > 5:
            lines.append(
                f"Largest single-day move: <strong>{'%+.3f' % worst_drop} ({'%+.1f' % worst_drop_pct}%)</strong> "
                f"from {d_from} → {d_to}."
            )
        cards.append(hl_card(label, " ".join(lines), kind))

    for window, val_col, label in [
        ("d0",  "avg_adrev_d0_value", "AdRev D0 Value"),
        ("d7",  "avg_adrev_d7_value", "AdRev D7 Value"),
        ("d28", "avg_adrev_value",    "AdRev D28 Value"),
    ]:
        daily = {}
        for r in adrev_rows:
            if r.get("post_install_window", "").strip() != window:
                continue
            d = r.get("submit_date", "")
            try:
                v, c = float(r[val_col]), int(r["start_count"])
                prev = daily.get(d, (0.0, 0))
                daily[d] = (prev[0] + v * c, prev[1] + c)
            except (ValueError, KeyError):
                pass
        if len(daily) < 3:
            continue
        pts = sorted((d, s / c) for d, (s, c) in daily.items() if c > 0)
        dates, vals = zip(*pts)
        first_v, last_v = vals[0], vals[-1]
        peak_v, peak_d = max((v, d) for d, v in pts)
        low_v,  low_d  = min((v, d) for d, v in pts)
        pct = (last_v - first_v) / first_v * 100 if first_v else 0
        drops = [(vals[i+1] - vals[i], dates[i], dates[i+1]) for i in range(len(vals)-1)]
        worst_drop, d_from, d_to = min(drops, key=lambda x: x[0])
        worst_pct = worst_drop / vals[list(dates).index(d_from)] * 100 if vals[list(dates).index(d_from)] else 0
        kind = "warn" if abs(worst_pct) > 10 or abs(pct) > 15 else "info"
        lines = [
            f"Range: <strong>{first_v:.4f}</strong> ({dates[0]}) → <strong>{last_v:.4f}</strong> ({dates[-1]}) "
            f"(<strong>{'%+.1f' % pct}%</strong> overall).",
            f"Peak: <strong>{peak_v:.4f}</strong> on {peak_d}. Low: <strong>{low_v:.4f}</strong> on {low_d}.",
        ]
        if abs(worst_pct) > 5:
            lines.append(
                f"Largest single-day move: <strong>{'%+.4f' % worst_drop} ({'%+.1f' % worst_pct}%)</strong> "
                f"from {d_from} → {d_to}."
            )
        cards.append(hl_card(label, " ".join(lines), kind))

    for etype in ("purchase", "level_complete", "retention"):
        daily = {}
        for r in cpe_rows:
            if r.get("app_event_type", "").strip() != etype:
                continue
            d = r.get("submit_date", "")
            try:
                v, c = float(r["avg_cpe_pred"]), int(r["start_count"])
                prev = daily.get(d, (0.0, 0))
                daily[d] = (prev[0] + v * c, prev[1] + c)
            except (ValueError, KeyError):
                pass
        if len(daily) < 3:
            continue
        pts = sorted((d, s / c) for d, (s, c) in daily.items() if c > 0)
        dates, vals = zip(*pts)
        first_v, last_v = vals[0], vals[-1]
        peak_v, peak_d = max((v, d) for d, v in pts)
        low_v,  low_d  = min((v, d) for d, v in pts)
        pct = (last_v - first_v) / first_v * 100 if first_v else 0
        drops = [(vals[i+1] - vals[i], dates[i], dates[i+1]) for i in range(len(vals)-1)]
        worst_drop, d_from, d_to = min(drops, key=lambda x: x[0])
        worst_pct = worst_drop / vals[list(dates).index(d_from)] * 100 if vals[list(dates).index(d_from)] else 0
        vol_daily = {}
        for r in cpe_rows:
            if r.get("app_event_type", "").strip() != etype:
                continue
            d = r.get("submit_date", "")
            try:
                vol_daily[d] = vol_daily.get(d, 0) + int(r["start_count"])
            except (ValueError, KeyError):
                pass
        peak_vol_d = max(vol_daily, key=vol_daily.get) if vol_daily else ""
        peak_vol   = vol_daily.get(peak_vol_d, 0)
        kind = "warn" if abs(worst_pct) > 10 or abs(pct) > 15 else "info"
        lines = [
            f"Range: <strong>{first_v:.5f}</strong> ({dates[0]}) → <strong>{last_v:.5f}</strong> ({dates[-1]}) "
            f"(<strong>{'%+.1f' % pct}%</strong> overall).",
            f"Peak prob: <strong>{peak_v:.5f}</strong> on {peak_d}. Low: <strong>{low_v:.5f}</strong> on {low_d}.",
        ]
        if abs(worst_pct) > 5:
            lines.append(
                f"Largest single-day move: <strong>{'%+.5f' % worst_drop} ({'%+.1f' % worst_pct}%)</strong> "
                f"from {d_from} → {d_to}."
            )
        if peak_vol_d:
            lines.append(f"Volume peak: <strong>{peak_vol:,}</strong> starts on {peak_vol_d}.")
        cards.append(hl_card(f"CPE — {etype.replace('_',' ').title()} Probability", " ".join(lines), kind))

    # IAP model version transitions
    iap_model_dates = {}
    for r in iap_rows:
        m = r.get("dep_model_version", "").replace("unified-user-value-", "") or "(no version)"
        d = r.get("submit_date", "")
        if m not in iap_model_dates:
            iap_model_dates[m] = [d, d]
        else:
            iap_model_dates[m][0] = min(iap_model_dates[m][0], d)
            iap_model_dates[m][1] = max(iap_model_dates[m][1], d)
    iap_dates = sorted({r.get("submit_date","") for r in iap_rows if r.get("submit_date")})
    iap_first, iap_last = (iap_dates[0], iap_dates[-1]) if iap_dates else ("", "")
    iap_entries = sorted([(m, ds[0]) for m, ds in iap_model_dates.items() if ds[0] > iap_first], key=lambda x: x[1])
    iap_exits   = sorted([(m, ds[1]) for m, ds in iap_model_dates.items() if ds[1] < iap_last],  key=lambda x: x[1])
    if iap_entries or iap_exits:
        lines = []
        if iap_entries:
            lines.append("New IAP model versions entered: " + ", ".join(f"<code>{m}</code> ({d})" for m, d in iap_entries) + ".")
        if iap_exits:
            lines.append("IAP model versions exited: " + ", ".join(f"<code>{m}</code> (last seen {d})" for m, d in iap_exits) + ".")
        cards.append(hl_card("IAP — Model Version Transitions", " ".join(lines), "neutral"))

    # Cost trend
    cost_daily = {}
    for r in cost_rows:
        d = r.get("submit_date","")
        try:
            v, c = float(r["avg_cost"]), int(r["start_count"])
            prev = cost_daily.get(d, (0.0, 0))
            cost_daily[d] = (prev[0] + v * c, prev[1] + c)
        except (ValueError, KeyError):
            pass
    if len(cost_daily) >= 3:
        pts = sorted((d, s / c) for d, (s, c) in cost_daily.items() if c > 0)
        dates, vals = zip(*pts)
        first_v, last_v = vals[0], vals[-1]
        peak_v, peak_d = max((v, d) for d, v in pts)
        low_v,  low_d  = min((v, d) for d, v in pts)
        pct = (last_v - first_v) / first_v * 100 if first_v else 0
        kind = "warn" if abs(pct) > 20 else "neutral"
        cards.append(hl_card(
            "Avg Cost Trend",
            f"Range: <strong>{first_v:,.0f}</strong> ({dates[0]}) → <strong>{last_v:,.0f}</strong> ({dates[-1]}) "
            f"(<strong>{'%+.1f' % pct}%</strong> overall). "
            f"Peak: <strong>{peak_v:,.0f}</strong> on {peak_d}. Low: <strong>{low_v:,.0f}</strong> on {low_d}.",
            kind,
        ))

    if not cards:
        return ""
    grid = "\n".join(cards)
    return f"""
<div class="highlights">
  <h2 style="border-left:4px solid #f0c040;color:#f0c040;margin-top:0">Highlights &amp; Analysis</h2>
  <div class="hl-grid">{grid}</div>
</div>"""

highlights_html = build_highlights(iap_rows, adrev_rows, cpe_rows, cost_rows, campaign_rows, allval_rows)

# ── Label distribution section ─────────────────────────────────────────────────
label_dist_html, label_dist_js = build_label_dist_section(campaign_rows)

# ── Campaign summary section ───────────────────────────────────────────────────
campaign_section = ""
if campaign_rows:
    campaign_section = f"""
<h2>Campaigns for Game {GAME_ID} ({game_name})</h2>
<div class="card">{csv_to_html_table(campaign_rows)}</div>
"""

sections_html = campaign_section + label_dist_html
plots_js = label_dist_js

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
sql_section = f"""
<h2>SQL Queries &amp; Results</h2>
<div class="card">
<h3>Query 0 — Campaign List for Game {GAME_ID}</h3>
<pre><code>{SQL_0}</code></pre>
<h4>Results</h4>
{csv_to_html_table(campaign_rows)}
</div>
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
</div>"""

title_str = f"{game_name} ({platform}) — Game {GAME_ID}"

html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>UV Prediction Report — {title_str}</title>
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
  .highlights {{ background: #12172a; border: 1px solid #3a4a7a; border-radius: 12px; padding: 24px; margin: 24px 0; }}
  .hl-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(380px, 1fr)); gap: 14px; margin-top: 16px; }}
  .hl-card {{ border-radius: 8px; padding: 16px; border-left: 4px solid; }}
  .hl-warn    {{ background: #1f1a10; border-color: #f0a040; }}
  .hl-info    {{ background: #0f1a2a; border-color: #4a9eff; }}
  .hl-neutral {{ background: #151d2a; border-color: #5a7a9a; }}
  .hl-title {{ font-size: 0.95rem; font-weight: 600; margin-bottom: 8px; color: #e8eaf0; }}
  .hl-body  {{ font-size: 0.85rem; color: #a8b8cc; line-height: 1.6; }}
  .hl-body strong {{ color: #e8eaf0; }}
</style>
</head>
<body>
<div class="container">
<h1>UV Model Prediction Report — {title_str}</h1>
<div class="meta">
  Developer: <strong>PLR Worldwide Sales Ltd (Playrix)</strong> &nbsp;|&nbsp;
  Dev ID: <strong>11972</strong> &nbsp;|&nbsp;
  Date range: <strong>{START_DATE} → {END_DATE}</strong> &nbsp;|&nbsp;
  Game: <strong>{GAME_ID}</strong> &nbsp;|&nbsp;
  Campaign: <strong>{CAMPAIGN_ID}</strong>
</div>
{highlights_html}
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
