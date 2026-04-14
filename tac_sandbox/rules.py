from __future__ import annotations

HEADING_PRESETS = {
    "north": {
        "axial": {
            0: (0, -1),
            1: (1, -1),
            2: (1, 0),
            3: (0, 1),
            4: (-1, 1),
            5: (-1, 0),
        },
        "cube": {
            0: (0, 1, -1),
            1: (1, 0, -1),
            2: (1, -1, 0),
            3: (0, -1, 1),
            4: (-1, 0, 1),
            5: (-1, 1, 0),
        },
    },
    "east": {
        "axial": {
            0: (1, 0),
            1: (1, -1),
            2: (0, -1),
            3: (-1, 0),
            4: (-1, 1),
            5: (0, 1),
        },
        "cube": {
            0: (1, -1, 0),
            1: (1, 0, -1),
            2: (0, 1, -1),
            3: (-1, 1, 0),
            4: (-1, 0, 1),
            5: (0, -1, 1),
        },
    },
}


def active_unit_ids(scenario: dict, session: dict) -> list[str]:
    return [
        unit_id
        for unit_id in scenario["unit_order"]
        if not session["units"][unit_id]["destroyed"]
    ]


def validate_plot(unit: dict, heading_config: dict, heading: int, speed: int) -> list[str]:
    errors = []
    max_speed = unit["max_speed"]
    valid_headings = heading_indices(heading_config)
    if not isinstance(heading, int):
        errors.append(f"{unit['id']} heading must be an integer")
    elif heading not in valid_headings:
        errors.append(f"{unit['id']} heading must be between 0 and {len(valid_headings) - 1}")

    if not isinstance(speed, int):
        errors.append(f"{unit['id']} speed must be an integer")
    elif speed < 0 or speed > max_speed:
        errors.append(f"{unit['id']} speed must be between 0 and {max_speed}")

    return errors


def walk_hex(start: list[int], heading_config: dict, heading: int, speed: int) -> list[int]:
    dq, dr = axial_directions(heading_config)[heading]
    return [start[0] + (dq * speed), start[1] + (dr * speed)]


def in_bounds(position: list[int], space: dict) -> bool:
    footprint = space["footprint"]
    if footprint == "rect":
        bounds = space["bounds"]
        return 0 <= position[0] < bounds[0] and 0 <= position[1] < bounds[1]
    if footprint == "radius":
        return hex_distance(position, space["center"]) <= space["radius"]
    raise ValueError(f"unsupported footprint: {footprint}")


def hex_distance(a: list[int], b: list[int]) -> int:
    aq, ar = a
    bq, br = b
    ax, ay, az = aq, -aq - ar, ar
    bx, by, bz = bq, -bq - br, br
    return max(abs(ax - bx), abs(ay - by), abs(az - bz))


def approximate_direction(heading_config: dict, a: list[int], b: list[int]) -> int | None:
    if a == b:
        return None

    aq, ar = a
    bq, br = b
    dx, dy, dz = (bq - aq), (aq + ar - bq - br), (br - ar)

    best_direction = None
    best_score = None
    for direction, vector in cube_directions(heading_config).items():
        score = (dx * vector[0]) + (dy * vector[1]) + (dz * vector[2])
        if best_score is None or score > best_score:
            best_direction = direction
            best_score = score
    return best_direction


def heading_indices(heading_config: dict) -> list[int]:
    return list(axial_directions(heading_config))


def axial_directions(heading_config: dict) -> dict[int, tuple[int, int]]:
    return HEADING_PRESETS[heading_config["zero"]]["axial"]


def cube_directions(heading_config: dict) -> dict[int, tuple[int, int, int]]:
    return HEADING_PRESETS[heading_config["zero"]]["cube"]


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
