"""Hierarchia klas z dokumentacji API dołączonej do Arma Reforger Tools (od 1.8.8).

Workbench ma lokalnie dokumentację Doxygen:
  <Arma Reforger Tools>/Workbench/docs/ArmaReforgerScriptAPIPublic/html/hierarchy.html
  <Arma Reforger Tools>/Workbench/docs/EnfusionScriptAPI/html/hierarchy.html
Strona hierarchy.html zapisuje drzewo dziedziczenia w wierszach tabeli: id="row_0_3_1_" oznacza
trzecie dziecko -> pierwsze dziecko korzenia 0. Dane API w Enfusion MCP BK mają dla wielu klas błędną
hierarchię (BK odczytywał ją z obrazków-diagramów), więc silnik bierze klasy bazowe stąd.

Tylko odczyt plików z dysku, sama biblioteka standardowa, bez sieci. Brak plików niczego nie psuje:
silnik wraca wtedy do deklaracji z plików gry ([BAZA])."""
from __future__ import annotations

import html
import os
import re
from pathlib import Path

DOC_SETS = ("ArmaReforgerScriptAPIPublic", "EnfusionScriptAPI")

_ROW_RE = re.compile(r'<tr[^>]*\bid="(row_[0-9_]+)"[^>]*>(.*?)</tr>', re.S)
_ENTRY_RE = re.compile(r'<td class="entry">(.*?)</td>', re.S)
_LINK_RE = re.compile(r'<a class="el"[^>]*>([^<]+)</a>')


def docs_dir(game_path: str, configured: str = "") -> Path:
    """Folder docs: z konfiguracji (zmienna REFORGER_DOCS_PATH albo ustawienia z interfejsu), inaczej
    <steamapps/common>/Arma Reforger Tools/Workbench/docs obok folderu gry."""
    if configured:
        return Path(configured)
    env = os.environ.get("REFORGER_DOCS_PATH", "").strip()
    if env:
        return Path(env)
    return Path(game_path).parent / "Arma Reforger Tools" / "Workbench" / "docs"


def parse_hierarchy(text: str) -> tuple[dict[str, str], dict[str, list[str]]]:
    """(rodzic klasy, dzieci klasy) ze strony hierarchy.html. Wiersze bez linku (klasy spoza tej
    dokumentacji, np. bazowe klasy silnika) też są węzłami drzewa."""
    id_to_name: dict[str, str] = {}
    parents: dict[str, str] = {}
    children: dict[str, list[str]] = {}
    for row_id, body in _ROW_RE.findall(text):
        m = _ENTRY_RE.search(body)
        entry = m.group(1) if m else body
        link = _LINK_RE.search(entry)
        if link:
            name = link.group(1)
        else:
            tokens = re.sub(r"<[^>]+>", " ", entry).split()
            name = tokens[-1] if tokens else ""
        name = html.unescape(name).replace("\xa0", " ").strip()
        if not name:
            continue
        id_to_name[row_id] = name
        children.setdefault(name, [])
        segs = row_id[len("row_"):].rstrip("_").split("_")
        if len(segs) > 1:
            parent = id_to_name.get("row_" + "_".join(segs[:-1]) + "_")
            if parent and parent != name:
                parents.setdefault(name, parent)        # pierwsze wystąpienie wygrywa
                if name not in children.setdefault(parent, []):
                    children[parent].append(name)
    return parents, children


class DocHierarchy:
    """Klasy bazowe i podklasy z obu stron hierarchy.html (Arma ma pierwszeństwo przed Enfusion)."""

    def __init__(self) -> None:
        self.parents: dict[str, str] = {}
        self.children: dict[str, list[str]] = {}
        self.sources: list[str] = []
        self.missing: list[str] = []

    def load(self, base: Path) -> "DocHierarchy":
        for name in DOC_SETS:
            path = base / name / "html" / "hierarchy.html"
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                self.missing.append(str(path))
                continue
            parents, children = parse_hierarchy(text)
            for cls, parent in parents.items():
                self.parents.setdefault(cls, parent)
            for cls, kids in children.items():
                merged = self.children.setdefault(cls, [])
                merged.extend(k for k in kids if k not in merged)
            self.sources.append(f"{name}: {len(children)} klas")
        return self

    def __bool__(self) -> bool:
        return bool(self.children)

    def knows(self, cls: str) -> bool:
        return cls in self.children

    def chain(self, cls: str, depth: int = 12) -> list[str]:
        """Przodkowie od najbliższego; pusta lista = klasa bez klasy bazowej albo nieznana."""
        out: list[str] = []
        current = cls
        while len(out) < depth:
            parent = self.parents.get(current)
            if not parent or parent == cls or parent in out:
                break
            out.append(parent)
            current = parent
        return out

    def subclasses(self, cls: str) -> list[str]:
        return list(self.children.get(cls, []))
