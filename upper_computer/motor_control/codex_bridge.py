"""Local, authenticated debug bridge for Codex and other diagnostic tools.

The bridge runs inside Motor Studio so the GUI remains the sole owner of the
serial port.  HTTP worker threads never touch Tk objects directly: every
request is dispatched onto the Tk main thread.
"""

import json
import os
from pathlib import Path
import secrets
import socketserver
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, Callable, Dict, Optional
from urllib.parse import parse_qs, urlparse


BRIDGE_SCHEMA = 1
DEFAULT_MANIFEST = Path(
    os.environ.get("MOTOR_STUDIO_BRIDGE_FILE")
    or (Path(tempfile.gettempdir()) / "motor-studio-codex-bridge.json")
)
MAX_REQUEST_BYTES = 64 * 1024


class BridgeRequestError(Exception):
    """An error that should be returned to the local API caller."""

    def __init__(self, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.status = int(status)


class _ThreadingHttpServer(socketserver.ThreadingMixIn, HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


class _BridgeRequestHandler(BaseHTTPRequestHandler):
    server_version = "MotorStudioCodexBridge/1"
    protocol_version = "HTTP/1.1"

    def log_message(self, _format: str, *args: Any) -> None:
        # Requests are exposed in Motor Studio's own communication log.
        return

    @property
    def bridge(self) -> "CodexBridge":
        return self.server.bridge  # type: ignore[attr-defined]

    def _write_json(self, status: int, payload: Dict[str, Any]) -> None:
        body = json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def _authenticated(self) -> bool:
        supplied = self.headers.get("Authorization", "")
        expected = "Bearer {}".format(self.bridge.token)
        return secrets.compare_digest(supplied, expected)

    def _read_payload(self) -> Dict[str, Any]:
        raw_length = self.headers.get("Content-Length", "0")
        try:
            length = int(raw_length)
        except ValueError:
            raise BridgeRequestError("invalid Content-Length")
        if length < 0 or length > MAX_REQUEST_BYTES:
            raise BridgeRequestError("request body is too large", 413)
        if length == 0:
            return {}
        try:
            value = json.loads(self.rfile.read(length).decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            raise BridgeRequestError("request body must be valid UTF-8 JSON")
        if not isinstance(value, dict):
            raise BridgeRequestError("request body must be a JSON object")
        return value

    @staticmethod
    def _first(query: Dict[str, Any], key: str, default: Any) -> Any:
        values = query.get(key)
        return values[0] if values else default

    def _route_get(self, path: str, query: Dict[str, Any]) -> Any:
        if path == "/v1/status":
            return self.bridge.dispatch("status", {})
        if path == "/v1/logs":
            return self.bridge.dispatch(
                "logs",
                {"limit": self._first(query, "limit", "200")},
            )
        if path == "/v1/history":
            return self.bridge.dispatch(
                "history",
                {
                    "seconds": self._first(query, "seconds", "5"),
                    "limit": self._first(query, "limit", "500"),
                },
            )
        if path == "/v1/ports":
            return self.bridge.dispatch("ports", {})
        if path == "/v1/arm":
            return self.bridge.dispatch("arm_status", {})
        prefix = "/v1/transactions/"
        if path.startswith(prefix):
            return self.bridge.dispatch(
                "transaction",
                {"sequence": path[len(prefix):]},
            )
        raise BridgeRequestError("unknown endpoint", 404)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/v1/health":
            self._write_json(
                200,
                {
                    "ok": True,
                    "result": {
                        "service": "motor-studio-codex-bridge",
                        "schema": BRIDGE_SCHEMA,
                    },
                },
            )
            return
        if not self._authenticated():
            self._write_json(401, {"ok": False, "error": "unauthorized"})
            return
        try:
            result = self._route_get(parsed.path, parse_qs(parsed.query))
        except BridgeRequestError as exc:
            self._write_json(exc.status, {"ok": False, "error": str(exc)})
        except Exception as exc:
            self._write_json(500, {"ok": False, "error": str(exc)})
        else:
            self._write_json(200, {"ok": True, "result": result})

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if not self._authenticated():
            self._write_json(401, {"ok": False, "error": "unauthorized"})
            return
        prefix = "/v1/actions/"
        if not parsed.path.startswith(prefix):
            self._write_json(404, {"ok": False, "error": "unknown endpoint"})
            return
        action = parsed.path[len(prefix):].strip("/")
        if not action:
            self._write_json(404, {"ok": False, "error": "missing action"})
            return
        try:
            result = self.bridge.dispatch(action, self._read_payload())
        except BridgeRequestError as exc:
            self._write_json(exc.status, {"ok": False, "error": str(exc)})
        except Exception as exc:
            self._write_json(500, {"ok": False, "error": str(exc)})
        else:
            self._write_json(200, {"ok": True, "result": result})


class CodexBridge:
    """Authenticated localhost server sharing Motor Studio's Tk main thread."""

    def __init__(
        self,
        root: Any,
        action_handler: Callable[[str, Dict[str, Any]], Any],
        manifest_path: Optional[Path] = None,
        dispatch_timeout: float = 5.0,
    ) -> None:
        self.root = root
        self.action_handler = action_handler
        self.manifest_path = Path(manifest_path or DEFAULT_MANIFEST)
        self.dispatch_timeout = float(dispatch_timeout)
        self.token = secrets.token_hex(24)
        self.started_at = time.time()
        self._server = None  # type: Optional[_ThreadingHttpServer]
        self._thread = None  # type: Optional[threading.Thread]

    @property
    def running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    @property
    def port(self) -> int:
        if self._server is None:
            return 0
        return int(self._server.server_address[1])

    def start(self) -> None:
        if self.running:
            return
        server = _ThreadingHttpServer(("127.0.0.1", 0), _BridgeRequestHandler)
        server.bridge = self  # type: ignore[attr-defined]
        self._server = server
        self._thread = threading.Thread(
            target=server.serve_forever,
            name="motor-codex-bridge",
            daemon=True,
        )
        self._thread.start()
        self._write_manifest()

    def _write_manifest(self) -> None:
        value = {
            "schema": BRIDGE_SCHEMA,
            "pid": os.getpid(),
            "host": "127.0.0.1",
            "port": self.port,
            "token": self.token,
            "started_at": self.started_at,
        }
        self.manifest_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.manifest_path.with_suffix(
            self.manifest_path.suffix + ".tmp"
        )
        with temporary.open("w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
        os.replace(str(temporary), str(self.manifest_path))
        try:
            os.chmod(str(self.manifest_path), 0o600)
        except OSError:
            pass

    def dispatch(self, action: str, params: Dict[str, Any]) -> Any:
        completed = threading.Event()
        result = {}  # type: Dict[str, Any]

        def invoke() -> None:
            try:
                result["value"] = self.action_handler(action, params)
            except Exception as exc:
                result["error"] = exc
            finally:
                completed.set()

        try:
            self.root.after(0, invoke)
        except Exception:
            raise BridgeRequestError("Motor Studio is shutting down", 503)
        if not completed.wait(self.dispatch_timeout):
            raise BridgeRequestError(
                "Motor Studio main thread did not respond in time",
                503,
            )
        error = result.get("error")
        if error is not None:
            if isinstance(error, BridgeRequestError):
                raise error
            raise BridgeRequestError(str(error))
        return result.get("value")

    def stop(self) -> None:
        server = self._server
        if server is not None:
            server.shutdown()
            server.server_close()
        if self._thread and self._thread.is_alive():
            self._thread.join(1.0)
        self._server = None
        self._thread = None
        self._remove_manifest()

    def _remove_manifest(self) -> None:
        try:
            with self.manifest_path.open("r", encoding="utf-8") as stream:
                current = json.load(stream)
            if current.get("token") == self.token:
                self.manifest_path.unlink()
        except (OSError, ValueError):
            pass
