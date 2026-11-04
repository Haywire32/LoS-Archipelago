"""Seed-owned requirements for the render-only World Map check indicator."""
from __future__ import annotations

from .catalog import LEVELS
from .logic import AllOf, AnyOf, CHECK_REQUIREMENTS, COMPLETION_REQUIREMENTS, TRIAL_REQUIREMENTS
from .locations import LOCATION_TABLE


def encode_requirement(rule):
    if rule is None or isinstance(rule, str):
        return rule
    return {"all" if isinstance(rule, AllOf) else "any": [
        encode_requirement(child) for child in rule.requirements
    ]}


def seed_map_rules():
    """Snapshot generation rules, including completion requirements for trials."""
    result = {}
    for data in LOCATION_TABLE.values():
        if data.region == "Menu":
            continue
        rule = (COMPLETION_REQUIREMENTS.get(data.region)
                if data.bridge_key.startswith("level_complete:") else
                TRIAL_REQUIREMENTS.get(data.region)
                if data.bridge_key.startswith("trial_complete:") else
                CHECK_REQUIREMENTS.get(data.bridge_key))
        result[str(data.code)] = encode_requirement(rule)
    return result


def owns_requirement(rule, counts):
    if rule is None:
        return True
    if isinstance(rule, str):
        name = {"Silver Daggers": "Progressive Daggers", "Fairies": "Progressive Fairies"}.get(rule, rule)
        return counts.get(name, 0) > 0
    if not isinstance(rule, dict) or len(rule) != 1:
        return False
    if "all" in rule and isinstance(rule["all"], list):
        return all(owns_requirement(child, counts) for child in rule["all"])
    if "any" in rule and isinstance(rule["any"], list):
        return any(owns_requirement(child, counts) for child in rule["any"])
    return False


def map_check_states(unlocked_indices, enabled_locations, checked_locations, counts, rules):
    """46 digits: 0 unknown/locked, 1 available, 2 blocked, 3 fully cleared.

    Enabled locations come from Connected's checked+missing sets, so disabled
    trials, removed checks and skills never enter a level's totals. Excluded
    (filler-only) checks still count, just like any other enabled location.
    """
    if not isinstance(rules, dict):
        return "0" * 46  # Old seeds lack a trustworthy logic snapshot.
    by_level = {}
    for data in LOCATION_TABLE.values():
        if data.code in enabled_locations and data.region != "Menu":
            if str(data.code) not in rules:
                return "0" * 46
            by_level.setdefault(data.region, []).append(data.code)
    states = []
    for index, _, level, _ in LEVELS:
        if index > 46:
            continue
        locations = by_level.get(level, [])
        if index not in unlocked_indices or not locations:
            states.append("0")
            continue
        remaining = [code for code in locations if code not in checked_locations]
        if not remaining:
            states.append("3")
        elif any(str(code) not in rules for code in remaining):
            states.append("0")  # Do not report unknown requirements as reachable.
        elif any(owns_requirement(rules[str(code)], counts) for code in remaining):
            states.append("1")
        else:
            states.append("2")
    return "".join(states)
