"""Build the aggregated planning tables for the Baho Neza app (offline; reads household tables, writes aggregates only).

Inputs (data/processed only, never raw .dta files): household_master, household_cpi_shock, household_scores (through
`build_data.load_frame`), reports/final_model_metrics.csv and cpi_features.parquet. Outputs (data/processed):

- dashboard_groups.parquet: Rwanda and each district x area (all, urban, rural) x household group (all; head's sex;
  member with a disability; member aged 65+; poverty status in 2023/24). Observed survey statistics with 95% intervals,
  model estimates (poverty likelihood, predicted VUP coverage), and the reference monthly basket cost by category.
- dashboard_planning.parquet: planning groups for "Compare support": the top 10/20/30% by estimated poverty likelihood or
  by distress, high-need households without VUP, new Direct Support households under the validated coverage-expansion
  scenario, and current NSDS households. Reach (households, people, poor in 2023/24) and reference basket costs.
- dashboard_meta.json: reference periods, model metrics (holdout) and simulation statistics (cross-fitted, full sample).

Reference basket (per household, RWF per month at September 2026 prices): the household's own January 2024 basket
(real consumption x basket share, notebook 07) revalued with the published urban or rural CPI change by category:
    ref_c = basket_jan2024 x (share_c + contrib_c / 100) / 12
so the observed January 2024 to September 2026 change is applied exactly once. A scenario increase p_c on top gives
an extra monthly cost of sum_c ref_c x p_c, which is linear, so group means are exact from these aggregates.

Disclosure control (src/dashboard/disclosure.py): primary suppression below 30 sample households (30 sample high-need
households for high-need indicators), secondary suppression for every additive relation (area, district, group pairs),
and nested-level checks so differencing two published selections never isolates fewer than 30 sample households.

    python -m src.dashboard.build_planning
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from src.dashboard import build_data as bd
from src.dashboard.disclosure import MIN_CELL_SAMPLE, nested_level_suppression, secondary_suppression
from src.simulation import policy_simulator as ps

PROCESSED = ps.PROCESSED
REPORTS = ps.PROJECT_ROOT / "reports"
DASHBOARD_GROUPS = PROCESSED / "dashboard_groups.parquet"
DASHBOARD_PLANNING = PROCESSED / "dashboard_planning.parquet"
DASHBOARD_META = PROCESSED / "dashboard_meta.json"

CATEGORIES = ["food", "energy", "transport", "education", "other"]
GROUP_DIMENSIONS = {
    "head_sex": {"female": lambda d: d["head_female"].eq(1), "male": lambda d: d["head_female"].eq(0)},
    "disability": {"yes": lambda d: d["n_members_with_disability"].gt(0), "no": lambda d: d["n_members_with_disability"].eq(0)},
    "elderly": {"yes": lambda d: d["n_elderly_65plus"].gt(0), "no": lambda d: d["n_elderly_65plus"].eq(0)},
    "poverty": {"poor": lambda d: d["poor"].eq(1), "nonpoor": lambda d: d["poor"].eq(0)},
}
CI_INDICATORS = {   # indicator: (value column, weight column, restricted to high-need households)
    "poverty_rate": ("poor", "pop_wt", False),
    "poverty_likelihood": ("poverty_score", "weight", False),
    "high_need_share": ("high_need", "weight", False),
    "high_need_vup_coverage": ("vup_any", "weight", True),
    "basket_change_pct": ("price_change_pct", "weight", False),
}
HIGH_NEED_VALUES = ["high_need_vup_coverage", "high_need_vup_coverage_ci_low", "high_need_vup_coverage_ci_high",
                    "protection_gap_households", "protection_gap_households_ci_low", "protection_gap_households_ci_high",
                    "predicted_coverage_high_need"]
RANKED_RULES = {"poverty_top": [10, 20, 30], "distress_top": [10, 20, 30]}
ADDITIVE_RULES = {"high_need_no_vup": [100], "nsds_current": [100], "ds_expansion": [1, 2, 5]}
DISTRESS_ORDER = (["distress_score_excl_vup", "poverty_score", "hhid"], [False, False, True])
Z95 = 1.959964


# ---------------------------------------------------------------------------
# Household frame (offline only)
# ---------------------------------------------------------------------------
def load_frame(processed: Path = PROCESSED) -> pd.DataFrame:
    """Simulation frame plus each household's reference monthly basket cost by category (RWF, September 2026 prices)."""
    df = bd.load_frame(processed)
    shock = pd.read_parquet(processed / "household_cpi_shock.parquet", columns=[
        "hhid", "basket_share_of_consumption", "food_share_of_basket", "energy_share_of_basket", "transport_share_of_basket",
        "education_share_of_basket", "contrib_food_pp", "contrib_energy_pp", "contrib_transport_excl_fuel_pp",
        "contrib_education_pp", "contrib_communication_pp", "contrib_meals_away_pp", "contrib_other_pp"])
    master = pd.read_parquet(processed / "household_master.parquet")
    basket_cells = [c for c in master.columns if c.startswith("exp_cell_")
                    and c not in ("exp_cell_housing_rent_imputed", "exp_cell_durables_use_value")]
    master = master.assign(_basket_nominal=master[basket_cells].sum(axis=1))[
        ["hhid", "cons_real_jan2024", "exp_cell_transport_fuel", "vup_ds_amount_12m", "_basket_nominal"]]
    df = df.merge(shock, on="hhid", validate="1:1").merge(master, on="hhid", validate="1:1")

    basket = df["cons_real_jan2024"] * df["basket_share_of_consumption"]               # RWF per year, Jan 2024 prices
    fuel = (df["exp_cell_transport_fuel"] / df["_basket_nominal"]).where(df["_basket_nominal"] > 0, 0.0)
    share = {"food": df["food_share_of_basket"], "energy": df["energy_share_of_basket"],
             "transport": df["transport_share_of_basket"] - fuel, "education": df["education_share_of_basket"]}
    share["other"] = 1 - sum(share.values())
    contrib = {"food": df["contrib_food_pp"], "energy": df["contrib_energy_pp"], "transport": df["contrib_transport_excl_fuel_pp"],
               "education": df["contrib_education_pp"],
               "other": df["contrib_communication_pp"] + df["contrib_meals_away_pp"] + df["contrib_other_pp"]}
    for c in CATEGORIES:
        df[f"ref_{c}"] = (basket * (share[c].fillna(0) + contrib[c].fillna(0) / 100) / 12).fillna(0.0)
    df["base_monthly"] = (basket / 12).fillna(0.0)
    df["ref_monthly"] = df[[f"ref_{c}" for c in CATEGORIES]].sum(axis=1)
    df["uncovered_high_need"] = (df["high_need"].eq(1) & df["vup_any"].eq(0)).astype(float)
    return df.drop(columns=["_basket_nominal"])


# ---------------------------------------------------------------------------
# Survey-design intervals (Taylor linearisation, clusters within strata)
# ---------------------------------------------------------------------------
class Design:
    def __init__(self, df: pd.DataFrame):
        psu = pd.Series(list(zip(df["strata_id"], df["clust"])))
        self.psu, psu_index = pd.factorize(psu)
        strata = pd.Series([s for s, _ in psu_index])
        self.psu_stratum, _ = pd.factorize(strata)
        self.n_psu = len(psu_index)
        counts = np.bincount(self.psu_stratum)
        self.factor = np.where(counts > 1, counts / np.maximum(counts - 1, 1), 0.0)

    def variance(self, z: np.ndarray) -> float:
        zc = np.bincount(self.psu, weights=z, minlength=self.n_psu)
        totals = np.bincount(self.psu_stratum, weights=zc)
        counts = np.bincount(self.psu_stratum)
        dev = zc - (totals / counts)[self.psu_stratum]
        return float((self.factor * np.bincount(self.psu_stratum, weights=dev ** 2)).sum())

    def mean(self, y: np.ndarray, w: np.ndarray, dom: np.ndarray) -> tuple[float, float, float]:
        d = dom & ~np.isnan(y)
        wd = w * d
        total_w = wd.sum()
        if total_w <= 0:
            return (np.nan, np.nan, np.nan)
        yy = np.where(d, y, 0.0)
        m = float((wd * yy).sum() / total_w)
        se = np.sqrt(self.variance(wd * (yy - m) / total_w))
        return (m, m - Z95 * se, m + Z95 * se)

    def total(self, y: np.ndarray, w: np.ndarray, dom: np.ndarray) -> tuple[float, float, float]:
        z = w * np.where(dom, y, 0.0)
        t = float(z.sum())
        se = np.sqrt(self.variance(z))
        return (t, max(t - Z95 * se, 0.0), t + Z95 * se)


# ---------------------------------------------------------------------------
# Groups table
# ---------------------------------------------------------------------------
def _scopes(df: pd.DataFrame):
    """(geo, area, mask) for Rwanda and every district, each for all areas, urban and rural."""
    geos = [("Rwanda", pd.Series(True, index=df.index))] + [(d, df["district_name"].eq(d)) for d in sorted(df["district_name"].unique())]
    for geo, gmask in geos:
        for area in ["all", "urban", "rural"]:
            yield geo, area, gmask if area == "all" else gmask & df["area"].eq(area)


def _summary(df: pd.DataFrame, design: Design, mask: pd.Series) -> dict:
    m = mask.to_numpy()
    w, pw = df["weight"].to_numpy(), df["pop_wt"].to_numpy()
    hn = df["high_need"].eq(1).to_numpy()
    out = {"sample_households": int(m.sum()), "high_need_sample": int((m & hn).sum()),
           "households": float(w[m].sum()), "people": float(pw[m].sum()),
           "high_need_households": float(w[m & hn].sum())}
    for name, (col, wcol, hn_only) in CI_INDICATORS.items():
        dom = m & hn if hn_only else m
        v, lo, hi = design.mean(df[col].to_numpy(float), df[wcol].to_numpy(float), dom)
        out[name], out[f"{name}_ci_low"], out[f"{name}_ci_high"] = v, lo, hi
    t, lo, hi = design.total(df["uncovered_high_need"].to_numpy(float), w, m)
    out.update(protection_gap_households=t, protection_gap_households_ci_low=lo, protection_gap_households_ci_high=hi)
    wm = w * m
    out["vup_coverage"] = float((wm * df["vup_any"]).sum() / wm.sum()) if wm.sum() else np.nan
    whn = w * (m & hn)
    out["predicted_coverage_high_need"] = float((whn * df["vup_coverage_score"].fillna(0)).sum() / whn.sum()) if whn.sum() else np.nan
    for c in CATEGORIES + ["base"]:
        col = "base_monthly" if c == "base" else f"ref_{c}"
        out[f"ref_{c}" if c != "base" else "base_monthly"] = float((wm * df[col]).sum() / wm.sum()) if wm.sum() else np.nan
    return out


def build_groups(df: pd.DataFrame) -> pd.DataFrame:
    design = Design(df)
    rows = []
    for geo, area, mask in _scopes(df):
        rows.append({"geo": geo, "area": area, "dimension": "all", "group": "all", **_summary(df, design, mask)})
        for dim, values in GROUP_DIMENSIONS.items():
            for value, fn in values.items():
                rows.append({"geo": geo, "area": area, "dimension": dim, "group": value, **_summary(df, design, mask & fn(df))})
    out = pd.DataFrame(rows)
    for c in [c for c in out.columns if c.endswith("_ci_low") or c.endswith("_ci_high")]:
        if not c.startswith(("basket_change_pct", "protection_gap_households")):
            out[c] = out[c].clip(0, 1)
    out["level"] = np.where(out["geo"].eq("Rwanda"), "national", "district")
    return apply_group_suppression(out)


def _group_relations(out: pd.DataFrame) -> list:
    idx = {(r.geo, r.area, r.dimension, r.group): i for i, r in enumerate(out.itertuples())}
    rel = []
    geos = out["geo"].unique()
    pairs = [("all", "all")] + [(d, v) for d, vs in GROUP_DIMENSIONS.items() for v in vs]
    for geo in geos:
        for dim, val in pairs:
            rel.append((idx[(geo, "all", dim, val)], [idx[(geo, "urban", dim, val)], idx[(geo, "rural", dim, val)]]))
        for area in ["all", "urban", "rural"]:
            for dim, vs in GROUP_DIMENSIONS.items():
                rel.append((idx[(geo, area, "all", "all")], [idx[(geo, area, dim, v)] for v in vs]))
    districts = [g for g in geos if g != "Rwanda"]
    for area in ["all", "urban", "rural"]:
        for dim, val in pairs:
            rel.append((idx[("Rwanda", area, dim, val)], [idx[(d, area, dim, val)] for d in districts]))
    return rel


def apply_group_suppression(out: pd.DataFrame) -> pd.DataFrame:
    out = out.reset_index(drop=True)
    rel = _group_relations(out)
    out["suppressed"] = secondary_suppression(out["sample_households"] < MIN_CELL_SAMPLE, out["sample_households"], rel)
    hn_primary = out["suppressed"] | (out["high_need_sample"] < MIN_CELL_SAMPLE)
    out["high_need_suppressed"] = secondary_suppression(hn_primary, out["high_need_sample"], rel)
    keep = {"geo", "area", "dimension", "group", "level", "sample_households", "high_need_sample", "suppressed", "high_need_suppressed"}
    values = [c for c in out.columns if c not in keep]
    out.loc[out["suppressed"], values] = np.nan
    out.loc[out["high_need_suppressed"], HIGH_NEED_VALUES] = np.nan
    # Sample sizes of hidden cells are shown only as "fewer than 30"
    out.loc[out["suppressed"], "sample_households"] = np.nan
    out.loc[out["high_need_suppressed"], "high_need_sample"] = np.nan
    return out


# ---------------------------------------------------------------------------
# Planning table
# ---------------------------------------------------------------------------
def _allocate_ordered(sub: pd.DataFrame, order_cols: list[str], ascending: list[bool], budget: float) -> pd.Series:
    """Inclusion share per household when `budget` weighted households are taken in the given order (fractional last)."""
    inc = pd.Series(0.0, index=sub.index)
    if budget <= 0:
        return inc
    order = sub.sort_values(order_cols, ascending=ascending).index
    w = sub.loc[order, "weight"].to_numpy()
    before = np.concatenate([[0.0], np.cumsum(w)[:-1]])
    inc.loc[order] = np.clip((budget - before) / w, 0.0, 1.0)
    return inc


def _reach(df: pd.DataFrame, inc: pd.Series) -> dict:
    w, pw = df["weight"] * inc, df["pop_wt"] * inc
    hh = w.sum()
    out = {"sample_households": int((inc > 0).sum()), "households": hh, "people": pw.sum(),
           "poor_households": (w * df["poor"]).sum(), "poor_people": (pw * df["poor"]).sum(),
           "high_need_households": (w * df["high_need"]).sum(),
           "uncovered_high_need_reached": (w * df["uncovered_high_need"]).sum()}
    for c in CATEGORIES:
        out[f"ref_{c}"] = (w * df[f"ref_{c}"]).sum() / hh if hh else np.nan
    out["base_monthly"] = (w * df["base_monthly"]).sum() / hh if hh else np.nan
    return out


def build_planning(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    scopes = list(_scopes(df))
    ds_inclusion = {pp: ps.coverage_expansion(df, pp)["inclusion"] for pp in ADDITIVE_RULES["ds_expansion"]}
    nsds = ps.benefit_increase(df, 100)
    for geo, area, mask in scopes:
        sub = df[mask]
        cell = {"geo": geo, "area": area, "cell_sample_households": len(sub), "cell_households": sub["weight"].sum()}
        for k in RANKED_RULES["poverty_top"]:
            inc = ps.allocate(sub, pd.Series(True, index=sub.index), k / 100 * sub["weight"].sum())
            rows.append({**cell, "rule": "poverty_top", "level": k, **_reach(sub, inc)})
        for k in RANKED_RULES["distress_top"]:
            inc = _allocate_ordered(sub, *DISTRESS_ORDER, k / 100 * sub["weight"].sum())
            rows.append({**cell, "rule": "distress_top", "level": k, **_reach(sub, inc)})
        rows.append({**cell, "rule": "high_need_no_vup", "level": 100, **_reach(sub, sub["uncovered_high_need"])})
        nsds_inc = sub["vup_nsds"].astype(float)
        nsds_w = sub["weight"] * nsds_inc
        mean_q = (nsds_w * sub["vup_nsds_quarterly_payment"].fillna(0)).sum() / nsds_w.sum() if nsds_w.sum() else np.nan
        rows.append({**cell, "rule": "nsds_current", "level": 100, **_reach(sub, nsds_inc), "mean_quarterly_payment_rwf": mean_q})
        for pp, inc in ds_inclusion.items():
            rows.append({**cell, "rule": "ds_expansion", "level": pp, **_reach(sub, inc.loc[sub.index])})
    out = pd.DataFrame(rows)
    out["scope"] = np.where(out["rule"].eq("ds_expansion"), "national_rule", "within_geography")
    out["programme_rate_quarterly_rwf"] = np.where(out["rule"].eq("nsds_current"), ps.PAYMENT_QUARTERLY_RWF, np.nan)
    nat = out["geo"].eq("Rwanda") & out["area"].eq("all") & out["rule"].eq("nsds_current")
    assert np.isclose(out.loc[nat, "mean_quarterly_payment_rwf"].iloc[0], nsds["mean_quarterly_payment_rwf"])
    out["level_type"] = out["geo"].map(lambda g: "national" if g == "Rwanda" else "district")
    return apply_planning_suppression(out)


def apply_planning_suppression(out: pd.DataFrame) -> pd.DataFrame:
    out = out.reset_index(drop=True)
    sup = out["sample_households"] < MIN_CELL_SAMPLE
    # Nested selections within each geography x area (and against the whole cell)
    for (rule, geo, area), g in out.groupby(["rule", "geo", "area"]):
        hidden = nested_level_suppression(dict(zip(g["level"], g["sample_households"])), int(g["cell_sample_households"].iloc[0]))
        sup.loc[g.index[g["level"].isin(hidden)]] = True
    # Additive selections: district = urban + rural, Rwanda = sum of districts
    idx = {(r.rule, r.level, r.geo, r.area): i for i, r in enumerate(out.itertuples())}
    rel = []
    districts = sorted(g for g in out["geo"].unique() if g != "Rwanda")
    for rule, levels in ADDITIVE_RULES.items():
        for lv in levels:
            for geo in ["Rwanda", *districts]:
                rel.append((idx[(rule, lv, geo, "all")], [idx[(rule, lv, geo, "urban")], idx[(rule, lv, geo, "rural")]]))
            for area in ["all", "urban", "rural"]:
                rel.append((idx[(rule, lv, "Rwanda", area)], [idx[(rule, lv, d, area)] for d in districts]))
    out["suppressed"] = secondary_suppression(sup, out["sample_households"], rel)
    keep = {"geo", "area", "rule", "level", "scope", "level_type", "suppressed", "cell_households", "cell_sample_households",
            "programme_rate_quarterly_rwf"}
    values = [c for c in out.columns if c not in keep]
    out.loc[out["suppressed"], values] = np.nan
    return out.drop(columns=["cell_sample_households"])


# ---------------------------------------------------------------------------
# Metadata
# ---------------------------------------------------------------------------
def build_meta(df: pd.DataFrame, processed: Path = PROCESSED, reports: Path = REPORTS) -> dict:
    cpi = pd.read_parquet(processed / "cpi_features.parquet", columns=["date"])
    metrics = pd.read_csv(reports / "final_model_metrics.csv")
    deployed = metrics["model"].isin(["lightgbm_tuned+group_recal", "xgboost_tuned+platt"]) & metrics["role"].str.contains("deployed")
    dep = metrics[deployed].drop_duplicates(["model_target", "metric"]).set_index(["model_target", "metric"])

    def holdout(target: str, metric: str) -> dict:
        r = dep.loc[(target, metric)]
        return {"value": float(r["value"]), "ci_low": None if pd.isna(r["ci_low"]) else float(r["ci_low"]),
                "ci_high": None if pd.isna(r["ci_high"]) else float(r["ci_high"])}

    splits = pd.read_parquet(processed / "model_splits.parquet", columns=["split"])
    tgt = ps.targeting(df, 0.2)["national"]
    cov = ps.coverage_expansion(df, 2.0)["national"]
    return {
        "built": date.today().isoformat(),
        "survey": {"name": "EICV7", "start": "2023-10-16", "end": "2024-10-15", "households_sampled": int(len(df))},
        "price_base_month": "2024-01",
        "latest_cpi_month": pd.Timestamp(cpi["date"].max()).strftime("%Y-%m"),
        "min_cell_sample": MIN_CELL_SAMPLE,
        "categories": CATEGORIES,
        "payments": {"nsds_programme_rate_quarterly_rwf": ps.PAYMENT_QUARTERLY_RWF,
                     "ds_simulation_assumption_quarterly_rwf": ps.PAYMENT_QUARTERLY_RWF,
                     "ds_observed_median_annual_rwf": float(df.loc[df["vup_direct_support"].eq(1), "vup_ds_amount_12m"].median())},
        "holdout_households": int(splits["split"].eq("holdout").sum()),
        "holdout": {
            "poverty_roc_auc": holdout("poverty", "roc_auc"), "poverty_pr_auc": holdout("poverty", "pr_auc"),
            "poverty_precision_top20": holdout("poverty", "precision_top20"),
            "poverty_poor_people_reached_top20": holdout("poverty", "recall_people_top20"),
            "poverty_calibration_slope": holdout("poverty", "calibration_slope"),
            "vup_roc_auc": holdout("vup_gap", "roc_auc"), "vup_pr_auc": holdout("vup_gap", "pr_auc")},
        "cross_fitted": {"precision_top20": float(tgt["precision"]), "poor_people_reached_top20": float(tgt["recall_people"]),
                         "ds_2pp_households": float(cov["households_added"]),
                         "ds_2pp_uncovered_high_need_after": float(cov["uncovered_high_need_after"])},
    }


def build_all(processed: Path = PROCESSED, write: bool = True) -> dict:
    df = load_frame(processed)
    groups, planning, meta = build_groups(df), build_planning(df), build_meta(df, processed)
    for name, t in [("dashboard_groups", groups), ("dashboard_planning", planning)]:
        bd.assert_aggregated(t, name)
    if write:
        groups.to_parquet(DASHBOARD_GROUPS, index=False)
        planning.to_parquet(DASHBOARD_PLANNING, index=False)
        DASHBOARD_META.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return {"dashboard_groups": groups, "dashboard_planning": planning, "dashboard_meta": meta}


if __name__ == "__main__":
    t = build_all()
    for name in ["dashboard_groups", "dashboard_planning"]:
        print(f"{name}: {t[name].shape[0]:,} rows x {t[name].shape[1]} columns, {int(t[name]['suppressed'].sum())} suppressed")
