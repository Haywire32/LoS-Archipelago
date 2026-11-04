-- Version 5 menu patch; preserves purchase journal, receipts and XP.
local S=assert(APPaidSkills)
if S.MenuRevision==5 then return end
assert(S.MenuRevision==nil, 'legacy paid-skill menu hooks require a fresh game process')
assert(S.Healthy() and not S.Pending, 'pause purchases before installing menu patch')
local E,T,M=Experience,TravelBook,TravelBook.ActionsManager
local managed=S.Definitions
local setup,open=T.SetupBuyDialog,T.OpenRightMenu
local getUpgrade,isUpgrade=M.GetActionUpgrade,M.IsUpgrade
local accessible,marked=M.IsActionAccesible,M.IsMarkedAsBuyable
-- Purchase and move ownership are independent. Use the same vocabulary on
-- the list and detail page, including moves supplied by an upgrade item.
function S.MoveStatus(a,compact)
    if S.Active and S.Active[a] then return 'Ready' end
    if not S.Owned[a] then return 'Locked' end
    local missing,seen={},{}
    local function collect(action)
        local d=managed[action]
        for _,parent in ipairs(d.skills) do collect(parent) end
        for _,relic in ipairs(d.relics) do
            if not S.Relics[relic] and not seen[relic] then
                seen[relic]=true; table.insert(missing,relic)
            end
        end
    end
    collect(a)
    if #missing==0 then return 'Ready' end
    if compact and #missing>1 then return 'Needs '..#missing..' relics' end
    return 'Needs '..table.concat(missing,', ')
end

-- Retail calls either of these markers for every visible action row, with
-- IsActionDisabled taking priority over IsBought. Intercept both so that a
-- vanilla padlock can never replace a paid check's purchase status.
local markState,markPrice=T.MarkActionState,T.MarkActionPrice
function S.RenderListStatus(id,name)
    local text=Scorer.GetItem(id,name)
    if not text or not text.uData then return end
    local row=Scorer.GetItem(id,text.uData.APRow)
    if not row or not row.uData or not managed[row.uData.ActionName] then
        text.Visible=0; return
    end
    local a=row.uData.ActionName
    local isCheck=text.uData.APCheck
    local normal=TravelBookItems.TextColor
    if isCheck then
        local state=S.Checked[a] and 'Bought' or (S.Pending==a and 'Pending' or tostring(managed[a].price)..' XP')
        text.Text='Check: '..state
        text.Color=S.Checked[a] and normal or (S.CanBuy(a) and T.ActionPriceAffordableColor or T.ActionPriceUnaffordableColor)
    else
        local state=S.MoveStatus(a,true)
        text.Text='Move: '..state
        text.Color=state=='Ready' and T.ActionPriceAffordableColor or normal
    end
    -- Native coordinates: the old status icon ended at x=660. Keep both
    -- columns beneath the name and inside that edge; fit actual font metrics.
    local width=math.max(1,660-row.x)
    local column=isCheck and width*0.46-6 or width*0.54
    local measured=Scorer.GetTextArea(T.Fonts.ActionKeys,text.Text)
    local scale=math.min(1,column/math.max(1,measured))
    text.Scale=V2D(scale,scale)
    text.Pos=V2D(row.x+(isCheck and 0 or width*0.46),row.y+17)
    text.Alpha=row.Alpha
    text.Visible=row.Visible
end
local function markPaidStatus(name)
    local row=Scorer.GetItem(0,name)
    if not row or not row.uData or not managed[row.uData.ActionName] then return false end
    T.ActionStatusItems=T.ActionStatusItems or {}
    for _,isCheck in ipairs({true,false}) do
        local statusName='StatusIcon'..tostring(#T.ActionStatusItems+1)
        local text=Scorer.NewItem(0,statusName,'Text',1)
        text.Font=T.Fonts.ActionKeys; text.Align='Left'; text.UseAlpha=1
        text.uData.APRow=name; text.uData.APCheck=isCheck
        text.OnRender='APPaidSkills.RenderListStatus'
        table.insert(T.ActionStatusItems,statusName)
        S.RenderListStatus(0,statusName)
    end
    return true
end
T.MarkActionState=function(name,...)
    if markPaidStatus(name) then return end
    return markState(name,...)
end
T.MarkActionPrice=function(name,...)
    if markPaidStatus(name) then return end
    return markPrice(name,...)
end
-- Shop entries must remain inspectable independently of received move ownership.
M.IsActionAccesible=function(self,a,...) if managed[a] then return true end return accessible(self,a,...) end
M.IsMarkedAsBuyable=function(self,a,...) if managed[a] then return true end return marked(self,a,...) end
M.GetActionUpgrade=function(self,a,...) if managed[a] then return nil end return getUpgrade(self,a,...) end
M.IsUpgrade=function(self,a,...) if managed[a] then return false end return isUpgrade(self,a,...) end
T.OpenRightMenu=function(...)
    local original=Game.GetLangStr
    Game.GetLangStr=function(key,...)
        local a=string.match(tostring(key),'^TBook_Action_Name_(.+)$'); if a and S.Labels[a] then return S.Labels[a] end
        return original(key,...)
    end
    local ok,result=pcall(open,...)
    Game.GetLangStr=original
    if not ok then error(result) end
    return result
end
local positions={ActionBoughtText=0.735,ActionAvailableCashHeader=0.78,
    ActionAvailableCash=0.82,ActionPrice=0.86,ActionAcceptButton=0.92}
local function restoreLayout()
    T.GetItem('ActionBoughtText').Scale=V2D(1,1)
    if not TravelBookItems then return end
    for name in pairs({ActionBoughtText=true,ActionAvailableCashHeader=true,ActionAvailableCash=true,ActionPrice=true,ActionAcceptButton=true,ActionConfirmText=true}) do
        local item=T.GetItem(name)
        for _,prop in ipairs(TravelBookItems.Items[name] or {}) do
            if prop[1]=='Font' or prop[1]=='fPos' then T.ApplyProperty(item,prop) end
        end
    end
end
T.SetupBuyDialog=function(...)
    restoreLayout()
    setup(...)
    local a=T.CurrentActionName
    if not managed[a] then return end
    local check=S.Checked[a] and 'Bought' or (S.Pending==a and 'Pending' or 'Unbought')
    local move=S.MoveStatus(a,false)
    local text=T.GetItem('ActionBoughtText')
    text.Text='Check: '..check..'  |  Move: '..move
    T.ApplyProperty(text,{'Font',T.Fonts.ActionKeys}) -- retail HoratioTiny
    -- Several required relic names can be longer than the old generic message.
    -- Reset the scale on every visit so shorter statuses return to normal size.
    local scale=1
    if Scorer.GetTextArea then
        local width=(T.MaxLowerRight.x-T.MinUpperLeft.x)*0.44
        scale=math.min(1,width/math.max(1,Scorer.GetTextArea(T.Fonts.ActionKeys,text.Text)))
    end
    text.Scale=V2D(scale,scale)
    text.OnRender=''; text.Visible=1
    local reward=T.GetItem('ActionConfirmText')
    reward.Visible=0
    if S.RevealRewards and not S.Checked[a] then
        reward.Text=(S.RewardLabels and S.RewardLabels[a]) or 'Reward: awaiting server'
        T.ApplyProperty(reward,{'Font',T.Fonts.ActionKeys})
        T.ApplyProperty(reward,{'fPos',V2D(0.25,0.78)})
        reward.OnRender='APPaidSkills.RenderReward'; reward.Visible=1
    end
    for name,y in pairs(positions) do T.ApplyProperty(T.GetItem(name),{'fPos',V2D(0.25,y)}) end
    if S.RevealRewards and not S.Checked[a] then
        T.GetItem('ActionAvailableCashHeader').Visible=0
        T.GetItem('ActionAvailableCash').Text='XP: '..tostring(E.EPoints.Value)
    end
    -- Re-anchor currency icons after moving their parent price/XP labels.
    if not S.Checked[a] then
        T.AppendCurrencyIconToText(T.GetItem('ActionPrice'),'ActionBuyDialogCurrencyIcon1',T.Fonts.ActionBuyDialog,V2D(12,1))
        T.AppendCurrencyIconToText(T.GetItem('ActionAvailableCash'),'ActionBuyDialogCurrencyIcon2',T.Fonts.ActionBuyDialog,V2D(10,1))
    end
end
-- Extend the original exact hook checks to include the newly installed menu hooks.
local eBuy,mBought,mCan,mBuy=E.BuyCombo,M.IsBought,M.CanBeBought,M.BuyAction
local tSetup,tAccept,tOpen=T.SetupBuyDialog,T.BuyAction,T.OpenRightMenu
local mAccess,mMarked,mUpgrade,mIsUpgrade=M.IsActionAccesible,M.IsMarkedAsBuyable,M.GetActionUpgrade,M.IsUpgrade
local tMarkState,tMarkPrice=T.MarkActionState,T.MarkActionPrice
S.Healthy=function()
    return Experience==E and TravelBook==T and T.ActionsManager==M
        and E.BuyCombo==eBuy and M.IsBought==mBought and M.CanBeBought==mCan and M.BuyAction==mBuy
        and T.SetupBuyDialog==tSetup and T.BuyAction==tAccept and T.OpenRightMenu==tOpen
        and M.IsActionAccesible==mAccess and M.IsMarkedAsBuyable==mMarked
        and M.GetActionUpgrade==mUpgrade and M.IsUpgrade==mIsUpgrade
        and T.MarkActionState==tMarkState and T.MarkActionPrice==tMarkPrice
end
S.MenuRevision=5
Game.Set('InitLuaLine','--PAID|menu-v5-installed')

function S.RenderReward()
    local a=T.CurrentActionName
    if S.RevealRewards and managed[a] and not S.Checked[a] then
        T.GetItem('ActionConfirmText').Text=(S.RewardLabels and S.RewardLabels[a]) or 'Reward: awaiting server'
    end
end
local confirm=T.ShowBuyActionConfirmation
T.ShowBuyActionConfirmation=function(...)
    T.GetItem('ActionConfirmText').OnRender=''
    return confirm(...)
end
