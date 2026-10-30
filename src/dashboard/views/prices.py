"""What if prices rise? Price-change scenario on top of the latest observed CPI month."""
import streamlit as st

from src.dashboard import logic as lg
from src.dashboard import scenario as sc
from src.dashboard import theme as th
from src.dashboard import ui
from src.dashboard.i18n import bound, current_language, t

tab = ui.tables()
groups, meta = tab["groups"], tab["meta"]
lang = current_language()
tl = bound(lang)                  # widget labels, fixed to the language of this run
latest = lg.fmt_month(meta["latest_cpi_month"], lang)

ui.page_title("prices")

# Controls in one compact row: place, area, period and how prices change; then the increases
c1, c2, c3, c4 = st.columns(4)
geo, area = ui.geo_controls(groups, (c1, c2))
c3.select_slider(t("prices.horizon"), sc.HORIZONS, key="price_horizon", format_func=lambda m: tl("units.months", n=m))
c4.radio(t("prices.mode"), sc.PRICE_MODES, key="price_mode", format_func=lambda m: tl(f"prices.mode_{m}"))
if st.session_state["price_mode"] == "simple":
    st.slider(t("prices.all_increase"), 0.0, 50.0, step=1.0, key="price_all", format="%.0f%%")
else:
    for col, c in zip(st.columns(len(sc.CATEGORIES)), sc.CATEGORIES):
        col.slider(t(f"prices.increase.{c}"), 0.0, 50.0, step=1.0, key=f"price_{c}", format="%.0f%%",
                   help=t(f"category.{c}_help"))
st.caption(f"{t('ux.prices.controls_note', latest=latest)} {t('ux.prices.earnings_note')}")

spec = ui.current_price_spec()
fp = ui.price_fingerprint(spec, geo, area)
if st.button(t("prices.calculate"), key="cta_price_calc", type="primary", icon=":material/calculate:"):
    try:
        ui.save("saved_price", fp, sc.price_result(groups, geo, area, spec))
        ui.request_ai_explanation("price", fp)       # AI explains these results right away, if configured
    except sc.UnsupportedScenario as e:
        ui.save("saved_price", fp, {"error": e.code})
result, status = ui.saved("saved_price", fp)

if status == "stale":
    ui.stale_box("state.stale_price")
elif status == "none":
    st.info(t("prices.prompt"), icon=":material/touch_app:")
elif "error" in result:
    st.warning(t(f"errors.{result['error']}"), icon=":material/visibility_off:")
if status != "valid" or "error" in result:
    ui.explanation_unavailable("price")
else:
    inc = spec["increases"]
    ui.chips([
        (t("context.geography"), lg.geography_label(geo, area, lang)),
        (t("ux.prices.chip_period"), t("ux.prices.chip_period_value", months=spec["horizon_months"], latest=latest)),
        (t("ux.prices.chip_prices"), t("ux.prices.chip_simple", pct=f"{inc['food']:g}") if spec["mode"] == "simple"
         else t("ux.prices.chip_detailed")),
        (t("ux.prices.chip_incomes"), t("ux.prices.chip_incomes_value")),
    ])
    ui.card_row([
        ui.kpi_card(t("prices.result.basket_change"), lg.fmt_percent(result["basket_change_pct"], signed=True),
                    t("prices.result.basket_change_sub"), "scenario"),
        ui.kpi_card(t("prices.result.extra_monthly"), lg.fmt_rwf(result["extra_monthly"], lang),
                    t("prices.result.extra_monthly_sub", ref=lg.fmt_rwf(result["reference_monthly"], lang)), "scenario"),
        ui.kpi_card(t("prices.result.purchasing_power"), lg.fmt_percent(result["purchasing_power_change_pct"], signed=True),
                    t("prices.result.purchasing_power_sub"), "scenario"),
        ui.kpi_card(t("prices.result.extra_total"), lg.fmt_rwf(result["extra_monthly_total"], lang),
                    t("prices.result.extra_total_sub", households=lg.fmt_count(result["households"])), "scenario"),
    ])
    ui.result_sentence(t("ux.prices.sentence", change=lg.fmt_percent(result["basket_change_pct"]),
                         extra=lg.fmt_rwf(result["extra_monthly"], lang)))

    left, right = st.columns(2, gap="large")
    with left:
        st.markdown(f"**{t('ux.prices.chart_before_after')}**")
        ui.show(ui.hbar([
            (t("ux.prices.chart_today", latest=latest), result["reference_monthly"], th.PRIMARY,
             lg.fmt_rwf(result["reference_monthly"], lang)),
            (t("ux.prices.chart_scenario"), result["scenario_monthly"], th.ELEVATED, lg.fmt_rwf(result["scenario_monthly"], lang)),
        ], t("ux.prices.axis_monthly")), key="chart_price_before_after")
    with right:
        st.markdown(f"**{t('ux.prices.chart_contrib')}**")
        order = sorted(sc.CATEGORIES, key=lambda c: -result["extra_by_category"][c])
        ui.show(ui.hbar([(f"{t(f'category.{c}')} (+{inc[c]:g}%)", result["extra_by_category"][c], th.ATTENTION,
                          f"+{lg.fmt_rwf(result['extra_by_category'][c], lang)}") for c in order],
                        t("ux.prices.axis_extra")), key="chart_price_contrib")

    with st.expander(t("ux.prices.details_title"), icon=":material/table:"):
        ui.html_table([t("prices.table.category"), t("prices.table.reference"), t("prices.table.increase"), t("prices.table.extra")],
                      [[t(f"category.{c}"), lg.fmt_rwf(result["reference_by_category"][c], lang), f"+{inc[c]:g}%",
                        lg.fmt_rwf(result["extra_by_category"][c], lang)] for c in sc.CATEGORIES])
        st.markdown(f"**{t('prices.exposed_title')}**")
        exposed = result["exposed"]
        if exposed:
            ui.html_table([t("community.groups.group"), t("prices.result.basket_change"), t("prices.result.extra_monthly")],
                          [[t(f"group.{g['dimension']}.{g['group']}"), lg.fmt_percent(g["basket_change_pct"], signed=True),
                            lg.fmt_rwf(g["extra_monthly"], lang)] for g in exposed])
            st.caption(t("prices.exposed_uniform") if spec["mode"] == "simple" else t("prices.exposed_note"))
        else:
            st.caption(t("errors.suppressed"))
    ui.explanation_panel("price", result, fp, meta)
    if st.button(t("prices.to_compare"), key="cta_to_compare", icon=":material/arrow_forward:"):
        st.switch_page(ui.PAGES["compare"])

with st.expander(t("ux.prices.assumptions_title"), icon=":material/rule:"):
    st.markdown(t("ux.prices.assumptions", latest=latest, base=lg.fmt_month(meta["price_base_month"], lang)))
ui.disclaimer("prices.not_forecast")
