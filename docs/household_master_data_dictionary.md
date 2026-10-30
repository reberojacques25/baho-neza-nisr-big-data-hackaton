# Household master table: data dictionary

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
  missing, not zero, for the 4 households with two conflicting versions of section 9 (and for household
  [ID withheld] in transfers sent).

`pct_missing` is the unweighted share of households with a missing value.


## Identifiers and design

| Column | Type | % missing | Description | Source and rule |
|---|---|---:|---|---|
| `hhid` | int64 | 0 | Household ID; primary key | poverty file `hhid`, cast to int64 |
| `clust` | int64 | 0 | Primary sampling unit (1,674 clusters) | poverty file `clust` |
| `strata_id` | Int64 | 0 | Sampling stratum (60 = district x urban/rural) | household file `strata_id` |
| `province` | int8 | 0 | Province code (1 Kigali, 2 South, 3 West, 4 North, 5 East) | poverty file `province` |
| `province_name` | str | 0 | Province name | poverty file value label of `province` |
| `district` | int16 | 0 | District code (11-57) | poverty file `district` |
| `district_name` | str | 0 | District name | poverty file value label of `district` |
| `ur` | int8 | 0 | Urban/rural code (1 urban, 2 rural); selects the CPI area | poverty file `ur` |
| `area` | str | 0 | 'urban' or 'rural' | from `ur` |
| `weight` | float64 | 0 | Household weight. Use for household-level estimates | poverty file `weight` |
| `pop_wt` | float32 | 0 | Population weight (= weight x hh_size). Use for person-level estimates such as poverty rates | poverty file `pop_wt` |

## Welfare and poverty

| Column | Type | % missing | Description | Source and rule |
|---|---|---:|---|---|
| `hh_size` | int16 | 0 | Household size (members) | poverty file `member`; equals the roster count |
| `adult_equivalents` | float64 | 0 | Household size in adult equivalents | poverty file `ae` |
| `cons_nominal` | float32 | 0 | Annual consumption, survey-period prices, RWF (NISR aggregate) | poverty file `cons1` |
| `cons_nominal_ae` | float32 | 0 | Annual consumption per adult equivalent, survey-period prices, RWF | poverty file `cons1ae` |
| `hh_price_index` | float64 | 0 | NISR household Paasche price index to national January 2024 prices | poverty file `hh_index` |
| `cons_real_ae_jan2024` | float32 | 0 | Real consumption per adult equivalent, January 2024 prices, RWF. NISR's welfare measure | poverty file `sol_jan` (= cons1ae / hh_index) |
| `cons_real_jan2024` | float64 | 0 | Real household consumption, January 2024 prices, RWF | cons1 / hh_index |
| `cons_real_pc_jan2024` | float64 | 0 | Real consumption per person, January 2024 prices, RWF | cons_real_jan2024 / hh_size |
| `exp1` | float32 | 0 | NISR aggregate: education (includes food at school) | poverty file `exp1` |
| `exp2` | float32 | 0 | NISR aggregate: imputed rent of owner-occupiers | poverty file `exp2` |
| `exp3` | float32 | 0 | NISR aggregate: actual rent | poverty file `exp3` |
| `exp4` | float32 | 0 | NISR aggregate: water | poverty file `exp4` |
| `exp5` | float32 | 0 | NISR aggregate: electricity | poverty file `exp5` |
| `exp6` | float64 | 0 | NISR aggregate: annual non-food items (S8A1) | poverty file `exp6` |
| `exp7` | float64 | 0 | NISR aggregate: monthly non-food items (S8A2) | poverty file `exp7` |
| `exp8` | float64 | 0 | NISR aggregate: frequent non-food items (S8A3) | poverty file `exp8` |
| `exp9` | float64 | 0 | NISR aggregate: food and drink consumed at home, incl. own production (S8B) | poverty file `exp9` |
| `exp10` | float64 | 0 | NISR aggregate: food away from home (S8C) | poverty file `exp10` |
| `exp11` | float64 | 1.7 | NISR aggregate: use value of durable goods (S10B). Missing for 1.7% of households; cons1 counts it as 0 | poverty file `exp11` |
| `food` | float32 | 0 | NISR total food (= exp9 + exp10 + food at school). Never add to exp1 | poverty file `food` |
| `food_at_school` | float32 | 0 | Food at school; counted in both exp1 and food | poverty file `Food_at_school` |
| `poverty_line_jan2024` | float32 | 0 | Poverty line, RWF per adult equivalent per year, January 2024 prices (560,127) | poverty file `Poverty_line` |
| `extreme_line_jan2024` | float32 | 0 | Extreme (food) poverty line, January 2024 prices (356,432) | poverty file `Extreme_line` |
| `poor` | Int8 | 0 | 1 = poor. Harmonised: poverty file codes 0/100, module files 0/1 | poverty file `pov_jan` / 100 |
| `extreme_poor` | Int8 | 0 | 1 = extremely poor (harmonised to 0/1) | poverty file `epov_jan` / 100 |
| `welfare_category` | Int8 | 0 | 1 severely poor, 2 moderately poor, 3 non-poor | poverty file `poverty` |
| `welfare_category_name` | str | 0 | Label of welfare_category | poverty file value label of `poverty` |
| `quintile` | Int8 | 0 | Quintile of real consumption per adult equivalent (1 poorest) | poverty file `quintile` |
| `welfare_ratio` | float32 | 0 | Real consumption per adult equivalent / poverty line | sol_jan / Poverty_line |
| `near_poor` | Int8 | 0 | 1 = not poor but below 1.5 x the poverty line (project definition) | 1 <= welfare_ratio < 1.5 |

## Demographics

| Column | Type | % missing | Description | Source and rule |
|---|---|---:|---|---|
| `n_children_0_14` | int16 | 0 | Members aged 0-14 | person file `s1q3y` |
| `n_working_age_15_64` | int16 | 0 | Members aged 15-64 | person file `s1q3y` |
| `n_elderly_65plus` | int16 | 0 | Members aged 65 and over | person file `s1q3y` |
| `n_children_0_4` | int16 | 0 | Members aged 0-4 | person file `s1q3y` |
| `dependency_ratio` | float64 | 5.59 | (children 0-14 + elderly 65+) / working-age 15-64. Missing when no member is 15-64 | derived |
| `no_working_age_member` | Int8 | 0 | 1 = no member aged 15-64 (dependency ratio undefined) | derived |
| `share_dependents` | float64 | 0 | (children 0-14 + elderly 65+) / household size. Always defined | derived |
| `n_members_with_disability` | int16 | 0 | Members with 'a lot of difficulty' or 'cannot do' in any Washington Group domain | person file `s3q7`-`s3q12` in (3, 4) |
| `head_female` | Int8 | 0 | 1 = household head is female | person file `s1q1` where `s1q2` = 1 |
| `head_age` | int16 | 0 | Age of the household head, years | person file `s1q3y` (998 = don't know set missing; none found) |
| `head_age_over_100` | Int8 | 0 | Quality flag: head's reported age above 100 | derived |
| `head_marital_status` | str | 0 | married / divorced_separated / widowed / never_married | person file `s1q4` grouped |

## Education, health and ICT

| Column | Type | % missing | Description | Source and rule |
|---|---|---:|---|---|
| `share_members_health_insured` | float64 | 0 | Share of members covered by health insurance | person file `s3q2` |
| `head_education_code` | Int8 | 0 | Head's highest level attended, 0 none ... 5 tertiary (see head_education_level) | person file `s4aq1`, `s4aq2`; ECD and nursery count as none |
| `head_education_level` | str | 0 | none / primary / post_primary_vocational / lower_secondary / upper_secondary / tertiary | from head_education_code |
| `head_literate` | Int8 | 0 | 1 = head can read a simple note | person file `s4bq4` |
| `max_education_code` | Int8 | 0 | Highest education code of any member | as head_education_code |
| `n_children_in_school` | int16 | 0 | Members aged 6-17 who attended school in the last 12 months | person file `s4aq7` |
| `any_member_mobile_phone` | Int8 | 0 | 1 = at least one member has a mobile phone | person file `s4bq8` |
| `any_member_mobile_money_use` | Int8 | 0 | 1 = at least one member used mobile financial services (asked of internet users only) | person file `s4bq23c` |

## Employment and livelihoods

| Column | Type | % missing | Description | Source and rule |
|---|---|---:|---|---|
| `n_employed` | int16 | 0 | Members with a main job recorded (any age) | person file `s6bq7` filled |
| `n_own_farming` | int16 | 0 | Employed members whose main job is in agriculture (ISIC A), not as employee | person file `s6bq4` = 1, `s6bq7` not 1-2 |
| `n_farm_wage` | int16 | 0 | Employed members in agriculture as employees | person file `s6bq4` = 1, `s6bq7` in 1-2 |
| `n_nonfarm_wage` | int16 | 0 | Employed members outside agriculture as employees | person file `s6bq4` != 1, `s6bq7` in 1-2 |
| `n_nonfarm_self_employment` | int16 | 0 | Employed members outside agriculture, not as employee | person file `s6bq4` != 1, `s6bq7` not 1-2 |
| `n_informal_proxy` | int16 | 0 | Employed members in informal work (proxy, see share_employed_informal_proxy) | derived |
| `n_casual_wage` | int16 | 0 | Employees on casual, seasonal, daily or other contracts | person file `s6bq8` in 3-6 |
| `share_employed_in_agriculture` | float64 | 2.61 | Share of employed members whose main job is in agriculture | derived; missing if none employed |
| `share_employed_informal_proxy` | float64 | 2.61 | Share of employed members not in formal work. Formal = public, mixed or international-NGO employer, or employee with a permanent or fixed-term contract. EICV7 has no social-security or registration question, so this is a proxy | person file `s6bq5`, `s6bq7`, `s6bq8` |
| `agriculture_dependent` | Int8 | 2.61 | 1 = at least half of employed members work mainly in agriculture | share_employed_in_agriculture >= 0.5 |
| `any_wage_worker` | Int8 | 0 | 1 = at least one employee (farm or non-farm) | derived |
| `any_nonfarm_wage_worker` | Int8 | 0 | 1 = at least one non-farm employee | derived |
| `any_self_employed` | Int8 | 0 | 1 = at least one member self-employed (farm or non-farm) | derived |
| `any_agricultural_activity` | Int8 | 0 | 1 = any member worked on own farm or did any agricultural activity | person file `s6aq2`, `s6aq4` |
| `any_nonfarm_business` | Int8 | 0 | 1 = any member runs a non-farm business or is non-farm self-employed | person file `s6aq6` |
| `main_livelihood` | str | 0 | Main income source (employment-based proxy): livelihood type of most employed members; ties go to the head's type. own_farming / farm_wage / nonfarm_wage / nonfarm_self_employment / no_employed_member. EICV7 has no household income aggregate | derived |
| `head_employed` | Int8 | 0 | 1 = head has a main job | derived |
| `head_livelihood` | str | 0 | Head's livelihood type ('none' if not employed) | derived |
| `head_informal_proxy` | Int8 | 7.87 | 1 = head's main job is informal (proxy); missing if head not employed | derived |

## Expenditure

| Column | Type | % missing | Description | Source and rule |
|---|---|---:|---|---|
| `exp_cell_bread_cereals` | float64 | 0 | Annual spending in one price cell, survey-period prices, RWF. NISR aggregates exp1-exp11 split by the household's own item values (see docs/expenditure_cpi_mapping.md). The 25 cells sum to exp1 + ... + exp11 | derived from exp1-exp11, S8A1-S8A3, S8B, person file |
| `exp_cell_meat` | float64 | 0 | Annual spending in one price cell, survey-period prices, RWF. NISR aggregates exp1-exp11 split by the household's own item values (see docs/expenditure_cpi_mapping.md). The 25 cells sum to exp1 + ... + exp11 | derived from exp1-exp11, S8A1-S8A3, S8B, person file |
| `exp_cell_milk_cheese_eggs` | float64 | 0 | Annual spending in one price cell, survey-period prices, RWF. NISR aggregates exp1-exp11 split by the household's own item values (see docs/expenditure_cpi_mapping.md). The 25 cells sum to exp1 + ... + exp11 | derived from exp1-exp11, S8A1-S8A3, S8B, person file |
| `exp_cell_vegetables` | float64 | 0 | Annual spending in one price cell, survey-period prices, RWF. NISR aggregates exp1-exp11 split by the household's own item values (see docs/expenditure_cpi_mapping.md). The 25 cells sum to exp1 + ... + exp11 | derived from exp1-exp11, S8A1-S8A3, S8B, person file |
| `exp_cell_non_alcoholic_beverages` | float64 | 0 | Annual spending in one price cell, survey-period prices, RWF. NISR aggregates exp1-exp11 split by the household's own item values (see docs/expenditure_cpi_mapping.md). The 25 cells sum to exp1 + ... + exp11 | derived from exp1-exp11, S8A1-S8A3, S8B, person file |
| `exp_cell_food_other_fresh` | float64 | 0 | Annual spending in one price cell, survey-period prices, RWF. NISR aggregates exp1-exp11 split by the household's own item values (see docs/expenditure_cpi_mapping.md). The 25 cells sum to exp1 + ... + exp11 | derived from exp1-exp11, S8A1-S8A3, S8B, person file |
| `exp_cell_food_other_local` | float64 | 0 | Annual spending in one price cell, survey-period prices, RWF. NISR aggregates exp1-exp11 split by the household's own item values (see docs/expenditure_cpi_mapping.md). The 25 cells sum to exp1 + ... + exp11 | derived from exp1-exp11, S8A1-S8A3, S8B, person file |
| `exp_cell_food_other_imported` | float64 | 0 | Annual spending in one price cell, survey-period prices, RWF. NISR aggregates exp1-exp11 split by the household's own item values (see docs/expenditure_cpi_mapping.md). The 25 cells sum to exp1 + ... + exp11 | derived from exp1-exp11, S8A1-S8A3, S8B, person file |
| `exp_cell_food_other_nec` | float64 | 0 | Annual spending in one price cell, survey-period prices, RWF. NISR aggregates exp1-exp11 split by the household's own item values (see docs/expenditure_cpi_mapping.md). The 25 cells sum to exp1 + ... + exp11 | derived from exp1-exp11, S8A1-S8A3, S8B, person file |
| `exp_cell_alcohol_tobacco` | float64 | 0 | Annual spending in one price cell, survey-period prices, RWF. NISR aggregates exp1-exp11 split by the household's own item values (see docs/expenditure_cpi_mapping.md). The 25 cells sum to exp1 + ... + exp11 | derived from exp1-exp11, S8A1-S8A3, S8B, person file |
| `exp_cell_clothing_footwear` | float64 | 0 | Annual spending in one price cell, survey-period prices, RWF. NISR aggregates exp1-exp11 split by the household's own item values (see docs/expenditure_cpi_mapping.md). The 25 cells sum to exp1 + ... + exp11 | derived from exp1-exp11, S8A1-S8A3, S8B, person file |
| `exp_cell_housing_rent_actual` | float64 | 0 | Annual spending in one price cell, survey-period prices, RWF. NISR aggregates exp1-exp11 split by the household's own item values (see docs/expenditure_cpi_mapping.md). The 25 cells sum to exp1 + ... + exp11 | derived from exp1-exp11, S8A1-S8A3, S8B, person file |
| `exp_cell_housing_rent_imputed` | float64 | 0 | Annual spending in one price cell, survey-period prices, RWF. NISR aggregates exp1-exp11 split by the household's own item values (see docs/expenditure_cpi_mapping.md). The 25 cells sum to exp1 + ... + exp11 | derived from exp1-exp11, S8A1-S8A3, S8B, person file |
| `exp_cell_housing_energy` | float64 | 0 | Annual spending in one price cell, survey-period prices, RWF. NISR aggregates exp1-exp11 split by the household's own item values (see docs/expenditure_cpi_mapping.md). The 25 cells sum to exp1 + ... + exp11 | derived from exp1-exp11, S8A1-S8A3, S8B, person file |
| `exp_cell_housing_other` | float64 | 0 | Annual spending in one price cell, survey-period prices, RWF. NISR aggregates exp1-exp11 split by the household's own item values (see docs/expenditure_cpi_mapping.md). The 25 cells sum to exp1 + ... + exp11 | derived from exp1-exp11, S8A1-S8A3, S8B, person file |
| `exp_cell_furnishing_household` | float64 | 0 | Annual spending in one price cell, survey-period prices, RWF. NISR aggregates exp1-exp11 split by the household's own item values (see docs/expenditure_cpi_mapping.md). The 25 cells sum to exp1 + ... + exp11 | derived from exp1-exp11, S8A1-S8A3, S8B, person file |
| `exp_cell_health` | float64 | 0 | Annual spending in one price cell, survey-period prices, RWF. NISR aggregates exp1-exp11 split by the household's own item values (see docs/expenditure_cpi_mapping.md). The 25 cells sum to exp1 + ... + exp11 | derived from exp1-exp11, S8A1-S8A3, S8B, person file |
| `exp_cell_transport_fuel` | float64 | 0 | Annual spending in one price cell, survey-period prices, RWF. NISR aggregates exp1-exp11 split by the household's own item values (see docs/expenditure_cpi_mapping.md). The 25 cells sum to exp1 + ... + exp11 | derived from exp1-exp11, S8A1-S8A3, S8B, person file |
| `exp_cell_transport_other` | float64 | 0 | Annual spending in one price cell, survey-period prices, RWF. NISR aggregates exp1-exp11 split by the household's own item values (see docs/expenditure_cpi_mapping.md). The 25 cells sum to exp1 + ... + exp11 | derived from exp1-exp11, S8A1-S8A3, S8B, person file |
| `exp_cell_communication` | float64 | 0 | Annual spending in one price cell, survey-period prices, RWF. NISR aggregates exp1-exp11 split by the household's own item values (see docs/expenditure_cpi_mapping.md). The 25 cells sum to exp1 + ... + exp11 | derived from exp1-exp11, S8A1-S8A3, S8B, person file |
| `exp_cell_recreation_culture` | float64 | 0 | Annual spending in one price cell, survey-period prices, RWF. NISR aggregates exp1-exp11 split by the household's own item values (see docs/expenditure_cpi_mapping.md). The 25 cells sum to exp1 + ... + exp11 | derived from exp1-exp11, S8A1-S8A3, S8B, person file |
| `exp_cell_education` | float64 | 0 | Annual spending in one price cell, survey-period prices, RWF. NISR aggregates exp1-exp11 split by the household's own item values (see docs/expenditure_cpi_mapping.md). The 25 cells sum to exp1 + ... + exp11 | derived from exp1-exp11, S8A1-S8A3, S8B, person file |
| `exp_cell_restaurants_hotels` | float64 | 0 | Annual spending in one price cell, survey-period prices, RWF. NISR aggregates exp1-exp11 split by the household's own item values (see docs/expenditure_cpi_mapping.md). The 25 cells sum to exp1 + ... + exp11 | derived from exp1-exp11, S8A1-S8A3, S8B, person file |
| `exp_cell_miscellaneous` | float64 | 0 | Annual spending in one price cell, survey-period prices, RWF. NISR aggregates exp1-exp11 split by the household's own item values (see docs/expenditure_cpi_mapping.md). The 25 cells sum to exp1 + ... + exp11 | derived from exp1-exp11, S8A1-S8A3, S8B, person file |
| `exp_cell_durables_use_value` | float64 | 0 | Annual spending in one price cell, survey-period prices, RWF. NISR aggregates exp1-exp11 split by the household's own item values (see docs/expenditure_cpi_mapping.md). The 25 cells sum to exp1 + ... + exp11 | derived from exp1-exp11, S8A1-S8A3, S8B, person file |
| `share_food` | float64 | 0 | Food and non-alcoholic drinks at home (COICOP 01, incl. own production) / cons_nominal | food cells / cons1 |
| `share_food_nisr` | float32 | 0 | NISR food share: (exp9 + exp10 + food at school) / cons_nominal. Includes alcohol at home and meals away | food / cons1 |
| `share_meals_away` | float64 | 0 | Meals and drinks away from home / cons_nominal | exp10 / cons1 |
| `share_alcohol_tobacco` | float64 | 0 | Alcohol and tobacco / cons_nominal | cell / cons1 |
| `share_housing_utilities` | float64 | 0 | Rent (actual and imputed), water, electricity, fuels, maintenance / cons_nominal | housing cells / cons1 |
| `share_housing_utilities_excl_imputed_rent` | float64 | 0 | As share_housing_utilities without imputed rent | housing cells / cons1 |
| `share_energy` | float64 | 0 | Electricity, gas, kerosene, charcoal, firewood, generator and vehicle fuel / cons_nominal | housing_energy + transport_fuel / cons1 |
| `share_transport` | float64 | 0 | Transport (fuel, fares, repairs, school transport) / cons_nominal | transport cells / cons1 |
| `share_education` | float64 | 0 | Education services (fees, contributions, other school costs) / cons_nominal. Excludes uniforms, books, school transport and school food, which COICOP puts elsewhere | education cell / cons1 |
| `share_education_nisr` | float32 | 0 | NISR education share: exp1 / cons_nominal (includes uniforms, books, transport, food at school) | exp1 / cons1 |
| `share_communication` | float64 | 0 | Airtime, internet, phone charging, postage / cons_nominal | cell / cons1 |
| `share_health` | float64 | 0 | Health spending in cons1 / cons_nominal (NISR leaves lumpy health spending out of cons1) | cell / cons1 |
| `share_food_own_produced` | float64 | 0.79 | Share of the food diary value (visits 2-5) that is own production | S8B, valued |
| `n_aggregates_split_by_area_average` | int8 | 0 | Number of NISR aggregates split with the area-average item mix because the household had no item detail | derived |

## Housing, utilities and assets

| Column | Type | % missing | Description | Source and rule |
|---|---|---:|---|---|
| `tenure_owner` | Int8 | 0 | 1 = owner-occupied | household file `s5aq8` = 1 |
| `tenure_renter` | Int8 | 0 | 1 = renting | household file `s5aq8` = 2 |
| `sleeping_rooms` | int8 | 0 | Rooms used for sleeping | household file `s5aq3` |
| `persons_per_sleeping_room` | float64 | 0 | hh_size / sleeping rooms | derived |
| `wall_material` | Int8 | 0 | Wall material code | household file `s5dq1` |
| `roof_material` | Int8 | 0 | Roof material code | household file `s5dq2` |
| `floor_material` | Int8 | 0 | Floor material code | household file `s5dq3` |
| `improved_wall` | Int8 | 0 | 1 = fired bricks with cement, cement blocks, or stones with cement | household file `s5dq1` in 4, 5, 8 |
| `improved_roof` | Int8 | 0 | 1 = metal sheets, clay tiles, concrete or industrial tiles | household file `s5dq2` in 1, 2, 3, 5 |
| `improved_floor` | Int8 | 0 | 1 = not beaten earth or dung | household file `s5dq3` in 3-7 |
| `improved_drinking_water` | Int8 | 0.12 | 1 = JMP improved source (piped, borehole, protected well/spring, rain, tanker, bottled) | household file `s5cq3` |
| `electricity_any` | Int8 | 0 | 1 = grid or solar electricity | household file `s5cq14` in 1-3 |
| `electricity_grid` | Int8 | 0 | 1 = connected to the grid | household file `s5cq14` in 1, 3 |
| `clean_cooking_fuel` | Int8 | 0.58 | 1 = main cooking fuel is gas, biogas, solar or electricity | household file `s5cq22a` |
| `cooking_fuel_firewood` | Int8 | 0.58 | 1 = main cooking fuel is firewood | household file `s5cq22a` = 1 |
| `cooking_fuel_charcoal` | Int8 | 0.58 | 1 = main cooking fuel is charcoal | household file `s5cq22a` = 2 |
| `improved_sanitation` | Int8 | 0 | 1 = JMP improved toilet | household file `s5cq25` in 1-6 |
| `basic_sanitation` | Int8 | 0 | 1 = improved toilet not shared with other households | household file `s5cq25`, `s5cq26` |
| `internet_at_home` | Int8 | 0 | 1 = household has an internet connection | household file `s5cq20a` |
| `any_shock_12m` | Int8 | 0 | 1 = household reported an unusual negative event in the last 12 months | household file `s5eq1` |
| `shock_high_food_prices` | Int8 | 0 | 1 = unusually high food prices named among the three main shocks | household file `s5eq2a`-`c` = 8 |
| `girinka_cow_received` | Int8 | 0 | 1 = ever received a cow under Girinka (One Cow per Poor Family) | household file `s7a2q1` |
| `n_cattle` | float64 | 0 | Cattle owned (0 if no livestock) | household file `s7aq4a` |
| `n_goats` | float64 | 0 | Goats owned | household file `s7aq4b` |
| `n_sheep` | float64 | 0 | Sheep owned | household file `s7aq4c` |
| `n_pigs` | float64 | 0 | Pigs owned | household file `s7aq4d` |
| `n_poultry` | float64 | 0 | Poultry owned | household file `s7aq4e` |
| `tropical_livestock_units` | float64 | 0 | Livestock in TLU: cattle 0.7, goats and sheep 0.1, pigs 0.2, poultry 0.01 (FAO weights for sub-Saharan Africa) | derived |
| `owns_livestock` | Int8 | 0.01 | 1 = owns or raises livestock | household file `s7aq4` |
| `owns_car` | Int8 | 0 | 1 = household owns at least one of the durable (car, motorcycle, bicycle, solar lamp, refrigerator, basic mobile, smartphone, computer, television, radio; owns_mobile_phone = basic or smart) | durables file `s10bq0`, `s10bq2` |
| `owns_motorcycle` | Int8 | 0 | 1 = household owns at least one of the durable (car, motorcycle, bicycle, solar lamp, refrigerator, basic mobile, smartphone, computer, television, radio; owns_mobile_phone = basic or smart) | durables file `s10bq0`, `s10bq2` |
| `owns_bicycle` | Int8 | 0 | 1 = household owns at least one of the durable (car, motorcycle, bicycle, solar lamp, refrigerator, basic mobile, smartphone, computer, television, radio; owns_mobile_phone = basic or smart) | durables file `s10bq0`, `s10bq2` |
| `owns_solar_lamp` | Int8 | 0 | 1 = household owns at least one of the durable (car, motorcycle, bicycle, solar lamp, refrigerator, basic mobile, smartphone, computer, television, radio; owns_mobile_phone = basic or smart) | durables file `s10bq0`, `s10bq2` |
| `owns_refrigerator` | Int8 | 0 | 1 = household owns at least one of the durable (car, motorcycle, bicycle, solar lamp, refrigerator, basic mobile, smartphone, computer, television, radio; owns_mobile_phone = basic or smart) | durables file `s10bq0`, `s10bq2` |
| `owns_mobile_basic` | Int8 | 0 | 1 = household owns at least one of the durable (car, motorcycle, bicycle, solar lamp, refrigerator, basic mobile, smartphone, computer, television, radio; owns_mobile_phone = basic or smart) | durables file `s10bq0`, `s10bq2` |
| `owns_smartphone` | Int8 | 0 | 1 = household owns at least one of the durable (car, motorcycle, bicycle, solar lamp, refrigerator, basic mobile, smartphone, computer, television, radio; owns_mobile_phone = basic or smart) | durables file `s10bq0`, `s10bq2` |
| `owns_computer` | Int8 | 0 | 1 = household owns at least one of the durable (car, motorcycle, bicycle, solar lamp, refrigerator, basic mobile, smartphone, computer, television, radio; owns_mobile_phone = basic or smart) | durables file `s10bq0`, `s10bq2` |
| `owns_television` | Int8 | 0 | 1 = household owns at least one of the durable (car, motorcycle, bicycle, solar lamp, refrigerator, basic mobile, smartphone, computer, television, radio; owns_mobile_phone = basic or smart) | durables file `s10bq0`, `s10bq2` |
| `owns_radio` | Int8 | 0 | 1 = household owns at least one of the durable (car, motorcycle, bicycle, solar lamp, refrigerator, basic mobile, smartphone, computer, television, radio; owns_mobile_phone = basic or smart) | durables file `s10bq0`, `s10bq2` |
| `owns_mobile_phone` | Int8 | 0 | 1 = household owns at least one of the durable (car, motorcycle, bicycle, solar lamp, refrigerator, basic mobile, smartphone, computer, television, radio; owns_mobile_phone = basic or smart) | durables file `s10bq0`, `s10bq2` |
| `n_key_assets` | int8 | 0 | Count of: radio, television, mobile phone, bicycle, motorcycle, car, refrigerator, computer (0-8) | derived |

## Service access

| Column | Type | % missing | Description | Source and rule |
|---|---|---:|---|---|
| `minutes_to_drinking_water` | float64 | 22.29 | Travel time to the service, minutes (hours x 60 + minutes). Missing when not reported, e.g. service not used | services file `s5fq0`, `s5fq3a`, `s5fq3b` |
| `minutes_to_food_market` | float64 | 7.17 | Travel time to the service, minutes (hours x 60 + minutes). Missing when not reported, e.g. service not used | services file `s5fq0`, `s5fq3a`, `s5fq3b` |
| `minutes_to_produce_market` | float64 | 65.56 | Travel time to the service, minutes (hours x 60 + minutes). Missing when not reported, e.g. service not used | services file `s5fq0`, `s5fq3a`, `s5fq3b` |
| `minutes_to_public_transport` | float64 | 10.64 | Travel time to the service, minutes (hours x 60 + minutes). Missing when not reported, e.g. service not used | services file `s5fq0`, `s5fq3a`, `s5fq3b` |
| `minutes_to_primary_school` | float64 | 50.53 | Travel time to the service, minutes (hours x 60 + minutes). Missing when not reported, e.g. service not used | services file `s5fq0`, `s5fq3a`, `s5fq3b` |
| `minutes_to_secondary_school` | float64 | 84.45 | Travel time to the service, minutes (hours x 60 + minutes). Missing when not reported, e.g. service not used | services file `s5fq0`, `s5fq3a`, `s5fq3b` |
| `minutes_to_district_hospital` | float64 | 18.64 | Travel time to the service, minutes (hours x 60 + minutes). Missing when not reported, e.g. service not used | services file `s5fq0`, `s5fq3a`, `s5fq3b` |
| `minutes_to_health_centre` | float64 | 5.87 | Travel time to the service, minutes (hours x 60 + minutes). Missing when not reported, e.g. service not used | services file `s5fq0`, `s5fq3a`, `s5fq3b` |

## Savings and credit

| Column | Type | % missing | Description | Source and rule |
|---|---|---:|---|---|
| `any_account` | Int8 | 0 | 1 = any member has an account (bank, MFI, SACCO, mobile money) | savings file `s10cq4` |
| `any_bank_account` | Int8 | 0 | 1 = account at a commercial bank, microfinance or cooperative bank | savings file `s10cq5` in 1-3 |
| `any_sacco_account` | Int8 | 0 | 1 = SACCO account | savings file `s10cq5` = 4 |
| `any_mobile_money_account` | Int8 | 0 | 1 = MoMo or Mokash account | savings file `s10cq5` in 5, 6 |
| `any_tontine` | Int8 | 0 | 1 = any member in a tontine (informal savings group) | savings file `s10cq8` |
| `loan_denied_12m` | Int8 | 0 | 1 = a member applied for and failed to get a loan in the last 12 months | credit file `s10aq1` |
| `any_loan_12m` | Int8 | 0 | 1 = members owe or owed money or goods in the last 12 months | credit file `s10aq3` |
| `any_formal_loan` | Int8 | 0 | 1 = loan from employer, bank, credit cooperative, MFI, VUP, SACCO or Mokash | credit file `s10aq6` |
| `any_informal_loan` | Int8 | 0 | 1 = loan from relative, tontine, informal lender, business or other | credit file `s10aq6` |
| `n_loans` | int16 | 0 | Number of loans listed | credit file |
| `any_savings_instrument` | Int8 | 0 | 1 = any account or tontine | derived |

## VUP and social protection

| Column | Type | % missing | Description | Source and rule |
|---|---|---:|---|---|
| `vup_direct_support` | Int8 | 0 | 1 = VUP Direct Support beneficiary, last 12 months | S9D1 `s9d1q2` |
| `vup_classic_pw` | Int8 | 0 | 1 = VUP classic Public Works | S9D2 `s9d2q1` |
| `vup_expanded_pw` | Int8 | 0 | 1 = VUP expanded Public Works | S9D3 `s9d3q1` |
| `vup_nsds` | Int8 | 0 | 1 = Nutrition-Sensitive Direct Support | S9D4 `s9d4q1` |
| `vup_fs_applied` | Int8 | 0 | 1 = applied for a VUP Financial Services loan, last 12 months | S9D5 `s9d5q1` |
| `vup_financial_services` | Int8 | 0 | 1 = VUP Financial Services loan approved | S9D5 `s9d5q2` = 1 |
| `vup_any` | Int8 | 0 | 1 = any of the five components above (FS = approved). Built from the component flags, not `s9d1q1`, which only flags each file's own component. Asset transfers and skills development are not in the public files | derived |
| `vup_n_components` | int8 | 0 | Number of the five components received | derived |
| `vup_ds_amount_12m` | float64 | 97.1 | Direct Support received, last 12 months, RWF | S9D1 `s9d1q4` |
| `vup_cpw_months_12m` | float64 | 97.42 | Months in classic Public Works, last 12 months | S9D2 `s9d2q3` |
| `vup_cpw_daily_wage` | float64 | 97.42 | Classic Public Works daily wage, RWF | S9D2 `s9d2q4` |
| `vup_cpw_amount_12m` | float64 | 98 | Classic Public Works payments, last 12 months, RWF (not imputed) | S9D2 `s9d2q11` |
| `vup_cpw_amount_missing` | Int8 | 0 | Flag: classic PW beneficiary with no payment total | derived |
| `vup_epw_amount_12m` | float64 | 98.41 | Expanded Public Works payments, last 12 months, RWF (not imputed) | S9D3 `s9d3q10` |
| `vup_epw_amount_missing` | Int8 | 0 | Flag: expanded PW beneficiary with no payment total | derived |
| `vup_nsds_quarters_paid_12m` | float64 | 96.29 | Quarters with an NSDS payment, last 12 months | S9D4 `s9d4q7` |
| `vup_nsds_quarterly_payment` | float64 | 96.29 | NSDS payment per quarter, RWF. `s9d4q8` only; `s9d4q8a`-`d` are ignored | S9D4 `s9d4q8` |
| `vup_nsds_amount_12m_est` | float64 | 96.29 | Derived estimate: quarterly payment x quarters paid, RWF | `s9d4q8` x `s9d4q7` |
| `vup_fs_loan_amount` | float64 | 97.91 | VUP Financial Services loan received, RWF | S9D5 `s9d5q4` |

## Income and transfers

| Column | Type | % missing | Description | Source and rule |
|---|---|---:|---|---|
| `remittances_received_12m` | float64 | 0.03 | Cash transfers received, last 12 months, RWF. Missing for households unusable after deduplication | data/interim (notebook 05) S9B `s9bq8` |
| `any_remittance_received` | Int8 | 0.03 | 1 = household received transfers | data/interim (notebook 05) S9B `s9bq0` |
| `transfers_sent_12m` | float64 | 0.03 | Cash + food + in-kind transfers sent, last 12 months, RWF | data/interim (notebook 05) S9A `s9aq7` + `s9aq10` + `s9aq12` |
| `income_public_support_12m` | float64 | 0.03 | Public income support received, codes 01-11 (pensions, FARG, scholarships, food relief, goods ...), RWF | data/interim (notebook 05) S9E `s9eq4` |
| `income_private_other_12m` | float64 | 0.03 | Other private income, codes 12-23 (private pensions, rents, asset sales, dividends, GiveDirectly ...), RWF | data/interim (notebook 05) S9E `s9eq4` |
| `income_farm_12m` | float64 | 0.03 | Income from crop farming, livestock and aquaculture, codes 24-26, RWF | data/interim (notebook 05) S9E `s9eq4` |
| `other_income_total_12m` | float64 | 0.03 | Sum of the three S9E groups, RWF. Not a full income aggregate: no wages or business profits | data/interim (notebook 05) S9E `s9eq4` |
| `any_public_support` | Int8 | 0.03 | 1 = received public support codes 01-09 or 11. Code 10 (goods donations) is excluded | data/interim (notebook 05) S9E `s9eq2` |
| `received_govt_goods_donation` | Int8 | 0.03 | 1 = received government donations of goods (code 10: mosquito nets, buckets, phones ...) | data/interim (notebook 05) S9E `s9eq2` |

## Quality flags

| Column | Type | % missing | Description | Source and rule |
|---|---|---:|---|---|
| `s9_version_conflict` | Int8 | 0 | 1 = two conflicting versions of section 9 (notebook 05); section 9 totals are missing | data/interim (notebook 05) household flags |
