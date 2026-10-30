# Fairness diagnostics and mitigation: summary

Notebook `notebooks/12_fairness_analysis.ipynb`; code `src/models/fairness.py`. Run 2026-10-17.

**Data.** Development set only: out-of-fold predictions from the 5 cluster-based folds. The holdout is not used here; it is scored once in notebook 14.

**Groups.** Household with a disabled member, head age group (under 35, 35–59, 60+), province, urban/rural, head's sex, household size band, main income source.

**Metrics per group.**
- ROC-AUC and PR-AUC, for groups with at least 20 positives.
- Recall (people) and precision at a **single national cut-off**: the top 20% of households.
- Selection rate.
- Mean prediction error (predicted − observed) and Brier score.
- 95% cluster-bootstrap intervals, 200 draws.

Group CSVs are in `reports/fairness/`, charts in `reports/figures/fairness/`.

## 1. Baseline diagnostics

### Poverty model (default LightGBM)

Out-of-fold PR-AUC 0.744, ROC-AUC 0.901; 66.5% of poor people reached at a 20% budget.

| Group | Poor people selected at 20% | Mean prediction error (pp) | ROC-AUC |
|---|---:|---:|---:|
| Member with disability | 73.5% | **−2.9** (−5.3 to −0.3) | 0.89 |
| Head 60+ | 61.6% | **−1.4** (−2.7 to −0.3) | 0.88 |
| Head under 35 | **54.1%** | −1.0 | 0.89 |
| Western Province | 69.7% | **−4.1** (−5.6 to −2.7) | 0.89 |
| Southern Province | 69.7% | **−2.3** (−3.6 to −0.8) | 0.90 |
| Northern Province | 59.1% | **+2.0** (+0.7 to +3.4) | 0.87 |
| Kigali City | **53.3%** | +0.6 | 0.94 |
| Urban | 58.3% | **−1.4** (−2.4 to −0.4) | 0.94 |
| Rural | 68.3% | −0.8 | 0.88 |
| Female head / male head | 65.9% / 66.7% | −0.9 / −1.0 | 0.89 / 0.90 |
| 1-person household | **18.5%** (10.5–26.7) | +0.2 | 0.90 |
| 2–3 members | **41.5%** | −1.2 | 0.86 |
| 6–7 members | 74.4% | −1.5 | 0.91 |
| Farm wage income | 82.6% | −0.9 | 0.85 |
| Non-farm self-employment | 54.4% | −0.6 | 0.93 |

- **Male and female heads are treated alike.**
- **Small households have the lowest recall.** A national cut-off reaches few poor people in one- and two-to-three-person households, in Kigali and among young heads. These groups have low poverty rates, and their poverty is measured per adult equivalent. Within-group ranking stays good (AUC 0.85–0.94), so this is largely a property of a single national cut-off.
- **Calibration errors are small but systematic.** The model under-predicts in the Western and Southern provinces, for households with a disabled member and for older heads. It over-predicts in the Northern Province.

### VUP coverage-gap model (default logistic regression, high-need households)

Out-of-fold ROC-AUC 0.678, calibration slope 0.46.

- **Calibration by group.** Gaps are within ±1.7 points for every group except households of 8+ members (+3.7, interval −1.0 to +8.3, 15 recipients).
- **Small samples.** Groups have 20–100 recipients, so subgroup AUCs and recalls are imprecise. Intervals span roughly ±0.1 to ±0.2.
- **Eastern Province:** 19 recipients, too few to estimate a reliable AUC. Its predicted coverage is 5.1% against 3.6% observed.

## 2. Poverty model mitigations

| Approach | PR-AUC (± fold SE) | Recall gap | Worst-group recall | Mean \|calibration gap\| | Max \|gap\| | Calibration slope |
|---|---:|---:|---:|---:|---:|---:|
| Baseline (LightGBM) | 0.744 ± 0.007 | 0.194 | 0.185 | 1.1 pp | 4.1 pp | 0.96 |
| 1 Interaction features | 0.743 ± 0.008 | 0.196 | 0.180 | 1.1 pp | 4.0 pp | 0.96 |
| 2a Subgroup-balanced weights | 0.740 ± 0.006 (fails gate) | 0.193 | **0.118** | 1.1 pp | 4.1 pp | 0.93 |
| 2b Class-balanced weights | 0.746 ± 0.008 | **0.177** | 0.159 | **7.7 pp** | 11.9 pp | 0.94 |
| **3a Group recalibration** | **0.747 ± 0.006** | 0.207 | 0.172 | **0.1 pp** | **1.2 pp** | **0.99** |

Columns:
- **Recall gap:** mean over the 7 dimensions of (highest − lowest) people-recall at the 20% budget.
- **Worst-group recall:** the lowest such recall.
- **Calibration gap:** household-weighted mean |predicted − observed| across groups.

**Policy option 3b: separate urban/rural cut-offs.**

| Cut-off | Urban poor reached | Rural poor reached | All poor people reached | Precision |
|---|---:|---:|---:|---:|
| National | 58.3% | 68.3% | 66.5% | 71.2% |
| Separate | 61.6% | 67.3% | 66.3% | 70.9% |

- **How it works.** The 20% budget is split between areas in proportion to each area's *predicted* number of poor people, so no labels are used.
- **Who decides.** It is a policy choice, not a model property.

**Decision.**
- **Formal outcome: baseline.** The pre-registered rule (PR-AUC within one standard error, then the best mean rank on recall gap, worst-group recall and calibration gap) ranks the **baseline** first.
- **Group recalibration (3a) is the best trade-off on the numbers.**
  - It has the highest PR-AUC and calibration close to perfect by group.
  - Its recall differences from the baseline (−0.013 on both recall indices) are within sampling noise.
  - The rank rule cannot see magnitudes, so it ranked 3a second.
- **The rule was kept, not changed after the fact.** Group recalibration is carried into the final selection in notebook 13. There, the gates use one-standard-error tolerances, so differences within sampling noise are treated as ties.

## 3. Remaining gaps

**Fairness is not solved**, whichever approach is used:
1. **Small households, Kigali and young heads** stay far below the national recall at a 20% national budget: 19–54% vs 66%. Recalibration does not change this. A different selection policy would: separate cut-offs, quotas by household size, or per-capita need measures.
2. **Calibration by province and disability** is corrected by group recalibration *on average*. The recalibration only shifts intercepts, so errors within those groups (for example by disability type or severity) are not addressed. The survey's disability questions are coarse.
3. **The VUP model's subgroup performance cannot be assessed precisely** with 241 development recipients. No fairness mitigation was applied to it. Its overall calibration (slope 0.46) is addressed by recalibration in notebook 13.
4. **Choosing these group variables is itself a policy decision.** Disability, age, sex and location are used as grouping and calibration variables because social-protection programmes monitor them. Whether they may be used in an operational model needs a decision by the programme owner.
