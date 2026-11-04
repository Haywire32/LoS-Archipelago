-- Executed by the preserving NPC archive wrapper during level loading.
-- The sidecar and seed plan are fully staged BEFORE starting the game.
local root=assert(APEnemyRoot)
local function read(name) return assert(loadfile(root..'/'..name))() end
local active=read('active.lua')
if not active.enabled then return end
assert(active.version==7 and type(active.seed)=='string','Enemy plan version/seed mismatch')
local level=tostring(init.LevelName):gsub('^level%.','')
local plan=active.levels and active.levels[level]
-- The retail pause book is a separate level. Shared character libraries can be
-- requested again while that level is coming up, but it intentionally has no
-- enemy plan. Treating that normal transition as a broken seed aborts the menu
-- loader and leaves the game hung on Backspace.
if not plan or plan.passthrough then
    local reason=plan and 'retail-only' or 'no-plan'
    APEnemyEarly={Version=7,Seed=active.seed,Level=level,State='inactive',Reason=reason}
    if io and io.open then
        pcall(function()
            local f=io.open(root..'/loading.log','a')
            if f then f:write(level..'|'..active.seed..'|inactive:'..reason..'\n');f:close() end
        end)
    end
    return
end
APEnemyEarly={Version=7,Seed=active.seed,Level=level,State='armed'}
local E=APEnemyEarly
-- Flush each boundary independently so native faults leave useful evidence.
function APEnemyTrace(stage,detail)
    E.LastStage=stage..':'..tostring(detail or '')
    if io and io.open then
        pcall(function()
            local f=io.open(root..'/loading.log','a')
            if f then f:write(level..'|'..active.seed..'|'..E.LastStage..'\n');f:close() end
        end)
    end
end
APEnemyTrace('armed')
local originalLoad=assert(init.LoadChar)
local originalMap=assert(NPC.CreateMapEnemies)
local originalCommon
local commonWrapper
local function prepare()
    if E.State=='ready' then return end
    assert(E.State=='armed','Enemy early preparation previously failed')
    E.State='preparing'
    read('enemy_loader.lua')
    local config=read('levels/'..level..'.lua')
    APEnemyLoader.Definitions=config.enemies
    APEnemyLoader.NativePaths=config.native
    APEnemyLoader.ChunkProvider=function(hash) return loadfile(root..'/chunks/'..hash..'.luac') end
    read('enemy_floor.lua');read('enemy_runtime.lua')
    APEnemyShuffle.Configure(active.seed,level,active.pool,config.enemies,config.protected,plan)
    -- All original character initializers finish first. Imported classes must
    -- not run inside the first native character's initialization sequence.
    -- Still before CommonAIBehav.main, graphs, and every map enemy creation.
    for _,name in ipairs(plan.roster) do
        APEnemyTrace('prepare',name)
        local ok,why=APEnemyEnsure(name)
        assert(ok,'Enemy dependency '..name..': '..tostring(why))
        APEnemyTrace('prepared',name)
    end
    -- Preload death/gore assets for imported actors without permanently adding
    -- them to init.Enemies. Keep the authored roster available to other retail
    -- systems; the confirmed Backspace hang was an unrelated skill-hook cycle.
    -- Supply one expanded copy to
    -- the single retail preload call, then restore the native function before
    -- it executes so no wrapper survives into gameplay or menu transitions.
    if type(init.Enemies)=='table' and type(NPC.PreloadBoomPieces)=='function' then
        local present={};E.BoomList={}
        for _,name in ipairs(init.Enemies) do E.BoomList[#E.BoomList+1]=name;present[name]=true end
        for _,name in ipairs(plan.roster) do
            if not present[name] then E.BoomList[#E.BoomList+1]=name;present[name]=true end
        end
        E.OriginalBoomPieces=NPC.PreloadBoomPieces
        E.BoomPieces=function(names,...)
            NPC.PreloadBoomPieces=E.OriginalBoomPieces
            return E.OriginalBoomPieces(E.BoomList,...)
        end
        NPC.PreloadBoomPieces=E.BoomPieces
    end
    APEnemyShuffle.Early=true
    assert(APEnemyShuffle.Install())
    E.State='ready'
    APEnemyTrace('ready')
end
init.LoadChar=function(...)
    local result={originalLoad(...)}
    if not commonWrapper then
        originalCommon=assert(CommonAIBehav and CommonAIBehav.main,'Missing common AI boundary')
        commonWrapper=function(...)
            local ok,why=pcall(prepare)
            if not ok then
                E.State='error';E.Error=tostring(why);APEnemyTrace('error',why);error(why,0)
            end
            CommonAIBehav.main=originalCommon
            init.LoadChar=originalLoad
            return originalCommon(...)
        end
        CommonAIBehav.main=commonWrapper
        APEnemyTrace('waiting-for-native-characters')
    end
    return unpack(result)
end
NPC.CreateMapEnemies=function(...)
    APEnemyTrace('map-begin')
    -- Loading characters and graphs must have happened first. Never silently
    -- substitute the old asynchronous client path if this contract changes.
    assert(E.State=='ready','Enemy loader did not prepare before map creation')
    local ok,why=pcall(originalMap,...)
    if not ok then E.State='error';E.Error=tostring(why);error(why,0) end
    APEnemyShuffle.MapCreated=true;E.State='map-created'
    APEnemyTrace('map-created')
    init.LoadChar=originalLoad
    if E.OriginalBoomPieces and NPC.PreloadBoomPieces==E.BoomPieces then
        NPC.PreloadBoomPieces=E.OriginalBoomPieces
    end
end
