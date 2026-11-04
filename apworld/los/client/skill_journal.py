"""Transport-independent purchase journal for the private pilot.

No connection, seed, XP grant or game launch happens on import. The future client
adapter supplies the existing bridge as commit(session, runtime, tx, action).
Location sends may be retried; XP debit must never be blindly retried after a
runtime change. File corruption and ambiguous transactions fail closed.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
from uuid import uuid4

from ..skills import BY_ACTION as PILOT


class AmbiguousPurchase(RuntimeError):
    pass


class Coordinator:
    def __init__(self, path: Path, session: str):
        if not session:
            raise ValueError('Seed/team/slot identity is required')
        self.path, self.session = path, session
        self.faulted = False
        self.state = {'version': 1, 'session': session, 'checked': [], 'pending': None}
        if path.exists():
            self.state = json.loads(path.read_text(encoding='utf-8'))
        if (not isinstance(self.state, dict) or set(self.state) != {'version','session','checked','pending'}
                or self.state.get('version') != 1 or self.state.get('session') != session
                or not isinstance(self.state.get('checked'), list)
                or any(a not in PILOT for a in self.state['checked'])):
            raise ValueError('Invalid or mismatched skill journal; do not reset automatically')
        pending = self.state.get('pending')
        if pending is not None and (not isinstance(pending, dict)
                or pending.get('action') not in PILOT
                or not all(isinstance(pending.get(k), str) and pending[k] for k in ('runtime', 'tx'))):
            raise ValueError('Invalid pending skill transaction')

    def _save(self):
        try:
            self._write()
        except Exception:
            # In-memory changes cannot be treated as durable after any write failure.
            # Reopen the journal before further game debits or AP sends.
            self.faulted = True
            raise

    def _healthy(self):
        if self.faulted:
            raise AmbiguousPurchase('Journal write failed; reopen before continuing')

    def _write(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, name = tempfile.mkstemp(prefix='skill-', suffix='.tmp', dir=self.path.parent)
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as stream:
                json.dump(self.state, stream, sort_keys=True)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(name, self.path)
        finally:
            Path(name).unlink(missing_ok=True)

    def purchase(self, action: str, runtime: str, commit) -> bool:
        self._healthy()
        if action not in PILOT or not runtime:
            raise ValueError('Unknown paid skill or missing runtime identity')
        if self.state['pending'] is not None:
            raise AmbiguousPurchase('Recover pending purchase before accepting another')
        if action in self.state['checked']:
            return False
        self.state['pending'] = {'action': action, 'runtime': runtime, 'tx': uuid4().hex}
        self._save()  # A failure here must never reach the game debit.
        return self.recover(runtime, commit)

    def recover(self, runtime: str, commit) -> bool:
        self._healthy()
        pending = self.state['pending']
        if pending is None:
            return False
        if pending['runtime'] != runtime:
            raise AmbiguousPurchase('Game runtime changed: XP debit is uncertain; purchases paused')
        result = commit(self.session, runtime, pending['tx'], pending['action'])
        if result not in ('paid', 'rejected'):
            raise AmbiguousPurchase('No definite game receipt; retain journal and pause purchases')
        if result == 'paid' and pending['action'] not in self.state['checked']:
            self.state['checked'].append(pending['action'])
        self.state['pending'] = None
        self._save()  # Only after this succeeds may the adapter send AP locations.
        return result == 'paid'

    def unsent_checks(self, server_checked: set[str]) -> set[str]:
        self._healthy()
        return set(self.state['checked']) - server_checked
