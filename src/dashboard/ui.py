"""Shared Streamlit components for Baho Neza: state, header, context, cards, geography controls, map and footer.

All words come from the i18n catalogues through `t`; this module only arranges them. Scenario inputs live in
session state under fixed keys, so the current scenario spec (and its fingerprint) can be rebuilt on any page.
"""
from __future__ import annotations

import html
import textwrap
import time

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src.dashboard import ai_service as ai
from src.dashboard import data as dd
from src.dashboard import explain as ex
from src.dashboard import logic as lg
from src.dashboard import scenario as sc
from src.dashboard import theme as th
from src.dashboard.i18n import DEFAULT_LANGUAGE, LANGUAGES, bound, current_language, t

PAGES = {
    "overview": "views/overview.py",
    "community": "views/community.py",
    "prices": "views/prices.py",
    "compare": "views/compare.py",
    "how_it_works": "views/how_it_works.py",
    "data_limits": "views/data_limits.py",
}
MAIN_NAV = ["overview", "community", "prices", "compare"]
SECONDARY_NAV = ["how_it_works", "data_limits"]
NAV_ICONS = {"overview": ":material/home:", "community": ":material/map:", "prices": ":material/trending_up:",
             "compare": ":material/balance:", "how_it_works": ":material/menu_book:", "data_limits": ":material/fact_check:"}
PLOTLY_CONFIG = {"displayModeBar": False, "scrollZoom": False, "topojsonURL": "./app/static/"}

# Scenario inputs and their defaults (set once per session, before any widget renders)
PRICE_DEFAULTS = {"price_mode": sc.DEFAULT_PRICE["mode"], "price_horizon": sc.DEFAULT_PRICE["horizon_months"],
                  "price_all": sc.DEFAULT_PRICE["all"], **{f"price_{c}": sc.DEFAULT_PRICE["all"] for c in sc.CATEGORIES}}
SUPPORT_DEFAULTS = {"sup_action": "cash", "sup_rule": sc.DEFAULT_SUPPORT["rule"], "sup_level": sc.DEFAULT_SUPPORT["level"],
                    "sup_amount": sc.DEFAULT_SUPPORT["amount_rwf"], "sup_frequency": sc.DEFAULT_SUPPORT["frequency"],
                    "sup_duration": sc.DEFAULT_SUPPORT["duration_months"], "sup_delivery": sc.DEFAULT_SUPPORT["delivery_pct"],
                    "sup_ds_level": sc.DEFAULT_SUPPORT["ds_level"],
                    "sup_ds_payment": sc.DEFAULT_SUPPORT["ds_payment_quarterly_rwf"],
                    "sup_nsds_pct": sc.DEFAULT_SUPPORT["nsds_increase_pct"]}
STATE_DEFAULTS = {"geo": lg.ALL, "area": "all", "indicator": "poverty", **PRICE_DEFAULTS, **SUPPORT_DEFAULTS}


def esc(text: str) -> str:
    """Escape text for our HTML snippets (quotes stay readable: Kinyarwanda uses apostrophes)."""
    return html.escape(text, quote=False)


# ---------------------------------------------------------------------------
# Data (cached; aggregated tables only)
# ---------------------------------------------------------------------------
@st.cache_data(show_spinner=False)
def tables() -> dict:
    return dd.load_public_tables()


@st.cache_data(show_spinner=False)
def geojson() -> dict:
    return dd.load_geojson()


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------
def init_state() -> None:
    """Language from ?lang= on first load; defaults for every shared input; keep inputs across pages."""
    if "lang" not in st.session_state:
        q = st.query_params.get("lang", DEFAULT_LANGUAGE)
        st.session_state["lang"] = q if q in LANGUAGES else DEFAULT_LANGUAGE
    for k, v in STATE_DEFAULTS.items():
        if k not in st.session_state:
            st.session_state[k] = v
        else:
            st.session_state[k] = st.session_state[k]   # keeps widget values when their page is not shown
    st.markdown(th.CSS, unsafe_allow_html=True)


def geography() -> tuple[str, str]:
    return st.session_state["geo"], st.session_state["area"]


def current_price_spec() -> dict:
    s = st.session_state
    return sc.price_spec(s["price_mode"], s["price_horizon"], s["price_all"],
                         {c: s[f"price_{c}"] for c in sc.CATEGORIES})


def current_support_spec() -> dict:
    s = st.session_state
    return sc.support_spec(s["sup_action"], rule=s["sup_rule"], level=s["sup_level"], amount_rwf=s["sup_amount"],
                           frequency=s["sup_frequency"], duration_months=s["sup_duration"], delivery_pct=s["sup_delivery"],
                           ds_level=s["sup_ds_level"], ds_payment_quarterly_rwf=s["sup_ds_payment"],
                           nsds_increase_pct=s["sup_nsds_pct"])


def reset_price_inputs() -> None:
    """No new price change: every increase back to zero (the reference basket)."""
    st.session_state.update({"price_all": 0.0, **{f"price_{c}": 0.0 for c in sc.CATEGORIES}})


def saved(name: str, fp: str) -> tuple[dict | None, str]:
    """(result, status): 'valid' when the saved fingerprint matches the inputs, 'stale' when they changed, else 'none'."""
    entry = st.session_state.get(name)
    if not entry:
        return None, "none"
    return (entry["result"], "valid") if entry["fp"] == fp else (None, "stale")


def save(name: str, fp: str, result: dict) -> None:
    st.session_state[name] = {"fp": fp, "result": result}


def price_fingerprint(spec: dict, geo: str, area: str) -> str:
    return sc.fingerprint("price", spec, geo, area)


def compare_fingerprint(price: dict, support: dict, geo: str, area: str) -> str:
    return sc.fingerprint("compare", price, support, geo, area)


# ---------------------------------------------------------------------------
# Page furniture
# ---------------------------------------------------------------------------
def _sync_language() -> None:
    st.query_params["lang"] = st.session_state["lang"]


def header() -> None:
    """Brand, the four main pages, and the language selector; then the persistent planning message."""
    brand, nav, lang = st.columns([1.5, 6.7, 1.8], vertical_alignment="center")
    brand.markdown(f'<div class="bn-brand">🌱 {esc(t("app.name"))}</div>', unsafe_allow_html=True)
    with nav:
        with st.container(horizontal=True, vertical_alignment="center", gap="small"):
            for key in MAIN_NAV:
                st.page_link(PAGES[key], label=t(f"nav.{key}"), icon=NAV_ICONS[key])
    lang.selectbox(t("lang.label"), list(LANGUAGES), key="lang", format_func=lambda c: f"🌐 {LANGUAGES[c]}",
                   label_visibility="collapsed", on_change=_sync_language)
    st.markdown(f'<p class="bn-note">ⓘ {esc(t("app.persistent"))}</p>', unsafe_allow_html=True)


def page_title(prefix: str) -> None:
    st.title(t(f"{prefix}.title"))
    st.markdown(f'<p class="bn-note">{esc(t(f"{prefix}.question"))}</p>', unsafe_allow_html=True)


def scenario_label(price: dict, meta: dict) -> str:
    base = lg.fmt_month(meta["latest_cpi_month"], current_language())
    if price["mode"] == "simple":
        return t("scenario.label_simple", pct=f"{price['increases']['food']:g}", months=price["horizon_months"], base=base)
    return t("scenario.label_detailed", months=price["horizon_months"], base=base)


def chips(pairs: list[tuple[str, str]]) -> None:
    """A compact row of 'label: value' chips (wraps on narrow screens)."""
    body = "".join(f"<span>{esc(k)}: <b>{esc(v)}</b></span>" for k, v in pairs)
    st.markdown(f'<div class="bn-context">{body}</div>', unsafe_allow_html=True)


def context(meta: dict, geo: str | None = None, area: str | None = None, price: dict | None = None) -> None:
    """Compact context chips: geography, survey period, latest CPI month and (optionally) the price scenario."""
    lang = current_language()
    pairs = []
    if geo is not None:
        pairs.append((t("context.geography"), lg.geography_label(geo, area, lang)))
    pairs.append((t("context.survey"), lg.survey_period(meta, lang)))
    pairs.append((t("context.cpi"), lg.fmt_month(meta["latest_cpi_month"], lang)))
    if price is not None:
        pairs.append((t("context.scenario"), scenario_label(price, meta)))
    chips(pairs)


def result_sentence(text: str) -> None:
    """The one short deterministic sentence that states the main result."""
    st.markdown(f'<p class="bn-result">{plain(text)}</p>', unsafe_allow_html=True)


def source_tag(source: str) -> str:
    bg, ink, icon = th.SOURCE_TAGS[source]
    return (f'<span class="bn-tag" style="background:{bg};color:{ink}">'
            f'<span aria-hidden="true">{icon}</span>{esc(t(f"source.{source}"))}</span>')


def kpi_card(label: str, value: str, sub: str = "", source: str | None = None) -> str:
    sub_html = f'<div class="sub">{esc(sub)}</div>' if sub else ""
    tag = source_tag(source) if source else ""
    return (f'<div class="bn-card"><div class="label">{esc(label)}</div>'
            f'<div class="value">{esc(value)}</div>{sub_html}{tag}</div>')


def text_card(title: str, body: str) -> str:
    return f'<div class="bn-card"><h3>{esc(title)}</h3><p>{esc(body)}</p></div>'


def card_row(cards: list[str]) -> None:
    for col, c in zip(st.columns(len(cards)), cards):
        col.markdown(c, unsafe_allow_html=True)


def rows_html(rows: list[tuple[str, str, str]]) -> str:
    """Label / value / optional interval rows for side panels."""
    out = []
    for k, v, ci in rows:
        ci_html = f'<span class="ci">{esc(ci)}</span>' if ci else ""
        out.append(f'<div class="bn-row"><span class="k">{esc(k)}</span>'
                   f'<span class="v">{esc(v)}{ci_html}</span></div>')
    return "".join(out)


def html_table(headers: list[str], rows: list[list[str]]) -> None:
    head = "".join(f'<th scope="col">{esc(h)}</th>' for h in headers)
    body = "".join("<tr>" + "".join(f"<td>{esc(c)}</td>" for c in r) + "</tr>" for r in rows)
    st.markdown(f'<div class="bn-table-wrap"><table class="bn-table"><thead><tr>{head}</tr></thead>'
                f"<tbody>{body}</tbody></table></div>", unsafe_allow_html=True)


def stale_box(key: str) -> None:
    st.markdown(f'<div class="bn-stale" role="status">⚠ {esc(t(key))}</div>', unsafe_allow_html=True)


def disclaimer(key: str) -> None:
    st.caption(f"ⓘ {t(key)}")


def footer() -> None:
    st.divider()
    left, right = st.columns([3, 1.4])
    left.markdown(f'<div class="bn-footer">{esc(t("footer.credits"))}</div>', unsafe_allow_html=True)
    with right:
        for key in SECONDARY_NAV:
            st.page_link(PAGES[key], label=t(f"nav.{key}"), icon=NAV_ICONS[key])


# ---------------------------------------------------------------------------
# Geography controls (values are codes; labels are translated)
# ---------------------------------------------------------------------------
def geo_controls(groups: pd.DataFrame, cols=None) -> tuple[str, str]:
    options = [lg.ALL] + lg.district_names(groups)
    tl = bound()
    if st.session_state.get("geo") not in options:
        st.session_state["geo"] = lg.ALL
    c1, c2 = cols if cols is not None else st.columns(2)
    c1.selectbox(t("geo.label"), options, key="geo", format_func=lambda d: tl("geo.rwanda") if d == lg.ALL else d)
    c2.selectbox(t("area.label"), sc.AREAS, key="area", format_func=lambda a: tl(f"area.{a}"))
    return geography()


# ---------------------------------------------------------------------------
# Map
# ---------------------------------------------------------------------------
def indicator_map(view: pd.DataFrame, indicator: str, zrange: tuple[float, float], hover: list[str],
                  highlight: str | None, height: int = 500) -> go.Figure:
    """Districts filled on one fixed scale per indicator; hidden districts in grey (hover says why)."""
    ind = lg.INDICATORS[indicator]
    scale = th.PRESSURE_SCALE if ind.higher_is_worse else th.COVERAGE_SCALE
    factor = 100 if ind.kind == "share" else 1
    z = view[ind.column].astype(float).to_numpy()
    sel = view["geo"].eq(highlight).to_numpy()
    hover = np.asarray(hover, dtype=object)
    fig = go.Figure()
    for missing in (True, False):
        m = np.isnan(z) == missing
        if not m.any():
            continue
        line = dict(color=np.where(sel[m], th.TEXT, th.CARD).tolist(), width=np.where(sel[m], 3.5, 1).tolist())
        common = dict(geojson=geojson(), featureidkey="properties.shapeName", locations=view.loc[m, "geo"],
                      marker_line=line, text=hover[m].tolist(), hovertemplate="%{text}<extra></extra>")
        if missing:
            fig.add_trace(go.Choropleth(z=np.zeros(m.sum()), colorscale=[[0, th.MISSING], [1, th.MISSING]],
                                        showscale=False, **common))
        else:
            fig.add_trace(go.Choropleth(
                z=z[m] * factor, zmin=zrange[0] * factor, zmax=zrange[1] * factor, colorscale=scale, **common,
                colorbar=dict(title=dict(text=t(f"indicator.{indicator}.unit"), side="right"), ticksuffix="%",
                              thickness=12, len=0.8, outlinewidth=0)))
    fig.update_geos(fitbounds="locations", visible=False, projection_type="mercator", bgcolor="rgba(0,0,0,0)")
    fig.update_layout(height=height, margin=dict(l=0, r=0, t=0, b=0), paper_bgcolor="rgba(0,0,0,0)", dragmode=False,
                      hoverlabel=dict(bgcolor=th.CARD, font_color=th.TEXT, bordercolor=th.BORDER))
    return fig


def _wrap(label: str, width: int = 22) -> str:
    """Break long chart labels (Kinyarwanda labels are often longer) so bars keep room on narrow screens."""
    return "<br>".join(textwrap.wrap(label, width)) or label


def hbar(rows: list[tuple], axis_title: str, height: int | None = None) -> go.Figure:
    """Horizontal bars, top to bottom, each labelled with its formatted value (colour is never the only cue).
    rows: (label, value or None for a hidden/missing value, colour, text beside the bar[, extra hover text])."""
    labels = [_wrap(r[0]) for r in rows]
    values = [r[1] if r[1] is not None else 0 for r in rows]
    fig = go.Figure(go.Bar(
        y=labels, x=values, orientation="h", marker=dict(color=[r[2] for r in rows], line=dict(width=0)),
        text=[r[3] for r in rows], textposition="auto", cliponaxis=False, insidetextanchor="end",
        insidetextfont=dict(color=[th.TEXT if r[2] in (th.ATTENTION, th.MISSING, "#7FB8B1") else th.CARD for r in rows]),
        outsidetextfont=dict(color=th.TEXT), hovertext=[f"{r[0]}: {r[3]}" + (f"<br>{r[4]}" if len(r) > 4 and r[4] else "") for r in rows],
        hoverinfo="text"))
    top = max([v for v in values if v] or [1])
    fig.update_xaxes(title=dict(text=_wrap(axis_title, 40), font=dict(size=13, color=th.TEXT2)), range=[0, top * 1.6],
                     showgrid=True, gridcolor=th.BORDER, zeroline=True, zerolinecolor=th.BORDER, tickfont=dict(color=th.TEXT2))
    fig.update_yaxes(autorange="reversed", tickfont=dict(size=14, color=th.TEXT), automargin=True)
    fig.update_layout(height=height or 70 + 46 * len(rows), margin=dict(l=8, r=16, t=8, b=8), bargap=0.35,
                      paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", showlegend=False,
                      font=dict(size=14, color=th.TEXT), hoverlabel=dict(bgcolor=th.CARD, font_color=th.TEXT,
                                                                        bordercolor=th.BORDER))
    return fig


def show(fig: go.Figure, key: str) -> None:
    st.plotly_chart(fig, width="stretch", config=PLOTLY_CONFIG, key=key)


def map_legend() -> None:
    st.markdown(f'<div class="bn-legend"><span><span class="bn-swatch" style="background:{th.MISSING}"></span>'
                f'{esc(t("map.legend_missing"))}</span>'
                f'<span><span class="bn-swatch" style="border:3px solid {th.TEXT}"></span>'
                f'{esc(t("map.legend_selected"))}</span></div>', unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Plain-language explanation (deterministic, plus optional AI-assisted wording)
# ---------------------------------------------------------------------------
def plain(text: str) -> str:
    """Untrusted or user-facing text for our HTML snippets: no HTML and no Markdown formatting survive."""
    out = esc(text)
    for ch in "*_#~[]`|":
        out = out.replace(ch, f"&#{ord(ch)};")
    return out


def _explanation_sections(sections: dict[str, str]) -> None:
    body = "".join(f'<div class="bn-explain"><h4>{esc(t(f"explain.section.{s}"))}</h4><p>{plain(sections[s])}</p></div>'
                   for s in ex.SECTIONS if sections.get(s))
    st.markdown(body, unsafe_allow_html=True)


def request_ai_explanation(kind: str, fp: str) -> None:
    """Called when the user asks for results: generate the AI explanation once for this result (if configured)."""
    st.session_state["ai_autorun"] = (kind, fp)


def explanation_panel(kind: str, result: dict, fp: str, meta: dict, price_label: str = "") -> None:
    """A visible AI box under the results, then the deterministic explanation collapsed below it.

    The AI explanation is bound to (kind, result fingerprint, language), so it never appears under other settings.
    It is generated once when the user asks for results (Show results / Compare) or clicks "Explain simply";
    never on page load, slider changes or reruns. Without configuration the button stays visible but disabled."""
    lang = current_language()
    facts = ex.build_facts(kind, result, meta, lang, price_label)
    state = st.session_state.setdefault("ai_state", {})
    key = (kind, fp, lang)
    done = state.get("done", {}).get(key)
    autorun = st.session_state.get("ai_autorun") == (kind, fp)
    if autorun:
        st.session_state.pop("ai_autorun", None)
    status, cfg = ai.load_config()
    with st.container(border=True, key=f"ai_{kind}"):
        head, action = st.columns([3, 1.2], vertical_alignment="center")
        head.markdown(f"**✦ {t('explain.ai_title')}**")
        clicked = action.button(t("explain.button"), key=f"cta_explain_{kind}", icon=":material/auto_awesome:",
                                disabled=status != "ready" or done is not None, width="stretch")
        if status != "ready":
            st.caption(t("explain.not_configured"))
            if autorun:
                ai.log_config_status()          # server log only: which setting is missing (booleans, no values)
        elif done is None and (clicked or autorun):
            with st.spinner(t("explain.loading")):
                done, err = ai.request_explanation(kind, result, facts, fp, lang, cfg, state, time.time())
            state["error"] = None if done else (key, err)
            if done:
                st.rerun()          # redraw with the button disabled; the rerun reads the stored text, no new request
        error = state.get("error")
        if done:
            st.markdown(f'<div class="bn-ai-label">✦ {esc(t("explain.ai_label"))}</div>', unsafe_allow_html=True)
            _explanation_sections(done)
            st.caption(t("explain.ai_note"))
        elif error and error[0] == key:
            st.caption(f"{t(f'explain.error.{error[1]}')} {t('explain.fallback')}")
    with st.expander(t("explain.title"), icon=":material/chat_info:"):
        _explanation_sections(ex.deterministic_sections(kind, result, facts, lang))


def explanation_unavailable(kind: str) -> None:
    """No valid result: the button stays visible but disabled."""
    st.button(t("explain.button"), key=f"cta_explain_{kind}_off", icon=":material/auto_awesome:", disabled=True,
              help=t("explain.needs_results"))
