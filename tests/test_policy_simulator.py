"""Tests for src/simulation/policy_simulator.py.

Synthetic tests check the arithmetic on tables where the answer can be worked out by hand. Integration tests run on
the real processed tables when they exist (they are not shipped with the repository) and are skipped otherwise.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.simulation import policy_simulator as ps


def make_frame() -> pd.DataFrame:
    """10 households in 2 districts; weights 100 each (1,000 households), 4 people per household."""
    n = 10
    return pd.DataFrame({
        "hhid": np.arange(1, n + 1),
        "clust": [1, 1, 1, 1, 1, 2, 2, 2, 2, 2],
        "strata_id": [1] * 5 + [2] * 5,
        "province_name": ["P"] * n,
        "district_name": ["A"] * 5 + ["B"] * 5,
        "area": ["rural", "rural", "urban", "rural", "urban", "rural", "rural", "rural", "urban", "rural"],
        "weight": [100.0] * n,
        "pop_wt": [400.0] * n,
        "hh_size": [4] * n,
        "poor": [1, 1, 0, 1, 0, 1, 0, 0, 0, 1.0],
        "extreme_poor": [0.0] * n,
        "main_livelihood": ["own_farming"] * 5 + ["farm_wage"] * 5,
        "income_source": ["Own farming"] * 5 + ["Farm wage work"] * 5,
        "vup_any": [0, 0, 0, 1, 0, 0, 0, 1, 0, 0.0],
        "vup_direct_support": [0, 0, 0, 1, 0, 0, 0, 0, 0, 0.0],
        "vup_nsds": [0, 0, 0, 0, 0, 0, 0, 1, 0, 0.0],
        "vup_nsds_quarterly_payment": [np.nan] * 7 + [30_000.0] + [np.nan] * 2,
        "vup_nsds_quarters_paid_12m": [np.nan] * 7 + [3.0] + [np.nan] * 2,
        "share_food": [0.5] * n,
        "head_female": [0.0] * n,
        "distress_score": [80, 70, 30, 60, 20, 90, 40, 50, 10, 75.0],
        "distress_score_excl_vup": [80, 70, 30, 60, 20, 90, 40, 50, 10, 75.0],
        "distress_quintile_excl_vup": [5, 5, 2, 4, 1, 5, 3, 3, 1, 5],
        "price_change_pct": [38.0] * n,
        # Scores: household 6 highest, then 1, then 10 and 2 tied (distress breaks the tie: 10 before 2)
        "poverty_score": [0.80, 0.60, 0.10, 0.70, 0.05, 0.90, 0.30, 0.50, 0.02, 0.60],
        "high_need": [1, 1, 0, 0, 0, 1, 0, 0, 0, 1.0],
        "vup_coverage_score": [0.1, 0.2, np.nan, np.nan, np.nan, 0.3, np.nan, np.nan, np.nan, 0.05],
    })


@pytest.fixture
def frame():
    return make_frame()


# ---------------------------------------------------------------------------
# Allocation
# ---------------------------------------------------------------------------
def test_priority_order_uses_score_then_distress(frame):
    order = frame.loc[ps.priority_order(frame), "hhid"].tolist()
    assert order[:4] == [6, 1, 4, 10]
    assert order.index(10) < order.index(2)  # tie at 0.60 broken by distress (75 > 70)


def test_allocate_exact_budget_with_fractional_last_household(frame):
    inc = ps.allocate(frame, pd.Series(True, index=frame.index), budget_households=250)
    assert np.isclose((frame["weight"] * inc).sum(), 250)
    by_id = dict(zip(frame["hhid"], inc))
    assert by_id[6] == 1 and by_id[1] == 1 and np.isclose(by_id[4], 0.5) and by_id[10] == 0


def test_allocate_respects_pool_and_caps(frame):
    pool = frame["vup_any"].eq(0)
    inc = ps.allocate(frame, pool, budget_households=10_000)
    assert (inc[~pool] == 0).all()
    assert np.isclose((frame["weight"] * inc).sum(), frame.loc[pool, "weight"].sum())


# ---------------------------------------------------------------------------
# 1. Coverage expansion
# ---------------------------------------------------------------------------
def test_coverage_expansion_counts_and_value(frame):
    r = ps.coverage_expansion(frame, increase_pp=20, payment_quarterly=30_500)["national"]
    assert np.isclose(r["households_added"], 200)            # 20% of 1,000 households
    assert np.isclose(r["people_added"], 800)
    # Pool = no VUP: household 6 (score 0.9) then household 1 (0.8); both poor and high-need
    assert np.isclose(r["poor_households_added"], 200) and np.isclose(r["precision_poor"], 1.0)
    assert np.isclose(r["uncovered_high_need_before"], 400)  # households 1, 2, 6, 10
    assert np.isclose(r["uncovered_high_need_after"], 200)
    assert np.isclose(r["additional_quarterly_transfer_rwf"], 200 * 30_500)
    assert np.isclose(r["additional_annual_transfer_rwf"], 200 * 30_500 * 4)
    assert np.isclose(r["direct_support_coverage_before"], 0.10) and np.isclose(r["direct_support_coverage_after"], 0.30)


def test_coverage_expansion_district_breakdown_sums_to_national(frame):
    r = ps.coverage_expansion(frame, increase_pp=35)
    by = r["by_district_area"]
    assert np.isclose(by["households_added"].sum(), r["national"]["households_added"])
    assert np.isclose(by["uncovered_high_need_after"].sum(), r["national"]["uncovered_high_need_after"])


def test_coverage_expansion_capped_by_pool(frame):
    r = ps.coverage_expansion(frame, increase_pp=100)["national"]
    assert np.isclose(r["households_added"], 800)            # only 8 households have no VUP
    assert r["capped_by_pool"]


# ---------------------------------------------------------------------------
# 2. Targeting
# ---------------------------------------------------------------------------
def test_targeting_precision_and_recall(frame):
    r = ps.targeting(frame, 0.30)["national"]
    # Top 3: households 6, 1, 4 -> all poor; 5 poor households in total
    assert np.isclose(r["selected_households"], 300)
    assert np.isclose(r["poor_households_reached"], 300) and np.isclose(r["precision"], 1.0)
    assert np.isclose(r["recall_households"], 0.6) and np.isclose(r["recall_people"], 0.6)
    assert np.isclose(r["poor_households_missed"], 200)


def test_targeting_breakdowns_partition_the_selection(frame):
    r = ps.targeting(frame, 0.40)
    for key in ["by_district", "by_area", "by_income_source"]:
        b = r[key]
        assert np.isclose(b["selected_households"].sum(), r["national"]["selected_households"])
        assert np.isclose(b["poor_households_reached"].sum(), r["national"]["poor_households_reached"])
        assert np.isclose(b["share_of_selection"].sum(), 1.0)
    a = r["by_district"].loc["A"]
    assert np.isclose(a["recall_households"], 2 / 3)       # district A poor: 1, 2, 4; selected among them: 1, 4


# ---------------------------------------------------------------------------
# 3. Benefit increase
# ---------------------------------------------------------------------------
def test_benefit_increase_value(frame):
    r = ps.benefit_increase(frame, increase_pct=10)
    assert np.isclose(r["covered_households"], 100)
    assert np.isclose(r["current_quarterly_transfer_rwf"], 100 * 30_000)
    assert np.isclose(r["additional_quarterly_transfer_rwf"], 100 * 30_000 * 0.10)
    assert np.isclose(r["additional_annual_transfer_rwf_4_quarters"], 100 * 30_000 * 0.10 * 4)
    assert np.isclose(r["additional_annual_transfer_rwf_observed_quarters"], 100 * 30_000 * 3 * 0.10)


def test_benefit_increase_is_linear(frame):
    a, b = ps.benefit_increase(frame, 10), ps.benefit_increase(frame, 30)
    assert np.isclose(3 * a["additional_quarterly_transfer_rwf"], b["additional_quarterly_transfer_rwf"])


# ---------------------------------------------------------------------------
# 4. Protection gap
# ---------------------------------------------------------------------------
def test_district_gaps_ranked_by_uncovered(frame):
    g = ps.district_gaps(frame)
    assert g["district_name"].tolist() == ["A", "B"]          # A: 1, 2 uncovered; B: 6, 10 uncovered (tie -> stable)
    assert np.isclose(g["uncovered_high_need"].sum(), 400)
    assert (g["protection_gap_rate"] <= 1).all()


def test_protection_gap_targets_top_districts_only(frame):
    r = ps.protection_gap(frame, increase_pct_of_high_need=50, n_districts=1)
    t = r["by_district"].set_index("district_name")
    target = r["national"]["districts"][0]
    other = [d for d in t.index if d != target][0]
    assert np.isclose(t.loc[target, "households_added"], 100)  # 50% of 200 high-need households
    assert t.loc[other, "households_added"] == 0
    assert np.isclose(r["national"]["uncovered_high_need_after"], 300)
    assert (t["uncovered_high_need_after"] >= -1e-9).all()


def test_protection_gap_never_exceeds_uncovered(frame):
    r = ps.protection_gap(frame, increase_pct_of_high_need=100, n_districts=2)
    assert np.isclose(r["national"]["uncovered_high_need_after"], 0)
    assert np.isclose(r["national"]["households_added"], 400)


# ---------------------------------------------------------------------------
# Scenario grid
# ---------------------------------------------------------------------------
def test_scenario_grid_has_no_household_rows(frame):
    g = ps.scenario_grid(frame)
    assert "hhid" not in g.columns
    assert set(g["scenario"]) == {"coverage_expansion", "targeting", "benefit_increase", "protection_gap"}
    assert set(g["level"]) <= {"national", "district_area", "district", "area", "income_source"}
    assert g["label"].str.contains("Decision-support estimate").all()
    nat = g[(g["scenario"] == "targeting") & (g["level"] == "national") & (g["metric"] == "precision")]
    assert nat["parameter_value"].nunique() == len(ps.TARGETING_GRID)


# ---------------------------------------------------------------------------
# Integration (real processed tables)
# ---------------------------------------------------------------------------
needs_data = pytest.mark.skipif(not (ps.PROCESSED / "household_scores.parquet").exists(), reason="processed tables not available")


@needs_data
def test_real_frame_reproduces_poverty_rate():
    df = ps.load_simulation_frame()
    assert len(df) == 15_054 and df["hhid"].is_unique
    assert round(100 * np.average(df["poor"], weights=df["pop_wt"]), 1) == 27.4


@needs_data
def test_real_targeting_matches_holdout_order_of_magnitude():
    df = ps.load_simulation_frame()
    r = ps.targeting(df, 0.20)["national"]
    assert 0.60 < r["recall_people"] < 0.75 and 0.65 < r["precision"] < 0.80  # out-of-sample scores, cf. notebook 14


@needs_data
def test_real_coverage_expansion_monotone():
    df = ps.load_simulation_frame()
    vals = [ps.coverage_expansion(df, x)["national"]["uncovered_high_need_after"] for x in (0, 1, 2, 5)]
    assert all(a >= b for a, b in zip(vals, vals[1:]))
