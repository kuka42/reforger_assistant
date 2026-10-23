#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Przegladarkowy interfejs Reforger Assistant MCP BK, bez OpenCode.

Wymaga pliku reforger_assistant_MCP_BK.py w tym samym folderze. Uzywa jego
istniejacego klienta MCP i Ollamy. Utrwala jedynie rozmowy oraz metadane wywolan narzedzi; surowe
wyniki MCP sa przechowywane w pamieci procesu, nie w historii na dysku.

Uruchom: python reforger_assistant_WEB.py
Opcje:    --port 8765 --no-browser --model gpt-oss:20b
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import re
import secrets
import sys
import threading
import time
import traceback
import urllib.error
import urllib.request
from urllib.parse import urlsplit
import webbrowser

import reforger_assistant_MCP_BK as engine

BASE = Path(__file__).resolve().parent
HTML = BASE / "assistant.html"
STORE = BASE / "assistant_web_data" / "conversations.json"
SETTINGS_STORE = BASE / "assistant_web_data" / "settings.json"
# Limity wyników narzędzi w silniku są dobrane do 32 768 tokenów, więc to jest minimum wybierane w interfejsie.
MIN_NUM_CTX = 32_768
MAX_NUM_CTX = 262_144
CTX_PRESETS = (32_768, 49_152, 65_536, 98_304, 131_072)
MODEL_NAME_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/@+\-]{0,99}")
MODELS_CACHE_TTL = 10.0
MAX_REQUEST_BYTES = 48_000
MAX_QUESTION_LENGTH = 16_000
MAX_SESSIONS = 200
MAX_TRACES = 90


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def unique_id() -> str:
    return secrets.token_hex(12)


# Odpowiedzi awaryjne (synteza bez pełnego badania) rozpoznajemy po komunikatach silnika.
EMERGENCY_MARKERS = (
    "_[Podsumowanie dostępnych wyników MCP:",
    "Model dwukrotnie zwrócił pustą odpowiedź",
    "Nie udało się zebrać żadnych potwierdzonych wyników MCP",
)


def is_emergency_answer(text: str) -> bool:
    return any(marker in text for marker in EMERGENCY_MARKERS)


def history_from_turns(turns: list[dict]) -> list[dict]:
    """Kontekst modelu odbudowany z turns (po błędzie tury albo po restarcie).

    Zgodnie z silnikiem: bez pytań, na które nie było odpowiedzi (wiszące pytanie na końcu albo pytanie
    po którym od razu jest kolejne), i - gdy REFORGER_EMERGENCY_IN_HISTORY=placeholder - bez treści
    odpowiedzi awaryjnych (wchodzi krótki placeholder), żeby ich błędy nie wracały jako fakty."""
    items = [t for t in turns if isinstance(t, dict) and t.get("role") in ("user", "assistant")]
    placeholder = getattr(engine, "EMERGENCY_PLACEHOLDER", None)
    keep = getattr(engine, "EMERGENCY_IN_HISTORY", "placeholder") == "keep"
    out = []
    for idx, turn in enumerate(items):
        if turn["role"] == "user":
            nxt = items[idx + 1] if idx + 1 < len(items) else None
            if nxt is None or nxt["role"] == "user":
                continue
        content = turn["content"]
        if turn["role"] == "assistant" and is_emergency_answer(content):
            entry = getattr(engine, "_emergency_history_entry", None)
            if callable(entry):                 # od 1.8.1: znacznik + kod z odpowiedzi (jak w silniku)
                content = entry(content)["content"]
            elif placeholder and not keep:
                content = placeholder
        out.append({"role": turn["role"], "content": content})
    return [{"role": "system", "content": engine.SYSTEM_PROMPT}] + out


def as_public_session(session: dict, detail: bool = False) -> dict:
    value = {key: session[key] for key in ("id", "title", "created_at", "updated_at")}
    value["message_count"] = len(session["turns"])
    value["busy"] = session["busy"]
    if detail:
        value["turns"] = list(session["turns"])
        value["traces"] = list(session["traces"])
    return value


class Application:
    def __init__(self, mcp: engine.MCPStdioClient, model: str, num_ctx: int):
        self.mcp = mcp
        self.model = model
        self.num_ctx = num_ctx
        self.lock = threading.RLock()
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="reforger-chat")
        self.sessions: dict[str, dict] = {}
        self.jobs: dict[str, dict] = {}
        self._models_cache: tuple[float, dict] | None = None
        self._load()

    def _load(self) -> None:
        if not STORE.exists():
            return
        try:
            payload = json.loads(STORE.read_text(encoding="utf-8"))
            records = payload.get("sessions", [])
            for item in records[:MAX_SESSIONS]:
                sid = item.get("id")
                if not isinstance(sid, str) or len(sid) != 24:
                    continue
                turns = [
                    {"role": t["role"], "content": t["content"]}
                    for t in item.get("turns", [])
                    if isinstance(t, dict) and t.get("role") in ("user", "assistant")
                    and isinstance(t.get("content"), str)
                ][-engine.MAX_HISTORY_MESSAGES:]
                traces = [t for t in item.get("traces", []) if isinstance(t, dict)][-MAX_TRACES:]
                for trace in traces:
                    if trace.get("status") == "running":      # praca przerwana (zamknięcie/awaria procesu)
                        trace["status"] = "error"
                        trace["duration_ms"] = None
                        trace["interrupted"] = True
                self.sessions[sid] = {
                    "id": sid,
                    "title": str(item.get("title", "Nowa rozmowa"))[:90],
                    "created_at": item.get("created_at", now_iso()),
                    "updated_at": item.get("updated_at", now_iso()),
                    "turns": turns,
                    "traces": traces,
                    "messages": history_from_turns(turns),
                    "busy": False,
                }
        except (OSError, ValueError, KeyError, TypeError) as exc:
            print(f"[WEB] Nie udało się odczytać historii: {exc}; rozpoczynam bez zapisanych sesji.", file=sys.stderr)

    def _save_locked(self) -> None:
        # Nigdy nie zapisujemy messages: zawieraja surowe wyniki MCP/kod gry.
        data = {"version": 1, "sessions": [
            {k: s[k] for k in ("id", "title", "created_at", "updated_at", "turns", "traces")}
            for s in self.sessions.values()
        ]}
        STORE.parent.mkdir(parents=True, exist_ok=True)
        temp = STORE.with_suffix(".tmp")
        temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        temp.replace(STORE)

    # ---------------------------------------------------------------- ustawienia (model, kontekst)
    def get_settings(self) -> dict:
        with self.lock:
            return {"model": self.model, "num_ctx": self.num_ctx, "min_ctx": MIN_NUM_CTX,
                    "max_ctx": MAX_NUM_CTX, "presets": list(CTX_PRESETS)}

    def _ollama_root(self) -> str:
        url = engine.OLLAMA_URL
        if url.endswith("/api/chat"):
            return url[: -len("/api/chat")]
        parts = urlsplit(url)
        return f"{parts.scheme}://{parts.netloc}"

    def _ollama_json(self, path: str, payload: dict | None = None, timeout: float = 3.0) -> dict:
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(self._ollama_root() + path, data=data,
                                         headers={"Content-Type": "application/json"} if data else {})
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))

    def list_models(self, force: bool = False) -> dict:
        """Modele zainstalowane w Ollamie (z krótkim cache). Adres Ollamy pochodzi wyłącznie z konfiguracji
        silnika, nigdy z żądania przeglądarki."""
        now = time.monotonic()
        with self.lock:
            if not force and self._models_cache and now - self._models_cache[0] < MODELS_CACHE_TTL:
                return self._models_cache[1]
        try:
            tags = self._ollama_json("/api/tags")
            models = []
            for item in (tags.get("models") or [])[:60]:
                name = item.get("name") or item.get("model")
                if not isinstance(name, str) or not MODEL_NAME_RE.fullmatch(name):
                    continue
                details = item.get("details") or {}
                tools, completion = None, True
                try:      # nowsze wersje Ollamy podają możliwości modelu
                    caps = self._ollama_json("/api/show", {"model": name}).get("capabilities")
                    if isinstance(caps, list):
                        tools = "tools" in caps
                        completion = "completion" in caps
                except (OSError, ValueError):
                    pass
                if not completion:
                    continue      # np. modele wyłącznie do osadzeń (embeddings)
                size = item.get("size")
                models.append({"name": name, "params": details.get("parameter_size") or "",
                               "size_gb": round(size / 1e9, 1) if isinstance(size, (int, float)) else None,
                               "tools": tools})
            result = {"ok": True, "models": sorted(models, key=lambda m: m["name"].lower()), "error": None}
        except (OSError, ValueError) as exc:     # URLError, timeout, zły JSON
            result = {"ok": False, "models": [], "error": f"Ollama nie odpowiada ({exc})"}
        with self.lock:
            self._models_cache = (now, result)
        return result

    def update_settings(self, data: dict) -> dict:
        new_model, new_ctx = data.get("model"), data.get("num_ctx")
        if new_model is None and new_ctx is None:
            raise UserError(400, "Brak zmian: podaj model lub num_ctx")
        if new_model is not None:
            if not isinstance(new_model, str) or not MODEL_NAME_RE.fullmatch(new_model):
                raise UserError(400, "Nieprawidłowa nazwa modelu")
            listing = self.list_models(force=True)
            if not listing["ok"]:
                raise UserError(503, "Ollama nie odpowiada, nie można zmienić modelu: " + str(listing["error"]))
            found = next((m for m in listing["models"] if m["name"] == new_model), None)
            if not found:
                raise UserError(400, f"Model '{new_model}' nie jest zainstalowany w Ollamie (ollama pull {new_model})")
            if found["tools"] is False:
                raise UserError(400, f"Model '{new_model}' nie obsługuje wywoływania narzędzi, a asystent ich potrzebuje")
        if new_ctx is not None:
            if isinstance(new_ctx, bool) or not isinstance(new_ctx, int) or not MIN_NUM_CTX <= new_ctx <= MAX_NUM_CTX:
                raise UserError(400, f"Kontekst musi być liczbą całkowitą od {MIN_NUM_CTX} do {MAX_NUM_CTX}")
        with self.lock:
            model = new_model if new_model is not None else self.model
            num_ctx = new_ctx if new_ctx is not None else self.num_ctx
            try:
                self._save_settings({"version": 1, "model": model, "num_ctx": num_ctx})
            except OSError as exc:
                raise UserError(500, f"Nie udało się zapisać ustawień: {exc}") from exc
            self.model, self.num_ctx = model, num_ctx
            self._models_cache = None
            return self.get_settings()

    @staticmethod
    def _save_settings(payload: dict) -> None:
        SETTINGS_STORE.parent.mkdir(parents=True, exist_ok=True)
        temp = SETTINGS_STORE.with_suffix(".tmp")
        temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        temp.replace(SETTINGS_STORE)

    def list_sessions(self) -> list[dict]:
        with self.lock:
            return [as_public_session(s) for s in sorted(
                self.sessions.values(), key=lambda s: s["updated_at"], reverse=True
            )]

    def create_session(self) -> dict:
        with self.lock:
            if len(self.sessions) >= MAX_SESSIONS:
                raise UserError(409, "Osiągnięto limit rozmów. Usuń starszą rozmowę.")
            sid = unique_id()
            s = {"id": sid, "title": "Nowa rozmowa", "created_at": now_iso(),
                 "updated_at": now_iso(), "turns": [], "traces": [],
                 "messages": [{"role": "system", "content": engine.SYSTEM_PROMPT}],
                 "busy": False}
            self.sessions[sid] = s
            self._save_locked()
            return as_public_session(s, detail=True)

    def get_session(self, sid: str) -> dict:
        with self.lock:
            s = self.sessions.get(sid)
            if not s:
                raise UserError(404, "Nie znaleziono rozmowy")
            return as_public_session(s, detail=True)

    def delete_session(self, sid: str) -> None:
        with self.lock:
            s = self.sessions.get(sid)
            if not s:
                raise UserError(404, "Nie znaleziono rozmowy")
            if s["busy"]:
                raise UserError(409, "Nie można usunąć rozmowy podczas generowania odpowiedzi")
            del self.sessions[sid]
            self._save_locked()

    def submit(self, sid: str, question: str) -> dict:
        question = question.strip()
        if not question or len(question) > MAX_QUESTION_LENGTH:
            raise UserError(400, f"Wiadomość musi mieć 1–{MAX_QUESTION_LENGTH} znaków")
        with self.lock:
            s = self.sessions.get(sid)
            if not s:
                raise UserError(404, "Nie znaleziono rozmowy")
            if s["busy"]:
                raise UserError(409, "Poczekaj na zakończenie bieżącej odpowiedzi w tej rozmowie")
            s["busy"] = True
            s["turns"].append({"role": "user", "content": question})
            if s["title"] == "Nowa rozmowa":
                s["title"] = " ".join(question.split())[:65] or "Nowa rozmowa"
            s["updated_at"] = now_iso()
            job_id = unique_id()
            job = {"id": job_id, "session_id": sid, "status": "queued", "phase": "Oczekiwanie na model",
                   "answer": None, "error": None, "tool_events": [], "created_at": now_iso()}
            self.jobs[job_id] = job
            # Ograniczamy zapamietane joby; metadane narzedzi sa tez w sesji.
            if len(self.jobs) > 250:
                for key in list(self.jobs):
                    if len(self.jobs) <= 200:
                        break
                    if self.jobs[key]["status"] in ("done", "error"):
                        del self.jobs[key]
            self._save_locked()
            self.executor.submit(self._run_job, job_id, question)
            return {"job_id": job_id, "status": "queued"}

    def _run_job(self, job_id: str, question: str) -> None:
        with self.lock:
            job = self.jobs[job_id]
            session = self.sessions[job["session_id"]]
            job["status"] = "running"
            model, num_ctx = self.model, self.num_ctx      # zmiana ustawień w trakcie pracy dotyczy następnych pytań

        app = self

        class ObservableMCP:
            tools = app.mcp.tools

            def call_tool(self, name: str, arguments: dict) -> dict:
                event = {"id": unique_id(), "job_id": job_id, "name": name,
                         "arguments": arguments, "status": "running", "duration_ms": None,
                         "started_at": now_iso()}
                with app.lock:
                    job["tool_events"].append(event)
                    session["traces"].append(event)
                    session["traces"] = session["traces"][-MAX_TRACES:]
                started = time.monotonic()
                try:
                    result = app.mcp.call_tool(name, arguments)
                    status = "error" if result.get("isError") else "done"
                    return result
                except Exception:
                    status = "error"
                    raise
                finally:
                    with app.lock:
                        event["status"] = status
                        event["duration_ms"] = round((time.monotonic() - started) * 1000)

        def on_phase(text: str) -> None:
            with self.lock:
                job["phase"] = text

        try:
            # Tylko jeden worker korzysta z MCP stdio, zeby nie pomieszac JSON-RPC.
            answer = engine.ask(question, session["messages"], ObservableMCP(),
                                model, num_ctx, on_phase=on_phase)
            with self.lock:
                session["turns"].append({"role": "assistant", "content": answer})
                # Zachowaj zweryfikowane wyniki MCP w RAM kolejnych pytań.
                # engine.ask już kompaktuje kontekst i zakończoną historię.
                # Na dysku zapisujemy wyłącznie turns i metadane (jak wcześniej).
                # Po restarcie aplikacji surowe wyniki MCP nie są odtwarzane.
                job["status"] = "done"
                job["phase"] = "Gotowe"
                job["answer"] = answer
        except Exception as exc:
            with self.lock:
                job["status"] = "error"
                job["phase"] = "Błąd"
                job["error"] = str(exc)[:2000]
                # Po niepelnej turze nie pozostawiaj niezamknietych tool_calls.
                session["messages"] = history_from_turns(session["turns"])
            print(f"[WEB] Błąd rozmowy: {exc}", file=sys.stderr)
        finally:
            with self.lock:
                session["busy"] = False
                session["updated_at"] = now_iso()
                try:
                    self._save_locked()
                except OSError as exc:
                    print(f"[WEB] Nie udało się zapisać historii: {exc}", file=sys.stderr)

    def get_job(self, jid: str) -> dict:
        with self.lock:
            job = self.jobs.get(jid)
            if not job:
                raise UserError(404, "Nie znaleziono zadania")
            return {**job, "tool_events": [dict(event) for event in job["tool_events"]]}

    def close(self) -> None:
        self.executor.shutdown(wait=True, cancel_futures=False)


class UserError(Exception):
    def __init__(self, code: int, text: str):
        super().__init__(text)
        self.code = code


def make_handler(app: Application, port: int):
    class Handler(BaseHTTPRequestHandler):
        server_version = "ReforgerAssistantWeb/1.0"

        def log_message(self, fmt: str, *args: object) -> None:
            # Ogranicz logowanie co-polsekundowych zapytan o status.
            if "/api/jobs/" not in self.path:
                super().log_message(fmt, *args)

        def _safe_host(self) -> bool:
            host = self.headers.get("Host", "")
            return host in (f"127.0.0.1:{port}", f"localhost:{port}")

        def _safe_origin(self) -> bool:
            origin = self.headers.get("Origin")
            return not origin or origin in (f"http://127.0.0.1:{port}", f"http://localhost:{port}")

        def _json(self, code: int, value: dict | list) -> None:
            raw = json.dumps(value, ensure_ascii=False).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(raw)

        def _html(self) -> None:
            try:
                raw = HTML.read_bytes()
            except OSError:
                self._json(500, {"error": f"Brak pliku {HTML.name} obok Pythona"})
                return
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; base-uri 'none'; form-action 'none'")
            self.end_headers()
            self.wfile.write(raw)

        def _read_json(self) -> dict:
            try:
                size = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                raise UserError(400, "Nieprawidłowy rozmiar żądania")
            if size < 0 or size > MAX_REQUEST_BYTES:
                raise UserError(413, "Za duże żądanie")
            if self.headers.get("Content-Type", "").split(";")[0].strip() != "application/json":
                raise UserError(415, "Wymagany Content-Type: application/json")
            if self.headers.get("X-Assistant-UI") != "1":
                raise UserError(403, "Brakuje nagłówka lokalnego interfejsu")
            try:
                data = json.loads(self.rfile.read(size).decode("utf-8"))
            except (ValueError, UnicodeError):
                raise UserError(400, "Nieprawidłowy JSON")
            if not isinstance(data, dict):
                raise UserError(400, "Wymagany obiekt JSON")
            return data

        def _dispatch_get(self, path: str) -> None:
            if path in ("/", "/assistant.html"):
                self._html()
            elif path == "/api/settings":
                self._json(200, app.get_settings())
            elif path == "/api/models":
                self._json(200, app.list_models())
            elif path == "/api/bootstrap":
                self._json(200, {"version": engine.VERSION, "model": app.model, "settings": app.get_settings(),
                                 "tools": list(app.mcp.tools), "sessions": app.list_sessions(),
                                 "status": "connected", "read_only": True})
            elif path.startswith("/api/sessions/"):
                self._json(200, app.get_session(path.removeprefix("/api/sessions/")))
            elif path.startswith("/api/jobs/"):
                self._json(200, app.get_job(path.removeprefix("/api/jobs/")))
            else:
                raise UserError(404, "Nie znaleziono ścieżki")

        def _dispatch_post(self, path: str, data: dict) -> None:
            if path == "/api/settings":
                self._json(200, app.update_settings(data))
            elif path == "/api/sessions":
                self._json(201, app.create_session())
            elif path.startswith("/api/sessions/") and path.endswith("/chat"):
                sid = path.removeprefix("/api/sessions/").removesuffix("/chat")
                if not isinstance(data.get("text"), str):
                    raise UserError(400, "Brak tekstu wiadomości")
                self._json(202, app.submit(sid, data["text"]))
            elif path.startswith("/api/sessions/") and path.endswith("/delete"):
                sid = path.removeprefix("/api/sessions/").removesuffix("/delete")
                app.delete_session(sid)
                self._json(200, {"ok": True})
            else:
                raise UserError(404, "Nie znaleziono ścieżki")

        def do_GET(self) -> None:
            if not self._safe_host():
                self._json(403, {"error": "Nieprawidłowy host"})
                return
            try:
                self._dispatch_get(urlsplit(self.path).path)
            except UserError as exc:
                self._json(exc.code, {"error": str(exc)})
            except Exception as exc:  # noqa: BLE001 - serwer nie może zrywać połączenia bez odpowiedzi
                self._internal_error(exc)

        def do_POST(self) -> None:
            if not self._safe_host() or not self._safe_origin():
                self._json(403, {"error": "Żądanie spoza lokalnego interfejsu"})
                return
            try:
                data = self._read_json()
                self._dispatch_post(urlsplit(self.path).path, data)
            except UserError as exc:
                self._json(exc.code, {"error": str(exc)})
            except OSError as exc:
                self._json(500, {"error": f"Błąd zapisu historii: {exc}"})
            except Exception as exc:  # noqa: BLE001
                self._internal_error(exc)

        def _internal_error(self, exc: Exception) -> None:
            print(f"[WEB] Nieoczekiwany błąd obsługi {self.command} {self.path}: {exc!r}", file=sys.stderr)
            traceback.print_exc()
            try:
                self._json(500, {"error": "Błąd wewnętrzny serwera (szczegóły w konsoli)"})
            except OSError:
                pass

    return Handler


def load_saved_settings() -> dict:
    """Zapisane ustawienia z interfejsu; uszkodzony lub niepełny plik jest ignorowany."""
    try:
        data = json.loads(SETTINGS_STORE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    out: dict = {}
    if isinstance(data, dict):
        if isinstance(data.get("model"), str) and MODEL_NAME_RE.fullmatch(data["model"]):
            out["model"] = data["model"]
        ctx = data.get("num_ctx")
        if isinstance(ctx, int) and not isinstance(ctx, bool) and MIN_NUM_CTX <= ctx <= MAX_NUM_CTX:
            out["num_ctx"] = ctx
    return out


def resolve_startup_settings(cli_model, cli_ctx, saved: dict) -> tuple[str, int, str]:
    """Pierwszeństwo: argumenty wiersza poleceń > ustawienia zapisane w interfejsie > zmienne środowiskowe/domyślne.
    Zwraca (model, num_ctx, opis źródła). Argumenty nie nadpisują pliku ustawień."""
    model = cli_model or saved.get("model") or engine.MODEL
    num_ctx = cli_ctx or saved.get("num_ctx") or engine.NUM_CTX
    sources = []
    sources.append("argument" if cli_model else "plik ustawień" if saved.get("model") else "domyślny/środowisko")
    sources.append("argument" if cli_ctx else "plik ustawień" if saved.get("num_ctx") else "domyślny/środowisko")
    return model, num_ctx, f"model: {sources[0]}, kontekst: {sources[1]}"


def main() -> int:
    parser = argparse.ArgumentParser(description="Reforger Assistant - przegladarka + MCP BK")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-browser", action="store_true", help="nie otwieraj przegladarki automatycznie")
    parser.add_argument("--model", default=None, help="model Ollamy (nadpisuje zapisane ustawienia tylko na tę sesję)")
    parser.add_argument("--num-ctx", type=int, default=None, help="rozmiar kontekstu (jak wyżej)")
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("--port musi być z zakresu 1–65535")
    if not HTML.is_file():
        print(f"Brak {HTML.name} w folderze {BASE}", file=sys.stderr)
        return 1
    print("REFORGER ASSISTANT WEB | MCP BK tylko do odczytu | silnik", engine.VERSION)
    try:
        with engine.MCPStdioClient() as mcp:
            print("Połączono z BK:", ", ".join(mcp.tools))
            model, num_ctx, source = resolve_startup_settings(args.model, args.num_ctx, load_saved_settings())
            print(f"Model: {model} | kontekst: {num_ctx} ({source})")
            app = Application(mcp, model, num_ctx)
            try:
                server = ThreadingHTTPServer(("127.0.0.1", args.port), make_handler(app, args.port))
                server.daemon_threads = True
                url = f"http://127.0.0.1:{args.port}"
                print("Otwórz:", url)
                print("Zatrzymaj serwer: Ctrl+C. Historia: assistant_web_data/conversations.json")
                if not args.no_browser:
                    threading.Timer(0.45, lambda: webbrowser.open(url)).start()
                try:
                    server.serve_forever(poll_interval=0.3)
                except KeyboardInterrupt:
                    print("\nZamykanie serwera...")
                finally:
                    server.server_close()
            finally:
                app.close()
    except (engine.MCPError, OSError) as exc:
        print(f"BŁĄD: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
