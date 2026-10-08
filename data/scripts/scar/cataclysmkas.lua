-- cataclysmkas.lua: runtime for missions translated from cataclysm.exe by tools/kas2lua.py.
--
-- The translated code calls K_<address>(...) for every KAS API function (cataclysm.exe KASFunc.c). Every one
-- used by any mission has a logging stub in cataclysmkas_stubs.lua (generated); this file replaces stubs with
-- real implementations as they are written. Semantics follow the decompiled exe (Cataclysm-decomp/out/kasapi/)
-- and HW1's KASFunc.c. Lua 4: no booleans (comparisons give 1/nil), 0 is true, no bit operators.
--
-- Teams are their label strings (= the SobGroup the level creates); selections are SobGroup names.
-- Load order in a mission script: KASUtil.lua and friends, then cataclysmkas_stubs.lua, then this file.

-- ------------------------------------------------------------------ context (CurrentTeamP and variable scope)
KAS_Team = ""
KAS_ScopeKind = 0
KAS_Scope = 0
KAS_Stack = {}
KAS_LabelHash = KAS_LabelHash or {}

function KAS_Push()
    tinsert(KAS_Stack, { KAS_Team, KAS_ScopeKind, KAS_Scope })
end

function KAS_Pop()
    local top = tremove(KAS_Stack)
    if top then
        KAS_Team = top[1]
        KAS_ScopeKind = top[2]
        KAS_Scope = top[3]
    end
end

function KAS_TeamHash(team)
    return KAS_LabelHash[team] or 0
end

-- ------------------------------------------------------------------ diagnostics
KAS_Warned = {}

function KAS_WarnOnce(key, text)
    if KAS_Warned[key] == nil then
        KAS_Warned[key] = 1
        print("CKAS: " .. text)
    end
end

function KAS_Stub(addr, name, ...)
    KAS_WarnOnce(addr, "unimplemented " .. addr .. " " .. name .. " (team " .. KAS_Team .. ")")
    return 0
end

function KAS_Unsupported(fn, why)
    KAS_WarnOnce(fn, "untranslated function " .. fn .. ": " .. why)
end

function KAS_Native(addr, ...)
    KAS_WarnOnce("native" .. addr, "native call " .. addr .. " not implemented")
    return 0
end

-- ------------------------------------------------------------------ C helpers (no bit ops in Lua 4)
function KAS_B(v)
    if v then return 1 end
    return 0
end

function KAS_div(a, b)
    if b == 0 then return 0 end
    local q = a / b
    if q < 0 then return -floor(-q) end
    return floor(q)
end

function KAS_mod(a, b)
    if b == 0 then return 0 end
    return a - KAS_div(a, b) * b
end

function KAS_u32(a)
    if a < 0 then return a + 4294967296 end
    return a
end

function KAS_bitop(a, b, op)
    a = KAS_u32(a)
    b = KAS_u32(b)
    local r, bit = 0, 1
    local i = 0
    while i < 32 do
        local x, y = mod(a, 2), mod(b, 2)
        local v = 0
        if op == 1 and x == 1 and y == 1 then v = 1 end
        if op == 2 and (x == 1 or y == 1) then v = 1 end
        if op == 3 and x ~= y then v = 1 end
        r = r + v * bit
        a = floor(a / 2)
        b = floor(b / 2)
        bit = bit * 2
        i = i + 1
    end
    return r
end

function KAS_band(a, b) return KAS_bitop(a, b, 1) end
function KAS_bor(a, b) return KAS_bitop(a, b, 2) end
function KAS_bxor(a, b) return KAS_bitop(a, b, 3) end
function KAS_bnot(a) return 4294967295 - KAS_u32(a) end
function KAS_shl(a, n) return mod(KAS_u32(a) * 2 ^ n, 4294967296) end
function KAS_shr(a, n) return floor(KAS_u32(a) / 2 ^ n) end

KAS_Globals = {}
function KAS_G(addr) return KAS_Globals[addr] or 0 end
function KAS_SetG(addr, v) KAS_Globals[addr] = v end

-- ------------------------------------------------------------------ named labels -> engine objects
function KAS_GS(name)
    local g = "GS_" .. name
    SobGroup_CreateIfNotExist(g)
    SobGroup_SetSwitchOwnerFlag(g, 0)   -- HW1 behaviour: keep ships that change owner
    return g
end

function KAS_Vector(name) return name end
function KAS_TeamVector(team) return SobGroup_GetPosition(team) end
function KAS_ShipsVector(sel) return SobGroup_GetPosition(sel) end
function KAS_VolumeVector(vol) return Volume_GetPosition(vol) end

function KAS_ClearStateRule(team)
    if KASStateRulesByTeam[team] then
        KASRule_Remove(team, KASStateRulesByTeam[team], "KAS_ClearStateRule")
    end
end

function KAS_ClearFSMRule(team)
    KAS_ClearStateRule(team)
end

-- ------------------------------------------------------------------ variables and timers (scoped by hash)
-- A name hash with bit 31 set is global; otherwise it belongs to the current scope (mission or team hash).
function KAS_Key(h)
    if h < 0 then
        return "0:" .. (h + 2147483648)
    end
    if KAS_ScopeKind ~= 0 then
        return KAS_Scope .. ":" .. h
    end
    return "0:" .. h
end

KAS_Vars = {}
function K_491cf0(h) local k = KAS_Key(h); if KAS_Vars[k] == nil then KAS_Vars[k] = 0 end end      -- kasfVarCreate
function K_491d30(h, v) KAS_Vars[KAS_Key(h)] = v end                                                -- kasfVarCreateSet
function K_491d70(h, v) KAS_Vars[KAS_Key(h)] = v end                                                -- kasfVarValueSet
function K_491db0(h) local k = KAS_Key(h); KAS_Vars[k] = (KAS_Vars[k] or 0) + 1 end                 -- kasfVarValueInc
function K_491df0(h) local k = KAS_Key(h); KAS_Vars[k] = (KAS_Vars[k] or 0) - 1 end                 -- kasfVarValueDec
function K_491e30(h) return KAS_Vars[KAS_Key(h)] or 0 end                                           -- kasfVarValueGet
function K_491e70(h) KAS_Vars[KAS_Key(h)] = nil end                                                 -- kasfVarDestroy

-- Timers follow HW1 Game/Timer.c exactly: a timer that exists but is not running has 0 remaining and therefore
-- counts as EXPIRED (created-but-never-started, started with duration <= 0, or stopped). Non-existent timers are
-- never expired. Stop stores the remaining time as the new duration.
KAS_Timers = {}
function KAS_Now() return Universe_GameTime() end

function KAS_TimerRemaining(t)
    if t.running ~= 1 then return 0 end
    local rem = floor(t.dur - (KAS_Now() - t.start))
    if rem < 0 then rem = 0 end
    return rem
end

function K_491ec0(h)                                                                                -- kasfTimerCreate
    local k = KAS_Key(h)
    if KAS_Timers[k] == nil then KAS_Timers[k] = { dur = 0, start = 0, running = 0 } end
end
function K_491f00(h, d)                                                                             -- kasfTimerSet
    local t = KAS_Timers[KAS_Key(h)]
    if t then t.dur = d end
end
function K_491f50(h)                                                                                -- kasfTimerStart
    local t = KAS_Timers[KAS_Key(h)]
    if t == nil then return end
    if t.dur > 0 then
        t.start = KAS_Now()
        t.running = 1
    else
        t.running = 0
    end
end
function K_491f90(h, d)                                                                             -- kasfTimerCreateSetStart
    K_491ec0(h)
    K_491f00(h, d)
    K_491f50(h)
end
function K_491fe0(h)                                                                                -- kasfTimerStop
    local t = KAS_Timers[KAS_Key(h)]
    if t then t.dur = KAS_TimerRemaining(t); t.running = 0 end
end
function K_492020(h)                                                                                -- kasfTimerRemaining
    local t = KAS_Timers[KAS_Key(h)]
    if t then return KAS_TimerRemaining(t) end
    return 0
end
function K_492060(h)                                                                                -- kasfTimerExpired
    local t = KAS_Timers[KAS_Key(h)]
    if t == nil then return 0 end
    return KAS_B(KAS_TimerRemaining(t) == 0)
end
function K_4920a0(h)                                                                                -- kasfTimerExpiredDestroy
    local k = KAS_Key(h)
    local t = KAS_Timers[k]
    if t == nil then return 0 end
    if KAS_TimerRemaining(t) == 0 then
        KAS_Timers[k] = nil
        return 1
    end
    return 0
end
function K_4920e0(h) KAS_Timers[KAS_Key(h)] = nil end                                               -- kasfTimerDestroy

-- ------------------------------------------------------------------ team messages (exe FUN_00417e10/60/c0)
-- Per-team queue of (message hash, sender). Reading message i removes it by swapping in the last one.
KAS_Msgs = {}

function KAS_MsgSendRawUntraced(from, to, msg)
    local q = KAS_Msgs[to]
    if q == nil then q = {}; KAS_Msgs[to] = q end
    if getn(q) >= 64 then KAS_Msgs[to] = {}; q = KAS_Msgs[to] end   -- the exe resets the count at 64
    tinsert(q, msg)
end

function KAS_TeamMsgQueue(team)
    if KAS_Msgs[team] then return 1 end
    return 0
end

function KAS_TeamMsgCount(team)
    local q = KAS_Msgs[team]
    if q then return getn(q) end
    return 0
end

function KAS_TeamMsgGet(team, i)
    local q = KAS_Msgs[team]
    if q == nil or i < 0 or i >= getn(q) then return 0 end
    local m = q[i + 1]
    q[i + 1] = q[getn(q)]
    tremove(q)
    if KAS_TraceMsgs == 1 then print("CKAS got " .. team .. " : " .. m) end
    return m
end

function K_492120(msg)                                                                              -- kasfMsgReceived
    local q = KAS_Msgs[KAS_Team]
    if q == nil or msg == 0 then return 0 end
    local i = 1
    while i <= getn(q) do
        if q[i] == msg then
            q[i] = q[getn(q)]
            tremove(q)
            return 1
        end
        i = i + 1
    end
    return 0
end

function K_494a00(team, msg) KAS_MsgSendRaw(KAS_Team, team, msg) end                               -- kasfMsgSend

function K_4949b0(msg)                                                                              -- kasfMsgSendAll
    local i = 0
    while i < KASNumberTeams do
        KAS_MsgSendRaw(KAS_Team, KASTeams[i], msg)
        i = i + 1
    end
end

-- ------------------------------------------------------------------ team, selection and misc queries
function K_492ce0() return SobGroup_Count(KAS_Team) end                                             -- kasfTeamCount
function K_492d10(sel) SobGroup_Clear(sel) end                                                      -- kasfGrowSelectionClear
function K_492d20(sel) return SobGroup_Count(sel) end                                               -- kasfShipsCount
function K_493de0(team) return KAS_B(team == KAS_Team) end                                          -- kasfThisTeamIs
function K_492910(lo, hi) return RandomIntRange(hi, lo) end                                         -- kasfRandom
function K_493b90() return Player_GetLevelOfDifficulty(0) end                                       -- kasfMissionSkillGet

function K_495bd0(a, b)                                                                             -- kasfShipsAdd
    if a ~= b then SobGroup_SobGroupAdd(a, b) end
    return SobGroup_Count(a)
end

function K_495c40(a, b)                                                                             -- kasfShipsRemove
    if a == b then
        SobGroup_Clear(a)
        return 0
    end
    SobGroup_CreateIfNotExist("KAS_Temp")
    SobGroup_FillSubtract("KAS_Temp", a, b)
    SobGroup_Clear(a)
    SobGroup_SobGroupAdd(a, "KAS_Temp")
    return SobGroup_Count(a)
end

-- ------------------------------------------------------------------ objectives (labels -> HWRM objective ids)
KAS_Objectives = {}

function K_494e70(label, brief, full)                                                               -- kasfObjectiveCreate
    if KAS_Objectives[label] == nil then
        KAS_Objectives[label] = Objective_Add(brief, OT_Primary)
        if full and full ~= "" and full ~= brief then
            Objective_AddDescription(KAS_Objectives[label], full)
        end
    end
end

function K_494f70()                                                                                 -- kasfObjectiveDestroyAll
    for label, id in KAS_Objectives do
        Objective_SetState(id, OS_Off)
    end
    KAS_Objectives = {}
end

function K_494f60(label)                                                                            -- kasfObjectiveDestroy
    if KAS_Objectives[label] then
        Objective_SetState(KAS_Objectives[label], OS_Off)
        KAS_Objectives[label] = nil
    end
end

-- ------------------------------------------------------------------ visibility and volumes
-- Discovery radius: Cataclysm's Recon fowRadius (16000) scaled to HWRM units (x0.35).
KAS_DiscoverRadius = 5600

-- 0x499570 (kasfHasShipBeenDiscovered?): 1 if any ship of the selection is visible to the player. The exe checks
-- each ship's position against the fog-of-war map; here: any player ship within sensor range of it.
function K_499570(sel)
    if SobGroup_Count(sel) == 0 then return 0 end
    SobGroup_CreateIfNotExist("KAS_Discover")
    SobGroup_Clear("KAS_Discover")
    Player_FillProximitySobGroup("KAS_Discover", 0, sel, KAS_DiscoverRadius)
    return KAS_B(SobGroup_Count("KAS_Discover") > 0)
end

-- kasfFindShipsInside(volume, ships): every live ship of every player inside the volume
function K_492db0(volume, sel)
    SobGroup_Clear(sel)
    SobGroup_CreateIfNotExist("KAS_InVolume")
    local p = 0
    while p < Universe_PlayerCount() do
        SobGroup_Clear("KAS_InVolume")
        Player_FillSobGroupInVolume("KAS_InVolume", p, volume)
        SobGroup_SobGroupAdd(sel, "KAS_InVolume")
        p = p + 1
    end
    return SobGroup_Count(sel)
end

-- kasfTutEnableFlags: tutorial UI enable flags; no HWRM equivalent needed outside the tutorial
function K_496720(flags) end
-- ------------------------------------------------------------------ single-player engine variables
-- Cataclysm's SP code (exe FUN_005197d0) talks to missions through global KAS variables: a mission sets
-- G_PlayNis / G_PlayNislet = N to request cutscene N; the engine sets G_Nis<N>Complete / G_Nislet<N>Complete
-- (format strings in the exe) when it ends, and G_ShipsHaveArrived after the fleet hyperspaces in.
-- Until NIS playback exists (Phase 0.5) KAS_EngineTick completes every requested cutscene at once.
KAS_Key_PlayNis = "0:84324259"
KAS_Key_PlayNislet = "0:184168644"
KAS_Key_ShipsHaveArrived = "0:132054244"
KAS_Key_NisComplete = {}
KAS_Key_NisletComplete = {}
KAS_Key_NisComplete[0] = "0:134957621"
KAS_Key_NisletComplete[0] = "0:207887397"
KAS_Key_NisComplete[1] = "0:134957877"
KAS_Key_NisletComplete[1] = "0:207887653"
KAS_Key_NisComplete[2] = "0:134957109"
KAS_Key_NisletComplete[2] = "0:207887909"
KAS_Key_NisComplete[3] = "0:134957365"
KAS_Key_NisletComplete[3] = "0:207888165"
KAS_Key_NisComplete[4] = "0:134956597"
KAS_Key_NisletComplete[4] = "0:207884325"
KAS_Key_NisComplete[5] = "0:134956853"
KAS_Key_NisletComplete[5] = "0:207884581"
KAS_Key_NisComplete[6] = "0:134956085"
KAS_Key_NisletComplete[6] = "0:207884837"
KAS_Key_NisComplete[7] = "0:134956341"
KAS_Key_NisletComplete[7] = "0:207885093"
KAS_Key_NisComplete[8] = "0:134955573"
KAS_Key_NisletComplete[8] = "0:207885349"
KAS_Key_NisComplete[9] = "0:134955829"
KAS_Key_NisletComplete[9] = "0:207885605"
KAS_Key_NisComplete[10] = "0:46228421"
KAS_Key_NisletComplete[10] = "0:139854213"
KAS_Key_NisComplete[11] = "0:46228165"
KAS_Key_NisletComplete[11] = "0:139855493"
KAS_Key_NisComplete[12] = "0:46227909"
KAS_Key_NisletComplete[12] = "0:139854725"
KAS_Key_NisComplete[13] = "0:46227653"
KAS_Key_NisletComplete[13] = "0:139853957"
KAS_Key_NisComplete[14] = "0:46231493"
KAS_Key_NisletComplete[14] = "0:139857285"
KAS_Key_NisComplete[15] = "0:46231237"
KAS_Key_NisletComplete[15] = "0:139854469"
KAS_Key_NisComplete[16] = "0:46230981"
KAS_Key_NisletComplete[16] = "0:139857797"
KAS_Key_NisComplete[17] = "0:46230725"
KAS_Key_NisletComplete[17] = "0:139857029"
KAS_Key_NisComplete[18] = "0:46230469"
KAS_Key_NisletComplete[18] = "0:139856261"
KAS_Key_NisComplete[19] = "0:46230213"
KAS_Key_NisletComplete[19] = "0:139857541"
KAS_Key_NisComplete[20] = "0:46232517"
KAS_Key_NisletComplete[20] = "0:139858309"

-- Cutscenes (Phase 0.5). Converted ones (tools/nis2hwrm.py -> data/nis/cataclysm/<name>.nis) play relative to the
-- player's mothership like singlePlayerStartNis does; the rest still "play" for KAS_NisSeconds. Completing a missing
-- one at once started every team before the level's ships were in their SobGroups (instant mission failure).
KAS_NisSeconds = 5
KAS_NisPending = nil
KAS_NisPath = "nis/cataclysm/"
KAS_NisAvailable = {}                 -- names converted so far
KAS_NisAvailable["n01"] = 1

-- Cues: what a converted cutscene's HWRM script can't play (music: its musicStart stayed silent), as
-- { seconds after the start, kind, argument }; generated next to each NIS by tools/nis2hwrm.py
-- (data/nis/cataclysm/<name>_cues.lua, report in docs/nis/<name>.md).
KAS_NisCues = {}
for name, _ in KAS_NisAvailable do
    dofilepath("data:nis/cataclysm/" .. name .. "_cues.lua")
end

function KAS_NisCuesStart(name)
    KAS_NisCueList = KAS_NisCues[name]
    KAS_NisCueNext = 1
    KAS_NisCueStart = Universe_GameTime()
    if KAS_NisCueList and getn(KAS_NisCueList) > 0 then
        Rule_AddInterval("KAS_NisCueTick", 0.1)
    end
end

function KAS_NisCueTick()
    local l = KAS_NisCueList
    if l == nil then
        Rule_Remove("KAS_NisCueTick")
        return
    end
    local t = Universe_GameTime() - KAS_NisCueStart
    while KAS_NisCueNext <= getn(l) and l[KAS_NisCueNext][1] <= t do
        local c = l[KAS_NisCueNext]
        KAS_NisCueNext = KAS_NisCueNext + 1
        if c[2] == "music" then                        -- as kasfMusicPlay
            Sound_MusicPlayType(c[3], MUS_Ambient)
        end
        print("CKAS: NIS cue " .. c[2] .. " " .. c[3] .. " at " .. t .. "s")
    end
    if KAS_NisCueNext > getn(l) then
        KAS_NisCueList = nil
        Rule_Remove("KAS_NisCueTick")
    end
end

function KAS_NisName(number, nislet)
    if nislet then
        if number < 10 then return "nislet0" .. number end
        return "nislet" .. number
    end
    if number < 10 then return "n0" .. number end
    return "n" .. number
end

function KAS_NisStart(name)
    local path = KAS_NisPath .. name
    NISLoad(path)
    SobGroup_CreateIfNotExist("KAS_NisCentre")
    K_498790("KAS_NisCentre")
    local position = { 0, 0, 0 }
    local nisMatrix = Matrix3_Identity()
    if SobGroup_Count("KAS_NisCentre") > 0 then
        local info = NISShipStartPosition(path, SobGroup_GetShipType("KAS_NisCentre"), -1)
        if info[1] == 1 then
            local motherVector = { info[2], info[3], info[4] }
            local motherMatrix = { info[5], info[6], info[7], info[8], info[9], info[10], info[11], info[12], info[13] }
            nisMatrix = Matrix3_MultiplyByMatrix3(SobGroup_GetCoordSys("KAS_NisCentre"), Matrix3_Transpose(motherMatrix))
            position = Vector3_Subtract(SobGroup_GetPosition("KAS_NisCentre"),
                                        Matrix3_MultiplyVector3ByMatrix(motherVector, nisMatrix))
        else
            print("CKAS: " .. path .. " has no " .. SobGroup_GetShipType("KAS_NisCentre") .. " to centre on - skipped")
            return nil
        end
    end
    NISPlayFromCoordSys(path, position, nisMatrix)
    KAS_NisCuesStart(name)
    print("CKAS: playing " .. path .. " at {" .. position[1] .. ", " .. position[2] .. ", " .. position[3] .. "}")
    return 1
end

-- Play a cutscene; when it ends set KAS variable `key` (may be nil) and call `after` (may be nil).
function KAS_NisPlay(name, key, after)
    KAS_NisPending = { key = key, after = after, playing = 1, started = Universe_GameTime() }
    if KAS_NisStart(name) == nil then
        KAS_NisPending = { key = key, after = after, at = Universe_GameTime() }
    end
end

function KAS_NisRequest(number, nislet, key)
    local name = KAS_NisName(number, nislet)
    if KAS_NisAvailable[name] then
        KAS_NisPlay(name, key, nil)
    else
        KAS_NisPending = { key = key, at = Universe_GameTime() + KAS_NisSeconds }
        print("CKAS: " .. name .. " requested (not converted yet: completes in " .. KAS_NisSeconds .. "s)")
    end
end

-- Mission start: play the intro cutscene (if any), then start the mission's KAS code.
function KAS_RunAfterIntro(name, start)
    print("CKAS: actors FleetCommand=" .. Actor_HW1_FleetCommand .. " FleetIntel=" .. Actor_HW1_FleetIntel)
    if name ~= "" and KAS_NisAvailable[name] then
        -- The intro has its own copies of the player's ships (HW1 played it before the mission's ships existed):
        -- hide the real ones until it ends. (Gearbox keeps the NIS ships instead with remainAtEnd; later.)
        KAS_IntroStart = start
        SobGroup_SetHidden("Player_Ships0", 1)
        KAS_NisPlay(name, nil, KAS_IntroDone)
    else
        start()
    end
end

function KAS_IntroDone()
    SobGroup_SetHidden("Player_Ships0", 0)
    KAS_IntroStart()
end

function KAS_NisFinished()
    local p = KAS_NisPending
    local now = Universe_GameTime()
    if p.playing == nil then return now >= p.at end
    if now - p.started < 2 then return nil end
    local h = NISGetAnyPlayingHandle()
    if h == NISHandle_Invalid then return 1 end
    if NISComplete(h) == 1 then return 1 end
    return now - p.started > 600
end

function KAS_EngineTick()
    local now = Universe_GameTime()
    if KAS_AlliancesDone == nil then
        KAS_AlliancesDone = 1
        KAS_ApplyAlliances()
    end
    if KAS_NisPending == nil then
        local n = KAS_Vars[KAS_Key_PlayNislet]
        if n and n ~= 0 then
            KAS_Vars[KAS_Key_PlayNislet] = 0
            KAS_NisRequest(n, 1, KAS_Key_NisletComplete[n])
        end
        n = KAS_Vars[KAS_Key_PlayNis]
        if KAS_NisPending == nil and n and n ~= 0 then
            KAS_Vars[KAS_Key_PlayNis] = 0
            KAS_NisRequest(n, nil, KAS_Key_NisComplete[n])
        end
    elseif KAS_NisFinished() then
        local p = KAS_NisPending
        KAS_NisPending = nil
        KAS_NisCueList = nil              -- ended or skipped: no more cues
        if p.key then KAS_Vars[p.key] = 1 end
        print("CKAS: cutscene complete")
        if p.after then p.after() end
    end
    if KAS_ShipsArriveAt and now >= KAS_ShipsArriveAt then
        KAS_ShipsArriveAt = nil
        KAS_Vars[KAS_Key_ShipsHaveArrived] = 1
        print("CKAS: G_ShipsHaveArrived")
    end
end

-- kasfStartLevelByHyperspacingShips: the engine hyperspaces the player's fleet in, then sets G_ShipsHaveArrived.
-- The stand-in fleet is already placed by the level, so only the signal is needed (after a short delay).
function K_498230()
    KAS_ShipsArriveAt = Universe_GameTime() + 3
end

-- Player 2 (when the level has one) is the allied Kushan fleet. Applied at start and again on the first tick.
function KAS_ApplyAlliances()
    local n = Universe_PlayerCount()
    print("CKAS: " .. n .. " players; allying 0 and 2")
    if n > 2 then
        SetAlliance(0, 2)
        SetAlliance(2, 0)
    end
end

-- Cataclysm research is offered by the mission (kasfAllowPlayerToResearch / Purchase): lock every tech first.
function KAS_RestrictTechs()
    if KAS_Techs == nil then return end
    local i = 1
    while i <= getn(KAS_Techs) do
        Player_RestrictResearchOption(0, KAS_Techs[i])
        i = i + 1
    end
end

-- Kuun-Lan modules the mission starts with (KAS_StartModules from build_mission.py: subsystems smt_kl_*).
function KAS_CreateStartModules()
    if KAS_StartModules == nil then return end
    SobGroup_Create("KAS_KuunLan")
    SobGroup_Clear("KAS_KuunLan")
    SobGroup_FilterInclude("KAS_KuunLan", "Player_Ships0", "ShipType", "smt_ms_sp")
    print("CKAS: Kuun-Lan x" .. SobGroup_Count("KAS_KuunLan") .. ", " .. getn(KAS_StartModules) .. " modules")
    local i = 1
    while i <= getn(KAS_StartModules) do
        SobGroup_CreateSubSystem("KAS_KuunLan", KAS_StartModules[i])
        i = i + 1
    end
    -- the structural modules have to be in the build list for SobGroup_CreateSubSystem to accept them; keep them
    -- out of the player's reach once the starting ones exist (a tick later, so creation is not affected)
    Rule_AddInterval("KAS_RestrictStructuralModules", 1)
end

function KAS_RestrictStructuralModules()
    Rule_Remove("KAS_RestrictStructuralModules")
    if KAS_StructuralModules == nil then return end
    local i = 1
    while i <= getn(KAS_StructuralModules) do
        Player_RestrictBuildOption(0, KAS_StructuralModules[i])
        i = i + 1
    end
    print("CKAS: structural modules restricted: " .. getn(KAS_StructuralModules))
end

function KAS_StartEngine()
    KAS_ApplyAlliances()
    KAS_RestrictTechs()
    Rule_AddInterval("KAS_EngineTick", 0.5)
end

-- ------------------------------------------------------------------ orders and selections (Gearbox KASUtil helpers)
-- kasfAttack: HW1 passes the targets to its advanced attack AI, which only engages enemies; HWRM SobGroup_Attack
-- attacks whatever it is given (Mission01's guards attack "every non-capital ship in BattleZone"). Keep only the
-- ships of this team's enemies.
function K_492190(targets)                                                                           -- kasfAttack
    if SobGroup_Count(KAS_Team) == 0 then return end
    SobGroup_CreateIfNotExist("KAS_AttackTargets")
    SobGroup_CreateIfNotExist("KAS_AttackTmp")
    SobGroup_Clear("KAS_AttackTargets")
    local enemies = KAS_EnemyPlayers(SobGroup_GetPlayerOwner(KAS_Team))
    local i = 1
    while i <= getn(enemies) do
        SobGroup_Clear("KAS_AttackTmp")
        SobGroup_FilterInclude("KAS_AttackTmp", targets, "PlayerOwner", "" .. enemies[i])
        SobGroup_SobGroupAdd("KAS_AttackTargets", "KAS_AttackTmp")
        i = i + 1
    end
    if SobGroup_Count("KAS_AttackTargets") > 0 then KAS_Attack(KAS_Team, "KAS_AttackTargets") end
end

function KAS_SelectInto(newShips, orig, fill)
    if newShips == orig then
        SobGroup_CreateIfNotExist("KAS_SelTemp")
        SobGroup_Clear("KAS_SelTemp")
        SobGroup_SobGroupAdd("KAS_SelTemp", orig)
        orig = "KAS_SelTemp"
    end
    SobGroup_Clear(newShips)
    return fill(newShips, orig)
end
function K_495560(n, o) return KAS_SelectInto(n, o, KAS_FillShipsByCapital) end                  -- kasfShipsSelectCapital
function K_495620(n, o) return KAS_SelectInto(n, o, KAS_FillShipsByNonCapital) end               -- kasfShipsSelectNonCapital

-- Cataclysm's kasfTeamSwitchPlayerOwner takes the new owner (HW1's had none): Mission01 hands allied Kushan teams
-- to player 0 this way.
-- exe 0x493f80 toggles each ship: player-owned -> computer player, anything else -> human player. HWRM SobGroups
-- drop ships that change owner unless their switch-owner flag is cleared (Gearbox's KASSobGroup_Create does this),
-- which emptied the team and made e.g. the proximity array report itself destroyed.
-- Teams keep their level owner (1 enemy, 2 allied Kushan: mission2level.py) to switch back to.
KAS_TeamOwners = {}
function K_494160(flag)                                                                              -- kasfTeamSwitchPlayerOwner
    SobGroup_SetSwitchOwnerFlag(KAS_Team, 0)
    if SobGroup_Count(KAS_Team) == 0 then return end
    local owner = SobGroup_GetPlayerOwner(KAS_Team)
    if owner == 0 then
        SobGroup_SwitchOwner(KAS_Team, KAS_TeamOwners[KAS_Team] or 1)
    else
        KAS_TeamOwners[KAS_Team] = owner
        SobGroup_SwitchOwner(KAS_Team, 0)
    end
end

-- kasfResetShipRenderFlags: clears per-ship "has been rendered" bits used by kasfRenderedShips; no HWRM state.
function K_498c70(sel) end

-- ------------------------------------------------------------------ KAS.c helpers called with a run-time hash
-- The translator turns constant-hash lookups into label strings; these handle hashes held in variables.
KAS_LabelByHash = nil
function KAS_HashLabel(h)
    if KAS_LabelByHash == nil then
        KAS_LabelByHash = {}
        for label, hash in KAS_LabelHash do KAS_LabelByHash[hash] = label end
    end
    if h < 0 then h = h + 2147483648 end
    return KAS_LabelByHash[h]
end

function K_4907a0(h) return KAS_HashLabel(h) or "" end                                             -- kasAITeamPtr
function K_4907e0(h) return KAS_HashLabel(h) or "" end                                             -- kasAITeamShipsPtr
function K_490a60(h) return KAS_HashLabel(h) or "" end                                             -- kasPathPtrNoErrorChecking
function K_490aa0(h) return KAS_HashLabel(h) or "" end                                             -- kasPathPtr
function K_490af0(h) return KAS_HashLabel(h) or "" end                                             -- kasVolumePtr
function K_490b30(h) return KAS_Vector(KAS_HashLabel(h) or "") end                                 -- kasVectorPtr
function K_490b70(h) return KAS_GS(KAS_HashLabel(h) or format("gs_%08x", h)) end                   -- kasGetGrowSelectionPtrIfExists
function K_490bb0(h) return KAS_GS(KAS_HashLabel(h) or format("gs_%08x", h)) end                   -- kasGrowSelectionPtr
function K_4908c0(h) return KAS_TeamVector(KAS_HashLabel(h) or "") end                             -- kasTeamsVectorPtr
function K_490960(h) return KAS_VolumeVector(KAS_HashLabel(h) or "") end                           -- kasVolumeVectorPtr
function K_490820(sel) return KAS_ShipsVector(sel) end                                             -- kasShipsVectorPtr
function K_4909f0() return KAS_TeamVector(KAS_Team) end                                            -- kasThisTeamsVectorPtr

-- message trace (set KAS_TraceMsgs = 0 to silence)
KAS_TraceMsgs = 1
function KAS_MsgSendRaw(from, to, msg)
    if KAS_TraceMsgs == 1 then
        print("CKAS msg " .. (from or "?") .. " -> " .. (to or "?") .. " : " .. msg)
    end
    if to == "" or to == 0 then
        KAS_WarnOnce("lostmsg" .. msg, "message " .. msg .. " sent to an unknown team (lost)")
        return
    end
    KAS_MsgSendRawUntraced(from, to, msg)
end

-- ------------------------------------------------------------------ speech (Phase 0.4)
-- kasfSpeechEvent(event, variable): low 10 bits = event number (HW1 SPEECH_EVENT_MASK), higher bits pick the actor. The phrase is chosen as HW1 SEselectsentence does (cataclysmspeech.lua, generated) and played
-- with Subtitle_AddSkippable: data/sound/speech/missions/cataclysm/<id>.wav plus string <id> from speech.dat.
-- kasfIntelEventEnded (exe 0x497b00) reports 1 once the line has finished.
KAS_SpeechEnd = 0
KAS_SpeechPath = "speech:missions/cataclysm/"

function KAS_SpeechPlay(event, variable)
    if event < 0 then event = event + 4294967296 end
    local ev = mod(event, 1024)
    local e = KAS_SpeechEvents and KAS_SpeechEvents["sect" .. ev]
    if e == nil then
        KAS_WarnOnce("speech" .. ev, "no speech for event " .. ev .. " (" .. event .. ")")
        KAS_SpeechEnd = Universe_GameTime() + 1
        return
    end
    local maxvar = e[2]
    if maxvar < 1 then maxvar = 1 end
    if variable < 0 or variable >= maxvar then variable = 0 end
    local id = KAS_SpeechBankBase.sect + e[3] + variable
    -- Cataclysm actor bits (from Mission01's lines): 0x1000 Fleet Command, 0x2000 Tactical Officer, 0x8000 other
    -- fleets (allies). HWRM has no Tactical Officer actor; Fleet Intel's voice slot is the nearest match.
    local actor = Actor_HW1_FleetIntel
    if mod(floor(event / 4096), 2) == 1 then actor = Actor_HW1_FleetCommand end
    local secs = (KAS_SpeechDurations[id] or 3000) / 1000
    local t = Subtitle_AddSkippable(actor, "$" .. id, secs)
    if t and t > secs then secs = t end
    KAS_SpeechEnd = Universe_GameTime() + secs
    print("CKAS speech event " .. ev .. " -> $" .. id .. " (" .. secs .. "s)")
end

function K_496eb0(event, variable) KAS_SpeechPlay(event, variable) end                              -- kasfSpeechEvent

function K_497b00()                                                                               -- kasfIntelEventEnded
    return KAS_B(Universe_GameTime() >= KAS_SpeechEnd)
end

function K_497b80() end                                                                           -- kasfSubtitleReset

-- state-change trace (the translator emits KAS_TraceJump before each kasJump / kasFSMCreate)
function KAS_TraceJump(team, from, to)
    if KAS_TraceMsgs == 1 then print("CKAS jump " .. team .. " : " .. from .. " -> " .. to) end
end

-- ------------------------------------------------------------------ player mothership
-- exe 0x498790 (kasfGetPlayerMothership): empties the selection and adds the human player's mothership
-- (FUN_0041b090 on the computer player returns the other player's mothership). Mission01 fails the mission when
-- this selection is empty after G_ShipsHaveArrived, so every mothership type the port uses must be listed here.
KAS_MothershipTypes = { "smt_ms_sp", "smt_ms", "Kus_Mothership" }   -- Kuun-Lan (Cataclysm Remastered), Kushan stand-in

function K_498790(sel)                                                                            -- kasfGetPlayerMothership
    SobGroup_Clear(sel)
    local i = 1
    while i <= getn(KAS_MothershipTypes) do
        Player_FillShipsByType(sel, 0, KAS_MothershipTypes[i])
        if SobGroup_Count(sel) > 0 then return end
        i = i + 1
    end
end

-- ================================================================== Mission01 API (stubs implemented)
-- Distances in KAS code are HW1 units; HWRM levels are scaled by 0.35 (mission2level.py, Gearbox's HW1 port).
KAS_WorldScale = 0.35

function KAS_Dist(d) return d * KAS_WorldScale end

function KAS_HWRMType(t)
    if t == nil then return KAS_PlaceholderType end
    return KAS_ShipTypes[strlower(t)] or KAS_PlaceholderType
end

-- Log once and do nothing: HWRM has no equivalent (yet) or the function only drives HW1 UI state.
function KAS_NoOp(addr, what)
    KAS_WarnOnce("noop" .. addr, "no-op " .. addr .. " " .. what)
end

function KAS_Owner(sel) return SobGroup_GetPlayerOwner(sel) end

-- ------------------------------------------------------------------ mission / team
function K_491cb0() KAS_MissionFailed() end                                                          -- kasfMissionFailed
function K_492780() KAS_SetFormation(KAS_Team, "Delta") end                                          -- kasfFormationDelta
function K_492810() KAS_SetFormation(KAS_Team, "Claw") end                                           -- kasfFormationClaw
function K_492960(sel) SobGroup_GuardSobGroup(KAS_Team, sel) end                                     -- kasfGuardShips
function K_4929d0(path) SobGroup_FollowPath(KAS_Team, path, 1, 1, 0) end                             -- kasfPatrolPath
function K_492b20() return floor(KAS_TeamHealth(KAS_Team)) end                                      -- kasfTeamHealthAverage
function K_493aa0(pct) SobGroup_SetHealth(KAS_Team, pct / 100) end                                  -- kasfTeamSetPercentDamaged
function K_493cf0(team, sel) SobGroup_SobGroupAdd(team, sel) end                                    -- kasfReinforceTeamWithShips

-- kasfTeamCountOriginal: ship count when the team was first asked (Gearbox registers at team creation).
KAS_TeamOriginalCounts = {}
function K_493e00()
    if KAS_TeamOriginalCounts[KAS_Team] == nil then
        KAS_TeamOriginalCounts[KAS_Team] = SobGroup_Count(KAS_Team)
    end
    return KAS_TeamOriginalCounts[KAS_Team]
end

-- ------------------------------------------------------------------ orders
function K_4941a0(vec)                                                                              -- kasfMoveTo
    if SobGroup_Count(KAS_Team) > 0 then SobGroup_MoveToPoint(KAS_Owner(KAS_Team), KAS_Team, vec) end
end
function K_494750(host) SobGroup_DockSobGroupInstant(KAS_Team, host) end                            -- kasfDockInstant
function K_4947c0() KAS_Launch(KAS_Team) end                                                         -- kasfLaunch
function K_4948a0() return KAS_B(KAS_TeamFinishedLaunching(KAS_Team) ~= 0) end                      -- kasfTeamFinishedLaunching
function K_494940() return KAS_B(SobGroup_IsDockedCompletely(KAS_Team) == 1) end                   -- kasfTeamDockedReadyForLaunch
function K_495eb0()                                                                                  -- kasfStop
    if SobGroup_Count(KAS_Team) > 0 then SobGroup_Stop(KAS_Owner(KAS_Team), KAS_Team) end
end
function K_495f00() KAS_Harvest(KAS_Owner(KAS_Team), KAS_Team) end                                  -- kasfHarvest

-- ------------------------------------------------------------------ ships
function K_493980(sel, pct) SobGroup_SetDamageMultiplier(sel, pct / 100) end                        -- kasfShipsSetDamageFactor
function K_493a10(sel, v) KAS_NoOp("493a10", "kasfShipsSetRepairFactor") end
function K_4939d0(sel) KAS_NoOp("4939d0", "kasfShipsClearRepairFactor") end

-- kasfShipsParalyze (the exe sets SOF_DontApplyPhysics): the ships cannot move.
function K_4984c0(sel, on)
    if on ~= 0 then SobGroup_AbilityActivate(sel, AB_Move, 0) else SobGroup_AbilityActivate(sel, AB_Move, 1) end
end

-- kasfShipsSetColor(ships, scheme): Gearbox colour schemes when the index exists.
function K_49aae0(sel, scheme)
    if KAS_ColourSchemes and KAS_ColourSchemes[scheme] then KAS_SetColourScheme(sel, scheme)
    else KAS_NoOp("49aae0", "kasfShipsSetColor scheme " .. scheme) end
end

-- 0x497ed0(team), called right after kasfTeamSwitchPlayerOwner: per-ship engine update (FUN_0051c0b0).
function K_497ed0(sel) KAS_NoOp("497ed0", "post owner-switch ship update") end

-- 0x499870(team): 1 if any ship lacks the data at ship+0x370 (Mission01: decides whether to hunt Workers).
function K_499870(sel) return 1 end

-- 0x499c70(dst, shipType, count, nearShips, player): creates count ships of the type next to nearShips.
function K_499c70(dst, shipType, count, near, player)
    SobGroup_Clear(dst)
    if count <= 0 or SobGroup_Count(near) == 0 then return end
    local t = KAS_HWRMType(shipType)
    local i = 0
    while i < count do
        local g = SobGroup_CreateShip(near, t)
        if g and g ~= "" then SobGroup_SobGroupAdd(dst, g) end
        i = i + 1
    end
end

-- ------------------------------------------------------------------ selections
-- Source of a selection call; copied first when it is also the destination (as KAS_SelectInto does).
function KAS_SelSrc(n, o)
    if n == o then
        SobGroup_CreateIfNotExist("KAS_SelTemp")
        SobGroup_Clear("KAS_SelTemp")
        SobGroup_SobGroupAdd("KAS_SelTemp", o)
        return "KAS_SelTemp"
    end
    return o
end

function K_495690(n, o, shipType)                                                                   -- kasfShipsSelectType
    local src = KAS_SelSrc(n, o)
    SobGroup_Clear(n)
    SobGroup_FillShipsByType(n, src, KAS_HWRMType(shipType))
    return SobGroup_Count(n)
end

function K_495a50(n, o, vec, dist)                                                                  -- kasfShipsSelectNearby
    local src = KAS_SelSrc(n, o)
    SobGroup_Clear(n)
    SobGroup_FillProximityPoint(n, src, vec, KAS_Dist(dist))
    return SobGroup_Count(n)
end

-- Selections through the generic filter (FUN_00494f90) whose callback is not identified yet: keep all ships.
function KAS_SelectAll(n, o)
    local src = KAS_SelSrc(n, o)
    SobGroup_Clear(n)
    SobGroup_SobGroupAdd(n, src)
    return SobGroup_Count(n)
end
function K_4952b0(n, o)
    KAS_WarnOnce("sel4952b0", "0x4952b0 filter not identified: selecting all")
    return KAS_SelectAll(n, o)
end
function K_4985f0(n, o, v)
    KAS_WarnOnce("sel4985f0", "0x4985f0 filter not identified: selecting all")
    return KAS_SelectAll(n, o)
end

function K_498d90(dst, src) SobGroup_Clear(dst) SobGroup_SobGroupAdd(dst, src) end                -- kasfFirstShip (all, for now)
function K_49a100(sel, vec) end                                                                    -- sort by distance: order unused

-- Enemies are relative to the asking team's owner: players 0 (human) and 2 (allied Kushan) are allied, 1 is the
-- enemy (mission2level.py). Always using player 0 made teams handed to the player attack themselves.
function KAS_EnemyPlayers(owner)
    if owner == 1 then return { 0, 2 } end
    return { 1 }
end

function KAS_FillEnemiesNear(sel, centre, radius)
    SobGroup_Clear(sel)
    if SobGroup_Count(centre) == 0 then return 0 end
    SobGroup_CreateIfNotExist("KAS_EnemyTmp")
    local enemies = KAS_EnemyPlayers(SobGroup_GetPlayerOwner(centre))
    local i = 1
    while i <= getn(enemies) do
        SobGroup_Clear("KAS_EnemyTmp")
        Player_FillProximitySobGroup("KAS_EnemyTmp", enemies[i], centre, radius)
        SobGroup_SobGroupAdd(sel, "KAS_EnemyTmp")
        i = i + 1
    end
    return SobGroup_Count(sel)
end

-- kasfFindEnemyShipsInside(ships, radius) as Mission01 calls it: enemy ships within radius of this team.
function K_492e90(sel, radius) return KAS_FillEnemiesNear(sel, KAS_Team, KAS_Dist(radius)) end

-- kasfFindEnemiesInside(ships, point, radius) as Mission01 calls it: this team's enemies near the point.
function K_4931a0(sel, vec, radius)
    SobGroup_Clear(sel)
    if SobGroup_Count(KAS_Team) == 0 then return 0 end
    local enemies = KAS_EnemyPlayers(SobGroup_GetPlayerOwner(KAS_Team))
    Volume_AddSphere("KAS_FindVol", vec, KAS_Dist(radius))
    SobGroup_CreateIfNotExist("KAS_EnemyTmp")
    local i = 1
    while i <= getn(enemies) do
        SobGroup_Clear("KAS_EnemyTmp")
        Player_FillSobGroupInVolume("KAS_EnemyTmp", enemies[i], "KAS_FindVol")
        SobGroup_SobGroupAdd(sel, "KAS_EnemyTmp")
        i = i + 1
    end
    Volume_Delete("KAS_FindVol")
    return SobGroup_Count(sel)
end

-- ------------------------------------------------------------------ pings and tutorial pointers
function K_495e50(sel, name) KAS_PingRemove(name, name) KAS_PingAddShips(sel, name, name) end     -- kasfPingAddShips
-- kasfPingAddPoint(point, name): Ping_AddPoint takes a volume name (Gearbox passes AI volume names), so ping a
-- small sphere made at the point.
function K_495e80(vec, name)                                                                        -- kasfPingAddPoint
    KAS_PingRemove(name, name)
    Volume_AddSphere("KAS_Ping_" .. name, vec, 10)
    KAS_PingAddPoint("KAS_Ping_" .. name, name, name)
end
function K_495ea0(name) KAS_PingRemove(name, name) end                                            -- kasfPingRemove

KAS_Pointers = {}
function KAS_PointerSet(name, id)
    if KAS_Pointers[name] then KASPointer_Remove(KAS_Pointers[name]) end
    KAS_Pointers[name] = id
end
function K_4963a0(name, sel) KAS_PointerSet(name, KASPointer_AddShip(sel)) end                   -- kasfTutSetPointerTargetShip
function K_4963e0(name, sel) KAS_PointerSet(name, KASPointer_AddShip(sel)) end                   -- ...TargetShipSelection
function K_496490(name, vol) KAS_PointerSet(name, KASPointer_AddVolume(vol)) end                 -- ...TargetAIVolume
function K_4964b0(name, vol) KAS_PointerSet(name, KASPointer_AddVolume(vol)) end                 -- kasfTutSetObjPointerTargetAIVolume
function K_4964e0(name)                                                                          -- kasfTutRemovePointer
    if KAS_Pointers[name] then
        KASPointer_Remove(KAS_Pointers[name])
        KAS_Pointers[name] = nil
    end
end
function K_496530() KASPointer_RemoveAll() KAS_Pointers = {} end                                 -- kasfTutRemoveAllPointers
function K_496870(sel) KAS_FocusShips(sel) end                                                   -- kasfTutCameraFocus
function K_496ae0() KAS_FocusCancel() end                                                        -- kasfTutCameraFocusCancel

-- ------------------------------------------------------------------ sensors, camera, screen
function K_496bc0(flags) KAS_SensorsToggle(1, flags) end                                        -- kasfOpenSensors
function K_496c30() KAS_SensorsToggle(0, 1) end                                                  -- kasfCloseSensors
function K_496c80(flags) return KAS_B(Sensors_ManagerIsActive() == 1) end                        -- kasfSensorsIsOpen
function K_496190() return 0 end                                                                 -- kasfCameraGetAngleDeg
function K_4961f0() return 0 end                                                                 -- kasfCameraGetDeclinationDeg
function K_496250() return 0 end                                                                 -- kasfCameraGetDistance
function K_4961b0(a) KAS_NoOp("4961b0", "kasfCameraSetAngleDeg") end
function K_496210(a) KAS_NoOp("496210", "kasfCameraSetDeclinationDeg") end
function K_496260(a) KAS_NoOp("496260", "kasfCameraSetDistance") end
function K_49a2a0(vec) KAS_NoOp("49a2a0", "set focus point (sensors manager)") end
function K_497580(frames) KAS_SetLetterboxState(1, frames / 30) end                              -- kasfWideScreenIn
function K_497630(frames) KAS_SetLetterboxState(0, frames / 30) end                              -- kasfWideScreenOut
-- Fleet Intel pauses the universe and the other KAS teams while it points something out (Mission01 variables
-- PauseUniverse / UnpauseOtherKAS). Not reproduced: HWRM keeps playing during the sensors-manager reveal.
function K_497a90() KAS_NoOp("497a90", "pause universe (Fleet Intel)") end
function K_497aa0() KAS_NoOp("497aa0", "unpause universe") end
function K_497ad0() KAS_NoOp("497ad0", "pause other KAS teams") end
function K_497af0() KAS_NoOp("497af0", "unpause other KAS teams") end

-- ------------------------------------------------------------------ economy, research, trading, music
function K_496e20(player, ru) Player_SetRU(player, ru) end                                       -- kasfRUsSet
function K_496e40() return Universe_GetWorldResources() end                                      -- kasfGetWorldResources
function K_496cf0(tech) Player_UnrestrictResearchOption(0, tech) print("CKAS: research allowed " .. tech) end   -- kasfAllowPlayerToResearch
function K_496d10(tech) Player_UnrestrictResearchOption(0, tech) print("CKAS: purchase allowed " .. tech) end   -- kasfAllowPlayerToPurchase
function K_497710(i, text) KAS_NoOp("497710", "kasfSetTraderDialog") end
function K_4977a0(scale) KAS_NoOp("4977a0", "kasfSetTraderPriceScale") end
function K_497800(off) KAS_NoOp("497800", "kasfSetTraderDisabled") end
-- kasfMusicPlay(trackNum): Cataclysm stream trackNum (tools/build_music.py), 1102 = a random one of 0-16.
-- HWRM has no music stop: kasfMusicStop goes back to the previous track, as Gearbox's HW1 KAS port does.
KAS_MusicPrevious, KAS_MusicCurrent = "", ""
function K_497000(track)
    if track == 1102 then track = random(0, 16) end
    if track < 0 or track > 61 then return end
    local path = format("data:sound/music/cataclysm/music_%02d", track)
    KAS_MusicPrevious, KAS_MusicCurrent = KAS_MusicCurrent, path
    print("CKAS: music " .. path)
    Sound_MusicPlayType(path, MUS_Ambient)
end
function K_498c10(fadeTime)                                                                      -- kasfMusicStop
    if KAS_MusicPrevious ~= "" then
        KAS_MusicCurrent, KAS_MusicPrevious = KAS_MusicPrevious, ""
        Sound_MusicPlayType(KAS_MusicCurrent, MUS_Ambient)
    end
end

-- kasfEnableShipConstruction(type, race, enabled)
function K_4980c0(shipType, race, on)
    local t = KAS_ShipTypes[strlower(shipType)]
    if t == nil then return end
    if on ~= 0 then Player_UnrestrictBuildOption(0, t) else Player_RestrictBuildOption(0, t) end
end

-- 0x497290(flag, destination): end-of-mission hyperspace ("Hiigara", "~ End of Mission").
function K_497290(flag, dest)
    print("CKAS: hyperspace destination '" .. dest .. "' (" .. flag .. ") - mission end flow not ported yet")
end
