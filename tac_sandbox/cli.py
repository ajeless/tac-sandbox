from __future__ import annotations

import argparse
import shlex
from pathlib import Path

from .engine import advance, load_scenario, start_session, submit_input, terminal_state
from .presentation import describe_event


def main() -> int:
    parser = argparse.ArgumentParser(description="Manual host loop for the current spike")
    parser.add_argument(
        "scenario",
        nargs="?",
        default="scenarios/ship_duel.toml",
        help="path to a scenario TOML file",
    )
    args = parser.parse_args()

    try:
        scenario = load_scenario(Path(args.scenario))
    except ValueError as exc:
        print(f"error: {exc}")
        return 1
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
    terminal = terminal_state(scenario, session)
    if terminal is not None:
        print(f"session ended: {terminal['text']}")
    for unit_id in scenario["unit_order"]:
        unit = session["units"][unit_id]
        status = "destroyed" if unit["destroyed"] else "active"
        print(
            f"{unit_id}: side={unit['side']} at={tuple(unit['at'])} "
            f"facing={unit['facing']} hull={unit['hull']} shield={unit['shield']} "
            f"speed={unit['speed']} max_speed={unit['max_speed']} status={status}"
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
        print(describe_event(event))


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

    if status == "terminal":
        print(result["terminal"]["text"])
        return

    if status == "resolved":
        if result.get("terminal") is not None:
            print(f"resolved {result['phase']} -> session ended")
        else:
            print(
                f"resolved {result['phase']} -> turn {result['turn']} phase {result['next_phase']}"
            )
        if result["events"]:
            for event in result["events"]:
                print(describe_event(event))
        else:
            print("no events")
        return

    print(result)


if __name__ == "__main__":
    raise SystemExit(main())
