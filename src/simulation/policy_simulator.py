"""Baho Neza policy simulator: decision-support scenarios on precomputed household tables.

Inputs (data/processed only, never raw .dta files):
- household_master.parquet (notebook 06), household_cpi_shock.parquet (notebook 07)
- household_scores.parquet (src/models/score_households.py): out-of-sample poverty-model and VUP-gap scores

Every population total is survey-weighted: households with `weight`, people with `pop_wt`.

What these numbers are: static, first-round accounting estimates of who a rule would reach and what it would
cost, using EICV7 2023/24 households as they were surveyed. They assume no behavioural response, no change in
eligibility rules and no targeting error beyond what the scores themselves contain. They are NOT estimates of
causal poverty reduction, and the model scores must not be used to select or exclude individual beneficiaries.

Scenarios:
1. coverage_expansion: add X percentage points of national households to VUP Direct Support, taken from households
   with no VUP component, prioritised by poverty-model score then distress score.
2. targeting: select the top k% of households by poverty-model score.
3. benefit_increase: raise the NSDS quarterly payment by X% for currently covered households.
4. protection_gap: in the n districts with the most uncovered high-need households, newly cover X% of each district's
   high-need households (taken from the uncovered, by the same priority order).
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PROCESSED = PROJECT_ROOT / "data" / "processed"
SCENARIO_PATH = PROCESSED / "scenario_results.parquet"

# NSDS programme rate: 10,000 RWF a month paid quarterly, 30,500 RWF per quarter including 500 RWF bank fees
# (EICV7 instruction manual, PDF p. 112 / printed p. 110). Survey: weighted median 30,000 RWF among NSDS recipients.
PAYMENT_QUARTERLY_RWF = 30_500
QUARTERS_PER_YEAR = 4
LABEL = "Decision-support estimate (EICV7 2023/24, survey-weighted); not a causal impact or an eligibility decision"

FRAME_COLUMNS = ["hhid", "clust", "strata_id", "province_name", "district_name", "area", "weight", "pop_wt", "hh_size",
                 "poor", "extreme_poor", "main_livelihood", "vup_any", "vup_direct_support", "vup_nsds",
                 "vup_nsds_quarterly_payment", "vup_nsds_quarters_paid_12m", "share_food", "head_female"]
SHOCK_COLUMNS = ["hhid", "distress_score", "distress_score_excl_vup", "distress_quintile_excl_vup", "price_change_pct"]
LIVELIHOOD_LABELS = {"own_farming": "Own farming", "farm_wage": "Farm wage work", "nonfarm_wage": "Non-farm wage work",
                     "nonfarm_self_employment": "Non-farm self-employment", "no_employed_member": "No employed member"}


# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------
def load_simulation_frame(processed: Path = PROCESSED) -> pd.DataFrame:
    """One row per household with the columns the scenarios need (from data/processed only)."""
    master = pd.read_parquet(processed / "household_master.parquet", columns=FRAME_COLUMNS)
    shock = pd.read_parquet(processed / "household_cpi_shock.parquet", columns=SHOCK_COLUMNS)
    scores = pd.read_parquet(processed / "household_scores.parquet", columns=["hhid", "poverty_score", "high_need", "vup_coverage_score"])
    df = master.merge(shock, on="hhid", validate="1:1").merge(scores, on="hhid", validate="1:1")
    df["income_source"] = df["main_livelihood"].map(LIVELIHOOD_LABELS)
    for c in ["poor", "extreme_poor", "vup_any", "vup_direct_support", "vup_nsds", "high_need", "head_female"]:
        df[c] = df[c].astype(float)
    assert df["hhid"].is_unique and df["poverty_score"].notna().all()
    return df


# ---------------------------------------------------------------------------
# Allocation
# ---------------------------------------------------------------------------
def priority_order(df: pd.DataFrame) -> pd.Index:
    """Households in priority order: poverty-model score (high first), then distress score, then hhid (deterministic)."""
    return df.sort_values(["poverty_score", "distress_score", "hhid"], ascending=[False, False, True]).index


def allocate(df: pd.DataFrame, pool: pd.Series, budget_households: float) -> pd.Series:
    """Inclusion share (0-1) per household when `budget_households` weighted households are taken from `pool`
    in priority order. The household that crosses the budget is included fractionally, so totals are exact."""
    inc = pd.Series(0.0, index=df.index)
    if budget_households <= 0:
        return inc
    order = priority_order(df)
    order = order[pool.loc[order].to_numpy(bool)]
    w = df.loc[order, "weight"].to_numpy()
    before = np.concatenate([[0.0], np.cumsum(w)[:-1]])
    share = np.clip((budget_households - before) / w, 0.0, 1.0)
    inc.loc[order] = share
    return inc


def _sums(df: pd.DataFrame, inc: pd.Series) -> dict:
    w, pw = df["weight"] * inc, df["pop_wt"] * inc
    return {"households": w.sum(), "people": pw.sum(), "poor_households": (w * df["poor"]).sum(),
            "poor_people": (pw * df["poor"]).sum(), "high_need_households": (w * df["high_need"]).sum()}


def breakdown(df: pd.DataFrame, inc: pd.Series, by: str) -> pd.DataFrame:
    """Selected households, poor reached, precision and recall within each group (weighted)."""
    d = df.assign(_w=df["weight"] * inc, _pw=df["pop_wt"] * inc)
    g = d.groupby(by)
    out = pd.DataFrame({
        "sample_households": g.size(),
        "households": g["weight"].sum(),
        "selected_households": g["_w"].sum(),
        "poor_households": g.apply(lambda x: (x["weight"] * x["poor"]).sum()),
        "poor_households_reached": g.apply(lambda x: (x["_w"] * x["poor"]).sum()),
        "poor_people": g.apply(lambda x: (x["pop_wt"] * x["poor"]).sum()),
        "poor_people_reached": g.apply(lambda x: (x["_pw"] * x["poor"]).sum()),
    })
    out["selection_rate"] = out["selected_households"] / out["households"]
    out["precision"] = out["poor_households_reached"] / out["selected_households"].where(out["selected_households"] > 0)
    out["recall_households"] = out["poor_households_reached"] / out["poor_households"].where(out["poor_households"] > 0)
    out["recall_people"] = out["poor_people_reached"] / out["poor_people"].where(out["poor_people"] > 0)
    out["share_of_selection"] = out["selected_households"] / out["selected_households"].sum()
    return out


# ---------------------------------------------------------------------------
# 1. Coverage expansion (VUP Direct Support)
# ---------------------------------------------------------------------------
def coverage_expansion(df: pd.DataFrame, increase_pp: float, payment_quarterly: float = PAYMENT_QUARTERLY_RWF,
                       pool: str = "no_vup") -> dict:
    """Add `increase_pp` percentage points of all households to Direct Support.

    pool="no_vup": new beneficiaries come from households with no VUP component (default);
    pool="no_direct_support": from households not yet in Direct Support.
    """
    total_hh = df["weight"].sum()
    eligible = df["vup_any"].eq(0) if pool == "no_vup" else df["vup_direct_support"].eq(0)
    budget = increase_pp / 100 * total_hh
    inc = allocate(df, eligible, budget)
    s = _sums(df, inc)
    uncovered_hn = df["high_need"].eq(1) & df["vup_any"].eq(0)
    before = (df["weight"] * uncovered_hn).sum()
    reached_hn_uncovered = (df["weight"] * inc * uncovered_hn).sum()
    ds_before = (df["weight"] * df["vup_direct_support"]).sum()
    nat = {
        "increase_pp": increase_pp, "pool": pool, "payment_quarterly_rwf": payment_quarterly,
        "budget_households": budget, "households_added": s["households"], "people_added": s["people"],
        "capped_by_pool": s["households"] < budget - 1e-6,
        "poor_households_added": s["poor_households"], "poor_people_added": s["poor_people"],
        "precision_poor": s["poor_households"] / s["households"] if s["households"] else np.nan,
        "high_need_households_added": s["high_need_households"],
        "direct_support_coverage_before": ds_before / total_hh,
        "direct_support_coverage_after": (ds_before + s["households"]) / total_hh,
        "uncovered_high_need_before": before, "uncovered_high_need_after": before - reached_hn_uncovered,
        "uncovered_high_need_reduction_pct": 100 * reached_hn_uncovered / before if before else np.nan,
        "additional_quarterly_transfer_rwf": s["households"] * payment_quarterly,
        "additional_annual_transfer_rwf": s["households"] * payment_quarterly * QUARTERS_PER_YEAR,
    }
    d = df.assign(_new=df["weight"] * inc, _new_hn=df["weight"] * inc * uncovered_hn, _unc=df["weight"] * uncovered_hn)
    by = d.groupby(["district_name", "area"]).agg(sample_households=("hhid", "size"), households=("weight", "sum"),
                                                   households_added=("_new", "sum"), uncovered_high_need_before=("_unc", "sum"),
                                                   uncovered_high_need_reached=("_new_hn", "sum")).reset_index()
    by["uncovered_high_need_after"] = by["uncovered_high_need_before"] - by["uncovered_high_need_reached"]
    by["additional_quarterly_transfer_rwf"] = by["households_added"] * payment_quarterly
    return {"national": nat, "by_district_area": by, "inclusion": inc}


# ---------------------------------------------------------------------------
# 2. Targeting simulation
# ---------------------------------------------------------------------------
def targeting(df: pd.DataFrame, k: float) -> dict:
    """Select the top `k` share (0-1) of weighted households by poverty-model score (ties: distress score)."""
    inc = allocate(df, pd.Series(True, index=df.index), k * df["weight"].sum())
    s = _sums(df, inc)
    poor_hh = (df["weight"] * df["poor"]).sum()
    poor_people = (df["pop_wt"] * df["poor"]).sum()
    nat = {"k": k, "selected_households": s["households"], "selected_people": s["people"],
           "poor_households_reached": s["poor_households"], "poor_people_reached": s["poor_people"],
           "precision": s["poor_households"] / s["households"], "recall_households": s["poor_households"] / poor_hh,
           "recall_people": s["poor_people"] / poor_people, "non_poor_selected": s["households"] - s["poor_households"],
           "poor_households_missed": poor_hh - s["poor_households"]}
    return {"national": nat, "by_district": breakdown(df, inc, "district_name"), "by_area": breakdown(df, inc, "area"),
            "by_income_source": breakdown(df, inc, "income_source"), "inclusion": inc}


# ---------------------------------------------------------------------------
# 3. Benefit-level simulation (NSDS)
# ---------------------------------------------------------------------------
def benefit_increase(df: pd.DataFrame, increase_pct: float) -> dict:
    """Additional transfer value if the NSDS quarterly payment of currently covered households rises by `increase_pct`%."""
    cov = df["vup_nsds"].eq(1)
    w = df["weight"] * cov
    pay = df["vup_nsds_quarterly_payment"].fillna(0)
    quarters = df["vup_nsds_quarters_paid_12m"].clip(upper=QUARTERS_PER_YEAR).fillna(0)
    current_q = (w * pay).sum()
    add_q = current_q * increase_pct / 100
    return {"increase_pct": increase_pct, "covered_households": w.sum(), "covered_people": (df["pop_wt"] * cov).sum(),
            "covered_poor_people": (df["pop_wt"] * cov * df["poor"]).sum(),
            "current_quarterly_transfer_rwf": current_q, "additional_quarterly_transfer_rwf": add_q,
            "additional_annual_transfer_rwf_4_quarters": add_q * QUARTERS_PER_YEAR,
            "additional_annual_transfer_rwf_observed_quarters": (w * pay * quarters).sum() * increase_pct / 100,
            "mean_quarterly_payment_rwf": current_q / w.sum() if w.sum() else np.nan,
            "additional_per_household_quarterly_rwf": (current_q / w.sum()) * increase_pct / 100 if w.sum() else np.nan}


# ---------------------------------------------------------------------------
# 4. Protection-gap simulation
# ---------------------------------------------------------------------------
def district_gaps(df: pd.DataFrame) -> pd.DataFrame:
    """High-need households and those with no VUP component, by district (weighted)."""
    hn = df["high_need"].eq(1)
    d = df.assign(_hn=df["weight"] * hn, _unc=df["weight"] * (hn & df["vup_any"].eq(0)), _hn_n=hn.astype(int))
    g = d.groupby(["province_name", "district_name"]).agg(sample_households=("hhid", "size"), high_need_sample=("_hn_n", "sum"),
                                                          households=("weight", "sum"), high_need_households=("_hn", "sum"),
                                                          uncovered_high_need=("_unc", "sum")).reset_index()
    g["protection_gap_rate"] = g["uncovered_high_need"] / g["high_need_households"]
    return g.sort_values("uncovered_high_need", ascending=False).reset_index(drop=True)


def protection_gap(df: pd.DataFrame, increase_pct_of_high_need: float, n_districts: int = 10,
                   payment_quarterly: float = PAYMENT_QUARTERLY_RWF) -> dict:
    """In the `n_districts` with the most uncovered high-need households, newly cover `increase_pct_of_high_need`% of each
    district's high-need households, taken from its uncovered high-need households in priority order (capped at all of them)."""
    gaps = district_gaps(df)
    chosen = gaps.head(n_districts)["district_name"].tolist()
    inc = pd.Series(0.0, index=df.index)
    for dist in chosen:
        in_d = df["district_name"].eq(dist)
        sub = df[in_d]
        pool = sub["high_need"].eq(1) & sub["vup_any"].eq(0)
        budget = increase_pct_of_high_need / 100 * (sub["weight"] * sub["high_need"]).sum()
        inc.loc[sub.index] = allocate(sub, pool, budget)
    after = df.assign(_added=df["weight"] * inc).groupby("district_name")["_added"].sum()
    table = gaps.copy()
    table["targeted"] = table["district_name"].isin(chosen)
    table["households_added"] = table["district_name"].map(after).fillna(0.0)
    table["uncovered_high_need_after"] = table["uncovered_high_need"] - table["households_added"]
    table["protection_gap_rate_after"] = table["uncovered_high_need_after"] / table["high_need_households"]
    table["additional_quarterly_transfer_rwf"] = table["households_added"] * payment_quarterly
    s = _sums(df, inc)
    before = table["uncovered_high_need"].sum()
    nat = {"increase_pct_of_high_need": increase_pct_of_high_need, "n_districts": n_districts, "districts": chosen,
           "payment_quarterly_rwf": payment_quarterly, "households_added": s["households"], "people_added": s["people"],
           "poor_households_added": s["poor_households"], "uncovered_high_need_before": before,
           "uncovered_high_need_after": before - s["households"],
           "uncovered_high_need_reduction_pct": 100 * s["households"] / before if before else np.nan,
           "uncovered_in_targeted_before": table.loc[table["targeted"], "uncovered_high_need"].sum(),
           "uncovered_in_targeted_after": table.loc[table["targeted"], "uncovered_high_need_after"].sum(),
           "additional_quarterly_transfer_rwf": s["households"] * payment_quarterly,
           "additional_annual_transfer_rwf": s["households"] * payment_quarterly * QUARTERS_PER_YEAR}
    return {"national": nat, "by_district": table, "inclusion": inc}


# ---------------------------------------------------------------------------
# Scenario grid (aggregated results only; read by the dashboard)
# ---------------------------------------------------------------------------
COVERAGE_GRID = [0.5 * i for i in range(1, 21)]           # +0.5 ... +10 percentage points of households
TARGETING_GRID = [0.05 * i for i in range(1, 11)]         # top 5% ... 50%
BENEFIT_GRID = [5 * i for i in range(1, 21)]              # +5% ... +100%
GAP_GRID = [5 * i for i in range(1, 21)]                  # 5% ... 100% of high-need households in the target districts


def _long(scenario: str, param: str, value: float, level: str, frame: pd.DataFrame | dict, group_col: str | None = None) -> list[dict]:
    rows = []
    if isinstance(frame, dict):
        for m, v in frame.items():
            if isinstance(v, (int, float, np.floating, np.integer, bool, np.bool_)) and m not in (param,):
                rows.append({"scenario": scenario, "parameter": param, "parameter_value": value, "level": level,
                             "group": "Rwanda", "area": "all", "metric": m, "value": float(v), "sample_households": np.nan})
        return rows
    for _, r in frame.iterrows():
        group = r[group_col] if group_col else "Rwanda"
        area = r["area"] if "area" in frame.columns else "all"
        for m in frame.columns:
            if m in (group_col, "area", "province_name", "district_name", "sample_households", "targeted") or not np.issubdtype(frame[m].dtype, np.number):
                continue
            rows.append({"scenario": scenario, "parameter": param, "parameter_value": value, "level": level, "group": group,
                         "area": area, "metric": m, "value": float(r[m]), "sample_households": float(r.get("sample_households", np.nan))})
    return rows


def scenario_grid(df: pd.DataFrame, payment_quarterly: float = PAYMENT_QUARTERLY_RWF) -> pd.DataFrame:
    """All scenario results on parameter grids, aggregated (national, district, area, income source). No household rows."""
    rows = []
    for x in COVERAGE_GRID:
        r = coverage_expansion(df, x, payment_quarterly)
        rows += _long("coverage_expansion", "increase_pp", x, "national", r["national"])
        rows += _long("coverage_expansion", "increase_pp", x, "district_area", r["by_district_area"], "district_name")
    for k in TARGETING_GRID:
        r = targeting(df, k)
        rows += _long("targeting", "k", k, "national", r["national"])
        for lvl, key, col in [("district", "by_district", "district_name"), ("area", "by_area", "area"), ("income_source", "by_income_source", "income_source")]:
            rows += _long("targeting", "k", k, lvl, r[key].reset_index(), col)
    for x in BENEFIT_GRID:
        rows += _long("benefit_increase", "increase_pct", x, "national", benefit_increase(df, x))
    for x in GAP_GRID:
        r = protection_gap(df, x, payment_quarterly=payment_quarterly)
        nat = {k_: v for k_, v in r["national"].items() if k_ != "districts"}
        rows += _long("protection_gap", "increase_pct_of_high_need", x, "national", nat)
        bd = r["by_district"].assign(targeted_flag=r["by_district"]["targeted"].astype(float))
        rows += _long("protection_gap", "increase_pct_of_high_need", x, "district", bd, "district_name")
    out = pd.DataFrame(rows)
    out["label"] = LABEL
    out["payment_quarterly_rwf_assumed"] = payment_quarterly
    return out
