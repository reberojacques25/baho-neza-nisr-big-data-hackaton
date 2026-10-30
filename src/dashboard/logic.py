"""Indicators, formatting, findings and comparisons for the Baho Neza pages.

Pure pandas on the aggregated public tables (dashboard_groups, dashboard_planning); no Streamlit. Functions that return
words take the language code and look text up through `translate`, using whole translated sentences.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from src.dashboard.i18n import translate
from src.dashboard.scenario import CATEGORIES, GROUP_DIMENSIONS, NATIONAL

ALL = NATIONAL                   # geography value for the whole country
COMPARISON_DIMENSIONS = ["head_sex", "disability", "elderly"]   # protected-group comparisons on "Our community"


@dataclass(frozen=True)
class Indicator:
    column: str
    kind: str                # share (0-1) or percent (already in %)
    source: str              # survey (observed statistic) or model (model estimate)
    higher_is_worse: bool


INDICATORS = {
    "poverty": Indicator("poverty_likelihood", "share", "model", True),
    "price": Indicator("basket_change_pct", "percent", "survey", True),
    "need": Indicator("high_need_share", "share", "survey", True),
    "coverage": Indicator("high_need_vup_coverage", "share", "survey", False),
}
MAP_INDICATORS = list(INDICATORS)
FINDING_COLUMNS = ["poverty_rate", "high_need_share", "high_need_vup_coverage", "basket_change_pct"]
COMPARISON_COLUMNS = {"poverty_rate": "share", "high_need_share": "share", "high_need_vup_coverage": "share",
                      "basket_change_pct": "percent"}


# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------
def _missing(v) -> bool:
    return v is None or (isinstance(v, (float, np.floating)) and np.isnan(v))


def round_count(v: float) -> float:
    return round(v, -2) if abs(v) >= 10_000 else round(v, -1)


def fmt_count(v: float) -> str:
    return "–" if _missing(v) else f"{round_count(v):,.0f}"


def fmt_share(v: float, digits: int = 1) -> str:
    return "–" if _missing(v) else f"{100 * v:.{digits}f}%"


def fmt_percent(v: float, signed: bool = False) -> str:
    if _missing(v):
        return "–"
    return f"{v:+.1f}%" if signed else f"{v:.1f}%"


def fmt_value(v: float, kind: str, signed: bool = False) -> str:
    return fmt_share(v) if kind == "share" else fmt_percent(v, signed)


def fmt_interval(lo: float, hi: float, kind: str) -> str:
    if _missing(lo) or _missing(hi):
        return "–"
    if kind == "share":
        return f"{100 * lo:.1f}–{100 * hi:.1f}%"
    if kind == "percent":
        return f"{lo:.1f}–{hi:.1f}%"
    return f"{fmt_count(lo)}–{fmt_count(hi)}"


def fmt_rwf(v: float, lang: str) -> str:
    if _missing(v):
        return "–"
    if abs(v) >= 1e9:
        return translate("units.billion_rwf", lang, v=f"{v / 1e9:,.2f}")
    if abs(v) >= 1e6:
        return translate("units.million_rwf", lang, v=f"{v / 1e6:,.1f}")
    return translate("units.rwf", lang, v=f"{round(v, -1) if abs(v) >= 1000 else v:,.0f}")


def fmt_month(ym: str, lang: str) -> str:
    """'2026-09' -> 'September 2026' in the chosen language."""
    year, month = ym.split("-")
    return translate("units.month_year", lang, month=translate(f"months.m{int(month)}", lang), year=year)


def survey_period(meta: dict, lang: str) -> str:
    s, e = meta["survey"]["start"][:7], meta["survey"]["end"][:7]
    return translate("context.survey_period", lang, start=fmt_month(s, lang), end=fmt_month(e, lang))


# ---------------------------------------------------------------------------
# Look-ups
# ---------------------------------------------------------------------------
def overall(groups: pd.DataFrame, geo: str, area: str) -> pd.Series:
    m = groups["geo"].eq(geo) & groups["area"].eq(area) & groups["dimension"].eq("all")
    return groups.loc[m].iloc[0]


def district_view(groups: pd.DataFrame, area: str) -> pd.DataFrame:
    m = groups["level"].eq("district") & groups["area"].eq(area) & groups["dimension"].eq("all")
    return groups.loc[m].sort_values("geo").reset_index(drop=True)


def district_names(groups: pd.DataFrame) -> list[str]:
    return sorted(groups.loc[groups["level"].eq("district"), "geo"].unique())


def map_range(groups: pd.DataFrame, indicator: str) -> tuple[float, float]:
    """One colour scale per indicator for every area view, so maps stay comparable when the area changes."""
    col = INDICATORS[indicator].column
    v = groups.loc[groups["level"].eq("district") & groups["dimension"].eq("all"), col].dropna()
    return float(v.min()), float(v.max())


def rank_range(view: pd.DataFrame, indicator: str, district: str) -> tuple[int, int, int] | None:
    """Plausible rank of a district (1 = most pressure) given 95% intervals: districts whose interval lies entirely on
    the worse side rank above it for sure, those entirely on the better side rank below. Returns (best, worst, n)."""
    ind = INDICATORS[indicator]
    lo, hi = f"{ind.column}_ci_low", f"{ind.column}_ci_high"
    v = view.dropna(subset=[ind.column, lo, hi]).set_index("geo")
    if district not in v.index:
        return None
    me = v.loc[district]
    others = v.drop(index=district)
    if ind.higher_is_worse:
        surely_worse, surely_better = (others[lo] > me[hi]).sum(), (others[hi] < me[lo]).sum()
    else:
        surely_worse, surely_better = (others[hi] < me[lo]).sum(), (others[lo] > me[hi]).sum()
    n = len(v)
    return int(surely_worse) + 1, n - int(surely_better), n


# ---------------------------------------------------------------------------
# Findings: only differences whose 95% intervals exclude the comparison value
# ---------------------------------------------------------------------------
def _kind(col: str) -> str:
    return COMPARISON_COLUMNS[col]


def findings(groups: pd.DataFrame, geo: str, area: str, lang: str, limit: int = 3) -> list[str]:
    """Up to `limit` data-supported findings. A district is compared with Rwanda (same area); Rwanda's rural households
    are compared with urban households. A finding is reported only when the 95% interval excludes the other value."""
    out: list[str] = []
    row = overall(groups, geo, area)
    if bool(row["suppressed"]):
        return out
    if geo != ALL:
        ref = overall(groups, ALL, area)
        for col in FINDING_COLUMNS:
            v, lo, hi, r = row[col], row[f"{col}_ci_low"], row[f"{col}_ci_high"], ref[col]
            if _missing(v) or _missing(r):
                continue
            direction = "higher" if lo > r else "lower" if hi < r else None
            if direction:
                out.append(translate(f"finding.{col}.{direction}", lang, value=fmt_value(v, _kind(col)),
                                     ci=fmt_interval(lo, hi, _kind(col)), ref=fmt_value(r, _kind(col))))
    elif area == "all":
        rural, urban = overall(groups, ALL, "rural"), overall(groups, ALL, "urban")
        for col in FINDING_COLUMNS:
            if rural[f"{col}_ci_low"] > urban[f"{col}_ci_high"]:
                direction = "rural_higher"
            elif rural[f"{col}_ci_high"] < urban[f"{col}_ci_low"]:
                direction = "rural_lower"
            else:
                continue
            out.append(translate(f"finding_area.{col}.{direction}", lang, rural=fmt_value(rural[col], _kind(col)),
                                 urban=fmt_value(urban[col], _kind(col))))
    return out[:limit]


# ---------------------------------------------------------------------------
# Protected-group comparisons
# ---------------------------------------------------------------------------
def group_comparisons(groups: pd.DataFrame, geo: str, area: str) -> pd.DataFrame:
    """One row per group (head's sex, disability, elderly member) with observed indicators; hidden cells stay NaN."""
    m = groups["geo"].eq(geo) & groups["area"].eq(area) & groups["dimension"].isin(COMPARISON_DIMENSIONS)
    sub = groups.loc[m].copy()
    order = {(d, g): i for i, (d, g) in enumerate((d, g) for d in COMPARISON_DIMENSIONS for g in GROUP_DIMENSIONS[d])}
    sub["_o"] = [order[(d, g)] for d, g in zip(sub["dimension"], sub["group"])]
    return sub.sort_values("_o").drop(columns="_o").reset_index(drop=True)


def comparison_note(cmp: pd.DataFrame, lang: str) -> list[str]:
    """Plain statements for pairs whose 95% intervals do not overlap (poverty rate and need only)."""
    notes = []
    for dim in COMPARISON_DIMENSIONS:
        pair = cmp[cmp["dimension"].eq(dim)].set_index("group")
        if len(pair) != 2 or pair["suppressed"].any():
            continue
        a, b = GROUP_DIMENSIONS[dim]
        for col in ["poverty_rate", "high_need_share"]:
            if pair.loc[a, f"{col}_ci_low"] > pair.loc[b, f"{col}_ci_high"]:
                notes.append(translate(f"compare_groups.{dim}.{col}.first_higher", lang,
                                       a=fmt_share(pair.loc[a, col]), b=fmt_share(pair.loc[b, col])))
            elif pair.loc[a, f"{col}_ci_high"] < pair.loc[b, f"{col}_ci_low"]:
                notes.append(translate(f"compare_groups.{dim}.{col}.first_lower", lang,
                                       a=fmt_share(pair.loc[a, col]), b=fmt_share(pair.loc[b, col])))
    return notes


# ---------------------------------------------------------------------------
# Overview figures (national, from the aggregated table)
# ---------------------------------------------------------------------------
def overview_figures(groups: pd.DataFrame) -> dict[str, float]:
    nat = overall(groups, ALL, "all")
    ref = sum(nat[f"ref_{c}"] for c in CATEGORIES)
    return {"basket_change_pct": nat["basket_change_pct"], "poverty_rate": nat["poverty_rate"],
            "gap_households": nat["protection_gap_households"], "gap_share": 1 - nat["high_need_vup_coverage"],
            "high_need_households": nat["high_need_households"], "reference_monthly": ref}


def geography_label(geo: str, area: str, lang: str) -> str:
    place = translate("geo.rwanda", lang) if geo == ALL else geo
    return translate("geo.place_area", lang, place=place, area=translate(f"area.{area}", lang))

