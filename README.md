# Baho Neza

**Plan better support for your community. · Tegura ubufasha bunoze ku baturage bawe.**

**English.** Baho Neza helps Rwandan policymakers and district planners with three tasks:
1. understand where needs are;
2. test how rising prices could affect households;
3. compare what support responses could cost and whom they would reach.

It is a public, login-free, bilingual (English and Kinyarwanda) planning app. It is built on the NISR **EICV7 2023/24** household survey and the NISR **Consumer Price Index** up to September 2026.

**Ikinyarwanda.** Baho Neza ifasha abafata ibyemezo n'abategura igenamigambi ry'uturere:
1. kumenya aho ibikenewe biri;
2. kugerageza uko izamuka ry'ibiciro ryagira ingaruka ku ngo;
3. kugereranya ikiguzi n'abagerwaho n'ubufasha butandukanye.

Ishingiye ku bushakashatsi **EICV7 2023/24** bwa NISR n'**Igipimo cy'ibiciro ku baguzi** kugeza Nzeri 2026. _(Ubusobanuro bw'Ikinyarwanda buracyasuzumwa.)_

> **Responsible use.** Planning estimates. Official eligibility and verification still apply.
> - Baho Neza is **not** an automatic beneficiary selector, an eligibility decision or a guaranteed policy-impact predictor.
> - Low predicted VUP coverage is **not** proof that anyone was wrongly excluded.
> - Scenarios are **not** forecasts. No poverty change after support is estimated.
>
> See [Responsible use](#responsible-use), [`docs/community_planning_app_spec.md`](docs/community_planning_app_spec.md) and [`docs/model_card.md`](docs/model_card.md).

## The app

| Page | Question | Contents |
|---|---|---|
| **Overview** | Plan better support for your community. | **Buttons:** Explore my district and Test a price change. **Figures:** four national figures, each with units, period and denominator. **Flow:** the three steps. |
| **Our community** | Where is support needed? | **Controls:** district, area (All, Urban, Rural) and indicator. **Map and panel:** a map with a summary panel giving 95% intervals and a rank range. **Below the map:** up to three findings supported by the intervals, protected-group comparisons, observed support gaps, predicted coverage patterns (in an expander), and the **district planning brief** (CSV and PDF). |
| **What if prices rise?** | How could changing prices affect our community? | **Before any input:** the baseline (latest CPI month) and the horizon. **Inputs:** one increase for all prices, or separate increases by category. **Results:** basket change, extra monthly cost, purchasing power, the most exposed groups, and what the scenario leaves out. |
| **Compare support** | What response could help, and what would it cost? | **Inputs:** the price scenario, carried from the previous page (edit or reset), and a choice of new cash transfer, Direct Support expansion or NSDS increase. **Results:** a table of Today, Price change only and Price change + support; households and people reached; direct transfers, delivery costs and total cost; and a CSV export. |
| How it works | | The four components (poverty model, price-shock engine, distress score, VUP coverage model), with technical details in an expander. |
| Data & limitations | | **The numbers:** survey statistics, model estimates and scenarios. **Also:** disclosure rules, what is not supported, translation status and sample sizes. |

**Languages.**
- **How to switch:** the 🌐 selector, or `?lang=rw`, switches every label, chart, legend, unit, error, assumption, disclosure and download.
- **Where the text lives:** [`src/dashboard/i18n/en.yaml`](src/dashboard/i18n/en.yaml) and [`rw.yaml`](src/dashboard/i18n/rw.yaml).
- **Review status:** **the Kinyarwanda text is machine-drafted and must be reviewed by a native speaker before public release.**

**State safety.**
- **Fingerprints:** every result is saved with a fingerprint of all its calculation inputs.
- **Changing inputs:** changing any input on any page hides the old numbers ("Settings changed. Compare again.") and disables their exports.
- **Changing language:** switching language keeps valid results.

**Plain-language explanations.**
- **Always on:** every valid result on *What if prices rise?* and *Compare support* shows a deterministic "In plain words" explanation.
- **Optional AI rewording:** once configured, Gemini explains each new result as soon as you click **Show results** or **Compare**; the **Explain simply** button stays visible to retry. It is **off by default**, never calls on page load, slider moves or reruns, and Baho Neza inserts every number itself.
- **Setup and conditions:** see [`docs/ai_explanation.md`](docs/ai_explanation.md) for setup, the outbound-data contract and the free-tier data-use conditions that must be reviewed first.

## Screenshots

> _Placeholders: add release screenshots to `docs/screenshots/`. `tests/test_browser_layout.py` with `BAHO_NEZA_SHOTS` set produces them._

| Page | English (desktop) | Kinyarwanda (390 px mobile) |
|---|---|---|
| Overview | `docs/screenshots/overview_en_desktop.png` | `docs/screenshots/overview_rw_mobile.png` |
| Our community | `docs/screenshots/community_en_desktop.png` | `docs/screenshots/community_rw_mobile.png` |
| What if prices rise? | `docs/screenshots/prices_en_desktop.png` | `docs/screenshots/prices_rw_mobile.png` |
| Compare support | `docs/screenshots/compare_en_desktop.png` | `docs/screenshots/compare_rw_mobile.png` |

## 60-second demonstration

1. **Overview (0–10 s).** Read the four figures. Click **Explore my district**.
2. **Our community (10–25 s).** Choose **Rutsiro**. Show the map, the panel with its intervals, and the rank range. Read one finding.
3. **What if prices rise? (25–40 s).** Switch to *By spending category*, set food to +20% over 12 months, and click **Show results**. Point out "Scenario, not a forecast." Click **Use this scenario to compare support**.
4. **Compare support (40–55 s).** Choose a new cash transfer to the top 20% by estimated poverty likelihood, and click **Compare**. Read the three columns and the total cost. Change the amount to show "Settings changed. Compare again."
5. **Close (55–60 s).** Download the district planning brief (PDF). Close on "Planning estimates. Official eligibility and verification still apply."

The full script is in [`docs/community_planning_app_spec.md`](docs/community_planning_app_spec.md#12-60-second-demonstration-script).

## Architecture

```
NISR EICV7 .dta + NISR CPI .xls                       (raw, not in the repository)
        │  notebooks 03–07   src/data, src/features
        ▼
household_master / household_cpi_shock .parquet        one row per household (private)
        │  notebooks 08–15   src/models, src/simulation (validated scenarios)
        ▼
household_scores.parquet, scenario_results.parquet     out-of-sample scores, scenario grid (private / offline)
        │  python -m src.dashboard.build_planning      aggregation + disclosure control (offline)
        ▼
dashboard_groups.parquet · dashboard_planning.parquet · dashboard_meta.json     (public aggregates)
        │  streamlit run src/dashboard/app.py          reads ONLY these + district GeoJSON
        ▼
Baho Neza: Overview · Our community · What if prices rise? · Compare support  (+ How it works, Data & limitations)
```

| Path | Contents |
|---|---|
| `src/dashboard/app.py`, `views/` | Entry point and the six pages |
| `src/dashboard/ui.py`, `theme.py` | Shared components; design tokens and the only CSS (owned `bn-*` classes) |
| `src/dashboard/scenario.py` | Pure scenario engine: normalised specs, fingerprints, price and support formulas |
| `src/dashboard/logic.py`, `brief.py` | Indicators, formatting, findings; district planning brief (CSV/PDF) |
| `src/dashboard/build_planning.py`, `disclosure.py` | Offline aggregation and disclosure control |
| `src/dashboard/i18n/` | `en.yaml`, `rw.yaml`, `t()` |
| `src/simulation/policy_simulator.py` | Validated scenarios (coverage expansion, targeting, benefit, protection gap) |

## Run locally

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dashboard.txt     # app only (same pins as src/dashboard/requirements.txt)
streamlit run src/dashboard/app.py            # from the project root; http://localhost:8501 (add ?lang=rw)
```

**Dependency files:**

| File | Purpose |
|---|---|
| `src/dashboard/requirements.txt` | App runtime. Streamlit Community Cloud reads this file, because it sits next to the entry point. |
| `requirements-dashboard.txt` | Local app install. It points to the file above. |
| `requirements.txt` | Full analysis environment (notebooks, models, tests). It is needed only with NISR microdata access. |

**What this public repository contains:**
- code, documentation and tests;
- the disclosure-controlled aggregate tables that the app reads;
- notebooks **without outputs**: the `.gitattributes` filter strips them, and `tools/strip_notebook_outputs.py` documents how.

It does **not** contain raw EICV7 or FinScope microdata, household-level tables, model files, private originals, or secrets. The reports that named households are published in redacted form.

**Rebuild the public aggregates** from the private household tables (offline, with NISR microdata access; place the EICV7 files in `Microdata/`, which Git ignores):

```bash
python -m src.dashboard.build_data            # dashboard_data (offline reference table)
python -m src.dashboard.build_planning        # dashboard_groups, dashboard_planning, dashboard_meta.json
```

The full analysis is in notebooks 03–15 (see `docs/`). Notebook 14 holds the one-time holdout evaluation and must not be rerun casually.

## Tests

```bash
python -m pytest -q                                           # offline data, simulator, planning layer, app
BAHO_NEZA_URL=http://localhost:8501 python -m pytest -q tests/test_browser_layout.py   # needs Playwright + a running app
```

| File | What it tests |
|---|---|
| `tests/test_policy_simulator.py`, `tests/test_dashboard_data.py` | The validated scenarios and the original aggregates. These are retained. |
| `tests/test_planning.py` | **Disclosure:** secondary and nested suppression, and that no relation has exactly one hidden cell. **Agreement:** groups match `dashboard_data`. **Price engine:** the reference basket applies the observed change once, and zero increase reproduces it. **Support:** costs equal recipients × amount × payments; zero assistance equals price change only; zero duration means zero transfers; a benefit increase adds no recipients; cash does not change prices. **Reconciliation:** the validated DS and NSDS figures are reproduced. **Errors:** unsupported scenarios fail with clear codes. **Rebuild:** the saved tables match a fresh build. |
| `tests/test_dashboard_app.py` | **Translations:** parity, every key exists, no hardcoded text. **Branding.** **Units.** **Theme tokens.** **Aggregate-only runtime.** **Pages:** every page loads in both languages. **Persistence:** language and place carry across pages. **Results:** stale results are hidden across pages and exports disabled; a language switch keeps valid results. **Scope:** districts versus Rwanda. **Brief:** reflects the selected filters and scenario, hides suppressed cells, and exports in both languages. |
| `tests/test_visual_results.py` | **Charts:** values match the calculation engine in both languages. **Stale results:** changing settings hides charts and exports. **Suppression:** applied in chart labels and hover text. **AI:** the fallback works when it is off. |
| `tests/test_browser_layout.py` | **Viewports:** 1,440 px, 1,920 px and 390 px. **Overflow:** none horizontally. **Layout:** a 70/30 map and panel split on desktop, stacked on mobile. **Width:** content is wide but capped. **Targets:** at least 44 px. **Results:** pages with charts render fully. |

In a public clone, tests that need private household data are skipped automatically.

## Deployment checklist (not deployed)

**Ship only:**
- `src/__init__.py`;
- `src/dashboard/`, except `build_*.py` and `disclosure.py`, which are offline only;
- `.streamlit/config.toml`;
- `data/external/geo/rwa_districts.geojson`;
- `data/processed/dashboard_groups.parquet`, `dashboard_planning.parquet` and `dashboard_meta.json`;
- `src/dashboard/requirements.txt` (the app dependencies).

**Streamlit Community Cloud settings:**
- repository: this one;
- branch: `main`;
- entry point: `src/dashboard/app.py`;
- Python: 3.12;
- secrets: entered under **Settings → Secrets** only.

**Never ship:**
- `household_*.parquet`, `*_scores*.parquet`, `model_splits.parquet`, `scenario_results.parquet` (it has small district cells) or `models/`;
- `Microdata/`, `FINSCOPE_DATA/` or `data/interim/`.

**Before going public:**
- [ ] NISR reviews the disclosure-control rules and the published aggregates. Approval is not claimed anywhere.
- [ ] A native Kinyarwanda speaker reviews `src/dashboard/i18n/rw.yaml`.
- [ ] The programme owner (for example LODA or MINALOC) reviews the planning-group rules, the payment assumptions and the wording.
- [ ] Screenshots are added to `docs/screenshots/`.
- [ ] `python -m pytest -q` and the browser checks pass on the deployment build.
- [ ] AI explanations: real secrets go only in Streamlit Cloud **Settings → Secrets** (never committed); `external_data_approved` stays `false` until the review in `docs/ai_explanation.md` §3 is done.
- [ ] The maps and PDF work with no external network access. The map base layer is served from `src/dashboard/static/`, and the PDF uses matplotlib's bundled font.

## Licence

- **Code:** the project's own code is released under the MIT licence (see `LICENSE`).
- **Data and documents:** survey data, CPI data, boundaries and third-party documents keep their own terms (see below). The MIT licence does **not** apply to them.
- **No microdata:** EICV7 and FinScope microdata are not included and may not be redistributed.

## Data sources and licences

| Source | Publisher | Used for | Terms |
|---|---|---|---|
| EICV7 2023/24 microdata | NISR | Households, consumption, poverty, VUP | NISR microdata terms: no redistribution, no re-identification; only aggregates are published |
| Consumer Price Index to September 2026 | NISR | Household baskets by category (urban and rural indices). Official values are never altered | NISR terms, with attribution |
| District boundaries, ADM2 ([geoBoundaries](https://www.geoboundaries.org)) | geoBoundaries / NISR | Maps | CC BY 4.0 |
| `world_110m.json` (Natural Earth 1:110m, Plotly copy) | Plotly / Natural Earth | Hidden map base layer, served locally | Public domain |
| FinScope Rwanda 2024 | Access to Finance Rwanda | Inspected only; **not linked at household level** | Provider terms |

## Model performance (holdout, scored once)

| | Poverty model | VUP coverage model |
|---|---|---|
| ROC-AUC | 0.904 (0.891–0.915) | 0.714 (0.651–0.766) |
| PR-AUC | 0.764 (0.736–0.793) | 0.234 (0.166–0.321) |
| Top 20% | 73% of selected households poor; 66% of poor people reached | |

**Cross-fitted full-sample simulation statistics** are reported separately and are not a second test. At the top 20%:
- 72.4% of selected households are poor;
- 67.1% of poor people are reached.

**Fairness is not solved.** At a single national cut-off, small households, Kigali and young heads of household are reached less. See [`reports/fairness_analysis_summary.md`](reports/fairness_analysis_summary.md).

## Responsible use

**Use Baho Neza to:**
- see where to look first;
- test price scenarios;
- compare the cost and reach of support options.

**Do not:**
- enrol, exclude or rank individual households from it;
- present scenarios as forecasts;
- claim causal poverty reduction;
- judge districts or staff on coverage patterns;
- attempt re-identification.

**Limitations:**
- households are as surveyed in 2023/24; the survey is not a live register;
- district estimates are imprecise (intervals shown);
- there is no district price index;
- no poverty change after support is estimated;
- the Kinyarwanda text has not yet been reviewed by a native speaker.
