from __future__ import annotations

from .rules import active_unit_ids


def terminal_state(scenario: dict, session: dict) -> dict | None:
    if active_unit_ids(scenario, session):
        return None

    return {
        "reason": "no_active_units",
        "text": "No active units remain. Reset to start over.",
    }
