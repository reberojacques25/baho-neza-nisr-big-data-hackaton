"""Plain-language explanations of verified Baho Neza results (no provider code here; see ai_service.py).

Every explanation starts from *facts*: an allowlisted set of values taken from a completed, valid, disclosure-approved
result (`scenario.price_result` / `scenario.compare`), each with an explicit unit and a display string formatted by
Baho Neza in the chosen language. Illustrative examples are computed here, in Python.

- `deterministic_sections` fills translated templates with the facts. It is always shown and is the fallback.
- `build_payload` is the only data that may leave the app for the optional AI explanation (docs/ai_explanation.md).
- `validate_response` accepts AI text only if it uses fact placeholders ([[fact_key]]) for every number, references
  allowed facts and limitations only, respects length limits and contains no markup. Baho Neza then inserts the
  numbers itself. These checks reduce, but cannot remove, the risk of wrong or poorly translated wording.
"""
from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass

from src.dashboard import logic as lg
from src.dashboard.i18n import translate
from src.dashboard.scenario import CATEGORIES

KINDS = ("price", "compare")
SECTIONS = ("tested", "meaning", "example", "support", "limitation")
PRICE_LIMITATIONS = ("not_forecast", "no_substitution", "incomes_fixed", "survey_age")
COMPARE_LIMITATIONS = ("no_poverty_change", "averages", "survey_age", "not_eligibility", "national_rule")
PRICE_FACTS = ("place", "baseline_month", "horizon_months", "increase_all_pct",
               *(f"increase_{c}_pct" for c in CATEGORIES), "basket_change_pct", "reference_monthly_rwf",
               "extra_monthly_rwf", "purchasing_power_loss_pct", "households", "extra_monthly_total_rwf",
               "example_budget_rwf", "example_new_rwf", "example_extra_rwf")
COMPARE_FACTS = ("place", "programme", "recipient_group", "payment", "price_scenario", "duration_months", "payments",
                 "new_recipient_households", "new_recipient_people", "existing_recipient_households",
                 "poor_recipient_households", "extra_monthly_rwf", "support_monthly_rwf", "not_offset_monthly_rwf",
                 "direct_transfers_rwf", "delivery_costs_rwf", "total_cost_rwf", "example_per_household_rwf")
PAYLOAD_KEYS = {"scenario_id", "kind", "language", "facts", "limitations", "support_section_required", "word_target"}
MAX_PAYLOAD_CHARS = 8_000
MAX_RESPONSE_CHARS = 4_000
WORD_LIMITS = {"en": (60, 200), "rw": (60, 280)}      # whole explanation; target about 100-150 English words
SECTION_WORD_LIMIT = {"en": 80, "rw": 110}
PLACEHOLDER = re.compile(r"\[\[([a-z0-9_]+)\]\]")
FORBIDDEN_MARKUP = re.compile(r"[<>`{}\[\]|\\]|https?:|www\.|javascript:", re.I)
# Claims the explanation must never make (English only; Kinyarwanda relies on the other checks and human review)
FORBIDDEN_CLAIMS = ("will reduce poverty", "will lift", "out of poverty", "we recommend", "i recommend", "you should",
                    "should implement", "will happen", "guarantees")


@dataclass(frozen=True)
class Fact:
    value: float | int | str
    unit: str            # rwf_per_household_per_month, rwf_per_month_all_households, rwf_total, percent_price_increase,
                         # percent_change, households, people, months, payments, text
    meaning: str         # English description sent to the model
    display: str         # formatted by Baho Neza in the chosen language


class InvalidExplanation(ValueError):
    """The AI response failed validation; the deterministic explanation is used instead."""


# ---------------------------------------------------------------------------
# Facts (from valid aggregate results only)
# ---------------------------------------------------------------------------
def _num(v) -> float:
    v = float(v)
    if not math.isfinite(v):
        raise ValueError("hidden or missing value: a suppressed cell can never enter an explanation")
    return v


def price_facts(result: dict, meta: dict, lang: str) -> dict[str, Fact]:
    spec = result["spec"]
    inc = spec["increases"]
    f = {
        "place": Fact(lg.geography_label(result["geo"], result["area"], lang), "text", "place and area", ""),
        "baseline_month": Fact(meta["latest_cpi_month"], "text", "latest observed CPI month; increases are added on top of its prices", ""),
        "horizon_months": Fact(spec["horizon_months"], "months", "period over which the increases happen (cumulative)", ""),
    }
    if spec["mode"] == "simple":
        f["increase_all_pct"] = Fact(_num(inc["food"]), "percent_price_increase", "extra price increase for all goods over the period", "")
    else:
        for c in CATEGORIES:
            f[f"increase_{c}_pct"] = Fact(_num(inc[c]), "percent_price_increase", f"extra price increase for {c} over the period", "")
    change = _num(result["basket_change_pct"])
    f.update({
        "basket_change_pct": Fact(change, "percent_change", "change in the cost of the same basket, scenario vs latest prices", ""),
        "reference_monthly_rwf": Fact(_num(result["reference_monthly"]), "rwf_per_household_per_month", "average basket cost today", ""),
        "extra_monthly_rwf": Fact(_num(result["extra_monthly"]), "rwf_per_household_per_month", "average extra cost", ""),
        "purchasing_power_loss_pct": Fact(-_num(result["purchasing_power_change_pct"]), "percent_change",
                                          "how much less the same money buys if incomes are unchanged", ""),
        "households": Fact(_num(result["households"]), "households", "households in this place (survey estimate)", ""),
        "extra_monthly_total_rwf": Fact(_num(result["extra_monthly_total"]), "rwf_per_month_all_households",
                                        "extra cost for all households in this place, per month", ""),
        # The example is the result itself, told for the average household in this place (not a made-up budget)
        "example_budget_rwf": Fact(_num(result["reference_monthly"]), "rwf_per_household_per_month",
                                   "EXAMPLE: average household in this place, monthly basket cost today (from the result)", ""),
        "example_new_rwf": Fact(_num(result["scenario_monthly"]), "rwf_per_household_per_month",
                                "EXAMPLE: the same household's monthly basket cost after the price change (from the result)", ""),
        "example_extra_rwf": Fact(_num(result["extra_monthly"]), "rwf_per_household_per_month",
                                  "EXAMPLE: how much more that household pays each month (from the result)", ""),
    })
    return _with_display(f, lang)


def compare_facts(result: dict, meta: dict, lang: str, price_label: str) -> dict[str, Fact]:
    s = result["support"]
    tr = lambda k, **kw: translate(k, lang, **kw)  # noqa: E731
    if s["action"] == "cash":
        group = tr("compare.group_cash", rule=tr(f"rule.{s['rule']}.name"),
                   level=tr("compare.level_all") if s["level"] == 100 else tr("compare.level_share", pct=s["level"]))
        payment = tr("compare.payment_cash", amount=lg.fmt_rwf(s["amount_rwf"], lang), frequency=tr(f"frequency.{s['frequency']}"))
    elif s["action"] == "ds_expansion":
        group = tr("compare.group_ds", pp=s["level"])
        payment = tr("compare.payment_ds", amount=lg.fmt_rwf(s["payment_quarterly_rwf"], lang))
    else:
        group = tr("compare.group_nsds")
        payment = tr("compare.payment_nsds", pct=f"{s['increase_pct']:g}", amount=lg.fmt_rwf(result["amount_per_payment"], lang))
    col = result["columns"]["shock_support"]
    existing = s["action"] == "nsds_increase"
    f = {
        "place": Fact(lg.geography_label(result["geo"], result["area"], lang), "text", "place and area", ""),
        "programme": Fact(tr(f"action.{s['action']}.name"), "text", "support programme", ""),
        "recipient_group": Fact(group, "text", "who receives support", ""),
        "payment": Fact(payment, "text", "payment amount and frequency (an assumption)", ""),
        "price_scenario": Fact(price_label, "text", "price scenario used", ""),
        "duration_months": Fact(s["duration_months"], "months", "how long support is paid", ""),
        "payments": Fact(int(result["payments"]), "payments", "number of payments in the period", ""),
        "new_recipient_households": Fact(_num(result["new_recipient_households"]), "households", "ADDITIONAL households reached", ""),
        "new_recipient_people": Fact(_num(result["new_recipient_people"]), "people", "people living in the additional households", ""),
        "poor_recipient_households": Fact(_num(result["poor_households"]), "households",
                                          "recipient households below the poverty line in the 2023/24 survey (observed, not predicted)", ""),
        "extra_monthly_rwf": Fact(_num(col["extra"]), "rwf_per_household_per_month", "average extra cost from the price change", ""),
        "support_monthly_rwf": Fact(_num(col["support"]), "rwf_per_household_per_month", "average support received per month", ""),
        "not_offset_monthly_rwf": Fact(_num(col["not_offset"]), "rwf_per_household_per_month",
                                       "average extra cost not covered by support (group average)", ""),
        "direct_transfers_rwf": Fact(_num(result["direct_transfers"]), "rwf_total", "transfer cost over the whole period, excluding delivery", ""),
        "delivery_costs_rwf": Fact(_num(result["delivery_costs"]), "rwf_total", "delivery costs over the period (0 if not specified)", ""),
        "total_cost_rwf": Fact(_num(result["total_cost"]), "rwf_total", "total cost including delivery costs", ""),
        "example_per_household_rwf": Fact(_num(result["amount_per_payment"]) * int(result["payments"]), "rwf_total",
                                          "EXAMPLE: total one recipient household receives over the period (from the result)", ""),
    }
    if existing:
        f["existing_recipient_households"] = Fact(_num(result["recipient_households"]), "households",
                                                  "EXISTING NSDS households receiving more (not new recipients)", "")
    return _with_display(f, lang)


def _display(fact: Fact, lang: str) -> str:
    v, u = fact.value, fact.unit
    if u == "text":
        return lg.fmt_month(v, lang) if re.fullmatch(r"\d{4}-\d{2}", str(v)) else str(v)
    if u.startswith("rwf"):
        return lg.fmt_rwf(v, lang)
    if u in ("percent_price_increase", "percent_change"):
        return lg.fmt_percent(v)
    if u == "months":
        return translate("units.months", lang, n=v)
    if u == "payments":
        return f"{int(v)}"
    return lg.fmt_count(v)


def _with_display(facts: dict[str, Fact], lang: str) -> dict[str, Fact]:
    return {k: Fact(f.value, f.unit, f.meaning, _display(f, lang)) for k, f in facts.items()}


def build_facts(kind: str, result: dict, meta: dict, lang: str, price_label: str = "") -> dict[str, Fact]:
    if kind == "price":
        facts = price_facts(result, meta, lang)
    elif kind == "compare":
        facts = compare_facts(result, meta, lang, price_label)
    else:
        raise ValueError(kind)
    allowed = PRICE_FACTS if kind == "price" else COMPARE_FACTS
    assert set(facts) <= set(allowed), set(facts) - set(allowed)
    return facts


def limitation_ids(kind: str, result: dict) -> tuple[str, ...]:
    if kind == "price":
        return PRICE_LIMITATIONS
    ids = [i for i in COMPARE_LIMITATIONS if i != "national_rule"]
    if result.get("scope") == "national_rule" and result.get("geo") != lg.ALL:
        ids.append("national_rule")
    if result["support"]["action"] != "cash":
        ids.remove("not_eligibility")
    return tuple(ids)


# ---------------------------------------------------------------------------
# Deterministic explanation (always shown; the fallback)
# ---------------------------------------------------------------------------
def deterministic_sections(kind: str, result: dict, facts: dict[str, Fact], lang: str) -> dict[str, str]:
    d = {k: f.display for k, f in facts.items()}
    if kind == "price":
        mode = result["spec"]["mode"]
        out = {"tested": translate(f"explain.price.tested_{mode}", lang, **d),
               "meaning": translate("explain.price.meaning", lang, **d),
               "example": translate(f"explain.price.example_{mode}", lang, **d),
               "limitation": translate("explain.limit.not_forecast", lang)}
        return out
    existing = "existing_recipient_households" in facts
    limit = "national_rule" if "national_rule" in limitation_ids(kind, result) else "no_poverty_change"
    return {"tested": translate("explain.support.tested", lang, **d),
            "meaning": translate("explain.support.meaning_existing" if existing else "explain.support.meaning_new", lang, **d),
            "example": translate("explain.support.example", lang, **d),
            "support": translate("explain.support.changes", lang, **d),
            "limitation": translate(f"explain.limit.{limit}", lang)}


# ---------------------------------------------------------------------------
# Outbound payload, prompt and response schema
# ---------------------------------------------------------------------------
def build_payload(kind: str, result: dict, facts: dict[str, Fact], fingerprint: str, lang: str) -> dict:
    """The only data sent to the AI provider: allowlisted aggregate facts, limitation texts, no records or raw data."""
    payload = {
        "scenario_id": fingerprint,
        "kind": kind,
        "language": lang,
        "facts": {k: {"meaning": f.meaning, "unit": f.unit, "display": f.display} for k, f in facts.items()},
        "limitations": {i: translate(f"explain.limit.{i}", lang) for i in limitation_ids(kind, result)},
        "support_section_required": kind == "compare",
        "word_target": "100-150 words in English; Kinyarwanda may be somewhat longer",
    }
    assert set(payload) == PAYLOAD_KEYS
    if len(json.dumps(payload, ensure_ascii=False)) > MAX_PAYLOAD_CHARS:
        raise ValueError("payload too large")
    return payload


LANGUAGE_NAMES = {"en": "English", "rw": "Kinyarwanda"}

SYSTEM_INSTRUCTION = """You write short, plain explanations of results that Baho Neza has ALREADY calculated, for
non-technical Rwandan policymakers. You are not a calculator, adviser or chatbot.

Rules:
- Write in {language}. Simple words, short sentences. About 100-150 words in total (Kinyarwanda may be longer).
- Never write a digit or a number. Every number must be a placeholder [[fact_key]] using only keys in "facts".
  Do not calculate, round, compare numerically or invent any number. Do not invent facts.
- Explain THESE results only: the scenario in "facts" and its numbers. Do not explain other scenarios, general
  economics or examples that are not in "facts".
- Sections: "tested" (what was tested), "meaning" (what the results mean), "example" (one concrete example for an
  average household in this place, built only from the example_* facts, which come from this result), "support"
  (what the support changes; only if support_section_required is true, otherwise null), "limitation" (one important
  limitation, chosen from "limitations"; set limitation_id to its key).
- Keep these distinctions: a price increase over the period is NOT a change in the inflation rate; percent is not
  percentage points; people are not households; monthly, quarterly and annual amounts differ; additional recipients
  are not existing recipients; transfer cost excludes delivery costs, the total includes them; a scenario is not a
  forecast; estimated poverty likelihood (a model estimate) is not observed poverty.
- Do not claim poverty reduction, causal effects, guarantees or eligibility. No recommendations or advice.
- Plain text only: no HTML, links, code, tables, headings or lists."""


def system_instruction(lang: str) -> str:
    return SYSTEM_INSTRUCTION.format(language=LANGUAGE_NAMES[lang])


def response_schema(limitations: tuple[str, ...]) -> dict:
    text = {"type": "string"}
    return {"type": "object",
            "properties": {"tested": text, "meaning": text, "example": text,
                           "support": {"type": ["string", "null"]},
                           "limitation_id": {"type": "string", "enum": list(limitations)},
                           "limitation": text},
            "required": ["tested", "meaning", "example", "support", "limitation_id", "limitation"]}


# ---------------------------------------------------------------------------
# Validation and rendering of AI output (untrusted)
# ---------------------------------------------------------------------------
def _words(text: str) -> int:
    return len(text.split())


def validate_response(raw: str, kind: str, facts: dict[str, Fact], limitations: tuple[str, ...], lang: str) -> dict[str, str]:
    """Parse, check and render an AI response. Returns {section: text, "limitation_id": id} or raises InvalidExplanation."""
    if not isinstance(raw, str) or not raw.strip() or len(raw) > MAX_RESPONSE_CHARS:
        raise InvalidExplanation("empty or too long")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise InvalidExplanation("not JSON") from e
    expected = {"tested", "meaning", "example", "support", "limitation_id", "limitation"}
    if not isinstance(data, dict) or set(data) != expected:
        raise InvalidExplanation("unexpected structure")
    if data["limitation_id"] not in limitations:
        raise InvalidExplanation("unknown limitation")
    needs_support = kind == "compare"
    sections = [s for s in SECTIONS if s != "support" or needs_support]
    if not needs_support and data["support"] not in (None, ""):
        raise InvalidExplanation("support section not allowed")
    out: dict[str, str] = {}
    total = 0
    for s in sections:
        text = data[s]
        if not isinstance(text, str) or not text.strip():
            raise InvalidExplanation(f"missing section {s}")
        refs = PLACEHOLDER.findall(text)
        if set(refs) - set(facts):
            raise InvalidExplanation("unknown fact reference")
        bare = PLACEHOLDER.sub(" ", text)
        if re.search(r"\d", bare):
            raise InvalidExplanation("number not taken from verified facts")
        if FORBIDDEN_MARKUP.search(bare):
            raise InvalidExplanation("markup or link")
        if lang == "en" and any(c in bare.lower() for c in FORBIDDEN_CLAIMS):
            raise InvalidExplanation("unsupported claim")
        rendered = PLACEHOLDER.sub(lambda m: facts[m.group(1)].display, text.strip())
        if _words(rendered) > SECTION_WORD_LIMIT[lang]:
            raise InvalidExplanation("section too long")
        total += _words(rendered)
        out[s] = rendered
    if not PLACEHOLDER.search(data["meaning"]):
        raise InvalidExplanation("meaning not grounded in facts")
    if not any(r.startswith("example_") for r in PLACEHOLDER.findall(data["example"])):
        raise InvalidExplanation("example not based on the computed example")
    lo, hi = WORD_LIMITS[lang]
    if not lo <= total <= hi:
        raise InvalidExplanation("length outside limits")
    out["limitation_id"] = data["limitation_id"]
    return out
