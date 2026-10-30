"""Optional Gemini service for Baho Neza's "Explain simply" button (docs/ai_explanation.md).

Off unless .streamlit/secrets.toml (or Streamlit Community Cloud's Secrets settings) has, under [ai]:
enabled = true, provider = "gemini", a real api_key (no "REPLACE_WITH" placeholder) and external_data_approved = true.
`model` is optional: missing or placeholder values use DEFAULT_MODEL (verified free-tier model, docs/ai_explanation.md).
Otherwise the app shows its deterministic explanation only. When ready, an explanation is generated once when the user
asks for results (Show results / Compare) or clicks "Explain simply"; never on page load, slider changes or reruns.

The key is read server-side through st.secrets and never displayed, logged or sent anywhere except to the provider.
Prompts and responses are never logged; only short error codes are. Requests are bounded (timeout, one retry for
transient errors only, payload and response size) and limited per session (cooldown, cap, duplicate protection).
Session limits are not a global spending or quota cap: Google applies quotas per project.
"""
from __future__ import annotations

import json
import logging
import re
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field

from src.dashboard import explain as ex

log = logging.getLogger(__name__)
if not log.handlers:                 # make sanitised diagnostics visible in Streamlit Community Cloud's log (stderr)
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    log.addHandler(_handler)

PLACEHOLDER_PREFIX = "REPLACE_WITH"
DEFAULT_MODEL = "gemini-3.8-flash"     # stable, free tier, structured output (verified 2026-10-30)
MODEL_ID = re.compile(r"^[a-z0-9][a-z0-9.\-]{2,63}$")
TIMEOUT_MS = 25_000
MAX_ATTEMPTS = 2                    # the original request plus at most one retry, for transient errors only
RETRY_DELAY_S = 1.5
TRANSIENT_STATUS = {500, 502, 503, 504}
MAX_OUTPUT_TOKENS = 2_048           # includes the model's internal "thinking" tokens
COOLDOWN_S = 10.0
MAX_REQUESTS_PER_SESSION = 8
INFLIGHT_EXPIRY_S = TIMEOUT_MS / 1000 * MAX_ATTEMPTS + 10


@dataclass(frozen=True)
class AIConfig:
    provider: str
    model: str
    api_key: str = field(repr=False)
    thinking_level: str = "low"


class ProviderError(Exception):
    """Provider failure, mapped to a short code: timeout, quota, provider."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


# ---------------------------------------------------------------------------
# Configuration (never echoes values)
# ---------------------------------------------------------------------------
def _real(value) -> bool:
    return isinstance(value, str) and value.strip() != "" and not value.strip().upper().startswith(PLACEHOLDER_PREFIX)


def config_status(raw: Mapping | None) -> tuple[str, AIConfig | None]:
    """('ready', config) only when every condition holds; otherwise (reason, None).

    Reasons: not_configured (missing, placeholder or invalid values), disabled, not_approved.
    The app shows one generic message for every reason, so configuration details are never exposed.
    """
    if not isinstance(raw, Mapping):
        return "not_configured", None
    if raw.get("enabled") is not True:
        return "disabled", None
    if raw.get("provider", "gemini") != "gemini" or not _real(raw.get("api_key")):
        return "not_configured", None
    model = raw["model"].strip() if _real(raw.get("model")) else DEFAULT_MODEL
    if not MODEL_ID.match(model):
        return "not_configured", None
    if raw.get("external_data_approved") is not True:
        return "not_approved", None
    level = raw.get("thinking_level", "low")
    return "ready", AIConfig("gemini", model, raw["api_key"].strip(), level if isinstance(level, str) else "low")


def load_config() -> tuple[str, AIConfig | None]:
    """Read [ai] from st.secrets. A missing file, section or key never raises."""
    try:
        import streamlit as st
        raw = st.secrets.get("ai")
        raw = dict(raw) if raw is not None else None
    except Exception:            # no secrets file, malformed TOML, or not running in Streamlit
        raw = None
    return config_status(raw)


# ---------------------------------------------------------------------------
# Provider call
# ---------------------------------------------------------------------------
def make_client(cfg: AIConfig):
    from google import genai
    from google.genai import types
    return genai.Client(api_key=cfg.api_key, http_options=types.HttpOptions(
        timeout=TIMEOUT_MS, retry_options=types.HttpRetryOptions(attempts=1)))


def _request_config(cfg: AIConfig, lang: str, limitations: tuple[str, ...]):
    from google.genai import types
    kwargs = dict(system_instruction=ex.system_instruction(lang), temperature=0.2, max_output_tokens=MAX_OUTPUT_TOKENS,
                  response_mime_type="application/json", response_json_schema=ex.response_schema(limitations),
                  automatic_continuation=False)
    if cfg.thinking_level:
        kwargs["thinking_config"] = types.ThinkingConfig(thinking_level=cfg.thinking_level.upper())
    return types.GenerateContentConfig(**kwargs)


# Error categories shown to users (explain.error.<code>) and written to the diagnostic log
ACCESS_REASONS = {"API_KEY_INVALID", "API_KEY_SERVICE_BLOCKED", "API_KEY_HTTP_REFERRER_BLOCKED", "API_KEY_IP_ADDRESS_BLOCKED",
                  "SERVICE_DISABLED", "CONSUMER_INVALID", "ACCESS_TOKEN_SCOPE_INSUFFICIENT", "USER_PROJECT_DENIED"}
ACCESS_STATUS = {"PERMISSION_DENIED", "UNAUTHENTICATED", "FAILED_PRECONDITION"}   # FAILED_PRECONDITION: e.g. location


def sdk_version() -> str:
    try:
        from importlib.metadata import version
        return version("google-genai")
    except Exception:            # noqa: BLE001
        return "not-installed"


def _error_details(exc: Exception) -> dict:
    """Safe, structured fields of a provider error: HTTP status, Google status and reason codes. Never the message."""
    out = {"exception": type(exc).__name__, "http_status": None, "api_status": None, "reason": None}
    code = getattr(exc, "code", None)
    out["http_status"] = code if isinstance(code, int) else None
    status = getattr(exc, "status", None)
    out["api_status"] = status if isinstance(status, str) and re.fullmatch(r"[A-Z_]{3,40}", status) else None
    details = getattr(exc, "details", None)
    items = (details or {}).get("error", {}).get("details", []) if isinstance(details, dict) else []
    reasons = [d.get("reason") for d in items if isinstance(d, dict) and isinstance(d.get("reason"), str)]
    reasons = [r for r in reasons if re.fullmatch(r"[A-Z_]{3,60}", r)]
    out["reason"] = reasons[0] if reasons else None
    return out


def _classify(exc: Exception) -> tuple[str, bool]:
    """(code, transient) for a provider exception."""
    try:
        from google.genai import errors
    except ImportError:              # SDK not installed
        return "setup", False
    import httpx
    if isinstance(exc, (httpx.TimeoutException, TimeoutError)):
        return "timeout", True
    if isinstance(exc, errors.APIError):
        d = _error_details(exc)
        if exc.code == 429:
            return "quota", False
        if exc.code in (401, 403) or d["reason"] in ACCESS_REASONS or d["api_status"] in ACCESS_STATUS:
            return "access", False
        if exc.code in (400, 404):
            return "incompatible", False      # request format, schema, thinking setting or model name rejected
        if exc.code in TRANSIENT_STATUS:
            return "provider", True
    return "provider", False


def diagnostic(stage: str, category: str, cfg: AIConfig | None = None, exc: Exception | None = None, **extra) -> str:
    """One sanitised log line: stage, category, error codes, model and SDK version, configuration booleans.
    Never the API key, headers, payload, prompt, response text or provider error message."""
    fields = {"stage": stage, "category": category}
    if exc is not None:
        fields.update(_error_details(exc))
    fields.update({"model": cfg.model if cfg else None, "sdk": sdk_version(), "config_ready": cfg is not None, **extra})
    line = "BAHO_NEZA_AI_DIAG " + " ".join(f"{k}={v}" for k, v in fields.items())
    log.warning(line)
    return line


def config_report(raw: Mapping | None) -> dict:
    """Configuration booleans for diagnostics (no values)."""
    raw = raw if isinstance(raw, Mapping) else {}
    model = raw.get("model").strip() if _real(raw.get("model")) else DEFAULT_MODEL
    return {"section_present": bool(raw), "enabled_true": raw.get("enabled") is True,
            "provider_ok": raw.get("provider", "gemini") == "gemini", "key_present": _real(raw.get("api_key")),
            "model_set": _real(raw.get("model")), "model_valid": MODEL_ID.match(model) is not None,
            "approved_true": raw.get("external_data_approved") is True}


def log_config_status() -> str:
    """Log why AI is not ready (booleans only); used when a user asks for results while AI is off."""
    try:
        import streamlit as st
        raw = st.secrets.get("ai")
        raw = dict(raw) if raw is not None else None
    except Exception:            # noqa: BLE001
        raw = None
    status, _ = config_status(raw)
    rep = config_report(raw)
    line = "BAHO_NEZA_AI_CONFIG status=" + status + " " + " ".join(f"{k}={v}" for k, v in rep.items())
    log.warning(line)
    return line


def generate(payload: dict, cfg: AIConfig, limitations: tuple[str, ...], *, client=None,
             sleep: Callable[[float], None] = time.sleep) -> str:
    """Raw JSON text from the model. At most one retry, for timeouts and 5xx errors only."""
    text = json.dumps(payload, ensure_ascii=False)
    if len(text) > ex.MAX_PAYLOAD_CHARS:
        diagnostic("payload", "invalid", cfg)
        raise ProviderError("invalid")
    try:
        client = client or make_client(cfg)
        config = _request_config(cfg, payload["language"], limitations)
    except Exception as exc:     # noqa: BLE001 - SDK missing or the request configuration cannot be built
        diagnostic("setup", "setup", cfg, exc)
        raise ProviderError("setup") from None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            response = client.models.generate_content(model=cfg.model, contents=text, config=config)
        except Exception as exc:     # noqa: BLE001 - mapped to a short code, never logged in full
            code, transient = _classify(exc)
            diagnostic("request", code, cfg, exc, attempt=attempt, transient=transient)
            if transient and attempt < MAX_ATTEMPTS:
                sleep(RETRY_DELAY_S)
                continue
            raise ProviderError(code) from None
        out = getattr(response, "text", None)
        if not isinstance(out, str) or not out.strip() or len(out) > ex.MAX_RESPONSE_CHARS:
            finish = None
            try:
                finish = str(response.candidates[0].finish_reason.name)
            except Exception:        # noqa: BLE001
                pass
            diagnostic("response", "malformed", cfg, attempt=attempt, finish_reason=finish,
                       text_chars=len(out) if isinstance(out, str) else 0)
            raise ProviderError("malformed")
        return out
    raise ProviderError("provider")


# ---------------------------------------------------------------------------
# Session guard: duplicate protection, cooldown, per-session cap
# ---------------------------------------------------------------------------
def guard_check(state: dict, key: tuple, now: float) -> str | None:
    """Reason to refuse a new request, or None. `state` lives in st.session_state (one browser session)."""
    if key in state.get("done", {}):
        return "done"
    inflight = state.get("inflight")
    if inflight and now - inflight[1] < INFLIGHT_EXPIRY_S:
        return "inflight"
    if state.get("count", 0) >= MAX_REQUESTS_PER_SESSION:
        return "limit"
    if now - state.get("last", -1e9) < COOLDOWN_S:
        return "cooldown"
    return None


def request_explanation(kind: str, result: dict, facts: dict, fingerprint: str, lang: str, cfg: AIConfig,
                        state: dict, now: float, *, client=None, sleep=time.sleep) -> tuple[dict | None, str | None]:
    """Validated AI sections for (kind, fingerprint, lang), or (None, error_code). Results are stored in `state`."""
    key = (kind, fingerprint, lang)
    reason = guard_check(state, key, now)
    if reason == "done":
        return state["done"][key], None
    if reason:
        return None, reason
    state["inflight"] = (key, now)
    state["count"] = state.get("count", 0) + 1
    state["last"] = now
    try:
        limitations = ex.limitation_ids(kind, result)
        payload = ex.build_payload(kind, result, facts, fingerprint, lang)
        raw = generate(payload, cfg, limitations, client=client, sleep=sleep)
        sections = ex.validate_response(raw, kind, facts, limitations, lang)
    except ProviderError as e:
        return None, e.code
    except ex.MalformedResponse as e:
        diagnostic("parse", "malformed", cfg, rule=str(e).replace(" ", "_"))
        return None, "malformed"
    except ex.InvalidExplanation as e:
        diagnostic("validate", "invalid", cfg, rule=str(e).replace(" ", "_"))     # our own rule names only
        return None, "invalid"
    except ValueError:
        diagnostic("payload", "invalid", cfg)
        return None, "invalid"
    finally:
        state["inflight"] = None
    done = state.setdefault("done", {})
    done[key] = sections
    while len(done) > 12:                       # bounded per-session store
        done.pop(next(iter(done)))
    return sections, None
