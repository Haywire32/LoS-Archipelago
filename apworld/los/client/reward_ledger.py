from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
from typing import Mapping


REWARD_FIELDS = (
    "experience",
    "refill",
    "dagger",
    "vial",
    "fairy",
    "crystal",
    "magic_drain",
    "poison",
)


def _nonnegative_integer(value: object) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError, OverflowError):
        return 0


def default_ledger_path() -> Path:
    """Return the per-user durable ledger used for one-shot AP rewards."""
    local_app_data = os.environ.get("LOCALAPPDATA")
    root = Path(local_app_data) if local_app_data else Path.home() / "AppData" / "Local"
    return root / "Archipelago" / "LordsOfShadow" / "reward-ledger.json"


def reward_session_key(seed_name: object, team: object, slot: object) -> str:
    """Build a stable identity for one player in one generated multiworld."""
    return f"{seed_name or 'unknown-seed'}|team={int(team or 0)}|slot={int(slot or 0)}"


class RewardLedger:
    """Persist cumulative one-shot reward totals across client restarts."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or default_ledger_path()

    def read(self, session_key: str) -> dict[str, int]:
        try:
            document = json.loads(self.path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            document = {}
        raw = document.get(session_key, {}) if isinstance(document, dict) else {}
        if not isinstance(raw, dict):
            raw = {}
        return {
            field: _nonnegative_integer(raw.get(field, 0))
            for field in REWARD_FIELDS
        }

    def write(self, session_key: str, totals: Mapping[str, int]) -> None:
        try:
            document = json.loads(self.path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            document = {}
        if not isinstance(document, dict):
            document = {}
        document[session_key] = {
            field: _nonnegative_integer(totals.get(field, 0))
            for field in REWARD_FIELDS
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        handle, temporary_name = tempfile.mkstemp(
            prefix=f"{self.path.stem}-",
            suffix=".tmp",
            dir=self.path.parent,
        )
        temporary = Path(temporary_name)
        try:
            with os.fdopen(handle, "w", encoding="utf-8") as stream:
                json.dump(document, stream, indent=2, sort_keys=True)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
        finally:
            temporary.unlink(missing_ok=True)
