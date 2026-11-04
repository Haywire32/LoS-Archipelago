"""Paid-only skills, serialized through the existing native bridge owner."""
from __future__ import annotations
import hashlib
from importlib import resources
import os
from pathlib import Path
import time
from uuid import uuid4

from ..skills import BY_ACTION, SKILL_ITEM_NAMES, SKILL_LOCATION_IDS, RELICS
from .skill_journal import Coordinator, AmbiguousPurchase


def quote(text: str) -> str:
    return '"' + ''.join('\\%03d' % byte for byte in text.encode('utf-8')) + '"'


def flags(values) -> str:
    return '{' + ','.join('['+quote(v)+']=true' for v in sorted(values)) + '}'


def preview_text(item_name: str, recipient: str) -> str:
    # Remote names are display data, never Lua, markup or commands.
    clean = lambda s: ' '.join(''.join(c for c in str(s) if c.isprintable()).split())
    return 'Reward: ' + clean(item_name) + ' -> ' + clean(recipient)


def preview_frame(text: str, phase: int, width: int = 52) -> str:
    """Overlapping pages preserve the full foreign item/recipient name on small UI."""
    if len(text) <= width:
        return text
    offsets = list(range(0, max(1, len(text)-width+1), width-8))
    if offsets[-1] != len(text)-width:
        offsets.append(len(text)-width)
    offset = offsets[phase % len(offsets)]
    return ('<' if offset else ' ') + text[offset:offset+width] + ('>' if offset+width<len(text) else ' ')


class SkillClient:
    def __init__(self, session: str, journal: Path | None = None):
        if journal is None:
            root=Path(os.environ.get('LOCALAPPDATA', str(Path.home()/'AppData/Local')))
            journal=root/'Archipelago/LordsOfShadow/skill-purchases'/(
                hashlib.sha256(session.encode()).hexdigest()+'.json')
        self.coordinator=Coordinator(journal,session)
        self.session=session

    def tick(self, execute, counts: dict, checked_ids: set[int], *, connected: bool,
             reveal: bool, rewards: dict[str,str]) -> set[int]:
        self.coordinator._healthy()
        probe=execute("local s=APPaidSkills; local ready=Experience and Experience.CombatScrollActive and Experience.EPoints and TravelBook and TravelBook.ActionsManager and TravelBook.ActionsManager.ActionAnimName and TravelBook.ActionsManager.ActionAnimName.Guillotine; Game.Set('InitLuaLine',not ready and '--SKILLS|waiting' or (s and ('--SKILLS|'..tostring(s.Version)..'|'..(s.Runtime or '')..'|'..(s.Pending or '')) or '--SKILLS|absent'))")
        if probe=='--SKILLS|waiting':
            return set()
        if probe=='--SKILLS|absent':
            if not connected:
                return set()
            if self.coordinator.state['pending']:
                raise AmbiguousPurchase('Skill purchase interrupted by game reload; retain journal for recovery')
            execute(resources.files(__package__).joinpath('paid_skills.lua').read_text(encoding='utf-8'))
            execute(resources.files(__package__).joinpath('paid_skills_menu.lua').read_text(encoding='utf-8'))
            runtime=uuid4().hex; pending=''
        else:
            parts=probe.split('|')
            if len(parts)!=4 or parts[:2]!=['--SKILLS','3']:
                raise RuntimeError('Unexpected skill runtime; close private test helper and restart game')
            runtime,pending=parts[2:]
            if not runtime:
                runtime=uuid4().hex
                execute(resources.files(__package__).joinpath('paid_skills_menu.lua').read_text(encoding='utf-8'))
        owned={action for action,name in SKILL_ITEM_NAMES.items() if counts.get(name,0)>0}
        relics={name for name in RELICS.values() if counts.get(name,0)>0}
        server_checked={action for action,code in SKILL_LOCATION_IDS.items() if code in checked_ids}
        checked=server_checked | set(self.coordinator.state['checked'])
        windows={a:preview_frame(label,int(time.monotonic()/3)) for a,label in rewards.items()} if reveal else {}
        table='{'+','.join('['+quote(a)+']='+quote(v) for a,v in windows.items() if a in BY_ACTION)+'}'
        execute('APPaidSkills.RevealRewards='+('true' if reveal else 'false')+
                '; APPaidSkills.RewardLabels='+table+'; APPaidSkills.Sync('+','.join([
                    quote(self.session),quote(runtime),flags(checked),flags(owned),flags(relics),
                    'true' if connected else 'false'])+
                "); Game.Set('InitLuaLine','--SKILLS|synced')")
        if not connected:
            return set()
        def commit(session,run,tx,action):
            reply=execute("Game.Set('InitLuaLine','--SKILLS|'..APPaidSkills.Commit("+
                          ','.join(quote(x) for x in (session,run,tx,action))+'))')
            if reply not in ('--SKILLS|paid','--SKILLS|rejected'):
                raise AmbiguousPurchase('No definite XP receipt; retain journal and stop purchases')
            return reply.split('|')[1]
        if self.coordinator.state['pending']:
            self.coordinator.recover(runtime,commit)
        elif pending:
            self.coordinator.purchase(pending,runtime,commit)
        return {SKILL_LOCATION_IDS[a] for a in self.coordinator.unsent_checks(server_checked)}
