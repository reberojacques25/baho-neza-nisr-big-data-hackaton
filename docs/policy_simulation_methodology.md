# Policy simulation: methodology

**Code:** `src/simulation/policy_simulator.py`. **Notebook:** `notebooks/15_policy_simulation.ipynb`. **Tests:** `tests/test_policy_simulator.py`.

**Outputs:**
- `data/processed/scenario_results.parquet`: the aggregated scenario grid read by the dashboard.
- `reports/policy_simulation_summary.md`

> **What these numbers are.** Decision-support estimates: static, first-round accounting of who a rule would reach and what it would cost, using EICV7 2023/24 households as they were surveyed.
>
> **What they are not.**
> - Estimates of causal poverty reduction.
> - Forecasts of programme outcomes.
> - A tool for selecting or excluding individual beneficiaries.

## 1. Inputs

The simulator reads **precomputed household-level tables only**. It never reads the raw EICV7 `.dta` files.

| Table | Built by | Used for |
|---|---|---|
| `household_master.parquet` | notebook 06 | Geography, weights, poverty status, VUP participation, NSDS payments, livelihood |
| `household_cpi_shock.parquet` | notebook 07 | Distress score, high-need quintile, CPI shock |
| `household_scores.parquet` | `src/models/score_households.py` | **Out-of-sample** model scores (below) |

**Out-of-sample model scores.**
- **Poverty score:** the final poverty model (tuned LightGBM + group recalibration).
  - Development households get cross-fitted out-of-fold scores, including cross-fitted recalibration.
  - Holdout households get scores from the model fitted on the development set.
  - So no household is scored by a model that trained on it, and precision and recall are not inflated.
- **VUP coverage score:** the final VUP coverage-gap model (tuned XGBoost + Platt scaling), for high-need households only. Same construction.

**Weights.** Household totals use `weight`; person totals use `pop_wt`. All totals are national estimates for 2023/24 (3.29 million households, 13.55 million people).

**Definitions:**
- **High-need:** the top quintile of the distress score excluding its VUP component (notebook 07).
- **Uncovered:** receiving no VUP component.
- **Protection gap:** the number (or share) of high-need households that are uncovered.

## 2. Priority order and allocation

Where a scenario selects households, it ranks them by:
1. poverty-model score, highest first;
2. then distress score, highest first;
3. then household ID, so the order is reproducible.

**Allocation** (`allocate`) walks down the ordered list inside an eligible pool, adding household weights until the budget (a number of weighted households) is reached.
- The household that crosses the budget is included **fractionally**, so totals match the budget exactly.
- A fractional household means "a share of the population that household represents". It is a weighting device, not a partial benefit.

## 3. Scenarios

| Scenario | Rule | Outputs |
|---|---|---|
| **1. Coverage expansion** | Add *X* percentage points of all households to VUP **Direct Support**, taken from households with no VUP component (option: from households not yet in Direct Support), in priority order. Each new household receives the assumed quarterly payment. | Households and people added, of which poor; precision (share poor); high-need households reached; uncovered high-need households before and after; Direct Support coverage before and after; additional quarterly and annual (×4) transfer value; breakdown by district × urban/rural |
| **2. Targeting** | Select the top *k* share of all households (10%, 20%, 30%; grid 5–50%) by priority order. | Households and people selected; poor households and people reached; precision; recall (households, people); non-poor selected; poor missed; breakdown by district, urban/rural and main income source (selection rate, precision, recall, share of the selection) |
| **3. Benefit level** | Raise the **NSDS** quarterly payment by *X*% for currently covered NSDS households, using each household's observed quarterly payment (`s9d4q8`). | Covered households and people; current quarterly transfer total; additional quarterly value; additional annual value (4 payments; and observed quarters paid, capped at 4); additional value per household |
| **4. Protection gap** | Rank districts by the number of uncovered high-need households. In the top *n* = 10, newly cover *X*% of each district's high-need households, taken from its uncovered high-need households in priority order and capped at all of them. | District gap table (before and after); households added; uncovered high-need households nationally and in the targeted districts, before and after; additional transfer value |

**Payment assumption: 30,500 RWF per household per quarter.** This is the NSDS programme rate in the EICV7 instruction manual (PDF p. 112, printed p. 110): 10,000 RWF per month, paid quarterly, plus 500 RWF for bank services. The survey's weighted median quarterly payment among NSDS recipients is 30,000 RWF. Transfer values scale linearly with the assumption, which the dashboard lets users change. Coverage expansion uses this NSDS rate as the payment for new Direct Support households, as specified.

## 4. Grid stored for the dashboard

`scenario_grid()` evaluates every scenario on fixed parameter grids. It stores **aggregated results only** (national, district, district × urban/rural, urban/rural, income source), in long format: `scenario`, `parameter`, `parameter_value`, `level`, `group`, `area`, `metric`, `value`, `sample_households`, `label`.

| Scenario | Grid |
|---|---|
| Coverage expansion | +0.5 to +10 percentage points, in steps of 0.5 |
| Targeting | 5% to 50%, in steps of 5 |
| Benefit level | +5% to +100%, in steps of 5. Linear, so the dashboard computes any value exactly. |
| Protection gap | 5% to 100% of high-need households, in steps of 5, for the 10 highest-gap districts |

Transfer values are stored at 30,500 RWF and rescaled linearly in the dashboard.

## 5. Uncertainty

**Method.** Notebook 15 reruns the headline scenarios on 200 cluster-bootstrap samples (clusters resampled within strata), recomputing ranking, budgets and allocation in every draw.

**What the intervals cover.** Survey sampling uncertainty only, not model error beyond what the out-of-sample scores contain, and not assumption error.

**Results:**

| Estimate | Value | 95% interval |
|---|---:|---|
| Targeting at 20%: precision | 72.4% | 70.2–74.3% |
| Targeting at 20%: poor people reached | 67.1% | 65.6–68.6% |
| Coverage +2 points: uncovered high-need households after | 546,800 | 521,500–569,000 |

**District-level results are much less precise.** About 485 sample households, and 100–200 high-need households, per district. Every district output carries its sample size, and the dashboard flags small samples.

## 6. Assumptions and limitations

1. **Static, first-round accounting.** No behavioural response (labour supply, transfers between households), no general-equilibrium or price effects, no change in household composition.
2. **No causal poverty reduction is estimated.** "Poor households reached" counts households that were poor in 2023/24 and would be selected. It does not say they would leave poverty. Transfers are not added to consumption to re-measure poverty, because that would need assumptions about consumption responses that EICV7 cannot support.
3. **2023/24 households, 2026 prices.** The CPI shock (January 2024 to September 2026) informs the distress score, but households and eligibility reflect the survey period.
4. **Model-based priority is not eligibility.** The priority order uses the poverty-model score, which is only a ranking device. In practice, VUP eligibility follows programme rules (categorisation, labour capacity, NSDS criteria) and verification. The model reaches about two thirds of poor people at a 20% budget, so it misses about one third.
5. **Pool definition.** Coverage expansion draws only on households with no VUP component. Expansion that adds Direct Support to households already in other components is a separate option (`pool="no_direct_support"`).
6. **Payment assumption.** The NSDS rate is applied to new Direct Support households as specified. Actual Direct Support payments vary with household size (survey median about 90,000 RWF per year).
7. **District rankings are imprecise.** The protection-gap district list is based on point estimates. Neighbouring ranks are usually not statistically different.
8. **Observed quarters paid** include one implausible value (7 quarters in 12 months), capped at 4.
