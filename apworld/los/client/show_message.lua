local message = __MESSAGE_LITERAL__
local mapOnly = __MAP_ONLY__
if Scorer == nil or Game == nil or Game.Set == nil then
    if Game ~= nil and Game.Set ~= nil then
        Game.Set('InitLuaLine', '--APMSG|NOTREADY|HUD_MESSAGE_NOT_READY')
    end
else
local ok, detail = pcall(function()
    local map = Scorer.GetItem and Scorer.GetItem(0, 'ChapterPerc')
    if message == '' then
        local toast = Scorer.GetItem and Scorer.GetItem(0, 'APRewardMessage')
        if toast then toast.Visible = 0 end
        return true
    end
    if map ~= nil and Scorer.NewItem and V2D and V4D then
        -- Re-resolve each time: retail destroys these items on page changes.
        local toast = Scorer.GetItem(0, 'APRewardMessage') or
            Scorer.NewItem(0, 'APRewardMessage', 'Text', 1)
        -- Native scorer properties are not guaranteed to be readable after
        -- assignment. In Proton, toast.Font returned nil here despite setting it.
        local font = 'HoratioSmall'
        toast.Font = font
        toast.Align = 'Center'
        toast.Effect = 'Shadow'
        toast.Text = message
        toast.Color = V4D(255, 225, 130, 255)
        toast.Pos = V2D(512, 55)
        local width = 800
        if Scorer.GetTextArea then
            local measured, area = pcall(Scorer.GetTextArea, font, message)
            if measured and type(area) == 'number' and area > 0 then width = area end
        end
        local scale = math.min(1, 800 / math.max(1, width))
        toast.Scale = V2D(scale, scale)
        toast.Visible = 1
        return true
    end
    if mapOnly or Scorer.SetMsgText == nil or Game.GetTime == nil then return false end
    -- Retail uses this same five-second, non-modal channel for ordinary gold
    -- gameplay messages. It does not pause input or start a pickup animation.
    Scorer.SetMsgText(message, Game.GetTime() + 5.0)
    return true
end)
Game.Set('InitLuaLine', ok and (detail and '--APMSG|OK' or
    '--APMSG|NOTREADY|HUD_MESSAGE_NOT_READY') or '--APMSG|ERROR|' .. tostring(detail))
end
