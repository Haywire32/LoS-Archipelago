from __future__ import annotations

import asyncio
from collections import deque
import logging
import time

from CommonClient import CommonContext
from NetUtils import ClientStatus

from .bridge import (
    BRIDGE_KEY_TO_LOCATION_ID,
    BridgeUnavailable,
    LEVEL_COMPLETION_LOCATION_IDS,
    NativeBridge,
    ap_completed_level_indices,
    location_ids_from_state,
    received_item_counts,
    instant_reward_totals,
    requested_level_indices,
)
from ..map_checks import map_check_states
from ..locations import TRIAL_LOCATION_IDS
from .notifications import format_item_send_message
from .reward_ledger import RewardLedger, reward_session_key
from .skills import SkillClient, preview_text
from ..skills import SKILL_LOCATION_IDS
from .enemy_client import EnemyClient, EarlyEnemyClient
from ..enemies import LAYOUT_VERSION
from .enemy_preferences import EnemyPreferences
from .commands import LordsOfShadowCommandProcessor
from .dropin_transport import DropInUnavailable


logger = logging.getLogger("Client.LoS")
PAUSED_NOTICE_SECONDS = 8.0
TRANSITION_RECONNECT_GRACE_SECONDS = 20.0
CONFIRMED_TRANSITION_RETRY_SECONDS = 20.0
SAFE_ATTACH_RETRY_SECONDS = 5.0
EMPTY_INITIAL_ITEMS_GRACE_SECONDS = 5.0
HUD_MESSAGE_INTERVAL_SECONDS = 6.0


class LordsOfShadowContext(CommonContext):
    game = "Castlevania: Lords of Shadow"
    items_handling = 0b111
    command_processor = LordsOfShadowCommandProcessor

    def __init__(self, server_address: str | None, password: str | None) -> None:
        super().__init__(server_address, password)
        self.bridge: NativeBridge | None = None
        self.monitor_installed = False
        self.last_sample_time: str | None = None
        self.last_sample_change = time.monotonic()
        self.paused_notice_logged = False
        self.goal_reported = False
        self.game_was_connected = False
        self.menu_ready_announced = False
        self.sync_stable_samples = 0
        self.sync_announced = False
        self.live_ready_announced = False
        self.bridge_wait_started = None
        self.bridge_wait_warned = False
        self.next_monitor_attempt = 0.0
        self.slot_data: dict[str, object] = {}
        self.seed_data_received = False
        self.server_connected_at: float | None = None
        self.seed_data_error_logged = False
        self.seed_wait_logged = False
        self.received_items_ready = False
        self.instant_rewards_applied = {
            "experience": 0,
            "refill": 0,
            "dagger": 0,
            "vial": 0,
            "fairy": 0,
            "crystal": 0,
            "magic_drain": 0,
            "poison": 0,
        }
        self.reward_ledger = RewardLedger()
        self.reward_session_key: str | None = None
        self.hud_messages: deque[str] = deque()
        self.next_hud_message_time = 0.0
        self.hud_toast_pending = False
        self.interaction_status_requested = False
        self.skill_client = None
        self.skill_failure = None
        self.skill_scout_time = 0.0
        self.enemy_client = None
        self.enemy_failure = None
        self.enemy_stop_pending = False
        self.enemy_preferences = EnemyPreferences()
        self.enemy_restart_notice = False

    def on_package(self, cmd: str, args: dict) -> None:
        if cmd == "RoomUpdate" and "checked_locations" in args:
            logging.getLogger('LoSBridge').info(
                'Server acknowledged checks: %s', sorted(args['checked_locations']))
        if cmd == "ReceivedItems":
            self.received_items_ready = True
            self.watcher_event.set()
            return
        if cmd != "Connected":
            return
        raw_slot_data = args.get("slot_data", {})
        self.server_connected_at = time.monotonic()
        self.hud_messages.clear()
        self.next_hud_message_time = 0.0
        self.slot_data = dict(raw_slot_data) if isinstance(raw_slot_data, dict) else {}
        self.enemy_stop_pending = True
        self.enemy_client = None
        self.enemy_failure = None
        self.skill_client = None
        self.skill_failure = None
        self.skill_scout_time = 0.0
        starting_indices = list(self.slot_data.get("starting_level_indices", []))
        self.seed_data_received = bool(starting_indices)
        self.seed_data_error_logged = False
        self.reward_session_key = reward_session_key(
            self.slot_data.get("reward_seed_id", getattr(self, "seed_name", None)),
            args.get("team", getattr(self, "team", 0)),
            args.get("slot", getattr(self, "slot", 0)),
        )
        self.instant_rewards_applied = self.reward_ledger.read(
            self.reward_session_key
        )
        logging.getLogger('LoSBridge').info('Enemy controls: /enemies shows status; /enemies off disables randomized enemies locally for this seed. Restart the game after disabling.')
        if self.seed_data_received:
            logging.getLogger('LoSBridge').info(
                "Seed settings received: %d starting levels; Final Fight after %d new completions.",
                len(starting_indices),
                int(self.slot_data.get("required_level_completions", 25)),
            )
        else:
            logger.error(
                "The server did not provide starting-level seed data. "
                "World Map authorization will remain disabled."
            )
        self.watcher_event.set()

    def update_map_check_states(self, counts: dict, completed_count: int) -> None:
        if self.bridge is None:
            return
        slot = self.slot_data
        unlocked = requested_level_indices(
            counts, list(slot.get("starting_level_indices", [])),
            int(slot.get("required_level_completions", 25)), completed_count,
        )
        self.bridge.world_map_check_states = map_check_states(
            unlocked, set(self.missing_locations) | set(self.checked_locations),
            set(self.locations_checked) | set(self.checked_locations), counts,
            slot.get("world_map_rules") if slot.get("world_map_protocol") == 1
            and slot.get("show_logic_colors", True) else None,
        )

    def on_print_json(self, args: dict) -> None:
        """Queue only live item transfers for the retail non-modal HUD."""
        super().on_print_json(args)
        try:
            message = format_item_send_message(
                args,
                concerns_self=self.slot_concerns_self,
                player_names=self.player_names,
                item_name_lookup=lambda item_id, receiving: (
                    self.item_names.lookup_in_slot(item_id, receiving)
                ),
            )
        except Exception:
            logger.debug("Could not format an Archipelago HUD message.", exc_info=True)
            return
        if message is not None:
            self.hud_messages.append(message)
            self.watcher_event.set()

    async def flush_hud_messages(self, map_only: bool = False) -> None:
        if self.bridge is None or time.monotonic() < self.next_hud_message_time:
            return
        if self.hud_toast_pending:
            await asyncio.to_thread(self.bridge.show_hud_message, "", True)
            self.hud_toast_pending = False
        if not self.hud_messages:
            return
        displayed = await asyncio.to_thread(
            self.bridge.show_hud_message, self.hud_messages[0], map_only
        )
        if displayed:
            self.hud_messages.popleft()
            self.hud_toast_pending = True
            self.next_hud_message_time = time.monotonic() + HUD_MESSAGE_INTERVAL_SECONDS
        elif not map_only:
            self.next_hud_message_time = time.monotonic() + 1.0

    async def server_auth(self, password_requested: bool = False) -> None:
        if password_requested and not self.password:
            await super().server_auth(password_requested)
        await self.get_username()
        await self.send_connect()

    async def sync_enemies(self) -> bool:
        if not self.bridge:
            return False
        def enemy_root():
            try:
                root = self.bridge.transport.executable_path().parent/'APEnemy'
                if getattr(self, '_diagnostic_enemy_root', None) != root:
                    logging.getLogger('LoSBridge').info('Enemy plan folder=%s early_loader_present=%s', root, (root/'enemy_early.lua').is_file())
                    self._diagnostic_enemy_root = root
                return root
            except DropInUnavailable as exc:
                # Startup/exit can race process-path lookup. Let the ordinary
                # bridge reconnect loop retry; this is not an enemy-data fault.
                raise BridgeUnavailable(str(exc)) from exc
        try:
            if self.enemy_preferences.disabled(self.reward_session_key):
                root=enemy_root()
                if (root/'enemy_early.lua').is_file():
                    self.enemy_preferences.stage(self.reward_session_key,root,{'enabled':False})
                # Never dismantle a running encounter. Already loaded enemy
                # controllers/dependencies require a fresh process to clear.
                state=await asyncio.to_thread(self.bridge._execute_lua,
                    "Game.Set('InitLuaLine',((APEnemyShuffle and APEnemyShuffle.Enabled) or (APEnemyEarly and APEnemyEarly.State~='inactive')) and 'restart' or 'off')")
                if state!='off':
                    if not self.enemy_restart_notice:
                        logger.warning('Local enemy opt-out saved. Restart the game before continuing; current enemies are still loaded.')
                        self.enemy_restart_notice=True
                    return False
                self.enemy_restart_notice=False
                self.enemy_stop_pending=False
                return True
        except (OSError, ValueError) as exc:
            logger.error('Cannot read/stage local enemy preference: %s',exc)
            return False
        if self.enemy_stop_pending:
            if not self.slot_data.get('randomize_minor_enemies'):
                root=enemy_root()
                await asyncio.to_thread(EarlyEnemyClient.disable,self.bridge._execute_lua,root)
            self.enemy_stop_pending = False
        if not self.slot_data.get('randomize_minor_enemies'):return True
        if self.enemy_failure:return False
        try:
            if self.slot_data.get('enemy_layout_version') != LAYOUT_VERSION:
                raise ValueError('Enemy layout version mismatch; use the matching experimental package')
            root=enemy_root()
            if self.enemy_client is None:
                self.enemy_client = EarlyEnemyClient(str(self.slot_data['reward_seed_id']))
            return await asyncio.to_thread(self.enemy_client.tick, self.bridge._execute_lua,root,
                                           self.enemy_preferences,self.reward_session_key)
        except BridgeUnavailable:
            raise
        except Exception as exc:
            self.enemy_failure = str(exc)
            logger.exception('Experimental enemy setup stopped; preserve this log')
            logging.getLogger('LoSBridge').exception('Enemy setup stopped')
            return False

    async def sync_skills(self, counts: dict) -> None:
        if not self.slot_data.get('skills_as_checks') or self.skill_failure or not self.bridge:
            return
        if int(self.slot_data.get('skill_protocol', 0)) != 1:
            self.skill_failure = 'Unsupported skill protocol; use the matching client version'
            logger.error(self.skill_failure)
            return
        connected = bool(self.server and self.server.socket and not self.server.socket.closed)
        reveal = bool(self.slot_data.get('reveal_skill_rewards'))
        rewards = {}
        if reveal:
            missing = set(SKILL_LOCATION_IDS.values()) - set(self.locations_info)
            if connected and missing and time.monotonic()-self.skill_scout_time >= 10:
                await self.send_msgs([{'cmd':'LocationScouts','locations':sorted(missing),'create_as_hint':0}])
                self.skill_scout_time = time.monotonic()
            for action, code in SKILL_LOCATION_IDS.items():
                info = self.locations_info.get(code)
                if info is not None:
                    try:
                        item_name = self.item_names.lookup_in_slot(info.item, info.player)
                    except (KeyError, IndexError, TypeError):
                        continue  # Datapackage not received yet; display awaiting server.
                    recipient = self.player_names.get(info.player, f'Player {info.player}')
                    rewards[action] = preview_text(item_name, recipient)
        try:
            if self.skill_client is None:
                self.skill_client = SkillClient(self.reward_session_key)
            checks = await asyncio.to_thread(self.skill_client.tick, self.bridge._execute_lua,
                counts, self.locations_checked, connected=connected, reveal=reveal, rewards=rewards)
            if connected and checks:
                # Journaled checks are resent until acknowledged by the server.
                await self.send_msgs([{'cmd':'LocationChecks','locations':sorted(checks)}])
        except BridgeUnavailable:
            raise
        except Exception as exc:
            self.skill_failure = str(exc)
            logger.error('Skill purchases paused: %s. Keep the journal; do not retry XP charges.', exc)
            try:
                await asyncio.to_thread(self.bridge._execute_lua, 'if APPaidSkills then APPaidSkills.Ready=false end')
            except (BridgeUnavailable, OSError):
                pass

    async def sync_game_checks(self, game_state: dict) -> set[int]:
        """Read-only checks keep flowing on menus and retry until server acknowledgement."""
        detected = location_ids_from_state(game_state)
        if not bool(self.slot_data.get("trials_as_checks", False)):
            detected.difference_update(TRIAL_LOCATION_IDS)
        enabled = set(self.missing_locations) | set(self.checked_locations)
        detected.intersection_update(enabled)
        new_checks = detected - self.locations_checked
        self.locations_checked.update(detected)
        if new_checks:
            logging.getLogger('LoSBridge').info('Game detected checks: %s', sorted(new_checks))
        pending = self.locations_checked & set(self.missing_locations)
        connection = getattr(self.server, 'socket', None)
        if not pending or not self.slot or connection is None or not connection.open or connection.closed:
            return detected
        now = time.monotonic()
        if pending != getattr(self, '_last_sent_game_checks', set()) or now >= getattr(self, '_next_check_send', 0):
            sent = set(pending)
            await self.send_msgs([{'cmd': 'LocationChecks', 'locations': sorted(sent)}])
            logging.getLogger('LoSBridge').info('Check submission (awaiting acknowledgement): %s', sorted(sent))
            for location_id in sorted(sent & new_checks):
                logging.getLogger('LoSBridge').info('Check sent: %s', self.location_names.lookup_in_game(location_id))
            self._last_sent_game_checks = set(pending)
            self._next_check_send = now + 5.0
        return detected

    def make_gui(self):
        from kvui import GameManager

        class LordsOfShadowManager(GameManager):
            base_title = "Lords of Shadow Archipelago Client"

        return LordsOfShadowManager

    def announce_live_ready(self) -> None:
        # Monitor reinstallations and item reconciliation are routine. Keep their
        # diagnostic milestones without repeating the initial player notice.
        logging.getLogger('LoSBridge').info('LIVE SESSION READY')
        if not self.live_ready_announced:
            logger.info("Game connected.")
            self.live_ready_announced = True

    def report_bridge_wait(self, message: str) -> None:
        if self.bridge_wait_started is None:
            self.bridge_wait_started = time.monotonic()
        # Loading/reloading normally reconnects in about six seconds. Surface a
        # sustained interruption, not each intermediate Lua/monitor state.
        if (not self.bridge_wait_warned and
                (not self.game_was_connected or
                 time.monotonic() - self.bridge_wait_started >= TRANSITION_RECONNECT_GRACE_SECONDS)):
            logging.getLogger('LoSBridge').warning("Waiting for the game connection: %s", message)
            self.bridge_wait_warned = True

    def clear_bridge_wait(self) -> None:
        if self.bridge_wait_warned:
            logging.getLogger('LoSBridge').info("Game connection restored.")
        self.bridge_wait_started = None
        self.bridge_wait_warned = False

    def reset_game_bridge(self, retry_delay: float = 0.0) -> None:
        if self.bridge is not None:
            self.bridge.close()
        self.bridge = None
        self.monitor_installed = False
        self.menu_ready_announced = False
        self._next_platform_probe = 0.0
        self.last_sample_time = None
        self.last_sample_change = time.monotonic()
        self.paused_notice_logged = False
        self.sync_stable_samples = 0
        self.sync_announced = False
        self.next_monitor_attempt = max(
            self.next_monitor_attempt,
            time.monotonic() + retry_delay,
        )

    async def game_watcher(self) -> None:
        last_error: str | None = None
        while not self.exit_event.is_set():
            if getattr(self, 'game_dir_refresh_requested', False):
                # Only reset between requests, never while a worker owns the socket.
                self.reset_game_bridge()
                self.enemy_failure = None
                self.game_dir_refresh_requested = False
            # Connected supplies the seed settings and ReceivedItems supplies
            # the authoritative inventory.  Never infer an empty loadout while
            # either half of that handshake is pending.
            # Archipelago does not send ReceivedItems at all for a brand-new
            # slot whose received list is empty.  After a short grace period,
            # that exact case is therefore a complete empty inventory rather
            # than a missing packet.  Non-empty and reconnecting slots still
            # wait for their authoritative ReceivedItems packet.
            if (
                self.seed_data_received
                and not self.received_items_ready
                and not self.items_received
                and self.server_connected_at is not None
                and time.monotonic() - self.server_connected_at
                >= EMPTY_INITIAL_ITEMS_GRACE_SECONDS
            ):
                self.received_items_ready = True
                logging.getLogger('LoSBridge').info(
                    "The server sent no initial items; continuing with the approved "
                    "empty AP loadout."
                )
            if not self.seed_data_received or not self.received_items_ready:
                gate = (self.seed_data_received, self.received_items_ready)
                if gate != getattr(self, '_last_start_gate', None):
                    logging.getLogger('LoSBridge').info(
                        'Startup waiting: seed_data=%s initial_items=%s', *gate)
                    self._last_start_gate = gate
                if not self.seed_wait_logged:
                    logging.getLogger('LoSBridge').info(
                        "Waiting for the Archipelago seed and initial items before touching "
                        "the game state."
                    )
                    self.seed_wait_logged = True
                try:
                    await asyncio.wait_for(self.watcher_event.wait(), timeout=1.0)
                    self.watcher_event.clear()
                except asyncio.TimeoutError:
                    pass
                continue
            if (
                not self.monitor_installed
                and time.monotonic() < self.next_monitor_attempt
            ):
                try:
                    await asyncio.wait_for(self.watcher_event.wait(), timeout=1.0)
                    self.watcher_event.clear()
                except asyncio.TimeoutError:
                    pass
                continue
            try:
                if self.bridge is None:
                    logging.getLogger('LoSBridge').info(
                        'Startup prerequisites ready; attaching to game.')
                    self.bridge = await asyncio.to_thread(NativeBridge)
                if getattr(self.bridge.transport, 'diagnostics_enabled', False) and time.monotonic() >= getattr(self, '_next_platform_probe', 0):
                    self._next_platform_probe = time.monotonic() + 5
                    snapshot = await asyncio.to_thread(self.bridge._execute_lua,
                        self.bridge._template('platform_snapshot.lua'))
                    logging.getLogger('LoSBridge').info('Platform state: %s', snapshot)
                # Completion/trial flags are valid on the result screen and map.
                # Never gate their delivery on a live player or installed monitor.
                check_state = await asyncio.to_thread(self.bridge.read_check_state)
                await self.sync_game_checks(check_state)
                # The gameplay sample clock stops on the map. Deliver queued
                # check rewards independently, without requiring a player entity.
                await self.flush_hud_messages(map_only=True)
                if not await self.sync_enemies():
                    await asyncio.sleep(1)
                    continue
                if not self.monitor_installed:
                    counts = received_item_counts(self.items_received)
                    slot_data = self.slot_data
                    ignored_completions = {
                        int(location_id)
                        for location_id in slot_data.get(
                            "ignored_completion_location_ids", []
                        )
                    }
                    completed_level_count = len(
                        (self.locations_checked & LEVEL_COMPLETION_LOCATION_IDS)
                        - ignored_completions
                    )
                    completed_indices = ap_completed_level_indices(
                        self.locations_checked
                    )
                    self.update_map_check_states(counts, completed_level_count)
                    menu_active = await asyncio.to_thread(
                        self.bridge.prepare_main_menu,
                        counts,
                        list(slot_data.get("starting_level_indices", [])),
                        int(slot_data.get("required_level_completions", 25)),
                        completed_level_count,
                        completed_indices,
                    )
                    if menu_active:
                        self.clear_bridge_wait()
                        self.game_was_connected = True
                        self.next_monitor_attempt = 0.0
                        if not self.menu_ready_announced:
                            logging.getLogger('LoSBridge').info('MAIN MENU ARMED')
                            self.announce_live_ready()
                            self.menu_ready_announced = True
                        try:
                            await asyncio.wait_for(
                                self.watcher_event.wait(), timeout=1.0
                            )
                            self.watcher_event.clear()
                        except asyncio.TimeoutError:
                            pass
                        continue
                    await asyncio.to_thread(
                        self.bridge.install_monitor,
                        counts,
                        list(slot_data.get("starting_level_indices", [])),
                        int(slot_data.get("required_level_completions", 25)),
                        completed_level_count,
                        completed_indices,
                    )
                    self.monitor_installed = True
                    self.game_was_connected = True
                    self.next_monitor_attempt = 0.0
                    logging.getLogger('LoSBridge').info(
                        "Game connected through its main window thread; items and level "
                        "access were applied without editing the save or game archive."
                    )

                game_state = await asyncio.to_thread(self.bridge.read_state)
                if self.interaction_status_requested:
                    detail = await asyncio.to_thread(self.bridge.interaction_status)
                    logger.info('Interaction snapshot:\n%s', detail)
                    self.interaction_status_requested = False
                sample_time = str(game_state.get("sample_time", ""))
                sample_advanced = True
                if self.last_sample_time is None:
                    self.last_sample_time = sample_time
                    self.last_sample_change = time.monotonic()
                elif sample_time != self.last_sample_time:
                    self.last_sample_time = sample_time
                    self.last_sample_change = time.monotonic()
                    self.paused_notice_logged = False
                else:
                    sample_advanced = False

                detected = await self.sync_game_checks(game_state)

                final_completion = BRIDGE_KEY_TO_LOCATION_ID["level_complete:46"]
                if final_completion in detected and not self.goal_reported:
                    await self.send_msgs(
                        [{"cmd": "StatusUpdate", "status": ClientStatus.CLIENT_GOAL}]
                    )
                    self.goal_reported = True
                    logger.info("Final Fight complete: goal sent to Archipelago.")

                applied: list[str] = []
                if self.seed_data_received:
                    counts = received_item_counts(self.items_received)
                    slot_data = self.slot_data
                    ignored_completions = {
                        int(location_id)
                        for location_id in slot_data.get(
                            "ignored_completion_location_ids", []
                        )
                    }
                    completed_level_count = len(
                        (self.locations_checked & LEVEL_COMPLETION_LOCATION_IDS)
                        - ignored_completions
                    )
                    completed_indices = ap_completed_level_indices(
                        self.locations_checked
                    )
                    self.update_map_check_states(counts, completed_level_count)
                    await asyncio.to_thread(
                        self.bridge.sync_world_map_ui,
                        completed_indices,
                        completed_level_count,
                        int(slot_data.get("required_level_completions", 25)),
                    )
                    # Ownership and World Map reconciliation follows a fresh
                    # retail sample. One-shot network rewards do not: a
                    # ReceivedItems packet can arrive while the sampled state
                    # is unchanged (for example during a pickup result screen).
                    # Coupling rewards to sample_advanced silently lost those
                    # deliveries until a later transition.
                    if sample_advanced:
                        applied = await asyncio.to_thread(
                            self.bridge.apply_received_items,
                            game_state,
                            counts,
                            list(slot_data.get("starting_level_indices", [])),
                            int(slot_data.get("required_level_completions", 25)),
                            completed_level_count,
                        )
                    reward_totals = instant_reward_totals(counts)
                    await self.sync_skills(counts)
                    reward_deltas = {
                        name: max(
                            0,
                            total - self.instant_rewards_applied.get(name, 0),
                        )
                        for name, total in reward_totals.items()
                    }
                    ordinary_reward_names = (
                        "experience", "refill", "dagger", "vial", "fairy", "crystal"
                    )
                    ordinary_deltas = {
                        name: reward_deltas[name] for name in ordinary_reward_names
                    }
                    if any(ordinary_deltas.values()):
                        logging.getLogger('LoSBridge').info(
                            "Applying one-shot rewards: experience=%d, refill=%d, "
                            "dagger=%d, vial=%d, fairy=%d, crystal=%d.",
                            *(ordinary_deltas[name] for name in ordinary_reward_names),
                        )
                        await asyncio.to_thread(
                            self.bridge.grant_instant_rewards, ordinary_deltas
                        )
                        for name in ordinary_reward_names:
                            self.instant_rewards_applied[name] = reward_totals[name]
                        if self.reward_session_key is not None:
                            await asyncio.to_thread(
                                self.reward_ledger.write,
                                self.reward_session_key,
                                self.instant_rewards_applied,
                            )
                        applied.append("Experience Points or consumables reward")

                    # Poison is delivered one copy at a time. If several arrive
                    # together, each later copy waits until the prior retail
                    # poison has ended or been cured. Magic drain is idempotent,
                    # so all pending copies can safely resolve together.
                    trap_deltas = {
                        "magic_drain": reward_deltas["magic_drain"],
                        "poison": min(1, reward_deltas["poison"]),
                    }
                    if any(trap_deltas.values()):
                        traps_applied = await asyncio.to_thread(
                            self.bridge.apply_received_traps, trap_deltas
                        )
                        if traps_applied:
                            self.instant_rewards_applied["magic_drain"] += trap_deltas[
                                "magic_drain"
                            ]
                            self.instant_rewards_applied["poison"] += trap_deltas[
                                "poison"
                            ]
                            if self.reward_session_key is not None:
                                await asyncio.to_thread(
                                    self.reward_ledger.write,
                                    self.reward_session_key,
                                    self.instant_rewards_applied,
                                )
                            if trap_deltas["magic_drain"]:
                                applied.append("Magic Drain Trap")
                            if trap_deltas["poison"]:
                                applied.append("Poison Trap")
                elif sample_advanced and not self.seed_data_error_logged:
                    logger.error(
                        "Waiting for valid seed settings; no World Map authorization was sent."
                    )
                    self.seed_data_error_logged = True
                if sample_advanced:
                    await self.flush_hud_messages()
                for item_name in applied:
                    logging.getLogger('LoSBridge').info("Received item applied in game: %s", item_name)
                if applied:
                    self.sync_stable_samples = 0
                    self.sync_announced = False
                elif (
                    sample_advanced
                    and self.seed_data_received
                    and str(game_state.get("command_result")) in {"READY", "OK"}
                ):
                    self.sync_stable_samples += 1
                    if self.sync_stable_samples >= 2 and not self.sync_announced:
                        self.announce_live_ready()
                        self.sync_announced = True
                self.clear_bridge_wait()
                last_error = None
            except BridgeUnavailable as exc:
                message = str(exc)
                if message != last_error:
                    logging.getLogger('LoSBridge').warning('Watcher: %s', message)
                self.report_bridge_wait(message)
                if self.game_was_connected and "CastlevaniaLoSUE.exe is not running" in message:
                    if message != last_error:
                        logging.getLogger('LoSBridge').info(
                            "The game closed. Waiting for Lords of Shadow to reopen; "
                            "the Archipelago connection and received progress remain active."
                        )
                    self.reset_game_bridge(SAFE_ATTACH_RETRY_SECONDS)
                    last_error = message
                elif message != last_error:
                    if self.monitor_installed:
                        logging.getLogger('LoSBridge').info(
                            "The level changed or reloaded. Reconnecting the safe runtime "
                            "when playable gameplay is ready."
                        )
                        self.reset_game_bridge(SAFE_ATTACH_RETRY_SECONDS)
                    else:
                        logging.getLogger('LoSBridge').info("Waiting for playable gameplay: %s", message)
                        self.reset_game_bridge(SAFE_ATTACH_RETRY_SECONDS)
                    last_error = message
            except OSError as exc:
                message = str(exc)
                self.report_bridge_wait(message)
                if self.game_was_connected and "CastlevaniaLoSUE.exe is not running" in message:
                    if message != last_error:
                        logging.getLogger('LoSBridge').info(
                            "The game closed. Waiting for Lords of Shadow to reopen; "
                            "the Archipelago connection and received progress remain active."
                        )
                    self.reset_game_bridge(SAFE_ATTACH_RETRY_SECONDS)
                    last_error = message
                elif message != last_error:
                    logging.getLogger('LoSBridge').info("Waiting for the paused game: %s", message)
                    last_error = message

            try:
                await asyncio.wait_for(self.watcher_event.wait(), timeout=1.0)
                self.watcher_event.clear()
            except asyncio.TimeoutError:
                pass

    async def shutdown(self) -> None:
        if self.bridge is not None:
            try:
                await asyncio.to_thread(self.bridge.uninstall_monitor)
            except (BridgeUnavailable, OSError):
                # The game may already be closed or between Lua environments.
                # A new install also removes any old named callbacks first.
                pass
        self.reset_game_bridge()
        await super().shutdown()
