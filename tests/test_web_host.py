from http.server import HTTPServer
import json
from pathlib import Path
import threading
import unittest
import urllib.error
import urllib.request

from tac_sandbox.web_host import BrowserHost, _build_handler


SCENARIO_PATH = Path(__file__).resolve().parents[1] / "scenarios" / "ship_duel.toml"


class BrowserHostApiTests(unittest.TestCase):
    def setUp(self) -> None:
        app = BrowserHost(SCENARIO_PATH)
        self.server = HTTPServer(("127.0.0.1", 0), _build_handler(app))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        host, port = self.server.server_address
        self.base_url = f"http://{host}:{port}"

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    def test_plot_rejects_malformed_json(self) -> None:
        error = self._post_error("/api/plot", b"{bad")

        self.assertEqual(error.code, 400)
        self.assertEqual(
            json.loads(error.read().decode("utf-8")),
            {"error": "invalid JSON: Expecting property name enclosed in double quotes"},
        )

    def test_plot_rejects_non_object_json(self) -> None:
        error = self._post_error("/api/plot", b"[]")

        self.assertEqual(error.code, 400)
        self.assertEqual(
            json.loads(error.read().decode("utf-8")),
            {"error": "request body must be a JSON object"},
        )

    def _post_error(self, path: str, body: bytes) -> urllib.error.HTTPError:
        request = urllib.request.Request(
            f"{self.base_url}{path}",
            data=body,
            headers={"Content-Type": "application/json"},
        )
        with self.assertRaises(urllib.error.HTTPError) as context:
            urllib.request.urlopen(request)
        self.addCleanup(context.exception.close)
        return context.exception
