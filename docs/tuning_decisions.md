# Tuning and final model selection: decisions

Notebook `notebooks/13_hyperparameter_tuning.ipynb`; code `src/models/tuning.py`, `src/models/fairness.py`. Run 2026-10-17 (36 minutes).

**Outputs**
- `reports/tuning_results.csv`: 22 candidates, with every gate.
- `reports/tuning_trials.csv`: all 201 Optuna trials, with fold scores.
- `reports/tuning_gate_tolerances.json`
- `models/poverty_vulnerability_pipeline_final.joblib` and `models/vup_gap_pipeline_final.joblib`, each with a `.json` metadata file.

## 1. What the holdout was (not) used for

**Selection used only the development set.** Every tuning, mitigation and selection decision used **out-of-fold predictions on the development set**, from the same 5 cluster-based folds as notebooks 09–12.

**Why not holdout performance.** The brief asked for final models to be selected on holdout performance. Doing so would have made the final holdout evaluation optimistic. "Holdout performance" in the rule below is therefore estimated out-of-fold, and the holdout was scored once, after the choice, in notebook 14.

**Disclosure.** Notebooks 09–11 had already scored the *default* models on the holdout and looked at holdout subgroups. No model or setting was chosen from those results. The tuned and recalibrated models were new to the holdout in notebook 14.

## 2. Search setup

| | Poverty model | VUP coverage-gap model |
|---|---|---|
| Primary metric | PR-AUC (weighted, mean over folds) | ROC-AUC (weighted, mean over folds) |
| Population | 12,032 development households | 2,457 high-need development households (241 VUP recipients) |
| Tuned | LightGBM, XGBoost | Logistic regression, LightGBM, XGBoost |
| Budget per study | at most 60 trials and 600 seconds | at most 60 trials; 180 s (logistic), 300 s (trees) |
| Trials completed | LightGBM 19 (time-limited), XGBoost 42 | Logistic 60, LightGBM 20 (time-limited), XGBoost 60 |

- **Sampler:** Optuna TPE, seed 2026.
- **Logging:** every trial is logged with its parameters, fold scores and duration.
- **Search spaces** (`tuning.space`):
  - **LightGBM:** trees 100–1,200, learning rate 0.01–0.2, leaves 8–128, minimum child samples 5–200, row and column subsampling, L1 and L2 penalties.
  - **XGBoost:** trees 100–1,200, learning rate 0.01–0.3, depth 2–9, minimum child weight, subsampling, L2 penalty, gamma.
  - **Logistic regression:** C from 0.001 to 10, L2 (lbfgs) or L1 (liblinear).
- **Training weights:** the household weight, normalised to mean 1, as before.

**Tuning gains** (mean fold score, default → tuned):

| Model | Poverty, PR-AUC | VUP, ROC-AUC |
|---|---|---|
| LightGBM | 0.744 → 0.759 | 0.642 → 0.655 |
| XGBoost | 0.740 → 0.764 | 0.629 → 0.688 |
| Logistic regression | not tuned (0.721 default) | 0.680 → 0.681 |

**Caution.** A tuned model's cross-validation score is optimistic: it is the best of many trials evaluated on the same folds. The one-standard-error rule and the final holdout guard against this.

## 3. Candidates

**22 candidates in total.** For each target, every model family appears as default and as tuned, each with and without recalibration. For the poverty model, logistic regression appears as default only:

| Recalibration | Model | How it works |
|---|---|---|
| **Group recalibration** | Poverty | Platt scaling with group intercepts for disability, head-age group, province and area. Carried forward from notebook 12. |
| **Platt scaling** | VUP | Overall Platt scaling, because the VUP model's probabilities were too spread out. |

In both cases the calibrator is **cross-fitted**: the calibrator for fold *f* is fitted on the other folds' out-of-fold scores.

**Complexity score** (used only to break ties between models that pass all gates):

| Model | Default | Tuned | Recalibration |
|---|---:|---:|---:|
| Logistic regression | 1 | +1 | +0.5 |
| LightGBM | 2 | +1 | +0.5 |
| XGBoost | 2.5 | +1 | +0.5 |

## 4. Selection rule

Applied in order (`tuning.select_final`):

1. **Performance.** Mean fold primary metric ≥ the best minus one fold standard error of the best.
2. **Fairness.** Among those:
   - recall gap ≤ the best + 1 SE;
   - worst-group recall ≥ the best − 1 SE.
3. **Calibration.** Among those:
   - mean absolute group calibration gap ≤ the best + 1 SE;
   - |slope − 1| ≤ the best + max(1 SE, 0.05).
4. **Simplicity.** The simplest survivor wins; ties go to the higher primary metric.

**Revision history.** This is disclosed because it was decided with partial information.
- **Notebook 12** fixed a rank-based rule for choosing a mitigation. Under it, the baseline ranked ahead of group recalibration, even though recalibration cut the calibration gap tenfold for recall changes within noise.
- **First version of this rule.** Before any tuning, I wrote it with fixed tolerances (0.02 on the recall indices, 0.005 on the calibration gap). These were chosen after seeing notebook 12's development results.
- **A 3-trial smoke test** showed those tolerances were smaller than the indices' sampling noise. One candidate was excluded by 0.0008, and the choice then depended on noise.
- **Before the full run,** the tolerances were changed to **one cluster-bootstrap standard error** of each index. The SEs were computed from the default model of each target (100 draws), so every gate means "within one standard error".

**Tolerances used:**

| | Recall gap | Worst-group recall | Mean \|calibration gap\| | Slope distance |
|---|---:|---:|---:|---:|
| Poverty | 0.015 | 0.045 | 0.0026 | 0.05 |
| VUP | 0.037 | 0.085 | 0.0030 | 0.053 |

## 5. Poverty model: decision

| Candidate | PR-AUC (mean ± SE) | Calibration slope | Mean \|group gap\| | Recall gap | Worst-group recall | Gates passed | Complexity |
|---|---|---:|---:|---:|---:|---|---:|
| XGBoost tuned | **0.764 ± 0.007** | 1.00 | 0.55 pp | 0.193 | 0.188 | performance, fairness | 3.5 |
| XGBoost tuned + group recalibration | 0.763 ± 0.007 | 0.99 | **0.08 pp** | 0.197 | 0.188 | all | 4.0 |
| **LightGBM tuned + group recalibration** | **0.760 ± 0.008** | **0.99** | **0.11 pp** | 0.202 | 0.158 | **all** | **3.5** |
| LightGBM tuned | 0.759 ± 0.008 | 1.09 | 0.54 pp | 0.191 | 0.137 | performance | 3.0 |
| LightGBM default + group recalibration | 0.747 ± 0.007 | 0.99 | 0.11 pp | 0.207 | 0.172 | — | 2.5 |
| LightGBM default (notebook 09 model) | 0.744 ± 0.007 | 0.96 | 1.10 pp | 0.194 | 0.185 | — | 2.0 |
| Logistic regression default | 0.721 ± 0.011 | 0.90 | 0.24 pp | 0.208 | 0.243 | — | 1.0 |

**Selected for deployment: LightGBM tuned + group recalibration** (`models/poverty_vulnerability_pipeline_final.joblib`).

**Why:**
- Its PR-AUC (0.760) is within one standard error of the best (0.764 − 0.007 = 0.756).
- It passes the fairness gate (worst-group recall 0.158 ≥ 0.188 − 0.045).
- It has near-zero group calibration error.
- Among the two survivors it is simpler than XGBoost tuned + group recalibration (3.5 vs 4.0).

**Rejected candidates:**
- Untuned models fail the performance gate.
- **Tuned XGBoost without recalibration** has the best PR-AUC but fails the calibration gate: its mean group gap is 0.55 points against 0.08–0.11 for the recalibrated models.
- **Tuned LightGBM without recalibration** fails the fairness gate (worst-group recall 0.137).

**Comparison set for notebook 14** (the same rule applied separately to each set of candidates):

| Role | Model |
|---|---|
| Best unmitigated model | XGBoost tuned |
| Best group-recalibrated model | LightGBM tuned + group recalibration (the deployment model) |

Notebook 14 also scores the deployment model's own base, tuned LightGBM before recalibration, to isolate the effect of recalibration.

**Tuned LightGBM settings:**

| Setting | Value |
|---|---|
| Trees | 1,034 |
| Learning rate | 0.025 |
| Leaves | 8 |
| Minimum child samples | 12 |
| Row subsampling | 0.61 |
| Column subsampling | 0.44 |
| L2 penalty | 0.48 |
| L1 penalty | 0.93 |

These are many small, regularised trees.

### How group recalibration works

The final pipeline is `GroupRecalibratedClassifier(base, calibrator)`.

1. **Base model.** The tuned LightGBM pipeline, fitted on all development households, produces a score *p*.
2. **Calibrator.** One weighted logistic regression, fitted on the base model's **cross-fitted out-of-fold** development scores:

   logit(*q*) = *a* · logit(*p*) + *b* + Σ_g *c_g* · 1[household in group *g*]

   The groups are: member with a disability (yes/no), head age (under 35, 35–59, 60+), province (5) and urban/rural.
3. **Output.** *q* is the deployed poverty-risk score.

**Effect on rankings.**
- **Within a group** (for example rural households in the Western Province with a head aged 35–59 and no disabled member) the transformation is monotone (*a* > 0), so the order of households is unchanged.
- **Between groups,** the intercepts *c_g* move whole groups up or down. This changes who falls inside a national cut-off.
- **This is deliberate.** It corrects systematic under- or over-prediction by group, for example under-prediction in the Western and Southern provinces and for households with a disabled member. It is also a policy-relevant choice, because it uses disability, age and location explicitly.
- **Magnitude.** Notebook 14 reports the fitted coefficients and how much the holdout top-20% selection changes.

## 6. VUP coverage-gap model: decision

| Candidate | ROC-AUC (mean ± SE) | Calibration slope | Mean \|group gap\| | Recall gap | Worst-group recall | Gates passed | Complexity |
|---|---|---:|---:|---:|---:|---|---:|
| **XGBoost tuned + Platt** | **0.688 ± 0.018** | **0.99** | 0.84 pp | 0.119 | **0.290** | **all** | 4.0 |
| XGBoost tuned | 0.688 ± 0.018 | 0.87 | 0.89 pp | 0.126 | 0.255 | performance, fairness | 3.5 |
| Logistic tuned (L1, C = 3.58) | 0.681 ± 0.015 | 0.43 | 0.50 pp | 0.136 | 0.192 | performance | 2.0 |
| Logistic tuned + Platt | 0.681 ± 0.015 | 0.98 | 0.79 pp | 0.130 | 0.192 | performance | 2.5 |
| Logistic default (notebook 10 model) | 0.680 ± 0.016 | 0.46 | 0.51 pp | 0.125 | 0.192 | performance | 1.0 |
| LightGBM tuned | 0.655 ± 0.023 | 0.54 | 3.35 pp | 0.154 | 0.153 | — | 3.0 |

**Selected for deployment: XGBoost tuned + Platt scaling** (`models/vup_gap_pipeline_final.joblib`).

**Why:**
- It has the highest out-of-fold ROC-AUC.
- It is the only model family that passes the fairness gate: worst-group recall 0.290 ≥ 0.290 − 0.085, while the logistic models score 0.192.
- Platt scaling fixes its calibration slope (0.87 → 0.99) without changing its ranking.

**Caveat, flagged for the programme owner.**
- **The choice rests on one noisy index.** Logistic regression is within one standard error on ROC-AUC (0.681 vs 0.688). It was excluded only because its worst-group recall (0.19) is lower than XGBoost's (0.29), a difference of about 1.2 SE. That index rests on 20–30 recipients per group.
- **Evidence of the noise.** XGBoost tuned and XGBoost tuned + Platt rank households almost identically, yet their worst-group recall differs by 0.035, because the cross-fitted calibrators differ by fold.
- **The rule's choice is kept** rather than overridden after the fact.
- **Logistic regression (tuned + Platt) remains a credible, more interpretable alternative.** The VUP model is descriptive (who is relatively underserved), so interpretability weighs heavily there.

**Tuned XGBoost settings:**

| Setting | Value |
|---|---|
| Trees | 381 |
| Learning rate | 0.060 |
| Maximum depth | 8 |
| Minimum child weight | 1.47 |
| Row subsampling | 0.79 |
| Column subsampling | 0.77 |
| L2 penalty | 0.004 |
| Gamma | 4.65 |

The large gamma prunes most splits.

**Platt scaling:** logit(*q*) = *a* · logit(*p*) + *b*, fitted on cross-fitted out-of-fold scores. It is monotone, so the ranking and ROC-AUC are unchanged; only the probability scale changes.

**Poverty-vulnerability feature.** The VUP model's poverty score now comes from the final poverty model: out-of-fold for development households, and the development-fitted final model for holdout households, using features only.

## 7. Fairness mitigations (notebook 12, summary)

| Mitigation tested on the default poverty model | Result |
|---|---|
| 1 Interaction features (disability, head-age, urban interactions) | No change |
| 2a Subgroup-balanced weights | Lower PR-AUC; worst-group recall 0.12 |
| 2b Class-balanced weights | Calibration-in-the-large +7.7 pp |
| 3a Group recalibration | Best PR-AUC, calibration gap 1.1 → 0.1 pp, recall indices −0.013 (within noise) |
| 3b Separate urban/rural cut-offs | Policy option: urban recall 58% → 62%, overall unchanged |

Group recalibration is the only mitigation that reached the final model. Separate urban/rural cut-offs remain a **policy option** for the programme owner; they are not part of the model.

## 8. Not done

- No nested cross-validation (too expensive within the time limits), so tuned cross-validation scores are optimistic. The holdout in notebook 14 gives an unbiased estimate.
- No tuning of the fairness-mitigation settings: calibration groups, weight exponents.
- No threshold optimisation. The models output scores, and the cut-off or budget is a policy decision.
