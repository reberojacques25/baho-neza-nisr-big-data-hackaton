"""Baho Neza (Streamlit entry point): plan better support for your community.

Run from the project root:

    streamlit run src/dashboard/app.py

The app reads aggregated tables only (data/processed/dashboard_groups.parquet, dashboard_planning.parquet,
dashboard_meta.json) and the district boundaries. It never loads household-level records, models or raw survey files.
All text comes from src/dashboard/i18n.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st  # noqa: E402

from src.dashboard import ui  # noqa: E402
from src.dashboard.i18n import t  # noqa: E402

st.set_page_config(page_title=t("app.name"), page_icon="🌱", layout="wide", initial_sidebar_state="collapsed")
ui.init_state()

pages = [st.Page(path, title=t(f"nav.{key}"), icon=ui.NAV_ICONS[key], default=key == "overview")
         for key, path in ui.PAGES.items()]
page = st.navigation(pages, position="hidden")

ui.header()
try:
    ui.tables()
except FileNotFoundError:
    st.error(t("errors.missing_tables"), icon=":material/error:")
    st.stop()

page.run()
ui.footer()
