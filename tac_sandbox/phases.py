from __future__ import annotations

from collections import defaultdict
from copy import deepcopy

from .rules import (
    active_unit_ids,
    approximate_direction,
    event,
    hex_distance,
    in_bounds,
    is_forward_arc,
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

    def awaiting(self, scenario: dict, session: dict) -> dict | None:
        plots = session["phase_data"].setdefault("plots", {})
        missing = []
        errors = []

        for unit_id in active_unit_ids(scenario, session):
            if unit_id not in plots:
                missing.append(unit_id)
                continue
            errors.extend(
                validate_plot(
                    session["units"][unit_id],
                    scenario["heading"],
                    plots[unit_id]["heading"],
                    plots[unit_id]["speed"],
                )
            )

        if missing or errors:
            return {"missing_units": missing, "errors": errors}
        return None

    def resolve(self, scenario: dict, session: dict) -> list[dict]:
        plots = session["phase_data"].setdefault("plots", {})
        events = []
        for unit_id in active_unit_ids(scenario, session):
            plot = plots[unit_id]
            events.append(
                event(
                    session,
                    "orders_locked",
                    unit=unit_id,
                    heading=plot["heading"],
                    speed=plot["speed"],
                )
            )
        return events


class ResolvePlottedMovePhase(PhaseHandler):
    name = "resolve_plotted_move"

    def resolve(self, scenario: dict, session: dict) -> list[dict]:
        plots = session["phase_data"].get("plots", {})
        events = []
        for unit_id in active_unit_ids(scenario, session):
            unit = session["units"][unit_id]
            plot = plots[unit_id]
            origin = list(unit["at"])
            unit["facing"] = plot["heading"]
            unit["speed"] = plot["speed"]
            destination = walk_hex(origin, scenario["heading"], plot["heading"], plot["speed"])
            if in_bounds(destination, scenario["space"]):
                unit["at"] = list(destination)
                events.append(
                    event(
                        session,
                        "moved",
                        unit=unit_id,
                        from_hex=origin,
                        to_hex=destination,
                    )
                )
                continue

            events.append(
                event(
                    session,
                    "move_blocked_bounds",
                    unit=unit_id,
                    from_hex=origin,
                    attempted=destination,
                )
            )

        return events


class ResolveAttacksPhase(PhaseHandler):
    name = "resolve_attacks"

    def resolve(self, scenario: dict, session: dict) -> list[dict]:
        events = []
        attacks = []
        active_units = active_unit_ids(scenario, session)

        for unit_id in active_units:
            attacker = session["units"][unit_id]
            enemies = [
                other_id
                for other_id in active_units
                if session["units"][other_id]["side"] != attacker["side"]
            ]
            if len(enemies) != 1:
                events.append(
                    event(
                        session,
                        "attack_skipped",
                        unit=unit_id,
                        reason="ambiguous_or_missing_target",
                    )
                )
                continue

            target_id = enemies[0]
            target = session["units"][target_id]
            attack_range = hex_distance(attacker["at"], target["at"])
            if attack_range > attacker["weapon"]["range"]:
                events.append(
                    event(
                        session,
                        "attack_skipped",
                        unit=unit_id,
                        target=target_id,
                        reason="out_of_range",
                        range=attack_range,
                    )
                )
                continue

            direction = approximate_direction(scenario["heading"], attacker["at"], target["at"])
            if attacker["weapon"]["arc"] == "front" and not is_forward_arc(
                attacker["facing"], direction
            ):
                events.append(
                    event(
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
                event(
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
                event(
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
                events.append(event(session, "unit_destroyed", unit=unit_id))

        return events


PHASE_HANDLERS = {
    handler.name: handler
    for handler in (
        PlotHeadingSpeedPhase(),
        ResolvePlottedMovePhase(),
        ResolveAttacksPhase(),
    )
}
