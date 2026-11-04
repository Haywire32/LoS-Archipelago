local ok = true
local detail = 'OK'

local function APDoRewards()
    local magicAllowed = APBridgeMonitor == nil or
        APBridgeMonitor.MagicSuppressed == nil or
        not APBridgeMonitor.MagicSuppressed()

    if __EXPERIENCE__ > 0 then
        local points = nil
        if Experience ~= nil then points = Experience.EPoints end
        if points == nil and Game ~= nil and Game.GVar ~= nil then
            points = Game.GVar('gvExperience')
        end
        if points == nil then return false, 'EXPERIENCE' end
        local before = tonumber(points.Value) or 0
        local target = before + __EXPERIENCE__
        points.Value = target
        if tonumber(points.Value) ~= target then
            return false, 'EXPERIENCE_VERIFY'
        end
        if Game ~= nil and Game.Get ~= nil and Game.Set ~= nil then
            local total = tonumber(Game.Get('gvTotalExperience')) or 0
            Game.Set('gvTotalExperience', total + __EXPERIENCE__)
        end
        if Experience ~= nil and Experience.UnlockExperienceAchievements ~= nil then
            Experience.UnlockExperienceAchievements()
        end
    end

    if __REFILL__ > 0 then
        if magicAllowed and LightPower ~= nil and LightPower.PowerOn ~= nil and
            LightPower.PowerOn.Value == true and LightPower.Power ~= nil and
            LightPower.PowerMax ~= nil and
            (tonumber(LightPower.Power.Value) or 0) < (tonumber(LightPower.PowerMax.Value) or 0) then
            LightPower.Power.Value = LightPower.PowerMax.Value
        end
        if magicAllowed and DarkPower ~= nil and DarkPower.PowerOn ~= nil and
            DarkPower.PowerOn.Value == true and DarkPower.Power ~= nil and
            DarkPower.PowerMax ~= nil and
            (tonumber(DarkPower.Power.Value) or 0) < (tonumber(DarkPower.PowerMax.Value) or 0) then
            DarkPower.Power.Value = DarkPower.PowerMax.Value
        end
    end

    if (__REFILL__ > 0 or __DAGGER__ > 0) and APBridgeDaggers ~= nil and
        APBridgeDaggers.Owned == true and WeaponsDagger ~= nil and
        WeaponsDagger.Daggers ~= nil and WeaponsDagger.GetMaxDaggers ~= nil then
        WeaponsDagger.Daggers.Value = WeaponsDagger.GetMaxDaggers()
    end
    if (__REFILL__ > 0 or __VIAL__ > 0) and Belmont ~= nil and
        Belmont.VialActive ~= nil and Belmont.VialActive.Value == true and
        WeaponsVial ~= nil and WeaponsVial.Vials ~= nil and
        WeaponsVial.GetMaxVials ~= nil then
        WeaponsVial.Vials.Value = WeaponsVial.GetMaxVials()
    end
    if (__REFILL__ > 0 or __FAIRY__ > 0) and Belmont ~= nil and
        Belmont.FairiesActive ~= nil and Belmont.FairiesActive.Value == true then
        if WeaponsFairy == nil or WeaponsFairy.Fairies == nil or
            WeaponsFairy.GetMaxFairies == nil or WeaponsFairy.Inc == nil or
            player == nil or player.oAI == nil or player.oAI.NumFairies == nil then
            return false, 'FAIRY_NOT_READY'
        end
        local fairyMax = tonumber(WeaponsFairy.GetMaxFairies())
        local fairyBefore = tonumber(player.oAI:NumFairies())
        if fairyMax == nil or fairyBefore == nil then return false, 'FAIRY_COUNT' end
        if fairyBefore < fairyMax then WeaponsFairy.Inc('Belmont', -1) end
        local fairyAfter = tonumber(player.oAI:NumFairies())
        if fairyAfter == nil or fairyAfter < fairyMax then
            return false, 'FAIRY_VERIFY'
        end
        WeaponsFairy.Fairies.Value = fairyAfter
    end
    if (__REFILL__ > 0 or __CRYSTAL__ > 0) and Belmont ~= nil and
        Belmont.CrystalActive ~= nil and Belmont.CrystalActive.Value == true and
        WeaponsCrystal ~= nil and WeaponsCrystal.CrystalPieces ~= nil and
        WeaponsCrystal.InitialUses ~= nil and WeaponsCrystal.Inc ~= nil then
        -- Retail SaveGame serializes CrystalPieces as the sixth consumable
        -- field. Four pieces are one usable Dark Crystal. Filling the separate
        -- ScorerCrystalEnergy meter did not create a crystal and was discarded
        -- on the next level load.
        local crystalBefore = tonumber(WeaponsCrystal.CrystalPieces.Value)
        local crystalMax = tonumber(WeaponsCrystal.InitialUses)
        if crystalBefore == nil or crystalMax == nil then
            return false, 'CRYSTAL_COUNT'
        end
        if crystalBefore < crystalMax then WeaponsCrystal.Inc('Belmont', -1) end
        local crystalAfter = tonumber(WeaponsCrystal.CrystalPieces.Value)
        if crystalAfter == nil or crystalAfter < crystalMax then
            return false, 'CRYSTAL_VERIFY'
        end
    end
    return true, 'OK'
end

ok, detail = APDoRewards()
Game.Set('InitLuaLine', ok and '--APREWARD|OK' or
    '--APREWARD|NOTREADY|' .. tostring(detail))
