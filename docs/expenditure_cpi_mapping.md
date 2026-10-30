# EICV7 expenditure to CPI mapping

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

## 1. Cells and the index that prices them

Price change = September 2026 index / January 2024 index - 1, official NISR values.

| Cell | In main basket | Urban index | Urban change | Rural index | Rural change | Note |
|---|---|---|---:|---|---:|---|
| `bread_cereals` | yes | `bread_cereals` | 11.7% | `bread_cereals` | 6.8% | subgroup 01.1.1 |
| `meat` | yes | `meat` | 85.7% | `meat` | 81.8% | subgroup 01.1.2 |
| `milk_cheese_eggs` | yes | `milk_cheese_eggs` | 29.1% | `milk_cheese_eggs` | 26.9% | subgroup 01.1.4 |
| `vegetables` | yes | `vegetables` | 54.2% | `vegetables` | 54.6% | subgroup 01.1.7 (incl. tubers, pulses, plantains) |
| `non_alcoholic_beverages` | yes | `non_alcoholic_beverages` | 20.9% | `non_alcoholic_beverages` | 19.3% | group 01.2 |
| `food_other_fresh` | yes | `fresh_products` | 52.1% | `food_non_alcoholic_beverages` | 40.8% | RURAL FALLBACK: no rural fresh-products index; rural food division 01 |
| `food_other_local` | yes | `local_food` | 37.2% | `food_non_alcoholic_beverages` | 40.8% | RURAL FALLBACK: no rural local-goods index; rural food division 01 |
| `food_other_imported` | yes | `imported_food` | 24.3% | `food_non_alcoholic_beverages` | 40.8% | RURAL FALLBACK: no rural imported-goods index; rural food division 01 |
| `food_other_nec` | yes | `food_non_alcoholic_beverages` | 34.3% | `food_non_alcoholic_beverages` | 40.8% | division 01 (no published subgroup: fish, oils, fruit, sugar, other) |
| `alcohol_tobacco` | yes | `alcohol_tobacco` | 31.1% | `alcohol_tobacco` | 26.0% | division 02 |
| `clothing_footwear` | yes | `clothing_footwear` | 13.5% | `clothing_footwear` | 17.6% | division 03 |
| `housing_rent_actual` | yes | `housing_utilities` | 27.1% | `housing_utilities` | 25.7% | division 04 |
| `housing_rent_imputed` | no | `housing_utilities` | 27.1% | `housing_utilities` | 25.7% | division 04 as proxy; EXCLUDED from the main basket |
| `housing_energy` | yes | `energy` | 54.0% | `housing_utilities` | 25.7% | RURAL FALLBACK: no rural energy index; rural division 04 (housing, water, electricity, gas, other fuels) |
| `housing_other` | yes | `housing_utilities` | 27.1% | `housing_utilities` | 25.7% | division 04 |
| `furnishing_household` | yes | `furnishing_household` | 20.5% | `furnishing_household` | 20.9% | division 05 |
| `health` | yes | `health` | 76.3% | `health` | 65.3% | division 06 |
| `transport_fuel` | yes | `energy` | 54.0% | `transport` | 71.1% | RURAL FALLBACK: no rural energy index; rural division 07 (transport) |
| `transport_other` | yes | `transport` | 55.7% | `transport` | 71.1% | division 07 |
| `communication` | yes | `communication` | 11.6% | `communication` | 113.2% | division 08 |
| `recreation_culture` | yes | `recreation_culture` | 5.7% | `recreation_culture` | 35.0% | division 09 |
| `education` | yes | `education` | 31.2% | `education` | 44.3% | division 10 |
| `restaurants_hotels` | yes | `restaurants_hotels` | 45.3% | `restaurants_hotels` | 32.0% | division 11 |
| `miscellaneous` | yes | `miscellaneous` | 27.7% | `miscellaneous` | 16.5% | division 12 |
| `durables_use_value` | no | `furnishing_household` | 20.5% | `furnishing_household` | 20.9% | division 05 as proxy; EXCLUDED from the main basket |

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

## 3. Flagged index months in the window

Months between February 2024 and September 2026 that notebook 03 flagged as abrupt jumps or outliers, for the indices used here. Official values are used unchanged; the sensitivity scenarios in `docs/household_cpi_shock_methodology.md` show how much the flagged series matter.

| Index | Area | Flagged months |
|---|---|---|
| `communication` | rural | 2024-10, 2026-08 |
| `communication` | urban | 2026-04 |
| `education` | rural | 2025-09, 2026-09 |
| `education` | urban | 2024-09, 2025-09, 2026-09 |
| `energy` | urban | 2025-10, 2026-04 |
| `food_non_alcoholic_beverages` | rural | 2026-09 |
| `health` | rural | 2025-07 |
| `health` | urban | 2025-07 |
| `housing_utilities` | rural | 2026-04, 2026-07 |
| `housing_utilities` | urban | 2025-10, 2026-04 |
| `meat` | rural | 2024-08, 2026-07 |
| `meat` | urban | 2026-07 |
| `milk_cheese_eggs` | rural | 2026-09 |
| `milk_cheese_eggs` | urban | 2026-09 |
| `miscellaneous` | urban | 2026-08, 2026-09 |
| `restaurants_hotels` | urban | 2025-01, 2026-01 |
| `transport` | rural | 2024-03, 2024-04, 2026-04 |
| `transport` | urban | 2024-03, 2024-04, 2026-04 |
| `vegetables` | rural | 2025-01, 2026-09 |
| `vegetables` | urban | 2026-09 |

## 4. Item mapping

All 389 rows of `reports/data_inspection/expenditure_cpi_mapping.csv` with the cell each one feeds. NISR aggregate rows (`exp*`) and household-file rows are listed for completeness; the split uses the item rows and the aggregates as described in section 1 of `docs/household_cpi_shock_methodology.md`.


### food (148 rows)

| Code / variable | Item | COICOP 1999 | CPI category | Alternative (urban) | Cell |
|---|---|---|---|---|---|
| 10 | Corn (flour from Mill) | 01.1.1 | bread_cereals |  | bread_cereals |
| 11 | Corn (flour from Factory) | 01.1.1 | bread_cereals |  | bread_cereals |
| 16 | Local rice | 01.1.1 | bread_cereals | local_goods | bread_cereals |
| 17 | Imported rice | 01.1.1 | bread_cereals | imported_goods | bread_cereals |
| 19 | Dry maize (grain) | 01.1.1 | bread_cereals |  | bread_cereals |
| 23 | Cakes/Chapati/Mandazi | 01.1.1 | bread_cereals |  | bread_cereals |
| 24 | Bread | 01.1.1 | bread_cereals |  | bread_cereals |
| 45 | Sorghum | 01.1.1 | bread_cereals |  | bread_cereals |
| 46 | Fermented sorghum | 01.1.1 | bread_cereals |  | bread_cereals |
| 47 | Wheat (grain) | 01.1.1 | bread_cereals |  | bread_cereals |
| 48 | Other cereals | 01.1.1 | bread_cereals |  | bread_cereals |
| 49 | Sorghum (flour) | 01.1.1 | bread_cereals |  | bread_cereals |
| 50 | Wheat (flour) | 01.1.1 | bread_cereals |  | bread_cereals |
| 51 | Millet (flour) | 01.1.1 | bread_cereals |  | bread_cereals |
| 52 | Other flour of cereals | 01.1.1 | bread_cereals |  | bread_cereals |
| 53 | Biscuits | 01.1.1 | bread_cereals |  | bread_cereals |
| 54 | Pasta | 01.1.1 | bread_cereals |  | bread_cereals |
| 36 | Beef meat | 01.1.2 | meat |  | meat |
| 37 | Sheep /Mutton / lamb meat | 01.1.2 | meat |  | meat |
| 38 | Goat meat | 01.1.2 | meat |  | meat |
| 39 | Pork meat | 01.1.2 | meat |  | meat |
| 40 | Rabbit Meat | 01.1.2 | meat |  | meat |
| 41 | Wild Meat | 01.1.2 | meat |  | meat |
| 42 | Other Meats | 01.1.2 | meat |  | meat |
| 43 | Sausages, bacon, ham  etc | 01.1.2 | meat |  | meat |
| 44 | Preserved/canned meat | 01.1.2 | meat |  | meat |
| 55 | Chicken live | 01.1.2 | meat |  | meat |
| 56 | Frozen chicken | 01.1.2 | meat |  | meat |
| 57 | Other domestic poultries e.g. ducks | 01.1.2 | meat |  | meat |
| 59 | Fish (fresh / frozen) | 01.1.3 | food_non_alcoholic_beverages | fresh_products | food_other_fresh |
| 60 | Small Sized Fish (fresh) | 01.1.3 | food_non_alcoholic_beverages | fresh_products | food_other_fresh |
| 61 | Fish (dry / smoked) | 01.1.3 | food_non_alcoholic_beverages |  | food_other_nec |
| 62 | Small Sized Fish (dry) | 01.1.3 | food_non_alcoholic_beverages |  | food_other_nec |
| 63 | Preserved/canned fish | 01.1.3 | food_non_alcoholic_beverages |  | food_other_nec |
| 21 | Fresh milk | 01.1.4 | milk_cheese_eggs |  | milk_cheese_eggs |
| 22 | Curdled Milk | 01.1.4 | milk_cheese_eggs |  | milk_cheese_eggs |
| 58 | Eggs | 01.1.4 | milk_cheese_eggs |  | milk_cheese_eggs |
| 64 | Condensed milk unsweetened | 01.1.4 | milk_cheese_eggs |  | milk_cheese_eggs |
| 65 | Milk powder | 01.1.4 | milk_cheese_eggs |  | milk_cheese_eggs |
| 66 | Yogurt | 01.1.4 | milk_cheese_eggs |  | milk_cheese_eggs |
| 68 | Cheese | 01.1.4 | milk_cheese_eggs |  | milk_cheese_eggs |
| 31 | Peanut oil | 01.1.5 | food_non_alcoholic_beverages |  | food_other_nec |
| 32 | Margarine | 01.1.5 | food_non_alcoholic_beverages |  | food_other_nec |
| 33 | Palm oil | 01.1.5 | food_non_alcoholic_beverages |  | food_other_nec |
| 34 | Other plant oils | 01.1.5 | food_non_alcoholic_beverages |  | food_other_nec |
| 35 | Lard of pork | 01.1.5 | food_non_alcoholic_beverages |  | food_other_nec |
| 69 | Butter (local) | 01.1.5 | food_non_alcoholic_beverages | local_goods | food_other_local |
| 70 | Butter (imported) | 01.1.5 | food_non_alcoholic_beverages | imported_goods | food_other_imported |
| 4 | Groundnut flour | 01.1.6 | food_non_alcoholic_beverages |  | food_other_nec |
| 71 | Banana fruit (Imineke) | 01.1.6 | food_non_alcoholic_beverages | fresh_products | food_other_fresh |
| 72 | Banana - beer (Ikakama/Inkashi) | 01.1.6 | food_non_alcoholic_beverages |  | food_other_nec |
| 73 | Mangos | 01.1.6 | food_non_alcoholic_beverages | fresh_products | food_other_fresh |
| 74 | Papayas | 01.1.6 | food_non_alcoholic_beverages | fresh_products | food_other_fresh |
| 75 | Avocado | 01.1.6 | food_non_alcoholic_beverages | fresh_products | food_other_fresh |
| 76 | Pineapple | 01.1.6 | food_non_alcoholic_beverages | fresh_products | food_other_fresh |
| 77 | Guava | 01.1.6 | food_non_alcoholic_beverages | fresh_products | food_other_fresh |
| 78 | Orange (local) | 01.1.6 | food_non_alcoholic_beverages | fresh_products | food_other_fresh |
| 79 | Orange (imported) | 01.1.6 | food_non_alcoholic_beverages | fresh_products | food_other_fresh |
| 80 | Tangerine | 01.1.6 | food_non_alcoholic_beverages | fresh_products | food_other_fresh |
| 81 | Citron - Lemon | 01.1.6 | food_non_alcoholic_beverages | fresh_products | food_other_fresh |
| 82 | Passion Fruit | 01.1.6 | food_non_alcoholic_beverages | fresh_products | food_other_fresh |
| 83 | Plums | 01.1.6 | food_non_alcoholic_beverages | fresh_products | food_other_fresh |
| 84 | Berries | 01.1.6 | food_non_alcoholic_beverages | fresh_products | food_other_fresh |
| 85 | Apples | 01.1.6 | food_non_alcoholic_beverages | fresh_products | food_other_fresh |
| 86 | Other fruits | 01.1.6 | food_non_alcoholic_beverages | fresh_products | food_other_fresh |
| 88 | Sunflower flour | 01.1.6 | food_non_alcoholic_beverages |  | food_other_nec |
| 89 | Ground nuts (peanuts) | 01.1.6 | food_non_alcoholic_beverages |  | food_other_nec |
| 90 | Grilled ground nuts | 01.1.6 | food_non_alcoholic_beverages |  | food_other_nec |
| 1 | Dry bean | 01.1.7 | vegetables |  | vegetables |
| 2 | Fresh bean | 01.1.7 | vegetables | fresh_products | vegetables |
| 3 | String bean | 01.1.7 | vegetables | fresh_products | vegetables |
| 5 | Irish potato | 01.1.7 | vegetables | fresh_products | vegetables |
| 6 | Sweet potato | 01.1.7 | vegetables | fresh_products | vegetables |
| 7 | Cassava (root) | 01.1.7 | vegetables | fresh_products | vegetables |
| 8 | Tarot/amateke | 01.1.7 | vegetables | fresh_products | vegetables |
| 9 | Banana-cooking (Inyamunyo) | 01.1.7 | vegetables | fresh_products | vegetables |
| 12 | Cassava flour (yasekuwe) | 01.1.7 | vegetables |  | vegetables |
| 13 | Cassava (fermented) | 01.1.7 | vegetables |  | vegetables |
| 14 | Cassava from Mill) | 01.1.7 | vegetables |  | vegetables |
| 15 | Cassava from Factory) | 01.1.7 | vegetables |  | vegetables |
| 18 | Maize (fresh) | 01.1.7 | vegetables | fresh_products | vegetables |
| 20 | Tomato | 01.1.7 | vegetables | fresh_products | vegetables |
| 87 | Soya Flour | 01.1.7 | vegetables |  | vegetables |
| 91 | Soya (fresh) | 01.1.7 | vegetables | fresh_products | vegetables |
| 92 | Soya (dry) | 01.1.7 | vegetables |  | vegetables |
| 93 | Green pea (fresh) | 01.1.7 | vegetables | fresh_products | vegetables |
| 94 | Green pea (dry) | 01.1.7 | vegetables |  | vegetables |
| 95 | Onion | 01.1.7 | vegetables | fresh_products | vegetables |
| 96 | Garlic | 01.1.7 | vegetables | fresh_products | vegetables |
| 97 | Pumpkin | 01.1.7 | vegetables | fresh_products | vegetables |
| 98 | Cucumber | 01.1.7 | vegetables | fresh_products | vegetables |
| 99 | Eggplant | 01.1.7 | vegetables | fresh_products | vegetables |
| 100 | Carrot | 01.1.7 | vegetables | fresh_products | vegetables |
| 101 | Leeks | 01.1.7 | vegetables | fresh_products | vegetables |
| 102 | Lettuce | 01.1.7 | vegetables | fresh_products | vegetables |
| 103 | Celery | 01.1.7 | vegetables | fresh_products | vegetables |
| 104 | Parsley | 01.1.7 | vegetables | fresh_products | vegetables |
| 105 | Mushrooms | 01.1.7 | vegetables | fresh_products | vegetables |
| 106 | Cassava leaves | 01.1.7 | vegetables | fresh_products | vegetables |
| 107 | Amarante (small leafed green) | 01.1.7 | vegetables | fresh_products | vegetables |
| 108 | Cabbages | 01.1.7 | vegetables | fresh_products | vegetables |
| 109 | Spinach | 01.1.7 | vegetables | fresh_products | vegetables |
| 110 | Amarante (large leafed green) | 01.1.7 | vegetables | fresh_products | vegetables |
| 111 | Other Vegetables | 01.1.7 | vegetables | fresh_products | vegetables |
| 112 | Chayote | 01.1.7 | vegetables | fresh_products | vegetables |
| 113 | Pepper | 01.1.7 | vegetables | fresh_products | vegetables |
| 114 | Yams/Ibikoro | 01.1.7 | vegetables | fresh_products | vegetables |
| 115 | Other tubers | 01.1.7 | vegetables | fresh_products | vegetables |
| 126 | Pepper-raw | 01.1.7 | vegetables | fresh_products | vegetables |
| 25 | Sugar  (imported) | 01.1.8 | food_non_alcoholic_beverages | imported_goods | food_other_imported |
| 26 | Sugar (local) | 01.1.8 | food_non_alcoholic_beverages | local_goods | food_other_local |
| 67 | Ice cream | 01.1.8 | food_non_alcoholic_beverages |  | food_other_nec |
| 116 | Sugarcane | 01.1.8 | food_non_alcoholic_beverages |  | food_other_nec |
| 117 | Jam, marmalade | 01.1.8 | food_non_alcoholic_beverages |  | food_other_nec |
| 118 | Honey | 01.1.8 | food_non_alcoholic_beverages |  | food_other_nec |
| 119 | Chocolate | 01.1.8 | food_non_alcoholic_beverages |  | food_other_nec |
| 120 | Candy / Gum | 01.1.8 | food_non_alcoholic_beverages |  | food_other_nec |
| 121 | Sugar glu | 01.1.8 | food_non_alcoholic_beverages |  | food_other_nec |
| 27 | Salt | 01.1.9 | food_non_alcoholic_beverages |  | food_other_nec |
| 122 | Pepper(ground / liquid) | 01.1.9 | food_non_alcoholic_beverages |  | food_other_nec |
| 123 | Vinegar | 01.1.9 | food_non_alcoholic_beverages |  | food_other_nec |
| 124 | Mayonnaise | 01.1.9 | food_non_alcoholic_beverages |  | food_other_nec |
| 125 | Tomato concentrate | 01.1.9 | food_non_alcoholic_beverages |  | food_other_nec |
| 127 | Boullion cubes(MAGGI) | 01.1.9 | food_non_alcoholic_beverages |  | food_other_nec |
| 128 | Baby food | 01.1.9 | food_non_alcoholic_beverages |  | food_other_nec |
| 129 | Other food items | 01.1.9 | food_non_alcoholic_beverages |  | food_other_nec |
| 29 | Sorghum juice(Ubushera) | 01.2 | non_alcoholic_beverages |  | non_alcoholic_beverages |
| 130 | Coffee (local) | 01.2 | non_alcoholic_beverages | local_goods | non_alcoholic_beverages |
| 131 | Coffee (imported) | 01.2 | non_alcoholic_beverages | imported_goods | non_alcoholic_beverages |
| 132 | Tea (local) | 01.2 | non_alcoholic_beverages | local_goods | non_alcoholic_beverages |
| 133 | Tea (imported) | 01.2 | non_alcoholic_beverages | imported_goods | non_alcoholic_beverages |
| 134 | Cocoa and powdered drinking chocolate | 01.2 | non_alcoholic_beverages |  | non_alcoholic_beverages |
| 135 | Mineral water | 01.2 | non_alcoholic_beverages |  | non_alcoholic_beverages |
| 136 | Carbonated Soft Drinks | 01.2 | non_alcoholic_beverages |  | non_alcoholic_beverages |
| 137 | Local banana juice | 01.2 | non_alcoholic_beverages |  | non_alcoholic_beverages |
| 138 | Passion fruit juice | 01.2 | non_alcoholic_beverages |  | non_alcoholic_beverages |
| 139 | Other juices of fruits (local) | 01.2 | non_alcoholic_beverages | local_goods | non_alcoholic_beverages |
| 140 | Other juices of fruits (imported) | 01.2 | non_alcoholic_beverages | imported_goods | non_alcoholic_beverages |
| 141 | Powdered juice(super dip) | 01.2 | non_alcoholic_beverages |  | non_alcoholic_beverages |
| 28 | Local banana beer | 02.1 | alcohol_tobacco |  | alcohol_tobacco |
| 30 | Local sorghum beer(ikigage) | 02.1 | alcohol_tobacco |  | alcohol_tobacco |
| 142 | Liqueurs  (local) | 02.1 | alcohol_tobacco | local_goods | alcohol_tobacco |
| 143 | Liqueurs  (imported) | 02.1 | alcohol_tobacco | imported_goods | alcohol_tobacco |
| 144 | Wine (local) | 02.1 | alcohol_tobacco | local_goods | alcohol_tobacco |
| 145 | Wine (imported) | 02.1 | alcohol_tobacco | imported_goods | alcohol_tobacco |
| 146 | Other local beer | 02.1 | alcohol_tobacco |  | alcohol_tobacco |
| 147 | Commercial beer (local) | 02.1 | alcohol_tobacco | local_goods | alcohol_tobacco |
| 148 | Commercial beer (imported) | 02.1 | alcohol_tobacco | imported_goods | alcohol_tobacco |

### nonfood_annual (77 rows)

| Code / variable | Item | COICOP 1999 | CPI category | Alternative (urban) | Cell |
|---|---|---|---|---|---|
| 1 | Fabric (cloth) for men | 03.1 | clothing_footwear |  | clothing_footwear |
| 2 | Fabric (cloth) for women | 03.1 | clothing_footwear |  | clothing_footwear |
| 3 | Wrap around cloth for women (Igitenge) | 03.1 | clothing_footwear |  | clothing_footwear |
| 4 | Men's garments | 03.1 | clothing_footwear |  | clothing_footwear |
| 5 | Men's tailoring | 03.1 | clothing_footwear |  | clothing_footwear |
| 6 | Men's underwear | 03.1 | clothing_footwear |  | clothing_footwear |
| 7 | Men's clothing accessories (ties, hats, belts) | 03.1 | clothing_footwear |  | clothing_footwear |
| 8 | Women's garments | 03.1 | clothing_footwear |  | clothing_footwear |
| 9 | Women's tailoring | 03.1 | clothing_footwear |  | clothing_footwear |
| 10 | Women's underwear | 03.1 | clothing_footwear |  | clothing_footwear |
| 11 | Women's clothing accessories (scarves, hats, belts) | 03.1 | clothing_footwear |  | clothing_footwear |
| 12 | Children's clothing (excluding school uniform) | 03.1 | clothing_footwear |  | clothing_footwear |
| 13 | Children's underwear | 03.1 | clothing_footwear |  | clothing_footwear |
| 14 | Children's tailoring | 03.1 | clothing_footwear |  | clothing_footwear |
| 15 | Men's footwear | 03.2 | clothing_footwear |  | clothing_footwear |
| 16 | Women's footwear | 03.2 | clothing_footwear |  | clothing_footwear |
| 17 | Children's footwear | 03.2 | clothing_footwear |  | clothing_footwear |
| 18 | Jewelry | 12.3 | miscellaneous |  | miscellaneous |
| 19 | Watches (timepiece) | 12.3 | miscellaneous |  | miscellaneous |
| 20 | Clocks | 12.3 | miscellaneous |  | miscellaneous |
| 21 | Metal/Wooden Case | 12.3 | miscellaneous |  | miscellaneous |
| 22 | Suitcases | 12.3 | miscellaneous |  | miscellaneous |
| 23 | Travel bags | 12.3 | miscellaneous |  | miscellaneous |
| 24 | Hand bags (other than women’s handbags) | 12.3 | miscellaneous |  | miscellaneous |
| 25 | women’s handbags | 12.3 | miscellaneous |  | miscellaneous |
| 26 | Other personal effects, e.g. wallet | 12.3 | miscellaneous |  | miscellaneous |
| 27 | Umbrellas | 12.3 | miscellaneous |  | miscellaneous |
| 28 | Sunglasses | 12.3 | miscellaneous |  | miscellaneous |
| 29 | Materials for the maintenance repair of the dwelling (e.g. cement, ironsheets,sand, nails); carpets; small plumbing items,) | 04.3 | housing_utilities |  | not in exp6 (NISR excludes) |
| 30 | Security equipment (e.g. smoke detectors, surveillance cameras, fire extinguisher, etc.) | 04.3 | housing_utilities |  | not in exp6 (NISR excludes) |
| 31 | Services of plumbers, electricians, carpenters, masons, painters, decorators, security services | 04.3 | housing_utilities |  | housing_other |
| 34 | Building repairs (labor) | 04.3 | housing_utilities |  | housing_other |
| 32 | Garden products  (pots, decorations and ornanments for gardens, soil, fertilizer etc) | 09 | recreation_culture |  | recreation_culture |
| 33 | Plants and flowers(indoor and outdoor) | 09 | recreation_culture |  | recreation_culture |
| 62 | Musical instruments | 09 | recreation_culture |  | not in exp6 (NISR excludes) |
| 63 | Sporting equipment | 09 | recreation_culture |  | recreation_culture |
| 64 | Subscription to DSTV, Star times, etc | 09 | recreation_culture |  | recreation_culture |
| 35 | Mattresses | 05.1 | furnishing_household |  | not in exp6 (NISR excludes) |
| 36 | Rugs, floor coverings, carpets | 05.1 | furnishing_household |  | furnishing_household |
| 37 | Mats | 05.1 | furnishing_household |  | furnishing_household |
| 38 | Furniture repair (Furniture, beds, kitchen items) | 05.1 | furnishing_household |  | furnishing_household |
| 39 | Draperies (curtains) | 05.2 | furnishing_household |  | furnishing_household |
| 40 | Bed Pillows | 05.2 | furnishing_household |  | furnishing_household |
| 41 | Blanket | 05.2 | furnishing_household |  | furnishing_household |
| 42 | Bed Sheets | 05.2 | furnishing_household |  | furnishing_household |
| 43 | Mosquito nets | 05.2 | furnishing_household |  | furnishing_household |
| 44 | Tablecloth | 05.2 | furnishing_household |  | furnishing_household |
| 45 | Dish towel/Rag/Wiper | 05.2 | furnishing_household |  | furnishing_household |
| 46 | Cloth for wiping table ware | 05.2 | furnishing_household |  | furnishing_household |
| 47 | Other household textiles | 05.2 | furnishing_household |  | furnishing_household |
| 48 | Local Energy saving Stove | 05.3 | furnishing_household |  | furnishing_household |
| 49 | Other small household appliances (tea kettles etc.) | 05.3 | furnishing_household |  | furnishing_household |
| 51 | Electric clothes iron | 05.3 | furnishing_household |  | not in exp6 (NISR excludes) |
| 52 | Non-electric clothes iron | 05.3 | furnishing_household |  | not in exp6 (NISR excludes) |
| 53 | Repair of household appliances | 05.3 | furnishing_household |  | furnishing_household |
| 50 | Torch (flashlight) | 05.5 | furnishing_household |  | furnishing_household |
| 57 | Other household and garden tools | 05.5 | furnishing_household |  | furnishing_household |
| 54 | Dishes (tableware) | 05.4 | furnishing_household |  | furnishing_household |
| 55 | Kitchen and domestic utensils(Pots and pans) | 05.4 | furnishing_household |  | furnishing_household |
| 56 | Cutlery, flatware and silverware | 05.4 | furnishing_household |  | furnishing_household |
| 58 | International travel –bus fares | 07.3 | transport |  | transport_other |
| 59 | Aeroplane flights | 07.3 | transport |  | transport_other |
| 60 | Motor boat transport | 07.3 | transport |  | transport_other |
| 61 | Vehicle/ Motor insurance | 12.5 | miscellaneous |  | miscellaneous |
| 71 | Health insurance (Mutuelle, RAMA, MMI, etc.) | 12.5 | miscellaneous | health | miscellaneous |
| 65 | Hotel overnight and hotel services | 11.2 | restaurants_hotels |  | restaurants_hotels |
| 66 | Assistive health products for vision (e.g., glasses, white canes) | 06 | health |  | health |
| 67 | Dental care costs (eg fillings, tooth removal, treatment for gum disease etc) | 06 | health |  | health |
| 68 | Assistive health products for hearing and communication (e.g., hearing aids) | 06 | health |  | health |
| 69 | Hospitalization | 06 | health |  | not in exp6 (NISR excludes) |
| 70 | Giving birth | 06 | health |  | not in exp6 (NISR excludes) |
| 72 | Emergency transportation and emergency rescue services | 06 | health |  | not in exp6 (NISR excludes) |
| 73 | Assistive health products for mobility and daily living (e.g., crutches, therapeutic footwear, wheelchairs, prosthesis) | 06 | health |  | not in exp6 (NISR excludes) |
| 74 | Diagnostic and laboratory tests, such as blood tests and x-rays, for other reasons than preventive care. | 06 | health |  | not in exp6 (NISR excludes) |
| 75 | Medical products, (e.g., pregnancy test, glucose meters, blood pressure meters, masks, bandage, thermometers etc.) | 06 | health |  | health |
| 76 | Preventive care services (e.g. Immunization/vaccination services, family planning, antenatal care, postnatal care, routine check-ups, child growth monitoring) | 06 | health |  | health |
| 77 | Issue of administrative (official) documents | 12.7 | miscellaneous |  | miscellaneous |

### nonfood_monthly (65 rows)

| Code / variable | Item | COICOP 1999 | CPI category | Alternative (urban) | Cell |
|---|---|---|---|---|---|
| 1 | Laundry services (washing clothes & others) | 03.1 | clothing_footwear |  | clothing_footwear |
| 51 | Clothing repair | 03.1 | clothing_footwear |  | clothing_footwear |
| 52 | Shoes repair | 03.1 | clothing_footwear |  | clothing_footwear |
| 2 | Rubbish collection services | 04.4 | housing_utilities |  | housing_other |
| 53 | Security services | 04.4 | housing_utilities |  | housing_other |
| 3 | Bleach | 05.6 | furnishing_household |  | furnishing_household |
| 4 | Disinfectant and cleaners | 05.6 | furnishing_household |  | furnishing_household |
| 5 | Broom/Brush | 05.6 | furnishing_household |  | furnishing_household |
| 6 | Shoe brush | 05.6 | furnishing_household |  | furnishing_household |
| 7 | Shoe polish | 05.6 | furnishing_household |  | furnishing_household |
| 8 | Other non-durable household goods e.g., sponges, window cleaning products etc. | 05.6 | furnishing_household |  | furnishing_household |
| 9 | Wages for household (domestic) help | 05.6 | furnishing_household |  | furnishing_household |
| 10 | Spare  parts of Vehicle  (Excluding engine) | 07.2 | transport |  | transport_other |
| 11 | Spare parts of motorcycle or bicycle (parts) | 07.2 | transport |  | transport_other |
| 12 | Vehicle repair (labour) | 07.2 | transport |  | transport_other |
| 13 | Repair of motorcycle or bicycle (labour) | 07.2 | transport |  | transport_other |
| 14 | Petrol (Fuel) | 07.2 | transport | energy | transport_fuel |
| 15 | Diesel (Fuel) | 07.2 | transport | energy | transport_fuel |
| 16 | Vehicles Lubricants | 07.2 | transport | energy | transport_fuel |
| 17 | Gas (propane) | 04.5 | housing_utilities | energy | housing_energy |
| 18 | Kerosene | 04.5 | housing_utilities | energy | housing_energy |
| 19 | Batteries | 05.5 | furnishing_household |  | furnishing_household |
| 20 | Light bulbs | 05.5 | furnishing_household |  | furnishing_household |
| 21 | Video On Demand Services (VOD) e.g. Subscription on Netflix, | 09 | recreation_culture |  | recreation_culture |
| 22 | Internet downloads (eg: film, books, games, etc.,) | 09 | recreation_culture |  | recreation_culture |
| 23 | Film and developing | 09 | recreation_culture |  | recreation_culture |
| 24 | Toys | 09 | recreation_culture |  | recreation_culture |
| 25 | Natural & artificial flowers, foliages & plants | 09 | recreation_culture |  | recreation_culture |
| 27 | Other recreational or cultural items, (Pets:- cats, dogs, Birds) | 09 | recreation_culture |  | recreation_culture |
| 28 | Books | 09 | recreation_culture |  | recreation_culture |
| 29 | Magazines | 09 | recreation_culture |  | recreation_culture |
| 30 | Stationary supplies (stapler, perforator, Folder, etc..) | 09 | recreation_culture |  | recreation_culture |
| 32 | Stadium entry | 09 | recreation_culture |  | recreation_culture |
| 33 | Cinema/movie entry/ Video club | 09 | recreation_culture |  | recreation_culture |
| 34 | Dancing | 09 | recreation_culture |  | recreation_culture |
| 35 | Other leisure activities | 09 | recreation_culture |  | recreation_culture |
| 26 | Other interior decorations | 05.1 | furnishing_household |  | furnishing_household |
| 31 | Passport photos | 12.7 | miscellaneous |  | miscellaneous |
| 54 | Photocopies/printing/scanner/other secretarial services | 12.7 | miscellaneous |  | miscellaneous |
| 36 | Men's haircut (barber) | 12.1 | miscellaneous |  | miscellaneous |
| 37 | Women's haircut (stylist & treatment) | 12.1 | miscellaneous |  | miscellaneous |
| 38 | Beauty Treatment/Massage(Non-medical)/ Manicure & steam bath | 12.1 | miscellaneous |  | miscellaneous |
| 39 | Shaving accessories | 12.1 | miscellaneous |  | miscellaneous |
| 40 | Combs | 12.1 | miscellaneous |  | miscellaneous |
| 41 | Other personal hygiene products, e.g.; razor blades, nail cutters | 12.1 | miscellaneous |  | miscellaneous |
| 42 | Toothpaste (and accessories) | 12.1 | miscellaneous |  | miscellaneous |
| 43 | Hair products | 12.1 | miscellaneous |  | miscellaneous |
| 44 | Beauty/cosmetics products | 12.1 | miscellaneous |  | miscellaneous |
| 45 | Deodorants | 12.1 | miscellaneous |  | miscellaneous |
| 46 | Sanitary napkins, pampers | 12.1 | miscellaneous |  | miscellaneous |
| 47 | Postage stamps | 08 | communication |  | communication |
| 48 | Rwandatel/MTN fixed line charges | 08 | communication |  | communication |
| 49 | Fax and courier services | 08 | communication |  | communication |
| 50 | Internet connection subscription (MTN/Airtel-TIGO/…) | 08 | communication |  | communication |
| 55 | Diabetes drugs | 06 | health |  | health |
| 56 | Heart disease medicines | 06 | health |  | health |
| 57 | High/low blood pressure drugs | 06 | health |  | health |
| 58 | Asthma drugs | 06 | health |  | health |
| 59 | ARV drugs | 06 | health |  | health |
| 60 | Pain relievers (Aspirin/Paracetamol/Hedex, …) | 06 | health |  | health |
| 61 | Antimalarial drugs | 06 | health |  | health |
| 62 | Astringents (iodine, alcohol) | 06 | health |  | health |
| 63 | Worm medicine | 06 | health |  | health |
| 64 | Condoms | 06 | health |  | health |
| 65 | Medical consultations | 06 | health |  | health |

### nonfood_weekly (23 rows)

| Code / variable | Item | COICOP 1999 | CPI category | Alternative (urban) | Cell |
|---|---|---|---|---|---|
| 1 | Laundry soap | 05.6 | furnishing_household |  | furnishing_household |
| 3 | Other soaps and Detergents | 05.6 | furnishing_household |  | furnishing_household |
| 4 | Insecticides/ Other mosquito repellant | 05.6 | furnishing_household |  | furnishing_household |
| 14 | Candle | 05.6 | furnishing_household |  | furnishing_household |
| 15 | Matches/lighter | 05.6 | furnishing_household |  | furnishing_household |
| 2 | Bath soap | 12.1 | miscellaneous |  | miscellaneous |
| 5 | Toilet paper | 12.1 | miscellaneous |  | miscellaneous |
| 6 | Parking | 07.2 | transport |  | transport_other |
| 7 | Taxi fees (Voiture) | 07.3 | transport |  | transport_other |
| 8 | Buses  including Coaster and minibus | 07.3 | transport |  | transport_other |
| 9 | Motorcycle | 07.3 | transport |  | transport_other |
| 10 | Bicycle | 07.3 | transport |  | transport_other |
| 11 | Other transport, e,g Boats etc | 07.3 | transport |  | transport_other |
| 12 | Charcoal (cooking) | 04.5 | housing_utilities | energy | housing_energy |
| 13 | Wood (cooking) | 04.5 | housing_utilities | energy | housing_energy |
| 16 | Fuel for generator | 04.5 | housing_utilities | energy | housing_energy |
| 17 | Mobile phone battery recharging | 08 | communication |  | communication |
| 18 | Airtime (cell phone) | 08 | communication |  | communication |
| 19 | Internet cafe | 08 | communication |  | communication |
| 20 | Dried tobacco leaves | 02.2 | alcohol_tobacco |  | alcohol_tobacco |
| 21 | Cigarettes | 02.2 | alcohol_tobacco |  | alcohol_tobacco |
| 22 | Construction wood | 04.3 | housing_utilities |  | housing_other |
| 23 | Other non-food products | 12.7 | miscellaneous | headline | miscellaneous |

### other_expenditure (13 rows)

| Code / variable | Item | COICOP 1999 | CPI category | Alternative (urban) | Cell |
|---|---|---|---|---|---|
| 1 | Taxes on property | transfers | excluded |  | not in cons1 |
| 2 | Other taxes/Duties | transfers | excluded |  | not in cons1 |
| 3 | Contributions to mutual aid or developmental projects | transfers | excluded |  | not in cons1 |
| 4 | Charitable works | transfers | excluded |  | not in cons1 |
| 5 | Gifts and donations (excluding  those declared above as transfers) | transfers | excluded |  | not in cons1 |
| 7 | Contribution to other HH's wedding | transfers | excluded |  | not in cons1 |
| 11 | Offering and tythes | transfers | excluded |  | not in cons1 |
| 6 | Weddings/Introduction own HH | ceremonies | headline |  | not in cons1 |
| 8 | Baptism | ceremonies | headline |  | not in cons1 |
| 10 | Religious festivals (Christmas, Easter, etc.) | ceremonies | headline |  | not in cons1 |
| 12 | Other ceremonies (child naming, graduation ceremonies etc.) | ceremonies | headline |  | not in cons1 |
| 13 | Other expenditure  (to exclude any savings) | ceremonies | headline |  | not in cons1 |
| 9 | Death (Including funerary articles e.g. coffin, etc.) | 12.7 | miscellaneous |  | not in cons1 |

### durables (27 rows)

| Code / variable | Item | COICOP 1999 | CPI category | Alternative (urban) | Cell |
|---|---|---|---|---|---|
| 1 | Living room suite (table+chairs) | 05.1 | furnishing_household |  | durables_use_value (through exp11) |
| 2 | Dining Table (table+chairs) | 05.1 | furnishing_household |  | durables_use_value (through exp11) |
| 3 | Beds | 05.1 | furnishing_household |  | durables_use_value (through exp11) |
| 4 | Matresses | 05.1 | furnishing_household |  | durables_use_value (through exp11) |
| 5 | Table | 05.1 | furnishing_household |  | durables_use_value (through exp11) |
| 6 | Chairs | 05.1 | furnishing_household |  | durables_use_value (through exp11) |
| 7 | Bench | 05.1 | furnishing_household |  | durables_use_value (through exp11) |
| 8 | Car for home use | 07.1 | transport |  | durables_use_value (through exp11) |
| 9 | Motorcycle for personal use | 07.1 | transport |  | durables_use_value (through exp11) |
| 10 | Bicycle/Tricycles for personal use | 07.1 | transport |  | durables_use_value (through exp11) |
| 11 | Solar lamps | 05.5 | furnishing_household |  | durables_use_value (through exp11) |
| 27 | Garden tractors (Grass Cutting Machine) | 05.5 | furnishing_household |  | durables_use_value (through exp11) |
| 12 | Refrigerator/Freezers | 05.3 | furnishing_household |  | durables_use_value (through exp11) |
| 13 | Electric/Gas Cooker | 05.3 | furnishing_household |  | durables_use_value (through exp11) |
| 14 | Washing Machine/ Dryer | 05.3 | furnishing_household |  | durables_use_value (through exp11) |
| 15 | Electrical Iron | 05.3 | furnishing_household |  | durables_use_value (through exp11) |
| 16 | Microwave | 05.3 | furnishing_household |  | durables_use_value (through exp11) |
| 17 | Blender/ mixer | 05.3 | furnishing_household |  | durables_use_value (through exp11) |
| 18 | Water dispenser | 05.3 | furnishing_household |  | durables_use_value (through exp11) |
| 19 | Mobile handsets (basic) | 08 | communication |  | durables_use_value (through exp11) |
| 20 | Mobile handsets (smart phone) | 08 | communication |  | durables_use_value (through exp11) |
| 21 | Computer (desktop/laptop) | 09 | recreation_culture |  | durables_use_value (through exp11) |
| 22 | Tablet | 09 | recreation_culture |  | durables_use_value (through exp11) |
| 23 | Television sets | 09 | recreation_culture |  | durables_use_value (through exp11) |
| 24 | Radio sets | 09 | recreation_culture |  | durables_use_value (through exp11) |
| 25 | Home theater, CD players and sound players | 09 | recreation_culture |  | durables_use_value (through exp11) |
| 26 | Cameras (still, digital, Video cameras) | 09 | recreation_culture |  | durables_use_value (through exp11) |

### poverty (12 rows)

| Code / variable | Item | COICOP 1999 | CPI category | Alternative (urban) | Cell |
|---|---|---|---|---|---|
| `exp1` | Total education expenditures | 10 | education |  | split by items |
| `exp2` | Imputed rents | 04.2 | housing_utilities |  | housing_rent_imputed |
| `exp3` | Actual rents | 04.1 | housing_utilities |  | housing_rent_actual |
| `exp4` | Water expenses | 04.4 | housing_utilities |  | housing_other |
| `exp5` | Electricity expenses | 04.5 | housing_utilities | energy | housing_energy |
| `exp6` | Annual non-food expenditures (S8A1) | item level | item level |  | split by items |
| `exp7` | Monthly non-food expenditures (S8A2) | item level | item level |  | split by items |
| `exp8` | Frequent non-food expenditures (S8A3) | item level | item level |  | split by items |
| `exp9` | Food consumption at home (S8B) | item level | item level |  | split by items |
| `exp10` | Food outside home (S8C) | 11.1 | restaurants_hotels |  | restaurants_hotels |
| `exp11` | Use values of durable goods (S10B) | item level | item level |  | durables_use_value |
| `Food_at_school` | Education expenses / food at school | 11.1 | restaurants_hotels |  | restaurants_hotels |

### person (10 rows)

| Code / variable | Item | COICOP 1999 | CPI category | Alternative (urban) | Cell |
|---|---|---|---|---|---|
| `s4aq14a` | Registration and school fees | 10 | education |  | education |
| `s4aq14b` | Parent contributions | 10 | education |  | education |
| `s4aq14c` | School uniforms | 03.1 | clothing_footwear |  | clothing_footwear |
| `s4aq14d` | Books and school supplies | 09 | recreation_culture | education | recreation_culture |
| `s4aq14e` | Transport to and from school | 07.3 | transport |  | transport_other |
| `s4aq14f` | Room and board | 10 | education | restaurants_hotels | not in exp1 (NISR excludes) |
| `s4aq14g` | Other schooling expenditures | 10 | education |  | education |
| `s4aq14h` | Total education expenses (non-distributed) | 10 | education |  | education |
| `s4aq15a` | School feeding | 11.1 | restaurants_hotels |  | restaurants_hotels (amount is Food_at_school) |
| `s4bq2` | Vocational training expenses | 10 | education |  | not in exp1 (NISR excludes) |

### food_away (7 rows)

| Code / variable | Item | COICOP 1999 | CPI category | Alternative (urban) | Cell |
|---|---|---|---|---|---|
| `s8cq4_v*` | Breakfast away from home | 11.1 | restaurants_hotels |  | restaurants_hotels |
| `s8cq6_v*` | Lunch away from home | 11.1 | restaurants_hotels |  | restaurants_hotels |
| `s8cq8_v*` | Dinner away from home | 11.1 | restaurants_hotels |  | restaurants_hotels |
| `s8cq10_v*` | Snacks between meals away from home | 11.1 | restaurants_hotels |  | restaurants_hotels |
| `s8cq12_v*` | Hot beverages away from home | 11.1 | restaurants_hotels |  | restaurants_hotels |
| `s8cq14_v*` | Non-alcoholic drinks away from home | 11.1 | restaurants_hotels |  | restaurants_hotels |
| `s8cq16_v*` | Alcoholic drinks away from home | 11.1 | restaurants_hotels |  | restaurants_hotels |

### household (7 rows)

| Code / variable | Item | COICOP 1999 | CPI category | Alternative (urban) | Cell |
|---|---|---|---|---|---|
| `s5bq2a` | Estimated rent for dwelling (owners) | 04.2 | housing_utilities |  | not used: NISR aggregates exp2-exp5 carry these amounts |
| `s5bq3a` | Actual rent paid in cash | 04.1 | housing_utilities |  | not used: NISR aggregates exp2-exp5 carry these amounts |
| `s5bq5a` | Services or payment in kind for dwelling | 04.1 | housing_utilities |  | not used: NISR aggregates exp2-exp5 carry these amounts |
| `s5cq9b` | Last water bill (WASAC or other) | 04.4 | housing_utilities |  | not used: NISR aggregates exp2-exp5 carry these amounts |
| `s5cq11` | Paid to private water vendor | 04.4 | housing_utilities |  | not used: NISR aggregates exp2-exp5 carry these amounts |
| `s5cq12` | Contribution to maintain water source | 04.4 | housing_utilities |  | not used: NISR aggregates exp2-exp5 carry these amounts |
| `s5cq20` | Electricity payments | 04.5 | housing_utilities | energy | not used: NISR aggregates exp2-exp5 carry these amounts |
