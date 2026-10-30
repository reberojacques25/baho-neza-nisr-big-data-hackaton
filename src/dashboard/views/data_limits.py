"""Data & limitations: what the numbers are, how small cells are protected, what is not supported, review status."""
import streamlit as st

from src.dashboard import logic as lg
from src.dashboard import scenario as sc
from src.dashboard import ui
from src.dashboard.i18n import current_language, t

tab = ui.tables()
groups, meta = tab["groups"], tab["meta"]
lang = current_language()

ui.page_title("data")
ui.context(meta)

st.subheader(t("data.kinds_title"))
ui.card_row([ui.text_card(t(f"source.{s}"), t(f"data.kind.{s}")) for s in ["survey", "model", "scenario"]])
st.markdown(t("data.not_register"))

st.subheader(t("data.privacy_title"))
st.markdown(t("data.privacy", n=meta["min_cell_sample"]))

st.subheader(t("data.supported_title"))
st.markdown("\n".join(f"- {t(f'action.{a}.name')}: {t(f'action.{a}.help')}" for a in sc.ACTIONS))
st.markdown(f"**{t('data.unsupported_title')}**")
st.markdown("\n".join(f"- {t(f'action.{a}.name')}: {t(f'action.{a}.why')}" for a in sc.UNAVAILABLE_ACTIONS)
            + "\n- " + t("data.no_poverty_change"))

st.subheader(t("data.translation_title"))
st.markdown(t("data.translation"))

with st.expander(t("data.samples_title")):
    rows = []
    for d in lg.district_names(groups):
        cells = []
        for a in sc.AREAS:
            r = lg.overall(groups, d, a)
            cells.append(t("data.hidden_cell") if r["suppressed"] else f"{int(r['sample_households']):,}")
        rows.append([d, *cells])
    ui.html_table([t("geo.district")] + [t(f"area.{a}") for a in sc.AREAS], rows)
    st.caption(t("data.samples_note", n=meta["min_cell_sample"]))
ui.disclaimer("data.disclaimer")
