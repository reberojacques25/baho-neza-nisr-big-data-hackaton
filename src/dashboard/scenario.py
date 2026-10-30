"""Scenario engine for Baho Neza: price changes and support responses, computed from aggregated tables only.

Pure pandas, no Streamlit. Every calculation-relevant input lives in a normalised, language-independent spec (a dict
of plain values), and `fingerprint` hashes the specs a result depends on, so the app can tell when a saved result no
longer matches the current inputs.

Price scenario. Increases p_c (percent, cumulative over the horizon) are applied on top of the reference basket, which
already carries the observed CPI change from January 2024 to the latest CPI month (built offline). Nothing observed is
applied twice. Because the extra cost sum_c ref_c x p_c is linear, group means from the aggregates are exact.

Support. Recipients come from the planning table (dashboard_planning): a planning group for a new cash transfer, the
validated Direct Support coverage-expansion scenario, or current NSDS households for a benefit increase.
    payments          = duration_months / payment_interval_months
    direct transfers  = recipient households x amount per payment x payments
    delivery costs    = direct transfers x delivery_pct / 100
    total             = direct transfers + delivery costs
Cash does not change prices; a benefit increase adds no recipients. No poverty change is computed: transfers are not
added to consumption to re-measure poverty (no validated consumption-response or price-updated poverty line).
"""
from __future__ import annotations

import hashlib
import json
import math

import numpy as np
import pandas as pd

CATEGORIES = ["food", "energy", "transport", "education", "other"]
PRICE_MODES = ["simple", "detailed"]
HORIZONS = [3, 6, 12]                     # months after the latest CPI month
MAX_INCREASE_PCT = 100.0
AREAS = ["all", "urban", "rural"]
NATIONAL = "Rwanda"
GROUP_DIMENSIONS = {"head_sex": ["female", "male"], "disability": ["yes", "no"], "elderly": ["yes", "no"],
                    "poverty": ["poor", "nonpoor"]}

ACTIONS = ["cash", "ds_expansion", "nsds_increase"]
UNAVAILABLE_ACTIONS = ["public_works", "school_costs", "food_assistance", "livelihoods", "combined"]
RULES = {"poverty_top": [10, 20, 30], "distress_top": [10, 20, 30], "high_need_no_vup": [100]}
DS_LEVELS = [1, 2, 5]
FREQUENCIES = {"monthly": 1, "quarterly": 3}
DURATIONS = [0, 3, 6, 12]
QUARTER = 3
DEFAULT_PRICE = {"mode": "simple", "horizon_months": 12, "all": 10.0}
DEFAULT_SUPPORT = {"action": "cash", "rule": "poverty_top", "level": 20, "amount_rwf": 10_000, "frequency": "monthly",
                   "duration_months": 12, "delivery_pct": 0.0, "ds_level": 2, "ds_payment_quarterly_rwf": 30_500,
                   "nsds_increase_pct": 10.0}


class UnsupportedScenario(ValueError):
    """A scenario the data cannot support. `code` is a translation key suffix (errors.<code>)."""

    def __init__(self, code: str, **details):
        super().__init__(code)
        self.code = code
        self.details = details


# ---------------------------------------------------------------------------
# Specs and fingerprints
# ---------------------------------------------------------------------------
def _pct(v, name: str) -> float:
    v = float(v)
    if not (0 <= v <= MAX_INCREASE_PCT) or math.isnan(v):
        raise UnsupportedScenario("increase_range", name=name)
    return round(v, 4)


def price_spec(mode: str = "simple", horizon_months: int = 12, all_pct: float = 0.0,
               detailed: dict[str, float] | None = None) -> dict:
    """Normalised price scenario. Simple mode applies one increase to every category; detailed mode one per category.
    The modes are exclusive: only the chosen mode's inputs enter the spec."""
    if mode not in PRICE_MODES:
        raise UnsupportedScenario("unknown_mode")
    if int(horizon_months) not in HORIZONS:
        raise UnsupportedScenario("horizon")
    if mode == "simple":
        p = _pct(all_pct, "all")
        increases = {c: p for c in CATEGORIES}
    else:
        detailed = detailed or {}
        unknown = set(detailed) - set(CATEGORIES)
        if unknown:
            raise UnsupportedScenario("unknown_category", categories=sorted(unknown))
        increases = {c: _pct(detailed.get(c, 0.0), c) for c in CATEGORIES}
    return {"mode": mode, "horizon_months": int(horizon_months), "increases": increases}


def support_spec(action: str, *, rule: str = "poverty_top", level: int = 20, amount_rwf: float = 0.0,
                 frequency: str = "monthly", duration_months: int = 12, delivery_pct: float = 0.0, ds_level: float = 2,
                 ds_payment_quarterly_rwf: float = 30_500, nsds_increase_pct: float = 0.0) -> dict:
    """Normalised support action. Only the inputs that the chosen action uses enter the spec."""
    if action in UNAVAILABLE_ACTIONS:
        raise UnsupportedScenario("action_unavailable", action=action)
    if action not in ACTIONS:
        raise UnsupportedScenario("unknown_action", action=action)
    duration_months = int(duration_months)
    if duration_months not in DURATIONS:
        raise UnsupportedScenario("duration")
    delivery_pct = float(delivery_pct)
    if not 0 <= delivery_pct <= 100:
        raise UnsupportedScenario("delivery_range")
    common = {"action": action, "duration_months": duration_months, "delivery_pct": round(delivery_pct, 4)}
    if action == "cash":
        if rule not in RULES or int(level) not in RULES[rule]:
            raise UnsupportedScenario("planning_group")
        if frequency not in FREQUENCIES:
            raise UnsupportedScenario("frequency")
        if duration_months % FREQUENCIES[frequency]:
            raise UnsupportedScenario("duration_frequency")
        if float(amount_rwf) < 0:
            raise UnsupportedScenario("amount_range")
        return {**common, "rule": rule, "level": int(level), "amount_rwf": round(float(amount_rwf), 2), "frequency": frequency}
    if duration_months % QUARTER:
        raise UnsupportedScenario("duration_frequency")
    if action == "ds_expansion":
        if float(ds_level) not in DS_LEVELS:
            raise UnsupportedScenario("ds_level")
        if float(ds_payment_quarterly_rwf) < 0:
            raise UnsupportedScenario("amount_range")
        return {**common, "level": float(ds_level), "payment_quarterly_rwf": round(float(ds_payment_quarterly_rwf), 2)}
    return {**common, "increase_pct": _pct(nsds_increase_pct, "nsds")}


def fingerprint(*parts) -> str:
    """Stable hash of every calculation-relevant input (specs, geography). Language is never part of it."""
    blob = json.dumps(parts, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Table look-ups
# ---------------------------------------------------------------------------
def group_row(groups: pd.DataFrame, geo: str, area: str, dimension: str = "all", group: str = "all") -> pd.Series:
    m = groups["geo"].eq(geo) & groups["area"].eq(area) & groups["dimension"].eq(dimension) & groups["group"].eq(group)
    if m.sum() != 1:
        raise UnsupportedScenario("geography", geo=geo, area=area)
    return groups.loc[m].iloc[0]


def planning_row(planning: pd.DataFrame, rule: str, level: float, geo: str, area: str) -> pd.Series:
    m = planning["rule"].eq(rule) & planning["level"].eq(level) & planning["geo"].eq(geo) & planning["area"].eq(area)
    if m.sum() != 1:
        raise UnsupportedScenario("planning_group")
    row = planning.loc[m].iloc[0]
    if bool(row["suppressed"]):
        raise UnsupportedScenario("suppressed", geo=geo, area=area)
    return row


def reference_costs(row: pd.Series) -> dict[str, float]:
    return {c: float(row[f"ref_{c}"]) for c in CATEGORIES}


# ---------------------------------------------------------------------------
# Price scenario
# ---------------------------------------------------------------------------
def basket_effect(ref: dict[str, float], increases: dict[str, float]) -> dict:
    """Monthly basket cost per household before and after the scenario increases (RWF), and the derived shares."""
    reference = sum(ref.values())
    extra_by = {c: ref[c] * increases[c] / 100 for c in CATEGORIES}
    extra = sum(extra_by.values())
    scenario = reference + extra
    return {"reference_monthly": reference, "scenario_monthly": scenario, "extra_monthly": extra,
            "reference_by_category": dict(ref), "extra_by_category": extra_by, "basket_change_pct": 100 * extra / reference if reference else np.nan,
            "purchasing_power_change_pct": -100 * extra / scenario if scenario else np.nan}


def price_result(groups: pd.DataFrame, geo: str, area: str, spec: dict) -> dict:
    row = group_row(groups, geo, area)
    if bool(row["suppressed"]):
        raise UnsupportedScenario("suppressed", geo=geo, area=area)
    eff = basket_effect(reference_costs(row), spec["increases"])
    out = {"geo": geo, "area": area, "spec": spec, "households": float(row["households"]), "people": float(row["people"]),
           **eff, "extra_monthly_total": eff["extra_monthly"] * float(row["households"]),
           "observed_change_pct": float(row["basket_change_pct"]), "exposed": exposed_groups(groups, geo, area, spec)}
    return out


def exposed_groups(groups: pd.DataFrame, geo: str, area: str, spec: dict) -> list[dict]:
    """Basket change by household group (published cells only), most exposed first."""
    sub = groups[groups["geo"].eq(geo) & groups["area"].eq(area) & groups["dimension"].ne("all") & ~groups["suppressed"]]
    rows = []
    for _, r in sub.iterrows():
        eff = basket_effect(reference_costs(r), spec["increases"])
        rows.append({"dimension": r["dimension"], "group": r["group"], "households": float(r["households"]),
                     "basket_change_pct": eff["basket_change_pct"], "extra_monthly": eff["extra_monthly"],
                     "reference_monthly": eff["reference_monthly"]})
    return sorted(rows, key=lambda x: (-x["basket_change_pct"], -x["extra_monthly"]))


# ---------------------------------------------------------------------------
# Support comparison
# ---------------------------------------------------------------------------
def _support_parameters(spec: dict, row: pd.Series) -> tuple[float, float, float]:
    """(amount per payment per household, payment interval in months, new recipients share 0/1)."""
    if spec["action"] == "cash":
        return spec["amount_rwf"], FREQUENCIES[spec["frequency"]], 1.0
    if spec["action"] == "ds_expansion":
        return spec["payment_quarterly_rwf"], QUARTER, 1.0
    return float(row["mean_quarterly_payment_rwf"]) * spec["increase_pct"] / 100, QUARTER, 0.0


def recipients_row(planning: pd.DataFrame, geo: str, area: str, spec: dict) -> pd.Series:
    if spec["action"] == "cash":
        return planning_row(planning, spec["rule"], spec["level"], geo, area)
    if spec["action"] == "ds_expansion":
        return planning_row(planning, "ds_expansion", spec["level"], geo, area)
    return planning_row(planning, "nsds_current", 100, geo, area)


def compare(planning: pd.DataFrame, geo: str, area: str, price: dict, support: dict) -> dict:
    """Reference | price shock only | price shock + support, for the recipients of `support` in geo x area."""
    row = recipients_row(planning, geo, area, support)
    households, people = float(row["households"]), float(row["people"])
    eff = basket_effect(reference_costs(row), price["increases"])
    amount, interval, new_share = _support_parameters(support, row)
    payments = support["duration_months"] // interval
    monthly_support = amount / interval if payments > 0 else 0.0
    transfers = households * amount * payments
    delivery = transfers * support["delivery_pct"] / 100
    extra = eff["extra_monthly"]
    columns = {
        "reference": {"basket": eff["reference_monthly"], "extra": 0.0, "support": 0.0, "not_offset": 0.0},
        "shock": {"basket": eff["scenario_monthly"], "extra": extra, "support": 0.0, "not_offset": extra},
        "shock_support": {"basket": eff["scenario_monthly"], "extra": extra, "support": monthly_support,
                          "not_offset": max(extra - monthly_support, 0.0)},
    }
    return {
        "geo": geo, "area": area, "price": price, "support": support,
        "scope": str(row["scope"]), "columns": columns,
        "surplus_monthly": max(monthly_support - extra, 0.0),
        "recipient_households": households, "recipient_people": people,
        "new_recipient_households": households * new_share, "new_recipient_people": people * new_share,
        "poor_households": float(row["poor_households"]), "poor_people": float(row["poor_people"]),
        "amount_per_payment": amount, "payment_interval_months": interval, "payments": payments,
        "direct_transfers": transfers, "delivery_costs": delivery, "total_cost": transfers + delivery,
        "extra_monthly_total": extra * households,
        "not_offset_monthly_total": max(extra - monthly_support, 0.0) * households,
        "uncovered_high_need_reached": float(row["uncovered_high_need_reached"]),
    }
