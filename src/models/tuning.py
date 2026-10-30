"""Hyperparameter tuning (Optuna) and final model selection, on the development set only.

Every trial is scored by the same 5 cluster-based folds used since notebook 09. The holdout is
never touched here: "holdout performance" in the selection is estimated out-of-fold.

Final selection rule (written before the full tuning run; see docs/tuning_decisions.md):
1. Performance gate: mean fold primary metric >= best - one fold standard error of the best.
2. Fairness gate:   recall_gap <= best eligible + 1 SE and worst_group_recall >= best eligible - 1 SE.
3. Calibration gate: mean_abs_calibration_gap <= best remaining + 1 SE and
                     |calibration_slope - 1| <= best remaining + max(1 SE of the slope, 0.05).
4. Simplest survivor (lowest `complexity`); ties go to the higher primary metric.
The SEs are cluster-bootstrap standard errors of each index for the default model of that target
(`fairness.index_standard_errors`), so every gate means "within one standard error", as the
performance gate does. A gate that would remove every candidate is skipped, and this is reported.
"""
from __future__ import annotations

import time

import numpy as np
import optuna
import pandas as pd
from lightgbm import LGBMClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from xgboost import XGBClassifier

from src.models import common as cm
from src.models import fairness as fr

DEFAULT_TOL = {"recall_gap": 0.02, "worst_group_recall": 0.02, "mean_abs_calibration_gap": 0.005, "slope_distance": 0.15}


def tolerances(index_se: dict) -> dict:
    """Gate tolerances = one bootstrap SE of each index (slope: at least 0.05)."""
    return {"recall_gap": index_se["recall_gap"], "worst_group_recall": index_se["worst_group_recall"],
            "mean_abs_calibration_gap": index_se["mean_abs_calibration_gap"],
            "slope_distance": max(index_se["calibration_slope"], 0.05)}
BASE_COMPLEXITY = {"logistic_regression": 1.0, "lightgbm": 2.0, "xgboost": 2.5}
TUNED_EXTRA, RECAL_EXTRA = 1.0, 0.5


# ---------------------------------------------------------------------------
# Search spaces
# ---------------------------------------------------------------------------
def space(name: str, trial: optuna.Trial) -> dict:
    if name == "lightgbm":
        return {"n_estimators": trial.suggest_int("n_estimators", 100, 1200, log=True),
                "learning_rate": trial.suggest_float("learning_rate", 0.01, 0.2, log=True),
                "num_leaves": trial.suggest_int("num_leaves", 8, 128, log=True),
                "min_child_samples": trial.suggest_int("min_child_samples", 5, 200, log=True),
                "subsample": trial.suggest_float("subsample", 0.5, 1.0), "subsample_freq": 1,
                "colsample_bytree": trial.suggest_float("colsample_bytree", 0.3, 1.0),
                "reg_lambda": trial.suggest_float("reg_lambda", 1e-3, 10.0, log=True),
                "reg_alpha": trial.suggest_float("reg_alpha", 1e-3, 10.0, log=True)}
    if name == "xgboost":
        return {"n_estimators": trial.suggest_int("n_estimators", 100, 1200, log=True),
                "learning_rate": trial.suggest_float("learning_rate", 0.01, 0.3, log=True),
                "max_depth": trial.suggest_int("max_depth", 2, 9),
                "min_child_weight": trial.suggest_float("min_child_weight", 1.0, 50.0, log=True),
                "subsample": trial.suggest_float("subsample", 0.5, 1.0),
                "colsample_bytree": trial.suggest_float("colsample_bytree", 0.3, 1.0),
                "reg_lambda": trial.suggest_float("reg_lambda", 1e-3, 10.0, log=True),
                "gamma": trial.suggest_float("gamma", 0.0, 5.0)}
    if name == "logistic_regression":
        return {"C": trial.suggest_float("C", 1e-3, 10.0, log=True),
                "l1_ratio": float(trial.suggest_categorical("penalty", ["l2", "l1"]) == "l1")}
    raise ValueError(name)


def estimator(name: str, params: dict | None = None):
    params = dict(params or {})
    rs = cm.RANDOM_STATE
    if name == "lightgbm":
        return LGBMClassifier(random_state=rs, verbose=-1, **params)
    if name == "xgboost":
        return XGBClassifier(random_state=rs, n_jobs=-1, eval_metric="logloss", **params)
    if name == "logistic_regression":
        if params:  # tuned: L2 (lbfgs) or L1 (liblinear)
            p = {k: v for k, v in params.items() if k != "penalty"}
            l1 = float(p.pop("l1_ratio", 0.0)) == 1.0 or params.get("penalty") == "l1"
            return LogisticRegression(solver="liblinear" if l1 else "lbfgs", l1_ratio=1.0 if l1 else 0.0, max_iter=5000, **p)
        return LogisticRegression(max_iter=5000)
    raise ValueError(name)


def pipeline(spec: cm.FeatureSpec, name: str, params: dict | None = None) -> Pipeline:
    prep = cm.make_preprocessor(spec, scale=(name == "logistic_regression")).set_output(transform="pandas")
    return Pipeline([("prep", prep), ("model", estimator(name, params))])


# ---------------------------------------------------------------------------
# Tuning
# ---------------------------------------------------------------------------
def run_study(name: str, spec: cm.FeatureSpec, data: pd.DataFrame, target: str, folds: pd.Series, metric: str,
              n_trials: int, timeout: float, seed: int = cm.RANDOM_STATE) -> tuple[optuna.Study, pd.DataFrame]:
    """TPE search maximising the mean fold `metric`; every trial is logged with its fold scores."""
    optuna.logging.set_verbosity(optuna.logging.WARNING)

    def objective(trial):
        t0 = time.time()
        params = space(name, trial)
        oof = fr.cv_predict(pipeline(spec, name, params), data, spec.columns, target, folds)
        fs = fr.fold_scores(data, oof, target, folds, metric)
        trial.set_user_attr("fold_scores", [round(float(v), 5) for v in fs])
        trial.set_user_attr("fold_se", float(fs.std() / np.sqrt(len(fs))))
        trial.set_user_attr("seconds", round(time.time() - t0, 1))
        return float(fs.mean())

    study = optuna.create_study(direction="maximize", sampler=optuna.samplers.TPESampler(seed=seed),
                                study_name=f"{name}_{target}")
    study.optimize(objective, n_trials=n_trials, timeout=timeout)
    log = study.trials_dataframe()
    log.insert(0, "study", study.study_name)
    log.insert(1, "metric", metric)
    return study, log


# ---------------------------------------------------------------------------
# Candidates and selection
# ---------------------------------------------------------------------------
def candidate_row(label: str, score: pd.Series, data: pd.DataFrame, target: str, folds: pd.Series, primary: str,
                  complexity: float, model: str, tuned: bool, recalibrated: bool, params: dict | None = None) -> dict:
    d = fr.add_groups(data).assign(score=score.to_numpy())
    fs = fr.fold_scores(d, d["score"], target, folds, primary)
    e = cm.evaluate(d[target], d["score"], d["weight"], d["pop_wt"])
    summary = fr.fairness_summary(fr.group_table(d, "score", target))
    return {"candidate": label, "model": model, "tuned": tuned, "recalibrated": recalibrated, "complexity": complexity,
            f"{primary}_mean": float(fs.mean()), f"{primary}_se": float(fs.std() / np.sqrt(len(fs))),
            "roc_auc": e["roc_auc"], "pr_auc": e["pr_auc"], "brier": e["brier"],
            "precision_top20": e["precision_top20"], "recall_top20": e["recall_top20"], "recall_people_top20": e["recall_people_top20"],
            "calibration_slope": e["calibration_slope"], "calibration_in_the_large": e["calibration_in_the_large"],
            **summary, "params": params or {}}


def select_final(table: pd.DataFrame, primary: str, tol: dict | None = None) -> tuple[str, pd.DataFrame, list[str]]:
    tol = tol or DEFAULT_TOL
    t = table.set_index("candidate").copy()
    notes = []
    m, s = f"{primary}_mean", f"{primary}_se"
    top = t[m].idxmax()
    t["gate_performance"] = t[m] >= t.loc[top, m] - t.loc[top, s]
    alive = t["gate_performance"]

    e = t[alive]
    fair = (e["recall_gap"] <= e["recall_gap"].min() + tol["recall_gap"]) & \
           (e["worst_group_recall"] >= e["worst_group_recall"].max() - tol["worst_group_recall"])
    t["gate_fairness"] = fair.reindex(t.index).fillna(False).astype(bool)
    if t["gate_fairness"].any():
        alive = alive & t["gate_fairness"]
    else:
        notes.append("fairness gate skipped (would remove every candidate)")

    e = t[alive]
    dist = (e["calibration_slope"] - 1).abs()
    cal = (e["mean_abs_calibration_gap"] <= e["mean_abs_calibration_gap"].min() + tol["mean_abs_calibration_gap"]) & \
          (dist <= dist.min() + tol["slope_distance"])
    t["gate_calibration"] = cal.reindex(t.index).fillna(False).astype(bool)
    if t["gate_calibration"].any():
        alive = alive & t["gate_calibration"]
    else:
        notes.append("calibration gate skipped (would remove every candidate)")

    t["survivor"] = alive
    best = t[alive].sort_values(["complexity", m], ascending=[True, False]).index[0]
    t["selected"] = t.index == best
    return best, t.reset_index(), notes
