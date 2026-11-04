if Game == nil or Game.Set == nil or WorldMap == nil or
    WorldMap.GetNumSkillsDone == nil or WorldMap.LoadMapRegion == nil or
    SaveGame == nil or SaveGame.GameMaps == nil then
    if Game ~= nil and Game.Set ~= nil then
        Game.Set('InitLuaLine', '--APMAPUI|NOTREADY|WORLD_MAP_UI_NOT_READY')
    end
else
local ok, detail = pcall(function()

    local low = __COMPLETION_LOW_MASK__
    local high = __COMPLETION_HIGH_MASK__
    local function Has(value, bit)
        return math.floor(value / (2 ^ bit)) % 2 == 1
    end

    APBridgeWorldMapUI = APBridgeWorldMapUI or {}
    local ui = APBridgeWorldMapUI
    ui.Completed = {}
    ui.CompletedCount = math.max(0, __COMPLETED_COUNT__)
    ui.RequiredCount = math.max(1, __REQUIRED_COUNT__)
    ui.CheckStates = {}
    local checkStates = '__CHECK_STATES__'
    for index = 1, 46 do
        local packed = index <= 23 and low or high
        local bit = index <= 23 and index - 1 or index - 24
        local name = SaveGame.GameMaps[index]
        if name ~= nil then
            ui.CheckStates[tostring(name)] = tonumber(string.sub(checkStates, index, index)) or 0
        end
        if Has(packed, bit) then
            local levelName = SaveGame.GameMaps[index]
            if levelName ~= nil then ui.Completed[tostring(levelName)] = true end
        end
    end

    -- Only recolor the three retail selection sprites. No completion,
    -- difficulty, loading, input or save predicates are changed here.
    ui.SelectionState = function(controlName)
        if Scorer == nil or Scorer.GetItem == nil then return 0 end
        local control = Scorer.GetItem(0, controlName)
        if control == nil or control.uData == nil then return 0 end
        local data = control.uData
        if not data.IsChapter then
            return ui.CheckStates[tostring(data.ChapterName)] or 0
        end
        local index = tonumber(string.sub(controlName, 13))
        local levels = SaveGame.GameChapters and SaveGame.GameChapters[index]
        if type(levels) ~= 'table' then return 0 end
        local result = 0
        for _, level in ipairs(levels) do
            local state = ui.CheckStates[tostring(level)] or 0
            -- Locked levels have state 0 and do not affect the chapter.
            if state == 1 then return 1 end
            if state == 2 then result = 2
            elseif state == 3 and result == 0 then result = 3 end
        end
        return result
    end
    ui.RestoreSelectionBlend = function()
        if Scorer == nil or Scorer.GetItem == nil then return end
        for name, mode in pairs(ui.NativeBlending or {}) do
            local item = Scorer.GetItem(0, name)
            if item ~= nil then item.BlendingMode = mode end
        end
    end
    ui.UpdateSelectionColor = function()
        if ui.SelectedControl == nil or Color == nil then return end
        local state = ui.SelectionState(ui.SelectedControl)
        local color = nil
        -- User-selected palette: green available, red blocked, blue cleared.
        -- Red uses the retail glow blend below: tinting alone leaves a black
        -- overlay in the circle/flame art. Preserve native shading underneath.
        if state == 1 then color = Color(64, 255, 64)
        -- The original flame is cyan: visible texels average R70/G198/B242.
        -- Normal red tint multiplies that weak red channel into near-black.
        -- A fourfold red multiplier lifts it before final screen saturation.
        -- Use the vector directly to preserve values above ordinary tint range.
        elseif state == 2 then color = V4D(1020, 24, 16, 255)
        elseif state == 3 then color = Color(100, 165, 255) end
        ui.RestoreSelectionBlend()
        for _, name in ipairs({'Orb', 'Effect', 'AnimatedFire'}) do
            local item = Scorer.GetItem(0, name)
            local native = ui.NativeColors and ui.NativeColors[name]
            if item ~= nil and (color ~= nil or native ~= nil) then
                item.Color = color or native
                if state == 2 and (name == 'Orb' or name == 'AnimatedFire') then
                    ui.NativeBlending = ui.NativeBlending or {}
                    if ui.NativeBlending[name] == nil then
                        ui.NativeBlending[name] = item.BlendingMode
                    end
                    -- Mode 2 is used by the retail map's Effect glow. Only
                    -- switch if we can restore the original mode afterwards.
                    if ui.NativeBlending[name] ~= nil then item.BlendingMode = 2 end
                end
            end
        end
    end
    if ui.WrappedRegionFocus == nil then
        ui.WrappedRegionFocus = function(id, controlName, ...)
            ui.RestoreSelectionBlend()
            local result = ui.OriginalRegionFocus(id, controlName, ...)
            ui.SelectedControl = controlName
            ui.NativeColors = {}
            for _, name in ipairs({'Orb', 'Effect', 'AnimatedFire'}) do
                local item = Scorer.GetItem(0, name)
                if item ~= nil then ui.NativeColors[name] = item.Color end
            end
            pcall(ui.UpdateSelectionColor)
            return result
        end
    end
    if type(WorldMap.OnRegionSpriteItemFocusGained) == 'function' then
        if WorldMap.OnRegionSpriteItemFocusGained ~= ui.WrappedRegionFocus then
            ui.OriginalRegionFocus = WorldMap.OnRegionSpriteItemFocusGained
        end
        WorldMap.OnRegionSpriteItemFocusGained = ui.WrappedRegionFocus
    end

    ui.UpdateCounter = function()
        if Scorer == nil or Scorer.GetItem == nil or Scorer.NewItem == nil or
            V2D == nil or V4D == nil then return false end
        -- ChapterPerc exists only on the retail World Map. Requiring it keeps
        -- this display from leaking into normal gameplay HUD screens.
        if Scorer.GetItem(0, 'ChapterPerc') == nil then return false end
        local item = Scorer.GetItem(0, 'APFinalFightCounter')
        if item == nil then
            item = Scorer.NewItem(0, 'APFinalFightCounter', 'Text', 1)
        end
        item.Font = 'HoratioSmall'
        item.Align = 'Center'
        item.Effect = 'Shadow'
        item.Text = tostring(math.min(ui.CompletedCount, ui.RequiredCount)) ..
            '/' .. tostring(ui.RequiredCount) .. ' levels until Final Fight'
        item.Color = V4D(200, 200, 150, 255)
        -- Upper-left page, away from the chapter and level markers on the
        -- right. This uses the same virtual coordinates as retail UI.
        item.Pos = V2D(170, 82)
        item.Visible = 1
        return true
    end

    if ui.WrappedGetNumSkillsDone == nil then
        ui.WrappedGetNumSkillsDone = function(levelName, ...)
            local original = ui.OriginalGetNumSkillsDone(levelName, ...)
            local numeric = tonumber(original) or 0
            if ui.Completed[tostring(levelName)] == true and numeric < 1 then
                return 1
            end
            return original
        end
    end
    if ui.WrappedLoadMapRegion == nil then
        ui.WrappedLoadMapRegion = function(...)
            ui.RestoreSelectionBlend()
            ui.NativeBlending = {}
            ui.SelectedControl = nil
            local result = ui.OriginalLoadMapRegion(...)
            pcall(ui.UpdateCounter)
            pcall(ui.UpdateSelectionColor)
            return result
        end
    end

    if WorldMap.GetNumSkillsDone ~= ui.WrappedGetNumSkillsDone then
        ui.OriginalGetNumSkillsDone = WorldMap.GetNumSkillsDone
    end
    if WorldMap.LoadMapRegion ~= ui.WrappedLoadMapRegion then
        ui.OriginalLoadMapRegion = WorldMap.LoadMapRegion
    end
    if ui.OriginalGetNumSkillsDone == nil or ui.OriginalLoadMapRegion == nil then
        error('WORLD_MAP_UI_ORIGINALS_MISSING')
    end
    WorldMap.GetNumSkillsDone = ui.WrappedGetNumSkillsDone
    WorldMap.LoadMapRegion = ui.WrappedLoadMapRegion
    pcall(ui.UpdateCounter)
    pcall(ui.UpdateSelectionColor)
end)
Game.Set('InitLuaLine', ok and '--APMAPUI|OK' or
    '--APMAPUI|ERROR|' .. tostring(detail))
end
