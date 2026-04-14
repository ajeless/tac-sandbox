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

    def test_state_exposes_editable_runtime_config(self) -> None:
        data = self._get_json("/api/state")

        self.assertEqual(data["snapshot"]["presentation"]["unit_scale"], 1.5)
        self.assertEqual(data["snapshot"]["config"]["space"]["footprint"], "radius")
        self.assertEqual(
            [unit["id"] for unit in data["snapshot"]["config"]["units"]],
            ["red_1", "blue_1"],
        )

    def test_apply_scenario_restarts_session_with_runtime_overrides(self) -> None:
        config = self._get_json("/api/state")["snapshot"]["config"]

        self._post_json("/api/plot", {"unit": "red_1", "heading": 3, "speed": 1})
        self._post_json("/api/plot", {"unit": "blue_1", "heading": 0, "speed": 1})
        self._post_json("/api/step", {})

        config["presentation"]["unit_scale"] = 2.2
        config["units"][0]["at"] = [1, -3]
        config["units"][0]["shield"] = 5

        data = self._post_json("/api/apply_scenario", config)

        self.assertEqual(data["result"], {"status": "scenario_applied"})
        self.assertEqual(
            data["snapshot"]["turn"],
            {"number": 1, "phase": "plot_heading_speed"},
        )
        self.assertEqual(data["snapshot"]["presentation"]["unit_scale"], 2.2)
        self.assertEqual(data["snapshot"]["entities"][0]["at"], [1, -3])
        self.assertEqual(data["snapshot"]["entities"][0]["stats"]["shield"], 5)
        self.assertEqual(data["snapshot"]["recent_events"], [])

    def test_apply_scenario_rejects_invalid_runtime_config_without_mutation(self) -> None:
        config = self._get_json("/api/state")["snapshot"]["config"]
        config["presentation"]["unit_scale"] = 0

        data = self._post_json("/api/apply_scenario", config)

        self.assertEqual(
            data["result"],
            {
                "status": "rejected",
                "errors": ["presentation.unit_scale must be greater than 0"],
            },
        )
        self.assertEqual(data["snapshot"]["presentation"]["unit_scale"], 1.5)
        self.assertEqual(data["snapshot"]["turn"]["phase"], "plot_heading_speed")

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

    def _get_json(self, path: str) -> dict:
        with urllib.request.urlopen(f"{self.base_url}{path}") as response:
            return json.load(response)

    def _post_json(self, path: str, payload: dict) -> dict:
        request = urllib.request.Request(
            f"{self.base_url}{path}",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(request) as response:
            return json.load(response)
