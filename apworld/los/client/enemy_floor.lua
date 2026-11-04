-- Retail evidence: WeaponsCombo 0.32 uses ent:GetOnFloorPos(pos, distance)
-- and ent:TestCharPos(pos) -> isOk, onFloor, isDynamic, platform.
-- Y is vertical. Query with Belmont's walk capsule; never move Belmont.
APEnemyFloor={Radius=800,Drop=1200,Footprint=100,Step=45}
local F=APEnemyFloor
local function finite(n) return type(n)=='number' and n==n and math.abs(n)<10000000 end
local function point(p) return p and finite(p.x) and finite(p.y) and finite(p.z) end
local function valid(probe,p)
    local ok,floor,dynamic=probe:TestCharPos(p)
    return ok and floor and not dynamic
end
function F.Find(origin,controller,probe)
    probe=probe or player
    if not point(origin) or not probe or type(probe.GetOnFloorPos)~='function'
        or type(probe.TestCharPos)~='function' then return nil,'floor-query-unavailable' end
    if not AI or type(AI.IsEntAssocNearGraph)~='function' or not controller then
        return nil,'navigation-query-unavailable'
    end
    local best,bestDistance=nil,nil
    -- Deterministic finite search, not a navmesh nearest-point assertion.
    -- Wide support rejects fence rails and narrow ledges; static collision only.
    local offsets={{0,0}}
    for _,r in ipairs({100,200,400,800}) do
        for _,d in ipairs({{1,0},{0,1},{-1,0},{0,-1},{0.7071,0.7071},
            {-0.7071,0.7071},{-0.7071,-0.7071},{0.7071,-0.7071}}) do
            offsets[#offsets+1]={d[1]*r,d[2]*r}
        end
    end
    for _,d in ipairs(offsets) do
        local p=probe:GetOnFloorPos(V3D(origin.x+d[1],origin.y+100,origin.z+d[2]),F.Drop)
        if point(p) and p.y<=origin.y+100 and p.y>=origin.y-F.Drop and valid(probe,p) then
            local supported=true
            for _,side in ipairs({{F.Footprint,0},{-F.Footprint,0},{0,F.Footprint},{0,-F.Footprint}}) do
                local q=probe:GetOnFloorPos(V3D(p.x+side[1],p.y+F.Step,p.z+side[2]),F.Step*2)
                if not point(q) or math.abs(q.y-p.y)>F.Step or not valid(probe,q) then
                    supported=false;break
                end
            end
            local distance=(p.x-origin.x)^2+(p.y-origin.y)^2+(p.z-origin.z)^2
            -- Retail AISpecific.ValidateEnemiesNearGraph uses zero for an
            -- absent/unreachable enemy graph. This does not prove connectivity
            -- to the player's arena across a wall or a locked door.
            local graph=supported and AI.IsEntAssocNearGraph(p,controller)
            if supported and type(graph)=='number' and graph~=0 and (not bestDistance or distance<bestDistance) then
                best=V3D(p.x,p.y,p.z);bestDistance=distance
                if distance<0.0001 then return best,'floor' end
            end
        end
    end
    return best,best and 'floor' or 'no-supported-floor'
end

-- Preflight before the authored NPC is constructed. This object never joins an
-- encounter, receives AI, an entrance action, death callbacks, or activation.
-- Native NPC.DeleteEntity uses the same entity:Del() cleanup method.
function F.Preflight(origin,controller,graphType)
    if not point(origin) then return nil,'invalid-origin' end
    F.Serial=(F.Serial or 0)+1
    local name='__APEnemyFloorProbe_'..F.Serial
    if Game.GetEntity(name) then return nil,'probe-name-in-use' end
    local probe
    local ok,ground,reason=pcall(function()
        probe=Game.CreateEntity(name,'WalkChar')
        assert(probe,'Cannot create floor probe')
        probe.bActive=false
        probe.Pos=V3D(origin.x,origin.y,origin.z)
        probe.ActCtrl=controller
        return F.Find(origin,graphType or controller,probe)
    end)
    -- Clean up both success and Lua-error paths before real NPC creation.
    if probe then probe:Del() end
    if not ok then return nil,'floor-query-error' end
    return ground,reason
end
