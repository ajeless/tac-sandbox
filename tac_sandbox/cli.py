from __future__ import annotations

import argparse
import shlex
from pathlib import Path

from .engine import advance, load_scenario, start_session, submit_input


def main() -> int:
    parser = argparse.ArgumentParser(description="Manual host loop for the current spike")
    parser.add_argument(
        "scenario",
        nargs="?",
        default="scenarios/ship_duel.toml",
        help="path to a scenario TOML file",
    )
    args = parser.parse_args()

    scenario = load_scenario(Path(args.scenario))
    session = start_session(scenario)

    print(f"Loaded {scenario['title']} from {scenario['path']}")
    print("Commands: show, plot <unit> <heading> <speed>, step, log, reset, help, quit")

    while True:
        try:
            raw = input("> ")
        except EOFError:
            print()
            return 0

        if not raw.strip():
            continue

        parts = shlex.split(raw)
        command = parts[0]

        if command in {"quit", "exit"}:
            return 0
        if command == "help":
            print("show")
            print("plot <unit> <heading> <speed>")
            print("step")
            print("log")
            print("reset")
            print("quit")
            continue
        if command == "show":
            _show_session(scenario, session)
            continue
        if command == "log":
            _show_log(session)
            continue
        if command == "reset":
            session = start_session(scenario)
            print("Session reset")
            _show_session(scenario, session)
            continue
        if command == "plot":
            if len(parts) != 4:
                print("usage: plot <unit> <heading> <speed>")
                continue
            try:
                heading = int(parts[2])
                speed = int(parts[3])
            except ValueError:
                print("heading and speed must be integers")
                continue
            result = submit_input(
                scenario,
                session,
                {"unit": parts[1], "heading": heading, "speed": speed},
            )
            _print_result(result)
            continue
        if command == "step":
            result = advance(scenario, session)
            _print_result(result)
            continue

        print(f"unknown command: {command}")


def _show_session(scenario: dict, session: dict) -> None:
    print(f"Turn {session['turn']} phase {session['phase']}")
    for unit_id in scenario["unit_order"]:
        unit = session["units"][unit_id]
        status = "destroyed" if unit["destroyed"] else "active"
        print(
            f"{unit_id}: side={unit['side']} at={tuple(unit['at'])} "
            f"facing={unit['facing']} hull={unit['hull']} shield={unit['shield']} "
            f"speed={unit['speed']} status={status}"
        )

    plots = session["phase_data"].get("plots", {})
    if plots:
        print("plots:")
        for unit_id in scenario["unit_order"]:
            if unit_id in plots:
                plot = plots[unit_id]
                print(
                    f"  {unit_id}: heading={plot['heading']} speed={plot['speed']}"
                )


def _show_log(session: dict) -> None:
    if not session["log"]:
        print("log is empty")
        return

    for event in session["log"]:
        print(_format_event(event))


def _print_result(result: dict) -> None:
    status = result["status"]
    if status == "input_recorded":
        plot = result["plot"]
        print(
            f"stored plot for {result['unit']}: heading={plot['heading']} speed={plot['speed']}"
        )
        return

    if status == "rejected":
        for error in result.get("errors", []):
            print(f"error: {error}")
        return

    if status == "awaiting_input":
        print(f"awaiting input for phase {result['phase']}")
        if result.get("missing_units"):
            print("missing plots:", ", ".join(result["missing_units"]))
        for error in result.get("errors", []):
            print(f"error: {error}")
        return

    if status == "resolved":
        print(
            f"resolved {result['phase']} -> turn {result['turn']} phase {result['next_phase']}"
        )
        if result["events"]:
            for event in result["events"]:
                print(_format_event(event))
        else:
            print("no events")
        return

    print(result)


def _format_event(event: dict) -> str:
    event_type = event["type"]
    if event_type == "orders_locked":
        return (
            f"turn {event['turn']} {event['unit']} plotted heading={event['heading']} "
            f"speed={event['speed']}"
        )
    if event_type == "moved":
        return (
            f"turn {event['turn']} {event['unit']} moved "
            f"{tuple(event['from_hex'])} -> {tuple(event['to_hex'])}"
        )
    if event_type == "move_blocked_bounds":
        return (
            f"turn {event['turn']} {event['unit']} stayed at {tuple(event['from_hex'])} "
            f"because {tuple(event['attempted'])} is out of bounds"
        )
    if event_type == "move_blocked_collision":
        return (
            f"turn {event['turn']} {event['unit']} stayed at {tuple(event['from_hex'])} "
            f"because of a collision at {tuple(event['attempted'])}"
        )
    if event_type == "attack_declared":
        return (
            f"turn {event['turn']} {event['unit']} attacked {event['target']} "
            f"for {event['damage']} at range {event['range']}"
        )
    if event_type == "attack_skipped":
        target = f" target={event['target']}" if "target" in event else ""
        return f"turn {event['turn']} {event['unit']} skipped attack{target} reason={event['reason']}"
    if event_type == "damage_applied":
        return (
            f"turn {event['turn']} {event['unit']} took {event['damage']} damage "
            f"(shield {event['shield_before']}->{event['shield_after']}, "
            f"hull {event['hull_before']}->{event['hull_after']})"
        )
    if event_type == "unit_destroyed":
        return f"turn {event['turn']} {event['unit']} was destroyed"
    return str(event)


if __name__ == "__main__":
    raise SystemExit(main())
