"""CPI feature engineering for the NISR consumer price index (September 2026 release).

Builds a tidy monthly CPI table for Rwanda (urban, rural, national) and derives
inflation features that can be joined to household survey data by month and area.

Reproduce everything (parquet + charts) from the project root with:

    python -m src.features.cpi_features

Requires: pandas, numpy, xlrd (to read the legacy .xls), pyarrow, matplotlib.

Design rules
------------
* Dates are treated as year-month only. The day stored in the workbook header
  is meaningless (it switches between the 1st, the 10th and arbitrary days), so
  every column is converted to a monthly period and stamped on the 1st.
* No future data. Anything after ``LATEST_MONTH`` (September 2026) is dropped,
  and every feature, including the outlier flags, uses only the current and
  earlier months. Truncating the input therefore never changes past values.
* Official index values are never altered. Outliers and jumps are flagged in
  separate columns, not smoothed or replaced.
"""

from __future__ import annotations

import re
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RAW_CPI_PATH = PROJECT_ROOT / "data" / "external" / "prices" / "CPI_time_series_September_2026.xls"
PROCESSED_PATH = PROJECT_ROOT / "data" / "processed" / "cpi_features.parquet"
FIGURES_DIR = PROJECT_ROOT / "reports" / "figures" / "cpi"

LATEST_MONTH = pd.Period("2026-09", freq="M")
BASE_MONTH = pd.Period("2014-02", freq="M")  # reference period, index = 100

AREA_SHEETS = {"Urban": "urban", "Rural": "rural", "All Rwanda": "national"}
OTHER_INDICES_SHEET = "Other_Indices"  # urban only

# COICOP code -> category slug for the Urban / Rural / All Rwanda sheets.
COICOP_CATEGORIES = {
    "00": "headline",
    "01": "food_non_alcoholic_beverages",
    "01.1.1": "bread_cereals",
    "01.1.2": "meat",
    "01.1.4": "milk_cheese_eggs",
    "01.1.7": "vegetables",
    "01.2": "non_alcoholic_beverages",
    "02": "alcohol_tobacco",
    "03": "clothing_footwear",
    "04": "housing_utilities",
    "05": "furnishing_household",
    "06": "health",
    "07": "transport",
    "08": "communication",
    "09": "recreation_culture",
    "10": "education",
    "11": "restaurants_hotels",
    "12": "miscellaneous",
}

# Other_Indices rows are identified by label: column A codes and COICOP codes repeat.
OTHER_INDEX_GROUPS = [
    (r"^local goods index", "local_goods"),
    (r"^imported goods index", "imported_goods"),
    (r"^fresh products", "fresh_products"),
    (r"^energy index", "energy"),
    (r"^general index excluding fresh products and energy", "core"),
]
# Code 04 is housing under local goods but furnishing under imported goods, so it is resolved by label.
OTHER_INDEX_SUBCATEGORIES = {
    "01": [("food", "food")],
    "04": [("housing", "housing_utilities"), ("furnishing", "furnishing")],
    "07": [("transport", "transport")],
}

# The indicators requested for modelling. All other categories stay in the table
# (they are needed for outlier review) but are not part of this set.
INDICATORS = [
    "headline",
    "food_non_alcoholic_beverages",
    "bread_cereals",
    "meat",
    "milk_cheese_eggs",
    "vegetables",
    "non_alcoholic_beverages",
    "fresh_products",
    "energy",
    "transport",
    "housing_utilities",
    "core",
    "local_goods",
    "imported_goods",
]

# Outlier settings. Both flags use month-over-month inflation.
JUMP_THRESHOLD_PCT = 10.0  # |MoM| at or above this is an abrupt jump
ROBUST_Z_THRESHOLD = 6.0  # |robust z| at or above this is an outlier
ROBUST_WINDOW = 36  # trailing months used for the median / MAD
ROBUST_MIN_PERIODS = 24
ROBUST_MIN_SCALE_PCT = 0.5  # floor on the scale so flat series do not explode

FEATURE_COLUMNS = [
    "mom_pct",
    "yoy_pct",
    "ann_3m_pct",
    "cum_change_12m_pct",
    "avg_annual_pct",
    "gap_rural_urban_mom_pp",
    "gap_rural_urban_yoy_pp",
    "gap_rural_urban_ann_3m_pp",
    "mom_robust_z",
    "flag_abrupt_jump",
    "flag_outlier",
    "flag_review",
]


# --------------------------------------------------------------------------- #
# Loading
# --------------------------------------------------------------------------- #
def _clean_label(label: str) -> str:
    """Strip NISR's 'v' bullet, non-breaking spaces and footnote markers."""
    label = str(label).replace("\xa0", " ")
    label = re.sub(r"^v\s+", "", label.strip())
    label = re.sub(r"\(\d\)", "", label)
    return re.sub(r"\s+", " ", label).strip()


def _read_wide_sheet(path: Path, sheet: str, latest_month: pd.Period) -> pd.DataFrame:
    """Return one sheet as a wide frame: key columns plus one column per month."""
    raw = pd.read_excel(path, sheet_name=sheet, header=None, engine="xlrd")

    header_rows = raw.index[raw[4].astype(str).str.strip().eq("Weights")]
    if len(header_rows) != 1:
        raise ValueError(f"{sheet}: expected one 'Weights' header row, found {len(header_rows)}")
    header = header_rows[0]

    months = pd.to_datetime(raw.iloc[header, 5:]).dt.to_period("M")
    if months.isna().any() or months.duplicated().any():
        raise ValueError(f"{sheet}: month header has blanks or duplicates")
    expected = pd.period_range(months.iloc[0], months.iloc[-1], freq="M")
    if not months.reset_index(drop=True).equals(pd.Series(expected)):
        raise ValueError(f"{sheet}: months are not consecutive")
    if months.iloc[-1] < latest_month:
        raise ValueError(f"{sheet}: data ends {months.iloc[-1]}, before {latest_month}")

    body = raw.iloc[header + 1 :]
    body = body[pd.to_numeric(body[4], errors="coerce").notna() & body[3].notna()]
    keep = [c for c, m in zip(raw.columns[5:], months) if m <= latest_month]
    wide = body[[2, 3, 4, *keep]].copy()
    wide.columns = ["coicop", "category_label", "weight", *[m for m in months if m <= latest_month]]
    wide["coicop"] = wide["coicop"].astype(str).str.strip()
    wide["category_label"] = wide["category_label"].map(_clean_label)
    wide["weight"] = wide["weight"].astype(float)
    return wide.reset_index(drop=True)


def _label_other_indices(wide: pd.DataFrame) -> pd.Series:
    """Map Other_Indices rows to slugs; sub-rows inherit their parent group."""
    slugs, parent = [], None
    for code, label in zip(wide["coicop"], wide["category_label"].str.lower()):
        group = next((slug for pattern, slug in OTHER_INDEX_GROUPS if re.match(pattern, label)), None)
        if group is not None:
            slugs.append(group)
            parent = group.split("_")[0] if group in ("local_goods", "imported_goods") else None
            continue
        sub = next((s for prefix, s in OTHER_INDEX_SUBCATEGORIES.get(code, []) if label.startswith(prefix)), None)
        if parent is None or sub is None:
            raise ValueError(f"Other_Indices: unexpected row {code!r} {label!r}")
        slugs.append(f"{parent}_{sub}")
    return pd.Series(slugs, index=wide.index)


def load_cpi_long(path: Path | str = RAW_CPI_PATH, latest_month: pd.Period | str = LATEST_MONTH) -> pd.DataFrame:
    """Load Urban, Rural, All Rwanda and Other_Indices into one long table.

    Columns: date, area, category, category_label, coicop, source_sheet, weight, index_value.
    ``weight`` is in parts per 10,000 of that area's basket.
    """
    path, latest_month = Path(path), pd.Period(latest_month, freq="M")
    frames = []
    for sheet, area in AREA_SHEETS.items():
        wide = _read_wide_sheet(path, sheet, latest_month)
        unknown = set(wide["coicop"]) - set(COICOP_CATEGORIES)
        if unknown:
            raise ValueError(f"{sheet}: unexpected COICOP codes {sorted(unknown)}")
        division_weight = wide.loc[wide["coicop"].str.fullmatch(r"\d\d") & wide["coicop"].ne("00"), "weight"].sum()
        if not np.isclose(division_weight, 10_000, atol=0.5):
            raise ValueError(f"{sheet}: division weights sum to {division_weight:.1f}, not 10,000")
        wide.insert(0, "category", wide["coicop"].map(COICOP_CATEGORIES))
        frames.append(wide.assign(area=area, source_sheet=sheet))

    other = _read_wide_sheet(path, OTHER_INDICES_SHEET, latest_month)
    other.insert(0, "category", _label_other_indices(other))
    frames.append(other.assign(area="urban", source_sheet=OTHER_INDICES_SHEET))

    keys = ["area", "category", "category_label", "coicop", "source_sheet", "weight"]
    long = pd.concat(frames, ignore_index=True).melt(id_vars=keys, var_name="period", value_name="index_value")
    long["date"] = pd.PeriodIndex(long["period"], freq="M").to_timestamp()
    long["index_value"] = long["index_value"].astype(float)
    long = long[["date", *keys, "index_value"]].sort_values(["area", "category", "date"], ignore_index=True)

    if long.duplicated(["date", "area", "category"]).any():
        raise ValueError("duplicate (date, area, category) rows")
    if long["index_value"].isna().any() or (long["index_value"] <= 0).any():
        raise ValueError("missing or non-positive index values")
    if latest_month >= BASE_MONTH:
        base = long.loc[long["date"].eq(BASE_MONTH.to_timestamp()), "index_value"]
        if not np.allclose(base, 100.0):
            raise ValueError(f"not every series equals 100 in {BASE_MONTH}")
    return long


# --------------------------------------------------------------------------- #
# Features
# --------------------------------------------------------------------------- #
def _trailing_robust_z(mom: pd.Series) -> pd.Series:
    """Robust z-score of MoM against the previous ROBUST_WINDOW months only."""
    past = mom.shift(1).rolling(ROBUST_WINDOW, min_periods=ROBUST_MIN_PERIODS)
    median = past.median()
    mad = past.apply(lambda a: np.nanmedian(np.abs(a - np.nanmedian(a))), raw=True)
    scale = np.maximum(1.4826 * mad, ROBUST_MIN_SCALE_PCT)
    return (mom - median) / scale


def add_inflation_features(long: pd.DataFrame) -> pd.DataFrame:
    """Add inflation measures, the rural-urban gap and outlier flags.

    All measures are in percent; gaps are in percentage points. Each value at
    month t uses only months <= t.
    """
    df = long.sort_values(["area", "category", "date"], ignore_index=True)
    g = df.groupby(["area", "category"], sort=False)["index_value"]
    lag = {k: g.shift(k) for k in (1, 3, 12)}

    df["mom_pct"] = 100 * (df["index_value"] / lag[1] - 1)
    df["yoy_pct"] = 100 * (df["index_value"] / lag[12] - 1)
    df["ann_3m_pct"] = 100 * ((df["index_value"] / lag[3]) ** 4 - 1)

    # Compound the last 12 monthly changes. Algebraically identical to yoy_pct;
    # kept as an explicit, separately computed check on the chained series.
    log_change = np.log(df["index_value"] / lag[1])
    rolling_log = log_change.groupby([df["area"], df["category"]], sort=False).transform(
        lambda s: s.rolling(12, min_periods=12).sum()
    )
    df["cum_change_12m_pct"] = 100 * np.expm1(rolling_log)

    # NISR's "annual average inflation": 12-month mean vs the previous 12-month mean.
    mean_12m = g.transform(lambda s: s.rolling(12, min_periods=12).mean())
    df["avg_annual_pct"] = 100 * (mean_12m / mean_12m.groupby([df["area"], df["category"]]).shift(12) - 1)

    measures = {"mom_pct": "mom", "yoy_pct": "yoy", "ann_3m_pct": "ann_3m"}
    wide = df[df["area"].isin(["urban", "rural"])].pivot_table(
        index=["date", "category"], columns="area", values=list(measures), dropna=False
    )
    gap = pd.DataFrame(
        {f"gap_rural_urban_{short}_pp": wide[(col, "rural")] - wide[(col, "urban")] for col, short in measures.items()}
    ).reset_index()
    df = df.merge(gap, on=["date", "category"], how="left")

    df["mom_robust_z"] = df.groupby(["area", "category"], sort=False)["mom_pct"].transform(_trailing_robust_z)
    df["flag_abrupt_jump"] = df["mom_pct"].abs().ge(JUMP_THRESHOLD_PCT)
    df["flag_outlier"] = df["mom_robust_z"].abs().ge(ROBUST_Z_THRESHOLD)
    df["flag_review"] = df["flag_abrupt_jump"] | df["flag_outlier"]
    df["is_indicator"] = df["category"].isin(INDICATORS)
    return df.sort_values(["area", "category", "date"], ignore_index=True)


def build_cpi_features(
    path: Path | str = RAW_CPI_PATH, latest_month: pd.Period | str = LATEST_MONTH
) -> pd.DataFrame:
    """Load the workbook and return the full feature table."""
    return add_inflation_features(load_cpi_long(path, latest_month))


def to_wide(
    features: pd.DataFrame,
    measures: tuple[str, ...] = ("yoy_pct", "mom_pct", "ann_3m_pct"),
    categories: list[str] | None = None,
) -> pd.DataFrame:
    """One row per (date, area), one column per ``<category>__<measure>``.

    Handy for joining to household data on survey month and urban/rural status.
    Urban-only indicators (fresh products, energy, core, local, imported) are
    missing for rural and national rows.
    """
    subset = features[features["category"].isin(categories or INDICATORS)]
    wide = subset.pivot_table(index=["date", "area"], columns="category", values=list(measures), dropna=False)
    wide.columns = [f"{category}__{measure}" for measure, category in wide.columns]
    return wide.sort_index(axis=1).reset_index()


def save_features(features: pd.DataFrame, path: Path | str = PROCESSED_PATH) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    features.to_parquet(path, index=False)
    return path


# --------------------------------------------------------------------------- #
# Charts
# --------------------------------------------------------------------------- #
AREA_COLORS = {"national": "#2a78d6", "urban": "#eb6834", "rural": "#1baf7a"}
AREA_NAMES = {"national": "Rwanda", "urban": "Urban", "rural": "Rural"}
INK = {"primary": "#0b0b0b", "secondary": "#52514e", "muted": "#898781"}
SURFACE, GRID, BASELINE, REFERENCE = "#fcfcfb", "#e1e0d9", "#c3c2b7", "#898781"
SOURCE_NOTE = "Source: NISR CPI, September 2026 release. Index base: February 2014 = 100."

CHARTS = {
    "headline_inflation": {
        "title": "Headline inflation: Rwanda, urban and rural",
        "category": "headline",
        "areas": ["national", "urban", "rural"],
    },
    "food_inflation": {
        "title": "Food and non-alcoholic beverages inflation",
        "category": "food_non_alcoholic_beverages",
        "areas": ["national", "urban", "rural"],
    },
    "fresh_products_inflation": {
        "title": "Fresh-products inflation (urban only)",
        "category": "fresh_products",
        "areas": ["urban"],
        "series_label": "Fresh products",
        "reference": "headline",
    },
    "energy_inflation": {
        "title": "Energy inflation (urban only)",
        "category": "energy",
        "areas": ["urban"],
        "series_label": "Energy",
        "reference": "headline",
    },
    "transport_inflation": {
        "title": "Transport inflation",
        "category": "transport",
        "areas": ["national", "urban", "rural"],
    },
}


def _style_axes(ax, ylabel: str) -> None:
    ax.set_facecolor(SURFACE)
    ax.grid(axis="y", color=GRID, linewidth=1, linestyle="-")
    ax.set_axisbelow(True)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(BASELINE)
    ax.tick_params(colors=INK["muted"], labelsize=9, length=0)
    ax.axhline(0, color=BASELINE, linewidth=1, zorder=1)
    ax.set_ylabel(ylabel, color=INK["secondary"], fontsize=9)
    ax.margins(x=0.01)


def _end_labels(ax, ends: list[tuple[pd.Timestamp, float, str]], min_gap_frac: float = 0.055) -> None:
    """Label line ends; spread colliding labels and join them with leader lines."""
    from matplotlib.dates import date2num

    lo, hi = ax.get_ylim()
    min_gap = (hi - lo) * min_gap_frac
    ends = sorted(ends, key=lambda e: e[1])
    placed: list[float] = []
    for _, y, _ in ends:
        placed.append(max(y, placed[-1] + min_gap) if placed else y)
    overflow = placed[-1] - (hi - min_gap / 2) if placed else 0
    if overflow > 0:
        placed = [p - overflow for p in placed]
    for (x, y, text), y_label in zip(ends, placed):
        ax.annotate(
            text,
            xy=(date2num(x), y),
            xytext=(1.02, y_label),
            textcoords=("axes fraction", "data"),
            fontsize=9,
            color=INK["primary"],
            va="center",
            ha="left",
            annotation_clip=False,
            arrowprops={"arrowstyle": "-", "color": BASELINE, "linewidth": 1, "shrinkA": 0, "shrinkB": 5},
        )


def _new_figure(title: str, subtitle: str, nrows: int = 1):
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(nrows, 1, figsize=(10, 4.6 * nrows), sharex=True, squeeze=False)
    fig.patch.set_facecolor(SURFACE)
    fig.subplots_adjust(left=0.07, right=0.84, top=0.84 if nrows == 1 else 0.9, bottom=0.14 if nrows == 1 else 0.08)
    fig.text(0.07, 0.95 if nrows == 1 else 0.965, title, fontsize=14, fontweight="bold", color=INK["primary"])
    fig.text(0.07, 0.905 if nrows == 1 else 0.94, subtitle, fontsize=10, color=INK["secondary"])
    fig.text(0.07, 0.03 if nrows == 1 else 0.015, SOURCE_NOTE, fontsize=8, color=INK["muted"])
    return fig, axes[:, 0]


def plot_yoy_chart(features: pd.DataFrame, name: str):
    """Year-over-year inflation for one category, one line per area."""
    spec = CHARTS[name]
    fig, (ax,) = _new_figure(spec["title"], "Year-over-year change in the consumer price index, %")
    _style_axes(ax, "% change on a year earlier")
    ends = []
    series = [
        (area, spec["category"], AREA_COLORS[area], spec.get("series_label", AREA_NAMES[area]), False)
        for area in spec["areas"]
    ]
    if "reference" in spec:
        series.insert(0, ("urban", spec["reference"], REFERENCE, "Urban headline", True))
    for area, category, color, label, is_reference in series:
        s = features[(features["area"] == area) & (features["category"] == category)].dropna(subset=["yoy_pct"])
        ax.plot(
            s["date"], s["yoy_pct"], color=color, linewidth=1.5 if is_reference else 2,
            solid_capstyle="round", solid_joinstyle="round", label=label, zorder=2 if is_reference else 3,
        )
        last = s.iloc[-1]
        ax.plot(last["date"], last["yoy_pct"], "o", color=color, markersize=8,
                markeredgecolor=SURFACE, markeredgewidth=2, zorder=4)
        ends.append((last["date"], last["yoy_pct"], f"{label} {last['yoy_pct']:.1f}%"))
    ax.legend(loc="upper left", frameon=False, fontsize=9, labelcolor=INK["secondary"], ncols=len(series))
    _end_labels(ax, ends)
    return fig


def plot_gap_chart(features: pd.DataFrame, categories=("headline", "food_non_alcoholic_beverages")):
    """Rural minus urban YoY inflation, one panel per category, shared y-scale."""
    titles = {"headline": "Headline CPI", "food_non_alcoholic_beverages": "Food and non-alcoholic beverages"}
    fig, axes = _new_figure(
        "Rural-versus-urban inflation gap",
        "Rural minus urban year-over-year inflation, percentage points. Above zero: prices rising faster in rural areas.",
        nrows=len(categories),
    )
    data = {
        c: features[(features["area"] == "rural") & (features["category"] == c)].dropna(subset=["gap_rural_urban_yoy_pp"])
        for c in categories
    }
    all_gaps = pd.concat(d["gap_rural_urban_yoy_pp"] for d in data.values())
    pad = 0.12 * (all_gaps.max() - all_gaps.min())
    for i, (ax, category) in enumerate(zip(axes, categories)):
        d = data[category]
        x, y = d["date"], d["gap_rural_urban_yoy_pp"]
        _style_axes(ax, "percentage points")
        ax.set_ylim(all_gaps.min() - pad, all_gaps.max() + pad)
        ax.fill_between(x, y, 0, where=y >= 0, color=AREA_COLORS["rural"], alpha=0.18, linewidth=0, interpolate=True,
                        label="Rural inflation higher")
        ax.fill_between(x, y, 0, where=y < 0, color=AREA_COLORS["urban"], alpha=0.18, linewidth=0, interpolate=True,
                        label="Urban inflation higher")
        ax.plot(x, y, color=INK["secondary"], linewidth=1.5, solid_joinstyle="round", zorder=3)
        last = d.iloc[-1]
        ax.plot(last["date"], last["gap_rural_urban_yoy_pp"], "o", color=INK["secondary"], markersize=8,
                markeredgecolor=SURFACE, markeredgewidth=2, zorder=4)
        _end_labels(ax, [(last["date"], last["gap_rural_urban_yoy_pp"], f"{last['gap_rural_urban_yoy_pp']:+.1f} pp")])
        ax.set_title(titles.get(category, category), loc="left", fontsize=10, color=INK["primary"], pad=6)
        if i == 0:
            ax.legend(loc="upper left", frameon=False, fontsize=9, labelcolor=INK["secondary"], ncols=2)
    return fig


def save_charts(features: pd.DataFrame, out_dir: Path | str = FIGURES_DIR) -> list[Path]:
    """Render every chart to PNG and return the paths."""
    import matplotlib.pyplot as plt

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    figures = {name: plot_yoy_chart(features, name) for name in CHARTS}
    figures["rural_urban_inflation_gap"] = plot_gap_chart(features)
    paths = []
    for name, fig in figures.items():
        path = out_dir / f"{name}.png"
        fig.savefig(path, dpi=150, facecolor=SURFACE)
        plt.close(fig)
        paths.append(path)
    return paths


def main() -> None:
    features = build_cpi_features()
    path = save_features(features)
    charts = save_charts(features)
    print(f"Saved {len(features):,} rows ({features['date'].min():%Y-%m} to {features['date'].max():%Y-%m}) to {path}")
    print(f"Saved {len(charts)} charts to {charts[0].parent}")


if __name__ == "__main__":
    main()
