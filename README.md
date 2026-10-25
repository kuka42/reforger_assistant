# Reforger Assistant WEB

**[English](#english) · [Polski](#polski)**

---

<a id="english"></a>

## English

A local assistant for **Arma Reforger** modders. It answers questions about the game's scripts, API and prefabs using the real game files and the wiki, not the model's memory. Everything runs on your own computer: the model runs in Ollama, and the game files are read by the **Enfusion MCP BK** server.

> **Model answers need verification before you use them in a mod.** The assistant quotes code from the game files and shows which tools it used, but the model can still be wrong (see [Limitations](#limitations)).

```text
Browser  <->  local server (Python)  <->  engine  <->  model (Ollama)
assistant.html  reforger_assistant_WEB.py  reforger_assistant_MCP_BK.py
                                              |
                                              +-->  Enfusion MCP BK (Node)  <->  game files, wiki
```

The assistant works in **English or Polish** (switch in the interface, see [Language](#language)).

### Requirements

| Requirement | Notes |
|-|-|
| Windows | Used and tested on Windows; the `.cmd` launchers are Windows only |
| Python 3.10 or newer | Standard library only, **nothing to install with pip** (tested on 3.12) |
| Node.js in `PATH` | Runs the MCP server (`node dist/index.js`) |
| Enfusion MCP BK | A built MCP server, file `dist/index.js`: [github.com/steffenbk/enfusion-mcp-BK](https://github.com/steffenbk/enfusion-mcp-BK) |
| Ollama + a model with tool support | Tuned and tested on `gpt-oss:20b` |
| Arma Reforger | The installed game (you need the path to its folder) |
| Arma Reforger Tools (optional) | The local API documentation gives the assistant the correct class hierarchy |

Example tested hardware: RTX 4070 Ti Super 16 GB. `gpt-oss:20b` with a 32k context uses about 12 GB of VRAM and runs fully on the GPU.

### Quick start

1. Copy all assistant files into one folder (list in [Files](#files)).
2. Make sure Ollama is running and the model is downloaded:
   ```bat
   ollama pull gpt-oss:20b
   ```
3. Start `START_ASSISTANT_WEB.cmd` (double-click) or in PowerShell:
   ```powershell
   python .\reforger_assistant_WEB.py
   ```
4. The browser opens at [http://127.0.0.1:8765](http://127.0.0.1:8765).
5. **Set the paths:** the **paths** button in the top bar. Enter the `dist\index.js` file of Enfusion MCP BK and the game folder (e.g. `D:\SteamLibrary\steamapps\common\Arma Reforger`). The documentation folder is found automatically next to the game; you only need to enter it if Arma Reforger Tools is installed elsewhere. **Check** shows for each field whether the file or folder exists, **Save** stores the paths. **Restart the assistant** to use them.
6. Optionally switch the language: the **language** button.

If BK does not start (e.g. a wrong path), the assistant does not exit: it starts in setup mode and opens the paths form right away.

Closing the console window (or Ctrl+C) stops the server. `START_ASSISTANT_WEB_LOG.cmd` works the same way but writes the log to `logs\log_YYYYMMDD_HHMMSS.txt` (UTF-8). To follow it live in a second PowerShell window: `Get-Content .\logs\NAME.txt -Wait`.

### Interface

* **Left panel:** conversation history, search, **New conversation**, MCP connection status and version at the bottom.
* **Top bar:**
  * **model** – list of models installed in Ollama. Models without tool support are disabled, embedding-only models are hidden.
  * **context** – presets 32k–128k or a custom value from 32,768 to 262,144 (the minimum follows from the tool result limits).
  * **paths** – BK, game and documentation; applied after a restart.
  * **language** – PL/EN; the interface switches immediately, the assistant after a restart.
  * Model and context apply from the next question. All settings are saved in `assistant_web_data\settings.json`. On narrow screens the buttons show only their values.
* **Right panel "MCP activity":** every tool call (name, arguments, status, time), read-only preview.
* **Answers:** tables, lists and code blocks with a **Copy** button. Problems that survived the engine's fix round are marked in the text with `⚠`.

### Language

Polish (default) or English. The language covers the browser interface and the whole engine: system prompt, hints for the model, answer checks, the console log and the test set.

* Change it with the **language** button. The interface switches immediately; the engine switches after a restart (texts for the model are set at startup). Until then the menu shows which language the assistant still answers in.
* The choice is saved as `"lang"` in `assistant_web_data\settings.json`.
* The environment variable `REFORGER_LANG=en` (or `pl`) takes precedence and locks the button.
* The checks understand both languages, so an older conversation in the other language keeps working.

### Command-line options

```powershell
python .\reforger_assistant_WEB.py --port 8766
python .\reforger_assistant_WEB.py --no-browser
python .\reforger_assistant_WEB.py --model gpt-oss:20b --num-ctx 32768
```

| Option | Default | Description |
|-|-|-|
| `--port` | `8765` | Local server port |
| `--no-browser` | off | Do not open the browser automatically |
| `--model` | from settings | Ollama model for this session only (does not change the settings file) |
| `--num-ctx` | from settings | Context size for this session only |

Precedence for model and context: **command-line argument > saved in the interface (`settings.json`) > environment variables and defaults**.

### Configuration (environment variables)

Set them in the launcher (`set "NAME=value"`) or in PowerShell (`$env:NAME = "value"`). At startup the engine prints a `[CONFIG]` line with the current values. Most users only need the interface; the variables are for fine-tuning.

**Paths, connection, language** (precedence: variable > interface > default; a path set by a variable is shown read-only in the interface)

| Variable | Default | Description |
|-|-|-|
| `ENFUSION_MCP_SCRIPT` | `C:\enfusion-mcp-BK\dist\index.js` | The `dist/index.js` file of Enfusion MCP BK |
| `ENFUSION_GAME_PATH` | `C:\Program Files\Steam\steamapps\common\Arma Reforger` | Game folder |
| `REFORGER_DOCS_PATH` | next to the game: `Arma Reforger Tools\Workbench\docs` | API documentation folder (class hierarchy) |
| `REFORGER_LANG` | `pl` | Language: `pl` or `en` |
| `OLLAMA_CHAT_URL` | `http://127.0.0.1:11434/api/chat` | Ollama address |
| `OLLAMA_MODEL` | `gpt-oss:20b` | Default model (overridden by `settings.json` and `--model`) |

**Model**

| Variable | Default | Description |
|-|-|-|
| `OLLAMA_NUM_CTX` | `32768` | Context size (overridden by `settings.json` and `--num-ctx`) |
| `OLLAMA_NUM_PREDICT` | `16384` | Max tokens of one generation, including reasoning; `0` or `-1` = no limit |
| `OLLAMA_TEMPERATURE` | `0.1` | Temperature |
| `OLLAMA_THINK` | empty | Reasoning level `low`, `medium`, `high` (gpt-oss); empty = not sent |
| `OLLAMA_TIMEOUT` | `300` | Ollama response timeout (seconds) |
| `REFORGER_THINKING_CHARS` | `3000` | How much of the reasoning stays in context within a turn; `0` = none, `-1` = all |
| `REFORGER_STREAM` | `on` | Receive Ollama output as a stream; `off` = whole answer at once (no reasoning abort) |
| `REFORGER_THINK_ABORT` | `8000` | After this many reasoning-only tokens the engine aborts and retries with low reasoning; `0` = never |

**Tools and limits**

| Variable | Default | Description |
|-|-|-|
| `REFORGER_MCP_TIMEOUT` | `90` | MCP startup and call timeout (seconds) |
| `REFORGER_MAX_TOOL_CALLS` | `25` | Max tool calls per question |
| `REFORGER_MAX_TOOL_RESULT_CHARS` | `14000` | Max size of one tool result in context |
| `REFORGER_MAX_TOOL_CONTEXT_CHARS` | `45000` | Total size of tool results in one turn |
| `REFORGER_SOFT_LIMIT_CLASS` / `REFORGER_SOFT_LIMIT_OTHER` | `5` / `10` | `api_search` result limit for classes / other types |
| `REFORGER_VIEW_LIMIT` | `6` | Max local views (search or line range) of one file per turn |
| `REFORGER_MAX_HISTORY_MESSAGES` | `60` | How many recent messages go into context |
| `REFORGER_KB_CHECK` | `on` | Knowledge before code: for the model's own code the engine fetches patterns from the BK knowledge base and gives one comparison round |

Advanced (usually unchanged): `REFORGER_FINISHED_SOURCE_CHARS` (`3600`), `REFORGER_FINISHED_EVIDENCE_CHARS` (`20000`), `REFORGER_COMPACT_SEARCH_CHARS` (`1200`), `REFORGER_COMPACT_OLD_CHARS` (`3600`) – how much of the read sources stays in context after a turn and how older results are shortened.

**Checks and fallback answers**

| Variable | Default | Description |
|-|-|-|
| `REFORGER_VERIFY` | `fix` | Quote verifier: `off`, `log` (log only), `footer` (plus a note under the answer), `fix` (fix round, remaining issues under the answer) |
| `REFORGER_API_CHECK` | `fix` | API name check in code: `fix` (fix round and warning), `log`, `off` |
| `REFORGER_EMERGENCY_IN_HISTORY` | `placeholder` | `placeholder`: a fallback answer is replaced by a short marker in the model's context; `keep`: full text |

### Assistant tools

The model gets only eight **read-only** tools from an allowlist, whatever the MCP server offers:

| Tool | Purpose |
|-|-|
| `asset_search` | Find game files and assets by name |
| `game_browse` | Browse game folders (`pattern` is **only an extension filter**, e.g. `*.c`) |
| `game_read` | Read a game file; the engine can also search inside it and show line ranges without another MCP call |
| `api_search` | Search classes, methods and properties of the script API |
| `component_search` | Search components (`ScriptComponent`) |
| `wiki_search`, `wiki_read` | Search and read wiki pages |
| `wb_knowledge` | Modding knowledge base (patterns and conventions) |

The assistant never reads your own mod project files and never writes anything.

### How the assistant keeps answers reliable

**Better search results for the model**
* Search results start with `[Exact match ...]` or `[NO EXACT MATCH ...]`, so the model does not treat a similar name as proof that something exists.
* An exact class name in `api_search` gives the full class view (all methods). Long results are shortened without losing declarations.
* Correct class hierarchy: the BK API data has a wrong hierarchy for many classes, so the engine reads the real inheritance tree from the local Arma Reforger Tools documentation (`hierarchy.html`, read from disk only). Without the tools it reads `class X : Y` from the game files. Log: `[DOCS]`, `[BASE]`.
* Global functions (`Print`, `PrintFormat`, `GetGame`) are not indexed by `api_search`; the engine adds a note and the verbatim declaration from `EnDebug.c` (`[GLOBAL]`).
* Missing names: when `api_search` does not know a name but there is a game file with exactly that name, the engine points to it (`[FILE]`). For enums that BK does not index, the engine finds the declaration in the enum's file or in the file of the class that uses it, and gives the model the exact list of values (`[ENUM]`).
* Game files named in the question are looked up right away (`[QUESTION]`).
* Typical tool-call mistakes are repaired; invented tools, repeated calls and calls that cannot give results are rejected without using up the limit. Runs of rounds without new data end the search (`[STALL]`); after 15 calls the model gets a one-time limit reminder (`[LIMIT]`).

**Checks of the answer**
* **Quote verifier:** every code block attributed to a game file is compared with the file read in this conversation. A quote that is not in the file, a file that was not read, or line numbers the model never saw in a file view start a fix round. Log: `[VERIFY]`, `[LINES]`.
* **API check:** class and method names in code must appear in tool results (also through base classes). It also checks base classes in `class X : Y`, `modded class X`, `override` methods, enum values, return types in assignments, a `SCR_` prefix on new mod classes (`SCR_` belongs to the game), `.et` entries written as JSON, `PrintFormat` with `%s` instead of `%1`.
* **Syntax:** `0.5f`, `?:`, `?.`, `GetComponent<T>()` and other syntax that Enforce Script does not accept.
* **Knowledge before code:** for the model's own code the engine compares it with patterns from the BK knowledge base (`[KB]`).
* **After a compile error** pasted by the user, the answer must contain the whole corrected script, not just a description.
* Fix rounds see the rejected draft; if the fix is worse than the first draft, the first draft stays (`[DRAFT]`). Problems that survived are marked in the text with `⚠` (`[MARKS]`).
* Leaked model reasoning and looped repeated lines are removed from the answer (`[REASONING]`, `[REPEATS]`).

**Fallback answers.** When the search is stopped (MCP call limit or rounds without new data), the model writes its answer in the same conversation from the collected results, without further tools; it gets the note `_[Search stopped (...)]_` (`[END]`). Only if the model twice fails to return complete text does the engine build an emergency summary (`_[Summary of the available MCP results: ...]_`) – treat it as incomplete.

### Local data and privacy

* `assistant_web_data\conversations.json` – chat history and tool call metadata (name, arguments, status, time). **Tool results (e.g. game file contents) are not saved.** Answers may contain quoted game code, so mind the game's license if you publish conversations.
* `assistant_web_data\settings.json` – model, context, paths, language.
* Full texts of read files are kept **in process memory only** (for the verifier and local views) until the server stops.
* Logs (`logs`) contain tool names, arguments and diagnostics, without file contents.
* Deleting `assistant_web_data` clears history and settings.

### Security

* The server listens on `127.0.0.1` only and has no authentication: **do not expose it to a network**.
* Requests are checked (`Host`, `Origin`, for POST `Content-Type: application/json` and `X-Assistant-UI: 1`, 48 KB size limit, strict CSP).
* Read-only tools only; nothing is written to game files and no game code is run.

### Test set

`reforger_eval.py` has 10 questions (Polish and English) and rule-based scoring (required elements, known errors). Ask the questions yourself in the interface, each in a new conversation (test A has two questions in one conversation), then score the saved history:

```powershell
python reforger_eval.py questions                    # the 10 questions
python reforger_eval.py score --md results.md        # score assistant_web_data\conversations.json
python reforger_eval.py log logs\log_....txt         # server log summary, turn by turn
```

Questions and report follow the language (`REFORGER_LANG` or the interface setting); the scoring key understands both languages. Rule-based scoring is an approximation, not a replacement for reading the answers.

### Limitations

* Models make mistakes. The most common in our tests: invented values (e.g. non-existent `LogLevel` levels), confusing the muzzle with the magazine, wrong public/private claims, prefab code with invented keys or GUIDs.
* Tuned and tested mainly on `gpt-oss:20b`. In larger tasks (e.g. "fix this whole script") it can wander and hit the 25-call limit: split the task into smaller questions and name the classes or files you know. An early test with a larger dense Qwen model scored better but was several times slower.
* The model sometimes reasons for a very long time (minutes); there is no Stop button yet.
* The English version is newer (2.0) and less tested than the Polish one.

### Troubleshooting

| Symptom | What to do |
|-|-|
| `MCP server not found: ...` / setup mode at start | Set the BK path with the **paths** button (the `dist/index.js` file must exist) and restart |
| `Cannot start Node/Enfusion MCP` | Install Node.js and make sure `node` is in `PATH` |
| `Ollama is not responding (...)` | Start Ollama or fix `OLLAMA_CHAT_URL` |
| Model change: "does not support tool calling" | Choose a model with tool support |
| The page looks old after updating files | Reload without cache (Ctrl+F5) |
| Very long answer, `reason=length` in the log | Reasoning used up the generation limit; the assistant retries with low reasoning. You can also set `OLLAMA_THINK=low` or lower `OLLAMA_NUM_PREDICT` |
| Note `_[Search stopped ...]_` | The search was stopped (see fallback answers above). Ask a narrower question |
| Port in use | Start with another port: `--port 8766` |
| Broken characters in the console or log | Start with `START_ASSISTANT_WEB.cmd` (sets UTF-8) |

### Files

| File | Description |
|-|-|
| `reforger_assistant_MCP_BK.py` | **Engine:** conversation with Ollama, tool calls, safeguards, verifier |
| `reforger_assistant_WEB.py` | Local HTTP server |
| `assistant.html` | Interface (HTML, CSS and JavaScript in one file, no external libraries) |
| `reforger_config.py` | Configuration: version, paths, limits, modes |
| `reforger_prompts.py` / `reforger_prompts_en.py` | Texts for the model in Polish / English (`python reforger_prompts_en.py` checks that both match) |
| `reforger_i18n.py` | Language selection and short bilingual messages |
| `reforger_rules.py` | Rules as data: tools, patterns, name lists |
| `reforger_checks.py` | Answer checks: quote verifier, API and syntax checks |
| `reforger_helpers.py` | Tool-call repair, shortening of results |
| `reforger_mcp.py` | Enfusion MCP client |
| `reforger_docs.py` | Class hierarchy from the local Workbench API documentation |
| `reforger_paths.py` | Paths and settings from the interface |
| `reforger_eval.py` | Test set and scoring |
| `START_ASSISTANT_WEB.cmd` / `START_ASSISTANT_WEB_LOG.cmd` | Launchers (the second writes a log to `logs`) |
| `assistant_web_data` | Created automatically: `conversations.json`, `settings.json` |

### License and author

Made by KUKA, MIT license. Enfusion MCP BK is also MIT licensed.

---

<a id="polski"></a>

## Polski

Lokalny asystent dla modderów **Arma Reforger**. Odpowiada na pytania o skrypty, API i prefaby gry, korzystając z prawdziwych plików gry i wiki, a nie z pamięci modelu. Działa w całości na Twoim komputerze: model uruchamia Ollama, a pliki gry czyta serwer **Enfusion MCP BK**.

> **Odpowiedzi modelu wymagają weryfikacji przed użyciem w modzie.** Asystent cytuje kod z plików gry i pokazuje, z których narzędzi korzystał, ale model nadal może się mylić (patrz [Ograniczenia](#ograniczenia)).

```text
Przeglądarka  <->  lokalny serwer (Python)  <->  silnik  <->  model (Ollama)
assistant.html     reforger_assistant_WEB.py     reforger_assistant_MCP_BK.py
                                                    |
                                                    +-->  Enfusion MCP BK (Node)  <->  pliki gry, wiki
```

Asystent działa **po polsku albo po angielsku** (przełącznik w interfejsie, patrz [Język](#język)).

### Wymagania

| Wymaganie | Uwagi |
|-|-|
| Windows | Używane i testowane na Windows; launchery `.cmd` są tylko dla Windows |
| Python 3.10 lub nowszy | Tylko biblioteka standardowa, **nic nie trzeba instalować przez pip** (testowane na 3.12) |
| Node.js w `PATH` | Uruchamia serwer MCP (`node dist/index.js`) |
| Enfusion MCP BK | Zbudowany serwer MCP, plik `dist/index.js`: [github.com/steffenbk/enfusion-mcp-BK](https://github.com/steffenbk/enfusion-mcp-BK) |
| Ollama + model z obsługą narzędzi | Dostrajane i testowane na `gpt-oss:20b` |
| Arma Reforger | Zainstalowana gra (potrzebna ścieżka do jej folderu) |
| Arma Reforger Tools (opcjonalnie) | Lokalna dokumentacja API daje asystentowi poprawną hierarchię klas |

Przykładowy testowany sprzęt: RTX 4070 Ti Super 16 GB. `gpt-oss:20b` z kontekstem 32k zajmuje około 12 GB VRAM i działa w całości na GPU.

### Szybki start

1. Skopiuj wszystkie pliki asystenta do jednego folderu (lista w sekcji [Pliki](#pliki)).
2. Upewnij się, że Ollama działa i model jest pobrany:
   ```bat
   ollama pull gpt-oss:20b
   ```
3. Uruchom `START_ASSISTANT_WEB.cmd` (dwuklik) albo w PowerShellu:
   ```powershell
   python .\reforger_assistant_WEB.py
   ```
4. Przeglądarka otworzy się pod adresem [http://127.0.0.1:8765](http://127.0.0.1:8765).
5. **Ustaw ścieżki:** przycisk **ścieżki** na górnym pasku. Podaj plik `dist\index.js` z Enfusion MCP BK i folder gry (np. `D:\SteamLibrary\steamapps\common\Arma Reforger`). Folder dokumentacji asystent znajdzie sam obok gry; podajesz go tylko wtedy, gdy Arma Reforger Tools jest zainstalowane gdzie indziej. **Sprawdź** pokazuje przy każdym polu, czy plik albo folder istnieje, **Zapisz** zapisuje ścieżki. **Uruchom asystenta ponownie**, żeby ich użyć.
6. Opcjonalnie zmień język: przycisk **język**.

Jeśli BK się nie uruchomi (np. zła ścieżka), asystent nie kończy pracy: startuje w trybie konfiguracji i od razu otwiera formularz ścieżek.

Zamknięcie okna konsoli (albo Ctrl+C) zatrzymuje serwer. `START_ASSISTANT_WEB_LOG.cmd` działa tak samo, ale zapisuje log do pliku `logs\log_RRRRMMDD_GGMMSS.txt` (UTF-8). Podgląd na żywo w drugim oknie PowerShella: `Get-Content .\logs\NAZWA.txt -Wait`.

### Interfejs

* **Lewy panel:** historia rozmów, wyszukiwanie, **Nowa rozmowa**, na dole stan połączenia z MCP i wersja.
* **Górny pasek:**
  * **model** – lista modeli zainstalowanych w Ollamie. Modele bez obsługi narzędzi są wyłączone, modele tylko do osadzeń ukryte.
  * **kontekst** – presety 32k–128k albo własna wartość od 32 768 do 262 144 (minimum wynika z limitów wyników narzędzi).
  * **ścieżki** – BK, gra i dokumentacja; działają od ponownego uruchomienia.
  * **język** – PL/EN; interfejs zmienia się od razu, asystent od ponownego uruchomienia.
  * Model i kontekst obowiązują od następnego pytania. Wszystkie ustawienia zapisują się w `assistant_web_data\settings.json`. Na wąskich ekranach przyciski pokazują same wartości.
* **Prawy panel „Aktywność MCP”:** każde wywołanie narzędzia (nazwa, argumenty, status, czas), tylko do podglądu.
* **Odpowiedzi:** tabele, listy i bloki kodu z przyciskiem **Kopiuj**. Problemy, które przetrwały rundę poprawek silnika, są oznaczone w treści znakiem `⚠`.

### Język

Polski (domyślnie) albo angielski. Język obejmuje interfejs w przeglądarce i cały silnik: prompt systemowy, podpowiedzi dla modelu, kontrole odpowiedzi, log w konsoli i zestaw testowy.

* Zmieniasz go przyciskiem **język**. Interfejs przełącza się od razu, silnik po ponownym uruchomieniu (teksty dla modelu są ustawiane przy starcie). Do tego czasu menu pokazuje, w jakim języku asystent nadal odpowiada.
* Wybór zapisuje się jako `"lang"` w `assistant_web_data\settings.json`.
* Zmienna środowiskowa `REFORGER_LANG=en` (albo `pl`) ma pierwszeństwo i blokuje przycisk.
* Kontrole rozumieją oba języki, więc starsza rozmowa w drugim języku dalej działa.

### Opcje uruchamiania

```powershell
python .\reforger_assistant_WEB.py --port 8766
python .\reforger_assistant_WEB.py --no-browser
python .\reforger_assistant_WEB.py --model gpt-oss:20b --num-ctx 32768
```

| Opcja | Domyślnie | Opis |
|-|-|-|
| `--port` | `8765` | Port serwera lokalnego |
| `--no-browser` | wyłączone | Nie otwieraj przeglądarki automatycznie |
| `--model` | z ustawień | Model Ollamy tylko na tę sesję (nie zmienia pliku ustawień) |
| `--num-ctx` | z ustawień | Rozmiar kontekstu tylko na tę sesję |

Pierwszeństwo ustawień modelu i kontekstu: **argument wiersza poleceń > zapisane w interfejsie (`settings.json`) > zmienne środowiskowe i wartości domyślne**.

### Konfiguracja (zmienne środowiskowe)

Ustawiasz je w launcherze (`set "NAZWA=wartość"`) albo w PowerShellu (`$env:NAZWA = "wartość"`). Przy starcie silnik wypisuje linię `[CONFIG]` z aktualnymi wartościami. Większości osób wystarczy interfejs; zmienne służą do dostrajania.

**Ścieżki, połączenie, język** (pierwszeństwo: zmienna > interfejs > wartość domyślna; ścieżka ustawiona zmienną jest w interfejsie tylko do podglądu)

| Zmienna | Domyślnie | Opis |
|-|-|-|
| `ENFUSION_MCP_SCRIPT` | `C:\enfusion-mcp-BK\dist\index.js` | Plik `dist/index.js` serwera Enfusion MCP BK |
| `ENFUSION_GAME_PATH` | `C:\Program Files\Steam\steamapps\common\Arma Reforger` | Folder gry |
| `REFORGER_DOCS_PATH` | obok gry: `Arma Reforger Tools\Workbench\docs` | Folder dokumentacji API (hierarchia klas) |
| `REFORGER_LANG` | `pl` | Język: `pl` albo `en` |
| `OLLAMA_CHAT_URL` | `http://127.0.0.1:11434/api/chat` | Adres Ollamy |
| `OLLAMA_MODEL` | `gpt-oss:20b` | Model domyślny (nadpisywany przez `settings.json` i `--model`) |

**Model**

| Zmienna | Domyślnie | Opis |
|-|-|-|
| `OLLAMA_NUM_CTX` | `32768` | Rozmiar kontekstu (nadpisywany przez `settings.json` i `--num-ctx`) |
| `OLLAMA_NUM_PREDICT` | `16384` | Maksimum tokenów jednej generacji, z rozumowaniem; `0` lub `-1` = bez limitu |
| `OLLAMA_TEMPERATURE` | `0.1` | Temperatura |
| `OLLAMA_THINK` | puste | Poziom rozumowania `low`, `medium`, `high` (gpt-oss); puste = nie wysyłaj |
| `OLLAMA_TIMEOUT` | `300` | Limit czasu odpowiedzi Ollamy (sekundy) |
| `REFORGER_THINKING_CHARS` | `3000` | Ile rozumowania zostaje w kontekście w obrębie tury; `0` = nic, `-1` = całość |
| `REFORGER_STREAM` | `on` | Odbieranie odpowiedzi Ollamy na bieżąco; `off` = cała odpowiedź naraz (bez przerywania rozumowania) |
| `REFORGER_THINK_ABORT` | `8000` | Po tylu tokenach samego rozumowania silnik przerywa generację i ponawia ją z niskim rozumowaniem; `0` = nigdy |

**Narzędzia i limity**

| Zmienna | Domyślnie | Opis |
|-|-|-|
| `REFORGER_MCP_TIMEOUT` | `90` | Limit czasu uruchomienia i wywołań MCP (sekundy) |
| `REFORGER_MAX_TOOL_CALLS` | `25` | Maksimum wywołań narzędzi na jedno pytanie |
| `REFORGER_MAX_TOOL_RESULT_CHARS` | `14000` | Maksymalny rozmiar jednego wyniku narzędzia w kontekście |
| `REFORGER_MAX_TOOL_CONTEXT_CHARS` | `45000` | Łączny rozmiar wyników narzędzi w jednej turze |
| `REFORGER_SOFT_LIMIT_CLASS` / `REFORGER_SOFT_LIMIT_OTHER` | `5` / `10` | Limit wyników `api_search` dla klas / pozostałych typów |
| `REFORGER_VIEW_LIMIT` | `6` | Maksimum lokalnych widoków (wyszukiwanie albo zakres linii) jednego pliku w turze |
| `REFORGER_MAX_HISTORY_MESSAGES` | `60` | Ile ostatnich wiadomości trafia do kontekstu |
| `REFORGER_KB_CHECK` | `on` | Wiedza przed kodem: przy własnym kodzie modelu silnik pobiera wzorce z bazy wiedzy BK i daje jedną rundę na porównanie |

Zaawansowane (zwykle bez zmian): `REFORGER_FINISHED_SOURCE_CHARS` (`3600`), `REFORGER_FINISHED_EVIDENCE_CHARS` (`20000`), `REFORGER_COMPACT_SEARCH_CHARS` (`1200`), `REFORGER_COMPACT_OLD_CHARS` (`3600`) – ile odczytanych źródeł zostaje w kontekście po turze i jak skracane są starsze wyniki.

**Kontrole i odpowiedzi awaryjne**

| Zmienna | Domyślnie | Opis |
|-|-|-|
| `REFORGER_VERIFY` | `fix` | Weryfikator cytatów: `off`, `log` (tylko log), `footer` (dodatkowo uwaga pod odpowiedzią), `fix` (runda poprawkowa, pozostałe uwagi pod odpowiedzią) |
| `REFORGER_API_CHECK` | `fix` | Kontrola nazw API w kodzie: `fix` (runda poprawkowa i ostrzeżenie), `log`, `off` |
| `REFORGER_EMERGENCY_IN_HISTORY` | `placeholder` | `placeholder`: odpowiedź awaryjna jest w kontekście modelu zastępowana krótkim znacznikiem; `keep`: pełna treść |

### Narzędzia asystenta

Model dostaje wyłącznie osiem narzędzi **tylko do odczytu** z listy dozwolonych, niezależnie od tego, co udostępnia serwer MCP:

| Narzędzie | Do czego służy |
|-|-|
| `asset_search` | Szukanie plików i zasobów gry po nazwie |
| `game_browse` | Przeglądanie folderów gry (`pattern` to **tylko filtr rozszerzenia**, np. `*.c`) |
| `game_read` | Odczyt pliku gry; silnik potrafi też przeszukać go i pokazać zakres linii bez kolejnego wywołania MCP |
| `api_search` | Szukanie klas, metod i właściwości API skryptów |
| `component_search` | Szukanie komponentów (`ScriptComponent`) |
| `wiki_search`, `wiki_read` | Wyszukiwanie i odczyt stron wiki |
| `wb_knowledge` | Baza wiedzy modderskiej (wzorce i konwencje) |

Asystent nigdy nie czyta plików Twojego projektu moda i niczego nie zapisuje.

### Jak asystent dba o wiarygodność

**Lepsze wyniki wyszukiwania dla modelu**
* Wyniki wyszukiwania zaczynają się od `[Dokładne trafienie ...]` albo `[BRAK DOKŁADNEGO TRAFIENIA ...]`, żeby model nie traktował podobnej nazwy jako dowodu istnienia.
* Dokładna nazwa klasy w `api_search` daje pełny widok klasy (wszystkie metody). Długie wyniki są skracane bez gubienia deklaracji.
* Poprawna hierarchia klas: dane API w BK mają dla wielu klas błędną hierarchię, więc silnik czyta prawdziwe drzewo dziedziczenia z lokalnej dokumentacji Arma Reforger Tools (`hierarchy.html`, tylko odczyt z dysku). Bez Tools czyta `class X : Y` z plików gry. W logu: `[DOKUMENTACJA]`, `[BAZA]`.
* Funkcji globalnych (`Print`, `PrintFormat`, `GetGame`) `api_search` nie indeksuje; silnik dopisuje notatkę i dosłowną deklarację z `EnDebug.c` (`[GLOBALNA]`).
* Brakujące nazwy: gdy `api_search` nie zna nazwy, a w grze jest plik o dokładnie takiej nazwie, silnik go wskazuje (`[PLIK]`). Dla enumów, których BK nie indeksuje, silnik znajduje deklarację w pliku enuma albo w pliku klasy, która go używa, i podaje modelowi dokładną listę wartości (`[ENUM]`).
* Pliki gry wymienione w pytaniu są wyszukiwane od razu (`[PYTANIE]`).
* Typowe błędy wywołań narzędzi są naprawiane; wymyślone narzędzia, powtórzenia i wywołania, które nie mogą dać wyniku, są odrzucane bez zużywania limitu. Seria rund bez nowych danych kończy wyszukiwanie (`[STALL]`); po 15 wywołaniach model dostaje jednorazowe przypomnienie o limicie (`[LIMIT]`).

**Kontrole odpowiedzi**
* **Weryfikator cytatów:** każdy blok kodu przypisany do pliku gry jest porównywany z plikiem odczytanym w tej rozmowie. Cytat, którego nie ma w pliku, powołanie na nieodczytany plik albo numery linii, których model nie widział w widoku pliku, uruchamiają rundę poprawkową. W logu: `[VERIFY]`, `[LINIE]`.
* **Kontrola API:** nazwy klas i metod w kodzie muszą występować w wynikach narzędzi (także przez klasy bazowe). Sprawdzane są też klasy bazowe w `class X : Y`, `modded class X`, metody `override`, wartości enumów, typy zwracane przy przypisaniu, prefiks `SCR_` w nowych klasach moda (`SCR_` należy do gry), wpisy `.et` zapisane jako JSON, `PrintFormat` z `%s` zamiast `%1`.
* **Składnia:** `0.5f`, `?:`, `?.`, `GetComponent<T>()` i inne konstrukcje, których Enforce Script nie przyjmuje.
* **Wiedza przed kodem:** własny kod modelu silnik porównuje ze wzorcami z bazy wiedzy BK (`[KB]`).
* **Po błędzie kompilacji** wklejonym przez użytkownika odpowiedź musi zawierać cały poprawiony skrypt, a nie tylko opis.
* Rundy poprawkowe widzą odrzucony szkic; jeśli poprawka jest gorsza od pierwszego szkicu, zostaje pierwszy szkic (`[SZKIC]`). Problemy, które przetrwały, są oznaczone w treści znakiem `⚠` (`[OZNACZENIA]`).
* Rozumowanie modelu, które wyciekło do odpowiedzi, i zapętlone powtórzenia linii są usuwane (`[ROZUMOWANIE]`, `[POWTÓRZENIA]`).

**Odpowiedzi awaryjne.** Gdy wyszukiwanie zostaje przerwane (limit wywołań MCP albo rundy bez nowych danych), model pisze odpowiedź w tej samej rozmowie z zebranych wyników, już bez narzędzi; dostaje ona stopkę `_[Wyszukiwanie przerwane (...)]_` (`[KONIEC]`). Dopiero gdy model dwa razy nie odda kompletnego tekstu, silnik składa podsumowanie awaryjne (`_[Podsumowanie dostępnych wyników MCP: ...]_`) – traktuj je jako niepełne.

### Dane lokalne i prywatność

* `assistant_web_data\conversations.json` – historia czatu i metadane wywołań narzędzi (nazwa, argumenty, status, czas). **Wyniki narzędzi (np. treść plików gry) nie są zapisywane.** Odpowiedzi mogą zawierać przytoczony kod gry, więc pamiętaj o licencji gry, jeśli publikujesz rozmowy.
* `assistant_web_data\settings.json` – model, kontekst, ścieżki, język.
* Pełne teksty odczytanych plików są trzymane **tylko w pamięci procesu** (dla weryfikatora i widoków lokalnych) do zamknięcia serwera.
* Logi (`logs`) zawierają nazwy narzędzi, argumenty i diagnostykę, bez treści plików.
* Usunięcie folderu `assistant_web_data` czyści historię i ustawienia.

### Bezpieczeństwo

* Serwer nasłuchuje tylko na `127.0.0.1` i nie ma uwierzytelniania: **nie wystawiaj go do sieci**.
* Żądania są sprawdzane (`Host`, `Origin`, dla POST `Content-Type: application/json` i `X-Assistant-UI: 1`, limit 48 KB, ścisła polityka CSP).
* Tylko narzędzia odczytu; nic nie jest zapisywane do plików gry i żaden kod gry nie jest uruchamiany.

### Zestaw testowy

`reforger_eval.py` zawiera 10 pytań (po polsku i po angielsku) i ocenę według reguł (wymagane elementy, znane błędy). Pytania zadajesz sam w interfejsie, każde w nowej rozmowie (test A ma dwa pytania w jednej rozmowie), a potem oceniasz zapisaną historię:

```powershell
python reforger_eval.py questions                    # 10 pytań
python reforger_eval.py score --md wyniki.md         # ocena assistant_web_data\conversations.json
python reforger_eval.py log logs\log_....txt         # podsumowanie logu serwera tura po turze
```

Pytania i raport są w języku asystenta (`REFORGER_LANG` albo ustawienie z interfejsu); klucz odpowiedzi rozumie oba języki. Ocena regułowa jest przybliżeniem, nie zastępuje przeczytania odpowiedzi.

### Ograniczenia

* Modele się mylą. Najczęstsze błędy w naszych testach: wymyślone wartości (np. nieistniejące poziomy `LogLevel`), pomylenie lufy (`muzzle`) z magazynkiem, błędy co do tego, co jest publiczne, a co prywatne, kod prefabów z wymyślonymi kluczami albo GUID-ami.
* Dostrajane i testowane głównie na `gpt-oss:20b`. Przy większych zadaniach (np. „popraw cały skrypt”) model potrafi błądzić i dojść do limitu 25 wywołań: dziel zadanie na mniejsze pytania i podawaj nazwy klas albo plików, które znasz. Wstępny test z większym, gęstym modelem Qwen dał lepszy wynik, ale był kilka razy wolniejszy.
* Model czasem bardzo długo rozumuje (minuty); na razie nie ma przycisku „Stop”.
* Wersja angielska jest nowsza (2.0) i mniej przetestowana niż polska.

### Rozwiązywanie problemów

| Objaw | Co zrobić |
|-|-|
| `Nie znaleziono serwera MCP: ...` / tryb konfiguracji przy starcie | Ustaw ścieżkę BK przyciskiem **ścieżki** (plik `dist/index.js` musi istnieć) i uruchom ponownie |
| `Nie można uruchomić Node/Enfusion MCP` | Zainstaluj Node.js i upewnij się, że `node` jest w `PATH` |
| `Ollama nie odpowiada (...)` | Uruchom Ollamę albo popraw `OLLAMA_CHAT_URL` |
| Zmiana modelu: „nie obsługuje wywoływania narzędzi” | Wybierz model z obsługą narzędzi |
| Strona wygląda po staremu po podmianie plików | Odśwież z pominięciem pamięci podręcznej (Ctrl+F5) |
| Bardzo długa odpowiedź, w logu `reason=length` | Rozumowanie zużyło limit generacji; asystent ponawia z niskim rozumowaniem. Możesz też ustawić `OLLAMA_THINK=low` albo zmniejszyć `OLLAMA_NUM_PREDICT` |
| Stopka `_[Wyszukiwanie przerwane ...]_` | Wyszukiwanie przerwano (patrz odpowiedzi awaryjne wyżej). Zadaj węższe pytanie |
| Port zajęty | Uruchom z innym portem: `--port 8766` |
| Rozsypane polskie znaki w konsoli lub logu | Uruchamiaj przez `START_ASSISTANT_WEB.cmd` (ustawia UTF-8) |

### Pliki

| Plik | Opis |
|-|-|
| `reforger_assistant_MCP_BK.py` | **Silnik:** rozmowa z Ollamą, wywołania narzędzi, zabezpieczenia, weryfikator |
| `reforger_assistant_WEB.py` | Lokalny serwer HTTP |
| `assistant.html` | Interfejs (HTML, CSS i JavaScript w jednym pliku, bez zewnętrznych bibliotek) |
| `reforger_config.py` | Konfiguracja: wersja, ścieżki, limity, tryby |
| `reforger_prompts.py` / `reforger_prompts_en.py` | Teksty dla modelu po polsku / po angielsku (`python reforger_prompts_en.py` sprawdza zgodność) |
| `reforger_i18n.py` | Wybór języka i krótkie komunikaty w dwóch językach |
| `reforger_rules.py` | Reguły jako dane: narzędzia, wzorce, listy nazw |
| `reforger_checks.py` | Kontrole odpowiedzi: weryfikator cytatów, kontrola API i składni |
| `reforger_helpers.py` | Naprawa wywołań narzędzi, skracanie wyników |
| `reforger_mcp.py` | Klient Enfusion MCP |
| `reforger_docs.py` | Hierarchia klas z lokalnej dokumentacji API Workbencha |
| `reforger_paths.py` | Ścieżki i ustawienia z interfejsu |
| `reforger_eval.py` | Zestaw testowy i ocena |
| `START_ASSISTANT_WEB.cmd` / `START_ASSISTANT_WEB_LOG.cmd` | Launchery (drugi zapisuje log do `logs`) |
| `assistant_web_data` | Tworzony automatycznie: `conversations.json`, `settings.json` |

### Licencja i autor

Stworzone przez KUKA, na licencji MIT. Enfusion MCP BK również na licencji MIT.
