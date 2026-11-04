from __future__ import annotations

from dataclasses import dataclass

from BaseClasses import ItemClassification

from .catalog import LEVELS


ITEM_ID_BASE = 20_130_000


@dataclass(frozen=True)
class ItemData:
    code: int
    classification: ItemClassification
    count: int = 1


ITEM_TABLE: dict[str, ItemData] = {
    "Hook Tip": ItemData(ITEM_ID_BASE + 1, ItemClassification.progression),
    "Light Magic": ItemData(ITEM_ID_BASE + 2, ItemClassification.progression),
    "Focus Scroll": ItemData(ITEM_ID_BASE + 3, ItemClassification.progression, count=0),
    "Cyclone Boots": ItemData(ITEM_ID_BASE + 4, ItemClassification.progression),
    "Dagger Capacity Upgrade": ItemData(
        ITEM_ID_BASE + 5, ItemClassification.useful, count=0
    ),
    "Life Gem": ItemData(ITEM_ID_BASE + 6, ItemClassification.useful, count=0),
    # The pool size is calculated from the enabled locations in create_items.
    "Research Token": ItemData(ITEM_ID_BASE + 7, ItemClassification.filler, count=0),
    "Light Gem": ItemData(ITEM_ID_BASE + 8, ItemClassification.useful, count=0),
    "Shadow Gem": ItemData(ITEM_ID_BASE + 9, ItemClassification.useful, count=0),
    "Vial Capacity Upgrade": ItemData(
        ITEM_ID_BASE + 10, ItemClassification.useful, count=0
    ),
    "Fairy Capacity Upgrade": ItemData(
        ITEM_ID_BASE + 11, ItemClassification.useful, count=0
    ),
    "Spiked Chain": ItemData(ITEM_ID_BASE + 12, ItemClassification.progression),
    "Stake": ItemData(ITEM_ID_BASE + 13, ItemClassification.progression),
    "Dark Gauntlet": ItemData(ITEM_ID_BASE + 14, ItemClassification.progression),
    "Seraph Shoulders": ItemData(ITEM_ID_BASE + 15, ItemClassification.progression),
    "Shadow Magic": ItemData(ITEM_ID_BASE + 16, ItemClassification.progression),
    "Dark Crystal": ItemData(
        ITEM_ID_BASE + 17, ItemClassification.progression
    ),
    "Fairies": ItemData(ITEM_ID_BASE + 18, ItemClassification.progression, count=0),
    "Silver Daggers": ItemData(
        ITEM_ID_BASE + 19, ItemClassification.progression, count=0
    ),
    # Public-facing combined unlock/capacity items.  The first copy enables
    # the subweapon and each later copy raises its retail carrying capacity.
    "Progressive Daggers": ItemData(
        ITEM_ID_BASE + 20, ItemClassification.progression, count=6
    ),
    "Progressive Holy Water": ItemData(
        ITEM_ID_BASE + 21, ItemClassification.progression, count=4
    ),
    "Progressive Fairies": ItemData(
        ITEM_ID_BASE + 22, ItemClassification.progression, count=4
    ),
    "2 Life Gems": ItemData(ITEM_ID_BASE + 23, ItemClassification.useful, count=0),
    "2 Light Gems": ItemData(ITEM_ID_BASE + 24, ItemClassification.useful, count=0),
    "2 Shadow Gems": ItemData(ITEM_ID_BASE + 25, ItemClassification.useful, count=0),
    "1500 Experience Points": ItemData(ITEM_ID_BASE + 26, ItemClassification.useful, count=0),
    "2000 Experience Points": ItemData(ITEM_ID_BASE + 27, ItemClassification.useful, count=0),
    "2500 Experience Points": ItemData(ITEM_ID_BASE + 28, ItemClassification.useful, count=0),
    "Consumables Refill": ItemData(ITEM_ID_BASE + 29, ItemClassification.filler, count=0),
    "Magic Drain Trap": ItemData(ITEM_ID_BASE + 30, ItemClassification.trap, count=0),
    "Poison Trap": ItemData(ITEM_ID_BASE + 31, ItemClassification.trap, count=0),
    "3000 Experience Points": ItemData(ITEM_ID_BASE + 32, ItemClassification.useful, count=0),
}


SINGLE_GEM_REWARD_COUNTS = {
    "Life Gem": 30,
    "Light Gem": 30,
    "Shadow Gem": 30,
}
PAIRED_GEM_REWARD_COUNTS = {
    "2 Life Gems": 15,
    "2 Light Gems": 15,
    "2 Shadow Gems": 15,
}


EXPERIENCE_REWARD_NAMES = (
    "2000 Experience Points",
    "2500 Experience Points",
    "3000 Experience Points",
    "2500 Experience Points",
    "3000 Experience Points",
)
GENERAL_REFILL_ITEM_NAME = "Consumables Refill"
TRAP_ITEM_NAMES = ("Magic Drain Trap", "Poison Trap")
FINAL_LEVEL_ID = "12_3_final_fight"
LEVEL_ACCESS_ITEMS: dict[str, tuple[int, str]] = {}
for map_index, _chapter, level_id, display_name in LEVELS:
    if level_id == FINAL_LEVEL_ID:
        continue
    item_name = f"{display_name} Access"
    ITEM_TABLE[item_name] = ItemData(
        ITEM_ID_BASE + 1000 + map_index,
        ItemClassification.progression,
        count=0,
    )
    LEVEL_ACCESS_ITEMS[item_name] = (map_index, level_id)

LEVEL_ID_TO_ACCESS_ITEM = {
    level_id: item_name
    for item_name, (_map_index, level_id) in LEVEL_ACCESS_ITEMS.items()
}

from .skills import SKILL_ITEM_NAMES, SKILL_ITEM_IDS
for action, name in SKILL_ITEM_NAMES.items():
    ITEM_TABLE[name] = ItemData(SKILL_ITEM_IDS[action], ItemClassification.useful, count=0)

ITEM_NAME_TO_ID = {name: data.code for name, data in ITEM_TABLE.items()}
PROGRESSION_ITEMS = {
    name
    for name, data in ITEM_TABLE.items()
    if data.classification & ItemClassification.progression
}
