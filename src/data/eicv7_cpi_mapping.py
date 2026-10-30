"""Recommended mapping from EICV7 expenditure items to published NISR CPI series.

Each EICV7 item is first assigned a COICOP 1999 group (the classification the
Rwanda CPI uses), then the most detailed CPI series NISR publishes for that
group. Category slugs match ``src/features/cpi_features.py``.

``cpi_match_level`` records how close the match is:
    subgroup  - a published CPI sub-index covers the item (e.g. bread and cereals)
    division  - only the COICOP division index is published (e.g. fish -> food)
    proxy     - the CPI does not price this concept (imputed rent, use value of
                durables, ceremonies); the named series is the closest stand-in
    excluded  - not household consumption (taxes, transfers, donations);
                ``cpi_category`` is "excluded"

``alt_cpi_category`` names an urban-only NISR index (fresh products, energy,
local or imported goods) that is a closer fit where it applies.
"""

from __future__ import annotations

import pandas as pd

# COICOP 1999 group -> (group label, CPI category slug, match level)
COICOP_GROUPS = {
    "01.1.1": ("Bread and cereals", "bread_cereals", "subgroup"),
    "01.1.2": ("Meat", "meat", "subgroup"),
    "01.1.3": ("Fish and seafood", "food_non_alcoholic_beverages", "division"),
    "01.1.4": ("Milk, cheese and eggs", "milk_cheese_eggs", "subgroup"),
    "01.1.5": ("Oils and fats", "food_non_alcoholic_beverages", "division"),
    "01.1.6": ("Fruit and nuts", "food_non_alcoholic_beverages", "division"),
    "01.1.7": ("Vegetables, pulses and tubers", "vegetables", "subgroup"),
    "01.1.8": ("Sugar, jam, honey, confectionery", "food_non_alcoholic_beverages", "division"),
    "01.1.9": ("Food products n.e.c.", "food_non_alcoholic_beverages", "division"),
    "01.2": ("Non-alcoholic beverages", "non_alcoholic_beverages", "subgroup"),
    "02.1": ("Alcoholic beverages", "alcohol_tobacco", "division"),
    "02.2": ("Tobacco", "alcohol_tobacco", "division"),
    "03.1": ("Clothing and clothing services", "clothing_footwear", "division"),
    "03.2": ("Footwear", "clothing_footwear", "division"),
    "04.1": ("Actual rentals", "housing_utilities", "division"),
    "04.2": ("Imputed rentals", "housing_utilities", "proxy"),
    "04.3": ("Maintenance and repair of the dwelling", "housing_utilities", "division"),
    "04.4": ("Water supply and dwelling services", "housing_utilities", "division"),
    "04.5": ("Electricity, gas and other fuels", "housing_utilities", "division"),
    "05.1": ("Furniture, furnishings, carpets", "furnishing_household", "division"),
    "05.2": ("Household textiles", "furnishing_household", "division"),
    "05.3": ("Household appliances", "furnishing_household", "division"),
    "05.4": ("Glassware, tableware and utensils", "furnishing_household", "division"),
    "05.5": ("Tools and equipment for house and garden", "furnishing_household", "division"),
    "05.6": ("Routine household maintenance", "furnishing_household", "division"),
    "06": ("Health", "health", "division"),
    "07.1": ("Purchase of vehicles", "transport", "division"),
    "07.2": ("Operation of personal transport", "transport", "division"),
    "07.3": ("Transport services", "transport", "division"),
    "08": ("Communication", "communication", "division"),
    "09": ("Recreation and culture", "recreation_culture", "division"),
    "10": ("Education", "education", "division"),
    "11.1": ("Catering services", "restaurants_hotels", "division"),
    "11.2": ("Accommodation services", "restaurants_hotels", "division"),
    "12.1": ("Personal care", "miscellaneous", "division"),
    "12.3": ("Personal effects n.e.c.", "miscellaneous", "division"),
    "12.5": ("Insurance", "miscellaneous", "division"),
    "12.7": ("Other services n.e.c.", "miscellaneous", "division"),
    "ceremonies": ("Ceremonies and other mixed spending", "headline", "proxy"),
    "transfers": ("Taxes, contributions, gifts and donations", "excluded", "excluded"),
}


def _codes(*parts) -> list[int]:
    out = []
    for p in parts:
        out.extend(range(p[0], p[1] + 1) if isinstance(p, tuple) else [p])
    return out


# Item code -> COICOP 1999 group, per EICV7 item module (codes from the files' value labels).
ITEM_GROUPS = {
    "food": {  # S8B, s8bq0
        "01.1.1": _codes(10, 11, 16, 17, 19, 23, 24, (45, 54)),
        "01.1.2": _codes((36, 44), (55, 57)),
        "01.1.3": _codes((59, 63)),
        "01.1.4": _codes(21, 22, 58, 64, 65, 66, 68),
        "01.1.5": _codes((31, 35), 69, 70),
        "01.1.6": _codes(4, 71, 72, (73, 86), 88, 89, 90),
        "01.1.7": _codes((1, 3), (5, 9), (12, 15), 18, 20, 87, (91, 115), 126),
        "01.1.8": _codes(25, 26, 67, (116, 121)),
        "01.1.9": _codes(27, (122, 125), (127, 129)),
        "01.2": _codes(29, (130, 141)),
        "02.1": _codes(28, 30, (142, 148)),
    },
    "nonfood_annual": {  # S8A1, s8a1q0
        "03.1": _codes((1, 14)),
        "03.2": _codes((15, 17)),
        "12.3": _codes((18, 28)),
        "04.3": _codes(29, 30, 31, 34),
        "09": _codes(32, 33, 62, 63, 64),
        "05.1": _codes(35, 36, 37, 38),
        "05.2": _codes((39, 47)),
        "05.3": _codes(48, 49, 51, 52, 53),
        "05.5": _codes(50, 57),
        "05.4": _codes(54, 55, 56),
        "07.3": _codes(58, 59, 60),
        "12.5": _codes(61, 71),
        "11.2": _codes(65),
        "06": _codes((66, 70), (72, 76)),
        "12.7": _codes(77),
    },
    "nonfood_monthly": {  # S8A2, s8a2q0
        "03.1": _codes(1, 51, 52),
        "04.4": _codes(2, 53),
        "05.6": _codes((3, 9)),
        "07.2": _codes((10, 16)),
        "04.5": _codes(17, 18),
        "05.5": _codes(19, 20),
        "09": _codes((21, 25), (27, 30), (32, 35)),
        "05.1": _codes(26),
        "12.7": _codes(31, 54),
        "12.1": _codes((36, 46)),
        "08": _codes((47, 50)),
        "06": _codes((55, 65)),
    },
    "nonfood_weekly": {  # S8A3, s8a3q0
        "05.6": _codes(1, 3, 4, 14, 15),
        "12.1": _codes(2, 5),
        "07.2": _codes(6),
        "07.3": _codes((7, 11)),
        "04.5": _codes(12, 13, 16),
        "08": _codes(17, 18, 19),
        "02.2": _codes(20, 21),
        "04.3": _codes(22),
        "12.7": _codes(23),
    },
    "other_expenditure": {  # S9C, s9cq1
        "transfers": _codes(1, 2, 3, 4, 5, 7, 11),
        "ceremonies": _codes(6, 8, 10, 12, 13),
        "12.7": _codes(9),
    },
    "durables": {  # S10B, s10bq0 (use value of durables, exp11)
        "05.1": _codes((1, 7)),
        "07.1": _codes(8, 9, 10),
        "05.5": _codes(11, 27),
        "05.3": _codes((12, 18)),
        "08": _codes(19, 20),
        "09": _codes((21, 26)),
    },
}

ITEM_VARS = {
    "food": ("s8bq0", "S8B", "diary, visits 2-5", "exp9"),
    "nonfood_annual": ("s8a1q0", "S8A1", "12 months", "exp6"),
    "nonfood_monthly": ("s8a2q0", "S8A2", "4 weeks", "exp7"),
    "nonfood_weekly": ("s8a3q0", "S8A3", "7 days", "exp8"),
    "other_expenditure": ("s9cq1", "S9C", "12 months", "not in cons1"),
    "durables": ("s10bq0", "S10B", "stock (current value)", "exp11"),
}

# Expenditure variables that are not item-coded: (dataset, variable(s), label, COICOP group, recall, aggregate, note)
VARIABLE_ITEMS = [
    ("poverty", "exp1", "Total education expenditures", "10", "annual", "exp1", "Includes Food_at_school, which is also counted in food."),
    ("poverty", "exp2", "Imputed rents", "04.2", "annual", "exp2", "Not priced by the CPI; housing index used as proxy."),
    ("poverty", "exp3", "Actual rents", "04.1", "annual", "exp3", ""),
    ("poverty", "exp4", "Water expenses", "04.4", "annual", "exp4", ""),
    ("poverty", "exp5", "Electricity expenses", "04.5", "annual", "exp5", ""),
    ("poverty", "exp6", "Annual non-food expenditures (S8A1)", "item level", "annual", "exp6", "Map through the S8A1 item rows."),
    ("poverty", "exp7", "Monthly non-food expenditures (S8A2)", "item level", "annual", "exp7", "Map through the S8A2 item rows."),
    ("poverty", "exp8", "Frequent non-food expenditures (S8A3)", "item level", "annual", "exp8", "Map through the S8A3 item rows."),
    ("poverty", "exp9", "Food consumption at home (S8B)", "item level", "annual", "exp9", "Map through the S8B item rows; includes alcoholic drinks."),
    ("poverty", "exp10", "Food outside home (S8C)", "11.1", "annual", "exp10", ""),
    ("poverty", "exp11", "Use values of durable goods (S10B)", "item level", "annual", "exp11", "Use value is not priced; map through S10B item rows as proxy."),
    ("poverty", "Food_at_school", "Education expenses / food at school", "11.1", "annual", "exp1 and food", "School canteen meals (COICOP 11.1.2)."),
    ("person", "s4aq14a", "Registration and school fees", "10", "school year", "exp1", ""),
    ("person", "s4aq14b", "Parent contributions", "10", "school year", "exp1", ""),
    ("person", "s4aq14c", "School uniforms", "03.1", "school year", "exp1", "Clothing in COICOP; counted under education by NISR."),
    ("person", "s4aq14d", "Books and school supplies", "09", "school year", "exp1", "COICOP 1999 09.5; education index is an alternative."),
    ("person", "s4aq14e", "Transport to and from school", "07.3", "school year", "exp1", ""),
    ("person", "s4aq14f", "Room and board", "10", "school year", "exp1", "Boarding; restaurants and hotels is an alternative."),
    ("person", "s4aq14g", "Other schooling expenditures", "10", "school year", "exp1", ""),
    ("person", "s4aq14h", "Total education expenses (non-distributed)", "10", "school year", "exp1", "Use only when a-g are not reported."),
    ("person", "s4aq15a", "School feeding", "11.1", "school year", "Food_at_school", ""),
    ("person", "s4bq2", "Vocational training expenses", "10", "12 months", "exp1", ""),
    ("food_away", "s8cq4_v*", "Breakfast away from home", "11.1", "since last visit", "exp10", ""),
    ("food_away", "s8cq6_v*", "Lunch away from home", "11.1", "since last visit", "exp10", ""),
    ("food_away", "s8cq8_v*", "Dinner away from home", "11.1", "since last visit", "exp10", ""),
    ("food_away", "s8cq10_v*", "Snacks between meals away from home", "11.1", "since last visit", "exp10", ""),
    ("food_away", "s8cq12_v*", "Hot beverages away from home", "11.1", "since last visit", "exp10", ""),
    ("food_away", "s8cq14_v*", "Non-alcoholic drinks away from home", "11.1", "since last visit", "exp10", ""),
    ("food_away", "s8cq16_v*", "Alcoholic drinks away from home", "11.1", "since last visit", "exp10", "Served drinks are catering in COICOP."),
    ("household", "s5bq2a", "Estimated rent for dwelling (owners)", "04.2", "see s5bq2b", "exp2", "Not priced by the CPI."),
    ("household", "s5bq3a", "Actual rent paid in cash", "04.1", "see s5bq3b", "exp3", ""),
    ("household", "s5bq5a", "Services or payment in kind for dwelling", "04.1", "see s5bq5b", "exp3", ""),
    ("household", "s5cq9b", "Last water bill (WASAC or other)", "04.4", "month", "exp4", ""),
    ("household", "s5cq11", "Paid to private water vendor", "04.4", "7 days", "exp4", ""),
    ("household", "s5cq12", "Contribution to maintain water source", "04.4", "month", "exp4", ""),
    ("household", "s5cq20", "Electricity payments", "04.5", "4 weeks", "exp5", ""),
]

FRESH_FOOD_CODES = set(_codes(2, 3, (5, 9), 18, 20, 59, 60, 71, (73, 86), 91, 93, (95, 115), 126))
IMPORTED_FOOD_CODES = {17: "imported", 25: "imported", 70: "imported", 79: "imported", 131: "imported", 133: "imported",
                       140: "imported", 143: "imported", 145: "imported", 148: "imported",
                       16: "local", 26: "local", 69: "local", 78: "local", 130: "local", 132: "local", 139: "local",
                       142: "local", 144: "local", 147: "local"}
ENERGY_ITEMS = {("nonfood_monthly", c) for c in (14, 15, 16)}  # petrol, diesel, lubricants (07.2.2)

# Alternatives that are not urban-only indices: (dataset, item code or variable) -> CPI category
ALT_OVERRIDES = {
    ("nonfood_annual", 71): "health",
    ("nonfood_weekly", 23): "headline",
    ("person", "s4aq14d"): "education",
    ("person", "s4aq14f"): "restaurants_hotels",
}

ITEM_NOTES = {
    ("food", 4): "Groundnut flour classed with nuts.",
    ("food", 9): "Cooking bananas (plantain) classed as vegetables.",
    ("food", 29): "Ubushera is a non-alcoholic sorghum drink.",
    ("food", 35): "Lard is a fat, not meat.",
    ("food", 72): "Bananas for brewing, classed as fruit.",
    ("food", 88): "Sunflower seed flour classed with nuts and seeds.",
    ("nonfood_annual", 30): "Security equipment for the dwelling.",
    ("nonfood_annual", 61): "Transport insurance is COICOP 1999 12.5.4.",
    ("nonfood_annual", 71): "Health insurance is COICOP 1999 12.5.3; the health index is an alternative.",
    ("nonfood_weekly", 16): "Generator fuel treated as household energy.",
    ("nonfood_weekly", 17): "Phone charging service treated as communication.",
    ("nonfood_weekly", 23): "Unspecified items; headline CPI is an alternative.",
    ("other_expenditure", 9): "Funeral costs (COICOP 12.7 funeral services).",
    ("durables", 19): "Telephone equipment is COICOP 1999 08.2.",
    ("durables", 21): "Information processing equipment is COICOP 1999 09.1.",
}


def _alt_category(dataset: str, item, group: str) -> str:
    """Closer urban-only index or other alternative, if any."""
    if (dataset, item) in ALT_OVERRIDES:
        return ALT_OVERRIDES[(dataset, item)]
    if group == "04.5" or (dataset, item) in ENERGY_ITEMS:
        return "energy"
    if dataset == "food" and item in FRESH_FOOD_CODES:
        return "fresh_products"
    if dataset == "food" and item in IMPORTED_FOOD_CODES:
        return f"{IMPORTED_FOOD_CODES[item]}_goods"
    return ""


def check_item_groups(value_labels_by_module: dict[str, dict]) -> None:
    """Every labelled item code must be mapped exactly once."""
    for module, groups in ITEM_GROUPS.items():
        mapped = [c for codes in groups.values() for c in codes]
        duplicates = sorted({c for c in mapped if mapped.count(c) > 1})
        labelled = {int(k) for k in value_labels_by_module[module]}
        missing, extra = sorted(labelled - set(mapped)), sorted(set(mapped) - labelled)
        if duplicates or missing or extra:
            raise ValueError(f"{module}: duplicates {duplicates}, unmapped {missing}, unknown {extra}")


def build_mapping(value_labels_by_module: dict[str, dict]) -> pd.DataFrame:
    """Return one row per EICV7 expenditure item or variable with its CPI match."""
    check_item_groups(value_labels_by_module)
    rows = []
    for module, groups in ITEM_GROUPS.items():
        var, section, recall, aggregate = ITEM_VARS[module]
        labels = value_labels_by_module[module]
        for group, codes in groups.items():
            for code in codes:
                rows.append({
                    "module": section, "dataset": module, "variable": var, "item_code": code,
                    "item_label": str(labels[code]).strip(), "recall_period": recall, "poverty_aggregate": aggregate,
                    "coicop_1999_group": group, "alt_cpi_category": _alt_category(module, code, group),
                    "notes": ITEM_NOTES.get((module, code), ""),
                })
    for dataset, var, label, group, recall, aggregate, note in VARIABLE_ITEMS:
        rows.append({
            "module": dataset, "dataset": dataset, "variable": var, "item_code": None, "item_label": label,
            "recall_period": recall, "poverty_aggregate": aggregate, "coicop_1999_group": group,
            "alt_cpi_category": _alt_category(dataset, var, group), "notes": note,
        })
    mapping = pd.DataFrame(rows)
    info = mapping["coicop_1999_group"].map(COICOP_GROUPS)
    mapping["coicop_group_label"] = info.map(lambda x: x[0] if isinstance(x, tuple) else "See item rows")
    mapping["cpi_category"] = info.map(lambda x: x[1] if isinstance(x, tuple) else "item level")
    mapping["cpi_match_level"] = info.map(lambda x: x[2] if isinstance(x, tuple) else "item level")
    mapping["item_code"] = mapping["item_code"].astype("Int64")
    cols = ["module", "dataset", "variable", "item_code", "item_label", "recall_period", "poverty_aggregate",
            "coicop_1999_group", "coicop_group_label", "cpi_category", "cpi_match_level", "alt_cpi_category", "notes"]
    return mapping[cols]
