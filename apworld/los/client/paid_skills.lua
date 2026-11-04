-- Private paid-skill prototype. In-memory state only: never add save GVars.
-- No automatic installation. The existing client must own all bridge traffic.
-- Host protocol: Sync -> request in menu -> durable prepare -> Commit -> durable
-- completion -> AP location send. A runtime loss during prepare is ambiguous.
if APPaidSkills then return end
local S = {Version=3, Ready=false, Checked={}, Owned={}, Relics={}, Receipts={}}
local defs = {
["LightFlash"]={combo="BlockSyncBlind",price=1500,skills={},relics={"Light Magic"}},
["DaggerWave"]={combo="MultipleDaggers",price=400,skills={},relics={}},
["FlapWindWave"]={combo="WhipBlockComboUppercutJ",price=3500,skills={},relics={"Dark Gauntlet","Seraph Shoulders"}},
["SomersaultStrike"]={combo="WhipBlockSommerJumpDDD",price=3000,skills={},relics={"Cyclone Boots","Dark Gauntlet"}},
["ShadowFlames"]={combo="WhipComboADDrh",price=3000,skills={},relics={"Shadow Magic"}},
["HolyCross"]={combo="WhipComboADLMh",price=6000,skills={},relics={"Light Magic"}},
["FlapWhirlwind"]={combo="WhipComboAJJ",price=3500,skills={},relics={"Seraph Shoulders"}},
["ComboChainBarrier"]={combo="WhipComboAh",price=800,skills={},relics={}},
["ComboChainBarrier_Upgrade"]={combo="WhipComboAhA",price=1500,skills={"ComboChainBarrier"},relics={}},
["CircularChain"]={combo="WhipComboDAA",price=1000,skills={},relics={}},
["ChainSaw"]={combo="WhipComboDAD",price=2000,skills={"CircularChain"},relics={}},
["ExplodingQuake"]={combo="WhipComboDADrh",price=6000,skills={"CircularChain"},relics={"Shadow Magic"}},
["ErosiveChains"]={combo="WhipComboDALMh",price=3000,skills={"CircularChain"},relics={"Light Magic"}},
["UpwardGuillotine"]={combo="WhipComboDJJ",price=3500,skills={},relics={"Seraph Shoulders"}},
["ComboDHeavy"]={combo="WhipComboDrD",price=800,skills={},relics={}},
["ComboDHeavy_Upgrade"]={combo="WhipComboDrDrDrD",price=1500,skills={"ComboDHeavy"},relics={}},
["ComboDHeavy_Upgrade_Upgrade"]={combo="WhipComboDrDrDrDrD",price=2000,skills={"ComboDHeavy_Upgrade"},relics={}},
["DarkFocusMode"]={combo="WhipComboDrMh",price=25000,skills={"ShadowFlames","ExplodingQuake"},relics={"Shadow Magic"}},
["LightFocusMode"]={combo="WhipComboLMh",price=25000,skills={"HolyCross","ErosiveChains"},relics={"Light Magic"}},
["AvalanchePunch"]={combo="WhipFallBlockComboAh",price=2500,skills={},relics={"Dark Gauntlet"}},
["LandslidePunch"]={combo="WhipFallBlockComboDh",price=2500,skills={},relics={"Dark Gauntlet"}},
["SpinningChain"]={combo="WhipFallComboAh",price=150,skills={},relics={}},
["GroundCutter"]={combo="WhipFallComboDDhD",price=2000,skills={},relics={}},
["Guillotine"]={combo="WhipFallComboDh",price=25,skills={},relics={}},
["Guillotine_Upgrade"]={combo="WhipFallComboDhD",price=1500,skills={"Guillotine"},relics={}},
["DownwardKick"]={combo="WhipFallComboGripBig",price=200,skills={},relics={"Hook Tip"}},
["AirGrab"]={combo="WhipFallComboGripSmall",price=200,skills={},relics={"Hook Tip"}},
["DownwardPunch"]={combo="WhipFallComboGripSmallDown",price=300,skills={"AirGrab"},relics={"Hook Tip"}},
["SprintThrust"]={combo="WhipSprintComboAD",price=1000,skills={},relics={"Cyclone Boots"}},
["FlameClaws"]={combo="WhipSprintComboDDark",price=3500,skills={},relics={"Cyclone Boots","Shadow Magic","Dark Gauntlet"}},
["CounterstrikeA"]={combo="WhipSyncComboAAA",price=600,skills={},relics={}}
}
local byCombo={}
for action,d in pairs(defs) do byCombo[d.combo]=action end
assert(Experience and Experience.CombatScrolls and Experience.CombatScrollActive)
assert(TravelBook and TravelBook.ActionsManager and TravelBook.SetupBuyDialog)
local E,M,T=Experience,TravelBook.ActionsManager,TravelBook
for action,d in pairs(defs) do
    local retail=E.CombatScrolls[d.combo]
    assert(retail and retail.Price==d.price, 'paid skill price mismatch: '..action)
    assert(M:GetActionAnimName(action)==d.combo, 'paid skill mapping mismatch: '..action)
end
local oldBuy,oldBought,oldCan,oldAction=E.BuyCombo,M.IsBought,M.CanBeBought,M.BuyAction
local oldSetup,oldAccept=T.SetupBuyDialog,T.BuyAction
local hookedBuy,hookedBought,hookedCan,hookedAction,hookedSetup,hookedAccept

function S.Healthy()
    return Experience==E and TravelBook==T and T.ActionsManager==M
        and E.BuyCombo==hookedBuy and M.IsBought==hookedBought
        and M.CanBeBought==hookedCan and M.BuyAction==hookedAction
        and T.SetupBuyDialog==hookedSetup and T.BuyAction==hookedAccept
end

function S.Requirements(action)
    local d=defs[action]; if not d then return false end
    -- Shop predecessors are not additional received-item requirements.
    -- Retain inherited equipment requirements for every received move.
    for _,parent in ipairs(d.skills) do
        if not S.Requirements(parent) then return false end
    end
    for _,relic in ipairs(d.relics) do if not S.Relics[relic] then return false end end
    return true
end
function S.PurchaseRequirements(action)
    local d=defs[action]; if not d then return false end
    for _,parent in ipairs(d.skills) do if not S.Checked[parent] then return false end end
    for _,relic in ipairs(d.relics) do if not S.Relics[relic] then return false end end
    return true
end
function S.CanBuy(action)
    return S.Ready and not S.Pending and not S.Checked[action]
        and S.PurchaseRequirements(action) and E.EPoints.Value>=defs[action].price
end
function S.Sync(session, runtime, checked, owned, relics, ready)
    assert(S.Healthy(), 'paid skill hooks replaced; reload required')
    assert(type(session)=='string' and #session>0 and type(runtime)=='string' and #runtime>0)
    assert(not S.Session or S.Session==session, 'session switch requires fresh game runtime')
    assert(not S.Runtime or S.Runtime==runtime, 'runtime identity mismatch')
    S.Session,S.Runtime=session,runtime
    -- Runtime receipts remain authoritative until the host journals them.
    for action in pairs(defs) do
        S.Checked[action]=checked[action]==true or S.Checked[action]==true
        S.Owned[action]=owned[action]==true
    end
    S.Relics=relics
    S.Ready=ready==true
    local entryMoves={ComboChainBarrier_Upgrade='ComboChainBarrier',
        ComboDHeavy_Upgrade='ComboDHeavy',
        ComboDHeavy_Upgrade_Upgrade='ComboDHeavy_Upgrade',
        Guillotine_Upgrade='Guillotine',DownwardPunch='AirGrab',
        -- Retail reaches Exploding Quake through the Chain Saw entry, which
        -- itself passes the Circular Chain scroll filter. Owning only the final
        -- scroll otherwise displays Ready but leaves the input route blocked.
        ExplodingQuake='ChainSaw',ChainSaw='CircularChain',ErosiveChains='CircularChain'}
    S.Active={}
    local function activate(action)
        if S.Active[action] then return end
        S.Active[action]=true
        if entryMoves[action] then activate(entryMoves[action]) end
    end
    for action in pairs(defs) do
        if S.Owned[action] and S.Requirements(action) then activate(action) end
    end
    for action,d in pairs(defs) do E.CombatScrollActive[d.combo]=S.Active[action] or nil end
end
function S.Request(action)
    if not defs[action] or not S.CanBuy(action) then return false end
    S.Pending=action
    return true
end
function S.Commit(session,runtime,transaction,action)
    assert(S.Healthy(), 'paid skill hooks replaced; purchase paused')
    assert(session==S.Session and runtime==S.Runtime, 'stale paid skill transaction')
    assert(type(transaction)=='string' and #transaction>0)
    if S.Receipts[transaction] then
        assert(S.Receipts[transaction].action==action, 'transaction reused')
        return S.Receipts[transaction].result
    end
    local d=defs[action]
    local result='rejected'
    if d and S.Pending==action and S.Ready and not S.Checked[action]
        and S.PurchaseRequirements(action) and E.EPoints.Value>=d.price then
        -- Do not call retail BuyCombo: it immediately grants/persists the move.
        E.EPoints.Value=E.EPoints.Value-d.price
        S.Checked[action]=true
        result='paid'
    end
    S.Receipts[transaction]={action=action,result=result}
    S.Pending=nil
    return result
end
function S.Status(action)
    local check=S.Checked[action] and 'Bought' or (S.Pending==action and 'Pending' or 'Unbought')
    local move='Locked'
    if S.Owned[action] then move=S.Requirements(action) and 'Owned' or 'Owned (needs prerequisite)' end
    return 'CHECK: '..check..' | MOVE: '..move
end
E.BuyCombo=function(combo,...)
    local action=byCombo[combo]
    if action then return S.Request(action) end
    return oldBuy(combo,...)
end
M.IsBought=function(self,action,...)
    if defs[action] then return S.Checked[action]==true end
    return oldBought(self,action,...)
end
M.CanBeBought=function(self,action,...)
    if defs[action] then return S.CanBuy(action) and true or false end
    return oldCan(self,action,...)
end
M.BuyAction=function(self,action,...)
    if defs[action] then return S.Request(action) end
    return oldAction(self,action,...)
end
T.SetupBuyDialog=function(...)
    oldSetup(...)
    local action=T.CurrentActionName
    if defs[action] then
        local text=T.GetItem('ActionBoughtText')
        text.Text=S.Status(action); text.Visible=1
        -- Layout/overlap and localization still require a live UI pass.
        local button=T.GetItem('ActionAcceptButton')
        button.Text='Buy check'; button.Visible=S.CanBuy(action) and 1 or 0
        for _,name in ipairs({'ActionAvailableCash','ActionAvailableCashHeader',
            'ActionPrice','ActionBuyDialogCurrencyIcon1','ActionBuyDialogCurrencyIcon2'}) do
            T.GetItem(name).Visible=S.Checked[action] and 0 or 1
        end
    end
end
T.BuyAction=function(...)
    if not defs[T.CurrentActionName] then return oldAccept(...) end
    -- Retail callback announces success unconditionally; never use it for pending checks.
    S.Request(T.CurrentActionName)
    T.SetupBuyDialog()
end
hookedBuy,hookedBought,hookedCan,hookedAction=E.BuyCombo,M.IsBought,M.CanBeBought,M.BuyAction
hookedSetup,hookedAccept=T.SetupBuyDialog,T.BuyAction
S.Definitions=defs
S.Labels={["LightFlash"]="Light Flash",["DaggerWave"]="Dagger Wave",["FlapWindWave"]="Flapping Wind",["SomersaultStrike"]="Somersault Strike",["ShadowFlames"]="Shadow Flames",["HolyCross"]="Holy Cross",["FlapWhirlwind"]="Flapping Whirlwind",["ComboChainBarrier"]="Chain Barrier",["ComboChainBarrier_Upgrade"]="Chain Barrier Upgrade",["CircularChain"]="Circular Chain",["ChainSaw"]="Chain Saw",["ExplodingQuake"]="Exploding Quake",["ErosiveChains"]="Erosive Chains",["UpwardGuillotine"]="Upward Guillotine",["ComboDHeavy"]="Direct Heavy Combo",["ComboDHeavy_Upgrade"]="Direct Heavy Combo Upgrade",["ComboDHeavy_Upgrade_Upgrade"]="Direct Heavy Combo Upgrade 2",["DarkFocusMode"]="Ultimate Shadow",["LightFocusMode"]="Ultimate Light",["AvalanchePunch"]="Avalanche Punch",["LandslidePunch"]="Landslide Punch",["SpinningChain"]="Spinning Chain",["GroundCutter"]="Ground Cutter",["Guillotine"]="Guillotine",["Guillotine_Upgrade"]="Guillotine Upgrade",["DownwardKick"]="Downward Kick",["AirGrab"]="Air Grab",["DownwardPunch"]="Downward Punch",["SprintThrust"]="Sprint Thrust",["FlameClaws"]="Flame Claws",["CounterstrikeA"]="Counterstrike"}
APPaidSkills=S
