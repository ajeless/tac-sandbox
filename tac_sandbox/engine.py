from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import tomllib

from .phases import PHASE_HANDLERS, PhaseHandler
from .rules import in_bounds
from .session_state import terminal_state

SUPPORTED_PHASES = set(PHASE_HANDLERS)
DEFAULT_UNIT_SCALE = 1.5


def load_scenario(path: str | Path) -> dict:
    scenario_path = _resolve_scenario_path(Path(path))
    with scenario_path.open("rb") as handle:
        raw = tomllib.load(handle)
    return scenario_from_data(raw, source_path=scenario_path)


def scenario_from_data(raw: dict, *, source_path: str | Path = "runtime_scenario") -> dict:
    if not isinstance(raw, dict):
        raise ValueError("scenario config must be an object")

    source = Path(source_path)

    space = _load_space(raw.get("space", {}))
    if space.get("model") != "hex":
        raise ValueError("v0 only supports space.model = 'hex'")
    heading = _load_heading(raw.get("heading", {}), space)
    presentation = _load_presentation(raw.get("presentation", {}))

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
        if not unit_id:
            raise ValueError("unit id must not be empty")
        if unit_id in units:
            raise ValueError(f"duplicate unit id: {unit_id}")
        speed = _load_int(raw_unit["speed"], f"{unit_id} speed")
        max_speed = _load_int(raw_unit.get("max_speed", raw_unit["speed"]), f"{unit_id} max_speed")
        if speed < 0:
            raise ValueError(f"{unit_id} speed must be non-negative")
        if max_speed < 0:
            raise ValueError(f"{unit_id} max_speed must be non-negative")
        if speed > max_speed:
            raise ValueError(f"{unit_id} speed must be less than or equal to max_speed")
        units[unit_id] = {
            "id": unit_id,
            "side": raw_unit["side"],
            "at": _load_coordinate_pair(raw_unit["at"], f"{unit_id} at"),
            "facing": _load_int(raw_unit["facing"], f"{unit_id} facing"),
            "hull": _load_int(raw_unit["hull"], f"{unit_id} hull"),
            "shield": _load_int(raw_unit["shield"], f"{unit_id} shield"),
            "speed": speed,
            "max_speed": max_speed,
            "weapon": {
                "arc": raw_unit["weapon"]["arc"],
                "range": _load_int(raw_unit["weapon"]["range"], f"{unit_id} weapon.range"),
                "damage": _load_int(raw_unit["weapon"]["damage"], f"{unit_id} weapon.damage"),
            },
        }
        if not in_bounds(units[unit_id]["at"], space):
            raise ValueError(f"{unit_id} starts outside the play surface")
        unit_order.append(unit_id)

    if not units:
        raise ValueError("scenario.units must contain at least one unit")

    return {
        "path": str(source),
        "title": raw.get("title", source.stem),
        "space": space,
        "heading": heading,
        "presentation": presentation,
        "turn": {"phases": list(phases)},
        "unit_order": unit_order,
        "units": units,
    }


def scenario_to_config(scenario: dict) -> dict:
    return {
        "title": scenario["title"],
        "path": scenario["path"],
        "space": deepcopy(scenario["space"]),
        "heading": deepcopy(scenario["heading"]),
        "presentation": deepcopy(scenario["presentation"]),
        "turn": deepcopy(scenario["turn"]),
        "units": [
            deepcopy(scenario["units"][unit_id])
            for unit_id in scenario["unit_order"]
        ],
    }


def _load_space(raw_space: dict) -> dict:
    if raw_space.get("model") != "hex":
        return {"model": raw_space.get("model")}

    orientation = raw_space.get("orientation", "flat_top")
    if orientation not in {"flat_top", "pointy_top"}:
        raise ValueError("space.orientation must be 'flat_top' or 'pointy_top'")

    footprint = raw_space.get("footprint")

    if footprint == "rect" or ("bounds" in raw_space and footprint is None):
        return {
            "model": "hex",
            "orientation": orientation,
            "footprint": "rect",
            "bounds": _load_coordinate_pair(raw_space["bounds"], "space.bounds"),
        }

    if footprint == "radius" or ("radius" in raw_space and footprint is None):
        radius = _load_int(raw_space["radius"], "space.radius")
        if radius < 0:
            raise ValueError("space.radius must be non-negative")
        center = _load_coordinate_pair(raw_space.get("center", [0, 0]), "space.center")
        return {
            "model": "hex",
            "orientation": orientation,
            "footprint": "radius",
            "center": center,
            "radius": radius,
        }

    raise ValueError("space must define a supported footprint and its geometry")


def _load_heading(raw_heading: dict, space: dict) -> dict:
    model = raw_heading.get("model", "discrete_6")
    if model != "discrete_6":
        raise ValueError("v0 only supports heading.model = 'discrete_6'")

    rotation = raw_heading.get("rotation", "clockwise")
    if rotation != "clockwise":
        raise ValueError("v0 only supports heading.rotation = 'clockwise'")

    default_zero = "north" if space["orientation"] == "flat_top" else "east"
    zero = raw_heading.get("zero", default_zero)

    allowed_zero = {
        "flat_top": {"north"},
        "pointy_top": {"east"},
    }
    if zero not in allowed_zero[space["orientation"]]:
        allowed = ", ".join(sorted(allowed_zero[space["orientation"]]))
        raise ValueError(
            f"space.orientation = '{space['orientation']}' requires heading.zero in {{{allowed}}}"
        )

    return {
        "model": model,
        "zero": zero,
        "rotation": rotation,
    }


def _load_presentation(raw_presentation: dict) -> dict:
    try:
        unit_scale = float(raw_presentation.get("unit_scale", DEFAULT_UNIT_SCALE))
    except (TypeError, ValueError) as exc:
        raise ValueError("presentation.unit_scale must be a number") from exc

    if unit_scale <= 0:
        raise ValueError("presentation.unit_scale must be greater than 0")

    return {"unit_scale": unit_scale}


def _load_int(value: object, label: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{label} must be an integer")
    if isinstance(value, float):
        if not value.is_integer():
            raise ValueError(f"{label} must be an integer")
        return int(value)

    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be an integer") from exc


def _load_coordinate_pair(value: object, label: str) -> list[int]:
    try:
        coords = list(value)
    except TypeError as exc:
        raise ValueError(f"{label} must contain exactly two coordinates") from exc
    if len(coords) != 2:
        raise ValueError(f"{label} must contain exactly two coordinates")
    return [
        _load_int(coords[0], f"{label}[0]"),
        _load_int(coords[1], f"{label}[1]"),
    ]


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
        "phase_data": {"plots": {}, "fire_orders": {}},
        "log": [],
    }


def submit_input(scenario: dict, session: dict, data: dict) -> dict:
    terminal = terminal_state(scenario, session)
    if terminal is not None:
        return {
            "status": "terminal",
            "phase": session["phase"],
            "terminal": terminal,
        }

    handler = _phase_handler(session["phase"])
    return handler.submit_input(scenario, session, data)


def advance(scenario: dict, session: dict) -> dict:
    terminal = terminal_state(scenario, session)
    if terminal is not None:
        return {
            "status": "terminal",
            "phase": session["phase"],
            "terminal": terminal,
        }

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
    terminal = terminal_state(scenario, session)
    if terminal is None:
        _advance_phase(scenario, session)
    return {
        "status": "resolved",
        "phase": resolved_phase,
        "events": events,
        "next_phase": None if terminal is not None else session["phase"],
        "terminal": terminal,
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
    session["phase_data"] = {"plots": {}, "fire_orders": {}}
