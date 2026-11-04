from __future__ import annotations

import asyncio
from collections.abc import Sequence
import logging

import colorama
from CommonClient import get_base_parser, gui_enabled, handle_url_arg, server_loop

from .context import LordsOfShadowContext


async def main(args) -> None:
    from .platform_diagnostics import configure
    context = LordsOfShadowContext(args.connect, args.password)
    context.auth = args.name
    context.server_task = asyncio.create_task(server_loop(context), name="server loop")
    watcher = asyncio.create_task(context.game_watcher(), name="Lords of Shadow game watcher")
    def report_watcher_exit(task):
        if task.cancelled():
            return
        error = task.exception()
        if error is not None:
            logging.getLogger('LoSBridge').error(
                'Game watcher stopped unexpectedly',
                exc_info=(type(error), error, error.__traceback__))
        elif not context.exit_event.is_set():
            logging.getLogger('LoSBridge').error('Game watcher exited before shutdown')
    watcher.add_done_callback(report_watcher_exit)

    if gui_enabled and not getattr(args, "nogui", False):
        context.run_gui()
    # Set up our handlers after the UI has initialized its logging machinery.
    configure(getattr(args, 'game_dir', None))
    context.run_cli()

    try:
        await context.exit_event.wait()
    finally:
        watcher.cancel()
        await asyncio.gather(watcher, return_exceptions=True)
        await context.shutdown()


def launch_client(*args: Sequence[str]) -> None:
    parser = get_base_parser(description="Lords of Shadow Archipelago Client")
    parser.add_argument("--game-dir", help="Linux/Proton: installed game folder or bin folder")
    parser.add_argument("--name", default=None, help="Archipelago slot name")
    parser.add_argument("url", nargs="?", help="Archipelago connection URL")
    parsed = handle_url_arg(parser.parse_args(args), parser=parser)

    logging.getLogger().setLevel(logging.INFO)
    colorama.just_fix_windows_console()
    try:
        asyncio.run(main(parsed))
    finally:
        colorama.deinit()
