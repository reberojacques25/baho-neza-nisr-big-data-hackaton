"""Model-agnostic training helpers shared by the poverty and VUP coverage-gap models.

Pipelines (preprocessing + estimator), fold metrics, the pre-registered selection rule
(best mean fold metric; simplest model within one standard error), fitting on the development
split, targeting curves and saving a pipeline with a JSON metadata sidecar.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from lightgbm import LGBMClassifier
from sklearn.base import clone
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from xgboost import XGBClassifier

from src.models import common as cm

SELECTION_METRIC = "pr_auc"


def estimator(name: str):
    rs = cm.RANDOM_STATE
    return {
        "logistic_regression": LogisticRegression(max_iter=5000),
        "random_forest": RandomForestClassifier(n_jobs=-1, random_state=rs),
        "lightgbm": LGBMClassifier(random_state=rs, verbose=-1),
        "xgboost": XGBClassifier(random_state=rs, n_jobs=-1, eval_metric="logloss"),
    }[name]


def make_pipelines(spec: cm.FeatureSpec, models, group_col: str = "district") -> tuple[dict, dict]:
    """Pipelines and the input columns each one needs."""
    pipes, cols = {}, {}
    for name in models:
        if name.endswith("_baseline"):
            pipes[name] = Pipeline([("model", cm.GroupRateBaseline(group_col))])
            cols[name] = [group_col]
        else:
            prep = cm.make_preprocessor(spec, scale=(name == "logistic_regression")).set_output(transform="pandas")
            pipes[name] = Pipeline([("prep", prep), ("model", estimator(name))])
            cols[name] = spec.columns
    return pipes, cols


def fold_metrics(oof: pd.DataFrame, data: pd.DataFrame, folds: pd.Series, target: str) -> pd.DataFrame:
    rows = []
    for f in sorted(folds.unique()):
        m = folds.eq(f)
        for name in oof.columns:
            e = cm.evaluate(data.loc[m, target], oof.loc[m, name], data.loc[m, "weight"], data.loc[m, "pop_wt"])
            rows.append({"model": name, "fold": f, **e})
    return pd.DataFrame(rows)


def select_best(fm: pd.DataFrame, candidates, metric: str = SELECTION_METRIC) -> tuple[str, pd.DataFrame]:
    """Highest mean fold metric; within one standard error of it, the simplest model."""
    s = fm[fm["model"].isin(candidates)].groupby("model")[metric].agg(["mean", "std", "count"])
    s["se"] = s["std"] / np.sqrt(s["count"])
    top = s["mean"].idxmax()
    s["within_1se_of_best"] = s["mean"] >= s.loc[top, "mean"] - s.loc[top, "se"]
    eligible = [m for m in candidates if m in s.index and s.loc[m, "within_1se_of_best"]]
    return eligible[0], s.sort_values("mean", ascending=False)


def fit_on(pipes: dict, cols: dict, data: pd.DataFrame, target: str) -> dict:
    return {n: cm.fit_pipeline(clone(p), data[cols[n]], data[target], data["weight"]) for n, p in pipes.items()}


def predict(fitted: dict, cols: dict, data: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame({n: m.predict_proba(data[cols[n]])[:, 1] for n, m in fitted.items()}, index=data.index)


def targeting_curve(y, p, w, pw, grid=np.linspace(0, 1, 101)) -> pd.DataFrame:
    """Share of positives (people, pop_wt) reached when the top k share of households is selected."""
    y, w, pw = np.asarray(y, int), np.asarray(w, float), np.asarray(pw, float)
    rows = []
    for k in grid:
        inc = cm.top_k_inclusion(p, w, k) if k > 0 else np.zeros(len(y))
        rows.append({"k": k, "recall_people": (inc * pw * y).sum() / (pw * y).sum(),
                     "precision": (inc * w * y).sum() / max((inc * w).sum(), 1e-12)})
    return pd.DataFrame(rows)


def allocation_metrics(y, selected, w, pw) -> dict:
    """Precision and recall of a fixed 0/1 allocation (e.g. current VUP)."""
    y, s, w, pw = (np.asarray(a, float) for a in (y, selected, w, pw))
    return {"share_selected": (s * w).sum() / w.sum(), "precision": (s * w * y).sum() / (s * w).sum(),
            "recall_people": (s * pw * y).sum() / (pw * y).sum()}


def results_table(fm: pd.DataFrame, oof_metrics: pd.DataFrame, holdout_metrics: pd.DataFrame, boot: pd.DataFrame,
                  feature_set: str, best: str) -> pd.DataFrame:
    """Wide results: one row per (feature set, model, evaluation), metrics as columns."""
    metric_cols = [c for c in holdout_metrics.columns if c not in ("model",)]
    parts = []
    g = fm.groupby("model")[metric_cols]
    for ev, t in [("cv_fold_mean", g.mean()), ("cv_fold_sd", g.std())]:
        parts.append(t.reset_index().assign(evaluation=ev))
    parts.append(oof_metrics.assign(evaluation="cv_out_of_fold_pooled"))
    parts.append(holdout_metrics.assign(evaluation="holdout"))
    for bound in ("ci_low", "ci_high"):
        b = boot.pivot_table(index="score", columns="metric", values=bound).reset_index().rename(columns={"score": "model"})
        parts.append(b.assign(evaluation=f"holdout_{bound}"))
        if "diff_vs_baseline_ci_low" in boot:
            col = f"diff_vs_baseline_{bound}"
            b = boot.dropna(subset=[col]).pivot_table(index="score", columns="metric", values=col).reset_index().rename(columns={"score": "model"})
            parts.append(b.assign(evaluation=f"holdout_diff_vs_district_baseline_{bound}"))
    out = pd.concat(parts, ignore_index=True)
    out.insert(0, "feature_set", feature_set)
    out.insert(2, "selected", out["model"].eq(best))
    first = ["feature_set", "model", "selected", "evaluation"]
    return out[first + [c for c in out.columns if c not in first]]


def save_pipeline(pipe: Pipeline, path: Path, meta: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(pipe, path)
    import lightgbm, sklearn, xgboost
    meta = {**meta, "saved": str(date.today()), "path": str(path.relative_to(cm.PROJECT_ROOT)),
            "versions": {"scikit-learn": sklearn.__version__, "lightgbm": lightgbm.__version__,
                         "xgboost": xgboost.__version__, "pandas": pd.__version__, "numpy": np.__version__}}
    path.with_suffix(".json").write_text(json.dumps(meta, indent=2, default=str))
    return path
