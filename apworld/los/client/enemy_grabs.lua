-- Runtime combat-link policy, independent of enemy randomization and chain tier.
APBridgeEnemyGrabs=APBridgeEnemyGrabs or {Originals={}}
local G=APBridgeEnemyGrabs
function G.Ensure()
    G.Stake=(APBridgeStake and APBridgeStake.Owned==true) and 1 or 0
    if not (CombatLinks and CombatLinks.Presets) then return end
    local classes={Ghoul=true,GhoulDLC=true,AnimArmour=true,SwordMaster=true,VampireWarrior=true}
    for _,links in pairs(CombatLinks.Presets) do
        for _,link in ipairs(links) do
            local c=link[2]
            if c and classes[c.Class] and string.find(link[1],'Catch',1,true) then
                if G.Originals[c]==nil then
                    G.Originals[c]={value=c['Boolean expresion']}
                    local parts={}
                    for part in string.gmatch(c['Boolean expresion'] or '', '[^,]+') do
                        if not string.match(part,'^Belmont%.ChainModelInUse%.Value>=[23]$') then
                            parts[#parts+1]=part
                        end
                    end
                    if c.Class=='VampireWarrior' then parts[#parts+1]='APBridgeEnemyGrabs.Stake==1' end
                    c['Boolean expresion']=#parts>0 and table.concat(parts,',') or nil
                end
            end
        end
    end
end
function G.Stop()
    for c,original in pairs(G.Originals) do c['Boolean expresion']=original.value end
    G.Originals={}
end
