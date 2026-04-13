from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import tomllib

from .phases import PHASE_HANDLERS, PhaseHandler

SUPPORTED_PHASES = set(PHASE_HANDLERS)


def load_scenario(path: str | Path) -> dict:
    scenario_path = _resolve_scenario_path(Path(path))
    with scenario_path.open("rb") as handle:
        raw = tomllib.load(handle)

    space = raw.get("space", {})
    if space.get("model") != "hex":
        raise ValueError("v0 only supports space.model = 'hex'")

    phases = raw.get("turn", {}).get("phases", [])
    if not phases:
        raise ValueError("scenario.turn.phases must not be empty")

    unknown_phases = [phase for phase in phases if phase not in SUPPORTED_PHASES]
    if unknown_phases:
        raise ValueError(f"unsupported phases: {', '.join(unknown_phases)}")

    units = {}
    unit_order = []
    for raw_unit in raw.get("units", []):
        unit_id = raw_unit["id"]
        if unit_id in units:
            raise ValueError(f"duplicate unit id: {unit_id}")
        units[unit_id] = {
            "id": unit_id,
            "side": raw_unit["side"],
            "at": list(raw_unit["at"]),
            "facing": int(raw_unit["facing"]),
            "hull": int(raw_unit["hull"]),
            "shield": int(raw_unit["shield"]),
            "speed": int(raw_unit["speed"]),
            "weapon": {
                "arc": raw_unit["weapon"]["arc"],
                "range": int(raw_unit["weapon"]["range"]),
                "damage": int(raw_unit["weapon"]["damage"]),
            },
        }
        unit_order.append(unit_id)

    if not units:
        raise ValueError("scenario.units must contain at least one unit")

    return {
        "path": str(scenario_path),
        "title": raw.get("title", scenario_path.stem),
        "space": {
            "model": space["model"],
            "bounds": list(space["bounds"]),
        },
        "turn": {"phases": list(phases)},
        "unit_order": unit_order,
        "units": units,
    }


def _resolve_scenario_path(path: Path) -> Path:
    if path.is_dir():
        candidates = sorted(
            candidate for candidate in path.iterdir() if candidate.is_file() and candidate.suffix == ".toml"
        )
        if len(candidates) == 1:
            return candidates[0]
        if not candidates:
            raise ValueError(f"scenario directory has no .toml files: {path}")
        names = ", ".join(candidate.name for candidate in candidates)
        raise ValueError(f"scenario directory is ambiguous: {path} ({names})")

    if not path.exists():
        raise ValueError(f"scenario file not found: {path}")

    return path


def start_session(scenario: dict) -> dict:
    units = {}
    for unit_id in scenario["unit_order"]:
        authored = deepcopy(scenario["units"][unit_id])
        authored["destroyed"] = False
        units[unit_id] = authored

    return {
        "turn": 1,
        "phase": scenario["turn"]["phases"][0],
        "units": units,
        "phase_data": {"plots": {}},
        "log": [],
    }


def submit_input(scenario: dict, session: dict, data: dict) -> dict:
    handler = _phase_handler(session["phase"])
    return handler.submit_input(scenario, session, data)


def advance(scenario: dict, session: dict) -> dict:
    handler = _phase_handler(session["phase"])
    awaiting = handler.awaiting(scenario, session)
    if awaiting is not None:
        return {
            "status": "awaiting_input",
            "phase": session["phase"],
            **awaiting,
        }

    events = handler.resolve(scenario, session)
    session["log"].extend(events)
    resolved_phase = session["phase"]
    _advance_phase(scenario, session)
    return {
        "status": "resolved",
        "phase": resolved_phase,
        "events": events,
        "next_phase": session["phase"],
        "turn": session["turn"],
    }


def _phase_handler(phase_name: str) -> PhaseHandler:
    return PHASE_HANDLERS[phase_name]


def _advance_phase(scenario: dict, session: dict) -> None:
    phases = scenario["turn"]["phases"]
    current_index = phases.index(session["phase"])
    if current_index + 1 < len(phases):
        session["phase"] = phases[current_index + 1]
        return

    session["turn"] += 1
    session["phase"] = phases[0]
    session["phase_data"] = {"plots": {}}
