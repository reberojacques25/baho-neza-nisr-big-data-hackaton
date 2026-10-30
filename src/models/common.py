"""Shared data, features, splits and evaluation for the Baho Neza models.

- `load_frame()` joins the household master table and the CPI shock table and adds
  program-free versions of the features that would otherwise encode VUP participation.
- `make_splits()` assigns whole survey clusters, within each stratum, to a final holdout
  (one cluster in five) and to cross-validation folds. Households are never split at random.
- `evaluate()` and the helpers below compute survey-weighted metrics.

Weights: `weight` for household-level metrics, `pop_wt` for person-level recall ("share of poor
people reached"). Models are trained with `weight` normalised to mean 1.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, ClassifierMixin
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, brier_score_loss, log_loss, roc_auc_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import FunctionTransformer, OneHotEncoder, StandardScaler

from src.features import build_household_master as bm
from src.features.household_cpi_shock import domain_mean

PROJECT_ROOT = Path(__file__).resolve().parents[2]
MASTER_PATH = PROJECT_ROOT / "data" / "processed" / "household_master.parquet"
SHOCK_PATH = PROJECT_ROOT / "data" / "processed" / "household_cpi_shock.parquet"
SPLITS_PATH = PROJECT_ROOT / "data" / "processed" / "model_splits.parquet"
MODELS_DIR = PROJECT_ROOT / "models"
REPORTS_DIR = PROJECT_ROOT / "reports"

RANDOM_STATE = 2026
HOLDOUT_EVERY = 5          # one cluster in five, within each stratum, goes to the final holdout
N_FOLDS = 5
TOP_K = (0.10, 0.20, 0.30)
VUP_LOAN_SOURCE = 8        # s10aq6: VUP financial service loan
VUP_SECTOR = 5             # s6bq5: institutional sector "VUP"


# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------
def program_free_employment() -> pd.DataFrame:
    """Employment features with VUP-sector jobs (Public Works) not counted as employment."""
    p = bm.read_person()
    vup_job = p["s6bq5"].eq(VUP_SECTOR)
    n_vup = vup_job.groupby(p["hhid"]).sum().astype(np.int16)
    p.loc[vup_job, ["s6bq4", "s6bq5", "s6bq7", "s6bq8"]] = np.nan
    emp = bm.employment(p)
    emp["n_vup_sector_jobs"] = n_vup.reindex(emp.index).fillna(0).astype(np.int16)
    return emp


def program_free_finance() -> pd.DataFrame:
    """Loan features with VUP Financial Services loans left out."""
    c = bm.read("credit", ["hhid", "s10aq6"])
    src = c["s10aq6"]
    formal_excl_vup = tuple(s for s in bm.FORMAL_LOAN_SOURCES if s != VUP_LOAN_SOURCE)
    out = pd.DataFrame({
        "any_loan_excl_vup": bm.any_by_hh(c, src.notna() & src.ne(VUP_LOAN_SOURCE)),
        "any_formal_loan_excl_vup": bm.any_by_hh(c, src.isin(formal_excl_vup)),
        "has_vup_fs_loan": bm.any_by_hh(c, src.eq(VUP_LOAN_SOURCE)),
    })
    out["n_loans_excl_vup"] = (src.notna() & src.ne(VUP_LOAN_SOURCE)).groupby(c["hhid"]).sum().astype(np.int16)
    for col in ["any_loan_excl_vup", "any_formal_loan_excl_vup", "has_vup_fs_loan"]:
        out[col] = bm.flag(out[col])
    return out


def load_frame() -> pd.DataFrame:
    """One row per household: master + shock + program-free features and scores."""
    master = pd.read_parquet(MASTER_PATH).set_index("hhid")
    shock = pd.read_parquet(SHOCK_PATH).set_index("hhid")
    df = master.join(shock[[c for c in shock.columns if c not in master.columns]])
    emp = program_free_employment()
    for col in emp.columns:
        df[f"{col}_pf" if col in df.columns else col] = emp[col].reindex(df.index)
    df = df.join(program_free_finance())
    df["urban"] = df["ur"].eq(1).astype(np.int8)
    f = lambda cond: cond.astype("boolean").fillna(False).astype(float)
    no_formal_job = f((df["n_employed_pf"] - df["n_informal_proxy_pf"]).le(0))
    df["c_income_instability_pf"] = (no_formal_job + f(df["agriculture_dependent_pf"].eq(1)) + f(df["n_casual_wage_pf"].gt(0))) / 3
    no_formal_account = f(df["any_bank_account"].eq(0) & df["any_sacco_account"].eq(0))
    df["c_savings_credit_gap_pf"] = (no_formal_account + f(df["any_formal_loan_excl_vup"].eq(0)) + f(df["any_tontine"].eq(0))) / 3
    # Distress score without its poverty and VUP components, program-free: the version allowed in the poverty model.
    df["distress_score_model"] = 100 * df[["c_inflation", "c_food_share", "c_income_instability_pf", "c_savings_credit_gap_pf"]].mean(axis=1)
    # Need score = distress excluding VUP (as in notebook 07), with program-free inputs: sensitivity for the VUP analysis.
    df["need_score_pf"] = 100 * df[["c_inflation", "c_food_share", "c_poverty", "c_income_instability_pf", "c_savings_credit_gap_pf"]].mean(axis=1)
    return df.reset_index()


# ---------------------------------------------------------------------------
# Features
# ---------------------------------------------------------------------------
MONEY = ["remittances_received_12m", "transfers_sent_12m", "income_private_other_12m", "income_farm_12m"]
GROUPS = {
    "geography": ["urban", "district"],
    "demographics": ["hh_size", "adult_equivalents", "n_children_0_4", "n_children_0_14", "n_working_age_15_64",
                     "n_elderly_65plus", "dependency_ratio", "share_dependents", "head_age", "n_members_with_disability",
                     "head_female", "no_working_age_member", "head_marital_status"],
    "education": ["head_education_code", "max_education_code", "n_children_in_school", "head_literate"],
    "employment_income_source": ["n_employed_pf", "n_own_farming_pf", "n_farm_wage_pf", "n_nonfarm_wage_pf",
                                 "n_nonfarm_self_employment_pf", "n_informal_proxy_pf", "n_casual_wage_pf",
                                 "share_employed_in_agriculture_pf", "share_employed_informal_proxy_pf",
                                 "agriculture_dependent_pf", "any_wage_worker_pf", "any_nonfarm_wage_worker_pf",
                                 "any_self_employed_pf", "any_agricultural_activity_pf", "any_nonfarm_business_pf",
                                 "head_employed_pf", "head_informal_proxy_pf", "main_livelihood_pf", "head_livelihood_pf"],
    "private_income": [*MONEY, "any_remittance_received"],
    "ict_finance": ["any_member_mobile_phone", "any_member_mobile_money_use", "any_account", "any_bank_account",
                    "any_sacco_account", "any_mobile_money_account", "any_tontine", "loan_denied_12m",
                    "any_loan_excl_vup", "any_formal_loan_excl_vup", "any_informal_loan", "n_loans_excl_vup",
                    "share_members_health_insured"],
    "assets": ["n_key_assets", "tropical_livestock_units", "n_cattle", "n_goats", "n_sheep", "n_pigs", "n_poultry",
               "owns_livestock", "owns_car", "owns_motorcycle", "owns_bicycle", "owns_solar_lamp", "owns_refrigerator",
               "owns_mobile_basic", "owns_smartphone", "owns_computer", "owns_television", "owns_radio", "owns_mobile_phone"],
    "housing": ["sleeping_rooms", "persons_per_sleeping_room", "tenure_owner", "tenure_renter", "improved_wall",
                "improved_roof", "improved_floor", "improved_drinking_water", "electricity_any", "electricity_grid",
                "clean_cooking_fuel", "cooking_fuel_firewood", "cooking_fuel_charcoal", "improved_sanitation",
                "basic_sanitation", "internet_at_home", "any_shock_12m", "shock_high_food_prices"],
    "services": ["minutes_to_drinking_water", "minutes_to_food_market", "minutes_to_produce_market",
                 "minutes_to_public_transport", "minutes_to_primary_school", "minutes_to_secondary_school",
                 "minutes_to_district_hospital", "minutes_to_health_centre"],
    "expenditure_shares": ["share_food", "share_meals_away", "share_alcohol_tobacco", "share_housing_utilities",
                           "share_energy", "share_transport", "share_education", "share_communication", "share_health",
                           "share_food_own_produced", "basket_share_of_consumption"],
    "cpi_shock": ["price_change_pct", "food_shock_pp", "energy_shock_pp", "transport_shock_pp",
                  "education_shock_pp", "communication_shock_pp"],
    "distress": ["distress_score_model"],
}
CATEGORICAL = {"district", "head_marital_status", "main_livelihood_pf", "head_livelihood_pf"}
CONSUMPTION_DERIVED = ["expenditure_shares", "cpi_shock", "distress"]

# Never features. Each entry: reason. Checked by `assert_no_leakage`.
LEAKAGE = {
    "poverty": {
        **{c: "poverty target or defines it (consumption level, lines, welfare ranks)" for c in [
            "poor", "extreme_poor", "welfare_category", "welfare_category_name", "quintile", "welfare_ratio", "near_poor",
            "cons_nominal", "cons_nominal_ae", "cons_real_ae_jan2024", "cons_real_jan2024", "cons_real_pc_jan2024",
            "hh_price_index", "food", "food_at_school", *[f"exp{i}" for i in range(1, 12)],
            "extra_cost_same_basket_rwf", "extra_cost_same_basket_rwf_per_ae", "poverty_line_jan2024", "extreme_line_jan2024"]},
        "exp_cell_*": "consumption level by cell",
        "c_poverty": "built from poverty status and the welfare ratio",
        "distress_score": "contains c_poverty and c_no_vup",
        "distress_quintile": "from distress_score",
        "distress_score_excl_vup": "contains c_poverty",
        "distress_quintile_excl_vup": "from distress_score_excl_vup",
        "need_score_pf": "contains c_poverty",
        "vup_*": "program participation (circular for targeting)",
        "c_no_vup": "program participation",
        "girinka_cow_received": "program participation",
        "any_public_support": "public transfer receipt (targeted programs)",
        "income_public_support_12m": "public transfer receipt",
        "received_govt_goods_donation": "public transfer receipt",
        "has_vup_fs_loan": "VUP Financial Services",
        "n_vup_sector_jobs": "VUP Public Works employment",
    },
    "vup": {
        "vup_*": "target and its components",
        "c_no_vup": "target",
        "distress_score": "contains c_no_vup",
        "distress_quintile": "from distress_score",
        "has_vup_fs_loan": "VUP Financial Services loan in the credit module",
        "n_vup_sector_jobs": "VUP Public Works jobs in the employment module",
        "any_formal_loan": "includes VUP loans (use any_formal_loan_excl_vup)",
        "any_loan_12m": "includes VUP loans",
        "n_loans": "includes VUP loans",
        "n_nonfarm_wage": "includes VUP-sector jobs (use the _pf version)",
        "main_livelihood": "includes VUP-sector jobs (use the _pf version)",
        "c_income_instability": "includes VUP-sector jobs",
        "c_savings_credit_gap": "includes VUP loans",
    },
}


@dataclass
class FeatureSpec:
    name: str
    groups: list[str]
    extra: list[str] = field(default_factory=list)

    @property
    def columns(self) -> list[str]:
        cols = [c for g in self.groups for c in GROUPS[g]] + self.extra
        return list(dict.fromkeys(cols))

    @property
    def categorical(self) -> list[str]:
        return [c for c in self.columns if c in CATEGORICAL]

    @property
    def money(self) -> list[str]:
        return [c for c in self.columns if c in MONEY]

    @property
    def numeric(self) -> list[str]:
        return [c for c in self.columns if c not in CATEGORICAL and c not in MONEY]


def assert_no_leakage(spec: FeatureSpec, target: str) -> None:
    for col in spec.columns:
        for pattern, reason in LEAKAGE[target].items():
            hit = col.startswith(pattern[:-1]) if pattern.endswith("*") else col == pattern
            assert not hit, f"{col} is a leakage variable for the {target} model: {reason}"


# ---------------------------------------------------------------------------
# Splits: whole clusters, within strata
# ---------------------------------------------------------------------------
def make_splits(df: pd.DataFrame, seed: int = RANDOM_STATE) -> pd.DataFrame:
    """Holdout = one cluster in five within each stratum; the rest get CV folds 0-4 within stratum."""
    rng = np.random.default_rng(seed)
    rows = []
    for stratum, g in df.groupby("strata_id"):
        clusters = rng.permutation(np.sort(g["clust"].unique()))
        offset = rng.integers(HOLDOUT_EVERY)
        holdout = [c for i, c in enumerate(clusters) if (i + offset) % HOLDOUT_EVERY == 0]
        dev = [c for c in clusters if c not in holdout]
        fold_offset = rng.integers(N_FOLDS)
        for c in holdout:
            rows.append((c, stratum, "holdout", -1))
        for i, c in enumerate(dev):
            rows.append((c, stratum, "development", (i + fold_offset) % N_FOLDS))
    clusters = pd.DataFrame(rows, columns=["clust", "strata_id", "split", "fold"])
    out = df[["hhid", "clust"]].merge(clusters[["clust", "split", "fold"]], on="clust", how="left")
    assert out["split"].notna().all()
    return out


def load_splits() -> pd.DataFrame:
    return pd.read_parquet(SPLITS_PATH)


# ---------------------------------------------------------------------------
# Pipelines
# ---------------------------------------------------------------------------
def make_preprocessor(spec: FeatureSpec, scale: bool) -> ColumnTransformer:
    num_steps = [("impute", SimpleImputer(strategy="median", add_indicator=True))]
    money_steps = [("impute", SimpleImputer(strategy="median", add_indicator=True)),
                   ("log1p", FunctionTransformer(np.log1p, feature_names_out="one-to-one"))]
    if scale:
        num_steps.append(("scale", StandardScaler()))
        money_steps.append(("scale", StandardScaler()))
    cat = Pipeline([("impute", SimpleImputer(strategy="most_frequent")),
                    ("onehot", OneHotEncoder(handle_unknown="ignore", sparse_output=False))])
    transformers = [("num", Pipeline(num_steps), spec.numeric)]
    if spec.money:
        transformers.append(("money", Pipeline(money_steps), spec.money))
    if spec.categorical:
        transformers.append(("cat", cat, spec.categorical))
    return ColumnTransformer(transformers, verbose_feature_names_out=True)


class GroupRateBaseline(BaseEstimator, ClassifierMixin):
    """Predicts the weighted rate of the target in the household's group (e.g. district), learned on training data."""

    def __init__(self, group_col: str = "district"):
        self.group_col = group_col

    def fit(self, X, y, sample_weight=None):
        w = np.ones(len(y)) if sample_weight is None else np.asarray(sample_weight, float)
        y = np.asarray(y, float)
        g = pd.Series(np.asarray(X[self.group_col]))
        t = pd.DataFrame({"g": g, "wy": w * y, "w": w}).groupby("g")[["wy", "w"]].sum()
        self.rates_ = (t["wy"] / t["w"]).to_dict()
        self.overall_ = float((w * y).sum() / w.sum())
        self.classes_ = np.array([0, 1])
        return self

    def predict_proba(self, X):
        p = pd.Series(np.asarray(X[self.group_col])).map(self.rates_).fillna(self.overall_).to_numpy(float)
        return np.column_stack([1 - p, p])

    def predict(self, X):
        return (self.predict_proba(X)[:, 1] >= 0.5).astype(int)


def fit_pipeline(pipe: Pipeline, X: pd.DataFrame, y: pd.Series, w: pd.Series) -> Pipeline:
    wn = (w / w.mean()).to_numpy()
    return pipe.fit(X, y.to_numpy(int), model__sample_weight=wn)


def cross_validate(pipes: dict[str, Pipeline], data: pd.DataFrame, columns: dict[str, list[str]], target: str,
                   folds: pd.Series) -> pd.DataFrame:
    """Out-of-fold predicted probabilities for every model (columns = model names)."""
    from sklearn.base import clone
    oof = pd.DataFrame(index=data.index, columns=list(pipes), dtype=float)
    for f in sorted(folds.unique()):
        tr, te = folds.ne(f), folds.eq(f)
        for name, pipe in pipes.items():
            fitted = fit_pipeline(clone(pipe), data.loc[tr, columns[name]], data.loc[tr, target], data.loc[tr, "weight"])
            oof.loc[te, name] = fitted.predict_proba(data.loc[te, columns[name]])[:, 1]
    return oof


# ---------------------------------------------------------------------------
# Metrics (survey-weighted)
# ---------------------------------------------------------------------------
def top_k_inclusion(p: np.ndarray, w: np.ndarray, k: float) -> np.ndarray:
    """Inclusion weight (0-1) of each household when the top k share of weighted households is selected.

    Households tied at the cut-off are included fractionally, so ties (e.g. a district baseline) are fair.
    """
    p, w = np.asarray(p, float), np.asarray(w, float)
    target = k * w.sum()
    s = pd.DataFrame({"p": p, "w": w}).groupby("p")["w"].sum().sort_index(ascending=False)
    above = s.cumsum() - s
    thr_idx = np.searchsorted(s.cumsum().to_numpy(), target, side="left")
    thr_idx = min(thr_idx, len(s) - 1)
    thr = s.index[thr_idx]
    frac = (target - above.iloc[thr_idx]) / s.iloc[thr_idx]
    return np.where(p > thr, 1.0, np.where(p == thr, frac, 0.0))


def calibration_slope_intercept(y, p, w) -> tuple[float, float]:
    lp = np.log(np.clip(p, 1e-6, 1 - 1e-6) / (1 - np.clip(p, 1e-6, 1 - 1e-6)))
    lr = LogisticRegression(C=1e6, max_iter=1000).fit(lp.reshape(-1, 1), y, sample_weight=w / w.mean())
    return float(lr.coef_[0, 0]), float(lr.intercept_[0])


def evaluate(y, p, w, pw=None, k_values=TOP_K) -> dict:
    """ROC-AUC, PR-AUC, Brier, log loss, calibration and top-k precision/recall, all survey-weighted."""
    y, p, w = np.asarray(y, int), np.asarray(p, float), np.asarray(w, float)
    pw = w if pw is None else np.asarray(pw, float)
    out = {"n": len(y), "base_rate": float((w * y).sum() / w.sum()),
           "roc_auc": roc_auc_score(y, p, sample_weight=w), "pr_auc": average_precision_score(y, p, sample_weight=w),
           "brier": brier_score_loss(y, p, sample_weight=w),
           "log_loss": log_loss(y, np.clip(p, 1e-6, 1 - 1e-6), sample_weight=w),
           "mean_predicted": float((w * p).sum() / w.sum())}
    out["calibration_in_the_large"] = out["mean_predicted"] - out["base_rate"]
    out["calibration_slope"], out["calibration_intercept"] = calibration_slope_intercept(y, p, w)
    for k in k_values:
        inc = top_k_inclusion(p, w, k)
        tag = f"top{int(round(100 * k))}"
        out[f"precision_{tag}"] = float((inc * w * y).sum() / (inc * w).sum())
        out[f"recall_{tag}"] = float((inc * w * y).sum() / (w * y).sum())
        out[f"recall_people_{tag}"] = float((inc * pw * y).sum() / (pw * y).sum())
    return out


def calibration_table(y, p, w, n_bins: int = 10) -> pd.DataFrame:
    """Weighted observed rate vs mean prediction in bins of predicted probability (deciles)."""
    d = pd.DataFrame({"y": np.asarray(y, float), "p": np.asarray(p, float), "w": np.asarray(w, float)})
    d["bin"] = pd.qcut(d["p"].rank(method="first"), n_bins, labels=False)
    g = d.groupby("bin")
    return pd.DataFrame({"mean_predicted": g.apply(lambda x: np.average(x["p"], weights=x["w"])),
                         "observed": g.apply(lambda x: np.average(x["y"], weights=x["w"])),
                         "households": g.size()})


def cluster_bootstrap(data: pd.DataFrame, scores: list[str], target: str, B: int = 500, seed: int = RANDOM_STATE,
                      baseline: str | None = None, metrics=("roc_auc", "pr_auc", "brier", "recall_people_top20",
                                                            "precision_top20")) -> pd.DataFrame:
    """Percentile 95% CIs for metrics (and differences vs `baseline`), resampling clusters within strata."""
    rng = np.random.default_rng(seed)
    idx_by = {s: [g.index.to_numpy() for _, g in d.groupby("clust")] for s, d in data.reset_index(drop=True).groupby("strata_id")}
    base = data.reset_index(drop=True)
    draws = []
    for _ in range(B):
        rows = np.concatenate([np.concatenate([cl[i] for i in rng.integers(len(cl), size=len(cl))]) for cl in idx_by.values()])
        d = base.iloc[rows]
        res = {}
        for s in scores:
            e = evaluate(d[target], d[s], d["weight"], d["pop_wt"])
            for m in metrics:
                res[(s, m)] = e[m]
        draws.append(res)
    draws = pd.DataFrame(draws)
    rows = []
    for s in scores:
        for m in metrics:
            v = draws[(s, m)]
            row = {"score": s, "metric": m, "ci_low": v.quantile(0.025), "ci_high": v.quantile(0.975)}
            if baseline and s != baseline:
                dv = v - draws[(baseline, m)]
                row.update({"diff_vs_baseline_ci_low": dv.quantile(0.025), "diff_vs_baseline_ci_high": dv.quantile(0.975),
                            "share_of_draws_better": float((dv < 0).mean() if m in ("brier", "log_loss") else (dv > 0).mean())})
            rows.append(row)
    return pd.DataFrame(rows)


def subgroup_metrics(data: pd.DataFrame, score: str, target: str, by: str, k: float = 0.20,
                     min_positives: int = 20) -> pd.DataFrame:
    """Per-group performance. Selection uses the national top-k cut-off, so recall shows who a national ranking reaches."""
    inc = top_k_inclusion(data[score], data["weight"], k)
    d = data.assign(_inc=inc)
    rows = []
    for g, x in d.groupby(by):
        y, p, w, pw = x[target].to_numpy(int), x[score].to_numpy(float), x["weight"].to_numpy(float), x["pop_wt"].to_numpy(float)
        pos = int(y.sum())
        row = {"group": g, "households": len(x), "positives": pos, "observed_rate": np.average(y, weights=w),
               "mean_predicted": np.average(p, weights=w), "selected_share": np.average(x["_inc"], weights=w),
               "recall_people_at_national_top20": (x["_inc"] * pw * y).sum() / (pw * y).sum() if pos else np.nan,
               "false_positive_rate_at_national_top20": (x["_inc"] * w * (1 - y)).sum() / (w * (1 - y)).sum()}
        row["calibration_gap"] = row["mean_predicted"] - row["observed_rate"]
        ok = pos >= min_positives and pos < len(x)
        row["roc_auc"] = roc_auc_score(y, p, sample_weight=w) if ok else np.nan
        row["pr_auc"] = average_precision_score(y, p, sample_weight=w) if ok else np.nan
        row["reliable"] = ok
        rows.append(row)
    return pd.DataFrame(rows).set_index("group")


def weighted_rate_table(df: pd.DataFrame, y: str, by: str, weight: str = "pop_wt", order=None) -> pd.DataFrame:
    """Weighted mean of y per group with a design-based SE and 95% CI (Taylor linearisation, strata and clusters)."""
    groups = order if order is not None else sorted(df[by].dropna().unique())
    rows = []
    for g in groups:
        m, se = domain_mean(df[y].astype(float), df[weight], df[by].eq(g), df["strata_id"], df["clust"])
        rows.append({"group": g, "households": int(df[by].eq(g).sum()), "mean": m, "se": se,
                     "ci_low": m - 1.96 * se, "ci_high": m + 1.96 * se})
    return pd.DataFrame(rows).set_index("group")


def subgroup_bootstrap(data: pd.DataFrame, score: str, target: str, by: str, B: int = 200, seed: int = RANDOM_STATE,
                       metrics=("roc_auc", "recall_people_at_national_top20", "calibration_gap")) -> pd.DataFrame:
    """Subgroup metrics with percentile 95% CIs from a cluster bootstrap (clusters resampled within strata)."""
    rng = np.random.default_rng(seed)
    base = data.reset_index(drop=True)
    idx_by = {s: [g.index.to_numpy() for _, g in d.groupby("clust")] for s, d in base.groupby("strata_id")}
    point = subgroup_metrics(base, score, target, by)
    draws = []
    for _ in range(B):
        rows = np.concatenate([np.concatenate([cl[i] for i in rng.integers(len(cl), size=len(cl))]) for cl in idx_by.values()])
        draws.append(subgroup_metrics(base.iloc[rows], score, target, by)[list(metrics)])
    stacked = pd.concat(draws, keys=range(B), names=["draw", "group"])
    for m in metrics:
        q = stacked[m].groupby("group").quantile([0.025, 0.975]).unstack()
        lo, hi = q[0.025].reindex(point.index), q[0.975].reindex(point.index)
        if m in ("roc_auc", "pr_auc"):  # no interval where the point estimate is not reliable
            lo, hi = lo.where(point["reliable"]), hi.where(point["reliable"])
        point[f"{m}_ci_low"], point[f"{m}_ci_high"] = lo, hi
    return point
