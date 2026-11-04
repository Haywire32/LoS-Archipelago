from __future__ import annotations

from dataclasses import dataclass

from .catalog import COLLECTIBLES, LEVELS


LOCATION_ID_BASE = 20_131_000


@dataclass(frozen=True)
class LocationData:
    code: int
    region: str
    bridge_key: str


# Keep the collectible ranges stable for existing location IDs.
COLLECTIBLE_ID_OFFSETS = {
    "life_gem": 0,
    "dagger_ark": 100,
    "light_gem": 300,
    "dark_gem": 400,
    "vial_ark": 500,
    "fairy_ark": 600,
}


LOCATION_TABLE: dict[str, LocationData] = {}

for kind, global_flag, level_id, _local_id, bridge_key, display_name in COLLECTIBLES:
    LOCATION_TABLE[display_name] = LocationData(
        LOCATION_ID_BASE + COLLECTIBLE_ID_OFFSETS[kind] + global_flag,
        level_id,
        bridge_key,
    )

for map_index, _chapter, level_id, display_name in LEVELS:
    LOCATION_TABLE[f"{display_name} - Level Complete"] = LocationData(
        LOCATION_ID_BASE + 1000 + map_index,
        level_id,
        f"level_complete:{map_index}",
    )
    # AP starts from the retail World Map/replay path, which makes every
    # base-game trial available on its first AP visit, including Besieged
    # Village. DLC trials remain outside the supported catalog.
    if map_index <= 46:
        LOCATION_TABLE[f"{display_name} - Trial"] = LocationData(
            LOCATION_ID_BASE + 2000 + map_index,
            level_id,
            f"trial_complete:{map_index}",
        )


from .skills import SKILL_LOCATION_NAMES, SKILL_LOCATION_IDS
for action, name in SKILL_LOCATION_NAMES.items():
    LOCATION_TABLE[name] = LocationData(SKILL_LOCATION_IDS[action], 'Menu', 'skill:' + action)

LOCATION_NAME_TO_ID = {name: data.code for name, data in LOCATION_TABLE.items()}
BRIDGE_KEY_TO_LOCATION_ID = {
    data.bridge_key: data.code for data in LOCATION_TABLE.values()
}
TRIAL_LOCATION_IDS = frozenset(
    data.code
    for data in LOCATION_TABLE.values()
    if data.bridge_key.startswith("trial_complete:")
)
