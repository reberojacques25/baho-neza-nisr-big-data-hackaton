"""Poverty vulnerability model: predict EICV7 poverty status from household characteristics.

Target: `poor` (sol_jan below the poverty line). Poverty status, consumption levels and program
participation are never features (see `common.LEAKAGE["poverty"]`).

Models (library defaults, no tuning): district poverty-rate baseline, logistic regression,
random forest, LightGBM, XGBoost. All preprocessing sits inside each scikit-learn Pipeline.

Validation: 5-fold cross-validation over whole survey clusters (within strata) on the development
split; the final holdout (one cluster in five) is scored once, by models fitted on the full
development split.

Selection rule, fixed before results were seen: highest mean fold PR-AUC; among models within one
standard error of the best, the simplest (logistic < random forest < LightGBM < XGBoost).
"""
from __future__ import annotations

from functools import partial

from src.models import common as cm
from src.models import training as tr
from src.models.training import allocation_metrics, estimator, predict, results_table, save_pipeline, targeting_curve

TARGET = "poor"
PIPELINE_PATH = cm.MODELS_DIR / "poverty_vulnerability_pipeline.joblib"
RESULTS_PATH = cm.REPORTS_DIR / "model_results_poverty.csv"
SCORES_PATH = cm.PROJECT_ROOT / "data" / "processed" / "poverty_scores.parquet"
FIG_DIR = cm.REPORTS_DIR / "figures" / "poverty_model"

FEATURE_SETS = {
    "full": cm.FeatureSpec("full", list(cm.GROUPS)),
    "pmt": cm.FeatureSpec("pmt", [g for g in cm.GROUPS if g not in cm.CONSUMPTION_DERIVED]),
}
MODELS = ["district_baseline", "logistic_regression", "random_forest", "lightgbm", "xgboost"]
COMPLEXITY = ["logistic_regression", "random_forest", "lightgbm", "xgboost"]
SELECTION_METRIC = tr.SELECTION_METRIC


make_pipelines = partial(tr.make_pipelines, models=MODELS)
fold_metrics = partial(tr.fold_metrics, target=TARGET)
select_best = partial(tr.select_best, candidates=COMPLEXITY)
fit_on = partial(tr.fit_on, target=TARGET)
