# Modelling EDA: summary

Notebook `notebooks/08_modeling_eda.ipynb`, run 2026-10-17. Charts are in `reports/figures/modeling_eda/`.

- **Development set only.** Everything below uses the development set. The final holdout was split off first and has not been looked at.
- **Weights.** Poverty rates are shares of people (`pop_wt`). Distress scores and VUP coverage are household-level (`weight`).
- **Intervals.** 95% design-based confidence intervals (strata and clusters).

## 1. Cluster-aware split

Saved in `data/processed/model_splits.parquet` and used by notebooks 09–11.

| | Households | Clusters | Strata | Poverty (people) | VUP coverage (households) | Urban share |
|---|---:|---:|---:|---:|---:|---:|
| Development | 12,032 | 1,338 | 60 | 27.3% | 11.5% | 29.1% |
| Final holdout | 3,022 | 336 | 54 | 27.6% | 11.6% | 30.2% |

- **How clusters are assigned.** Whole survey clusters are allocated within each stratum. One cluster in five goes to the holdout, and the remaining clusters are spread over 5 cross-validation folds (2,357–2,456 households each). Households from the same cluster are never split.
- **Uncovered strata.** Six small strata (2–3 clusters) have no holdout cluster.
- **Balance.** The two parts have the same poverty, VUP and urban profile.

## 2. Poverty and distress by group

| Group | Poor (% of people) | 95% CI | Mean distress score | 95% CI |
|---|---:|---|---:|---|
| **Rwanda (development set)** | **27.3** | | **57.4** | |
| Urban | 17.6 | 15.5–19.7 | 50.3 | 49.3–51.2 |
| Rural | 31.1 | 29.8–32.4 | 60.3 | 59.9–60.6 |
| Own farming | 27.0 | 25.5–28.5 | 60.7 | 60.3–61.1 |
| **Farm wage work** | **53.7** | 50.9–56.5 | **68.2** | 67.6–68.8 |
| Non-farm wage work | 19.4 | 17.5–21.3 | 50.5 | 49.8–51.3 |
| Non-farm self-employment | 15.8 | 13.6–18.0 | 50.1 | 49.3–50.9 |
| No employed member | 23.3 | 17.2–29.4 | 49.0 | 47.6–50.4 |
| Head: no education | 42.3 | 39.6–45.0 | 62.2 | 61.6–62.9 |
| Head: primary | 30.3 | 28.9–31.6 | 60.4 | 60.0–60.7 |
| Head: lower secondary | 13.4 | 10.7–16.1 | 52.4 | 51.4–53.4 |
| Head: upper secondary | 6.8 | 4.6–8.9 | 44.6 | 43.7–45.5 |
| Head: tertiary | 0.0* | – | 34.7 | 34.1–35.4 |
| 1-person household | 6.5 | 5.1–8.0 | 51.7 | 50.7–52.7 |
| 8+ members | 34.3 | 30.5–38.0 | 55.8 | 54.5–57.0 |
| Dependency ratio above 2 | 40.6 | 35.8–45.5 | 61.7 | 60.4–63.0 |
| Female head | 29.9 | 27.8–32.0 | 58.0 | 57.3–58.6 |
| Male head | 26.7 | 25.5–27.8 | 57.1 | 56.7–57.5 |
| 0 key assets | 48.7 | 45.9–51.6 | 65.0 | 64.3–65.8 |
| 4+ key assets | 2.7 | 1.1–4.3 | 39.9 | 38.9–40.9 |
| Any VUP component | 38.0 | 34.9–41.2 | 44.2** | 43.6–44.8 |
| No VUP | 25.9 | 24.8–27.0 | 59.1 | 58.7–59.5 |

\* No poor household with a tertiary-educated head was observed in the development set (640 households).
\*\* The published distress score counts the absence of VUP as distress, so VUP households score lower by construction. Section 6 uses the score without that component.

- **Strongest gradients:** education, assets and livelihood. Farm wage workers stand out on both poverty and distress.
- **Distress tracks poverty,** but less steeply. It also captures the food share, the price shock, income instability and access to finance.
- **Districts.** Poverty ranges from 7.1% to 51.6%, but the median interval is 11.6 points wide. Eight districts' intervals overlap the highest-poverty district (Nyamagabe). **District rankings should not be read finely.** Groups of districts differ; neighbouring districts usually cannot be told apart.

## 3. Correlations and multicollinearity

The candidate poverty-model features are 115 numeric plus 4 categorical.

- **16 pairs have |r| ≥ 0.8.** All are expected by construction:
  - tropical livestock units vs cattle (0.999);
  - each expenditure share vs its CPI shock (transport 0.99, education 0.98, food 0.89, energy 0.83);
  - household size vs adult equivalents (0.96);
  - remittance flag vs amount (0.96);
  - phone ownership measured twice (0.91).
- **26 features have a variance inflation factor above 10.** They are mostly employment counts (informal workers, casual workers, own-farming members) and the share/shock pairs.
- **What this implies:**
  - Predictions are unaffected, and no feature is dropped at this stage (no tuning yet).
  - Logistic-regression coefficients will be unstable within these groups.
  - Tree importance will be split between substitutes.
  - Interpretation (notebook 11) aggregates SHAP values by feature group.

## 4. Single-feature screen

Weighted AUC of each allowed feature on its own, against poverty:

| Rank | Feature | AUC |
|---:|---|---:|
| 1 | Transfers sent (log RWF) | 0.70 |
| 2 | `distress_score_model` (distress without poverty and VUP components) | 0.70 |
| 3 | Transport share | 0.68 |
| 4 | Food share | 0.67 |
| 5 | Number of key assets | 0.67 |
| 6 | Improved floor | 0.66 |
| 7 | Persons per sleeping room | 0.66 |

**No allowed feature exceeds 0.85,** so there is no sign of hidden leakage. For comparison, the excluded variables score:
- welfare ratio, real consumption and `c_poverty`: 1.00 (they define the target);
- extra cost of the basket per adult equivalent: 0.98 (it is scaled by consumption);
- published distress score excluding VUP: 0.84 (it contains `c_poverty`).

## 5. Leakage

The full list, with reasons, is `LEAKAGE` in `src/models/common.py`; `assert_no_leakage` checks every feature set against it.

**Poverty model, excluded:**
- the target and anything that defines it: consumption aggregates and levels, the welfare ratio, quintiles, poverty lines, expenditure-cell amounts, the extra-cost columns;
- the poverty component of the distress score (`c_poverty`), and every distress score that contains it;
- all program variables (VUP, Girinka, public transfers in S9E). Including them would make the model learn current targeting rather than poverty.

**VUP model, excluded:** every VUP variable, the VUP component of the distress score, and the published distress score.

**Hidden VUP signals found and removed:**
- **Employment module.** 118 development households have a member whose main job is in the "VUP" institutional sector, and 115 of them are VUP Public Works participants. These jobs counted as non-farm wage work.
- **Credit module.** 263 development households have a VUP Financial Services loan, which counted as a formal loan.
- **Fix.** Both models use program-free versions of the affected features: employment variables ending `_pf`, loan variables ending `_excl_vup`, and a program-free `distress_score_model`.

**Consumption-derived features.** Expenditure shares, the CPI shock and the distress score come from the same consumption module that defines poverty.
- Shares carry no level information, so they are allowed as specified.
- They would not exist for households that were never surveyed. Notebook 09 therefore also reports a **PMT-feasible** model without them (a proxy means test uses only easily observed characteristics).

## 6. VUP coverage among high-need households

High need is the top quintile of the distress score excluding its VUP component, as defined in notebook 07.

| Need quintile | VUP coverage (households) | 95% CI | Poor (% of people) |
|---|---:|---|---:|
| 1 (lowest need) | 5.7% | 4.7–6.6 | 0.4% |
| 2 | 14.7% | 13.2–16.2 | 8.5% |
| 3 | 13.8% | 12.5–15.1 | 19.8% |
| 4 | 14.1% | 12.7–15.5 | 37.6% |
| **5 (highest need)** | **9.3%** | 8.1–10.4 | 66.9% |

- **Coverage falls in the highest-need quintile,** even though two thirds of its people are poor.
- **Size of the group.** The development set has 2,457 high-need households in 1,001 clusters, of which 241 receive VUP. That is enough to model coverage, but holdout estimates will be noisy.
- **By area and livelihood:**
  - Coverage is 9.7% rural and 7.5% urban. It is 5.9% for non-farm wage households, against about 10% for farming households.
  - Households with no employed member reach 33% (n = 27, wide interval).
  - Poor high-need households are covered more often than non-poor ones (10.7% vs 7.0%).
- **By district.** Coverage of high-need households runs from 0% (Kicukiro, n = 32) to 30% (Nyaruguru, n = 54).
  - Eastern Province districts cluster at the bottom: Ngoma, Kirehe, Gatsibo, Nyagatare, Rwamagana and Bugesera are all at 1–4%.
  - Most district intervals overlap, but the provincial pattern is consistent. District and province will therefore matter in the coverage-gap model.
- **The definition is stable.** A program-free need score agrees with the published one for 99.7% of households (21 leave the top quintile, 22 enter). The published definition is kept, as specified.

## 7. Decisions carried into the models

1. **Splits.** Use the saved cluster split. The holdout is evaluated once, for the selected models only.
2. **Poverty model features (`full` set, 119 features):** geography, demographics, education, program-free employment, private income, ICT/finance, assets, housing, services, expenditure shares, CPI shock and `distress_score_model`. Sensitivity: the same set without consumption-derived features (PMT-feasible).
3. **VUP gap model features:**
   - poverty vulnerability: the out-of-fold score from the poverty model;
   - CPI shock, demographics and education, program-free income source, assets, housing, services, district and urban/rural;
   - no finance features (VUP loans) and no other program variables.
4. **Multicollinearity is kept,** and interpretation is done by feature group.
5. **Reporting.** District-level results are always reported with intervals; small differences are not interpreted.
