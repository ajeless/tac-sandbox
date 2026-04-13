from __future__ import annotations

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


def active_unit_ids(scenario: dict, session: dict) -> list[str]:
    return [
        unit_id
        for unit_id in scenario["unit_order"]
        if not session["units"][unit_id]["destroyed"]
    ]


def validate_plot(unit: dict, heading: int, speed: int) -> list[str]:
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


def walk_hex(start: list[int], heading: int, speed: int) -> list[int]:
    dq, dr = AXIAL_DIRECTIONS[heading]
    return [start[0] + (dq * speed), start[1] + (dr * speed)]


def in_bounds(position: list[int], bounds: list[int]) -> bool:
    return 0 <= position[0] < bounds[0] and 0 <= position[1] < bounds[1]


def hex_distance(a: list[int], b: list[int]) -> int:
    aq, ar = a
    bq, br = b
    ax, ay, az = aq, -aq - ar, ar
    bx, by, bz = bq, -bq - br, br
    return max(abs(ax - bx), abs(ay - by), abs(az - bz))


def approximate_direction(a: list[int], b: list[int]) -> int | None:
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


def is_forward_arc(facing: int, direction: int | None) -> bool:
    if direction is None:
        return True
    return direction in {(facing - 1) % 6, facing, (facing + 1) % 6}


def event(session: dict, event_type: str, **payload: object) -> dict:
    return {
        "turn": session["turn"],
        "phase": session["phase"],
        "type": event_type,
        **payload,
    }
