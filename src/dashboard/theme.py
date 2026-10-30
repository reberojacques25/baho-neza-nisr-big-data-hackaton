"""Baho Neza design tokens and the app's only CSS.

Streamlit's theme (.streamlit/config.toml) sets colours, fonts, heading sizes and radii. The CSS below styles owned
`bn-*` classes used in our own HTML snippets, plus layout width/padding and a minimum height for keyed call-to-action
buttons (Streamlit's documented `st-key-<key>` class). It does not restyle Streamlit widgets in general or hide any
accessibility control.
"""
from __future__ import annotations

PRIMARY = "#1B4B73"
BACKGROUND = "#F7F9FB"
CARD = "#FFFFFF"
TEXT = "#1F2937"
TEXT2 = "#5B6773"
BORDER = "#D9E1E7"
SUPPORT = "#0F766E"          # support / positive
ATTENTION = "#F59E0B"        # attention (always with dark text)
ELEVATED = "#EA580C"         # elevated pressure
UNMET = "#9F1239"            # high unmet need
MISSING = "#E5E7EB"          # missing / suppressed

# Map scales: one light-to-dark ramp per meaning. Pressure: pale amber -> amber -> orange -> crimson.
PRESSURE_SCALE = [[0.0, "#FEF3C7"], [0.35, ATTENTION], [0.7, ELEVATED], [1.0, UNMET]]
COVERAGE_SCALE = [[0.0, "#E3F1EE"], [1.0, SUPPORT]]

# Source tags: survey statistic, model estimate, scenario. Text labels carry the meaning; colour only groups them.
SOURCE_TAGS = {"survey": ("#E3F1EE", SUPPORT, "✓"), "model": ("#E8EEF4", PRIMARY, "≈"), "scenario": ("#FEF3C7", TEXT, "?")}

CSS = f"""
<style>
.block-container {{max-width: 1600px; padding: 24px 32px 40px;}}
@media (max-width: 640px) {{ .block-container {{padding: 16px 16px 32px;}} }}
.bn-prose, .bn-note, .bn-result {{max-width: 900px;}}
[data-testid="stPageLink"] p {{white-space: nowrap;}}
[class*="st-key-cta_"] button {{min-height: 44px;}}
.bn-brand {{font-weight: 700; font-size: 22px; color: {PRIMARY}; white-space: nowrap; line-height: 44px;}}
.bn-note {{color: {TEXT2}; font-size: 14px; margin: 0 0 8px;}}
.bn-context {{display: flex; flex-wrap: wrap; gap: 8px; margin: 0 0 16px;}}
.bn-context span {{background: {CARD}; border: 1px solid {BORDER}; border-radius: 999px; padding: 4px 12px;
  font-size: 14px; color: {TEXT2}; overflow-wrap: anywhere;}}
.bn-context b {{color: {TEXT}; font-weight: 600;}}
.bn-card {{background: {CARD}; border: 1px solid {BORDER}; border-radius: 12px; padding: 20px; height: 100%;
  overflow-wrap: anywhere;}}
.bn-card .label {{color: {TEXT2}; font-size: 14px; margin-bottom: 4px;}}
.bn-card .value {{color: {TEXT}; font-size: 36px; font-weight: 700; line-height: 1.15;}}
@media (max-width: 640px) {{ .bn-card .value {{font-size: 32px;}} }}
.bn-card .sub {{color: {TEXT2}; font-size: 14px; margin-top: 8px;}}
.bn-card h3 {{color: {PRIMARY}; font-size: 18px; margin: 0 0 8px; padding: 0;}}
.bn-card p {{color: {TEXT}; font-size: 16px; margin: 0;}}
.bn-tag {{display: inline-flex; align-items: center; gap: 4px; border-radius: 999px; padding: 2px 8px; font-size: 12px;
  font-weight: 600; margin-top: 8px;}}
.bn-flow {{display: flex; flex-wrap: wrap; gap: 8px; align-items: center; margin: 8px 0 16px;}}
.bn-flow .step {{background: {CARD}; border: 1px solid {BORDER}; border-radius: 12px; padding: 8px 16px; font-weight: 600;
  color: {PRIMARY};}}
.bn-flow .arrow {{color: {TEXT2};}}
.bn-row {{display: flex; justify-content: space-between; align-items: baseline; gap: 8px; padding: 8px 0;
  border-bottom: 1px solid {BORDER};}}
.bn-row .k {{color: {TEXT2}; font-size: 14px;}}
.bn-row .v {{color: {TEXT}; font-weight: 700; text-align: right;}}
.bn-row .ci {{color: {TEXT2}; font-size: 12px; font-weight: 400; display: block; white-space: nowrap;}}
.bn-stale {{background: #FEF3C7; color: {TEXT}; border: 1px solid {ATTENTION}; border-radius: 12px; padding: 16px 20px;
  font-weight: 600; margin: 8px 0 16px;}}
.bn-table {{width: 100%; border-collapse: collapse; background: {CARD}; border: 1px solid {BORDER}; border-radius: 12px;
  font-size: 14px;}}
.bn-table th, .bn-table td {{padding: 8px 12px; border-bottom: 1px solid {BORDER}; text-align: right;}}
.bn-table th:first-child, .bn-table td:first-child {{text-align: left;}}
.bn-table th {{color: {TEXT2}; font-weight: 600; background: {BACKGROUND};}}
.bn-table-wrap {{overflow-x: auto; max-width: 100%;}}
.bn-legend {{display: flex; flex-wrap: wrap; gap: 8px 16px; color: {TEXT2}; font-size: 14px; margin: 4px 0 8px;}}
.bn-swatch {{display: inline-block; width: 14px; height: 14px; border-radius: 3px; vertical-align: -2px; margin-right: 4px;
  border: 1px solid {BORDER};}}
.bn-explain h4 {{color: {PRIMARY}; font-size: 16px; margin: 8px 0 2px; padding: 0;}}
.bn-explain p {{color: {TEXT}; font-size: 16px; margin: 0 0 8px;}}
.bn-ai-label {{display: inline-block; background: #E8EEF4; color: {PRIMARY}; border-radius: 999px; padding: 2px 10px;
  font-size: 12px; font-weight: 600; margin: 8px 0 4px;}}
.bn-result {{color: {TEXT}; font-size: 18px; font-weight: 600; margin: 8px 0 16px; border-left: 4px solid {PRIMARY};
  padding: 4px 0 4px 12px;}}
.bn-footer {{color: {TEXT2}; font-size: 14px;}}
</style>
"""
