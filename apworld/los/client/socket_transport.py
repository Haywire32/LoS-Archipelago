"""Authenticated loopback transport for a native client and the DLL under Proton.

No Lua commands, results, server passwords or endpoint tokens are logged.
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
import re
import socket
import struct
import threading
import time

from .dropin_transport import DropInUnavailable

logger = logging.getLogger('LoSBridge')
HEADER = struct.Struct('<4sIII')
MAX_FRAME = 140840
GAME_DIR = None


def set_game_dir(value):
    global GAME_DIR
    GAME_DIR = Path(value).expanduser() if value else None


def game_bins():
    explicit = GAME_DIR or os.environ.get('LOS_AP_GAME_DIR')
    if explicit:
        path = Path(explicit).expanduser()
        if path.name.lower() == 'castlevanialosue.exe':
            path = path.parent
        return [path if (path / 'CastlevaniaLoSUE.exe').is_file() else path / 'bin']
    home = Path.home()
    roots = [home / '.steam/steam', home / '.local/share/Steam',
             home / '.var/app/com.valvesoftware.Steam/.local/share/Steam']
    libraries = list(roots)
    for root in roots:
        try:
            text = (root / 'steamapps/libraryfolders.vdf').read_text(encoding='utf-8')
            libraries.extend(Path(s.replace('\\\\', '\\')) for s in re.findall(r'"path"\s*"([^"]+)"', text))
        except OSError:
            pass
    bins = []
    for library in libraries:
        folder = 'CastlevaniaLoS'
        try:
            text = (library / 'steamapps/appmanifest_234080.acf').read_text(encoding='utf-8')
            match = re.search(r'"installdir"\s*"([^"]+)"', text)
            if match:
                folder = match[1]
        except OSError:
            pass
        path = (library / 'steamapps/common' / folder / 'bin').resolve()
        if path not in bins:
            bins.append(path)
    return bins


def receive(sock, count):
    data = bytearray()
    while len(data) < count:
        chunk = sock.recv(count - len(data))
        if not chunk:
            raise DropInUnavailable('Game bridge disconnected. Check bridge.log and restart/reconnect.')
        data.extend(chunk)
    return bytes(data)


class SocketTransport:
    diagnostics_enabled = True
    def __init__(self):
        self._socket = None
        self._lock = threading.Lock()
        self._sequence = 0
        failures = []
        for folder in game_bins():
            endpoint = folder / 'APEnemy/bridge.json'
            try:
                if os.name != 'nt' and endpoint.is_file():
                    endpoint.chmod(0o600)
                info = json.loads(endpoint.read_text(encoding='utf-8'))
                if info.get('protocol') != 1 or not isinstance(info.get('port'), int) or not 1 <= info['port'] <= 65535:
                    raise ValueError('unsupported endpoint protocol/port')
                token = info.get('token', '')
                if not isinstance(token, str) or not re.fullmatch('[0-9a-f]{64}', token):
                    raise ValueError('invalid endpoint token')
                self._socket = socket.create_connection(('127.0.0.1', info['port']), timeout=2)
                self._socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                self._socket.settimeout(5)
                response = self._exchange(1, token.encode('ascii'))
                hello = response.decode('ascii').split('|')
                if len(hello) != 3 or int(hello[0]) != info['pid'] or hello[1] not in ('0.7.6', 'linux-preview-1'):
                    raise ValueError('endpoint identity/build mismatch')
                self._pid = int(hello[0])
                self._folder = folder
                logger.info('LoS bridge connected: loopback build=%s pid=%s state=%s game=%s', hello[1], hello[0], hello[2], folder)
                return
            except (OSError, ValueError, KeyError, TypeError, DropInUnavailable) as exc:
                self.close()
                # Never include endpoint contents/auth tokens in diagnostics.
                failures.append(f'{folder}: {type(exc).__name__}: {exc}')
        raise DropInUnavailable('Linux/Proton bridge unavailable. Start the game with the installed dinput8.dll. '
            'If Proton does not load it, add WINEDLLOVERRIDES="dinput8=n,b" %command% to Steam launch options. '
            'Use /game_dir PATH for a custom Steam library. '
            'If bridge.json/log is missing, the DLL did not start or its folder is not writable. ' + '; '.join(failures))

    def _exchange(self, kind, payload):
        self._sequence = (self._sequence + 1) & 0xffffffff or 1
        self._socket.sendall(HEADER.pack(b'LSAP', kind, self._sequence, len(payload)) + payload)
        magic, response_kind, sequence, length = HEADER.unpack(receive(self._socket, HEADER.size))
        if magic != b'LSAP' or sequence != self._sequence or length > MAX_FRAME or response_kind not in (kind, 3):
            raise DropInUnavailable('Invalid bridge reply header; connection closed.')
        response = receive(self._socket, length)
        if response_kind == 3:
            raise DropInUnavailable(response.decode('utf-8', errors='replace'))
        return response

    def execute(self, lua, *, cleanup='Game.Set("InitLuaLine","")', timeout=20.0):
        command, clean = lua.encode('utf-8'), cleanup.encode('utf-8')
        if len(command) >= 131072 or len(clean) >= 1024 or b'\0' in command or b'\0' in clean:
            raise DropInUnavailable('Lua command exceeds bridge limits or contains a NUL.')
        with self._lock:
            if self._socket is None:
                raise DropInUnavailable('Game bridge connection is closed.')
            started = time.monotonic()
            try:
                self._socket.settimeout(timeout + 5)
                value = self._exchange(2, struct.pack('<II', len(command), len(clean)) + command + clean)
                elapsed = time.monotonic() - started
                if elapsed > 2 or self._sequence % 64 == 0:
                    logger.info('LoS bridge reply: sequence=%s seconds=%.2f bytes=%s', self._sequence, elapsed, len(command))
                return value.decode('utf-8', errors='replace')
            except (OSError, DropInUnavailable) as exc:
                logger.warning('LoS bridge request failed: sequence=%s elapsed=%.2f error=%s; request NOT replayed', self._sequence, time.monotonic()-started, exc)
                self.close()
                raise DropInUnavailable(f'Loopback bridge: {exc}') from exc

    def close(self):
        if self._socket is not None:
            self._socket.close()
            self._socket = None

    def executable_path(self):
        path = self._folder / 'CastlevaniaLoSUE.exe'
        if not path.is_file():
            raise DropInUnavailable(f'Game executable missing at {path}; use /game_dir PATH.')
        return path

    @property
    def target_pid(self):
        return self._pid
