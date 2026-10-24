# Reforger Assistant WEB

Lokalny asystent dla modderów **Arma Reforger**. Odpowiada na pytania o skrypty, API i prefaby gry, korzystając z prawdziwych plików gry i biki, a nie z pamięci modelu. Działa w całości na Twoim komputerze: model uruchamia Ollama, a pliki gry czyta serwer **Enfusion MCP BK**.

> 
*Odpowiedzi modelu wymagają weryfikacji przed użyciem w modzie.*
* Asystent cytuje kod z plików gry i pokazuje, z których narzędzi korzystał, ale model nadal może się mylić (patrz [Ograniczenia](#ograniczenia)).

```text
Przeglądarka  <->  lokalny serwer (Python)  <->  silnik  <->  model (Ollama)  <->  ustawienia
  assistant.html     reforger_assistant_WEB.py     reforger_assistant_MCP_BK.py     reforger_config.py
                                                      |
                                             reforger_assistant_MCP_BK
                                                      |
                                                      +-->  Enfusion MCP BK (Node)  <->  pliki gry, wiki
```

## Wymagania

|**Wymaganie**|**Uwagi**|
|-|-|
|Windows|Używane i testowane na Windows; launchery `.cmd` są tylko dla Windows|
|Python 3.10 lub nowszy|Tylko biblioteka standardowa, **nie trzeba nic instalować przez pip** (testowane na 3.12)|
|Node.js w `PATH`|Uruchamia serwer MCP (`node dist/index.js`)|
|Enfusion MCP BK|Zbudowany serwer MCP, plik `dist/index.js` -> https:/github.com/steffenbk/enfusion-mcp-BK|
|Ollama + model z obsługą narzędzi|Testowano na `gpt-oss:20b`|
|Arma Reforger|Zainstalowana gra (potrzebna ścieżka do jej folderu)|

Przykladowy testowany sprzet: RTX 4070 Ti Super 16 GB. Model `gpt-oss:20b` z kontekstem 32k (zajmuje około 12 GB VRAM i działa w całości na GPU)

## Szybki start

1. Skopiuj wszystkie pliki asystenta do jednego folderu (lista w sekcji [Pliki](#pliki)).
2. **Ustaw ścieżki.** Domyślne wartości wskazują (`C:\enfusion-mcp-BK\dist\index.js` i `C:\Program Files\Steam\steamapps\common\Arma Reforger`)
W `reforger_config.py`, dopisz własne po linii z wersja aplikacji `VERSION = "1.8.X""`:

```bat
   set "ENFUSION_MCP_SCRIPT=C:\ścieżka\do\enfusion-mcp-BK\dist\index.js"
   set "ENFUSION_GAME_PATH=C:\Program Files\Steam\steamapps\common\Arma Reforger"
   ```

W PowerShellu to samo robisz poleceniami `$env:ENFUSION_MCP_SCRIPT = "..."` i `$env:ENFUSION_GAME_PATH = "..."`.

3. Upewnij się, że Ollama działa i model jest pobrany:

```bat
   ollama pull gpt-oss:20b
   ```

4. Uruchom `START_ASSISTANT_WEB.cmd` (dwuklik) albo w PowerShellu:

```powershell
   python .\reforger_assistant_WEB.py
   ```

5. Przeglądarka otworzy się sama pod adresem [http:/127.0.0.1:8765](http:/127.0.0.1:8765). Zamknięcie okna konsoli (albo Ctrl+C) zatrzymuje serwer.

`START_ASSISTANT_WEB_LOG.cmd` działa tak samo, ale zapisuje log do pliku `logs\log_RRRRMMDD_GGMMSS.txt` (UTF-8), a okno konsoli zostaje puste. Podgląd na żywo w drugim oknie PowerShella: `Get-Content .logs\NAZWA.txt -Wait`. Oba launchery ustawiają UTF-8, więc polskie znaki w konsoli i w logu nie rozsypują się.

## Interfejs

* **Lewy panel:** historia rozmów, wyszukiwanie, przycisk „Nowa rozmowa”, na dole stan połączenia z serwerem MCP
* **Góra:** przyciski **model** i **kontekst** (wybór z listy), obok znacznika `LOCAL ONLY`.

  * Lista modeli pochodzi z Ollamy. Modele bez obsługi narzędzi są wyłączone, a modele tylko do osadzeń ukryte.
  * Kontekst: presety 32k, 48k, 64k, 96k, 128k lub własna wartość od 32 768 do 262 144. Minimum wynika z limitów wyników narzędzi, które są dobrane do 32 768 tokenów.
  * Zmiana obowiązuje od następnego pytania i zapisuje się w `assistant_web_data\settings.json`.
* **Góra, dalej:** przycisk **ścieżki** (BK, gra, dokumentacja; działają od ponownego uruchomienia) i **język** (PL/EN; interfejs od razu, asystent od ponownego uruchomienia, patrz [Język odpowiedzi](#język-odpowiedzi-od-200--answer-language)). Na węższych ekranach przyciski pokazują same wartości.
* **Prawy panel „Aktywność MCP”:** każde wywołanie narzędzia (nazwa, argumenty, status, czas), tylko do podglądu.
* **Odpowiedzi:** tabele, listy, linie poziome i bloki kodu z przyciskiem „Kopiuj”.

## Opcje uruchamiania

```powershell
python .reforger_assistant_WEB.py --port 8766
python .reforger_assistant_WEB.py --no-browser
python .reforger_assistant_WEB.py --model gpt-oss:20b --num-ctx 32768
```

|**Opcja**|**Domyślnie**|**Opis**|
|-|-|-|
|`--port`|`8765`|Port serwera lokalnego|
|`--no-browser`|wyłączone|Nie otwieraj przeglądarki automatycznie|
|`--model`|z ustawień|Model Ollamy tylko na tę sesję (nie nadpisuje pliku ustawień)|
|`--num-ctx`|z ustawień|Rozmiar kontekstu tylko na tę sesję|

Pierwszeństwo ustawień modelu i kontekstu: **argument wiersza poleceń > zapisane w interfejsie (`settings.json`) > zmienne środowiskowe i wartości domyślne**.

## Język odpowiedzi (od 2.0.0) / Answer language

Asystent działa po polsku (domyślnie) albo po angielsku. Język obejmuje interfejs w przeglądarce i wszystko po stronie silnika: prompt systemowy, podpowiedzi i komunikaty dla modelu, kontrole odpowiedzi (weryfikator cytatów, kontrola API i składni, oznaczenia `⚠` w treści, stopki), log w konsoli i zestaw testowy.

Język zmieniasz przyciskiem **język** na górnym pasku (od 2.0.1). Interfejs przełącza się od razu, a silnik po ponownym uruchomieniu asystenta (teksty dla modelu są ustawiane przy starcie); do tego czasu menu pokazuje, w jakim języku asystent nadal odpowiada. Wybór zapisuje się jako `"lang"` w `assistant_web_data\settings.json`.

Zmienna środowiskowa `REFORGER_LANG=en` (albo `pl`) ma pierwszeństwo: ustawiona w launcherze (`set "REFORGER_LANG=en"`) albo w PowerShellu (`$env:REFORGER_LANG = "en"`) blokuje przycisk w interfejsie. Kontrole rozumieją oba języki, więc stara rozmowa po polsku nie psuje się po przełączeniu. Język silnika widać w linii `[CONFIG]` (`jezyk=` / `language=`).

*The assistant works in Polish (default) or English: the browser UI, system prompt, model hints, all answer checks, the console log and the test set. Use the **language** button in the top bar: the UI switches immediately, the engine after a restart. `REFORGER_LANG=en` in the launcher overrides the button.*

## Konfiguracja (zmienne środowiskowe)

Ustawiasz je w launcherze (`set "NAZWA=wartość"`) albo w PowerShellu (`$env:NAZWA = "wartość"`). Przy starcie silnik wypisuje w konsoli linię `[CONFIG]` z aktualnymi wartościami.

### Ścieżki i połączenia

Od 1.9.0 ścieżki do BK, gry i dokumentacji ustawisz w interfejsie: przycisk **ścieżki** na górnym pasku. „Sprawdź” pokazuje przy każdym polu, czy plik albo folder istnieje (dla BK także, czy jest Node.js). „Zapisz” zapisuje je w `assistant_web_data\settings.json`. **Nowe ścieżki działają od ponownego uruchomienia asystenta.** Jeśli przy starcie BK się nie uruchomi (np. zła ścieżka), asystent nie kończy pracy, tylko startuje w trybie konfiguracji i od razu pokazuje formularz ścieżek. Pierwszeństwo: zmienna środowiskowa > ustawienia z interfejsu > wartość domyślna; ścieżka narzucona zmienną jest w interfejsie tylko do podglądu. Przy starcie w logu: `[ŚCIEŻKI]` z aktualnymi ścieżkami i ich źródłem.

|**Zmienna**|**Domyślnie**|**Opis**|
|-|-|-|
|`ENFUSION_MCP_SCRIPT`|ścieżka autora|Plik `dist/index.js` serwera Enfusion MCP BK|
|`ENFUSION_GAME_PATH`|ścieżka autora|Folder zainstalowanej gry|
|`REFORGER_LANG`|`pl`|Język silnika: `pl` albo `en` (patrz [Język odpowiedzi](#język-odpowiedzi-od-200--answer-language))|
|`REFORGER_DOCS_PATH`|obok gry: `Arma Reforger Tools\Workbench\docs`|Folder `docs` dokumentacji API z Arma Reforger Tools (hierarchia klas). Zwykle nie trzeba ustawiać: asystent szuka go w tym samym `steamapps\common` co gra|
|`OLLAMA_CHAT_URL`|`http:/127.0.0.1:11434/api/chat`|Adres Ollamy|
|`OLLAMA_MODEL`|`gpt-oss:20b`|Model domyślny (nadpisywany przez `settings.json` i `--model`)|

### Model

|**Zmienna**|**Domyślnie**|**Opis**|
|-|-|-|
|`OLLAMA_NUM_CTX`|`32768`|Rozmiar kontekstu (nadpisywany przez `settings.json` i `--num-ctx`)|
|`OLLAMA_NUM_PREDICT`|`16384`|Maksimum tokenów jednej generacji, wliczając rozumowanie; `0` lub `-1` = bez limitu|
|`OLLAMA_TEMPERATURE`|`0.1`|Temperatura|
|`OLLAMA_THINK`|puste|Poziom rozumowania: `low`, `medium`, `high`; puste = nie wysyłaj|
|`OLLAMA_TIMEOUT`|`300`|Limit czasu odpowiedzi Ollamy (sekundy)|
|`REFORGER_THINKING_CHARS`|`3000`|Ile końcówki rozumowania zostaje w kontekście w obrębie tury; `0` = nic, `-1` = całość|
|`REFORGER_STREAM`|`on`|Odbieranie odpowiedzi Ollamy na bieżąco; `off` = stary tryb (cała odpowiedź naraz, bez przerywania rozumowania)|
|`REFORGER_THINK_ABORT`|`8000`|Po ilu tokenach samego rozumowania (bez tekstu odpowiedzi) silnik przerywa generację i ponawia ją z niskim rozumowaniem; `0` = nie przerywaj|

### Narzędzia i limity

|**Zmienna**|**Domyślnie**|**Opis**|
|-|-|-|
|`REFORGER_MCP_TIMEOUT`|`90`|Limit czasu uruchomienia i wywołań MCP (sekundy)|
|`REFORGER_MAX_TOOL_CALLS`|`25`|Maksimum wywołań narzędzi na jedno pytanie|
|`REFORGER_MAX_TOOL_RESULT_CHARS`|`14000`|Maksymalny rozmiar jednego wyniku narzędzia w kontekście|
|`REFORGER_MAX_TOOL_CONTEXT_CHARS`|`45000`|Łączny rozmiar wyników narzędzi w jednej turze|
|`REFORGER_SOFT_LIMIT_CLASS` / `REFORGER_SOFT_LIMIT_OTHER`|`5` / `10`|Limit wyników `api_search` dla klas / dla pozostałych typów|
|`REFORGER_VIEW_LIMIT`|`6`|Maksimum lokalnych widoków (wyszukiwanie lub zakres linii) jednego pliku w turze|
|`REFORGER_MAX_HISTORY_MESSAGES`|`60`|Ile ostatnich wiadomości trafia do kontekstu|
|`REFORGER_KB_CHECK`|'on'|Wiedza przed kodem: przy własnym kodzie silnik pobiera wzorce z bazy BK i daje modelowi jedną rundę na porównanie (on/off)|

**Zaawansowane (zwykle bez zmian):** `REFORGER_FINISHED_SOURCE_CHARS` (`3600`), `REFORGER_FINISHED_EVIDENCE_CHARS` (`20000`), `REFORGER_COMPACT_SEARCH_CHARS` (`1200`), `REFORGER_COMPACT_OLD_CHARS` (`3600`). Sterują tym, ile odczytanych źródeł zostaje w kontekście po zakończeniu tury i jak są skracane starsze wyniki, gdy kontekst się zapełnia.

### Weryfikacja i odpowiedzi awaryjne

|**Zmienna**|**Domyślnie**|**Opis**|
|-|-|-|
|`REFORGER_VERIFY`|`fix`|Weryfikator cytatów: `off`, `log` (tylko wpisy w logu), `footer` (dodatkowo znacznik pod odpowiedzią) albo `fix` (runda poprawkowa, a uwagi, które zostały, pod odpowiedzią)|
|`REFORGER_EMERGENCY_IN_HISTORY`|`placeholder`|`placeholder`: w kontekście modelu zostaje krótki znacznik zamiast treści odpowiedzi awaryjnej; `keep`: pełna treść|
|`REFORGER_API_CHECK`<br />|`fix`|Kontrola nazw API w kodzie: fix (runda poprawkowa i ostrzeżenie), log (tylko wpis w logu), off|

## Narzędzia asystenta

Do modelu trafia wyłącznie osiem narzędzi **tylko do odczytu** z listy dozwolonych, niezależnie od tego, co udostępnia serwer MCP:

|**Narzędzie**|**Do czego służy**|
|-|-|
|`asset_search`|Szukanie plików i zasobów gry po nazwie|
|`game_browse`|Przeglądanie katalogów gry (`pattern` to **tylko filtr rozszerzenia**, np. `*.c`; pliki po fragmencie nazwy szuka `asset_search`)|
|`game_read`|Odczyt pliku z gry; asystent potrafi też lokalnie przeszukiwać odczytany plik i pokazywać zakres linii bez ponownego wywołania MCP|
|`api_search`|Szukanie klas, metod i właściwości w API skryptów|
|`component_search`|Szukanie komponentów (`ScriptComponent`)|
|`wiki_search`, `wiki_read`|Wyszukiwanie i odczyt stron wiki|
|`wb_knowledge`|Baza wiedzy modderskiej (wzorce i konwencje)|

## Jak asystent dba o wiarygodność

* Poprawia typowe błędy wywołań narzędzi i wykrywa powtórzenia oraz pętle bez nowych danych.
* Skraca długie wyniki tak, żeby zachować wszystkie deklaracje (nie ucina listy metod w połowie).
* Oznacza wyniki wyszukiwania pierwszym wierszem `[Dokładne trafienie ...]` albo `[BRAK DOKŁADNEGO TRAFIENIA ...]`, żeby model nie traktował podobnej nazwy jako dowodu istnienia. Wyjątek: funkcje globalne (`GetGame`, `Print`, `PrintFormat`), których `api_search` nie indeksuje, dostają osobną notatkę, że brak trafienia nie znaczy „nie istnieje”.
* Uzupełnia hierarchię klas. Dane API w BK mają dla wielu klas błędną hierarchię: brak klasy bazowej (np. `ArmaReforgerScripted`, `ChimeraWorld`) albo przodków wpisanych jako „Direct subclasses” (np. `SCR_ToggleSafetyUserAction`). Od 1.8.8 silnik czyta prawdziwe drzewo dziedziczenia z lokalnej dokumentacji API dołączonej do Arma Reforger Tools (`Workbench\docs\ArmaReforgerScriptAPIPublic\html\hierarchy.html` i `Workbench\docs\EnfusionScriptAPI\html\hierarchy.html`; tylko odczyt z dysku, bez internetu). Gdy model szuka dokładnej nazwy klasy, a BK podaje inną klasę bazową albo błędne podklasy, silnik dopisuje do wyniku prawdziwy łańcuch, podklasy i nazwy metod klas bazowych. Bez Arma Reforger Tools silnik czyta deklarację `class X : Y` z pliku gry, jak wcześniej. Przy starcie w logu: `[DOKUMENTACJA]`, przy klasie: `[BAZA]`. Wywołania silnika nie wliczają się do limitu modelu.
* Wpis `.et`, którego klasa różni się od nowej klasy w skrypcie tej samej odpowiedzi tylko tagiem (np. `SCR_X` we wpisie, `TAG_X` w skrypcie), silnik ujednolica sam (`[AUTOPOPRAWKA]`). Blok podpisany plikiem gry, którego asystent nie odczytał, jest oznaczony w treści.
* Seria rund bez nowych danych kończy wyszukiwanie dopiero po wykorzystaniu części limitu wywołań (od 1.8.9: 8 wywołań MCP) albo po 6 takich rundach; wcześniej model bywał zatrzymywany po 4 wywołaniach.
* Gdy `api_search` nie zna nazwy (np. enumu `LogLevel`), a w grze jest plik o dokładnie takiej nazwie, silnik dopisuje jego ścieżkę, żeby model nie uznał, że takiej rzeczy nie ma. W logu: `[PLIK]`.
* Kontrola nazw API sama pobiera pełny widok klasy i jej przodków, zanim zgłosi nazwę jako niepotwierdzoną. Sprawdza też deklaracje: klasę bazową w `class X : Y`, klasę w `modded class X` i metody oznaczone `override`.
* Gdy model zapyta `api_search` o dokładną nazwę klasy, dostaje pełny widok klasy (wszystkie metody), a nie skrót z 10 metod. Długie wyniki są skracane bez gubienia sygnatur.
* Odrzuca od razu, bez zużywania limitu, wywołania, które z definicji nic nie dadzą: `game_browse` z `pattern` innym niż rozszerzenie i `asset_search` z fragmentem kodu w zapytaniu.
* Kod opisany jako „z gry”, którego nie ma w odczytanym pliku, i numery linii, których model nie widział w żadnym widoku pliku, uruchamiają rundę poprawkową (tryb `REFORGER_VERIFY=fix`).
* Pliki gry o nazwach wymienionych w pytaniu (np. `Weapon_Base`, `SCR_ToggleSafetyUserAction`) silnik wyszukuje od razu i podaje modelowi ścieżki (tylko dokładne nazwy plików). W logu: `[PYTANIE]`.
* Numery linii są przypisywane do pliku, o którym mowa w zdaniu lub wierszu tabeli: numer widziany w widoku innego pliku nie potwierdza odwołania. Logi `[MCP]` pokazują parametry widoku (`+ widok linie 200-400`).
* W kodzie własnej klasy wywołania bez obiektu (np. `GetEntity()` w komponencie) muszą istnieć w klasie bazowej lub jej przodkach; `GetComponent<T>()` jest zgłaszane jako składnia, której Enforce Script nie ma.
* Numery linii sprawdzane są także w kolumnach tabel (nagłówek „Linia/Linie”). W logu `[LINIE]` widać, ile odwołań do linii ma odpowiedź i ile numerów model faktycznie widział w widokach pliku. Kontrola cytatów obejmuje też odpowiedzi napisane po przerwaniu wyszukiwania.
* Wartości enumów w kodzie (np. `LogLevel.INFO`) są sprawdzane, gdy enum jest w odczytanych plikach albo wynikach `api_search`.
* Dla funkcji globalnych (`Print`, `PrintFormat`, `GetGame`) `api_search` nie pokazuje mylących metod klas testowych o tej samej nazwie, tylko notatkę i listę takich klas. Od 1.9.2 przy `Print` i `PrintFormat` silnik dopisuje dosłowną deklarację z pliku gry `EnDebug.c` (ścieżkę ustala sam; w logu `[GLOBALNA]`), bo BK nie przeszukuje treści plików i model nie miał jak jej znaleźć.
* Wymyślone narzędzia „szukaj w treści plików” (np. `game_search`): ze ścieżką do pliku zamieniane na `game_read` z `query`, bez ścieżki odrzucane z podpowiedzią.
* Rundy poprawkowe (kontrola API, cytaty, wiedza przed kodem): model widzi swój odrzucony szkic. Od 1.9.1 podpowiedź z wzorcami z bazy wiedzy przypomina pytanie użytkownika (model nie odpowiada wtedy na samą podpowiedź), a deklaracje klas, których nie potwierdza API, są oznaczone w treści przy bloku kodu. Jeśli poprawka ma więcej problemów niż pierwszy szkic, zostaje pierwszy szkic. W logu: `[SZKIC]`.
* Przy pustej generacji po użyciu narzędzi ponawia próbę z niskim poziomem rozumowania, w tej samej rozmowie. Od 1.8.7 rozumowanie, które przekroczy `REFORGER_THINK_ABORT` tokenów bez tekstu odpowiedzi, jest przerywane od razu (wcześniej model potrafił „myśleć” do limitu 16 384 tokenów, ok. 2-3 minuty). W logu: `rozumowanie przerwane`.
* Rozumowanie modelu, które trafi do treści odpowiedzi (np. „We need to answer...”), jest usuwane (`[ROZUMOWANIE]`), a zapętlone, powtarzane wiersze tabel i tekstu skracane (`[POWTÓRZENIA]`).
* Problemy, które przetrwały rundę poprawek, są oznaczone **w treści** odpowiedzi, a nie tylko w stopce: blok podpisany plikiem gry, którego linii nie ma w pliku, blok z niedozwoloną składnią (`> ⚠ Uwaga silnika: ...`) i numer linii spoza widoków pliku (od 1.9.4 krótkie `⚠` przy numerze; wyjaśnienie w stopce). W logu: `[OZNACZENIA]`.
* Kontrola kodu sprawdza też: typ zwracany przy przypisaniu (np. `ResourceName x = ...GetPrefab()`, gdy `GetPrefab()` zwraca `BaseContainer`), nową klasę moda z prefiksem `SCR_` (to prefiks klas gry) i zalecanie `SCR_` jako tagu moda, wpis prefabu `.et` zapisany jako JSON oraz wartości enumów także w kodzie w tabelach i w tekście. Odpowiedź napisana po przerwaniu wyszukiwania przechodzi te same kontrole (jedna poprawka bez narzędzi).
* Prompt wymaga odróżniania faktów zweryfikowanych od założeń, oznaczania kodu jako „z kodu gry” tylko wtedy, gdy jest przepisany dosłownie z odczytu pliku, oraz opisania, co jeszcze trzeba przetestować w grze.

### Odpowiedzi awaryjne

Gdy wyszukiwanie zostaje przerwane (limit wywołań MCP albo seria rund bez nowych danych), model pisze odpowiedź **w tej samej rozmowie**, ze wszystkimi zebranymi wynikami, tylko bez dalszych narzędzi. Taka odpowiedź ma stopkę `_[Wyszukiwanie przerwane (...); odpowiedź na podstawie zebranych wyników, może być niepełna.]_`. W logu: `[KONIEC]`.

Dopiero gdy model dwa razy nie odda kompletnego tekstu, silnik składa odpowiedź awaryjną z wybranych wyników (najpierw odczyty plików i dokładne trafienia). Ma ona stopkę `_[Podsumowanie dostępnych wyników MCP: ...]_`. Traktuj ją jako niepełną. W kontekście kolejnych pytań taka odpowiedź jest zastępowana krótkim znacznikiem, żeby jej błędy nie wracały jako fakty.

### Weryfikator cytatów

Weryfikator sprawdza każdy blok kodu przypisany w odpowiedzi do pliku gry: czy jego linie (z pominięciem białych znaków i komentarzy) występują w tym pliku, który asystent odczytał w tej rozmowie. Zgłasza też sprzeczność w klasie bazowej (np. „`X` dziedziczy po `Y`”) oraz powołanie się na plik, którego nie odczytano. Uwagi widać w logu jako wpisy `[VERIFY]`. Przykładowe ścieżki i kod własny modelu (oznaczony jako szkic lub przykład) są pomijane.

Weryfikator **nie** sprawdza wszystkiego: nie oceni np. opisu działania kodu w prozie ani źródeł podanych w tabelach (np. „metoda X pochodzi z pliku Y”).

## Dane lokalne i prywatność

* `assistant_web_data\conversations.json`: historia czatu i metadane wywołań MCP (nazwa narzędzia, argumenty, status, czas). **Nie zapisujemy wyników narzędzi** (np. treści plików gry). Odpowiedzi asystenta zostają w historii, także gdy zawierają przytoczone fragmenty kodu gry, więc pamiętaj o licencji gry, jeśli publikujesz rozmowy.
* `assistant_web_data\settings.json`: wybrany model i rozmiar kontekstu.
* Pełne teksty odczytanych plików są przechowywane **tylko w pamięci procesu** (dla weryfikatora i widoków lokalnych) do zamknięcia serwera.
* Logi z `START_ASSISTANT_WEB_LOG.cmd` (`logs`) zawierają nazwy narzędzi, argumenty wywołań, diagnostykę i krótkie fragmenty z uwag weryfikatora, bez treści plików.
* Usunięcie folderu `assistant_web_data` czyści historię i ustawienia.

## Bezpieczeństwo

* Serwer nasłuchuje wyłącznie na `127.0.0.1`. Nie ma uwierzytelniania, więc **nie wystawiaj go do sieci** (przekierowanie portu, odwrotne proxy).
* Żądania są sprawdzane: nagłówek `Host`, nagłówek `Origin`, dla POST wymagany `Content-Type: application/json` i `X-Assistant-UI: 1`, limit rozmiaru żądania (48 KB), ścisła polityka CSP strony.
* Asystent używa wyłącznie narzędzi odczytu z listy dozwolonych; nie zapisuje do plików gry ani nie uruchamia kodu z gry.
* Dostęp do zasobów gry ma serwer MCP BK (folder z `ENFUSION_GAME_PATH`).

## Testy jakości

`reforger_eval.py` zawiera zestaw 10 pytań i ocenę odpowiedzi według reguł (wymagane elementy, znane błędy). Pytania zadajesz sam w interfejsie, każde w osobnej rozmowie (test A ma dwa pytania w jednej rozmowie), a skrypt ocenia zapisaną historię.

```powershell
python reforger_eval.py questions                       # lista 10 pytań
python reforger_eval.py score                           # ocena assistant_web_data\conversations.json
python reforger_eval.py score ścieżka\do\pliku.json --md wyniki.md
python reforger_eval.py log log.txt                     # podsumowanie logu serwera tura po turze
```

Pytania i reguły są dobrane pod `gpt-oss:20b`. Od 2.0.0 każde pytanie ma wersję angielską: przy `REFORGER_LANG=en` polecenie `questions` wypisuje pytania po angielsku, a raport `score` i `log` jest po angielsku. Klucz odpowiedzi rozumie oba języki i rozpoznaje rozmowy z pytaniami polskimi i angielskimi. Ocena regułowa jest przybliżeniem: nie zastępuje przeczytania odpowiedzi.

## Ograniczenia

* Modele bywają w błędzie. Z naszych testów najczęstsze to wymyślone wartości (np. nieistniejące poziomy `LogLevel`), pomylenie lufy (`muzzle`) z magazynkiem, pomyłki w tym, co jest publiczne, a co prywatne, oraz kod prefabów z wymyślonymi nazwami kluczy lub identyfikatorami GUID.
* Asystent był dostrajany i testowany na `gpt-oss:20b`. Inne modele mogą działać inaczej.
* Czasem model wpada w bardzo długie rozumowanie (nawet kilkanaście tysięcy tokenów, czyli kilka minut - na razie Nie ma przycisku „Stop”.)
* Wersja angielska jest nowa (od 2.0.0) i mniej przetestowana niż polska.

## Rozwiązywanie problemów

|**Objaw**|**Co zrobić**|
|-|-|
|`Nie znaleziono serwera MCP: ...`|Popraw `ENFUSION_MCP_SCRIPT` (plik `dist/index.js` musi istnieć)|
|`Nie można uruchomić Node/Enfusion MCP`|Zainstaluj Node.js i upewnij się, że `node` jest w `PATH`|
|`Ollama nie odpowiada (...)`|Uruchom Ollamę albo popraw `OLLAMA_CHAT_URL`|
|Zmiana modelu: „nie obsługuje wywoływania narzędzi”|Wybierz model z obsługą narzędzi|
|Strona wygląda po staremu po podmianie plików|Odśwież z pominięciem pamięci podręcznej (Ctrl+F5)|
|Odpowiedź trwa bardzo długo, w logu `reason=length`|Rozumowanie zużyło limit generacji. Asystent ponawia próbę z niskim rozumowaniem. Możesz też ustawić `OLLAMA_THINK=low` albo zmniejszyć `OLLAMA_NUM_PREDICT`|
|Stopka `_[Wyszukiwanie przerwane ...]_` albo `_[Podsumowanie dostępnych wyników MCP: ...]_`|Wyszukiwanie przerwano, patrz [Odpowiedzi awaryjne](#odpowiedzi-awaryjne). Spróbuj zadać pytanie węziej|
|Port zajęty|Uruchom z innym portem: `--port 8766`|
|Polskie znaki rozsypane w konsoli lub logu|Uruchamiaj przez `START_ASSISTANT_WEB.cmd` (ustawia UTF-8)|

## Pliki

|Plik|Opis|
|-|-|
|`reforger_assistant_MCP_BK.py`|**Silnik:** rozmowa z Ollamą, klient MCP, zabezpieczenia i weryfikator|
|`reforger_helpers.py`|Zabezpieczenia dla modelu (naprawa wywołań narzędzi, skracanie wyników)|
|`reforger_assistant_WEB.py`|Lokalny serwer HTTP|
|`assistant.html`|Interfejs (HTML, CSS i JavaScript w jednym pliku, bez zewnętrznych bibliotek)|
|`reforger_eval.py`|Zestaw testowy i ocena odpowiedzi|
|`START_ASSISTANT_WEB.cmd`|Uruchamianie dwuklikiem|
|`START_ASSISTANT_WEB_LOG.cmd`|Uruchamianie z logiem do pliku w `logs`|
|`assistant_web_data`|Tworzony automatycznie: `conversations.json` i `settings.json`|
|`reforger_config.py`|Konfiguracja: wersja, ścieżki, limity, tryby|
|`reforger_prompts.py`|Teksty dla modelu: prompt systemowy, podpowiedzi, stopki|
|`reforger_prompts_en.py`|Te same teksty po angielsku (od 2.0.0); `python reforger_prompts_en.py` sprawdza zgodność nazw i pól z wersją polską|
|`reforger_i18n.py`|Wybór języka (`REFORGER_LANG` / `settings.json`) i funkcja `tr()` dla krótkich komunikatów (od 2.0.0)|
|`reforger_rules.py`|Reguły jako dane: narzędzia, wzorce, listy nazw|
|`reforger_checks.py`|Kontrole odpowiedzi: weryfikator cytatów, kontrola API|
|`reforger_mcp.py`|Klient Enfusion MCP|
|`reforger_docs.py`|Hierarchia klas z lokalnej dokumentacji API Workbencha (od 1.8.8)|
|`reforger_paths.py`|Ścieżki z interfejsu: zapis w `settings.json` i sprawdzanie plików (od 1.9.0)|

## Licencja i autor

Stworzone przez KUKA, na licencji MIT

(Enfusion MCP BK również na licencji MIT)



\---

