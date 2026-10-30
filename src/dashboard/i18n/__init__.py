"""Translations for the Baho Neza app: English (en.yaml) and Kinyarwanda (rw.yaml).

Every user-facing string lives in the YAML catalogues. Keys are dotted paths into the nested YAML ("home.hero_title").
`translate(key, lang, **values)` is pure; `t(key, **values)` reads the language chosen in the app's session.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml

I18N_DIR = Path(__file__).resolve().parent
LANGUAGES = {"en": "English", "rw": "Kinyarwanda"}
DEFAULT_LANGUAGE = "en"


def _flatten(tree: dict, prefix: str = "") -> dict[str, str]:
    out: dict[str, str] = {}
    for k, v in tree.items():
        key = f"{prefix}{k}"
        if isinstance(v, dict):
            out.update(_flatten(v, key + "."))
        else:
            out[key] = str(v)
    return out


@lru_cache(maxsize=None)
def catalog(lang: str) -> dict[str, str]:
    if lang not in LANGUAGES:
        raise ValueError(f"Unknown language {lang!r}; choose from {sorted(LANGUAGES)}")
    with open(I18N_DIR / f"{lang}.yaml", encoding="utf-8") as f:
        return _flatten(yaml.safe_load(f))


def translate(key: str, lang: str = DEFAULT_LANGUAGE, **values) -> str:
    """Text for `key` in `lang` (English if the key is missing there), with `{placeholders}` filled from `values`."""
    text = catalog(lang).get(key)
    if text is None:
        text = catalog(DEFAULT_LANGUAGE).get(key)
    if text is None:
        raise KeyError(f"No translation for {key!r}")
    return text.format(**values) if values else text


def current_language() -> str:
    import streamlit as st
    lang = st.session_state.get("lang", DEFAULT_LANGUAGE)
    return lang if lang in LANGUAGES else DEFAULT_LANGUAGE


def t(key: str, **values) -> str:
    return translate(key, current_language(), **values)


def bound(lang: str | None = None):
    """`t` fixed to one language. Use it for widget format functions, which Streamlit may call outside a script run."""
    lang = lang or current_language()
    return lambda key, **values: translate(key, lang, **values)
