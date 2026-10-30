"""Tests for the Baho Neza planning layer: disclosure control, the aggregated planning tables and the scenario engine."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.dashboard import build_planning as bp
from src.dashboard import data as dd
from src.dashboard import scenario as sc
from src.dashboard.disclosure import MIN_CELL_SAMPLE, nested_level_suppression, secondary_suppression

needs_tables = pytest.mark.skipif(not all(p.exists() for p in dd.PUBLIC_FILES.values()) or not dd.META_PATH.exists(),
                                  reason="planning tables not built")
SCENARIOS = dd.PROCESSED / "scenario_results.parquet"
# Private, household-level or offline-only inputs: present on the analysis machine, absent from the public release
needs_private = pytest.mark.skipif(not (dd.PROCESSED / "household_master.parquet").exists()
                                   or not dd.APP_FILES["dashboard"].exists(),
                                   reason="private household-level data not available (public release)")


# ---------------------------------------------------------------------------
# Disclosure rules (synthetic)
# ---------------------------------------------------------------------------
def test_secondary_suppression_hides_a_second_part():
    sample = pd.Series({"total": 100, "a": 10, "b": 50, "c": 40})
    sup = secondary_suppression(sample < MIN_CELL_SAMPLE, sample, [("total", ["a", "b", "c"])])
    assert sup.to_dict() == {"total": False, "a": True, "b": False, "c": True}     # smallest open part hidden too


def test_secondary_suppression_hides_a_part_when_only_the_total_is_hidden():
    sample = pd.Series({"total": 100, "a": 60, "b": 40})
    primary = pd.Series({"total": True, "a": False, "b": False})
    assert secondary_suppression(primary, sample, [("total", ["a", "b"])]).sum() == 2


def test_secondary_suppression_cascades_across_shared_cells():
    # district D1 = urban + rural; Rwanda urban = D1 urban + D2 urban
    sample = pd.Series({"D1": 200, "D1u": 10, "D1r": 190, "D2u": 80, "Ru": 90})
    rel = [("D1", ["D1u", "D1r"]), ("Ru", ["D1u", "D2u"])]
    sup = secondary_suppression(sample < MIN_CELL_SAMPLE, sample, rel)
    for total, parts in rel:
        assert sum(sup[m] for m in [total, *parts]) != 1


@pytest.mark.parametrize("levels,population,hidden", [
    ({10: 50, 20: 100, 30: 150}, 500, set()),
    ({10: 50, 20: 70, 30: 150}, 500, {20}),          # 20% - 10% isolates 20 households
    ({10: 20, 20: 100, 30: 150}, 500, {10}),
    ({10: 50, 20: 100, 30: 480}, 500, {30}),          # everyone minus top 30% isolates 20 households
])
def test_nested_levels_never_isolate_small_slices(levels, population, hidden):
    assert nested_level_suppression(levels, population) == hidden


# ---------------------------------------------------------------------------
# Specs, fingerprints and the price formula (synthetic)
# ---------------------------------------------------------------------------
REF = {"food": 100.0, "energy": 20.0, "transport": 10.0, "education": 5.0, "other": 65.0}


def test_price_modes_are_exclusive_and_normalised():
    simple = sc.price_spec("simple", 12, 10, detailed={"food": 50})
    assert simple["increases"] == {c: 10.0 for c in sc.CATEGORIES}          # detailed inputs ignored in simple mode
    detailed = sc.price_spec("detailed", 6, 99, detailed={"food": 20, "transport": 5})
    assert detailed["increases"]["food"] == 20 and detailed["increases"]["energy"] == 0 and detailed["horizon_months"] == 6


def test_fingerprint_is_stable_and_sensitive():
    a = sc.price_spec("simple", 12, 10)
    assert sc.fingerprint(a, "Rutsiro", "all") == sc.fingerprint(sc.price_spec("simple", 12, 10.0), "Rutsiro", "all")
    assert sc.fingerprint(a, "Rutsiro", "all") != sc.fingerprint(sc.price_spec("simple", 12, 11), "Rutsiro", "all")
    assert sc.fingerprint(a, "Rutsiro", "all") != sc.fingerprint(a, "Rutsiro", "rural")
    assert sc.fingerprint(a, "Rutsiro", "all") != sc.fingerprint(sc.price_spec("simple", 6, 10), "Rutsiro", "all")


def test_zero_price_change_reproduces_the_reference_basket():
    eff = sc.basket_effect(REF, sc.price_spec("simple", 12, 0)["increases"])
    assert eff["scenario_monthly"] == eff["reference_monthly"] == 200 and eff["extra_monthly"] == 0


def test_price_increase_is_applied_once_to_the_reference_basket():
    eff = sc.basket_effect(REF, sc.price_spec("detailed", 12, detailed={"food": 10, "transport": 50})["increases"])
    assert eff["extra_monthly"] == pytest.approx(100 * 0.10 + 10 * 0.50)
    assert eff["basket_change_pct"] == pytest.approx(100 * 15 / 200)
    assert eff["purchasing_power_change_pct"] == pytest.approx(-100 * 15 / 215)
    uniform = sc.basket_effect(REF, sc.price_spec("simple", 12, 10)["increases"])
    assert uniform["basket_change_pct"] == pytest.approx(10.0)              # a uniform increase moves every basket equally


@pytest.mark.parametrize("call,code", [
    (lambda: sc.price_spec("simple", 12, -5), "increase_range"),
    (lambda: sc.price_spec("simple", 24, 5), "horizon"),
    (lambda: sc.price_spec("detailed", 12, detailed={"rice": 5}), "unknown_category"),
    (lambda: sc.support_spec("public_works"), "action_unavailable"),
    (lambda: sc.support_spec("combined"), "action_unavailable"),
    (lambda: sc.support_spec("vouchers"), "unknown_action"),
    (lambda: sc.support_spec("cash", rule="poverty_top", level=25), "planning_group"),
    (lambda: sc.support_spec("cash", frequency="quarterly", duration_months=4), "duration"),
    (lambda: sc.support_spec("ds_expansion", ds_level=3), "ds_level"),
    (lambda: sc.support_spec("cash", amount_rwf=-1), "amount_range"),
])
def test_unsupported_scenarios_fail_clearly(call, code):
    with pytest.raises(sc.UnsupportedScenario) as e:
        call()
    assert e.value.code == code


# ---------------------------------------------------------------------------
# Real aggregated tables
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def tabs():
    return dd.load_public_tables()


@needs_tables
def test_public_tables_are_aggregated(tabs):
    for name in ("groups", "planning"):
        assert not dd.HOUSEHOLD_COLUMNS & set(tabs[name].columns), name
    assert tabs["groups"]["sample_households"].dropna().min() >= MIN_CELL_SAMPLE
    assert tabs["planning"]["sample_households"].dropna().min() >= MIN_CELL_SAMPLE


@needs_tables
def test_hidden_cells_carry_no_values(tabs):
    g, p = tabs["groups"], tabs["planning"]
    value_cols = [c for c in g.columns if c.startswith(("poverty", "high_need_share", "basket", "ref_", "households", "people"))]
    assert g.loc[g["suppressed"], value_cols].isna().all().all()
    assert g.loc[g["high_need_suppressed"], ["high_need_vup_coverage", "protection_gap_households"]].isna().all().all()
    assert p.loc[p["suppressed"], ["households", "people", "poor_households", "ref_food"]].isna().all().all()


@needs_tables
def test_no_additive_relation_has_exactly_one_hidden_cell(tabs):
    g = tabs["groups"].reset_index(drop=True)
    for flag in ("suppressed", "high_need_suppressed"):
        for total, parts in bp._group_relations(g):
            assert sum(bool(g.loc[m, flag]) for m in [total, *parts]) != 1
    p = tabs["planning"]
    for (rule, level), sub in p[p["rule"].isin(bp.ADDITIVE_RULES)].groupby(["rule", "level"]):
        s = sub.set_index(["geo", "area"])["suppressed"]
        for area in ["all", "urban", "rural"]:
            members = [("Rwanda", area)] + [(d, area) for d in s.index.get_level_values(0).unique() if d != "Rwanda"]
            assert sum(bool(s[m]) for m in members) != 1, (rule, level, area)
        for geo in s.index.get_level_values(0).unique():
            assert sum(bool(s[(geo, a)]) for a in ["all", "urban", "rural"]) != 1, (rule, level, geo)


@needs_tables
@needs_private
def test_groups_match_the_published_district_table(tabs):
    dash = pd.read_parquet(dd.APP_FILES["dashboard"])
    g = tabs["groups"]
    a = g[g["dimension"].eq("all")].rename(columns={"geo": "district"}).set_index(["district", "area"])
    d = dash.set_index(["district", "area"])
    for gcol, dcol in [("poverty_rate", "poverty_rate"), ("poverty_likelihood", "poverty_vulnerability"),
                       ("high_need_share", "high_need_share"), ("basket_change_pct", "cpi_shock_pct"),
                       ("high_need_vup_coverage", "high_need_vup_coverage"), ("protection_gap_households", "protection_gap_households")]:
        pd.testing.assert_series_equal(a[gcol].sort_index(), d[dcol].sort_index(), check_names=False, rtol=1e-9)
    assert (a["suppressed"].sort_index() == d["suppressed"].sort_index()).all()


@needs_tables
def test_intervals_contain_the_estimate(tabs):
    g = tabs["groups"].dropna(subset=["poverty_rate"])
    for col in bp.CI_INDICATORS:
        v = g.dropna(subset=[col])
        assert ((v[f"{col}_ci_low"] <= v[col] + 1e-12) & (v[col] <= v[f"{col}_ci_high"] + 1e-12)).all(), col


@needs_tables
def test_reference_basket_includes_the_observed_change_once(tabs):
    nat = tabs["groups"].query("geo == 'Rwanda' and area == 'all' and dimension == 'all'").iloc[0]
    ref = sum(nat[f"ref_{c}"] for c in sc.CATEGORIES)
    # Basket-weighted observed change: reference / January 2024 basket - 1, close to the household mean (38.0%)
    assert 0.35 < ref / nat["base_monthly"] - 1 < 0.42
    res = sc.price_result(tabs["groups"], "Rwanda", "all", sc.price_spec("simple", 12, 0))
    assert res["scenario_monthly"] == pytest.approx(ref) and res["extra_monthly"] == 0


@needs_tables
def test_planning_groups_have_the_right_scope_and_denominators(tabs):
    p, g = tabs["planning"], tabs["groups"]
    cell = g.query("geo == 'Rutsiro' and area == 'all' and dimension == 'all'").iloc[0]
    for k in (10, 20, 30):
        row = sc.planning_row(p, "poverty_top", k, "Rutsiro", "all")
        assert row["households"] == pytest.approx(k / 100 * cell["households"], rel=1e-9)   # share of the district itself
        assert row["scope"] == "within_geography"
    hn = sc.planning_row(p, "high_need_no_vup", 100, "Rutsiro", "all")
    assert hn["households"] == pytest.approx(cell["protection_gap_households"])
    ds = sc.planning_row(p, "ds_expansion", 5, "Rutsiro", "all")
    assert ds["scope"] == "national_rule"


@needs_tables
@pytest.mark.skipif(not SCENARIOS.exists(), reason="scenario grid not built")
def test_validated_scenarios_are_reproduced(tabs):
    scen = pd.read_parquet(SCENARIOS)
    nat = lambda s, p, m: scen.query("scenario == @s and parameter_value == @p and level == 'national' and metric == @m")["value"].iloc[0]  # noqa: E731
    for pp in sc.DS_LEVELS:
        row = sc.planning_row(tabs["planning"], "ds_expansion", pp, "Rwanda", "all")
        assert row["households"] == pytest.approx(nat("coverage_expansion", pp, "households_added"))
        assert row["poor_households"] == pytest.approx(nat("coverage_expansion", pp, "poor_households_added"))
    price = sc.price_spec("simple", 12, 0)
    ds = sc.compare(tabs["planning"], "Rwanda", "all", price, sc.support_spec("ds_expansion", ds_level=2, duration_months=12))
    assert ds["direct_transfers"] == pytest.approx(nat("coverage_expansion", 2.0, "additional_annual_transfer_rwf"))
    assert round(ds["new_recipient_households"], -2) == 65_800 and round(ds["direct_transfers"] / 1e9, 1) == 8.0
    nsds = sc.compare(tabs["planning"], "Rwanda", "all", price, sc.support_spec("nsds_increase", nsds_increase_pct=10, duration_months=12))
    assert nsds["direct_transfers"] == pytest.approx(nat("benefit_increase", 10, "additional_annual_transfer_rwf_4_quarters"))
    assert nsds["recipient_households"] == pytest.approx(nat("benefit_increase", 10, "covered_households"))
    meta = tabs["meta"]
    assert meta["cross_fitted"]["precision_top20"] == pytest.approx(nat("targeting", 0.2, "precision"))


# ---------------------------------------------------------------------------
# Support comparison on the real tables
# ---------------------------------------------------------------------------
PRICE10 = sc.price_spec("simple", 12, 10)


@needs_tables
def test_costs_reconcile_to_recipients_amounts_and_periods(tabs):
    for freq, payments in [("monthly", 12), ("quarterly", 4)]:
        s = sc.support_spec("cash", rule="poverty_top", level=20, amount_rwf=9_000, frequency=freq, duration_months=12, delivery_pct=5)
        r = sc.compare(tabs["planning"], "Rutsiro", "all", PRICE10, s)
        assert r["payments"] == payments
        assert r["direct_transfers"] == pytest.approx(r["recipient_households"] * 9_000 * payments)
        assert r["delivery_costs"] == pytest.approx(0.05 * r["direct_transfers"])
        assert r["total_cost"] == pytest.approx(r["direct_transfers"] + r["delivery_costs"])
        assert r["columns"]["shock_support"]["support"] == pytest.approx(9_000 / (1 if freq == "monthly" else 3))


@needs_tables
def test_zero_assistance_reproduces_the_shock_only_column(tabs):
    for kw in [dict(amount_rwf=0), dict(amount_rwf=10_000, duration_months=0)]:
        s = sc.support_spec("cash", **{"rule": "distress_top", "level": 20, "duration_months": 12, **kw})
        r = sc.compare(tabs["planning"], "Rwanda", "all", PRICE10, s)
        assert r["columns"]["shock_support"] == r["columns"]["shock"]
        assert r["direct_transfers"] == 0 and r["total_cost"] == 0


@needs_tables
def test_zero_price_change_means_no_extra_cost(tabs):
    r = sc.compare(tabs["planning"], "Rwanda", "all", sc.price_spec("simple", 12, 0), sc.support_spec("cash", amount_rwf=1_000))
    assert r["columns"]["shock"] == r["columns"]["reference"]
    assert r["columns"]["shock_support"]["not_offset"] == 0 and r["surplus_monthly"] == 1_000


@needs_tables
def test_benefit_increase_adds_no_recipients(tabs):
    r = sc.compare(tabs["planning"], "Rwanda", "all", PRICE10, sc.support_spec("nsds_increase", nsds_increase_pct=20))
    assert r["new_recipient_households"] == 0 and r["new_recipient_people"] == 0 and r["recipient_households"] > 0
    assert r["direct_transfers"] > 0


@needs_tables
def test_cash_does_not_change_prices(tabs):
    r = sc.compare(tabs["planning"], "Rwanda", "rural", PRICE10, sc.support_spec("cash", amount_rwf=50_000))
    assert r["columns"]["shock_support"]["basket"] == r["columns"]["shock"]["basket"]
    assert r["columns"]["shock_support"]["not_offset"] == 0 and r["surplus_monthly"] > 0


@needs_tables
def test_suppressed_selections_fail_clearly(tabs):
    with pytest.raises(sc.UnsupportedScenario) as e:
        sc.compare(tabs["planning"], "Nyarugenge", "rural", PRICE10, sc.support_spec("cash"))
    assert e.value.code == "suppressed"
    hidden = tabs["groups"].query("dimension == 'all' and suppressed").iloc[0]
    with pytest.raises(sc.UnsupportedScenario):
        sc.price_result(tabs["groups"], hidden["geo"], hidden["area"], PRICE10)


@needs_tables
def test_exposed_groups_use_published_cells_only(tabs):
    res = sc.price_result(tabs["groups"], "Rwanda", "all", sc.price_spec("detailed", 12, detailed={"food": 30}))
    assert res["exposed"] and res["exposed"][0]["basket_change_pct"] >= res["exposed"][-1]["basket_change_pct"]
    poor = next(x for x in res["exposed"] if x["group"] == "poor")
    nonpoor = next(x for x in res["exposed"] if x["group"] == "nonpoor")
    assert poor["basket_change_pct"] > nonpoor["basket_change_pct"]          # food is a larger share for poorer households


@needs_tables
@needs_private
def test_saved_planning_tables_match_a_rebuild():
    fresh = bp.build_all(write=False)
    saved = dd.load_public_tables()
    pd.testing.assert_frame_equal(fresh["dashboard_groups"].reset_index(drop=True), saved["groups"], check_dtype=False)
    pd.testing.assert_frame_equal(fresh["dashboard_planning"].reset_index(drop=True), saved["planning"], check_dtype=False)
    assert {k: v for k, v in fresh["dashboard_meta"].items() if k != "built"} == {k: v for k, v in saved["meta"].items() if k != "built"}
