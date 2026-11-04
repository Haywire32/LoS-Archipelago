-- Retail treats the last VisitedLevels entry as a first visit. That predicate
-- both selects the load-time trial/replay route and hides the map's right page.
-- AP authorization must decide this BEFORE loading, not by changing Trials.isTrial
-- after initialization. Saved completion, trial results and ownership stay intact.
APBridgeReplayAccess = APBridgeReplayAccess or {}
do
    local replay = APBridgeReplayAccess
    local function Key(name)
        return string.gsub(string.lower(tostring(name or '')), '^level%.', '')
    end

    replay.IsAuthorized = function(name)
        local key = Key(name)
        return replay.Enabled == true and replay.BaseLevels[key] == true and
            replay.Provider(key) == true
    end

    if replay.TrialFn == nil then
        replay.TrialFn = function(name, ...)
            if replay.Enabled == true and replay.BaseLevels[Key(name)] == true then
                return replay.IsAuthorized(name)
            end
            return replay.OriginalTrial(name, ...)
        end
    end

    replay.Ensure = function(provider)
        if SaveGame == nil or SaveGame.GameMaps == nil or
            type(SaveGame.isLevelTrial) ~= 'function' then return false end
        if provider ~= nil then replay.Provider = provider end
        if type(replay.Provider) ~= 'function' then return false end
        replay.BaseLevels = {}
        for index = 1, 46 do
            local name = SaveGame.GameMaps[index]
            if name ~= nil then replay.BaseLevels[Key(name)] = true end
        end
        if SaveGame.isLevelTrial ~= replay.TrialFn then
            replay.OriginalTrial = SaveGame.isLevelTrial
        end
        SaveGame.isLevelTrial = replay.TrialFn
        replay.Enabled = true
        return true
    end

    replay.Stop = function()
        replay.Enabled = false
        if SaveGame ~= nil and SaveGame.isLevelTrial == replay.TrialFn then
            SaveGame.isLevelTrial = replay.OriginalTrial
        end
    end
end
