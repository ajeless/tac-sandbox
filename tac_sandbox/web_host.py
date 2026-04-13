from __future__ import annotations

import argparse
import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import urlparse

from .engine import advance, load_scenario, start_session, submit_input
from .presentation import present_session


STATIC_DIR = Path(__file__).with_name("static")


class BrowserHost:
    def __init__(self, scenario_path: Path) -> None:
        self.scenario = load_scenario(scenario_path)
        self.session = start_session(self.scenario)

    def snapshot(self) -> dict:
        return present_session(self.scenario, self.session)

    def reset(self) -> dict:
        self.session = start_session(self.scenario)
        return {"status": "reset"}

    def step(self) -> dict:
        return advance(self.scenario, self.session)

    def plot(self, data: dict) -> dict:
        return submit_input(self.scenario, self.session, data)


def main() -> int:
    parser = argparse.ArgumentParser(description="Minimal browser host for the current spike")
    parser.add_argument(
        "scenario",
        nargs="?",
        default="scenarios/ship_duel.toml",
        help="path to a scenario TOML file",
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    try:
        app = BrowserHost(Path(args.scenario))
    except ValueError as exc:
        print(f"error: {exc}")
        return 1
    handler_class = _build_handler(app)
    server = HTTPServer((args.host, args.port), handler_class)
    print(f"Serving {app.scenario['title']} on http://{args.host}:{args.port}")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping browser host")
    finally:
        server.server_close()

    return 0


def _build_handler(app: BrowserHost) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            path = urlparse(self.path).path
            if path in {"/", "/index.html"}:
                self._send_html((STATIC_DIR / "index.html").read_text(encoding="utf-8"))
                return
            if path == "/api/state":
                self._send_json({"snapshot": app.snapshot()})
                return
            self._send_json({"error": "not found"}, status=404)

        def do_POST(self) -> None:
            path = urlparse(self.path).path
            data = self._read_json()

            if path == "/api/plot":
                result = app.plot(data)
                self._send_json({"result": result, "snapshot": app.snapshot()})
                return
            if path == "/api/step":
                result = app.step()
                self._send_json({"result": result, "snapshot": app.snapshot()})
                return
            if path == "/api/reset":
                result = app.reset()
                self._send_json({"result": result, "snapshot": app.snapshot()})
                return

            self._send_json({"error": "not found"}, status=404)

        def log_message(self, format: str, *args: object) -> None:
            return

        def _read_json(self) -> dict:
            length = int(self.headers.get("Content-Length", "0"))
            if length == 0:
                return {}
            raw = self.rfile.read(length).decode("utf-8")
            return json.loads(raw)

        def _send_html(self, body: str, status: int = 200) -> None:
            encoded = body.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def _send_json(self, payload: dict, status: int = 200) -> None:
            encoded = json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

    return Handler


if __name__ == "__main__":
    raise SystemExit(main())
