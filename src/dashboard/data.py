"""Data access and scenario look-ups for the Baho Neza dashboard.

The public app reads aggregated tables only (built offline by `src.dashboard.build_planning`) plus district boundaries.
No household-level table is loaded here, and nothing in this module imports the modelling or simulation code, so the
dashboard needs only pandas, pyarrow, plotly and streamlit.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PROCESSED = PROJECT_ROOT / "data" / "processed"
GEOJSON_PATH = PROJECT_ROOT / "data" / "external" / "geo" / "rwa_districts.geojson"
APP_FILES = {
    "dashboard": PROCESSED / "dashboard_data.parquet",
    "profiles": PROCESSED / "dashboard_profiles.parquet",
    "drivers": PROCESSED / "dashboard_drivers.parquet",
    "scenarios": PROCESSED / "scenario_results.parquet",
}
# The public app reads these aggregated files only (plus district boundaries); see src/dashboard/build_planning.py.
PUBLIC_FILES = {"groups": PROCESSED / "dashboard_groups.parquet", "planning": PROCESSED / "dashboard_planning.parquet"}
META_PATH = PROCESSED / "dashboard_meta.json"
HOUSEHOLD_COLUMNS = {"hhid", "pid", "clust", "strata_id"}

BASE_PAYMENT_RWF = 30_500          # NSDS quarterly rate used to build the scenario grid
QUARTERS_PER_YEAR = 4
PAYMENT_SCENARIOS = {"coverage_expansion", "protection_gap"}       # transfer values scale with the payment assumption
PAYMENT_METRICS = {"additional_quarterly_transfer_rwf", "additional_annual_transfer_rwf"}

DISCLAIMER = ("Decision-support estimates (EICV7 2023/24, survey-weighted). Outputs support prioritization and "
              "verification, not automatic beneficiary selection.")
AREAS = {"All areas": "all", "Rural": "rural", "Urban": "urban"}
ALL_DISTRICTS = "All districts"
SUPPRESSED_TEXT = "suppressed (fewer than 30 sample households)"


@dataclass(frozen=True)
class Indicator:
    label: str
    kind: str          # share (0-1), percent (already in %), score, count, people, number, text
    help: str


INDICATORS: dict[str, Indicator] = {
    "priority_score": Indicator(
        "Model-based priority score", "score",
        "0 to 100. Districts ranked by the estimated number of people who are likely poor (poverty model) and receive no "
        "VUP support; 100 means the most such people. Ranked within the area view shown. A planning aid, not an allocation rule."),
    "poverty_vulnerability": Indicator(
        "Poverty vulnerability (model)", "share",
        "Average predicted chance that a household is consumption-poor, from the poverty model. Scores are out-of-sample: "
        "no household is scored by a model that was trained on it."),
    "poverty_rate": Indicator(
        "Poverty rate (survey)", "share",
        "Share of people below the national poverty line in EICV7 2023/24, as measured by NISR."),
    "cpi_shock_pct": Indicator(
        "Price shock, Jan 2024 to Sep 2026", "percent",
        "Average rise in the cost of each household's own consumption basket between January 2024 and September 2026, "
        "priced with the NISR urban or rural CPI."),
    "distress_score": Indicator(
        "Cost-of-living distress score", "score",
        "0 to 100. Equal-weight average of five components: price shock, food share of spending, distance from the poverty "
        "line, income instability, and lack of savings or credit. VUP is left out so the score can be compared with coverage."),
    "vup_coverage": Indicator(
        "VUP coverage", "share",
        "Share of households receiving any of the five VUP components in the survey: Direct Support, NSDS, classic or "
        "expanded Public Works, or Financial Services."),
    "protection_gap_rate": Indicator(
        "Protection gap", "share",
        "Share of high-need households (top fifth nationally by distress score) that receive no VUP component."),
    "protection_gap_households": Indicator(
        "Uncovered high-need households", "count",
        "Estimated number of high-need households that receive no VUP component."),
    "high_need_share": Indicator("High-need share", "share", "Share of households in the top fifth nationally by distress score."),
    "high_need_households": Indicator("High-need households", "count", "Estimated number of households in the top fifth nationally by distress score."),
    "high_need_vup_coverage": Indicator("VUP coverage of high-need households", "share", "Share of high-need households receiving any VUP component."),
    "predicted_coverage_high_need": Indicator(
        "Predicted coverage of high-need households (VUP-gap model)", "share",
        "Average chance that a high-need household with this profile receives VUP, as predicted from current coverage "
        "patterns. Lower than the national average means relative underservice, not wrongful exclusion."),
    "expected_uncovered_poor_people": Indicator(
        "People likely poor without VUP (model)", "count",
        "Sum over households of people x predicted poverty probability, for households receiving no VUP component."),
    "population_estimate": Indicator("Population", "count", "Survey-weighted number of people (pop_wt)."),
    "household_estimate": Indicator("Households", "count", "Survey-weighted number of households (weight)."),
    "poor_people_estimate": Indicator("People below the poverty line", "count", "Survey-weighted number of poor people."),
    "direct_support_coverage": Indicator("VUP Direct Support coverage", "share", "Share of households in VUP Direct Support."),
    "nsds_coverage": Indicator("NSDS coverage", "share", "Share of households in Nutrition-Sensitive Direct Support."),
    "share_farm_wage": Indicator("Main income: farm wage work", "share", "Share of households whose members mainly work for wages on farms."),
    "share_own_farming": Indicator("Main income: own farming", "share", "Share of households mainly farming their own land."),
    "share_head_no_education": Indicator("Head has no schooling", "share", "Share of households whose head never attended primary school."),
    "share_no_key_assets": Indicator("No key assets", "share", "Share of households with none of: radio, TV, phone, bicycle, motorcycle, car, fridge, computer."),
    "share_female_head": Indicator("Female-headed households", "share", "Share of households headed by a woman."),
    "share_with_elderly": Indicator("Has a member aged 65+", "share", "Share of households with at least one member aged 65 or over."),
    "share_with_disability": Indicator("Has a member with a disability", "share", "Share of households with at least one member with a disability."),
    "share_with_electricity": Indicator("Has electricity (grid or solar)", "share", "Share of households with grid or solar electricity."),
    "food_share": Indicator("Food share of spending", "share", "Average share of consumption spent on food at home."),
    "mean_household_size": Indicator("Average household size", "number", "Average number of members per household."),
}
MAP_INDICATORS = ["priority_score", "poverty_vulnerability", "poverty_rate", "cpi_shock_pct", "distress_score",
                  "vup_coverage", "protection_gap_rate", "protection_gap_households"]
PROFILE_INDICATORS = ["share_farm_wage", "share_own_farming", "share_head_no_education", "share_no_key_assets", "share_female_head",
                      "share_with_elderly", "share_with_disability", "share_with_electricity", "food_share", "mean_household_size"]
TIER_LABELS = {"high": "High priority", "medium": "Medium priority", "low": "Lower priority",
               "insufficient sample": "Insufficient sample", "not ranked": "Not ranked"}


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------
def load_tables(files: dict[str, Path] = APP_FILES) -> dict[str, pd.DataFrame]:
    missing = [str(p.relative_to(PROJECT_ROOT)) if p.is_relative_to(PROJECT_ROOT) else str(p) for p in files.values() if not p.exists()]
    if missing:
        raise FileNotFoundError("Dashboard tables missing: " + ", ".join(missing)
                                + ". Build them with `python -m src.dashboard.build_data` (and notebook 15 for scenario_results).")
    tables = {k: pd.read_parquet(p) for k, p in files.items()}
    for name, t in tables.items():
        leaked = HOUSEHOLD_COLUMNS & set(t.columns)
        if leaked:
            raise ValueError(f"{name} contains household-level columns {sorted(leaked)}; the dashboard reads aggregates only")
    return tables


def load_public_tables() -> dict:
    """The two aggregated planning tables and the reference metadata (periods, metrics) for the public app."""
    if not META_PATH.exists():
        raise FileNotFoundError(f"Dashboard metadata missing: {META_PATH.name}. Build it with `python -m src.dashboard.build_planning`.")
    return {**load_tables(PUBLIC_FILES), "meta": json.loads(META_PATH.read_text(encoding="utf-8"))}


def _signed_area(ring: list) -> float:
    xy = np.asarray(ring, float)[:, :2]
    x, y = xy[:, 0], xy[:, 1]
    return 0.5 * float(np.sum(x[:-1] * y[1:] - x[1:] * y[:-1]))


def rewind_for_plotly(gj: dict) -> dict:
    """Plotly's map renderer (d3-geo) needs clockwise outer rings and anticlockwise holes, the opposite of the GeoJSON
    right-hand rule that geoBoundaries follows; otherwise each district is drawn as the whole globe minus the district."""
    for feature in gj["features"]:
        geom = feature["geometry"]
        polygons = [geom["coordinates"]] if geom["type"] == "Polygon" else geom["coordinates"]
        for polygon in polygons:
            for i, ring in enumerate(polygon):
                if (_signed_area(ring) > 0) == (i == 0):   # outer ring anticlockwise, or hole clockwise
                    ring.reverse()
    return gj


def load_geojson(path: Path = GEOJSON_PATH) -> dict:
    with open(path, encoding="utf-8") as f:
        return rewind_for_plotly(json.load(f))


# ---------------------------------------------------------------------------
# District table helpers
# ---------------------------------------------------------------------------
def districts(dash: pd.DataFrame, area: str = "all") -> pd.DataFrame:
    return dash[dash["level"].eq("district") & dash["area"].eq(area)].reset_index(drop=True)


def national(dash: pd.DataFrame, area: str = "all") -> pd.Series:
    return dash[dash["level"].eq("national") & dash["area"].eq(area)].iloc[0]


def district_row(dash: pd.DataFrame, district: str, area: str = "all") -> pd.Series:
    return dash[dash["level"].eq("district") & dash["district"].eq(district) & dash["area"].eq(area)].iloc[0]


def district_names(dash: pd.DataFrame) -> list[str]:
    return sorted(dash.loc[dash["level"].eq("district"), "district"].unique())


def province_of(dash: pd.DataFrame) -> dict[str, str]:
    d = dash[dash["level"].eq("district")]
    return dict(zip(d["district"], d["province"]))


# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------
def round_count(v: float) -> float:
    if pd.isna(v):
        return np.nan
    return round(v, -2) if abs(v) >= 10_000 else round(v, -1)


def fmt(v, kind: str) -> str:
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "n/a"
    if kind == "share":
        return f"{100 * v:.1f}%"
    if kind == "percent":
        return f"{v:.1f}%"
    if kind == "score":
        return f"{v:.1f}"
    if kind == "count":
        return f"{round_count(v):,.0f}"
    if kind == "number":
        return f"{v:.1f}"
    if kind == "rwf":
        return fmt_rwf(v)
    return str(v)


def fmt_rwf(v: float) -> str:
    if pd.isna(v):
        return "n/a"
    if abs(v) >= 1e9:
        return f"{v / 1e9:,.2f} bn RWF"
    if abs(v) >= 1e6:
        return f"{v / 1e6:,.1f} m RWF"
    return f"{v:,.0f} RWF"


def fmt_indicator(col: str, v) -> str:
    return fmt(v, INDICATORS[col].kind) if col in INDICATORS else fmt(v, "number")


def difference_text(col: str, v, ref) -> str:
    """Plain-language difference from the national value (percentage points for shares)."""
    if pd.isna(v) or pd.isna(ref):
        return ""
    kind = INDICATORS[col].kind
    d = v - ref
    if kind == "share":
        return f"{100 * d:+.1f} pts vs national"
    if kind == "percent":
        return f"{d:+.1f} pts vs national"
    if kind == "count":
        return ""
    return f"{d:+.1f} vs national"


# ---------------------------------------------------------------------------
# Scenario grid look-ups
# ---------------------------------------------------------------------------
def grid_values(scen: pd.DataFrame, scenario: str) -> list[float]:
    v = scen.loc[scen["scenario"].eq(scenario), "parameter_value"].unique()
    return sorted(float(round(x, 6)) for x in v)


def _rescale(scenario: str, metric: pd.Series, value: pd.Series, payment: float) -> pd.Series:
    factor = np.where(metric.isin(PAYMENT_METRICS) & (scenario in PAYMENT_SCENARIOS), payment / BASE_PAYMENT_RWF, 1.0)
    return value * factor


def _slice(scen: pd.DataFrame, scenario: str, value: float, level: str) -> pd.DataFrame:
    s = scen[scen["scenario"].eq(scenario) & scen["level"].eq(level)]
    s = s[np.isclose(s["parameter_value"], value)]
    if s.empty:
        raise KeyError(f"No {scenario} results at {value} (level {level}); grid values: {grid_values(scen, scenario)}")
    return s


def scenario_national(scen: pd.DataFrame, scenario: str, value: float, payment: float = BASE_PAYMENT_RWF) -> pd.Series:
    s = _slice(scen, scenario, value, "national")
    return pd.Series(_rescale(scenario, s["metric"], s["value"], payment).to_numpy(), index=s["metric"].to_numpy())


def scenario_breakdown(scen: pd.DataFrame, scenario: str, value: float, level: str, payment: float = BASE_PAYMENT_RWF) -> pd.DataFrame:
    s = _slice(scen, scenario, value, level).copy()
    s["value"] = _rescale(scenario, s["metric"], s["value"], payment)
    wide = s.pivot_table(index=["group", "area"], columns="metric", values="value", aggfunc="first").reset_index()
    n = s.groupby(["group", "area"])["sample_households"].first().rename("sample_households").reset_index()
    return wide.merge(n, on=["group", "area"], how="left").rename_axis(columns=None)


def scenario_curve(scen: pd.DataFrame, scenario: str, metrics: list[str], payment: float = BASE_PAYMENT_RWF) -> pd.DataFrame:
    s = scen[scen["scenario"].eq(scenario) & scen["level"].eq("national") & scen["metric"].isin(metrics)].copy()
    s["value"] = _rescale(scenario, s["metric"], s["value"], payment)
    return s.pivot_table(index="parameter_value", columns="metric", values="value").reset_index().rename_axis(columns=None)


def coverage_by_district(scen: pd.DataFrame, value: float, area: str = "all", payment: float = BASE_PAYMENT_RWF) -> pd.DataFrame:
    """Coverage expansion by district, summed over urban/rural cells (area='all') or for one area."""
    b = scenario_breakdown(scen, "coverage_expansion", value, "district_area", payment)
    if area != "all":
        b = b[b["area"].eq(area)]
    cols = ["households", "households_added", "uncovered_high_need_before", "uncovered_high_need_after",
            "uncovered_high_need_reached", "additional_quarterly_transfer_rwf", "sample_households"]
    out = b.groupby("group")[cols].sum().reset_index().rename(columns={"group": "district"})
    out["share_of_households_added"] = out["households_added"] / out["households"]
    return out.sort_values("households_added", ascending=False).reset_index(drop=True)


def benefit_estimate(scen: pd.DataFrame, increase_pct: float) -> dict:
    """NSDS benefit increase for any percentage: exact, because the estimate is linear in the increase."""
    ref_value = grid_values(scen, "benefit_increase")[0]
    r = scenario_national(scen, "benefit_increase", ref_value)
    current = r["current_quarterly_transfer_rwf"]
    observed_quarters = r["additional_annual_transfer_rwf_observed_quarters"] / r["additional_quarterly_transfer_rwf"]
    add_q = current * increase_pct / 100
    return {
        "covered_households": r["covered_households"], "covered_people": r["covered_people"], "covered_poor_people": r["covered_poor_people"],
        "current_quarterly_transfer_rwf": current, "mean_quarterly_payment_rwf": r["mean_quarterly_payment_rwf"],
        "additional_quarterly_transfer_rwf": add_q,
        "additional_annual_transfer_rwf_4_quarters": add_q * QUARTERS_PER_YEAR,
        "additional_annual_transfer_rwf_observed_quarters": add_q * observed_quarters,
        "mean_quarters_paid": observed_quarters,
        "additional_per_household_quarterly_rwf": r["mean_quarterly_payment_rwf"] * increase_pct / 100,
    }


def protection_gap_districts(scen: pd.DataFrame, value: float, payment: float = BASE_PAYMENT_RWF) -> pd.DataFrame:
    b = scenario_breakdown(scen, "protection_gap", value, "district", payment).rename(columns={"group": "district"})
    b["targeted"] = b["targeted_flag"].eq(1)
    return b.sort_values(["targeted", "uncovered_high_need"], ascending=False).reset_index(drop=True)


# ---------------------------------------------------------------------------
# District brief (CSV download)
# ---------------------------------------------------------------------------
BRIEF_SECTIONS = {
    "Profile": ["population_estimate", "household_estimate", "poor_people_estimate", "mean_household_size"],
    "Vulnerability": ["poverty_rate", "poverty_vulnerability", "cpi_shock_pct", "distress_score", "high_need_share", "high_need_households"],
    "Coverage": ["vup_coverage", "direct_support_coverage", "nsds_coverage", "high_need_vup_coverage", "protection_gap_households",
                 "protection_gap_rate", "predicted_coverage_high_need"],
    "Priority": ["expected_uncovered_poor_people", "priority_score"],
    "Characteristics": PROFILE_INDICATORS[:-1],
}


def district_brief(dash: pd.DataFrame, profiles: pd.DataFrame, drivers: pd.DataFrame, district: str, area: str = "all") -> pd.DataFrame:
    row, nat = district_row(dash, district, area), national(dash, area)
    rows = [
        {"section": "About", "indicator": "District", "district_value": district, "national_value": "Rwanda", "note": f"Province: {row['province']}; area: {area}"},
        {"section": "About", "indicator": "Status", "district_value": "Decision-support estimate", "national_value": "",
         "note": DISCLAIMER + " Not a causal impact estimate or an eligibility decision."},
        {"section": "About", "indicator": "Source", "district_value": "NISR EICV7 2023/24; NISR CPI Jan 2024 to Sep 2026", "national_value": "",
         "note": "Survey-weighted: households use weight, people use pop_wt"},
        {"section": "About", "indicator": "Sample households", "district_value": int(row["sample_households"]), "national_value": int(nat["sample_households"]),
         "note": row["reliability"]},
        {"section": "Priority", "indicator": "Priority tier", "district_value": TIER_LABELS.get(row["priority_tier"], row["priority_tier"]),
         "national_value": "", "note": "Top, middle or bottom third of districts by the model-based priority score"},
        {"section": "Priority", "indicator": "Recommended action", "district_value": row["recommended_action"], "national_value": "",
         "note": "Rule-based planning prompt; verify on the ground"},
    ]
    for section, cols in BRIEF_SECTIONS.items():
        for c in cols:
            ind = INDICATORS[c]
            rows.append({"section": section, "indicator": ind.label, "district_value": fmt(row[c], ind.kind) if pd.notna(row[c]) else SUPPRESSED_TEXT,
                         "national_value": fmt(nat[c], ind.kind) if c != "priority_score" else "", "note": ind.help})
    drv = drivers[drivers["district"].eq(district) & drivers["area"].eq(area) & drivers["difference_from_national"].notna()]
    for _, d in drv.reindex(drv["difference_from_national"].abs().sort_values(ascending=False).index).head(5).iterrows():
        rows.append({"section": "Model drivers", "indicator": d["feature_group_label"],
                     "district_value": f"{d['difference_from_national']:+.2f} log-odds vs national", "national_value": "0",
                     "note": "Positive raises the model's poverty score here relative to the national average; describes the model, not causes"})
    prof = profiles[profiles["scope"].eq(district)]
    for _, p in prof.iterrows():
        val = SUPPRESSED_TEXT if p["suppressed"] else f"coverage {fmt(p['vup_coverage'], 'share')}; predicted {fmt(p['mean_predicted_coverage'], 'share')}"
        rows.append({"section": "High-need groups", "indicator": f"{p['dimension']}: {p['group']}", "district_value": val,
                     "national_value": f"predicted {fmt(p['national_predicted_coverage'], 'share')}",
                     "note": "Relatively underserved (predicted coverage below 80% of national)" if p["relatively_underserved"] else ""})
    return pd.DataFrame(rows, columns=["section", "indicator", "district_value", "national_value", "note"]).astype(str)
