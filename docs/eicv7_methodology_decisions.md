# EICV7 methodology decisions

This document records what the official EICV7 documentation says about six questions that affect our analysis, and the decision taken for each. Prepared 2026-10-16.

**Rule followed:** every finding is backed by a quotation or a page reference. Where the documents do not answer a question, it is marked **Unresolved**; no assumption has been made to fill the gap. Checks run against our own data files are labelled *Data check* and are kept separate from documentary evidence.

## Summary

| # | Question | Status | Decision in one line |
|---|---|---|---|
| 1 | What does `s9d4q8` measure? | **Resolved** (which quarter is not specified) | NSDS payment received **per quarter**, in RWF. Do not use `s9d4q8a`–`d`. |
| 2 | Exact fieldwork period | **Resolved** for the survey; **unresolved** for each household | 16 October 2023 to 15 October 2024, in 9 cycles. Interview dates are not in the public files. |
| 3 | Conversion to January 2024 prices | **Resolved** | Household-specific Paasche index (`hh_index`); `sol_jan` = `cons1ae` / `hh_index`. Use as delivered. |
| 4 | Official household- or category-level price adjustment | **Partly resolved** | Household-level: yes, to January 2024 only. Category-level: none for EICV7. Updating beyond January 2024: **unresolved**. |
| 5 | Official weights and how to use them | **Resolved** (two documentation gaps) | `weight` for household statistics, `pop_wt` for person statistics, with `clust` and `strata_id` for standard errors. |
| 6 | Restrictions on linking EICV7 and FinScope | **Partly unresolved** | Record-level linkage is prohibited. Whether attaching area-level aggregates counts as a link is **unresolved**, so none will be attached until NISR confirms. |

## Sources

The folder `docs/source_documentation/eicv7/` did not exist and none of the requested documents were found on this machine. The official copies were downloaded from NISR on 2026-10-16. **Please confirm these are the versions you intended.**

| File | Origin | SHA-256 (first 12) |
|---|---|---|
| `eicv7/EICV7_Final_Questionnaire_English.pdf` (74 pp.) | [Microdata catalog 119](https://microdata.statistics.gov.rw/index.php/catalog/119/related_materials), download 1080 | `36c3c6180400` |
| `eicv7/EICV7_Methodological_Note_2025-07.pdf` (56 pp.) | [statistics.gov.rw publication page](https://statistics.gov.rw/statistical-publications/poverty-and-social-protection/eicv7-methodological-notes) | `0d9af0ddb603` |
| `eicv7/EICV7_Methodological_Note_2025-04.pdf` (56 pp.) | Version linked from catalog 119; text identical to July apart from line wrapping | `5005d1edee1b` |
| `eicv7/EICV7_Instruction_Manual_Final_Kinyarwanda.pdf` (143 pp.) | Catalog 119, download 1082. **Kinyarwanda only**; the English translations below are ours, not official. | `cbc8cf4b53f0` |
| `eicv7/EICV7_DDI_Metadata_Documentation_119.pdf` (231 pp.) | Catalog 119, download 1084 | `7cf39ddc9da4` |
| `eicv7/EICV7_Poverty_Profile_2023-24.pdf` (48 pp.) | [statistics.gov.rw EICV7 poverty profile page](https://statistics.gov.rw/data-sources/surveys/EICV/integrated-household-living-conditions-survey-7-eicv-7/eicv7-poverty-profile-report-202324) | `8e711487c011` |
| `eicv7/EICV7_VUP_Thematic_Report.pdf` (56 pp.) | [statistics.gov.rw VUP thematic report page](https://statistics.gov.rw/data-sources/surveys/EICV/integrated-household-living-conditions-survey-7-eicv-7/eicv7-thematic-report-vup-202324) | `0555f6cf02e9` |
| `finscope/FinScope_2024_DDI_Metadata_Documentation_120.pdf` (13 pp.) | Catalog 120 metadata export (extra source, used for question 6) | `7568e6b62058` |
| `nisr_policy/NISR_Microdata_Release_Policy_2025-02.pdf` (22 pp., scanned) | statistics.gov.rw, posted 2025-02 (extra source, used for question 6). The cover reads **"Kigali, August 2012"**. | `e3336a9b0f80` |

**Page references.** References give the PDF page, followed by the page number printed on the document wherever it could be read from the page footer. For example, "MN PDF 40 / p. 38" means page 40 of the PDF file, numbered 38 on the page itself.

**Abbreviations used below:**
- MN: Methodological Note (2025-07)
- PP: Poverty Profile
- QNR: Questionnaire
- IM: Instruction Manual
- DDI: catalog metadata documentation
- VUP-TR: VUP Thematic Report
- MRP: Microdata Release Policy

---

## 1. What does `s9d4q8` in `CS_S9D4_NSDS.dta` measure?

**Status: Resolved.** One detail is not documented: which of the year's quarters the reported amount refers to.

### Evidence found

- **QNR PDF 66 / p. 66, Part D4 "VUP, Nutrition Sensitive Direct Support":**
  - Question 7: "For how many quarters has [NAME] received NSDS payments in the past 12 months? [Put here number of Quarters]"
  - Question 8: "How much was [NAME]'s quarterly benefit? [Put here amount per quarter]"
  - Question 9 asks the delay in days for the last three payments (A, B, C).
  - The questionnaire has no questions 8a–8d.
- **IM PDF 114 / p. 112:** "Ikibazo cya S9D4Q8: Ni amafaranga angahe [IZINA] yahawe ku gihembwe?"
  - Our translation: "Question S9D4Q8: How much money was [NAME] given per quarter?"
  - The guidance continues: "iki kibazo kigamije kumenya umubare w'amafaranga umuntu wo mu rugo yahawe mu gihembwe kimwe mu gihe cy'amezi 12 ashize". Our translation: "this question aims to find out the amount of money the household member received in one quarter during the past 12 months".
- **IM PDF 112 / p. 110** (the programme rate): "Umugenerwabikorwa wa NSDS agenerwa 10,000 Frw buri kwezi, akayahererwa rimwe mu gihembwe amaze kuba 30,500 Frw y'amezi atatu ajyize igihembwe hiyonjyereyeho na 500 Frw ya servisi za banki".
  - Our translation: "An NSDS beneficiary is entitled to 10,000 Frw per month, paid once per quarter, amounting to 30,500 Frw for the three months of the quarter, including an additional 500 Frw for bank services."
- **DDI PDF 43 / p. 43** (variable labels):
  - `s9d4q8` = "amount benefitted from NSDS in first quarter"
  - `s9d4q8a` = "amount benefitted from NSDS in first quarter"
  - `s9d4q8b` = "… in third quarter"
  - `s9d4q8c` = "… in third quarter"
  - `s9d4q8d` = "… in fourth quarter"

  These labels conflict with the questionnaire, and two variables carry the same label ("third quarter").
- *Data check (notebook 04):*
  - `s9d4q8` is filled for all 561 NSDS beneficiary rows; median 30,000 RWF, mean 29,813 RWF. This is consistent with the 30,500 RWF quarterly rate in the manual.
  - `s9d4q8a` is filled for 2 rows; `s9d4q8b`–`d` are empty.

### Decision for our project

- Treat `s9d4q8` as **the NSDS payment received for one quarter** (RWF), following the questionnaire and the instruction manual. The variable label is wrong and will not be used.
- Do **not** use `s9d4q8a`–`s9d4q8d`. They have no questionnaire counterpart, inconsistent labels, and almost no data.
- When an annual figure is needed, compute `s9d4q8 × s9d4q7` and label it a **derived estimate**. It assumes every quarter received paid the reported quarterly amount; the fixed programme rate in IM p. 110 supports this, but the documents do not state it.

### Impact on analysis

- Corrects the "confirm in questionnaire" note in `reports/eicv7_finscope_inventory.md` and `household_table_design.csv`. The NSDS amount is per quarter, not "first quarter".
- NSDS transfers add up to about 4 × 30,000 RWF a year per beneficiary. That is small next to consumption, but material for the poorest households.

---

## 2. What was the exact EICV7 fieldwork period?

**Status: Resolved** for the survey as a whole. **Unresolved** for individual households: their interview dates are not in the public files.

### Evidence found

- **MN PDF 10:** "NISR conducted EICV7 from 16th October 2023 to 15th October 2024. … the 12-month data collection period was structured into 9 cycles, with each cycle further divided into 3 sub-cycles."
- **MN PDF 13 / p. 11:** "data collection for the EICV7 survey commenced on October 16th, 2023, and covered the full year till October 15th, 2024. The data collection period was divided into 9 cycles."
- **DDI PDF 4 / p. 4, "Data Collection Dates":**

  | Cycle | Start | End |
  |---|---|---|
  | 1 | 2023-10-16 | 2023-11-22 |
  | 2 | 2023-11-26 | 2024-01-02 |
  | 3 | 2024-01-06 | 2024-02-12 |
  | 4 | 2024-02-16 | 2024-03-24 |
  | 5 | 2024-03-28 | 2024-05-04 |
  | 6 | 2024-05-08 | 2024-06-14 |
  | 7 | 2024-06-18 | 2024-07-25 |
  | 8 | 2024-07-29 | 2024-09-04 |
  | 9 | 2024-09-08 | 2024-10-15 |

- **PP PDF 12:** "15,054 were successfully interviewed between mid-October 2023 and mid-October 2024."
- The documents disagree on cycle length: "Each cycle spans 36 days" (MN PDF 10) against "9 cycles of about 41 days each" (MN PDF 16 / p. 14). The DDI dates give 38 days per cycle. This has no effect on our analysis.
- **VUP-TR PDF 12:** the separate VUP survey also "spanned 12 months (October 2023 to October 2024)".
- *Data check:* the DDI lists 838 variables for the cross-section files, the same 838 we hold. None records an interview date, month or cycle.

### Decision for our project

- Use **16 October 2023 to 15 October 2024** as the EICV7 reference period.
- Do **not** assign interview months to households. The cycle or date for each household is not in the public data, and guessing it would be an assumption.
- If month-level timing becomes necessary, ask NISR for the cycle of each cluster (`clust`). This is listed as an open request below.

### Impact on analysis

- A household's CPI cannot be matched to its interview month. Price linkage has to use NISR's January 2024 price base (see question 3).
- Seasonality cannot be controlled directly. NISR's `hh_index` already absorbs time-of-interview price differences.

---

## 3. How did NISR convert EICV7 household consumption to January 2024 prices?

**Status: Resolved.**

### Evidence found

- **MN PDF 31 / p. 29:** "Deflation to the prices of January 2024 using household-level Paasche deflators, rather than the regional-level indexes used in EICV5". It adds: "Household-level deflation properly takes into account the differing spending decisions made by each household."
- **MN PDF 39–40 / pp. 37–38, "Deflating to prices of January 2024":**
  - Rationale: "Households were surveyed in different parts of Rwanda at different times of the year. They thus faced different prices, which vary over time and space."
  - Formula (shown as an image on PDF 40; read from the rendered page): u^h ≈ x^h / P^h, with P^h = (Σ_i w_i^h · p_i^0 / p_i^h)^−1.
    - x^h is "the nominal value of household consumption".
    - P^h is "a Paasche price index for each household".
    - w_i^h are "the shares in nominal total consumption of spending on good i".
    - p_i^0 and p_i^h are the prices "in the base period, and at the time and place where the household was interviewed".
  - **Base prices:** "we find the median CPI prices at the district level as of January 2024 (or in a handful of cases, unit values, or administrative prices). We then obtain the population-weighted averages of these medians." The three Kigali districts are treated as one unit, and unit values are used for "about 5% of food costs".
  - **Prices households faced:**
    - Own production is valued at "the price that the household reports it could get if it were to sell".
    - Items consumed but not bought use "district-level median unit values (if there are at least five observations) in the relevant month; or failing that, the regional-level unit values; or the national-level unit values".
    - Otherwise, CPI prices are used.
  - **Coverage:** "Once the index was constructed, it was applied to all nominal spending." "There is a separate price index for each household."
- **PP PDF 20 / p. 18:** "We use national prices in January 2024 as the reference prices."
- **PP PDF 9:** consumption is converted to "January 2024, using household-specific Paasche price indexes."
- **DDI PDF 53 / p. 53:** `hh_index` "Household Index", 15,054 valid cases, range 0.21–2.83, mean 0.9.
- *Data check (notebook 04):*
  - `sol_jan` = `cons1ae` / `hh_index` holds for every household (maximum relative difference 2 × 10⁻⁷).
  - `pov_jan` = 100 × (`sol_jan` < 560,127) holds for every household.

### Decision for our project

- Use NISR's welfare measures exactly as delivered:
  - `sol_jan`: real consumption per adult equivalent, in national January 2024 prices;
  - `cons1 / hh_index`: real household consumption.
- Do not re-deflate EICV7 consumption with the CPI for differences in time or place within the survey period. `hh_index` already does this.
- Express any later price level relative to **January 2024 national prices**, the documented base.

### Impact on analysis

- The CPI join in `household_table_design.csv` (change from January 2024 to September 2026) has the correct anchor month.
- NISR applies **one deflator per household to all spending** (MN p. 38). It gives no separate real values by category. Real category spending can only be nominal category spending ÷ `hh_index`.

---

## 4. Does NISR provide an official household-level or category-level price adjustment method?

**Status: Partly resolved.**

| Aspect | Status |
|---|---|
| Household-level adjustment to January 2024 | Yes: documented method, and `hh_index` is in the data |
| Category-level adjustment for EICV7 | None documented |
| Method for moving EICV7 values beyond January 2024 | **Unresolved**: not addressed in any document reviewed |

### Evidence found

- **Household level:** the Paasche method and `hh_index` described under question 3 (MN pp. 29, 37–38; DDI p. 53).
  - The ingredients of P^h are not published: the shares w_i^h, the local prices p_i^h and the base prices p_i^0. The poverty profile annex gives national January 2024 base prices only for the food poverty basket (PP PDF 43: "lists each item, it's associate national price in the base period (January 2024)").
- **Category level:** the only CPI-component adjustment in the documents concerns **EICV5, not EICV7**. "the EICV5 prices were deflated to January 2024 using the non-food price component of the consumer price index" (MN PDF 49 / p. 47). This was done for the EICV5–EICV7 imputation model.
- **Comparison table, MN PDF 48 / p. 46:**
  - EICV7: "Deflation to get real consumption in prices of January 2024 use consumption weights at the household level".
  - EICV5: "Deflation used a poor-person price index constructed at the level of each of the 5 regions".
- **Updating to later periods:** a search of all seven EICV7 documents for CPI updating, uprating and inflation adjustment found nothing beyond the items above. The poverty profile discusses CPI trends descriptively only (PP PDF 16 / p. 14).
- **Urban definitions differ between EICV7 and the CPI:**
  - EICV7 (MN PDF 48 / p. 46): "After the publication of the 2022 Census, the definition of urban areas was expanded to include urbanizing areas, and using this new standard, 28.4% of the population was urban in 2024."
  - The NISR CPI report (`docs/source_documentation/prices/`, PDF 5): "Urban CPI is calculated based on approximately 1,622 products in twelve urban centres of Rwanda."

### Decision for our project

- Use `hh_index` only as NISR delivered it. Do not attempt to rebuild it.
- Label any household-specific inflation exposure built from CPI categories (EICV7 budget shares × change in CPI categories since January 2024, as in `household_table_design.csv`) a **project method, not an NISR method**. Report it next to a simple alternative: headline CPI change for the household's area.
- Matching EICV7 `ur` to urban or rural CPI is an approximation, because EICV7 "urban" (2022 Census definition) is wider than the 12 urban centres the CPI covers. Report results with national CPI as a sensitivity check.

### Impact on analysis

- Our category-level inflation measures cannot be presented as official. Methods sections must say they are the team's construction.
- Some EICV7 urban households live in places outside the urban CPI's coverage.

---

## 5. What are the official EICV7 survey weights and how should they be used?

**Status: Resolved.** Two gaps remain: no document defines `pop_wt` in words, and none states the variance-estimation method.

### Evidence found

- **Design weights, MN PDF 19:** "The design weights for the households selected for EICV7 are based on the inverse of the overall probabilities of selection, taking into account the probability at each sampling stage." It continues: "this probability simplifies to that of a stratified two-stage sample, where the EAs are selected directly from the 2022 Census frame with PPS. The basic weight … is calculated as the inverse of this probability."
- **Non-response:** the sources disagree.
  - MN PDF 19: "the final weighting procedures may also have an adjustment factor for nonresponse."
  - DDI PDF 5 / p. 5: "all non-interviewed households were successfully replaced during data collection, resulting in exactly nine completed interviews per sample cluster. In this case there is no need to adjust the EICV7 Cross-Sectional Survey weights for non-response."
- **Weights must be used, PP PDF 17:** "Since some households in effect represent more households … than others …, all computations based on the survey data need to use sampling weights."
- **Variables, DDI PDF 53–54:**
  - `weight` "Household Weight": range 48.8–626.7, mean 218.5.
  - `pop_wt` "Population Weight".
  - No text describes `pop_wt` beyond its label.
- **Strata:** DDI PDF 4: "Samples were drawn from each of the country's 30 districts (strata)", with clusters "allocated to urban and rural strata". MN PDF 15 describes the same allocation.
- **Published sampling errors, MN PDF 54 / p. 52 (Appendix 1):** national poverty 27.4, standard error 0.5, 95% interval 26.4–28.4, design effect 1.9. The method used to compute them is not stated.
- **The VUP thematic report uses a different sample:**
  - VUP-TR PDF 12 describes "a large, nationally representative cross-sectional sample of households and the EICV7 VUP Survey, targeting households receiving benefits".
  - VUP-TR PDF 15: "Based on a weighted sample of 3,771 households". The VUP sample has its own weights (MN PDF 24 / p. 22).
- *Data checks:*
  - `pop_wt` = `weight` × `member` for every household.
  - With `pop_wt`, PSU = `clust` and strata = `strata_id`, Taylor-linearised estimation reproduces Appendix 1: poverty 27.37%, standard error 0.50, interval 26.4–28.3, design effect 1.87. Using district-only strata gives the same standard error.
  - With `weight` instead of `pop_wt`, the rate is 23.4%: the share of *households* that are poor.

### Decision for our project

- **Household-level statistics** (share of households, household totals): use `weight`.
- **Person-level statistics** (poverty headcount, population shares, per-capita measures): use `pop_wt`. This is the only weight that reproduces NISR's published 27.4%.
- **Standard errors:** Taylor linearisation with PSU `clust` and strata `strata_id` (60 district × urban/rural strata). Take `strata_id` from any module file; it is missing from the poverty and household files.
- **VUP analysis:** our `CS_S9D*` files belong to the cross-section sample. Our estimates **will not match** the VUP thematic report, which uses the separate VUP sample (catalog 121), and must not be compared with it directly.

### Impact on analysis

- Weight choice changes the headline: 27.4% of people are poor, but 23.4% of households.
- Design-based standard errors are about 1.9 times larger in variance (design effect) than simple random sampling would give. District estimates rest on "about five hundred households" each (PP PDF 34 / p. 32).

---

## 6. Are there any restrictions on linking EICV7 and FinScope data?

**Status: Partly unresolved.**

| Use | Status |
|---|---|
| Record-level linkage | Prohibited under NISR's public-use terms, and impossible anyway (different samples, no shared identifiers) |
| Attaching FinScope area aggregates (district × urban/rural) to EICV7 households | **Unresolved**: no document addresses it |
| Terms that apply to our copies | **Unresolved**: depends on how they were obtained (public-use registration or licence), which is not recorded in the project |

### Evidence found

- **No EICV7 document mentions FinScope** or data linkage. All seven documents were searched for FinScope, link, merge, access conditions, licence and re-identification.
- **The catalog access pages are empty.** The "Data Access" sections for EICV7 (catalogs 119 and 121) and FinScope 2024 (catalog 120) contain no conditions (retrieved 2026-10-16). Both DDI files describe the data as "Edited anonymous dataset for public distribution" (EICV7 DDI PDF 2; FinScope DDI PDF 2).
- **FinScope 2024 producer:** Access to Finance Rwanda (FinScope DDI PDF 8), distributed through the NISR catalog. Universe: "every 16 years old and above resident in selected households"; "Only one individual per selected household was interviewed" (FinScope DDI PDF 7, 9).
- **NISR Microdata Release Policy** (file posted 2025-02; cover dated "Kigali, August 2012"):
  - **Appendix B, public-use terms, term 4 (PDF 9 / p. 9):** "No attempt will be made to produce links among datasets provided by NISR, or among data from the NISR and other datasets that could identify individuals or organizations."
  - **Undertaking item 8 (PDF 15 / p. 16):** "No attempt will be made to produce links among datasets provided by the NISR with other datasets that could identify individuals or organizations." The heading and items 1–4 of this list fall on printed page 15, which is missing from the PDF.
  - **PDF 6 / p. 6:** "Attempts to re-identify respondents are expressly forbidden."
  - **Licensed-data request form, PDF 19:** includes "Data matching — Will you need to merge the dataset with other data? … If YES specify all other datasets that will need to be merged". So under a licence, merging is declared and reviewed.
  - **Contact for access questions, PDF 7 / p. 7:** Director of Statistical Methods, Research and Publication.
- Other NISR catalog entries list the same rule as an access condition, for example catalog 93 (Seasonal Agriculture Survey 2019): "No attempt will be made to produce links among datasets provided by the National Institute of Statistics of Rwanda." These are evidence of NISR's standard terms, not of EICV7-specific terms.
- **The term is ambiguous.** It is unclear whether "that could identify individuals or organizations" qualifies both parts of public-use term 4 or only the second. The documents do not say whether attaching area-level aggregates counts as "producing links".

### Decision for our project

- **No record-level linkage** of EICV7 and FinScope, and no attempt at probabilistic or statistical matching of individual records.
- **Until NISR confirms in writing**, do not add FinScope-derived variables to EICV7 household records. Analyse the two surveys **side by side**, using separately weighted estimates for the same district × urban/rural cells in shared tables.
- Request written clarification from NISR, at the contact on MRP p. 7. Ask:
  1. whether attaching district × urban/rural aggregates from FinScope 2024 to EICV7 records is allowed;
  2. which terms (public-use or licensed) apply to our copies.
- Meet the public-use conditions in every case:
  - aggregate reporting only;
  - no re-identification;
  - no redistribution of the microdata;
  - cite each dataset;
  - send NISR a copy of outputs (MRP Appendix B, terms 1–6).

### Impact on analysis

- The "Financial inclusion (FinScope)" block in `reports/data_inspection/household_table_design.csv` is **on hold**. Financial inclusion at household level must come from EICV7 itself (`S10A`, `S10C`, `s4bq23c`, VUP financial services) until NISR replies.
- Models cannot yet use FinScope variables as household-level predictors. Comparisons between FinScope and EICV7 stay at aggregate level.

---

## Open items and requests to NISR

| # | Item | Why it matters | Who to ask |
|---|---|---|---|
| A | Whether FinScope district × urban/rural aggregates may be attached to EICV7 records, and which terms (public-use or licensed) cover our copies | Unblocks the FinScope block of the household table | NISR, Director of Statistical Methods, Research and Publication (MRP p. 7) |
| B | Interview cycle per cluster (`clust` → cycles 1–9) | Would allow month-level CPI matching and seasonality checks | NISR data dissemination |
| C | Any official method for moving EICV7 consumption beyond January 2024 | Our CPI uplift to September 2026 is a project method until then | NISR poverty unit |
| D | A written definition of `pop_wt`, and the variance method behind Appendix 1 | Documentation gap; our reproduction already matches | NISR |
| E | Whether the S9D4 metadata labels ("first/third/fourth quarter") are errors | Documentation gap; questionnaire and manual already resolve `s9d4q8` | NISR |
| F | Confirm these downloaded documents are the versions the team intended | The folder was empty when the work started | Project team |
