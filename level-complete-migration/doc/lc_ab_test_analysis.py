"""
A/B Test Analysis: v11-cpe-lc-4 (test) vs ctx1i / bhv1n (control)
Event type: level_complete (LC)

Expected input: lc_df_all — pandas DataFrame with columns produced by the BQ query.
Run via run_analysis.py (fetches BQ data automatically) or from a Jupyter notebook.
"""

import pandas as pd
import numpy as np
from scipy import stats
import warnings
warnings.filterwarnings("ignore")

pd.set_option("display.width", 160)

# ── 0. Tidy up ────────────────────────────────────────────────────────────────

df = lc_df_all.copy()
df = df[df["app_event_model_version"].notna()].copy()
df["submit_date"] = pd.to_datetime(df["submit_date"])

MODEL_TEST  = "v11-cpe-lc"
MODELS_CTRL = ["ctx1i", "bhv1n"]

df["group"] = df["app_event_model_version"].apply(
    lambda v: "test"    if v == MODEL_TEST else
              "control" if v in MODELS_CTRL else "other"
)

# Detect whether target event columns are present (requires the updated query)
HAS_TARGET = "sum_target_event_d0" in df.columns

# ── 1. Derived metrics ────────────────────────────────────────────────────────

SUM_COLS = [
    "starts", "installs",
    "sum_pred", "sum_pred_installs", "sum_tcpe", "sum_cost", "sum_campaign_spend",
    "sum_lc_label_d0", "sum_lc_label_d1", "sum_lc_label_d3", "sum_lc_label_d7",
    "sum_lc_count_d0", "sum_lc_count_d1", "sum_lc_count_d3", "sum_lc_count_d7",
]
if HAS_TARGET:
    SUM_COLS += [
        "sum_target_event_d0", "sum_target_event_d1",
        "sum_target_event_d3", "sum_target_event_d7",
    ]

def add_derived(agg: pd.DataFrame) -> pd.DataFrame:
    a = agg.copy()

    # Per-start averages
    a["avg_pred"] = a["sum_pred"] / a["starts"]
    a["avg_tcpe"] = a["sum_tcpe"] / a["starts"]
    a["avg_cost"] = a["sum_cost"] / a["starts"]

    # Install rate
    a["install_rate"] = a["installs"] / a["starts"]

    # Generic LC event rates (any level complete, per install)
    for d in ["d0", "d1", "d3", "d7"]:
        installs_safe = a["installs"].replace(0, np.nan)
        a[f"er_{d}"]  = a[f"sum_lc_label_{d}"] / installs_safe   # binary ER
        a[f"epc_{d}"] = a[f"sum_lc_count_{d}"]  / installs_safe  # events per install

    # Target event rate: fraction of installs where the campaign-targeted
    # SDK event was fired (mirrors prob_sdk_event_name_label in datagen).
    # Wildcard campaigns use the generic lc_label, specific campaigns require
    # the exact targeted event.
    if HAS_TARGET:
        for d in ["d0", "d1", "d3", "d7"]:
            installs_safe = a["installs"].replace(0, np.nan)
            a[f"target_er_{d}"] = a[f"sum_target_event_{d}"] / installs_safe

    # ── General model bias Dx ─────────────────────────────────────────────────
    # Uses sum_pred_installs (predictions summed over installing auctions only),
    # so numerator and denominator are on the same install population.
    #
    #   bias_generic_dx = (sum_pred_installs / sum_lc_label_dx) - 1
    #
    # sum_pred_installs = Σ pred_i for auctions that resulted in installs
    # sum_lc_label_dx   = number of installs with ≥1 LC event by day X (binary)
    # Both are counts over the install population — no averaging distortion.
    # >0 = model over-predicts; <0 = under-predicts
    # At D7 (fully mature label): should approach 0 for a well-calibrated model.
    #
    # Fallback to avg_pred / er_d0 if sum_pred_installs not available
    # (e.g., loading from a CSV produced by an older query).
    has_pred_installs = "sum_pred_installs" in a.columns
    for d in ["d0", "d1", "d3", "d7"]:
        label_safe = a[f"sum_lc_label_{d}"].replace(0, np.nan)
        if has_pred_installs:
            a[f"bias_generic_{d}"] = a["sum_pred_installs"] / label_safe - 1
        else:
            er_safe = a[f"er_{d}"].replace(0, np.nan)
            a[f"bias_generic_{d}"] = a["avg_pred"] / er_safe - 1  # legacy fallback

    # Legacy aliases
    a["bias_abs"]   = a["avg_pred"] - a["er_d0"]
    a["bias_ratio"] = a["bias_generic_d0"]

    # ── Target model bias Dx ──────────────────────────────────────────────────
    # Same sum-based approach: sum_pred_installs vs campaign-specific binary count.
    #
    #   bias_target_dx = (sum_pred_installs / sum_target_event_dx) - 1
    if HAS_TARGET:
        for d in ["d0", "d1", "d3", "d7"]:
            target_safe = a[f"sum_target_event_{d}"].replace(0, np.nan)
            if has_pred_installs:
                a[f"bias_target_{d}"] = a["sum_pred_installs"] / target_safe - 1
            else:
                ter_safe = a[f"target_er_{d}"].replace(0, np.nan)
                a[f"bias_target_{d}"] = a["avg_pred"] / ter_safe - 1  # legacy fallback
        # Legacy aliases
        a["bias_vs_target_abs"]   = a["avg_pred"] - a["target_er_d0"]
        a["bias_vs_target_ratio"] = a["bias_target_d0"]

    # ── Actual CPE (binary label — installs with ≥1 event) ────────────────────
    for d in ["d0", "d1", "d3", "d7"]:
        events_safe = a[f"sum_lc_label_{d}"].replace(0, np.nan)
        a[f"actual_cpe_{d}"] = a["sum_cost"] / events_safe

    # Target event CPE (cost per targeted-event conversion, binary)
    if HAS_TARGET:
        for d in ["d0", "d1", "d3", "d7"]:
            events_safe = a[f"sum_target_event_{d}"].replace(0, np.nan)
            a[f"target_cpe_{d}"] = a["sum_cost"] / events_safe

    # ── Product bias (CPE bias) Dx ────────────────────────────────────────────
    # Observed CPE Dx = Spend / cumulative LC event count by day X
    #   (uses sum_lc_count_dx — total events, not just binary flag)
    # Product bias Dx = (Observed CPE Dx / Avg Target CPE) - 1
    #   >0 = spending more per event than the advertiser's target (overspend)
    #   <0 = spending less (underspend — leaving money on the table)
    tcpe_safe = a["avg_tcpe"].replace(0, np.nan)
    for d in ["d1", "d3", "d7"]:
        count_safe = a[f"sum_lc_count_{d}"].replace(0, np.nan)
        a[f"cpe_count_{d}"]     = a["sum_cost"] / count_safe
        a[f"product_bias_{d}"]  = a[f"cpe_count_{d}"] / tcpe_safe - 1

    # CPE efficiency d0 (legacy: target / actual, >1 = underspending)
    a["cpe_efficiency_d0"] = a["avg_tcpe"] / a["actual_cpe_d0"]

    return a


# ── 2. Overall test vs control ────────────────────────────────────────────────

overall = (
    df.groupby("group")[SUM_COLS].sum()
    .pipe(add_derived)
)

def fmt(v):
    if not isinstance(v, (int, float)) or (isinstance(v, float) and np.isnan(v)):
        return str(v)
    if abs(v) >= 1e9:   return f"{v:,.0f}"
    if abs(v) >= 1e3:   return f"{v:,.2f}"
    return f"{v:.5f}"

print("=" * 82)
print("OVERALL SUMMARY  (full date range, test vs control)")
print("=" * 82)

sections = {
    "--- Volume ---": [
        ("Starts",       "starts"),
        ("Installs",     "installs"),
        ("Install Rate", "install_rate"),
    ],
    "--- Spend ---": [
        ("Sum Cost",               "sum_cost"),
        ("Sum Campaign Spend",     "sum_campaign_spend"),
        ("Avg Cost / Start",       "avg_cost"),
        ("Avg Target CPE",         "avg_tcpe"),
    ],
    "--- Generic LC Event Rates (any LC, per install) ---": [
        ("ER d0", "er_d0"),
        ("ER d1", "er_d1"),
        ("ER d3", "er_d3"),
        ("ER d7", "er_d7"),
    ],
    "--- Events Per Install (cumulative count) ---": [
        ("EPC d0", "epc_d0"),
        ("EPC d1", "epc_d1"),
        ("EPC d3", "epc_d3"),
        ("EPC d7", "epc_d7"),
    ],
}

# Target event rates only if data is present
if HAS_TARGET:
    sections["--- Target Event Rate (campaign-specific SDK event, per install) ---"] = [
        ("Target ER d0", "target_er_d0"),
        ("Target ER d1", "target_er_d1"),
        ("Target ER d3", "target_er_d3"),
        ("Target ER d7", "target_er_d7"),
    ]

sections["--- General Model Bias Dx = (avg_pred / generic_er_dx) - 1 ---"] = [
    ("Avg Pred (D7 prediction)",  "avg_pred"),
    ("Generic ER d0",             "er_d0"),
    ("General Bias d0",           "bias_generic_d0"),
    ("Generic ER d1",             "er_d1"),
    ("General Bias d1",           "bias_generic_d1"),
    ("Generic ER d3",             "er_d3"),
    ("General Bias d3",           "bias_generic_d3"),
    ("Generic ER d7 (*immature)", "er_d7"),
    ("General Bias d7 (*immature)","bias_generic_d7"),
]
if HAS_TARGET:
    sections["--- Target Model Bias Dx = (avg_pred / target_er_dx) - 1 ---"] = [
        ("Target ER d0",       "target_er_d0"),
        ("Target Bias d0",     "bias_target_d0"),
        ("Target ER d1",       "target_er_d1"),
        ("Target Bias d1",     "bias_target_d1"),
        ("Target ER d3",       "target_er_d3"),
        ("Target Bias d3",     "bias_target_d3"),
    ]
sections["--- Product Bias Dx = (obs_cpe_dx / avg_tcpe) - 1 ---"] = [
    ("Avg Target CPE",       "avg_tcpe"),
    ("Obs CPE d1 (count)",   "cpe_count_d1"),
    ("Product Bias d1",      "product_bias_d1"),
    ("Obs CPE d3 (count)",   "cpe_count_d3"),
    ("Product Bias d3",      "product_bias_d3"),
    ("Obs CPE d7 (*immature)","cpe_count_d7"),
    ("Product Bias d7 (*imm.)","product_bias_d7"),
]

sections["--- Actual CPE (generic LC) ---"] = [
    ("Actual CPE d0",                     "actual_cpe_d0"),
    ("Actual CPE d1",                     "actual_cpe_d1"),
    ("Actual CPE d3",                     "actual_cpe_d3"),
    ("Actual CPE d7",                     "actual_cpe_d7"),
    ("CPE Efficiency d0 (target/actual)", "cpe_efficiency_d0"),
]
if HAS_TARGET:
    sections["--- Actual CPE (targeted event) ---"] = [
        ("Target Actual CPE d0", "target_cpe_d0"),
        ("Target Actual CPE d1", "target_cpe_d1"),
        ("Target Actual CPE d3", "target_cpe_d3"),
        ("Target Actual CPE d7", "target_cpe_d7"),
    ]

rows = []
for section, metrics in sections.items():
    rows.append({"Metric": section, "test": "", "control": "", "delta % (T/C-1)": ""})
    for label, col in metrics:
        t = overall.loc["test",    col] if "test"    in overall.index else np.nan
        c = overall.loc["control", col] if "control" in overall.index else np.nan
        try:
            d = (t / c - 1) * 100 if (c and c != 0) else np.nan
        except Exception:
            d = np.nan
        rows.append({
            "Metric"         : f"  {label}",
            "test"           : fmt(t),
            "control"        : fmt(c),
            "delta % (T/C-1)": f"{d:+.2f}%" if (isinstance(d, float) and not np.isnan(d)) else "",
        })

print(pd.DataFrame(rows).to_string(index=False))


# ── 3. Statistical significance ───────────────────────────────────────────────

print("\n" + "=" * 82)
print("STATISTICAL SIGNIFICANCE — two-proportion z-test")
print("=" * 82)

def prop_ztest(n1, k1, n2, k2, label=""):
    p1, p2 = k1 / n1, k2 / n2
    p_pool = (k1 + k2) / (n1 + n2)
    se = np.sqrt(p_pool * (1 - p_pool) * (1/n1 + 1/n2))
    z  = (p1 - p2) / se
    p  = 2 * (1 - stats.norm.cdf(abs(z)))
    sig = "***" if p < 0.001 else "**" if p < 0.01 else "*" if p < 0.05 else "ns"
    print(f"  {label:<38}  test={p1:.5f}  ctrl={p2:.5f}  delta={p1-p2:+.5f}  z={z:+.2f}  p={p:.4f}  {sig}")

if "test" in overall.index and "control" in overall.index:
    t, c = overall.loc["test"], overall.loc["control"]

    print("\nInstall rate (installs / starts):")
    prop_ztest(int(t["starts"]), int(t["installs"]),
               int(c["starts"]), int(c["installs"]), "Install rate")

    print("\nGeneric LC event rate (any level complete):")
    for d in ["d0", "d1", "d3", "d7"]:
        prop_ztest(int(t["installs"]), int(t[f"sum_lc_label_{d}"]),
                   int(c["installs"]), int(c[f"sum_lc_label_{d}"]),
                   label=f"Generic ER {d}")

    if HAS_TARGET:
        print("\nTarget event rate (campaign-specific SDK event):")
        for d in ["d0", "d1", "d3", "d7"]:
            prop_ztest(int(t["installs"]), int(t[f"sum_target_event_{d}"]),
                       int(c["installs"]), int(c[f"sum_target_event_{d}"]),
                       label=f"Target ER {d}")


# ── 4. Per-model breakdown ────────────────────────────────────────────────────

print("\n" + "=" * 82)
print("PER-MODEL BREAKDOWN")
print("=" * 82)

per_model = (
    df.groupby("app_event_model_version")[SUM_COLS].sum()
    .pipe(add_derived)
)

key_metrics = [
    "starts", "installs", "install_rate",
    "sum_cost", "sum_campaign_spend", "avg_cost", "avg_tcpe",
    "er_d0", "er_d1", "er_d3", "er_d7",
]
if HAS_TARGET:
    key_metrics += ["target_er_d0", "target_er_d1", "target_er_d3", "target_er_d7"]
key_metrics += [
    "avg_pred",
    "bias_generic_d0", "bias_generic_d1", "bias_generic_d3", "bias_generic_d7",
]
if HAS_TARGET:
    key_metrics += ["bias_target_d0", "bias_target_d1", "bias_target_d3", "bias_target_d7"]
key_metrics += [
    "actual_cpe_d0", "actual_cpe_d1", "cpe_efficiency_d0",
    "cpe_count_d1", "cpe_count_d3", "cpe_count_d7",
    "product_bias_d1", "product_bias_d3", "product_bias_d7",
]
if HAS_TARGET:
    key_metrics += ["target_cpe_d0", "target_cpe_d1"]

print(per_model[key_metrics].T.to_string(
    float_format=lambda x: f"{x:.5f}" if abs(x) < 1e6 else f"{x:,.0f}"
))


# ── 5. Daily trends ───────────────────────────────────────────────────────────

print("\n" + "=" * 82)
print("DAILY TRENDS")
print("=" * 82)

daily = (
    df.groupby(["submit_date", "app_event_model_version"])[SUM_COLS].sum()
    .pipe(add_derived)
    .reset_index()
)

trend_metrics = [
    ("starts",           "Starts",                              "{:.0f}"),
    ("installs",         "Installs",                             "{:.0f}"),
    ("install_rate",     "Install Rate",                         "{:.5f}"),
    ("er_d0",            "Generic ER d0 (any LC, cumul.)",       "{:.5f}"),
    ("er_d1",            "Generic ER d1 (cumul.)",               "{:.5f}"),
    ("sum_cost",         "Daily Cost",                           "{:,.0f}"),
    ("bias_generic_d0",  "General Bias d0 (pred/er_d0-1)",       "{:.4f}"),
    ("bias_generic_d1",  "General Bias d1 (pred/er_d1-1)",       "{:.4f}"),
    ("product_bias_d1",  "Product Bias d1 (CPE_d1/tcpe-1)",      "{:.4f}"),
    ("product_bias_d3",  "Product Bias d3 (CPE_d3/tcpe-1)",      "{:.4f}"),
]
if HAS_TARGET:
    trend_metrics += [
        ("target_er_d0",    "Target ER d0 (specific event)",    "{:.5f}"),
        ("target_er_d1",    "Target ER d1",                     "{:.5f}"),
        ("bias_target_d0",  "Target Bias d0 (pred/tgt_er_d0-1)", "{:.4f}"),
        ("bias_target_d1",  "Target Bias d1",                   "{:.4f}"),
    ]

for metric, label, ffmt in trend_metrics:
    pivot = daily.pivot(index="submit_date", columns="app_event_model_version", values=metric)
    print(f"\n{label}:")
    print(pivot.to_string(float_format=lambda x, f=ffmt: f.format(x)))


# ── 6. Bias summary ───────────────────────────────────────────────────────────
#
# Three bias types:
#
#  1. GENERAL MODEL BIAS Dx  = (avg_pred / er_dx) - 1
#     Model predicts p(LC by D7 | install). Comparing vs observed cumulative
#     ER at D0/D1/D3/D7 shows how calibration improves as the label matures.
#     At D7 (fully mature): should ≈ 0 for a well-calibrated model.
#
#  2. TARGET MODEL BIAS Dx   = (avg_pred / target_er_dx) - 1
#     Same, but denominator is the campaign-specific SDK event rate.
#     Most accurate calibration check: model was trained on
#     prob_sdk_event_name_label (specific event, D7 label).
#
#  3. PRODUCT BIAS (CPE BIAS) Dx  = (Observed CPE Dx / Avg Target CPE) - 1
#     Observed CPE Dx = sum_cost / sum_lc_count_dx (cumulative event count)
#     >0 = overspending vs advertiser target CPE
#     <0 = underspending

print("\n" + "=" * 82)
print("MODEL BIAS SUMMARY")
print("=" * 82)

src = "sum_pred_installs" if has_pred_installs else "avg_pred (fallback)"
print(f"\n--- 1. General Model Bias Dx = ({src} / sum_lc_label_dx) - 1 ---")
print(f"  {src} = sum of predictions for installing auctions only")
print("  sum_lc_label_dx = installs with ≥1 LC event on day X (same population)")
print("  At D7 (mature label) this should approach 0.\n")
gbias_cols = ["starts", "installs", "avg_pred"]
for d in ["d0", "d1", "d3", "d7"]:
    gbias_cols += [f"er_{d}", f"bias_generic_{d}"]
gbias = per_model[gbias_cols].copy()
for d in ["d0", "d1", "d3", "d7"]:
    gbias[f"bias_generic_{d}_%"] = gbias[f"bias_generic_{d}"] * 100
print(gbias[[c for c in gbias.columns if c not in [f"bias_generic_{d}" for d in ["d0","d1","d3","d7"]]]
           ].to_string(float_format=lambda x: f"{x:.5f}" if abs(x) < 1e4 else f"{x:,.0f}"))

if HAS_TARGET:
    print(f"\n--- 2. Target Model Bias Dx = ({src} / sum_target_event_dx) - 1 ---")
    print("  sum_target_event_dx = installs where campaign-specific SDK event fired")
    print("  Most accurate calibration: model trained on prob_sdk_event_name_label.\n")
    tbias_cols = ["avg_pred"]
    for d in ["d0", "d1", "d3", "d7"]:
        tbias_cols += [f"target_er_{d}", f"bias_target_{d}"]
    tbias = per_model[tbias_cols].copy()
    for d in ["d0", "d1", "d3", "d7"]:
        tbias[f"bias_target_{d}_%"] = tbias[f"bias_target_{d}"] * 100
    print(tbias[[c for c in tbias.columns if c not in [f"bias_target_{d}" for d in ["d0","d1","d3","d7"]]]
               ].to_string(float_format=lambda x: f"{x:.5f}" if abs(x) < 1e4 else f"{x:,.0f}"))

print("\n--- 3. Product Bias (CPE Bias) Dx = (Observed CPE Dx / Avg Target CPE) - 1 ---")
print("  Observed CPE Dx = sum_cost / sum_lc_count_dx  (cumulative LC event count)")
print("  >0 = overspend vs advertiser target,  <0 = underspend\n")
pbias_cols = ["avg_tcpe"]
for d in ["d1", "d3", "d7"]:
    pbias_cols += [f"cpe_count_{d}", f"product_bias_{d}"]
pbias = per_model[pbias_cols].copy()
for d in ["d1", "d3", "d7"]:
    pbias[f"product_bias_{d}_%"] = pbias[f"product_bias_{d}"] * 100
print(pbias[[c for c in pbias.columns if c not in [f"product_bias_{d}" for d in ["d1","d3","d7"]]]
           ].to_string(float_format=lambda x: f"{x:.5f}" if abs(x) < 1e6 else f"{x:,.0f}"))


# ── 7. Data maturity by install date ──────────────────────────────────────────
#
# lc_label_dX and target_event_dX are CUMULATIVE binary labels:
#   lc_label_d0 = 1 if any LC event by day 0
#   lc_label_d7 = 1 if any LC event by day 7 post-install
#
# A label is only reliable once the post-install window has closed.
# Required days of post-install data (= window + processing lag):
#   d0: 1 day   d1: 2 days   d3: 4 days   d7: 9 days
#
# Installs from recent dates will have artificially low dX ERs because
# the cumulative label hasn't had time to populate — this explains why
# d7 ER < d0 ER in aggregate: the recent cohorts drag d7 down.

print("\n" + "=" * 82)
print("DATA MATURITY BY INSTALL DATE")
print("=" * 82)
print("  Labels are CUMULATIVE: lc_label_d7 = 'any LC by day 7'.")
print("  d7 < d0 in aggregate is a data-truncation artifact — recent cohorts")
print("  have not yet accumulated 7 days of post-install data.")
print("  Maturity thresholds (days since install needed for reliable label):")
print("    d0: 1 day  |  d1: 2 days  |  d3: 4 days  |  d7: 9 days\n")

TODAY = pd.Timestamp.now(tz="UTC").normalize().tz_localize(None)

# Per-date, per-group totals
date_group = (
    df.groupby(["submit_date", "group"])[SUM_COLS].sum()
    .pipe(add_derived)
    .reset_index()
)

MATURITY_DAYS = {"d0": 1, "d1": 2, "d3": 4, "d7": 9}

maturity_rows = []
for _, row in date_group.iterrows():
    days_since = (TODAY - row["submit_date"]).days
    mrow = {
        "install_date": row["submit_date"].date(),
        "group": row["group"],
        "starts": int(row["starts"]),
        "installs": int(row["installs"]),
        "install_rate": row["install_rate"],
    }
    for d, thresh in MATURITY_DAYS.items():
        mature = "✓" if days_since >= thresh else f"~{days_since}d/{thresh}d"
        mrow[f"er_{d}"] = row[f"er_{d}"]
        mrow[f"er_{d}_mature"] = mature
        if HAS_TARGET:
            mrow[f"target_er_{d}"] = row[f"target_er_{d}"]
    maturity_rows.append(mrow)

mat_df = pd.DataFrame(maturity_rows)

for grp in ["test", "control"]:
    sub = mat_df[mat_df["group"] == grp].copy()
    if sub.empty:
        continue
    print(f"\n--- {grp.upper()} ---")
    disp_cols = ["install_date", "starts", "installs", "install_rate"]
    for d in ["d0", "d1", "d3", "d7"]:
        disp_cols += [f"er_{d}", f"er_{d}_mature"]
    print(sub[disp_cols].to_string(
        index=False,
        float_format=lambda x: f"{x:.5f}" if isinstance(x, float) else str(x),
    ))

if HAS_TARGET:
    print("\n--- TARGET ER BY INSTALL DATE (test vs control) ---")
    for d in ["d0", "d1", "d3", "d7"]:
        thresh = MATURITY_DAYS[d]
        pivot = mat_df.pivot(index="install_date", columns="group", values=f"target_er_{d}")
        days_since_col = (TODAY - pd.to_datetime(pivot.index)).days
        mature_mask = days_since_col >= thresh
        print(f"\nTarget ER {d}  (need install_date + {thresh} days; ✓ = mature):")
        disp = pivot.copy().astype(object)
        for i, (idx, is_mature) in enumerate(zip(pivot.index, mature_mask)):
            suffix = "  ✓" if is_mature else f"  ~{days_since_col[i]}d"
            for col in disp.columns:
                disp.loc[idx, col] = f"{pivot.loc[idx, col]:.5f}{suffix}"
        print(disp.to_string())
        # Aggregate over mature dates only
        mature_sub = date_group[
            (TODAY - date_group["submit_date"]).dt.days >= thresh
        ]
        if not mature_sub.empty:
            mat_agg = mature_sub.groupby("group")[SUM_COLS].sum().pipe(add_derived)
            t_er = mat_agg.loc["test",    f"target_er_{d}"] if "test"    in mat_agg.index else np.nan
            c_er = mat_agg.loc["control", f"target_er_{d}"] if "control" in mat_agg.index else np.nan
            delta = (t_er / c_er - 1) * 100 if (not np.isnan(c_er) and c_er != 0) else np.nan
            n_dates = (TODAY - date_group["submit_date"]).dt.days.ge(thresh).sum() // max(date_group["app_event_model_version"].nunique(), 1)
            print(f"  → Mature-cohort aggregate:  test={t_er:.5f}  ctrl={c_er:.5f}  delta={delta:+.2f}%")
