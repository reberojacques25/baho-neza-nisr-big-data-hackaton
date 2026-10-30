"""VUP coverage-gap model: among high-need households, which ones does VUP currently reach?

Population: high-need households, the top quintile of the Cost-of-Living Distress Score excluding
its VUP component (`distress_quintile_excl_vup == 5`, notebook 07). Sensitivity: the top two quintiles.

Target: `vup_any` (any of the five VUP components). VUP participation is never a feature, and
features that hide it are replaced by program-free versions (see `common.LEAKAGE["vup"]`).

Reading: the model estimates how likely a high-need household with given characteristics is to be
covered. High-need households with a low predicted probability have profiles that current VUP
coverage reaches relatively rarely: they are *relatively underserved*. This describes coverage,
not eligibility or causation.

Models (library defaults, no tuning): district coverage baseline, logistic regression, random
forest, LightGBM. Same cluster-based folds and holdout as the poverty model; same selection rule.
"""
from __future__ import annotations

from functools import partial

import numpy as np
import pandas as pd

from src.models import common as cm
from src.models import training as tr
from src.models.poverty_model import SCORES_PATH as POVERTY_SCORES_PATH
from src.models.training import estimator, predict, results_table, save_pipeline

TARGET = "vup_any"
NEED_COL = "distress_quintile_excl_vup"
HIGH_NEED = (5,)
HIGH_NEED_SENSITIVITY = (4, 5)
PIPELINE_PATH = cm.MODELS_DIR / "vup_gap_pipeline.joblib"
RESULTS_PATH = cm.REPORTS_DIR / "model_results_vup_gap.csv"
GAP_SCORES_PATH = cm.PROJECT_ROOT / "data" / "processed" / "vup_gap_scores.parquet"
DISTRICT_PATH = cm.REPORTS_DIR / "vup_gap_by_district.csv"
FIG_DIR = cm.REPORTS_DIR / "figures" / "vup_gap_model"

FEATURES = cm.FeatureSpec("vup_gap", ["geography", "demographics", "education", "employment_income_source",
                                      "private_income", "assets", "housing", "services", "cpi_shock"],
                          extra=["poverty_score"])
MODELS = ["district_baseline", "logistic_regression", "random_forest", "lightgbm"]
COMPLEXITY = ["logistic_regression", "random_forest", "lightgbm"]

make_pipelines = partial(tr.make_pipelines, models=MODELS)
fold_metrics = partial(tr.fold_metrics, target=TARGET)
select_best = partial(tr.select_best, candidates=COMPLEXITY)
fit_on = partial(tr.fit_on, target=TARGET)


def load_population(quintiles=HIGH_NEED, scores_path=POVERTY_SCORES_PATH) -> pd.DataFrame:
    """High-need households with their split, fold and out-of-sample poverty vulnerability score."""
    df = cm.load_frame().merge(cm.load_splits(), on=["hhid", "clust"])
    scores = pd.read_parquet(scores_path)[["hhid", "poverty_score"]]
    df = df.merge(scores, on="hhid", how="left")
    assert df["poverty_score"].notna().all()
    return df[df[NEED_COL].isin(quintiles)].reset_index(drop=True)


def profile(data: pd.DataFrame, score: str, n_groups: int = 5) -> pd.DataFrame:
    """Characteristics of high-need households by quintile of predicted coverage (1 = least likely covered)."""
    d = data.assign(coverage_quintile=pd.qcut(data[score].rank(method="first"), n_groups, labels=range(1, n_groups + 1)))
    def summarise(g):
        w = g["weight"]
        return pd.Series({
            "households": len(g), "mean predicted coverage": np.average(g[score], weights=w),
            "observed coverage": np.average(g[TARGET], weights=w),
            "poor (people)": np.average(g["poor"], weights=g["pop_wt"]),
            "mean poverty score": np.average(g["poverty_score"], weights=w),
            "urban": np.average(g["urban"], weights=w),
            "Eastern Province": np.average(g["province"].eq(5), weights=w),
            "Kigali City": np.average(g["province"].eq(1), weights=w),
            "farm wage work": np.average(g["main_livelihood_pf"].eq("farm_wage"), weights=w),
            "own farming": np.average(g["main_livelihood_pf"].eq("own_farming"), weights=w),
            "non-farm work": np.average(g["main_livelihood_pf"].isin(["nonfarm_wage", "nonfarm_self_employment"]), weights=w),
            "female head": np.average(g["head_female"], weights=w),
            "elderly member (65+)": np.average(g["n_elderly_65plus"].gt(0), weights=w),
            "children 0-4": np.average(g["n_children_0_4"].gt(0), weights=w),
            "head has no education": np.average(g["head_education_code"].eq(0), weights=w),
            "mean price change, %": np.average(g["price_change_pct"], weights=w)})
    return d.groupby("coverage_quintile", observed=True).apply(summarise).T


def district_gaps(data: pd.DataFrame, score: str) -> pd.DataFrame:
    """High-need households not covered by VUP, by district: weighted counts, coverage with CI, mean predicted coverage."""
    rows = []
    for (prov, dist), g in data.groupby(["province_name", "district_name"]):
        m, se = cm.domain_mean(data[TARGET].astype(float), data["weight"], data["district_name"].eq(dist), data["strata_id"], data["clust"])
        unc = g[g[TARGET].eq(0)]
        rows.append({"province": prov.replace(" Province", ""), "district": dist, "high_need_sample": len(g),
                     "vup_recipients_sample": int(g[TARGET].sum()),
                     "high_need_households_weighted": g["weight"].sum(),
                     "uncovered_high_need_households_weighted": unc["weight"].sum(),
                     "uncovered_high_need_people_weighted": unc["pop_wt"].sum(),
                     "observed_coverage": m, "coverage_ci_low": max(m - 1.96 * se, 0), "coverage_ci_high": m + 1.96 * se,
                     "mean_predicted_coverage": np.average(g[score], weights=g["weight"]),
                     "uncovered_poor_share": np.average(unc["poor"], weights=unc["pop_wt"]) if len(unc) else np.nan})
    return pd.DataFrame(rows).sort_values("observed_coverage")
