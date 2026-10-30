"""Score every EICV7 household with the final models (modelling layer; run once after notebook 14).

Writes, to data/processed/ (household-level files stay private; they are never shipped with the dashboard):
- household_scores.parquet: one row per household
  - poverty_score: final poverty model (tuned LightGBM + group recalibration), OUT-OF-SAMPLE:
    cross-fitted out-of-fold for development households, development-fitted model for holdout households
    (copied from poverty_scores_final.parquet, notebook 13)
  - high_need: distress score excluding VUP in the top quintile (notebook 07)
  - vup_coverage_score: final VUP coverage-gap model (tuned XGBoost + Platt), OUT-OF-SAMPLE, high-need only:
    cross-fitted out-of-fold for development, final model for holdout; missing otherwise
- district_model_drivers.parquet: AGGREGATED mean SHAP contributions (log-odds) of the base poverty model by
  feature group, plus the mean group-recalibration shift, per district x urban/rural and nationally

This is the only step after the household tables that reads model features (via common.load_frame, which uses the
raw EICV7 files). The policy simulator and the dashboard builder read only data/processed tables.

    python -m src.models.score_households
"""
from __future__ import annotations

import json

import joblib
import numpy as np
import pandas as pd

from src.models import common as cm
from src.models import fairness as fr
from src.models import interpretation as it
from src.models import poverty_model as pm
from src.models import tuning as tu
from src.models import vup_gap_model as vm

PROCESSED = cm.PROJECT_ROOT / "data" / "processed"
SCORES_OUT = PROCESSED / "household_scores.parquet"
DRIVERS_OUT = PROCESSED / "district_model_drivers.parquet"
POVERTY_SCORES_FINAL = PROCESSED / "poverty_scores_final.parquet"
POVERTY_FINAL = cm.MODELS_DIR / "poverty_vulnerability_pipeline_final.joblib"
VUP_FINAL = cm.MODELS_DIR / "vup_gap_pipeline_final.joblib"


def vup_out_of_sample() -> pd.Series:
    """Final VUP model scores for high-need households: cross-fitted out-of-fold (development) and final model (holdout)."""
    meta = json.loads(VUP_FINAL.with_suffix(".json").read_text())
    hn = vm.load_population(scores_path=POVERTY_SCORES_FINAL)
    spec = vm.FEATURES
    dev, hold = hn[hn["split"].eq("development")].reset_index(drop=True), hn[hn["split"].eq("holdout")].reset_index(drop=True)
    pipe = tu.pipeline(spec, meta["base_estimator"], meta["hyperparameters"])
    oof = fr.cv_predict(pipe, dev, spec.columns, "vup_any", dev["fold"])
    if meta.get("platt_recalibration"):
        oof = fr.cross_fit_calibration(oof, dev, "vup_any", dev["fold"], groups=())
    final = joblib.load(VUP_FINAL)
    hold_score = final.predict_proba(hold[spec.columns])[:, 1]
    return pd.concat([pd.Series(oof.to_numpy(), index=dev["hhid"]), pd.Series(hold_score, index=hold["hhid"])])


def poverty_drivers(df: pd.DataFrame) -> pd.DataFrame:
    """Mean SHAP by feature group (base poverty model) and mean recalibration shift, by district x area (aggregated)."""
    final = joblib.load(POVERTY_FINAL)
    spec = pm.FEATURE_SETS["full"]
    X = df[spec.columns]
    shap_t, base = it.explain(final.base, X)
    shap_f = it.aggregate(shap_t, spec)
    groups = shap_f.T.groupby(it.feature_group).sum().T
    p = final.base.predict_proba(X)[:, 1]
    q = final.predict_proba(X)[:, 1]
    groups["group_recalibration"] = fr._logit(q) - fr._logit(p)
    groups = groups.set_index(df.index)
    d = df[["district_name", "province_name", "area", "weight"]].join(groups)
    gcols = list(groups.columns)
    rows = []
    for keys, g in [(("Rwanda", "Rwanda", "all"), d)] + [((dist, prov, "all"), g) for (dist, prov), g in d.groupby(["district_name", "province_name"])] + \
                    [((dist, prov, area), g) for (dist, prov, area), g in d.groupby(["district_name", "province_name", "area"])]:
        means = {c: np.average(g[c], weights=g["weight"]) for c in gcols}
        rows.append({"district": keys[0], "province": keys[1], "area": keys[2], "sample_households": len(g), **means})
    out = pd.DataFrame(rows)
    nat = out.iloc[0][gcols]
    long = out.melt(id_vars=["district", "province", "area", "sample_households"], value_vars=gcols,
                    var_name="feature_group", value_name="mean_contribution_log_odds")
    long["difference_from_national"] = long["mean_contribution_log_odds"] - long["feature_group"].map(nat)
    long["base_log_odds"] = base
    return long


def run() -> tuple[pd.DataFrame, pd.DataFrame]:
    df = cm.load_frame().merge(cm.load_splits(), on=["hhid", "clust"])
    pov = pd.read_parquet(POVERTY_SCORES_FINAL).set_index("hhid")["poverty_score"]
    vup = vup_out_of_sample()
    scores = df[["hhid", "split", "fold"]].copy()
    scores["poverty_score"] = scores["hhid"].map(pov)
    scores["high_need"] = df["distress_quintile_excl_vup"].eq(5).astype(np.int8)
    scores["vup_coverage_score"] = scores["hhid"].map(vup)
    assert scores["poverty_score"].notna().all() and scores["hhid"].is_unique and len(scores) == 15_054
    assert scores.loc[scores["high_need"].eq(1), "vup_coverage_score"].notna().all()
    scores.to_parquet(SCORES_OUT, index=False)
    drivers = poverty_drivers(df)
    drivers.to_parquet(DRIVERS_OUT, index=False)
    return scores, drivers


if __name__ == "__main__":
    s, d = run()
    print(f"{SCORES_OUT.relative_to(cm.PROJECT_ROOT)}: {len(s):,} households; {DRIVERS_OUT.relative_to(cm.PROJECT_ROOT)}: {len(d):,} rows")
