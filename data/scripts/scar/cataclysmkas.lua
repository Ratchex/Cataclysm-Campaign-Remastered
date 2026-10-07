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

KAS_Timers = {}
function KAS_Now() return Universe_GameTime() end
function K_491ec0(h) KAS_Timers[KAS_Key(h)] = { dur = 0, start = 0, running = 0, left = 0 } end    -- kasfTimerCreate
function K_491f00(h, d)                                                                             -- kasfTimerSet
    local k = KAS_Key(h)
    local t = KAS_Timers[k] or { dur = 0, start = 0, running = 0, left = 0 }
    t.dur = d
    t.left = d
    KAS_Timers[k] = t
end
function K_491f50(h)                                                                                -- kasfTimerStart
    local t = KAS_Timers[KAS_Key(h)]
    if t then t.start = KAS_Now() - (t.dur - t.left); t.running = 1 end
end
function K_491f90(h, d)                                                                             -- kasfTimerCreateSetStart
    KAS_Timers[KAS_Key(h)] = { dur = d, start = KAS_Now(), running = 1, left = d }
end
function KAS_TimerLeft(t)
    if t.running == 1 then
        local left = t.dur - (KAS_Now() - t.start)
        if left < 0 then left = 0 end
        return left
    end
    return t.left
end
function K_491fe0(h)                                                                                -- kasfTimerStop
    local t = KAS_Timers[KAS_Key(h)]
    if t then t.left = KAS_TimerLeft(t); t.running = 0 end
end
function K_492020(h)                                                                                -- kasfTimerRemaining
    local t = KAS_Timers[KAS_Key(h)]
    if t then return floor(KAS_TimerLeft(t)) end
    return 0
end
function K_492060(h)                                                                                -- kasfTimerExpired
    local t = KAS_Timers[KAS_Key(h)]
    if t and t.running == 1 and KAS_TimerLeft(t) <= 0 then return 1 end
    return 0
end
function K_4920a0(h)                                                                                -- kasfTimerExpiredDestroy
    local k = KAS_Key(h)
    if K_492060(h) == 1 then KAS_Timers[k] = nil; return 1 end
    return 0
end
function K_4920e0(h) KAS_Timers[KAS_Key(h)] = nil end                                               -- kasfTimerDestroy

-- ------------------------------------------------------------------ team messages (exe FUN_00417e10/60/c0)
-- Per-team queue of (message hash, sender). Reading message i removes it by swapping in the last one.
KAS_Msgs = {}

function KAS_MsgSendRaw(from, to, msg)
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
    SobGroup_FillSubstract("KAS_Temp", a, b)
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

function K_494f60(label)                                                                            -- kasfObjectiveDestroy
    if KAS_Objectives[label] then
        Objective_SetState(KAS_Objectives[label], OS_Off)
        KAS_Objectives[label] = nil
    end
end
