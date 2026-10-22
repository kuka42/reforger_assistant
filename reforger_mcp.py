"""Klient Enfusion MCP (JSON-RPC przez stdio, tylko narzędzia odczytu) i pomocnicze funkcje schematów narzędzi."""
from __future__ import annotations

import json
import os
import queue
import subprocess
import threading
import time
from collections import deque
from pathlib import Path

from reforger_config import VERSION, MCP_SCRIPT, GAME_PATH, MCP_TIMEOUT
from reforger_rules import READ_ONLY_TOOLS


class MCPError(RuntimeError):
    pass


class MCPStdioClient:
    """Minimalny klient MCP JSON-RPC 2.0 przez stdin/stdout procesu Node.

    Uwaga: stdout na Windows to potok blokujący; wątek czyta go do kolejki,
    a wywołania request() mają rzeczywisty timeout.
    """

    def __init__(self, script: str = MCP_SCRIPT, timeout: int = MCP_TIMEOUT):
        self.script = script
        self.timeout = timeout
        self.process: subprocess.Popen | None = None
        self.responses: queue.Queue = queue.Queue()
        self.logs = deque(maxlen=30)
        self.next_id = 0
        self.tools: dict[str, dict] = {}

    def __enter__(self) -> "MCPStdioClient":
        if not Path(self.script).is_file():
            raise MCPError(f"Nie znaleziono serwera MCP: {self.script}")
        env = os.environ.copy()
        env.update({
            "ENFUSION_GAME_PATH": GAME_PATH,
        })
        try:
            self.process = subprocess.Popen(
                ["node", self.script], env=env,
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                encoding="utf-8", errors="replace", text=True, bufsize=1,
            )
        except OSError as exc:
            raise MCPError(f"Nie można uruchomić Node/Enfusion MCP: {exc}") from exc

        threading.Thread(target=self._stdout_reader, daemon=True).start()
        threading.Thread(target=self._stderr_reader, daemon=True).start()
        try:
            hello = self.request("initialize", {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "reforger-python-assistant", "version": VERSION},
            })
            if not isinstance(hello, dict) or "protocolVersion" not in hello:
                raise MCPError("Serwer nie zwrócił wersji protokołu podczas initialize")
            self._send({"jsonrpc": "2.0", "method": "notifications/initialized"})
            cursor = None
            while True:
                params = {"cursor": cursor} if cursor else {}
                listing = self.request("tools/list", params)
                for tool in listing.get("tools", []):
                    if tool.get("name") in READ_ONLY_TOOLS:
                        self.tools[tool["name"]] = tool
                cursor = listing.get("nextCursor")
                if not cursor:
                    break
            if not self.tools:
                raise MCPError("BK połączył się, ale nie udostępnia żadnego narzędzia odczytu")
            return self
        except BaseException:
            self.close()
            raise

    def _stdout_reader(self) -> None:
        assert self.process and self.process.stdout
        try:
            for line in self.process.stdout:
                try:
                    message = json.loads(line)
                except json.JSONDecodeError:
                    self.logs.append("Niepoprawny JSON z stdout MCP: " + line[:250])
                    continue
                if isinstance(message, dict):
                    self.responses.put(message)
        finally:
            self.responses.put(None)

    def _stderr_reader(self) -> None:
        assert self.process and self.process.stderr
        for line in self.process.stderr:
            self.logs.append(line.rstrip()[:500])

    def _send(self, message: dict) -> None:
        if not self.process or not self.process.stdin:
            raise MCPError("Proces MCP nie został uruchomiony")
        try:
            self.process.stdin.write(json.dumps(message, ensure_ascii=False) + "\n")
            self.process.stdin.flush()
        except (OSError, BrokenPipeError) as exc:
            raise MCPError(f"Nie można wysłać wiadomości do MCP: {exc}") from exc

    def request(self, method: str, params: dict | None = None) -> dict:
        self.next_id += 1
        request_id = self.next_id
        self._send({"jsonrpc": "2.0", "id": request_id,
                    "method": method, "params": params or {}})
        deadline = time.monotonic() + self.timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise MCPError(f"Przekroczono czas odpowiedzi MCP ({method}, {self.timeout}s)")
            try:
                msg = self.responses.get(timeout=remaining)
            except queue.Empty as exc:
                details = "; ".join(list(self.logs)[-3:])
                raise MCPError(f"MCP nie odpowiedział ({method}); {details}") from exc
            if msg is None:
                raise MCPError("Proces MCP zakończył połączenie; " + "; ".join(list(self.logs)[-3:]))
            if "method" in msg and "id" in msg:
                # Nie udostępniamy operacji od MCP do użytkownika; ping obsługujemy.
                if msg["method"] == "ping":
                    self._send({"jsonrpc": "2.0", "id": msg["id"], "result": {}})
                else:
                    self._send({"jsonrpc": "2.0", "id": msg["id"],
                                "error": {"code": -32601, "message": "Unsupported client request"}})
                continue
            if msg.get("id") != request_id:
                # Notyfikacje nie mają id; obecny klient wysyła tylko jeden request naraz.
                if "id" in msg:
                    self.logs.append(f"Pominięto nieoczekiwaną odpowiedź MCP id={msg['id']}")
                continue
            if "error" in msg:
                raise MCPError(f"MCP {method}: {msg['error']}")
            result = msg.get("result")
            if not isinstance(result, dict):
                raise MCPError(f"MCP {method} zwrócił nieoczekiwany format")
            return result

    def call_tool(self, name: str, arguments: dict) -> dict:
        if name not in self.tools:
            raise MCPError(f"Narzędzie {name!r} jest niedostępne lub niewłączone")
        if not isinstance(arguments, dict):
            raise MCPError("Argumenty narzędzia muszą być obiektem JSON")
        schema = self.tools[name].get("inputSchema", {})
        properties = schema.get("properties", {})
        required = schema.get("required", [])
        unknown = sorted(set(arguments) - set(properties))
        missing = sorted(set(required) - set(arguments))
        if unknown or missing:
            raise MCPError(f"Niepoprawne argumenty {name}: nieznane={unknown}, brak={missing}")
        return self.request("tools/call", {"name": name, "arguments": arguments})

    def close(self) -> None:
        p = self.process
        self.process = None
        if not p:
            return
        if p.stdin:
            try:
                p.stdin.close()
            except OSError:
                pass
        try:
            p.wait(timeout=2)
        except subprocess.TimeoutExpired:
            p.terminate()
            try:
                p.wait(timeout=2)
            except subprocess.TimeoutExpired:
                p.kill()
                p.wait()
        for pipe in (p.stdout, p.stderr):
            if pipe:
                try:
                    pipe.close()
                except OSError:
                    pass

    def __exit__(self, *_: object) -> None:
        self.close()


def ollama_tool_definitions(mcp_tools: dict[str, dict]) -> list[dict]:
    return [{"type": "function", "function": {
        "name": name,
        "description": tool.get("description", ""),
        "parameters": tool.get("inputSchema", {"type": "object", "properties": {}}),
    }} for name, tool in mcp_tools.items()]


def tool_schema_hint(mcp_tools: dict[str, dict], name: str) -> str:
    """Pomoc z PRAWDZIWEGO tools/list BK; nie zgadujemy nazw ani schematow."""
    if name not in mcp_tools:
        signatures = []
        for candidate, tool in sorted(mcp_tools.items()):
            schema = tool.get("inputSchema", {})
            props = schema.get("properties", {})
            required = set(schema.get("required", []))
            args = ", ".join((p + "*" if p in required else p) for p in props)
            signatures.append(f"{candidate}({args})")
        return "Dostępne narzędzia MCP (* = wymagane): " + "; ".join(signatures)[:1800]
    schema = mcp_tools[name].get("inputSchema", {})
    hint = {
        "narzedzie": name,
        "wymagane": schema.get("required", []),
        "parametry": schema.get("properties", {}),
    }
    return "Schemat parametrów z MCP: " + json.dumps(hint, ensure_ascii=False)[:3000]


def _raw_text(result: dict) -> str:
    """Pełny tekst wyniku narzędzia, bez skracania i bez dopisków."""
    chunks = []
    for item in result.get("content", []):
        if item.get("type") == "text":
            chunks.append(str(item.get("text", "")))
        else:
            chunks.append("[Pominięto wynik nie-tekstowy narzędzia]")
    # Nie dubluj tego samego kodu, gdy BK zwraca jednoczesnie content
    # i structuredContent. Dublowanie zuzywalo kontekst bez nowych faktow.
    if not chunks and "structuredContent" in result:
        chunks.append(json.dumps(result["structuredContent"], ensure_ascii=False))
    return "\n".join(chunks) or "[Brak wyniku tekstowego]"
