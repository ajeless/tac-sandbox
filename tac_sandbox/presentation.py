from __future__ import annotations

from copy import deepcopy

from .engine import terminal_state


def present_session(
    scenario: dict,
    session: dict,
    *,
    recent_event_count: int = 12,
) -> dict:
    plots = session["phase_data"].get("plots", {})
    entities = []
    for unit_id in scenario["unit_order"]:
        unit = session["units"][unit_id]
        entities.append(
            {
                "id": unit_id,
                "kind": "ship",
                "side": unit["side"],
                "at": list(unit["at"]),
                "facing": unit["facing"],
                "destroyed": unit["destroyed"],
                "stats": {
                    "hull": unit["hull"],
                    "shield": unit["shield"],
                    "speed": unit["speed"],
                    "max_speed": unit["max_speed"],
                },
                "weapon": deepcopy(unit["weapon"]),
                "plot": deepcopy(plots.get(unit_id)),
            }
        )

    recent_events = []
    for event in session["log"][-recent_event_count:]:
        recent_events.append(
            {
                "type": event["type"],
                "text": describe_event(event),
                "raw": deepcopy(event),
            }
        )

    return {
        "title": scenario["title"],
        "board": deepcopy(scenario["space"]),
        "heading": deepcopy(scenario["heading"]),
        "terminal": terminal_state(scenario, session),
        "turn": {"number": session["turn"], "phase": session["phase"]},
        "entities": entities,
        "recent_events": recent_events,
    }


def describe_event(event: dict) -> str:
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
