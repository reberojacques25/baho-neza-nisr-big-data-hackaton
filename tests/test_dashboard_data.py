"""Tests for the dashboard data layer: src/dashboard/build_data.py (aggregation, suppression) and src/dashboard/data.py
(loading, formatting, scenario look-ups, district brief).

Synthetic tests check the arithmetic by hand; integration tests run on the real processed tables when they exist.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.dashboard import build_data as bd
from src.dashboard import data as dd
from src.simulation import policy_simulator as ps
from tests.test_policy_simulator import make_frame


def make_dashboard_frame(copies: int = 10) -> pd.DataFrame:
    """The 10-household simulator frame replicated `copies` times: districts A and B with 5 x copies households each."""
    base = make_frame()
    base["head_education_code"] = [0, 1, 2, 0, 3, 0, 1, 1, 4, 0]
    base["n_key_assets"] = [0, 1, 3, 0, 4, 0, 2, 1, 5, 0]
    base["n_elderly_65plus"] = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0]
    base["n_children_0_4"] = [1, 1, 0, 1, 0, 1, 0, 0, 0, 1]
    base["n_members_with_disability"] = [0, 0, 0, 1, 0, 1, 0, 0, 0, 0]
    base["electricity_any"] = [0, 0, 1, 0, 1, 0, 1, 1, 1, 0]
    base["head_age"] = [70, 30, 45, 50, 40, 66, 33, 52, 29, 38]
    df = pd.concat([base] * copies, ignore_index=True)
    df["hhid"] = np.arange(1, len(df) + 1)
    return df


@pytest.fixture
def frame():
    return make_dashboard_frame()


# ---------------------------------------------------------------------------
# build_data: dashboard_data
# ---------------------------------------------------------------------------
def test_one_row_per_district_and_area_without_household_columns(frame):
    out = bd.build_dashboard_data(frame)
    assert len(out) == (2 + 1) * 3                                   # (districts + national) x (all, urban, rural)
    assert not (bd.FORBIDDEN_COLUMNS & set(out.columns))
    assert not out.duplicated(["level", "district", "area"]).any()
    assert out["label"].str.contains("Decision-support estimate").all()


def test_totals_are_survey_weighted_and_consistent(frame):
    out = bd.build_dashboard_data(frame)
    nat = out[out["level"].eq("national")].set_index("area")
    assert np.isclose(nat.loc["all", "household_estimate"], frame["weight"].sum())
    assert np.isclose(nat.loc["all", "population_estimate"], frame["pop_wt"].sum())
    assert np.isclose(nat.loc["urban", "household_estimate"] + nat.loc["rural", "household_estimate"], nat.loc["all", "household_estimate"])
    for area in ["all", "urban", "rural"]:
        d = out[out["level"].eq("district") & out["area"].eq(area)]
        assert np.isclose(d["household_estimate"].sum(), nat.loc[area, "household_estimate"])
    # Hand-computed national rates: 5 of 10 poor (equal weights); VUP: households 4 and 8; high-need 1, 2, 6, 10 all uncovered
    assert np.isclose(nat.loc["all", "poverty_rate"], 0.5)
    assert np.isclose(nat.loc["all", "vup_coverage"], 0.2)
    assert np.isclose(nat.loc["all", "protection_gap_rate"], 1.0)
    assert np.isclose(nat.loc["all", "protection_gap_households"], 40 * 100)


def test_small_cells_are_suppressed_but_keep_sizes(frame):
    out = bd.build_dashboard_data(frame)
    # District A urban: households 3 and 5 x 10 copies = 20 sample households (< 30)
    a_urban = out[out["district"].eq("A") & out["area"].eq("urban")].iloc[0]
    assert a_urban["suppressed"] and a_urban["sample_households"] == 20
    assert np.isnan(a_urban["poverty_rate"]) and np.isnan(a_urban["vup_coverage"]) and np.isnan(a_urban["priority_score"])
    assert a_urban["priority_tier"] == "insufficient sample"
    assert np.isclose(a_urban["household_estimate"], 2000)
    # District A overall: 50 sample households, but only 20 high-need -> high-need indicators suppressed, others shown
    a_all = out[out["district"].eq("A") & out["area"].eq("all")].iloc[0]
    assert not a_all["suppressed"] and a_all["high_need_suppressed"]
    assert np.isclose(a_all["poverty_rate"], 0.6) and np.isnan(a_all["protection_gap_rate"])


def test_values_when_cells_are_large_enough(frame, monkeypatch):
    monkeypatch.setattr(bd, "MIN_CELL_SAMPLE", 1)
    out = bd.build_dashboard_data(frame)
    b = out[out["district"].eq("B") & out["area"].eq("all")].iloc[0]
    assert np.isclose(b["poverty_rate"], 0.4)                       # households 6 and 10 poor out of 5
    assert np.isclose(b["vup_coverage"], 0.2)                       # household 8
    assert np.isclose(b["high_need_households"], 2000) and np.isclose(b["protection_gap_rate"], 1.0)
    # Expected uncovered poor people: sum of pop_wt x score over households without VUP
    no_vup = frame[frame["district_name"].eq("B") & frame["vup_any"].eq(0)]
    assert np.isclose(b["expected_uncovered_poor_people"], (no_vup["pop_wt"] * no_vup["poverty_score"]).sum())


def test_priority_score_ranks_expected_uncovered_poor(frame):
    out = bd.build_dashboard_data(frame)
    d = out[out["level"].eq("district") & out["area"].eq("all")].set_index("district")
    assert d["priority_score"].between(0, 100).all()
    top = d["expected_uncovered_poor_people"].idxmax()
    assert d.loc[top, "priority_score"] == 100 and d.loc[top, "priority_tier"] == "high"


def test_recommended_actions_are_decision_support_wording(frame):
    out = bd.build_dashboard_data(frame)
    text = " ".join(out["recommended_action"]).lower()
    for banned in ["eligib", "enrol", "exclude", "remove", "deny", "select"]:
        assert banned not in text
    assert bd.recommended_action("high", 0.95, 0.9, 40, 38).startswith("High priority")
    assert "protection gap above" in bd.recommended_action("low", 0.95, 0.9, 38, 38)
    assert "price shock above" in bd.recommended_action("medium", 0.5, 0.9, 39.5, 38)


# ---------------------------------------------------------------------------
# build_data: profiles and suppression
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("sizes, expected", [
    ([100, 20, 50], [False, True, True]),        # one small cell -> smallest other cell also suppressed
    ([100, 200], [False, False]),
    ([10, 20, 100], [True, True, False]),        # two small cells already protect each other
    ([10, 300], [True, True]),
])
def test_complementary_suppression(sizes, expected):
    cells = pd.DataFrame({"high_need_sample": sizes})
    assert bd.complementary_suppression(cells).tolist() == expected


def test_profiles_hide_values_of_suppressed_cells(frame):
    out = bd.build_profiles(frame)
    assert not (bd.FORBIDDEN_COLUMNS & set(out.columns))
    sup = out[out["suppressed"]]
    assert sup[bd.PROFILE_VALUES].isna().all().all()
    shown = out[~out["suppressed"]]
    assert (shown["high_need_sample"] >= bd.MIN_CELL_SAMPLE).all()
    assert out["label"].str.contains("not wrongful exclusion").all()
    assert not out.loc[out["suppressed"], "relatively_underserved"].any()


# ---------------------------------------------------------------------------
# data.py: loading, geometry and formatting
# ---------------------------------------------------------------------------
def test_load_tables_rejects_household_level_columns(tmp_path):
    ok = tmp_path / "ok.parquet"
    bad = tmp_path / "bad.parquet"
    pd.DataFrame({"district": ["A"], "value": [1.0]}).to_parquet(ok)
    pd.DataFrame({"hhid": [1], "value": [1.0]}).to_parquet(bad)
    assert set(dd.load_tables({"ok": ok})) == {"ok"}
    with pytest.raises(ValueError, match="household-level"):
        dd.load_tables({"ok": ok, "bad": bad})
    with pytest.raises(FileNotFoundError):
        dd.load_tables({"missing": tmp_path / "missing.parquet"})


def test_rewind_makes_outer_rings_clockwise_and_holes_anticlockwise():
    outer_ccw = [[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]
    hole_cw = [[0.2, 0.2], [0.2, 0.8], [0.8, 0.8], [0.8, 0.2], [0.2, 0.2]]
    gj = {"features": [{"geometry": {"type": "Polygon", "coordinates": [list(outer_ccw), list(hole_cw)]}},
                       {"geometry": {"type": "MultiPolygon", "coordinates": [[list(outer_ccw)]]}}]}
    dd.rewind_for_plotly(gj)
    poly = gj["features"][0]["geometry"]["coordinates"]
    assert dd._signed_area(poly[0]) < 0 and dd._signed_area(poly[1]) > 0
    assert dd._signed_area(gj["features"][1]["geometry"]["coordinates"][0][0]) < 0


def test_formatting():
    assert dd.fmt(0.27371, "share") == "27.4%"
    assert dd.fmt(38.04, "percent") == "38.0%"
    assert dd.fmt(595_807, "count") == "595,800"
    assert dd.fmt(np.nan, "share") == "n/a"
    assert dd.fmt_rwf(2.007e9) == "2.01 bn RWF" and dd.fmt_rwf(30_500) == "30,500 RWF"
    assert dd.difference_text("poverty_rate", 0.364, 0.274) == "+9.0 pts vs national"


# ---------------------------------------------------------------------------
# data.py: scenario look-ups on a synthetic grid
# ---------------------------------------------------------------------------
@pytest.fixture
def grid():
    return ps.scenario_grid(make_frame())


def test_payment_assumption_rescales_transfers_only(grid):
    base = dd.scenario_national(grid, "coverage_expansion", 2.0)
    double = dd.scenario_national(grid, "coverage_expansion", 2.0, payment=2 * dd.BASE_PAYMENT_RWF)
    assert np.isclose(double["additional_quarterly_transfer_rwf"], 2 * base["additional_quarterly_transfer_rwf"])
    assert np.isclose(double["additional_annual_transfer_rwf"], 2 * base["additional_annual_transfer_rwf"])
    assert np.isclose(double["households_added"], base["households_added"])
    tgt = dd.scenario_national(grid, "targeting", 0.2, payment=1.0)       # targeting has no payment metrics
    assert np.isclose(tgt["precision"], dd.scenario_national(grid, "targeting", 0.2)["precision"])


def test_benefit_estimate_is_exact_and_linear(grid):
    at_grid = dd.scenario_national(grid, "benefit_increase", 10.0)
    est = dd.benefit_estimate(grid, 10)
    assert np.isclose(est["additional_quarterly_transfer_rwf"], at_grid["additional_quarterly_transfer_rwf"])
    assert np.isclose(est["additional_annual_transfer_rwf_observed_quarters"], at_grid["additional_annual_transfer_rwf_observed_quarters"])
    assert np.isclose(dd.benefit_estimate(grid, 12.5)["additional_quarterly_transfer_rwf"], 1.25 * est["additional_quarterly_transfer_rwf"])
    assert dd.benefit_estimate(grid, 0)["additional_quarterly_transfer_rwf"] == 0


def test_coverage_by_district_sums_to_national(grid):
    for x in [1.0, 5.0, 10.0]:
        nat = dd.scenario_national(grid, "coverage_expansion", x)
        by = dd.coverage_by_district(grid, x)
        assert np.isclose(by["households_added"].sum(), nat["households_added"])
        assert np.isclose(by["uncovered_high_need_after"].sum(), nat["uncovered_high_need_after"])
        urban, rural = dd.coverage_by_district(grid, x, "urban"), dd.coverage_by_district(grid, x, "rural")
        assert np.isclose(urban["households_added"].sum() + rural["households_added"].sum(), nat["households_added"])


def test_grid_lookup_rejects_values_off_the_grid(grid):
    with pytest.raises(KeyError):
        dd.scenario_national(grid, "coverage_expansion", 0.3)


def test_protection_gap_table_flags_targeted_districts(grid):
    t = dd.protection_gap_districts(grid, 50.0)
    assert t["targeted"].all()                                          # only 2 districts, both within the top 10
    assert (t["uncovered_high_need_after"] <= t["uncovered_high_need"]).all()


# ---------------------------------------------------------------------------
# Integration: the real dashboard tables
# ---------------------------------------------------------------------------
needs_tables = pytest.mark.skipif(not all(p.exists() for p in dd.APP_FILES.values()), reason="dashboard tables not built")
needs_households = pytest.mark.skipif(not (ps.PROCESSED / "household_scores.parquet").exists(), reason="processed tables not available")


@needs_tables
def test_real_dashboard_data_structure_and_totals():
    t = dd.load_tables()
    dash = t["dashboard"]
    assert len(dash) == (30 + 1) * 3
    for name, tab in t.items():
        assert not (bd.FORBIDDEN_COLUMNS & set(tab.columns)), name
    nat = dash[dash["level"].eq("national")].set_index("area")
    assert round(nat.loc["all", "household_estimate"]) == 3_289_819
    assert round(nat.loc["all", "population_estimate"]) == 13_549_457
    assert round(100 * nat.loc["all", "poverty_rate"], 1) == 27.4
    for area in ["all", "urban", "rural"]:
        d = dd.districts(dash, area)
        assert np.isclose(d["household_estimate"].sum(), nat.loc[area, "household_estimate"])
    assert dd.districts(dash, "all")["priority_tier"].value_counts().to_dict() == {"high": 10, "medium": 10, "low": 10}
    small = dash["sample_households"] < bd.MIN_CELL_SAMPLE
    assert dash.loc[small, ["poverty_rate", "vup_coverage", "priority_score"]].isna().all().all()
    assert (dash.loc[dash["high_need_sample"] < bd.MIN_CELL_SAMPLE, bd.HIGH_NEED_INDICATORS].isna()).all().all()


@needs_tables
def test_real_profiles_respect_suppression():
    p = dd.load_tables()["profiles"]
    assert (p.loc[~p["suppressed"], "high_need_sample"] >= bd.MIN_CELL_SAMPLE).all()
    assert p.loc[p["suppressed"], bd.PROFILE_VALUES].isna().all().all()
    # within each scope x dimension, never exactly one suppressed cell next to shown cells
    counts = p.groupby(["scope", "dimension"])["suppressed"].agg(["sum", "size"])
    assert not ((counts["sum"] == 1) & (counts["size"] > 1)).any()


@needs_tables
def test_real_district_brief_is_aggregated_and_labelled():
    t = dd.load_tables()
    brief = dd.district_brief(t["dashboard"], t["profiles"], t["drivers"], "Nyagatare")
    assert set(brief.columns) == {"section", "indicator", "district_value", "national_value", "note"}
    assert brief["note"].str.contains("not automatic beneficiary selection").any()
    assert {"About", "Vulnerability", "Coverage", "Priority", "Model drivers"} <= set(brief["section"])


@needs_tables
@needs_households
def test_saved_dashboard_tables_match_a_rebuild():
    rebuilt = bd.build_all(write=False)
    t = dd.load_tables()
    pd.testing.assert_frame_equal(rebuilt["dashboard_data"], t["dashboard"], check_dtype=False)
    pd.testing.assert_frame_equal(rebuilt["dashboard_profiles"], t["profiles"], check_dtype=False)
