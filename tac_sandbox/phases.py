from __future__ import annotations

from copy import deepcopy

from .action_resolution import resolve_attacks
from .rules import (
    active_unit_ids,
    event,
    in_bounds,
    validate_plot,
    walk_hex,
)


class PhaseHandler:
    name = ""
    accepts_input = False

    def submit_input(self, scenario: dict, session: dict, data: dict) -> dict:
        return {
            "status": "rejected",
            "phase": session["phase"],
            "errors": ["current phase does not accept manual input"],
        }

    def awaiting(self, scenario: dict, session: dict) -> dict | None:
        return None

    def resolve(self, scenario: dict, session: dict) -> list[dict]:
        raise NotImplementedError

    def active_units(self, scenario: dict, session: dict):
        for unit_id in active_unit_ids(scenario, session):
            yield unit_id, session["units"][unit_id]

    def plots(self, session: dict) -> dict:
        return session["phase_data"].setdefault("plots", {})


class PlotHeadingSpeedPhase(PhaseHandler):
    name = "plot_heading_speed"
    accepts_input = True

    def submit_input(self, scenario: dict, session: dict, data: dict) -> dict:
        unit_id = data.get("unit")
        heading = data.get("heading")
        speed = data.get("speed")

        if unit_id not in session["units"]:
            return {"status": "rejected", "errors": [f"unknown unit: {unit_id}"]}

        unit = session["units"][unit_id]
        if unit["destroyed"]:
            return {"status": "rejected", "errors": [f"{unit_id} is destroyed"]}

        errors = validate_plot(unit, scenario["heading"], heading, speed)
        if errors:
            return {"status": "rejected", "phase": session["phase"], "errors": errors}

        plots = self.plots(session)
        plots[unit_id] = {
            "heading": int(heading),
            "speed": int(speed),
        }
        return {
            "status": "input_recorded",
            "phase": session["phase"],
            "unit": unit_id,
            "plot": deepcopy(plots[unit_id]),
        }

    def awaiting(self, scenario: dict, session: dict) -> dict | None:
        plots = self.plots(session)
        missing = []
        errors = []

        for unit_id, unit in self.active_units(scenario, session):
            if unit_id not in plots:
                missing.append(unit_id)
                continue
            errors.extend(
                validate_plot(
                    unit,
                    scenario["heading"],
                    plots[unit_id]["heading"],
                    plots[unit_id]["speed"],
                )
            )

        if missing or errors:
            return {"missing_units": missing, "errors": errors}
        return None

    def resolve(self, scenario: dict, session: dict) -> list[dict]:
        plots = self.plots(session)
        return [
            event(
                session,
                "orders_locked",
                unit=unit_id,
                heading=plots[unit_id]["heading"],
                speed=plots[unit_id]["speed"],
            )
            for unit_id, _unit in self.active_units(scenario, session)
        ]


class ResolvePlottedMovePhase(PhaseHandler):
    name = "resolve_plotted_move"

    def resolve(self, scenario: dict, session: dict) -> list[dict]:
        plots = self.plots(session)
        events = []
        for unit_id, unit in self.active_units(scenario, session):
            events.extend(_resolve_move(scenario, session, unit_id, unit, plots[unit_id]))
        return events


class ResolveAttacksPhase(PhaseHandler):
    name = "resolve_attacks"

    def resolve(self, scenario: dict, session: dict) -> list[dict]:
        active_unit_ids_for_phase = [
            unit_id for unit_id, _unit in self.active_units(scenario, session)
        ]
        return resolve_attacks(scenario, session, active_unit_ids_for_phase)


def _resolve_move(scenario: dict, session: dict, unit_id: str, unit: dict, plot: dict) -> list[dict]:
    origin = list(unit["at"])
    unit["facing"] = plot["heading"]
    unit["speed"] = plot["speed"]
    destination = walk_hex(origin, scenario["heading"], plot["heading"], plot["speed"])

    if in_bounds(destination, scenario["space"]):
        unit["at"] = list(destination)
        return [
            event(
                session,
                "moved",
                unit=unit_id,
                from_hex=origin,
                to_hex=destination,
            )
        ]

    return [
        event(
            session,
            "move_blocked_bounds",
            unit=unit_id,
            from_hex=origin,
            attempted=destination,
        )
    ]

PHASE_HANDLERS = {
    handler.name: handler
    for handler in (
        PlotHeadingSpeedPhase(),
        ResolvePlottedMovePhase(),
        ResolveAttacksPhase(),
    )
}
