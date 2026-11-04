"""Small, opt-in export of bridge diagnostics; never export bridge.json or saves."""
import ctypes
import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import platform
import time
import zipfile

BUILD = '0.7.6'
_log_handler = None


def state_dir():
    base = Path(os.environ.get('LOCALAPPDATA', str(Path.home() / 'AppData/Local'))) if os.name == 'nt' else Path(os.environ.get('XDG_STATE_HOME', str(Path.home() / '.local/state')))
    return base / 'Archipelago/LordsOfShadow'


def ensure_logging():
    global _log_handler
    if _log_handler is None:
        root = state_dir()
        root.mkdir(parents=True, exist_ok=True)
        _log_handler = RotatingFileHandler(root / 'bridge-client.log', maxBytes=1048576, backupCount=2, encoding='utf-8')
        _log_handler.setFormatter(logging.Formatter('%(asctime)s pid=%(process)d %(levelname)s %(name)s %(message)s'))
    for name in ('LoSBridge', 'Client.LoS'):
        logger = logging.getLogger(name)
        if _log_handler not in logger.handlers:
            logger.addHandler(_log_handler)
        logger.disabled = False
        logger.setLevel(logging.INFO)
        # Bridge details belong only in the diagnostic file, never in the
        # launcher's console/root handlers. Player notices still reach Client.
        logger.propagate = name != 'LoSBridge'
    return Path(_log_handler.baseFilename)


def configure(game_dir=None):
    from .socket_transport import set_game_dir
    ensure_logging()
    root = state_dir()
    logger = logging.getLogger('LoSBridge')
    if not game_dir:
        try:
            game_dir = json.loads((root / 'linux-settings.json').read_text()).get('game_dir')
        except (OSError, ValueError, AttributeError):
            pass
    set_game_dir(game_dir)
    logger.info('Startup build=%s OS=%s Python=%s bits=%s long_size=%s game_override=%s', BUILD, platform.platform(), platform.python_version(), ctypes.sizeof(ctypes.c_void_p)*8, ctypes.sizeof(ctypes.c_long), game_dir)


def save_game_dir(value):
    from .socket_transport import set_game_dir
    path = Path(value.strip().strip('"').strip("'")).expanduser().resolve()
    folder = path.parent if path.name.lower() == 'castlevanialosue.exe' else path
    folder = folder if (folder / 'CastlevaniaLoSUE.exe').is_file() else folder / 'bin'
    if not (folder / 'CastlevaniaLoSUE.exe').is_file() or not (folder / 'APEnemy/enemy_early.lua').is_file():
        raise ValueError('Choose the installed CastlevaniaLoS folder (or its bin folder), containing the mod APEnemy files.')
    root = state_dir(); root.mkdir(parents=True, exist_ok=True)
    temp = root / 'linux-settings.tmp'
    temp.write_text(json.dumps({'game_dir': str(folder)}), encoding='utf-8')
    os.replace(temp, root / 'linux-settings.json')
    set_game_dir(folder)
    logging.getLogger('LoSBridge').info('Game folder selected: %s', folder)
    return folder


def export_diagnostics():
    from .socket_transport import game_bins
    from .dropin_transport import SharedCommand
    log_path = ensure_logging()
    logging.getLogger('LoSBridge').info('Exporting diagnostics build=%s', BUILD)
    _log_handler.flush()
    root = state_dir(); root.mkdir(parents=True, exist_ok=True)
    target = root / ('LoS-diagnostics-' + time.strftime('%Y%m%d-%H%M%S') + '.zip')
    summary = {'build': BUILD, 'os': platform.platform(), 'python': platform.python_version(),
               'long_size': ctypes.sizeof(ctypes.c_long), 'bridge_layout': ctypes.sizeof(SharedCommand),
               'client_pid': os.getpid(), 'client_log_path': str(log_path), 'folders': []}
    with zipfile.ZipFile(target, 'w', zipfile.ZIP_DEFLATED) as z:
        for name in ('bridge-client.log', 'bridge-client.log.1', 'bridge-client.log.2'):
            path = log_path.parent / name
            if path.is_file():
                z.write(path, name)
        for index, folder in enumerate(game_bins()):
            summary['folders'].append({'path': str(folder), 'exe': (folder / 'CastlevaniaLoSUE.exe').is_file(),
                                      'endpoint_present': (folder / 'APEnemy/bridge.json').is_file()})
            # Whitelist only diagnostics; never token, seed plans, journals or saves.
            for name in ('bridge.log', 'bridge.previous.log', 'loading.log', 'archive-view.log'):
                path = folder / 'APEnemy' / name
                if path.is_file():
                    with path.open('rb') as f:
                        f.seek(max(0, path.stat().st_size - 2*1024*1024))
                        z.writestr(f'game-{index}/{name}', f.read())
        z.writestr('summary.json', json.dumps(summary, indent=2))
    return target
