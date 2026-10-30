"""Charts shared by the modelling notebooks (static PNGs, same style as the CPI shock charts)."""
from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

INK = {"primary": "#0b0b0b", "secondary": "#52514e", "muted": "#898781"}
SURFACE, GRID, BASELINE = "#fcfcfb", "#e1e0d9", "#c3c2b7"
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]  # fixed order
NEUTRAL = "#898781"
MODEL_COLORS = {"district_baseline": NEUTRAL, "logistic_regression": SERIES[0], "random_forest": SERIES[1],
                "lightgbm": SERIES[2], "xgboost": SERIES[3]}
MODEL_LABELS = {"district_baseline": "District baseline", "logistic_regression": "Logistic regression",
                "random_forest": "Random forest", "lightgbm": "LightGBM", "xgboost": "XGBoost"}
SOURCE = "Source: EICV7 2023/24 (NISR); NISR CPI Jan 2024 to Sep 2026. Survey-weighted."


def figure(title: str, subtitle: str, width: float = 10, height: float = 5, ncols: int = 1, source: str = SOURCE):
    fig, axes = plt.subplots(1, ncols, figsize=(width, height), squeeze=False)
    fig.patch.set_facecolor(SURFACE)
    fig.text(0.03, 1 - 0.32 / height, title, fontsize=14, fontweight="bold", color=INK["primary"])
    fig.text(0.03, 1 - 0.6 / height, subtitle, fontsize=10, color=INK["secondary"])
    fig.text(0.03, 0.15 / height, source, fontsize=8, color=INK["muted"])
    for ax in axes[0]:
        style(ax)
    return fig, axes[0]


def style(ax, grid_axis: str = "x") -> None:
    ax.set_facecolor(SURFACE)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(BASELINE)
    ax.tick_params(colors=INK["secondary"], labelsize=9, length=0)
    ax.grid(axis=grid_axis, color=GRID, linewidth=1)
    ax.set_axisbelow(True)


def save(fig, path: Path, top: float, bottom: float = 0.12, left: float = 0.25, right: float = 0.95, wspace: float = 0.35) -> Path:
    fig.subplots_adjust(top=top, bottom=bottom, left=left, right=right, wspace=wspace)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=150, facecolor=SURFACE)
    plt.close(fig)
    return path


def dot_ci(ax, table: pd.DataFrame, scale: float = 100, color: str = SERIES[0], label_fmt: str = "{:.0f}",
           reference: float | None = None, show_n: bool = True) -> None:
    """Horizontal dot (estimate) with 95% CI whisker, one row per group, top to bottom in table order."""
    y = np.arange(len(table))[::-1]
    m, lo, hi = table["mean"] * scale, table["ci_low"] * scale, table["ci_high"] * scale
    ax.hlines(y, lo, hi, color=color, linewidth=2, alpha=0.45)
    ax.plot(m, y, "o", color=color, markersize=7, markeredgecolor=SURFACE, markeredgewidth=1.5, zorder=3)
    offset = 0.015 * (np.nanmax(hi) - min(np.nanmin(lo), 0))
    for yi, mi, hii in zip(y, m, hi):
        ax.text(hii + offset, yi, label_fmt.format(mi), va="center", fontsize=8.5, color=INK["primary"])
    labels = [f"{g}  (n={n:,})" if show_n else str(g) for g, n in zip(table.index, table["households"])]
    ax.set_yticks(y, labels, fontsize=8.5, color=INK["primary"])
    if reference is not None:
        ax.axvline(reference * scale, color=INK["muted"], linewidth=1, linestyle="--", zorder=1)
    ax.set_ylim(-0.7, len(table) - 0.3)


def curves(ax, kind: str, data: dict[str, tuple], baseline_rate: float | None = None) -> None:
    """ROC or precision-recall curves; data = {model: (x, y, auc)}."""
    for name, (x, yv, auc) in data.items():
        ls = "--" if name == "district_baseline" else "-"
        ax.plot(x, yv, ls, color=MODEL_COLORS.get(name, NEUTRAL), linewidth=2,
                label=f"{MODEL_LABELS.get(name, name)} ({auc:.3f})")
    if kind == "roc":
        ax.plot([0, 1], [0, 1], ":", color=BASELINE, linewidth=1)
        ax.set_xlabel("False positive rate", color=INK["secondary"], fontsize=9)
        ax.set_ylabel("True positive rate", color=INK["secondary"], fontsize=9)
    else:
        if baseline_rate is not None:
            ax.axhline(baseline_rate, linestyle=":", color=BASELINE, linewidth=1)
        ax.set_xlabel("Recall", color=INK["secondary"], fontsize=9)
        ax.set_ylabel("Precision", color=INK["secondary"], fontsize=9)
    ax.grid(axis="both", color=GRID, linewidth=1)
    ax.legend(frameon=False, fontsize=8, loc="lower right" if kind == "roc" else "upper right", labelcolor=INK["secondary"])
