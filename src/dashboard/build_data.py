"""Build the aggregated tables the Baho Neza dashboard reads (no household-level records).

Inputs (data/processed only): household_master.parquet, household_cpi_shock.parquet, household_scores.parquet,
district_model_drivers.parquet. Outputs (data/processed):

- dashboard_data.parquet: one row per district x area (all, urban, rural) plus national rows: population and household
  estimates, observed poverty, model-based poverty vulnerability, CPI shock, distress, VUP coverage, protection gap,
  model-based priority score and tier, recommended action, reliability flag, and plain-language driver indicators.
- dashboard_profiles.parquet: high-need households by profile (national and within district): observed coverage and
  mean predicted coverage from the VUP-gap model ("relative underservice", not wrongful exclusion).
- dashboard_drivers.parquet: mean model contributions (log-odds) by feature group, district x area (aggregated).

Disclosure control: indicators are suppressed for cells with fewer than 30 sample households (high-need indicators: fewer
than 30 sample high-need households), with secondary suppression so no hidden cell can be recovered as district minus
the other area or Rwanda minus the other districts; profile cells get complementary suppression within each dimension.

Weights: households `weight`, people `pop_wt`. Every value is a decision-support estimate.

    python -m src.dashboard.build_data
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from src.dashboard.disclosure import secondary_suppression
from src.simulation import policy_simulator as ps

PROCESSED = ps.PROCESSED
DASHBOARD_DATA = PROCESSED / "dashboard_data.parquet"
DASHBOARD_PROFILES = PROCESSED / "dashboard_profiles.parquet"
DASHBOARD_DRIVERS = PROCESSED / "dashboard_drivers.parquet"

MIN_CELL_SAMPLE = 30              # suppress indicators for cells with fewer sample households (or high-need households)
SMALL_SAMPLE = 100                # flag cells below this as "interpret with caution"
UNDERSERVED_RATIO = 0.8           # profile flagged when mean predicted coverage < 80% of the national high-need mean
EXTRA_MASTER = ["hhid", "head_education_code", "n_key_assets", "n_elderly_65plus", "n_children_0_4", "n_members_with_disability",
                "electricity_any", "head_age"]
FORBIDDEN_COLUMNS = {"hhid", "pid", "clust", "strata_id"}
GROUP_LABELS = {"assets": "Assets", "cpi_shock": "Price shock exposure", "demographics": "Household size and composition",
                "distress": "Distress (food share, income, finance)", "education": "Education", "employment_income_source": "Work and income source",
                "expenditure_shares": "Spending pattern", "geography": "Location", "housing": "Housing and utilities",
                "ict_finance": "Phones and financial access", "private_income": "Private income and transfers", "services": "Distance to services",
                "group_recalibration": "Group calibration adjustment"}
HIGH_NEED_INDICATORS = ["high_need_vup_coverage", "protection_gap_households", "protection_gap_rate", "predicted_coverage_high_need"]
KEEP_WHEN_SUPPRESSED = {"level", "district", "province", "area", "sample_households", "high_need_sample", "population_estimate", "household_estimate"}


def load_frame(processed: Path = PROCESSED) -> pd.DataFrame:
    df = ps.load_simulation_frame(processed)
    extra = pd.read_parquet(processed / "household_master.parquet", columns=EXTRA_MASTER)
    return df.merge(extra, on="hhid", validate="1:1")


def _wavg(x, w):
    x, w = np.asarray(x, float), np.asarray(w, float)
    ok = ~np.isnan(x)
    return float(np.average(x[ok], weights=w[ok])) if ok.any() and w[ok].sum() > 0 else np.nan


def summarise(g: pd.DataFrame) -> dict:
    w, pw = g["weight"], g["pop_wt"]
    hn = g["high_need"].eq(1)
    unc = hn & g["vup_any"].eq(0)
    return {
        "sample_households": len(g), "high_need_sample": int(hn.sum()),
        "population_estimate": pw.sum(), "household_estimate": w.sum(),
        "poverty_rate": _wavg(g["poor"], pw), "poor_people_estimate": (pw * g["poor"]).sum(),
        "poverty_vulnerability": _wavg(g["poverty_score"], w),
        "cpi_shock_pct": _wavg(g["price_change_pct"], w), "distress_score": _wavg(g["distress_score_excl_vup"], w),
        "vup_coverage": _wavg(g["vup_any"], w), "direct_support_coverage": _wavg(g["vup_direct_support"], w),
        "nsds_coverage": _wavg(g["vup_nsds"], w),
        "high_need_households": (w * hn).sum(), "high_need_share": _wavg(hn.astype(float), w),
        "high_need_vup_coverage": _wavg(g.loc[hn, "vup_any"], w[hn]) if hn.any() else np.nan,
        "protection_gap_households": (w * unc).sum(),
        "protection_gap_rate": (w * unc).sum() / (w * hn).sum() if hn.any() else np.nan,
        "predicted_coverage_high_need": _wavg(g.loc[hn, "vup_coverage_score"], w[hn]) if hn.any() else np.nan,
        "expected_uncovered_poor_people": (pw * g["poverty_score"] * (1 - g["vup_any"])).sum(),
        # plain-language driver indicators
        "share_farm_wage": _wavg(g["main_livelihood"].eq("farm_wage"), w),
        "share_own_farming": _wavg(g["main_livelihood"].eq("own_farming"), w),
        "share_head_no_education": _wavg(g["head_education_code"].eq(0), w),
        "share_no_key_assets": _wavg(g["n_key_assets"].eq(0), w),
        "share_female_head": _wavg(g["head_female"], w),
        "share_with_elderly": _wavg(g["n_elderly_65plus"].gt(0), w),
        "share_with_disability": _wavg(g["n_members_with_disability"].gt(0), w),
        "share_with_electricity": _wavg(g["electricity_any"], w),
        "food_share": _wavg(g["share_food"], w),
        "mean_household_size": _wavg(g["hh_size"], w),
    }


def reliability(n: int) -> str:
    if n < MIN_CELL_SAMPLE:
        return "insufficient sample: indicators suppressed"
    if n < SMALL_SAMPLE:
        return "small sample: interpret with caution"
    return "adequate sample"


def recommended_action(tier: str, gap_rate: float, national_gap: float, shock: float, national_shock: float) -> str:
    """Rule-based, decision-support wording; never an eligibility instruction."""
    if tier == "insufficient sample":
        return "Insufficient survey sample in this area: use the district-wide view"
    if tier == "high":
        base = "High priority: many people likely poor without VUP support. Verify high-need households and review coverage first"
    elif tier == "medium":
        base = "Medium priority: review coverage of high-need groups in the next planning cycle"
    else:
        base = "Lower priority: maintain coverage and monitor"
    notes = []
    if pd.notna(gap_rate) and gap_rate > national_gap:
        notes.append("protection gap above the national rate")
    if pd.notna(shock) and shock >= national_shock + 1:
        notes.append("price shock above national: monitor food and energy costs")
    return base + ("; " + "; ".join(notes) if notes else "")


def area_district_relations(out: pd.DataFrame) -> list:
    """Additive relations between rows: district (all) = urban + rural; Rwanda (area) = sum of its districts."""
    idx = {(r.district, r.area): i for i, r in enumerate(out.itertuples())}
    districts = out.loc[out["level"].eq("district"), "district"].unique()
    rel = [(idx[(d, "all")], [idx[(d, "urban")], idx[(d, "rural")]]) for d in districts if (d, "urban") in idx and (d, "rural") in idx]
    rel += [(idx[("Rwanda", a)], [idx[(d, a)] for d in districts if (d, a) in idx]) for a in ["all", "urban", "rural"]]
    return rel


def build_dashboard_data(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for area in ["all", "urban", "rural"]:
        sub = df if area == "all" else df[df["area"].eq(area)]
        rows.append({"level": "national", "district": "Rwanda", "province": "Rwanda", "area": area, **summarise(sub)})
        for (prov, dist), g in sub.groupby(["province_name", "district_name"]):
            rows.append({"level": "district", "district": dist, "province": prov.replace(" Province", ""), "area": area, **summarise(g)})
    out = pd.DataFrame(rows)
    out["expected_uncovered_poor_per_1000"] = 1000 * out["expected_uncovered_poor_people"] / out["population_estimate"]

    # Disclosure control and reliability
    rel = area_district_relations(out)
    out["suppressed"] = secondary_suppression(out["sample_households"] < MIN_CELL_SAMPLE, out["sample_households"], rel)
    out["high_need_suppressed"] = secondary_suppression(out["suppressed"] | (out["high_need_sample"] < MIN_CELL_SAMPLE),
                                                        out["high_need_sample"], rel)
    value_cols = [c for c in out.columns if c not in KEEP_WHEN_SUPPRESSED | {"suppressed", "high_need_suppressed"}]
    out.loc[out["suppressed"], value_cols] = np.nan
    out.loc[out["high_need_suppressed"], HIGH_NEED_INDICATORS] = np.nan
    out["reliability"] = out["sample_households"].map(reliability).where(~out["suppressed"], reliability(0))

    # Model-based priority: percentile rank among districts (same area view) of expected poor people without VUP
    out["priority_score"] = np.nan
    out["priority_tier"] = np.where(out["level"].eq("national"), "not ranked", "insufficient sample")
    for area in ["all", "urban", "rural"]:
        m = out["level"].eq("district") & out["area"].eq(area) & ~out["suppressed"]
        r = out.loc[m, "expected_uncovered_poor_people"].rank(pct=True)
        out.loc[m, "priority_score"] = (100 * r).round(1)
        out.loc[m, "priority_tier"] = np.select([r > 2 / 3, r > 1 / 3], ["high", "medium"], "low")

    nat = out[out["level"].eq("national")].set_index("area")
    out["recommended_action"] = [
        "National reference" if lvl == "national" else
        recommended_action(t, gr, nat.loc[a, "protection_gap_rate"], s, nat.loc[a, "cpi_shock_pct"])
        + (" (small sample: interpret with caution)" if rel.startswith("small") else "")
        for lvl, t, gr, s, a, rel in zip(out["level"], out["priority_tier"], out["protection_gap_rate"], out["cpi_shock_pct"], out["area"], out["reliability"])]
    out["label"] = ps.LABEL
    return out


PROFILE_DIMENSIONS = {
    "Main income source": lambda d: d["income_source"],
    "Head's sex": lambda d: np.where(d["head_female"].eq(1), "Female head", "Male head"),
    "Head's age": lambda d: pd.cut(d["head_age"], [-1, 34, 59, 200], labels=["Under 35", "35-59", "60 and over"]).astype(str),
    "Household size": lambda d: pd.cut(d["hh_size"], [0, 1, 3, 5, 7, 99], labels=["1 person", "2-3", "4-5", "6-7", "8 or more"]).astype(str),
    "Elderly member (65+)": lambda d: np.where(d["n_elderly_65plus"].gt(0), "Yes", "No"),
    "Child under 5": lambda d: np.where(d["n_children_0_4"].gt(0), "Yes", "No"),
    "Member with a disability": lambda d: np.where(d["n_members_with_disability"].gt(0), "Yes", "No"),
    "Urban / rural": lambda d: d["area"].str.capitalize(),
}
DISTRICT_PROFILE_DIMENSIONS = ["Main income source", "Head's sex", "Elderly member (65+)", "Child under 5"]
PROFILE_VALUES = ["high_need_households", "uncovered_high_need", "vup_coverage", "mean_predicted_coverage", "poverty_rate"]


def complementary_suppression(cells: pd.DataFrame) -> pd.Series:
    """Within one scope x dimension: if exactly one cell is suppressed, also suppress the smallest other cell."""
    s = cells["high_need_sample"] < MIN_CELL_SAMPLE
    if s.sum() == 1 and len(cells) > 1:
        s.loc[cells.loc[~s, "high_need_sample"].idxmin()] = True
    return s


def build_profiles(df: pd.DataFrame) -> pd.DataFrame:
    hn = df[df["high_need"].eq(1)].copy()
    nat_pred = _wavg(hn["vup_coverage_score"], hn["weight"])
    nat_cov = _wavg(hn["vup_any"], hn["weight"])
    rows = []
    for scope, scope_df in [("Rwanda", hn)] + list(hn.groupby("district_name")):
        dims = PROFILE_DIMENSIONS if scope == "Rwanda" else {k: PROFILE_DIMENSIONS[k] for k in DISTRICT_PROFILE_DIMENSIONS}
        for dim, fn in dims.items():
            labels = pd.Series(fn(scope_df), index=scope_df.index)
            for grp, g in scope_df.groupby(labels):
                rows.append({"scope": scope, "dimension": dim, "group": grp, "high_need_sample": len(g),
                             "high_need_households": g["weight"].sum(), "uncovered_high_need": (g["weight"] * g["vup_any"].eq(0)).sum(),
                             "vup_coverage": _wavg(g["vup_any"], g["weight"]), "mean_predicted_coverage": _wavg(g["vup_coverage_score"], g["weight"]),
                             "poverty_rate": _wavg(g["poor"], g["pop_wt"])})
    out = pd.DataFrame(rows)
    out["suppressed"] = pd.concat([complementary_suppression(c) for _, c in out.groupby(["scope", "dimension"])]).reindex(out.index)
    out.loc[out["suppressed"], PROFILE_VALUES] = np.nan
    out["national_predicted_coverage"] = nat_pred
    out["national_observed_coverage"] = nat_cov
    out["relative_underservice"] = 1 - out["mean_predicted_coverage"] / nat_pred
    out["relatively_underserved"] = (~out["suppressed"]) & (out["mean_predicted_coverage"] < UNDERSERVED_RATIO * nat_pred)
    out["label"] = ps.LABEL + "; relative underservice describes current coverage, not wrongful exclusion"
    return out


def build_drivers(processed: Path = PROCESSED) -> pd.DataFrame:
    d = pd.read_parquet(processed / "district_model_drivers.parquet")
    d["feature_group_label"] = d["feature_group"].map(GROUP_LABELS).fillna(d["feature_group"])
    d["province"] = d["province"].str.replace(" Province", "", regex=False)
    small = d["sample_households"] < MIN_CELL_SAMPLE
    d.loc[small, ["mean_contribution_log_odds", "difference_from_national"]] = np.nan
    d["label"] = "Mean model contribution (log-odds) of the poverty model by feature group; describes the model, not causes"
    return d


def assert_aggregated(table: pd.DataFrame, name: str) -> None:
    bad = FORBIDDEN_COLUMNS & set(table.columns)
    assert not bad, f"{name} contains household identifiers: {bad}"


def build_all(processed: Path = PROCESSED, write: bool = True) -> dict[str, pd.DataFrame]:
    df = load_frame(processed)
    tables = {"dashboard_data": build_dashboard_data(df), "dashboard_profiles": build_profiles(df), "dashboard_drivers": build_drivers(processed)}
    for name, t in tables.items():
        assert_aggregated(t, name)
    if write:
        tables["dashboard_data"].to_parquet(DASHBOARD_DATA, index=False)
        tables["dashboard_profiles"].to_parquet(DASHBOARD_PROFILES, index=False)
        tables["dashboard_drivers"].to_parquet(DASHBOARD_DRIVERS, index=False)
    return tables


if __name__ == "__main__":
    t = build_all()
    for name, tab in t.items():
        print(f"{name}: {tab.shape[0]:,} rows x {tab.shape[1]} columns")
