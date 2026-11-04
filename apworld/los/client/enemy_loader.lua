-- Donor-aware successor to the successful six-enemy private loader.
APEnemyLoader={Bank={},NativePaths={},Definitions={},Loading={},Done={},Initialized={},Ready={},Failed={}}
local L=APEnemyLoader
local function key(path) return string.lower((path:gsub('\\','/'):gsub('%.lua$',''))) end
local function pack(...) return {n=select('#',...),...} end
local function cataloguedEvent(events,actor)
    if type(events)~='table' then return false end
    if events[actor]==true then return true end
    -- Installed sidecar configs serialize manifest event names as arrays,
    -- while the live client transfer uses a boolean lookup table.
    for _,name in pairs(events) do if name==actor then return true end end
    return false
end
function L.Load(path,name,initialize)
    if APEnemyTrace then APEnemyTrace('library',path) end
    local k=key(path);local hash=L.Paths[k]
    assert(not L.Loading[k],'Recursive dependency '..k)
    if L.Done[k] then assert(L.Done[k]==hash,'Conflicting donor script '..k) end
    if type(_G[name])=='table' then
        if L.Done[k] and initialize~=false and not L.Initialized[k] then
            L.Loading[k]=true
            assert(type(_G[name].main)=='function','No initializer '..name)
            _G[name].main();L.Initialized[k]=true;L.Loading[k]=nil
        end
        return true
    end
    -- Retail intentionally clears transient property/action libraries. A hash
    -- records provenance, not a permanently live library: reload cleared tables.
    L.Initialized[k]=nil
    -- Prefer the audited bytes even when the target's compiled bundle names
    -- this path. Do not send a supplied dependency back through native file IO.
    if not (hash and (L.Bank[hash] or L.ChunkProvider)) and L.NativePaths[k] then
        return L.NativePreload(path,name,initialize)
    end
    assert(hash and (L.Bank[hash] or L.ChunkProvider),'Missing catalogued bytes '..k)
    local chunk,why
    if L.Bank[hash] then chunk,why=loadstring(L.Bank[hash])
    else chunk,why=L.ChunkProvider(hash) end
    assert(chunk,why)
    L.Loading[k]=true;_G[name]={};chunk()
    if initialize~=false then
        assert(type(_G[name].main)=='function','No initializer '..name);_G[name].main()
        L.Initialized[k]=true
    end
    L.Done[k]=hash;L.Loading[k]=nil;return true
end
-- Restore missing enemy-specific player actions using the normal script APIs.
-- Never feed a loose LBT into Game.GetSingleTable/LoadPersistentEvents: that
-- experiment caused a native crash that Lua pcall cannot contain. The builder
-- decodes the audited event/track records offline into ordinary Lua tables.
function L.EnsureFinisher(enemyName,definition)
    local f=definition.finisher
    if not (f and f.lua_events) then return end
    local ac=assert(Act.GetClass('Belmont'),'Missing player class for finisher')
    local missing={};local count=0
    for _,name in ipairs(f.actions) do
        if not ac:GetAct(name) then
            assert(f.lua_events.actions[name],'Missing decoded finisher '..name)
            missing[name]=true;count=count+1
        end
    end
    if count==0 then return end -- authored maps retain their own actions/events
    if APEnemyTrace then APEnemyTrace('finisher-begin',enemyName) end
    local create=MakeChar.CreateEditableAction
    -- Retail libraries also configure existing actions. Suppress those entries
    -- so revisits/partially shared libraries cannot overwrite native behavior.
    MakeChar.CreateEditableAction=function(class,name,animation)
        assert(class==ac,'Unexpected finisher player class')
        if not missing[name] then return nil end
        return create(class,name,animation)
    end
    local ok,why=pcall(function()
        L.Load(f.script,f.library,false)
        assert(type(_G[f.library].main)=='function','Missing finisher initializer')
        _G[f.library].main()
    end)
    MakeChar.CreateEditableAction=create
    if not ok then error(why,0) end
    for _,name in ipairs(f.actions) do
        if missing[name] then
            local am=assert(ac:GetAct(name),'Finisher was not created '..name)
            local data=f.lua_events.actions[name]
            for _,row in ipairs(data.events) do
                local event=am:NewEvent(row[1]) -- retail seconds, not frames
                event.Name=row[2];event.Func=row[3];event.Discardable=row[4]
            end
            for _,row in ipairs(data.tracks) do
                local track=am.oTracks:Add(row[1])
                track.Info=row[2]
                if row[3]~='' then track.OnSwitch=row[3] end
                track.n=#row[4]
                for i,segment in ipairs(row[4]) do
                    local item=track[i]
                    item.Init=segment[1];item.bEmpty=segment[3];item.Info=segment[4]
                end
                track[#row[4]].End=row[4][#row[4]][2]
            end
            -- These actions are needed even though this enemy is absent from
            -- the map's authored roster. This changes no equipment ownership.
            am.uData.LoadWith=nil
        end
    end
    FXSoundTable=FXSoundTable or {};FXSoundTable.Belmont=FXSoundTable.Belmont or {}
    for name,data in pairs(f.lua_events.fx) do
        if FXSoundTable.Belmont[name]==nil then FXSoundTable.Belmont[name]=data end
    end
    if APEnemyTrace then APEnemyTrace('finisher-ready',enemyName..':'..count) end
end
function APEnemyEnsure(name)
    if L.Ready[name] then return true end
    if L.Fault then return false,L.Fault end
    if L.Failed[name] then return false,L.Failed[name] end
    local definition=L.Definitions[name]
    if not definition then return false,'unknown-controller' end
    local preload,valid,events,levelpath=Game.PreloadLibrary,ValidPreloadLibrary,MakeChar.LoadEvents,Game.GetLevelPath
    L.NativePreload=preload;L.Paths=definition.scripts
    local function guarded(path,library,initialize)
        local k=key(path)
        assert(L.Paths[k] or L.NativePaths[k],'Uncatalogued dependency '..k)
        return L.Load(path,library,initialize)
    end
    Game.PreloadLibrary=guarded
    ValidPreloadLibrary=function(path,library,initialize)
        local k=key(path)
        if not L.Paths[k] and not L.NativePaths[k] then return false end
        return L.Load(path,library,initialize)
    end
    MakeChar.LoadEvents=function(ac)
        if APEnemyTrace then APEnemyTrace('events-begin',ac.Name) end
        -- Route ANY imported character using its own verified event donor.
        local previous=Game.GetLevelPath
        local previousLevelFile=init and init.LevelFile
        local actor=string.lower(ac.Name)
        if not L.NativePaths['scripts/chars/'..actor] then
            -- Nested body-part/summoned controllers use the SAME donor bundle
            -- currently being imported. Never pass an unverified event path
            -- into the native loader (missing LBTs crashed the earlier pilot).
            assert(cataloguedEvent(definition.events,actor), 'Uncatalogued character events '..actor)
            Game.GetLevelPath=function() return definition.donor end
            -- Retail LoadEvents first calls LoadSpecificCharFiles, which uses
            -- init.LevelFile (not GetLevelPath). Both must refer to the donor:
            -- its event LBT can contain actions added by that specific script.
            -- E.g. LycGreat__2_4_labyrinth_entrance creates CinematicFake;
            -- loading its events without that action crashes the native reader.
            if init then init.LevelFile=definition.donor end
        end
        local result=pack(pcall(function()
            local target=Game.GetLevelPath()..'/Scripts/Char_'..ac.Name..'.lbt'
            if APEnemyTrace then APEnemyTrace('event-file',target) end
            if Game.FileExist then assert(Game.FileExist(target),'Missing character events '..target) end
            return events(ac)
        end));Game.GetLevelPath=previous
        if init then init.LevelFile=previousLevelFile end
        if not result[1] then error(result[2],0) end
        if APEnemyTrace then APEnemyTrace('events-ready',ac.Name) end
        return unpack(result,2,result.n)
    end
    local ok,why=pcall(function()
        L.Load('scripts/chars/'..string.lower(name)..'.lua',name,true)
        if name=='Scarecrow' and not L.NativePaths['scripts/chars/scarecrow'] then
            Act.GetClass(name).bShowLifeBar=true
        end
        L.Load('scripts/ai/ai'..string.lower(name)..'.lua','AI'..name,true)
        for _,d in ipairs({{'scripts/config/aibehavparamseditor/aiparams','AIParams'},
                          {'scripts/config/aigroupbehav/aigroupbehav','AIGroupBehav'}}) do
            local path=d[1]..string.lower(name)
            if L.Paths[path] or L.NativePaths[path] then L.Load(path..'.lua',d[2]..name,true) end
        end
        L.EnsureFinisher(name,definition)
    end)
    Game.PreloadLibrary=preload;ValidPreloadLibrary=valid
    MakeChar.LoadEvents=events;Game.GetLevelPath=levelpath
    if not ok then
        L.Failed[name]=tostring(why)
        -- Partial native initialization is not rollback-safe. Freeze further
        -- imports for this level, keep original spawns, and report the fault.
        L.Fault=tostring(why);return false,why
    end
    L.Ready[name]=true;return true
end
