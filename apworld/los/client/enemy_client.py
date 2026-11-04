"""Serialized, bounded preparation through the existing AP bridge only."""
from importlib import resources
import hashlib
import json
import logging
from collections import deque
from ..enemies import ENEMY_POOL, LAYOUT_VERSION
from .skills import quote
from .enemy_plan import write_active
from ..enemies import build_plan

log=logging.getLogger('Lords of Shadow enemies')

class EarlyEnemyClient:
    def __init__(self,seed):
        root=resources.files(__package__).joinpath('enemy_data')
        self.manifest=json.loads(root.joinpath('manifest.json').read_text())
        if self.manifest['layout_version']!=LAYOUT_VERSION:
            raise ValueError('Enemy catalog/layout mismatch')
        self.seed=seed
        self.plan=build_plan(seed,self.manifest['spawn_catalog'])
        self.plan['enabled']=True
        self.last_status=None

    def tick(self,execute,root,preferences=None,session=None):
        if not (root/'enemy_early.lua').is_file():
            raise RuntimeError('Install the 0.7.0 early-loader package before enabling enemy randomization')
        if preferences is None:
            write_active(root,self.plan)
        elif not preferences.stage(session,root,self.plan):
            return False  # An opt-out may arrive while this worker is in flight.
        state=execute("local e=APEnemyEarly;local s=APEnemyShuffle;Game.Set('InitLuaLine',tostring(init and init.LevelName)..'|'..tostring(e and e.Seed)..'|'..tostring(e and e.State)..'|'..tostring(e and e.Error)..'|'..tostring(s and s.Changed)..'|'..tostring(s and s.Skipped)..'|'..tostring(e and e.Version==7 and s and s.Version==7 and s.Enabled and NPC.CreateSingleEnemy==s.Single and true))")
        parts=state.split('|')
        if len(parts)!=7:return False
        level,seed,status,error,changed,skipped,attached=parts
        level=level.removeprefix('level.')
        passthrough=self.plan['levels'].get(level,{}).get('passthrough',False)
        ready=level not in self.manifest['levels'] or (seed==self.seed and (
            (passthrough and status=='inactive') or
            (not passthrough and status=='map-created' and attached=='true')))
        if state!=self.last_status:
            if ready:
                log.info('Precomputed enemy plan ready: level=%s state=%s changed=%s preserved=%s',level,status,changed,skipped)
                if level in self.manifest['levels']:
                    detail=execute("local s=APEnemyShuffle;Game.Set('InitLuaLine',s and table.concat(s.Log or {},';') or '')")
                    if detail:log.info('Enemy spawn decisions (latest 25): %s',detail)
            else:log.error('Early enemy loader not ready (%s / %s). Plan is staged; return to the menu and re-enter the level. %s',level,status,error)
            self.last_status=state
        return ready

    @staticmethod
    def disable(execute,root):
        if (root/'enemy_early.lua').is_file():write_active(root,{'enabled':False})
        EnemyClient.stop(execute)

class EnemyClient:
    def __init__(self,seed):
        if not isinstance(seed,str) or not seed: raise ValueError('Enemy seed must be a nonempty string')
        self.seed=seed
        self.root=resources.files(__package__)
        self.data=self.root.joinpath('enemy_data')
        self.manifest=json.loads(self.data.joinpath('manifest.json').read_text())
        if self.manifest['layout_version']!=LAYOUT_VERSION or tuple(self.manifest['pool'])!=ENEMY_POOL:
            raise ValueError('Enemy catalog/layout mismatch')
        self.level=None;self.token=None;self.commands=deque();self.blocked=set();self.serial=0
        self.last_status=None

    def prepare(self,level):
        self.serial+=1
        self.level=level;self.token=hashlib.sha256((self.seed+'|'+level+'|'+str(self.serial)).encode()).hexdigest()[:24]
        native=set(self.manifest['levels'][level])
        self.commands=deque()
        self.commands.append('if APEnemyShuffle and APEnemyShuffle.Stop then APEnemyShuffle.Stop() end;APEnemyReady=nil;\n'+self.root.joinpath('enemy_loader.lua').read_text()+'\nAPEnemyPreparing='+quote(self.token))
        def entries(target,values):
            lines=[]
            for key,value in sorted(values.items()):
                lines.append(target+'['+quote(key)+']='+value)
                if len(lines)==40: self.commands.append(';'.join(lines));lines=[]
            if lines: self.commands.append(';'.join(lines))
        entries('APEnemyLoader.NativePaths',{p:'true' for p in native})
        required=set()
        for name,d in sorted(self.manifest['enemies'].items()):
            target='APEnemyLoader.Definitions['+quote(name)+']'
            self.commands.append(target+'={action='+quote(d['action'])+',donor='+quote(d['donor'])+',scripts={},events={'+','.join('['+quote(n)+']=true' for n in d['events'])+'}}')
            entries(target+'.scripts',{p:quote(h) for p,h in d['scripts'].items()})
            required.update(h for p,h in d['scripts'].items() if p not in native)
        for digest in sorted(required):
            payload=self.data.joinpath(self.manifest['chunks'][digest]).read_bytes()
            if hashlib.sha256(payload).hexdigest()!=digest: raise ValueError('Corrupt enemy dependency '+digest)
            self.commands.append('APEnemyTransfer={}')
            for offset in range(0,len(payload),20000):
                escaped='"'+''.join('\\%03d'%b for b in payload[offset:offset+20000])+'"'
                self.commands.append('APEnemyTransfer[#APEnemyTransfer+1]='+escaped)
            self.commands.append('APEnemyLoader.Bank['+quote(digest)+']=table.concat(APEnemyTransfer);APEnemyTransfer=nil')
        self.commands.append(self.root.joinpath('enemy_floor.lua').read_text())
        self.commands.append(self.root.joinpath('enemy_runtime.lua').read_text())
        protected=self.manifest.get('protected',{}).get(level,[])
        setup='APEnemyShuffle.Configure('+quote(self.seed)+','+quote(level)+',{' + ','.join(quote(n) for n in ENEMY_POOL)+'},APEnemyLoader.Definitions,{'+','.join('['+quote(n)+']=true' for n in protected)+'});'
        setup+='assert(APEnemyShuffle.Install());APEnemyReady='+quote(self.token)
        self.commands.append(setup)
        log.info('Preparing %d enemy types in %s (%d bounded transfer steps)',len(ENEMY_POOL),level,len(self.commands))

    def tick(self,execute):
        state=execute("Game.Set('InitLuaLine',tostring(init and init.LevelName)..'|'..tostring(APEnemyPreparing)..'|'..tostring(APEnemyReady)..'|'..tostring(NPC and NPC.CreateSingleEnemy and EnemyGen and player and player.GetOnFloorPos and MakeChar and MakeChar.LoadEvents and Game.PreloadLibrary and AI and AI.IsEntAssocNearGraph and true))")
        parts=state.split('|')
        if len(parts)!=4: return
        level,preparing,ready,available=parts;level=level.removeprefix('level.')
        if level not in self.manifest['levels'] or available!='true': return
        if level in self.blocked:return
        if level!=self.level or (self.token and preparing!=self.token):
            self.prepare(level)
        if ready==self.token:
            status=execute("local s=APEnemyShuffle;Game.Set('InitLuaLine',tostring(s and s.Changed)..'|'..tostring(s and s.Skipped)..'|'..tostring(APEnemyLoader and APEnemyLoader.Fault)..'|'..(s and table.concat(s.Log,';') or ''))")
            if status!=self.last_status:
                log.info('Enemy coverage %s: %s',level,status);self.last_status=status
            return
        try:
            # Bound preparation work per AP loop; never run a second bridge owner.
            for _ in range(12):
                if not self.commands:break
                source=self.commands[0]
                condition="tostring(init and init.LevelName):gsub('^level%.','')=="+quote(level)
                if not source.startswith('APEnemyLoader='):
                    condition+=' and APEnemyPreparing=='+quote(self.token)
                # First loader source starts with comments, so use identity of
                # queue item to determine whether the token exists yet.
                if 'APEnemyPreparing='+quote(self.token) in source:
                    condition="tostring(init and init.LevelName):gsub('^level%.','')=="+quote(level)
                result=execute('if '+condition+' then local ok,why=pcall(function() '+source+'\nend);Game.Set("InitLuaLine",ok and "--enemy-step" or ("--enemy-error:"..tostring(why))) else Game.Set("InitLuaLine","--enemy-transition") end')
                if result=='--enemy-transition': self.level=None;self.commands.clear();return
                if result!='--enemy-step':raise RuntimeError(result)
                self.commands.popleft()
            if not self.commands:log.warning('Enemy hooks ready in %s; coverage logs report preserved/early spawns',level)
        except Exception:
            self.blocked.add(level);self.commands.clear()
            log.exception('Enemy preparation quarantined for %s; original spawns retained',level)

    @staticmethod
    def stop(execute):
        execute("if APEnemyShuffle and APEnemyShuffle.Stop then APEnemyShuffle.Stop() end;APEnemyPreparing=nil;APEnemyReady=nil;Game.Set('InitLuaLine','--enemy-stopped')")
