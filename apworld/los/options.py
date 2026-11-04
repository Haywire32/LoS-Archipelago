from __future__ import annotations

from dataclasses import dataclass

from Options import Choice, PerGameCommonOptions, Range, StartInventoryPool


class StartingLevelCount(Range):
    """Any AP-unlocked level can be entered. This controls how many are available
    at the start of the game. A higher value is easier."""

    display_name = "Starting Level Count"
    range_start = 1
    range_end = 45
    default = 10


class RequiredLevelCompletions(Range):
    """Satan becomes available after this many level-completion checks."""

    display_name = "Required Level Completions"
    range_start = 1
    range_end = 45
    default = 25


class IncludeDLC(Choice):
    """DLC is not supported in this version. Keep this disabled."""

    display_name = "Include DLC"
    option_disabled = 0
    option_enabled = 1
    default = 0


class TrialsAsChecks(Choice):
    """Add trials as checks. Trials vary in difficulty and can make the seed harder.
    disabled: trials off - gem rewards are given two at a time.
    enabled: trials on - gems rewards are given individually."""

    display_name = "Trials as Checks"
    option_disabled = 0
    option_enabled = 1
    default = 0


class FocusScrollMode(Choice):
    """Focus Scroll allows you to get orbs from combos to fill your magic meter.
    Enabled: Start with Focus Scroll. Disabled: Focus Scroll is added to the item pool."""

    display_name = "Focus Scroll"
    option_disabled = 0
    option_enabled = 1
    alias_randomized = 0
    alias_starting = 1
    default = 1


class StartingMagic(Choice):
    """Choose which magic medallions you begin with:
    neither, light, shadow, or both."""

    display_name = "Starting Magic"
    option_neither = 0
    option_light = 1
    option_shadow = 2
    option_both = 3
    default = 0


class EarlyMagic(Choice):
    """Guarantee Light and Shadow Magic appear early in the seed."""

    display_name = "Early Magic"
    option_disabled = 0
    option_enabled = 1
    default = 1


class TrapFrequency(Choice):
    """Add traps - magic drain and poison
    Traps replace the "Consumable refill" rewards: none=0%, low=10%, normal=30%, high=50%."""

    display_name = "Trap Frequency"
    option_none = 0
    option_low = 10
    option_normal = 30
    option_high = 50
    default = 0


class SkillsAsChecks(Choice):
    """Add all 31 purchasable skill purchases as checks and shuffle their move unlocks."""
    display_name = "Skills as Checks"
    option_disabled = 0
    option_enabled = 1
    default = 1


class RevealSkillRewards(Choice):
    """Show the AP reward before buying checks.
    Requires skills_as_checks: enabled."""
    display_name = "Reveal Skill Rewards"
    option_disabled = 0
    option_enabled = 1
    default = 1


class RandomizeMinorEnemies(Choice):
    """Randomize minor enemies. Note that this feature is currently unstable and could cause bugs or crashes."""
    display_name = "Randomize Minor Enemies (Experimental)"
    option_disabled = 0
    option_enabled = 1
    default = 0


class ShowLogicColors(Choice):
    """World map will show which levels have unlocks in logic or not. This does not account for experience points farming to buy checks. Green = unlocks in logic, red = unlocks are blocked by requirements, blue = all checks are completed in this level"""

    display_name = "Show Logic Colors"
    option_disabled = 0
    option_enabled = 1
    default = 1


@dataclass
class LordsOfShadowOptions(PerGameCommonOptions):
    """Lords of Shadow randomizer options."""

    starting_level_count: StartingLevelCount
    required_level_completions: RequiredLevelCompletions
    include_dlc: IncludeDLC
    trials_as_checks: TrialsAsChecks
    focus_scroll: FocusScrollMode
    starting_magic: StartingMagic
    early_magic: EarlyMagic
    trap_frequency: TrapFrequency
    start_inventory_from_pool: StartInventoryPool
    skills_as_checks: SkillsAsChecks
    reveal_skill_rewards: RevealSkillRewards
    randomize_minor_enemies: RandomizeMinorEnemies
    show_logic_colors: ShowLogicColors
