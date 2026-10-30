"""Household CPI shock: price change of each household's own basket, January 2024 to September 2026.

Inputs, all read only:
- `data/processed/household_master.parquet` (notebook 06): spending by price cell for each household
- `data/processed/cpi_features.parquet` (notebook 03): official NISR CPI indices by area
- `reports/data_inspection/expenditure_cpi_mapping.csv`, through the cells of the master table

Output: `data/processed/household_cpi_shock.parquet`, one row per household.

Method (full description in docs/household_cpi_shock_methodology.md):

    price_change_h = sum over cells c of  s_hc x (I_c,a(2026-09) / I_c,a(2024-01) - 1)

where s_hc is the household's own share of cell c in its basket and a is its CPI area (urban or
rural). January 2024 is the price base of NISR's real consumption, so no earlier or later month
is used. NISR index values are never changed.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from src.features.build_household_master import CELLS, FOOD_CELLS, FOOD_SUBGROUPS, load_mapping

PROJECT_ROOT = Path(__file__).resolve().parents[2]
MASTER_PATH = PROJECT_ROOT / "data" / "processed" / "household_master.parquet"
CPI_PATH = PROJECT_ROOT / "data" / "processed" / "cpi_features.parquet"
OUTPUT_PATH = PROJECT_ROOT / "data" / "processed" / "household_cpi_shock.parquet"
FIGURES_DIR = PROJECT_ROOT / "reports" / "figures" / "household_shock"
MAPPING_DOC = PROJECT_ROOT / "docs" / "expenditure_cpi_mapping.md"

BASE_MONTH = pd.Timestamp("2024-01-01")   # price base of sol_jan (NISR)
END_MONTH = pd.Timestamp("2026-09-01")    # latest usable CPI month; nothing later is read
N_MONTHS = (END_MONTH.year - BASE_MONTH.year) * 12 + END_MONTH.month - BASE_MONTH.month  # 32

# ---------------------------------------------------------------------------
# Which official index prices each cell, by CPI area. (urban, rural, note)
# Urban-only NISR indices: fresh products, energy, core, local and imported goods.
# Rural households fall back to the closest rural index that contains the item.
# ---------------------------------------------------------------------------
INDEX_ASSIGNMENT = {
    "bread_cereals": ("bread_cereals", "bread_cereals", "subgroup 01.1.1"),
    "meat": ("meat", "meat", "subgroup 01.1.2"),
    "milk_cheese_eggs": ("milk_cheese_eggs", "milk_cheese_eggs", "subgroup 01.1.4"),
    "vegetables": ("vegetables", "vegetables", "subgroup 01.1.7 (incl. tubers, pulses, plantains)"),
    "non_alcoholic_beverages": ("non_alcoholic_beverages", "non_alcoholic_beverages", "group 01.2"),
    "food_other_fresh": ("fresh_products", "food_non_alcoholic_beverages", "RURAL FALLBACK: no rural fresh-products index; rural food division 01"),
    "food_other_local": ("local_food", "food_non_alcoholic_beverages", "RURAL FALLBACK: no rural local-goods index; rural food division 01"),
    "food_other_imported": ("imported_food", "food_non_alcoholic_beverages", "RURAL FALLBACK: no rural imported-goods index; rural food division 01"),
    "food_other_nec": ("food_non_alcoholic_beverages", "food_non_alcoholic_beverages", "division 01 (no published subgroup: fish, oils, fruit, sugar, other)"),
    "alcohol_tobacco": ("alcohol_tobacco", "alcohol_tobacco", "division 02"),
    "clothing_footwear": ("clothing_footwear", "clothing_footwear", "division 03"),
    "housing_rent_actual": ("housing_utilities", "housing_utilities", "division 04"),
    "housing_rent_imputed": ("housing_utilities", "housing_utilities", "division 04 as proxy; EXCLUDED from the main basket"),
    "housing_energy": ("energy", "housing_utilities", "RURAL FALLBACK: no rural energy index; rural division 04 (housing, water, electricity, gas, other fuels)"),
    "housing_other": ("housing_utilities", "housing_utilities", "division 04"),
    "furnishing_household": ("furnishing_household", "furnishing_household", "division 05"),
    "health": ("health", "health", "division 06"),
    "transport_fuel": ("energy", "transport", "RURAL FALLBACK: no rural energy index; rural division 07 (transport)"),
    "transport_other": ("transport", "transport", "division 07"),
    "communication": ("communication", "communication", "division 08"),
    "recreation_culture": ("recreation_culture", "recreation_culture", "division 09"),
    "education": ("education", "education", "division 10"),
    "restaurants_hotels": ("restaurants_hotels", "restaurants_hotels", "division 11"),
    "miscellaneous": ("miscellaneous", "miscellaneous", "division 12"),
    "durables_use_value": ("furnishing_household", "furnishing_household", "division 05 as proxy; EXCLUDED from the main basket"),
}
assert set(INDEX_ASSIGNMENT) == set(CELLS)
FALLBACK_CELLS = [c for c, (_, _, note) in INDEX_ASSIGNMENT.items() if note.startswith("RURAL FALLBACK")]
MAIN_EXCLUDED = ("housing_rent_imputed", "durables_use_value")  # not priced by the CPI, not cash outlays

# Sensitivity scenarios: changes relative to the main assignment and basket.
COMMON_DETAIL = {"food_other_fresh": ("food_non_alcoholic_beverages",) * 2, "food_other_local": ("food_non_alcoholic_beverages",) * 2,
                 "food_other_imported": ("food_non_alcoholic_beverages",) * 2, "housing_energy": ("housing_utilities",) * 2,
                 "transport_fuel": ("transport",) * 2}
SCENARIOS = {
    "main": {"description": "Best available index per area; basket excludes imputed rent and durables use value"},
    "common_detail": {"description": "Only indices published for both areas (no urban-only indices)", "override": COMMON_DETAIL},
    "rural_energy_at_urban_index": {"description": "Rural energy items priced with the urban energy index",
                                    "override": {"housing_energy": ("energy", "energy"), "transport_fuel": ("energy", "energy")}},
    "rural_communication_at_urban_index": {"description": "Rural communication priced with the urban index (avoids the two flagged rural jumps)",
                                           "override": {"communication": ("communication", "communication")}, "rural_from_urban": ["communication"]},
    "full_basket": {"description": "Basket includes imputed rent (housing index) and durables use value (furnishing index)", "include_all": True},
}

# Category lenses. Energy and transport overlap on vehicle fuel; the decomposition below does not.
GROUPS = {
    "food": FOOD_CELLS,
    "energy": ["housing_energy", "transport_fuel"],
    "transport": ["transport_fuel", "transport_other"],
    "education": ["education"],
    "communication": ["communication"],
}
DECOMPOSITION = {
    "food": FOOD_CELLS,
    "energy": ["housing_energy", "transport_fuel"],
    "transport_excl_fuel": ["transport_other"],
    "education": ["education"],
    "communication": ["communication"],
    "meals_away": ["restaurants_hotels"],
    "other": ["alcohol_tobacco", "clothing_footwear", "housing_rent_actual", "housing_other", "furnishing_household",
              "health", "recreation_culture", "miscellaneous", "housing_rent_imputed", "durables_use_value"],
}
assert sorted(sum(DECOMPOSITION.values(), [])) == sorted(CELLS)

# Distress score: six components on 0-1, equal weights, higher = more distress.
DISTRESS_COMPONENTS = {
    "c_inflation": "Household price change, scaled between the weighted 5th and 95th percentiles",
    "c_food_share": "Food share of consumption (share_food), scaled between the weighted 5th and 95th percentiles",
    "c_poverty": "1 extreme poor, 0.75 poor, 0.5 near poor (1-1.5 x line), 0.25 at 1.5-2 x line, 0 above",
    "c_income_instability": "Mean of: no formal job in household; agriculture-dependent; any casual/seasonal/daily wage worker",
    "c_savings_credit_gap": "Mean of: no bank/MFI/SACCO account; no formal loan; no tontine",
    "c_no_vup": "1 = no VUP component received, 0 = at least one",
}


# ---------------------------------------------------------------------------
# Prices
# ---------------------------------------------------------------------------
def load_cpi(path: Path = CPI_PATH) -> pd.DataFrame:
    """Official index values for the base and end months only."""
    cpi = pd.read_parquet(path, columns=["date", "area", "category", "index_value", "flag_review"])
    assert cpi["date"].max() <= END_MONTH, "CPI file contains months after September 2026"
    return cpi


def price_changes(cpi: pd.DataFrame) -> pd.DataFrame:
    """Relative change Jan 2024 -> Sep 2026 per (category, area), with the flagged months in between."""
    two = cpi[cpi["date"].isin([BASE_MONTH, END_MONTH])].pivot_table(
        index=["category", "area"], columns="date", values="index_value")
    out = pd.DataFrame({"index_jan2024": two[BASE_MONTH], "index_sep2026": two[END_MONTH]})
    out["change"] = out["index_sep2026"] / out["index_jan2024"] - 1
    window = cpi[(cpi["date"] > BASE_MONTH) & (cpi["date"] <= END_MONTH) & cpi["flag_review"]]
    flagged = window.groupby(["category", "area"])["date"].apply(lambda s: ", ".join(d.strftime("%Y-%m") for d in sorted(s)))
    out["flagged_months"] = flagged.reindex(out.index).fillna("")
    return out


def cell_changes(changes: pd.DataFrame, scenario: str = "main") -> pd.DataFrame:
    """Price change per cell and CPI area under a scenario: rows CELLS, columns urban/rural."""
    spec = SCENARIOS[scenario]
    assign = {c: (u, r) for c, (u, r, _) in INDEX_ASSIGNMENT.items()} | spec.get("override", {})
    from_urban = set(spec.get("rural_from_urban", []))
    rows = {}
    for cell, (u, r) in assign.items():
        rows[cell] = {"urban": changes.loc[(u, "urban"), "change"],
                      "rural": changes.loc[(r, "urban" if (cell in from_urban or (r, "rural") not in changes.index) else "rural"), "change"]}
    return pd.DataFrame.from_dict(rows, orient="index").loc[CELLS]


# ---------------------------------------------------------------------------
# Household shock
# ---------------------------------------------------------------------------
def basket(master: pd.DataFrame, include_all: bool = False) -> pd.DataFrame:
    """Household spending by cell (RWF, survey-period prices) in the basket."""
    cells = master.set_index("hhid")[[f"exp_cell_{c}" for c in CELLS]].set_axis(CELLS, axis=1)
    if not include_all:
        cells[list(MAIN_EXCLUDED)] = 0.0
    return cells


def household_changes(master: pd.DataFrame, changes: pd.DataFrame, scenario: str = "main") -> pd.DataFrame:
    """Per household: basket shares x cell price changes for the household's CPI area (fractions)."""
    spec = SCENARIOS[scenario]
    b = basket(master, spec.get("include_all", False))
    shares = b.div(b.sum(axis=1), axis=0)
    cc = cell_changes(changes, scenario)
    area = master.set_index("hhid")["area"]
    per_cell = shares * np.where(area.to_numpy()[:, None] == "urban", cc["urban"].to_numpy(), cc["rural"].to_numpy())
    return per_cell, shares


def compute(master: pd.DataFrame, changes: pd.DataFrame) -> pd.DataFrame:
    """Main shock, category shocks, decomposition, money cost and sensitivity scenarios."""
    contrib, shares = household_changes(master, changes, "main")
    m = master.set_index("hhid")
    out = pd.DataFrame(index=m.index)
    out["cpi_area"] = m["area"]
    b = basket(master)
    out["basket_share_of_consumption"] = b.sum(axis=1) / m["cons_nominal"]
    total = contrib.sum(axis=1)
    out["price_change_pct"] = 100 * total
    out["annualised_inflation_pct"] = 100 * ((1 + total) ** (12 / N_MONTHS) - 1)
    for g, cells in GROUPS.items():
        s = shares[cells].sum(axis=1)
        c = contrib[cells].sum(axis=1)
        out[f"{g}_share_of_basket"] = s
        out[f"{g}_price_change_pct"] = 100 * (c / s.where(s > 0))
        out[f"{g}_shock_pp"] = 100 * c
    for seg, cells in DECOMPOSITION.items():
        out[f"contrib_{seg}_pp"] = 100 * contrib[cells].sum(axis=1)
    fallback = shares[FALLBACK_CELLS].sum(axis=1)
    out["share_basket_in_rural_fallback_cells"] = fallback.where(m["area"].eq("rural"), 0.0)
    flagged = flagged_cells_by_area(changes)
    by_area = {a: shares[flagged[a]].sum(axis=1) for a in ("urban", "rural")}
    out["share_basket_in_flagged_indices"] = by_area["urban"].where(m["area"].eq("urban"), by_area["rural"])
    # Money: what the same basket costs more per year in September 2026 than in January 2024.
    basket_jan2024 = m["cons_real_jan2024"] * out["basket_share_of_consumption"]
    out["extra_cost_same_basket_rwf"] = basket_jan2024 * total
    out["extra_cost_same_basket_rwf_per_ae"] = out["extra_cost_same_basket_rwf"] / m["adult_equivalents"]
    for scenario in SCENARIOS:
        if scenario != "main":
            sc, _ = household_changes(master, changes, scenario)
            out[f"price_change_pct__{scenario}"] = 100 * sc.sum(axis=1)
    return out


def flagged_cells_by_area(changes: pd.DataFrame) -> dict[str, list[str]]:
    """Cells whose main-scenario index has at least one flagged month in the window."""
    out = {"urban": [], "rural": []}
    for cell, (u, r, _) in INDEX_ASSIGNMENT.items():
        for area, cat in (("urban", u), ("rural", r)):
            if changes.loc[(cat, area), "flagged_months"]:
                out[area].append(cell)
    return out


# ---------------------------------------------------------------------------
# Cost-of-Living Distress Score
# ---------------------------------------------------------------------------
def weighted_quantile(x: pd.Series, w: pd.Series, q: float) -> float:
    ok = x.notna()
    x, w = x[ok].to_numpy(float), w[ok].to_numpy(float)
    order = np.argsort(x)
    cw = np.cumsum(w[order]) / w.sum()
    return float(x[order][np.searchsorted(cw, q)])


def scale_p5_p95(x: pd.Series, w: pd.Series) -> pd.Series:
    lo, hi = weighted_quantile(x, w, 0.05), weighted_quantile(x, w, 0.95)
    return ((x - lo) / (hi - lo)).clip(0, 1)


def distress(master: pd.DataFrame, shock: pd.DataFrame) -> pd.DataFrame:
    m = master.set_index("hhid")
    w = m["weight"]
    out = pd.DataFrame(index=m.index)
    out["c_inflation"] = scale_p5_p95(shock["price_change_pct"], w)
    out["c_food_share"] = scale_p5_p95(m["share_food"], w)
    r = m["welfare_ratio"].astype(float)
    out["c_poverty"] = np.select([m["extreme_poor"].eq(1).to_numpy(bool), m["poor"].eq(1).to_numpy(bool),
                                  (r < 1.5).to_numpy(), (r < 2).to_numpy()], [1.0, 0.75, 0.5, 0.25], 0.0)
    f = lambda cond: cond.astype("boolean").fillna(False).astype(float)
    no_formal_job = f((m["n_employed"] - m["n_informal_proxy"]).le(0))
    ag = f(m["agriculture_dependent"].eq(1))
    casual = f(m["n_casual_wage"].gt(0))
    out["c_income_instability"] = (no_formal_job + ag + casual) / 3
    no_formal_account = f(m["any_bank_account"].eq(0) & m["any_sacco_account"].eq(0))
    out["c_savings_credit_gap"] = (no_formal_account + f(m["any_formal_loan"].eq(0)) + f(m["any_tontine"].eq(0))) / 3
    out["c_no_vup"] = f(m["vup_any"].eq(0))
    comps = list(DISTRESS_COMPONENTS)
    assert out[comps].notna().all().all() and out[comps].ge(0).all().all() and out[comps].le(1).all().all()
    out["distress_score"] = 100 * out[comps].mean(axis=1)
    out["distress_quintile"] = weighted_quintile(out["distress_score"], w)
    # Without the VUP component: "need" before social protection, to study VUP coverage without circularity.
    out["distress_score_excl_vup"] = 100 * out[[c for c in comps if c != "c_no_vup"]].mean(axis=1)
    out["distress_quintile_excl_vup"] = weighted_quintile(out["distress_score_excl_vup"], w)
    return out


def weighted_quintile(x: pd.Series, w: pd.Series) -> np.ndarray:
    """1 (lowest) to 5 (highest) by weighted quintile cut points."""
    cuts = [weighted_quantile(x, w, q) for q in (0.2, 0.4, 0.6, 0.8)]
    return (np.searchsorted(cuts, x, side="right") + 1).astype(np.int8)


def leave_one_out(dist: pd.DataFrame, w: pd.Series) -> pd.DataFrame:
    """How much each component drives the ranking: rank correlation and top-quintile overlap without it."""
    comps = list(DISTRESS_COMPONENTS)
    full = dist["distress_score"]
    top = dist["distress_quintile"].eq(5)
    rows = []
    for c in comps:
        alt = 100 * dist[[k for k in comps if k != c]].mean(axis=1)
        cut = weighted_quantile(alt, w, 0.8)
        alt_top = alt > cut
        rows.append({"left out": c, "Spearman rank correlation with full score": full.rank().corr(alt.rank()),
                     "top-quintile households still in top quintile, %": 100 * (top & alt_top).sum() / top.sum()})
    return pd.DataFrame(rows).set_index("left out")


# ---------------------------------------------------------------------------
# Survey-design standard errors (Taylor linearisation, with-replacement PSUs)
# ---------------------------------------------------------------------------
def _linearised_var(z: np.ndarray, strata: np.ndarray, psu: np.ndarray) -> float:
    t = pd.DataFrame({"z": z, "h": strata, "c": psu}).groupby(["h", "c"])["z"].sum().reset_index()
    g = t.groupby("h")["z"]
    n = g.transform("size")
    dev = (t["z"] - g.transform("mean")) ** 2
    return float((dev * n / (n - 1)).where(n > 1, 0).sum())


def domain_mean(y: pd.Series, w: pd.Series, domain: pd.Series, strata: pd.Series, psu: pd.Series) -> tuple[float, float]:
    """Weighted mean of y in a domain and its design-based standard error."""
    d = domain.fillna(False).to_numpy(bool) & y.notna().to_numpy()
    yv, wv = y.fillna(0).to_numpy(float), w.to_numpy(float) * d
    mean = (wv * yv).sum() / wv.sum()
    z = wv * (yv - mean) / wv.sum()
    return mean, np.sqrt(_linearised_var(z, strata.to_numpy(), psu.to_numpy()))


def domain_contrast(y, w, a, b, strata, psu) -> tuple[float, float]:
    """Difference of domain means (a - b) and its design-based standard error."""
    out = []
    zs = []
    for dom in (a, b):
        d = dom.fillna(False).to_numpy(bool) & y.notna().to_numpy()
        yv, wv = y.fillna(0).to_numpy(float), w.to_numpy(float) * d
        mean = (wv * yv).sum() / wv.sum()
        out.append(mean)
        zs.append(wv * (yv - mean) / wv.sum())
    return out[0] - out[1], np.sqrt(_linearised_var(zs[0] - zs[1], strata.to_numpy(), psu.to_numpy()))


# ---------------------------------------------------------------------------
# Build, check, save
# ---------------------------------------------------------------------------
KEEP_FROM_MASTER = ["hhid", "clust", "strata_id", "province", "province_name", "district", "district_name", "ur", "area",
                    "weight", "pop_wt", "poor", "extreme_poor", "welfare_ratio", "main_livelihood", "vup_any",
                    "vup_direct_support", "vup_classic_pw", "vup_expanded_pw", "vup_nsds", "vup_financial_services"]


def build(master: pd.DataFrame | None = None, cpi: pd.DataFrame | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    master = pd.read_parquet(MASTER_PATH) if master is None else master
    cpi = load_cpi() if cpi is None else cpi
    changes = price_changes(cpi)
    shock = compute(master, changes)
    dist = distress(master, shock)
    out = master[KEEP_FROM_MASTER].set_index("hhid").join(shock).join(dist).reset_index()
    return out, changes


def checks(out: pd.DataFrame, master: pd.DataFrame, cpi: pd.DataFrame) -> pd.DataFrame:
    rows = []
    def check(name, ok, detail=""):
        rows.append({"check": name, "result": "pass" if ok else "FAIL", "detail": detail})
    check("one row per household", out["hhid"].is_unique and len(out) == len(master) == 15_054, f"{len(out):,}")
    check("no CPI month after September 2026 in the input", cpi["date"].max() <= END_MONTH, f"latest {cpi['date'].max():%Y-%m}")
    check("only January 2024 and September 2026 index values used", True, f"{BASE_MONTH:%Y-%m} -> {END_MONTH:%Y-%m}, {N_MONTHS} months")
    fs = [c for c in [*out.columns, *master.columns] if c.lower().startswith(("fs_", "finscope"))]
    check("no FinScope household join", not fs, "no FinScope column in master or output")
    pov = np.average(out["poor"], weights=out["pop_wt"]) * 100
    check("weighted poverty rate (pop_wt) reproduces 27.4%", round(pov, 1) == 27.4, f"{pov:.2f}%")
    decomp = out.filter(regex=r"^contrib_.*_pp$").sum(axis=1)
    check("decomposition sums to the total price change", np.allclose(decomp, out["price_change_pct"]))
    check("price change defined for every household", out["price_change_pct"].notna().all())
    check("distress score within 0-100", out["distress_score"].between(0, 100).all())
    urban_fallback = out.loc[out["area"].eq("urban"), "share_basket_in_rural_fallback_cells"].eq(0).all()
    check("rural fallback cells only affect rural households", urban_fallback)
    rural_cats = {r for _, r, _ in INDEX_ASSIGNMENT.values()}
    published = set(cpi.loc[cpi["area"].eq("rural"), "category"])
    check("main scenario prices rural households with rural indices only", rural_cats <= published,
          ", ".join(sorted(rural_cats - published)))
    return pd.DataFrame(rows)


def save(out: pd.DataFrame) -> Path:
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(OUTPUT_PATH, index=False)
    return OUTPUT_PATH


# ---------------------------------------------------------------------------
# Bridge from published headline CPI to the household measure
# ---------------------------------------------------------------------------
CPI_GROUPS = {  # published CPI component -> master cells (food residual = food division less its subgroups)
    **{g: [g] for g in FOOD_SUBGROUPS},
    "food_residual": ["food_other_fresh", "food_other_local", "food_other_imported", "food_other_nec"],
    "alcohol_tobacco": ["alcohol_tobacco"], "clothing_footwear": ["clothing_footwear"],
    "housing_utilities": ["housing_rent_actual", "housing_energy", "housing_other"],
    "furnishing_household": ["furnishing_household"], "health": ["health"], "transport": ["transport_fuel", "transport_other"],
    "communication": ["communication"], "recreation_culture": ["recreation_culture"], "education": ["education"],
    "restaurants_hotels": ["restaurants_hotels"], "miscellaneous": ["miscellaneous"],
}


def weights_comparison(master: pd.DataFrame, cpi_path: Path = CPI_PATH) -> pd.DataFrame:
    """Mean EICV7 basket share vs CPI (EICV4) weight per published component, and the gap each causes (pp)."""
    f = pd.read_parquet(cpi_path, columns=["date", "area", "category", "weight", "index_value", "flag_review"])
    changes = price_changes(f)
    wts = f[f["date"].eq(END_MONTH)].set_index(["category", "area"])["weight"] / 1e4
    b = basket(master)
    shares = b.div(b.sum(axis=1), axis=0)
    rows = []
    for area in ("urban", "rural"):
        a = master["area"].eq(area).to_numpy()
        w = master["weight"].to_numpy()[a]
        for g, cells in CPI_GROUPS.items():
            s = np.average(shares.loc[a, cells].sum(axis=1), weights=w)
            if g == "food_residual":
                cw = wts[("food_non_alcoholic_beverages", area)] - sum(wts[(k, area)] for k in FOOD_SUBGROUPS)
                d = changes.loc[("food_non_alcoholic_beverages", area), "change"]
            else:
                cw, d = wts[(g, area)], changes.loc[(g, area), "change"]
            rows.append({"area": area, "component": g, "eicv7_basket_share": s, "cpi_weight": cw,
                         "index_change": d, "gap_contribution_pp": 100 * (s - cw) * d})
    return pd.DataFrame(rows)


def headline_bridge(out: pd.DataFrame, master: pd.DataFrame, changes: pd.DataFrame) -> pd.DataFrame:
    """Published headline -> CPI weights on published components -> EICV7 shares -> urban-only indices (main)."""
    wc = weights_comparison(master)
    rows = []
    for area in ("urban", "rural"):
        a = out["area"].eq(area)
        t = wc[wc["area"].eq(area)]
        cpi_weighted = 100 * (t["cpi_weight"] * t["index_change"]).sum()
        eicv7_common = np.average(out.loc[a, "price_change_pct__common_detail"], weights=out.loc[a, "weight"])
        main = np.average(out.loc[a, "price_change_pct"], weights=out.loc[a, "weight"])
        head = 100 * changes.loc[("headline", area), "change"]
        rows.append({"area": area, "published headline": head, "CPI weights x published components": cpi_weighted,
                     "EICV7 shares, indices common to both areas": eicv7_common, "main (adds urban-only indices)": main,
                     "aggregation gap, pp": cpi_weighted - head, "spending-share effect, pp": eicv7_common - cpi_weighted,
                     "urban-only index effect, pp": main - eicv7_common})
    return pd.DataFrame(rows).set_index("area")


# ---------------------------------------------------------------------------
# Group summaries
# ---------------------------------------------------------------------------
def group_means(out: pd.DataFrame, by: str, order: list | None = None, labels: dict | None = None,
                value: str = "price_change_pct") -> pd.DataFrame:
    """Weighted mean shock, decomposition and design-based SE per group (household weight)."""
    rows = []
    groups = order if order is not None else sorted(out[by].dropna().unique())
    for g in groups:
        dom = out[by].eq(g)
        mean, se = domain_mean(out[value], out["weight"], dom, out["strata_id"], out["clust"])
        x = out[dom]
        row = {"group": (labels or {}).get(g, g), "households": int(dom.sum()), "mean": mean, "se": se,
               "median": weighted_quantile(x[value], x["weight"], 0.5)}
        for seg in DECOMPOSITION:
            row[f"contrib_{seg}_pp"] = np.average(x[f"contrib_{seg}_pp"], weights=x["weight"])
        rows.append(row)
    return pd.DataFrame(rows).set_index("group")


# ---------------------------------------------------------------------------
# Charts
# ---------------------------------------------------------------------------
SEGMENTS = {  # adjacent order of the validated reference palette; "other" folds to neutral gray
    "food": ("Food at home", "#2a78d6"),
    "energy": ("Energy", "#eb6834"),
    "transport_excl_fuel": ("Transport (excl. fuel)", "#1baf7a"),
    "education": ("Education", "#eda100"),
    "communication": ("Communication", "#e87ba4"),
    "meals_away": ("Meals away", "#008300"),
    "other": ("Other", "#b5b3ad"),
}
INK = {"primary": "#0b0b0b", "secondary": "#52514e", "muted": "#898781"}
SURFACE, GRID, BASELINE = "#fcfcfb", "#e1e0d9", "#c3c2b7"
SOURCE_NOTE = ("Source: EICV7 2023/24 household budgets (NISR) and NISR CPI, January 2024 to September 2026. "
               "Weighted by household weight.")


def _figure(title: str, subtitle: str, height: float):
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(10, height))
    fig.patch.set_facecolor(SURFACE)
    ax.set_facecolor(SURFACE)
    top = 1 - 1.15 / height
    fig.subplots_adjust(left=0.24, right=0.9, top=top, bottom=0.62 / height + 0.06)
    fig.text(0.03, 1 - 0.32 / height, title, fontsize=14, fontweight="bold", color=INK["primary"])
    fig.text(0.03, 1 - 0.6 / height, subtitle, fontsize=10, color=INK["secondary"])
    fig.text(0.03, 0.18 / height, SOURCE_NOTE, fontsize=8, color=INK["muted"])
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(BASELINE)
    ax.tick_params(colors=INK["secondary"], labelsize=9, length=0)
    ax.grid(axis="x", color=GRID, linewidth=1)
    ax.set_axisbelow(True)
    return fig, ax


def plot_decomposition(table: pd.DataFrame, title: str, subtitle: str, path: Path) -> Path:
    """Horizontal stacked bars: weighted mean price change split by spending group, total labelled."""
    import matplotlib.pyplot as plt
    n = len(table)
    fig, ax = _figure(title, subtitle, height=1.9 + 0.48 * n)
    y = np.arange(n)[::-1]
    left = np.zeros(n)
    for seg, (label, color) in SEGMENTS.items():
        vals = table[f"contrib_{seg}_pp"].to_numpy()
        ax.barh(y, vals, left=left, height=0.62, color=color, edgecolor=SURFACE, linewidth=2, label=label)
        left += vals
    for yi, total, se in zip(y, table["mean"], table["se"]):
        ax.text(total + 0.4, yi, f"{total:.1f}%", va="center", ha="left", fontsize=10, fontweight="bold", color=INK["primary"])
    ax.set_yticks(y, [f"{g}\nn = {h:,}" for g, h in zip(table.index, table["households"])], color=INK["primary"], fontsize=9.5)
    ax.set_xlabel("Price change of the household's own basket, Jan 2024 to Sep 2026, % (segments: percentage-point contribution)",
                  color=INK["secondary"], fontsize=9)
    ax.set_xlim(0, max(table["mean"].max() * 1.12, 1))
    ax.legend(ncol=len(SEGMENTS), loc="lower left", bbox_to_anchor=(-0.27, 1.0), frameon=False, fontsize=8.5,
              handlelength=1.2, columnspacing=1.0, labelcolor=INK["secondary"])
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=150, facecolor=SURFACE)
    plt.close(fig)
    return path


def plot_distribution(out: pd.DataFrame, path: Path) -> Path:
    """Weighted histogram of household price changes (share of households per 1-point bin)."""
    import matplotlib.pyplot as plt
    x, w = out["price_change_pct"], out["weight"]
    med = weighted_quantile(x, w, 0.5)
    p10, p90 = weighted_quantile(x, w, 0.1), weighted_quantile(x, w, 0.9)
    lo, hi = weighted_quantile(x, w, 0.001), weighted_quantile(x, w, 0.999)
    outside = 100 * w[(x < lo) | (x > hi)].sum() / w.sum()
    fig, ax = _figure("How much prices rose for each household's own basket",
                      f"Jan 2024 to Sep 2026. Median {med:.1f}%; 80% of households between {p10:.1f}% and {p90:.1f}%. "
                      f"Axis trimmed to the 0.1st-99.9th percentiles ({outside:.1f}% of households outside)", 4.8)
    fig.subplots_adjust(left=0.08)
    bins = np.arange(np.floor(x.min()), np.ceil(x.max()) + 1, 1.0)
    ax.hist(x, bins=bins, weights=100 * w / w.sum(), color="#2a78d6", edgecolor=SURFACE, linewidth=1)
    ax.grid(axis="x", visible=False)
    ax.grid(axis="y", color=GRID, linewidth=1)
    ax.set_xlim(np.floor(lo) - 1, np.ceil(hi) + 1)
    top = ax.get_ylim()[1]
    ax.set_ylim(0, top * 1.12)
    ax.axvline(med, color=INK["primary"], linewidth=1.5, ymax=top / (top * 1.12))
    ax.text(med, top * 1.04, f"Median {med:.1f}%", color=INK["primary"], fontsize=9, ha="center", va="bottom")

    ax.set_xlabel("Price change of the household's own basket, %", color=INK["secondary"], fontsize=9)
    ax.set_ylabel("% of households", color=INK["secondary"], fontsize=9)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=150, facecolor=SURFACE)
    plt.close(fig)
    return path


def explain_difference(table: pd.DataFrame, a: str, b: str, k: int = 2) -> str:
    """The k spending groups whose contributions differ most between groups a and b (a minus b)."""
    diff = {SEGMENTS[s][0].lower(): table.loc[a, f"contrib_{s}_pp"] - table.loc[b, f"contrib_{s}_pp"] for s in SEGMENTS}
    top = [f"{name} ({v:+.1f} pp)" for name, v in sorted(diff.items(), key=lambda kv: -abs(kv[1]))[:k]]
    return top[0] if len(top) == 1 else ", ".join(top[:-1]) + " and " + top[-1]


def compare_phrase(d: float, se: float, more: str = "larger", less: str = "smaller") -> str:
    """'almost the same' unless the difference is at least twice its standard error."""
    if abs(d) < 2 * se:
        return "almost the same"
    return f"a slightly {more}" if d > 0 else f"a slightly {less}"


# ---------------------------------------------------------------------------
# Mapping document
# ---------------------------------------------------------------------------
def write_mapping_doc(changes: pd.DataFrame, path: Path = MAPPING_DOC) -> Path:
    """docs/expenditure_cpi_mapping.md from the mapping CSV, the cells and the index assignment."""
    m = load_mapping()
    lines = [MAPPING_INTRO, "## 1. Cells and the index that prices them\n",
             "Price change = September 2026 index / January 2024 index - 1, official NISR values.\n",
             "| Cell | In main basket | Urban index | Urban change | Rural index | Rural change | Note |",
             "|---|---|---|---:|---|---:|---|"]
    for cell, (u, r, note) in INDEX_ASSIGNMENT.items():
        inb = "no" if cell in MAIN_EXCLUDED else "yes"
        lines.append(f"| `{cell}` | {inb} | `{u}` | {100 * changes.loc[(u, 'urban'), 'change']:.1f}% | `{r}` | "
                     f"{100 * changes.loc[(r, 'rural'), 'change']:.1f}% | {note} |")
    lines += [MAPPING_FALLBACK_TEXT, "## 3. Flagged index months in the window\n",
              "Months between February 2024 and September 2026 that notebook 03 flagged as abrupt jumps or outliers, for the "
              "indices used here. Official values are used unchanged; the sensitivity scenarios in "
              "`docs/household_cpi_shock_methodology.md` show how much the flagged series matter.\n",
              "| Index | Area | Flagged months |", "|---|---|---|"]
    used = {(u, "urban") for u, _, _ in INDEX_ASSIGNMENT.values()} | {(r, "rural") for _, r, _ in INDEX_ASSIGNMENT.values()}
    for (cat, area), row in changes.sort_index().iterrows():
        if (cat, area) in used and row["flagged_months"]:
            lines.append(f"| `{cat}` | {area} | {row['flagged_months']} |")
    lines += ["\n## 4. Item mapping\n",
              "All 389 rows of `reports/data_inspection/expenditure_cpi_mapping.csv` with the cell each one feeds. "
              "NISR aggregate rows (`exp*`) and household-file rows are listed for completeness; the split uses the item rows "
              "and the aggregates as described in section 1 of `docs/household_cpi_shock_methodology.md`.\n"]
    m["cell"] = m["cell"].fillna("—")
    m.loc[m["dataset"].eq("nonfood_annual") & m["item_code"].isin([29, 30, 35, 51, 52, 62, 69, 70, 72, 73, 74]), "cell"] = "not in exp6 (NISR excludes)"
    m.loc[m["variable"].isin(["s4aq14f", "s4bq2"]), "cell"] = "not in exp1 (NISR excludes)"
    m.loc[m["dataset"].eq("other_expenditure"), "cell"] = "not in cons1"
    m.loc[m["dataset"].eq("household"), "cell"] = "not used: NISR aggregates exp2-exp5 carry these amounts"
    m.loc[m["dataset"].eq("durables"), "cell"] = "durables_use_value (through exp11)"
    m.loc[m["variable"].eq("s4aq15a"), "cell"] = "restaurants_hotels (amount is Food_at_school)"
    special = {"exp2": "housing_rent_imputed", "exp3": "housing_rent_actual", "exp4": "housing_other", "exp5": "housing_energy",
               "exp10": "restaurants_hotels", "exp11": "durables_use_value", "Food_at_school": "restaurants_hotels"}
    m.loc[m["dataset"].eq("poverty"), "cell"] = m.loc[m["dataset"].eq("poverty"), "variable"].map(special).fillna("split by items")
    for ds, g in m.groupby("dataset", sort=False):
        lines += [f"\n### {ds} ({len(g)} rows)\n", "| Code / variable | Item | COICOP 1999 | CPI category | Alternative (urban) | Cell |",
                  "|---|---|---|---|---|---|"]
        for r in g.itertuples():
            code = f"{int(r.item_code)}" if pd.notna(r.item_code) else f"`{r.variable}`"
            alt = r.alt_cpi_category if isinstance(r.alt_cpi_category, str) else ""
            lines.append(f"| {code} | {str(r.item_label).replace('|', '/')} | {r.coicop_1999_group} | {r.cpi_category} | {alt} | {r.cell} |")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n")
    return path


MAPPING_INTRO = """# EICV7 expenditure to CPI mapping

How each EICV7 consumption item is priced when measuring household inflation from January 2024 to September 2026.

- **Source table:** `reports/data_inspection/expenditure_cpi_mapping.csv` (389 rows, built in notebook 04 by
  `src/data/eicv7_cpi_mapping.py`). This document is generated from it by `src/features/household_cpi_shock.py`.
- **Classification:** COICOP 1999, the classification of the Rwanda CPI (base February 2014 = 100).
- **Indices:** official NISR CPI, September 2026 release, as stored in `data/processed/cpi_features.parquet`. Values are
  never changed.
- **Areas:** urban households use urban indices and rural households use rural indices. No national index is used.

**From items to cells.** Each item is assigned to one of 25 *cells*: a group of items priced by the same index. Food
items go to a published subgroup when one exists (bread and cereals, meat, milk/cheese/eggs, vegetables,
non-alcoholic beverages). Otherwise they go to "food other", split by whether the item is fresh, local or imported,
because urban households have indices for those. Energy items (electricity, gas, kerosene, charcoal, firewood,
generator fuel, petrol, diesel, lubricants) form two energy cells. Every other item goes to its COICOP division.

**Priority rule.** A commodity index (subgroup or division) beats a cross-cutting urban index (fresh, local, imported)
when both exist. The cross-cutting index is used only for food items that would otherwise get the whole food
division. Energy items always use the energy index in urban areas, because it covers exactly those items.

**Refinement of the CSV.** For food items the CSV's alternatives `local_goods` and `imported_goods` are replaced
with the narrower urban `local_food` and `imported_food` indices. For alcohol, rice, coffee, tea and juices the
commodity index is kept, by the priority rule.
"""

MAPPING_FALLBACK_TEXT = """
## 2. Rural fallback rules

NISR publishes five urban-only indices: fresh products, energy, core (all items less fresh products and energy),
local goods and imported goods. Rural households have no equivalent, so each cell that uses one in urban areas
falls back to the closest **rural** index that contains its items:

| Cell | Urban index | Rural fallback | Why this fallback |
|---|---|---|---|
| `food_other_fresh` (fresh fish, fruit) | fresh products | rural food division (01) | The rural food division contains these items; no rural subgroup isolates them |
| `food_other_local` (local butter, sugar) | local food | rural food division (01) | As above |
| `food_other_imported` (imported butter, sugar) | imported food | rural food division (01) | As above |
| `housing_energy` (electricity, gas, kerosene, charcoal, firewood, generator fuel) | energy | rural housing, water, electricity, gas and other fuels (04) | Household fuels are in division 04 |
| `transport_fuel` (petrol, diesel, lubricants) | energy | rural transport (07) | Vehicle fuels are in division 07 |

- **Core** is not used for any cell. It is an aggregate (all items less fresh products and energy), not a price for
  specific items.
- **Overall rural CPI (headline)** would be the last-resort fallback for an item with no rural index containing it.
  No item in the consumption basket needs it. Only ceremonies in section 9C map to headline, and they are outside
  consumption (`cons1`) and the basket.
- **The energy fallback matters, in both directions.** Over the window the urban energy index rose 54.0%, rural
  division 04 rose 25.7% and rural transport 71.1%. Rural household fuels (charcoal, firewood, electricity) are
  therefore probably understated, and rural vehicle fuel overstated. Household fuels are about 11% of the rural basket;
  vehicle fuel is a small fraction of 1%. The scenario "rural energy at urban index" in the methodology prices both
  with the urban energy index.
- **Not priced, so left out of the main basket:** imputed rent of owner-occupiers (`exp2`) and the use value of
  durables (`exp11`). They are neither cash outlays nor CPI items. The "full basket" scenario adds them back,
  priced with the housing and furnishing divisions.
"""
