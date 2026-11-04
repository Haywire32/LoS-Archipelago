from CommonClient import ClientCommandProcessor


class LordsOfShadowCommandProcessor(ClientCommandProcessor):
    def _cmd_game_dir(self, *parts: str) -> bool:
        """Linux/Proton: /game_dir /path/to/CastlevaniaLoS (spaces allowed). Saved for future launches."""
        from .platform_diagnostics import save_game_dir
        path = ' '.join(parts)
        if not path:
            self.output('Usage: /game_dir /full/path/to/CastlevaniaLoS')
            return False
        try:
            folder = save_game_dir(path)
            self.ctx.game_dir_refresh_requested = True
            self.ctx.watcher_event.set()
            self.output('Saved game folder: ' + str(folder) + '. Wait at the main menu for Game connected.')
            return True
        except (OSError, ValueError) as exc:
            self.output(str(exc)); return False

    def _cmd_diagnostics(self) -> bool:
        """Export bridge logs for testing. Excludes saves, journals, bridge token and seed files."""
        from .platform_diagnostics import export_diagnostics
        try:
            self.output('Diagnostic ZIP: ' + str(export_diagnostics()))
            return True
        except OSError as exc:
            self.output('Could not export diagnostics: ' + str(exc)); return False

    def _cmd_interaction(self) -> bool:
        """Record the current selected object/enemy and grab state without changing the game."""
        self.ctx.interaction_status_requested = True
        self.ctx.watcher_event.set()
        self.output('Interaction snapshot queued. Stand near the object/enemy that will not respond; details will appear here and in the client log.')
        return True

    def _cmd_enemies(self, setting: str = '') -> bool:
        """Show enemy mode, or use /enemies off to disable it locally for this seed. Restart the game afterwards."""
        ctx = self.ctx
        if not ctx.reward_session_key or not ctx.seed_data_received:
            self.output('Connect to your multiworld slot first, then use /enemies off.')
            return False
        if setting.strip().lower() not in ('', 'off'):
            self.output('Usage: /enemies or /enemies off')
            return False
        try:
            if setting:
                staged = ctx.enemy_preferences.disable(ctx.reward_session_key)
                ctx.enemy_failure = None
                ctx.watcher_event.set()
                self.output('Randomized enemies disabled locally for this seed and player. '
                            'Close and restart the game and client; wait for Game connected before Continue. '
                            'Restart the level if resuming its checkpoint still causes trouble.')
                if not staged:
                    self.output('Game folder not yet available. Leave the game at the main menu until the client confirms readiness.')
            else:
                mode = ('OFF (local override)' if ctx.enemy_preferences.disabled(ctx.reward_session_key)
                        else 'ON (seed setting)' if ctx.slot_data.get('randomize_minor_enemies') else 'OFF (seed setting)')
                self.output('Randomized enemies: ' + mode + '. Use /enemies off to opt out locally.')
            return True
        except (OSError, ValueError) as exc:
            self.output('Could not finish enemy preference update: ' + str(exc) + '. Do not enter a level until resolved.')
            return False
