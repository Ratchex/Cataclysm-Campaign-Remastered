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
    if t.paused then return 2147483647 end      -- Timer.c: a paused timer never expires (SDWORD_Max)
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
    if label == "Hyperspace" then KAS_HyperspaceAllow() return end
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
KAS_NisAvailable["nislet01"] = 1

-- Cues: what a converted cutscene's HWRM script can't play (music: its musicStart stayed silent), as
-- { seconds after the start, kind, argument }; generated next to each NIS by tools/nis2hwrm.py
-- (data/nis/cataclysm/<name>_cues.lua, report in docs/nis/<name>.md).
KAS_NisCues = {}
KAS_NisEndsBlack = {}                 -- names of NIS that end on black (set by the cues files)
-- After an NIS that ends on black the screen stays black: the next NIS (a mission often requests one at once:
-- Mission01 n01 -> nislet01) plays from black, else the game fades in after this long.
KAS_NisGapSeconds = 3
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

function KAS_NisEndWatch()
    local h = NISGetAnyPlayingHandle()
    if h == NISHandle_Invalid or NISComplete(h) == 1 then
        if KAS_BlackSince then                -- (not if the safety net already faded in)
            Universe_Fade(1, 0)
            Camera_SetLetterboxStateNoUI(1, 0)
        end
        Rule_Remove("KAS_NisEndWatch")
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
        elseif c[2] == "hideui" then                   -- NIS ending on black, before its wideScreenOut: the HUD
            UI_SetScreenVisible("NewTaskbar", 0)          -- screen itself hidden (the letterbox alone flashed it)
            KAS_HudHidden = 1
        elseif c[2] == "noui" then                     -- NIS ending on black, after its wideScreenOut: UI hidden
            Camera_SetLetterboxStateNoUI(1, 0)
            KAS_BlackSince = Universe_GameTime()
            -- the NIS drops its black fade when it ends: black again on the very tick it does (the 0.5 s
            -- KAS_EngineTick showed a quarter second of space and UI)
            Rule_Add("KAS_NisEndWatch")
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
            -- HW1 SinglePlayer.c: no centre ship in the NIS -> played about the world origin, unrotated (nislet01's
            -- battle is in the level's own coordinates; nis2hwrm and mission2level map positions the same way)
            print("CKAS: " .. path .. " has no " .. SobGroup_GetShipType("KAS_NisCentre") .. ": played at the origin")
        end
    end
    KAS_FadeInAt = nil                    -- black between two NIS: the new one does its own fade in
    NISPlayFromCoordSys(path, position, nisMatrix)
    KAS_NisCuesStart(name)
    print("CKAS: playing " .. path .. " at {" .. position[1] .. ", " .. position[2] .. ", " .. position[3] .. "}")
    return 1
end

-- Play a cutscene; when it ends set KAS variable `key` (may be nil) and call `after` (may be nil).
function KAS_NisPlay(name, key, after)
    KAS_NisPending = { name = name, key = key, after = after, playing = 1, started = Universe_GameTime() }
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
        KAS_FleetCapture()
        KAS_NisPlay(name, nil, KAS_IntroDone)  -- first: it centres on the Kuun-Lan, despawned just after
        if KAS_FleetAwaitHyperspace() == nil then KAS_IntroHidden = 1 SobGroup_SetHidden("Player_Ships0", 1) end
    else
        KAS_FleetCapture()
        KAS_FleetAwaitHyperspace()
        start()
    end
end

function KAS_IntroDone()
    if KAS_IntroHidden then KAS_IntroHidden = nil SobGroup_SetHidden("Player_Ships0", 0) end
    KAS_IntroStart()
end

function KAS_NisFinished()
    local p = KAS_NisPending
    local now = Universe_GameTime()
    if p.playing == nil then return now >= p.at end
    if now - p.started < 2 then return nil end
    local h = NISGetAnyPlayingHandle()
    if KAS_BlackSince then                -- safety net: an NIS that ends black but never completes
        if now - KAS_BlackSince > 15 then
            print("CKAS: NIS did not end 15 s after the black cue: fading in")
            KAS_BlackSince = nil
            Universe_Fade(0, 1)
            Camera_SetLetterboxStateNoUI(0, 1)
            if KAS_HudHidden then
                KAS_HudHidden = nil
                UI_SetScreenVisible("NewTaskbar", 1)
            end
        end
    end
    if h == NISHandle_Invalid then return 1 end
    if NISComplete(h) == 1 then return 1 end
    return now - p.started > 600
end

function KAS_EngineTick()
    local now = Universe_GameTime()
    if KAS_AlliancesDone == nil then
        KAS_AlliancesDone = 1
        KAS_ApplyAlliances()
        KAS_FreezeSensorArrays()
    end
    KAS_PatrolTick()
    if KAS_ROEAt == nil or now >= KAS_ROEAt then
        KAS_ROEAt = now + 5
        KAS_TeamsDefensive()
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
        KAS_BlackSince = nil
        if p.name and KAS_NisEndsBlack[p.name] then
            Universe_Fade(1, 0)
            Camera_SetLetterboxStateNoUI(1, 0)
            KAS_FadeInAt = now + KAS_NisGapSeconds
        end
        if p.key then KAS_Vars[p.key] = 1 end
        print("CKAS: cutscene complete")
        if p.after then p.after() end
    end
    if KAS_FadeInAt and KAS_NisPending == nil and now >= KAS_FadeInAt then
        KAS_FadeInAt = nil
        Universe_Fade(0, 1.5)
        Camera_SetLetterboxStateNoUI(0, 1.5)
        if KAS_HudHidden then
            KAS_HudHidden = nil
            UI_SetScreenVisible("NewTaskbar", 1)
        end
        print("CKAS: fade in after the cutscenes")
    end
    if KAS_ShipsArriveAt and now >= KAS_ShipsArriveAt then
        KAS_ShipsArriveAt = nil
        KAS_Vars[KAS_Key_ShipsHaveArrived] = 1
        print("CKAS: G_ShipsHaveArrived")
    end
end

-- kasfStartLevelByHyperspacingShips (every Cataclysm mission calls it): the SP flow (exe FUN_005197d0 state 9)
-- hyperspaces the player's fleet in at StartPointPlayer, then sets G_ShipsHaveArrived. Here the Kuun-Lan arrives
-- with the small ships docked and launches them once out of hyperspace (user: "warp in and undock"). Until then the
-- fleet is out of the universe: docked and despawned at mission start (KAS_FleetAwaitHyperspace), as Gearbox's
-- kasTeamHyperspaceOut does at frame 0, and brought in with SobGroup_HyperspaceTo as their kasTeamHyperspaceIn.
-- The player's real fleet, taken before any NIS starts: an NIS's ships belong to the player too (n01's Kuun-Lan
-- copy was despawned and its Recon / Workers docked away when this ran after it started)
function KAS_FleetCapture()
    SobGroup_CreateIfNotExist("KAS_ArrivalMS")
    K_498790("KAS_ArrivalMS")
    SobGroup_CreateIfNotExist("KAS_ArrivalDocked")
    SobGroup_Clear("KAS_ArrivalDocked")
    SobGroup_FillSubtract("KAS_ArrivalDocked", "Player_Ships0", "KAS_ArrivalMS")
end

function KAS_FleetAwaitHyperspace()
    if SobGroup_Count("KAS_ArrivalMS") == 0 then return nil end
    SobGroup_DockSobGroupInstant("KAS_ArrivalDocked", "KAS_ArrivalMS")
    KAS_ArrivalPlaceBehind()
    SobGroup_Despawn("KAS_ArrivalMS")
    KAS_FleetWaiting = 1
    print("CKAS: fleet waits in hyperspace (" .. SobGroup_Count("KAS_ArrivalDocked") .. " ships docked)")
    return 1
end

-- camera distance from the Kuun-Lan's centre on arrival: KAS_ArrivalCamera's (mission2level ARRIVAL_*; 3700 was too
-- far, 2200 a little (user, Mission01: zoom in a bit))
KAS_ArrivalCameraDistance = 1760

-- The Kuun-Lan's heading on arrival: SobGroup_HyperspaceTo ignores the start point's rotation, and the exit flies it
-- in along its line from where it was (despawned on the start point itself: no line, so bow +Z, and turning it by
-- script was steered back: user). So it waits in hyperspace KAS_ArrivalBack behind the start point, opposite the
-- way it should face (KAS_ArrivalYaw degrees left of +Z: the mission's, build_mission.py ARRIVAL_YAW; Mission01:
-- straight away from the sensor net, user)
KAS_ArrivalBack = 5000
function KAS_ArrivalPlaceBehind()
    if KAS_ArrivalYaw == nil or KAS_ArrivalYaw == 0 then return end
    local p = Volume_GetPosition("StartPointPlayer")
    if p == nil then return end
    local d = KAS_ArrivalBack
    SobGroup_SetPosition("KAS_ArrivalMS", { p[1] - d * sin(KAS_ArrivalYaw), p[2], p[3] - d * cos(KAS_ArrivalYaw) })
end

-- the Kuun-Lan's bow in the log (checking the arrival turn)
function KAS_LogBow(when)
    if KAS_ArrivalYaw == nil or KAS_ArrivalYaw == 0 or SobGroup_Count("KAS_ArrivalMS") == 0 then return end
    local m = SobGroup_GetCoordSys("KAS_ArrivalMS")
    if m and getn(m) == 9 then
        print(format("CKAS: Kuun-Lan bow %s: (%.2f, %.2f, %.2f) (wanted (%.2f, 0, %.2f))", when, m[7], m[8], m[9],
                     sin(KAS_ArrivalYaw), cos(KAS_ArrivalYaw)))
    end
end

function K_498230()
    if KAS_FleetWaiting == nil then           -- no Kuun-Lan held back: only the signal
        KAS_ShipsArriveAt = Universe_GameTime() + 3
        return
    end
    KAS_FleetWaiting = nil
    SobGroup_HyperspaceTo("KAS_ArrivalMS", "StartPointPlayer")
    if KAS_OpeningLock == 1 then KAS_Lockout(1) end

    SobGroup_SetHidden("KAS_ArrivalMS", 0)
    Camera_UseCameraPoint("KAS_ArrivalCamera")    -- mission2level.py: below the port bow, looking up
    KAS_ArrivalStarted = Universe_GameTime()
    Rule_AddInterval("KAS_ArrivalWatch", 0.5)
    print("CKAS: fleet hyperspacing in at StartPointPlayer")
end

-- out of hyperspace (the Kuun-Lan idle again, as Gearbox's singlePlayerWatchHyperspaceComplete): launch, arrived
function KAS_ArrivalWatch()
    local t = Universe_GameTime() - KAS_ArrivalStarted
    if KAS_ArrivalFocused == nil then
        -- the camera point is fixed: focus it on the Kuun-Lan (now spawned) so it follows the ship, at the camera
        -- point's distance (Gearbox's hyperspace focus call). Camera_FocusSobGroup(g, 0, 0, 0) zoomed right in:
        -- the start view stayed at the hangar however far out the camera point was put (1x, 2x, 6x)
        KAS_ArrivalFocused = 1
        Camera_FocusSobGroupWithBuffer("KAS_ArrivalMS", KAS_ArrivalCameraDistance, 0, 0)
    end
    if t < 2 then return end
    if SobGroup_GetCurrentOrder("KAS_ArrivalMS") ~= COMMAND_Idle and t < 30 then return end
    Rule_Remove("KAS_ArrivalWatch")
    if KAS_ArrivalYaw and KAS_ArrivalYaw ~= 0 then Rule_AddInterval("KAS_ArrivalBowLog", 2) end
    KAS_Autolaunch()
    KAS_Vars[KAS_Key_ShipsHaveArrived] = 1
    print("CKAS: fleet out of hyperspace after " .. t .. "s; launching " .. SobGroup_Count("KAS_ArrivalDocked")
          .. " ships; G_ShipsHaveArrived")
end

KAS_ArrivalBowLogs = 0
function KAS_ArrivalBowLog()
    KAS_ArrivalBowLogs = KAS_ArrivalBowLogs + 1
    KAS_LogBow("+" .. (2 * KAS_ArrivalBowLogs) .. "s after the exit")
    if KAS_ArrivalBowLogs >= 5 then Rule_Remove("KAS_ArrivalBowLog") end
end

-- Every Cataclysm mission starts with Fleet Command's "Autolaunch set" and the docked ships flying out into the
-- Kuun-Lan's parade (user). HW1's arrival (SinglePlayer.c HYPERSPACE_SHIPSARRIVING): clAutoLaunch turns autolaunch
-- back on, launching everything inside with the line; each launched ship joins the parade round the ship it left
-- (CommandLayer.c GroupShip), as HWRM's launches do on their own: Cataclysm's layout is the Kuun-Lan's paradeData
-- (tools/make_parade.py). Cataclysm's line is its event 104 ("auto launch set"; out/speech_text_sect.tsv), not
-- HW1's 169 (Cataclysm's: "Swarmer is locked on", user).
KAS_AUTOLAUNCH_EVENT = 104 + 4096         -- (KAS_SpeechPlay: 0x1000 = Fleet Command)
function KAS_Autolaunch()
    SobGroup_SetAutoLaunch("KAS_ArrivalMS", ShipHoldLaunch)
    if SobGroup_Count("KAS_ArrivalDocked") == 0 then return end
    SobGroup_Launch("KAS_ArrivalDocked", "KAS_ArrivalMS")
    KAS_SpeechPlay(KAS_AUTOLAUNCH_EVENT, 0)
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
-- DEVELOPMENT ONLY: research the missions don't allow yet, unlocked for testing a later mission's mechanics
-- (keep empty in commits that aren't a test)
KAS_DevTechs = {}
KAS_DevModules = {}     -- ...and the Kuun-Lan modules they need (e.g. { "smt_kl_weapons" } for TECH_MISSILE)

function KAS_RestrictTechs()
    if KAS_Techs == nil then return end
    local i = 1
    while i <= getn(KAS_Techs) do
        Player_RestrictResearchOption(0, KAS_Techs[i])
        i = i + 1
    end
    i = 1
    while i <= getn(KAS_DevTechs) do
        Player_UnrestrictResearchOption(0, KAS_DevTechs[i])
        print("CKAS: DEV research unlocked " .. KAS_DevTechs[i])
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
    i = 1
    while i <= getn(KAS_DevModules) do
        SobGroup_CreateSubSystem("KAS_KuunLan", KAS_DevModules[i])
        print("CKAS: DEV module " .. KAS_DevModules[i])
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

-- Cataclysm's proximity sensor arrays (Mission01's Kushan picket) are never ordered anywhere and hold position; in
-- HWRM the stock kus_proximitysensor drifted off with no order given, so non-player sensors lose their engines, and
-- are shown deployed.
KAS_SensorTypes = { "kus_proximitysensor", "tai_proximitysensor" }
function KAS_FreezeSensorArrays()
    SobGroup_CreateIfNotExist("KAS_Sensors")
    local p = 1
    while p < Universe_PlayerCount() do
        local i = 1
        while i <= getn(KAS_SensorTypes) do
            SobGroup_Clear("KAS_Sensors")
            SobGroup_FilterInclude("KAS_Sensors", "Player_Ships" .. p, "ShipType", KAS_SensorTypes[i])
            if SobGroup_Count("KAS_Sensors") > 0 then
                SobGroup_AbilityActivate("KAS_Sensors", AB_Move, 0)
                -- deployed, panels open (kus_proximitysensor.madstate Open; user: the sensor net in its deployed look)
                SobGroup_SetMadState("KAS_Sensors", "Open")
                print("CKAS: " .. SobGroup_Count("KAS_Sensors") .. " " .. KAS_SensorTypes[i] .. " of player " .. p .. " hold position")
            end
            i = i + 1
        end
        p = p + 1
    end
end

-- Ships of KAS teams (the computer, player 1, and the allies, player 2) attack what the mission orders and defend
-- themselves; HWRM's default offensive ROE sent them after anything they saw (the picket's interceptors and the
-- flank bombers / ion frigates ended up in the capital ship battle, which Mission01's dialogue keeps apart).
-- Defensive ROE (1) on every non-player ship, again every 5 s for ships that arrive later.
function KAS_TeamsDefensive()
    local p = 1
    while p < Universe_PlayerCount() do
        SobGroup_SetROE("Player_Ships" .. p, 1)
        p = p + 1
    end
end

-- HWRM runs its skirmish AI for every computer player unless told not to (Gearbox's KAS_CPUPlayerInit: player 1
-- KAS-controlled, player 2 the human's allies, both CPU_Enable(p, 0)). Left on, it ran the Taiidan and the Kushan
-- alongside the mission: attack-moves (order 20) nobody scripted sent the picket's interceptor wings across the map.
function KAS_DisableCPUPlayers()
    local p = 1
    while p < Universe_PlayerCount() do
        CPU_Enable(p, 0)
        p = p + 1
    end
end

-- Cataclysm's RU trickle (resource.script, every player): regenerateRUs 25 every regenerateRUrate 255 frames
-- (+1: the check is frame & 255, at HW1's 16 frames/s: 16 s) while the player has under regenerateRUsIfUnder 400.
KAS_RU_REGEN, KAS_RU_REGEN_UNDER, KAS_RU_REGEN_SECONDS = 25, 400, 256 / 16
function KAS_RURegen()
    local p = 0
    while p < Universe_PlayerCount() do
        local ru = Player_GetRU(p)
        if ru < KAS_RU_REGEN_UNDER then Player_SetRU(p, ru + KAS_RU_REGEN) end
        p = p + 1
    end
end

-- Cataclysm's button abilities (tools/make_abilities.py: those that aren't a ship's one native CustomCommand): a
-- press puts the human's selected ships in cat_cmd_<name> for their rules (data/scripts/cataclysm/shiprules.lua,
-- which also check the ship is still selected) and empties it a second later; a button shows only while the
-- human's selection has a ship that can use it.
dofilepath("data:scripts/cataclysm/abilities_gen.lua")
CatAbilityPressed, CatAbilityShown = {}, {}
CAT_ABILITY_HOLD = 1.0      -- over shiprules.lua CAT_TICK (0.5 s), so every selected ship sees the press

function CatAbility_OwnSelection(grp)
    SobGroup_CreateIfNotExist(grp)
    SobGroup_Clear(grp)
    SobGroup_FilterInclude(grp, MainUI_CurrentSelection(), "PlayerOwner", "0")
    return grp
end

-- Menus (the Mimic's "Select Mimic Type"): a button with opens = <menu> shows / hides the buttons with menu = <menu>
-- (no ship action); pressing one of those closes the menu
CatMenuOpen = {}

function CatAbility_Find(name)
    for i = 1, getn(CatAbilities) do
        if CatAbilities[i].name == name then return CatAbilities[i] end
    end
    return nil
end

function CatAbility(name)
    local a = CatAbility_Find(name)
    if a and a.opens ~= "" then
        if CatMenuOpen[a.opens] then CatMenuOpen[a.opens] = nil else CatMenuOpen[a.opens] = 1 end
        return
    end
    if a and a.menu ~= "" then CatMenuOpen[a.menu] = nil end
    local grp = "cat_cmd_" .. name
    SobGroup_CreateIfNotExist(grp)
    SobGroup_Clear(grp)
    SobGroup_SobGroupAdd(grp, CatAbility_OwnSelection("cat_cmd_own"))
    CatAbilityPressed[name] = Universe_GameTime()
    print("CKAS: ability " .. name .. " pressed, " .. SobGroup_Count(grp) .. " ships in the selection")
end

-- 1 if the selection shares a ship with the named group (abilities_gen.lua group: the disguised Mimics)
function CatAbility_SelectionIn(sel, grp)
    SobGroup_CreateIfNotExist(grp)
    SobGroup_CreateIfNotExist("cat_sel_in")
    SobGroup_Clear("cat_sel_in")
    SobGroup_FillIntersect("cat_sel_in", sel, grp)
    if SobGroup_Empty("cat_sel_in") == 0 then return 1 end
    return 0
end

function CatAbilityTick()
    local now, sel = Universe_GameTime(), CatAbility_OwnSelection("cat_sel_own")
    -- a menu closes once the selection has nothing that could open it
    for i = 1, getn(CatAbilities) do
        local a = CatAbilities[i]
        if a.opens ~= "" and CatMenuOpen[a.opens] and
           (SobGroup_Count(sel) == 0 or SobGroup_AreAnyOfTheseTypes(sel, a.types) == 0) then
            CatMenuOpen[a.opens] = nil
        end
    end
    for i = 1, getn(CatAbilities) do
        local a = CatAbilities[i]
        if a.native == 0 then
            local t = CatAbilityPressed[a.name]
            if t and now - t > CAT_ABILITY_HOLD then
                SobGroup_Clear("cat_cmd_" .. a.name)
                CatAbilityPressed[a.name] = nil
            end
            local show = 0
            if SobGroup_Count(sel) > 0 and SobGroup_AreAnyOfTheseTypes(sel, a.types) == 1 and
               (a.tech == "" or Player_HasResearch(0, a.tech) == 1) and (a.menu == "" or CatMenuOpen[a.menu]) and
               (a.group == nil or a.group == "" or CatAbility_SelectionIn(sel, a.group) == 1) then
                show = 1
            end
            if CatAbilityShown[a.name] ~= show then
                UI_SetElementVisible("NewTaskbar", "btnCat_" .. a.name, show)
                CatAbilityShown[a.name] = show
            end
        end
    end
end

-- research the player starts the mission with (the mission's KAS_StartResearch, build_mission.py START_RESEARCH;
-- after KAS_RestrictTechs): Mission01's fighter drive (user)
function KAS_GrantStartResearch()
    if KAS_StartResearch == nil then return end
    local i = 1
    while i <= getn(KAS_StartResearch) do
        Player_UnrestrictResearchOption(0, KAS_StartResearch[i])
        Player_GrantResearchOption(0, KAS_StartResearch[i])
        print("CKAS: start research " .. KAS_StartResearch[i])
        i = i + 1
    end
end

-- engine abilities our upgrade system switches per ship (tools/make_race.py RUNTIME_RESEARCH, KAS_RuntimeResearch in
-- cataclysmtech.lua): granted to the human
function KAS_GrantRuntimeResearch()
    local i = 1
    while i <= getn(KAS_RuntimeResearch) do
        Player_GrantResearchOption(0, KAS_RuntimeResearch[i])
        i = i + 1
    end
end

-- Ship type variants (tools/ship_variants.py, variants_gen.lua): a weapon-upgrade copy of a type. Mission scripts
-- selecting the base type get its variants too (KAS_FillShipsByType); once a variant's research is done the build
-- list offers it instead of the base (KAS_VariantBuildWatch), unless the mission has the base's construction off.
dofilepath("data:scripts/cataclysm/variants_gen.lua")
KAS_ConstructionOff = {}
-- Damage-factor copies (tools/make_variants.py: <type>_d<pct>, weaker weapons, placed by the level for teams whose
-- kasfShipsSetDamageFactor HWRM's multiplier can't give): selected with their base type too.
dofilepath("data:scripts/cataclysm/variants_damage_gen.lua")
KAS_DamageCopies = {}
for copy, v in CatDamageVariants do
    if KAS_DamageCopies[v[1]] == nil then KAS_DamageCopies[v[1]] = {} end
    tinsert(KAS_DamageCopies[v[1]], copy)
end

function KAS_FillShipsByType(n, src, t)
    SobGroup_FillShipsByType(n, src, t)
    local d = KAS_DamageCopies[strlower(t)]
    if d then
        SobGroup_CreateIfNotExist("KAS_VariantTemp")
        local j = 1
        while j <= getn(d) do
            SobGroup_Clear("KAS_VariantTemp")
            SobGroup_FillShipsByType("KAS_VariantTemp", src, d[j])
            SobGroup_SobGroupAdd(n, "KAS_VariantTemp")
            j = j + 1
        end
    end
    local v = CatVariants and CatVariants[t]
    if v == nil then return end
    SobGroup_CreateIfNotExist("KAS_VariantTemp")
    local i = 1
    while i <= getn(v) do
        SobGroup_Clear("KAS_VariantTemp")
        SobGroup_FillShipsByType("KAS_VariantTemp", src, v[i].type)
        SobGroup_SobGroupAdd(n, "KAS_VariantTemp")
        i = i + 1
    end
end

function KAS_VariantBuildWatch()
    for base, list in CatVariants do
        local i, upgraded = 1, nil
        while i <= getn(list) do
            if Player_HasResearch(0, list[i].tech) == 1 then upgraded = list[i].type end
            i = i + 1
        end
        if upgraded then
            Player_RestrictBuildOption(0, base)
            if KAS_ConstructionOff[base] then Player_RestrictBuildOption(0, upgraded)
            else Player_UnrestrictBuildOption(0, upgraded) end
        end
    end
end

-- Cataclysm's team colours (tools/make_colours.py): the 8 colour schemes into Gearbox's KAS_ColourSchemes, then each
-- team in its mission's scheme (KAS_TeamSchemes, tools/mission2level.py: the Ships lines' colorScheme(n));
-- kasfShipsSetColor (K_49aae0) uses the same table
dofilepath("data:scripts/scar/cataclysmcolours.lua")
function KAS_ApplyColourSchemes()
    for n, s in CatColourSchemes do KAS_SetColourSchemeColours(n, s[1], s[2], s[3], s[4], s[5]) end
    if KAS_TeamSchemes == nil then return end
    local count = 0
    for team, n in KAS_TeamSchemes do
        if SobGroup_Exists(team) == 1 and SobGroup_Count(team) > 0 then
            KAS_SetColourScheme(team, n)
            count = count + 1
        end
    end
    print("CKAS: colour schemes on " .. count .. " teams")
end

-- The Somtaaw announcer: the speech logic's raceHelper() picks the announcer by Race_ID[currentRace], read from
-- player:racelist.lua, which Players Patch writes only from its skirmish rules (SpeechRaceHelper); write it here too,
-- so the campaign's list has the Somtaaw (install_cr.py patches raceHelper: Somtaaw -> "cat_fleet", Cataclysm's
-- Fleet Command, data/soundscripts/cataclysm/catspeech.lua)
dofilepath("data:scripts/playerspatch_speech_util.lua")

-- TRACE (user: Mission01's Kushan fleet still wiped out): every 15 s each team's ships, average health and how many
-- are damage copies (tools/make_variants.py), in the log ("CKAS battle")
KAS_BattleReport = 0             -- (on: the 15 s team report in the log)
KAS_BattleStart = nil
function KAS_BattleTick()
    if KAS_BattleStart == nil then KAS_BattleStart = Universe_GameTime() end
    SobGroup_CreateIfNotExist("KAS_BattleCopies")
    local i = 0
    while KASNumberTeams and i < KASNumberTeams do
        local t = KASTeams[i]
        local n = SobGroup_Count(t)
        if n > 0 then
            local copies = 0
            for copy, _ in CatDamageVariants do
                SobGroup_Clear("KAS_BattleCopies")
                SobGroup_FillShipsByType("KAS_BattleCopies", t, copy)
                copies = copies + SobGroup_Count("KAS_BattleCopies")
            end
            print("CKAS battle t+" .. floor(Universe_GameTime() - KAS_BattleStart) .. " " .. t .. ": " .. n ..
                  " ships, health " .. floor(SobGroup_HealthPercentage(t) * 100) .. "%, copies " .. copies)
        end
        i = i + 1
    end
end

function KAS_StartEngine()
    Rule_AddInterval("KAS_RecordTeamCounts", 1)
    if KAS_BattleReport == 1 then Rule_AddInterval("KAS_BattleTick", 15) end
    SpeechRaceHelper()
    KAS_ApplyColourSchemes()
    Rule_AddInterval("CatAbilityTick", 0.25)
    Rule_AddInterval("CatSayTick", 0.5)
    Rule_AddInterval("KAS_VariantBuildWatch", 2)
    KAS_GrantRuntimeResearch()
    KAS_DisableCPUPlayers()
    KAS_ApplyAlliances()
    KAS_RestrictTechs()
    KAS_GrantStartResearch()
    singlePlayerHyperspaceButtonDisable()     -- (Gearbox's singlePlayerStartGame): shown by K_497290
    Rule_AddInterval("KAS_EngineTick", 0.5)
    Rule_AddInterval("KAS_RURegen", KAS_RU_REGEN_SECONDS)
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
    KAS_EndPatrol()
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
-- kasfShipsSelectEnemy / kasfShipsSelectFriendly (exe 0x495560 / 0x495620: filter 0x495580 mode 0 / 1). Absolute
-- sides, not relative to the team: "enemy" = ships of the human player (in Cataclysm the Kushan too, once switched
-- to the human; here player 0 and the allied player 2), "friendly" = the computer's (player 1). Mission01 fills its
-- Enemy / FRIENDLY selections with them; the Taiidan raiders look for kProximitySensor in Enemy (the picket). These
-- were taken for "select capital / non-capital": the raiders found no sensors and went for capital ships, with the
-- picket's interceptors chasing them.
function KAS_FillByOwners(newShips, orig, owners)
    SobGroup_CreateIfNotExist("KAS_OwnerTmp")
    local i = 1
    while i <= getn(owners) do
        SobGroup_Clear("KAS_OwnerTmp")
        SobGroup_FilterInclude("KAS_OwnerTmp", orig, "PlayerOwner", "" .. owners[i])
        SobGroup_SobGroupAdd(newShips, "KAS_OwnerTmp")
        i = i + 1
    end
    return SobGroup_Count(newShips)
end
function KAS_FillHumanSide(newShips, orig) return KAS_FillByOwners(newShips, orig, { 0, 2 }) end
function KAS_FillComputerSide(newShips, orig) return KAS_FillByOwners(newShips, orig, { 1 }) end
function K_495560(n, o) return KAS_SelectInto(n, o, KAS_FillHumanSide) end                         -- kasfShipsSelectEnemy
function K_495620(n, o) return KAS_SelectInto(n, o, KAS_FillComputerSide) end                      -- kasfShipsSelectFriendly

-- Cataclysm's kasfTeamSwitchPlayerOwner takes the new owner (HW1's had none): Mission01 hands allied Kushan teams
-- to player 0 this way.
-- exe 0x493f80 toggles each ship: player-owned -> computer player, anything else -> human player. HWRM SobGroups
-- drop ships that change owner unless their switch-owner flag is cleared (Gearbox's KASSobGroup_Create does this),
-- which emptied the team and made e.g. the proximity array report itself destroyed.
-- Cataclysm starts every mission team with the computer (its .mission files have no owner) and Mission01 switches
-- the Kushan teams to the human at their start, then flags them (K_497ed0) so they stay KAS-driven. HWRM has a
-- third player for that: the level gives allies to player 2 (mission2level.py), allied with the player and not
-- under the player's control. So "to the human" is player 2 here when the level has one; an allied team's first
-- switch is the one the level already made, a second one turns it back to the computer (hostile), as in Cataclysm.
-- Switching allies to player 0 put them in the player's hands, recoloured the picket and let the arrival code dock
-- and launch it with the fleet (it then flew off).
KAS_TeamSwitched = {}
function KAS_AllyPlayer()
    if Universe_PlayerCount() > 2 then return 2 end
    return 0
end
function K_494160(flag)                                                                              -- kasfTeamSwitchPlayerOwner
    SobGroup_SetSwitchOwnerFlag(KAS_Team, 0)
    if SobGroup_Count(KAS_Team) == 0 then return end
    local owner = SobGroup_GetPlayerOwner(KAS_Team)
    local to = 1
    if owner == 1 then
        to = KAS_AllyPlayer()
    elseif owner == 2 and KAS_TeamSwitched[KAS_Team] == nil then
        to = 2
    end
    KAS_TeamSwitched[KAS_Team] = 1
    if to ~= owner then SobGroup_SwitchOwner(KAS_Team, to) end
    print("CKAS: team " .. KAS_Team .. " owner " .. owner .. " -> " .. to)
end

-- kasfResetShipRenderFlags: clears per-ship "has been rendered" bits used by kasfRenderedShips; no HWRM state.
-- kasfShipsUpgrade (named kasfResetShipRenderFlags in the first API pass; 0x498c70 runs FUN_00514490, the instant
-- upgrade, on each ship): the ships' rules upgrade them (shiprules.lua CatUpgrade_Instant) while they are in
-- cat_kas_upgrade, emptied two seconds later (over their 0.5 s tick)
function K_498c70(sel)
    SobGroup_CreateIfNotExist("cat_kas_upgrade")
    SobGroup_SobGroupAdd("cat_kas_upgrade", sel)
    KAS_KasUpgradeAt = Universe_GameTime()
    if Rule_Exists("KAS_KasUpgradeClear") == 0 then Rule_AddInterval("KAS_KasUpgradeClear", 1) end
end
function KAS_KasUpgradeClear()
    if Universe_GameTime() - KAS_KasUpgradeAt < 2 then return end
    SobGroup_Clear("cat_kas_upgrade")
    Rule_Remove("KAS_KasUpgradeClear")
end

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

-- Barks the engine's speech logic can't trigger (data/soundscripts/cataclysm/catspeech.lua covers the rest): Link /
-- Unlink from the ship rules, "<technology> available" on research. Same phrase files as KAS_SpeechPlay, but they
-- don't hold up the mission's dialogue (KAS_SpeechEnd untouched). Variable = the speaking ship's Cataclysm ShipType /
-- the TechnologyType (catspeech_gen.lua CatSpeech_Var / CatSpeech_TechLine, tools/make_unitspeech.py).
dofilepath("data:soundscripts/cataclysm/catspeech_gen.lua")
CatSayEvents = {156, 157, 165, 166, 167, 168, 5}   -- Link, Unlink, mimic, unmimic, kamikaze, disguise assumed, the Ram order (attack; shiprules.lua CatSay: cat_say_<event>)
CatSayLast = 0
CatTechHad = nil

function KAS_SpeechBark(ev, variable, actor)
    local e = KAS_SpeechEvents and KAS_SpeechEvents["sect" .. ev]
    if e == nil or variable == nil or variable < 0 or variable >= e[2] then
        return
    end
    -- one of the event's recordings at random (Cataclysm's variations: e[1] of them, e[2] apart; user: the
    -- kamikaze scream was always the first), of those this variable has (a duration: the recording exists)
    local ids = {}
    for v = 0, e[1] - 1 do
        local i = KAS_SpeechBankBase.sect + e[3] + v * e[2] + variable
        if KAS_SpeechDurations[i] then tinsert(ids, i) end
    end
    local id = KAS_SpeechBankBase.sect + e[3] + variable
    if getn(ids) > 0 then id = ids[random(1, getn(ids))] end
    Subtitle_AddSkippable(actor or Actor_HW1_FleetIntel, "$" .. id, (KAS_SpeechDurations[id] or 2000) / 1000)
    print("CKAS bark " .. ev .. "/" .. variable .. " -> $" .. id)
end

function CatSayTick()
    local now = Universe_GameTime()
    for i = 1, getn(CatSayEvents) do
        local grp = "cat_say_" .. CatSayEvents[i]
        if SobGroup_Exists(grp) == 1 and SobGroup_Count(grp) > 0 then
            if now - CatSayLast > 1.5 then      -- one bark per press, however many ships
                local t = strlower(SobGroup_GetShipType(grp))
                if CatSpeech_Var[t] == nil and CatVariantBase and CatVariantBase[t] then t = CatVariantBase[t] end
                KAS_SpeechBark(CatSayEvents[i], CatSpeech_Var[t])   -- a disguise speaks as its Mimic
                CatSayLast = now
            end
            SobGroup_Clear(grp)
        end
    end
    -- technology lines (the Tactical Officer): when the human gains such a research (not for what it starts the
    -- mission with), after Fleet Command's "Research completed." has finished plus a short pause (user)
    local first = CatTechHad == nil
    if first then CatTechHad = {} end
    for tech, v in CatSpeech_TechLine do
        local has = Player_HasResearch(0, tech)
        if not first and has == 1 and CatTechHad[tech] ~= 1 then
            tinsert(CatTechQueue, { at = now + CatResearchCompleteSecs() + CAT_TECH_LINE_GAP, v = v })
        end
        CatTechHad[tech] = has
    end
    local k = 1
    while k <= getn(CatTechQueue) do
        if now >= CatTechQueue[k].at then
            KAS_SpeechBark(188, CatTechQueue[k].v, Actor_HW1_FleetIntel)   -- Tactical Officer (as KAS_SpeechPlay)
            tremove(CatTechQueue, k)
        else
            k = k + 1
        end
    end
end

CatTechQueue = {}
CAT_TECH_LINE_GAP = 1.0   -- seconds of silence between "Research completed." and the technology line

-- length of Fleet Command's "Research completed." (event 51, the line catspeech.lua plays for it)
function CatResearchCompleteSecs()
    local e = KAS_SpeechEvents and KAS_SpeechEvents["sect51"]
    if e == nil then return 1.5 end
    return (KAS_SpeechDurations[KAS_SpeechBankBase.sect + e[3]] or 1500) / 1000
end

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
    KAS_PlayerMothership(sel, 0)          -- (the real one: not an NIS's despawned copy)
end

-- ================================================================== Mission01 API (stubs implemented)
-- Distances in KAS code are HW1 units; HWRM levels are scaled by mission2level.py SCALE (Gearbox's 0.35 x MAP_SPREAD
-- 1.5: a bigger map, ships unchanged). Keep the two equal.
KAS_WorldScale = 0.525

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
-- Formations: a strike group of the ships the team has in space; a team still launching (Mission01's first pester
-- wing, user: not in delta like the second) gets it again once it has launched (K_4948a0).
-- Ships just out of a hangar ignored it (the first wing asked one state after launching): formed again 3 and 8 s on.
KAS_TeamFormation = {}
KAS_FormAgain = {}
function KAS_Form(name)
    KAS_TeamFormation[KAS_Team] = name
    KAS_SetFormation(KAS_Team, name)
    local t = Universe_GameTime()
    KAS_FormAgain[KAS_Team] = { t + 3, t + 8 }
    if Rule_Exists("KAS_FormAgainTick") == 0 then Rule_AddInterval("KAS_FormAgainTick", 1) end
end
function KAS_FormAgainTick()
    local t = Universe_GameTime()
    for team, at in KAS_FormAgain do
        if SobGroup_Count(team) == 0 then
            KAS_FormAgain[team] = nil
        elseif at[1] and t >= at[1] then
            KAS_SetFormation(team, KAS_TeamFormation[team])
            if at[2] then KAS_FormAgain[team] = { at[2] } else KAS_FormAgain[team] = nil end
        end
    end
end
function K_492780() KAS_Form("Delta") end                                                            -- kasfFormationDelta
function K_492810() KAS_Form("Claw") end                                                             -- kasfFormationClaw
-- kasfGuardShips (HW1 aimCreateGuardShips: the protect command, the guards around the guarded ships). HWRM's guard
-- order only trails them (user: Mission01's carrier defenders should hold a sphere round the carrier): each guard
-- ship is sent to its own point on a sphere of KAS_GuardRadius round them (KAS_GuardTick), and with an enemy within
-- KAS_GuardAlarm of them the team takes HWRM's guard order (it engages), back to the sphere once clear.
KAS_Guards = {}
KAS_GuardRadius = 450
KAS_GuardAlarm = 3000
function K_492960(sel)                                                                                -- kasfGuardShips
    KAS_EndPatrol()
    SobGroup_GuardSobGroup(KAS_Team, sel)
    KAS_Guards[KAS_Team] = { sel = sel, engaged = 1 }
    if Rule_Exists("KAS_GuardTick") == 0 then Rule_AddInterval("KAS_GuardTick", 2) end
end
function KAS_GuardTick()
    SobGroup_CreateIfNotExist("KAS_GuardOne")
    SobGroup_CreateIfNotExist("KAS_GuardFoes")
    for team, g in KAS_Guards do
        local n = SobGroup_Count(team)
        if n == 0 or SobGroup_Count(g.sel) == 0 then
            KAS_Guards[team] = nil
        elseif KAS_FillEnemiesNear("KAS_GuardFoes", g.sel, KAS_GuardAlarm) > 0 then
            if g.engaged == nil then SobGroup_GuardSobGroup(team, g.sel) end
            g.engaged = 1
        else
            g.engaged = nil
            local c, owner = SobGroup_GetPosition(g.sel), KAS_Owner(team)
            local i = 0
            while i < n do               -- even points on a sphere (golden-angle spiral)
                local y = 1 - 2 * (i + 0.5) / n
                local r = sqrt(1 - y * y)
                local a = i * 137.508      -- degrees (Lua 4 trig)
                SobGroup_Clear("KAS_GuardOne")
                SobGroup_FillShipsByIndexRange("KAS_GuardOne", team, i, 1)
                SobGroup_MoveToPoint(owner, "KAS_GuardOne", { c[1] + KAS_GuardRadius * r * cos(a),
                                                               c[2] + KAS_GuardRadius * y,
                                                               c[3] + KAS_GuardRadius * r * sin(a) })
                i = i + 1
            end
        end
    end
end
-- kasfPatrolPath: SobGroup_FollowPath (Gearbox's emulation) is an attack-move (COMMAND_AttackMove, 20): the ships
-- engage whatever their side sees, and Mission01's Kushan picket (33 proximity sensors) sees across the map, so the
-- picket's interceptor wings left their patrol for the Taiidan interceptors on the far side (trace: order 20, then
-- 2 = attack, with no kasfAttack for them, even with passive ROE). Cataclysm's wings patrol until the alarm (an
-- explicit kasfAttack). Here the patrol is plain moves point to point (KAS_Paths: mission2level.py
-- m<NN>_paths.lua), around a closed path, back and forth along an open one; any other order ends it.
KAS_Patrols = {}
KAS_PatrolReach = 600          -- a team is at a waypoint when its centre is this close (or it has stopped)
function KAS_EndPatrol() KAS_Patrols[KAS_Team] = nil if KAS_Guards then KAS_Guards[KAS_Team] = nil end end
function KAS_PatrolGo(team)
    local p = KAS_Patrols[team]
    SobGroup_MoveToPoint(KAS_Owner(team), team, KAS_Paths[p.path][p.i])
end
function K_4929d0(path)                                                                             -- kasfPatrolPath
    if KAS_Paths == nil or KAS_Paths[path] == nil then
        KAS_Patrols[KAS_Team] = nil
        SobGroup_FollowPath(KAS_Team, path, 1, 1, 0)
        return
    end
    KAS_Patrols[KAS_Team] = { path = path, i = 1, dir = 1 }
    KAS_PatrolGo(KAS_Team)
end
function KAS_PatrolTick()
    local gone = {}
    for team, p in KAS_Patrols do
        if SobGroup_Count(team) == 0 then
            gone[getn(gone) + 1] = team
        else
            local pts, a = KAS_Paths[p.path], SobGroup_GetPosition(team)
            local b = pts[p.i]
            local d = sqrt((a[1] - b[1]) * (a[1] - b[1]) + (a[2] - b[2]) * (a[2] - b[2]) + (a[3] - b[3]) * (a[3] - b[3]))
            if d < KAS_PatrolReach or SobGroup_GetCurrentOrder(team) == COMMAND_Idle then
                local n = getn(pts)
                if pts.closed == 1 then
                    p.i = p.i + 1
                    if p.i > n then p.i = 1 end
                else
                    if p.i + p.dir < 1 or p.i + p.dir > n then p.dir = -p.dir end
                    p.i = p.i + p.dir
                end
                KAS_PatrolGo(team)
            end
        end
    end
    local i = 1
    while i <= getn(gone) do
        KAS_Patrols[gone[i]] = nil
        i = i + 1
    end
end
function K_492b20() return floor(KAS_TeamHealth(KAS_Team)) end                                      -- kasfTeamHealthAverage
function K_493aa0(pct) SobGroup_SetHealth(KAS_Team, pct / 100) end                                  -- kasfTeamSetPercentDamaged
function K_493cf0(team, sel) SobGroup_SobGroupAdd(team, sel) end                                    -- kasfReinforceTeamWithShips

-- kasfTeamCountOriginal: the team's ship count at its creation (Gearbox registers it then). Recorded for every team
-- once it has ships (KAS_RecordTeamCounts, from KAS_StartEngine): cached on first ask, Mission01's PesterHInt1 first
-- asked after its wing died, got 0, and "reinforced" itself with nothing (user: no second wing).
KAS_TeamOriginalCounts = {}
function KAS_RecordTeamCounts()
    local i, left = 0, 0
    while KASNumberTeams and i < KASNumberTeams do
        local t = KASTeams[i]
        if KAS_TeamOriginalCounts[t] == nil then
            if SobGroup_Count(t) > 0 then KAS_TeamOriginalCounts[t] = SobGroup_Count(t) else left = left + 1 end
        end
        i = i + 1
    end
    if KASNumberTeams and KASNumberTeams > 0 and left == 0 then Rule_Remove("KAS_RecordTeamCounts") end
end
function K_493e00()
    if KAS_TeamOriginalCounts[KAS_Team] == nil then
        KAS_TeamOriginalCounts[KAS_Team] = SobGroup_Count(KAS_Team)
    end
    return KAS_TeamOriginalCounts[KAS_Team]
end

-- ------------------------------------------------------------------ orders
function K_4941a0(vec)                                                                              -- kasfMoveTo
    KAS_EndPatrol()
    if SobGroup_Count(KAS_Team) > 0 then SobGroup_MoveToPoint(KAS_Owner(KAS_Team), KAS_Team, vec) end
end
function K_494750(host) SobGroup_DockSobGroupInstant(KAS_Team, host) end                            -- kasfDockInstant
-- kasfTeamFinishedLaunching: KASUtil's flag (set by the launch order, cleared as each ship leaves its hangar) never
-- cleared for a team that wasn't docked (Mission01's PesterHInt1 launched and waited forever, user: no patrols), so a
-- team ordered to launch has also finished once none of it is docked, or KAS_LaunchGiveUp seconds after the order.
KAS_LaunchAt = {}
KAS_LaunchGiveUp = 20
function K_4947c0() KAS_LaunchAt[KAS_Team] = Universe_GameTime() KAS_Launch(KAS_Team) end            -- kasfLaunch
function K_4948a0()                                                                                  -- kasfTeamFinishedLaunching
    local t = KAS_LaunchAt[KAS_Team]
    if KAS_TeamFinishedLaunching(KAS_Team) ~= 0 then
        if t and t ~= -1 and KAS_TeamFormation[KAS_Team] then KAS_SetFormation(KAS_Team, KAS_TeamFormation[KAS_Team]) end
        if t then KAS_LaunchAt[KAS_Team] = -1 end
        return KAS_B(1)
    end
    if t == nil or t == -1 or SobGroup_Count(KAS_Team) == 0 then return KAS_B(nil) end
    local since = Universe_GameTime() - t
    local done = since > 1 and (SobGroup_IsDocked(KAS_Team) == 0 or since > KAS_LaunchGiveUp)
    if done and KAS_TeamFormation[KAS_Team] and KAS_LaunchAt[KAS_Team] ~= -1 then
        KAS_SetFormation(KAS_Team, KAS_TeamFormation[KAS_Team])      -- formed again now it is all in space
    end
    if done then KAS_LaunchAt[KAS_Team] = -1 end
    return KAS_B(done)
end
function K_494940() return KAS_B(SobGroup_IsDockedCompletely(KAS_Team) == 1) end                   -- kasfTeamDockedReadyForLaunch
function K_495eb0()                                                                                  -- kasfStop
    KAS_EndPatrol()
    if SobGroup_Count(KAS_Team) > 0 then SobGroup_Stop(KAS_Owner(KAS_Team), KAS_Team) end
end
function K_495f00() KAS_Harvest(KAS_Owner(KAS_Team), KAS_Team) end                                  -- kasfHarvest

-- ------------------------------------------------------------------ ships
-- kasfShipsSetDamageFactor (HW1 KASFunc.c: damage the ships deal x pct / 100). SobGroup_SetDamageMultiplier
-- COMPOUNDS (measured, range test 2026-10-12: 0.5 then 0.5 again = 0.25, then 2 = 0.5) and ion beams stop firing
-- below about 0.5 (user: no beam, no damage, and Mission01's battle never resolved). So only the ship rules set it
-- (shiprules.lua CatShip_ApplyMultipliers: rank x this factor, floored, by ratio); this only puts the ships in
-- cat_dmgf (any factor) and cat_dmgf_<pct> (rounded to 5) for them (another Lua state).
function K_493980(sel, pct)                                                                            -- kasfShipsSetDamageFactor
    SobGroup_CreateIfNotExist("KAS_DmgfTmp")
    local q = floor(pct / 5 + 0.5) * 5
    if q < 5 then q = 5 elseif q > 100 then q = 100 end
    -- (damage copies too: the ship rules take the factor as a ratio to the copy's own)
    SobGroup_CreateIfNotExist("cat_dmgf")
    SobGroup_CreateIfNotExist("cat_dmgf_" .. q)
    local p = 5
    while p <= 100 do                     -- out of any earlier factor's group: the latest one counts
        if p ~= q then
            SobGroup_CreateIfNotExist("cat_dmgf_" .. p)
            SobGroup_FillSubstract("KAS_DmgfTmp", "cat_dmgf_" .. p, sel)
            SobGroup_Clear("cat_dmgf_" .. p)
            SobGroup_SobGroupAdd("cat_dmgf_" .. p, "KAS_DmgfTmp")
        end
        p = p + 5
    end
    SobGroup_SobGroupAdd("cat_dmgf", sel)
    SobGroup_SobGroupAdd("cat_dmgf_" .. q, sel)
end
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
-- kasfShipsDeleteAfterHyperspace (exe 0x497ed0: sets ATTRIBUTES_DeleteAfterHSOut, 0x40, on each ship): HW1 deletes
-- such ships when the fleet jumps out instead of carrying them to the next mission. Mission01 sets it on the Kushan
-- teams it gives the player; here allies stay with player 2 and are never carried, so nothing to do.
function K_497ed0(sel) end

-- 0x499870(team): 1 if any ship lacks the data at ship+0x370 (Mission01: decides whether to hunt Workers).
function K_499870(sel) return 1 end

-- 0x499c70(dst, shipType, count, nearShips, player): creates count ships of the type next to nearShips.
-- In space beside them, as Cataclysm: SobGroup_CreateShip builds inside a ship that can build and returns no group
-- (Gearbox, KASUtil KAS_RequestShips), so Mission01's second pester wing never existed for its team (user).
KAS_SpawnSerial = 0
function K_499c70(dst, shipType, count, near, player)
    SobGroup_CreateIfNotExist(dst)
    SobGroup_Clear(dst)
    if count <= 0 or SobGroup_Count(near) == 0 then return end
    local t = KAS_HWRMType(shipType)
    local c = SobGroup_GetPosition(near)
    -- owned like the ships they appear beside: Cataclysm asks for its Kushan as the human's (kasfTeamSwitchPlayerOwner
    -- hands them over; here they stay on allied player 2), so the Kushan carrier's interceptors went to the player
    local owner = SobGroup_GetPlayerOwner(near)
    if owner and owner >= 0 then player = owner end
    local i = 0
    while i < count do
        KAS_SpawnSerial = KAS_SpawnSerial + 1
        local vol = "KAS_SpawnVol" .. KAS_SpawnSerial
        Volume_AddSphere(vol, { c[1] + random(-300, 300), c[2] + random(-100, 100), c[3] + random(-300, 300) }, 1)
        SobGroup_SpawnNewShipInSobGroup(player, t, "KAS_Spawned" .. KAS_SpawnSerial, dst, vol)
        Volume_Delete(vol)
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
    KAS_FillShipsByType(n, src, KAS_HWRMType(shipType))
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

-- kasfFirstShip: the selection's first ship. (It took all of them: Mission01's sensor-net raiders, told to move to
-- the "first" sensor, flew to the centre of the whole net, the map origin, after two kills; user.)
function K_498d90(dst, src)                                                                          -- kasfFirstShip
    SobGroup_Clear(dst)
    if SobGroup_Count(src) > 0 then SobGroup_FillShipsByIndexRange(dst, src, 0, 1) end
end
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
-- kasfUniversePause / kasfUniverseUnpause (exe 0x497a90 / 0x497aa0 set nisUniversePause; HW1 NIS.c): every ship
-- stops while KAS goes on (Mission01's Fleet Intel briefings). Gearbox's port left it empty (Universe_Pause would
-- stop timers and KAS too); without it the battles played on through the briefings (user: at 1:28 the bombers had
-- drifted into the main fight, in Cataclysm they had not moved). Ships are held with speed 0 and no attacks.
function KAS_UniverseHold(on)
    local speed, attack = 1, 1
    if on ~= 0 then speed, attack = 0, 0 end
    local p = 0
    while p < Universe_PlayerCount() do
        SobGroup_SetSpeed("Player_Ships" .. p, speed)
        SobGroup_AbilityActivate("Player_Ships" .. p, AB_Attack, attack)
        p = p + 1
    end
    KAS_UniverseHeld = on
    print("CKAS: universe " .. (on ~= 0 and "paused" or "unpaused"))
    -- HW1 takes no orders while the universe is paused: the player watches the briefing (user: Mission01 opens with
    -- control restricted until the end of the first sensors scene). A mission's opening lock ends with it too.
    if on ~= 0 then
        KAS_Lockout(1)
    else
        KAS_OpeningLock = nil
        KAS_Lockout(0)
    end
end

-- Player control off / on: orders and the sensors manager toggle (Gearbox's spMainScreenAndLockout / spUnlockout,
-- without leaving the sensors manager: Cataclysm's briefings play in it); the camera stays the player's (user).
-- KAS_OpeningLock (the
-- mission's, build_mission.py OPENING_LOCK) keeps it off from the warp-in to the end of the first briefing.
function KAS_Lockout(on)
    if on == 0 and KAS_OpeningLock == 1 then return end
    Universe_AllowPlayerOrders(1 - on)
    Sensors_EnableToggle(1 - on)
    if on == 1 then SobGroup_DeSelectAll() end
    print("CKAS: player control " .. ((on == 1 and "locked") or "unlocked"))
end
function K_497a90() KAS_UniverseHold(1) end
function K_497aa0() KAS_UniverseHold(0) end

-- kasfOtherKASPause / kasfOtherKASUnpause (exe 0x497ad0 / 0x497af0, HW1 KASFunc.c): only the calling team's FSM
-- keeps running; every other team's and the mission's watches stop (Gearbox's KASRules_PauseExceptFSM) and every
-- timer outside the team's scope pauses (Timer.c timTimerPauseAllNotScoped / timTimerUnpauseAll). Mission01 does
-- it around Fleet Intel's sensors sequences.
function K_497ad0()
    KASRules_PauseExceptFSM(KAS_Team)
    local prefix, now = KAS_Scope .. ":", KAS_Now()
    for k, t in KAS_Timers do
        if strsub(k, 1, strlen(prefix)) ~= prefix and t.paused == nil then
            t.paused = now
        end
    end
    print("CKAS: other KAS paused (running only " .. KAS_Team .. ")")
end
function K_497af0()
    KASRules_UnpauseOthers()
    local now = KAS_Now()
    for k, t in KAS_Timers do
        if t.paused then
            t.dur = t.dur + (now - t.paused)
            t.paused = nil
        end
    end
    print("CKAS: other KAS unpaused")
end

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
    -- a Kuun-Lan module: our sMothership<Module> type is its loose dummy ship (cutscenes); the build option is the
    -- module subsystem (user: Mission 1 offered the modules it turns off)
    if strsub(t, -6) == "_dummy" then t = strsub(t, 1, -7) end
    KAS_ConstructionOff[t] = (on == 0) or nil     -- KAS_VariantBuildWatch follows it for the variants
    if on ~= 0 then Player_UnrestrictBuildOption(0, t) else Player_RestrictBuildOption(0, t) end
    KAS_VariantBuildWatch()
end

-- 0x497290(mission, label): Cataclysm's autosave (decompiled: it queues one, 0x4972d0 writes
-- "SavedGames\SinglePlayer\<mission> - <label>": Mission01's "Hiigara" after the warp-in, "~ End of Mission" with
-- the Hyperspace objective). Taken first for the end-of-mission hyperspace, it showed the button at the warp-in
-- (user). HWRM's campaign quicksave, as Gearbox's KAS_SetLetterboxState saves.
function K_497290(mission, label)
    print("CKAS: autosave '" .. format("%02d", mission) .. " - " .. label .. "'")
    Campaign_QuickSaveNb(mission, label)
end

-- The end of a mission: the "Hyperspace" objective is no objective, it shows the HYPERSPACE button (HW1; Gearbox's
-- KASObjective_Add, K_494e70 here). Gearbox's HW1 hyperspace as it is (SinglePlayerHyperspace.lua, user: steal
-- HW1RM's end): pressed, the roll call (strike craft dock, the rest parade, Go Now), everyone still out docked
-- instantly, all into hyperspace off the map, white-out, setMissionComplete(1). The engine keeps the fleet in
-- hyperspace (squadrons, holds, Kuun-Lan modules, research, RUs) for the next mission (persistence). Its state
-- machine runs on KAS_HyperspaceTick, not Gearbox's singlePlayerGameUpdate (that fails the mission without a
-- Kus_Mothership).
function KAS_HyperspaceAllow()
    print("CKAS: end-of-mission hyperspace allowed")
    spGameInfo_currentMission = spGameInfo_currentMission or 0     -- (Gearbox's flow names it in a message)
    singlePlayerHyperspaceButtonEnable()
    if Rule_Exists("KAS_HyperspaceTick") == 0 then Rule_AddInterval("KAS_HyperspaceTick", 0.25) end
end

KAS_HyperspaceLastState = -1
function KAS_HyperspaceTick()
    singlePlayerHyperspaceStateUpdate()
    if spGameInfo_hyperspaceState ~= KAS_HyperspaceLastState then
        KAS_HyperspaceLastState = spGameInfo_hyperspaceState
        print("CKAS: hyperspace state " .. spGameInfo_hyperspaceState)
    end
end

-- Gearbox's mothership lookup (KASUtil.lua, used by the roll call, which wants exactly one) knows only the stock
-- motherships: the Kuun-Lan, the player's real one (KAS_ArrivalMS): by type it also found the intro NIS's despawned
-- copy, two, and the HYPERSPACE button did nothing ("no mothership", user)
function KAS_PlayerMothership(sobGroupName, playerIndex)
    SobGroup_CreateIfNotExist("KAS_ArrivalMS")
    SobGroup_CreateIfNotExist(sobGroupName)
    SobGroup_Clear(sobGroupName)
    if (playerIndex or 0) == 0 and sobGroupName ~= "KAS_ArrivalMS" and SobGroup_Count("KAS_ArrivalMS") > 0 then
        SobGroup_SobGroupAdd(sobGroupName, "KAS_ArrivalMS")
        return
    end
    SobGroup_CreateIfNotExist("KAS_MothershipAll")
    local i = 1
    while i <= getn(KAS_MothershipTypes) do
        SobGroup_Clear("KAS_MothershipAll")
        Player_FillShipsByType("KAS_MothershipAll", playerIndex or 0, KAS_MothershipTypes[i])
        local n = SobGroup_Count("KAS_MothershipAll")
        if n > 0 then
            if n > 1 then print("CKAS: " .. n .. " " .. KAS_MothershipTypes[i] .. " for player " .. (playerIndex or 0) .. ": the first") end
            SobGroup_FillShipsByIndexRange(sobGroupName, "KAS_MothershipAll", 0, 1)
            return
        end
        i = i + 1
    end
end
