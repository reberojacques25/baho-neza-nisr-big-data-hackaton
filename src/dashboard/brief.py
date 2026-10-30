"""District planning brief: aggregate CSV and a one-page A4 PDF, in the chosen language.

Built from the same aggregated rows the pages show, so hidden (suppressed) cells stay hidden and no household record
can appear. The PDF is drawn with matplotlib's bundled DejaVu Sans font (covers Kinyarwanda's Latin alphabet); nothing
is fetched from the network. The brief is a planning aid, not an approved government document, and carries no seal.
"""
from __future__ import annotations

import io
import textwrap
from datetime import date

import pandas as pd

from src.dashboard import logic as lg
from src.dashboard.i18n import translate
from src.dashboard.scenario import CATEGORIES

A4_MM = (210, 297)
MM_PER_INCH = 25.4


def _hidden(lang: str) -> str:
    return translate("brief.hidden", lang)


def brief_rows(groups: pd.DataFrame, meta: dict, geo: str, area: str, lang: str, price: dict | None = None,
               comparison: dict | None = None, today: date | None = None) -> list[dict]:
    """Rows (section, item, value, note). `price` and `comparison` must be valid results for this geography."""
    tr = lambda k, **kw: translate(k, lang, **kw)  # noqa: E731
    today = today or date.today()
    rows: list[dict] = []

    def add(section: str, item: str, value: str, note: str = "") -> None:
        rows.append({"section": tr(f"brief.section.{section}"), "item": item, "value": value, "note": note})

    add("about", tr("brief.item.title"), tr("brief.title"))
    add("about", tr("brief.item.geography"), lg.geography_label(geo, area, lang))
    add("about", tr("brief.item.generated"), today.isoformat())
    add("about", tr("brief.item.survey"), lg.survey_period(meta, lang), tr("brief.note.survey"))
    add("about", tr("brief.item.prices"), tr("brief.price_window", base=lg.fmt_month(meta["price_base_month"], lang),
                                             latest=lg.fmt_month(meta["latest_cpi_month"], lang)))

    row = lg.overall(groups, geo, area)
    hidden = bool(row["suppressed"])
    hn_hidden = bool(row["high_need_suppressed"])
    ind = [("poverty_rate", "share", "survey", hidden), ("poverty_likelihood", "share", "model", hidden),
           ("high_need_share", "share", "survey", hidden), ("high_need_vup_coverage", "share", "survey", hn_hidden),
           ("basket_change_pct", "percent", "survey", hidden)]
    for col, kind, source, h in ind:
        value = _hidden(lang) if h else lg.fmt_value(row[col], kind)
        ci = "" if h else tr("brief.ci", ci=lg.fmt_interval(row[f"{col}_ci_low"], row[f"{col}_ci_high"], kind))
        add("indicators", tr(f"brief.indicator.{col}"), value, " · ".join(x for x in [tr(f"source.{source}"), ci] if x))
    gap_value = _hidden(lang) if hn_hidden else lg.fmt_count(row["protection_gap_households"])
    gap_ci = "" if hn_hidden else tr("brief.ci", ci=lg.fmt_interval(row["protection_gap_households_ci_low"],
                                                                    row["protection_gap_households_ci_high"], "count"))
    add("indicators", tr("brief.indicator.protection_gap_households"), gap_value,
        " · ".join(x for x in [tr("source.survey"), gap_ci] if x))
    ref = None if hidden else sum(row[f"ref_{c}"] for c in CATEGORIES)
    add("indicators", tr("brief.indicator.reference_monthly"), _hidden(lang) if hidden else lg.fmt_rwf(ref, lang),
        tr("brief.note.reference_monthly", latest=lg.fmt_month(meta["latest_cpi_month"], lang)))

    found = lg.findings(groups, geo, area, lang)
    for i, f in enumerate(found or [tr("finding.none")], start=1):
        add("findings", str(i), f)

    if price is not None:
        add("scenario", tr("brief.item.scenario"), _price_label(price["spec"], meta, lang), tr("source.scenario"))
        add("scenario", tr("prices.result.basket_change"), lg.fmt_percent(price["basket_change_pct"], signed=True))
        add("scenario", tr("prices.result.extra_monthly"), lg.fmt_rwf(price["extra_monthly"], lang), tr("brief.note.per_household"))
        add("scenario", tr("prices.result.purchasing_power"), lg.fmt_percent(price["purchasing_power_change_pct"], signed=True),
            tr("prices.assumption.earnings"))
    else:
        add("scenario", tr("brief.item.scenario"), tr("brief.no_scenario"))

    if comparison is not None:
        s = comparison["support"]
        add("support", tr("brief.item.programme"), tr(f"action.{s['action']}.name"), tr("source.scenario"))
        add("support", tr("compare.reach.households"), lg.fmt_count(comparison["new_recipient_households"]))
        add("support", tr("compare.reach.people"), lg.fmt_count(comparison["new_recipient_people"]))
        add("support", tr("compare.cost.transfers"), lg.fmt_rwf(comparison["direct_transfers"], lang))
        add("support", tr("compare.cost.delivery"), lg.fmt_rwf(comparison["delivery_costs"], lang))
        add("support", tr("compare.cost.total"), lg.fmt_rwf(comparison["total_cost"], lang),
            tr("brief.note.duration", months=s["duration_months"]))
        add("support", tr("compare.row.not_offset"), lg.fmt_rwf(comparison["columns"]["shock_support"]["not_offset"], lang),
            tr("brief.note.per_household"))
    add("notes", tr("brief.item.suppression"), tr("brief.note.suppression", n=meta["min_cell_sample"]))
    add("notes", tr("brief.item.sources"), tr("brief.note.sources"))
    add("notes", tr("brief.item.use"), tr("app.persistent"), tr("brief.note.not_official"))
    return rows


def _price_label(spec: dict, meta: dict, lang: str) -> str:
    base = lg.fmt_month(meta["latest_cpi_month"], lang)
    if spec["mode"] == "simple":
        return translate("scenario.label_simple", lang, pct=f"{spec['increases']['food']:g}", months=spec["horizon_months"], base=base)
    parts = ", ".join(f"{translate(f'category.{c}', lang)} +{v:g}%" for c, v in spec["increases"].items())
    return translate("scenario.label_detailed", lang, months=spec["horizon_months"], base=base) + f" ({parts})"


def brief_csv(rows: list[dict], lang: str) -> bytes:
    cols = ["section", "item", "value", "note"]
    df = pd.DataFrame(rows, columns=cols).rename(columns={c: translate(f"brief.column.{c}", lang) for c in cols})
    return df.to_csv(index=False).encode("utf-8-sig")


def brief_filename(geo: str, area: str, lang: str, ext: str, today: date | None = None) -> str:
    place = (translate("geo.rwanda", lang) if geo == lg.ALL else geo).lower().replace(" ", "-")
    return translate("brief.filename", lang, place=place, area=area, date=(today or date.today()).isoformat(), ext=ext)


def brief_pdf(rows: list[dict], lang: str) -> bytes:
    """One A4 page (210 x 297 mm). Text is wrapped; if the content would overflow, the font shrinks."""
    import matplotlib
    matplotlib.use("Agg")
    from matplotlib import pyplot as plt

    width_in, height_in = (v / MM_PER_INCH for v in A4_MM)
    margin = 15 / A4_MM[0]
    for size in (8.5, 8.0, 7.5, 7.0, 6.5):
        lines = _layout(rows, lang, size)
        line_h = size * 1.45 / 72 / height_in
        if len(lines) * line_h < 1 - 2 * 15 / A4_MM[1] - 0.05:
            break
    fig = plt.figure(figsize=(width_in, height_in))
    fig.patch.set_facecolor("white")
    y = 1 - 15 / A4_MM[1]
    fig.text(margin, y, translate("app.name", lang), fontsize=size + 7, fontweight="bold", color="#1B4B73", va="top",
             family="DejaVu Sans")
    y -= (size + 7) * 1.6 / 72 / height_in
    fig.text(margin, y, translate("brief.title", lang), fontsize=size + 3, color="#1F2937", va="top", family="DejaVu Sans")
    y -= (size + 3) * 1.8 / 72 / height_in
    for kind, text in lines:
        style = {"section": dict(fontweight="bold", color="#1B4B73"), "row": dict(color="#1F2937"),
                 "note": dict(color="#5B6773", style="italic")}[kind]
        if kind == "section":
            y -= line_h * 0.5
        fig.text(margin, y, text, fontsize=size, va="top", family="DejaVu Sans", **style)
        y -= line_h
    fig.text(margin, 10 / A4_MM[1], translate("brief.footer", lang), fontsize=size - 1, color="#5B6773", family="DejaVu Sans")
    buf = io.BytesIO()
    fig.savefig(buf, format="pdf")
    plt.close(fig)
    return buf.getvalue()


def _layout(rows: list[dict], lang: str, size: float) -> list[tuple[str, str]]:
    chars = int(180 / (size * 0.19))       # characters per line across 180 mm of text width
    out: list[tuple[str, str]] = []
    section = None
    for r in rows:
        if r["section"] != section:
            section = r["section"]
            out.append(("section", section))
        text = f"{r['item']}: {r['value']}"
        out += [("row", line) for line in textwrap.wrap(text, chars, subsequent_indent="   ")]
        if r["note"]:
            out += [("note", line) for line in textwrap.wrap(r["note"], chars, initial_indent="   ", subsequent_indent="   ")]
    return out
