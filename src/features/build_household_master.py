"""Build the EICV7 household master table: one row per household.

Inputs, all read only:
- EICV7 public-use files in `Microdata/Cross_Section/`
- deduplicated section 9 files and household flags in `data/interim/` (notebook 05)
- `reports/data_inspection/expenditure_cpi_mapping.csv` (EICV7 item -> CPI category)

Output: `data/processed/household_master.parquet`, one row per `hhid`.

Rules:
- NISR values are never changed. Every derived quantity is a new column.
- FinScope is not used.
- `weight` is for household statistics, `pop_wt` for person statistics.
- Section 9 totals are missing, not zero, where notebook 05 set `use_in_totals` to False.
- Flags are 0/1 integers (nullable), so a weighted mean is a rate.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
EICV7_DIR = PROJECT_ROOT / "Microdata" / "Cross_Section"
INTERIM_DIR = PROJECT_ROOT / "data" / "interim"
OUTPUT_PATH = PROJECT_ROOT / "data" / "processed" / "household_master.parquet"
MAPPING_PATH = PROJECT_ROOT / "reports" / "data_inspection" / "expenditure_cpi_mapping.csv"
FOOD_CACHE = INTERIM_DIR / "s8b_food_item_values.parquet"

EXPECTED_HOUSEHOLDS = 15_054
WEEKS_PER_YEAR = 365 / 7

FILES = {
    "poverty": "CS_EICV7_poverty_file.dta",
    "household": "CS_S01_S5_S7_Household.dta",
    "person": "CS_S0_S1_S2_S3_S4_S6A_S6B_S6C_Person.dta",
    "credit": "CS_S10A1_A2_credits.dta",
    "durables": "CS_S10B_durables.dta",
    "savings": "CS_S10C_Savings.dta",
    "services": "CS_S5F_access_to_services.dta",
    "nonfood_annual": "CS_S8A1_Expenditure.dta",
    "nonfood_monthly": "CS_S8A2_Expenditure.dta",
    "nonfood_weekly": "CS_S8A3_Expenditure.dta",
    "food": "CS_S8B_Food_Expenditure_Consumption.dta",
    "vup_ds": "CS_S9D1_Direct_Support.dta",
    "vup_cpw": "CS_S9D2_Classic_Public_Work.dta",
    "vup_epw": "CS_S9D3_Expanded_Public_Work.dta",
    "vup_nsds": "CS_S9D4_NSDS.dta",
    "vup_fs": "CS_S9D5_Financial_Services.dta",
}
INTERIM_S9 = {
    "transfers_out": "s9a_transfers_out_dedup.parquet",
    "transfers_in": "s9b_transfers_in_dedup.parquet",
    "other_income": "s9e_other_income_dedup.parquet",
}

# ---------------------------------------------------------------------------
# Expenditure cells. Each cell is one price concept; together they partition cons1.
# ---------------------------------------------------------------------------
FOOD_SUBGROUPS = ["bread_cereals", "meat", "milk_cheese_eggs", "vegetables", "non_alcoholic_beverages"]
CELLS = [
    *FOOD_SUBGROUPS,
    "food_other_fresh", "food_other_local", "food_other_imported", "food_other_nec",
    "alcohol_tobacco", "clothing_footwear",
    "housing_rent_actual", "housing_rent_imputed", "housing_energy", "housing_other",
    "furnishing_household", "health", "transport_fuel", "transport_other", "communication",
    "recreation_culture", "education", "restaurants_hotels", "miscellaneous", "durables_use_value",
]
FOOD_CELLS = CELLS[:9]
ALT_FOOD_CELL = {"fresh_products": "food_other_fresh", "local_goods": "food_other_local",
                 "imported_goods": "food_other_imported"}

# exp6 equals S8A1 purchases + gifts once these 11 item codes are left out (exact for all
# 15,047 households with exp6 > 0; notebook 06, section 2). Lumpy health spending, dwelling
# materials and some durables.
EXP6_EXCLUDED_ITEMS = (29, 30, 35, 51, 52, 62, 69, 70, 72, 73, 74)
# exp1 = these person-level education components + Food_at_school for 72% of households
# exactly and is at most their sum for all; room and board (s4aq14f) and vocational
# training (s4bq2) are left out by NISR.
EXP1_COMPONENTS = ("s4aq14a", "s4aq14b", "s4aq14c", "s4aq14d", "s4aq14e", "s4aq14g", "s4aq14h")

# ---------------------------------------------------------------------------
# Code lists used in derived columns (value labels in the EICV7 files).
# ---------------------------------------------------------------------------
MARITAL_GROUPS = {1: "married", 2: "married", 3: "married", 4: "divorced_separated",
                  5: "divorced_separated", 6: "never_married", 7: "widowed"}
EDUCATION_LEVELS = {0: "none", 1: "primary", 2: "post_primary_vocational", 3: "lower_secondary",
                    4: "upper_secondary", 5: "tertiary"}
S4AQ2_TO_LEVEL = {1: 0, 2: 0, 3: 1, 4: 2, 5: 3, 6: 4, 7: 5}  # ECD and nursery count as none
WAGE_STATUS = (1, 2)                     # s6bq7: employee, paid apprentice
CASUAL_CONTRACTS = (3, 4, 5, 6)           # s6bq8: casual, seasonal, daily, other
FORMAL_CONTRACTS = (1, 2)                 # s6bq8: permanent, fixed-term
FORMAL_SECTORS = (1, 2, 6)                # s6bq5: public, mixed public/private, international NGO
LIVELIHOODS = ["own_farming", "farm_wage", "nonfarm_wage", "nonfarm_self_employment"]
IMPROVED_WALL = (4, 5, 8)                 # s5dq1: fired bricks with cement, cement blocks, stones with cement
IMPROVED_ROOF = (1, 2, 3, 5)              # s5dq2: metal sheets, clay tiles, concrete, industrial tiles
IMPROVED_FLOOR = (3, 4, 5, 6, 7)          # s5dq3: anything but beaten earth or dung
IMPROVED_WATER = (1, 2, 3, 4, 5, 6, 8, 10, 11, 14)  # s5cq3, JMP improved sources
IMPROVED_SANITATION = (1, 2, 3, 4, 5, 6)  # s5cq25, JMP improved facilities
CLEAN_COOKING = (3, 4, 5, 6)              # s5cq22a: gas, biogas, solar, electricity
TLU = {"s7aq4a": 0.7, "s7aq4b": 0.1, "s7aq4c": 0.1, "s7aq4d": 0.2, "s7aq4e": 0.01}  # FAO, sub-Saharan Africa
DURABLES = {8: "car", 9: "motorcycle", 10: "bicycle", 11: "solar_lamp", 12: "refrigerator",
            19: "mobile_basic", 20: "smartphone", 21: "computer", 23: "television", 24: "radio"}
SERVICES = {1: "drinking_water", 2: "food_market", 3: "produce_market", 4: "public_transport",
            7: "primary_school", 8: "secondary_school", 9: "district_hospital", 10: "health_centre"}
BANK_INSTITUTIONS = (1, 2, 3)             # s10cq5: commercial bank, microfinance, cooperative bank
SACCO_INSTITUTIONS = (4,)
MOBILE_MONEY_INSTITUTIONS = (5, 6)        # MoMo, Mokash
FORMAL_LOAN_SOURCES = (1, 2, 4, 7, 8, 9, 10)  # s10aq6: employer, bank, credit coop, MFI, VUP, SACCO, Mokash
INFORMAL_LOAN_SOURCES = (3, 5, 6, 11, 12)     # relative, tontine, informal lender, business, other
S9E_GROUPS = {"public_support": range(1, 12), "private_other": range(12, 24), "farm": range(24, 27)}
# Code 10 (government donations of goods such as mosquito nets) reaches ~81% of households with a
# median value of 3,000 RWF, so it is kept out of the "any public support" flag.
PUBLIC_SUPPORT_EXCL_GOODS = (1, 2, 3, 4, 5, 6, 7, 8, 9, 11)


def read(name: str, columns: list[str] | None = None) -> pd.DataFrame:
    """Read an EICV7 file with stored codes; `hhid` as int64."""
    d = pd.read_stata(EICV7_DIR / FILES[name], convert_categoricals=False, columns=columns)
    d["hhid"] = d["hhid"].astype(np.int64)
    return d


def flag(x: pd.Series) -> pd.Series:
    """Boolean (with missing) to nullable 0/1."""
    return x.astype("boolean").astype("Int8")


def any_by_hh(d: pd.DataFrame, condition: pd.Series) -> pd.Series:
    return condition.fillna(False).groupby(d["hhid"]).any()


# ---------------------------------------------------------------------------
# 1. Identifiers, design, welfare and poverty
# ---------------------------------------------------------------------------
def base_table() -> pd.DataFrame:
    p = read("poverty")
    labels = pd.read_stata(EICV7_DIR / FILES["poverty"], columns=["province", "district", "poverty"])
    strata = read("household", ["hhid", "strata_id"]).set_index("hhid")["strata_id"]
    out = pd.DataFrame({"hhid": p["hhid"]})
    out["clust"] = p["clust"].astype(np.int64)
    out["strata_id"] = out["hhid"].map(strata).astype("Int64")
    out["province"] = p["province"].astype(np.int8)
    out["province_name"] = labels["province"].astype(str).values
    out["district"] = p["district"].astype(np.int16)
    out["district_name"] = labels["district"].astype(str).values
    out["ur"] = p["ur"].astype(np.int8)
    out["area"] = out["ur"].map({1: "urban", 2: "rural"})
    out["weight"] = p["weight"]
    out["pop_wt"] = p["pop_wt"]
    out["hh_size"] = p["member"].astype(np.int16)
    out["adult_equivalents"] = p["ae"]
    # Consumption (NISR values, renamed).
    out["cons_nominal"] = p["cons1"]
    out["cons_nominal_ae"] = p["cons1ae"]
    out["hh_price_index"] = p["hh_index"]
    out["cons_real_ae_jan2024"] = p["sol_jan"]
    out["cons_real_jan2024"] = p["cons1"] / p["hh_index"]
    out["cons_real_pc_jan2024"] = out["cons_real_jan2024"] / p["member"]
    for i in range(1, 12):
        out[f"exp{i}"] = p[f"exp{i}"]
    out["food"] = p["food"]
    out["food_at_school"] = p["Food_at_school"]
    # Poverty: the poverty file codes 0/100; module files code 0/1. Harmonised to 0/1.
    out["poverty_line_jan2024"] = p["Poverty_line"]
    out["extreme_line_jan2024"] = p["Extreme_line"]
    out["poor"] = (p["pov_jan"] / 100).astype("Int8")
    out["extreme_poor"] = (p["epov_jan"] / 100).astype("Int8")
    out["welfare_category"] = p["poverty"].astype("Int8")
    out["welfare_category_name"] = labels["poverty"].astype(str).values
    out["quintile"] = p["quintile"].astype("Int8")
    out["welfare_ratio"] = p["sol_jan"] / p["Poverty_line"]
    out["near_poor"] = flag((out["welfare_ratio"] >= 1) & (out["welfare_ratio"] < 1.5))
    return out.copy()


# ---------------------------------------------------------------------------
# 2. Demographics, education and health (person file)
# ---------------------------------------------------------------------------
PERSON_COLS = ["hhid", "pid", "s1q1", "s1q2", "s1q3y", "s1q4", "s3q2", "s3q7", "s3q8", "s3q9",
               "s3q10", "s3q11", "s3q12", "s4aq1", "s4aq2", "s4aq7", "s4bq4", "s4bq8", "s4bq23c",
               "s6aq2", "s6aq4", "s6aq6", "s6bq4", "s6bq5", "s6bq7", "s6bq8"]


def read_person() -> pd.DataFrame:
    p = read("person", PERSON_COLS)
    p["age"] = p["s1q3y"].where(p["s1q3y"] < 998)
    p["is_head"] = p["s1q2"].eq(1)
    return p


def demographics(p: pd.DataFrame) -> pd.DataFrame:
    g = p.groupby("hhid")
    child, elderly = p["age"].lt(15), p["age"].ge(65)
    working = p["age"].between(15, 64)
    out = pd.DataFrame({
        "n_children_0_14": child.groupby(p["hhid"]).sum(),
        "n_working_age_15_64": working.groupby(p["hhid"]).sum(),
        "n_elderly_65plus": elderly.groupby(p["hhid"]).sum(),
        "n_children_0_4": p["age"].lt(5).groupby(p["hhid"]).sum(),
    }).astype(np.int16)
    out["dependency_ratio"] = ((out["n_children_0_14"] + out["n_elderly_65plus"])
                               / out["n_working_age_15_64"].replace(0, np.nan))
    out["no_working_age_member"] = flag(out["n_working_age_15_64"].eq(0))
    out["share_dependents"] = (out["n_children_0_14"] + out["n_elderly_65plus"]) / g.size()
    disabled = p[["s3q7", "s3q8", "s3q9", "s3q10", "s3q11", "s3q12"]].isin([3, 4]).any(axis=1)
    out["n_members_with_disability"] = disabled.groupby(p["hhid"]).sum().astype(np.int16)
    out["share_members_health_insured"] = p["s3q2"].eq(1).groupby(p["hhid"]).mean()

    level = p["s4aq2"].map(S4AQ2_TO_LEVEL).where(p["s4aq1"].ne(2), 0)
    head = p[p["is_head"]].set_index("hhid")
    head_level = level[p["is_head"]].set_axis(head.index)
    out["head_female"] = flag(head["s1q1"].eq(2))
    out["head_age"] = head["age"]
    out["head_age_over_100"] = flag(head["age"].gt(100))
    out["head_marital_status"] = head["s1q4"].map(MARITAL_GROUPS)
    out["head_education_code"] = head_level.astype("Int8")
    out["head_education_level"] = head_level.map(EDUCATION_LEVELS)
    out["head_literate"] = flag(head["s4bq4"].eq(1).where(head["s4bq4"].notna()))
    out["max_education_code"] = level.groupby(p["hhid"]).max().astype("Int8")
    out["n_children_in_school"] = (p["age"].between(6, 17) & p["s4aq7"].eq(1)).groupby(p["hhid"]).sum().astype(np.int16)
    out["any_member_mobile_phone"] = flag(any_by_hh(p, p["s4bq8"].eq(1)))
    out["any_member_mobile_money_use"] = flag(any_by_hh(p, p["s4bq23c"].eq(1)))
    return out


# ---------------------------------------------------------------------------
# 3. Employment and livelihoods (person file, main job)
# ---------------------------------------------------------------------------
def classify_jobs(p: pd.DataFrame) -> pd.DataFrame:
    """Per person: employed, livelihood type and formal/informal proxy of the main job."""
    j = p[["hhid", "pid", "is_head", "s6bq4", "s6bq5", "s6bq7", "s6bq8"]].copy()
    j["employed"] = j["s6bq7"].notna()
    farm = j["s6bq4"].eq(1)  # ISIC section A
    wage = j["s6bq7"].isin(WAGE_STATUS)
    j["livelihood"] = np.select(
        [~j["employed"], farm & ~wage, farm & wage, ~farm & wage],
        ["none", "own_farming", "farm_wage", "nonfarm_wage"], default="nonfarm_self_employment")
    formal = j["s6bq5"].isin(FORMAL_SECTORS) | (wage & j["s6bq8"].isin(FORMAL_CONTRACTS))
    j["informal_proxy"] = j["employed"] & ~formal
    j["casual_wage"] = wage & j["s6bq8"].isin(CASUAL_CONTRACTS)
    return j


def main_livelihood(j: pd.DataFrame) -> pd.Series:
    """Livelihood of most employed members; ties go to the head's, then to the order in LIVELIHOODS."""
    e = j[j["employed"]]
    counts = pd.crosstab(e["hhid"], e["livelihood"]).reindex(columns=LIVELIHOODS, fill_value=0)
    top = counts.max(axis=1)
    head = e[e["is_head"]].set_index("hhid")["livelihood"]
    pick = {}
    for h, row in counts.iterrows():
        tied = [c for c in LIVELIHOODS if row[c] == top[h]]
        pick[h] = head.get(h) if head.get(h) in tied else tied[0]
    return pd.Series(pick, name="main_livelihood")


def employment(p: pd.DataFrame) -> pd.DataFrame:
    j = classify_jobs(p)
    e = j[j["employed"]]
    g = e.groupby("hhid")
    out = pd.DataFrame(index=pd.Index(p["hhid"].unique(), name="hhid"))
    out["n_employed"] = g.size()
    for lv in LIVELIHOODS:
        out[f"n_{lv}"] = e["livelihood"].eq(lv).groupby(e["hhid"]).sum()
    out["n_informal_proxy"] = g["informal_proxy"].sum()
    out["n_casual_wage"] = g["casual_wage"].sum()
    out = out.fillna(0).astype(np.int16)
    n = out["n_employed"].replace(0, np.nan)
    out["share_employed_in_agriculture"] = (out["n_own_farming"] + out["n_farm_wage"]) / n
    out["share_employed_informal_proxy"] = out["n_informal_proxy"] / n
    out["agriculture_dependent"] = flag(out["share_employed_in_agriculture"].ge(0.5).where(n.notna()))
    out["any_wage_worker"] = flag((out["n_farm_wage"] + out["n_nonfarm_wage"]).gt(0))
    out["any_nonfarm_wage_worker"] = flag(out["n_nonfarm_wage"].gt(0))
    out["any_self_employed"] = flag((out["n_own_farming"] + out["n_nonfarm_self_employment"]).gt(0))
    out["any_agricultural_activity"] = flag(any_by_hh(p, p["s6aq2"].eq(1) | p["s6aq4"].eq(1)))
    out["any_nonfarm_business"] = flag(any_by_hh(p, p["s6aq6"].eq(1)) | out["n_nonfarm_self_employment"].gt(0))
    out["main_livelihood"] = main_livelihood(j).reindex(out.index).fillna("no_employed_member")
    head = j[j["is_head"]].set_index("hhid")
    out["head_employed"] = flag(head["employed"])
    out["head_livelihood"] = head["livelihood"]
    out["head_informal_proxy"] = flag(head["informal_proxy"].where(head["employed"]))
    return out


# ---------------------------------------------------------------------------
# 4. Expenditure: split NISR aggregates exp1-exp11 into price cells
# ---------------------------------------------------------------------------
def load_mapping() -> pd.DataFrame:
    m = pd.read_csv(MAPPING_PATH)
    m["cell"] = m.apply(cell_of, axis=1)
    return m


def cell_of(row: pd.Series) -> str | None:
    cat, alt = row["cpi_category"], row["alt_cpi_category"]
    if cat in FOOD_SUBGROUPS:
        return cat
    if cat == "food_non_alcoholic_beverages":
        return ALT_FOOD_CELL.get(alt, "food_other_nec")
    if alt == "energy":
        return {"housing_utilities": "housing_energy", "transport": "transport_fuel"}[cat]
    if cat == "housing_utilities":
        return "housing_other"
    if cat == "transport":
        return "transport_other"
    return cat if cat in CELLS else None


def food_item_values(rebuild: bool = False) -> pd.DataFrame:
    """Household x item value of food consumed at home over diary visits 2-5 (7 days), RWF.

    Quantities consumed from purchases, own production and gifts are valued at the household's
    own unit value for the item, else the median unit value of the item and unit in the same area,
    else in the country. Own production uses the household's reported price when given.
    The cache in data/interim/ is rebuilt only on request (reading the 1.1 GB file takes ~30 s).
    """
    if FOOD_CACHE.exists() and not rebuild:
        return pd.read_parquet(FOOD_CACHE)
    visits = (2, 3, 4, 5)
    q = ["s8bq3a", "s8bq3b", "s8bq4", "s8bq7b", "s8bq8", "s8bq10", "s8bq10a", "s8bq12"]
    cols = ["hhid", "ur", "s8bq0"] + [f"{x}_v{v}" for v in visits for x in q]
    raw = pd.concat(pd.read_stata(EICV7_DIR / FILES["food"], convert_categoricals=False,
                                  columns=cols, chunksize=300_000), ignore_index=True)
    long = pd.concat([raw[["hhid", "ur", "s8bq0"]].assign(**{x: raw[f"{x}_v{v}"] for x in q})
                      for v in visits], ignore_index=True)
    long = long[long[["s8bq4", "s8bq8", "s8bq10", "s8bq12"]].fillna(0).gt(0).any(axis=1)].copy()
    long["hhid"] = long["hhid"].astype(np.int64)
    long["unit"] = long["s8bq7b"].fillna(long["s8bq3b"])
    bought = long["s8bq3a"].gt(0) & long["s8bq4"].gt(0) & long["s8bq3b"].eq(long["unit"])
    uv = (long["s8bq4"] / long["s8bq3a"]).where(bought)
    key = ["hhid", "s8bq0", "unit"]
    hh_tot = long[bought].groupby(key)[["s8bq4", "s8bq3a"]].sum()
    hh_uv = (hh_tot["s8bq4"] / hh_tot["s8bq3a"]).rename("hh_uv")
    med_area = uv.groupby([long["s8bq0"], long["unit"], long["ur"]]).median().rename("med_area")
    med_all = uv.groupby([long["s8bq0"], long["unit"]]).median().rename("med_all")
    long = (long.join(hh_uv, on=key).join(med_area, on=["s8bq0", "unit", "ur"])
            .join(med_all, on=["s8bq0", "unit"]))
    market = long["hh_uv"].fillna(long["med_area"]).fillna(long["med_all"])
    own_price = long["s8bq10a"].where(long["s8bq10a"].gt(0))
    long["value_purchased"] = long["s8bq8"].fillna(0) * market.fillna(own_price)
    long["value_own"] = long["s8bq10"].fillna(0) * own_price.fillna(market)
    long["value_gift"] = long["s8bq12"].fillna(0) * market.fillna(own_price)
    long["unpriced"] = long[["value_purchased", "value_own", "value_gift"]].isna().any(axis=1)
    out = (long.groupby(["hhid", "s8bq0"])
           .agg(value_purchased=("value_purchased", "sum"), value_own=("value_own", "sum"),
                value_gift=("value_gift", "sum"), purchase_value=("s8bq4", "sum"),
                unpriced_rows=("unpriced", "sum"))
           .reset_index().rename(columns={"s8bq0": "item_code"}))
    out["value_total"] = out[["value_purchased", "value_own", "value_gift"]].sum(axis=1)
    FOOD_CACHE.parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(FOOD_CACHE, index=False)
    return out


def item_values(mapping: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Item values per NISR aggregate, as long frames (hhid, cell, value)."""
    def with_cell(d: pd.DataFrame, dataset: str, item: str, value: pd.Series) -> pd.DataFrame:
        cells = mapping[mapping["dataset"].eq(dataset)].set_index("item_code")["cell"]
        x = pd.DataFrame({"hhid": d["hhid"], "cell": d[item].map(cells), "value": value})
        assert x.loc[x["value"].gt(0), "cell"].notna().all(), f"unmapped {dataset} item"
        return x[x["value"].gt(0)]

    a1 = read("nonfood_annual")
    a1 = a1[~a1["s8a1q0"].isin(EXP6_EXCLUDED_ITEMS)]
    a2 = read("nonfood_monthly")
    a3 = read("nonfood_weekly")
    food = food_item_values()
    out = {
        "exp6": with_cell(a1, "nonfood_annual", "s8a1q0", a1["s8a1q3"].fillna(0) + a1["s8a1q6"].fillna(0)),
        "exp7": with_cell(a2, "nonfood_monthly", "s8a2q0", a2["s8a2q3"].fillna(0) + a2["s8a2q6"].fillna(0)),
        "exp8": with_cell(a3, "nonfood_weekly", "s8a3q0", a3["s8a3q3"].fillna(0) + a3["s8a3q6"].fillna(0)
                          + (a3["s08a4_5"] * a3["s08a4_7"]).fillna(0)),
        "exp9": with_cell(food, "food", "item_code", food["value_total"]),
    }
    person = read("person", ["hhid", *EXP1_COMPONENTS])
    pcells = mapping[mapping["dataset"].eq("person")].set_index("variable")["cell"]
    parts = [pd.DataFrame({"hhid": person["hhid"], "cell": pcells[c], "value": person[c].fillna(0)})
             for c in EXP1_COMPONENTS]
    school = read("poverty", ["hhid", "Food_at_school"])
    parts.append(pd.DataFrame({"hhid": school["hhid"], "cell": "restaurants_hotels", "value": school["Food_at_school"]}))
    edu = pd.concat(parts, ignore_index=True)
    out["exp1"] = edu[edu["value"].gt(0)]
    return out


def split_aggregate(base: pd.DataFrame, agg: str, items: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series]:
    """Split NISR aggregate `agg` across cells in proportion to the household's own item values.

    Households with agg > 0 but no item values get the weighted item composition of their area.
    Returns cell amounts (hhid x CELLS) and a 0/1 fallback flag.
    """
    by_cell = items.groupby(["hhid", "cell"])["value"].sum().unstack(fill_value=0.0)
    by_cell = by_cell.reindex(columns=CELLS, fill_value=0.0)
    total = by_cell.sum(axis=1)
    prop = by_cell.div(total, axis=0)
    b = base.set_index("hhid")
    w = b["weight"].reindex(by_cell.index)
    area_prop = by_cell.mul(w, axis=0).groupby(b["ur"].reindex(by_cell.index)).sum()
    area_prop = area_prop.div(area_prop.sum(axis=1), axis=0)
    prop = prop.reindex(b.index)
    fallback = b[agg].gt(0) & prop.isna().all(axis=1)
    prop.loc[fallback] = area_prop.reindex(b.loc[fallback, "ur"]).to_numpy()
    amounts = prop.fillna(0.0).mul(b[agg], axis=0)
    return amounts, flag(fallback)


def expenditure(base: pd.DataFrame) -> pd.DataFrame:
    mapping = load_mapping()
    items = item_values(mapping)
    b = base.set_index("hhid")
    cells = pd.DataFrame(0.0, index=b.index, columns=CELLS)
    fallbacks = {}
    for agg, it in items.items():
        amounts, fb = split_aggregate(base, agg, it)
        cells += amounts
        fallbacks[agg] = fb
    direct = {"exp2": "housing_rent_imputed", "exp3": "housing_rent_actual", "exp4": "housing_other",
              "exp5": "housing_energy", "exp10": "restaurants_hotels", "exp11": "durables_use_value"}
    for agg, cell in direct.items():
        cells[cell] += b[agg].fillna(0)  # exp11 is missing for 1.7% of households; cons1 counts it as 0
    out = cells.add_prefix("exp_cell_")
    cons = b["cons_nominal"]
    share = lambda cols: cells[cols].sum(axis=1) / cons
    out["share_food"] = share(FOOD_CELLS)
    out["share_food_nisr"] = b["food"] / cons
    out["share_meals_away"] = b["exp10"] / cons
    out["share_alcohol_tobacco"] = share(["alcohol_tobacco"])
    out["share_housing_utilities"] = share(["housing_rent_actual", "housing_rent_imputed", "housing_energy", "housing_other"])
    out["share_housing_utilities_excl_imputed_rent"] = share(["housing_rent_actual", "housing_energy", "housing_other"])
    out["share_energy"] = share(["housing_energy", "transport_fuel"])
    out["share_transport"] = share(["transport_fuel", "transport_other"])
    out["share_education"] = share(["education"])
    out["share_education_nisr"] = b["exp1"] / cons
    out["share_communication"] = share(["communication"])
    out["share_health"] = share(["health"])
    food = food_item_values().groupby("hhid")[["value_own", "value_total"]].sum()
    out["share_food_own_produced"] = (food["value_own"] / food["value_total"]).reindex(b.index)
    out["n_aggregates_split_by_area_average"] = pd.DataFrame(fallbacks).sum(axis=1).astype(np.int8)
    return out


# ---------------------------------------------------------------------------
# 5. Housing, assets and service access
# ---------------------------------------------------------------------------
def housing_assets_services(base: pd.DataFrame) -> pd.DataFrame:
    h = read("household").set_index("hhid")
    out = pd.DataFrame(index=h.index)
    out["tenure_owner"] = flag(h["s5aq8"].eq(1))
    out["tenure_renter"] = flag(h["s5aq8"].eq(2))
    out["sleeping_rooms"] = h["s5aq3"]
    size = base.set_index("hhid")["hh_size"]
    out["persons_per_sleeping_room"] = size / h["s5aq3"].where(h["s5aq3"].gt(0))
    out["wall_material"] = h["s5dq1"].astype("Int8")
    out["roof_material"] = h["s5dq2"].astype("Int8")
    out["floor_material"] = h["s5dq3"].astype("Int8")
    out["improved_wall"] = flag(h["s5dq1"].isin(IMPROVED_WALL).where(h["s5dq1"].notna()))
    out["improved_roof"] = flag(h["s5dq2"].isin(IMPROVED_ROOF).where(h["s5dq2"].notna()))
    out["improved_floor"] = flag(h["s5dq3"].isin(IMPROVED_FLOOR).where(h["s5dq3"].notna()))
    out["improved_drinking_water"] = flag(h["s5cq3"].isin(IMPROVED_WATER).where(h["s5cq3"].notna() & h["s5cq3"].ne(99)))
    out["electricity_any"] = flag(h["s5cq14"].isin([1, 2, 3]).where(h["s5cq14"].notna()))
    out["electricity_grid"] = flag(h["s5cq14"].isin([1, 3]).where(h["s5cq14"].notna()))
    out["clean_cooking_fuel"] = flag(h["s5cq22a"].isin(CLEAN_COOKING).where(h["s5cq22a"].notna()))
    out["cooking_fuel_firewood"] = flag(h["s5cq22a"].eq(1).where(h["s5cq22a"].notna()))
    out["cooking_fuel_charcoal"] = flag(h["s5cq22a"].eq(2).where(h["s5cq22a"].notna()))
    improved_san = h["s5cq25"].isin(IMPROVED_SANITATION)
    out["improved_sanitation"] = flag(improved_san.where(h["s5cq25"].notna()))
    out["basic_sanitation"] = flag((improved_san & h["s5cq26"].eq(2)).where(h["s5cq25"].notna()))
    out["internet_at_home"] = flag(h["s5cq20a"].eq(1).where(h["s5cq20a"].notna()))
    out["any_shock_12m"] = flag(h["s5eq1"].eq(1).where(h["s5eq1"].notna()))
    out["shock_high_food_prices"] = flag(h[["s5eq2a", "s5eq2b", "s5eq2c"]].eq(8).any(axis=1))
    out["girinka_cow_received"] = flag(h["s7a2q1"].eq(1).where(h["s7a2q1"].notna()))
    stock = h[list(TLU)].mul(h["s7aq4"].eq(1), axis=0).fillna(0)
    for c, name in zip(TLU, ["cattle", "goats", "sheep", "pigs", "poultry"]):
        out[f"n_{name}"] = stock[c]
    out["tropical_livestock_units"] = sum(stock[c] * w for c, w in TLU.items())
    out["owns_livestock"] = flag(h["s7aq4"].eq(1).where(h["s7aq4"].notna()))

    dur = read("durables", ["hhid", "s10bq0", "s10bq2"])
    counts = dur.pivot_table(index="hhid", columns="s10bq0", values="s10bq2", aggfunc="sum")
    for code, name in DURABLES.items():
        out[f"owns_{name}"] = flag(counts[code].reindex(out.index).fillna(0).gt(0))
    out["owns_mobile_phone"] = flag(out["owns_mobile_basic"].eq(1) | out["owns_smartphone"].eq(1))
    key_assets = ["owns_radio", "owns_television", "owns_mobile_phone", "owns_bicycle", "owns_motorcycle",
                  "owns_car", "owns_refrigerator", "owns_computer"]
    out["n_key_assets"] = out[key_assets].sum(axis=1).astype(np.int8)

    sv = read("services", ["hhid", "s5fq0", "s5fq3a", "s5fq3b"])
    sv["minutes"] = sv["s5fq3a"].fillna(0) * 60 + sv["s5fq3b"].fillna(0)
    sv.loc[sv["s5fq3a"].isna() & sv["s5fq3b"].isna(), "minutes"] = np.nan
    mins = sv.pivot_table(index="hhid", columns="s5fq0", values="minutes", aggfunc="first")
    for code, name in SERVICES.items():
        out[f"minutes_to_{name}"] = mins.get(code).reindex(out.index) if code in mins else np.nan
    return out


# ---------------------------------------------------------------------------
# 6. Savings and credit (EICV7 section 10)
# ---------------------------------------------------------------------------
def finance() -> pd.DataFrame:
    s = read("savings", ["hhid", "s10cq1", "s10cq4", "s10cq5", "s10cq8"])
    acct = s["s10cq4"].eq(1)
    out = pd.DataFrame({
        "any_account": any_by_hh(s, acct),
        "any_bank_account": any_by_hh(s, acct & s["s10cq5"].isin(BANK_INSTITUTIONS)),
        "any_sacco_account": any_by_hh(s, acct & s["s10cq5"].isin(SACCO_INSTITUTIONS)),
        "any_mobile_money_account": any_by_hh(s, acct & s["s10cq5"].isin(MOBILE_MONEY_INSTITUTIONS)),
        "any_tontine": any_by_hh(s, s["s10cq8"].eq(1)),
    })
    c = read("credit", ["hhid", "s10aq1", "s10aq3", "s10aq6"])
    out["loan_denied_12m"] = any_by_hh(c, c["s10aq1"].eq(1))
    out["any_loan_12m"] = any_by_hh(c, c["s10aq3"].eq(1))
    out["any_formal_loan"] = any_by_hh(c, c["s10aq6"].isin(FORMAL_LOAN_SOURCES))
    out["any_informal_loan"] = any_by_hh(c, c["s10aq6"].isin(INFORMAL_LOAN_SOURCES))
    out["n_loans"] = c["s10aq6"].notna().groupby(c["hhid"]).sum()
    out["any_savings_instrument"] = out["any_account"] | out["any_tontine"]
    out["n_loans"] = out["n_loans"].astype(np.int16)
    for col in out.columns.drop("n_loans"):
        out[col] = flag(out[col])
    return out


# ---------------------------------------------------------------------------
# 7. VUP and other social protection
# ---------------------------------------------------------------------------
def vup() -> pd.DataFrame:
    ds = read("vup_ds", ["hhid", "s9d1q2", "s9d1q4"])
    cpw = read("vup_cpw", ["hhid", "s9d2q1", "s9d2q3", "s9d2q4", "s9d2q11"])
    epw = read("vup_epw", ["hhid", "s9d3q1", "s9d3q10"])
    nsds = read("vup_nsds", ["hhid", "s9d4q1", "s9d4q7", "s9d4q8"])
    fs = read("vup_fs", ["hhid", "s9d5q1", "s9d5q2", "s9d5q4"])
    out = pd.DataFrame({
        "vup_direct_support": any_by_hh(ds, ds["s9d1q2"].eq(1)),
        "vup_classic_pw": any_by_hh(cpw, cpw["s9d2q1"].eq(1)),
        "vup_expanded_pw": any_by_hh(epw, epw["s9d3q1"].eq(1)),
        "vup_nsds": any_by_hh(nsds, nsds["s9d4q1"].eq(1)),
        "vup_fs_applied": any_by_hh(fs, fs["s9d5q1"].eq(1)),
        "vup_financial_services": any_by_hh(fs, fs["s9d5q2"].eq(1)),
    })
    components = ["vup_direct_support", "vup_classic_pw", "vup_expanded_pw", "vup_nsds", "vup_financial_services"]
    out["vup_any"] = out[components].any(axis=1)
    out["vup_n_components"] = out[components].sum(axis=1).astype(np.int8)
    for c in out.columns:
        if c != "vup_n_components":
            out[c] = flag(out[c])
    amt = lambda d, col, cond: d[col].where(cond).groupby(d["hhid"]).sum(min_count=1)
    out["vup_ds_amount_12m"] = amt(ds, "s9d1q4", ds["s9d1q2"].eq(1))
    c1 = cpw.set_index("hhid")
    out["vup_cpw_months_12m"] = c1["s9d2q3"]
    out["vup_cpw_daily_wage"] = c1["s9d2q4"]
    out["vup_cpw_amount_12m"] = c1["s9d2q11"]
    out["vup_cpw_amount_missing"] = flag(out["vup_classic_pw"].eq(1) & out["vup_cpw_amount_12m"].isna())
    out["vup_epw_amount_12m"] = amt(epw, "s9d3q10", epw["s9d3q1"].eq(1))
    epw_missing = (epw["s9d3q1"].eq(1) & epw["s9d3q10"].isna()).groupby(epw["hhid"]).any()
    out["vup_epw_amount_missing"] = flag(epw_missing)
    on = nsds["s9d4q1"].eq(1)
    out["vup_nsds_quarters_paid_12m"] = nsds["s9d4q7"].where(on).groupby(nsds["hhid"]).max()
    out["vup_nsds_quarterly_payment"] = amt(nsds, "s9d4q8", on)
    out["vup_nsds_amount_12m_est"] = (nsds["s9d4q8"] * nsds["s9d4q7"]).where(on).groupby(nsds["hhid"]).sum(min_count=1)
    out["vup_fs_loan_amount"] = amt(fs, "s9d5q4", fs["s9d5q2"].eq(1))
    return out


# ---------------------------------------------------------------------------
# 8. Transfers and other income (deduplicated section 9, notebook 05)
# ---------------------------------------------------------------------------
def transfers_income() -> pd.DataFrame:
    flags = pd.read_parquet(INTERIM_DIR / "s9_dedup_household_flags.parquet").set_index("hhid")
    t_in = pd.read_parquet(INTERIM_DIR / INTERIM_S9["transfers_in"])
    t_out = pd.read_parquet(INTERIM_DIR / INTERIM_S9["transfers_out"])
    inc = pd.read_parquet(INTERIM_DIR / INTERIM_S9["other_income"])
    for d in (t_in, t_out, inc):
        d["hhid"] = d["hhid"].astype(np.int64)
    usable = lambda name: flags[f"{name}_use_in_totals"]
    out = pd.DataFrame(index=flags.index)

    out["remittances_received_12m"] = t_in["s9bq8"].fillna(0).groupby(t_in["hhid"]).sum()
    out["any_remittance_received"] = flag(any_by_hh(t_in, t_in["s9bq0"].eq(1)))
    sent = t_out[["s9aq7", "s9aq10", "s9aq12"]].sum(axis=1)
    out["transfers_sent_12m"] = sent.groupby(t_out["hhid"]).sum()
    inc["group"] = pd.cut(inc["s9eq1"], [0, 11, 23, 26], labels=list(S9E_GROUPS)).astype(str)
    by_group = inc.pivot_table(index="hhid", columns="group", values="s9eq4", aggfunc="sum", fill_value=0)
    for g in S9E_GROUPS:
        out[f"income_{g}_12m"] = by_group[g]
    out["other_income_total_12m"] = by_group[list(S9E_GROUPS)].sum(axis=1)
    received = inc["s9eq2"].eq(1)
    out["any_public_support"] = flag(any_by_hh(inc, inc["s9eq1"].isin(PUBLIC_SUPPORT_EXCL_GOODS) & received))
    out["received_govt_goods_donation"] = flag(any_by_hh(inc, inc["s9eq1"].eq(10) & received))
    # Notebook 05 rule: unusable section 9 totals are missing, not zero.
    for col, name in [("remittances_received_12m", "transfers_in"), ("any_remittance_received", "transfers_in"),
                      ("transfers_sent_12m", "transfers_out")] + [(c, "other_income") for c in
                      [*[f"income_{g}_12m" for g in S9E_GROUPS], "other_income_total_12m", "any_public_support",
                       "received_govt_goods_donation"]]:
        out.loc[~usable(name), col] = pd.NA
    out["s9_version_conflict"] = flag(flags["s9_version_conflict"])
    return out


# ---------------------------------------------------------------------------
# Assemble, check, document
# ---------------------------------------------------------------------------
def build() -> pd.DataFrame:
    base = base_table()
    person = read_person()
    parts = [demographics(person), employment(person), expenditure(base),
             housing_assets_services(base), finance(), vup(), transfers_income()]
    index = pd.Index(base["hhid"], name="hhid")
    for part in parts:
        assert part.index.is_unique, "a block has duplicate hhid"
        assert set(part.index) == set(index), "a block does not cover every household"
    master = pd.concat([base.set_index("hhid"), *[part.reindex(index) for part in parts]], axis=1)
    return master.copy().reset_index()


def checks(master: pd.DataFrame) -> pd.DataFrame:
    rows = []
    def check(name, ok, detail=""):
        rows.append({"check": name, "result": "pass" if ok else "FAIL", "detail": detail})
    w, pw = master["weight"], master["pop_wt"]
    pov = np.average(master["poor"], weights=pw) * 100
    ext = np.average(master["extreme_poor"], weights=pw) * 100
    check("one row per household (hhid unique)", master["hhid"].is_unique)
    check(f"expected {EXPECTED_HOUSEHOLDS:,} rows", len(master) == EXPECTED_HOUSEHOLDS, f"{len(master):,}")
    check("poverty rate with pop_wt rounds to 27.4%", round(pov, 1) == 27.4, f"{pov:.2f}%")
    check("extreme poverty with pop_wt rounds to 5.4%", round(ext, 1) == 5.4, f"{ext:.2f}%")
    check("poor == (sol_jan < poverty line)",
          master["poor"].eq((master["cons_real_ae_jan2024"] < master["poverty_line_jan2024"]).astype(int)).all())
    check("extreme_poor == (sol_jan < extreme line)",
          master["extreme_poor"].eq((master["cons_real_ae_jan2024"] < master["extreme_line_jan2024"]).astype(int)).all())
    check("pop_wt == weight x hh_size", np.allclose(pw, w * master["hh_size"]))
    cells = master.filter(like="exp_cell_").sum(axis=1)
    exp_sum = master[[f"exp{i}" for i in range(1, 12)]].astype(float).sum(axis=1)
    check("expenditure cells sum to exp1 + ... + exp11", np.allclose(cells, exp_sum, rtol=1e-12, atol=1e-6),
          f"max abs diff {np.abs(cells - exp_sum).max():.2e} RWF")
    check("cons_nominal == exp1 + ... + exp11 (float32 storage)", np.allclose(master["cons_nominal"], exp_sum, rtol=1e-6),
          f"max abs diff {np.abs(master['cons_nominal'] - exp_sum).max():.2f} RWF")
    check("all 30 districts present", master["district"].nunique() == 30, f"{master['district'].nunique()}")
    check("all 5 provinces present", master["province"].nunique() == 5)
    check("strata_id complete", master["strata_id"].notna().all(), f"{master['strata_id'].nunique()} strata")
    comps = master[["vup_direct_support", "vup_classic_pw", "vup_expanded_pw", "vup_nsds", "vup_financial_services"]]
    check("vup_any == any of the five components", master["vup_any"].eq(comps.eq(1).any(axis=1).astype(int)).all())
    conflict = master["s9_version_conflict"].eq(1)
    check("version-conflict households have missing section 9 totals",
          master.loc[conflict, ["remittances_received_12m", "transfers_sent_12m", "other_income_total_12m"]].isna().all().all(),
          f"{int(conflict.sum())} households")
    check("no FinScope columns", not any(c.startswith(("fs_", "finscope")) for c in master.columns))
    check("NSDS amount from s9d4q8 only", "vup_nsds_quarterly_payment" in master and
          not any("s9d4q8" in c and c[-1] in "abcd" for c in master.columns))
    return pd.DataFrame(rows)


def save(master: pd.DataFrame) -> Path:
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    master.to_parquet(OUTPUT_PATH, index=False)
    return OUTPUT_PATH


# ---------------------------------------------------------------------------
# Data dictionary. One entry per column; a trailing "*" documents a family of columns.
# (column, block, description, source and rule)
# ---------------------------------------------------------------------------
P, H, PE, S9 = "poverty file", "household file", "person file", "data/interim (notebook 05)"
DICTIONARY = [
    # Identifiers and design
    ("hhid", "Identifiers and design", "Household ID; primary key", f"{P} `hhid`, cast to int64"),
    ("clust", "Identifiers and design", "Primary sampling unit (1,674 clusters)", f"{P} `clust`"),
    ("strata_id", "Identifiers and design", "Sampling stratum (60 = district x urban/rural)", f"{H} `strata_id`"),
    ("province", "Identifiers and design", "Province code (1 Kigali, 2 South, 3 West, 4 North, 5 East)", f"{P} `province`"),
    ("province_name", "Identifiers and design", "Province name", f"{P} value label of `province`"),
    ("district", "Identifiers and design", "District code (11-57)", f"{P} `district`"),
    ("district_name", "Identifiers and design", "District name", f"{P} value label of `district`"),
    ("ur", "Identifiers and design", "Urban/rural code (1 urban, 2 rural); selects the CPI area", f"{P} `ur`"),
    ("area", "Identifiers and design", "'urban' or 'rural'", "from `ur`"),
    ("weight", "Identifiers and design", "Household weight. Use for household-level estimates", f"{P} `weight`"),
    ("pop_wt", "Identifiers and design", "Population weight (= weight x hh_size). Use for person-level estimates such as poverty rates", f"{P} `pop_wt`"),
    # Welfare and poverty
    ("hh_size", "Welfare and poverty", "Household size (members)", f"{P} `member`; equals the roster count"),
    ("adult_equivalents", "Welfare and poverty", "Household size in adult equivalents", f"{P} `ae`"),
    ("cons_nominal", "Welfare and poverty", "Annual consumption, survey-period prices, RWF (NISR aggregate)", f"{P} `cons1`"),
    ("cons_nominal_ae", "Welfare and poverty", "Annual consumption per adult equivalent, survey-period prices, RWF", f"{P} `cons1ae`"),
    ("hh_price_index", "Welfare and poverty", "NISR household Paasche price index to national January 2024 prices", f"{P} `hh_index`"),
    ("cons_real_ae_jan2024", "Welfare and poverty", "Real consumption per adult equivalent, January 2024 prices, RWF. NISR's welfare measure", f"{P} `sol_jan` (= cons1ae / hh_index)"),
    ("cons_real_jan2024", "Welfare and poverty", "Real household consumption, January 2024 prices, RWF", "cons1 / hh_index"),
    ("cons_real_pc_jan2024", "Welfare and poverty", "Real consumption per person, January 2024 prices, RWF", "cons_real_jan2024 / hh_size"),
    ("exp1", "Welfare and poverty", "NISR aggregate: education (includes food at school)", f"{P} `exp1`"),
    ("exp2", "Welfare and poverty", "NISR aggregate: imputed rent of owner-occupiers", f"{P} `exp2`"),
    ("exp3", "Welfare and poverty", "NISR aggregate: actual rent", f"{P} `exp3`"),
    ("exp4", "Welfare and poverty", "NISR aggregate: water", f"{P} `exp4`"),
    ("exp5", "Welfare and poverty", "NISR aggregate: electricity", f"{P} `exp5`"),
    ("exp6", "Welfare and poverty", "NISR aggregate: annual non-food items (S8A1)", f"{P} `exp6`"),
    ("exp7", "Welfare and poverty", "NISR aggregate: monthly non-food items (S8A2)", f"{P} `exp7`"),
    ("exp8", "Welfare and poverty", "NISR aggregate: frequent non-food items (S8A3)", f"{P} `exp8`"),
    ("exp9", "Welfare and poverty", "NISR aggregate: food and drink consumed at home, incl. own production (S8B)", f"{P} `exp9`"),
    ("exp10", "Welfare and poverty", "NISR aggregate: food away from home (S8C)", f"{P} `exp10`"),
    ("exp11", "Welfare and poverty", "NISR aggregate: use value of durable goods (S10B). Missing for 1.7% of households; cons1 counts it as 0", f"{P} `exp11`"),
    ("food", "Welfare and poverty", "NISR total food (= exp9 + exp10 + food at school). Never add to exp1", f"{P} `food`"),
    ("food_at_school", "Welfare and poverty", "Food at school; counted in both exp1 and food", f"{P} `Food_at_school`"),
    ("poverty_line_jan2024", "Welfare and poverty", "Poverty line, RWF per adult equivalent per year, January 2024 prices (560,127)", f"{P} `Poverty_line`"),
    ("extreme_line_jan2024", "Welfare and poverty", "Extreme (food) poverty line, January 2024 prices (356,432)", f"{P} `Extreme_line`"),
    ("poor", "Welfare and poverty", "1 = poor. Harmonised: poverty file codes 0/100, module files 0/1", f"{P} `pov_jan` / 100"),
    ("extreme_poor", "Welfare and poverty", "1 = extremely poor (harmonised to 0/1)", f"{P} `epov_jan` / 100"),
    ("welfare_category", "Welfare and poverty", "1 severely poor, 2 moderately poor, 3 non-poor", f"{P} `poverty`"),
    ("welfare_category_name", "Welfare and poverty", "Label of welfare_category", f"{P} value label of `poverty`"),
    ("quintile", "Welfare and poverty", "Quintile of real consumption per adult equivalent (1 poorest)", f"{P} `quintile`"),
    ("welfare_ratio", "Welfare and poverty", "Real consumption per adult equivalent / poverty line", "sol_jan / Poverty_line"),
    ("near_poor", "Welfare and poverty", "1 = not poor but below 1.5 x the poverty line (project definition)", "1 <= welfare_ratio < 1.5"),
    # Demographics
    ("n_children_0_14", "Demographics", "Members aged 0-14", f"{PE} `s1q3y`"),
    ("n_children_0_4", "Demographics", "Members aged 0-4", f"{PE} `s1q3y`"),
    ("n_working_age_15_64", "Demographics", "Members aged 15-64", f"{PE} `s1q3y`"),
    ("n_elderly_65plus", "Demographics", "Members aged 65 and over", f"{PE} `s1q3y`"),
    ("dependency_ratio", "Demographics", "(children 0-14 + elderly 65+) / working-age 15-64. Missing when no member is 15-64", "derived"),
    ("no_working_age_member", "Demographics", "1 = no member aged 15-64 (dependency ratio undefined)", "derived"),
    ("share_dependents", "Demographics", "(children 0-14 + elderly 65+) / household size. Always defined", "derived"),
    ("n_members_with_disability", "Demographics", "Members with 'a lot of difficulty' or 'cannot do' in any Washington Group domain", f"{PE} `s3q7`-`s3q12` in (3, 4)"),
    ("head_female", "Demographics", "1 = household head is female", f"{PE} `s1q1` where `s1q2` = 1"),
    ("head_age", "Demographics", "Age of the household head, years", f"{PE} `s1q3y` (998 = don't know set missing; none found)"),
    ("head_age_over_100", "Demographics", "Quality flag: head's reported age above 100", "derived"),
    ("head_marital_status", "Demographics", "married / divorced_separated / widowed / never_married", f"{PE} `s1q4` grouped"),
    # Education, health and ICT
    ("head_education_code", "Education, health and ICT", "Head's highest level attended, 0 none ... 5 tertiary (see head_education_level)", f"{PE} `s4aq1`, `s4aq2`; ECD and nursery count as none"),
    ("head_education_level", "Education, health and ICT", "none / primary / post_primary_vocational / lower_secondary / upper_secondary / tertiary", "from head_education_code"),
    ("head_literate", "Education, health and ICT", "1 = head can read a simple note", f"{PE} `s4bq4`"),
    ("max_education_code", "Education, health and ICT", "Highest education code of any member", "as head_education_code"),
    ("n_children_in_school", "Education, health and ICT", "Members aged 6-17 who attended school in the last 12 months", f"{PE} `s4aq7`"),
    ("share_members_health_insured", "Education, health and ICT", "Share of members covered by health insurance", f"{PE} `s3q2`"),
    ("any_member_mobile_phone", "Education, health and ICT", "1 = at least one member has a mobile phone", f"{PE} `s4bq8`"),
    ("any_member_mobile_money_use", "Education, health and ICT", "1 = at least one member used mobile financial services (asked of internet users only)", f"{PE} `s4bq23c`"),
    # Employment and livelihoods
    ("n_employed", "Employment and livelihoods", "Members with a main job recorded (any age)", f"{PE} `s6bq7` filled"),
    ("n_own_farming", "Employment and livelihoods", "Employed members whose main job is in agriculture (ISIC A), not as employee", f"{PE} `s6bq4` = 1, `s6bq7` not 1-2"),
    ("n_farm_wage", "Employment and livelihoods", "Employed members in agriculture as employees", f"{PE} `s6bq4` = 1, `s6bq7` in 1-2"),
    ("n_nonfarm_wage", "Employment and livelihoods", "Employed members outside agriculture as employees", f"{PE} `s6bq4` != 1, `s6bq7` in 1-2"),
    ("n_nonfarm_self_employment", "Employment and livelihoods", "Employed members outside agriculture, not as employee", f"{PE} `s6bq4` != 1, `s6bq7` not 1-2"),
    ("n_informal_proxy", "Employment and livelihoods", "Employed members in informal work (proxy, see share_employed_informal_proxy)", "derived"),
    ("n_casual_wage", "Employment and livelihoods", "Employees on casual, seasonal, daily or other contracts", f"{PE} `s6bq8` in 3-6"),
    ("share_employed_in_agriculture", "Employment and livelihoods", "Share of employed members whose main job is in agriculture", "derived; missing if none employed"),
    ("share_employed_informal_proxy", "Employment and livelihoods", "Share of employed members not in formal work. Formal = public, mixed or international-NGO employer, or employee with a permanent or fixed-term contract. EICV7 has no social-security or registration question, so this is a proxy", f"{PE} `s6bq5`, `s6bq7`, `s6bq8`"),
    ("agriculture_dependent", "Employment and livelihoods", "1 = at least half of employed members work mainly in agriculture", "share_employed_in_agriculture >= 0.5"),
    ("any_wage_worker", "Employment and livelihoods", "1 = at least one employee (farm or non-farm)", "derived"),
    ("any_nonfarm_wage_worker", "Employment and livelihoods", "1 = at least one non-farm employee", "derived"),
    ("any_self_employed", "Employment and livelihoods", "1 = at least one member self-employed (farm or non-farm)", "derived"),
    ("any_agricultural_activity", "Employment and livelihoods", "1 = any member worked on own farm or did any agricultural activity", f"{PE} `s6aq2`, `s6aq4`"),
    ("any_nonfarm_business", "Employment and livelihoods", "1 = any member runs a non-farm business or is non-farm self-employed", f"{PE} `s6aq6`"),
    ("main_livelihood", "Employment and livelihoods", "Main income source (employment-based proxy): livelihood type of most employed members; ties go to the head's type. own_farming / farm_wage / nonfarm_wage / nonfarm_self_employment / no_employed_member. EICV7 has no household income aggregate", "derived"),
    ("head_employed", "Employment and livelihoods", "1 = head has a main job", "derived"),
    ("head_livelihood", "Employment and livelihoods", "Head's livelihood type ('none' if not employed)", "derived"),
    ("head_informal_proxy", "Employment and livelihoods", "1 = head's main job is informal (proxy); missing if head not employed", "derived"),
    # Income and transfers
    ("remittances_received_12m", "Income and transfers", "Cash transfers received, last 12 months, RWF. Missing for households unusable after deduplication", f"{S9} S9B `s9bq8`"),
    ("any_remittance_received", "Income and transfers", "1 = household received transfers", f"{S9} S9B `s9bq0`"),
    ("transfers_sent_12m", "Income and transfers", "Cash + food + in-kind transfers sent, last 12 months, RWF", f"{S9} S9A `s9aq7` + `s9aq10` + `s9aq12`"),
    ("income_public_support_12m", "Income and transfers", "Public income support received, codes 01-11 (pensions, FARG, scholarships, food relief, goods ...), RWF", f"{S9} S9E `s9eq4`"),
    ("income_private_other_12m", "Income and transfers", "Other private income, codes 12-23 (private pensions, rents, asset sales, dividends, GiveDirectly ...), RWF", f"{S9} S9E `s9eq4`"),
    ("income_farm_12m", "Income and transfers", "Income from crop farming, livestock and aquaculture, codes 24-26, RWF", f"{S9} S9E `s9eq4`"),
    ("other_income_total_12m", "Income and transfers", "Sum of the three S9E groups, RWF. Not a full income aggregate: no wages or business profits", f"{S9} S9E `s9eq4`"),
    ("any_public_support", "Income and transfers", "1 = received public support codes 01-09 or 11. Code 10 (goods donations) is excluded", f"{S9} S9E `s9eq2`"),
    ("received_govt_goods_donation", "Income and transfers", "1 = received government donations of goods (code 10: mosquito nets, buckets, phones ...)", f"{S9} S9E `s9eq2`"),
    # Expenditure
    ("exp_cell_*", "Expenditure", "Annual spending in one price cell, survey-period prices, RWF. NISR aggregates exp1-exp11 split by the household's own item values (see docs/expenditure_cpi_mapping.md). The 25 cells sum to exp1 + ... + exp11", "derived from exp1-exp11, S8A1-S8A3, S8B, person file"),
    ("share_food", "Expenditure", "Food and non-alcoholic drinks at home (COICOP 01, incl. own production) / cons_nominal", "food cells / cons1"),
    ("share_food_nisr", "Expenditure", "NISR food share: (exp9 + exp10 + food at school) / cons_nominal. Includes alcohol at home and meals away", "food / cons1"),
    ("share_meals_away", "Expenditure", "Meals and drinks away from home / cons_nominal", "exp10 / cons1"),
    ("share_alcohol_tobacco", "Expenditure", "Alcohol and tobacco / cons_nominal", "cell / cons1"),
    ("share_housing_utilities", "Expenditure", "Rent (actual and imputed), water, electricity, fuels, maintenance / cons_nominal", "housing cells / cons1"),
    ("share_housing_utilities_excl_imputed_rent", "Expenditure", "As share_housing_utilities without imputed rent", "housing cells / cons1"),
    ("share_energy", "Expenditure", "Electricity, gas, kerosene, charcoal, firewood, generator and vehicle fuel / cons_nominal", "housing_energy + transport_fuel / cons1"),
    ("share_transport", "Expenditure", "Transport (fuel, fares, repairs, school transport) / cons_nominal", "transport cells / cons1"),
    ("share_education", "Expenditure", "Education services (fees, contributions, other school costs) / cons_nominal. Excludes uniforms, books, school transport and school food, which COICOP puts elsewhere", "education cell / cons1"),
    ("share_education_nisr", "Expenditure", "NISR education share: exp1 / cons_nominal (includes uniforms, books, transport, food at school)", "exp1 / cons1"),
    ("share_communication", "Expenditure", "Airtime, internet, phone charging, postage / cons_nominal", "cell / cons1"),
    ("share_health", "Expenditure", "Health spending in cons1 / cons_nominal (NISR leaves lumpy health spending out of cons1)", "cell / cons1"),
    ("share_food_own_produced", "Expenditure", "Share of the food diary value (visits 2-5) that is own production", "S8B, valued"),
    ("n_aggregates_split_by_area_average", "Expenditure", "Number of NISR aggregates split with the area-average item mix because the household had no item detail", "derived"),
    # Housing, utilities and assets
    ("tenure_owner", "Housing, utilities and assets", "1 = owner-occupied", f"{H} `s5aq8` = 1"),
    ("tenure_renter", "Housing, utilities and assets", "1 = renting", f"{H} `s5aq8` = 2"),
    ("sleeping_rooms", "Housing, utilities and assets", "Rooms used for sleeping", f"{H} `s5aq3`"),
    ("persons_per_sleeping_room", "Housing, utilities and assets", "hh_size / sleeping rooms", "derived"),
    ("wall_material", "Housing, utilities and assets", "Wall material code", f"{H} `s5dq1`"),
    ("roof_material", "Housing, utilities and assets", "Roof material code", f"{H} `s5dq2`"),
    ("floor_material", "Housing, utilities and assets", "Floor material code", f"{H} `s5dq3`"),
    ("improved_wall", "Housing, utilities and assets", "1 = fired bricks with cement, cement blocks, or stones with cement", f"{H} `s5dq1` in 4, 5, 8"),
    ("improved_roof", "Housing, utilities and assets", "1 = metal sheets, clay tiles, concrete or industrial tiles", f"{H} `s5dq2` in 1, 2, 3, 5"),
    ("improved_floor", "Housing, utilities and assets", "1 = not beaten earth or dung", f"{H} `s5dq3` in 3-7"),
    ("improved_drinking_water", "Housing, utilities and assets", "1 = JMP improved source (piped, borehole, protected well/spring, rain, tanker, bottled)", f"{H} `s5cq3`"),
    ("electricity_any", "Housing, utilities and assets", "1 = grid or solar electricity", f"{H} `s5cq14` in 1-3"),
    ("electricity_grid", "Housing, utilities and assets", "1 = connected to the grid", f"{H} `s5cq14` in 1, 3"),
    ("clean_cooking_fuel", "Housing, utilities and assets", "1 = main cooking fuel is gas, biogas, solar or electricity", f"{H} `s5cq22a`"),
    ("cooking_fuel_firewood", "Housing, utilities and assets", "1 = main cooking fuel is firewood", f"{H} `s5cq22a` = 1"),
    ("cooking_fuel_charcoal", "Housing, utilities and assets", "1 = main cooking fuel is charcoal", f"{H} `s5cq22a` = 2"),
    ("improved_sanitation", "Housing, utilities and assets", "1 = JMP improved toilet", f"{H} `s5cq25` in 1-6"),
    ("basic_sanitation", "Housing, utilities and assets", "1 = improved toilet not shared with other households", f"{H} `s5cq25`, `s5cq26`"),
    ("internet_at_home", "Housing, utilities and assets", "1 = household has an internet connection", f"{H} `s5cq20a`"),
    ("any_shock_12m", "Housing, utilities and assets", "1 = household reported an unusual negative event in the last 12 months", f"{H} `s5eq1`"),
    ("shock_high_food_prices", "Housing, utilities and assets", "1 = unusually high food prices named among the three main shocks", f"{H} `s5eq2a`-`c` = 8"),
    ("girinka_cow_received", "Housing, utilities and assets", "1 = ever received a cow under Girinka (One Cow per Poor Family)", f"{H} `s7a2q1`"),
    ("owns_livestock", "Housing, utilities and assets", "1 = owns or raises livestock", f"{H} `s7aq4`"),
    ("n_cattle", "Housing, utilities and assets", "Cattle owned (0 if no livestock)", f"{H} `s7aq4a`"),
    ("n_goats", "Housing, utilities and assets", "Goats owned", f"{H} `s7aq4b`"),
    ("n_sheep", "Housing, utilities and assets", "Sheep owned", f"{H} `s7aq4c`"),
    ("n_pigs", "Housing, utilities and assets", "Pigs owned", f"{H} `s7aq4d`"),
    ("n_poultry", "Housing, utilities and assets", "Poultry owned", f"{H} `s7aq4e`"),
    ("tropical_livestock_units", "Housing, utilities and assets", "Livestock in TLU: cattle 0.7, goats and sheep 0.1, pigs 0.2, poultry 0.01 (FAO weights for sub-Saharan Africa)", "derived"),
    ("owns_*", "Housing, utilities and assets", "1 = household owns at least one of the durable (car, motorcycle, bicycle, solar lamp, refrigerator, basic mobile, smartphone, computer, television, radio; owns_mobile_phone = basic or smart)", "durables file `s10bq0`, `s10bq2`"),
    ("n_key_assets", "Housing, utilities and assets", "Count of: radio, television, mobile phone, bicycle, motorcycle, car, refrigerator, computer (0-8)", "derived"),
    # Service access
    ("minutes_to_*", "Service access", "Travel time to the service, minutes (hours x 60 + minutes). Missing when not reported, e.g. service not used", "services file `s5fq0`, `s5fq3a`, `s5fq3b`"),
    # Savings and credit
    ("any_account", "Savings and credit", "1 = any member has an account (bank, MFI, SACCO, mobile money)", "savings file `s10cq4`"),
    ("any_bank_account", "Savings and credit", "1 = account at a commercial bank, microfinance or cooperative bank", "savings file `s10cq5` in 1-3"),
    ("any_sacco_account", "Savings and credit", "1 = SACCO account", "savings file `s10cq5` = 4"),
    ("any_mobile_money_account", "Savings and credit", "1 = MoMo or Mokash account", "savings file `s10cq5` in 5, 6"),
    ("any_tontine", "Savings and credit", "1 = any member in a tontine (informal savings group)", "savings file `s10cq8`"),
    ("any_savings_instrument", "Savings and credit", "1 = any account or tontine", "derived"),
    ("loan_denied_12m", "Savings and credit", "1 = a member applied for and failed to get a loan in the last 12 months", "credit file `s10aq1`"),
    ("any_loan_12m", "Savings and credit", "1 = members owe or owed money or goods in the last 12 months", "credit file `s10aq3`"),
    ("any_formal_loan", "Savings and credit", "1 = loan from employer, bank, credit cooperative, MFI, VUP, SACCO or Mokash", "credit file `s10aq6`"),
    ("any_informal_loan", "Savings and credit", "1 = loan from relative, tontine, informal lender, business or other", "credit file `s10aq6`"),
    ("n_loans", "Savings and credit", "Number of loans listed", "credit file"),
    # VUP and social protection
    ("vup_direct_support", "VUP and social protection", "1 = VUP Direct Support beneficiary, last 12 months", "S9D1 `s9d1q2`"),
    ("vup_classic_pw", "VUP and social protection", "1 = VUP classic Public Works", "S9D2 `s9d2q1`"),
    ("vup_expanded_pw", "VUP and social protection", "1 = VUP expanded Public Works", "S9D3 `s9d3q1`"),
    ("vup_nsds", "VUP and social protection", "1 = Nutrition-Sensitive Direct Support", "S9D4 `s9d4q1`"),
    ("vup_fs_applied", "VUP and social protection", "1 = applied for a VUP Financial Services loan, last 12 months", "S9D5 `s9d5q1`"),
    ("vup_financial_services", "VUP and social protection", "1 = VUP Financial Services loan approved", "S9D5 `s9d5q2` = 1"),
    ("vup_any", "VUP and social protection", "1 = any of the five components above (FS = approved). Built from the component flags, not `s9d1q1`, which only flags each file's own component. Asset transfers and skills development are not in the public files", "derived"),
    ("vup_n_components", "VUP and social protection", "Number of the five components received", "derived"),
    ("vup_ds_amount_12m", "VUP and social protection", "Direct Support received, last 12 months, RWF", "S9D1 `s9d1q4`"),
    ("vup_cpw_months_12m", "VUP and social protection", "Months in classic Public Works, last 12 months", "S9D2 `s9d2q3`"),
    ("vup_cpw_daily_wage", "VUP and social protection", "Classic Public Works daily wage, RWF", "S9D2 `s9d2q4`"),
    ("vup_cpw_amount_12m", "VUP and social protection", "Classic Public Works payments, last 12 months, RWF (not imputed)", "S9D2 `s9d2q11`"),
    ("vup_cpw_amount_missing", "VUP and social protection", "Flag: classic PW beneficiary with no payment total", "derived"),
    ("vup_epw_amount_12m", "VUP and social protection", "Expanded Public Works payments, last 12 months, RWF (not imputed)", "S9D3 `s9d3q10`"),
    ("vup_epw_amount_missing", "VUP and social protection", "Flag: expanded PW beneficiary with no payment total", "derived"),
    ("vup_nsds_quarters_paid_12m", "VUP and social protection", "Quarters with an NSDS payment, last 12 months", "S9D4 `s9d4q7`"),
    ("vup_nsds_quarterly_payment", "VUP and social protection", "NSDS payment per quarter, RWF. `s9d4q8` only; `s9d4q8a`-`d` are ignored", "S9D4 `s9d4q8`"),
    ("vup_nsds_amount_12m_est", "VUP and social protection", "Derived estimate: quarterly payment x quarters paid, RWF", "`s9d4q8` x `s9d4q7`"),
    ("vup_fs_loan_amount", "VUP and social protection", "VUP Financial Services loan received, RWF", "S9D5 `s9d5q4`"),
    # Quality flags
    ("s9_version_conflict", "Quality flags", "1 = two conflicting versions of section 9 (notebook 05); section 9 totals are missing", f"{S9} household flags"),
]


def data_dictionary(master: pd.DataFrame) -> pd.DataFrame:
    """One row per master column with block, type, missingness, description and source."""
    exact = {c: e for c, *e in DICTIONARY if not c.endswith("*")}
    families = [(c[:-1], e) for c, *e in DICTIONARY if c.endswith("*")]
    rows = []
    for col in master.columns:
        entry = exact.get(col) or next((e for prefix, e in families if col.startswith(prefix)), None)
        assert entry is not None, f"column {col} is not documented"
        block, desc, source = entry
        rows.append({"column": col, "block": block, "dtype": str(master[col].dtype),
                     "pct_missing": round(master[col].isna().mean() * 100, 2),
                     "description": desc, "source": source})
    undocumented = set(exact) - set(master.columns)
    assert not undocumented, f"documented but absent: {undocumented}"
    return pd.DataFrame(rows)


DICTIONARY_INTRO = """# Household master table: data dictionary

`data/processed/household_master.parquet`: one row per EICV7 household (15,054 rows), built by
`src/features/build_household_master.py` (notebook `06_build_household_master_table.ipynb`).

**How to use it**

- Join key: `hhid`. Survey design: `clust` (PSU) and `strata_id` (stratum).
- Household estimates use `weight`; person estimates (poverty rates, people affected) use `pop_wt`.
- Flags are 0/1 integers with missing values where the question did not apply, so a weighted mean is a rate.
- Money is in Rwandan francs (RWF). Consumption columns marked *nominal* are in survey-period prices
  (October 2023 to October 2024); columns marked *jan2024* are in national January 2024 prices.
- NISR values are kept unchanged and renamed only where noted in *Source*. Everything else is derived.
- FinScope is not linked or included.
- Section 9 amounts (transfers, other income) come from the deduplicated files of notebook 05. They are
  missing, not zero, for the 4 households with two conflicting versions of section 9 (and for one further household (ID withheld) in transfers sent).

`pct_missing` is the unweighted share of households with a missing value.
"""


def write_data_dictionary(master: pd.DataFrame, path: Path) -> Path:
    """Write the data dictionary as Markdown, one table per block."""
    dd = data_dictionary(master)
    lines = [DICTIONARY_INTRO]
    for block, g in dd.groupby("block", sort=False):
        lines += [f"\n## {block}\n", "| Column | Type | % missing | Description | Source and rule |", "|---|---|---:|---|---|"]
        for r in g.itertuples():
            lines.append(f"| `{r.column}` | {r.dtype} | {r.pct_missing:g} | {r.description} | {r.source} |")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n")
    return path
