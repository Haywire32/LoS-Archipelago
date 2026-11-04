local level = tostring(init ~= nil and (init.LevelName or init.level_name) or '')
if string.find(string.lower(level), 'menu', 1, true) == nil then
    Game.Set('InitLuaLine', '--APMENUSTART|NOTMENU|' .. level)
else
    local ok, detail = pcall(function()
        if SaveGame == nil or SaveGame.GameMaps == nil or
            SaveGame.IsLevelVisited == nil then error('SAVE_MENU_NOT_READY') end
        if MainMenu == nil or MainMenu.Play == nil or MainMenu.NewGame == nil then
            error('MAIN_MENU_CALLBACKS_NOT_READY')
        end
        if WorldMap == nil or WorldMap.LoadHistoricLevel == nil or
            WorldMap.HistoricMenu == nil then
            error('WORLD_MAP_MENU_NOT_READY')
        end
        local low = __LEVEL_LOW_MASK__
        local high = __LEVEL_HIGH_MASK__
        local function Has(value, bit)
            return math.floor(value / (2 ^ bit)) % 2 == 1
        end
        APMenuLevelAccess = APMenuLevelAccess or {Armed = false}
        APMenuLevelAccess.Allowed = {}
        for index = 1, 46 do
            local packed = index <= 23 and low or high
            local bit = index <= 23 and index - 1 or index - 24
            if Has(packed, bit) then
                local name = SaveGame.GameMaps[index]
                if name ~= nil then APMenuLevelAccess.Allowed[name] = true end
            end
        end
        if APMenuLevelAccess.WrappedIsLevelVisited == nil then
            APMenuLevelAccess.WrappedIsLevelVisited = function(levelName, ...)
                return APMenuLevelAccess.Allowed[tostring(levelName)] == true
            end
        end
        if APMenuLevelAccess.WrappedLoadHistoricLevel == nil then
            APMenuLevelAccess.WrappedLoadHistoricLevel = function(...)
                local wanted = tostring(WorldMap.LevelToBeLoaded or '')
                if APMenuLevelAccess.Allowed[wanted] ~= true then
                    APMenuLevelAccess.LastDenied = wanted
                    return
                end
                return APMenuLevelAccess.OriginalLoadHistoricLevel(...)
            end
        end
        if APMenuLevelAccess.WrappedMainMenuPlay == nil then
            APMenuLevelAccess.WrappedMainMenuPlay = function(...)
                APMenuLevelAccess.PlayCalls = (APMenuLevelAccess.PlayCalls or 0) + 1
                if SaveGame.ClearSaveMarker == nil or Game.SoftSaveConfig == nil then
                    error('CLEAR_MARKER_NOT_READY')
                end
                SaveGame.ClearSaveMarker()
                if tonumber(Game.Get('SaveSlotUsed')) ~= 0 then
                    error('SAVE_MARKER_DID_NOT_CLEAR')
                end
                Game.SoftSaveConfig()
                SaveGame.IsLevelVisited = APMenuLevelAccess.WrappedIsLevelVisited
                WorldMap.LoadHistoricLevel = APMenuLevelAccess.WrappedLoadHistoricLevel
                return APMenuLevelAccess.OriginalMainMenuPlay(...)
            end
        end
        if APMenuLevelAccess.WrappedMainMenuNewGame == nil then
            APMenuLevelAccess.WrappedMainMenuNewGame = function(...)
                APMenuLevelAccess.NewGameCalls = (APMenuLevelAccess.NewGameCalls or 0) + 1
                if SaveGame.NewLevelNow == nil or SaveGame.ClearSaveMarker == nil or
                    Game.SoftSaveConfig == nil then
                    error('NEW_GAME_REDIRECT_NOT_READY')
                end
                local requestedLevel = nil
                local retailNewLevelNow = SaveGame.NewLevelNow
                SaveGame.NewLevelNow = function(levelName, ...)
                    requestedLevel = tostring(levelName or '')
                end
                local called = {pcall(APMenuLevelAccess.OriginalMainMenuNewGame, ...)}
                SaveGame.NewLevelNow = retailNewLevelNow
                if not called[1] then error(called[2]) end
                if requestedLevel == nil or requestedLevel == '' then
                    error('NEW_GAME_FIRST_LEVEL_NOT_CAPTURED')
                end
                SaveGame.ClearSaveMarker()
                if tonumber(Game.Get('SaveSlotUsed')) ~= 0 then
                    error('NEW_GAME_SAVE_MARKER_DID_NOT_CLEAR')
                end
                Game.SoftSaveConfig()
                SaveGame.IsLevelVisited = APMenuLevelAccess.WrappedIsLevelVisited
                WorldMap.LoadHistoricLevel = APMenuLevelAccess.WrappedLoadHistoricLevel
                APMenuLevelAccess.NewGameFirstLevel = requestedLevel
                return WorldMap.HistoricMenu(nil, nil, false)
            end
        end
        if SaveGame.IsLevelVisited ~= APMenuLevelAccess.WrappedIsLevelVisited then
            APMenuLevelAccess.OriginalIsLevelVisited = SaveGame.IsLevelVisited
        end
        if WorldMap.LoadHistoricLevel ~= APMenuLevelAccess.WrappedLoadHistoricLevel then
            APMenuLevelAccess.OriginalLoadHistoricLevel = WorldMap.LoadHistoricLevel
        end
        if MainMenu.Play ~= APMenuLevelAccess.WrappedMainMenuPlay then
            APMenuLevelAccess.OriginalMainMenuPlay = MainMenu.Play
        end
        if MainMenu.NewGame ~= APMenuLevelAccess.WrappedMainMenuNewGame then
            APMenuLevelAccess.OriginalMainMenuNewGame = MainMenu.NewGame
        end
        if APMenuLevelAccess.OriginalIsLevelVisited == nil or
            APMenuLevelAccess.OriginalLoadHistoricLevel == nil or
            APMenuLevelAccess.OriginalMainMenuPlay == nil or
            APMenuLevelAccess.OriginalMainMenuNewGame == nil then
            error('MENU_ORIGINALS_MISSING')
        end
        SaveGame.IsLevelVisited = APMenuLevelAccess.WrappedIsLevelVisited
        WorldMap.LoadHistoricLevel = APMenuLevelAccess.WrappedLoadHistoricLevel
        MainMenu.Play = APMenuLevelAccess.WrappedMainMenuPlay
        MainMenu.NewGame = APMenuLevelAccess.WrappedMainMenuNewGame
        if not APBridgeReplayAccess.Ensure(function(name)
            return APMenuLevelAccess.Allowed[name] == true
        end) then error('REPLAY_ACCESS_NOT_READY') end
        APMenuLevelAccess.Armed = true
        local names = {}
        for index, name in ipairs(SaveGame.GameMaps) do
            if APMenuLevelAccess.Allowed[name] == true then table.insert(names, name) end
        end
        APMenuLevelAccess.VisibleText = table.concat(names, ',')
    end)
    Game.Set('InitLuaLine', ok and
        '--APMENUSTART|ARMED|' .. tostring(APMenuLevelAccess.VisibleText or '') or
        '--APMENUSTART|ERROR|' .. tostring(detail))
end
