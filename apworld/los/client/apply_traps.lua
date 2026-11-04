local ok = true
local detail = 'OK'

local function APApplyTraps()
    if __MAGIC_DRAIN__ > 0 then
        if APBridgeMonitor ~= nil and APBridgeMonitor.MagicSuppressed ~= nil and
            APBridgeMonitor.MagicSuppressed() then
            return false, 'MAGIC_SUPPRESSED'
        end
        if LightPower == nil or LightPower.Power == nil or LightPower.PowerOn == nil or
            DarkPower == nil or DarkPower.Power == nil or DarkPower.PowerOn == nil then
            return false, 'MAGIC_NOT_READY'
        end
    end

    local poisonWasBlockedByLight = false
    if __POISON__ > 0 then
        if Belmont == nil or Belmont.BeginSpiderPoison == nil or Game == nil or
            Game.Get == nil or player == nil or player.Life == nil then
            return false, 'POISON_NOT_READY'
        end
        if (tonumber(player.Life) or 0) <= 0 then
            return false, 'PLAYER_DEAD'
        end
        if (tonumber(Game.Get('BelmontPoisonedTimeLeft')) or 0) > 0 then
            return false, 'POISON_ACTIVE'
        end
        poisonWasBlockedByLight = LightPower ~= nil and LightPower.PowerUse ~= nil and
            tonumber(LightPower.PowerUse.Value) == 1
    end

    if __MAGIC_DRAIN__ > 0 then
        if LightPower.PowerOn.Value == true then LightPower.Power.Value = 0 end
        if DarkPower.PowerOn.Value == true then DarkPower.Power.Value = 0 end
    end

    if __POISON__ > 0 then
        -- This is the common retail effect used by Spider Giant poison. It
        -- owns the pink life bar, timed damage, expiry, and Light Magic cure.
        Belmont.BeginSpiderPoison()
        if not poisonWasBlockedByLight and
            (tonumber(Game.Get('BelmontPoisonedTimeLeft')) or 0) <= 0 then
            return false, 'POISON_VERIFY'
        end
    end

    return true, 'OK'
end

ok, detail = APApplyTraps()
Game.Set('InitLuaLine', ok and '--APTRAP|OK' or
    '--APTRAP|NOTREADY|' .. tostring(detail))
