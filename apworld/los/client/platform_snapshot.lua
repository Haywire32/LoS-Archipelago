-- Read-only cross-check: never set level, save, ownership, or loading variables.
local out = {'--APPLATFORM'}
local function field(name, fn)
    local ok, value = pcall(fn)
    local text = ok and tostring(value) or 'unavailable'
    text = string.sub(string.gsub(text, '[|\r\n]', ' '), 1, 180)
    out[#out+1] = name .. '=' .. text
end
field('lua_level', function() return init.LevelName end)
field('lua_level_lower', function() return init.level_name end)
field('engine_path', function() return Game.GetLevelPath() end)
field('engine_menu', function() return Game.Get('isMainMenu') end)
field('game_time', function() return Game.GetTime() end)
field('player', function() return player.Name end)
field('menu_closed', function() return Game.GetMenu():IsClosed() end)
field('save_slot', function() return Game.Get('SaveSlotUsed') end)
field('play_wrapped', function() return APMenuLevelAccess ~= nil and MainMenu.Play == APMenuLevelAccess.WrappedMainMenuPlay end)
field('new_wrapped', function() return APMenuLevelAccess ~= nil and MainMenu.NewGame == APMenuLevelAccess.WrappedMainMenuNewGame end)
field('play_calls', function() return APMenuLevelAccess.PlayCalls or 0 end)
field('new_calls', function() return APMenuLevelAccess.NewGameCalls or 0 end)
field('new_game_target', function() return APMenuLevelAccess.NewGameFirstLevel end)
field('monitor', function() return APBridgeMonitor.Enabled end)
field('early_enemy', function() return APEnemyEarly.State end)
Game.Set('InitLuaLine', table.concat(out, '|'))
