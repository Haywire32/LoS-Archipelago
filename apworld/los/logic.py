from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, TypeAlias

from .logic_data import (
    CHECK_REQUIREMENT_ITEMS,
    COMPLETION_REQUIREMENT_ITEMS,
    TRIAL_REQUIREMENT_ITEMS,
)

if TYPE_CHECKING:
    from BaseClasses import CollectionState


@dataclass(frozen=True)
class AllOf:
    requirements: tuple["Requirement", ...]


@dataclass(frozen=True)
class AnyOf:
    requirements: tuple["Requirement", ...]


Requirement: TypeAlias = str | AllOf | AnyOf | None


def requirement_from_items(items: tuple[str, ...]) -> Requirement:
    if not items:
        return None
    if len(items) == 1:
        return items[0]
    return AllOf(items)


# These maps remain deliberately separate. A player may be able to reach one
# or more checks in a level without being able to complete that level.
CHECK_REQUIREMENTS: dict[str, Requirement] = {
    bridge_key: requirement_from_items(items)
    for bridge_key, items in CHECK_REQUIREMENT_ITEMS.items()
}
COMPLETION_REQUIREMENTS: dict[str, Requirement] = {
    level_id: requirement_from_items(items)
    for level_id, items in COMPLETION_REQUIREMENT_ITEMS.items()
}
# A trial needs the full completion route AND its own additional abilities.
# This does not restrict entry or early collectible checks within that level.
TRIAL_REQUIREMENTS: dict[str, Requirement] = {
    level_id: AllOf(
        tuple(
            requirement
            for requirement in (
                requirement_from_items(items),
                COMPLETION_REQUIREMENTS.get(level_id),
            )
            if requirement is not None
        )
    )
    for level_id, items in TRIAL_REQUIREMENT_ITEMS.items()
}


def requirement_met(
    state: "CollectionState", player: int, requirement: Requirement
) -> bool:
    if requirement is None:
        return True
    if isinstance(requirement, str):
        if requirement == "Silver Daggers":
            return state.has("Progressive Daggers", player)
        if requirement == "Fairies":
            return state.has("Progressive Fairies", player)
        return state.has(requirement, player)
    if isinstance(requirement, AllOf):
        return all(
            requirement_met(state, player, child)
            for child in requirement.requirements
        )
    return any(
        requirement_met(state, player, child)
        for child in requirement.requirements
    )
