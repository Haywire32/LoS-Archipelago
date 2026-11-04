-- Expanded experimental hooks. Original retail creators own counters, group
-- membership, callbacks, activation and save/checkpoint behavior.
if APEnemyShuffle and APEnemyShuffle.Stop then APEnemyShuffle.Stop() end
APEnemyShuffle={Version=7,Enabled=false,Seen=0,Changed=0,Skipped=0,Reasons={},Log={},Done={},BestiarySuppressed=0}
local S=APEnemyShuffle
local function pack(...) return {n=select('#',...),...} end
local function get(rows,key)
    for _,row in pairs(rows or {}) do if type(row)=='table' and row[1]==key then return row[2] end end
end
local function copy(rows,changes)
    local out,found={},{}
    for k,row in pairs(rows) do
        if type(row)=='table' then
            local v={};for a,b in pairs(row) do v[a]=b end
            if changes[row[1]]~=nil then v[2]=changes[row[1]];found[row[1]]=true end
            out[k]=v
        else out[k]=row end
    end
    for k,v in pairs(changes) do if not found[k] then out[#out+1]={k,v} end end
    return out
end
local function record(key,original,target,reason)
    S.Seen=S.Seen+1
    if reason=='replaced' then S.Changed=S.Changed+1 else
        S.Skipped=S.Skipped+1;S.Reasons[reason]=(S.Reasons[reason] or 0)+1
    end
    if #S.Log>=25 then table.remove(S.Log,1) end
    S.Log[#S.Log+1]=key..':'..tostring(original)..'>'..tostring(target)..':'..reason
end
function S.Hash(key)
    local seed=S.Seed;local level=S.Level
    local value='enemy-layout-7|'..#seed..':'..seed..'|'..#level..':'..level..'|'..key
    local h=0
    for i=1,#value do h=(h*31+string.byte(value,i))%65521 end
    return h
end
function S.Choose(key)
    if S.Plan then
        local name=key:match('^static:(.*)$')
        if name then return S.Plan.static[name] end
        local group,wave,member=key:match('^group:(.*):(%d+):(%d+)$')
        local stream=group and S.Plan.groups[group]
        if stream then
            local width=#S.Targets
            local waves=#stream/width
            local offset=(tonumber(wave)%waves)*width+(tonumber(member)%width)+1
            return S.Pool[string.byte(stream,offset)-64]
        end
        return nil
    end
    return S.Targets[S.Hash(key)%#S.Targets+1]
end
function S.Configure(seed,level,pool,definitions,protected,plan)
    assert(type(seed)=='string' and seed~='' and type(level)=='string')
    local set={};local sorted={}
    for _,name in ipairs(pool) do assert(not set[name] and definitions[name]);set[name]=true;sorted[#sorted+1]=name end
    assert(#sorted>0);table.sort(sorted)
    S.Seed=seed;S.Level=level:gsub('^level%.','');S.Pool=sorted;S.Allowed=set
    S.Targets={}
    for _,name in ipairs((plan and plan.roster) or sorted) do assert(set[name]);S.Targets[#S.Targets+1]=name end
    assert(#S.Targets>0)
    S.Definitions=definitions;S.Protected=protected or {};S.Plan=plan;S.Enabled=true
    -- A replacement imported from another level can fight normally, but its
    -- Travel Book portrait and description assets are not part of this map's
    -- resource bundle. Unlocking that entry makes the pause book wait forever.
    S.Foreign={}
    for _,name in ipairs(sorted) do
        local path='scripts/chars/'..string.lower(name)
        S.Foreign[name]=not (APEnemyLoader and APEnemyLoader.NativePaths and APEnemyLoader.NativePaths[path])
    end
    S.BestiarySources=setmetatable({}, {__mode='k'})
end
local function replacement(original,key,pos)
    if not S.Enabled or not S.Allowed[original] then return nil end
    for _,name in ipairs(S.Plan and S.Plan.preserved_types or {}) do
        if original==name then record(key,original,original,'puzzle-controller');return nil end
    end
    if S.Protected[key] then record(key,original,original,'scripted-protected');return nil end
    -- Goblin bombs are progression tools; retain original goblins until every
    -- puzzle source is individually audited. Goblins may be destinations.
    if original=='Goblin' then record(key,original,original,'puzzle-goblin');return nil end
    local target=S.Choose(key)
    if not target then record(key,original,original,'unplanned-spawn');return nil end
    -- Ground relocation is applied even if the deterministic choice equals the
    -- original. Otherwise the same-type branch could leave a wall entrance.
    local ready,why=APEnemyEnsure(target)
    if not ready then record(key,original,target,'dependency:'..tostring(why));return nil end
    -- Cross-level replacement controllers have no graph association registered
    -- in this map, which makes every valid position look unreachable. Validate
    -- arena connectivity through the authored enemy's native graph instead.
    -- The replacement probe still supplies the target's actual collision body.
    local graphType=original
    -- Validate placement BEFORE constructing the real NPC. A failed probe
    -- preserves the original row and native entrance behavior, without a
    -- partially created replacement or an exception escaping map creation.
    local ok,ground,reason
    if S.Early then
        ok,ground,reason=pcall(APEnemyFloor.Preflight,pos,target,graphType)
    else
        ok,ground,reason=pcall(APEnemyFloor.Find,pos,graphType)
    end
    if not ok or not ground then record(key,original,target,ok and reason or 'floor-query-error');return nil end
    return target,ground
end
function S.Install()
    if not NPC or not S.Enabled then return false end
    S.OriginalSingle=NPC.CreateSingleEnemy
    S.Single=function(data,controller,...)
        if S.InDynamic or not data then return S.OriginalSingle(data,controller,...) end
        local name=get(data,'Name');local original=get(data,'ActCtrl')
        if not name then return S.OriginalSingle(data,controller,...) end
        for _,group in ipairs(S.Plan and S.Plan.preserved_groups or {}) do
            if get(data,'EntityList')==group then return S.OriginalSingle(data,controller,...) end
        end
        local key='static:'..name
        S.EarlyStatic=S.Early and not S.MapCreated
        local target,pos=replacement(original,key,get(data,'Pos'))
        S.EarlyStatic=false
        if not target then return S.OriginalSingle(data,controller,...) end
        local changes={ActCtrl=target,Pos=pos,ForceAction=S.Definitions[target].action}
        local entity=S.OriginalSingle(copy(data,changes),controller,...)
        if entity~=nil then
            S.BestiarySources[entity]=original
        end
        S.Done[name]=true;record(key,original,target,'replaced')
        return entity
    end
    NPC.CreateSingleEnemy=S.Single
    S.OriginalDynamic=NPC.CreateWithAI
    S.Dynamic=function(controller,x,y,z,group,...)
        local data=NPC.Groups and NPC.Groups[group] and NPC.Groups[group].uData
        local key
        if S.Pending and S.Pending.group==group and data then
            local member=S.Pending.member or 0
            S.Pending.member=member+1
            key='group:'..tostring(group)..':'..tostring(S.Pending.wave)..':'..tostring(member)
        else
            -- A direct script call has no reliable authored identity/ordinal.
            -- Keep it explicit instead of hashing timing or a global counter.
            if S.Allowed[controller] then record(tostring(group),controller,controller,'unidentified-script-spawn') end
            return S.OriginalDynamic(controller,x,y,z,group,...)
        end
        local point
        for _,p in ipairs(data.spawnPoints or {}) do
            local q=get(p,'Pos')
            if q and q.x==x and q.y==y and q.z==z and get(p,'ActCtrl')==controller then point=p;break end
        end
        if not point then return S.OriginalDynamic(controller,x,y,z,group,...) end
        local target,pos=replacement(controller,key,V3D(x,y,z))
        if not target then return S.OriginalDynamic(controller,x,y,z,group,...) end
        -- Retail sets ForceAction AFTER CreateWithAI returns. Change its
        -- selected row temporarily; generator wrapper restores it on all exits.
        for i,row in ipairs(point) do
            if row[1]=='ForceAction' then
                S.Pending.rows[#S.Pending.rows+1]={point,i,row}
                point[i]={row[1],S.Definitions[target].action}
            end
        end
        local previous=S.InDynamic;S.InDynamic=true
        local result=pack(pcall(S.OriginalDynamic,target,pos.x,pos.y,pos.z,group,...))
        S.InDynamic=previous
        if not result[1] then error(result[2],0) end
        -- Remember what the authored encounter intended. The Travel Book sees
        -- the newly constructed entity and would otherwise unlock the imported
        -- replacement, whose menu resources may not exist in this level.
        if result[2]~=nil then
            S.BestiarySources[result[2]]=controller
        end
        record(key,controller,target,'replaced')
        return unpack(result,2,result.n)
    end
    NPC.CreateWithAI=S.Dynamic
    if EnemyGen and type(EnemyGen.ActivateSpontaneousEnemy)=='function' then
        S.OriginalGenerator=EnemyGen.ActivateSpontaneousEnemy
        S.Generator=function(group,...)
            for _,name in ipairs(S.Plan and S.Plan.preserved_groups or {}) do
                if group==name then return S.OriginalGenerator(group,...) end
            end
            local data=NPC.Groups and NPC.Groups[group] and NPC.Groups[group].uData
            local previous=S.Pending
            local pending={group=group,wave=data and (data.Spawned or 0) or 0,member=0,rows={}}
            S.Pending=pending
            local distribution,lastTry
            local reorder=data and data.nSpawnPoints and data.nSpawnPoints>0
            for _,point in ipairs((data and data.spawnPoints) or {}) do
                local original=get(point,'ActCtrl')
                if not S.Allowed[original] or original=='Goblin' then reorder=false;break end
            end
            if reorder then
                distribution=data.Distribution;lastTry=data.LastSpawnTry
                local start=S.Hash('entrance:'..tostring(group)..':'..tostring(data.Spawned or 0))%data.nSpawnPoints
                data.Distribution={}
                for i=1,data.nSpawnPoints do data.Distribution[i]=(start+i-1)%data.nSpawnPoints+1 end
                data.LastSpawnTry=0
            end
            local result=pack(pcall(S.OriginalGenerator,group,...))
            for i=#pending.rows,1,-1 do local r=pending.rows[i];r[1][r[2]]=r[3] end
            if reorder then data.Distribution=distribution;data.LastSpawnTry=lastTry end
            S.Pending=previous
            if not result[1] then error(result[2],0) end
            return unpack(result,2,result.n)
        end
        EnemyGen.ActivateSpontaneousEnemy=S.Generator
    end
    if TravelBook and TravelBook.CharManager then
        local manager=TravelBook.CharManager
        if type(TravelBook.OnEnemyGroupActivated)=='function' then
            S.OriginalBestiaryGroup=TravelBook.OnEnemyGroupActivated
            S.BestiaryGroup=function(group,...)
                local enemies=NPC and NPC.Groups and NPC.Groups[group]
                -- Use the retail path when this group contains no randomized
                -- entity. This keeps every unrelated bestiary behavior intact.
                local randomized=false
                for _,enemy in pairs(enemies or {}) do
                    local kind=type(enemy)
                    if (kind=='table' or kind=='userdata') and S.BestiarySources[enemy] then randomized=true;break end
                end
                if not randomized then return S.OriginalBestiaryGroup(group,...) end
                -- Mirror the retail group's bValidBaseType filter, substituting
                -- the original controller only for entities we replaced.
                local seen={}
                for _,enemy in pairs(enemies or {}) do
                    local kind=type(enemy)
                    if (kind=='table' or kind=='userdata') and enemy.bValidBaseType then
                        local name=S.BestiarySources[enemy] or enemy.ActCtrl
                        if name and not seen[name] then
                            seen[name]=true;manager:NewChar(name)
                        end
                    end
                end
            end
            TravelBook.OnEnemyGroupActivated=S.BestiaryGroup
        end
        if type(manager.DecrementKillsPending)=='function' then
            S.OriginalBestiaryKill=manager.DecrementKillsPending
            S.BestiaryKill=function(self,name,...)
                -- Natural enemies are native to the current level. Therefore a
                -- foreign controller name here can only be one of our imports.
                -- Suppress its kill-threshold unlock before it can redirect the
                -- book to resources which this level cannot display.
                if S.Foreign and S.Foreign[name] then
                    S.BestiarySuppressed=S.BestiarySuppressed+1
                    return
                end
                return S.OriginalBestiaryKill(self,name,...)
            end
            manager.DecrementKillsPending=S.BestiaryKill
        end
    end
    -- Report initial entities created before the host could attach. Never
    -- recreate/delete those entities: named references and save state matter.
    for _,rows in pairs((MapEnemies and MapEnemies.Enemies) or {}) do
        local name=get(rows,'Name');local original=get(rows,'ActCtrl')
        if name and S.Allowed[original] and Game.GetEntity(name) then
            record('static:'..name,original,original,'created-before-hook')
        end
    end
    return true
end
function S.Stop()
    S.Enabled=false
    if NPC and NPC.CreateSingleEnemy==S.Single then NPC.CreateSingleEnemy=S.OriginalSingle end
    if NPC and NPC.CreateWithAI==S.Dynamic then NPC.CreateWithAI=S.OriginalDynamic end
    if EnemyGen and EnemyGen.ActivateSpontaneousEnemy==S.Generator then EnemyGen.ActivateSpontaneousEnemy=S.OriginalGenerator end
    if TravelBook and TravelBook.OnEnemyGroupActivated==S.BestiaryGroup then TravelBook.OnEnemyGroupActivated=S.OriginalBestiaryGroup end
    if TravelBook and TravelBook.CharManager and TravelBook.CharManager.DecrementKillsPending==S.BestiaryKill then
        TravelBook.CharManager.DecrementKillsPending=S.OriginalBestiaryKill
    end
end
