"""Tests for the Baho Neza app: translations, branding, the aggregate-only boundary, the running pages in both
languages, scenario state across pages, and the district planning brief."""
from __future__ import annotations

import ast
import re
import string
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from src.dashboard import brief
from src.dashboard import data as dd
from src.dashboard import logic as lg
from src.dashboard import scenario as sc
from src.dashboard import theme as th
from src.dashboard.i18n import LANGUAGES, catalog, translate

ROOT = Path(dd.PROJECT_ROOT)
APP_DIR = ROOT / "src" / "dashboard"
VIEWS = sorted((APP_DIR / "views").glob("*.py"))
RUNTIME_CODE = [APP_DIR / f for f in ("app.py", "ui.py", "logic.py", "scenario.py", "brief.py", "theme.py", "data.py",
                                      "explain.py", "ai_service.py")]
RUNTIME_CODE += [APP_DIR / "i18n" / "__init__.py", *VIEWS]
MAIN_PAGES = ["views/overview.py", "views/community.py", "views/prices.py", "views/compare.py"]
ALL_PAGES = MAIN_PAGES + ["views/how_it_works.py", "views/data_limits.py"]
TITLE_KEYS = {"views/overview.py": "overview.title", "views/community.py": "community.title", "views/prices.py": "prices.title",
              "views/compare.py": "compare.title", "views/how_it_works.py": "how.title", "views/data_limits.py": "data.title"}

needs_tables = pytest.mark.skipif(not all(p.exists() for p in dd.PUBLIC_FILES.values()) or not dd.META_PATH.exists(),
                                  reason="planning tables not built")


# ---------------------------------------------------------------------------
# Translations
# ---------------------------------------------------------------------------
def _fields(text: str) -> set[str]:
    return {f for _, f, _, _ in string.Formatter().parse(text) if f}


def test_catalogues_parse_and_have_the_same_keys_and_placeholders():
    en, rw = catalog("en"), catalog("rw")
    assert set(en) == set(rw)
    for k in en:
        assert en[k].strip() and rw[k].strip(), k
        assert _fields(en[k]) == _fields(rw[k]), k


def test_kinyarwanda_is_flagged_for_native_review():
    head = (APP_DIR / "i18n" / "rw.yaml").read_text(encoding="utf-8").splitlines()[:3]
    assert any("NOT yet reviewed by a native speaker" in line for line in head)
    assert "native speaker" in translate("data.translation", "en")


def test_every_literal_key_used_in_code_exists():
    keys = set(catalog("en"))
    pattern = re.compile(r'\b(?:t|tr|translate)\(\s*"([a-z0-9_.]+)"')
    used = {k for f in RUNTIME_CODE for k in pattern.findall(f.read_text(encoding="utf-8"))}
    assert used and not used - keys, sorted(used - keys)


def test_every_generated_key_exists():
    keys = set(catalog("en"))
    gen = [f"indicator.{i}.{p}" for i in lg.MAP_INDICATORS for p in ("name", "unit", "help")]
    gen += [f"action.{a}.{p}" for a in sc.ACTIONS for p in ("name", "help")]
    gen += [f"action.{a}.{p}" for a in sc.UNAVAILABLE_ACTIONS for p in ("name", "why")]
    gen += [f"rule.{r}.name" for r in sc.RULES] + [f"frequency.{f}" for f in sc.FREQUENCIES]
    gen += [f"category.{c}" for c in sc.CATEGORIES] + [f"category.{c}_help" for c in sc.CATEGORIES]
    gen += [f"prices.increase.{c}" for c in sc.CATEGORIES] + [f"prices.mode_{m}" for m in sc.PRICE_MODES]
    gen += [f"group.{d}.{g}" for d, gs in sc.GROUP_DIMENSIONS.items() for g in gs] + [f"area.{a}" for a in sc.AREAS]
    gen += [f"finding.{c}.{d}" for c in lg.FINDING_COLUMNS for d in ("higher", "lower")]
    gen += [f"finding_area.{c}.{d}" for c in lg.FINDING_COLUMNS for d in ("rural_higher", "rural_lower")]
    gen += [f"compare_groups.{d}.{c}.{x}" for d in lg.COMPARISON_DIMENSIONS for c in ("poverty_rate", "high_need_share")
            for x in ("first_higher", "first_lower")]
    gen += [f"source.{s}" for s in th.SOURCE_TAGS] + [f"months.m{i}" for i in range(1, 13)]
    from src.dashboard import ui
    gen += [f"nav.{p}" for p in ui.PAGES]
    codes = re.findall(r'UnsupportedScenario\("([a-z_]+)"', (APP_DIR / "scenario.py").read_text(encoding="utf-8"))
    gen += [f"errors.{c}" for c in codes]
    assert codes and not set(gen) - keys, sorted(set(gen) - keys)


TEXT_CALLS = {"title", "header", "subheader", "caption", "markdown", "write", "info", "warning", "error", "success", "button",
              "selectbox", "radio", "toggle", "checkbox", "select_slider", "slider", "number_input", "text_input",
              "download_button", "expander", "page_link", "metric", "tabs"}


def _literal_text(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str) and re.search(r"[A-Za-z]{2,}", node.value):
        return node.value
    return None


@pytest.mark.parametrize("path", [APP_DIR / "app.py", APP_DIR / "ui.py", *VIEWS], ids=lambda p: p.name)
def test_no_hardcoded_user_facing_text(path):
    """Widgets and text elements take their words from the catalogues, never from string literals."""
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in TEXT_CALLS:
            args = node.args[:1] + [kw.value for kw in node.keywords if kw.arg in ("label", "help", "placeholder")]
            for a in args:
                assert _literal_text(a) is None, f"{path.name}:{node.lineno} hardcoded text {_literal_text(a)!r}"


def test_no_language_checks_scattered_through_pages():
    for f in [APP_DIR / "app.py", *VIEWS]:
        assert not re.search(r"""lang\s*==\s*["'](en|rw)["']""", f.read_text(encoding="utf-8")), f.name


def test_translate_formats_and_falls_back():
    assert translate("units.billion_rwf", "en", v="8.03") == "8.03 billion RWF"
    assert translate("units.billion_rwf", "rw", v="8.03") == "Miliyari 8.03 Frw"
    with pytest.raises(KeyError):
        translate("no.such.key", "en")
    with pytest.raises(ValueError):
        catalog("fr")


# ---------------------------------------------------------------------------
# Branding, units and theme
# ---------------------------------------------------------------------------
def test_branding_is_baho_neza_everywhere():
    for lang in LANGUAGES:
        assert translate("app.name", lang) == "Baho Neza"
    assert translate("app.tagline", "en") == "Plan better support for your community."
    assert translate("overview.title", "en") == "Plan better support for your community."
    assert translate("app.persistent", "en") == "Planning estimates. Official eligibility and verification still apply."
    files = RUNTIME_CODE + [APP_DIR / "i18n" / "en.yaml", APP_DIR / "i18n" / "rw.yaml", ROOT / "README.md",
                            ROOT / "docs" / "model_card.md", ROOT / "docs" / "community_planning_app_spec.md",
                            APP_DIR / "build_planning.py", APP_DIR / "build_data.py"]
    for f in files:
        text = f.read_text(encoding="utf-8")
        text = text.replace('"Umuseke (.venv)"', "")              # Jupyter kernel id, kept so the notebooks still open
        assert "Umuseke" not in text and "To Baho Neza" not in text, f.name
    assert 't("app.name")' in (APP_DIR / "app.py").read_text(encoding="utf-8")


def test_units_are_explicit():
    assert lg.fmt_share(0.2737) == "27.4%" and lg.fmt_percent(10, signed=True) == "+10.0%"
    assert lg.fmt_rwf(8_027_000_000, "en") == "8.03 billion RWF" and lg.fmt_rwf(932_300_000, "en") == "932.3 million RWF"
    assert lg.fmt_rwf(15_587, "en") == "15,590 RWF" and lg.fmt_rwf(15_587, "rw") == "15,590 Frw"
    assert lg.fmt_count(65_796) == "65,800" and lg.fmt_count(7_644) == "7,640"
    assert "percentage points" in translate("compare.ds_level_value", "en", pp=2)       # pp, not percent
    assert translate("units.months", "en", n=12) == "12 months"
    assert "households" in translate("compare.reach.households", "en").lower()
    assert "people" in translate("compare.reach.people_sub", "en", n="1").lower()
    assert lg.fmt_month("2026-09", "en") == "September 2026" and lg.fmt_month("2026-09", "rw") == "Nzeri 2026"


def test_theme_tokens_and_css():
    cfg = (ROOT / ".streamlit" / "config.toml").read_text()
    for line in ['primaryColor = "#1B4B73"', 'backgroundColor = "#F7F9FB"', 'secondaryBackgroundColor = "#FFFFFF"',
                 'textColor = "#1F2937"', 'borderColor = "#D9E1E7"', "baseFontSize = 16", "enableStaticServing = true"]:
        assert line in cfg
    assert (th.PRIMARY, th.BACKGROUND, th.CARD, th.TEXT, th.TEXT2, th.BORDER) == (
        "#1B4B73", "#F7F9FB", "#FFFFFF", "#1F2937", "#5B6773", "#D9E1E7")
    assert (th.SUPPORT, th.ATTENTION, th.ELEVATED, th.UNMET, th.MISSING) == ("#0F766E", "#F59E0B", "#EA580C", "#9F1239", "#E5E7EB")
    assert "max-width: 1600px" in th.CSS and "padding: 24px 32px" in th.CSS and "padding: 16px 16px" in th.CSS and "border-radius: 12px; padding: 20px" in th.CSS
    assert "min-height: 44px" in th.CSS and "display: none" not in th.CSS
    selectors = [line.split("{")[0] for line in th.CSS.splitlines() if "{" in line]
    assert all("st-key-cta_" in sel for sel in selectors if re.search(r"\bbutton\b", sel))   # no global button override
    assert th.SOURCE_TAGS["scenario"][1] == th.TEXT                  # dark text on pale amber
    assert "<style>" not in "".join(f.read_text(encoding="utf-8") for f in [APP_DIR / "ui.py", *VIEWS])   # CSS lives in theme.py


# ---------------------------------------------------------------------------
# Aggregate-only runtime
# ---------------------------------------------------------------------------
def test_runtime_reads_aggregated_tables_only():
    forbidden_files = re.compile(r"household_master|household_cpi_shock|household_scores|model_splits|poverty_scores|"
                                 r"vup_gap_scores|scenario_results|\.dta\b|\.joblib\b|Microdata|final_model_metrics")
    forbidden_imports = re.compile(r"^\s*(from|import)\s+[\w.]*(build_data|build_planning|policy_simulator|src\.models|joblib|"
                                   r"sklearn|lightgbm|xgboost|shap)", re.M)
    for f in RUNTIME_CODE:
        text = f.read_text(encoding="utf-8")
        if f.name != "data.py":                                       # data.py keeps APP_FILES for the offline tests
            assert not forbidden_files.search(text), f"{f.name} references a household-level or model file"
        assert not forbidden_imports.search(text), f"{f.name} imports modelling or household-level code"
    assert {p.name for p in dd.PUBLIC_FILES.values()} == {"dashboard_groups.parquet", "dashboard_planning.parquet"}
    assert dd.META_PATH.name == "dashboard_meta.json"
    ui_src = (APP_DIR / "ui.py").read_text(encoding="utf-8")
    assert "dd.load_public_tables()" in ui_src and "dd.load_tables(" not in ui_src


@needs_tables
def test_public_files_hold_no_household_columns():
    tabs = dd.load_public_tables()
    for name in ("groups", "planning"):
        assert not dd.HOUSEHOLD_COLUMNS & set(tabs[name].columns)
        assert len(tabs[name]) < 2_000                                # aggregates, not 15,054 household rows


# ---------------------------------------------------------------------------
# The running app
# ---------------------------------------------------------------------------
def _app(lang: str = "en", page: str | None = None):
    from streamlit.testing.v1 import AppTest
    at = AppTest.from_file(str(APP_DIR / "app.py"), default_timeout=90)
    at.query_params["lang"] = lang
    if page:
        at.switch_page(page)
    return at.run()


def _texts(at) -> str:
    parts = [m.value for m in at.markdown] + [c.value for c in at.caption] + [i.value for i in at.info]
    parts += [w.value for w in at.warning] + [h.value for h in at.title] + [h.value for h in at.subheader]
    parts += [b.label for b in at.button]
    return "\n".join(parts)


def _cards(at) -> dict[str, str]:
    out = {}
    for m in at.markdown:
        if m.value.startswith('<div class="bn-card"><div class="label">'):
            label = m.value.split('class="label">')[1].split("<")[0]
            out[label] = m.value.split('class="value">')[1].split("<")[0]
    return out


def _go(at, page: str):
    at.switch_page(page)
    return at.run()


@needs_tables
@pytest.mark.parametrize("lang", list(LANGUAGES))
@pytest.mark.parametrize("page", ALL_PAGES)
def test_every_page_loads_in_each_language(lang, page):
    at = _app(lang, page)
    assert not at.exception, [e.message for e in at.exception]
    text = _texts(at)
    assert at.title[0].value == translate(TITLE_KEYS[page], lang)
    assert translate("app.persistent", lang) in text
    assert [p.label for p in at.get("page_link")][:4] == [translate(f"nav.{k}", lang) for k in
                                                          ("overview", "community", "prices", "compare")]
    for df in at.dataframe:
        assert not set(map(str, df.value.columns)) & dd.HOUSEHOLD_COLUMNS


@needs_tables
def test_overview_has_four_data_backed_figures_and_two_actions():
    at = _app("en")
    cards = _cards(at)
    assert len(cards) == 4
    tabs = dd.load_public_tables()
    fig = lg.overview_figures(tabs["groups"])
    assert cards["High-need households without VUP support"] == lg.fmt_count(fig["gap_households"]) == "595,800"
    assert cards["People below the poverty line"] == lg.fmt_share(fig["poverty_rate"])
    assert cards["Cost of the same household basket"] == lg.fmt_percent(fig["basket_change_pct"], signed=True)
    assert "90.5% of the 658,000 high-need households" in _texts(at)
    assert at.button(key="cta_explore").label == "Explore my district" and at.button(key="cta_prices").label == "Test a price change"
    at.button(key="cta_explore").click().run()
    assert at.title[0].value == "Our community"


@needs_tables
def test_switching_language_changes_labels_and_persists():
    at = _app("en", "views/community.py")
    at.selectbox(key="lang").set_value("rw").run()
    assert not at.exception
    text = _texts(at)
    assert at.title[0].value == translate("community.title", "rw")
    for key in ("community.findings_title", "community.groups_title", "app.persistent"):
        assert translate(key, "rw") in text and translate(key, "en") not in text, key
    assert at.query_params["lang"] == "rw"


@needs_tables
def test_language_and_geography_persist_across_pages():
    at = _app("rw", "views/community.py")
    at.selectbox(key="geo").set_value("Gasabo")
    at.selectbox(key="area").set_value("urban").run()
    for page in ["views/prices.py", "views/compare.py", "views/overview.py", "views/community.py"]:
        at = _go(at, page)
        assert not at.exception
        assert at.title[0].value == translate(TITLE_KEYS[page], "rw")
        if page != "views/overview.py":
            assert at.selectbox(key="geo").value == "Gasabo" and at.selectbox(key="area").value == "urban"
            if page == "views/community.py":
                assert "Gasabo · Umujyi" in _texts(at)


@needs_tables
def test_community_page_findings_groups_and_suppression():
    at = _app("en", "views/community.py")
    at.selectbox(key="geo").set_value("Rutsiro").run()
    text = _texts(at)
    findings = [m.value for m in at.markdown if m.value.startswith("- ") and "Rwanda" in m.value]
    assert findings and findings[0].count("\n- ") + 1 <= 3
    assert "Rank for Estimated poverty likelihood" in text
    assert "This shows possible support gaps. It does not mean someone was wrongly excluded." in text
    assert translate("community.price_note", "en") not in text
    at.selectbox(key="indicator").set_value("price").run()
    assert translate("community.price_note", "en") in _texts(at)
    at.selectbox(key="geo").set_value("Gakenke")
    at.selectbox(key="area").set_value("urban").run()             # hidden cell: no numbers, a clear message
    assert not at.exception
    assert translate("errors.suppressed", "en") in _texts(at)
    panel = next(m.value for m in at.markdown if 'class="bn-row"' in m.value)
    assert panel.count(translate("common.hidden", "en")) == 5 and "%" not in panel


@needs_tables
def test_price_page_results_and_zero_change():
    at = _app("en", "views/prices.py")
    assert translate("prices.prompt", "en") in _texts(at)
    at.slider(key="price_all").set_value(0.0)
    at.button(key="cta_price_calc").click().run()
    cards = _cards(at)
    assert cards["Change in basket cost"] == "+0.0%" and cards["Extra cost per household per month"] == "0 RWF"
    at.radio(key="price_mode").set_value("detailed").run()
    at.slider(key="price_food").set_value(20.0).run()
    assert any("bn-stale" in m.value for m in at.markdown) and not _cards(at)       # old numbers hidden
    at.button(key="cta_price_calc").click().run()
    assert "Most exposed groups" in _texts(at) and "Scenario, not a forecast." in _texts(at)   # inside the details expander
    assert translate("prices.result.purchasing_power", "en") in _cards(at)
    at.button(key="cta_to_compare").click().run()
    assert at.title[0].value == "Compare support"
    assert "Separate increases by category over the next 12 months, from September 2026" in _texts(at)


@needs_tables
def test_compare_page_programmes():
    at = _app("en", "views/compare.py")
    assert translate("compare.prompt", "en") in _texts(at)
    at.radio(key="sup_action").set_value("ds_expansion").run()
    at.button(key="cta_compare").click().run()
    cards = _cards(at)
    assert cards["Additional households supported"] == "65,800" and cards["Total additional cost"] == "8.03 billion RWF"
    assert "Price change + support" in _texts(at)
    at.radio(key="sup_action").set_value("nsds_increase").run()
    at.button(key="cta_compare").click().run()
    cards = _cards(at)
    assert "Additional households supported" not in cards                      # a benefit increase adds no recipients
    assert cards["Existing recipients receiving more"] == "109,000" and cards["Total additional cost"] == "1.29 billion RWF"
    assert "No new recipients" in _texts(at)
    at.radio(key="sup_action").set_value("ds_expansion").run()
    at.selectbox(key="sup_ds_level").set_value(5)
    at.selectbox(key="geo").set_value("Rutsiro").run()
    at.button(key="cta_compare").click().run()
    assert translate("compare.national_rule_note", "en") in _texts(at)          # never shown as a district rule
    for a in sc.UNAVAILABLE_ACTIONS:
        assert translate(f"action.{a}.name", "en") in _texts(at)


@needs_tables
def test_stale_results_are_hidden_across_pages_and_exports_disabled():
    at = _app("en", "views/compare.py")
    at.button(key="cta_compare").click().run()
    assert _cards(at) and at.get("download_button")
    at = _go(at, "views/prices.py")
    at.slider(key="price_all").set_value(25.0).run()              # substantive change on another page
    at = _go(at, "views/compare.py")
    assert translate("state.stale_compare", "en") in _texts(at)
    assert not _cards(at) and not at.get("download_button")
    assert at.button(key="cta_compare_csv_disabled").disabled
    assert not at.button(key="cta_compare").disabled               # recalculation stays available
    at = _go(at, "views/community.py")
    assert translate("brief.excludes_scenario", "en") in _texts(at)
    at = _go(at, "views/compare.py")
    at.button(key="cta_compare").click().run()
    assert _cards(at) and at.get("download_button")
    at = _go(at, "views/compare.py")
    at.selectbox(key="area").set_value("rural").run()             # geography is part of the fingerprint
    assert translate("state.stale_compare", "en") in _texts(at)


@needs_tables
def test_language_switch_keeps_valid_results():
    at = _app("en", "views/compare.py")
    at.button(key="cta_compare").click().run()
    before = list(_cards(at).values())
    at.selectbox(key="lang").set_value("rw").run()
    assert not at.exception
    assert list(_cards(at).values())[:1] == before[:1]            # same households, now with Kinyarwanda labels
    assert translate("ux.compare.kpi_new", "rw") in _cards(at)
    assert translate("state.stale_compare", "rw") not in _texts(at)


# ---------------------------------------------------------------------------
# District planning brief
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def tabs():
    return dd.load_public_tables()


@needs_tables
def test_brief_reflects_filters_and_scenario(tabs):
    g, p, meta = tabs["groups"], tabs["planning"], tabs["meta"]
    price = sc.price_result(g, "Rutsiro", "all", sc.price_spec("simple", 6, 15))
    cmp = sc.compare(p, "Rutsiro", "all", price["spec"], sc.support_spec("cash", amount_rwf=12_000, duration_months=6))
    rows = brief.brief_rows(g, meta, "Rutsiro", "all", "en", price=price, comparison=cmp, today=date(2026, 10, 29))
    flat = "\n".join(f"{r['section']}|{r['item']}|{r['value']}|{r['note']}" for r in rows)
    assert "District planning brief" in flat and "Rutsiro · All areas" in flat and "2026-10-29" in flat
    assert "+15% on all prices over the next 6 months, from September 2026" in flat
    assert lg.fmt_rwf(cmp["total_cost"], "en") in flat and "New cash transfer" in flat
    assert "October 2023 to October 2024" in flat and "Not an approved government document." in flat
    assert sum(r["section"] == "What stands out" for r in rows) <= 3
    no_scen = brief.brief_rows(g, meta, "Rutsiro", "all", "en")
    assert any(r["value"] == translate("brief.no_scenario", "en") for r in no_scen)
    assert brief.brief_filename("Rutsiro", "rural", "en", "pdf", date(2026, 10, 29)) == "baho-neza-brief-rutsiro-rural-2026-10-29.pdf"


@needs_tables
def test_brief_hides_suppressed_cells(tabs):
    hidden = tabs["groups"].query("dimension == 'all' and suppressed").iloc[0]
    rows = brief.brief_rows(tabs["groups"], tabs["meta"], hidden["geo"], hidden["area"], "en")
    ind = [r for r in rows if r["section"] == "Key indicators"]
    assert ind and all(r["value"] == translate("brief.hidden", "en") for r in ind)
    assert not any(re.search(r"\d", r["value"]) for r in ind)


@needs_tables
def test_brief_exports_in_both_languages(tabs):
    for lang in LANGUAGES:
        rows = brief.brief_rows(tabs["groups"], tabs["meta"], "Rutsiro", "all", lang)
        csv = brief.brief_csv(rows, lang).decode("utf-8-sig")
        header = csv.splitlines()[0]
        assert header == ",".join(translate(f"brief.column.{c}", lang) for c in ["section", "item", "value", "note"])
        assert translate("brief.title", lang) in csv
        assert not dd.HOUSEHOLD_COLUMNS & set(pd.read_csv(__import__("io").StringIO(csv)).columns)
        pdf = brief.brief_pdf(rows, lang)
        assert pdf.startswith(b"%PDF") and len(pdf) > 5_000
