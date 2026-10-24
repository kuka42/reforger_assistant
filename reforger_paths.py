"""Ścieżki asystenta ustawiane w interfejsie (od 1.9.0): odczyt i zapis w assistant_web_data/settings.json
oraz sprawdzanie, czy wskazane pliki i foldery istnieją.

Zasady:
- Ścieżki obowiązują od NASTĘPNEGO uruchomienia asystenta (silnik i BK startują z jednym, spójnym zestawem).
- Pierwszeństwo: zmienna środowiskowa > settings.json > wartość domyślna.
- Sprawdzanie tylko odpowiada, czy wskazany plik/folder istnieje i wygląda właściwie; niczego nie listuje
  ani nie przegląda. Model nie dostaje przez to żadnego nowego dostępu.
Sama biblioteka standardowa."""
from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

SETTINGS_FILE = Path(__file__).resolve().parent / "assistant_web_data" / "settings.json"
MAX_PATH_LEN = 400

# klucz w settings.json -> (zmienna środowiskowa, opis w interfejsie)
PATH_FIELDS = {
    "mcp_script": ("ENFUSION_MCP_SCRIPT", "Plik dist/index.js serwera Enfusion MCP BK"),
    "game_path": ("ENFUSION_GAME_PATH", "Folder zainstalowanej gry Arma Reforger"),
    "docs_path": ("REFORGER_DOCS_PATH", "Folder docs dokumentacji API (opcjonalny)"),
}
SOURCE_LABELS = {"env": "zmienna środowiskowa", "settings": "ustawienia (interfejs)", "default": "domyślna"}


def read_settings() -> dict:
    try:
        data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def write_settings(updates: dict) -> None:
    """Zapis z zachowaniem pozostałych kluczy (model, num_ctx, paths)."""
    data = read_settings()
    data.update(updates)
    data["version"] = 1
    SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    temp = SETTINGS_FILE.with_suffix(".tmp")
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(SETTINGS_FILE)


def clean_path(value) -> str:
    """Ścieżka wklejona z Eksploratora: bez cudzysłowów i spacji na końcach. Pusty tekst = brak wartości."""
    if not isinstance(value, str):
        return ""
    value = value.strip().strip('"').strip("'").strip()
    if len(value) > MAX_PATH_LEN or any(ord(c) < 32 for c in value):
        raise ValueError("nieprawidłowa ścieżka (za długa albo ze znakami sterującymi)")
    return value


def saved_paths() -> dict[str, str]:
    raw = read_settings().get("paths")
    out: dict[str, str] = {}
    if isinstance(raw, dict):
        for key in PATH_FIELDS:
            try:
                value = clean_path(raw.get(key))
            except ValueError:
                continue
            if value:
                out[key] = value
    return out


def resolve(key: str, default: str) -> tuple[str, str]:
    """(wartość, źródło) dla ścieżki: env > settings.json > domyślna."""
    env_name = PATH_FIELDS[key][0]
    env_value = os.environ.get(env_name, "").strip()
    if env_value:
        return env_value, "env"
    saved = saved_paths().get(key)
    if saved:
        return saved, "settings"
    return default, "default"


def default_docs_path(game_path: str) -> str:
    return str(Path(game_path).parent / "Arma Reforger Tools" / "Workbench" / "docs") if game_path else ""


def check_mcp_script(path: str) -> tuple[bool, str]:
    if not path:
        return False, "podaj ścieżkę do pliku index.js"
    p = Path(path)
    if p.is_dir():
        hint = p / "dist" / "index.js"
        return False, ("to jest folder; plik serwera to " + str(hint)) if hint.is_file() else "to jest folder, a nie plik index.js"
    if not p.is_file():
        return False, "nie ma takiego pliku"
    if p.suffix.lower() != ".js":
        return False, "to nie jest plik .js"
    if not shutil.which("node"):
        return False, "plik jest, ale nie znaleziono programu node (Node.js) w PATH"
    return True, "plik serwera jest, Node.js dostępny"


def check_game_path(path: str) -> tuple[bool, str]:
    if not path:
        return False, "podaj folder gry"
    p = Path(path)
    if not p.is_dir():
        return False, "nie ma takiego folderu"
    if not (p / "addons").is_dir():
        return False, "brak podfolderu addons - to chyba nie jest folder gry Arma Reforger"
    return True, "folder gry jest (addons)"


def check_docs_path(path: str) -> tuple[bool, str]:
    if not path:
        return False, "brak ścieżki"
    p = Path(path)
    if not p.is_dir():
        return False, "nie ma takiego folderu (bez dokumentacji asystent bierze klasy bazowe z plików gry)"
    found = [name for name in ("ArmaReforgerScriptAPIPublic", "EnfusionScriptAPI")
             if (p / name / "html" / "hierarchy.html").is_file()]
    if not found:
        return False, "brak plików */html/hierarchy.html - to chyba nie jest folder Workbench\\docs"
    return True, "hierarchia klas: " + ", ".join(found)


def check_all(values: dict[str, str]) -> dict[str, dict]:
    """Wynik sprawdzenia dla każdego pola: {ok, message, value} (docs: pusta wartość = obok gry)."""
    out = {}
    mcp = values.get("mcp_script", "")
    game = values.get("game_path", "")
    docs = values.get("docs_path", "") or default_docs_path(game)
    for key, value, fn in (("mcp_script", mcp, check_mcp_script), ("game_path", game, check_game_path),
                           ("docs_path", docs, check_docs_path)):
        ok, message = fn(value)
        out[key] = {"ok": ok, "message": message, "value": value}
    if not values.get("docs_path"):
        out["docs_path"]["message"] = "(obok gry) " + out["docs_path"]["message"]
    return out
