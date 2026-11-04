local V = function(fn)
    local ok, value = pcall(fn)
    if ok then return tostring(value) end
    return "nil"
end

local TrialMask = function(first, last)
    local mask = 0
    if Trials == nil or Trials.Status == nil or
        SaveGame == nil or SaveGame.GameMaps == nil then
        return mask
    end
    for index = first, last do
        local levelName = SaveGame.GameMaps[index]
        if levelName ~= nil and
            Trials.Status[string.lower(tostring(levelName))] ~= nil then
            mask = mask + (2 ^ (index - first))
        end
    end
    return mask
end

Game.Set("InitLuaLine",
    "L=" .. V(function() return CollectableItems.gvLifeGems.Value end) ..
    "|G=" .. V(function() return CollectableItems.gvLightGems.Value end) ..
    "|K=" .. V(function() return CollectableItems.gvDarkGems.Value end) ..
    "|V=" .. V(function() return CollectableItems.gvVialUpgrades.Value end) ..
    "|D=" .. V(function() return CollectableItems.gvDaggerUpgrades.Value end) ..
    "|F=" .. V(function() return CollectableItems.gvFairyUpgrades.Value end) ..
    "|H=" .. V(function() return Belmont.ChainModelInUse.Value end) ..
    "|S=" .. V(function() return player.oActCtrl.oActClass.SprintOnDoubleTap end) ..
    "|B=" .. V(function() return DarkPower.DarkDashActive end) ..
    "|LC=" .. V(function() return LightPower.Power.Value end) ..
    "|LM=" .. V(function() return LightPower.PowerMax.Value end) ..
    "|LO=" .. V(function() return LightPower.PowerOn.Value end) ..
    "|DC=" .. V(function() return DarkPower.Power.Value end) ..
    "|DM=" .. V(function() return DarkPower.PowerMax.Value end) ..
    "|DO=" .. V(function() return DarkPower.PowerOn.Value end) ..
    "|CH=" .. V(function() return Chupacabra ~= nil and Chupacabra.HasPlayerPowers ~= nil and Chupacabra.HasPlayerPowers.Value == true end) ..
    "|MS=" .. V(function() return APBridgeMonitor ~= nil and APBridgeMonitor.MagicSuppressed ~= nil and APBridgeMonitor.MagicSuppressed() or false end) ..
    "|W=" .. V(function() return player.oActCtrl.oActClass.uData.bWings end) ..
    "|A=" .. V(function() return player.uData.bGauntlet end) ..
    "|FA=" .. V(function() return Belmont.FairiesActive.Value end) ..
    "|VA=" .. V(function() return Belmont.VialActive.Value end) ..
    "|CR=" .. V(function() return Belmont.CrystalActive.Value end) ..
    "|DA=" .. V(function() return Belmont.DaggersActive.Value end) ..
    "|DX=" .. V(function() return TravelBook.ActionsManager:GetActionStatus('SecondaryWeapon') end) ..
    "|DY=" .. V(function() return TravelBook.ActionsManager:GetActionStatus('Dagger') end) ..
    "|DZ=" .. V(function() return TravelBook.ActionsManager:GetActionStatus('ComboD') end) ..
    "|DT=" .. V(function() return APBridgeDaggers ~= nil and APBridgeDaggers.Enabled == true end) ..
    "|DW=" .. V(function() return APBridgeDaggers ~= nil and APBridgeDaggers.Owned == true end) ..
    "|DG=" .. V(function() return MapTutorials ~= nil and MapTutorials.DaggerTutorialCompleted == true end) ..
    "|DN=" .. V(function() return WeaponsDagger.Daggers.Value end) ..
    "|DMX=" .. V(function() return WeaponsDagger.GetMaxDaggers() end) ..
    "|ST=" .. V(function() if APBridgeStake ~= nil then return APBridgeStake.Owned == true end return TravelBook.IsStakeAvailable() end) ..
    "|AI=" .. V(function() return TravelBook.ActionsManager:GetActionIndex('Concentration') end) ..
    "|AS=" .. V(function() return TravelBook.ActionsManager:GetActionStatus('Concentration') end) ..
    "|AU=" .. V(function() return TravelBook.ActionsManager:IsUnlocked('Concentration') end) ..
    "|AF=" .. V(function() return Game.GVar('gvTBookActionsStatus').Value end) ..
    "|CM=" .. V(function() return Game.GVar('gvSkillMapStatus').Value end) ..
    "|TL=" .. V(function() return TrialMask(1, 23) end) ..
    "|TH=" .. V(function() return TrialMask(24, 46) end) ..
    "|TI=" .. V(function() return Trials ~= nil and Trials.isTrial == true end) ..
    "|TC=" .. V(function() return MapTrial ~= nil and MapTrial.Status or 'nil' end) ..
    "|VL=" .. V(function() return Game.GVar('VisitedLevels').Value end) ..
    "|AL=" .. V(function() if APBridgeMonitor ~= nil and APBridgeMonitor.AllowedLevelText ~= nil then return APBridgeMonitor.AllowedLevelText() end return '' end) ..
    "|LA=" .. V(function() return APBridgeLevelAccess ~= nil and APBridgeLevelAccess.Enabled == true end) ..
    "|PS=" .. V(function() return SaveGame.GetPlayerStatusString() end) ..
    "|HM=" .. V(function() return Act.GetClass('Belmont').Life end) ..
    "|DE=" .. V(function() return WeaponsDagger.DaggersExpansions end) ..
    "|VE=" .. V(function() return WeaponsVial.VialsExpansions end) ..
    "|FE=" .. V(function() return WeaponsFairy.FairiesExpansions end) ..
    "|SP=" .. V(function() return Team.GetSavedSpawnPlayerPoint() end) ..
    "|SR=" .. V(function() return Game.GetSaveVar(init.LevelName .. '.NivelCompletado') end) ..
    "|HE=" .. V(function() return APBridgeHook ~= nil and APBridgeHook.Enabled == true end) ..
    "|HF=" .. V(function() return APBridgeHook ~= nil and APBridgeHook.Blocked == true end) ..
    "|TE=" .. V(function() return APBridgeStake ~= nil and APBridgeStake.Enabled == true end) ..
    "|TF=" .. V(function() return APBridgeStake ~= nil and APBridgeStake.Blocked == true end) ..
    "|SE=" .. V(function() return APBridgeSpike ~= nil and APBridgeSpike.Enabled == true end) ..
    "|SF=" .. V(function() return APBridgeSpike ~= nil and APBridgeSpike.Blocked == true end) ..
    "|LE=" .. V(function() return APBridgeLightTutorial ~= nil and APBridgeLightTutorial.Enabled == true end) ..
    "|LF=" .. V(function() return APBridgeLightTutorial ~= nil and APBridgeLightTutorial.Blocked == true end) ..
    "|PX=" .. V(function() return APBridgeInventory ~= nil and APBridgeInventory.Enabled == true end) ..
    "|PT=" .. V(function() return APBridgeInventory ~= nil and APBridgeInventory.LastTrigger or 'none' end) ..
    "|IC=" .. V(function()
        if APBridgeInventory == nil then return '-1,-1,-1,-1,-1,-1' end
        return tostring(APBridgeInventory.LifeGems) .. ',' ..
            tostring(APBridgeInventory.LightGems) .. ',' ..
            tostring(APBridgeInventory.DarkGems) .. ',' ..
            tostring(APBridgeInventory.DaggerUpgrades) .. ',' ..
            tostring(APBridgeInventory.VialUpgrades) .. ',' ..
            tostring(APBridgeInventory.FairyUpgrades)
    end) ..
    "|ME=" .. V(function() return APBridgeMonitor ~= nil and APBridgeMonitor.Enabled == true end) ..
    "|PH=" .. V(function() return APBridgeHookUseGate ~= nil and APBridgeHookUseGate.Owned == true end) ..
    "|PW=" .. V(function() return Stamina ~= nil and Stamina.Enabled == true end) ..
    "|CG=false" ..
    "|N=" .. V(function() return init.LevelName end))
