# Model card (draft): Baho Neza poverty vulnerability and VUP coverage-gap models

> **Superseded** by `docs/model_card.md` (final models, 2026-10-17). Kept for the record of the untuned baseline models.

**Status:** draft, 2026-10-17. These are **baseline models without tuning**. They establish whether modelling adds value over simple geographic rules. They are **not approved for operational targeting.**

| | |
|---|---|
| **Notebooks** | `08_modeling_eda`, `09_poverty_vulnerability_model`, `10_vup_gap_model`, `11_model_interpretation` |
| **Code** | `src/models/` (`common.py`, `training.py`, `poverty_model.py`, `vup_gap_model.py`, `interpretation.py`, `plots.py`) |
| **Artifacts** | `models/poverty_vulnerability_pipeline.joblib` and `models/vup_gap_pipeline.joblib`, each with a `.json` metadata file |
| **Results** | `reports/model_results_poverty.csv`, `reports/model_results_vup_gap.csv`, `reports/vup_gap_by_district.csv`, `reports/interpretation/`, `reports/modeling_eda_summary.md` |
| **Environment** | Project `.venv` (kernel "Umuseke (.venv)"): scikit-learn 1.9.1, LightGBM 4.7.0, XGBoost 3.4.1, SHAP 0.54.1, pandas 3.0.3 |

## 1. Summary

1. **The poverty model beats the district baseline by a wide margin.** LightGBM reaches holdout ROC-AUC 0.90 (95% CI 0.89–0.91), against 0.67 for district poverty rates.
   - **At a budget of 20% of households,** it reaches 65% of poor people, against 30% for the baseline.
   - **At the current VUP budget (11.6% of households),** a ranking by the model would reach 46% of poor people at 83% precision. The current VUP allocation reaches 14%, and 31% of its households are poor.
   - **Caveat:** VUP is not designed to target consumption poverty alone (section 10).
2. **VUP coverage of high-need households is only weakly predictable.** Logistic regression reaches holdout ROC-AUC 0.72 (0.65–0.77), against 0.60 for the district baseline. The gain is real but modest.
   - Most variation in who is covered is not explained by household characteristics.
   - About **90% of high-need households (about 596,000 households, 2.5 million people) receive no VUP component.**
3. **"Relatively underserved" high-need profiles** are concentrated in the Eastern Province and urban areas. They are households without elderly members or young children, using charcoal, with an improved floor. In the 20% of high-need households least likely to be covered, 2.9% are covered (vs 18.1% in the top 20%), although they are nearly as poor (68% vs 74% poor).
4. **Fairness.** The poverty model is well calibrated overall. It **under-predicts** poverty for households with a disabled member (−5.0 percentage points, CI −9.1 to −0.3), the Southern Province (−3.3) and heads aged 60+ (−2.2).
   - A single national cut-off reaches a smaller share of the poor in urban areas (56% vs 66% rural) and among heads under 35 (49%).

## 2. Intended use

**Intended**
- **Research and planning:** describe which household profiles are poverty-vulnerable under the 2024–2026 price shock, and which high-need profiles current VUP coverage reaches least.
- **Evidence for decisions:** compare targeting rules (geographic, model-based, current allocation) at a fixed budget.
- **A starting point for a properly validated targeting tool,** after tuning, recalibration and external validation.

**Out of scope**
- **Deciding eligibility for individual households.** No model here should include or exclude a real household from a program.
- **Predicting poverty in 2026.** The target is poverty measured in 2023/24.
- **Use outside the survey without care.** The `full` poverty model needs consumption-module features (expenditure shares, CPI shock, distress score) that do not exist for households outside a consumption survey. Use the PMT-feasible variant (section 6) as the reference for non-survey households.
- **Causal claims.** Neither SHAP values nor coefficients are effects of features on poverty or coverage.

## 3. Data

- **Source.** NISR EICV7 2023/24 cross-section public-use files: 15,054 households, 1,674 clusters, 60 strata. Household master table (notebook 06) and household CPI shock table (notebook 07).
- **Prices.** NISR CPI, January 2024 to September 2026. No later month is used.
- **FinScope** is not used.
- **Weights.**
  - Training uses the household weight `weight`, normalised to mean 1.
  - Household metrics are weighted by `weight`.
  - "Poor people reached" uses `pop_wt`.
  - The development set reproduces the poverty rate: 27.3% of people (27.4% for the full sample).
- **Splits** (`data/processed/model_splits.parquet`):
  - **Final holdout:** one cluster in five, sampled within each stratum (3,022 households, 336 clusters, 54 strata). It is scored once, by models fitted on the development set.
  - **Development:** the remaining 12,032 households, split into 5 cross-validation folds by whole clusters within strata.
  - Households are never split at random.

## 4. Models

| | Poverty vulnerability | VUP coverage gap |
|---|---|---|
| **Population** | All households | High-need households: top quintile of the Cost-of-Living Distress Score **excluding its VUP component** (3,079; 308 VUP recipients) |
| **Target** | `poor` (real consumption per adult equivalent below the poverty line) | `vup_any` (any of the five VUP components in the public files) |
| **Features** | 119: geography (district, urban), demographics, education, program-free employment and income source, private income, ICT and finance, assets, housing, services, expenditure shares, CPI shock, `distress_score_model` | 95: out-of-sample poverty score, CPI shock, demographics, education, program-free income source, private income, assets, housing, services, district, urban |
| **Never used** | Poverty status, consumption levels and aggregates, the welfare ratio, quintiles, the poverty component of the distress score, all VUP, Girinka and public-transfer variables | Every VUP variable, the VUP distress component, the published distress score, finance features (they contain VUP loans), raw employment features (they contain VUP jobs) |
| **Selected model** | LightGBM | Logistic regression |
| **Candidates** | District poverty-rate baseline, logistic regression, random forest, LightGBM, XGBoost | District coverage baseline, logistic regression, random forest, LightGBM |

- **Hyperparameters.** Library defaults for every model. Logistic regression uses `max_iter=5000`. Nothing was tuned.
- **Preprocessing,** inside each scikit-learn Pipeline:
  - median imputation with missing-value indicators;
  - `log1p` for money amounts;
  - standardisation (logistic regression only);
  - one-hot encoding of categorical features.
- **Selection rule** (fixed before results were seen): highest mean fold PR-AUC; among the models within one standard error of it, the simplest.
  - **Poverty:** LightGBM. XGBoost was within one standard error but is more complex; logistic regression was not within it.
  - **VUP:** all three models were within one standard error, so logistic regression.
- **Program-free features.** Notebook 08 found two hidden program signals:
  - 144 households have a member whose main job is in the "VUP" institutional sector (139 of them in VUP);
  - 334 households have VUP Financial Services loans in the credit module.
  - Both models use employment and loan features rebuilt without them.
- **Distress score as a feature.** The poverty model uses `distress_score_model`: inflation, food share, income instability and the savings/credit gap, without the poverty and VUP components.

## 5. Evaluation design

**Metrics** (all survey-weighted):
- ROC-AUC and PR-AUC;
- precision and recall when the top 10/20/30% of weighted households are selected (ties at the cut-off are included fractionally);
- Brier score;
- calibration: slope, intercept, calibration-in-the-large, and decile tables.

**Uncertainty:**
- cross-validation fold means and standard deviations;
- holdout 95% intervals from a cluster bootstrap (500 draws, clusters resampled within strata);
- paired intervals for the difference with the baseline;
- subgroup intervals from 200 bootstrap draws.

## 6. Results: poverty vulnerability

**Holdout** (3,022 households; 95% bootstrap intervals in brackets):

| Model | ROC-AUC | PR-AUC | Precision, top 20% | Poor people reached, top 20% | Brier | Calibration slope |
|---|---:|---:|---:|---:|---:|---:|
| District baseline | 0.669 (0.643–0.694) | 0.345 (0.314–0.375) | 0.356 | 0.303 (0.272–0.337) | 0.169 | 0.91 |
| Logistic regression | 0.893 (0.881–0.906) | 0.737 (0.700–0.770) | 0.701 | 0.652 (0.616–0.683) | 0.108 | 0.88 |
| Random forest | 0.872 | 0.690 | 0.670 | 0.624 | 0.120 | 1.45 |
| **LightGBM (selected)** | **0.901 (0.889–0.912)** | **0.751 (0.720–0.782)** | **0.719 (0.673–0.759)** | **0.649 (0.615–0.685)** | **0.104** | **0.94** |
| XGBoost | 0.899 (0.887–0.911) | 0.757 (0.731–0.783) | 0.715 | 0.649 | 0.107 | 0.68 |

**Gain over the baseline** (LightGBM minus baseline, paired 95% interval):

| Metric | Gain |
|---|---|
| ROC-AUC | +0.21 to +0.26 |
| PR-AUC | +0.37 to +0.44 |
| Poor people reached at 20% | +0.30 to +0.39 |

Every model beats the baseline in every cross-validation fold. The smallest fold gain in ROC-AUC is +0.17.

**Top-k results** (LightGBM, holdout):

| Households selected | Precision | Poor people reached |
|---:|---:|---:|
| Top 10% | 0.85 | 0.42 |
| Top 20% | 0.72 | 0.65 |
| Top 30% | 0.61 | 0.80 |

**Cross-validation** (fold mean ± SD):

| Model | ROC-AUC | PR-AUC |
|---|---|---|
| LightGBM | 0.901 ± 0.010 | 0.744 ± 0.016 |
| District baseline | 0.679 ± 0.017 | 0.351 ± 0.017 |

**At the current VUP budget** (11.6% of holdout households):

| Allocation | Precision | Poor people reached |
|---|---:|---:|
| LightGBM ranking | 0.83 | 0.46 |
| District baseline | 0.37 | 0.18 |
| Current VUP | 0.31 | 0.14 |

**PMT-feasible variant** (no expenditure shares, CPI shock or distress score), holdout:

| Model | ROC-AUC | PR-AUC | Poor people reached, top 20% |
|---|---:|---:|---:|
| Logistic regression | 0.875 | 0.696 | 0.64 |
| LightGBM | 0.871 | 0.685 | 0.62 |

Most of the performance comes from non-consumption characteristics.

## 7. Results: VUP coverage gap

**Holdout** (622 high-need households, 67 recipients; intervals are wide):

| Model | ROC-AUC | PR-AUC | Precision, top 20% | Recall, top 20% | Calibration slope |
|---|---:|---:|---:|---:|---:|
| District baseline | 0.604 (0.526–0.666) | 0.149 (0.099–0.232) | 0.150 | 0.295 | 0.54 |
| **Logistic regression (selected)** | **0.716 (0.654–0.771)** | **0.289 (0.184–0.393)** | **0.189** | **0.371 (0.262–0.513)** | **0.68** |
| Random forest | 0.674 | 0.195 | 0.209 | 0.410 | 0.87 |
| LightGBM | 0.692 | 0.206 | 0.200 | 0.393 | 0.43 |

**Gain over the baseline** (logistic minus baseline, paired 95% interval):

| Metric | Gain |
|---|---|
| ROC-AUC | +0.045 to +0.187 |
| PR-AUC | +0.040 to +0.231 |
| Recall at 20% | −0.069 to +0.262 (not significant) |

- **Cross-validation:** logistic regression 0.679 ± 0.038 ROC-AUC, against 0.610 ± 0.024 for the baseline.
- **Sensitivity** (high need = top two quintiles, 1,199 holdout households):
  - Logistic regression reaches 0.728, LightGBM 0.737 and the baseline 0.648. The conclusions are unchanged.

**How to read it.** The model ranks high-need households by how likely they are to be covered, given their characteristics.
- **Observed coverage** rises from 2.9% (CI 1.6–4.2) in the lowest-predicted fifth to 18.1% (14.8–21.4) in the highest.
- **The lowest fifth:**
  - half are in the Eastern Province and 30% are urban;
  - fewer have a female head (21% vs 39%), an elderly member (9% vs 25%) or a child under 5 (38% vs 58%);
  - they are nearly as poor (68% vs 74% of people poor).
- **Two causes are mixed.** This pattern partly reflects **program design**: Direct Support targets households without labour capacity, and NSDS targets pregnant women and children under two. It also reflects **geographic phasing**. Six of the seven Eastern districts have 1.5–4.6% coverage of high-need households (Kayonza 9.1%), against up to 30% in Nyaruguru.
- **What it measures.** These are coverage differences, not evidence that individual households were wrongly excluded.

## 8. Explainability (SHAP, notebook 11)

**Poverty model, importance by feature group** (household-weighted mean |SHAP| in log-odds):

| Group | Importance |
|---|---:|
| Demographics | 0.76 |
| Expenditure shares | 0.65 |
| Private income | 0.61 |
| Housing | 0.46 |
| Assets | 0.36 |
| Geography | 0.28 |
| Education | 0.21 |
| CPI shock | 0.20 |

- **Top single features:**
  - adult equivalents (household size);
  - transfers sent (sending money signals resources);
  - transport share, improved floor, district, farm income, meals-away share, smartphone ownership, number of key assets.
- **Direction:**
  - poverty risk falls steeply with the head's education and with assets (0–1 assets raise risk, 2+ lower it);
  - it rises with the food share up to about 50% of consumption, then falls;
  - the CPI shock has a U-shaped, compositional relation: very low shocks come from cereal-heavy baskets, high shocks from vegetable- and meat-heavy ones.

**VUP coverage model, by group:**

| Group | Importance |
|---|---:|
| Demographics (dependants, young children, elderly) | 0.60 |
| Geography (district) | 0.53 |
| Employment and income source | 0.48 |
| Housing | 0.46 |
| CPI shock | 0.34 |
| Poverty score | 0.06 |

- **Coverage is barely related to the predicted poverty risk within the high-need group.**
- **Collinearity.** The large single weight on casual wage workers is an artefact: it is offset by the correlated employment counts. Notebook 11 checked that casual work does not proxy Public Works participation. Read this model at group level.

**Local explanations.** Notebook 11 explains 10 holdout households that are high-need, uncovered, and have a poverty risk of at least 0.5 (`reports/interpretation/local_explanations_*.png`).
- **Lower predicted coverage:** charcoal use, an improved floor, district, renting, a low agricultural share.
- **Higher predicted poverty risk:** no transfers sent, a low meals-away share, a low transport share.

## 9. Subgroup performance and fairness

**Poverty model** (holdout, LightGBM). Within-group ROC-AUC is 0.85 (farm wage households) to 0.92 (urban, Kigali, non-farm self-employed).

At a single national top-20% cut-off:

| Group | Poor people selected | Calibration gap, pp |
|---|---:|---:|
| Rural | 66% (63–70) | −1.5 |
| Urban | 56% (46–67) | +0.1 |
| Head under 35 | 49% (40–59) | −0.6 |
| Head 35–59 | 70% (67–73) | −0.8 |
| Head 60+ | 58% (51–67) | **−2.2 (−4.6 to −0.1)** |
| Farm wage households | 78% (73–83) | −2.9 (−6.0 to +0.1) |
| Non-farm self-employed | 51% (28–68) | +1.5 |
| Member with disability | 71% (62–81) | **−5.0 (−9.1 to −0.3)** |
| Southern Province | 64% (58–71) | **−3.3 (−5.5 to −0.8)** |

- **What drives lower selection.** Groups with lower poverty rates get lower selection under a national cut-off, which is a property of the cut-off, not only of the model. Area-specific cut-offs or quotas would change this and should be decided on policy grounds.
- **Under-prediction.** The model under-predicts poverty for households with a disabled member, the Southern Province and older heads. Recalibration by group, or adding disability detail, should be examined before any use.

**VUP coverage model** (out-of-sample, all high-need households).
- Calibration gaps are small: within ±1.6 points for every group with an adequate sample.
- The only interval that excludes zero is for non-poor households, a slight over-prediction (+1.3, CI 0.0 to +2.7).
- The 32 high-need households with no employed member show +4.5, but the interval is very wide (−10.2 to +20.0).
- Within-group ROC-AUC is 0.60–0.75. Groups with fewer than 20 recipients (Kigali, households with no employed member, non-farm self-employed) have no reliable AUC.

## 10. Limitations and risks

1. **The target is 2023/24 consumption poverty, measured after transfers.** VUP and other transfers raise consumption, so recipients can look less poor. This understates need among covered households and biases comparisons with current VUP targeting.
2. **VUP's objectives are wider than consumption poverty.** It targets labour capacity, pregnancy and young children, and uses geographic phasing and socio-economic categories. Comparing the model's precision with current VUP measures consumption-poverty targeting only; it does not evaluate the program.
3. **Consumption-derived features** make the `full` poverty model unusable outside a consumption survey. The PMT-feasible variant costs about 0.03 ROC-AUC.
4. **Self-reported, gameable features.** Transfers sent and other private income are self-reported. In an operational setting, applicants could change their answers to these questions to look poorer.
5. **The coverage model has small samples.** There are 67 holdout recipients, so intervals are wide and many subgroups cannot be assessed. The selected logistic model's probabilities are too spread out (calibration slope 0.46 out-of-fold, 0.68 on the holdout): use them for ranking only.
6. **No tuning,** and therefore no claim that these are the best achievable models.
7. **SHAP is not causal.** Feature-level attributions are unstable within collinear groups.
8. **District results** rest on about 100 high-need households per district. Do not rank neighbouring districts.
9. **Residual leakage cannot be fully excluded.** VUP-sector jobs and VUP loans were removed, but assets bought with transfers, for example, may still carry traces of participation.
10. **Public files only.** Asset transfers and skills development, the other two VUP components, are not observed.

## 11. Ethical considerations

- **Targeting errors are costly.** At 20% coverage, 28% of selected households are non-poor (inclusion error) and 35% of poor people are missed (exclusion error). Any use should include community validation and an appeals route.
- **Disparities.** The disability and older-head under-prediction (section 9) means a model-only ranking would disadvantage groups that social protection usually prioritises.
- **Privacy.** Household IDs are anonymised survey IDs. The local explanations show district and area only, and outputs contain no names or locations below district.
- **Not a judgement of the program.** The coverage-gap analysis describes coverage. It does not show that VUP mis-targets: program rules not visible in EICV7 drive much of it.

## 12. Next steps

1. **Tuning** of LightGBM and logistic regression, inside the same cluster folds and never touching the holdout. Re-check against the baselines afterwards.
2. **Calibration:** recalibrate the poverty model, overall and by group (disability, older heads, Southern Province). Calibrate the coverage model (e.g. Platt scaling on out-of-fold predictions).
3. **Feature work:**
   - develop the PMT-feasible poverty model as the reference for non-survey use;
   - reduce collinear groups for the logistic model (e.g. drop counts that duplicate shares).
4. **Coverage-gap analysis:** model the components separately (Direct Support, Public Works, NSDS have different eligibility). Test sector-level geography if NISR can provide it.
5. **External validation:** against the EICV7 VUP thematic survey, or administrative VUP data if available.
6. **Uncertainty:** report district estimates with small-area methods rather than direct estimates.

## 13. Reproduce

1. Run notebooks 05–07 to build the household tables.
2. Run notebooks 08–11 with the kernel **"Umuseke (.venv)"**:
   - **Notebook 08** writes the split. It is deterministic (seed 2026).
   - **Notebook 09** writes the poverty pipeline and out-of-fold scores, which notebook 10 uses.
   - **Notebook 11** reads both pipelines.
3. Runtime is about 3 minutes for notebook 09, 2.5 minutes for notebook 10, and 1 minute each for notebooks 08 and 11.
4. To load a pipeline:

```python
import json

import joblib
from src.models.common import load_frame
pipe = joblib.load("models/poverty_vulnerability_pipeline.joblib")
frame = load_frame()
cols = json.load(open("models/poverty_vulnerability_pipeline.json"))["feature_columns"]
risk = pipe.predict_proba(frame[cols])[:, 1]
```

The coverage model also needs `poverty_score`, from `data/processed/poverty_scores.parquet`.
