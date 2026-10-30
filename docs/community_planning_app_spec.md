# Baho Neza: community planning app specification

**Status:** implemented locally, not deployed. **Date:** 2026-10-29.
**Code:** `src/dashboard/`. **Offline builder:** `src/dashboard/build_planning.py`.
**Tests:** `tests/test_planning.py`, `tests/test_dashboard_app.py`, `tests/test_browser_layout.py`.

Baho Neza helps Rwandan policymakers and district planners do three things:
1. understand community needs;
2. test how rising prices could affect households;
3. compare practical support responses, their costs and their estimated reach.

It is a planning tool. It is **not**:
- an automatic beneficiary selector;
- an eligibility decision;
- a predictor of what a policy would cause.

---

## 1. Implemented flows

| Page | Question | What it does |
|---|---|---|
| **Overview** | Plan better support for your community. | Has two buttons: Explore my district and Test a price change. Shows four national figures, each with units, period and denominator, and the flow: Understand needs → Test a change → Compare responses. |
| **Our community** | Where is support needed? | **Controls:** district, area (All, Urban, Rural) and the indicator to map. **Map and panel:** a 65/35 split; the panel gives 95% intervals and a plausible rank range. **Below the map:** up to three findings supported by the intervals, comparisons for protected groups, observed support gaps, an expander on predicted coverage patterns, and the district planning brief (CSV and PDF). |
| **What if prices rise?** | How could changing prices affect our community? | **Before any input:** the baseline (latest CPI month) and the horizon (3, 6 or 12 months). **Inputs, in one of two exclusive modes:** one increase for all prices, or a separate increase per category. **Results:** basket change, extra monthly cost, purchasing power, the total for all households, a breakdown by category, and the most exposed groups. A button carries the scenario forward to Compare support. |
| **Compare support** | What response could help, and what would it cost? | **Carried scenario:** the price scenario comes from the previous page and can be edited there or reset to no new price change. **Choices:** a supported programme and its parameters. **Results:** a table of Today, Price change only, and Price change + support, plus reach and cost cards, with the scope stated (place, period, programme, recipients, payment, prices, assumptions). The results export as CSV. |
| **How it works** | | The four components in plain language. A technical expander covers: holdout metrics, cross-fitted simulation statistics, households versus people, calibration, fairness limitations, sources, the age of the survey, CPI mapping, scenario assumptions and the use of AI. |
| **Data & limitations** | | The three kinds of numbers, the disclosure rules, supported and unsupported scenarios, translation status, and survey sample sizes by district. |

**Every page has:**
- a header with the brand, the four main pages and a 🌐 language selector;
- the persistent message "Planning estimates. Official eligibility and verification still apply.";
- a footer linking to How it works and Data & limitations.

**Context chips** show:
- the selected place and area;
- the survey period (EICV7, October 2023 to October 2024);
- the latest CPI month (September 2026);
- the price scenario, on the pages that use one.

**Source tags** mark what kind of number each card holds:
- *Survey statistic* (✓) for observed figures;
- *Model estimate* (≈) for model output;
- *Scenario* (?) for anything derived from user assumptions.

There is **no login, access-code page or staff area**.

## 2. Analytical components

| Component | Used on | How |
|---|---|---|
| **A. Poverty model.** Tuned LightGBM with group recalibration; out-of-sample scores. | Our community; Compare support | **Our community:** the "Estimated poverty likelihood" indicator, a model estimate shown with a 95% sampling interval. **Compare support:** the planning group "Higher estimated poverty likelihood" (top 10/20/30% within the selected place) and the priority order for the validated Direct Support expansion. **Never used for:** eligibility, or editing features to simulate what a policy causes. |
| **B. Household price-shock engine.** Notebook 07. | Our community; What if prices rise?; Compare support | **Our community:** "Household price pressure", the change in the cost of the same basket from January 2024 to September 2026. **What if prices rise? and Compare support:** the reference basket by category, onto which scenario increases are added. |
| **C. Distress score.** Equal-weight average of six components; high need is the top fifth nationally, excluding VUP. | Our community; Compare support | **Our community:** "Need level" (share of households that are high-need). **Compare support:** the planning groups "Higher distress" (top 10/20/30%) and "High need without observed VUP support". **Never re-scored** under a scenario; users are never asked to "increase a score". |
| **D. VUP coverage model.** Tuned XGBoost with Platt scaling. | Our community | Only in the "Predicted coverage patterns" expander, set beside **observed** coverage of high-need households, with the wording "not proof of wrongful exclusion". Observed participation (the map indicator) comes from the survey, not the model. |

FinScope is not used. No FinScope household features or joins exist.

## 3. Formulas

### Reference basket (offline, per household; RWF per month at September 2026 prices)

    basket_jan2024 = real consumption (January 2024 prices) × basket share          (notebook 07)
    ref_c          = basket_jan2024 × (share_c + contrib_c / 100) / 12

- **Categories c:**
  - food;
  - energy and fuel (household energy and vehicle fuel);
  - transport (excluding fuel);
  - education (school fees and costs);
  - other (communication, meals away and everything else).
- **Inputs:** `share_c` and `contrib_c` (= 100 × Σ s Δ over the category's cells) come from `household_cpi_shock.parquet`. The transport share excluding fuel is the transport share minus the vehicle-fuel cell share.
- **Identity:** Σ_c ref_c = basket_jan2024 × (1 + price change) / 12. The observed change from January 2024 to September 2026 is applied **exactly once**, and checked to machine precision.

### Price scenario (runtime, from aggregates)

    extra_monthly       = Σ_c ref_c × p_c / 100
    basket_change_pct   = 100 × extra_monthly / Σ_c ref_c
    purchasing_power    = −100 × extra_monthly / (Σ_c ref_c + extra_monthly)     (incomes unchanged in money terms)

- **Inputs:** p_c are cumulative increases (0–50% in the interface, 0–100% in the engine) over the chosen horizon, added on top of September 2026 prices. They are **not** annual inflation rates.
- **Why group means are exact:** the formula is linear in p_c, so the survey-weighted mean of ref_c gives the exact group mean.
- **Zero increases** reproduce the reference basket.

### Support (runtime)

    payments          = duration_months / payment_interval_months       (monthly 1, quarterly 3)
    direct transfers  = recipient households × amount per payment × payments
    delivery costs    = direct transfers × delivery_pct / 100            (0 = "not specified")
    total             = direct transfers + delivery costs
    support / month   = amount per payment / payment interval            (0 when duration is 0)
    not offset        = max(extra_monthly − support / month, 0)         group average per household

**Comparison columns:**
- **Today:** reference basket, no extra cost, no support.
- **Price change only:** basket plus extra cost.
- **Price change + support:** the same basket, because **cash does not change market prices**, with support added and the uncovered extra cost shown.

The figures are group averages. Some households can still face a shortfall when the average is covered, and the app says so.

### Uncertainty and findings

- **95% intervals** use Taylor linearisation for domain means and totals: clusters within the 60 strata (district × urban/rural), with the stratum finite-sample factor n_h/(n_h − 1).
- **Findings** (at most three):
  - A district is compared with Rwanda (same area). A finding is listed only if the district's 95% interval excludes the national value.
  - For Rwanda overall, rural is compared with urban, and a finding is listed only if their intervals do not overlap.
- **Rank range:**
  - best = 1 + the number of districts whose interval lies entirely on the worse side;
  - worst = n − the number entirely on the better side.
  - This keeps the page from overstating differences between neighbouring ranks.

## 4. Supported scenarios

| Programme | Recipients | Geography | Payment | Source |
|---|---|---|---|---|
| **New cash transfer** | **Planning group, chosen by one of three rules:** (1) top 10/20/30% by estimated poverty likelihood; (2) top 10/20/30% by distress; (3) all high-need households without VUP. **Ranking:** within the selected place and area. | Rwanda or a district; all, urban or rural, where the cell is published | **Amount:** set by the user (default 10,000 RWF), labelled a planning assumption and not a programme rate. **Frequency:** monthly or quarterly. | Aggregates in `dashboard_planning` |
| **Expand VUP Direct Support** | New Direct Support households under the **validated** coverage-expansion scenario: +1, +2 or +5 percentage points of all households, drawn from households with no VUP, in poverty-model priority order (`policy_simulator.coverage_expansion`). | Rwanda. **A district shows only its share of the national expansion, labelled as such.** | **Payment:** a separate Direct Support input. The default of 30,500 RWF per quarter is the validated simulation assumption. **Observed reference:** the help text shows the observed median DS amount (90,000 RWF a year). | Reconciles exactly with `scenario_results.parquet` (+2 points: 65,800 households, 8.03 billion RWF a year) |
| **Increase NSDS payments** | Current NSDS households. **No new recipients.** | Rwanda (district cells are mostly suppressed) | **Payment:** +x% of each household's observed quarterly payment; its own basis, separate from DS. | Reconciles with the `benefit_increase` scenario (+10%: about 1.29 billion RWF a year) |

**Durations:** 0, 3, 6 or 12 months. The duration must be a whole number of payment periods.

**Not supported.** Each is listed in the app with its reason:

| Not supported | Reason |
|---|---|
| Paid public works | Gross wages could be counted, but net additional earnings are unknown, and the mapping from participants to households is not modelled. |
| School-cost support | No programme rules. Learners are not households. |
| Food assistance | No programme rules, and no valuation of in-kind food. |
| Training, farming or business support | No evidence on returns. |
| Combined packages | Overlap between programmes is not calculated, so recipients could be counted twice. |
| Earnings adjustments | Survey income is not reliable enough. |
| Poverty after support | No validated update of the poverty line, price basis or consumption response. Classifier features are never edited to imitate a policy. |

Unsupported requests raise `UnsupportedScenario(code)`, which the app shows as a translated message.

## 5. Assumptions (shown in the app)

- Households, recipients and programme membership are as surveyed in 2023/24. Nobody joins or leaves.
- Incomes and other resources stay the same in money terms.
- Households keep the same basket: no switching to cheaper goods.
- There are no gains to food-selling farm households and no wider effects on jobs or businesses.
- District differences in basket cost come from spending composition and the urban or rural CPI. NISR publishes no district price indices.

## 6. Scenario state safety

**Normalised specs.** `scenario.price_spec` and `scenario.support_spec` build normalised, language-independent dictionaries:
- they contain only the inputs of the chosen mode or programme;
- numbers are rounded;
- codes are used instead of labels.

**Fingerprints.**
- price: `fingerprint("price", price_spec, geo, area)`;
- comparison: `fingerprint("compare", price_spec, support_spec, geo, area)`.

The fingerprint is a SHA-256 hash.

**How results are kept and invalidated:**
- **Saving.** A completed result is saved in session state together with its fingerprint.
- **Any page.** On every page the current inputs, which persist across pages, are re-normalised. If the fingerprint differs from the saved one, the result is **stale**.
- **When stale:**
  - numbers are hidden and "Settings changed. Calculate again." or "Settings changed. Compare again." is shown;
  - the CSV export is replaced by a disabled button;
  - the planning brief leaves the scenario out;
  - controls and the recalculation button stay available. The page never calls `st.stop()` before recalculation.
- **Language.** Language is not part of any fingerprint, so switching language keeps valid results and re-renders them with translated labels.

## 7. Aggregate-only runtime and disclosure control

**The runtime reads only:**
- `dashboard_groups.parquet`;
- `dashboard_planning.parquet`;
- `dashboard_meta.json`;
- `data/external/geo/rwa_districts.geojson`.

**Runtime code never reads or imports** household tables, household predictions, `.dta` files, models, `scenario_results.parquet` (which has small district cells), or the build or simulation modules. Tests enforce this statically. All household-level work runs offline in `build_planning.py`.

**Disclosure rules** (`src/dashboard/disclosure.py`):

1. **Primary suppression.** Cells with fewer than 30 sample households are hidden (for high-need indicators, fewer than 30 sample high-need households). The sample sizes of hidden cells are not published.
2. **Complementary subtraction** (secondary suppression). For every additive relation, if exactly one member is hidden, the smallest published part is hidden too. This repeats until no relation has a single hidden member. The relations are:
   - district = urban + rural;
   - Rwanda = sum of districts, for each area;
   - all households = each pair of groups (head's sex, disability, elderly member, poverty status).

   The same rule is now applied to `dashboard_data.parquet`.
3. **Repeated differencing of nested selections.** The top 10%, 20% and 30%, and everyone, are checked so that every slice between consecutive published levels holds at least 30 sample households. Otherwise the higher level is hidden.
4. **Overlapping filters.** High-need households are not published as a spending group, so a high-need group cannot be differenced against the "high need without VUP" planning group. Price scenarios are linear combinations of already-published category means, so varying them reveals nothing new.

**Hidden cells** carry no values in the tables. They show "Not shown (small sample)" in cards, maps (grey), tooltips, tables and both brief formats.

**Residual risks, not formally assessed:**
- overlaps *between* different ranking rules (for example, the top 10% by poverty against the top 10% by distress);
- combining these tables with other published NISR tables.

**These rules have not been reviewed or approved by NISR.** The app says so.

## 8. District planning brief

- **Formats:** CSV, plus a one-page A4 PDF (210 × 297 mm). The PDF is drawn with matplotlib's bundled DejaVu Sans font, so it needs no network or external service.
- **Contents:**
  - Baho Neza and the selected place and area;
  - the generation date, survey period and price window;
  - indicators with 95% intervals and source type;
  - up to three findings;
  - the price scenario and the support comparison, **only when the saved results are valid** for the current inputs and place;
  - the suppression note, sources and the responsible-use message.
- **Language:** headings and file names are translated.
- **It is not:** an official document. It carries no seal, and it says it is "not an approved government document".

## 9. Translation review status

- **Single system:** `src/dashboard/i18n/{en,rw}.yaml` with `t()`, plus `bound()` for widget format functions.
- **Tested:**
  - key and placeholder parity;
  - that every literal and generated key exists;
  - that no text is hardcoded in pages;
  - that there are no language checks scattered through pages.
- **Kinyarwanda: machine-drafted, NOT reviewed by a native speaker.** The file header, the Data & limitations page and the How it works page all say so. No translations were copied from chat.

## 10. Verification

| Check | Result |
|---|---|
| `python -m pytest -q` (offline data, simulator, planning, app) | See the README and the latest run |
| Real-browser checks (`tests/test_browser_layout.py`, Playwright with Chrome) | **Pages:** all six, in English and Kinyarwanda, at 1280 px and 390 px, with no horizontal overflow. **Layout:** a 65/35 map and panel split on desktop, stacked on mobile; call-to-action targets of at least 44 px; a price calculation completed on mobile. |

## 11. Deferred work and blockers

1. **NISR disclosure-control review** of the published aggregates and of these rules. This is a blocker for a public launch.
2. **Native-speaker review** of `rw.yaml`. This is a blocker for a public launch.
3. **Poverty after support:** needs a validated poverty line at current prices, an equivalence scale and consumption-response assumptions.
4. **Public works, school costs and food assistance:** need programme rules and, for public works, net-earnings evidence.
5. **Combined packages:** need household-level overlap computed offline per package, then the same disclosure checks.
6. **Uncertainty for scenario outputs.** Only survey sampling intervals for indicators are shown. Scenario totals carry no interval.
7. **Optional AI explanations** (`docs/ai_explanation.md`): implemented but disabled. They need the outbound-data approval described there before `external_data_approved = true`.
8. **Programme owner review** (for example LODA or MINALOC) of the wording and of the planning-group rules.

## 12. 60-second demonstration script

| Time | Page | Action and talking point |
|---|---|---|
| 0–10 s | Overview | "Baho Neza helps districts plan support." Point to the four figures, for example 595,800 high-need households without VUP. Click **Explore my district**. |
| 10–25 s | Our community | Choose **Rutsiro**. The map and panel show estimated poverty likelihood with intervals, and the rank range shows that neighbouring ranks overlap. Read one finding. Note "possible support gaps, not wrongful exclusion". |
| 25–40 s | What if prices rise? | The baseline is September 2026. Set food +20% over 12 months (by category) and click **Show results**: the extra monthly cost per household and the most exposed groups. Point out "Scenario, not a forecast." Click **Use this scenario to compare support**. |
| 40–55 s | Compare support | The scenario has carried over. Choose a cash transfer to the top 20% by estimated poverty likelihood and click **Compare**. Read the three columns, households reached, and the total cost (= households × amount × payments). Change the amount: the result is hidden with "Settings changed. Compare again." |
| 55–60 s | Our community, then Data & limitations | Download the **District planning brief** (PDF). Close on the persistent message: "Planning estimates. Official eligibility and verification still apply." |
