-- Read-only snapshot for a failed grab/use. Never execute the object's UseFunc,
-- grant gear, change selection, or start a finisher while diagnosing it.
local rows = {}
local function field(name, read)
    local ok, value = pcall(read)
    rows[#rows+1] = name .. '=' .. (ok and tostring(value) or 'unavailable')
end
field('level', function() return init.LevelName end)
field('chain tier (1 basic, 2 Hook Tip, 3 Spiked Chain)', function() return Belmont.ChainModelInUse.Value end)
field('player action', function() return player.Action end)
field('action priority', function() return player.oActCtrl.AnimPriority end)
field('selected name', function() return player.SelectedEntity end)
field('auto selected name', function() return player.AutoSelectedEntity end)
local selected = player and player.oSelectedEntity
if selected == nil and player and Game.GetEntity and type(player.SelectedEntity)=='string' and player.SelectedEntity~='' then
    local ok, entity=pcall(Game.GetEntity,player.SelectedEntity)
    if ok then selected=entity end
end
field('selected controller', function() return selected.ActCtrl end)
field('use function', function() return selected.UseFunc end)
field('can-use function', function() return selected.CanUseFunc end)
field('selected AI stun state', function() return selected.oAI.iCrazyState end)
field('selected shield catch allowed', function() return selected.oAI.bCanCatchForShield end)
local missing={}
for _,name in ipairs({'KeyPick','PickFood','PushGetKeyLeft','PushGetKeyRight',
    'WhipGhCatchInit','WhipVwCatchInit','WhipAaCatchShieldInit','WhipPullGenericInit'}) do
    local ok, present=pcall(function() return Act.GetClass('Belmont'):GetAct(name) end)
    if not ok or not present then missing[#missing+1]=name end
end
rows[#rows+1]='absent player actions (some are normally level-specific)='..table.concat(missing,', ')
Game.Set('InitLuaLine','--APINTERACTION|'..table.concat(rows,'\n'))
