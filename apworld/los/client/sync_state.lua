local ok = false
local detail = 'NO_MONITOR'
if APBridgeMonitor ~= nil then
    pcall(APBridgeMonitor.InstallStoryBlocker)
    local a, ar = pcall(APBridgeMonitor.SyncAbilities, __ABILITY_MASK__)
    local i, ir = pcall(APBridgeMonitor.SyncInventory, __INVENTORY_MASK__)
    local l, lr = pcall(APBridgeMonitor.SyncLevels, __LEVEL_LOW_MASK__, 1, 23, true, false)
    local h, hr = pcall(APBridgeMonitor.SyncLevels, __LEVEL_HIGH_MASK__, 24, 46, false, true)
    ok = a and ar == true and i and ir == true and l and lr == true and h and hr == true
    detail = tostring(a) .. ',' .. tostring(ar) .. ',' ..
        tostring(i) .. ',' .. tostring(ir) .. ',' ..
        tostring(l) .. ',' .. tostring(lr) .. ',' ..
        tostring(h) .. ',' .. tostring(hr)
end
Game.Set('InitLuaLine', ok and '--APSYNC|OK' or '--APSYNC|NOTREADY|' .. detail)
