# -*- coding: utf-8 -*-
"""Zestaw testowy asystenta Reforger (Ollama + Enfusion MCP BK).

Trzy polecenia:
  python reforger_eval.py questions
      Wypisuje pytania do wklejenia (jedna NOWA rozmowa na test; test A ma 2 pytania w jednej rozmowie).

  python reforger_eval.py score [assistant_web_data\\conversations.json] [--md wyniki.md]
      Ocenia odpowiedzi z zapisanych rozmów według klucza (wymagane elementy + znane błędy).
      Rozmowy rozpoznaje po treści pierwszego pytania, więc kilka podejść do tego samego testu
      jest automatycznie liczonych jako kolejne uruchomienia.

  python reforger_eval.py log log.txt
      Podsumowuje log serwera: liczba wywołań MCP, błędy, [REPAIR]/[DUP]/[STALL], puste odpowiedzi,
      szczyt kontekstu i czas każdej tury.

Klucz odpowiedzi pochodzi z prawdziwych plików gry (odczytanych przez MCP BK), a nie z pamięci.
Ocena automatyczna to wyrażenia regularne: łapie nazwy, pola i znane błędy. Nie ocenia sensu
zdań ani tego, czy kod się skompiluje. Traktuj ją jako szybki przegląd, a nie wyrok.
"""
from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # starsze Pythony / przekierowania
    pass

I = re.I
S = re.S


def rx(pattern: str, flags: int = I | S):
    compiled = re.compile(pattern, flags)
    return lambda text: bool(compiled.search(text))


def all_of(*patterns: str):
    compiled = [re.compile(p, I | S) for p in patterns]
    return lambda text: all(c.search(text) for c in compiled)


def count_of(patterns: list[str], need: int):
    compiled = [re.compile(p, I | S) for p in patterns]
    def check(text: str) -> bool:
        return sum(1 for c in compiled if c.search(text)) >= need
    return check


def count_hits(patterns: list[str]):
    compiled = [re.compile(p, I | S) for p in patterns]
    return lambda text: sum(1 for c in compiled if c.search(text))


ALLOWED_ICONS = {"pick-up", "bipod", "not-available", "magazine", "availability-full"}


def invented_icon(text: str) -> bool:
    """m_sIconName spoza ikon znanych z Weapon_Base.et i bez oznaczenia 'WYMYSLONE/szkic' w tej linii."""
    for line in text.splitlines():
        m = re.search(r'm_sIconName\s+"([^"]+)"', line)
        if m and m.group(1) not in ALLOWED_ICONS and not re.search(r"wymy[sś]l|szkic|zast[aą]p", line, I):
            return True
    return False


NEGATION = re.compile(r"\bnie\b|\bbrak\b|\bbez\b|nieistniej|not found|does not exist", re.I)


def invented_weaponlog_file(text: str) -> bool:
    """Plik SCR_WeaponLogManager.c podany jak prawdziwe źródło: linia z przeczeniem, pytaniem
    ('sprawdź, czy istnieje') albo sugestią szukania nie jest twierdzeniem."""
    for line in text.splitlines():
        if (re.search(r"SCR_WeaponLogManager\.c", line, I) and not NEGATION.search(line)
                and not re.search(r"\bczy\b|sprawd[źz]|jeśli|jezeli|ewentualn|lub\s+`?SCR_WeaponLogManager\.et", line, I)):
            return True
    return False


def has_disclaimer_for_getprefabname(text: str) -> bool:
    return bool(re.search(
        r"(nie istnieje|nie występuje|nie znaleziono|brak\s+(?:\w+\s+){0,3}metod"
        r"|nie\s+(?:ma|jest)\s+[^\n]{0,60}(GetPrefabName|zdefiniowan|dostępn|metod\w*)"
        r"|GetPrefabName[^\n]{0,80}nie\s+(?:jest|istnieje|ma))", text, I))


def entity_getprefabname_call(text: str) -> bool:
    """Wywołanie X.GetPrefabName( na encji (IEntity tego nie ma). Linie z przeczeniem
    ('nie ma metody IEntity.GetPrefabName()') są pomijane, a EntityPrefabData i
    SCR_ResourceNameUtils są poprawnymi odbiorcami."""
    lines = text.splitlines()
    for idx, line in enumerate(lines):
        window = ((lines[idx - 1] + " " if idx else "") + line
                  + (" " + lines[idx + 1] if idx + 1 < len(lines) else ""))   # zaprzeczenie bywa w następnej linii
        if NEGATION.search(window):
            continue
        for m in re.finditer(r"(\w+)\s*\.\s*GetPrefabName\s*\(", line):
            ident = m.group(1).lower()
            if ident.endswith("data") or ident.endswith("class") or ident == "scr_resourcenameutils":
                continue
            if "entity" in ident or ident in ("owner", "ent", "e", "player", "weapon"):
                return True
    return False


# Błędy, które wystąpiły w różnych testach (sprawdzane w KAŻDEJ odpowiedzi).
COMMON_BAD = [
    ("wymyślony poziom LogLevel (są: SPAM, VERBOSE, DEBUG, NORMAL, WARNING, ERROR, FATAL)",
     rx(r"LogLevel\.(?!(?:SPAM|VERBOSE|DEBUG|NORMAL|WARNING|ERROR|FATAL)\b|c\b)\w+", I)),
    ("nieistniejąca klasa bazowa SCR_Component", rx(r":\s*SCR_Component\b")),
    ("operator ?. (nie widziałem go w Enforce Script - podejrzane)", rx(r"\)\s*\?\s*\.\s*\w")),
    ("'w pełni zweryfikowane' (nadmierna pewność)", rx(r"w pełni zweryfikowan")),
    ("numery linii w plikach (game_read ich nie zwraca - wymysł)", rx(r"\(\s*linia\s*~?\s*\d+|linii\s*~?\s*\d+\s*[-‑–]\s*\d+|\blinia\s*~?\s*\d+\s*[-‑–]\s*\d+")),
]


# ---------------------------------------------------------------------------------------------
# TESTY. Każdy test: lista pytań (tur) i reguły na odpowiedź KAŻDEJ tury.
# must: (etykieta, funkcja)  -> pożądane; ocena = ile spełnionych.
# bad : (etykieta, funkcja)  -> znane błędy; każde trafienie to naruszenie.
# ---------------------------------------------------------------------------------------------
Q_A1 = """Chcę dodać własną akcję użytkownika do broni, jako override prefabu
Weapon_Base w moim modzie. Znajdź w grze istniejącą akcję użytkownika
na broni (np. safety albo tryb ognia) i na jej podstawie wyjaśnij:

1. Który prefab i jakie pola ActionsManagerComponent definiują akcje
   i konteksty broni?
2. Po jakiej klasie dziedziczy ta akcja i które metody nadpisuje?
3. Jak taka akcja jest podpięta w prefabie i jak wiąże się z kontekstem?

Odpowiedz w trzech sekcjach: "Z kodu" (z nazwą pliku przy każdym
twierdzeniu), "Wnioski (niezweryfikowane)", "Czego nie sprawdzono".
Nie podawaj kodu ani pól, których nie było w odczytanych plikach."""

Q_A2 = """Na podstawie tego, co ustaliłeś, zaproponuj własną akcję użytkownika
dla broni: po wybraniu wypisuje do logu nazwę prefabu broni, na której
została użyta. Ma być widoczna tylko w trybie inspekcji broni.
Podaj (1) klasę Enforce Script, (2) wpis do additionalActions w moim
override Weapon_Base.et. Każdy element oznacz: "z kodu gry (plik)"
albo "szkic". Zaznacz, czego nie da się zweryfikować bez uruchomienia
Workbencha."""

TESTS = [
    {
        "id": "A",
        "name": "Akcja na broni (2 tury: badanie, potem własny kod)",
        "turns": [Q_A1, Q_A2],
        "rules": [
            {   # tura 1
                "must": [
                    ("prefab Weapon_Base.et", rx(r"Weapon_Base\.et")),
                    ("konteksty default/bipod/magazine/firemode", all_of(r"firemode", r"bipod", r"magazine")),
                    ("additionalActions", rx(r"additionalActions")),
                    ("ParentContextList", rx(r"ParentContextList")),
                    ("klasa bazowa SCR_InspectionUserAction", rx(r"SCR_InspectionUserAction")),
                    ("łańcuch SCR_InventoryAction -> ScriptedUserAction", all_of(r"SCR_InventoryAction", r"ScriptedUserAction")),
                    ("4 nadpisania Toggle Safety", all_of(r"PerformAction", r"CanBeShownScript", r"GetActionNameScript", r"\bInit\b")),
                ],
                "bad": [
                    ("muzzle przetłumaczone jako magazyn/municja", rx(r"(typ\w*|zależności od typu)\s+(magazyn|municj)|aktualny\s+magazyn|(?:odpowiedni|właściw)\w*\s+magazyn|sprawdza[^\n]{0,60}magazyn")),
                    ("'w pełni zweryfikowane' mimo sekcji Wnioski", rx(r"w pełni zweryfikowan")),
                    ("XML zamiast formatu .et", rx(r"<ActionsManagerComponent|<additionalActions")),
                    ("wymyślona tablica 'Actions'", rx(r"tablic\w*\s+Actions\b")),
                    ("IsSafetyOn jako prywatna", rx(r"IsSafetyOn[^\n]{0,40}prywatn|prywatn\w*[^\n]{0,25}IsSafetyOn")),
                ],
            },
            {   # tura 2
                "must": [
                    ("dziedziczy po SCR_InspectionUserAction", rx(r"class\s+\w+\s*:\s*SCR_InspectionUserAction")),
                    ("poprawna sygnatura PerformAction(IEntity, IEntity)",
                     rx(r"PerformAction\(\s*IEntity\s+pOwnerEntity\s*,\s*IEntity\s+pUserEntity\s*\)")),
                    ("nazwa prefabu przez istniejące API",
                     rx(r"SCR_ResourceNameUtils\.GetPrefabName\(\s*pOwnerEntity|GetPrefabData\(\)\s*\.\s*GetPrefabName|EntityPrefabData")),
                    ("globalne Print( lub PrintFormat(", rx(r"(?<![\w.])(?:Print|PrintFormat)\s*\(")),
                    ("ParentContextList w wpisie", rx(r"ParentContextList")),
                    ("UIInfo SCR_ActionUIInfo", rx(r"SCR_ActionUIInfo")),
                    ("uwaga o efekcie lokalnym", rx(r"HasLocalEffectOnly|tylko lokaln|efekt lokaln|lokalny efekt")),
                ],
                "bad": [
                    ("pOwnerEntity.GetPrefabName() (nie istnieje na IEntity)", rx(r"pOwnerEntity\s*\.\s*GetPrefabName\s*\(")),
                    ("GetPrefabName(this)", rx(r"GetPrefabName\(\s*this\s*\)")),
                    ("logowanie przez SCR_AddonManager/_print", rx(r"SCR_AddonManager|\b_print\s*\(")),
                    ("XML zamiast formatu .et", rx(r"<ActionsManagerComponent|<additionalActions|<action>")),
                    ("ponowna deklaracja m_WeaponComponent", rx(r"protected\s+BaseWeaponComponent\s+m_WeaponComponent")),
                    ("wymyślona ikona bez oznaczenia", invented_icon),
                    ("'default' jako 'tryb inspekcji'", rx(r"default[^\n]{0,60}(tryb\w*\s+inspekcj|czyli\s+w\s+trybie)")),
                    ("log opisany jako serwerowy (akcja ma efekt lokalny)",
                     rx(r"(Logujemy|wypisze|Print)[^\n]{0,80}(na serwerze|konsol\w+ serwera)|(na serwerze|konsol\w+ serwera)[^\n]{0,80}Print")),
                ],
            },
        ],
    },
    {
        "id": "B",
        "name": "Logowanie / funkcje globalne (Print)",
        "turns": ["Jak wypisać komunikat do logu w skrypcie Enforce Script? Podaj składnię, sposób użycia "
                  "poziomu logowania i krótki przykład. Zaznacz, skąd masz tę informację."],
        "rules": [{
            "must": [
                ("Print(", rx(r"(?<![\w.])Print\s*\(")),
                ("PrintFormat", rx(r"PrintFormat")),
                ("LogLevel", rx(r"LogLevel")),
                ("placeholdery %1", rx(r"%1")),
                ("podane źródło (wiki/plik)", rx(r"community\.bistudio|wiki|Scripting|\.c\b")),
            ],
            "bad": [
                ("SCR_AddonManager/_print", rx(r"SCR_AddonManager|\b_print\s*\(")),
                ("Print jako metoda klasy testowej SCR_Autotest* (to nie globalna funkcja logowania)",
                 rx(r"SCR_Autotest\w+\.Print\s*\(|Print[^\n]{0,40}z\s+klasy\s+`?SCR_Autotest")),
                ("wymyślone API logowania", rx(r"\b(Debug\.Print|System\.Print|Log\.(Info|Debug|Warn)|printf\s*\(|console\.log|SCR_Log)")),
                ("Log(prefix, level) klas UIInfo podane jako ogólne logowanie (to metoda instancji)", rx(r"\bSCR_\w+\.Log\s*\(")),
            ],
        }],
    },
    {
        "id": "C",
        "name": "Eventy ScriptedUserAction (lista z kodu)",
        "turns": ["Wymień wszystkie eventy ScriptedUserAction z sygnaturami i krótko napisz, kiedy są "
                  "wywoływane. Opieraj się wyłącznie na komentarzach z kodu gry i podaj plik."],
        "rules": [{
            "must": [
                ("plik ScriptedUserAction.c", rx(r"generated/UserAction/ScriptedUserAction\.c")),
                ("15 eventów (min. 13)", count_of([
                    r"\bInit\b", r"\bPerformAction\b", r"PerformContinuousAction", r"\bOnConfirmed\b", r"\bOnRejected\b",
                    r"OnActionCanceled", r"OnActionStart", r"GetActionNameScript", r"GetActionDescriptionScript",
                    r"CanBePerformedScript", r"CanBeShownScript", r"HasLocalEffectOnlyScript",
                    r"CheckOnServerFirstScript", r"CanBroadcastScript", r"GetActionProgressScript"], 13)),
                ("domyślny postęp fProgress + timeSlice", rx(r"fProgress\s*\+\s*timeSlice|dodaje\s+`?timeSlice|timeSlice[^\n]{0,50}(dodaj|do bieżącego)")),
            ],
            "bad": [
                ("metody BaseUserAction przypisane do ScriptedUserAction",
                 rx(r"ScriptedUserAction[^\n]{0,120}(GetContextIndex|SetActiveContext)")),
                ("'Init rejestruje akcję'", rx(r"Init[^\n]{0,80}rejestruj\w*\s+akcj")),
            ],
        }],
    },
    {
        "id": "D",
        "name": "UserActionContext (API + prefab)",
        "turns": ["Czym jest UserActionContext, jakie pola ma w prefabie Weapon_Base i jakie metody ma w API? "
                  "Podaj źródła."],
        "rules": [{
            "must": [
                ("pola prefabu ContextName/Position/Radius", all_of(r"ContextName", r"Radius", r"Position")),
                ("PointInfo albo SCR_ActionContextUIInfo", rx(r"PointInfo|SCR_ActionContextUIInfo")),
                ("API GetContextName/GetRadius", all_of(r"GetContextName", r"GetRadius")),
                ("API IsOmnidirectional/GetHeight/IsCapsule", rx(r"IsOmnidirectional|GetHeight|IsCapsule")),
                ("GetActionsList", rx(r"GetActionsList")),
                ("opis: kolekcja akcji w ActionsManagerComponent", rx(r"(kolekcj|zbi[oó]r|grup)\w*[^\n]{0,80}akcj|ActionsManagerComponent")),
            ],
            "bad": [
                ("XML zamiast formatu .et", rx(r"<UserActionContext|<ActionContexts")),
            ],
        }],
    },
    {
        "id": "E",
        "name": "WeaponComponent w prefabie (konfiguracja)",
        "turns": ["Jak w prefabie Weapon_Base skonfigurowany jest komponent WeaponComponent? Wymień pola "
                  "i ich wartości, które widać w pliku."],
        "rules": [{
            "must": [
                ("WeaponSlotType primary", all_of(r"WeaponSlotType", r"primary")),
                ("obstructionTestBBScale", rx(r"obstructionTestBBScale")),
                ("sightsCameraRollScaler", rx(r"sightsCameraRollScaler")),
                ("WeaponUIInfo / box.conf", rx(r"WeaponUIInfo|box\.conf|m_MagIndicator")),
                ("SightsComponent / WeaponAnimationComponent", rx(r"SightsComponent|WeaponAnimationComponent")),
                ("ścieżka Weapon_Base.et", rx(r"Weapon_Base\.et")),
            ],
            "bad": [
                ("pola/komponenty spoza tego prefabu", rx(r"fire\s*rate|MuzzleComponent|BaseMuzzleComponent|magazine\s*well|m_fFireRate")),
                ("XML zamiast formatu .et", rx(r"<WeaponComponent")),
            ],
        }],
    },
    {
        "id": "F",
        "name": "Init w SCR_ToggleSafetyUserAction (pułapka muzzle/magazyn)",
        "turns": ["Co robi Init w SCR_ToggleSafetyUserAction w zależności od atrybutu m_eMuzzleType? Opisz "
                  "każdą gałąź i wyjaśnij, po co ta akcja ma ten atrybut."],
        "rules": [{
            "must": [
                ("MT_BaseMuzzle", rx(r"MT_BaseMuzzle")),
                ("MT_UGLMuzzle", rx(r"MT_UGLMuzzle")),
                ("m_WeaponComponent", rx(r"m_WeaponComponent")),
                ("m_AttachmentStorage", rx(r"m_AttachmentStorage")),
                ("WeaponAttachmentsStorageComponent", rx(r"WeaponAttachmentsStorageComponent")),
                ("mowa o lufie/wyrzutni (muzzle)", rx(r"luf\w+|wyrzutni|granatnik|UGL|muzzle")),
            ],
            "bad": [
                ("muzzle przetłumaczone jako magazyn/municja", rx(r"(typ\w*|zależności od typu)\s+(magazyn|municj)|typ\s+magazyn")),
                ("Init rzekomo ustawia m_eMuzzleType", rx(r"Init[^\n]{0,80}ustawia[^\n]{0,40}m_eMuzzleType")),
            ],
        }],
    },
    {
        "id": "G",
        "name": "Sprawdzenie trybu inspekcji (krótki fragment kodu)",
        "turns": ["Jak w skrypcie sprawdzić, czy postać gracza jest w trybie inspekcji broni? Pokaż fragment "
                  "kodu z gry i podaj plik."],
        "rules": [{
            "must": [
                ("CharacterControllerComponent", rx(r"CharacterControllerComponent")),
                ("GetInspect()", rx(r"GetInspect\s*\(\s*\)")),
                ("FindComponent + Cast", all_of(r"FindComponent", r"\.Cast\s*\(")),
                ("plik SCR_InspectionUserAction/ToggleSafety", rx(r"SCR_InspectionUserAction\.c|SCR_ToggleSafetyUserAction\.c")),
            ],
            "bad": [
                ("GetComponent<T>() (to nie jest API Enforce Script; jest FindComponent + Cast)", rx(r"\bGetComponent\s*<")),
                ("FindComponent(...).Cast<T>() (nieprawidłowa składnia)", rx(r"FindComponent\([^)]*\)\s*\.\s*Cast\s*<")),
                ("zła klasa bazowa SCR_CharacterControllerComponent (jest CharacterControllerComponent)",
                 rx(r"class\s+SCR_CharacterControllerComponent\s*:\s*(?!CharacterControllerComponent\b)\w+")),
                ("m_bInspectionFocus opisane jako 'tryb inspekcji' (to fokus podglądu, nie stan trybu)",
                 rx(r"m_bInspectionFocus[^\n]{0,90}(tryb\w*\s+inspekcj|jest w trybie|czy postać)")),
                ("wymyślone API inspekcji", lambda t: bool(re.search(r"\b(GetIsInspecting|IsInspecting|IsInspect)\s*\(|\bInspectionComponent\b", t))),
                ("GetInspect przypisany do SCR_CharacterControllerComponent.c / .proto (plik .c go nie zawiera)",
                 rx(r"SCR_CharacterControllerComponent\.c[\s\S]{0,300}proto external|(zadeklarowan\w*|zdefiniowan\w*|definicj\w*)[^\n]{0,80}SCR_CharacterControllerComponent\.c|SCR_CharacterControllerComponent\.c[\s\S]{0,250}\.proto")),
            ],
        }],
    },
    {
        "id": "H",
        "name": "Fałszywa przesłanka: IEntity.GetPrefabName()",
        "turns": ["Jak użyć metody IEntity.GetPrefabName() żeby pobrać nazwę prefabu encji? Podaj przykład."],
        "rules": [{
            "must": [
                ("zaznacza, że takiej metody nie ma na IEntity", has_disclaimer_for_getprefabname),
                ("wskazuje działającą alternatywę",
                 rx(r"SCR_ResourceNameUtils\.GetPrefabName|GetPrefabData\s*\(\s*\)\s*\.\s*GetPrefabName|EntityPrefabData")),
            ],
            "bad": [
                ("wywołanie GetPrefabName() na encji (nie istnieje na IEntity)", entity_getprefabname_call),
                ("encja rzutowana na GenericEntityClass (to klasa danych prefabu, nie encja)",
                 rx(r"GenericEntityClass\s+\w+\s*=\s*(?:Class|GenericEntityClass)\.Cast\(\s*\w*[eE]ntity")),
            ],
        }],
    },
    {
        "id": "I",
        "name": "Fałszywa przesłanka: nieistniejąca klasa SCR_WeaponLogManager",
        "turns": ["Jak działa klasa SCR_WeaponLogManager i jakie ma metody? Podaj plik źródłowy."],
        "rules": [{
            "must": [
                ("informuje, że klasy nie znaleziono",
                 rx(r"(nie (znaleziono|istnieje|ma|udało się (znaleźć|odnaleźć))|brak (takiej )?klas|nie występuje|nie jest zdefiniowan)")),
            ],
            "bad": [
                ("wymyślony plik SCR_WeaponLogManager.c (bez przeczenia)", invented_weaponlog_file),
                ("opisuje klasę, jakby istniała", rx(r"SCR_WeaponLogManager\W{0,6}(ma|zawiera|definiuje|dziedziczy|udostępnia|oferuje)")),
                ("podstawia inną klasę (SCR_AddonManager itp.)", rx(r"SCR_AddonManager|SCR_CameraManager|SCR_ChatPanelManager")),
                ("cytuje 'api_search(...) -> brak wyników' (api_search zwraca rozmyte trafienia, nigdy 'brak')",
                 rx(r"api_search\([^)]*\)\s*(→|->|=>)\s*brak")),
            ],
        }],
    },
    {
        "id": "J",
        "name": "Prefiks modderski i katalogi skryptów (wiki)",
        "turns": ["Jakie prefiksy powinny mieć nazwy plików i klas w moim modzie i w jakich katalogach muszą "
                  "leżeć skrypty, żeby gra je załadowała? Podaj źródło."],
        "rules": [{
            "must": [
                ("prefiks / modder tag", rx(r"prefiks|tag\b|TAG_|ABC_")),
                ("katalogi Game i GameCode", all_of(r"\bGame\b", r"GameCode")),
                ("skrypty poza modułami są ignorowane", rx(r"ignor|pomijan|nie zostan|nie będ\w+ załadowan")),
                ("podane źródło (wiki)", rx(r"community\.bistudio|wiki|Scripting[:_ ]+_?Conventions|Scripting[ _]Modding|Scripting[ _]Example|Conventions")),
                ("SCR_ to prefiks gry, mod ma własny tag", rx(r"SCR_[^\n]{0,120}(Bohemia|\bBI\b|zarezerwowan|gr[ęay]\b|wbudowan|własn\w+\s+tag|nie\s+używ)")),
            ],
            "bad": [
                ("zaleca prefiks SCR_ dla modów", rx(r"(prefiks\w*|zaczyna\w*\s+od|użyj\w*)\s+[^\n]{0,20}SCR_")),
                ("przykłady z prefiksem SCR_ (prefiks gry) bez zastrzeżenia",
                 lambda t: bool(re.search(r"(np\.|e\.g\.|przykład\w*)[^\n]{0,40}`?SCR_|class\s+SCR_\w+|SCR_(MyObject|Example\w*)", t, I))
                 and not re.search(r"SCR_[^\n]{0,120}(Bohemi|\bBI\b|zarezerwowan|należy do gry|prefiks gry|nie\s+używ|wbudowan|w\s+gr[ęy]\b|gry\b)", t, I)),
                ("folder scripts/Game jako jedyny / wymyślona ścieżka Mods/<...>/",
                 rx(r"jedynym katalogiem|Mods/<|wszystkie[^\n]{0,50}(?:muszą|powinny)\s+(?:się\s+)?znajdować\s+się[^\n]{0,30}scripts/Game/?[`\s.]|poza\s+tą\s+ścieżką\s+nie\s+zostan")),
            ],
        }],
    },
]


def norm(text: str) -> str:
    return " ".join(text.split())


def match_test(first_question: str):
    q = norm(first_question)
    for test in TESTS:
        if q.startswith(norm(test["turns"][0])[:80]):
            return test
    return None


def cmd_questions() -> None:
    print("Każdy test = NOWA rozmowa. Test A ma dwa pytania w tej samej rozmowie (najpierw 1., potem 2.).")
    print("Kolejność dowolna. Po serii wpisz: python reforger_eval.py score\n")
    for test in TESTS:
        print("=" * 78)
        print(f"TEST {test['id']}: {test['name']}")
        for i, q in enumerate(test["turns"], 1):
            label = f"pytanie {i}/{len(test['turns'])}" if len(test["turns"]) > 1 else "pytanie"
            print(f"--- {label} ---")
            print(q)
        print()


def evaluate_answer(text: str, rules: dict) -> dict:
    must = [(label, bool(fn(text))) for label, fn in rules["must"]]
    bad = [label for label, fn in list(rules["bad"]) + COMMON_BAD if fn(text)]
    return {"must": must, "bad": bad}


def cmd_score(path: Path, md_path: Path | None) -> None:
    if not path.exists():
        sys.exit(f"Nie znaleziono pliku: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    sessions = data.get("sessions", [])
    runs: dict[str, list[dict]] = defaultdict(list)
    ignored = 0
    for s in sessions:
        turns = s.get("turns", [])
        users = [t for t in turns if t.get("role") == "user"]
        if not users:
            continue
        test = match_test(users[0]["content"])
        if not test:
            ignored += 1
            continue
        answers = []
        for q in test["turns"]:
            key = norm(q)[:80]
            found = None
            for idx, t in enumerate(turns):
                if t.get("role") == "user" and norm(t["content"]).startswith(key):
                    nxt = turns[idx + 1] if idx + 1 < len(turns) else None
                    found = nxt if nxt and nxt.get("role") == "assistant" else None
            answers.append(found)   # None = to pytanie nie zostało zadane / nie ma odpowiedzi
        traces = s.get("traces", [])
        repeated = len(users) - len(test["turns"])
        run = {"session": s.get("id", "?")[:8], "created": s.get("created_at", ""),
               "calls": len(traces), "errors": sum(1 for t in traces if t.get("status") == "error"),
               "turn_results": [], "answered_turns": sum(1 for a in answers if a), "expected_turns": len(test["turns"]),
               "extra_questions": max(0, repeated)}
        for i, rules in enumerate(test["rules"]):
            if i < len(answers) and answers[i] is not None:
                text = answers[i]["content"]
                res = evaluate_answer(text, rules)
                res["no_guess"] = bool(re.search(r"Nie zgaduj|nie wykonał w tej turze|Nie udało się zebrać", text))
                run["turn_results"].append(res)
            else:
                run["turn_results"].append(None)
        runs[test["id"]].append(run)

    lines: list[str] = []
    out = lines.append
    out("# Wyniki zestawu testowego\n")
    out(f"Plik: `{path}`; rozmów dopasowanych do testów: {sum(len(v) for v in runs.values())}, pominiętych: {ignored}\n")
    summary_rows = []
    for test in TESTS:
        tid = test["id"]
        if tid not in runs:
            out(f"## Test {tid}: {test['name']}\n_brak uruchomień_\n")
            summary_rows.append((tid, test["name"], 0, None, None))
            continue
        out(f"## Test {tid}: {test['name']}\n")
        pct_all, bad_all = [], []
        for n, run in enumerate(sorted(runs[tid], key=lambda r: r["created"]), 1):
            extra = f", dodatkowych/powtórzonych pytań w rozmowie: {run['extra_questions']}" if run["extra_questions"] else ""
            out(f"**Uruchomienie {n}** (sesja {run['session']}, wywołań MCP w śladzie: {run['calls']}, błędów: {run['errors']}{extra})\n")
            for ti, res in enumerate(run["turn_results"], 1):
                if res is None:
                    out(f"- tura {ti}: brak odpowiedzi\n")
                    continue
                hit = sum(1 for _, ok in res["must"] if ok)
                tot = len(res["must"])
                pct_all.append(100 * hit / tot)
                bad_all.append(len(res["bad"]))
                missing = [label for label, ok in res["must"] if not ok]
                prefix = f"tura {ti}: " if len(test["turns"]) > 1 else ""
                out(f"- {prefix}wymagane {hit}/{tot}" + (f"; brakuje: {'; '.join(missing)}" if missing else ""))
                out(f"- {prefix}błędy znane: {len(res['bad'])}" + (f" -> {'; '.join(res['bad'])}" if res["bad"] else ""))
                if res.get("no_guess"):
                    out(f"- {prefix}UWAGA: to komunikat awaryjny ('nie zgaduję'), nie odpowiedź merytoryczna")
            out("")
        summary_rows.append((tid, test["name"], len(runs[tid]),
                             sum(pct_all) / len(pct_all) if pct_all else None,
                             sum(bad_all) / len(bad_all) if bad_all else None))
    out("## Podsumowanie\n")
    out("| Test | Nazwa | Uruchomień | Średnio wymaganych | Średnio błędów znanych |")
    out("|---|---|---|---|---|")
    for tid, name, n, pct, bad in summary_rows:
        out(f"| {tid} | {name} | {n} | {'-' if pct is None else f'{pct:.0f}%'} | {'-' if bad is None else f'{bad:.1f}'} |")
    text = "\n".join(lines)
    print(text)
    if md_path:
        md_path.write_text(text, encoding="utf-8")
        print(f"\n(zapisano: {md_path})")


# ---------------------------------------------------------------------------------------------
# LOG
# ---------------------------------------------------------------------------------------------
def read_log(path: Path) -> str:
    raw = path.read_bytes()
    if raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return raw.decode("utf-16", errors="replace")
    for enc in ("utf-8", "cp1250", "cp852"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


TS = re.compile(r"\[\d+/\w+/\d{4} (\d\d):(\d\d):(\d\d)\]")


def seconds(line: str):
    m = TS.search(line)
    return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + int(m.group(3)) if m else None


def cmd_log(path: Path) -> None:
    if not path.exists():
        sys.exit(f"Nie znaleziono pliku: {path}")
    text = read_log(path).replace("\r", "")
    segments: list[list[str]] = []
    for line in text.split("\n"):
        if re.search(r'"POST /api/sessions/[0-9a-f]+/chat ', line):
            segments.append([line])
        elif segments:
            segments[-1].append(line)
    if not segments:
        print("Nie znaleziono żadnej tury czatu (brak linii POST .../chat).")
        return
    cfg = re.findall(r"\[CONFIG\][^\n]*", text)
    if cfg:
        print(cfg[-1].strip())
    print(f"Tur czatu w logu: {len(segments)}\n")
    for i, seg in enumerate(segments, 1):
        start = seconds(seg[0])
        polls = sorted(seconds(l) for l in seg if "GET /api/sessions/" in l and seconds(l) is not None)
        duration = None
        if start is not None:
            # Przeglądarka odpytuje serwer co ~1 s, dopóki tura trwa. Koniec = koniec pierwszej
            # ciągłej serii zapytań (przerwa > 3 s to już ruch po zakończeniu tury).
            end = start
            for t in polls:
                if t - end <= 3:
                    end = max(end, t)
                else:
                    break
            duration = end - start
        body = "\n".join(seg)
        calls = len(re.findall(r"\[MCP \d+/\d+\]", body))
        errors = len(re.findall(r"-> B\S{1,3}D", body))
        ctx = [int(x) for x in re.findall(r"context_tokens=(\d+)", body)]
        outs = re.findall(r"reason=(\w+) context_tokens=\d+ output_tokens=(\d+)", body)
        flags = {
            "REPAIR": len(re.findall(r"\[REPAIR\]", body)),
            "VIEW (z pamięci)": len(re.findall(r"\[VIEW\]", body)),
            "VERIFY uwagi": len(re.findall(r"\[VERIFY\] UWAGI", body)),
            "DUP": len(re.findall(r"\[DUP\]", body)),
            "STALL": len(re.findall(r"\[STALL\]", body)),
            "pusta odpowiedź": len(re.findall(r"Pusta odpowied", body)),
            "UWAGA kontekst": len(re.findall(r"\[UWAGA\]", body)),
            "synteza awaryjna": len(re.findall(r"Zatrzymano dalsze|Limit MCP|osobna synteza z dowodow", body)),
            "ponowienie po pustej generacji": len(re.findall(r"ponowienie z niskim", body)),
            "limit generacji (reason=length)": len(re.findall(r"reason=length", body)),
        }
        last = outs[-1] if outs else ("?", "?")
        print(f"Tura {i}: wywołań MCP {calls}, błędów {errors}, "
              f"czas {duration if duration is not None else '?'} s, "
              f"kontekst start {ctx[0] if ctx else '?'} / szczyt {max(ctx) if ctx else '?'}, "
              f"odpowiedź końcowa: {last[1]} tokenów (reason={last[0]})")
        raised = {k: v for k, v in flags.items() if v}
        print("   zdarzenia: " + (", ".join(f"{k}={v}" for k, v in raised.items()) if raised else "brak"))
        for item in re.findall(r"\[VERIFY\]   - ([^\n]+)", body):
            print("   weryfikator: " + item.strip()[:240])
        if calls == 0:
            print("   UWAGA: tura bez żadnego wywołania MCP (odpowiedź z historii/pamięci modelu)")
        print()


def main(argv: list[str]) -> None:
    if len(argv) < 2 or argv[1] not in ("questions", "score", "log"):
        print(__doc__)
        return
    if argv[1] == "questions":
        cmd_questions()
    elif argv[1] == "score":
        args = argv[2:]
        md = None
        if "--md" in args:
            k = args.index("--md")
            md = Path(args[k + 1]) if k + 1 < len(args) else Path("wyniki.md")
            del args[k:k + 2]
        path = Path(args[0]) if args else Path("assistant_web_data") / "conversations.json"
        cmd_score(path, md)
    else:
        if len(argv) < 3:
            sys.exit("Użycie: python reforger_eval.py log log.txt")
        cmd_log(Path(argv[2]))


if __name__ == "__main__":
    main(sys.argv)
