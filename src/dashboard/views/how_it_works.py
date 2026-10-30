"""How it works: the four analytical components in plain language, with technical details in an expander."""
import streamlit as st

from src.dashboard import logic as lg
from src.dashboard import ui
from src.dashboard.i18n import current_language, t

tab = ui.tables()
meta = tab["meta"]
lang = current_language()

ui.page_title("how")
ui.context(meta)
components = ["poverty", "price", "distress", "coverage"]
for pair in (components[:2], components[2:]):
    ui.card_row([ui.text_card(t(f"how.{c}.title"), t(f"how.{c}.body")) for c in pair])
    st.write("")
st.markdown("\n".join(f"- {t(f'how.{c}.not')}" for c in components))

with st.expander(t("how.tech_title")):
    h = meta["holdout"]
    st.markdown(f"**{t('how.tech.holdout_title')}**")
    st.caption(t("how.tech.holdout_note", n=f"{meta['holdout_households']:,}"))
    rows = []
    for key, kind in [("poverty_roc_auc", "num"), ("poverty_pr_auc", "num"), ("poverty_precision_top20", "share"),
                      ("poverty_poor_people_reached_top20", "share"), ("poverty_calibration_slope", "num"),
                      ("vup_roc_auc", "num"), ("vup_pr_auc", "num")]:
        m = h[key]
        fmt = (lambda v: lg.fmt_share(v)) if kind == "share" else (lambda v: f"{v:.3f}")
        ci = f"{fmt(m['ci_low'])}–{fmt(m['ci_high'])}" if m["ci_low"] is not None else "–"
        rows.append([t(f"how.tech.metric.{key}"), fmt(m["value"]), ci])
    ui.html_table([t("how.tech.measure"), t("how.tech.value"), t("common.ci_header")], rows)
    st.markdown(f"**{t('how.tech.crossfit_title')}**")
    cf = meta["cross_fitted"]
    ui.html_table([t("how.tech.measure"), t("how.tech.value")], [
        [t("how.tech.metric.poverty_precision_top20"), lg.fmt_share(cf["precision_top20"])],
        [t("how.tech.metric.poverty_poor_people_reached_top20"), lg.fmt_share(cf["poor_people_reached_top20"])],
    ])
    st.caption(t("how.tech.crossfit_note"))
    for section in ["units", "calibration", "fairness", "sources", "survey_age", "cpi", "scenarios", "ai"]:
        st.markdown(f"**{t(f'how.tech.{section}_title')}**")
        st.markdown(t(f"how.tech.{section}", latest=lg.fmt_month(meta["latest_cpi_month"], lang)))
ui.disclaimer("how.disclaimer")
