# Baho Neza release audit (2026-10-30)

This audit covers the first public commit. The release contents are listed exactly in `docs/release_manifest.txt` (204 files, about 27.5 MB as stored by git).

## 1. Decisions applied

| Topic | What was done |
|---|---|
| **Gemini** | Disabled and unconfigured. `.streamlit/secrets.toml` holds placeholders only, is git-ignored and is **not** published. The placeholder template `.streamlit/secrets.example.toml` is published. No live API call was made. |
| **Mapping CSV** | `reports/data_inspection/expenditure_cpi_mapping.csv` is published without `n_households_reporting` and `raw_weighted_share_of_module_pct`. The original is kept in `private/` (git-ignored). The pipeline loader gives identical results: same 389 rows and identical price cells. No other field repeats the counts. |
| **Documents and notebooks** | Redacted public copies, with originals kept in `private/originals/`: <ul><li>`reports/duplicate_validation.md`: 29 household IDs withheld, a per-household amounts table removed, and three individual amounts withheld.</li><li>`docs/household_master_data_dictionary.md`: 1 ID withheld.</li><li>`reports/eicv7_finscope_inventory.md`: ID range withheld.</li><li>`reports/data_inspection/quality_checks.csv`: ID range withheld.</li><li>`data_dictionary.csv` and `key_variables.csv`: the `min`, `max` and `unlabelled_codes` columns dropped, and the statistics on identifier rows blanked.</li><li>Notebook 05: IDs withheld in its markdown source.</li><li>`src/features/build_household_master.py`: one ID removed from its generated text. No logic changed.</li></ul> **All** notebooks are stored without outputs through the `.gitattributes` clean filter (`tools/strip_notebook_outputs.py`). |
| **Still excluded** | <ul><li>`reports/interpretation/local_explanations_*` (per-household explanations);</li><li>`reports/interpretation/shap_dependence_*.png` (one point per household);</li><li>third-party PDFs (`docs/source_documentation/`), cited by link instead;</li><li>all microdata, household tables, scores, splits, the scenario grid, offline reference tables and `models/*.joblib`.</li></ul> |
| **Dependencies** | `src/dashboard/requirements.txt` is the lightweight runtime set: Streamlit, pandas, numpy, pyarrow, plotly, pyyaml, matplotlib (PDF brief), google-genai and httpx (optional AI). Per Streamlit's docs, Community Cloud looks in the entry point's folder first, so this file takes precedence over the root `requirements.txt` (the analysis environment). `requirements-dashboard.txt` points to it. |
| **License** | MIT, "Copyright (c) 2026 Jacques Rebero and Carine Usanase", for the project's code and documentation only. Survey, CPI, boundary and third-party terms are stated separately, in `LICENSE` and `README.md`. |

## 2. Security and disclosure checks on the staged files

These were read from the git index, not the working tree:
- **Forbidden paths:** none staged (microdata, `private/`, `data/interim/`, household and score parquet files, scenario grid, offline tables, `*.joblib`, `secrets.toml`, per-household reports, source PDFs).
- **Notebooks:** all 13 are stored with 0 outputs and 0 execution counts. The 14 files staged earlier, including notebook 03, were re-normalised so the filter applied to them too.
- **Provider credential patterns** (Google, GitHub, OpenAI-style, AWS, private keys, Slack): none in the staged contents.
- **6-digit tokens equal to a household ID:** only coincidences remain:
  - map coordinates (`world_110m.json`);
  - timestamps (`tuning_trials.csv`);
  - two counts of zero values (`data_dictionary.csv`).
- **Limits:** these checks match patterns and identifiers. They do not prove that no disclosure risk remains. The published aggregates still need the NISR review described in `docs/community_planning_app_spec.md`.

## 3. Tests run before the commit

| Check | Result |
|---|---|
| Full suite in the project, with private data present | 190 passed, 1 skipped (browser tests run separately) |
| Release copy built from the git index with `git checkout-index`, fresh Python 3.12 venv from `src/dashboard/requirements.txt` plus pytest | 180 passed, 11 skipped. The skips cover tests that need private household or offline tables, and Playwright, which is not part of the app's dependencies. |
| Real server from the release copy, no `secrets.toml` | Health 200, local map asset 200, Kinyarwanda Compare page 200 |
| Previously intermittent browser check (Compare, Kinyarwanda, 1,440 px) against the release server | Passed 5 of 5 consecutive runs |
| Full browser suite against the release server (Chrome) | See the hand-off report |

## 4. Repository and backup

- **Backup:** `~/baho_neza_backups/2026-10-30/working_tree_with_git.tar.gz`, made before any change and verified. It is outside the repository and has not been uploaded.
- **Private originals of redacted files:** `private/originals/` (git-ignored).
- **Remote:** the approved target is `https://github.com/reberojacques25/baho-neza-nisr-big-data-hackaton.git`. On 2026-10-30 GitHub's public API returned 404 for it, and this machine has no GitHub credentials, so the push waits for the repository to be confirmed and for authentication.

## 5. Streamlit Community Cloud settings (for later)

- **Repository:** the approved repository.
- **Branch:** `main`.
- **Entry point:** `src/dashboard/app.py`.
- **Python:** 3.12, the current Community Cloud default per Streamlit's docs.
- **Secrets:** entered only under the app's **Settings → Secrets**.
