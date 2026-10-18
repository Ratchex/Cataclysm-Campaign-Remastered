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
-- ships that hyperspaced out mid-mission (K_493800): Cataclysm takes them out of the universe, so out of every
-- selection; HWRM keeps them in their groups (Mission02: the raider carrier that jumped out kept "Pirates" at 1 and the
-- mission from ending, user 2026-10-18). Not counted; back when their team hyperspaces in (K_493600 / K_493630).
function KAS_Present(sel)
    local n = SobGroup_Count(sel)
    if n == 0 or SobGroup_Exists("KAS_Departed") == 0 or SobGroup_Count("KAS_Departed") == 0 then return n end
    SobGroup_CreateIfNotExist("KAS_PresentTmp")
    SobGroup_Clear("KAS_PresentTmp")
    SobGroup_FillSubtract("KAS_PresentTmp", sel, "KAS_Departed")
    return SobGroup_Count("KAS_PresentTmp")
end
function KAS_Returned(team)
    if SobGroup_Exists("KAS_Departed") == 0 then return end
    SobGroup_CreateIfNotExist("KAS_PresentTmp")
    SobGroup_Clear("KAS_PresentTmp")
    SobGroup_FillSubtract("KAS_PresentTmp", "KAS_Departed", team)
    SobGroup_Clear("KAS_Departed")
    SobGroup_SobGroupAdd("KAS_Departed", "KAS_PresentTmp")
end
function K_492ce0() return KAS_Present(KAS_Team) end                                                -- kasfTeamCount
function K_492d10(sel) SobGroup_Clear(sel) end                                                      -- kasfGrowSelectionClear
function K_492d20(sel)                                                                              -- kasfShipsCount
    local n = KAS_Present(sel)
    -- TEST: Mission02 ends when "Pirates" empties (F_5dd2d0); log each change
    if sel == "GS_Pirates" and n ~= KAS_PiratesLast then
        KAS_PiratesLast = n
        local s = ""
        for _, t in { "pCarrier", "Kamikaze", "pFighter1", "pFighter2", "pFighter3", "pSalvage", "pGuard" } do
            if SobGroup_Exists(t) == 1 then s = s .. " " .. t .. "=" .. SobGroup_Count(t) end
        end
        print("CKAS: Pirates " .. n .. " left:" .. s)
    end
    return n
end
function K_493de0(team) return KAS_B(team == KAS_Team) end                                          -- kasfThisTeamIs
function K_492910(lo, hi) return RandomIntRange(hi, lo) end                                         -- kasfRandom
-- kasfMissionSkillGet: Cataclysm's skill 0-4, its default 2 (exe DAT_008941a0); HWRM's campaign difficulty is 0-2
-- (Easy / Normal / Hard), so 1 / 2 / 3 (raw, Mission02's patrols at skill 0 all died: user's run 2026-10-18)
function K_493b90()
    local d = Player_GetLevelOfDifficulty(0)
    if KAS_SkillSaid == nil then KAS_SkillSaid = 1 print("CKAS: HWRM difficulty " .. d .. " -> Cataclysm skill " .. (d + 1)) end
    return d + 1
end

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
-- each ship's position against the fog-of-war map; here: any of them within sensor range of any player ship, ship
-- by ship (measured against the whole selection, Mission02's meteors spread over the map counted as found at once:
-- user, the meteor warning came before the Engineering Module's)
function K_499570(sel)
    if SobGroup_Count(sel) == 0 then return 0 end
    SobGroup_CreateIfNotExist("KAS_Discover")
    SobGroup_CreateIfNotExist("KAS_DiscoverBy")
    for i = 0, SobGroup_Count("Player_Ships0") - 1 do
        SobGroup_Clear("KAS_DiscoverBy")
        SobGroup_FillShipsByIndexRange("KAS_DiscoverBy", "Player_Ships0", i, 1)
        SobGroup_Clear("KAS_Discover")
        if SobGroup_Count("KAS_DiscoverBy") > 0 then
            SobGroup_FillProximitySobGroup("KAS_Discover", sel, "KAS_DiscoverBy", KAS_DiscoverRadius)
            if SobGroup_Count("KAS_Discover") > 0 then return 1 end
        end
    end
    return 0
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
    Sensors_EnableToggle(0)               -- no sensors manager during a cutscene (user: opened during the intro)
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
        if KAS_NisPending == nil and KAS_LockedOut ~= 1 then Sensors_EnableToggle(1) end
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
    -- a carried-over fleet (persistence, KAS_PersistFleet from build_mission.py): HWRM's loader brings it in itself
    -- (the Processor warped in on its own; despawned for our own warp-in, the Kuun-Lan just sat there, user)
    if KAS_PersistFleet == 1 then return nil end
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
    -- (also with no turn: placed on the start point itself it "arrived" in place in 2.5 s, no flight in: Mission02, user)
    local yaw = KAS_ArrivalYaw or 0
    local p = Volume_GetPosition("StartPointPlayer")
    if p == nil then return end
    local d = KAS_ArrivalBack
    SobGroup_SetPosition("KAS_ArrivalMS", { p[1] - d * sin(yaw), p[2], p[3] - d * cos(yaw) })
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
        if KAS_PersistFleet == 1 and SobGroup_Count("KAS_ArrivalMS") > 0 then
            -- the loader's own arrival: launch with Fleet Command's line once the Kuun-Lan is in and idle
            KAS_ArrivalStarted = Universe_GameTime()
            KAS_ArrivalFocused = 1
            Rule_AddInterval("KAS_ArrivalWatch", 0.5)
            print("CKAS: carried-over fleet: HWRM's own arrival")
            return
        end
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
    if KAS_PersistFleet == 1 then
        -- HWRM's carried-over arrival runs in the starting letterbox without UI; Gearbox ends it once the mothership
        -- is idle (KASUtil KAS_EndStartingLetterbox). Without: no UI, nothing but sensors worked (Mission02, user)
        Camera_SetLetterboxStateNoUI(0, 2)
    end
    if KAS_ArrivalYaw and KAS_ArrivalYaw ~= 0 then Rule_AddInterval("KAS_ArrivalBowLog", 2) end
    KAS_Autolaunch()
    if KAS_DevHyperspaceAfter then
        print("CKAS: DEV HYPERSPACE button in " .. KAS_DevHyperspaceAfter .. "s")
        Rule_AddInterval("KAS_DevHyperspace", KAS_DevHyperspaceAfter)
    end
    KAS_Vars[KAS_Key_ShipsHaveArrived] = 1
    print("CKAS: fleet out of hyperspace after " .. t .. "s; launching " .. SobGroup_Count("KAS_ArrivalDocked")
          .. " ships; G_ShipsHaveArrived")
    if KAS_MusicHeld then       -- the mission's track, held through the arrival (K_497000)
        local path = KAS_MusicHeld
        KAS_MusicHeld = nil
        Sound_MusicPlayType(path, MUS_Ambient)
        print("CKAS: music " .. path .. " (held through the arrival)")
    end
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
KAS_AUTOLAUNCH_CODE = 67113064           -- 0x4001068: event 104, Fleet Command, 5 s (FUN_0044a640)
function KAS_Autolaunch()
    SobGroup_SetAutoLaunch("KAS_ArrivalMS", ShipHoldLaunch)
    -- and whatever the previous mission's fleet brought docked (persistence loads it inside: Mission02's Acolytes and
    -- ACVs stayed in, user)
    SobGroup_CreateIfNotExist("KAS_ArrivalAboard")
    SobGroup_Clear("KAS_ArrivalAboard")
    SobGroup_GetSobGroupDockedWithGroup("KAS_ArrivalMS", "KAS_ArrivalAboard")
    SobGroup_SobGroupAdd("KAS_ArrivalDocked", "KAS_ArrivalAboard")
    if SobGroup_Count("KAS_ArrivalDocked") == 0 then return end
    SobGroup_Launch("KAS_ArrivalDocked", "KAS_ArrivalMS")
    CatVoice_Event(KAS_AUTOLAUNCH_CODE, 0, KAS_VOICE_WAIT)
end

-- Player 2 (when the level has one) is the allied Kushan fleet. Applied at start and again on the first tick.
function KAS_ApplyAlliances()
    local n = Universe_PlayerCount()
    if n > 2 and KAS_AllyOnSwitch then
        print("CKAS: " .. n .. " players; 0 and 2 allied when 2's team switches sides (KAS_AllyOnSwitch)")
    elseif n > 2 then
        print("CKAS: " .. n .. " players; allying 0 and 2")
        SetAlliance(0, 2)
        SetAlliance(2, 0)
    end
    -- the meteors' player (tools/mission2level.py add_storm): nobody's enemy (Cataclysm's meteors are asteroids)
    if KAS_MeteorPlayer and KAS_MeteorPlayer >= 0 and n > KAS_MeteorPlayer then
        for i = 0, n - 1 do
            if i ~= KAS_MeteorPlayer then
                SetAlliance(i, KAS_MeteorPlayer)
                SetAlliance(KAS_MeteorPlayer, i)
            end
        end
    end
end

-- Cataclysm research is offered by the mission (kasfAllowPlayerToResearch / Purchase): lock every tech first.
-- DEVELOPMENT ONLY: research the missions don't allow yet, unlocked for testing a later mission's mechanics
-- (keep empty in commits that aren't a test)
KAS_DevTechs = {}
-- DEVELOPMENT ONLY: the HYPERSPACE button this many seconds after the warp-in (testing the end of a mission without
-- playing it; nil in commits that aren't a test)
KAS_DevHyperspaceAfter = nil
KAS_DevModules = {}     -- ...and the Kuun-Lan modules they need (e.g. { "smt_kl_weapons" } for TECH_MISSILE)

function KAS_RestrictTechs()
    if KAS_Techs == nil then return end
    local i = 1
    while i <= getn(KAS_Techs) do
        if Player_HasResearch(0, KAS_Techs[i]) ~= 1 then Player_RestrictResearchOption(0, KAS_Techs[i]) end
        i = i + 1
    end
    i = 1
    while i <= getn(KAS_DevTechs) do
        KAS_Unrestrict(KAS_DevTechs[i])
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
    -- each of the human's ships that is selected (SobGroup_Selected): MainUI_CurrentSelection()'s group only ever
    -- grew (logged 1, 4, 5 ... 17 ships, never less), so an upgraded Acolyte once selected kept Link on every later
    -- selection (user, 2026-10-17)
    SobGroup_CreateIfNotExist("cat_sel_one")
    local n = SobGroup_Count("Player_Ships0")
    for i = 0, n - 1 do
        SobGroup_Clear("cat_sel_one")
        SobGroup_FillShipsByIndexRange("cat_sel_one", "Player_Ships0", i, 1)
        if SobGroup_Count("cat_sel_one") > 0 and SobGroup_Selected("cat_sel_one") == 1 then
            SobGroup_SobGroupAdd(grp, "cat_sel_one")
        end
    end
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
               (a.group == nil or a.group == "" or CatAbility_SelectionIn(sel, a.group) == 1) and
               (a.upgrade == "" or CatAbility_SelectionIn(sel, "cat_has_" .. a.upgrade) == 1) then
                show = 1
            end
            -- every tick, not on a change only: the taskbar's rebuild for a new selection showed them again behind our
            -- back (user, 2026-10-17: Link / Unlink on a Worker)
            UI_SetElementVisible("NewTaskbar", "btnCat_" .. a.name, show)
            CatAbilityShown[a.name] = show
        end
    end
    -- HWRM's salvage-capture button, the Ramming Frigate's Ram: every tick, as the buttons above (the taskbar's rebuild
    -- for a new selection undid a change made once); the Worker's Salvage is its own button (btnCat_salvage, the same
    -- event: make_abilities.py CLICK; user: the frigate's showed Salvage)
    local ram = SobGroup_Count(sel) > 0 and SobGroup_AreAnyOfTheseTypes(sel, "smt_rammingfrigate") == 1
    UI_SetElementVisible("NewTaskbar", "btnSalCap", ram and 1 or 0)
end

-- research the player starts the mission with (the mission's KAS_StartResearch, build_mission.py START_RESEARCH;
-- after KAS_RestrictTechs): Mission01's fighter drive (user)
function KAS_GrantStartResearch()
    if KAS_StartResearch == nil then return end
    local i = 1
    while i <= getn(KAS_StartResearch) do
        KAS_Unrestrict(KAS_StartResearch[i])
        KAS_Grant(KAS_StartResearch[i])
        print("CKAS: start research " .. KAS_StartResearch[i])
        i = i + 1
    end
end

-- engine abilities our upgrade system switches per ship (tools/make_race.py RUNTIME_RESEARCH, KAS_RuntimeResearch in
-- cataclysmtech.lua): granted to the human
function KAS_GrantRuntimeResearch()
    local i = 1
    while i <= getn(KAS_RuntimeResearch) do
        KAS_Grant(KAS_RuntimeResearch[i])
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
    -- a Kuun-Lan module (Cataclysm ship type sMothership<Module> -> our dummy ship smt_kl_<key>_dummy): in HWRM a
    -- subsystem of the Kuun-Lan, so the Kuun-Lan when it has it (Mission02 looked for its docking bay among the
    -- player's ships, found none and reported it destroyed, user)
    if strsub(strlower(t), 1, 7) == "smt_kl_" and strsub(strlower(t), -6) == "_dummy" then
        local sub = strsub(strlower(t), 1, strlen(t) - 6)
        SobGroup_CreateIfNotExist("KAS_ModuleHost")
        SobGroup_Clear("KAS_ModuleHost")
        SobGroup_FillShipsByType("KAS_ModuleHost", src, "smt_ms_sp")
        if SobGroup_Count("KAS_ModuleHost") > 0 and SobGroup_HasSubsystem("KAS_ModuleHost", sub) == 1 then
            SobGroup_SobGroupAdd(n, "KAS_ModuleHost")
            if sub == "smt_kl_orecanarmour" then KAS_OreCanSel = n end   -- (the canister scene's camera target)
        elseif sub == "smt_kl_orecanarmour" and SobGroup_Count("KAS_JettCan") > 0 then
            -- jettisoned: in Cataclysm still a ship of that type, flying off (Mission02 focuses on it 3 s later)
            SobGroup_SobGroupAdd(n, "KAS_JettCan")
            KAS_OreCanSel = n
        end
        return
    end
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

-- Cataclysm's Support Units (cataclysm.exe, decompiled in Cataclysm-decomp/out/su_funcs.c): each ship uses its type's
-- supportUnits and adds its providesSU to the player's limit (FUN_00459a90 / 00459ae0: the player's +0x10 used,
-- +0xc limit; the Kuun-Lan 70, its Hangar 30, each Support Module 10, a Carrier 40). A ship can be queued only while
-- used < limit and its cost fits in what is left after everything already queued (FUN_004565a0 with FUN_00459c20);
-- the computer players in a mission don't count Support Units. Unit caps on top (unitlimitcaps.script, the types it
-- doesn't leave to Support Units): HWRM's own, data/scripts/races/somtaaw/singleplayer/unitcaps (install_base.py).
-- Here the engine's unit cap does the limiting (KAS_SUTick, install_base.py set_support_units); the build menu's
-- Support Units line (finalbuild.lua lblSUCount) shows used / limit as Cataclysm's build manager did.
-- Costs: tools/make_supportunits.py.
dofilepath("data:scripts/cataclysm/supportunits_gen.lua")
KAS_SUShown = nil
-- a type's ships of the player's, and (second) its damage copies' (tools/make_variants.py), which count as the type
function KAS_SUCount(t)
    SobGroup_CreateIfNotExist("KAS_SUType")
    SobGroup_Clear("KAS_SUType")
    Player_FillShipsByType("KAS_SUType", 0, t)
    local n, c = SobGroup_Count("KAS_SUType"), 0
    if KAS_SUCopies == nil then
        KAS_SUCopies = {}
        for copy, d in CatDamageVariants do
            if KAS_SUCopies[d[1]] == nil then KAS_SUCopies[d[1]] = {} end
            tinsert(KAS_SUCopies[d[1]], copy)
        end
    end
    local copies = KAS_SUCopies[t]
    if copies then
        for i = 1, getn(copies) do
            SobGroup_Clear("KAS_SUType")
            Player_FillShipsByType("KAS_SUType", 0, copies[i])
            c = c + SobGroup_Count("KAS_SUType")
        end
    end
    return n, c
end

-- Used SU and the limit, every second. The engine enforces the limit: every type in the Somtaaw build list takes
-- its SU from the "SupportUnits" unit cap (CatSU_Cap), so HWRM counts queues at the click as Cataclysm did, and
-- filler ships hold the rest of the cap: CatSU_Cap - limit, plus the SU of the player's ships the engine doesn't
-- count (CatSU_Native: types outside the build list, the Kushan / Taiidan ships a mission hands over, damage copies)
dofilepath("data:scripts/cataclysm/sunative_gen.lua")
KAS_SUUsed, KAS_SULimit = 0, 0
function KAS_SUTick()
    if KAS_SUOff then return end
    local limit, used, extra = 0, 0, 0
    for t, v in CatSU_Provides do
        local n, c = KAS_SUCount(t)
        limit = limit + v * (n + c)
    end
    SobGroup_CreateIfNotExist("KAS_SUMS")
    KAS_KuunLan("KAS_SUMS", 0)
    if SobGroup_Count("KAS_SUMS") > 0 then
        for hp, v in CatSU_Hardpoints do
            if SobGroup_GetHardPointHealth("KAS_SUMS", hp) > 0 then limit = limit + v end
        end
    end
    for t, v in CatSU_Cost do
        local n, c = KAS_SUCount(t)
        used = used + v * (n + c)
        if CatSU_Native[t] then extra = extra + v * c else extra = extra + v * (n + c) end
    end
    KAS_SUUsed, KAS_SULimit = used, limit
    local fill = CatSU_Cap - limit + extra
    if fill < 0 then fill = 0 end
    KAS_SUFillTo(fill)
    KAS_SUShow(used, KAS_SUQueued(), limit)
end

-- Filler ships (Complex EVO's unit cap fillers): one to a group, far below the map, hidden and invulnerable,
-- CatSU_Fillers' sizes largest first. In game (2026-10-14): one in the world counts against the cap, a despawned one
-- doesn't, so freeing SU despawns one
KAS_SUFill, KAS_SUFillTotal, KAS_SUFillSerial = {}, -1, 0
function KAS_SUFillTo(total)
    if total == KAS_SUFillTotal then return end
    KAS_SUFillTotal = total
    local rest = total
    for i = 1, getn(CatSU_Fillers) do
        local f = CatSU_Fillers[i]
        local want = floor(rest / f[2])
        rest = rest - want * f[2]
        local list = KAS_SUFill[f[1]] or {}
        KAS_SUFill[f[1]] = list
        while getn(list) < want do
            KAS_SUFillSerial = KAS_SUFillSerial + 1
            local g = "KAS_SUFill" .. KAS_SUFillSerial
            SobGroup_CreateIfNotExist(g)
            SobGroup_Clear(g)
            Volume_AddSphere(g .. "V", { mod(KAS_SUFillSerial, 20) * 400, -90000, floor(KAS_SUFillSerial / 20) * 400 }, 1)
            SobGroup_SpawnNewShipInSobGroup(0, f[1], g, g, g .. "V")
            if SobGroup_Count(g) == 0 then   -- (never spawn every second without end)
                print("CKAS SU: ERROR no " .. f[1] .. " spawned; fillers stopped")
                KAS_SUOff = 1
                return
            end
            tinsert(list, g)
            SobGroup_SetHidden(g, 1)
            SobGroup_SetInvulnerability(g, 1)
        end
        while getn(list) > want do
            SobGroup_Despawn(list[getn(list)])
            tremove(list)
        end
    end
    print("CKAS SU: fillers hold " .. total .. " of the cap " .. CatSU_Cap)
end

-- every filler out of the world (the jump out of the mission: none may be carried over), and no more
function KAS_SUFillersClear()
    KAS_SUOff = 1
    for t, list in KAS_SUFill do
        for i = 1, getn(list) do SobGroup_Despawn(list[i]) end
    end
    KAS_SUFill = {}
    print("CKAS SU: fillers cleared")
end

-- the build menu's SU line: Cataclysm takes a unit's SU when it's queued, so the line counts the queues too
function KAS_SUShow(used, queued, limit)
    local shown = (used + queued) .. " / " .. limit
    if shown ~= KAS_SUShown then
        KAS_SUShown = shown
        UI_SetTextLabelText("NewBuildMenu", "lblSUCount", shown)
        print("CKAS SU: " .. shown .. " (built " .. used .. ", queued " .. queued .. ")")
    end
end

-- SU queued or being built, for the line only (the engine does the limiting): Player_HasQueuedBuild says only
-- whether a type is queued (0/1), so several of one type show as one; at least one while a builder is building it
function KAS_SUQueued()
    local queued = 0
    SobGroup_CreateIfNotExist("KAS_SUBuilders")
    SobGroup_Clear("KAS_SUBuilders")
    Player_GetShipsByFilterInclude(0, "KAS_SUBuilders", "Ability", "CanBuildShips")
    for t, v in CatSU_Native do
        local n = Player_HasQueuedBuild(0, t) or 0
        if n < 1 and (SobGroup_IsBuilding("KAS_SUBuilders", t) or 0) ~= 0 then n = 1 end
        queued = queued + CatSU_Cost[t] * n
    end
    return queued
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
-- so the campaign's list has the Somtaaw (install_base.py patches raceHelper: Somtaaw -> "cat_fleet", Cataclysm's
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
    Rule_AddInterval("KAS_SUTick", 1)
    KAS_GrantRuntimeResearch()
    KAS_DisableCPUPlayers()
    KAS_ApplyAlliances()
    KAS_RestrictTechs()
    KAS_GrantStartResearch()
    singlePlayerHyperspaceButtonDisable()     -- (Gearbox's singlePlayerStartGame): shown by K_497290
    Rule_AddInterval("KAS_EngineTick", 0.5)
    Rule_AddInterval("KAS_MoveFireTick", 1)
    Rule_AddInterval("KAS_DestroyerTrace", 5)   -- TEST
    Rule_AddInterval("KAS_ResourcerTrace", 10)  -- TEST
    KAS_MeteorInit()
    KAS_SalvageFind()
    Rule_AddInterval("KAS_JettisonWatch", 0.25)
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
-- player 2 only once it is the human's: where the level starts it unallied (KAS_AllyOnSwitch: Mission02's BUSHAN-RE,
-- the computer's in Cataclysm until found), not before its team switches sides (the pirates went for it unfound)
function KAS_FillHumanSide(newShips, orig)
    if KAS_AllyOnSwitch and KAS_AlliedOnSwitch == nil then return KAS_FillByOwners(newShips, orig, { 0 }) end
    KAS_FillByOwners(newShips, orig, { 0, 2 })
    -- (a disguised team is the ally's only for show: K_497fd0)
    for sel, _ in KAS_DisguiseInfo do
        if SobGroup_Count(sel) > 0 then
            SobGroup_CreateIfNotExist("KAS_OwnerTmp")
            SobGroup_FillSubstract("KAS_OwnerTmp", newShips, sel)
            SobGroup_Clear(newShips)
            SobGroup_SobGroupAdd(newShips, "KAS_OwnerTmp")
        end
    end
    return SobGroup_Count(newShips)
end
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
    if to == 2 and KAS_AllyOnSwitch and KAS_AlliedOnSwitch == nil then
        KAS_AlliedOnSwitch = 1
        KAS_HealthTrace(KAS_Team, "before the alliance")
        SetAlliance(0, 2)
        SetAlliance(2, 0)
        KAS_HealthTrace(KAS_Team, "after the alliance")
        print("CKAS: 0 and 2 allied (" .. KAS_Team .. " joined)")
    end
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
function K_490b30(h) return KAS_Vector(KAS_VecKey(h)) end                                           -- kasVectorPtr
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

-- ------------------------------------------------------------------ speech
-- Every line goes through Cataclysm's speech queue (data/scripts/scar/cataclysmvoice.lua: CatVoice_Event with the
-- exe's event code and wait); nothing here plays speech itself. Recordings: data/sound/speech/missions/cataclysm/
-- <id>.wav plus string <id> from speech.dat (tools/build_speech.py, cataclysmspeech.lua).
dofilepath("data:scripts/scar/cataclysmvoice.lua")
KAS_SpeechPath = "speech:missions/cataclysm/"

-- kasfSpeechEvent(event, variable) (0x496eb0): queued with no expiry (wait -1, 0xbf800000). A variable the event
-- has no line for falls back to 0 (the exe drops it; the translator's variables don't always match).
-- kasfIntelEventEnded (0x497b00) reports 1 once that line has played (or was dropped).
KAS_IntelLine = nil
function K_496eb0(event, variable)                                                                  -- kasfSpeechEvent
    if event < 0 then event = event + 4294967296 end
    local e = KAS_SpeechEvents and KAS_SpeechEvents["sect" .. mod(event, 2048)]
    if e and (variable < 0 or variable >= e[2]) then variable = 0 end
    KAS_IntelLine = CatVoice_Event(event, variable, -1)
end
function K_497b00()                                                                               -- kasfIntelEventEnded
    return KAS_B(KAS_IntelLine == nil or KAS_IntelLine.done == 1)
end

-- Lines the engine's speech logic can't trigger (data/soundscripts/cataclysm/catspeech.lua covers the rest), each
-- with the exe's event code and wait (Cataclysm-decomp/out/speech_calls.tsv). Variable = the speaking ship's
-- Cataclysm ShipType / the TechnologyType / the module (catspeech_gen.lua CatSpeech_Var / CatSpeech_TechLine,
-- tools/make_unitspeech.py).
dofilepath("data:soundscripts/cataclysm/catspeech_gen.lua")
-- the ship rules' barks (shiprules.lua CatSay: cat_say_<event>): Link, Unlink, mimic, unmimic, kamikaze, disguise
-- assumed, the Ram order (attack), the Worker's salvage order: pilot chatter, 0 s wait (FUN_00467ae0, 00468580,
-- 005b8f30; 167 / 168 by the same pattern; the Ram order's attack acknowledgement as the selection acks, FUN_00523040;
-- salvage FUN_004490b0)
CatSayEvents = { [156] = 71305372, [157] = 71305373, [165] = 71305381, [166] = 71305382, [167] = 71305383,
                 [168] = 71305384, [5] = 67110917, [150] = 67111062 }   -- 0x400089c, 0x400089d, 0x40008a5-a8, 0x4000805, 0x4000896
CatTechHad = nil
KAS_CODE_MODULE_ONLINE = 33558576     -- 0x2001030: event 48, Fleet Command, 5 s (FUN_004f4530)
KAS_CODE_TECHNOLOGY = 33558716        -- 0x20010bc: event 188, 5 s (FUN_004f2a20)
KAS_VOICE_WAIT = 5                    -- the exe's 0x40a00000

-- modules coming online (catspeech.lua leaves them to this): Cataclysm's module index, the event 48 variable
-- (tools/make_unitspeech.py MODULES)
CatModuleOnline = { smt_kl_dockingbay = 0, smt_kl_armour = 1, smt_kl_micro = 2, smt_kl_special = 3, smt_kl_weapons = 4 }
CatModuleHad = nil
function CatModuleTick()
    SobGroup_CreateIfNotExist("CatModuleMS")
    SobGroup_Clear("CatModuleMS")
    KAS_KuunLan("CatModuleMS", 0)
    if SobGroup_Count("CatModuleMS") == 0 then return end
    local first = CatModuleHad == nil
    if first then CatModuleHad = {} end
    for sub, v in CatModuleOnline do
        local has = SobGroup_HasSubsystem("CatModuleMS", sub)
        if not first and has == 1 and CatModuleHad[sub] ~= 1 then CatVoice_Event(KAS_CODE_MODULE_ONLINE, v, KAS_VOICE_WAIT) end
        CatModuleHad[sub] = has
    end
end

function CatSayTick()
    local now = Universe_GameTime()
    CatModuleTick()
    for ev, code in CatSayEvents do
        local grp = "cat_say_" .. ev
        if SobGroup_Exists(grp) == 1 and SobGroup_Count(grp) > 0 then
            -- one bark per press, however many ships (the queue drops the same line again while it plays)
            local t = strlower(SobGroup_GetShipType(grp))
            if CatSpeech_Var[t] == nil and CatVariantBase and CatVariantBase[t] then t = CatVariantBase[t] end
            if CatSpeech_Var[t] then CatVoice_Event(code, CatSpeech_Var[t], 0) end   -- a disguise speaks as its Mimic
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
            -- the Tactical Officer's voice (Fleet Intel's slot) on channel 1 (user: it cut into her own meteor warning)
            CatVoice_Event(KAS_CODE_TECHNOLOGY, CatTechQueue[k].v, KAS_VOICE_WAIT, { actor = Actor_HW1_FleetIntel })
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
    KAS_KuunLan(sel, 0)                   -- (the real one: not an NIS's despawned copy)
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
function KAS_EndPatrol()
    KAS_Patrols[KAS_Team] = nil
    if KAS_Intercepts then KAS_Intercepts[KAS_Team] = nil end
    if KAS_Guards then KAS_Guards[KAS_Team] = nil end
    if KAS_Moves then KAS_Moves[KAS_Team] = nil end
end
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
-- (cataclysm.exe 0x493aa0: each ship's health = pct % of its maximum.) Set while a team is still hyperspacing in it
-- doesn't hold (Mission02's destroyer arrived whole, so its repairs passed 39 % at once and the disguised corvettes
-- came at the start: user): kept on the team until its ships are there and no healthier (never raised), 30 s at most
-- TEST: a team's health, percent and absolute (user: Mission02's destroyer read 50 % once it changed sides)
function KAS_HealthTrace(team, why)
    if SobGroup_Count(team) == 0 then return end
    print(format("CKAS: %s health %.1f %% (%.0f of %.0f) %s, owner %d", team, SobGroup_HealthPercentage(team) * 100,
                 SobGroup_HealthPercentage(team) * SobGroup_MaxHealthTotal(team), SobGroup_MaxHealthTotal(team), why,
                 SobGroup_GetPlayerOwner(team)))
end
function KAS_DestroyerTrace()
    if SobGroup_Exists("kDestroyer") == 0 then return end
    local n = SobGroup_Count("kDestroyer")
    if n > 0 then
        local q = SobGroup_GetPosition("kDestroyer")
        KAS_HealthTrace("kDestroyer", format("(every 1 s) at %.0f %.0f %.0f, order %d", q[1], q[2], q[3],
                        SobGroup_GetCurrentOrder("kDestroyer")))
    elseif KAS_DestroyerSeen then
        -- TEST (2026-10-17): gone from its team: destroyed, or only out of the group (any kus_destroyer left?)
        SobGroup_CreateIfNotExist("KAS_TraceKD")
        local left = ""
        for pl = 0, Universe_PlayerCount() - 1 do
            SobGroup_Clear("KAS_TraceKD")
            Player_FillShipsByType("KAS_TraceKD", pl, "kus_destroyer")
            left = left .. " player " .. pl .. ": " .. SobGroup_Count("KAS_TraceKD")
        end
        print("CKAS TEST: kDestroyer team empty; kus_destroyer ships left:" .. left)
        KAS_DestroyerSeen = nil
    end
    if n > 0 then KAS_DestroyerSeen = 1 end
end
-- TEST: Mission 1's resourcer objective never completed after the player killed them (every 10 s: who is left, where)
function KAS_ResourcerTrace()
    if KAS_Objectives["DestroyResourcers"] == nil or SobGroup_Exists("TaiidanResourcers") == 0 then return end
    local n = SobGroup_Count("TaiidanResourcers")
    print("CKAS TEST: TaiidanResourcers left " .. n)
    SobGroup_CreateIfNotExist("KAS_TraceOne")
    for i = 0, n - 1 do
        SobGroup_Clear("KAS_TraceOne")
        SobGroup_FillShipsByIndexRange("KAS_TraceOne", "TaiidanResourcers", i, 1)
        if SobGroup_Count("KAS_TraceOne") > 0 then
            local q = SobGroup_GetPosition("KAS_TraceOne")
            print(format("CKAS TEST:   #%d at %.0f %.0f %.0f health %.2f docked %d", i, q[1], q[2], q[3],
                SobGroup_HealthPercentage("KAS_TraceOne"), SobGroup_IsDocked("KAS_TraceOne")))
        end
    end
end
KAS_PendingHealth = {}
function K_493aa0(pct)                                                                              -- kasfTeamSetPercentDamaged
    SobGroup_SetHealth(KAS_Team, pct / 100)
    KAS_PendingHealth[KAS_Team] = { h = pct / 100, till = Universe_GameTime() + 30 }
    if Rule_Exists("KAS_PendingHealthTick") == 0 then Rule_AddInterval("KAS_PendingHealthTick", 0.5) end
end
function KAS_PendingHealthTick()
    local now, left, done = Universe_GameTime(), 0, {}
    for team, p in KAS_PendingHealth do
        if now > p.till then
            tinsert(done, team)
        elseif SobGroup_Count(team) > 0 then
            if SobGroup_HealthPercentage(team) > p.h + 0.01 then
                SobGroup_SetHealth(team, p.h)
                left = left + 1
            elseif p.seen then
                tinsert(done, team)
                print("CKAS: " .. team .. " health " .. floor(p.h * 100) .. " %")
            else
                p.seen = 1
                left = left + 1
            end
        else
            left = left + 1
        end
    end
    -- (removed after the walk: Lua 4's next fails on a key cleared mid-walk)
    for i = 1, getn(done) do KAS_PendingHealth[done[i]] = nil end
    if left == 0 then Rule_Remove("KAS_PendingHealthTick") end
end
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
    if SobGroup_Count(KAS_Team) > 0 then
        KAS_Moves[KAS_Team] = KAS_Pos(vec)
        SobGroup_MoveToPoint(KAS_Owner(KAS_Team), KAS_Team, KAS_Moves[KAS_Team])
    end
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
-- kasfShipsSetRepairFactor(ships, factor): 0 stops the ships repairing themselves (Mission02's crippled destroyer,
-- until 90 %). HWRM's own regeneration (the .ship's regentime: the Kushan destroyer's took it from 20 % to 50 % before
-- it was found, user) has no script switch, so every tick a rise in health up to the regeneration rate is taken back
-- (a Worker's repair, on top of it, stays); any other factor lets it be
KAS_NoRegen = {}
function K_493a10(sel, v)
    if v == 0 then
        KAS_NoRegen[sel] = { last = Universe_GameTime(), h = {} }
        if Rule_Exists("KAS_NoRegenTick") == 0 then Rule_AddInterval("KAS_NoRegenTick", 0.5) end
    else
        KAS_NoRegen[sel] = nil
    end
end
function KAS_NoRegenTick()
    local now, left = Universe_GameTime(), 0
    SobGroup_CreateIfNotExist("KAS_RegenOne")
    for sel, r in KAS_NoRegen do
        left = left + 1
        local dt = now - r.last
        r.last = now
        for i = 0, SobGroup_Count(sel) - 1 do
            SobGroup_Clear("KAS_RegenOne")
            SobGroup_FillShipsByIndexRange("KAS_RegenOne", sel, i, 1)
            if SobGroup_Count("KAS_RegenOne") > 0 then
                local h = SobGroup_HealthPercentage("KAS_RegenOne")
                local hull = CatHull[strlower(SobGroup_GetShipType("KAS_RegenOne"))]
                if r.h[i] and hull and hull.regen and h > r.h[i] then
                    local regen = dt / hull.regen
                    if h - r.h[i] < regen then regen = h - r.h[i] end
                    h = h - regen
                    SobGroup_SetHealth("KAS_RegenOne", h)
                end
                r.h[i] = h
            end
        end
    end
    if left == 0 then Rule_Remove("KAS_NoRegenTick") end
end
function K_4939d0(sel) KAS_NoOp("4939d0", "kasfShipsClearRepairFactor") end

-- 0x4984c0(ships, on): invulnerable (taken for kasfShipsParalyze / HW1's SOF_DontApplyPhysics; but the bit is
-- Cataclysm's +0x18 flags 0x4, and its damage function (FUN at blast.c:11725) takes no health from such a ship).
-- Mission02: the BUSHAN-RE from its arrival until Fleet Intel's ambush briefing, the disguised corvettes and the decoy
-- while disguised (frozen, they never flew in: user, 2026-10-17); Mission01: a Kushan destroyer until its patrol
-- Kept on the ships and set again every second: HWRM's flag didn't survive the BUSHAN-RE's first-frame jump out and
-- back (it took fire once found: user, 2026-10-17); Cataclysm's stays on the ship
-- A disabled ship (K_49a2d0, a derelict) keeps it until a repair first holds it still (KAS_DisabledTick): Mission02's
-- Fleet Intel makes the BUSHAN-RE vulnerable in the briefing after it is found, and the pirates killed it while the
-- Worker flew to it (user, 2026-10-18: protection ends when the Worker gets there)
KAS_Invulnerable, KAS_InvulnerableHeld = {}, {}
function K_4984c0(sel, on)
    if on == 0 and KAS_Invulnerable[sel] and KAS_Disabled[sel] and KAS_Disabled[sel].held == nil then
        KAS_InvulnerableHeld[sel] = 1
        print("CKAS: " .. sel .. " stays invulnerable until a repair reaches it")
        return
    end
    KAS_InvulnerableHeld[sel] = nil
    if on ~= 0 then KAS_Invulnerable[sel] = 1 else KAS_Invulnerable[sel] = nil end
    if SobGroup_Count(sel) > 0 then SobGroup_SetInvulnerability(sel, on ~= 0 and 1 or 0) end
    if on ~= 0 and Rule_Exists("KAS_InvulnerableTick") == 0 then Rule_AddInterval("KAS_InvulnerableTick", 1) end
end
function KAS_InvulnerableTick()
    for sel, _ in KAS_Invulnerable do
        if SobGroup_Count(sel) > 0 then SobGroup_SetInvulnerability(sel, 1) end
    end
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

-- 0x499870(team): 1 if any ship has no command (ship+0x370, the command pointer: idle). Mission02's patrols wait on it
-- for their move to end before the next waypoint (always 1 made all six re-order every half second: the game stuttered,
-- user); Mission01 decides with it whether to hunt Workers.
function K_499870(sel)
    local n = SobGroup_Count(sel)
    if n == 0 then return 0 end
    SobGroup_CreateIfNotExist("KAS_IdleOne")
    local i = 0
    while i < n do
        SobGroup_Clear("KAS_IdleOne")
        SobGroup_FillShipsByIndexRange("KAS_IdleOne", sel, i, 1)
        if SobGroup_GetCurrentOrder("KAS_IdleOne") == COMMAND_Idle then return 1 end
        i = i + 1
    end
    return 0
end

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
    SobGroup_FillProximityPoint(n, src, KAS_Pos(vec), KAS_Dist(dist))
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
    Volume_AddSphere("KAS_FindVol", KAS_Pos(vec), KAS_Dist(radius))
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
    local p = KAS_Pos(vec)
    print(format("CKAS: ping %s at %.0f %.0f %.0f (%.0f from the origin)", name, p[1], p[2], p[3],
                 sqrt(p[1] * p[1] + p[2] * p[2] + p[3] * p[3])))   -- TEST: user, the pings too close together
    KAS_PingRemove(name, name)
    Volume_AddSphere("KAS_Ping_" .. name, KAS_Pos(vec), 10)
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
function K_496ae0()
    -- Mission02 cancels its focus at the end of Fleet Command's line, about when the canister goes: the camera stays
    -- on it until the blast and holds there a moment (user, the original)
    if KAS_JettFocus and KAS_Jett and (KAS_Jett.blown == nil or Universe_GameTime() - KAS_Jett.blown < KAS_JettisonHold) then
        Rule_AddInterval("KAS_JettisonCancelTick", 0.1)
        return
    end
    KAS_JettisonFocusEnd()
end
function KAS_JettisonCancelTick()
    if KAS_Jett.blown == nil or Universe_GameTime() - KAS_Jett.blown < KAS_JettisonHold then return end
    Rule_Remove("KAS_JettisonCancelTick")
    KAS_JettisonFocusEnd()
end                                                        -- kasfTutCameraFocusCancel

-- ------------------------------------------------------------------ sensors, camera, screen
-- kasfOpenSensors / kasfCloseSensors: Gearbox's KAS_SensorsToggle, which ducks the music (Sound_EnterIntelEvent) on
-- opening and lifts it only on the script's close; the player can close the sensors manager here (KAS_Lockout gives
-- the toggle back), and Mission02 left it ducked until its ambush (user, 2026-10-17: silent until then). So the duck
-- is lifted once the manager is shut, by whoever, and never doubled
function K_496bc0(flags)                                                                         -- kasfOpenSensors
    if KAS_SensorsDuck then Sound_ExitIntelEvent() end
    KAS_SensorsToggle(1, flags)
    KAS_SensorsDuck = { seen = nil, at = Universe_GameTime() }
    if Rule_Exists("KAS_SensorsDuckTick") == 0 then Rule_AddInterval("KAS_SensorsDuckTick", 0.5) end
end
function K_496c30()                                                                              -- kasfCloseSensors
    if KAS_SensorsDuck then
        KAS_SensorsDuck = nil
        KAS_SensorsToggle(0, 1)
    elseif Sensors_ManagerIsActive() ~= 0 then
        Sensors_Toggle(0)
        Sensors_EnableToggle(1)
        smFleetIntelState = 0
    end
end
function KAS_SensorsDuckTick()
    local d = KAS_SensorsDuck
    if d == nil then Rule_Remove("KAS_SensorsDuckTick") return end
    if Sensors_ManagerIsActive() ~= 0 then
        d.seen = 1
    elseif d.seen or Universe_GameTime() - d.at > 2 then   -- shut (or it never opened)
        Sound_ExitIntelEvent()
        KAS_SensorsDuck = nil
        Rule_Remove("KAS_SensorsDuckTick")
        print("CKAS: sensors manager shut: music duck lifted")
    end
end
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
    KAS_LockedOut = on
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
-- HWRM unrestricts only a restricted item and grants only one not yet researched ("unable to unrestrict" /
-- "unable to grant" otherwise: FUN_005f6221 / FUN_005f635c), e.g. Mission02 allowing the fighter drive it starts with
function KAS_Unrestrict(tech)
    if Player_HasResearch(0, tech) == 1 or Player_ResearchOptionIsRestricted(0, tech) ~= 1 then return end
    Player_UnrestrictResearchOption(0, tech)
end
function KAS_Grant(tech)
    if Player_HasResearch(0, tech) ~= 1 then Player_GrantResearchOption(0, tech) end
end
function K_496cf0(tech) KAS_Unrestrict(tech) print("CKAS: research allowed " .. tech) end         -- kasfAllowPlayerToResearch
function K_496d10(tech) KAS_Unrestrict(tech) print("CKAS: purchase allowed " .. tech) end         -- kasfAllowPlayerToPurchase
function K_497710(i, text) KAS_NoOp("497710", "kasfSetTraderDialog") end
function K_4977a0(scale) KAS_NoOp("4977a0", "kasfSetTraderPriceScale") end
function K_497800(off) KAS_NoOp("497800", "kasfSetTraderDisabled") end
-- kasfMusicPlay(trackNum): Cataclysm stream trackNum (tools/build_music.py), 1102 = a random one of 0-16.
function K_497000(track)
    if track == 1102 then track = random(0, 16) end
    if track < 0 or track > 61 then return end
    local path = format("data:sound/music/cataclysm/music_%02d", track)
    -- held while HWRM's arrival of the carried-over fleet runs, and played once the mothership is out (KAS_ArrivalWatch),
    -- as Gearbox's HW1 Mission02 starts its music only after singlePlayerPauseUntilHyperspaceComplete: Mission02's
    -- track, started at time 0, was silenced by the arrival, and asking for it again did nothing (user, 2026-10-17)
    if KAS_PersistFleet == 1 and KAS_Vars[KAS_Key_ShipsHaveArrived] ~= 1 then
        KAS_MusicHeld = path
        print("CKAS: music " .. path .. " held until the fleet is in")
        return
    end
    print("CKAS: music " .. path)
    Sound_MusicPlayType(path, MUS_Ambient)
end
-- kasfTechSetResearched(techName) (cataclysm.exe 0x498c10; first named kasfMusicStop): marks a technology researched
-- for the computer player (its tech table at 0x00b6dcd4, refreshed by FUN_00514140), "" clears them all; Mission02
-- gives the pirates' ambush team TECH_MIMIC and TECH_SALVAGE before kasfShipsUpgrade (K_498c70). Kept per tech for
-- every computer player (shiprules.lua CatUpgrade_Researched): their races have no Somtaaw research to grant
KAS_CPUTechs = {}
function K_498c10(tech)
    if tech == "" then KAS_CPUTechs = {} else KAS_CPUTechs[tech] = 1 end
    print("CKAS: computer tech " .. (tech == "" and "cleared" or tech))
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
-- Saved from a plain rule a moment later: called inside a KAS team rule (Rule_AddIntervalParam, while the rule
-- system walks its rules) the save failed with "invalid key for `next'" and aborted the calling script (Mission02's
-- watch never started Fleet Intel's briefing, user); Gearbox saves from a plain rule (KAS_EndStartingLetterbox)
function K_497290(mission, label)
    print("CKAS: autosave '" .. format("%02d", mission) .. " - " .. label .. "' (queued)")
    KAS_SaveMission, KAS_SaveLabel = mission, label
    if Rule_Exists("KAS_DoSave") == 0 then Rule_AddInterval("KAS_DoSave", 0.1) end
end
function KAS_DoSave()
    Rule_Remove("KAS_DoSave")
    print("CKAS: autosave '" .. format("%02d", KAS_SaveMission) .. " - " .. KAS_SaveLabel .. "'")
    Campaign_QuickSaveNb(KAS_SaveMission, KAS_SaveLabel)
    print("CKAS: autosave done")
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
    KAS_KuunLan("KAS_MothershipGroup0", 0)  -- Gearbox's KAS_PlayerMothership takes it from here
    print("CKAS: roll call mothership x" .. SobGroup_Count("KAS_MothershipGroup0"))
    singlePlayerHyperspaceButtonEnable()
    if Rule_Exists("KAS_HyperspaceTick") == 0 then Rule_AddInterval("KAS_HyperspaceTick", 0.25) end
end

KAS_HyperspaceLastState = -1
-- The roll call's Go Now is Cataclysm's Emergency Hyperspace (user: it instantly jumps every hyperspace capable ship
-- and leaves everything else; part of the tension of some missions). Decompiled: its roll call offers Go Now
-- (0x5173a0: every ship still out docked instantly, then the jump) or Emergency Hyperspace (0x5174b0: every ship
-- still out flagged left behind, the hyperspace capable ones jump), the second when any player ship has a state
-- not identified yet (0x518f50: bytes 0x35a / 0x35b). Here always the second (data/ui/hyperspacerollcallscreen.lua
-- calls this; Gearbox's normal roll call, everything docked, is untouched). Ships already docked go with their
-- carrier; Gearbox's state machine then watches the jump (HYPERSPACE_SHIPSLEAVING, substate 2): white-out, mission
-- complete. Ships left behind are not in hyperspace when it completes.
function KAS_EmergencyHyperspace()
    if spGameInfo_hyperspaceState ~= HYPERSPACE_WAITINGROLLCALL then return end
    print("CKAS: EMERGENCY HYPERSPACE")
    SobGroup_CreateIfNotExist("KAS_LeftBehind")
    SobGroup_CreateIfNotExist("KAS_Jumpers")
    Player_GetShipsByFilterExclude(0, "KAS_LeftBehind", "Ability", "HyperSpaceCommand")
    SobGroup_FilterExclude("KAS_LeftBehind", "KAS_LeftBehind", "Docked", "")
    singlePlayerHyperspaceSkipNonDockers("KAS_LeftBehind")
    SobGroup_Stop(0, "KAS_LeftBehind")
    Player_GetShipsByFilterInclude(0, "KAS_Jumpers", "Ability", "HyperSpaceCommand")
    print("CKAS: " .. SobGroup_Count("KAS_Jumpers") .. " ships jump, " .. SobGroup_Count("KAS_LeftBehind")
          .. " left behind")
    SobGroup_EnterHyperSpaceOffMap("KAS_Jumpers")
    spGameInfo_screenSkipped = 1
    if spGameInfo_screenLoaded ~= 0 then
        MainUI_ActivateScreen("HyperspaceRollCallScreen", 0)
        MainUI_UnloadScreen("HyperspaceRollCallScreen")
        spGameInfo_screenLoaded = 0
    end
    spGameInfo_hyperspaceState = HYPERSPACE_SHIPSLEAVING
    spGameInfo_hyperspaceSubState = 2
end

function KAS_DevHyperspace()
    Rule_Remove("KAS_DevHyperspace")
    KAS_HyperspaceAllow()
end

-- The ships the jump waits for: every hyperspace capable ship of the player's, the Kuun-Lan only the real one.
-- Gearbox's WatchHyperspacingShips waits for every ship with HyperSpaceCommand to be in hyperspace, the intro NIS's
-- despawned Kuun-Lan too (KAS_KuunLan), which never jumps: the Emergency Hyperspace's Kuun-Lan left and the mission
-- never ended (user, Mission01). Done when each is in hyperspace or docked (inside one that is).
function KAS_HyperspaceJumpersGone()
    SobGroup_CreateIfNotExist("KAS_HSWatch")
    SobGroup_CreateIfNotExist("KAS_HSType")
    SobGroup_CreateIfNotExist("KAS_HSOne")
    Player_GetShipsByFilterInclude(0, "KAS_HSWatch", "Ability", "HyperSpaceCommand")
    local i = 1
    while i <= getn(KAS_MothershipTypes) do
        SobGroup_Clear("KAS_HSType")
        Player_FillShipsByType("KAS_HSType", 0, KAS_MothershipTypes[i])
        SobGroup_FillSubtract("KAS_HSWatch", "KAS_HSWatch", "KAS_HSType")
        i = i + 1
    end
    SobGroup_SobGroupAdd("KAS_HSWatch", "KAS_MothershipGroup0")
    local n = SobGroup_Count("KAS_HSWatch")
    for k = 0, n - 1 do
        SobGroup_Clear("KAS_HSOne")
        SobGroup_FillShipsByIndexRange("KAS_HSOne", "KAS_HSWatch", k, 1)
        if SobGroup_Count("KAS_HSOne") > 0 and SobGroup_AreAllInHyperspace("KAS_HSOne") == 0
           and SobGroup_IsDocked("KAS_HSOne") == 0 then
            return 0
        end
    end
    return 1
end

function KAS_HyperspaceTick()
    -- the Support Units fillers out of the world before the fleet is saved for the next mission
    if spGameInfo_hyperspaceState == HYPERSPACE_SHIPSLEAVING and KAS_SUOff == nil then KAS_SUFillersClear() end
    if spGameInfo_hyperspaceState == HYPERSPACE_SHIPSLEAVING and spGameInfo_hyperspaceSubState == 2
       and spGameInfo_hyperspaceFails == 0 and KAS_HyperspaceJumpersGone() ~= 0 then
        -- (Gearbox's SHIPSLEAVING substate 2 on all ships gone)
        print("CKAS: every jumping ship is in hyperspace")
        spGameInfo_hyperspaceState = HYPERSPACE_WHITEOUT
        spGameInfo_hyperspaceTimeStamp = Universe_GameTime() + HYPERSPACE_WHITEOUTTIME
        Universe_Fade(1, 1)
    end
    singlePlayerHyperspaceStateUpdate()
    if spGameInfo_hyperspaceState ~= KAS_HyperspaceLastState then
        KAS_HyperspaceLastState = spGameInfo_hyperspaceState
        print("CKAS: hyperspace state " .. spGameInfo_hyperspaceState)
    end
end

-- The player's Kuun-Lan: the real one (KAS_ArrivalMS) once captured, else the first by type (by type alone the
-- intro NIS's despawned copy is found too). Gearbox's KAS_PlayerMothership (the roll call's, which wants exactly
-- one) can't be redefined ("Cannot overwrite function": every attempt was dropped, the HYPERSPACE button found
-- "no mothership", user): it copies its cache group KAS_MothershipGroup<player> when that has ships, so
-- KAS_HyperspaceAllow fills that with this.
function KAS_KuunLan(sobGroupName, playerIndex)
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

-- ================================================================== Mission02 API (decompiled: Cataclysm-decomp/out/m02_stubs.c)
-- Vectors. kasVectorPtr gives a name (the translator's label, else "vec_<hash>": KAS_VecKey); the vectors a mission
-- sets live in KAS_Vec (HWRM coordinates, mission2level.py pos()), any other name is a level point. Engine calls take
-- KAS_Pos(name), a position. HW1 keeps computed vectors inside the universe (+-smUniverseSize per axis: KAS_Universe
-- from the mission's _paths.lua).
KAS_Vec = {}
function KAS_VecKey(h) return KAS_HashLabel(h) or format("vec_%08x", h) end
function KAS_Pos(v)
    if type(v) == "table" then return v end
    local p = KAS_Vec[v]
    if p then return { p[1], p[2], p[3] } end
    return Volume_GetPosition(v)
end
function KAS_SetVec(name, p)
    if KAS_Universe then
        local i = 1
        while i <= 3 do
            if p[i] > KAS_Universe[i] then p[i] = KAS_Universe[i] elseif p[i] < -KAS_Universe[i] then p[i] = -KAS_Universe[i] end
            i = i + 1
        end
    end
    KAS_Vec[name] = p
end
-- a random direction: three uniform components normalised (cataclysm.exe FUN_00419ed0)
function KAS_RandomDir()
    local x, y, z, l = 0, 0, 0, 0
    while l < 0.0001 do
        x, y, z = RandomRange(-1, 1), RandomRange(-1, 1), RandomRange(-1, 1)
        l = sqrt(x * x + y * y + z * z)
    end
    return { x / l, y / l, z / l }
end
-- kasfVectorSet(name, x, y, z) (0x498dd0), HW1 coordinates
function K_498dd0(h, x, y, z)
    KAS_Vec[KAS_VecKey(h)] = { -KAS_WorldScale * x, KAS_WorldScale * z, KAS_WorldScale * y }
end
-- 0x4991d0(dst, src, dist): dst = src + a random direction x dist (Mission02's patrols pick waypoints so), each
-- axis clamped to the universe (the exe clamps to DAT_00892d20..28: Mission02's ambushers came in 23600 from the
-- BUSHAN-RE, itself 46800 from the centre of a 65625 map)
-- KAS_RandomVecScale: teams whose random points sit nearer than Cataclysm's (Mission02's decoys hyperspace in 45000 out
-- from the BUSHAN-RE: closer in, user 2026-10-17)
KAS_RandomVecScale = { pTricky = 0.75 }
function K_4991d0(dst, src, dist)
    local p, d, r = KAS_Pos(src), KAS_RandomDir(), KAS_Dist(dist) * (KAS_RandomVecScale[KAS_Team] or 1)
    local q = { p[1] + d[1] * r, p[2] + d[2] * r, p[3] + d[3] * r }
    if KAS_Universe then
        for k = 1, 3 do
            if q[k] > KAS_Universe[k] then q[k] = KAS_Universe[k] elseif q[k] < -KAS_Universe[k] then q[k] = -KAS_Universe[k] end
        end
    end
    KAS_SetVec(dst, q)
end
-- 0x498f30(dst, a, b, n, total): dst = a + (b - a) x n / total
function K_498f30(dst, a, b, n, total)
    local p, q, f = KAS_Pos(a), KAS_Pos(b), n / total
    KAS_SetVec(dst, { p[1] + (q[1] - p[1]) * f, p[2] + (q[2] - p[2]) * f, p[3] + (q[3] - p[3]) * f })
end

-- formations (0x4927b0 / 4927e0 / 492840 / 492870 set the team's formation 1 / 2 / 4 / 5); Gearbox's KAS_SetFormation
-- names them (Delta3D -> "x", its approximation)
function K_4927b0() KAS_Form("Broad") end                                                            -- kasfFormationBroad
function K_4927e0() KAS_Form("Delta3D") end                                                          -- kasfFormationDelta3D
function K_492840() KAS_Form("Wall") end                                                             -- kasfFormationWall
function K_492870() KAS_Form("Sphere") end                                                           -- kasfFormationSphere

-- kasfIntercept(targets): the team flies to the first target (0x4924e0: a move order on it, not an attack; Mission02's
-- decoy intercepts the allied destroyer) and stops once near: HW1's aimProcessIntercept, done within
-- AIM_INTERCEPT_FINISH_DISTSQ (Cataclysm's aiplayer.script: 16000000, 4000 away), the destination re-aimed every few
-- seconds. KAS_InterceptStop: targets the interceptors stop further out from, at the edge of their sensors (Mission02:
-- the disguised corvettes stop where the BUSHAN-RE's sensors (kstandarddestroyer.shp fowRadius 9000) pick them up and
-- transform there, user 2026-10-17; they flew right up to it; then slightly closer, 8000, user)
KAS_InterceptFinish, KAS_InterceptRecalc = 4000, 3
KAS_InterceptStop = { kDestroyer = 8000 }
KAS_Intercepts = {}
function K_4924e0(sel)
    KAS_EndPatrol()
    if SobGroup_Count(KAS_Team) > 0 and SobGroup_Count(sel) > 0 then
        KAS_Intercepts[KAS_Team] = { target = sel, dist = KAS_Dist(KAS_InterceptStop[sel] or KAS_InterceptFinish), next = 0 }
        if Rule_Exists("KAS_InterceptTick") == 0 then Rule_AddInterval("KAS_InterceptTick", 0.5) end
        KAS_InterceptTick()
    end
end
function KAS_InterceptTick()
    local now, left, done = Universe_GameTime(), 0, {}
    for team, it in KAS_Intercepts do
        if SobGroup_Count(team) == 0 or SobGroup_Count(it.target) == 0 then
            tinsert(done, team)
        else
            local p, q = SobGroup_GetPosition(team), SobGroup_GetPosition(it.target)
            local d = { q[1] - p[1], q[2] - p[2], q[3] - p[3] }
            if d[1] * d[1] + d[2] * d[2] + d[3] * d[3] < it.dist * it.dist then
                SobGroup_Stop(KAS_Owner(team), team)       -- arrived: idle, which the missions wait on (K_4998c0)
                print("CKAS: " .. team .. " intercepted " .. it.target)
                tinsert(done, team)
            else
                left = left + 1
                if now >= it.next and SobGroup_AreAllInRealSpace(team) == 1 then
                    it.next = now + KAS_InterceptRecalc
                    SobGroup_MoveToPoint(KAS_Owner(team), team, q)
                end
            end
        end
    end
    for i = 1, getn(done) do KAS_Intercepts[done[i]] = nil end
    if left == 0 then Rule_Remove("KAS_InterceptTick") end
end
-- kasfShipsOrderAttributes(ships): the first ship's order attributes (HW1 COMMAND_MASK_*: 1 formation, 2 protecting).
-- Protecting = a guard order (K_492960) whose guarded ships are still alive (HW1 drops the order when they die)
function K_492ae0(sel)
    local a = 0
    local g = KAS_Guards[sel]
    if g and SobGroup_Count(g.sel) > 0 then a = a + 2 end
    if KAS_TeamFormation[sel] then a = a + 1 end
    return a
end
-- kasfTeamHealthLowest: the team's weakest ship, percent (Gearbox's KAS_TeamHealthLowest)
-- kasfTeamHealthLowest (0x492b90): the lowest of the team's ships' health, whole percent of its maximum (rounded).
-- (SobGroup_MinimumHealth x 100 read over 39 at 20 % health: Mission02's destroyer "repaired" at once and the
-- disguised corvettes came straight after it was found, user)
function K_492b90()
    local n = SobGroup_Count(KAS_Team)
    if n == 0 then return 0 end
    local low = 110
    SobGroup_CreateIfNotExist("KAS_HealthOne")
    for i = 0, n - 1 do
        SobGroup_Clear("KAS_HealthOne")
        SobGroup_FillShipsByIndexRange("KAS_HealthOne", KAS_Team, i, 1)
        if SobGroup_Count("KAS_HealthOne") > 0 then
            local h = floor(SobGroup_HealthPercentage("KAS_HealthOne") * 100 + 0.5)
            if h < low then low = h end
        end
    end
    return low
end
-- 0x492d60(out): the asteroids flagged ATTRIBUTES_HeadShotVelToMothership (0x200), Mission02's "meteors": our
-- meteor ships (KAS_MeteorInit)
function K_492d60(gs)
    SobGroup_Clear(gs)
    if KAS_MeteorStorms then
        for s = 1, getn(KAS_MeteorStorms) do SobGroup_SobGroupAdd(gs, KAS_MeteorStorms[s].group) end
    end
    return SobGroup_Count(gs)
end

-- ------------------------------------------------------------------ meteor storms (Cataclysm MeteorStorm)
-- Each meteor (a cat_meteor<n> ship, tools/make_meteor.py; placed and its storm's velocity / wrap box written by
-- tools/mission2level.py add_storm) flies its storm's velocity for good: cataclysm.exe FUN_005432d0 moves every
-- meteor at its velocity and, per axis, puts one that passes +ext at -ext (and -ext at +ext). Here each is ordered
-- to where it leaves the box at its storm's speed, and moved across when it gets there.
-- A meteor touching a ship (FUN_0043bac0: closer than the two collision radii; no bump, FUN_00545540) costs both
-- the lower of their two healths: a fighter dies, a ship that outweighs the meteor loses its health and destroys it.
dofilepath("data:scripts/cataclysm/hullinfo_gen.lua")   -- CatHull: ship sizes (tools/make_hullinfo.py)
-- collision radii (Cataclysm's are spheres round the whole model): half the diagonal of the HOD box, CatHull
KAS_HullRadii = {}
function KAS_HullRadius(t, default)
    t = strlower(t or "")
    if KAS_HullRadii[t] == nil then
        local hull, r = CatHull[t], default
        if hull then
            local b, q = hull.box, 0
            for k = 1, 3 do
                local a = abs(b[k])
                if abs(b[k + 3]) > a then a = abs(b[k + 3]) end
                q = q + a * a
            end
            r = sqrt(q)
        end
        KAS_HullRadii[t] = r
    end
    return KAS_HullRadii[t]
end
KAS_MeteorBlast, KAS_MeteorBlastScale = "dmg_cloud_main_explosion_combo", 7
KAS_MeteorBlastSound = "data:sound/sfx/etg/explosion/medium/etg_explode_medium_firey"
KAS_MeteorShipSpeed = 400      -- the meteor ships' top speed (tools/make_meteor.py MAX_SPEED)
KAS_MeteorReach = 1500         -- a first sweep: meteors this close to a ship are measured (largest meteor + hull)
-- contact slack on the meteor's radius: HWRM's physics stops the hulls where they touch and slides the ship along the
-- meteor, so they never got closer (an asteroid slid round an Acolyte: user, 2026-10-17)
KAS_MeteorContact = 1.2
KAS_MeteorHitFX, KAS_MeteorHitScale = "dmg_cloud_explosion_large_nodebris", 2
KAS_MeteorHitSound = "data:sound/sfx/etg/explosion/small/etg_explode_small_firey"
KAS_Meteors = {}               -- per meteor: { g = its group, st = its storm, due = when it reaches the box }
-- a meteor turned nose-first along its storm's velocity (coordsys rows: right, up, bow). A meteor can't turn
-- (tools/make_meteor.py, the headshot asteroid's: main engine only within 30 degrees of its heading): placed at
-- random headings, only the ~7 % already facing the way moved, 10-12 in each storm of 140 (user / log)
function KAS_MeteorFace(m)
    local st = m.st
    if st.facing == nil then
        local f = { st.v[1] / st.speed, st.v[2] / st.speed, st.v[3] / st.speed }
        local up = { 0, 1, 0 }
        if abs(f[2]) > 0.99 then up = { 1, 0, 0 } end
        local r = { up[2] * f[3] - up[3] * f[2], up[3] * f[1] - up[1] * f[3], up[1] * f[2] - up[2] * f[1] }
        local l = sqrt(r[1] * r[1] + r[2] * r[2] + r[3] * r[3])
        r = { r[1] / l, r[2] / l, r[3] / l }
        local u = { f[2] * r[3] - f[3] * r[2], f[3] * r[1] - f[1] * r[3], f[1] * r[2] - f[2] * r[1] }
        st.facing = { r[1], r[2], r[3], u[1], u[2], u[3], f[1], f[2], f[3] }
    end
    SobGroup_SetTransform(m.g, st.facing)
end
function KAS_MeteorInit()
    if KAS_MeteorStorms == nil or getn(KAS_MeteorStorms) == 0 then return end
    for s = 1, getn(KAS_MeteorStorms) do
        local st = KAS_MeteorStorms[s]
        st.speed = sqrt(st.v[1] * st.v[1] + st.v[2] * st.v[2] + st.v[3] * st.v[3])
        -- each meteor's own group from the level (tools/mission2level.py add_storm)
        for i = 0, st.n - 1 do
            local g = st.group .. "_" .. i .. "g"
            SobGroup_SetSpeed(g, st.speed / KAS_MeteorShipSpeed)
            -- no collisions of HWRM's own: Cataclysm's meteors don't bump (FUN_00545540), only the scripted contact
            -- (HWRM's nudged them up or down just before it: user, 2026-10-17); a ghost still flies its orders (the Ram)
            SobGroup_SetGhost(g, 1)
            local m = { g = g, st = st }
            tinsert(KAS_Meteors, m)
            KAS_MeteorFace(m)
            KAS_MeteorAim(m)
        end
    end
    SobGroup_CreateIfNotExist("KAS_MeteorAll")
    SobGroup_Clear("KAS_MeteorAll")
    K_492d60("KAS_MeteorAll")
    Rule_AddInterval("KAS_MeteorTick", 0.25)
    print("CKAS: " .. getn(KAS_Meteors) .. " meteors in " .. getn(KAS_MeteorStorms) .. " storms")
end
-- ordered on in legs: KAS_MeteorLeg seconds ahead, again every KAS_MeteorStep (ordered straight to the far edge of
-- the box, up to 200000 away, nine meteors in ten stood still, the same ones every run: user / log), and the last
-- leg to where it leaves its box, KAS_MeteorEdge short of it (the box is the world bounds), then moved across
KAS_MeteorEdge, KAS_MeteorLeg, KAS_MeteorStep = 100, 10, 5
function KAS_MeteorAim(m)
    local p, v = SobGroup_GetPosition(m.g), m.st.v
    local e = { m.st.ext[1] - KAS_MeteorEdge, m.st.ext[2] - KAS_MeteorEdge, m.st.ext[3] - KAS_MeteorEdge }
    local t = 1000000
    for k = 1, 3 do
        local tk = nil
        if v[k] > 0 then tk = (e[k] - p[k]) / v[k] elseif v[k] < 0 then tk = (-e[k] - p[k]) / v[k] end
        if tk and tk < t then t, m.axis = tk, k end
    end
    if t < 0 then t = 0 end
    m.wrap = t <= KAS_MeteorStep
    if m.wrap then m.due = Universe_GameTime() + t else m.due = Universe_GameTime() + KAS_MeteorStep end
    if t > KAS_MeteorLeg then t = KAS_MeteorLeg end
    SobGroup_MoveToPoint(KAS_MeteorPlayer, m.g, { p[1] + v[1] * t, p[2] + v[2] * t, p[3] + v[3] * t })
end
function KAS_MeteorTick()
    local now = Universe_GameTime()
    for i = 1, getn(KAS_Meteors) do
        local m = KAS_Meteors[i]
        if m.dead == nil and now >= m.due then
            if SobGroup_Count(m.g) == 0 then
                m.dead = 1
            else
                if m.wrap then
                    local p, e = SobGroup_GetPosition(m.g), m.st.ext[m.axis] - KAS_MeteorEdge
                    if m.st.v[m.axis] > 0 then p[m.axis] = -e else p[m.axis] = e end
                    SobGroup_SetPosition(m.g, p)
                    KAS_MeteorFace(m)
                end
                KAS_MeteorAim(m)
            end
        end
    end
    KAS_MeteorHits()
end
-- collisions: per ship of the other players, the meteors of each storm near it, then the measured ones. Swept: a
-- meteor flies 60-75 between two checks (storm speeds 245-300 a second, every 0.25 s), more than a small contact (an
-- Acolyte's with a small meteor is ~35), so the path it flew since the last check counts (its storm's velocity; the
-- ship's own movement left out); sampled only, passes went through ships unhurt (user, 2026-10-17: inconsistent)
function KAS_MeteorHits()
    local now = Universe_GameTime()
    local dt = now - (KAS_MeteorHitsAt or now)
    KAS_MeteorHitsAt = now
    if dt > 1 then dt = 1 end
    SobGroup_CreateIfNotExist("KAS_MeteorTargets")
    SobGroup_Clear("KAS_MeteorTargets")
    for pl = 0, Universe_PlayerCount() - 1 do
        if pl ~= KAS_MeteorPlayer then SobGroup_SobGroupAdd("KAS_MeteorTargets", "Player_Ships" .. pl) end
    end
    SobGroup_CreateIfNotExist("KAS_MeteorShip")
    SobGroup_CreateIfNotExist("KAS_MeteorNear")
    SobGroup_CreateIfNotExist("KAS_MeteorOne")
    for i = 0, SobGroup_Count("KAS_MeteorTargets") - 1 do
        SobGroup_Clear("KAS_MeteorShip")
        SobGroup_FillShipsByIndexRange("KAS_MeteorShip", "KAS_MeteorTargets", i, 1)
        SobGroup_Clear("KAS_MeteorNear")
        for s = 1, getn(KAS_MeteorStorms) do
            if SobGroup_Count("KAS_MeteorShip") == 0 then break end
            SobGroup_Clear("KAS_MeteorNear")
            SobGroup_FillProximitySobGroup("KAS_MeteorNear", KAS_MeteorStorms[s].group, "KAS_MeteorShip", KAS_MeteorReach)
            if SobGroup_Count("KAS_MeteorNear") > 0 then KAS_MeteorHitShip(KAS_MeteorStorms[s].v, dt) end
        end
    end
end
-- a meteor's radius: its largest half-extent (a rock; the box's corners made small ships' contacts too wide)
KAS_MeteorRadii = {}
function KAS_MeteorRadius(t)
    t = strlower(t or "")
    if KAS_MeteorRadii[t] == nil then
        local hull, r = CatHull[t], 30
        if hull then
            r = 0
            for k = 1, 6 do if abs(hull.box[k]) > r then r = abs(hull.box[k]) end end
        end
        KAS_MeteorRadii[t] = r
    end
    return KAS_MeteorRadii[t]
end
-- the distance from a point (relative to the ship, world axes) to the ship's hull box, turned with the ship (coordsys
-- rows: right, up, bow; CatHull box: min x y z, max x y z). The ship as a sphere round its box's corners was far too
-- wide for long ships (user, 2026-10-17: the larger ships' collision far too large); Cataclysm checks the box after
-- the sphere too (HW1 collision rectangles)
function KAS_BoxDistance(d, m, box)
    local q = { d[1] * m[1] + d[2] * m[2] + d[3] * m[3], d[1] * m[4] + d[2] * m[5] + d[3] * m[6],
                d[1] * m[7] + d[2] * m[8] + d[3] * m[9] }
    local s = 0
    for k = 1, 3 do
        local e = 0
        if q[k] < box[k] then e = box[k] - q[k] elseif q[k] > box[k + 3] then e = q[k] - box[k + 3] end
        s = s + e * e
    end
    return sqrt(s)
end
KAS_MeteorSamples = 4          -- points along a meteor's path since the last check (the closest counts)
function KAS_MeteorHitShip(v, dt)
    local st = strlower(SobGroup_GetShipType("KAS_MeteorShip"))
    local hull = CatHull[st]
    local rs = KAS_HullRadius(st, 20)
    local m = nil
    if hull then m = SobGroup_GetCoordSys("KAS_MeteorShip") end
    local ps = SobGroup_GetPosition("KAS_MeteorShip")
    for j = 0, SobGroup_Count("KAS_MeteorNear") - 1 do
        SobGroup_Clear("KAS_MeteorOne")
        SobGroup_FillShipsByIndexRange("KAS_MeteorOne", "KAS_MeteorNear", j, 1)
        local pm = SobGroup_GetPosition("KAS_MeteorOne")
        local rm = KAS_MeteorRadius(SobGroup_GetShipType("KAS_MeteorOne"))
        -- the closest the meteor came to the hull on its path since the last check (from d - v dt to d)
        local gap = nil
        for k = 0, KAS_MeteorSamples do
            local f = 1 - k / KAS_MeteorSamples
            local d = { pm[1] - v[1] * dt * f - ps[1], pm[2] - v[2] * dt * f - ps[2], pm[3] - v[3] * dt * f - ps[3] }
            local g
            if m then g = KAS_BoxDistance(d, m, hull.box) else g = sqrt(d[1] * d[1] + d[2] * d[2] + d[3] * d[3]) - rs end
            if gap == nil or g < gap then gap = g end
        end
        local reach = rm * KAS_MeteorContact
        if gap < reach then
            -- the lower health from both (FUN_00545540: damage = min of the two current healths, to each)
            local hs = SobGroup_HealthPercentage("KAS_MeteorShip") * SobGroup_MaxHealthTotal("KAS_MeteorShip")
            local hm = SobGroup_HealthPercentage("KAS_MeteorOne") * SobGroup_MaxHealthTotal("KAS_MeteorOne")
            local dmg = hs
            if hm < dmg then dmg = hm end
            SobGroup_SetHealth("KAS_MeteorShip", (hs - dmg) / SobGroup_MaxHealthTotal("KAS_MeteorShip"))
            SobGroup_SetHealth("KAS_MeteorOne", (hm - dmg) / SobGroup_MaxHealthTotal("KAS_MeteorOne"))
            KAS_MeteorHitN = (KAS_MeteorHitN or 0) + 1
            local vol = "KAS_MeteorHit" .. KAS_MeteorHitN
            Volume_AddSphere(vol, pm, 1)
            if hm <= dmg then
                -- the meteor destroyed: a frigate-sized blast (no death of its own: the ship is only a model)
                FX_PlayEffect(KAS_MeteorBlast, vol, KAS_MeteorBlastScale)
                Sound_SFXPlay3D(KAS_MeteorBlastSound, vol)
            else
                FX_PlayEffect(KAS_MeteorHitFX, vol, KAS_MeteorHitScale)
                Sound_SFXPlay3D(KAS_MeteorHitSound, vol)
            end
            print("CKAS: meteor hit " .. SobGroup_GetShipType("KAS_MeteorShip") .. " for " .. floor(dmg))
            if hs <= dmg then return end
        end
    end
end
-- 0x493400(ships): bit 3 of the first ship's flags at +0x1cc (kasfDockStay won't dock with such a ship: taken as "not
-- built yet"). HWRM modules are built when they exist
function K_493400(sel) return 0 end
-- 0x493490(bits): ORs ship attributes into the team's ships (it is no "BitClear"). Mission02 sets
-- ATTRIBUTES_StartInHS (0x80) right before kasfTeamHyperspaceOut, which then despawns them (Gearbox's handling)
KAS_TeamAttr = {}
function K_493490(bits)
    KAS_TeamAttr[KAS_Team] = bits
    if bits ~= 128 then KAS_NoOp("493490", "team attributes " .. bits) end
end
-- kasfTeamHyperspaceIn(vec) / kasfTeamHyperspaceInNear(vec, dist) / kasfTeamHyperspaceOut (Gearbox's KAS_Team*)
function K_493600(vec)
    print("CKAS: " .. KAS_Team .. " hyperspaces in")
    KAS_Returned(KAS_Team)
    SobGroup_HyperspaceToVector(KAS_Team, KAS_Pos(vec))
    SobGroup_SetHidden(KAS_Team, 0)
    if Universe_GameTime() < 1 then
        -- a team hyperspacing in as the mission starts (after its first-frame despawn, KAS_TeamHyperspaceOut): the jump
        -- brings it back but may be undone in the same frame (the disabled state switching hyperspace off: Mission02's
        -- destroyer stayed at its level spot past the map's edge, user), so it is also put there for the first seconds
        -- (SobGroup_Spawn left it despawned: counted, but nowhere to be seen, user)
        KAS_PlaceAt[KAS_Team] = { p = KAS_Pos(vec), till = Universe_GameTime() + 5 }
        if Rule_Exists("KAS_PlaceAtTick") == 0 then Rule_AddInterval("KAS_PlaceAtTick", 0.25) end
    end
end
KAS_PlaceAt = {}
function KAS_PlaceAtTick()
    local now, left, done = Universe_GameTime(), 0, {}
    for team, a in KAS_PlaceAt do
        if now > a.till then
            tinsert(done, team)
        else
            left = left + 1
            if SobGroup_Count(team) > 0 then
                local q = SobGroup_GetPosition(team)
                local d = (q[1] - a.p[1]) * (q[1] - a.p[1]) + (q[2] - a.p[2]) * (q[2] - a.p[2]) + (q[3] - a.p[3]) * (q[3] - a.p[3])
                if d > 1000 * 1000 then
                    SobGroup_SetPosition(team, a.p)
                    print(format("CKAS: %s put at %.0f %.0f %.0f", team, a.p[1], a.p[2], a.p[3]))
                end
            end
        end
    end
    for i = 1, getn(done) do KAS_PlaceAt[done[i]] = nil end
    if left == 0 then Rule_Remove("KAS_PlaceAtTick") end
end
function K_493630(vec, dist)
    local p, d, r = KAS_Pos(vec), KAS_RandomDir(), KAS_Dist(dist)
    print("CKAS: " .. KAS_Team .. " hyperspaces in near")
    KAS_Returned(KAS_Team)
    SobGroup_HyperspaceToVector(KAS_Team, { p[1] + d[1] * r, p[2] + d[2] * r, p[3] + d[3] * r })
    SobGroup_SetHidden(KAS_Team, 0)
end
function K_493800()
    KAS_TeamHyperspaceOut(KAS_Team)
    if Universe_GameTime() >= 1 then     -- (at frame 0 a despawn, the team hyperspaces in later)
        SobGroup_CreateIfNotExist("KAS_Departed")
        SobGroup_SobGroupAdd("KAS_Departed", KAS_Team)
        print("CKAS: " .. KAS_Team .. " departed (" .. SobGroup_Count(KAS_Team) .. " ships no longer counted)")
    end
end
-- kasfShipsSetMaxVelocity / ClearMaxVelocity (0x4938f0 / 493940): Mission02 holds the crippled destroyer at 1
function K_4938f0(sel, v)
    if v <= 10 then SobGroup_SetSpeed(sel, 0) else KAS_NoOp("4938f0", "max velocity " .. v) end
end
function K_493940(sel) SobGroup_SetSpeed(sel, 1) end
function K_493f40() end                                                -- kasfDisableAllAIFeatures (CPU_Enable(p, 0))
-- kasfUnderAttack(out) (0x494510: ships whose attack order targets the team) and 0x498630(ships, out): the same for
-- any selection
function KAS_Attackers(sel, out)
    SobGroup_Clear(out)
    if SobGroup_Count(sel) == 0 then return 0 end
    SobGroup_GetAttackers(sel, out)
    return SobGroup_Count(out)
end
function K_494510(out) return KAS_Attackers(KAS_Team, out) end                                     -- kasfUnderAttack
function K_494450(team, out) return KAS_Attackers(team, out) end                            -- kasfUnderAttackElsewhere
function K_498630(sel, out) return KAS_Attackers(sel, out) end
-- kasfDockStay(ships): dock with the first and stay (0x494630)
function K_494630(sel)
    KAS_EndPatrol()
    if SobGroup_Count(sel) > 0 then SobGroup_DockSobGroupAndStayDocked(KAS_Team, sel) end
end
-- selection filters through the generic one (0x494f90)
function KAS_Intersect(n, o, keep)
    local src = KAS_SelSrc(n, o)
    SobGroup_CreateIfNotExist("KAS_IsectTmp")
    SobGroup_Clear("KAS_IsectTmp")
    SobGroup_FillSubtract("KAS_IsectTmp", src, keep)           -- the ones not kept
    SobGroup_Clear(n)
    SobGroup_FillSubtract(n, src, "KAS_IsectTmp")
    return SobGroup_Count(n)
end
-- 0x495410(new, orig, ships): orig's ships that are in ships
function K_495410(n, o, sel) return KAS_Intersect(n, o, sel) end
-- 0x495180(new, orig, ships): orig's ships in the first of ships' attacker list (Mission02's pod guards: the enemies
-- attacking the message pod)
function K_495180(n, o, sel)
    SobGroup_CreateIfNotExist("KAS_PodAttackers")
    if KAS_Attackers(sel, "KAS_PodAttackers") == 0 then
        SobGroup_Clear(n)
        return 0
    end
    return KAS_Intersect(n, o, "KAS_PodAttackers")
end
-- 0x4954d0(new, orig): strike craft (statics +0x24 == 0: not capital; not class 9)
function K_4954d0(n, o)
    local src = KAS_SelSrc(n, o)
    SobGroup_Clear(n)
    local fam = { "Fighter", "Corvette", "Utility" }
    SobGroup_CreateIfNotExist("KAS_FamTmp")
    local i = 1
    while i <= getn(fam) do
        SobGroup_Clear("KAS_FamTmp")
        SobGroup_FilterInclude("KAS_FamTmp", src, "DisplayFamily", fam[i])
        SobGroup_SobGroupAdd(n, "KAS_FamTmp")
        i = i + 1
    end
    return SobGroup_Count(n)
end
-- 0x495640(new, orig, "CLASS_x"): select by HW1 ship class (not "damaged"); HWRM display families
KAS_ClassFamily = { CLASS_Fighter = "Fighter", CLASS_Corvette = "Corvette", CLASS_Frigate = "Frigate",
                    CLASS_Destroyer = "Capital", CLASS_HeavyCruiser = "Capital", CLASS_Carrier = "Capital",
                    CLASS_Mothership = "Flagship", CLASS_NonCombat = "Utility", CLASS_Resource = "Utility" }
function K_495640(n, o, class)
    local src = KAS_SelSrc(n, o)
    SobGroup_Clear(n)
    local fam = KAS_ClassFamily[class]
    if fam == nil then
        KAS_WarnOnce("cls" .. class, "0x495640: no family for " .. class)
        return 0
    end
    SobGroup_FilterInclude(n, src, "DisplayFamily", fam)
    return SobGroup_Count(n)
end
function K_496150() end                                                -- kasfBuilderRestrictNone
-- 0x4967b0(type): a build job of that type running for the player (FUN_00534040: the player's build queues).
-- Mission02 starts its ore canister sequence when the Engineering Module (sMothershipMicro) is being built.
function KAS_BuildName(t)
    local h = KAS_ShipTypes[strlower(t)]
    if h == nil then return nil end
    if strsub(h, -6) == "_dummy" then h = strsub(h, 1, -7) end   -- a Kuun-Lan module: its subsystem
    return h
end
function K_4967b0(t)
    local h = KAS_BuildName(t)
    if h == nil then return 0 end
    if Player_HasQueuedBuild(0, h) ~= 0 then return 1 end
    return 0
end

-- The Engineering Module takes the ore canister's place (Cataclysm: building it ejects the canister, Fleet Command
-- "Ore transferred to aux storage bays. Jettisoning canister. Triggering canister destruct to keep it out of pirate
-- hands.", event 363, played by Mission02 itself; user: the canister jettison before the Engineering Module). Ours
-- is a subsystem: when the player queues the module while the Kuun-Lan carries the canister, the subsystem is
-- destroyed, its loose model (the NIS dummy, built in the Kuun-Lan's frame) put where it was, and blown up a few
-- seconds later.
-- The canister's flight is cataclysm.exe's module jettison (FUN_005af940, fitting an Armour / Weapons / Special /
-- Engineering module: FUN_00466b00; per frame FUN_005af800): a force along the Kuun-Lan's up axis x [0.4, 0.5] plus its
-- right axis x [-0.3, 0.3] and again x [-0.02, 0.02] (table 0x8c3608 row 0; the exe reads the right axis twice),
-- normalised, x [50000, 70000] (0x8c35fc), on the canister's mass 1000, its speed capped at 1000 (smothershiporecan-
-- armour.shp), pushed for 7 + 10 s (0x87929c, 0x8792a0), then an ordinary ship death, still moving; spinning about
-- an axis 0.05 rad a universe update (16 a second; 0x8c35f8). The jettison is when the module latches on to its slot
-- (FUN_00466b00 from the dock state machine, case 4), at the start of its build: Mission02 sees the build, letterboxes
-- and focuses on the canister 3 s later (its Default timer). The spin (the draw, FUN_00577xxx: glRotatef about +0x660
-- after the model's matrix) is about the canister's world up axis at the jettison (+0x98, HW1's column 1) taken in
-- the model's own frame: for a level Kuun-Lan (HW1's world up is z) that is the model's heading axis, end over end.
-- Distances at the models' scale (0.35).
KAS_JettisonCamera = 900       -- camera distance from it (the mission's kasfTutCameraFocusFar sets its own)
KAS_JettisonCentre = { 0, 102.6076, -45.4616 }   -- its centre in the Kuun-Lan's frame (the loose model's Root is the
                                                 -- Kuun-Lan's centre: build/ships/smt_kl_orecanarmour/origin.txt)
KAS_JettisonUp = { 0.4, 0.5 }
KAS_JettisonRight = { -0.3, 0.3 }
KAS_JettisonRight2 = { -0.02, 0.02 }
KAS_JettisonForce = { 50000, 70000 }
KAS_JettisonMass, KAS_JettisonMaxSpeed = 1000, 1000
KAS_JettisonPush = 17
KAS_JettisonSpin = 0.05 * 16
KAS_JettisonScale = 0.35
KAS_JettisonBlast, KAS_JettisonBlastScale = "dmg_cloud_main_explosion_combo", 7
KAS_JettisonDeath = 2          -- its death after the first blast: flying on, smaller blasts following it (seconds)
KAS_JettisonSmall, KAS_JettisonSmallScale = "dmg_cloud_explosion_large_nodebris", 3
-- the sounds: Cataclysm's canister explodes as ET_FrigateExplosion (smothershiporecanarmour.shp); our frigates' death
-- sounds (bst_fieldfrigate.events)
KAS_JettisonSound = "data:sound/sfx/etg/explosion/medium/etg_explode_medium_firey"
KAS_JettisonSmallSound = "data:sound/sfx/etg/explosion/small/etg_explode_small_firey"
KAS_JettisonHold = 1           -- the scene's focus kept on the blast this long before it ends (user, the original)
function KAS_JettisonStart()
    SobGroup_CreateIfNotExist("KAS_JettMS")
    KAS_KuunLan("KAS_JettMS", 0)
    if SobGroup_Count("KAS_JettMS") == 0 or SobGroup_HasSubsystem("KAS_JettMS", "smt_kl_orecanarmour") ~= 1 then return end
    KAS_Jettisoned = 1            -- once
    local pos, m = SobGroup_GetPosition("KAS_JettMS"), SobGroup_GetCoordSys("KAS_JettMS")
    SobGroup_SetHardPointHealth("KAS_JettMS", "Ore Canister", 0)   -- (the hardpoint's name, smt_ms_sp.ship)
    SobGroup_CreateIfNotExist("KAS_JettCan")
    SobGroup_Clear("KAS_JettCan")
    Volume_AddSphere("KAS_JettVol", pos, 1)
    SobGroup_SpawnNewShipInSobGroup(0, "smt_kl_orecanarmour_dummy", "KAS_JettCanShip", "KAS_JettCan", "KAS_JettVol")
    Volume_Delete("KAS_JettVol")
    SobGroup_SetPosition("KAS_JettCan", pos)
    SobGroup_SetTransform("KAS_JettCan", m)
    -- the direction from the Kuun-Lan's axes (the coordsys' rows: right 1-3, up 4-6, bow 7-9, as the arrival check
    -- reads the bow; world = local x M)
    local up, right = { m[4], m[5], m[6] }, { m[1], m[2], m[3] }
    local a = RandomRange(KAS_JettisonUp[1], KAS_JettisonUp[2])
    local r = RandomRange(KAS_JettisonRight[1], KAS_JettisonRight[2]) + RandomRange(KAS_JettisonRight2[1], KAS_JettisonRight2[2])
    local dir = { a * up[1] + r * right[1], a * up[2] + r * right[2], a * up[3] + r * right[3] }
    local l = sqrt(dir[1] * dir[1] + dir[2] * dir[2] + dir[3] * dir[3])
    dir = { dir[1] / l, dir[2] / l, dir[3] / l }
    local c, k = KAS_JettisonCentre, 1
    local centre = {}
    while k <= 3 do
        centre[k] = pos[k] + c[1] * m[k] + c[2] * m[k + 3] + c[3] * m[k + 6]
        k = k + 1
    end
    KAS_Jett = { m = m, centre = centre, dir = dir, start = Universe_GameTime(), last = Universe_GameTime(),
                 accel = RandomRange(KAS_JettisonForce[1], KAS_JettisonForce[2]) / KAS_JettisonMass * KAS_JettisonScale,
                 vmax = KAS_JettisonMaxSpeed * KAS_JettisonScale, v = 0, s = 0, g = "KAS_JettCan" }
    Rule_AddInterval("KAS_JettisonFly", 0.05)
    print("CKAS: ore canister jettisoned (its replacement's build started)")
end
-- the model placed so the canister's centre is at c, turned th about its own heading axis (the bow row kept, the
-- right and up rows turned in their plane)
function KAS_JettisonPlace(c, th, g)
    local m0, cs, sn = KAS_Jett.m, cos(th * 57.29578), sin(th * 57.29578)    -- (Lua 4 sin / cos take degrees)
    local m = {}
    local i = 1
    while i <= 3 do
        m[i] = m0[i] * cs + m0[i + 3] * sn
        m[i + 3] = m0[i + 3] * cs - m0[i] * sn
        m[i + 6] = m0[i + 6]
        i = i + 1
    end
    local k, o, lc = 1, {}, KAS_JettisonCentre
    while k <= 3 do
        o[k] = c[k] - (lc[1] * m[k] + lc[2] * m[k + 3] + lc[3] * m[k + 6])
        k = k + 1
    end
    SobGroup_SetPosition(g, o)
    SobGroup_SetTransform(g, m)
end
function KAS_JettisonBlastAt(c, fx, scale, n, snd)
    Volume_AddSphere("KAS_JettBlast" .. n, c, 1)
    FX_PlayEffect(fx, "KAS_JettBlast" .. n, scale)
    Sound_SFXPlay3D(snd, "KAS_JettBlast" .. n)
end
-- HW1's camera, its focus ship dying, stays where it is; HWRM's keeps following a ship that is still there. So at the
-- blast the focused canister is swapped for an unfocused copy that flies on, and the camera is left behind (user)
function KAS_JettisonSwap(c, th)
    SobGroup_CreateIfNotExist("KAS_JettCan2")
    SobGroup_Clear("KAS_JettCan2")
    Volume_AddSphere("KAS_JettSwapVol", c, 1)
    SobGroup_SpawnNewShipInSobGroup(0, "smt_kl_orecanarmour_dummy", "KAS_JettCan2Ship", "KAS_JettCan2", "KAS_JettSwapVol")
    Volume_Delete("KAS_JettSwapVol")
    KAS_JettisonPlace(c, th, "KAS_JettCan2")
    SobGroup_Despawn("KAS_JettCan")
    KAS_Jett.g = "KAS_JettCan2"
end
function KAS_JettisonFocusEnd()
    KAS_JettFocus = nil
    KAS_FocusCancel()
end
function KAS_JettisonFly()
    local j = KAS_Jett
    local now = Universe_GameTime()
    local t, dt = now - j.start, now - j.last
    j.last = now
    if j.blown == nil or now - j.blown < KAS_JettisonDeath then
        if j.blown == nil then
            j.v = j.v + j.accel * dt
            if j.v > j.vmax then j.v = j.vmax end
        end
        j.s = j.s + j.v * dt
        local c = { j.centre[1] + j.dir[1] * j.s, j.centre[2] + j.dir[2] * j.s, j.centre[3] + j.dir[3] * j.s }
        if SobGroup_Count(j.g) > 0 then KAS_JettisonPlace(c, KAS_JettisonSpin * t, j.g) end
        if j.blown == nil and t >= KAS_JettisonPush then
            -- the death: the big blast where it is, the canister flying on; a camera still on it stays on that spot
            -- (only while the mission's focus on it lasts: user, a refocus after the scene snapped the camera back)
            j.blown, j.blasts = now, 0
            KAS_JettisonBlastAt(c, KAS_JettisonBlast, KAS_JettisonBlastScale, 0, KAS_JettisonSound)
            if KAS_JettFocus then KAS_JettisonSwap(c, KAS_JettisonSpin * t) end
            print("CKAS: ore canister destructed, " .. floor(j.v / KAS_JettisonScale) .. " a second")
        elseif j.blown and now - j.blown >= (j.blasts + 1) * 0.5 then
            j.blasts = j.blasts + 1
            KAS_JettisonBlastAt(c, KAS_JettisonSmall, KAS_JettisonSmallScale, j.blasts, KAS_JettisonSmallSound)
        end
        return
    end
    Rule_Remove("KAS_JettisonFly")
    if SobGroup_Count(j.g) > 0 then SobGroup_Despawn(j.g) end
end
-- camera: 0x496930 sets the distance, 0x496950 focuses ships (the tutorial camera; Fleet Intel's briefing views)
-- (Mission02's canister scene focuses on the loose canister; KAS_JettFocus while that focus lasts)
KAS_CamDist = nil
function K_496930(d) KAS_CamDist = KAS_Dist(d) end
function K_496950(sel)
    if sel == KAS_OreCanSel and KAS_Jettisoned == nil then KAS_JettisonStart() end   -- (the watch missed the build)
    local g = sel
    if sel == KAS_OreCanSel and SobGroup_Count("KAS_JettCan") > 0 then g = "KAS_JettCan" end
    KAS_JettFocus = nil
    if g == "KAS_JettCan" then KAS_JettFocus = 1 end
    if SobGroup_Count(g) > 0 then
        Camera_FocusSobGroupWithBuffer(g, KAS_CamDist or KAS_JettisonCamera, 0, 0)
        -- the focused ships seen for 45 s, as Gearbox's KAS_FocusShipsFar / KAS_FocusShips (K_496870) make them: HW1's
        -- main view had no fog of war, so a scripted focus showed them (Mission01's hyperspace-signature patrol, by
        -- kasfTutCameraFocus; this far one skipped it: Mission02's disguised corvettes, user 2026-10-17)
        if g ~= "KAS_JettCan" then KAS_FocusShipsRemember(g, 0) end
    end
end
-- the jettison at the start of an Armour / Weapons / Special / Engineering module's build (FUN_00466b00's types)
KAS_JettisonModules = { "smt_kl_armour", "smt_kl_weapons", "smt_kl_special", "smt_kl_micro" }
function KAS_JettisonWatch()
    if KAS_Jettisoned then Rule_Remove("KAS_JettisonWatch") return end
    local i = 1
    while KAS_JettisonModules[i] do
        if Player_HasQueuedBuild(0, KAS_JettisonModules[i]) ~= 0 then
            KAS_JettisonStart()
            return
        end
        i = i + 1
    end
end
function K_496d40(tech) return Player_HasResearch(0, tech) end                                    -- kasfCanPlayerResearch
-- 0x496e00(player): the player's RUs (Mission02: under 500, Fleet Intel says to harvest)
function K_496e00(p) return Player_GetRU(p) end
-- 0x497420(n) / 0x498250(on): game UI modes not identified (Mission02's Fleet Intel briefings)
-- 0x497420(frames): the same code as kasfWideScreenIn (0x497580): letterbox in (Mission02's canister scene, 90)
function K_497420(frames) K_497580(frames) end
-- 0x498250(on): 1 locks the interface (FUN_00518e10(7)), 0 releases it (FUN_00518f00, as kasfWideScreenOut does)
function K_498250(on) KAS_Lockout(on) end
-- 0x497850(team): removes the ships from the game outright
function K_497850(sel) SobGroup_Despawn(sel) end
-- 0x497f10(index, type) / 0x497f70(index, n): per-player numbered ship-type lists for a UI menu ("%d. %s",
-- FUN_004eac30; index 2 = asteroids). Not ported.
function K_497f10(i, t) end
function K_497f70(i, n) end
-- 0x497fd0(ships, type, flag) / 0x498080(ships) / 0x498270(ships): Cataclysm's disguise state (+0x760): Mission02's
-- decoy poses as a Kushan support frigate until the ambush. Not ported yet.
-- kasfShipsDisguise(ships, type, scheme) / kasfShipsUndisguise(ships) (0x497fd0 / 0x498080, FUN_005b8d70: the
-- Mimic's routine, mode 1 a ship type / 2 "A<n>" an asteroid, drawn in the scheme's colours): the teams that do it are
-- the disguisable corvette (tools/make_disguise.py), its model showing the disguise (KAS_Disguises: its mad state).
-- Kept on the ships and set again every second (a team disguised then hyperspaced out came back undisguised)
dofilepath("data:scripts/scar/cataclysmdisguise_gen.lua")
-- While disguised the team is the allied player's (KAS_AllyPlayer): it shows as a friend, as the ship it poses as
-- (user, 2026-10-17: Mission02's disguised corvettes showed as hostile), and back to its own player on dropping the
-- disguise; the pirates' "Enemy" leaves it out (KAS_FillHumanSide). Dropping it plays our Mimic's transformation
-- (MimicOut_<type>, tools/make_mimicfx.py SCRIPT_DISGUISES) with the model switched at once, as the Mimic's Unmimic.
KAS_Disguised, KAS_DisguiseInfo = {}, {}
function K_497fd0(sel, t, f)
    local state = KAS_Disguises and KAS_Disguises[strlower(t) .. "@" .. (f or 0)]
    if state == nil then KAS_NoOp("497fd0", "disguise as " .. t .. " (" .. (f or 0) .. "): not on the model") return end
    KAS_Disguised[sel] = state
    if KAS_DisguiseInfo[sel] == nil and SobGroup_Count(sel) > 0 then
        KAS_DisguiseInfo[sel] = { type = strlower(t), owner = SobGroup_GetPlayerOwner(sel) }
        local ally = KAS_AllyPlayer()
        if ally ~= KAS_DisguiseInfo[sel].owner then
            SobGroup_SetSwitchOwnerFlag(sel, 0)
            SobGroup_SwitchOwner(sel, ally)
        end
    end
    SobGroup_SetMadState(sel, state)
    KAS_DisguiseVisible(sel, 1)
    print("CKAS: " .. sel .. " disguised as " .. t .. " (" .. state .. ")")
    if Rule_Exists("KAS_DisguiseTick") == 0 then Rule_AddInterval("KAS_DisguiseTick", 1) end
end
function K_498080(sel)
    KAS_Disguised[sel] = nil
    local info = KAS_DisguiseInfo[sel]
    KAS_DisguiseInfo[sel] = nil
    if info and SobGroup_Count(sel) > 0 then
        FX_StartEvent(sel, "MimicOut_" .. info.type)
        if SobGroup_GetPlayerOwner(sel) ~= info.owner then
            SobGroup_SetSwitchOwnerFlag(sel, 0)
            SobGroup_SwitchOwner(sel, info.owner)
        end
    end
    SobGroup_SetMadState(sel, "NIS00")
    KAS_DisguiseVisible(sel, 0)
    print("CKAS: " .. sel .. " undisguised")
end
-- a disguised ship transmits its position as the ship it poses as: the human sees it through the fog of war (user,
-- 2026-10-17: Mission02's disguised corvettes, watched coming in), Gearbox's SobGroup_SetInherentVisibility
-- (KAS_FocusShipsRemember)
function KAS_DisguiseVisible(sel, on)
    if SobGroup_Count(sel) == 0 then return end
    if on == 1 then SobGroup_SetInherentVisibility(sel, 0, VisFull) else SobGroup_SetInherentVisibility(sel, 0, VisNone) end
end
function KAS_DisguiseTick()
    for sel, state in KAS_Disguised do
        if SobGroup_Count(sel) > 0 then
            SobGroup_SetMadState(sel, state)
            KAS_DisguiseVisible(sel, 1)   -- (again: a team disguised then hyperspaced out came back as it was)
        end
    end
end
-- 0x498270(ships): the ships die (FUN_0044a150: each gets a death time, now + a random fraction of a second, and the
-- ship update destroys it then, FUN_0054a6xx 0x2fc; a disguised one is unmimicked first). Mission02: once the pod is
-- taken, the raiders not yet discovered and the salvage corvettes go, so "Pirates" can empty and the mission end
-- (user 2026-10-18: the capture never ended it, the no-op left them alive)
KAS_Doomed = {}
KAS_DoomN = 0
function K_498270(sel)
    local now = Universe_GameTime()
    local n = SobGroup_Count(sel)
    print("CKAS: " .. sel .. " dies (" .. n .. " ships)")
    for i = 0, n - 1 do
        KAS_DoomN = KAS_DoomN + 1
        local g = "KAS_Doom" .. KAS_DoomN
        SobGroup_CreateIfNotExist(g)
        SobGroup_Clear(g)
        SobGroup_FillShipsByIndexRange(g, sel, i, 1)
        KAS_Doomed[g] = now + random()
    end
    if n > 0 and Rule_Exists("KAS_DoomTick") == 0 then Rule_AddInterval("KAS_DoomTick", 0.1) end
end
function KAS_DoomTick()
    local now, due, left = Universe_GameTime(), {}, 0
    for g, t in KAS_Doomed do
        if now >= t then tinsert(due, g) else left = left + 1 end
    end
    for i = 1, getn(due) do
        local g = due[i]
        if SobGroup_Count(g) > 0 then
            SobGroup_SetInvulnerability(g, 0)
            SobGroup_SetHealth(g, 0)
        end
        KAS_Doomed[g] = nil
    end
    if left == 0 then Rule_Remove("KAS_DoomTick") end
end
-- 0x498cb0(type, player): how many of that type the player has
-- Salvage objects (tools/mission2level.py SALVAGE_TYPES / KAS_Salvage in the mission's _paths.lua: Mission02's
-- message pod, a Worker tows it home with SalvageCommand): the level places them unnamed, so each one's team is
-- filled from a volume round where it starts (KAS_SalvageFind); "the player owns one" (K_498cb0) means a delivery
-- (Gearbox's salvage counter, Stats_GatheredRUSalvage, rose: each is worth 1 RU, install_base.py make_salvage)
KAS_SalvageTypes = {}   -- (none: Mission02's pod is a ship, captured as in HW1)
function KAS_SalvageFind()
    if KAS_Salvage == nil then return end
    KAS_SalvageBase = Stats_GatheredRUSalvage(0)
    for i = 1, getn(KAS_Salvage) do
        local s = KAS_Salvage[i]
        local v = "KAS_SalvageVol" .. i
        Volume_AddSphere(v, s.pos, 300)
        SobGroup_CreateIfNotExist(s.team)
        Player_FillSobGroupInVolume(s.team, -1, v)
        print("CKAS: salvage " .. s.type .. " for team " .. s.team .. ": " .. SobGroup_Count(s.team) .. " found")
        Volume_Delete(v)
    end
end
-- a mission team's name (Gearbox's KASTeams), not a ship type
function KAS_IsTeam(t)
    local i = 0
    while KASNumberTeams and i < KASNumberTeams do
        if KASTeams[i] == t then return 1 end
        i = i + 1
    end
    return nil
end
function K_498cb0(t, p)
    -- (cataclysm.exe: FUN_004d6e30 the type's index, -1 for a name that is no ship type, then FUN_00540030 the
    -- player's count of that type in its stats table, every type summed for -1: Mission02 passes its pod's TEAM,
    -- "dMessagePod", so it asks how many ships the player has taken, non-zero once the pod is captured. As a type
    -- it was always 0: capturing the pod never ended the mission, user 2026-10-18.) A team: its ships the player owns
    -- (the pod's group keeps it through the capture: its switch-owner flag was cleared when it changed sides)
    if KAS_IsTeam(t) then
        SobGroup_CreateIfNotExist("KAS_CountTmp")
        SobGroup_Clear("KAS_CountTmp")
        SobGroup_FilterInclude("KAS_CountTmp", t, "PlayerOwner", "" .. p)
        local n = SobGroup_Count("KAS_CountTmp")
        KAS_TeamTaken = KAS_TeamTaken or {}
        if KAS_TeamTaken[t] ~= n then
            KAS_TeamTaken[t] = n
            print("CKAS: team " .. t .. ": " .. n .. " of " .. SobGroup_Count(t) .. " owned by player " .. p)
        end
        return n
    end
    if KAS_SalvageTypes[strlower(KAS_HWRMType(t))] then
        if p ~= 0 or KAS_SalvageBase == nil then return 0 end
        return Stats_GatheredRUSalvage(0) - KAS_SalvageBase
    end
    SobGroup_CreateIfNotExist("KAS_CountTmp")
    SobGroup_Clear("KAS_CountTmp")
    Player_FillShipsByType("KAS_CountTmp", p, KAS_HWRMType(t))
    return SobGroup_Count("KAS_CountTmp")
end
-- 0x499330(targets): the team kamikazes them (Gearbox's KAS_Kamikaze)
function K_499330(targets) if SobGroup_Count(KAS_Team) > 0 then SobGroup_Kamikaze(KAS_Team, targets) end end
-- 0x4995e0(volume, out): derelicts in the volume (none converted yet: slipgates)
function K_4995e0(vol, out)
    SobGroup_Clear(out)
    KAS_NoOp("4995e0", "derelicts in volume")
    return 0
end
-- 0x4998c0: the team has no AI move left (FUN_00417260)
function K_4998c0()
    if SobGroup_Count(KAS_Team) == 0 then return 1 end
    if KAS_Intercepts and KAS_Intercepts[KAS_Team] then return 0 end   -- still intercepting (not yet ordered on)
    if SobGroup_GetCurrentOrder(KAS_Team) == COMMAND_Idle then return 1 end
    return 0
end
-- 0x49a2d0(ships, on): SOF_Disabled (Mission02's crippled destroyer): no move, no fire
-- 0x49a2d0(ships, on): Cataclysm's disabled state (FUN_005b3bd0 / 005b3c80, SOF_Disabled, as EMP): no control and
-- no guns, and (FUN_00545a80) a random spin added once, yaw / pitch / roll in tweak.script YAW/PITCH/ROLLCRAZYLO..HI
-- (+-2, +-1, +-5) x the universe update (1/16 s), radians a second about its own axes, kept while it drifts (Mission02's
-- destroyer listing slowly, user); off again: control back, the spin stopped
KAS_CrazyYaw, KAS_CrazyPitch, KAS_CrazyRoll, KAS_UnivUpdate = 2, 1, 5, 1 / 16
-- (halved: HWRM's latching repair can't get a Worker onto a ship spinning at Cataclysm's rate, user)
KAS_CrazyScale = 0.5
-- and held still while a ship with a repair order is this near (HWRM's latching repair can't get a Worker onto a ship
-- that turns at all, even at half Cataclysm's rate: user; Cataclysm's beams repaired it spinning)
KAS_DisabledRepairNear = 2000
function KAS_BeingRepaired(sel)
    SobGroup_CreateIfNotExist("KAS_RepairNear")
    SobGroup_CreateIfNotExist("KAS_RepairOne")
    for pl = 0, Universe_PlayerCount() - 1 do
        SobGroup_Clear("KAS_RepairNear")
        SobGroup_FillProximitySobGroup("KAS_RepairNear", "Player_Ships" .. pl, sel, KAS_DisabledRepairNear)
        for i = 0, SobGroup_Count("KAS_RepairNear") - 1 do
            SobGroup_Clear("KAS_RepairOne")
            SobGroup_FillShipsByIndexRange("KAS_RepairOne", "KAS_RepairNear", i, 1)
            if SobGroup_Count("KAS_RepairOne") > 0 and SobGroup_GetCurrentOrder("KAS_RepairOne") == (COMMAND_Repair or 15) then
                return 1
            end
        end
    end
    return nil
end
KAS_Disabled = {}
function K_49a2d0(sel, on)
    local a = 1 - on
    SobGroup_AbilityActivate(sel, AB_Move, a)
    SobGroup_AbilityActivate(sel, AB_Attack, a)
    SobGroup_AbilityActivate(sel, AB_Hyperspace, a)
    if on == 1 then
        SobGroup_SetROE(sel, PassiveROE)
        local k = KAS_UnivUpdate * KAS_CrazyScale
        KAS_Disabled[sel] = { RandomRange(-KAS_CrazyYaw, KAS_CrazyYaw) * k, RandomRange(-KAS_CrazyPitch, KAS_CrazyPitch) * k,
                              RandomRange(-KAS_CrazyRoll, KAS_CrazyRoll) * k }
        if Rule_Exists("KAS_DisabledTick") == 0 then Rule_AddInterval("KAS_DisabledTick", 0.05) end
    else
        SobGroup_SetROE(sel, DefensiveROE)
        KAS_Disabled[sel] = nil
        if KAS_InvulnerableHeld[sel] then   -- enabled before any repair held it: the mission's switch-off now
            KAS_InvulnerableHeld[sel] = nil
            KAS_Invulnerable[sel] = nil
            SobGroup_SetInvulnerability(sel, 0)
        end
    end
    print("CKAS: " .. sel .. ((on == 1 and " disabled") or " enabled"))
end
-- v turned by angle a (radians) about the unit axis k (Lua 4 sin / cos: degrees)
function KAS_Turn(v, k, a)
    local c, s = cos(a * 57.29578), sin(a * 57.29578)
    local d = k[1] * v[1] + k[2] * v[2] + k[3] * v[3]
    local x = { k[2] * v[3] - k[3] * v[2], k[3] * v[1] - k[1] * v[3], k[1] * v[2] - k[2] * v[1] }
    return { v[1] * c + x[1] * s + k[1] * d * (1 - c), v[2] * c + x[2] * s + k[2] * d * (1 - c),
             v[3] * c + x[3] * s + k[3] * d * (1 - c) }
end
function KAS_Unit(v)
    local l = sqrt(v[1] * v[1] + v[2] * v[2] + v[3] * v[3])
    return { v[1] / l, v[2] / l, v[3] / l }
end
function KAS_DisabledTick()
    local now, left = Universe_GameTime(), 0
    for sel, w in KAS_Disabled do
        left = left + 1
        local dt = now - (w.last or now)
        w.last = now
        if now >= (w.check or 0) and SobGroup_Count(sel) > 0 then
            w.check = now + 0.5
            local held = KAS_BeingRepaired(sel)
            if held ~= w.held then print("CKAS: " .. sel .. ((held and " held still for repairs") or " drifting again")) end
            if held and KAS_InvulnerableHeld[sel] then   -- the switch-off the mission asked for earlier (K_4984c0)
                KAS_InvulnerableHeld[sel] = nil
                KAS_Invulnerable[sel] = nil
                SobGroup_SetInvulnerability(sel, 0)
                print("CKAS: " .. sel .. " vulnerable now (a repair reached it)")
            end
            w.held = held
        end
        if dt > 0 and SobGroup_Count(sel) > 0 and w.held == nil then
            local m = SobGroup_GetCoordSys(sel)          -- rows: right, up, bow
            local r, u, f = { m[1], m[2], m[3] }, { m[4], m[5], m[6] }, { m[7], m[8], m[9] }
            -- yaw about up, pitch about right, roll about the bow (HW1 rotspeed x / y / z: up, right, heading)
            r, f = KAS_Turn(r, u, w[1] * dt), KAS_Turn(f, u, w[1] * dt)
            u, f = KAS_Turn(u, r, w[2] * dt), KAS_Turn(f, r, w[2] * dt)
            r, u = KAS_Turn(r, f, w[3] * dt), KAS_Turn(u, f, w[3] * dt)
            f = KAS_Unit(f)
            r = KAS_Unit({ u[2] * f[3] - u[3] * f[2], u[3] * f[1] - u[1] * f[3], u[1] * f[2] - u[2] * f[1] })
            u = { f[2] * r[3] - f[3] * r[2], f[3] * r[1] - f[1] * r[3], f[1] * r[2] - f[2] * r[1] }
            SobGroup_SetTransform(sel, { r[1], r[2], r[3], u[1], u[2], u[3], f[1], f[2], f[3] })
        end
    end
    if left == 0 then Rule_Remove("KAS_DisabledTick") end
end
-- 0x49a460(ships): remembers the first ship in a UI global (DAT_00a57798)
function K_49a460(sel) end
-- 0x49a790(ships, out): the ships those ships guard (their protect orders, K_492960)
function K_49a790(sel, out)
    SobGroup_Clear(out)
    SobGroup_CreateIfNotExist("KAS_GuardTmp")
    for team, g in KAS_Guards do
        if KAS_Intersect("KAS_GuardTmp", team, sel) > 0 then SobGroup_SobGroupAdd(out, g.sel) end
    end
    return SobGroup_Count(out)
end
-- 0x49ad80(out, ships): the ships docked inside them
function K_49ad80(out, sel)
    SobGroup_Clear(out)
    if SobGroup_Count(sel) > 0 then SobGroup_GetSobGroupDockedWithGroup(sel, out) end
    return SobGroup_Count(out)
end

-- ================================================================== firing while moving
-- A ship given a plain move (SobGroup_MoveToPoint, FollowPath alike) aims its turrets but fires nothing: no shot,
-- turrets lagging and snapping (user, range tests 2026-10-13: any moving HWRM capital ship, Mission01's fleeing
-- heavy cruiser). HWRM keeps firing only when the move is given while an attack is the ship's current command (HWRM
-- FUN_006808df: the move goes onto the attack, "firing while moving"; the UI does it for the player). HW1 ships fire on
-- whatever is in range while they travel, so a computer team on a scripted route (kasfPatrolPath, kasfMoveTo) with
-- enemies within KAS_MoveFireRange gets, each second in turn, an attack on them and its move again (confirmed in the
-- range: turrets and flight correct). Strike craft are left out (fixed guns; an attack starts a dogfight).
KAS_Moves = {}
KAS_MoveFireRange = 6000
KAS_MoveFireNext = {}
function KAS_MoveFireTeam(team, again)
    if SobGroup_Count(team) == 0 or KAS_Owner(team) == 0 then return end
    SobGroup_CreateIfNotExist("KAS_MoveFireSc")
    SobGroup_Clear("KAS_MoveFireSc")
    SobGroup_FilterExclude("KAS_MoveFireSc", team, "DisplayFamily", "Fighter")
    if SobGroup_Count("KAS_MoveFireSc") == 0 then return end
    SobGroup_CreateIfNotExist("KAS_MoveFireFoes")
    if KAS_FillEnemiesNear("KAS_MoveFireFoes", team, KAS_MoveFireRange) == 0 then
        KAS_MoveFireNext[team] = nil
        return
    end
    if KAS_MoveFireNext[team] ~= "move" then
        SobGroup_Attack(KAS_Owner(team), team, "KAS_MoveFireFoes")
        KAS_MoveFireNext[team] = "move"
    else
        again(team)
        KAS_MoveFireNext[team] = "attack"
    end
end
function KAS_MoveFireAgainPatrol(team) KAS_PatrolGo(team) end
function KAS_MoveFireAgainMove(team) SobGroup_MoveToPoint(KAS_Owner(team), team, KAS_Moves[team]) end
function KAS_MoveFireTick()
    for team, p in KAS_Patrols do KAS_MoveFireTeam(team, KAS_MoveFireAgainPatrol) end
    local done = {}
    for team, w in KAS_Moves do
        local a = SobGroup_GetPosition(team)
        if SobGroup_Count(team) == 0 or sqrt((a[1] - w[1]) * (a[1] - w[1]) + (a[2] - w[2]) * (a[2] - w[2])
                                             + (a[3] - w[3]) * (a[3] - w[3])) < KAS_PatrolReach then
            done[getn(done) + 1] = team
        else
            KAS_MoveFireTeam(team, KAS_MoveFireAgainMove)
        end
    end
    local i = 1
    while i <= getn(done) do
        KAS_Moves[done[i]] = nil
        i = i + 1
    end
end
