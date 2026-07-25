"""A minimal MCP stdio client (JSON-RPC 2.0 over newline-delimited stdio).

Launches an MCP server subprocess, performs the ``initialize`` handshake, and
exposes ``list_tools`` / ``call_tool``. Used by the gateway to talk to the mock
DataHub MCP server, but it will speak to any newline-delimited JSON-RPC MCP
server the same way.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from typing import Any

PROTOCOL_VERSION = "2024-11-05"
CLIENT_INFO = {"name": "datahub-steward-squad", "version": "0.1.0"}


class MCPError(RuntimeError):
    pass


class MCPStdioClient:
    """Speaks MCP JSON-RPC to a server subprocess over stdin/stdout.

    ``env`` overrides/extends the child process environment (merged over the
    current ``os.environ``). This is how the live gateway passes
    ``DATAHUB_GMS_URL`` / ``DATAHUB_GMS_TOKEN`` / ``TOOLS_IS_MUTATION_ENABLED``
    to the real ``uvx mcp-server-datahub`` process. The mock path leaves it
    ``None`` and inherits the parent environment unchanged.
    """

    def __init__(
        self,
        command: list[str],
        cwd: str | None = None,
        env: dict[str, str] | None = None,
    ) -> None:
        self.command = command
        self.cwd = cwd
        self.env = env
        self._process: subprocess.Popen | None = None
        self._next_id = 0

    # -- lifecycle -------------------------------------------------------
    def __enter__(self) -> "MCPStdioClient":
        self.start()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def start(self) -> dict[str, Any]:
        child_env = None
        if self.env is not None:
            child_env = {**os.environ, **self.env}
        self._process = subprocess.Popen(
            self.command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=sys.stderr,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            cwd=self.cwd,
            env=child_env,
        )
        init = self._request(
            "initialize",
            {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": CLIENT_INFO,
            },
        )
        self._notify("notifications/initialized", {})
        return init

    def close(self) -> None:
        if self._process is None:
            return
        process = self._process
        try:
            if process.stdin:
                process.stdin.close()
            process.wait(timeout=5)
        except Exception:  # pragma: no cover - best-effort teardown
            process.kill()
        finally:
            for stream in (process.stdout, process.stdin):
                try:
                    if stream and not stream.closed:
                        stream.close()
                except Exception:
                    pass
            self._process = None

    # -- MCP methods -----------------------------------------------------
    def list_tools(self) -> list[dict[str, Any]]:
        result = self._request("tools/list", {})
        return result.get("tools", [])

    def call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> Any:
        result = self._request("tools/call", {"name": name, "arguments": arguments or {}})
        content = result.get("content", [])
        text = "".join(block.get("text", "") for block in content if block.get("type") == "text")
        if result.get("isError"):
            raise MCPError(f"Tool '{name}' failed: {text}")
        if not text:
            return None
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return text

    # -- transport -------------------------------------------------------
    def _request(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        if self._process is None or self._process.stdin is None or self._process.stdout is None:
            raise MCPError("MCP client is not started")
        self._next_id += 1
        request_id = self._next_id
        self._process.stdin.write(
            json.dumps({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params}) + "\n"
        )
        self._process.stdin.flush()

        while True:
            line = self._process.stdout.readline()
            if not line:
                raise MCPError(f"MCP server closed the connection during '{method}'")
            line = line.strip()
            if not line:
                continue
            message = json.loads(line)
            if message.get("id") != request_id:
                continue  # skip notifications / other ids
            if "error" in message:
                raise MCPError(f"{method} error: {message['error']}")
            return message.get("result", {})

    def _notify(self, method: str, params: dict[str, Any]) -> None:
        if self._process is None or self._process.stdin is None:
            raise MCPError("MCP client is not started")
        self._process.stdin.write(
            json.dumps({"jsonrpc": "2.0", "method": method, "params": params}) + "\n"
        )
        self._process.stdin.flush()
