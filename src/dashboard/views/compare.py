"""Compare support: what response could help, and what would it cost? Reference | shock only | shock + support."""
import pandas as pd
import streamlit as st

from src.dashboard import logic as lg
from src.dashboard import scenario as sc
from src.dashboard import theme as th
from src.dashboard import ui
from src.dashboard.i18n import bound, current_language, t

tab = ui.tables()
groups, planning, meta = tab["groups"], tab["planning"], tab["meta"]
lang = current_language()
tl = bound(lang)                  # widget labels, fixed to the language of this run
latest = lg.fmt_month(meta["latest_cpi_month"], lang)

ui.page_title("compare")
c1, c2 = st.columns(2)
geo, area = ui.geo_controls(groups, (c1, c2))
price = ui.current_price_spec()

# Carried price scenario, with edit and reset, in one row
with st.container(horizontal=True, vertical_alignment="center", gap="small"):
    ui.chips([(t("ux.compare.chip_prices"), ui.scenario_label(price, meta))])
    st.page_link(ui.PAGES["prices"], label=t("compare.edit_price"), icon=":material/edit:")
    st.button(t("compare.reset_price"), key="cta_reset_price", on_click=ui.reset_price_inputs, icon=":material/restart_alt:")

# Programme and its inputs
st.radio(t("compare.action"), sc.ACTIONS, key="sup_action", format_func=lambda a: tl(f"action.{a}.name"), horizontal=True)
action = st.session_state["sup_action"]
st.caption(t(f"action.{action}.help"))
c1, c2, c3 = st.columns(3)
if action == "cash":
    rule = c1.selectbox(t("compare.rule"), list(sc.RULES), key="sup_rule", format_func=lambda r: tl(f"rule.{r}.name"))
    if st.session_state["sup_level"] not in sc.RULES[rule]:
        st.session_state["sup_level"] = sc.RULES[rule][0]
    c1.selectbox(t("compare.level"), sc.RULES[rule], key="sup_level", disabled=len(sc.RULES[rule]) == 1,
                 format_func=lambda v: tl("compare.level_all") if v == 100 else tl("compare.level_share", pct=v))
    c2.number_input(t("compare.amount"), min_value=0, max_value=1_000_000, step=1_000, key="sup_amount",
                    help=t("compare.amount_help"))
    c2.radio(t("compare.frequency"), list(sc.FREQUENCIES), key="sup_frequency", horizontal=True,
             format_func=lambda f: tl(f"frequency.{f}"))
elif action == "ds_expansion":
    c1.selectbox(t("compare.ds_level"), sc.DS_LEVELS, key="sup_ds_level", format_func=lambda v: tl("compare.ds_level_value", pp=v))
    c2.number_input(t("compare.ds_payment"), min_value=0, max_value=1_000_000, step=500, key="sup_ds_payment",
                    help=t("compare.ds_payment_help", sim=lg.fmt_rwf(meta["payments"]["ds_simulation_assumption_quarterly_rwf"], lang),
                           median=lg.fmt_rwf(meta["payments"]["ds_observed_median_annual_rwf"], lang)))
else:
    c1.slider(t("compare.nsds_pct"), 0.0, 100.0, step=5.0, key="sup_nsds_pct", format="%.0f%%")
    c2.caption(t("compare.nsds_note"))
c3.selectbox(t("compare.duration"), sc.DURATIONS, key="sup_duration", format_func=lambda m: tl("units.months", n=m))
c3.number_input(t("compare.delivery"), min_value=0.0, max_value=100.0, step=0.5, key="sup_delivery",
                help=t("compare.delivery_help"))
with st.expander(t("compare.unavailable_title"), icon=":material/block:"):
    for a in sc.UNAVAILABLE_ACTIONS:
        st.markdown(f"- **{t(f'action.{a}.name')}**: {t(f'action.{a}.why')}")

try:
    support = ui.current_support_spec()
    fp = ui.compare_fingerprint(price, support, geo, area)
except sc.UnsupportedScenario as e:     # keep the controls usable; never stop the page before the user can fix inputs
    st.warning(t(f"errors.{e.code}"))
    support = fp = None

if st.button(t("compare.run"), key="cta_compare", type="primary", icon=":material/balance:", disabled=fp is None):
    try:
        ui.save("saved_compare", fp, sc.compare(planning, geo, area, price, support))
        ui.request_ai_explanation("compare", fp)       # AI explains these results right away, if configured
    except sc.UnsupportedScenario as e:
        ui.save("saved_compare", fp, {"error": e.code})
result, status = ui.saved("saved_compare", fp) if fp else (None, "stale" if st.session_state.get("saved_compare") else "none")

if status == "stale":
    ui.stale_box("state.stale_compare")
elif status == "none":
    st.info(t("compare.prompt"), icon=":material/touch_app:")
elif "error" in result:
    st.warning(t(f"errors.{result['error']}"), icon=":material/visibility_off:")
if status != "valid" or "error" in result:
    ui.explanation_unavailable("compare")
else:
    s = result["support"]
    existing = s["action"] == "nsds_increase"
    if s["action"] == "cash":
        group = t("compare.group_cash", rule=t(f"rule.{s['rule']}.name"),
                  level=t("compare.level_all") if s["level"] == 100 else t("compare.level_share", pct=s["level"]))
        payment = t("compare.payment_cash", amount=lg.fmt_rwf(s["amount_rwf"], lang), frequency=t(f"frequency.{s['frequency']}"))
    elif s["action"] == "ds_expansion":
        group = t("compare.group_ds", pp=s["level"])
        payment = t("compare.payment_ds", amount=lg.fmt_rwf(s["payment_quarterly_rwf"], lang))
    else:
        group = t("compare.group_nsds")
        payment = t("compare.payment_nsds", pct=f"{s['increase_pct']:g}", amount=lg.fmt_rwf(result["amount_per_payment"], lang))
    ui.chips([
        (t("ux.compare.chip_programme"), t(f"action.{s['action']}.name")),
        (t("context.geography"), lg.geography_label(geo, area, lang)),
        (t("ux.compare.chip_payment"), payment),
        (t("ux.compare.chip_duration"), t("ux.compare.chip_duration_value", months=s["duration_months"], payments=result["payments"])),
        (t("compare.scope.group"), group),
    ])
    if result["scope"] == "national_rule" and geo != lg.ALL:
        st.info(t("compare.national_rule_note"), icon=":material/public:")

    col = result["columns"]["shock_support"]
    surplus = result["surplus_monthly"]
    households = result["recipient_households"] if existing else result["new_recipient_households"]
    people = result["recipient_people"] if existing else result["new_recipient_people"]
    poor = lg.fmt_count(result["poor_households"])
    delivery = s["delivery_pct"] > 0
    ui.card_row([
        ui.kpi_card(t("ux.compare.kpi_existing" if existing else "ux.compare.kpi_new"), lg.fmt_count(households),
                    t("ux.compare.kpi_existing_sub" if existing else "ux.compare.kpi_new_sub", poor=poor), "scenario"),
        ui.kpi_card(t("ux.compare.kpi_people"), lg.fmt_count(people),
                    t("ux.compare.kpi_people_sub_existing" if existing else "ux.compare.kpi_people_sub_new"), "scenario"),
        ui.kpi_card(t("ux.compare.kpi_cost"), lg.fmt_rwf(result["total_cost"], lang),
                    t("ux.compare.kpi_cost_sub", months=s["duration_months"], transfers=lg.fmt_rwf(result["direct_transfers"], lang),
                      delivery=lg.fmt_rwf(result["delivery_costs"], lang)) if delivery
                    else t("ux.compare.kpi_cost_sub_none", months=s["duration_months"]), "scenario"),
        ui.kpi_card(t("ux.compare.kpi_remaining"), lg.fmt_rwf(col["not_offset"], lang),
                    t("ux.compare.kpi_remaining_surplus_sub", surplus=lg.fmt_rwf(surplus, lang)) if surplus > 0
                    else t("ux.compare.kpi_remaining_sub"), "scenario"),
    ])
    kind = ("existing" if existing else "new") + ("_surplus" if surplus > 0 else "")
    ui.result_sentence(t(f"ux.compare.sentence_{kind}", households=lg.fmt_count(households),
                         support=lg.fmt_rwf(col["support"], lang), remaining=lg.fmt_rwf(col["not_offset"], lang),
                         surplus=lg.fmt_rwf(surplus, lang)))

    left, right = st.columns(2, gap="large")
    with left:
        # Additional living cost -> support -> what remains; support is never truncated, any excess is shown separately
        st.markdown(f"**{t('ux.compare.chart_offset')}**")
        bars = [(t("ux.compare.bar_extra"), col["extra"], th.ELEVATED, lg.fmt_rwf(col["extra"], lang)),
                (t("ux.compare.bar_support"), col["support"], th.SUPPORT, lg.fmt_rwf(col["support"], lang)),
                (t("ux.compare.bar_remaining"), col["not_offset"], th.UNMET, lg.fmt_rwf(col["not_offset"], lang))]
        if surplus > 0:
            bars.append((t("ux.compare.bar_surplus"), surplus, "#7FB8B1", lg.fmt_rwf(surplus, lang)))
        ui.show(ui.hbar(bars, t("ux.compare.axis_offset")), key="chart_compare_offset")
    cols = ["reference", "shock", "shock_support"]
    with right:
        st.markdown(f"**{t('ux.compare.table_title')}**")
        ui.html_table([t("compare.per_household")] + [t(f"compare.col.{c}") for c in cols],
                      [[t(f"compare.row.{k}")] + [lg.fmt_rwf(result["columns"][c][k], lang) for c in cols]
                       for k in ["basket", "extra", "support", "not_offset"]])
        st.caption(t("ux.compare.notes"))

    scope = [(t("compare.scope.geography"), lg.geography_label(geo, area, lang)),
             (t("compare.scope.period"), t("compare.period", months=s["duration_months"], latest=latest, payments=result["payments"])),
             (t("compare.scope.programme"), t(f"action.{s['action']}.name")), (t("compare.scope.group"), group),
             (t("compare.scope.payment"), payment), (t("compare.scope.prices"), ui.scenario_label(price, meta)),
             (t("compare.scope.assumptions"), t("compare.assumptions"))]
    item, value = t("brief.column.item"), t("brief.column.value")
    export = pd.DataFrame(
        [{item: k, value: v} for k, v in scope]
        + [{item: f"{t(f'compare.row.{k}')} · {t(f'compare.col.{c}')}", value: round(result["columns"][c][k])}
           for k in ["basket", "extra", "support", "not_offset"] for c in cols]
        + [{item: t(key), value: round(result[field])} for key, field in [
            ("compare.reach.households", "new_recipient_households"), ("compare.reach.people", "new_recipient_people"),
            ("compare.reach.poor", "poor_households"), ("compare.cost.transfers", "direct_transfers"),
            ("compare.cost.delivery", "delivery_costs"), ("compare.cost.total", "total_cost")]])
    ui.explanation_panel("compare", result, fp, meta, ui.scenario_label(price, meta))
    st.download_button(t("compare.download"), export.to_csv(index=False).encode("utf-8-sig"), key="cta_compare_csv",
                       file_name=t("compare.filename", place=geo.lower().replace(" ", "-"), area=area), mime="text/csv",
                       icon=":material/download:")
if status != "valid":
    st.button(t("compare.download"), key="cta_compare_csv_disabled", disabled=True, icon=":material/download:")

with st.expander(t("ux.compare.assumptions_title"), icon=":material/rule:"):
    st.markdown(f"- {t('compare.assumptions')}\n" + t("compare.not_estimated"))
ui.disclaimer("compare.disclaimer")
