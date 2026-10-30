"""Fairness diagnostics and mitigations for the Baho Neza models.

Diagnostics: performance, calibration and selection by group, using a single national cut-off
(the top 20% of weighted households by predicted score), with cluster-bootstrap intervals.

Mitigations tested on the poverty model (development set, cluster-based CV only):
1. Interaction features for protected or proxy groups (`GroupFeatureAdder`).
2. Re-weighting: subgroup-balanced sample weights, or class-balanced weights.
3. Group-aware calibration (`GroupRecalibratedClassifier`, cross-fitted) and, as an explicit
   policy choice, separate urban/rural cut-offs (`area_quota_inclusion`).

All mitigations use only allowed features. Disability, head age, sex and location are used as
group variables because they are common eligibility or monitoring criteria in social protection;
using them in a model is a policy decision, flagged as such.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, ClassifierMixin, TransformerMixin, clone
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, roc_auc_score

from src.models import common as cm

K = 0.20
LIV = {"own_farming": "own farming", "farm_wage": "farm wage", "nonfarm_wage": "non-farm wage",
       "nonfarm_self_employment": "non-farm self-employment", "no_employed_member": "no employed member"}
DIMENSIONS = ["disability", "head_age_group", "province", "area", "head_sex", "household_size", "income_source"]


# ---------------------------------------------------------------------------
# Groups
# ---------------------------------------------------------------------------
def add_groups(df: pd.DataFrame) -> pd.DataFrame:
    d = df.copy()
    d["disability"] = np.where(d["n_members_with_disability"].gt(0), "member with disability", "no member with disability")
    d["head_age_group"] = pd.cut(d["head_age"], [-1, 34, 59, 200], labels=["head under 35", "head 35-59", "head 60+"]).astype(str)
    d["province"] = (d["district"] // 10).map({1: "Kigali City", 2: "Southern", 3: "Western", 4: "Northern", 5: "Eastern"})
    d["area"] = np.where(d["urban"].eq(1), "urban", "rural")
    d["head_sex"] = np.where(d["head_female"].eq(1), "female head", "male head")
    d["household_size"] = pd.cut(d["hh_size"], [0, 1, 3, 5, 7, 99], labels=["1 person", "2-3", "4-5", "6-7", "8+"]).astype(str)
    d["income_source"] = d["main_livelihood_pf"].map(LIV)
    return d


# ---------------------------------------------------------------------------
# Group metrics
# ---------------------------------------------------------------------------
def _group_rows(data: pd.DataFrame, score: str, target: str, inc: np.ndarray, dims, min_positives: int) -> list[dict]:
    rows = []
    for dim in dims:
        for g, idx in data.groupby(dim).indices.items():
            y = data[target].to_numpy(int)[idx]
            p = data[score].to_numpy(float)[idx]
            w = data["weight"].to_numpy(float)[idx]
            pw = data["pop_wt"].to_numpy(float)[idx]
            s = inc[idx]
            pos = int(y.sum())
            ok = min_positives <= pos < len(y)
            sel_w = (s * w).sum()
            rows.append({
                "dimension": dim, "group": g, "households": len(y), "positives": pos, "reliable": ok,
                "weighted_households": w.sum(),
                "observed_rate": np.average(y, weights=w), "mean_predicted": np.average(p, weights=w),
                "mean_error": np.average(p - y, weights=w), "brier": np.average((p - y) ** 2, weights=w),
                "roc_auc": roc_auc_score(y, p, sample_weight=w) if ok else np.nan,
                "pr_auc": average_precision_score(y, p, sample_weight=w) if ok else np.nan,
                "selection_rate": sel_w / w.sum(),
                "precision_top20": (s * w * y).sum() / sel_w if sel_w > 0 else np.nan,
                "recall_top20": (s * w * y).sum() / (w * y).sum() if pos else np.nan,
                "recall_people_top20": (s * pw * y).sum() / (pw * y).sum() if pos else np.nan,
            })
    return rows


def group_table(data: pd.DataFrame, score: str, target: str, dims=DIMENSIONS, k: float = K, min_positives: int = 20,
                inclusion: np.ndarray | None = None) -> pd.DataFrame:
    """Metrics per group. Selection = national top-k by `score` unless an `inclusion` vector is given."""
    inc = cm.top_k_inclusion(data[score], data["weight"], k) if inclusion is None else np.asarray(inclusion, float)
    return pd.DataFrame(_group_rows(data.reset_index(drop=True), score, target, inc, dims, min_positives))


def group_table_ci(data: pd.DataFrame, score: str, target: str, dims=DIMENSIONS, B: int = 200, k: float = K,
                   seed: int = cm.RANDOM_STATE, ci_metrics=("roc_auc", "pr_auc", "recall_people_top20", "precision_top20", "mean_error")) -> pd.DataFrame:
    """`group_table` with percentile 95% intervals from a cluster bootstrap (clusters resampled within strata).

    The national cut-off is recomputed in every draw.
    """
    base = data.reset_index(drop=True)
    point = group_table(base, score, target, dims, k)
    rng = np.random.default_rng(seed)
    idx_by = [[g.index.to_numpy() for _, g in d.groupby("clust")] for _, d in base.groupby("strata_id")]
    draws = []
    for b in range(B):
        rows = np.concatenate([np.concatenate([cl[i] for i in rng.integers(len(cl), size=len(cl))]) for cl in idx_by])
        t = group_table(base.iloc[rows], score, target, dims, k)
        t["draw"] = b
        draws.append(t)
    draws = pd.concat(draws)
    q = draws.groupby(["dimension", "group"])[list(ci_metrics)].quantile([0.025, 0.975]).unstack()
    out = point.set_index(["dimension", "group"])
    for m in ci_metrics:
        lo, hi = q[(m, 0.025)].reindex(out.index), q[(m, 0.975)].reindex(out.index)
        if m in ("roc_auc", "pr_auc"):
            lo, hi = lo.where(out["reliable"]), hi.where(out["reliable"])
        out[f"{m}_ci_low"], out[f"{m}_ci_high"] = lo, hi
    return out.reset_index()


def fairness_summary(table: pd.DataFrame) -> dict:
    """Summary indices (lower is better except `worst_group_recall`).

    - recall_gap: mean over dimensions of (max - min) people-recall at the national top 20%, groups with >= 20 positives
    - worst_group_recall: lowest such recall across all groups
    - mean_abs_calibration_gap: mean over dimensions of the household-weighted mean |mean_error| across its groups
    - max_abs_calibration_gap: largest |mean_error| among groups with >= 20 positives
    - auc_gap: mean over dimensions of (max - min) ROC-AUC among reliable groups
    """
    t = table[table["reliable"]]
    by_dim = t.groupby("dimension")
    cal = table.groupby("dimension").apply(lambda g: np.average(g["mean_error"].abs(), weights=g["weighted_households"]))
    return {"recall_gap": float((by_dim["recall_people_top20"].max() - by_dim["recall_people_top20"].min()).mean()),
            "worst_group_recall": float(t["recall_people_top20"].min()),
            "mean_abs_calibration_gap": float(cal.mean()),
            "max_abs_calibration_gap": float(t["mean_error"].abs().max()),
            "auc_gap": float((by_dim["roc_auc"].max() - by_dim["roc_auc"].min()).mean())}


# ---------------------------------------------------------------------------
# Mitigation 1: interaction features
# ---------------------------------------------------------------------------
INTERACTION_FEATURES = ["has_disabled_member", "share_members_disabled", "head_60plus", "head_under35",
                        "disabled_x_no_working_age", "disabled_x_hh_size", "elderly_head_x_female",
                        "elderly_head_x_share_dependents", "urban_x_share_food", "urban_x_n_key_assets",
                        "urban_x_head_education", "urban_x_hh_size"]


class GroupFeatureAdder(BaseEstimator, TransformerMixin):
    """Adds explicit group indicators and group x feature interactions (stateless)."""

    def fit(self, X, y=None):
        return self

    def transform(self, X):
        X = X.copy()
        dis = X["n_members_with_disability"].gt(0).astype(float)
        old = X["head_age"].ge(60).astype(float)
        urb = X["urban"].astype(float)
        X["has_disabled_member"] = dis
        X["share_members_disabled"] = X["n_members_with_disability"] / X["hh_size"]
        X["head_60plus"] = old
        X["head_under35"] = X["head_age"].lt(35).astype(float)
        X["disabled_x_no_working_age"] = dis * X["no_working_age_member"].astype(float)
        X["disabled_x_hh_size"] = dis * X["hh_size"]
        X["elderly_head_x_female"] = old * X["head_female"].astype(float)
        X["elderly_head_x_share_dependents"] = old * X["share_dependents"]
        X["urban_x_share_food"] = urb * X["share_food"]
        X["urban_x_n_key_assets"] = urb * X["n_key_assets"]
        X["urban_x_head_education"] = urb * X["head_education_code"].astype(float)
        X["urban_x_hh_size"] = urb * X["hh_size"]
        return X

    def get_feature_names_out(self, input_features=None):
        return np.asarray(list(input_features or []) + INTERACTION_FEATURES, dtype=object)


# ---------------------------------------------------------------------------
# Mitigation 2: re-weighting
# ---------------------------------------------------------------------------
BALANCE_CELLS = ("disability", "head_age_group", "area")


def subgroup_balanced_multiplier(data: pd.DataFrame, cells=BALANCE_CELLS, alpha: float = 0.5) -> pd.Series:
    """Multiplier (N_cells * share_cell) ** -alpha on the survey weight; small cells gain weight, mean kept at 1."""
    d = add_groups(data) if not set(cells) <= set(data.columns) else data
    key = d[list(cells)].astype(str).agg("|".join, axis=1)
    share = d["weight"].groupby(key).sum() / d["weight"].sum()
    m = (len(share) * key.map(share)) ** (-alpha)
    return m / np.average(m, weights=d["weight"])


# ---------------------------------------------------------------------------
# Mitigation 3: group-aware calibration and area cut-offs
# ---------------------------------------------------------------------------
CALIBRATION_GROUPS = ("disability", "head_age_group", "province", "area")


def _logit(p):
    p = np.clip(np.asarray(p, float), 1e-6, 1 - 1e-6)
    return np.log(p / (1 - p))


def calibration_design(p, groups: pd.DataFrame, columns=None) -> pd.DataFrame:
    if groups.shape[1] == 0:  # overall Platt scaling
        X = pd.DataFrame(index=groups.index)
    else:
        X = pd.get_dummies(groups.astype(str), drop_first=False, dtype=float)
    if columns is not None:
        X = X.reindex(columns=[c for c in columns if c != "logit_p"], fill_value=0.0)
    X.insert(0, "logit_p", _logit(p))
    return X


class GroupCalibrator:
    """Platt scaling with group intercepts: logit(p_new) = a * logit(p) + b + sum_g c_g * 1[group g]."""

    def __init__(self, groups=CALIBRATION_GROUPS, C: float = 1.0):
        self.groups, self.C = tuple(groups), C

    def fit(self, p, data: pd.DataFrame, y, w):
        X = calibration_design(p, data[list(self.groups)])
        self.columns_ = list(X.columns)
        self.model_ = LogisticRegression(C=self.C, max_iter=2000).fit(X, np.asarray(y, int), sample_weight=np.asarray(w) / np.mean(w))
        return self

    def predict(self, p, data: pd.DataFrame):
        return self.model_.predict_proba(calibration_design(p, data[list(self.groups)], self.columns_))[:, 1]


def cross_fit_calibration(oof_p: pd.Series, data: pd.DataFrame, target: str, folds: pd.Series, groups=CALIBRATION_GROUPS) -> pd.Series:
    """Recalibrated out-of-fold scores: the calibrator for fold f is fitted on the other folds' out-of-fold scores."""
    d = add_groups(data)
    out = pd.Series(np.nan, index=data.index)
    for f in sorted(folds.unique()):
        tr, te = folds.ne(f), folds.eq(f)
        cal = GroupCalibrator(groups).fit(oof_p[tr], d[tr], d.loc[tr, target], d.loc[tr, "weight"])
        out[te] = cal.predict(oof_p[te], d[te])
    return out


class GroupRecalibratedClassifier(BaseEstimator, ClassifierMixin):
    """A fitted base pipeline followed by a fitted `GroupCalibrator` (saved together as one object)."""

    def __init__(self, base, calibrator):
        self.base, self.calibrator = base, calibrator
        self.classes_ = np.array([0, 1])

    def predict_proba(self, X):
        p = self.base.predict_proba(X)[:, 1]
        q = self.calibrator.predict(p, add_groups(X))
        return np.column_stack([1 - q, q])

    def predict(self, X):
        return (self.predict_proba(X)[:, 1] >= 0.5).astype(int)


def area_quota_inclusion(p, w, pw, urban, k: float = K) -> np.ndarray:
    """POLICY OPTION: split the national budget between urban and rural areas in proportion to each area's
    predicted number of poor people (sum of pop_wt x p), then select the highest scores within each area.
    Uses predictions only, never labels."""
    p, w, pw, urban = (np.asarray(a, float) for a in (p, w, pw, urban))
    budget = k * w.sum()
    inc = np.zeros(len(p))
    expected_poor = {a: (pw * p)[urban == a].sum() for a in (0.0, 1.0)}
    total = sum(expected_poor.values())
    for a in (0.0, 1.0):
        m = urban == a
        k_area = min(budget * expected_poor[a] / total / w[m].sum(), 1.0)
        inc[m] = cm.top_k_inclusion(p[m], w[m], k_area)
    return inc


# ---------------------------------------------------------------------------
# Cross-validation with optional weight multipliers
# ---------------------------------------------------------------------------
def cv_predict(pipe, data: pd.DataFrame, cols: list[str], target: str, folds: pd.Series, weight_multiplier: pd.Series | None = None) -> pd.Series:
    """Out-of-fold probabilities; training weight = survey weight x optional multiplier (normalised to mean 1)."""
    oof = pd.Series(np.nan, index=data.index)
    w = data["weight"] * (1.0 if weight_multiplier is None else weight_multiplier)
    for f in sorted(folds.unique()):
        tr, te = folds.ne(f), folds.eq(f)
        fitted = cm.fit_pipeline(clone(pipe), data.loc[tr, cols], data.loc[tr, target], w[tr])
        oof[te] = fitted.predict_proba(data.loc[te, cols])[:, 1]
    return oof


def fold_scores(data: pd.DataFrame, score: pd.Series, target: str, folds: pd.Series, metric: str = "pr_auc") -> pd.Series:
    fn = average_precision_score if metric == "pr_auc" else roc_auc_score
    return pd.Series({f: fn(data.loc[folds.eq(f), target], score[folds.eq(f)], sample_weight=data.loc[folds.eq(f), "weight"])
                      for f in sorted(folds.unique())})


# ---------------------------------------------------------------------------
# Choosing a mitigation (rule fixed before results were seen)
# ---------------------------------------------------------------------------
def choose_approach(res: pd.DataFrame) -> tuple[str, pd.DataFrame]:
    """1. Performance gate: mean fold PR-AUC within one standard error of the best approach.
    2. Among eligible approaches, fairness rank = mean of the ranks of recall_gap (low), worst_group_recall
       (high) and mean_abs_calibration_gap (low).
    3. Best fairness rank wins; ties go to the lower `complexity`.
    The unmitigated model is a candidate, so a mitigation is chosen only if it ranks better.
    """
    r = res.copy()
    top = r["pr_auc_mean"].idxmax()
    r["eligible"] = r["pr_auc_mean"] >= r.loc[top, "pr_auc_mean"] - r.loc[top, "pr_auc_se"]
    e = r[r["eligible"]]
    ranks = pd.DataFrame({"recall_gap": e["recall_gap"].rank(), "worst_group_recall": (-e["worst_group_recall"]).rank(),
                          "mean_abs_calibration_gap": e["mean_abs_calibration_gap"].rank()})
    r["fairness_rank"] = ranks.mean(axis=1)
    best = r[r["eligible"]].sort_values(["fairness_rank", "complexity"]).index[0]
    return best, r


def index_standard_errors(data: pd.DataFrame, score: str, target: str, B: int = 100, seed: int = cm.RANDOM_STATE) -> dict:
    """Cluster-bootstrap standard errors of the `fairness_summary` indices and of the calibration slope."""
    base = data.reset_index(drop=True)
    rng = np.random.default_rng(seed)
    idx_by = [[g.index.to_numpy() for _, g in d.groupby("clust")] for _, d in base.groupby("strata_id")]
    draws = []
    for _ in range(B):
        rows = np.concatenate([np.concatenate([cl[i] for i in rng.integers(len(cl), size=len(cl))]) for cl in idx_by])
        d = base.iloc[rows]
        s = fairness_summary(group_table(d, score, target))
        s["calibration_slope"] = cm.calibration_slope_intercept(d[target].to_numpy(int), d[score].to_numpy(float), d["weight"].to_numpy(float))[0]
        draws.append(s)
    return pd.DataFrame(draws).std().to_dict()
