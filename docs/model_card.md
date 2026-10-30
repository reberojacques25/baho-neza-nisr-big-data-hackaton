# Model card: Baho Neza poverty vulnerability and VUP coverage-gap models

| | |
|---|---|
| **Version** | 1.0, 2026-10-17 (replaces `docs/model_card_draft.md`) |
| **Models** | `models/poverty_vulnerability_pipeline_final.joblib` and `models/vup_gap_pipeline_final.joblib`, each with a `.json` metadata file |
| **Code** | `src/models/` (`common.py`, `training.py`, `tuning.py`, `fairness.py`, `poverty_model.py`, `vup_gap_model.py`, `interpretation.py`) |
| **Evidence** | Notebooks 08–14; `reports/final_model_evaluation.md`; `docs/tuning_decisions.md`; `reports/fairness_analysis_summary.md`; `reports/final_model_metrics.csv` |
| **Environment** | `.venv` (kernel "Umuseke (.venv)"), pinned in `requirements.txt` (scikit-learn 1.9.1, LightGBM 4.7.0, XGBoost 3.4.1, Optuna 5.0) |

> **Baho Neza supports prioritisation and verification, not automatic beneficiary selection.** Model scores rank households for attention: who to visit, verify or review first, and where coverage gaps may lie. No household should be enrolled in, or excluded from, a programme on the basis of a model score alone. Every decision about a real household needs eligibility verification, community validation and a route to appeal.

## 1. Purpose

**Poverty vulnerability model.** It estimates each surveyed household's probability of being consumption-poor. Uses:
- rank households for verification or outreach under a fixed budget;
- describe which profiles are most vulnerable under the January 2024 to September 2026 price shock.

**VUP coverage-gap model.** Among high-need households, it estimates how likely a household with a given profile is to receive any VUP component. Uses:
- identify which **high-need profiles current VUP coverage reaches least** ("relatively underserved");
- inform reviews of coverage and outreach.

It describes current coverage. It does not judge eligibility or programme performance.

## 2. Intended users

- Analysts and planners in social-protection programmes (for example LODA and MINALOC teams) and their partners, for **prioritisation, monitoring and planning**.
- Researchers studying poverty, inflation exposure and social-protection coverage in Rwanda.
- The Baho Neza team, as the analytical base for the policy simulator and the public dashboard.

Users need to read survey-weighted estimates and confidence intervals, and to understand the limitations in section 7.

## 3. Data

| | |
|---|---|
| **Source** | NISR EICV7 2023/24 cross-section public-use microdata: 15,054 households, 1,674 clusters, 60 strata |
| **Prices** | NISR CPI, January 2024 to September 2026. No later month is used. |
| **Not used** | FinScope, which is never linked at household level |
| **Derived tables** | `data/processed/household_master.parquet` (notebook 06), `household_cpi_shock.parquet` (notebook 07), deduplicated section 9 files (notebook 05) |
| **Targets** | Poverty: `poor`, real consumption per adult equivalent (January 2024 prices) below the NISR poverty line; 27.4% of people. VUP: `vup_any`, any of the five VUP components in the public files, among high-need households |
| **High-need population** | Top quintile of the Cost-of-Living Distress Score excluding its VUP component: 3,079 households, 308 of them VUP recipients |
| **Split** | Cluster-aware and fixed (`data/processed/model_splits.parquet`). Development: 80%, 12,032 households, 5 cross-validation folds by whole clusters within strata. Final holdout: 20%, 3,022 households, 336 clusters, scored once in notebook 14. |
| **Weights** | Training uses the household `weight`, normalised to mean 1. Household metrics use `weight`; person metrics ("poor people reached") use `pop_wt`. |

## 4. Features

**Poverty model: 119 inputs.**
- Geography: district, urban/rural.
- Demographics: size, composition, dependency, head's age, sex and marital status, disability.
- Education, and program-free employment and income source.
- Private income: remittances, transfers sent, private and farm income.
- ICT and finance: phones, mobile money, accounts, tontines, non-VUP loans.
- Assets, housing and utilities, travel times to services.
- Expenditure shares, the household CPI shock, and `distress_score_model` (the distress score without its poverty and VUP components).

**Never used in the poverty model:**
- poverty status, consumption levels and aggregates, the welfare ratio and quintiles;
- the poverty component of the distress score;
- **all VUP, Girinka and public-transfer variables**, to avoid learning current targeting.

**VUP coverage-gap model: 95 inputs.**
- The out-of-sample poverty score from the final poverty model.
- The CPI shock, demographics and education, program-free income source and private income.
- Assets, housing, services, district and urban/rural.

**Never used in the VUP model:** any VUP variable, the VUP distress component, and finance features (they contain VUP loans).

**Program-free features.** Employment and loan features exclude VUP-sector jobs (144 households) and VUP loans (334 households), which would otherwise leak participation.

**Consumption-derived features.** Expenditure shares, the CPI shock and the distress score require a consumption survey. For households outside the survey, a model without them (the "PMT-feasible" set) loses about 0.03 ROC-AUC (notebook 09).

## 5. Models and selection

| | Poverty vulnerability | VUP coverage gap |
|---|---|---|
| **Deployed model** | Tuned LightGBM + **group recalibration** | Tuned XGBoost + **Platt scaling** |
| **Primary metric** | PR-AUC | ROC-AUC |
| **Selection** | On development out-of-fold results only. The rule (fixed in advance): within one standard error of the best score → fairness gate → calibration gate → simplest survivor. | Same rule |
| **Why selected** | Its PR-AUC (0.760) is within one standard error of the best (0.764); it passes the fairness gate; it has the best calibration by group; it is simpler than the other survivor | Highest ROC-AUC; the only model family that passed the fairness gate (worst-group recall); Platt scaling fixes the probability scale |
| **Credible alternative** | Tuned XGBoost (unmitigated): equal accuracy on the holdout, slightly worse calibration by group | Logistic regression: equal on the holdout (ROC-AUC 0.716 default vs 0.714), more interpretable. Its exclusion rested on a noisy fairness index. **Decision flagged for the programme owner.** |

**Group recalibration (poverty model).** The base LightGBM score *p* is mapped to the final score *q*:

logit(*q*) = 1.082 · logit(*p*) + 0.067 + group intercepts for disability, head-age group, province and urban/rural

- **Fitting.** The calibrator is fitted on cross-fitted out-of-fold development scores.
- **Ranking.** It preserves the ranking within each group and shifts groups relative to each other. On the holdout, 96% of a top-20% selection is unchanged, and the rank correlation with the base model is 0.997.
- **Purpose.** It corrects systematic under-prediction (Western and Southern provinces, households with a disabled member) and over-prediction (Northern Province).
- **Policy choice.** Using these group variables is a policy choice for the programme owner.

## 6. Metrics (final holdout, scored once)

95% cluster-bootstrap intervals in brackets.

**Poverty vulnerability model** (3,022 households):

| Metric | District baseline | **Deployed model** | Best unmitigated (XGBoost tuned) |
|---|---:|---:|---:|
| ROC-AUC | 0.669 (0.645–0.694) | **0.904 (0.891–0.915)** | 0.903 |
| PR-AUC | 0.345 (0.315–0.378) | **0.764 (0.736–0.793)** | 0.767 |
| Precision at top 10 / 20 / 30% | 0.37 / 0.36 / 0.37 | **0.86 / 0.73 / 0.62** | 0.87 / 0.74 / 0.61 |
| Poor people reached at top 10 / 20 / 30% | 0.15 / 0.30 / 0.48 | **0.43 / 0.66 / 0.81** | 0.43 / 0.67 / 0.80 |
| Calibration slope / calibration-in-the-large | 0.91 / −0.005 | **0.94 / −0.000** | 0.92 / −0.004 |
| At the current VUP budget (11.6%): precision / poor people reached | 0.37 / 0.18 | **0.84 / 0.48** | 0.84 / 0.48 |

The current VUP allocation scores **0.31 / 0.14** on the same measures. VUP's eligibility rules go beyond consumption poverty, so this is not a programme evaluation.

**Confusion at a 20% budget** (deployed model, weighted households):
- 14.6% selected and poor;
- 5.4% selected but not poor (inclusion error 27%);
- 9.2% poor but not selected (exclusion error 39% of poor households).

**VUP coverage-gap model** (622 high-need holdout households, 67 recipients):

| Metric | District coverage baseline | **Deployed model** |
|---|---:|---:|
| ROC-AUC | 0.604 (0.524–0.668) | **0.714 (0.651–0.766)** |
| PR-AUC | 0.149 (0.099–0.227) | **0.234 (0.166–0.321)** |
| Precision / recall at top 10% | 0.17 / 0.16 | **0.32 / 0.32** |
| Precision / recall at top 20% | 0.15 / 0.30 | **0.21 / 0.41** (gain not significant) |
| Precision / recall at top 30% | 0.14 / 0.41 | **0.18 / 0.54** |
| Calibration slope | 0.54 | **1.08** |
| Observed coverage, lowest to highest fifth of predicted coverage | | **2.5% → 22.0%** |

## 7. Fairness findings

**Groups examined:** disability, head age group, province, urban/rural, head's sex, household size, main income source. The analysis uses development out-of-fold results (notebook 12) and holdout results (notebook 14).

**Mitigations tested on the poverty model:**

| Mitigation | Result |
|---|---|
| Interaction features | No effect |
| Subgroup-balanced weights | Worse |
| Class-balanced weights | Broke calibration |
| **Group recalibration** | **Best: accuracy-neutral, smaller calibration gaps by group** |
| Separate urban/rural cut-offs | A policy option (below), not part of the model |

**What is resolved (on average).**
- On the holdout, every group's calibration interval for the deployed model includes zero.
- The disability gap fell from −3.1 to −0.7 points, the Southern Province gap from −2.6 to −0.8, and head 60+ from −1.5 to −0.5.
- Male- and female-headed households are treated alike: 66% of poor people reached in both groups.

**What is not resolved: fairness is not solved.**
1. **Recall at a single national cut-off is unequal.** At a 20% budget, the share of poor people reached is:
   - one-person households 15% (interval 0–34%);
   - 2–3 person households 50%;
   - heads under 35 51%;
   - Northern Province 48%;
   - against 66% overall and 75–80% for households with a disabled member and farm wage workers.

   Within-group ranking is good (AUC 0.83–0.93), so this mostly reflects low poverty rates in those groups under a national cut-off. Changing it requires a **policy** choice, such as quotas or area-specific cut-offs. Separate urban/rural cut-offs raise urban recall from 62% to 65% with no loss nationally.
2. **Recalibration over-corrects the Western Province slightly** (+2.2 points on the holdout, interval −0.6 to +4.9). The development data suggested a larger calibration gain than the holdout shows.
3. **The VUP model's subgroup performance is imprecise** (20–60 recipients per group). The Northern Province is under-predicted (−7.0 points, interval −14.4 to −0.1).
4. **Using disability, age and location as model inputs** (via recalibration) is a policy decision. It must be approved by the programme owner and reviewed against applicable non-discrimination rules.

## 8. Limitations

1. **2023/24 data.** Poverty is measured in EICV7, after transfers. The model ranks risk at survey time and does not predict 2026 poverty. VUP transfers raise measured consumption, so recipients look less poor.
2. **Consumption-derived features** exist only for surveyed households. Use the PMT-feasible variant for anyone else, and validate it first.
3. **Self-reported and gameable features** (for example transfers sent and private income) could be manipulated if scores affected benefits.
4. **The VUP model is descriptive and only moderately predictive** (ROC-AUC 0.71). VUP's own eligibility rules are not observed: geographic phasing, categorisation, labour capacity, NSDS criteria. So "underserved" partly reflects programme design. Asset transfers and skills development are not in the public files.
5. **Small samples:** 67 holdout recipients, about 100 high-need households per district. District rankings and small subgroups have wide intervals.
6. **Tuning gains were small or nil out of sample.** PR-AUC rose by about 0.013 for the poverty model, and the VUP model showed no gain over default logistic regression. Scores from repeated tuning on the same folds are optimistic.
7. **SHAP and coefficients are not causal.** Correlated features split importance; read importance by feature group (notebook 11).
8. **Prior holdout use.** The default models were scored on the holdout before (notebooks 09–11), but no choice was made from those scores. The final models were scored on it once.
9. **No external validation.** No VUP administrative data or other survey year has been used. Performance may differ in other years or areas.

## 9. Prohibited uses

- **Automatic beneficiary selection or exclusion:** enrolling, removing or denying any household based on a model score without verification and human review.
- **Individual eligibility decisions** of any kind, including sanctions, benefit reductions or recertification.
- **Targeting households outside the survey with the `full` poverty model,** whose consumption-derived features they do not have.
- **Ranking or judging districts, sectors or staff** on the coverage-gap model's predictions, or treating it as evidence of mis-targeting or misconduct.
- **Causal claims** about what reduces poverty or drives coverage.
- **Re-identification.** Do not try to identify surveyed households, or link model outputs to other data about identifiable people. Doing so would breach NISR's microdata terms.
- **Linking to FinScope at household level.**
- **Use after material change** (new survey round, programme redesign, price regime change) without re-validation.

## 10. Maintenance

- **Retraining** is required with each new EICV round. Recalibrate when the poverty line, CPI base or programme rules change.
- **Before operational use:**
  - external validation on administrative data;
  - a decision on group variables and cut-off policy;
  - a fairness review of the selection rule actually used (budget, quotas);
  - a documented appeals process.
- **Owner:** the Baho Neza team. Questions about the underlying data go to NISR.
