from pathlib import Path
import unittest

from tac_sandbox.engine import advance, load_scenario, start_session, submit_input


SCENARIO_PATH = Path(__file__).resolve().parents[1] / "scenarios" / "ship_duel.toml"


def fresh_session() -> tuple[dict, dict]:
    scenario = load_scenario(SCENARIO_PATH)
    return scenario, start_session(scenario)


class EngineFlowTests(unittest.TestCase):
    def test_sample_scenario_uses_circular_hex_surface(self) -> None:
        scenario, _session = fresh_session()

        self.assertEqual(scenario["space"]["orientation"], "flat_top")
        self.assertEqual(scenario["space"]["footprint"], "radius")
        self.assertEqual(scenario["space"]["center"], [0, 0])
        self.assertEqual(scenario["space"]["radius"], 6)
        self.assertEqual(scenario["heading"]["model"], "discrete_6")
        self.assertEqual(scenario["heading"]["zero"], "north")
        self.assertEqual(scenario["heading"]["rotation"], "clockwise")

    def test_advance_requires_all_active_plots(self) -> None:
        scenario, session = fresh_session()

        submit_input(scenario, session, {"unit": "red_1", "heading": 3, "speed": 1})
        result = advance(scenario, session)

        self.assertEqual(result["status"], "awaiting_input")
        self.assertEqual(result["phase"], "plot_heading_speed")
        self.assertEqual(result["missing_units"], ["blue_1"])
        self.assertEqual(result["errors"], [])

    def test_units_can_share_a_hex_after_movement(self) -> None:
        scenario, session = fresh_session()

        session["units"]["red_1"]["at"] = [0, -2]
        session["units"]["blue_1"]["at"] = [0, 2]

        submit_input(scenario, session, {"unit": "red_1", "heading": 3, "speed": 2})
        submit_input(scenario, session, {"unit": "blue_1", "heading": 0, "speed": 2})

        advance(scenario, session)
        result = advance(scenario, session)

        self.assertEqual(result["status"], "resolved")
        self.assertEqual(result["phase"], "resolve_plotted_move")
        self.assertEqual(
            [(event["type"], event["unit"]) for event in result["events"]],
            [
                ("moved", "red_1"),
                ("moved", "blue_1"),
            ],
        )
        self.assertEqual(session["units"]["red_1"]["at"], [0, 0])
        self.assertEqual(session["units"]["blue_1"]["at"], [0, 0])

    def test_attacks_reduce_shields_before_hull_and_preserve_speed_state(self) -> None:
        scenario, session = fresh_session()

        session["units"]["red_1"]["at"] = [0, -2]
        session["units"]["blue_1"]["at"] = [0, 2]

        submit_input(scenario, session, {"unit": "red_1", "heading": 3, "speed": 1})
        submit_input(scenario, session, {"unit": "blue_1", "heading": 0, "speed": 1})

        advance(scenario, session)
        advance(scenario, session)
        result = advance(scenario, session)

        self.assertEqual(result["status"], "resolved")
        self.assertEqual(result["phase"], "resolve_attacks")
        self.assertEqual(session["turn"], 2)
        self.assertEqual(session["phase"], "plot_heading_speed")
        self.assertEqual(session["phase_data"]["plots"], {})
        self.assertEqual(session["units"]["red_1"]["speed"], 1)
        self.assertEqual(session["units"]["red_1"]["max_speed"], 3)
        self.assertEqual(session["units"]["red_1"]["shield"], 1)
        self.assertEqual(session["units"]["red_1"]["hull"], 4)
        self.assertEqual(session["units"]["blue_1"]["speed"], 1)
        self.assertEqual(session["units"]["blue_1"]["max_speed"], 3)
        self.assertEqual(session["units"]["blue_1"]["shield"], 1)
        self.assertEqual(session["units"]["blue_1"]["hull"], 4)
