"""Tests for the optional AI explanation layer. Mocked provider only: no network, no real keys."""
from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from src.dashboard import ai_service as ai
from src.dashboard import data as dd
from src.dashboard import explain as ex
from src.dashboard import scenario as sc
from src.dashboard.i18n import translate

ROOT = Path(dd.PROJECT_ROOT)
needs_tables = pytest.mark.skipif(not all(p.exists() for p in dd.PUBLIC_FILES.values()) or not dd.META_PATH.exists(),
                                  reason="planning tables not built")
READY = {"enabled": True, "provider": "gemini", "api_key": "test-key-not-real", "model": "gemini-test-model",
         "external_data_approved": True}


# ---------------------------------------------------------------------------
# Fixtures: real aggregate results (valid, published cells only)
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def tabs():
    return dd.load_public_tables()


@pytest.fixture(scope="module")
def price_simple(tabs):
    return sc.price_result(tabs["groups"], "Rutsiro", "all", sc.price_spec("simple", 6, 12))


@pytest.fixture(scope="module")
def price_detailed(tabs):
    return sc.price_result(tabs["groups"], "Rwanda", "rural", sc.price_spec("detailed", 12, detailed={"food": 20, "energy": 5}))


@pytest.fixture(scope="module")
def cash(tabs):
    price = sc.price_spec("simple", 12, 10)
    return sc.compare(tabs["planning"], "Rutsiro", "all", price,
                      sc.support_spec("cash", amount_rwf=9_000, frequency="quarterly", duration_months=12, delivery_pct=5))


@pytest.fixture(scope="module")
def nsds(tabs):
    return sc.compare(tabs["planning"], "Rwanda", "all", sc.price_spec("simple", 12, 10), sc.support_spec("nsds_increase", nsds_increase_pct=10))


def _facts(kind, result, tabs, lang="en"):
    return ex.build_facts(kind, result, tabs["meta"], lang, "price label")


PRICE_OK = {
    "tested": "You tested all prices going up by [[increase_all_pct]] over the next [[horizon_months]] in [[place]], on top of "
              "[[baseline_month]] prices. This is a rise in prices, not a new inflation rate.",
    "meaning": "The same basket would cost [[basket_change_pct]] more, about [[extra_monthly_rwf]] more for each household "
               "every month on average. If incomes stay the same, money buys about [[purchasing_power_loss_pct]] less.",
    "example": "As an illustration only, a household spending [[example_budget_rwf]] a month on these goods would need about "
               "[[example_extra_rwf]] more each month.",
    "support": None,
    "limitation_id": "not_forecast",
    "limitation": "This is a scenario and not a forecast of what prices will do.",
}
COMPARE_OK = {
    "tested": "You tested [[programme]] in [[place]] for [[recipient_group]], paid as [[payment]] for [[duration_months]].",
    "meaning": "About [[new_recipient_households]] additional households, home to [[new_recipient_people]] people, would be "
               "reached. Transfers cost [[direct_transfers_rwf]], and [[total_cost_rwf]] with delivery costs.",
    "example": "As an illustration, one household receiving support would get [[example_per_household_rwf]] over the whole period.",
    "support": "On average the support of [[support_monthly_rwf]] a month covers part of the extra cost of [[extra_monthly_rwf]], "
               "leaving [[not_offset_monthly_rwf]] each month.",
    "limitation_id": "no_poverty_change",
    "limitation": "It does not show how many people would leave poverty.",
}


class FakeModels:
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.calls = []

    def generate_content(self, *, model, contents, config):
        self.calls.append({"model": model, "contents": contents, "config": config})
        out = self.outcomes.pop(0)
        if isinstance(out, Exception):
            raise out
        return SimpleNamespace(text=out)


def fake_client(*outcomes):
    return SimpleNamespace(models=FakeModels(outcomes))


def api_error(code: int):
    from google.genai import errors
    cls = errors.ClientError if code < 500 else errors.ServerError
    return cls(code, {"error": {"code": code, "message": "mock", "status": "MOCK"}})


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("raw,status", [
    (None, "not_configured"),
    ({}, "disabled"),
    ({**READY, "enabled": False}, "disabled"),
    ({**READY, "enabled": "true"}, "disabled"),                       # strings are not booleans
    ({**READY, "api_key": "REPLACE_WITH_YOUR_GEMINI_API_KEY"}, "not_configured"),
    ({**READY, "model": "REPLACE_WITH_VERIFIED_FREE_TIER_MODEL_ID"}, "ready"),       # falls back to DEFAULT_MODEL
    ({k: v for k, v in READY.items() if k != "model"}, "ready"),
    ({**READY, "api_key": " "}, "not_configured"),
    ({**READY, "provider": "openai"}, "not_configured"),
    ({**READY, "model": "gemini model; rm -rf"}, "not_configured"),
    ({**READY, "external_data_approved": False}, "not_approved"),
    ({k: v for k, v in READY.items() if k != "external_data_approved"}, "not_approved"),
    (READY, "ready"),
])
def test_config_status(raw, status):
    got, cfg = ai.config_status(raw)
    assert got == status and (cfg is not None) == (status == "ready")


def test_missing_model_uses_the_verified_default():
    _, cfg = ai.config_status({**READY, "model": "REPLACE_WITH_VERIFIED_FREE_TIER_MODEL_ID"})
    assert cfg.model == ai.DEFAULT_MODEL == "gemini-3.8-flash"
    assert ai.config_status(READY)[1].model == "gemini-test-model"


def test_config_never_exposes_the_key():
    _, cfg = ai.config_status(READY)
    assert "test-key-not-real" not in repr(cfg)


def test_missing_or_broken_secrets_never_raise(monkeypatch):
    import streamlit as st

    class Broken:
        def get(self, *_):
            raise FileNotFoundError("no secrets")

    monkeypatch.setattr(st, "secrets", Broken())
    assert ai.load_config() == ("not_configured", None)


def test_placeholder_secrets_files():
    assert ".streamlit/secrets.toml" in (ROOT / ".gitignore").read_text()
    example = tomllib.loads((ROOT / ".streamlit" / "secrets.example.toml").read_text())["ai"]
    assert example["enabled"] is False and example["external_data_approved"] is False
    assert example["api_key"].startswith("REPLACE_WITH") and example["model"].startswith("REPLACE_WITH")
    assert ai.config_status(example)[0] == "disabled"


def test_no_api_key_like_strings_in_tracked_text():
    files = [*(ROOT / "src").rglob("*.py"), *(ROOT / "tests").rglob("*.py"), *(ROOT / "docs").rglob("*.md"), ROOT / "README.md",
             ROOT / ".streamlit" / "secrets.example.toml"]
    for f in files:
        assert not re.search(r"AIza[0-9A-Za-z_\-]{30,}", f.read_text(encoding="utf-8", errors="ignore")), f


# ---------------------------------------------------------------------------
# Facts, examples and deterministic text
# ---------------------------------------------------------------------------
@needs_tables
def test_price_example_arithmetic_is_python_computed(tabs, price_simple, price_detailed):
    f = _facts("price", price_simple, tabs)
    # The example is the result itself, for the average household in this place (not a made-up budget)
    assert f["example_budget_rwf"].value == pytest.approx(price_simple["reference_monthly"])
    assert f["example_new_rwf"].value == pytest.approx(price_simple["scenario_monthly"])
    assert f["example_extra_rwf"].value == pytest.approx(price_simple["extra_monthly"])
    assert f["example_new_rwf"].value - f["example_budget_rwf"].value == pytest.approx(f["example_extra_rwf"].value)
    assert f["increase_all_pct"].display == "12.0%" and f["horizon_months"].display == "6 months"
    assert f["baseline_month"].display == "September 2026" and f["place"].display == "Rutsiro · All areas"
    assert f["purchasing_power_loss_pct"].value == pytest.approx(-price_simple["purchasing_power_change_pct"])
    d = _facts("price", price_detailed, tabs)
    assert "increase_all_pct" not in d and d["increase_food_pct"].value == 20 and d["increase_transport_pct"].value == 0
    assert d["example_extra_rwf"].value == pytest.approx(price_detailed["extra_monthly"])


@needs_tables
def test_compare_facts_units_and_recipients(tabs, cash, nsds):
    f = _facts("compare", cash, tabs)
    assert f["payments"].value == 4 and f["duration_months"].display == "12 months"
    assert f["example_per_household_rwf"].value == 9_000 * 4                 # quarterly: 4 payments in 12 months
    assert f["new_recipient_households"].unit == "households" and f["new_recipient_people"].unit == "people"
    assert f["direct_transfers_rwf"].value == pytest.approx(cash["direct_transfers"])
    assert f["total_cost_rwf"].value == pytest.approx(cash["direct_transfers"] * 1.05)    # delivery-inclusive
    assert "existing_recipient_households" not in f
    n = _facts("compare", nsds, tabs)
    assert n["new_recipient_households"].value == 0 and n["existing_recipient_households"].value > 0
    assert "observed" in n["poor_recipient_households"].meaning


@needs_tables
@pytest.mark.parametrize("lang", ["en", "rw"])
def test_deterministic_explanations_in_both_languages(tabs, price_detailed, cash, nsds, lang):
    for kind, result in [("price", price_detailed), ("compare", cash), ("compare", nsds)]:
        facts = _facts(kind, result, tabs, lang)
        sec = ex.deterministic_sections(kind, result, facts, lang)
        assert set(sec) == ({"tested", "meaning", "example", "limitation"} | ({"support"} if kind == "compare" else set()))
        text = " ".join(sec.values())
        assert "{" not in text and "[[" not in text
        assert facts["place"].display in text
    en = ex.deterministic_sections("price", price_detailed, _facts("price", price_detailed, tabs), "en")
    assert "not changes in the yearly inflation rate" in en["tested"] and "the average household in" in en["example"]
    nsds_en = ex.deterministic_sections("compare", nsds, _facts("compare", nsds, tabs), "en")
    assert "No additional households" in nsds_en["meaning"]


def test_hidden_values_cannot_enter_facts():
    with pytest.raises(ValueError):
        ex._num(float("nan"))


# ---------------------------------------------------------------------------
# Outbound payload
# ---------------------------------------------------------------------------
@needs_tables
def test_payload_is_allowlisted_and_aggregate_only(tabs, price_simple, cash):
    for kind, result, allowed in [("price", price_simple, ex.PRICE_FACTS), ("compare", cash, ex.COMPARE_FACTS)]:
        facts = _facts(kind, result, tabs)
        p = ex.build_payload(kind, result, facts, "abc123", "en")
        assert set(p) == ex.PAYLOAD_KEYS and set(p["facts"]) <= set(allowed)
        assert all(set(v) == {"meaning", "unit", "display"} for v in p["facts"].values())
        blob = json.dumps(p)
        assert p["scenario_id"] == "abc123" and len(blob) <= ex.MAX_PAYLOAD_CHARS
        for forbidden in ("hhid", "clust", "strata", "weight", "poverty_score", "exposed", '"spec"', "api_key", "test-key"):
            assert forbidden not in blob, forbidden
        assert set(p["limitations"]) == set(ex.limitation_ids(kind, result))


@needs_tables
def test_district_share_of_national_rule_is_flagged(tabs):
    r = sc.compare(tabs["planning"], "Rutsiro", "all", sc.price_spec("simple", 12, 0), sc.support_spec("ds_expansion", ds_level=5))
    assert "national_rule" in ex.limitation_ids("compare", r)
    sec = ex.deterministic_sections("compare", r, _facts("compare", r, tabs), "en")
    assert "national expansion" in sec["limitation"]


# ---------------------------------------------------------------------------
# Validation of AI output
# ---------------------------------------------------------------------------
@needs_tables
def test_valid_response_is_rendered_with_verified_numbers(tabs, price_simple):
    facts = _facts("price", price_simple, tabs)
    out = ex.validate_response(json.dumps(PRICE_OK), "price", facts, ex.PRICE_LIMITATIONS, "en")
    assert out["limitation_id"] == "not_forecast" and "support" not in out
    assert facts["extra_monthly_rwf"].display in out["meaning"] and "[[" not in out["meaning"]
    assert facts["example_extra_rwf"].display in out["example"]


def _bad(base, **change):
    return json.dumps({**base, **change})


@needs_tables
@pytest.mark.parametrize("raw", [
    "not json",
    "",
    json.dumps({"tested": "x"}),
    _bad(PRICE_OK, extra="field"),
    _bad(PRICE_OK, meaning="Prices would rise by 12% so each household pays 4,000 RWF more."),       # invented numbers
    _bad(PRICE_OK, meaning="It costs [[made_up_fact]] more for every household in this place."),      # unknown reference
    _bad(PRICE_OK, limitation_id="anything"),
    _bad(PRICE_OK, support="Support would help."),                                                     # no support for prices
    _bad(PRICE_OK, example="A household would pay a little more each month, as an illustration only."),  # no example fact
    _bad(PRICE_OK, tested="<script>alert('x')</script> [[place]]"),
    _bad(PRICE_OK, tested="See https://example.org for [[place]]"),
    _bad(PRICE_OK, meaning="This will reduce poverty: [[extra_monthly_rwf]] more a month."),
    _bad(PRICE_OK, tested="Short.", meaning="[[basket_change_pct]].", example="[[example_extra_rwf]].", limitation="Short."),
    _bad(PRICE_OK, meaning="[[basket_change_pct]] " + "word " * 120),
    "x" * (ex.MAX_RESPONSE_CHARS + 1),
])
def test_invalid_responses_are_rejected(tabs, price_simple, raw):
    with pytest.raises(ex.InvalidExplanation):
        ex.validate_response(raw, "price", _facts("price", price_simple, tabs), ex.PRICE_LIMITATIONS, "en")


@needs_tables
def test_compare_requires_the_support_section(tabs, cash):
    facts = _facts("compare", cash, tabs)
    lim = ex.limitation_ids("compare", cash)
    assert ex.validate_response(json.dumps(COMPARE_OK), "compare", facts, lim, "en")["support"]
    with pytest.raises(ex.InvalidExplanation):
        ex.validate_response(_bad(COMPARE_OK, support=None), "compare", facts, lim, "en")


# ---------------------------------------------------------------------------
# Provider calls (mocked): timeout, retries, quota, errors
# ---------------------------------------------------------------------------
_, CFG = ai.config_status(READY)
NO_SLEEP = lambda s: None  # noqa: E731


@needs_tables
def test_request_config_is_bounded_and_structured(tabs, price_simple):
    facts = _facts("price", price_simple, tabs)
    client = fake_client(json.dumps(PRICE_OK))
    ai.generate(ex.build_payload("price", price_simple, facts, "fp", "en"), CFG, ex.PRICE_LIMITATIONS, client=client)
    call = client.models.calls[0]
    cfg = call["config"]
    assert call["model"] == "gemini-test-model"
    assert cfg.response_mime_type == "application/json" and cfg.response_json_schema["required"]
    assert cfg.max_output_tokens == ai.MAX_OUTPUT_TOKENS and cfg.automatic_continuation is False
    assert not cfg.tools and "Never write a digit" in cfg.system_instruction
    assert json.loads(call["contents"])["scenario_id"] == "fp"


def test_http_client_has_timeout_and_no_sdk_retries():
    client = ai.make_client(CFG)               # constructing a client makes no request
    opts = client._api_client._http_options
    assert opts.timeout == ai.TIMEOUT_MS and opts.retry_options.attempts == 1


@pytest.mark.parametrize("outcomes,code,calls", [
    ([api_error(429)], "quota", 1),                                          # quota: never retried
    ([api_error(400)], "provider", 1),
    ([api_error(403)], "provider", 1),
    ([api_error(503), api_error(503)], "provider", 2),                       # one retry only
    ([httpx.ReadTimeout("t"), httpx.ReadTimeout("t")], "timeout", 2),
    ([RuntimeError("boom")], "provider", 1),
    (["   "], "invalid", 1),
    (["x" * (ex.MAX_RESPONSE_CHARS + 1)], "invalid", 1),
])
def test_provider_failures_map_to_short_codes(outcomes, code, calls):
    client = fake_client(*outcomes)
    with pytest.raises(ai.ProviderError) as e:
        ai.generate({"language": "en", "x": 1}, CFG, ex.PRICE_LIMITATIONS, client=client, sleep=NO_SLEEP)
    assert e.value.code == code and len(client.models.calls) == calls


def test_one_transient_failure_is_retried_once():
    client = fake_client(api_error(503), json.dumps(PRICE_OK))
    assert ai.generate({"language": "en"}, CFG, ex.PRICE_LIMITATIONS, client=client, sleep=NO_SLEEP)
    assert len(client.models.calls) == 2


# ---------------------------------------------------------------------------
# Session guard and the end-to-end service (mocked)
# ---------------------------------------------------------------------------
@needs_tables
def test_request_explanation_stores_by_fingerprint_and_language(tabs, price_simple):
    facts = _facts("price", price_simple, tabs)
    state, client = {}, fake_client(json.dumps(PRICE_OK))
    sections, err = ai.request_explanation("price", price_simple, facts, "fp1", "en", CFG, state, 1000.0, client=client)
    assert err is None and sections["limitation_id"] == "not_forecast"
    again, err = ai.request_explanation("price", price_simple, facts, "fp1", "en", CFG, state, 1001.0, client=client)
    assert again == sections and len(client.models.calls) == 1           # duplicate request: no second call
    _, err = ai.request_explanation("price", price_simple, facts, "fp1", "rw", CFG, state, 1002.0, client=client)
    assert err == "cooldown"                                              # a new language is a new explanation key
    _, err = ai.request_explanation("price", price_simple, facts, "fp2", "en", CFG, state, 1001.0 + ai.COOLDOWN_S,
                                    client=fake_client("not json"))
    assert err == "invalid" and ("price", "fp2", "en") not in state["done"]


def test_guard_inflight_limit_and_expiry():
    key = ("price", "fp", "en")
    assert ai.guard_check({"inflight": (key, 100.0)}, key, 101.0) == "inflight"
    assert ai.guard_check({"inflight": (key, 100.0)}, key, 100.0 + ai.INFLIGHT_EXPIRY_S + 1) is None
    assert ai.guard_check({"count": ai.MAX_REQUESTS_PER_SESSION}, key, 1e6) == "limit"
    assert ai.guard_check({"last": 100.0}, key, 100.0 + ai.COOLDOWN_S - 1) == "cooldown"


@needs_tables
def test_provider_error_falls_back_without_storing(tabs, cash):
    facts = _facts("compare", cash, tabs)
    state = {}
    out, err = ai.request_explanation("compare", cash, facts, "fp", "en", CFG, state, 0.0, client=fake_client(api_error(429)))
    assert out is None and err == "quota" and not state.get("done") and state["inflight"] is None


# ---------------------------------------------------------------------------
# The running app (AppTest, mocked provider)
# ---------------------------------------------------------------------------
def _app(page: str, ai_secrets: dict | None, lang: str = "en"):
    from streamlit.testing.v1 import AppTest
    at = AppTest.from_file(str(ROOT / "src" / "dashboard" / "app.py"), default_timeout=90)
    at.query_params["lang"] = lang
    if ai_secrets is not None:
        at.secrets["ai"] = ai_secrets
    at.switch_page(page)
    return at.run()


def _texts(at) -> str:
    return "\n".join([m.value for m in at.markdown] + [c.value for c in at.caption])


@pytest.fixture
def mock_provider(monkeypatch):
    client = fake_client(*[json.dumps(PRICE_OK)] * 5)
    monkeypatch.setattr(ai, "make_client", lambda cfg: client)
    return client


@needs_tables
@pytest.mark.parametrize("secrets", [
    {"enabled": False, "provider": "gemini", "api_key": "REPLACE_WITH_YOUR_GEMINI_API_KEY",
     "model": "REPLACE_WITH_VERIFIED_FREE_TIER_MODEL_ID", "external_data_approved": False},
    {**READY, "external_data_approved": False},
    {**READY, "api_key": "REPLACE_WITH_YOUR_GEMINI_API_KEY"},
])
def test_button_disabled_and_generic_message_when_not_ready(secrets, mock_provider):
    at = _app("views/prices.py", secrets)
    assert at.button(key="cta_explain_price_off").disabled                 # no valid result yet
    at.button(key="cta_price_calc").click().run()
    assert not at.exception
    assert at.button(key="cta_explain_price").disabled
    assert translate("explain.not_configured", "en") in _texts(at)
    assert translate("explain.title", "en") in [e.label for e in at.expander]       # collapsed, still available
    assert translate("explain.section.meaning", "en") in _texts(at)        # deterministic explanation still rendered
    assert translate("ux.prices.sentence", "en", change="+0.0%", extra="x").split(":")[0][:20] in _texts(at)
    assert not mock_provider.models.calls
    assert "gemini-test-model" not in _texts(at) and "test-key" not in _texts(at)


@needs_tables
def test_ai_explanation_is_bound_to_the_valid_result(mock_provider):
    at = _app("views/prices.py", READY)
    at.slider(key="price_all").set_value(12.0).run()
    at.run()                                                              # page load, slider and reruns: no calls
    assert not mock_provider.models.calls
    assert not at.button(key="cta_explain_price_off").disabled is False   # no result yet: button shown, disabled
    at.button(key="cta_price_calc").click().run()                         # results requested: AI explains them once
    assert len(mock_provider.models.calls) == 1
    label = translate("explain.ai_label", "en")
    assert label in _texts(at) and at.button(key="cta_explain_price").disabled      # no duplicate request
    sent = json.loads(mock_provider.models.calls[0]["contents"])
    assert sent["facts"]["increase_all_pct"]["display"] == "12.0%"        # it explains THESE results
    cards_before = [m.value for m in at.markdown if m.value.startswith('<div class="bn-card">')]
    at.run()
    assert label in _texts(at) and len(mock_provider.models.calls) == 1
    at.slider(key="price_all").set_value(20.0).run()                      # inputs changed: result and explanation stale
    assert label not in _texts(at) and translate("state.stale_price", "en") in _texts(at)
    at.button(key="cta_price_calc").click().run()                         # new result: old AI text never reappears
    assert label not in _texts(at) and len(mock_provider.models.calls) == 1          # cooldown blocks a burst
    at.slider(key="price_all").set_value(12.0)
    at.button(key="cta_price_calc").click().run()                         # back to the explained settings
    assert label in _texts(at) and len(mock_provider.models.calls) == 1   # stored explanation reused, no new call
    assert [m.value for m in at.markdown if m.value.startswith('<div class="bn-card">')] == cards_before
    at.selectbox(key="lang").set_value("rw").run()                        # language: new explanation key, same numbers
    assert translate("explain.ai_label", "rw") not in _texts(at)
    assert not at.button(key="cta_explain_price").disabled
    assert translate("prices.result.basket_change", "rw") in _texts(at) and "+12.0%" in _texts(at)


@needs_tables
def test_provider_failure_shows_fallback_in_app(monkeypatch):
    monkeypatch.setattr(ai, "make_client", lambda cfg: fake_client(api_error(429)))
    at = _app("views/compare.py", READY)
    at.button(key="cta_compare").click().run()                           # the results click triggers the request
    assert not at.exception
    text = _texts(at)
    assert translate("explain.error.quota", "en") in text and translate("explain.fallback", "en") in text
    assert translate("explain.ai_label", "en") not in text
    assert translate("explain.section.support", "en") in text            # deterministic explanation remains


@needs_tables
def test_kinyarwanda_request_and_rendering(tabs, cash):
    facts = _facts("compare", cash, tabs, "rw")
    p = ex.build_payload("compare", cash, facts, "fp", "rw")
    assert p["language"] == "rw" and "Kinyarwanda" in ex.system_instruction("rw")
    assert facts["direct_transfers_rwf"].display.endswith("Frw") and facts["duration_months"].display == "Amezi 12"
    rw_ok = {**COMPARE_OK, "tested": "Wagerageje [[programme]] muri [[place]] ku [[recipient_group]], bahabwa [[payment]] mu gihe cya [[duration_months]]."}
    out = ex.validate_response(json.dumps(rw_ok), "compare", facts, ex.limitation_ids("compare", cash), "rw")
    assert facts["place"].display in out["tested"]
