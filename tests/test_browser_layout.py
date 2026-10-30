"""Real-browser layout checks for Baho Neza (desktop 1440 and 1920 px, mobile 390 px), with Playwright and a running app.

Skipped unless Playwright is installed and BAHO_NEZA_URL points at a running app, for example:

    streamlit run src/dashboard/app.py --server.headless true &
    BAHO_NEZA_URL=http://localhost:8501 BAHO_NEZA_SHOTS=/tmp/shots python -m pytest -q tests/test_browser_layout.py

Set BAHO_NEZA_BROWSER_CHANNEL=chrome to use an installed Chrome instead of Playwright's bundled Chromium.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest
import yaml

playwright = pytest.importorskip("playwright.sync_api")
URL = os.environ.get("BAHO_NEZA_URL")
pytestmark = pytest.mark.skipif(not URL, reason="set BAHO_NEZA_URL to a running Baho Neza app")
SHOTS = Path(os.environ["BAHO_NEZA_SHOTS"]) if os.environ.get("BAHO_NEZA_SHOTS") else None
I18N = Path(__file__).resolve().parents[1] / "src" / "dashboard" / "i18n"
TEXT = {lang: yaml.safe_load((I18N / f"{lang}.yaml").read_text(encoding="utf-8")) for lang in ("en", "rw")}
# URL path -> catalogue section; the default page (Overview) is served at the root URL
PAGES = {"": "overview", "community": "community", "prices": "prices", "compare": "compare",
         "how_it_works": "how", "data_limits": "data"}
VIEWPORTS = {"desktop": (1440, 900), "xl": (1920, 1080), "mobile": (390, 844)}


@pytest.fixture(scope="module")
def browser():
    with playwright.sync_playwright() as p:
        channel = os.environ.get("BAHO_NEZA_BROWSER_CHANNEL")
        b = p.chromium.launch(channel=channel, headless=True) if channel else p.chromium.launch(headless=True)
        yield b
        b.close()


def _open(browser, path: str, lang: str, viewport: str):
    w, h = VIEWPORTS[viewport]
    page = browser.new_page(viewport={"width": w, "height": h})
    page.goto(f"{URL}/{path}?lang={lang}", wait_until="domcontentloaded")
    page.wait_for_selector("h1", timeout=30_000)
    page.wait_for_timeout(1_500)
    return page


def _no_horizontal_overflow(page) -> bool:
    return page.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1")


@pytest.mark.parametrize("viewport", list(VIEWPORTS))
@pytest.mark.parametrize("lang", ["en", "rw"])
@pytest.mark.parametrize("path", list(PAGES), ids=lambda p: p or "overview")
def test_page_renders_without_horizontal_overflow(browser, path, lang, viewport):
    page = _open(browser, path, lang, viewport)
    try:
        assert page.locator("h1").first.inner_text().strip() == TEXT[lang][PAGES[path]]["title"]
        assert page.get_by_text(TEXT[lang]["app"]["persistent"]).first.is_visible()
        assert _no_horizontal_overflow(page), f"{path} overflows at {viewport}"
        if SHOTS:
            SHOTS.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(SHOTS / f"{path or 'overview'}_{lang}_{viewport}.png"), full_page=True)
    finally:
        page.close()


@pytest.mark.parametrize("viewport", ["desktop", "mobile"])
def test_map_and_panel_split_about_70_30_on_desktop_and_stack_on_mobile(browser, viewport):
    page = _open(browser, "community", "en", viewport)
    try:
        page.wait_for_selector(".js-plotly-plot", timeout=30_000)
        chart = page.locator(".js-plotly-plot").first.bounding_box()
        panel = page.locator(".bn-row").first.bounding_box()
        if viewport == "desktop":
            assert panel["x"] > chart["x"] + chart["width"] * 0.9          # side by side
            assert 0.62 < chart["width"] / (panel["x"] + panel["width"] - chart["x"]) < 0.78     # about 70/30
        else:
            assert panel["y"] > chart["y"] + chart["height"] * 0.9         # stacked
    finally:
        page.close()


@pytest.mark.parametrize("viewport", ["desktop", "mobile"])
def test_call_to_action_targets_are_at_least_44px(browser, viewport):
    page = _open(browser, "", "en", viewport)
    try:
        for key in ("cta_explore", "cta_prices"):
            button = page.locator(f".st-key-{key} button")
            try:
                button.wait_for(state="visible", timeout=30_000)
            except Exception:
                if SHOTS:                                   # keep evidence for an intermittent failure
                    SHOTS.mkdir(parents=True, exist_ok=True)
                    page.screenshot(path=str(SHOTS / f"FAILED_cta_{viewport}.png"), full_page=True)
                    (SHOTS / f"FAILED_cta_{viewport}.txt").write_text(page.locator("body").inner_text())
                raise
            box = button.bounding_box()
            assert box["height"] >= 43.5, key
    finally:
        page.close()


def test_price_scenario_calculates_in_the_browser(browser):
    page = _open(browser, "prices", "en", "mobile")
    try:
        page.locator(".st-key-cta_price_calc button").click()
        page.wait_for_selector(".bn-card", timeout=30_000)
        assert page.get_by_text(TEXT["en"]["prices"]["result"]["basket_change"]).first.is_visible()
        assert page.get_by_text("+10.0%").first.is_visible()
        assert _no_horizontal_overflow(page)
    finally:
        page.close()


@pytest.mark.parametrize("viewport,lo,hi", [("desktop", 0.88, 0.97), ("xl", 0.78, 0.84)])
def test_content_width_is_wide_and_capped(browser, viewport, lo, hi):
    """About 90-95% of a 1440 px window; capped near 1600 px (minus padding) on a 1920 px window."""
    page = _open(browser, "", "en", viewport)
    try:
        box = page.evaluate("""() => { const b = document.querySelector('.block-container'); const r = b.getBoundingClientRect();
            const cs = getComputedStyle(b); return {w: r.width - parseFloat(cs.paddingLeft) - parseFloat(cs.paddingRight),
            outer: r.width, vw: window.innerWidth}; }""")
        assert lo <= box["w"] / box["vw"] <= hi, box
        assert box["outer"] <= 1601
    finally:
        page.close()


def test_mobile_navigation_items_do_not_overlap(browser):
    page = _open(browser, "", "rw", "mobile")
    try:
        boxes = [page.locator('[data-testid="stPageLink"]').nth(i).bounding_box() for i in range(4)]
        for i, a in enumerate(boxes):
            assert a["x"] >= 0 and a["x"] + a["width"] <= 391
            for b in boxes[i + 1:]:
                overlap_x = min(a["x"] + a["width"], b["x"] + b["width"]) - max(a["x"], b["x"])
                overlap_y = min(a["y"] + a["height"], b["y"] + b["height"]) - max(a["y"], b["y"])
                assert overlap_x <= 0 or overlap_y <= 0
    finally:
        page.close()


@pytest.mark.parametrize("viewport", list(VIEWPORTS))
@pytest.mark.parametrize("lang", ["en", "rw"])
def test_result_pages_with_charts_fit(browser, viewport, lang):
    """Price (by category) and support results: KPI cards and charts render without clipping or page overflow."""
    w, h = VIEWPORTS[viewport]
    page = browser.new_page(viewport={"width": w, "height": h})
    try:
        page.goto(f"{URL}/prices?lang={lang}", wait_until="domcontentloaded")
        page.wait_for_selector("h1", timeout=30_000)
        page.get_by_text(TEXT[lang]["prices"]["mode_detailed"]).first.click()
        page.wait_for_timeout(800)
        page.locator(".st-key-cta_price_calc button").click()
        page.wait_for_selector(".js-plotly-plot", timeout=30_000)
        page.wait_for_timeout(1_200)
        for name in ("prices", "compare"):
            if name == "compare":
                page.locator(".st-key-cta_to_compare button").click()
                page.wait_for_selector(".st-key-cta_compare", timeout=30_000)
                page.locator(".st-key-cta_compare button").click()
                page.wait_for_selector(".js-plotly-plot", timeout=30_000)
                page.wait_for_timeout(1_200)
            assert page.locator(".bn-card").count() >= 4
            assert page.locator(".js-plotly-plot").count() >= (2 if name == "prices" else 1)
            assert _no_horizontal_overflow(page), f"{name} overflows at {viewport}"
            for box in [page.locator(".bn-card").nth(i).bounding_box() for i in range(page.locator(".bn-card").count())]:
                assert box["x"] >= 0 and box["x"] + box["width"] <= w + 1           # no clipped cards
            if SHOTS:
                SHOTS.mkdir(parents=True, exist_ok=True)
                page.set_viewport_size({"width": w, "height": max(h, 2400)})
                page.wait_for_timeout(600)
                page.screenshot(path=str(SHOTS / f"{name}_results_{lang}_{viewport}.png"))
                page.set_viewport_size({"width": w, "height": h})
    finally:
        page.close()
