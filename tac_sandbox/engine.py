from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
from pathlib import Path
import tomllib

AXIAL_DIRECTIONS = {
    0: (1, 0),
    1: (1, -1),
    2: (0, -1),
    3: (-1, 0),
    4: (-1, 1),
    5: (0, 1),
}

CUBE_DIRECTIONS = {
    0: (1, -1, 0),
    1: (1, 0, -1),
    2: (0, 1, -1),
    3: (-1, 1, 0),
    4: (-1, 0, 1),
    5: (0, -1, 1),
}

SUPPORTED_PHASES = {
    "plot_heading_speed",
    "resolve_plotted_move",
    "resolve_attacks",
}


def load_scenario(path: str | Path) -> dict:
    scenario_path = Path(path)
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
    if session["phase"] != "plot_heading_speed":
        return {
            "status": "rejected",
            "phase": session["phase"],
            "errors": ["current phase does not accept manual input"],
        }

    unit_id = data.get("unit")
    heading = data.get("heading")
    speed = data.get("speed")

    if unit_id not in session["units"]:
        return {"status": "rejected", "errors": [f"unknown unit: {unit_id}"]}

    unit = session["units"][unit_id]
    if unit["destroyed"]:
        return {"status": "rejected", "errors": [f"{unit_id} is destroyed"]}

    errors = _validate_plot(unit, heading, speed)
    if errors:
        return {"status": "rejected", "phase": session["phase"], "errors": errors}

    session["phase_data"].setdefault("plots", {})[unit_id] = {
        "heading": int(heading),
        "speed": int(speed),
    }
    return {
        "status": "input_recorded",
        "phase": session["phase"],
        "unit": unit_id,
        "plot": deepcopy(session["phase_data"]["plots"][unit_id]),
    }


def advance(scenario: dict, session: dict) -> dict:
    phase = session["phase"]
    handler = {
        "plot_heading_speed": _resolve_plot_phase,
        "resolve_plotted_move": _resolve_movement_phase,
        "resolve_attacks": _resolve_attack_phase,
    }[phase]
    return handler(scenario, session)


def _resolve_plot_phase(scenario: dict, session: dict) -> dict:
    plots = session["phase_data"].setdefault("plots", {})
    missing = []
    errors = []

    for unit_id in _active_unit_ids(scenario, session):
        if unit_id not in plots:
            missing.append(unit_id)
            continue
        errors.extend(_validate_plot(session["units"][unit_id], **plots[unit_id]))

    if missing or errors:
        return {
            "status": "awaiting_input",
            "phase": session["phase"],
            "missing_units": missing,
            "errors": errors,
        }

    events = []
    for unit_id in _active_unit_ids(scenario, session):
        plot = plots[unit_id]
        events.append(
            _event(
                session,
                "orders_locked",
                unit=unit_id,
                heading=plot["heading"],
                speed=plot["speed"],
            )
        )

    session["log"].extend(events)
    _advance_phase(scenario, session)
    return {
        "status": "resolved",
        "phase": "plot_heading_speed",
        "events": events,
        "next_phase": session["phase"],
        "turn": session["turn"],
    }


def _resolve_movement_phase(scenario: dict, session: dict) -> dict:
    plots = session["phase_data"].get("plots", {})
    bounds = scenario["space"]["bounds"]
    events = []

    desired = {}
    origins = {}
    for unit_id in _active_unit_ids(scenario, session):
        unit = session["units"][unit_id]
        plot = plots[unit_id]
        origins[unit_id] = list(unit["at"])
        unit["facing"] = plot["heading"]
        desired[unit_id] = _walk_hex(unit["at"], plot["heading"], plot["speed"])

    pre_collision = {}
    for unit_id, destination in desired.items():
        if _in_bounds(destination, bounds):
            pre_collision[unit_id] = destination
        else:
            pre_collision[unit_id] = origins[unit_id]
            events.append(
                _event(
                    session,
                    "move_blocked_bounds",
                    unit=unit_id,
                    from_hex=origins[unit_id],
                    attempted=destination,
                )
            )

    occupancy = defaultdict(list)
    for unit_id, destination in pre_collision.items():
        occupancy[tuple(destination)].append(unit_id)

    conflicts = {
        unit_id
        for unit_ids in occupancy.values()
        if len(unit_ids) > 1
        for unit_id in unit_ids
    }

    for unit_id in conflicts:
        events.append(
            _event(
                session,
                "move_blocked_collision",
                unit=unit_id,
                from_hex=origins[unit_id],
                attempted=pre_collision[unit_id],
            )
        )

    for unit_id in _active_unit_ids(scenario, session):
        final_hex = origins[unit_id] if unit_id in conflicts else pre_collision[unit_id]
        session["units"][unit_id]["at"] = list(final_hex)
        if final_hex != origins[unit_id]:
            events.append(
                _event(
                    session,
                    "moved",
                    unit=unit_id,
                    from_hex=origins[unit_id],
                    to_hex=final_hex,
                )
            )

    session["log"].extend(events)
    _advance_phase(scenario, session)
    return {
        "status": "resolved",
        "phase": "resolve_plotted_move",
        "events": events,
        "next_phase": session["phase"],
        "turn": session["turn"],
    }


def _resolve_attack_phase(scenario: dict, session: dict) -> dict:
    events = []
    attacks = []
    active_units = _active_unit_ids(scenario, session)

    for unit_id in active_units:
        attacker = session["units"][unit_id]
        enemies = [
            other_id
            for other_id in active_units
            if session["units"][other_id]["side"] != attacker["side"]
        ]
        if len(enemies) != 1:
            events.append(
                _event(
                    session,
                    "attack_skipped",
                    unit=unit_id,
                    reason="ambiguous_or_missing_target",
                )
            )
            continue

        target_id = enemies[0]
        target = session["units"][target_id]
        attack_range = _hex_distance(attacker["at"], target["at"])
        if attack_range > attacker["weapon"]["range"]:
            events.append(
                _event(
                    session,
                    "attack_skipped",
                    unit=unit_id,
                    target=target_id,
                    reason="out_of_range",
                    range=attack_range,
                )
            )
            continue

        direction = _approximate_direction(attacker["at"], target["at"])
        if attacker["weapon"]["arc"] == "front" and not _is_forward_arc(
            attacker["facing"], direction
        ):
            events.append(
                _event(
                    session,
                    "attack_skipped",
                    unit=unit_id,
                    target=target_id,
                    reason="target_outside_arc",
                    target_direction=direction,
                )
            )
            continue

        attacks.append(
            {
                "attacker": unit_id,
                "target": target_id,
                "damage": attacker["weapon"]["damage"],
                "range": attack_range,
            }
        )
        events.append(
            _event(
                session,
                "attack_declared",
                unit=unit_id,
                target=target_id,
                damage=attacker["weapon"]["damage"],
                range=attack_range,
            )
        )

    incoming_damage = defaultdict(int)
    for attack in attacks:
        incoming_damage[attack["target"]] += attack["damage"]

    for unit_id, damage in incoming_damage.items():
        unit = session["units"][unit_id]
        shield_before = unit["shield"]
        hull_before = unit["hull"]
        shield_loss = min(unit["shield"], damage)
        remaining = damage - shield_loss
        unit["shield"] -= shield_loss
        hull_loss = min(unit["hull"], remaining)
        unit["hull"] -= hull_loss

        events.append(
            _event(
                session,
                "damage_applied",
                unit=unit_id,
                damage=damage,
                shield_before=shield_before,
                shield_after=unit["shield"],
                hull_before=hull_before,
                hull_after=unit["hull"],
            )
        )

        if unit["hull"] == 0 and not unit["destroyed"]:
            unit["destroyed"] = True
            events.append(_event(session, "unit_destroyed", unit=unit_id))

    session["log"].extend(events)
    _advance_phase(scenario, session)
    return {
        "status": "resolved",
        "phase": "resolve_attacks",
        "events": events,
        "next_phase": session["phase"],
        "turn": session["turn"],
    }


def _advance_phase(scenario: dict, session: dict) -> None:
    phases = scenario["turn"]["phases"]
    current_index = phases.index(session["phase"])
    if current_index + 1 < len(phases):
        session["phase"] = phases[current_index + 1]
        return

    session["turn"] += 1
    session["phase"] = phases[0]
    session["phase_data"] = {"plots": {}}


def _active_unit_ids(scenario: dict, session: dict) -> list[str]:
    return [
        unit_id
        for unit_id in scenario["unit_order"]
        if not session["units"][unit_id]["destroyed"]
    ]


def _validate_plot(unit: dict, heading: int, speed: int) -> list[str]:
    errors = []
    if not isinstance(heading, int):
        errors.append(f"{unit['id']} heading must be an integer")
    elif heading not in AXIAL_DIRECTIONS:
        errors.append(f"{unit['id']} heading must be between 0 and 5")

    if not isinstance(speed, int):
        errors.append(f"{unit['id']} speed must be an integer")
    elif speed < 0 or speed > unit["speed"]:
        errors.append(f"{unit['id']} speed must be between 0 and {unit['speed']}")

    return errors


def _walk_hex(start: list[int], heading: int, speed: int) -> list[int]:
    dq, dr = AXIAL_DIRECTIONS[heading]
    return [start[0] + (dq * speed), start[1] + (dr * speed)]


def _in_bounds(position: list[int], bounds: list[int]) -> bool:
    return 0 <= position[0] < bounds[0] and 0 <= position[1] < bounds[1]


def _hex_distance(a: list[int], b: list[int]) -> int:
    aq, ar = a
    bq, br = b
    ax, ay, az = aq, -aq - ar, ar
    bx, by, bz = bq, -bq - br, br
    return max(abs(ax - bx), abs(ay - by), abs(az - bz))


def _approximate_direction(a: list[int], b: list[int]) -> int | None:
    if a == b:
        return None

    aq, ar = a
    bq, br = b
    dx, dy, dz = (bq - aq), (aq + ar - bq - br), (br - ar)

    best_direction = None
    best_score = None
    for direction, vector in CUBE_DIRECTIONS.items():
        score = (dx * vector[0]) + (dy * vector[1]) + (dz * vector[2])
        if best_score is None or score > best_score:
            best_direction = direction
            best_score = score
    return best_direction


def _is_forward_arc(facing: int, direction: int | None) -> bool:
    if direction is None:
        return True
    return direction in {(facing - 1) % 6, facing, (facing + 1) % 6}


def _event(session: dict, event_type: str, **payload: object) -> dict:
    return {
        "turn": session["turn"],
        "phase": session["phase"],
        "type": event_type,
        **payload,
    }
