# Household CPI shock and Cost-of-Living Distress Score: methodology

**Question.** How much more does each EICV7 household's own consumption basket cost in September 2026 than in January 2024? And which households are least able to absorb that increase?

| | |
|---|---|
| **Code** | `src/features/household_cpi_shock.py` |
| **Notebook** | `notebooks/07_household_cpi_shock.ipynb` |
| **Output** | `data/processed/household_cpi_shock.parquet` (one row per household, 15,054 rows) |
| **Inputs** | `data/processed/household_master.parquet` (notebook 06), `data/processed/cpi_features.parquet` (notebook 03), `reports/data_inspection/expenditure_cpi_mapping.csv` |
| **Item mapping and fallbacks** | `docs/expenditure_cpi_mapping.md` |
| **Results** | `reports/household_cpi_shock_summary.md` |

This is descriptive measurement. Nothing is modelled, estimated, tuned or forecast.

## 1. Time window

| | Month | Why |
|---|---|---|
| Base | **January 2024** | NISR's real consumption (`sol_jan`) is in national January 2024 prices (EICV7 Methodological Note). Starting there means the shock adds to NISR's own deflation without overlapping it. |
| End | **September 2026** | The latest CPI month available. No later month is read. The code asserts that the CPI file ends in September 2026 or earlier. |
| Length | 32 months | Annualised inflation = (1 + price change)^(12/32) − 1 |

Only two index values per series are used: January 2024 and September 2026. The months in between are used only to report flagged index movements.

## 2. Each household's basket

**Shares, not CPI weights.** Each household is weighted by its own EICV7 spending pattern, not by the EICV4 (2013/14) weights of the CPI.

1. **Start from NISR's totals.** NISR's 11 consumption aggregates `exp1`–`exp11` sum to consumption (`cons1`), and they are kept unchanged.
2. **Split each total across 25 price cells** in proportion to the household's own item values (notebook 06):

| Aggregate | Split using | Reconciliation with NISR's total |
|---|---|---|
| `exp6` annual non-food | S8A1 purchases + gifts, leaving out the 11 items NISR excludes | Exact for all 15,047 households with spending |
| `exp7` monthly non-food | S8A2 purchases + gifts | Exact (× 365/28) for at least 99% |
| `exp8` frequent non-food | S8A3 purchases + gifts + own production | Exact (× 365/7) for at least 95% |
| `exp9` food at home | S8B diary: consumed quantities from purchases, own production and gifts, valued at the household's unit value (else the area median) | Median ratio 52.14 (= 365/7); valuation differs slightly from NISR's |
| `exp1` education | Person-level school costs + food at school | Exact for most households |
| `exp2`–`exp5`, `exp10`, `exp11` | One cell each: imputed rent, actual rent, water, electricity, meals away, durables use value | Direct |

3. **Keep only priced, paid-for items in the main basket.** Imputed rent of owner-occupiers (`exp2`) and the use value of durables (`exp11`) are left out. The CPI does not price either, and neither is a cash outlay that rises with prices. The basket covers on average **93.7%** of consumption. 22 households, mostly owner-occupiers with large imputed rents, have less than half their consumption in the basket. The "full basket" scenario puts both items back.

The household's share of cell *c* is s_hc = spending_hc / Σ spending in the basket.

**Survey-period prices.** Shares come from survey-period values (October 2023 to October 2024). EICV7 has no interview dates, so shares cannot be moved to January 2024 prices item by item. The fieldwork mid-point (April 2024) is three months after the base month.

## 3. Prices

Every cell is priced with one **official** NISR index for the household's area: urban households with urban indices, rural households with rural indices. Index values are used exactly as published. The full assignment, with each index's change, is in `docs/expenditure_cpi_mapping.md` section 1. In short:

- **Food.** Published subgroups where they exist: bread and cereals, meat, milk/cheese/eggs, vegetables (including tubers and pulses), non-alcoholic beverages. Other food (fish, fruit, oils, sugar) gets the food division. In urban areas, fresh, local and imported food items get the urban fresh-products, local-food and imported-food indices.
- **Energy** (electricity, gas, kerosene, charcoal, firewood, generator fuel, petrol, diesel): the urban energy index for urban households.
- **Everything else:** its COICOP division.

**Rural fallbacks.** Fresh products, energy, core, local and imported are urban-only indices. For rural households:

| Cell | Urban | Rural fallback | Change, urban → rural |
|---|---|---|---|
| Fresh fish and fruit | fresh products | rural food division | 52.1% → 40.8% |
| Local butter and sugar | local food | rural food division | 37.2% → 40.8% |
| Imported butter and sugar | imported food | rural food division | 24.3% → 40.8% |
| Household energy | energy | rural housing, water, electricity, gas and other fuels | 54.0% → 25.7% |
| Vehicle fuel | energy | rural transport | 54.0% → 71.1% |

- **Core** is not used: it is an aggregate, not a price for specific items.
- **Overall rural CPI** (headline) is the last-resort fallback, but no basket item needs it.
- On average, 14.2% of a rural basket sits in fallback cells (`share_basket_in_rural_fallback_cells`).

**Flagged index months.** Notebook 03 flagged abrupt moves inside the window, kept unchanged here:
- **Rural communication:** +38% in October 2024 and +55% in August 2026. Over the window it rose 113%, against 12% urban.
- **Education:** jumps every September, at the start of the school year.
- **Others:** meat, vegetables, transport, housing, health, urban energy.

On average, 64% of a household's basket is in indices with at least one flagged month (`share_basket_in_flagged_indices`), so flags are common and mostly reflect real price moves. Section 6 tests the most influential series.

## 4. Formulas

For household *h* in area *a* (urban or rural), with Δ_c,a = I_c,a(Sep 2026) / I_c,a(Jan 2024) − 1:

| Output | Formula | Column |
|---|---|---|
| Price change of the household's basket | 100 × Σ_c s_hc Δ_c,a | `price_change_pct` |
| Annualised inflation | 100 × ((1 + price change)^(12/32) − 1) | `annualised_inflation_pct` |
| Category share | Σ_{c∈G} s_hc | `{G}_share_of_basket` |
| Category price change | 100 × Σ_{c∈G} s_hc Δ_c,a / Σ_{c∈G} s_hc; missing if the household spends nothing on G | `{G}_price_change_pct` |
| Category shock | 100 × Σ_{c∈G} s_hc Δ_c,a, percentage points of the total | `{G}_shock_pp` |
| Decomposition | Same as the category shock, over a partition of all cells; the parts sum to `price_change_pct` | `contrib_*_pp` |
| Extra annual cost of the same basket | real consumption (January 2024 prices) × basket share × price change, RWF per year | `extra_cost_same_basket_rwf`, `..._per_ae` |

The categories *G* are:
- **Food:** food and non-alcoholic drinks at home, 9 cells.
- **Energy:** household energy and vehicle fuel.
- **Transport:** vehicle fuel and other transport.
- **Education:** fees and school costs. Uniforms, books, school transport and school meals follow COICOP into clothing, recreation, transport and catering.
- **Communication.**

Energy and transport overlap on vehicle fuel. The decomposition does not: it uses food, energy, transport excluding fuel, education, communication, meals away, and other.

The extra cost is the money needed in September 2026 to buy the household's January 2024 basket. It is not a forecast of actual spending, since households substitute and incomes change.

## 5. Cost-of-Living Distress Score

The score is a transparent ranking device. It has six components, each scaled to 0–1 with 1 meaning more distress, averaged with **equal weights**, and multiplied by 100.

| Component | Column | Definition | Why |
|---|---|---|---|
| Inflation | `c_inflation` | `price_change_pct` scaled linearly between the weighted 5th (31.2%) and 95th (45.3%) percentiles, clipped to 0–1 | Size of the price shock to the household's own basket |
| Food share | `c_food_share` | `share_food` (food at home ÷ consumption), scaled the same way | Engel's law: households spending most on food have the least room to adjust |
| Poverty vulnerability | `c_poverty` | 1 extreme poor; 0.75 poor; 0.5 near poor (1–1.5 × poverty line); 0.25 at 1.5–2 × line; 0 above | Distance from the poverty line in January 2024 prices |
| Income instability | `c_income_instability` | Mean of three flags: no member in formal work; at least half of employed members mainly in agriculture; any casual, seasonal or daily wage worker | Irregular or seasonal income is harder to raise when prices rise |
| Savings and credit gap | `c_savings_credit_gap` | Mean of three flags: no bank, MFI or SACCO account; no formal loan in the last 12 months; no tontine | Buffers that let a household smooth a price shock |
| No VUP coverage | `c_no_vup` | 1 if no VUP component, 0 if at least one | VUP transfers partly offset the shock |

- **`distress_score`:** 100 × the mean of the six components. **`distress_quintile`:** weighted quintile, 1 lowest, 5 highest.
- **`distress_score_excl_vup` and its quintile:** the same score without the VUP component. Use these to study who VUP reaches. Otherwise VUP households would score lower partly by construction.
- **Equal weights** are a stated choice, not an estimate. In the robustness check, removing any single component keeps the rank correlation at 0.93–0.96, and 79–91% of top-quintile households stay in the top quintile.
- **Relative scaling.** The inflation and food-share components are scaled to this sample's distribution. A score compares households within EICV7; it is not an absolute threshold.
- **Proxies.** EICV7 has no social-security, registration or income-volatility questions, so income instability and access to finance are measured indirectly. VUP covers only the five components in the public files (no asset transfers or skills development).

## 6. Sensitivity

Each scenario changes one choice and leaves the official index values untouched. Results are weighted means of `price_change_pct`, using `weight`.

| Scenario | Rwanda | Urban | Rural | Rural − urban | Poor − non-poor | Rank correlation with main |
|---|---:|---:|---:|---:|---:|---:|
| **Main** | **38.0%** | **38.4%** | **37.9%** | −0.5 | −0.2 | 1.00 |
| Only indices published for both areas | 37.4% | 36.2% | 37.9% | +1.7 | 0.0 | 0.95 |
| Rural energy at the urban energy index | 40.2% | 38.4% | 41.0% | +2.6 | +0.7 | 0.84 |
| Rural communication at the urban index | 37.1% | 38.4% | 36.6% | −1.8 | −0.2 | 0.94 |
| Full basket (imputed rent and durables added) | 37.2% | 37.3% | 37.2% | −0.1 | 0.0 | 0.97 |

How to read it:

- **The national level is robust,** at 37–40% under every scenario.
- **The rural–urban gap is not.** Its sign depends on two index choices:
  - The urban-only energy index (+54%) lifts urban baskets. With only shared indices, rural is higher.
  - Rural energy has no index of its own. Pricing it like urban energy lifts rural by 3 points.
  - Report the rural–urban comparison together with these scenarios.
- **The flagged rural communication series adds about 1.3 points to the rural average.**
- **The poor versus non-poor gap is close to zero under every scenario.**

**Bridge to published headline CPI** (`headline_bridge` in the code; notebook 07, section 2):

| Step | Urban | Rural |
|---|---:|---:|
| Published headline, Jan 2024 → Sep 2026 | 33.4% | 36.2% |
| Published components × CPI (EICV4) weights | 34.4% (+1.0 pp) | 37.8% (+1.6 pp) |
| EICV7 household shares, indices common to both areas | 36.2% (+1.8 pp) | 37.9% (+0.1 pp) |
| Main measure: adds the urban-only indices | 38.4% (+2.1 pp) | 37.9% |

- **Aggregation gap (first step).** The published headline cannot be rebuilt exactly from the published components and weights. Rebuilding the residual food index runs into the same problem (section 7, item 5).
- **Spending-share effect (second step).** It comes mostly from vegetables and meals away (higher EICV7 shares) and is offset by transport, housing and alcohol (lower shares).

## 7. Assumptions and limitations

1. **Fixed basket.** Each household is assumed to buy its 2023/24 basket in both months. Substitution towards cheaper goods is ignored, so the price change is an upper bound on the true cost-of-living change.
2. **One price change per area and cell.** Within an area, all households face the same index change for a given cell, because the CPI is not published by district. Differences between households come from their shares only. District differences reflect what districts buy, not local prices.
3. **Own production is priced like purchases.** For farming households, rising food prices also raise the value of what they grow, so the shock measures the cost of the basket, not the cash needed. `share_food_own_produced` in the master table shows how much this matters: 32% of rural food comes from own production.
4. **Survey-period shares** stand in for January 2024 shares (section 2).
5. **Residual food items** (fish, oils, fruit, sugar) in rural areas use the food division. A residual index cannot be derived exactly, because the published weights do not reproduce the headline index exactly.
6. **Population and weights are those of 2023/24.** No reweighting to 2026.
7. **Imputed rent and durables use value are left out** of the main basket. They are in the full-basket scenario.
8. **No future data and no FinScope.** CPI months after September 2026 are not read, and FinScope is not linked at household level. Both are checked in the notebook.

## 8. Output columns (`household_cpi_shock.parquet`)

| Columns | Content |
|---|---|
| `hhid` … `vup_financial_services` | Identifiers, design (`clust`, `strata_id`), weights and grouping variables copied from the master table |
| `cpi_area` | Index area used (urban or rural) |
| `basket_share_of_consumption` | Basket ÷ `cons1` |
| `price_change_pct`, `annualised_inflation_pct` | Main shock |
| `{food,energy,transport,education,communication}_share_of_basket`, `_price_change_pct`, `_shock_pp` | Category shocks |
| `contrib_*_pp` | Decomposition (sums to `price_change_pct`) |
| `share_basket_in_rural_fallback_cells`, `share_basket_in_flagged_indices` | Quality flags |
| `extra_cost_same_basket_rwf`, `extra_cost_same_basket_rwf_per_ae` | Money cost of the same basket, RWF per year |
| `price_change_pct__{scenario}` | Sensitivity scenarios (section 6) |
| `c_*`, `distress_score`, `distress_quintile`, `distress_score_excl_vup`, `distress_quintile_excl_vup` | Distress score and components |

**Reproduce:** run notebooks 05, 06 and 07 in order. Notebook 07 regenerates `docs/expenditure_cpi_mapping.md` and the figures in `reports/figures/household_shock/`.
