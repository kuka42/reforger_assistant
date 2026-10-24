"""Język asystenta (od 2.0.0): "pl" albo "en". Jeden kod, dwa zestawy tekstów.

Źródło: zmienna REFORGER_LANG > assistant_web_data/settings.json ("lang") > "pl".
Teksty dla modelu i użytkownika są w reforger_prompts.py (PL) i reforger_prompts_en.py (EN);
krótkie komunikaty logu i drobne napisy w kodzie wybiera funkcja tr(pl, en).
Interfejs w przeglądarce (assistant.html) na razie zostaje po polsku."""
from __future__ import annotations

import os

from reforger_paths import read_settings

SUPPORTED = ("pl", "en")


def _resolve() -> str:
    value = os.environ.get("REFORGER_LANG", "").strip().lower()
    if value in SUPPORTED:
        return value
    saved = str(read_settings().get("lang", "")).strip().lower()
    return saved if saved in SUPPORTED else "pl"


LANG = _resolve()
EN = LANG == "en"


def tr(pl: str, en: str) -> str:
    """Tekst w bieżącym języku (oba warianty podaje się w miejscu użycia)."""
    return en if EN else pl
