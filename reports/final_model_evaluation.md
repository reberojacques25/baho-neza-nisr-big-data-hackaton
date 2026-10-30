# Final model evaluation (holdout)

Notebook `notebooks/14_final_evaluation.ipynb`, run once on 2026-10-17 (472 seconds). Metrics are in `reports/final_model_metrics.csv`; detail tables are in `reports/final_evaluation/` and charts in `reports/figures/final_evaluation/`.

**How the holdout was used.**
- **Size.** The final holdout is one survey cluster in five, chosen within each stratum: 3,022 households in 336 clusters, of which 622 are high-need.
- **Single pass.** It was scored once, by models fixed in advance from development results (notebook 13, `docs/tuning_decisions.md`).
- **No holdout-driven choices.** No tuning, selection, threshold or calibration step used holdout labels. The holdout results below did not change any choice.
- **Disclosure.** Notebooks 09–11 had scored the *default* models on this holdout. No model was selected from those scores. The models evaluated here are new to the holdout.

**Uncertainty.** Cluster bootstrap with 1,000 draws (clusters resampled within strata); differences are paired. Household metrics use `weight`; "poor people reached" uses `pop_wt`.

## Models selected for deployment

| Model | Deployed pipeline | Why (development results, before the holdout) |
|---|---|---|
| **Poverty vulnerability** | **Tuned LightGBM + group recalibration** (`models/poverty_vulnerability_pipeline_final.joblib`) | PR-AUC within one standard error of the best; passes the fairness gate; best calibration by group; simpler than the other survivor |
| **VUP coverage gap** | **Tuned XGBoost + Platt scaling** (`models/vup_gap_pipeline_final.joblib`) | Highest ROC-AUC and the only model family that passed the fairness gate (worst-group recall); Platt scaling corrects its probability scale |

**The holdout confirms both choices are sound, with two caveats:**
1. **Poverty:** the group-recalibrated model is statistically indistinguishable from the best unmitigated model (tuned XGBoost) on every metric. It is chosen for its calibration by group, not for accuracy.
2. **VUP gap:** tuning did not improve on the default logistic regression on this holdout (ROC-AUC 0.714 vs 0.716). Logistic regression remains a credible, more interpretable alternative; the decision is flagged for the programme owner.

## 1. Poverty vulnerability model

**Models compared:**
- **District baseline:** the district poverty rate.
- **Best unmitigated:** tuned XGBoost.
- **Deployed:** tuned LightGBM + group recalibration.
- **Supplementary:** the deployed model's own base before recalibration.

| Metric | District baseline | Unmitigated (XGBoost tuned) | **Deployed (LightGBM tuned + group recal.)** | Deployed − baseline | Deployed − unmitigated |
|---|---:|---:|---:|---|---|
| ROC-AUC | 0.669 (0.645–0.694) | 0.903 (0.891–0.915) | **0.904 (0.891–0.915)** | +0.209 to +0.258 | −0.002 to +0.003 |
| PR-AUC | 0.345 (0.315–0.378) | 0.767 (0.740–0.797) | **0.764 (0.736–0.793)** | +0.385 to +0.449 | −0.011 to +0.004 |
| Brier score | 0.169 | 0.101 | **0.102** | −0.075 to −0.060 | −0.001 to +0.002 |
| Precision, top 10% | 0.373 | 0.874 | **0.863** | +0.429 to +0.560 | −0.029 to +0.014 |
| Poor people reached, top 10% | 0.154 | 0.430 | **0.425** | +0.237 to +0.315 | −0.015 to +0.010 |
| Precision, top 20% | 0.356 | 0.744 | **0.731 (0.686–0.777)** | +0.327 to +0.424 | −0.027 to +0.005 |
| Poor people reached, top 20% | 0.303 | 0.674 | **0.662 (0.633–0.694)** | +0.317 to +0.407 | −0.025 to +0.001 |
| Poor households reached, top 20% | 0.300 | 0.626 | **0.615** | +0.277 to +0.358 | −0.023 to +0.004 |
| Precision, top 30% | 0.374 | 0.613 | **0.615** | +0.207 to +0.277 | −0.010 to +0.015 |
| Poor people reached, top 30% | 0.479 | 0.803 | **0.809** | +0.284 to +0.378 | −0.008 to +0.023 |
| Calibration slope | 0.91 | 0.92 | **0.94** | | |
| Calibration-in-the-large | −0.005 | −0.004 | **−0.000** | | |

- **Large gain over geography.** Both models beat the district baseline by a wide margin: ROC-AUC +0.21 to +0.26, and +0.32 to +0.41 in the share of poor people reached at 20%.
- **No accuracy difference between the two models.** Every paired interval for deployed minus unmitigated includes zero.
- **Recalibration costs no accuracy.** The supplementary base model (tuned LightGBM before recalibration) scores ROC-AUC 0.904 and PR-AUC 0.763. Recalibration changes ROC-AUC by −0.002 to +0.001 and PR-AUC by −0.002 to +0.004.
- **Tuning gain is small.** Against the default LightGBM scored on this holdout in notebook 09 (PR-AUC 0.751), tuning added about 0.013 PR-AUC.

### Confusion matrix (deployed model)

Weighted households (the holdout represents about 666,000 households):

| Decision rule | Selected and poor | Selected, not poor | Not selected, poor | Not selected, not poor | Precision | Recall (households) | Inclusion error | Exclusion error |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Top 20% of households | 97,346 (14.6%) | 35,834 (5.4%) | 60,963 (9.2%) | 471,755 (70.8%) | 0.731 | 0.615 | 0.269 | 0.385 |
| Predicted probability ≥ 0.5 (19.3% selected) | 96,028 (14.4%) | 32,634 (4.9%) | 62,282 (9.4%) | 474,954 (71.3%) | 0.746 | 0.607 | 0.254 | 0.393 |

At a 20% budget, about one in four selected households is not poor, and about four in ten poor households are missed.

### Against the current VUP allocation

At the current VUP budget (11.6% of holdout households):

| Allocation | Precision (share of selected households that are poor) | Poor people reached |
|---|---:|---:|
| District baseline | 0.371 | 0.177 |
| Unmitigated (XGBoost tuned) | 0.843 | 0.476 |
| **Deployed** | **0.842** | **0.475** |
| Current VUP allocation | 0.311 | 0.138 |

VUP also targets labour capacity, pregnancy and young children, and transfers raise measured consumption. This comparison therefore shows how well each rule concentrates on consumption-poor households. **It does not evaluate the programme.**

### Calibration

Deciles of predicted probability: `reports/final_evaluation/poverty_calibration_deciles.csv`.

- All three models track the diagonal closely.
- The deployed model has the best calibration-in-the-large (−0.000) and a slope of 0.94.

### How group recalibration works, and how it changes rankings

The deployed pipeline is `GroupRecalibratedClassifier(base, calibrator)`.

1. **Base score.** The tuned LightGBM, fitted on all development households, gives a poverty score *p*.
2. **Calibrator.** One weighted logistic regression maps *p* to the final score *q*:

   logit(*q*) = 1.082 · logit(*p*) + 0.067 + *c*(disability) + *c*(head-age group) + *c*(province) + *c*(urban/rural)

   It was fitted on the base model's **cross-fitted out-of-fold** development scores, so it never saw a score the base model produced for its own training data.
3. **Fitted group shifts** (log-odds; only differences between levels of the same group matter):

| Group | Log-odds shift | Effect on odds |
|---|---|---|
| Province | Western +0.28, Southern +0.22, Eastern +0.02, Northern −0.15, Kigali −0.31 | Western ×1.33 vs Kigali ×0.73 |
| Member with disability | +0.10 vs −0.04 without | ×1.14 relative |
| Urban / rural | +0.17 / −0.10 | ×1.31 for urban, relative |
| Head age | 60+ +0.06, under 35 +0.03, 35–59 −0.03 | small |

**Effect on rankings** (holdout features only, no labels):
- **Within a group,** the transformation is monotone, so the order of households is unchanged.
- **Between groups,** whole groups move up or down. The rank correlation with the base model's scores is 0.997, and **96.1% of the top-20% selection is unchanged** (3.9% of selected households are swapped).
- **Selection-rate changes at the 20% budget:**
  - up: Western +2.9 points, urban +0.8, disability +0.7, Southern +0.6;
  - down: Northern −2.0, Eastern −1.2, Kigali −0.6.

**Why.** On development data, the base model under-predicted poverty in the Western and Southern provinces and for households with a disabled member, and over-predicted in the Northern Province. The shifts correct these errors on average.

### Subgroup metrics (holdout, deployed model)

National top-20% cut-off; 95% cluster-bootstrap intervals (500 draws). Full tables: `reports/final_evaluation/poverty_subgroup_comparison.csv`.

| Group | Households | Poor people reached at 20% | Mean prediction error, pp (deployed) | Error before recalibration | Unmitigated error | ROC-AUC |
|---|---:|---:|---|---:|---:|---:|
| Member with disability | 200 | 75% (66–85) | −0.7 (−4.8 to +3.6) | −3.1 | −2.0 | 0.90 |
| Head 60+ | 648 | 63% (56–71) | −0.5 (−2.9 to +1.9) | −1.5 | −1.2 | 0.90 |
| Head under 35 | 802 | **51% (42–60)** | +0.0 | −0.2 | −0.4 | 0.89 |
| Southern Province | 781 | 67% (61–74) | −0.8 (−3.2 to +1.9) | −2.6 | −2.4 | 0.88 |
| Western Province | 675 | 75% (69–80) | +2.2 (−0.6 to +4.9) | −0.6 | −0.0 | 0.89 |
| Northern Province | 477 | **48% (37–59)** | −1.1 (−3.8 to +1.5) | +1.1 | +0.5 | 0.91 |
| Kigali City | 396 | 56% (26–81) | +0.2 | +1.4 | +1.0 | 0.91 |
| Urban | 826 | 62% (52–73) | +1.5 (−0.2 to +3.2) | +0.7 | +0.5 | 0.92 |
| Rural | 2,196 | 67% (64–70) | −0.7 | −0.9 | −0.8 | 0.89 |
| Female head | 801 | 66% (60–73) | −0.3 | −0.9 | −0.8 | 0.90 |
| 1-person household | 288 | **15% (0–34)** | +0.4 | +0.4 | −0.1 | 0.83 |
| 2–3 members | 976 | **50% (42–56)** | −1.3 | −1.7 | −1.5 | 0.90 |
| Farm wage income | 514 | 80% (75–85) | −1.1 | −2.2 | −1.9 | 0.85 |
| Non-farm self-employment | 412 | 55% (40–72) | +2.1 (−0.1 to +4.3) | +2.0 | +1.5 | 0.93 |

**Calibration by group.** Every group's calibration interval for the deployed model includes zero on the holdout.

- **Mean |gap| across groups:** 0.59 points, against 0.75 before recalibration and 0.67 for the unmitigated model.
- **Largest |gap|:** 2.2 points, against 3.1 and 2.4.
- **The development gain was larger** (0.11 vs 0.54 points), so expect a smaller benefit on new data.
- **Over-correction.** The Western Province moved from −0.6 to +2.2 points.

**Recall balance is unchanged by recalibration** (recall gap 0.208 vs 0.209 unmitigated).
- **Lowest recall:** one-person households (15%), 2–3 person households (50%), heads under 35 (51%) and the Northern Province (48%).
- **Partly a property of any national cut-off.** These groups have low poverty rates, and within-group ranking is good (AUC 0.83–0.93).

**Policy option, not part of the model: separate urban/rural cut-offs.**
- **How it works.** The budget is split by each area's predicted number of poor people.
- **Effect on the holdout:** urban poor reached rises from 62% to 65%, rural poor reached falls from 67% to 66%, and the national total is unchanged (66.2%).
- **This is the programme owner's decision.**

## 2. VUP coverage-gap model

**Data.** 622 high-need holdout households, 67 of them VUP recipients. Intervals are wide.

| Metric | District coverage baseline | **Deployed (XGBoost tuned + Platt)** | Deployed − baseline |
|---|---:|---:|---|
| ROC-AUC | 0.604 (0.524–0.668) | **0.714 (0.651–0.766)** | +0.050 to +0.181 |
| PR-AUC | 0.149 (0.099–0.227) | **0.234 (0.166–0.321)** | +0.023 to +0.160 |
| Brier score | 0.090 | **0.086** | −0.008 to −0.000 |
| Precision / recall, top 10% | 0.167 / 0.164 | **0.321 / 0.315** | recall +0.051 to +0.246 |
| Precision / recall, top 20% | 0.150 / 0.295 | **0.210 / 0.413** | recall −0.003 to +0.229 |
| Precision / recall, top 30% | 0.137 / 0.405 | **0.183 / 0.541** | recall +0.017 to +0.276 |
| Calibration slope | 0.54 | **1.08** (0.93 before Platt) | |
| Calibration-in-the-large | −0.010 | **−0.006** | |

- **Ranking:** the deployed model ranks coverage better than district geography alone (ROC-AUC and PR-AUC intervals exclude zero). The gain at the 20% cut-off is not statistically significant.
- **Platt scaling** leaves the ranking unchanged (same AUCs) and puts the probabilities on the right scale (slope 1.08).
- **Observed coverage by quintile of predicted coverage:**

| Quintile of predicted coverage | Observed coverage |
|---|---:|
| Q1 (least likely covered) | 2.5% |
| Q2 | 6.8% |
| Q3 | 5.5% |
| Q4 | 15.9% |
| Q5 | 22.0% |

  The profiles predicted to be least covered are in fact rarely covered.
- **Reference:** the default models scored on this holdout in notebook 10:

| Model (default settings) | ROC-AUC | PR-AUC |
|---|---:|---:|
| Logistic regression | 0.716 | 0.289 |
| LightGBM | 0.692 | 0.206 |

  **Tuning did not improve on default logistic regression out of sample.** The deployment choice was made on development results and is kept; the alternative is recorded for the programme owner.
- **Subgroups** (`reports/final_evaluation/vup_subgroups.csv`):
  - **AUC** can be estimated only where a group has 20 or more recipients; 10 of 24 groups qualify (0.67–0.83).
  - **Calibration gaps** mostly include zero. The Northern Province is under-predicted (−7.0 points, interval −14.4 to −0.1, 16 recipients) and female-headed households probably are too (−3.9, interval −8.6 to +0.5).
  - **Do not read these finely.**

## 3. Summary of what the holdout shows

1. **The poverty model ranks households far better than geography.** At a 20% budget it reaches two thirds of poor people, against 30% for district targeting and 14% for the current VUP allocation at its own budget.
2. **Group recalibration is accuracy-neutral and slightly improves calibration by group.** It closes the disability and Southern Province gaps on the holdout, and over-corrects the Western Province a little.
3. **Fairness gaps remain.** Small households, young heads and the Northern Province are reached much less at a national cut-off.
4. **VUP coverage is only moderately predictable** (ROC-AUC 0.71). The model is useful for describing which high-need profiles current coverage reaches least, not for individual decisions.

Full model card: `docs/model_card.md`.
