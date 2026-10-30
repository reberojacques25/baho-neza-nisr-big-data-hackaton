"""Overview: headline, two calls to action, four national figures and the three-step flow."""
import streamlit as st

from src.dashboard import logic as lg
from src.dashboard import ui
from src.dashboard.i18n import current_language, t

tab = ui.tables()
groups, meta = tab["groups"], tab["meta"]
lang = current_language()
fig = lg.overview_figures(groups)

ui.page_title("overview")
with st.container(horizontal=True, gap="small"):
    if st.button(t("overview.cta_explore"), key="cta_explore", type="primary", icon=":material/map:"):
        st.switch_page(ui.PAGES["community"])
    if st.button(t("overview.cta_prices"), key="cta_prices", icon=":material/trending_up:"):
        st.switch_page(ui.PAGES["prices"])
ui.context(meta)

base, latest = lg.fmt_month(meta["price_base_month"], lang), lg.fmt_month(meta["latest_cpi_month"], lang)
ui.card_row([
    ui.kpi_card(t("overview.kpi.basket.label"), lg.fmt_percent(fig["basket_change_pct"], signed=True),
                t("overview.kpi.basket.sub", base=base, latest=latest), "survey"),
    ui.kpi_card(t("overview.kpi.poverty.label"), lg.fmt_share(fig["poverty_rate"]), t("overview.kpi.poverty.sub"), "survey"),
    ui.kpi_card(t("overview.kpi.gap.label"), lg.fmt_count(fig["gap_households"]),
                t("overview.kpi.gap.sub", share=lg.fmt_share(fig["gap_share"]), total=lg.fmt_count(fig["high_need_households"])),
                "survey"),
    ui.kpi_card(t("overview.kpi.basket_cost.label"), lg.fmt_rwf(fig["reference_monthly"], lang),
                t("overview.kpi.basket_cost.sub", latest=latest), "survey"),
])

steps = [t("overview.flow.understand"), t("overview.flow.test"), t("overview.flow.compare")]
arrow = '<span class="arrow" aria-hidden="true">→</span>'
st.markdown('<div class="bn-flow">' + arrow.join(f'<span class="step">{i}. {ui.esc(s)}</span>'
                                                 for i, s in enumerate(steps, start=1)) + "</div>", unsafe_allow_html=True)
