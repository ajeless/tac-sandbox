from __future__ import annotations

from collections import defaultdict

from .rules import approximate_direction, event, hex_distance, is_forward_arc


def resolve_attacks(
    scenario: dict,
    session: dict,
    active_unit_ids_for_phase: list[str],
) -> list[dict]:
    events = []
    attacks = []
    fire_orders = session["phase_data"].get("fire_orders", {})

    for unit_id in active_unit_ids_for_phase:
        if not fire_orders.get(unit_id, False):
            events.append(
                event(
                    session,
                    "attack_skipped",
                    unit=unit_id,
                    reason="held_fire",
                )
            )
            continue

        attack, attack_events = _resolve_attack(
            scenario,
            session,
            active_unit_ids_for_phase,
            unit_id,
        )
        events.extend(attack_events)
        if attack is not None:
            attacks.append(attack)

    events.extend(_apply_attacks(session, attacks))
    return events


def _resolve_attack(
    scenario: dict,
    session: dict,
    active_unit_ids_for_phase: list[str],
    unit_id: str,
) -> tuple[dict | None, list[dict]]:
    attacker = session["units"][unit_id]
    enemies = [
        other_id
        for other_id in active_unit_ids_for_phase
        if session["units"][other_id]["side"] != attacker["side"]
    ]
    if len(enemies) != 1:
        return None, [
            event(
                session,
                "attack_skipped",
                unit=unit_id,
                reason="ambiguous_or_missing_target",
            )
        ]

    target_id = enemies[0]
    target = session["units"][target_id]
    attack_range = hex_distance(attacker["at"], target["at"])
    if attack_range > attacker["weapon"]["range"]:
        return None, [
            event(
                session,
                "attack_skipped",
                unit=unit_id,
                target=target_id,
                reason="out_of_range",
                range=attack_range,
            )
        ]

    direction = approximate_direction(scenario["heading"], attacker["at"], target["at"])
    if attacker["weapon"]["arc"] == "front" and not is_forward_arc(
        attacker["facing"], direction
    ):
        return None, [
            event(
                session,
                "attack_skipped",
                unit=unit_id,
                target=target_id,
                reason="target_outside_arc",
                target_direction=direction,
            )
        ]

    attack = {
        "attacker": unit_id,
        "target": target_id,
        "damage": attacker["weapon"]["damage"],
        "range": attack_range,
    }
    return attack, [
        event(
            session,
            "attack_declared",
            unit=unit_id,
            target=target_id,
            damage=attack["damage"],
            range=attack_range,
        )
    ]


def _apply_attacks(session: dict, attacks: list[dict]) -> list[dict]:
    incoming_damage = defaultdict(int)
    for attack in attacks:
        incoming_damage[attack["target"]] += attack["damage"]

    events = []
    for unit_id, damage in incoming_damage.items():
        events.extend(_apply_damage(session, unit_id, damage))
    return events


def _apply_damage(session: dict, unit_id: str, damage: int) -> list[dict]:
    unit = session["units"][unit_id]
    shield_before = unit["shield"]
    hull_before = unit["hull"]
    shield_loss = min(unit["shield"], damage)
    remaining = damage - shield_loss
    unit["shield"] -= shield_loss
    hull_loss = min(unit["hull"], remaining)
    unit["hull"] -= hull_loss

    events = [
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
    ]

    if unit["hull"] == 0 and not unit["destroyed"]:
        unit["destroyed"] = True
        events.append(event(session, "unit_destroyed", unit=unit_id))

    return events
