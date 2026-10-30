# Household master table: build summary

Built on 2026-10-16 from the EICV7 public-use files and the deduplicated section 9 files (notebook 05).

- **Output:** `data/processed/household_master.parquet`: 15,054 rows (one per household) × 208 columns, 6 MB
- **Notebook:** `notebooks/06_build_household_master_table.ipynb` (about 1 minute on first run)
- **Code:** `src/features/build_household_master.py`
- **Column definitions:** `docs/household_master_data_dictionary.md`

FinScope is not used. NISR values are kept unchanged (some are renamed); every derived value is a new column.

## 1. Checks

All 16 checks pass.

| Check | Result |
|---|---|
| One row per household; `hhid` unique | pass |
| 15,054 rows | pass |
| Poverty rate weighted by `pop_wt` rounds to **27.4%** | pass (27.37%) |
| Extreme poverty weighted by `pop_wt` rounds to 5.4% | pass (5.44%) |
| `poor` and `extreme_poor` agree with `sol_jan` against the two lines, for every household | pass |
| `pop_wt` = `weight` × household size | pass |
| The 25 expenditure cells sum to `exp1` + … + `exp11` | pass (largest difference 4 × 10⁻⁹ RWF) |
| `cons1` equals `exp1` + … + `exp11` | pass. `cons1` is stored as float32, so it differs by up to 6.39 RWF |
| All 30 districts, 5 provinces and 60 strata present | pass |
| `vup_any` equals "any of the five components" | pass |
| Section 9 totals missing for the 4 version-conflict households | pass |
| No FinScope columns; NSDS amount from `s9d4q8` only | pass |

## 2. Poverty

Weighted by `pop_wt` (share of people) unless stated otherwise.

| | Poor | Extreme poor | Poor, share of households (`weight`) |
|---|---:|---:|---:|
| **Rwanda** | **27.4%** | **5.4%** | 23.4% |
| Rural | 31.6% | 6.4% | 27.4% |
| Urban | 16.7% | 3.1% | 13.7% |

By province, the share of people who are poor is:

| Province | Poor | Extreme poor | Sample households |
|---|---:|---:|---:|
| Kigali City | 9.1% | 1.1% | 1,938 |
| Northern | 20.2% | 3.2% | 2,430 |
| Eastern | 26.8% | 4.5% | 3,401 |
| Southern | 34.7% | 7.4% | 3,885 |
| Western | 37.4% | 9.0% | 3,400 |

The poverty file codes `pov_jan` and `epov_jan` as 0/100, while the module files use 0/1. The master table harmonises both to 0/1 in `poor` and `extreme_poor`, so a weighted mean is a rate.

## 3. District coverage

- **Districts.** All 30 are present, with 484–647 sample households each.
- **District × urban/rural cells.** All 60 are present and match the 60 sampling strata.
- **Smallest cells.** Gakenke urban, Gisagara urban, Kicukiro rural and Nyaruguru urban have 18 households each (two clusters). Estimates for these cells will be imprecise; district-level estimates are fine.

## 4. VUP participation

Weighted shares of households, using `weight`.

| Component | Sample households | All households | Poor households | Non-poor households |
|---|---:|---:|---:|---:|
| Direct Support | 437 | 2.7% | 3.7% | 2.4% |
| Classic Public Works | 389 | 2.4% | 4.4% | 1.8% |
| Expanded Public Works | 334 | 2.1% | 3.2% | 1.7% |
| Nutrition-Sensitive Direct Support (NSDS) | 558 | 3.3% | 4.5% | 2.9% |
| Financial Services (loan approved) | 325 | 2.0% | 1.7% | 2.1% |
| **Any of the five** | **1,888** | **11.5%** | **15.9%** | **10.2%** |

- **How `vup_any` is built.** It uses the five component flags, not `s9d1q1`, which only flags each file's own component. 146 households receive two or three components.
- **Components not covered.** Asset transfers and skills development are part of VUP but not in the public cross-section files.
- **No comparison with the VUP thematic report.** That report uses a separate VUP sample, so its figures are not comparable with these.
- **NSDS amounts** use `s9d4q8`, the quarterly payment (median 30,000 RWF); `s9d4q8a`–`d` are ignored. `vup_nsds_amount_12m_est` multiplies it by the quarters paid (median 60,900 RWF) and is labelled an estimate.
- **Missing Public Works payment totals.** 88 classic and 95 expanded Public Works beneficiaries have no payment total. They are flagged, not imputed.

## 5. Expenditure shares

Each NISR aggregate (`exp1`–`exp11`) is split across 25 price cells in proportion to the household's own item values. The totals stay NISR's. The split rests on the item data reconciling with the aggregates:

| Aggregate | Aggregate ÷ item total (median) | Reconciliation |
|---|---:|---|
| `exp6` annual non-food | 1.000 for all 15,047 households | Exact once 11 items NISR leaves out are excluded: lumpy health costs, dwelling materials, mattresses, irons, musical instruments, security equipment |
| `exp7` monthly non-food | 13.04 (= 365 ÷ 28) | Exact for at least 99% of households |
| `exp8` frequent non-food | 52.14 (= 365 ÷ 7) | Exact for at least 95%; includes own production |
| `exp9` food at home | 52.14 (middle half 51.7–52.6) | Close; NISR's valuation of consumed quantities cannot be reproduced exactly |
| `exp1` education | 1.00 | Exact for most households; 80 households have `exp1` > 0 but no components and take their area's average mix |

Weighted household means, as fractions of consumption:

| Share | Rwanda | Rural | Urban |
|---|---:|---:|---:|
| Food and non-alcoholic drinks at home (`share_food`) | 47.5% | 51.1% | 38.8% |
| NISR food share (`share_food_nisr`: home + away + school) | 60.9% | 63.8% | 53.8% |
| Meals away from home | 10.9% | 9.9% | 13.3% |
| Housing and utilities (incl. imputed rent) | 17.6% | 16.8% | 19.4% |
| Energy (household fuels, electricity, vehicle fuel) | 9.5% | 10.6% | 6.8% |
| Transport | 3.3% | 2.5% | 5.4% |
| Education (CPI definition: fees and school costs) | 1.5% | 1.0% | 2.6% |
| Education (NISR `exp1`: incl. uniforms, books, transport, school food) | 4.3% | 4.1% | 4.8% |
| Communication | 1.4% | 1.2% | 1.8% |
| Own production, as a share of food at home | 25.2% | 32.4% | 7.5% |

The two education shares differ because COICOP, which the CPI follows, puts uniforms under clothing, books under recreation, school transport under transport and school meals under catering. The education price index only covers fees and school costs, so notebook 07 applies it to the narrower share.

## 6. Livelihoods

EICV7's public files have no household income aggregate. `main_livelihood` is therefore an employment-based proxy: the livelihood type held by most employed members, with ties going to the head's type.

| Main livelihood | Rural households | Urban households | Poverty rate (people) |
|---|---:|---:|---:|
| Own farming | 53.6% | 13.8% | 27.5% |
| Farm wage work | 18.9% | 6.2% | **54.0%** |
| Non-farm wage work | 16.8% | 51.2% | 19.0% |
| Non-farm self-employment | 8.4% | 25.2% | 14.7% |
| No employed member | 2.4% | 3.6% | 22.7% |

Other employment measures:
- **Informal work (proxy).** On average, 85% of a household's employed members are in informal work (92.5% rural, 67.5% urban; weighted household mean of `share_employed_informal_proxy`). Formal means a public, mixed or international-NGO employer, or an employee with a permanent or fixed-term contract. EICV7 has no social security or registration question.
- **Agricultural dependence.** In 68.7% of households, at least half of employed members work mainly in agriculture.

## 7. Other indicators

Weighted household shares:

| Indicator | Rwanda | Rural | Urban |
|---|---:|---:|---:|
| Female head | 26.2% | 26.9% | 24.4% |
| Improved drinking water | 89.8% | 86.7% | 97.2% |
| Electricity (grid or solar) | 72.5% | 66.0% | 88.3% |
| Clean cooking fuel | 5.4% | 0.8% | 16.8% |
| Basic sanitation (improved, not shared) | 72.4% | 79.6% | 55.1% |
| Owns a mobile phone | 83.1% | 78.9% | 93.3% |
| Any account or tontine | 95.0% | 94.0% | 97.4% |
| Formal loan | 14.5% | 11.8% | 20.8% |
| Received transfers (remittances) | 58.9% | 58.7% | 59.2% |
| Public support, excluding goods donations | 10.5% | 11.0% | 9.3% |

`any_public_support` leaves out S9E code 10, "government donations of goods" (mosquito nets, buckets, phones). That code reaches 81.2% of households, with a median value of 3,000 RWF; it has its own flag, `received_govt_goods_donation`.

## 8. Missingness

169 of 208 columns are complete. Of the 39 with missing values, most are structural: the question does not apply. Full per-column figures are in the data dictionary.

| Columns | Missing | Reason |
|---|---:|---|
| VUP amounts, months, wages | 96–98% | Non-beneficiaries |
| `minutes_to_*` (8 services) | 6–84% | Asked only for services the household uses or knows; secondary school 84%, health centre 6% |
| `head_informal_proxy` | 7.9% | Head not employed |
| `dependency_ratio` | 5.6% | 841 households with no member aged 15–64. Use `share_dependents`, which is always defined |
| Employment shares, `agriculture_dependent` | 2.6% | 393 households with no employed member |
| `exp11`, `exp_cell_durables_use_value` | 1.7% / 0% | NISR leaves `exp11` blank for 256 households. `cons1` counts it as 0, and so does the cell |
| `share_food_own_produced` | 0.8% | No food diary entries |
| Section 9 totals | 0.03% | The 4 version-conflict households (5 for transfers sent) |

## 9. Flags and limitations

- **`head_age_over_100`.** 11 heads have a reported age above 100. Ages are kept as reported.
- **Livelihood and informality are proxies.** No income aggregate, registration or social-security data exists in the public files.
- **Food valuation.** Diary quantities are valued at the household's own unit value, else the median price of the item in its area. 59 item rows have a quantity but no price, and their value is not counted. Values are used only to split NISR's `exp9`, never as totals.
- **Education.** For 80 households with `exp1` > 0 but no person-level components, `exp1` is split using the average mix of their area.
- **Not in the table.** FinScope (by rule), and wage or business earnings (EICV7 records wage amounts for employees only, in mixed time units).
