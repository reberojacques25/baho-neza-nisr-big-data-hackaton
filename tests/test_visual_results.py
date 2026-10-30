"""Tests for the compact visual results: chart values match the engine, stale settings hide charts, both languages,
suppression in chart labels and hover text, and the AI-off fallback."""
from __future__ import annotations

import base64
import json

import numpy as np
import pytest

from src.dashboard import data as dd
from src.dashboard import logic as lg
from src.dashboard import scenario as sc
from src.dashboard.i18n import translate

needs_tables = pytest.mark.skipif(not all(p.exists() for p in dd.PUBLIC_FILES.values()) or not dd.META_PATH.exists(),
                                  reason="planning tables not built")
APP = str(dd.PROJECT_ROOT / "src" / "dashboard" / "app.py")
PLACEHOLDER_AI = {"enabled": False, "provider": "gemini", "api_key": "REPLACE_WITH_YOUR_GEMINI_API_KEY",
                  "model": "REPLACE_WITH_VERIFIED_FREE_TIER_MODEL_ID", "external_data_approved": False}


def _app(page: str, lang: str = "en"):
    from streamlit.testing.v1 import AppTest
    at = AppTest.from_file(APP, default_timeout=90)
    at.query_params["lang"] = lang
    at.secrets["ai"] = PLACEHOLDER_AI
    at.switch_page(page)
    return at.run()


def _values(arr) -> list:
    if isinstance(arr, dict) and "bdata" in arr:          # plotly binary encoding
        return np.frombuffer(base64.b64decode(arr["bdata"]), dtype=arr["dtype"]).tolist()
    return list(arr)


def _charts(at) -> list[dict]:
    """Bar charts on the page as {y labels, x values, text, hover}."""
    out = []
    for el in at.get("plotly_chart"):
        spec = json.loads(el.proto.spec)
        for tr in spec["data"]:
            if tr.get("type") == "bar":
                out.append({"y": [y.replace("<br>", " ") for y in tr["y"]], "x": _values(tr["x"]), "text": list(tr["text"]),
                            "hover": list(tr.get("hovertext", []))})
    return out


@pytest.fixture(scope="module")
def tabs():
    return dd.load_public_tables()


# ---------------------------------------------------------------------------
# What if prices rise?
# ---------------------------------------------------------------------------
@needs_tables
@pytest.mark.parametrize("lang", ["en", "rw"])
def test_price_charts_match_the_engine(tabs, lang):
    at = _app("views/prices.py", lang)
    at.radio(key="price_mode").set_value("detailed").run()
    at.slider(key="price_food").set_value(20.0)
    at.slider(key="price_transport").set_value(30.0).run()
    at.button(key="cta_price_calc").click().run()
    assert not at.exception
    res = sc.price_result(tabs["groups"], lg.ALL, "all", at.session_state["saved_price"]["result"]["spec"])
    before_after, contrib = _charts(at)
    assert before_after["x"] == pytest.approx([res["reference_monthly"], res["scenario_monthly"]])
    assert before_after["text"] == [lg.fmt_rwf(res["reference_monthly"], lang), lg.fmt_rwf(res["scenario_monthly"], lang)]
    order = sorted(sc.CATEGORIES, key=lambda c: -res["extra_by_category"][c])
    assert contrib["x"] == pytest.approx([res["extra_by_category"][c] for c in order])
    assert sum(contrib["x"]) == pytest.approx(res["extra_monthly"])          # contributions add up to the KPI
    assert contrib["y"][0].startswith(translate(f"category.{order[0]}", lang))
    assert translate("ux.prices.chart_today", lang, latest=lg.fmt_month("2026-09", lang)) in before_after["y"]


@needs_tables
def test_price_summary_chips_units_and_sentence():
    at = _app("views/prices.py")
    at.slider(key="price_all").set_value(15.0)
    at.select_slider(key="price_horizon").set_value(6).run()
    at.button(key="cta_price_calc").click().run()
    chip_html = next(m.value for m in at.markdown if m.value.startswith('<div class="bn-context">'))
    for text in ("All Rwanda · All areas", "next 6 months from September 2026", "+15% on all prices", "unchanged (assumption)"):
        assert text in chip_html, text
    sentence = next(m.value for m in at.markdown if 'class="bn-result"' in m.value)
    assert "+15.0%" not in sentence and "15.0% more" in sentence and "RWF extra per household per month" in sentence
    cards = [m.value for m in at.markdown if m.value.startswith('<div class="bn-card">')]
    assert len(cards) == 4 and sum("RWF" in c for c in cards) == 2


@needs_tables
def test_stale_settings_hide_price_charts_and_sentence():
    at = _app("views/prices.py")
    at.button(key="cta_price_calc").click().run()
    assert len(_charts(at)) == 2
    at.slider(key="price_all").set_value(25.0).run()
    assert not _charts(at) and not any('class="bn-result"' in m.value for m in at.markdown)
    assert translate("state.stale_price", "en") in "\n".join(m.value for m in at.markdown)
    assert at.button(key="cta_explain_price_off").disabled


# ---------------------------------------------------------------------------
# Compare support
# ---------------------------------------------------------------------------
@needs_tables
def test_offset_chart_shows_support_untruncated_and_excess_separately(tabs):
    at = _app("views/compare.py")
    at.number_input(key="sup_amount").set_value(60_000).run()
    at.button(key="cta_compare").click().run()
    res = at.session_state["saved_compare"]["result"]
    col = res["columns"]["shock_support"]
    offset = _charts(at)[0]
    assert col["support"] > col["extra"]
    assert offset["x"] == pytest.approx([col["extra"], col["support"], 0.0, res["surplus_monthly"]])   # support not truncated
    assert offset["y"][-1] == translate("ux.compare.bar_surplus", "en")
    sentence = next(m.value for m in at.markdown if 'class="bn-result"' in m.value)
    assert "exceeds the extra price cost" in sentence


@needs_tables
@pytest.mark.parametrize("lang", ["en", "rw"])
def test_offset_chart_and_kpis_match_the_engine(tabs, lang):
    at = _app("views/compare.py", lang)
    at.button(key="cta_compare").click().run()
    res = at.session_state["saved_compare"]["result"]
    col = res["columns"]["shock_support"]
    offset = _charts(at)[0]
    assert offset["x"] == pytest.approx([col["extra"], col["support"], col["not_offset"]])
    assert offset["text"] == [lg.fmt_rwf(v, lang) for v in (col["extra"], col["support"], col["not_offset"])]
    cards = {m.value.split('class="label">')[1].split("<")[0]: m.value.split('class="value">')[1].split("<")[0]
             for m in at.markdown if m.value.startswith('<div class="bn-card">')}
    assert cards[translate("ux.compare.kpi_new", lang)] == lg.fmt_count(res["new_recipient_households"])
    assert cards[translate("ux.compare.kpi_people", lang)] == lg.fmt_count(res["new_recipient_people"])
    assert cards[translate("ux.compare.kpi_cost", lang)] == lg.fmt_rwf(res["total_cost"], lang)
    assert cards[translate("ux.compare.kpi_remaining", lang)] == lg.fmt_rwf(col["not_offset"], lang)


@needs_tables
def test_benefit_increase_shows_existing_recipients_only():
    at = _app("views/compare.py")
    at.radio(key="sup_action").set_value("nsds_increase").run()
    at.button(key="cta_compare").click().run()
    labels = [m.value for m in at.markdown if m.value.startswith('<div class="bn-card">')]
    assert any(translate("ux.compare.kpi_existing", "en") in c for c in labels)
    assert not any(translate("ux.compare.kpi_new", "en") in c for c in labels)
    sentence = next(m.value for m in at.markdown if 'class="bn-result"' in m.value)
    assert "current NSDS households" in sentence


@needs_tables
def test_stale_settings_hide_compare_charts_and_export():
    at = _app("views/compare.py")
    at.button(key="cta_compare").click().run()
    assert _charts(at) and at.get("download_button")
    at.number_input(key="sup_amount").set_value(5_000).run()
    assert not _charts(at) and not at.get("download_button") and at.button(key="cta_compare_csv_disabled").disabled
    assert translate("state.stale_compare", "en") in "\n".join(m.value for m in at.markdown)


@needs_tables
def test_ai_off_fallback_keeps_the_short_explanation():
    at = _app("views/compare.py")
    at.button(key="cta_compare").click().run()
    assert any('class="bn-result"' in m.value for m in at.markdown)                     # one short sentence, always
    assert translate("explain.title", "en") in [e.label for e in at.expander]            # detail collapsed below
    assert at.button(key="cta_explain_compare").disabled
    assert translate("explain.not_configured", "en") in [c.value for c in at.caption]


# ---------------------------------------------------------------------------
# Our community: group chart with suppression
# ---------------------------------------------------------------------------
@needs_tables
def test_group_chart_hides_suppressed_cells_in_labels_and_hover(tabs):
    g = tabs["groups"]
    cand = g[g["level"].eq("district") & g["area"].eq("all") & g["dimension"].isin(lg.COMPARISON_DIMENSIONS) & g["suppressed"]]
    district = cand["geo"].iloc[0]
    at = _app("views/community.py")
    at.selectbox(key="geo").set_value(district).run()
    chart = _charts(at)[0]
    cmp = lg.group_comparisons(g, district, "all")
    hidden = translate("common.hidden", "en")
    for (_, r), x, text, hover in zip(cmp.iterrows(), chart["x"], chart["text"], chart["hover"]):
        if r["suppressed"]:
            label = translate(f"group.{r['dimension']}.{r['group']}", "en")
            assert x == 0 and text == hidden and hover == f"{label}: {hidden}"           # no value, no interval
        else:
            assert x == pytest.approx(100 * r["poverty_rate"]) and text == lg.fmt_share(r["poverty_rate"])
            assert "95%" in hover                                                      # uncertainty kept in hover
    assert sum(cmp["suppressed"]) >= 1
