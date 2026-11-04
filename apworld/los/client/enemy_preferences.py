"""Local-only, per-seed/player enemy opt-out; never changes server slot data."""
import json
import os
from pathlib import Path
import tempfile
import threading
from .reward_ledger import default_ledger_path
from .enemy_plan import write_active


class EnemyPreferences:
    def __init__(self, path=None):
        self.path = Path(path) if path else default_ledger_path().with_name('enemy-preferences.json')
        self.lock = threading.RLock()

    def read(self):
        try:
            data = json.loads(self.path.read_text(encoding='utf-8'))
        except FileNotFoundError:
            return {'disabled': [], 'root': None}
        if not isinstance(data, dict) or not isinstance(data.get('disabled'), list):
            raise ValueError('Invalid local enemy preferences; restore this file before continuing')
        return data

    def save(self, data):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, name = tempfile.mkstemp(dir=self.path.parent, prefix='enemy-', suffix='.tmp')
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as stream:
                json.dump(data, stream); stream.flush(); os.fsync(stream.fileno())
            os.replace(name, self.path)
        finally:
            if os.path.exists(name): os.unlink(name)

    def disabled(self, session):
        with self.lock:
            return session in self.read()['disabled']

    def disable(self, session):
        with self.lock:
            data = self.read()
            if session not in data['disabled']: data['disabled'].append(session)
            self.save(data)  # Persist first: never lose opt-out if staging fails.
            root = Path(data['root']) if data.get('root') else None
            if root and (root / 'enemy_early.lua').is_file():
                write_active(root, {'enabled': False})
                return True
            return False

    def stage(self, session, root, plan):
        with self.lock:
            data = self.read()
            if data.get('root') != str(root):
                data['root'] = str(root)
                self.save(data)
            disabled = session in data['disabled']
            write_active(root, {'enabled': False} if disabled else plan)
            return not disabled
