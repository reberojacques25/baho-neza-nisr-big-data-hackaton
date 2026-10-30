# EICV7 and FinScope 2024: data inventory and inspection

Inspected 2026-10-15. The inspection is read-only: nothing has been cleaned, recoded, deduplicated or modelled.

- **Notebook:** `notebooks/04_eicv7_finscope_inspection.ipynb` (runs in about 1 minute)
- **Code:** `src/data/survey_inspection.py` (profiling) and `src/data/eicv7_cpi_mapping.py` (expenditure-to-CPI mapping)
- **Detailed outputs:** `reports/data_inspection/`

| Output file | Contents |
|---|---|
| `dataset_inventory.csv` | One row per file: size, rows, unit of analysis, key, duplicates, weights, geography |
| `data_dictionary.csv` | All 3,280 variables: label, type, value labels, topic, missingness, summary statistics |
| `key_variables.csv` | 142 key variables, grouped by the eight focus areas |
| `missingness_by_variable.csv`, `missingness_by_dataset.csv` | Missingness per variable, and missingness bands per file |
| `missingness_conditional.csv` | Missingness of key amounts among eligible respondents only |
| `quality_checks.csv` | 266 checks, each marked pass, warn or info |
| `expenditure_cpi_mapping.csv` | 389 EICV7 expenditure items and variables mapped to CPI series |
| `household_table_design.csv` | Proposed columns for the household analysis table |

## Key findings

1. **The data is in good shape for a household-level table.** All 21 EICV7 files cover the same 15,054 households. `hhid` is unique in the poverty and household files, and person IDs (`hhid` + `pid`) are unique. Weights, clusters and strata are clean. The weighted poverty rate is **27.4%** and extreme poverty **5.4%**, reproduced exactly from `sol_jan` and the poverty line.
2. **Neither survey has an interview date.** EICV7 consumption is already converted to **national January 2024 prices** by a household-specific price index (`sol_jan = cons1ae / hh_index`). CPI data should therefore be joined at the January 2024 base, not by interview month.
3. **Four files repeat rows and must be deduplicated before summing:** other expenditure (`S9C`), other income (`S9E`), transfers out (`S9A`) and transfers in (`S9B`). The same 222 households have their whole item list repeated in `S9C` and `S9E`. A few of the repeated rows carry conflicting amounts.
4. **Several variables do not mean what their labels say.**
   - `s9d1q1` is labelled "beneficiary of any VUP component", but in each VUP file it only flags that file's own component.
   - The poverty flags are coded 0/1 in some module files and 0/100 in the poverty file.
   - The NSDS amount actually filled is `s9d4q8`, not `s9d4q8a`–`d`.
5. **FinScope cannot be matched to EICV7 households.** It is a separate sample: one adult aged 16+ per household. It uses the same province, district and urban/rural codes, so it can be joined as **district × urban/rural indicators**. It covers 59 of the 60 cells; there are no rural Kicukiro respondents.
6. **About 76% of food purchase value maps to a published CPI sub-index** (vegetables, bread and cereals, meat, milk, non-alcoholic beverages). The rest maps to the food division index. EICV7 budget shares differ from the CPI's EICV4 weights, most clearly for food away from home and education.

## 1. Dataset inventory

| Survey | Dataset | File | Rows | Vars | Unit | Unique key |
|---|---|---|---:|---:|---|---|
| EICV7 | poverty | `CS_EICV7_poverty_file.dta` | 15,054 | 32 | household | `hhid` |
| EICV7 | household | `CS_S01_S5_S7_Household.dta` | 15,054 | 112 | household | `hhid` |
| EICV7 | person | `CS_S0_S1_S2_S3_S4_S6A_S6B_S6C_Person.dta` | 62,110 | 157 | person | `hhid` + `pid` |
| EICV7 | credit | `CS_S10A1_A2_credits.dta` | 20,509 | 20 | loan | `hhid` + `s10aq4` |
| EICV7 | durables | `CS_S10B_durables.dta` | 406,458 | 19 | household × 27 items | `hhid` + `s10bq0` |
| EICV7 | savings | `CS_S10C_Savings.dta` | 43,810 | 19 | account | `hhid` + `s10cq3` |
| EICV7 | services | `CS_S5F_access_to_services.dta` | 225,810 | 22 | household × 15 services | `hhid` + `s5fq0` |
| EICV7 | nonfood_annual | `CS_S8A1_Expenditure.dta` | 1,159,158 | 17 | household × 77 items | `hhid` + `s8a1q0` |
| EICV7 | nonfood_monthly | `CS_S8A2_Expenditure.dta` | 978,382 | 17 | household × 65 items | `hhid` + `s8a2q0` |
| EICV7 | nonfood_weekly | `CS_S8A3_Expenditure.dta` | 346,220 | 21 | household × 23 items | `hhid` + `s8a3q0` |
| EICV7 | food | `CS_S8B_Food_Expenditure_Consumption.dta` (1.1 GB) | 2,227,992 | 68 | household × 148 items | `hhid` + `s8bq0` |
| EICV7 | food_away | `CS_S8C_Food_Away_from_home.dta` | 62,110 | 72 | person | `hhid` + `pid` |
| EICV7 | transfers_out | `CS_S9A_transfers_out.dta` | 68,175 | 25 | transfer sent | none (1,292 exact duplicate rows) |
| EICV7 | transfers_in | `CS_S9B_transfers_in.dta` | 33,353 | 22 | transfer received | none (2,670 exact duplicate rows) |
| EICV7 | other_expenditure | `CS_S9C_other_expenditure.dta` | 198,588 | 13 | household × 13 items | none (222 households doubled) |
| EICV7 | vup_direct_support | `CS_S9D1_Direct_Support.dta` | 15,056 | 37 | household (× beneficiary) | `hhid` + `pid` |
| EICV7 | vup_classic_pw | `CS_S9D2_Classic_Public_Work.dta` | 15,054 | 40 | household | `hhid` |
| EICV7 | vup_expanded_pw | `CS_S9D3_Expanded_Public_Work.dta` | 15,055 | 41 | household (× beneficiary) | `hhid` + `pid` |
| EICV7 | vup_nsds | `CS_S9D4_NSDS.dta` | 15,057 | 46 | household (× beneficiary) | `hhid` + `pid` |
| EICV7 | vup_financial_services | `CS_S9D5_Financial_Services.dta` | 15,054 | 23 | household | `hhid` |
| EICV7 | other_income | `CS_S9E_other_income.dta` | 397,176 | 15 | household × 26 sources | none (222 households doubled) |
| FinScope 2024 | finscope | `FinScope 2024 Rwanda.dta` | 13,994 | 2,442 | adult respondent, one per household | `key` |

Every EICV7 module file repeats `hhid`, `clust`, `province`, `district` and `ur`. Most also repeat `strata_id`, `weight`, `quintile` and the poverty flags.

## 2. Identifiers, weights and geography

| Item | EICV7 | FinScope 2024 |
|---|---|---|
| Household ID | `hhid` ([ID withheld]–[ID withheld]). Stored as float32; exact at this range, but cast to int64 before joining. | `key` (1–13,994) |
| Person ID | `pid` (1–16) within `hhid` | Not applicable; one respondent per household |
| Household weight | `weight`. Sums to 3,289,819 households. Constant within each of the 1,674 clusters. | `hh_wt`. Sums to 3,575,491 households. |
| Person weight | `pop_wt` = `weight` × `member`. Sums to 13,549,457 people. | `pop_wt` for adults 16+. Sums to 8,155,637. |
| Design | `clust` (1,674 PSUs, about 9 households each). `strata_id` (60 strata = district × urban/rural) is in the module files but **not** in the poverty or household files. | No PSU or stratum variable |
| Geography | `province` (1–5), `district` (11–57, 30 districts), `ur` (1 urban, 2 rural) | `a1`, `a2`, `a6`, using the same codes |

## 3. Variables by focus area

Full lists are in `key_variables.csv`. Variable names below are EICV7 unless marked FS (FinScope).

| Focus area | Main variables | Notes |
|---|---|---|
| Poverty and consumption | `cons1`, `cons1ae`, `sol_jan`, `hh_index`, `ae`, `member`, `food`, `pov_jan`, `epov_jan`, `poverty`, `quintile`, `Poverty_line` (560,127 RWF), `Extreme_line` (356,432 RWF) | `sol_jan` (real consumption per adult equivalent, January 2024 prices) is NISR's welfare measure. |
| Food expenditure | `exp9` (food at home), `exp10` (food away), `Food_at_school`; item level: `S8B` (148 items over diary visits 2–5: purchases `s8bq4_v*`, own production `s8bq10_v*`, gifts `s8bq12_v*`), `S8C` (meals away, per person) | `food` = `exp9` + `exp10` + `Food_at_school`. |
| Non-food expenditure | `exp1`–`exp8`, `exp11`; item level: `S8A1` (12-month recall), `S8A2` (4 weeks), `S8A3` (7 days, plus own production), `S9C` (taxes, ceremonies; not part of `cons1`) | Rent, water and electricity amounts are also in the household file. |
| VUP and social protection | Direct support `s9d1q2`/`s9d1q4`; classic public works `s9d2q1`/`s9d2q11`; expanded public works `s9d3q1`/`s9d3q10`; NSDS `s9d4q1`/`s9d4q8`; financial services `s9d5q1`/`s9d5q4`; public transfers in `S9E` (codes 1–11, 22); Girinka `s7a2q1`; health insurance `s3q2`/`s3q3` | 1,891 households (11.6% weighted) are in at least one VUP component; 151 are in two or more. |
| Financial inclusion | EICV7: accounts `s10cq4`/`s10cq5`, tontine `s10cq8`, loans `s10aq1`/`s10aq3`/`s10aq6`, mobile money use `s4bq23c`. FS: institution use `qf3_*`/`qf4_*`, bank `k*`, mobile money `f*`, savings `g*`, credit `h*`, insurance `i*`, informal groups `l*`, payments `p*`, financial health `e*` | FinScope has about 1,900 financial-inclusion variables but **no derived access strand** (formal, informal, excluded); it must be built. |
| Income | Earnings from main job `s6bq9a` with unit `s6bq9b` (hour to year); other income `S9E`; remittances received `s9bq8`; transfers sent `s9aq7`; FS: `n1b`, `n11`, `n12` | EICV7 has no full income aggregate and no crop-production module. `S9E` codes 24–26 cover farm receipts. |
| Employment | `s6aq2`–`s6aq12` (activity status), `s6bq1`–`s6bq2` (hours), `s6bq3` (ISCO), `s6bq4` (ISIC), `s6bq7` (status); FS `n4` | |
| Education | `s4aq1`–`s4aq20` (attainment, attendance, spending), `s4bq3`–`s4bq7` (literacy); FS `c4a` | |
| Assets | Durables `S10B` (27 items: count, purchase year, value), livestock `s7aq4a`–`f` | |
| Housing and utilities | Dwelling `s5aq*`, materials `s5dq1`–`3`, water `s5cq1`–`13`, electricity `s5cq14`–`20`, internet `s5cq20a`, cooking `s5cq21`–`23`, sanitation `s5cq24`–`30`; FS `c6`–`c8` | |
| Service access | `S5F`: 15 services × use, travel time, distance and mode; FS `d1*` (distance and time to SACCO, bank, agent) | |

## 4. Data quality

The `quality_checks.csv` file has 183 passes, 66 warnings and 17 info items. These are the issues that change how the data must be handled:

| Issue | Where | Recommended handling |
|---|---|---|
| 222 households have their 13-item list repeated (27 household-items with conflicting amounts) | `S9C` other expenditure | Drop exact duplicates; review the 27 conflicts before summing |
| The same 222 households have their 26-source list repeated (6 conflicts) | `S9E` other income | As above |
| 1,292 and 2,670 exact duplicate rows; up to 99 rows per household | `S9A`, `S9B` transfers | Drop exact duplicates before summing |
| `s9d1q1` ("any VUP component") only flags the file's own component | all 5 VUP files | Build `vup_any` from the five component flags |
| `weight`, `quintile` and poverty flags filled only for VUP beneficiary rows (about 3%) | VUP files | Take these from the poverty file |
| `pov_jan`/`epov_jan` coded 0/1 instead of 0/100 | 9 module files | Use the poverty file; divide by 100 to get 0/1 |
| Poverty status differs from the poverty file for up to 10 households (quintile for 150 in the household file) | module files | Treat the poverty file as the authority |
| NSDS amounts `s9d4q8a`–`d` are almost empty; `s9d4q8` is filled for all 561 beneficiaries | `S9D4` | Use `s9d4q8` with `s9d4q7`; confirm the definition in the questionnaire |
| Payment totals missing for 22.6% (classic public works) and 28.4% (expanded public works) of beneficiaries | `S9D2`, `S9D3` | Impute from months × wage, or flag |
| 7 EICV7 and 122 FinScope variables are completely empty | e.g. `s9bq7`, `s9bq10`, FS multi-select parents | Drop; FinScope multi-select answers are in the `_1`, `_2`, … sub-variables |
| Codes outside the value labels | FS `i9a` (code 0 in 4,302 rows), `f4d_1`–`3` (2,054), `k16b_*` (code 99) | Treat as missing or ask the data provider |
| 19 EICV7 and 75 FinScope variables use labelled don't know or refused codes (e.g. 998 for age) | various | Set to missing before analysis |
| One person aged 117 | person | Check; likely a data-entry error |
| Labels need latin-1 decoding | household and person files | Cosmetic; curly quotes show as `?` |
| School feeding counted in both education (`exp1`) and food | poverty file | Never add `food` and `exp1` together |

Checks that passed: keys in 17 of 21 EICV7 files; household coverage across all files; positive and complete weights; `pop_wt` = `weight` × `member`; clusters nested in districts; one household head per household; `cons1` = sum of `exp1`–`exp11`; `sol_jan` = `cons1ae` / `hh_index`; `pov_jan` reproducible from the poverty line; matching geography codes in FinScope.

## 5. Missingness

Most missingness in these files is by design: questions are skipped when they do not apply. The file-level medians reflect questionnaire structure, not data loss: VUP files 96–98%, food diary 96%, person 69%, FinScope 78%. For real gaps, look at `missingness_conditional.csv`, which measures missingness among eligible respondents only:

| Amount | Eligible | Missing among eligible |
|---|---|---:|
| VUP direct support received (`s9d1q4`) | 439 beneficiary rows | 0.0% |
| Classic public works total (`s9d2q11`) | 389 | 22.6% |
| Expanded public works total (`s9d3q10`) | 335 | 28.4% |
| NSDS amount (`s9d4q8`) | 561 | 0.0% |
| VUP financial services loan (`s9d5q4`) | 325 approved | 3.1% |
| Non-food purchases (`s8a1q3`, `s8a2q3`, `s8a3q3`) | items purchased | 0.0% |

## 6. Recommended household-level analysis table

The proposed table has one row per EICV7 household (15,054 rows), keyed by `hhid` and built on the poverty file. The full column list is in `household_table_design.csv` (52 rows, in 14 blocks).

**Joins**

| Source | Join | Aggregation |
|---|---|---|
| Poverty file | base table | None |
| Household file, VUP classic public works and financial services | 1:1 on `hhid` | None |
| VUP direct support, expanded public works, NSDS | 1:many on `hhid` | Any or sum over beneficiary rows |
| Person, food away | 1:many on `hhid` | Head characteristics (`s1q2 == 1`), counts, shares, any-member flags |
| Item modules (`S8A1`–`S8A3`, `S8B`, `S10B`, `S5F`, `S9E`) | 1:many on `hhid` | Annualise by recall period, then sum by group or pivot wide |
| Credit, savings, transfers | 1:many on `hhid` | Deduplicate, then any, count or sum |
| FinScope | many:1 on `district` × `ur` | `pop_wt`-weighted shares of adults; fall back to district level for rural Kicukiro |
| CPI (`data/processed/cpi_features.parquet`) | many:1 on `ur` → CPI area | Category index changes, January 2024 → September 2026 |

**CPI linkage.** EICV7 has no interview month, so the CPI cannot be matched to interview timing. NISR has already put every household's consumption in national January 2024 prices (`sol_jan`). The recommended approach:

1. Compute each household's budget shares by CPI category, using item-level spending and `expenditure_cpi_mapping.csv`. Scale them to NISR's `exp1`–`exp11` totals.
2. Compute the change in each CPI category from January 2024 to September 2026, for the household's area (urban or rural).
3. Household inflation exposure = Σ share × category change.
4. Optionally, express welfare in September 2026 prices: `sol_jan` × (1 + headline change for the area).

**Analysis rules**
- Use `weight` for household statistics and `pop_wt` for person statistics.
- Use `clust` and `strata_id` for standard errors.
- Never sum `food` and `exp1` together.

## 7. EICV7 expenditure to CPI mapping

`expenditure_cpi_mapping.csv` maps 389 rows:
- 353 item codes: 148 food, 77 annual non-food, 65 monthly non-food, 23 weekly non-food, 13 other spending and 27 durables.
- 36 non-item variables: NISR aggregates, education, food away from home, rent and utilities.

**Method.** Each item is assigned a COICOP 1999 group, the classification the Rwanda CPI uses. EICV7 itself uses some COICOP 2018 codes: for example, durables carry 2018 codes, and health insurance moves to division 12 under 1999. The item is then mapped to the most detailed CPI series NISR publishes, using the category names in `src/features/cpi_features.py`.

| Match level | Rows | Meaning |
|---|---:|---|
| subgroup | 90 | A published sub-index covers the item: bread and cereals, meat, milk/cheese/eggs, vegetables (including pulses and tubers), non-alcoholic beverages |
| division | 280 | Only the division index exists, e.g. fish, oils, fruit and sugar fall back to the food division |
| proxy | 7 | The CPI does not price this concept: imputed rent, ceremonies |
| excluded | 7 | Not consumption: taxes, contributions, donations, tithes |
| item level | 5 | NISR aggregates (`exp6`–`exp9`, `exp11`) that must be mapped through their item rows |

`alt_cpi_category` lists closer urban-only NISR indices where they apply: fresh products (50 food items), energy (10), and local or imported goods (18 food items labelled local or imported).

**Food purchase value by CPI series** (survey-weighted purchase values over visits 2–5; not annualised or cleaned, so indicative only): vegetables 40.9%, bread and cereals 22.2%, food division only 21.6%, meat 6.1%, milk/cheese/eggs 3.6%, non-alcoholic beverages 3.0%, alcohol 2.6%.

**EICV7 budget shares compared with CPI weights.** EICV7 shares are weighted aggregate shares of `cons1`. CPI weights are the EICV4 2013/14 basket.

| Component | EICV7 urban | CPI urban | EICV7 rural | CPI rural |
|---|---:|---:|---:|---:|
| Food at home (`exp9`) vs CPI food + alcohol | 30.2% | 32.3% | 49.4% | 56.3% |
| Food away from home (`exp10`) vs restaurants and hotels | 11.2% | 8.8% | 10.8% | 4.6% |
| Education (`exp1`) | 6.9% | 2.7% | 5.2% | 1.4% |
| Rent, water and electricity (`exp2`–`exp5`) vs housing and utilities | 15.9% | 20.8% | 5.6% | 16.4% |

These are not like-for-like. CPI housing also covers cooking fuels, which are in `exp8`, and `exp9` includes own-produced food. Still, the gaps support using **household-specific budget shares** rather than CPI weights when measuring inflation exposure.

**Decisions for the team**
- Fresh products, energy, local goods and imported goods are urban-only indices. Use them for rural households only as a stated assumption.
- Imputed rent (`exp2`) and use value of durables (`exp11`) are not priced by the CPI. Either use the proxies listed in the mapping, or leave them out of inflation exposure.
- Ceremonies in `S9C` are outside `cons1` and are mapped to headline CPI as a proxy. Leave them out unless the analysis needs them.

## 8. Next steps (not done here)

1. Build `src/data/build_household_table.py`, following `household_table_design.csv`. It should deduplicate `S9A`, `S9B`, `S9C` and `S9E`, recode the poverty flags, and set don't know codes to missing.
2. Annualise item-level spending by recall period and reconcile it with `exp6`–`exp9`.
3. Derive FinScope access strands (formal banked, other formal, informal only, excluded) and district × urban/rural indicators.
4. Confirm against the EICV7 questionnaire and methodology report:
   - the NSDS amount definition (`s9d4q8`);
   - the fieldwork period;
   - how `hh_index` is built.
