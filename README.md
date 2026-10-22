# Reforger Assistant WEB

Lokalny asystent dla modderów **Arma Reforger**. Odpowiada na pytania o skrypty, API i prefaby gry, korzystając z prawdziwych plików gry i biki, a nie z pamięci modelu. Działa w całości na Twoim komputerze: model uruchamia Ollama, a pliki gry czyta serwer **Enfusion MCP BK**.

> \\\\\\\*\\\\\\\*Odpowiedzi modelu wymagają weryfikacji przed użyciem w modzie.\\\\\\\*\\\\\\\* Asystent cytuje kod z plików gry i pokazuje, z których narzędzi korzystał, ale model nadal może się mylić (patrz \\\\\\\[Ograniczenia](#ograniczenia)).

```text
Przeglądarka  <->  lokalny serwer (Python)  <->  silnik  <->  Ollama (model)
  assistant.html     reforger\\\\\\\_assistant\\\\\\\_WEB.py     reforger\\\\\\\_assistant\\\\\\\_MCP\\\\\\\_BK.py
                                                      |
                                                      +-->  Enfusion MCP BK (Node)  <->  pliki gry i wiki
```

## Wymagania

|**Wymaganie**|**Uwagi**|
|-|-|
|Windows|Używane i testowane na Windows; launchery `.cmd` są tylko dla Windows|
|Python 3.10 lub nowszy|Tylko biblioteka standardowa, **nie trzeba nic instalować przez pip** (testowane na 3.12)|
|Node.js w `PATH`|Uruchamia serwer MCP (`node dist\\\\\\\\index.js`)|
|Enfusion MCP BK|Zbudowany serwer MCP, plik `dist\\\\\\\\index.js` -> https://github.com/steffenbk/enfusion-mcp-BK|
|Ollama + model z obsługą narzędzi|Testowano na `gpt-oss:20b`|
|Arma Reforger|Zainstalowana gra (potrzebna ścieżka do jej folderu)|

Przykład sprzętu: RTX 4070 Ti Super 16 GB. Model `gpt-oss:20b` przy kontekście 32k zajmuje około 12 GB VRAM i działa w całości na GPU.

## Szybki start

1. Skopiuj wszystkie pliki asystenta do jednego folderu (lista w sekcji [Pliki](#pliki)).
2. **Ustaw ścieżki.** Domyślne wartości wskazują (`C:\\\\\\\\enfusion-mcp-BK\\\\\\\\dist\\\\\\\\index.js` i `C:\\\\\\\\SteamLibrary\\\\\\\\steamapps\\\\\\\\common\\\\\\\\Arma Reforger`)
W `START\\\\\\\_ASSISTANT\\\\\\\_WEB.cmd`, własne dopisz przed linią `python "reforger\\\\\\\_assistant\\\\\\\_WEB.py"`:

```bat
   set "ENFUSION\\\\\\\_MCP\\\\\\\_SCRIPT=C:\\\\\\\\ścieżka\\\\\\\\do\\\\\\\\enfusion-mcp-BK\\\\\\\\dist\\\\\\\\index.js"
   set "ENFUSION\\\\\\\_GAME\\\\\\\_PATH=C:\\\\\\\\Program Files (x86)\\\\\\\\Steam\\\\\\\\steamapps\\\\\\\\common\\\\\\\\Arma Reforger"
   ```

W PowerShellu to samo robisz poleceniami `$env:ENFUSION\\\\\\\_MCP\\\\\\\_SCRIPT = "..."` i `$env:ENFUSION\\\\\\\_GAME\\\\\\\_PATH = "..."`.

3. Upewnij się, że Ollama działa i model jest pobrany:

```bat
   ollama pull gpt-oss:20b
   ```

4. Uruchom `START\\\\\\\_ASSISTANT\\\\\\\_WEB.cmd` (dwuklik) albo w PowerShellu:

```powershell
   python .\\\\\\\\reforger\\\\\\\_assistant\\\\\\\_WEB.py
   ```

5. Przeglądarka otworzy się sama pod adresem [http://127.0.0.1:8765](http://127.0.0.1:8765). Zamknięcie okna konsoli (albo Ctrl+C) zatrzymuje serwer.

`START\\\\\\\_ASSISTANT\\\\\\\_WEB\\\\\\\_LOG.cmd` działa tak samo, ale zapisuje log do pliku `logs\\\\\\\\log\\\\\\\_RRRRMMDD\\\\\\\_GGMMSS.txt` (UTF-8), a okno konsoli zostaje puste. Podgląd na żywo w drugim oknie PowerShella: `Get-Content .\\\\\\\\logs\\\\\\\\NAZWA.txt -Wait`. Oba launchery ustawiają UTF-8, więc polskie znaki w konsoli i w logu nie rozsypują się.

## Interfejs

* **Lewy panel:** historia rozmów, wyszukiwanie, przycisk „Nowa rozmowa”, na dole stan połączenia z serwerem MCP
* **Góra:** przyciski **model** i **kontekst** (wybór z listy), obok znacznika `LOCAL ONLY`.

  * Lista modeli pochodzi z Ollamy. Modele bez obsługi narzędzi są wyłączone, a modele tylko do osadzeń ukryte.
  * Kontekst: presety 32k, 48k, 64k, 96k, 128k lub własna wartość od 32 768 do 262 144. Minimum wynika z limitów wyników narzędzi, które są dobrane do 32 768 tokenów.
  * Zmiana obowiązuje od następnego pytania i zapisuje się w `assistant\\\\\\\_web\\\\\\\_data\\\\\\\\settings.json`.
* **Prawy panel „Aktywność MCP”:** każde wywołanie narzędzia (nazwa, argumenty, status, czas), tylko do podglądu.
* **Odpowiedzi:** tabele, listy, linie poziome i bloki kodu z przyciskiem „Kopiuj”.

## Opcje uruchamiania

```powershell
python .\\\\\\\\reforger\\\\\\\_assistant\\\\\\\_WEB.py --port 8766
python .\\\\\\\\reforger\\\\\\\_assistant\\\\\\\_WEB.py --no-browser
python .\\\\\\\\reforger\\\\\\\_assistant\\\\\\\_WEB.py --model gpt-oss:20b --num-ctx 32768
```

|**Opcja**|**Domyślnie**|**Opis**|
|-|-|-|
|`--port`|`8765`|Port serwera lokalnego|
|`--no-browser`|wyłączone|Nie otwieraj przeglądarki automatycznie|
|`--model`|z ustawień|Model Ollamy tylko na tę sesję (nie nadpisuje pliku ustawień)|
|`--num-ctx`|z ustawień|Rozmiar kontekstu tylko na tę sesję|

Pierwszeństwo ustawień modelu i kontekstu: **argument wiersza poleceń > zapisane w interfejsie (`settings.json`) > zmienne środowiskowe i wartości domyślne**.

## Konfiguracja (zmienne środowiskowe)

Ustawiasz je w launcherze (`set "NAZWA=wartość"`) albo w PowerShellu (`$env:NAZWA = "wartość"`). Przy starcie silnik wypisuje w konsoli linię `\\\\\\\[CONFIG]` z aktualnymi wartościami.

### Ścieżki i połączenia

|**Zmienna**|**Domyślnie**|**Opis**|
|-|-|-|
|`ENFUSION\\\\\\\_MCP\\\\\\\_SCRIPT`|ścieżka autora|Plik `dist\\\\\\\\index.js` serwera Enfusion MCP BK|
|`ENFUSION\\\\\\\_GAME\\\\\\\_PATH`|ścieżka autora|Folder zainstalowanej gry|
|`OLLAMA\\\\\\\_CHAT\\\\\\\_URL`|`http://127.0.0.1:11434/api/chat`|Adres Ollamy|
|`OLLAMA\\\\\\\_MODEL`|`gpt-oss:20b`|Model domyślny (nadpisywany przez `settings.json` i `--model`)|

### Model

|**Zmienna**|**Domyślnie**|**Opis**|
|-|-|-|
|`OLLAMA\\\\\\\_NUM\\\\\\\_CTX`|`32768`|Rozmiar kontekstu (nadpisywany przez `settings.json` i `--num-ctx`)|
|`OLLAMA\\\\\\\_NUM\\\\\\\_PREDICT`|`16384`|Maksimum tokenów jednej generacji, wliczając rozumowanie; `0` lub `-1` = bez limitu|
|`OLLAMA\\\\\\\_TEMPERATURE`|`0.1`|Temperatura|
|`OLLAMA\\\\\\\_THINK`|puste|Poziom rozumowania: `low`, `medium`, `high`; puste = nie wysyłaj|
|`OLLAMA\\\\\\\_TIMEOUT`|`300`|Limit czasu odpowiedzi Ollamy (sekundy)|
|`REFORGER\\\\\\\_THINKING\\\\\\\_CHARS`|`3000`|Ile końcówki rozumowania zostaje w kontekście w obrębie tury; `0` = nic, `-1` = całość|

### Narzędzia i limity

|**Zmienna**|**Domyślnie**|**Opis**|
|-|-|-|
|`REFORGER\\\\\\\_MCP\\\\\\\_TIMEOUT`|`90`|Limit czasu uruchomienia i wywołań MCP (sekundy)|
|`REFORGER\\\\\\\_MAX\\\\\\\_TOOL\\\\\\\_CALLS`|`25`|Maksimum wywołań narzędzi na jedno pytanie|
|`REFORGER\\\\\\\_MAX\\\\\\\_TOOL\\\\\\\_RESULT\\\\\\\_CHARS`|`14000`|Maksymalny rozmiar jednego wyniku narzędzia w kontekście|
|`REFORGER\\\\\\\_MAX\\\\\\\_TOOL\\\\\\\_CONTEXT\\\\\\\_CHARS`|`45000`|Łączny rozmiar wyników narzędzi w jednej turze|
|`REFORGER\\\\\\\_SOFT\\\\\\\_LIMIT\\\\\\\_CLASS` / `REFORGER\\\\\\\_SOFT\\\\\\\_LIMIT\\\\\\\_OTHER`|`5` / `10`|Limit wyników `api\\\\\\\_search` dla klas / dla pozostałych typów|
|`REFORGER\\\\\\\_VIEW\\\\\\\_LIMIT`|`6`|Maksimum lokalnych widoków (wyszukiwanie lub zakres linii) jednego pliku w turze|
|`REFORGER\\\\\\\_MAX\\\\\\\_HISTORY\\\\\\\_MESSAGES`|`60`|Ile ostatnich wiadomości trafia do kontekstu|

**Zaawansowane (zwykle bez zmian):** `REFORGER\\\\\\\_FINISHED\\\\\\\_SOURCE\\\\\\\_CHARS` (`3600`), `REFORGER\\\\\\\_FINISHED\\\\\\\_EVIDENCE\\\\\\\_CHARS` (`20000`), `REFORGER\\\\\\\_COMPACT\\\\\\\_SEARCH\\\\\\\_CHARS` (`1200`), `REFORGER\\\\\\\_COMPACT\\\\\\\_OLD\\\\\\\_CHARS` (`3600`). Sterują tym, ile odczytanych źródeł zostaje w kontekście po zakończeniu tury i jak są skracane starsze wyniki, gdy kontekst się zapełnia.

### Weryfikacja i odpowiedzi awaryjne

|**Zmienna**|**Domyślnie**|**Opis**|
|-|-|-|
|`REFORGER\\\\\\\_VERIFY`|`log`|Weryfikator cytatów: `off`, `log` (tylko wpisy w logu) albo `footer` (dodatkowo znacznik pod odpowiedzią)|
|`REFORGER\\\\\\\_EMERGENCY\\\\\\\_IN\\\\\\\_HISTORY`|`placeholder`|`placeholder`: w kontekście modelu zostaje krótki znacznik zamiast treści odpowiedzi awaryjnej; `keep`: pełna treść|

## Narzędzia asystenta

Do modelu trafia wyłącznie osiem narzędzi **tylko do odczytu** z listy dozwolonych, niezależnie od tego, co udostępnia serwer MCP:

|**Narzędzie**|**Do czego służy**|
|-|-|
|`asset\\\\\\\_search`|Szukanie plików i zasobów gry po nazwie|
|`game\\\\\\\_browse`|Przeglądanie katalogów gry (wzorzec dopasowuje **nazwy plików**, nie treść)|
|`game\\\\\\\_read`|Odczyt pliku z gry; asystent potrafi też lokalnie przeszukiwać odczytany plik i pokazywać zakres linii bez ponownego wywołania MCP|
|`api\\\\\\\_search`|Szukanie klas, metod i właściwości w API skryptów|
|`component\\\\\\\_search`|Szukanie komponentów (`ScriptComponent`)|
|`wiki\\\\\\\_search`, `wiki\\\\\\\_read`|Wyszukiwanie i odczyt stron wiki|
|`wb\\\\\\\_knowledge`|Baza wiedzy modderskiej (wzorce i konwencje)|

## Jak asystent dba o wiarygodność

* Poprawia typowe błędy wywołań narzędzi i wykrywa powtórzenia oraz pętle bez nowych danych.
* Skraca długie wyniki tak, żeby zachować wszystkie deklaracje (nie ucina listy metod w połowie).
* Oznacza wyniki wyszukiwania pierwszym wierszem `\\\\\\\[Dokładne trafienie ...]` albo `\\\\\\\[BRAK DOKŁADNEGO TRAFIENIA ...]`, żeby model nie traktował podobnej nazwy jako dowodu istnienia.
* Przy pustej generacji po użyciu narzędzi ponawia próbę z niskim poziomem rozumowania, a dopiero potem składa odpowiedź awaryjną.
* Prompt wymaga odróżniania faktów zweryfikowanych od założeń, oznaczania kodu jako „z kodu gry” tylko wtedy, gdy jest przepisany dosłownie z odczytu pliku, oraz opisania, co jeszcze trzeba przetestować w grze.

### Odpowiedzi awaryjne

Stopka `\\\\\\\_\\\\\\\[Podsumowanie dostępnych wyników MCP: ...]\\\\\\\_` oznacza, że badanie przerwano (pętla bez nowych danych, limit wywołań albo pusta odpowiedź modelu), a odpowiedź złożono z tego, co zebrano. Traktuj ją jako niepełną. W kontekście kolejnych pytań taka odpowiedź jest zastępowana krótkim znacznikiem, żeby jej błędy nie wracały jako fakty.

### Weryfikator cytatów

Weryfikator sprawdza każdy blok kodu przypisany w odpowiedzi do pliku gry: czy jego linie (z pominięciem białych znaków i komentarzy) występują w tym pliku, który asystent odczytał w tej rozmowie. Zgłasza też sprzeczność w klasie bazowej (np. „`X` dziedziczy po `Y`”) oraz powołanie się na plik, którego nie odczytano. Uwagi widać w logu jako wpisy `\\\\\\\[VERIFY]`. Przykładowe ścieżki i kod własny modelu (oznaczony jako szkic lub przykład) są pomijane.

Weryfikator **nie** sprawdza wszystkiego: nie oceni np. wymyślonej wartości enuma ani opisu działania kodu w prozie.

## Dane lokalne i prywatność

* `assistant\\\\\\\_web\\\\\\\_data\\\\\\\\conversations.json`: historia czatu i metadane wywołań MCP (nazwa narzędzia, argumenty, status, czas). **Nie zapisujemy wyników narzędzi** (np. treści plików gry). Odpowiedzi asystenta zostają w historii, także gdy zawierają przytoczone fragmenty kodu gry, więc pamiętaj o licencji gry, jeśli publikujesz rozmowy.
* `assistant\\\\\\\_web\\\\\\\_data\\\\\\\\settings.json`: wybrany model i rozmiar kontekstu.
* Pełne teksty odczytanych plików są przechowywane **tylko w pamięci procesu** (dla weryfikatora i widoków lokalnych) do zamknięcia serwera.
* Logi z `START\\\\\\\_ASSISTANT\\\\\\\_WEB\\\\\\\_LOG.cmd` (`logs\\\\\\\\`) zawierają nazwy narzędzi, argumenty wywołań, diagnostykę i krótkie fragmenty z uwag weryfikatora, bez treści plików.
* Usunięcie folderu `assistant\\\\\\\_web\\\\\\\_data` czyści historię i ustawienia.

## Bezpieczeństwo

* Serwer nasłuchuje wyłącznie na `127.0.0.1`. Nie ma uwierzytelniania, więc **nie wystawiaj go do sieci** (przekierowanie portu, odwrotne proxy).
* Żądania są sprawdzane: nagłówek `Host`, nagłówek `Origin`, dla POST wymagany `Content-Type: application/json` i `X-Assistant-UI: 1`, limit rozmiaru żądania (48 KB), ścisła polityka CSP strony.
* Asystent używa wyłącznie narzędzi odczytu z listy dozwolonych; nie zapisuje do plików gry ani nie uruchamia kodu z gry.
* Dostęp do zasobów gry ma serwer MCP BK (folder z `ENFUSION\\\\\\\_GAME\\\\\\\_PATH`).

## Testy jakości

`reforger\\\\\\\_eval.py` zawiera zestaw 10 pytań i ocenę odpowiedzi według reguł (wymagane elementy, znane błędy). Pytania zadajesz sam w interfejsie, każde w osobnej rozmowie (test A ma dwa pytania w jednej rozmowie), a skrypt ocenia zapisaną historię.

```powershell
python reforger\\\\\\\_eval.py questions                       # lista 10 pytań
python reforger\\\\\\\_eval.py score                           # ocena assistant\\\\\\\_web\\\\\\\_data\\\\\\\\conversations.json
python reforger\\\\\\\_eval.py score ścieżka\\\\\\\\do\\\\\\\\pliku.json --md wyniki.md
python reforger\\\\\\\_eval.py log log.txt                     # podsumowanie logu serwera tura po turze
```

Pytania i reguły są po polsku i dobrane pod `gpt-oss:20b`. Ocena regułowa jest przybliżeniem: nie zastępuje przeczytania odpowiedzi.

## Ograniczenia

* Modele bywają w błędzie. Z naszych testów najczęstsze to wymyślone wartości (np. nieistniejące poziomy `LogLevel`), pomylenie lufy (`muzzle`) z magazynkiem, pomyłki w tym, co jest publiczne, a co prywatne, oraz kod prefabów z wymyślonymi nazwami kluczy lub identyfikatorami GUID.
* Asystent był dostrajany i testowany na `gpt-oss:20b`. Inne modele mogą działać inaczej.
* Czasem model wpada w bardzo długie rozumowanie (nawet kilkanaście tysięcy tokenów, czyli kilka minut - na razie Nie ma przycisku „Stop”.)
* Odpowiedzi są po polsku.
* Ścieżki do MCP i do gry ustawia się zmiennymi środowiskowymi (wybór w interfejsie jest w planach).

## Rozwiązywanie problemów

|**Objaw**|**Co zrobić**|
|-|-|
|`Nie znaleziono serwera MCP: ...`|Popraw `ENFUSION\\\\\\\_MCP\\\\\\\_SCRIPT` (plik `dist\\\\\\\\index.js` musi istnieć)|
|`Nie można uruchomić Node/Enfusion MCP`|Zainstaluj Node.js i upewnij się, że `node` jest w `PATH`|
|`Ollama nie odpowiada (...)`|Uruchom Ollamę albo popraw `OLLAMA\\\\\\\_CHAT\\\\\\\_URL`|
|Zmiana modelu: „nie obsługuje wywoływania narzędzi”|Wybierz model z obsługą narzędzi|
|Strona wygląda po staremu po podmianie plików|Odśwież z pominięciem pamięci podręcznej (Ctrl+F5)|
|Odpowiedź trwa bardzo długo, w logu `reason=length`|Rozumowanie zużyło limit generacji. Asystent ponawia próbę z niskim rozumowaniem. Możesz też ustawić `OLLAMA\\\\\\\_THINK=low` albo zmniejszyć `OLLAMA\\\\\\\_NUM\\\\\\\_PREDICT`|
|Stopka `\\\\\\\_\\\\\\\[Podsumowanie dostępnych wyników MCP: ...]\\\\\\\_`|Odpowiedź awaryjna, patrz [Odpowiedzi awaryjne](#odpowiedzi-awaryjne). Spróbuj zadać pytanie węziej|
|Port zajęty|Uruchom z innym portem: `--port 8766`|
|Polskie znaki rozsypane w konsoli lub logu|Uruchamiaj przez `START\\\\\\\_ASSISTANT\\\\\\\_WEB.cmd` (ustawia UTF-8)|

## Pliki

|Plik|Opis|
|-|-|
|`reforger\\\\\\\_assistant\\\\\\\_MCP\\\\\\\_BK.py`|**Silnik:** rozmowa z Ollamą, klient MCP, zabezpieczenia i weryfikator|
|`reforger\\\\\\\_helpers.py`|Zabezpieczenia dla modelu (naprawa wywołań narzędzi, skracanie wyników)|
|`reforger\\\\\\\_assistant\\\\\\\_WEB.py`|Lokalny serwer HTTP|
|`assistant.html`|Interfejs (HTML, CSS i JavaScript w jednym pliku, bez zewnętrznych bibliotek)|
|`reforger\\\\\\\_eval.py`|Zestaw testowy i ocena odpowiedzi|
|`START\\\\\\\_ASSISTANT\\\\\\\_WEB.cmd`|Uruchamianie dwuklikiem|
|`START\\\\\\\_ASSISTANT\\\\\\\_WEB\\\\\\\_LOG.cmd`|Uruchamianie z logiem do pliku w `logs\\\\\\\\`|
|`assistant\\\\\\\_web\\\\\\\_data\\\\\\\\`|Tworzony automatycznie: `conversations.json` i `settings.json`|

## Licencja i autor

Stworzone przez KUKA, na licencji MIT

(Enfusion MCP BK również na licencji MIT)



```


