"""SHAP helpers: explain a fitted pipeline and aggregate transformed columns back to original features.

SHAP values are in log-odds. For each household, an original feature's value is the sum over its
transformed columns (one-hot levels and missing-value indicators), so values stay additive:
base value + sum of feature SHAP values = the model's log-odds.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import shap

from src.models import common as cm


def explain(pipe, X: pd.DataFrame, background: pd.DataFrame | None = None) -> tuple[pd.DataFrame, float]:
    """SHAP values (households x transformed columns) and the base value, for a prep + model pipeline."""
    prep, model = pipe.named_steps["prep"], pipe.named_steps["model"]
    Xt = prep.transform(X)
    if hasattr(model, "coef_"):
        bg = prep.transform(background if background is not None else X)
        ex = shap.LinearExplainer(model, shap.maskers.Independent(bg, max_samples=2000))
        sv, base = ex.shap_values(Xt), float(np.ravel(ex.expected_value)[0])
        margin = model.decision_function(Xt)
    else:
        ex = shap.TreeExplainer(model)
        sv = ex.shap_values(Xt)
        sv = sv[1] if isinstance(sv, list) else sv
        sv = sv[:, :, 1] if np.ndim(sv) == 3 else sv
        base = float(np.ravel(ex.expected_value)[-1])
        if hasattr(model, "booster_"):          # LightGBM: SHAP explains the raw score (log-odds)
            margin = model.predict(Xt, raw_score=True)
        elif hasattr(model, "get_booster"):     # XGBoost: log-odds margin
            margin = model.predict(Xt, output_margin=True)
        else:                                   # random forest: SHAP explains the probability
            margin = model.predict_proba(Xt)[:, 1]
    out = pd.DataFrame(sv, columns=Xt.columns, index=X.index)
    err = np.abs(base + out.sum(axis=1).to_numpy() - margin).max()
    assert err < 1e-6, f"SHAP values do not add up to the model margin (max error {err})"
    return out, base


def original_feature(column: str, spec: cm.FeatureSpec) -> str:
    name = column.split("__", 1)[1]
    name = name.removeprefix("missingindicator_")
    if column.startswith("cat__"):
        return max((c for c in spec.categorical if name.startswith(c + "_")), key=len)
    return name


def aggregate(shap_t: pd.DataFrame, spec: cm.FeatureSpec) -> pd.DataFrame:
    """Households x original features."""
    mapping = {c: original_feature(c, spec) for c in shap_t.columns}
    return shap_t.T.groupby(mapping).sum().T[spec.columns]


def feature_group(feature: str) -> str:
    for g, cols in cm.GROUPS.items():
        if feature in cols:
            return g
    return "poverty_vulnerability" if feature == "poverty_score" else "other"


def global_importance(shap_f: pd.DataFrame, weights: pd.Series) -> tuple[pd.Series, pd.Series]:
    """Weighted mean |SHAP| per feature, and per feature group (|sum of the group's SHAP|)."""
    w = weights.to_numpy() / weights.sum()
    by_feature = pd.Series((np.abs(shap_f.to_numpy()) * w[:, None]).sum(axis=0), index=shap_f.columns).sort_values(ascending=False)
    groups = shap_f.T.groupby(feature_group).sum().T
    by_group = pd.Series((np.abs(groups.to_numpy()) * w[:, None]).sum(axis=0), index=groups.columns).sort_values(ascending=False)
    return by_feature, by_group


def pretty(feature: str) -> str:
    return feature.removesuffix("_pf").removesuffix("_excl_vup").replace("_", " ")


def local_table(shap_f: pd.DataFrame, X: pd.DataFrame, base: float, k: int = 6) -> pd.DataFrame:
    """Top-k contributions per household: feature, value, SHAP (log-odds), plus base and prediction."""
    rows = []
    for h in shap_f.index:
        s = shap_f.loc[h]
        top = s.reindex(s.abs().sort_values(ascending=False).index[:k])
        margin = base + s.sum()
        for f, v in top.items():
            rows.append({"row": h, "feature": f, "value": X.loc[h, f], "shap_log_odds": v, "base_log_odds": base,
                         "predicted_probability": 1 / (1 + np.exp(-margin))})
    return pd.DataFrame(rows)
