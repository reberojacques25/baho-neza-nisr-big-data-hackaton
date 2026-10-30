"""Our community: where is support needed? Map, summary panel, findings, group comparisons, support gaps, brief."""
import pandas as pd
import streamlit as st

from src.dashboard import brief
from src.dashboard import logic as lg
from src.dashboard import scenario as sc
from src.dashboard import theme as th
from src.dashboard import ui
from src.dashboard.i18n import bound, current_language, t

tab = ui.tables()
groups, planning, meta = tab["groups"], tab["planning"], tab["meta"]
lang = current_language()
tl = bound(lang)                  # widget labels, fixed to the language of this run

ui.page_title("community")
c1, c2, c3 = st.columns(3)
geo, area = ui.geo_controls(groups, (c1, c2))
indicator = c3.selectbox(t("community.indicator"), lg.MAP_INDICATORS, key="indicator",
                         format_func=lambda k: tl(f"indicator.{k}.name"))
ui.context(meta, geo, area)

ind = lg.INDICATORS[indicator]
view = lg.district_view(groups, area)
row = lg.overall(groups, geo, area)
hidden_text = t("common.hidden")


def value_and_ci(r: pd.Series, col: str, kind: str, hn: bool = False) -> tuple[str, str]:
    if bool(r["high_need_suppressed" if hn else "suppressed"]) or pd.isna(r[col]):
        return hidden_text, ""
    return lg.fmt_value(r[col], kind), t("common.ci", ci=lg.fmt_interval(r[f"{col}_ci_low"], r[f"{col}_ci_high"], kind))


hn_indicator = indicator == "coverage"
hover = []
for _, r in view.iterrows():
    v, ci = value_and_ci(r, ind.column, ind.kind, hn_indicator)
    hover.append(f"<b>{r['geo']}</b><br>{t(f'indicator.{indicator}.name')}: {v}" + (f"<br>{ci}" if ci else ""))

left, right = st.columns([70, 30], gap="medium")
with left:
    ui.show(ui.indicator_map(view, indicator, lg.map_range(groups, indicator), hover, geo if geo != lg.ALL else None,
                             height=600), key=f"map_{indicator}_{area}")
    ui.map_legend()
    if indicator == "price":
        st.caption(t("community.price_note"))
    with st.expander(t("ux.community.indicator_about"), icon=":material/info:"):
        st.markdown(t(f"indicator.{indicator}.help"))
with right:
    with st.container(border=True):
        st.markdown(f"**{lg.geography_label(geo, area, lang)}**")
        panel = []
        for key in lg.MAP_INDICATORS:
            i = lg.INDICATORS[key]
            v, ci = value_and_ci(row, i.column, i.kind, key == "coverage")
            panel.append((f"{t(f'indicator.{key}.name')} · {t(f'source.{i.source}')}", v, ci))
        gap_v = hidden_text if row["high_need_suppressed"] else lg.fmt_count(row["protection_gap_households"])
        panel.append((t("community.gap_households"), gap_v, ""))
        st.markdown(ui.rows_html(panel), unsafe_allow_html=True)
        if geo != lg.ALL:
            rr = lg.rank_range(view, indicator, geo)
            if rr:
                best, worst, n = rr
                st.caption(t("community.rank", name=t(f"indicator.{indicator}.name"), best=best, worst=worst, n=n)
                           if best != worst else t("community.rank_exact", name=t(f"indicator.{indicator}.name"), rank=best, n=n))
        st.caption(t("community.panel_note"))

with st.expander(t("community.table_view")):
    ui.html_table([t("geo.district"), t(f"indicator.{indicator}.name"), t("common.ci_header")],
                  [[r["geo"], *value_and_ci(r, ind.column, ind.kind, hn_indicator)] for _, r in view.iterrows()])

f_col, g_col = st.columns(2, gap="large")
with f_col:
    st.subheader(t("community.findings_title"))
    found = lg.findings(groups, geo, area, lang)
    st.markdown("\n".join(f"- {f}" for f in found) if found else t("finding.none"))
    st.caption(t("community.findings_note"))

cmp = lg.group_comparisons(groups, geo, area)
with g_col:
    st.subheader(t("community.groups_title"))
    st.markdown(f"**{t('ux.community.groups_chart')}**")
    bars = []
    for _, r in cmp.iterrows():
        label = t(f"group.{r['dimension']}.{r['group']}")
        if r["suppressed"]:
            bars.append((label, None, th.MISSING, hidden_text))
        else:
            ci = t("common.ci", ci=lg.fmt_interval(r["poverty_rate_ci_low"], r["poverty_rate_ci_high"], "share"))
            bars.append((label, 100 * r["poverty_rate"], th.PRIMARY, lg.fmt_share(r["poverty_rate"]), ci))
    ui.show(ui.hbar(bars, t("ux.community.groups_axis")), key=f"chart_groups_{geo}_{area}")
    for note in lg.comparison_note(cmp, lang):
        st.markdown(f"- {note}")

with st.expander(t("ux.community.groups_table"), icon=":material/table:"):
    rows = []
    for _, r in cmp.iterrows():
        cells = [t(f"group.{r['dimension']}.{r['group']}")]
        if r["suppressed"]:
            cells += [hidden_text] * 5
        else:
            cells.append(lg.fmt_count(r["households"]))
            for col, kind in lg.COMPARISON_COLUMNS.items():
                hn = col == "high_need_vup_coverage"
                cells.append(hidden_text if (hn and r["high_need_suppressed"]) else lg.fmt_value(r[col], kind))
        rows.append(cells)
    ui.html_table([t("community.groups.group"), t("community.groups.households"), t("brief.indicator.poverty_rate"),
                   t("indicator.need.name"), t("indicator.coverage.name"), t("indicator.price.name")], rows)
    st.caption(t("community.groups_note"))

st.subheader(t("community.gaps_title"))
if row["high_need_suppressed"]:
    st.info(t("errors.suppressed"), icon=":material/visibility_off:")
else:
    ui.card_row([
        ui.kpi_card(t("community.gap_households"), lg.fmt_count(row["protection_gap_households"]),
                    t("common.ci", ci=lg.fmt_interval(row["protection_gap_households_ci_low"],
                                                      row["protection_gap_households_ci_high"], "count")), "survey"),
        ui.kpi_card(t("community.gap_share"), lg.fmt_share(1 - row["high_need_vup_coverage"]),
                    t("community.gap_share_sub", total=lg.fmt_count(row["high_need_households"])), "survey"),
        ui.kpi_card(t("indicator.coverage.name"), lg.fmt_share(row["high_need_vup_coverage"]),
                    t("common.ci", ci=lg.fmt_interval(row["high_need_vup_coverage_ci_low"],
                                                      row["high_need_vup_coverage_ci_high"], "share")), "survey"),
    ])
    with st.expander(t("community.predicted_title")):
        nat = lg.overall(groups, lg.ALL, area)
        ui.html_table([t("community.predicted.measure"), lg.geography_label(geo, area, lang), lg.geography_label(lg.ALL, area, lang)], [
            [t("community.predicted.observed"), lg.fmt_share(row["high_need_vup_coverage"]), lg.fmt_share(nat["high_need_vup_coverage"])],
            [t("community.predicted.predicted"), lg.fmt_share(row["predicted_coverage_high_need"]),
             lg.fmt_share(nat["predicted_coverage_high_need"])],
        ])
        st.markdown(t("community.predicted_body"))
ui.disclaimer("community.gaps_note")

# District planning brief: includes a scenario only when its saved result matches the current inputs and geography
st.subheader(t("brief.title"))
price_res, price_status = ui.saved("saved_price", ui.price_fingerprint(ui.current_price_spec(), geo, area))
try:
    cmp_fp = ui.compare_fingerprint(ui.current_price_spec(), ui.current_support_spec(), geo, area)
    cmp_res, _ = ui.saved("saved_compare", cmp_fp)
except sc.UnsupportedScenario:
    cmp_res = None
if cmp_res is not None and "error" in cmp_res:
    cmp_res = None
rows = brief.brief_rows(groups, meta, geo, area, lang, price=price_res, comparison=cmp_res)
st.caption(t("brief.includes_scenario") if price_res else t("brief.excludes_scenario"))
with st.container(horizontal=True, gap="small"):
    st.download_button(t("brief.download_csv"), brief.brief_csv(rows, lang), key="cta_brief_csv",
                       file_name=brief.brief_filename(geo, area, lang, "csv"), mime="text/csv", icon=":material/download:")
    st.download_button(t("brief.download_pdf"), brief.brief_pdf(rows, lang), key="cta_brief_pdf",
                       file_name=brief.brief_filename(geo, area, lang, "pdf"), mime="application/pdf",
                       icon=":material/picture_as_pdf:")
