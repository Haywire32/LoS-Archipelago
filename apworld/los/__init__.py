from __future__ import annotations
from importlib import resources

from BaseClasses import Item, ItemClassification, Location, Region, Tutorial
from worlds.AutoWorld import WebWorld, World
from Options import OptionError
from worlds.generic.Rules import set_rule

from .catalog import LEVELS
from .items import (
    EXPERIENCE_REWARD_NAMES,
    FINAL_LEVEL_ID,
    GENERAL_REFILL_ITEM_NAME,
    ITEM_NAME_TO_ID,
    ITEM_TABLE,
    LEVEL_ID_TO_ACCESS_ITEM,
    PAIRED_GEM_REWARD_COUNTS,
    SINGLE_GEM_REWARD_COUNTS,
    TRAP_ITEM_NAMES,
)
from .logic import (
    CHECK_REQUIREMENTS,
    COMPLETION_REQUIREMENTS,
    TRIAL_REQUIREMENTS,
    requirement_met,
)
from .locations import LOCATION_NAME_TO_ID, LOCATION_TABLE
from .options import LordsOfShadowOptions
from .skills import SKILL_ITEM_NAMES, SKILL_LOCATION_NAMES, purchase_relics
from .enemies import LAYOUT_VERSION, build_plan


GAME_NAME = "Castlevania: Lords of Shadow"
EXPERIENCE_REWARD_COUNT = 25
EARLY_SKILL_XP_ITEM = "3000 Experience Points"
EARLY_SKILL_XP_COUNT = 2
MAGIC_ITEMS = ("Light Magic", "Shadow Magic")


class LordsOfShadowItem(Item):
    game = GAME_NAME


class LordsOfShadowLocation(Location):
    game = GAME_NAME


class LordsOfShadowWeb(WebWorld):
    theme = "stone"
    tutorials = [
        Tutorial(
            "Setup Guide",
            "Connect Castlevania: Lords of Shadow to an Archipelago multiworld.",
            "English",
            "setup_en.md",
            "setup/en",
            ["Simon"],
        )
    ]


class LordsOfShadowWorld(World):
    """Research build for the Lords of Shadow Archipelago integration."""

    game = GAME_NAME
    web = LordsOfShadowWeb()
    options_dataclass = LordsOfShadowOptions
    options: LordsOfShadowOptions
    topology_present = True
    required_client_version = (0, 6, 7)

    item_name_to_id = ITEM_NAME_TO_ID
    location_name_to_id = LOCATION_NAME_TO_ID

    def generate_early(self) -> None:
        enemy_option = getattr(self.options, "randomize_minor_enemies", None)
        if enemy_option is not None and enemy_option.value:
            if not resources.files(__package__).joinpath("client/enemy_data/manifest.json").is_file():
                raise OptionError("Randomize Minor Enemies requires the experimental enemy-data APWorld.")
        if self.options.include_dlc.value:
            raise OptionError(
                "DLC levels are reserved but disabled for the first playable version."
            )
        self.active_levels = tuple(
            level
            for level in LEVELS
            if level[1] <= 12
        )
        ordinary_levels = [
            level for level in self.active_levels if level[2] != FINAL_LEVEL_ID
        ]
        starting_count = min(
            self.options.starting_level_count.value, len(ordinary_levels)
        )
        self.starting_level_ids = frozenset(
            level[2] for level in self.random.sample(ordinary_levels, starting_count)
        )
        starting_items = self.options.start_inventory_from_pool.value
        starting_magic = self.options.starting_magic.value
        selected_starting_magic = {
            self.options.starting_magic.option_light: ("Light Magic",),
            self.options.starting_magic.option_shadow: ("Shadow Magic",),
            self.options.starting_magic.option_both: MAGIC_ITEMS,
        }.get(starting_magic, ())
        # Reuse Archipelago's standard start-inventory-from-pool handling. It
        # removes the chosen copy from the randomized pool instead of creating
        # a duplicate magic item.
        for item_name in selected_starting_magic:
            starting_items[item_name] = max(1, int(starting_items.get(item_name, 0)))

        # Both magic types are mandatory for the final level and broadly useful.
        # When enabled, request one early copy of each type not already starting.
        if self.options.early_magic.value == self.options.early_magic.option_enabled:
            for item_name in MAGIC_ITEMS:
                if int(starting_items.get(item_name, 0)) < 1:
                    self.multiworld.early_items[self.player][item_name] = 1
        if self.options.skills_as_checks.value:
            # Put two XP packages on early, locally reachable non-shop checks.
            # Skill locations require both packages, so the placer cannot put
            # either package behind the purchases that need their XP.
            self.multiworld.local_early_items[self.player][EARLY_SKILL_XP_ITEM] = (
                EARLY_SKILL_XP_COUNT
            )

    def create_item(self, name: str) -> LordsOfShadowItem:
        data = ITEM_TABLE[name]
        classification = data.classification
        if name == EARLY_SKILL_XP_ITEM and self.options.skills_as_checks.value:
            # AP normally omits useful-only items from CollectionState. Skill
            # logic must count the two guaranteed XP packages, so these copies
            # become progression only for seeds that enable the paid shop.
            classification = ItemClassification.progression_skip_balancing
        return LordsOfShadowItem(name, classification, data.code, self.player)

    def create_regions(self) -> None:
        region_names = (
            "Menu",
            *(level_id for _, _, level_id, _ in self.active_levels),
        )
        regions = {
            name: Region(name, self.player, self.multiworld) for name in region_names
        }
        self.multiworld.regions.extend(regions.values())

        for location_name, data in LOCATION_TABLE.items():
            if data.bridge_key.startswith('skill:') and not self.options.skills_as_checks.value:
                continue
            if data.region not in regions:
                continue
            if (
                data.bridge_key.startswith("trial_complete:")
                and not self.options.trials_as_checks.value
            ):
                continue
            regions[data.region].locations.append(
                LordsOfShadowLocation(
                    self.player, location_name, data.code, regions[data.region]
                )
            )

        # Level entrances have no ability requirements. They are controlled
        # only by the seed's starting set or their individual Level Access item.
        for _, _, level_id, display_name in self.active_levels:
            if level_id == FINAL_LEVEL_ID:
                required = self.options.required_level_completions.value
                regions["Menu"].connect(
                    regions[level_id],
                    "Unlock Satan",
                    lambda state, required=required: state.has(
                        "Level Completion", self.player, required
                    ),
                )
            elif level_id in self.starting_level_ids:
                regions["Menu"].connect(
                    regions[level_id], f"Starting Level - {display_name}"
                )
            else:
                access_item = LEVEL_ID_TO_ACCESS_ITEM[level_id]
                regions["Menu"].connect(
                    regions[level_id],
                    f"Unlock {display_name}",
                    lambda state, access_item=access_item: state.has(
                        access_item, self.player
                    ),
                )

            if level_id != FINAL_LEVEL_ID:
                capability = LordsOfShadowLocation(
                    self.player,
                    f"{display_name} - Completion Capability",
                    None,
                    regions[level_id],
                )
                capability.place_locked_item(
                    LordsOfShadowItem(
                        "Level Completion",
                        ItemClassification.progression,
                        None,
                        self.player,
                    )
                )
                regions[level_id].locations.append(capability)

        goal = LordsOfShadowLocation(
            self.player, "Prototype Goal", None, regions["12_3_final_fight"]
        )
        goal.place_locked_item(
            LordsOfShadowItem(
                "Prototype Victory",
                ItemClassification.progression,
                None,
                self.player,
            )
        )
        regions["12_3_final_fight"].locations.append(goal)

    def create_items(self) -> None:
        created = 0
        if self.options.skills_as_checks.value:
            for item_name in SKILL_ITEM_NAMES.values():
                self.multiworld.itempool.append(self.create_item(item_name))
                created += 1
        for _, _, level_id, _ in self.active_levels:
            if level_id == FINAL_LEVEL_ID or level_id in self.starting_level_ids:
                continue
            self.multiworld.itempool.append(
                self.create_item(LEVEL_ID_TO_ACCESS_ITEM[level_id])
            )
            created += 1
        if self.options.focus_scroll.value == self.options.focus_scroll.option_enabled:
            self.multiworld.push_precollected(self.create_item("Focus Scroll"))
        else:
            self.multiworld.itempool.append(self.create_item("Focus Scroll"))
            created += 1
        for item_name, data in ITEM_TABLE.items():
            for _ in range(data.count):
                self.multiworld.itempool.append(self.create_item(item_name))
                created += 1
        gem_rewards = (
            SINGLE_GEM_REWARD_COUNTS
            if self.options.trials_as_checks.value
            else PAIRED_GEM_REWARD_COUNTS
        )
        for item_name, count in gem_rewards.items():
            for _ in range(count):
                self.multiworld.itempool.append(self.create_item(item_name))
                created += 1
        for index in range(EXPERIENCE_REWARD_COUNT):
            self.multiworld.itempool.append(
                self.create_item(EXPERIENCE_REWARD_NAMES[index % len(EXPERIENCE_REWARD_NAMES)])
            )
            created += 1
        unfilled_locations = sum(
            location.address is not None and location.item is None
            for location in self.multiworld.get_locations(self.player)
        )
        remaining = unfilled_locations - created
        if remaining < 0:
            raise OptionError(
                f"The selected reward settings create {-remaining} more items than checks."
            )
        trap_percentage = self.options.trap_frequency.value
        # Archipelago replaces each start_inventory_from_pool item with filler
        # after create_items finishes. Include those future filler copies in the
        # percentage calculation so starting magic does not dilute the chosen
        # trap frequency.
        replacement_filler_count = sum(
            max(0, int(count))
            for count in self.options.start_inventory_from_pool.value.values()
        )
        trap_family_count = remaining + replacement_filler_count
        requested_trap_count = int(
            (trap_family_count * trap_percentage / 100.0) + 0.5
        )
        trap_count = min(remaining, requested_trap_count)
        self.replacement_traps_remaining = requested_trap_count - trap_count
        self.replacement_trap_index = trap_count
        # Keep the two owner-approved traps as even as possible. Item placement
        # itself remains randomized by Archipelago.
        for index in range(trap_count):
            self.multiworld.itempool.append(
                self.create_item(TRAP_ITEM_NAMES[index % len(TRAP_ITEM_NAMES)])
            )
        for _ in range(remaining - trap_count):
            self.multiworld.itempool.append(self.create_item(GENERAL_REFILL_ITEM_NAME))

    def get_filler_item_name(self) -> str:
        if getattr(self, "replacement_traps_remaining", 0) > 0:
            index = getattr(self, "replacement_trap_index", 0)
            self.replacement_traps_remaining -= 1
            self.replacement_trap_index = index + 1
            return TRAP_ITEM_NAMES[index % len(TRAP_ITEM_NAMES)]
        return GENERAL_REFILL_ITEM_NAME

    def set_rules(self) -> None:
        if self.options.skills_as_checks.value:
            for action, location_name in SKILL_LOCATION_NAMES.items():
                required = purchase_relics(action)
                set_rule(self.multiworld.get_location(location_name, self.player),
                         lambda state, required=required: state.has(
                             EARLY_SKILL_XP_ITEM, self.player, EARLY_SKILL_XP_COUNT
                         )
                         and all(state.has(item, self.player) for item in required))
        active_level_ids = {level[2] for level in self.active_levels}
        for location_name, data in LOCATION_TABLE.items():
            if data.region not in active_level_ids:
                continue
            if (
                data.bridge_key.startswith("trial_complete:")
                and not self.options.trials_as_checks.value
            ):
                continue
            requirement = (
                COMPLETION_REQUIREMENTS.get(data.region)
                if data.bridge_key.startswith("level_complete:")
                else (
                    TRIAL_REQUIREMENTS.get(data.region)
                    if data.bridge_key.startswith("trial_complete:")
                    else CHECK_REQUIREMENTS.get(data.bridge_key)
                )
            )
            set_rule(
                self.multiworld.get_location(location_name, self.player),
                lambda state, requirement=requirement: requirement_met(
                    state, self.player, requirement
                ),
            )
        for _, _, level_id, display_name in self.active_levels:
            if level_id == FINAL_LEVEL_ID:
                continue
            requirement = COMPLETION_REQUIREMENTS.get(level_id)
            set_rule(
                self.multiworld.get_location(
                    f"{display_name} - Completion Capability", self.player
                ),
                lambda state, requirement=requirement: requirement_met(
                    state, self.player, requirement
                ),
            )
        final_requirement = COMPLETION_REQUIREMENTS.get(FINAL_LEVEL_ID)
        set_rule(
            self.multiworld.get_location("Prototype Goal", self.player),
            lambda state, requirement=final_requirement: requirement_met(
                state, self.player, requirement
            ),
        )
        self.multiworld.completion_condition[self.player] = (
            lambda state: state.has("Prototype Victory", self.player)
        )

    def generate_output(self, output_directory: str) -> None:
        if self.options.randomize_minor_enemies.value:
            import json
            from pathlib import Path
            manifest=json.loads(resources.files(__package__).joinpath('client/enemy_data/manifest.json').read_text())
            plan=build_plan(str(self.multiworld.seed_name),manifest['spawn_catalog'])
            name=self.multiworld.get_out_file_name_base(self.player)+'.los-enemies.json'
            Path(output_directory,name).write_text(json.dumps(plan,sort_keys=True),encoding='utf-8')

    def fill_slot_data(self) -> dict[str, object]:
        from .map_checks import seed_map_rules
        excluded_names = set(self.options.exclude_locations.value)
        return {
            "world_map_protocol": 1,
            "show_logic_colors": bool(self.options.show_logic_colors.value),
            "world_map_rules": seed_map_rules(),
            "bridge_protocol": 2,
            "randomize_minor_enemies": bool(self.options.randomize_minor_enemies.value),
            "enemy_layout_version": LAYOUT_VERSION,
            "enemy_preload_required": bool(self.options.randomize_minor_enemies.value),
            "skills_as_checks": bool(self.options.skills_as_checks.value),
            "reveal_skill_rewards": bool(self.options.skills_as_checks.value and self.options.reveal_skill_rewards.value),
            "skill_protocol": 1,
            "skill_xp_farm": None,
            "reward_seed_id": str(self.multiworld.seed_name),
            "prototype": "level_access_logic_scaffold",
            "starting_level_indices": [
                map_index
                for map_index, _, level_id, _ in self.active_levels
                if level_id in self.starting_level_ids
            ],
            "required_level_completions": self.options.required_level_completions.value,
            "focus_scroll": self.options.focus_scroll.current_key,
            "starting_magic": self.options.starting_magic.current_key,
            "early_magic": self.options.early_magic.current_key,
            "trap_frequency": self.options.trap_frequency.current_key,
            "ignored_completion_location_ids": sorted(
                LOCATION_NAME_TO_ID[name]
                for name in excluded_names
                if name in LOCATION_TABLE
                and LOCATION_TABLE[name].bridge_key.startswith("level_complete:")
            ),
            "include_dlc": bool(self.options.include_dlc.value),
            "trials_as_checks": bool(self.options.trials_as_checks.value),
        }


# Register the bundled launcher client after the world has been defined.  The
# client itself is imported lazily, so generators and web hosts do not start it.
from . import components as components  # noqa: E402,F401
