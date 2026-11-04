from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any


def clean_hud_component(value: Any, maximum_length: int) -> str:
    """Make an AP-provided name safe and compact for the retail HUD."""
    compact = " ".join(str(value if value is not None else "").split())
    printable = "".join(character for character in compact if character.isprintable())
    if len(printable) <= maximum_length:
        return printable
    return printable[: max(1, maximum_length - 1)].rstrip() + "…"


def _network_item_field(item: Any, name: str, index: int) -> Any:
    if isinstance(item, Mapping):
        return item.get(name)
    if hasattr(item, name):
        return getattr(item, name)
    try:
        return item[index]
    except (IndexError, KeyError, TypeError):
        return None


def format_item_send_message(
    args: Mapping[str, Any],
    *,
    concerns_self: Callable[[int], bool],
    player_names: Mapping[int, str],
    item_name_lookup: Callable[[int, int], str],
) -> str | None:
    """Format one live Archipelago ItemSend packet for the in-game HUD."""
    if args.get("type") != "ItemSend":
        return None
    item = args.get("item")
    if item is None:
        return None
    try:
        receiving = int(args.get("receiving"))
        finder = int(_network_item_field(item, "player", 2))
        item_id = int(_network_item_field(item, "item", 0))
    except (TypeError, ValueError):
        return None

    receiving_is_self = bool(concerns_self(receiving))
    finder_is_self = bool(concerns_self(finder))
    if not receiving_is_self and not finder_is_self:
        return None

    try:
        item_name = item_name_lookup(item_id, receiving)
    except Exception:
        item_name = f"item {item_id}"
    item_text = clean_hud_component(item_name, 72) or f"item {item_id}"

    def player_text(slot: int) -> str:
        fallback = "Archipelago" if slot == 0 else f"Player {slot}"
        return clean_hud_component(player_names.get(slot, fallback), 48) or fallback

    if receiving_is_self and finder_is_self:
        return f"You found {item_text}"
    if receiving_is_self:
        return f"{player_text(finder)} has sent you {item_text}"
    return f"You sent {item_text} to {player_text(receiving)}"
