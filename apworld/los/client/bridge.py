from __future__ import annotations

from importlib import resources
import time
import os
import logging
from typing import Any

from ..catalog import LEVELS
from ..items import ITEM_NAME_TO_ID, LEVEL_ACCESS_ITEMS
from ..locations import BRIDGE_KEY_TO_LOCATION_ID
from .dropin_transport import DropInTransport, DropInUnavailable


class BridgeUnavailable(RuntimeError):
    pass


FLAG_LISTS = {
    "life_flags": "life_gem",
    "light_flags": "light_gem",
    "dark_flags": "dark_gem",
    "vial_upgrade_flags": "vial_ark",
    "dagger_upgrade_flags": "dagger_ark",
    "fairy_upgrade_flags": "fairy_ark",
}

LEVEL_INDEX_TO_ID = {map_index: level_id for map_index, _, level_id, _ in LEVELS}
FINAL_LEVEL_INDEX = 46
COLLECTIBLE_EVENT_PREFIXES = (
    (1, 30, "life_gem", 0),
    (31, 60, "light_gem", 30),
    (61, 90, "dark_gem", 60),
    (91, 95, "dagger_ark", 90),
    (96, 98, "vial_ark", 95),
    (99, 101, "fairy_ark", 98),
)
LEVEL_COMPLETION_LOCATION_IDS = {
    location_id
    for bridge_key, location_id in BRIDGE_KEY_TO_LOCATION_ID.items()
    if bridge_key.startswith("level_complete:")
}
LEVEL_COMPLETION_INDEX_BY_LOCATION_ID = {
    location_id: int(bridge_key.split(":", 1)[1])
    for bridge_key, location_id in BRIDGE_KEY_TO_LOCATION_ID.items()
    if bridge_key.startswith("level_complete:")
}

RECEIVED_INVENTORY = (
    ("life", "Life Gems", 30),
    ("light", "Light Gems", 30),
    ("dark", "Shadow Gems", 30),
    ("dagger", "Progressive Daggers", 5),
    ("vial", "Progressive Holy Water", 3),
    ("fairy", "Progressive Fairies", 3),
)

RECEIVED_ABILITIES = (
    ("Hook Tip", "hook-enable"),
    ("Spiked Chain", "spiked"),
    ("Stake", "stake"),
    ("Dark Gauntlet", "gauntlet"),
    ("Cyclone Boots", "cyclone"),
    ("Seraph Shoulders", "seraph"),
    ("Light Magic", "light"),
    ("Shadow Magic", "shadow"),
    ("Dark Crystal", "crystal"),
    ("Progressive Fairies", "fairies"),
    ("Progressive Daggers", "daggers"),
    ("Progressive Holy Water", "holy-water"),
    ("Focus Scroll", "focus"),
)

# Keep every ability with an independently readable ownership field exact: a
# vanilla story grant is removed until Archipelago has sent that item. Hook Tip
# and Spiked Chain share a visual chain-model value, but have independent AP
# ownership gates. Retail story pickups are deliberately not Archipelago locations:
# their original rewards are suppressed and ownership comes only from received
# Archipelago items.
RECONCILED_ABILITIES = (
    ("Stake", "stake"),
    ("Dark Gauntlet", "gauntlet"),
    ("Cyclone Boots", "cyclone"),
    ("Seraph Shoulders", "seraph"),
    ("Light Magic", "light"),
    ("Shadow Magic", "shadow"),
    ("Dark Crystal", "crystal"),
    ("Progressive Fairies", "fairies"),
    ("Progressive Daggers", "daggers"),
    ("Progressive Holy Water", "holy-water"),
    ("Focus Scroll", "focus"),
)
RECONCILED_ABILITY_NAMES = {
    "Hook Tip",
    "Spiked Chain",
    *(item_name for item_name, _command in RECONCILED_ABILITIES),
}
ABILITY_BIT_BY_NAME = {
    item_name: bit for bit, (item_name, _command) in enumerate(RECEIVED_ABILITIES)
}
INVENTORY_PACKING = (
    ("life", 5, 0),
    ("light", 5, 5),
    ("dark", 5, 10),
    ("dagger", 3, 15),
    ("vial", 2, 18),
    ("fairy", 2, 20),
)
INSTANT_REWARD_ITEMS = (
    "1500 Experience Points",
    "2000 Experience Points",
    "2500 Experience Points",
    "3000 Experience Points",
    "Consumables Refill",
    "Magic Drain Trap",
    "Poison Trap",
)


def completed_level_indices(raw_status: Any) -> set[int]:
    completed: set[int] = set()
    for index, value in enumerate(str(raw_status or "").split(","), start=1):
        try:
            if int(value.strip()) > 0:
                completed.add(index)
        except ValueError:
            continue
    return completed


def ap_completed_level_indices(location_ids: set[int]) -> set[int]:
    """Translate checked AP completion locations into retail World Map indices."""
    return {
        LEVEL_COMPLETION_INDEX_BY_LOCATION_ID[location_id]
        for location_id in location_ids
        if location_id in LEVEL_COMPLETION_INDEX_BY_LOCATION_ID
    }


def lua_utf8_literal(value: str, maximum_bytes: int = 512) -> str:
    """Encode untrusted AP text as an ASCII-only Lua 5.1 string literal."""
    encoded = str(value).encode("utf-8")[:maximum_bytes]
    # Decimal byte escapes avoid executable quotes, slashes, newlines, and any
    # locale-dependent source decoding inside the retail Lua 5.1 runtime.
    return '"' + "".join(f"\\{byte:03d}" for byte in encoded) + '"'


def completed_trial_indices(low_mask: Any, high_mask: Any) -> set[int]:
    completed: set[int] = set()
    for raw_mask, first, last in ((low_mask, 1, 23), (high_mask, 24, 46)):
        try:
            mask = int(float(str(raw_mask or "0")))
        except ValueError:
            continue
        for index in range(first, last + 1):
            if mask & (1 << (index - first)):
                completed.add(index)
    return completed


def checks_from_state(game_state: dict[str, Any]) -> set[str]:
    checks: set[str] = set()
    for field, prefix in FLAG_LISTS.items():
        for index, flag in enumerate(str(game_state.get(field, "")), start=1):
            if flag == "X":
                checks.add(f"{prefix}:{index}")
    checks.update(
        f"level_complete:{index}"
        for index in completed_level_indices(
            game_state.get("level_completion_status", "")
        )
    )
    checks.update(
        f"trial_complete:{index}"
        for index in completed_trial_indices(
            game_state.get("trial_low_mask", "0"),
            game_state.get("trial_high_mask", "0"),
        )
    )
    return checks


def location_ids_from_state(game_state: dict[str, Any]) -> set[int]:
    return {
        BRIDGE_KEY_TO_LOCATION_ID[key]
        for key in checks_from_state(game_state)
        if key in BRIDGE_KEY_TO_LOCATION_ID
    }


def received_item_counts(items: list[Any]) -> dict[str, int]:
    id_to_name = {item_id: name for name, item_id in ITEM_NAME_TO_ID.items()}
    counts: dict[str, int] = {}
    for network_item in items:
        name = id_to_name.get(int(network_item.item))
        if name is not None:
            counts[name] = counts.get(name, 0) + 1
    return counts


def instant_reward_totals(received_counts: dict[str, int]) -> dict[str, int]:
    """Return cumulative receipt totals for one-shot rewards."""
    return {
        "experience": (
            1500 * received_counts.get("1500 Experience Points", 0)
            + 2000 * received_counts.get("2000 Experience Points", 0)
            + 2500 * received_counts.get("2500 Experience Points", 0)
            + 3000 * received_counts.get("3000 Experience Points", 0)
        ),
        "refill": received_counts.get("Consumables Refill", 0),
        # Progressive subweapon copies are durable ownership, but each newly
        # received copy should also fill that subweapon to its new capacity once.
        # The reward ledger makes these grants reconnect-safe.
        "dagger": received_counts.get("Progressive Daggers", 0),
        "vial": received_counts.get("Progressive Holy Water", 0),
        "fairy": received_counts.get("Progressive Fairies", 0),
        "crystal": received_counts.get("Dark Crystal", 0),
        "magic_drain": received_counts.get("Magic Drain Trap", 0),
        "poison": received_counts.get("Poison Trap", 0),
    }


def bridge_inventory_counts(raw_counts: Any) -> dict[str, int]:
    values = str(raw_counts or "").split(",")
    if len(values) != len(RECEIVED_INVENTORY):
        return {}
    parsed: dict[str, int] = {}
    for (inventory_type, _item_name, _maximum), value in zip(
        RECEIVED_INVENTORY, values
    ):
        try:
            parsed[inventory_type] = int(value)
        except ValueError:
            return {}
    return parsed


def received_ability_enabled(item_name: str, game_state: dict[str, Any]) -> bool:
    if item_name == "Hook Tip":
        return str(game_state.get("hook_tip_owned", "")).lower() == "true"
    if item_name == "Spiked Chain":
        return str(game_state.get("hook_tip")) == "3"
    if item_name == "Stake":
        return str(game_state.get("stake_available", "")).lower() == "true"
    if item_name == "Dark Gauntlet":
        return str(game_state.get("dark_gauntlet", "")).lower() == "true"
    if item_name == "Cyclone Boots":
        return (
            str(game_state.get("cyclone_sprint")) == "1"
            and str(game_state.get("cyclone_dark_dash", "")).lower() == "true"
        )
    if item_name == "Seraph Shoulders":
        return str(game_state.get("seraph_shoulders", "")).lower() == "true"
    if item_name == "Light Magic":
        return str(game_state.get("light_power_on", "")).lower() == "true"
    if item_name == "Shadow Magic":
        return str(game_state.get("dark_power_on", "")).lower() == "true"
    if item_name == "Dark Crystal":
        return str(game_state.get("dark_crystal", "")).lower() == "true"
    if item_name == "Progressive Fairies":
        return str(game_state.get("fairies_enabled", "")).lower() == "true"
    if item_name == "Progressive Daggers":
        controls = silver_dagger_controls(game_state)
        return all(controls)
    if item_name == "Progressive Holy Water":
        return str(game_state.get("holy_water_enabled", "")).lower() == "true"
    if item_name == "Focus Scroll":
        return (
            str(game_state.get("focus_unlocked", "")).lower() == "true"
            and str(game_state.get("focus_gameplay_enabled", "")).lower() == "true"
        )
    raise ValueError(f"unknown received ability: {item_name}")


def silver_dagger_controls(
    game_state: dict[str, Any],
) -> tuple[bool, bool, bool, bool, bool, bool]:
    """Return every independent retail dagger ownership control."""
    active = str(game_state.get("silver_daggers", "")).lower() == "true"
    secondary_status = str(game_state.get("dagger_action_status", ""))
    dagger_status = str(game_state.get("dagger_move_action_status", ""))
    combo_status = str(game_state.get("dagger_combo_action_status", ""))
    unlocked = lambda value: value not in {"", "nil", "Locked"}
    guard_enabled = (
        str(game_state.get("dagger_throw_guard_enabled", "")).lower() == "true"
    )
    guard_owned = (
        str(game_state.get("dagger_throw_guard_owned", "")).lower() == "true"
    )
    return (
        active,
        unlocked(secondary_status),
        unlocked(dagger_status),
        unlocked(combo_status),
        guard_enabled,
        guard_owned,
    )


def desired_chain_value(received_counts: dict[str, int]) -> int:
    """Return the exact visual chain model; Hook Tip ownership is separate."""
    if received_counts.get("Spiked Chain", 0) > 0:
        return 3
    if received_counts.get("Hook Tip", 0) > 0:
        return 2
    return 1


def normalized_level_id(game_state: dict[str, Any]) -> str:
    level_name = str(game_state.get("level_name", "")).strip()
    if level_name.startswith("level."):
        return level_name[len("level.") :]
    return level_name


def defer_mandatory_tutorial_removal(
    item_name: str,
    game_state: dict[str, Any],
) -> bool:
    """Keep tutorial-required vanilla abilities until their scene can finish."""
    level_id = normalized_level_id(game_state)
    if item_name == "Progressive Daggers" and level_id == "1_1_besieged_village":
        # Retail sets this flag immediately after the mandatory pickup has
        # created its SecondaryWeapon and Dagger actions.  Keep the tutorial
        # functional until that exact point, then let AP remove an unreceived
        # dagger unlock while the level is still running.
        return (
            str(game_state.get("dagger_tutorial_completed", "false")).lower()
            != "true"
        )
    if (
        item_name == "Light Magic"
        and level_id == "2_2_enchanted_forest"
        and str(game_state.get("light_tutorial_block_triggered", "")).lower()
        != "true"
    ):
        return True
    return False


def packed_ability_mask(
    received_counts: dict[str, int],
    game_state: dict[str, Any],
) -> int:
    mask = 0
    for item_name, _command in RECEIVED_ABILITIES:
        desired = received_counts.get(item_name, 0) > 0
        if not desired and defer_mandatory_tutorial_removal(item_name, game_state):
            # Besieged Village freezes if its mandatory dagger tutorial is
            # entered with SecondaryWeapon locked. Keep both retail controls
            # enabled for that level, then remove them after the transition.
            desired = (
                True
                if item_name == "Progressive Daggers"
                else received_ability_enabled(item_name, game_state)
            )
        if desired:
            mask |= 1 << ABILITY_BIT_BY_NAME[item_name]
    return mask


def desired_inventory_counts(received_counts: dict[str, int]) -> dict[str, int]:
    return {
        "life": min(
            received_counts.get("Life Gem", 0)
            + 2 * received_counts.get("2 Life Gems", 0),
            30,
        ),
        "light": min(
            received_counts.get("Light Gem", 0)
            + 2 * received_counts.get("2 Light Gems", 0),
            30,
        ),
        "dark": min(
            received_counts.get("Shadow Gem", 0)
            + received_counts.get("Dark Gem", 0)
            + 2 * received_counts.get("2 Shadow Gems", 0),
            30,
        ),
        "dagger": min(
            max(received_counts.get("Progressive Daggers", 0) - 1, 0)
            + received_counts.get("Dagger Capacity Upgrade", 0),
            5,
        ),
        "vial": min(
            max(received_counts.get("Progressive Holy Water", 0) - 1, 0)
            + received_counts.get("Vial Capacity Upgrade", 0),
            3,
        ),
        "fairy": min(
            max(received_counts.get("Progressive Fairies", 0) - 1, 0)
            + received_counts.get("Fairy Capacity Upgrade", 0),
            3,
        ),
    }


def packed_inventory_mask(counts: dict[str, int]) -> int:
    mask = 0
    for inventory_type, width, shift in INVENTORY_PACKING:
        value = int(counts.get(inventory_type, 0))
        if value < 0 or value >= 1 << width:
            raise ValueError(f"{inventory_type} inventory count does not fit")
        mask |= value << shift
    return mask


def packed_level_mask(indices: set[int], first: int, last: int) -> int:
    if first < 1 or last > 46 or first > last or last - first >= 23:
        raise ValueError("invalid base-game level mask range")
    mask = 0
    for index in indices:
        if first <= index <= last:
            mask |= 1 << (index - first)
    return mask


def requested_level_indices(
    received_counts: dict[str, int],
    starting_level_indices: list[int] | tuple[int, ...] = (),
    required_level_completions: int = 25,
    completed_level_count: int = 0,
) -> set[int]:
    indices = {
        int(index)
        for index in starting_level_indices
        if int(index) in LEVEL_INDEX_TO_ID
    }
    indices.update(
        map_index
        for item_name, (map_index, _level_id) in LEVEL_ACCESS_ITEMS.items()
        if received_counts.get(item_name, 0) > 0
    )
    if completed_level_count >= required_level_completions:
        indices.add(FINAL_LEVEL_INDEX)
    return indices


def bridge_key_from_event(event_type: str, event_index: int) -> str | None:
    if event_type == "completion" and event_index in LEVEL_INDEX_TO_ID:
        return f"level_complete:{event_index}"
    if event_type == "collectible":
        for first, last, prefix, offset in COLLECTIBLE_EVENT_PREFIXES:
            if first <= event_index <= last:
                return f"{prefix}:{event_index - offset}"
    return None


class NativeBridge:
    def __init__(self) -> None:
        try:
            if os.name == 'nt' and os.environ.get('LOS_AP_SOCKET') != '1':
                self.transport = DropInTransport()
            else:
                from .socket_transport import SocketTransport
                self.transport = SocketTransport()
        except DropInUnavailable as exc:
            raise BridgeUnavailable(str(exc)) from exc
        self._last_world_map_ui_signature: tuple[int, int, int, int, str] | None = None

    def close(self) -> None:
        self.transport.close()

    @staticmethod
    def _template(name: str) -> str:
        package = resources.files(__package__)
        source = package.joinpath(name).read_text(encoding="utf-8")
        if name == "prepare_menu.lua":
            source = package.joinpath("replay_access.lua").read_text(encoding="utf-8") + "\n" + source
        return source

    @classmethod
    def _render_template(cls, name: str, values: dict[str, int]) -> str:
        source = cls._template(name)
        for token, value in values.items():
            marker = f"__{token}__"
            if marker not in source:
                raise BridgeUnavailable(f"The {name} template is missing {marker}")
            source = source.replace(marker, str(int(value)))
        if "__" in source:
            raise BridgeUnavailable(f"The {name} template is incomplete")
        return source

    @classmethod
    def _render_source_template(cls, name: str, values: dict[str, str]) -> str:
        source = cls._template(name)
        for token, value in values.items():
            marker = f"__{token}__"
            if marker not in source:
                raise BridgeUnavailable(f"The {name} template is missing {marker}")
            source = source.replace(marker, str(value))
        if "__" in source:
            raise BridgeUnavailable(f"The {name} template is incomplete")
        return source

    def _execute_lua(self, source: str) -> str:
        try:
            result = self.transport.execute(source)
            if getattr(self.transport, 'diagnostics_enabled', False):
                stage = result.split('|')[:2] if result.startswith('--APMENUSTART|') else None
                if stage and stage != getattr(self, '_last_start_stage', None):
                    logging.getLogger('LoSBridge').info('Startup reply: %s', '|'.join(stage))
                    self._last_start_stage = stage
            return result
        except DropInUnavailable as exc:
            raise BridgeUnavailable(str(exc)) from exc

    def run(self, *arguments: str) -> dict[str, Any]:
        if not arguments:
            raise BridgeUnavailable("The game bridge command is missing")
        command = arguments[0]
        if command == "probe-game":
            result = self._execute_lua(
                'Game.Set("InitLuaLine","--APDROPIN|OK")'
            )
            if result != "--APDROPIN|OK":
                raise BridgeUnavailable("The in-game bridge probe failed")
            return {"ok": True, "transport": "drop-in-dinput8", "result": result}
        if command == "read-state":
            result = self._execute_lua(self._template("state_query.lua"))
            if not result.startswith("L=") or "|N=" not in result:
                raise BridgeUnavailable("The read-only progression query failed")
            return {"ok": True, "transport": "drop-in-dinput8", "state": result}
        if command == "sync-state" and len(arguments) == 5:
            source = self._render_template(
                "sync_state.lua",
                {
                    "ABILITY_MASK": int(arguments[1]),
                    "INVENTORY_MASK": int(arguments[2]),
                    "LEVEL_LOW_MASK": int(arguments[3]),
                    "LEVEL_HIGH_MASK": int(arguments[4]),
                },
            )
            result = self._execute_lua(source)
            if result != "--APSYNC|OK":
                raise BridgeUnavailable(
                    f"Synchronous state reconciliation failed: {result}"
                )
            return {"ok": True, "transport": "drop-in-dinput8", "result": result}
        if command == "grant-rewards" and len(arguments) == 7:
            source = self._render_template(
                "grant_rewards.lua",
                dict(
                    zip(
                        ("EXPERIENCE", "REFILL", "DAGGER", "VIAL", "FAIRY", "CRYSTAL"),
                        (int(value) for value in arguments[1:]),
                    )
                ),
            )
            result = self._execute_lua(source)
            if result != "--APREWARD|OK":
                raise BridgeUnavailable(f"Instant reward delivery failed: {result}")
            return {"ok": True, "transport": "drop-in-dinput8", "result": result}
        if command == "apply-traps" and len(arguments) == 3:
            source = self._render_template(
                "apply_traps.lua",
                {
                    "MAGIC_DRAIN": int(arguments[1]),
                    "POISON": int(arguments[2]),
                },
            )
            result = self._execute_lua(source)
            if result.startswith("--APTRAP|NOTREADY|"):
                return {
                    "ok": True,
                    "applied": False,
                    "transport": "drop-in-dinput8",
                    "result": result,
                }
            if result != "--APTRAP|OK":
                raise BridgeUnavailable(f"Trap delivery failed: {result}")
            return {
                "ok": True,
                "applied": True,
                "transport": "drop-in-dinput8",
                "result": result,
            }
        if command == "prepare-menu" and len(arguments) == 3:
            source = self._render_template(
                "prepare_menu.lua",
                {
                    "LEVEL_LOW_MASK": int(arguments[1]),
                    "LEVEL_HIGH_MASK": int(arguments[2]),
                },
            )
            result = self._execute_lua(source)
            if result.startswith("--APMENUSTART|NOTMENU|"):
                return {"ok": True, "menu": False, "result": result}
            if not result.startswith("--APMENUSTART|ARMED|"):
                raise BridgeUnavailable(f"Main-menu authorization failed: {result}")
            return {"ok": True, "menu": True, "result": result}
        if command == "sync-world-map-ui" and len(arguments) in (5, 6):
            check_states = arguments[5] if len(arguments) == 6 else "0" * 46
            if len(check_states) != 46 or any(c not in "0123" for c in check_states):
                raise ValueError("Invalid World Map check states")
            source = self._render_source_template(
                "world_map_ui.lua",
                {
                    "COMPLETION_LOW_MASK": int(arguments[1]),
                    "COMPLETION_HIGH_MASK": int(arguments[2]),
                    "COMPLETED_COUNT": int(arguments[3]),
                    "REQUIRED_COUNT": int(arguments[4]),
                    "CHECK_STATES": check_states,
                },
            )
            result = self._execute_lua(source)
            if result.startswith("--APMAPUI|NOTREADY|"):
                return {
                    "ok": True,
                    "applied": False,
                    "transport": "drop-in-dinput8",
                    "result": result,
                }
            if result != "--APMAPUI|OK":
                raise BridgeUnavailable(f"World Map display synchronization failed: {result}")
            return {
                "ok": True,
                "applied": True,
                "transport": "drop-in-dinput8",
                "result": result,
            }
        raise BridgeUnavailable(f"Unsupported in-game bridge command: {command}")

    def _dump_monitor_script(
        self,
        ability_mask: int,
        inventory_mask: int,
        level_low_mask: int,
        level_high_mask: int,
    ) -> str:
        script = self._render_template(
            "monitor.lua",
            {
                "ABILITY_MASK": ability_mask,
                "INVENTORY_MASK": inventory_mask,
                "LEVEL_LOW_MASK": level_low_mask,
                "LEVEL_HIGH_MASK": level_high_mask,
            },
        )
        if "APBridgeMonitor" not in script:
            raise BridgeUnavailable("The Archipelago gameplay runtime is incomplete")
        return script

    @staticmethod
    def _decode_state(raw: str) -> dict[str, Any]:
        field_names = {
            "L": "life_flags", "G": "light_flags", "K": "dark_flags",
            "V": "vial_upgrade_flags", "D": "dagger_upgrade_flags",
            "F": "fairy_upgrade_flags", "H": "hook_tip",
            "S": "cyclone_sprint", "B": "cyclone_dark_dash",
            "LC": "light_power_current", "LM": "light_power_max",
            "LO": "light_power_on", "DC": "dark_power_current",
            "DM": "dark_power_max", "DO": "dark_power_on",
            "CH": "abilities_temporarily_suppressed",
            "MS": "magic_temporarily_suppressed",
            "W": "seraph_shoulders", "A": "dark_gauntlet",
            "FA": "fairies_enabled", "VA": "holy_water_enabled",
            "CR": "dark_crystal",
            "DA": "silver_daggers", "DX": "dagger_action_status",
            "DY": "dagger_move_action_status", "DZ": "dagger_combo_action_status",
            "DT": "dagger_throw_guard_enabled", "DW": "dagger_throw_guard_owned",
            "DG": "dagger_tutorial_completed",
            "DN": "dagger_count", "DMX": "dagger_max", "ST": "stake_available",
            "AI": "focus_action_index", "AS": "focus_action_status",
            "AU": "focus_unlocked", "AF": "action_status_flags",
            "CM": "level_completion_status", "VL": "visited_levels",
            "TL": "trial_low_mask", "TH": "trial_high_mask",
            "TI": "trial_active", "TC": "trial_current_status",
            "AL": "authorized_levels", "LA": "level_access_enabled",
            "PS": "player_status", "HM": "health_max",
            "DE": "dagger_expansions", "VE": "vial_expansions",
            "FE": "fairy_expansions", "SP": "saved_spawn",
            "SR": "spiked_chain_story_flag", "HE": "hook_story_block_enabled",
            "HF": "hook_story_block_triggered", "TE": "stake_story_block_enabled",
            "TF": "stake_story_block_triggered", "SE": "spiked_chain_block_enabled",
            "SF": "spiked_chain_block_triggered", "LE": "light_tutorial_block_enabled",
            "LF": "light_tutorial_block_triggered", "PX": "pickup_normalization_enabled",
            "PT": "pickup_normalization_triggered", "IC": "received_inventory_counts",
            "ME": "monitor_enabled", "PH": "hook_tip_owned",
            "PW": "focus_gameplay_enabled", "N": "level_name",
        }
        decoded: dict[str, Any] = {
            field_names[key]: value
            for part in raw.split("|")
            if "=" in part
            for key, value in [part.split("=", 1)]
            if key in field_names
        }
        for raw_key, name in (("L", "life_count"), ("G", "light_count"),
                              ("K", "dark_count"), ("V", "vial_upgrade_count"),
                              ("D", "dagger_upgrade_count"),
                              ("F", "fairy_upgrade_count")):
            value = next(
                (part.split("=", 1)[1] for part in raw.split("|")
                 if part.startswith(raw_key + "=")),
                "",
            )
            decoded[name] = value.count("X")
        decoded.update(
            connected=True,
            command_result="READY",
            sample_time=str(time.monotonic_ns()),
        )
        return decoded

    def read_check_state(self) -> dict[str, Any]:
        """Read saved check flags even when no gameplay monitor/player is ready."""
        payload = self.run("read-state")
        return self._decode_state(str(payload.get("state", "")))

    def _read_state(self, require_monitor: bool = True) -> dict[str, Any]:
        state = self.read_check_state()
        if not state.get("level_name") or state.get("level_name") == "nil":
            raise BridgeUnavailable("playable level state is not ready")
        if require_monitor and str(state.get("monitor_enabled", "")).lower() != "true":
            raise BridgeUnavailable("the Archipelago runtime belongs to the previous level")
        return state

    def install_monitor(
        self,
        received_counts: dict[str, int] | None = None,
        starting_level_indices: list[int] | tuple[int, ...] = (),
        required_level_completions: int = 25,
        completed_level_count: int = 0,
        completed_level_indices: set[int] | tuple[int, ...] = (),
    ) -> None:
        received_counts = received_counts or {}
        current = self._read_state(require_monitor=False)
        indices = requested_level_indices(
            received_counts,
            starting_level_indices,
            required_level_completions,
            completed_level_count,
        )
        masks = (
            packed_ability_mask(received_counts, current),
            packed_inventory_mask(desired_inventory_counts(received_counts)),
            packed_level_mask(indices, 1, 23),
            packed_level_mask(indices, 24, 46),
        )
        script = self._dump_monitor_script(*masks)
        self._execute_lua(script)
        verified = self._read_state(require_monitor=True)
        if str(verified.get("command_result")) != "READY":
            raise BridgeUnavailable("the Archipelago runtime did not initialize")
        NativeBridge.sync_world_map_ui(
            self,
            completed_level_indices,
            completed_level_count,
            required_level_completions,
            force=True,
        )

    def prepare_main_menu(
        self,
        received_counts: dict[str, int] | None = None,
        starting_level_indices: list[int] | tuple[int, ...] = (),
        required_level_completions: int = 25,
        completed_level_count: int = 0,
        completed_level_indices: set[int] | tuple[int, ...] = (),
    ) -> bool:
        """Authorize the retail World Map before Continue, without opening it."""
        indices = requested_level_indices(
            received_counts or {},
            starting_level_indices,
            required_level_completions,
            completed_level_count,
        )
        payload = self.run(
            "prepare-menu",
            str(packed_level_mask(indices, 1, 23)),
            str(packed_level_mask(indices, 24, 46)),
        )
        menu_active = bool(payload.get("menu"))
        if menu_active:
            NativeBridge.sync_world_map_ui(
                self,
                completed_level_indices,
                completed_level_count,
                required_level_completions,
                force=True,
            )
        return menu_active

    def sync_world_map_ui(
        self,
        completed_indices: set[int] | tuple[int, ...],
        completed_level_count: int,
        required_level_completions: int,
        *,
        force: bool = False,
    ) -> bool:
        """Install/update render-only AP World Map information."""
        low = packed_level_mask(set(completed_indices), 1, 23)
        high = packed_level_mask(set(completed_indices), 24, 46)
        completed = max(0, int(completed_level_count))
        required = max(1, int(required_level_completions))
        check_states = getattr(self, "world_map_check_states", "0" * 46)
        signature = (low, high, completed, required, check_states)
        if not force and getattr(self, "_last_world_map_ui_signature", None) == signature:
            return True
        arguments = ["sync-world-map-ui", str(low), str(high), str(completed), str(required)]
        if check_states != "0" * 46:
            arguments.append(check_states)
        payload = self.run(*arguments)
        applied = bool(payload.get("applied"))
        if applied:
            self._last_world_map_ui_signature = signature
        return applied

    def show_hud_message(self, message: str, map_only: bool = False) -> bool:
        """Display a non-modal map toast or a retail gameplay HUD message."""
        source = self._render_source_template(
            "show_message.lua",
            {"MESSAGE_LITERAL": lua_utf8_literal(message),
             "MAP_ONLY": "true" if map_only else "false"},
        )
        result = self._execute_lua(source)
        if result.startswith("--APMSG|NOTREADY|"):
            return False
        if result.startswith("--APMSG|ERROR|"):
            # A caught notification error is not a lost game connection. Keep
            # the queued message for retry without resetting gameplay monitors.
            if result != getattr(self, "_last_hud_error", None):
                logging.getLogger('LoSBridge').warning(
                    'Reward notification deferred; game connection retained: %s', result)
                self._last_hud_error = result
            return False
        if result != "--APMSG|OK":
            raise BridgeUnavailable(f"In-game message display failed: {result}")
        self._last_hud_error = None
        return True

    def interaction_status(self) -> str:
        result = self._execute_lua(self._render_source_template('interaction_status.lua', {}))
        if not result.startswith('--APINTERACTION|'):
            raise BridgeUnavailable('Interaction snapshot unavailable')
        return result.removeprefix('--APINTERACTION|')

    def uninstall_monitor(self) -> None:
        # The retail Lua environment owns the preloaded monitor and destroys it with the level.
        # Calling monitor-disable here would reintroduce the retired remote-thread Lua path.
        return None

    def read_state(self) -> dict[str, Any]:
        return self._read_state(require_monitor=True)

    def transition_started(self) -> bool:
        return False

    def read_bridge_event(self) -> dict[str, Any]:
        return {}

    def acknowledge_bridge_event(self, value: int) -> None:
        del value

    def apply_received_items(
        self,
        game_state: dict[str, Any],
        received_counts: dict[str, int],
        starting_level_indices: list[int] | tuple[int, ...] = (),
        required_level_completions: int = 25,
        completed_level_count: int | None = None,
    ) -> list[str]:
        # Reconcile the complete loadout synchronously on the proven game/window
        # thread.  No game scheduler or numeric mailbox is involved.
        # Hook Tip and Spiked Chain share the visual chain model, but Hook Tip's
        # actual grapple gate must also match independently.
        desired_chain = desired_chain_value(received_counts)
        try:
            current_chain = int(str(game_state.get("hook_tip", "0")))
        except ValueError:
            current_chain = 0
        abilities_suppressed = (
            str(game_state.get("abilities_temporarily_suppressed", "false")).lower()
            == "true"
        )
        magic_suppressed = (
            str(game_state.get("magic_temporarily_suppressed", "false")).lower()
            == "true"
        )
        ability_mismatch = False
        if not abilities_suppressed:
            desired_hook = received_counts.get("Hook Tip", 0) > 0
            ability_mismatch = (
                current_chain != desired_chain
                or received_ability_enabled("Hook Tip", game_state) != desired_hook
            )
            for item_name, command in RECONCILED_ABILITIES:
                desired = received_counts.get(item_name, 0) > 0
                current = received_ability_enabled(item_name, game_state)
                if not desired and defer_mandatory_tutorial_removal(item_name, game_state):
                    continue
                if magic_suppressed and item_name in {"Light Magic", "Shadow Magic"}:
                    continue
                if item_name == "Progressive Daggers":
                    dagger_controls = silver_dagger_controls(game_state)
                    ownership_controls = dagger_controls[:4] + (dagger_controls[5],)
                    if not dagger_controls[4] or any(
                        control != desired for control in ownership_controls
                    ):
                        ability_mismatch = True
                elif current != desired:
                    ability_mismatch = True
        changes: list[str] = []
        if ability_mismatch:
            changes.append("Ability loadout synchronized")

        current_inventory = bridge_inventory_counts(
            game_state.get("received_inventory_counts")
        )
        desired_inventory = desired_inventory_counts(received_counts)
        if (
            current_inventory != desired_inventory
            or str(game_state.get("pickup_normalization_enabled")).lower() != "true"
        ):
            changes.append("Inventory and pickup protection synchronized")

        authorized = {
            level.strip()
            for level in str(game_state.get("authorized_levels", "")).split(",")
            if level.strip()
        }
        if completed_level_count is None:
            completed_level_count = len(
                completed_level_indices(game_state.get("level_completion_status", ""))
            )
        indices = requested_level_indices(
            received_counts,
            starting_level_indices,
            required_level_completions,
            completed_level_count,
        )
        requested_ids = {LEVEL_INDEX_TO_ID[index] for index in indices}
        if (
            authorized != requested_ids
            or str(game_state.get("level_access_enabled", "")).lower() != "true"
        ):
            changes.append("World-map level availability")
        if changes:
            self.run(
                "sync-state",
                str(packed_ability_mask(received_counts, game_state)),
                str(packed_inventory_mask(desired_inventory)),
                str(packed_level_mask(indices, 1, 23)),
                str(packed_level_mask(indices, 24, 46)),
            )
        return changes

    def enable_level(self, map_index: int) -> None:
        raise BridgeUnavailable("research-only level grants are not exposed by the client")

    def grant_instant_rewards(self, deltas: dict[str, int]) -> None:
        """Apply newly received non-ownership rewards exactly once per client run."""
        values = tuple(
            max(0, int(deltas.get(name, 0)))
            for name in ("experience", "refill", "dagger", "vial", "fairy", "crystal")
        )
        if any(values):
            self.run("grant-rewards", *(str(value) for value in values))

    def apply_received_traps(self, deltas: dict[str, int]) -> bool:
        """Apply approved traps, returning false when retail state must settle first."""
        values = tuple(
            max(0, int(deltas.get(name, 0)))
            for name in ("magic_drain", "poison")
        )
        if not any(values):
            return True
        payload = self.run("apply-traps", *(str(value) for value in values))
        return bool(payload.get("applied"))
