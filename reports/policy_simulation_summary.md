# Policy simulation: summary of example scenarios

Notebook `notebooks/15_policy_simulation.ipynb`, run 2026-10-17. Method: `docs/policy_simulation_methodology.md`. Full grid: `data/processed/scenario_results.parquet` (18,100 aggregated rows).

> **Decision-support estimates.** Survey-weighted (households: `weight`; people: `pop_wt`), EICV7 2023/24 households as surveyed, with static first-round accounting.
> - **No causal poverty reduction is claimed.**
> - Model scores support prioritisation and verification, **not automatic beneficiary selection**.
> - Transfer values assume the NSDS rate of 30,500 RWF per household per quarter.

## Baseline (EICV7 2023/24)

| | |
|---|---:|
| Households / people | 3.29 million / 13.55 million |
| Poverty rate (people) | 27.4% |
| VUP coverage, any component (households) | 11.5% |
| Direct Support / NSDS coverage (households) | 2.7% / 3.3% |
| High-need households | 658,000 |
| High-need households with no VUP component | **595,800 (90.5%)** |

## 1. Coverage expansion (VUP Direct Support)

New beneficiaries come from households with no VUP component, prioritised by poverty-model score, then distress score.

| | +1 point | +2 points | +5 points |
|---|---:|---:|---:|
| Households added | 32,900 | 65,800 | 164,500 |
| People added | 209,200 | 402,000 | 946,700 |
| of which poor (people) | 206,800 | 387,100 | 851,600 |
| Share of added households that are poor | 98.9% | 96.0% | 89.5% |
| Direct Support coverage | 2.7% → 3.7% | 2.7% → 4.7% | 2.7% → 7.7% |
| Uncovered high-need households | 595,800 → 570,000 | → 546,800 | → 483,700 |
| Reduction in uncovered high-need | 4.3% | 8.2% | 18.8% |
| Additional transfers per quarter | 1.0 bn RWF | 2.0 bn RWF | 5.0 bn RWF |
| Additional transfers per year (4 quarters) | 4.0 bn RWF | 8.0 bn RWF | 20.1 bn RWF |

- **Uncertainty at +2 points** (95% cluster bootstrap):
  - uncovered high-need households after: 521,500–569,000;
  - share of added households that are poor: 93–98%.
- **Precision falls as coverage grows**, from 99% at +0.5 points to 83% at +10 points: the ranking runs out of the clearest cases.
- **Not all new beneficiaries are high-need.** About three quarters of the added households are; the others are poor but below the high-need cut-off.
- **Districts receiving the most new households at +2 points:** Rubavu, Nyagatare, Nyamagabe, Kamonyi and Kayonza, about 5,000–7,400 households each.

## 2. Targeting budgets

Ranking by out-of-sample poverty-model score:

| | Top 10% | Top 20% | Top 30% |
|---|---:|---:|---:|
| Households selected | 329,000 | 658,000 | 987,000 |
| Poor households reached | 281,400 | 476,600 | 606,100 |
| Precision (selected households that are poor) | 85.5% | 72.4% (70.2–74.3) | 61.4% |
| Poor households reached, % of all poor households | 36.6% | 61.9% | 78.8% |
| Poor people reached, % of all poor people | 42.5% | 67.1% (65.6–68.6) | 82.5% |
| Non-poor households selected | 47,600 | 181,400 | 380,800 |
| Poor households missed | 488,200 | 293,000 | 163,500 |

**Top 20% by group:**

| Group | Selection rate | Precision | Poor people reached |
|---|---:|---:|---:|
| Rural | 23.6% | 72% | 68% |
| Urban | 11.3% | 73% | 65% |
| Farm wage work | 48.3% | 76% | 83% |
| Own farming | 18.2% | 71% | 60% |
| Non-farm wage work | 13.2% | 71% | 65% |
| Non-farm self-employment | 8.8% | 68% | 55% |
| No employed member | 12.4% | 79% | 67% |

**By district:**
- **Most poor households reached:** Rubavu, Nyagatare, Nyamagabe, Rusizi, Kamonyi, Nyamasheke and Nyanza (26,000–34,000 each).
- **Lowest recall:** Gicumbi (41% of poor people), Gakenke and Kirehe (46%) and Gasabo (46%). These districts' poor households score lower than the national cut-off.

## 3. NSDS benefit level

Applies to currently covered NSDS households: 109,000 households, 527,000 people, of whom 184,700 are poor. They currently receive 3.24 bn RWF per quarter, an average of 29,700 RWF each.

| | +10% | +25% | +50% |
|---|---:|---:|---:|
| Additional per household per quarter | 2,970 RWF | 7,420 RWF | 14,840 RWF |
| Additional total per quarter | 0.32 bn RWF | 0.81 bn RWF | 1.62 bn RWF |
| Additional per year (4 quarters) | 1.29 bn RWF | 3.24 bn RWF | 6.47 bn RWF |
| Additional per year (quarters actually paid) | 0.78 bn RWF | 1.96 bn RWF | 3.92 bn RWF |

Households received fewer than four NSDS payments in the year on average, so the second annual estimate is lower.

## 4. Protection gap: the 10 districts with the most uncovered high-need households

| District | High-need households | Uncovered | Gap rate |
|---|---:|---:|---:|
| Kamonyi | 43,900 | 40,900 | 93% |
| Nyagatare | 36,100 | 35,100 | 97% |
| Nyamagabe | 39,300 | 32,800 | 83% |
| Kayonza | 32,600 | 29,700 | 91% |
| Ngoma | 29,000 | 28,500 | 99% |
| Nyanza | 29,300 | 27,200 | 93% |
| Rubavu | 30,200 | 26,900 | 89% |
| Rutsiro | 30,400 | 26,400 | 87% |
| Rwamagana | 25,700 | 25,100 | 98% |
| Gisagara | 26,200 | 23,200 | 89% |

These 10 districts hold 296,000 of the 596,000 uncovered high-need households. The ranking uses point estimates: each district has only 97–207 high-need sample households.

| Scenario: newly cover this share of each targeted district's high-need households | 25% | 50% |
|---|---:|---:|
| Households added | 80,700 (76,800–85,100) | 161,400 |
| Of which poor | 76,900 | 138,100 |
| Uncovered high-need, 10 districts | 295,900 → 215,200 | → 134,500 |
| Uncovered high-need, national | 595,800 → 515,100 (492,000–535,100) | → 434,400 |
| Reduction nationally | 13.5% | 27.1% |
| Additional transfers per year (30,500 RWF a quarter) | 9.8 bn RWF | 19.7 bn RWF |

## Reading these results

- **The poverty model concentrates resources far better than geography.** At a 20% budget it reaches two thirds of poor people. It still misses a third of them and selects about 181,000 non-poor households. Verification and community validation remain essential.
- **The protection gap is large everywhere.** No realistic single expansion closes it. Geographic focus (scenario 4) and household prioritisation (scenario 1) are complementary.
- **Costs are first-round transfer totals,** without administrative costs or behavioural responses.
