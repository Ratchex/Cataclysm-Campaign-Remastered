-- Cataclysm ship rules on every ship (custom code, hooked by tools/make_shipcode.py): pilot experience and the
-- Acolyte -> ACV link, from cataclysm.exe (Cataclysm-decomp, NOTES.md "Experience" / "Linking").
--
-- Experience (FUN_005147d0): each ship counts kills per class of victim; score = sum(kills x CatExpWeight[class]);
-- rank = how many of the killer's class thresholds (CatExpThresholds) the score exceeds (strictly), 0-4.
-- Rank multiplies weapon damage (FUN_005148f0) and speed (FUN_00514940) by 1.0/1.1/1.2/1.3/1.4; speed also drops
-- with damage, for every ship (-0.1 below 75% health, -0.2 below 50%, -0.4 below 25%, -0.6 below 10%).
-- Cataclysm credits the ship whose shot killed; HWRM does not say, so the kill goes to one of the ships that were
-- attacking the victim (preferring the human player's), at random.
-- Link (FUN_0044d3b0 / FUN_00467b80): two Acolytes fly together and become an ACV with health fraction = the mean
-- of theirs and their kills summed; Unlink (FUN_00468650) gives each Acolyte its own kills plus half of what the
-- ACV earned.

if not CatShips then
    CatShips = {}          -- shipID -> record
    CatPending = {}        -- ships about to be spawned by a link/unlink: { group, kills } for their Create
    CatLinkQueue = {}      -- Acolytes waiting for a link partner
    CatSerial = 0
end

-- Lua 4 table constructors can't mix [0] = with list items: tables indexed by class/rank from 0
function CatFrom0(t)
    local r = {}
    for i = 1, getn(t) do r[i - 1] = t[i] end
    return r
end

-- Ship classes (HW1 ShipClass order, Cataclysm's 12)
CAT_MOTHERSHIP, CAT_HEAVYCRUISER, CAT_CARRIER, CAT_DESTROYER, CAT_FRIGATE, CAT_CORVETTE, CAT_FIGHTER = 0, 1, 2, 3, 4, 5, 6
CAT_RESOURCE, CAT_NONCOMBAT, CAT_MONSTER, CAT_COMPONENT, CAT_MICRO = 7, 8, 9, 10, 11

-- 0x72bbb4: points per kill, by the victim's class
CatExpWeight = CatFrom0({ 20, 8, 10, 9, 5, 3, 1, 1, 1, 1, 1, 1 })
-- 0x72bbe4: score the killer must exceed for ranks 1-4, by the killer's class
CatExpThresholds = CatFrom0({
    { 10, 30, 60, 100 }, { 10, 30, 60, 100 }, { 10, 30, 60, 100 }, { 5, 10, 20, 40 }, { 3, 6, 12, 16 },
    { 2, 4, 6, 8 }, { 1, 2, 3, 4 }, { 10, 30, 60, 100 }, { 10, 30, 60, 100 }, { 2, 4, 6, 8 },
    { 10, 30, 60, 100 }, { 2, 4, 6, 8 },
})
-- 0x72bb78 / 0x72bb8c: damage and speed multipliers by rank
CatRankMult = CatFrom0({ 1.0, 1.1, 1.2, 1.3, 1.4 })
-- strExperienceLevel0-4 (english.script); strShipLevelUpNotify
CatRankName = CatFrom0({ "Flight Sergeant", "Lieutenant", "Flight Leader", "Squadron Leader", "Wing Commander" })
CAT_LEVELUP = "has gained a Level:"

CAT_TICK = 0.5            -- seconds between rule updates per ship
CAT_SHOW_STARS = 0        -- see CatShip_Update
CAT_STAR_SCALE = CatFrom0({ 12, 8, 8, 6, 4, 2, 1, 1, 1, 1, 1, 1 })   -- star effect size by class (ship size)

-- Link: Cataclysm's sacolyte.shp linkDistance 50, at our map scale (x 0.35, tools/mission2level.py SCALE)
CAT_LINK_DIST = 50 * 0.35
CAT_LINK_TIMEOUT = 30     -- give up if the pair has not met
CAT_LINK_WAIT = 1.5       -- an Acolyte with no partner after this long gives up ("No Ships To Link With")

-- a ship's own custom code, chained under ours (tools/make_shipcode.py), keeps its own update interval
if not CatChainNext then CatChainNext = {} end
function CatChainTick(g, p, id, fn, interval)
    local now = Universe_GameTime()
    if (CatChainNext[id] or 0) <= now then
        CatChainNext[id] = now + interval
        if fn then fn(g, p, id) end   -- nil if their script failed to load
    end
end

-- Weapon upgrades: upgrade ability -> the engine ability that lets that ship's "Special Attack" weapons fire in
-- normal attacks (granted to the type by research at mission start: tools/make_race.py RUNTIME_RESEARCH), switched
-- on per ship once it has the upgrade. Cataclysm's Acolyte gets its two missile launchers (sacolyte.shp GUN2/GUN3,
-- StartUpgradeLevel WEAPON_MISSILE) with ORDINANCE (tools/install_cr.py patch_acolyte). (Tried and dropped: weapon
-- subsystems. Added by script they need a ship that can build, so every Acolyte had a build menu tab; innate ones
-- held at 0 health still fired.)
CatUpgradeWeapons = {
    smt_acolyte = { ORDINANCE = "AB_UseSpecialWeaponsInNormalAttack" },
}

-- every tick (the engine may reset it, e.g. on docking)
function CatUpgradeWeapons_Tick(rec, id)
    local w = CatUpgradeWeapons[rec.t]
    if not w then return end
    for ability, ab in w do
        local on = 0
        if rec.up[ability] then on = 1 end
        if getglobal(ab) then SobGroup_AbilityActivate(rec.g, getglobal(ab), on) end
        if on == 1 and not rec.weaponsOn[ability] then
            rec.weaponsOn[ability] = 1
            print("CATACLYSM upgrade: " .. ability .. " weapons on for ship " .. id)
        end
    end
end

function CatShip_Create(g, p, id, t)
    local kills = {}
    for i = 0, 11 do kills[i] = 0 end
    local rec = { g = g, p = p, t = t, cls = CatClass[t] or CAT_FIGHTER, kills = kills, rank = 0, spd = 1, dmg = 1,
                  next = 0, att = "cat_att_" .. id }
    CatShips[id] = rec
    -- its button abilities (tools/make_abilities.py): the mission script fills cat_cmd_<name> on a press
    rec.buttons = {}
    for i = 1, getn(CatAbilities) do
        local a = CatAbilities[i]
        if a.native == 0 and strfind(", " .. a.types .. ",", ", " .. t .. ",", 1, 1) then
            tinsert(rec.buttons, { name = a.name, grp = "cat_cmd_" .. a.name })
            SobGroup_CreateIfNotExist("cat_cmd_" .. a.name)
        end
    end
    SobGroup_CreateIfNotExist(rec.att)
    SobGroup_Clear(rec.att)
    SobGroup_CreateIfNotExist("cat_kas_upgrade")
    -- new ships come with the player's upgrades (Cataclysm: only ships already in service need upgrading)
    rec.up, rec.armour = {}, 0
    CatUpgrade_Apply(rec)
    -- weapon upgrades (CatUpgradeWeapons): switched on and off by CatUpgradeWeapons_Tick
    rec.weaponsOn = {}
    -- a ship spawned by a link/unlink takes over its pilots' kills
    for i = 1, getn(CatPending) do
        local pend = CatPending[i]
        if SobGroup_GroupInGroup(g, pend.group) == 1 then
            for c = 0, 11 do kills[c] = pend.kills[c] end
            rec.parts = pend.parts
            tremove(CatPending, i)
            CatShip_UpdateRank(rec, 0)
            break
        end
    end
end

function CatShip_Update(g, p, id)
    local rec = CatShips[id]
    if not rec then return end
    local now = Universe_GameTime()
    if now < rec.next then return end
    rec.next = now + CAT_TICK
    if SobGroup_Empty(g) == 1 then return end
    rec.p = SobGroup_OwnedBy(g)
    -- who is shooting at us, for the kill credit when we die
    SobGroup_Clear(rec.att)
    SobGroup_GetAttackers(g, rec.att)
    CatShip_ApplyMultipliers(rec)
    -- Rank stars: off. FX_PlayEffect leaves the effect where the ship was (it doesn't follow the ship), and HWRM's
    -- health bar overlay (ui/ati/ati.lua) only draws engine values, so no per-ship star beside the stance icon.
    if CAT_SHOW_STARS == 1 and rec.rank > 0 and SobGroup_Selected(g) == 1 then
        FX_PlayEffect("cat_rank" .. rec.rank, g, CAT_STAR_SCALE[rec.cls] or 1)
    end
    -- button abilities: act on first finding ourselves in the press group, if still selected (the press group is
    -- the selection the mission script read; checking our own selection too keeps unselected ships out)
    for i = 1, getn(rec.buttons) do
        local b = rec.buttons[i]
        if SobGroup_GroupInGroup(g, b.grp) == 1 then
            if not b.pressed then
                b.pressed = 1
                if SobGroup_Selected(g) == 1 then
                    CatAbility_Run(b.name, g, p, id)
                    if rec.gone then return end
                end
            end
        else
            b.pressed = nil
        end
    end
    CatUpgradeWeapons_Tick(rec, id)
    if rec.link then CatLink_Tick(rec, id, now) end
    CatUpgrade_Instant(rec, id)
    if rec.upg then CatUpgrade_Tick(rec, id, now) end
end

function CatShip_Destroy(g, p, id)
    local rec = CatShips[id]
    if not rec then return end
    CatShips[id] = nil
    if rec.gone then return end           -- linked or unlinked away, not killed
    if rec.link then CatLink_Cancel(rec, id) end
    CatShip_CreditKill(rec)
end

-- Kill credit: one ship among the victim's last attackers, the human player's first
function CatShip_CreditKill(victim)
    if SobGroup_Empty(victim.att) == 1 then return end
    local human, other = {}, {}
    for id, rec in CatShips do
        if rec.p ~= victim.p and SobGroup_Empty(rec.g) == 0 and SobGroup_GroupInGroup(rec.g, victim.att) == 1 then
            if rec.p == 0 then tinsert(human, rec) else tinsert(other, rec) end
        end
    end
    local pool = human
    if getn(pool) == 0 then pool = other end
    if getn(pool) == 0 then return end
    local killer = pool[random(1, getn(pool))]
    killer.kills[victim.cls] = killer.kills[victim.cls] + 1
    CatShip_UpdateRank(killer, 1)
end

function CatShip_Score(rec)
    local s = 0
    for c = 0, 11 do s = s + rec.kills[c] * CatExpWeight[c] end
    return s
end

function CatShip_UpdateRank(rec, announce)
    if rec.rank == 4 then return end
    local s, th, rank = CatShip_Score(rec), CatExpThresholds[rec.cls] or CatExpThresholds[CAT_FIGHTER], 0
    for i = 1, 4 do
        if th[i] < s then rank = i end
    end
    if rank > rec.rank and announce == 1 and rec.p == 0 then
        local text = (CatName[rec.t] or rec.t) .. " " .. CAT_LEVELUP .. " " .. CatRankName[rank]
        print("CATACLYSM experience: " .. text .. " (score " .. s .. ")")
        if Subtitle_Message then Subtitle_Message(text, 4) end
    end
    rec.rank = rank
    CatShip_ApplyMultipliers(rec)
end

-- FUN_005148f0 (damage) and FUN_00514940 (speed, less when damaged)
function CatShip_ApplyMultipliers(rec)
    if SobGroup_Empty(rec.g) == 1 then return end
    local mult = CatRankMult[rec.rank]
    if rec.dmg ~= mult then
        SobGroup_SetDamageMultiplier(rec.g, mult)
        rec.dmg = mult
    end
    local h, spd = SobGroup_HealthPercentage(rec.g), mult
    -- Advanced Drive upgrades (ability bits 0-2): +0.15 (0x72af78)
    if rec.up.ADRIVE_FIGHTER or rec.up.ADRIVE_FRIGATE or rec.up.ADRIVE_DESTROYER then spd = spd + CAT_ADRIVE_SPEED end
    if h < 0.1 then spd = spd - 0.6
    elseif h < 0.25 then spd = spd - 0.4
    elseif h < 0.5 then spd = spd - 0.2
    elseif h < 0.75 then spd = spd - 0.1 end
    if rec.spd ~= spd then
        SobGroup_SetMaxSpeedMultiplier(rec.g, spd)
        rec.spd = spd
    end
end

-- ---------------------------------------------------------------------------------------------------------------
-- Abilities: one custom command each (tools/make_abilities.py; the engine sends it to the selected ships that have
-- it). An ability that is an upgrade (Link, Unlink, EMP, ...) needs this ship to have it: Cataclysm's ships in
-- service get a new ability only by upgrading (the tutorial: "Upgrade Acolytes", then "Link the upgraded
-- Acolytes"); then its handler.
function CatAbility_Run(name, g, p, id)
    local rec = CatShips[id]
    for i = 1, getn(CatAbilities) do
        local a = CatAbilities[i]
        if a.name == name then
            if a.upgrade ~= "" and not (rec and rec.up[a.upgrade]) then
                print("CATACLYSM ability " .. name .. ": ship " .. id .. " lacks the " .. a.upgrade .. " upgrade")
                return
            end
            getglobal(a.handler)(g, p, id)
            return
        end
    end
end

-- ---------------------------------------------------------------------------------------------------------------
-- Upgrades (tools/make_upgrades.py, from cataclysm.exe): what a ship can be upgraded with now
CAT_ADRIVE_SPEED = 0.15
CAT_UPGRADE_DOCK_GRACE = 2    -- seconds before a ship sent to dock counts as given other orders (order lag)

function CatUpgrade_PlayerArmour(p)
    if Player_HasResearch(p, CatArmourTech[2]) == 1 then return 2 end
    if Player_HasResearch(p, CatArmourTech[1]) == 1 then return 1 end
    return 0
end

-- abilities the ship lacks that its player has researched, and the armour level it can reach
-- DEVELOPMENT ONLY: upgrades the human player counts as researched from that game time (seconds), for testing later
-- missions' mechanics in an early one (keep empty in commits that aren't a test)
CatDevUpgrades = {}   -- e.g. { ORDINANCE = 600 } (game time includes the opening cutscene)

function CatUpgrade_Researched(p, name)
    if p == 0 and CatDevUpgrades[name] and Universe_GameTime() >= CatDevUpgrades[name] then return 1 end
    return Player_HasResearch(p, CatUpgradeTech[name])
end

function CatUpgrade_Pending(rec)
    local u, list = CatUpgradeType[rec.t], {}
    if not u then return list, rec.armour end
    for i = 1, getn(u.abilities) do
        local name = u.abilities[i]
        if not rec.up[name] and CatUpgrade_Researched(rec.p, name) == 1 then tinsert(list, name) end
    end
    local armour = CatUpgrade_PlayerArmour(rec.p)
    if armour > u.armour then armour = u.armour end
    if armour < rec.armour then armour = rec.armour end
    return list, armour
end

-- FUN_00514540: 10 s per new ability (20 for Infect), plus the time for the armour level reached, x the ship's
-- upgradeTimeModifier
function CatUpgrade_Time(rec, list, armour)
    local t = 0
    for i = 1, getn(list) do
        if list[i] == "INFECT" then t = t + CAT_UPGRADE_TIME_INFECT else t = t + CAT_UPGRADE_TIME end
    end
    if armour > rec.armour then t = t + CatArmourTime[armour] end
    return t * CatUpgradeType[rec.t].time
end

function CatUpgrade_Apply(rec)
    local list, armour = CatUpgrade_Pending(rec)
    for i = 1, getn(list) do rec.up[list[i]] = 1 end
    rec.armour = armour
    rec.spd = -1                      -- re-apply the speed multiplier
    return getn(list)
end

-- the Upgrade command (FUN_0044de80): strike craft dock to upgrade, the rest upgrade where they are
function CatUpgrade_Start(g, p, id)
    local rec = CatShips[id]
    if not rec or rec.gone or rec.upg or not CatUpgradeType[rec.t] then return end
    local list, armour = CatUpgrade_Pending(rec)
    if getn(list) == 0 and armour == rec.armour then return end
    rec.upg = { time = CatUpgrade_Time(rec, list, armour), since = Universe_GameTime() }
    if CatUpgradeType[rec.t].dock == 1 and SobGroup_IsDocked(g) ~= 1 then
        rec.upg.dock = 1
        SobGroup_DockSobGroupWithAny(g)
        if not CatDockNotified or Universe_GameTime() - CatDockNotified > 2 then
            CatDockNotified = Universe_GameTime()
            print("CATACLYSM upgrade: Docking Ships to Upgrade")
            if Subtitle_Message then Subtitle_Message("Docking Ships to Upgrade", 3) end
        end
    else
        rec.upg.done = Universe_GameTime() + rec.upg.time
    end
    print("CATACLYSM upgrade: ship " .. id .. " (" .. rec.t .. ") " .. rec.upg.time .. " s")
end

-- Instant upgrades (FUN_00514490 without the command's timer): an UpgradeByDocking ship that is docked, for any
-- reason (FUN_00465860, its dock completing), and the ships a mission script upgrades (kasfShipsUpgrade, K_498c70 in
-- cataclysmkas.lua: SobGroup cat_kas_upgrade)
function CatUpgrade_Instant(rec, id)
    local u = CatUpgradeType[rec.t]
    if not u then return end
    local why
    if u.dock == 1 and SobGroup_IsDocked(rec.g) == 1 then why = "docked"
    elseif SobGroup_GroupInGroup(rec.g, "cat_kas_upgrade") == 1 then why = "mission" end
    if not why then return end
    local list, armour = CatUpgrade_Pending(rec)
    if getn(list) == 0 and armour == rec.armour then return end
    CatUpgrade_Apply(rec)
    CatShip_ApplyMultipliers(rec)
    print("CATACLYSM upgrade: ship " .. id .. " (" .. rec.t .. ") upgraded (" .. why .. ")")
end

function CatUpgrade_Tick(rec, id, now)
    local u = rec.upg
    if u.dock then
        if SobGroup_IsDocked(rec.g) == 1 then
            -- docking upgrades at once (CatUpgrade_Instant); the command then sends it back out
            u.dock, u.launch, u.done = nil, 1, now
        elseif now - u.since > CAT_UPGRADE_DOCK_GRACE and SobGroup_GetCurrentOrder(rec.g) ~= (COMMAND_Dock or 4) then
            rec.upg = nil                 -- given other orders on the way: no upgrade
            print("CATACLYSM upgrade: ship " .. id .. " cancelled")
        end
        return
    end
    if now < u.done then return end
    rec.upg = nil
    CatUpgrade_Apply(rec)
    CatShip_ApplyMultipliers(rec)
    print("CATACLYSM upgrade: ship " .. id .. " (" .. rec.t .. ") upgraded")
    if u.launch and SobGroup_IsDocked(rec.g) == 1 then
        SobGroup_CreateIfNotExist("cat_dockedwith")
        SobGroup_Clear("cat_dockedwith")
        SobGroup_GetSobGroupDockedWithGroup(rec.g, "cat_dockedwith")
        SobGroup_Launch(rec.g, "cat_dockedwith")
    end
end

-- test of a second custom command on the Acolyte; becomes the missile volley (Mission 3)
function CatVolley_Start(g, p, id)
    print("CATACLYSM ability volley: ship " .. id)
end

-- Link / Unlink

function CatLink_Start(g, p, id)
    local rec = CatShips[id]
    if not rec or rec.link or rec.gone then return end
    rec.link = { since = Universe_GameTime() }
    tinsert(CatLinkQueue, id)
    CatLink_Pair(p)
end


-- pair waiting Acolytes of a player, nearest first
function CatLink_Pair(p)
    local waiting = {}
    for i = 1, getn(CatLinkQueue) do
        local rec = CatShips[CatLinkQueue[i]]
        if rec and rec.p == p and rec.link and not rec.link.partner then tinsert(waiting, CatLinkQueue[i]) end
    end
    while getn(waiting) >= 2 do
        local a, best, bestd = waiting[1], 2, nil
        local pa = SobGroup_GetPosition(CatShips[a].g)
        for i = 2, getn(waiting) do
            local d = CatDist(pa, SobGroup_GetPosition(CatShips[waiting[i]].g))
            if not bestd or d < bestd then best, bestd = i, d end
        end
        local b = waiting[best]
        tremove(waiting, best)
        tremove(waiting, 1)
        local ra, rb = CatShips[a], CatShips[b]
        ra.link.partner, rb.link.partner = b, a
        ra.link.since, rb.link.since = Universe_GameTime(), Universe_GameTime()
        ra.link.lead = 1                     -- one of the pair does the swap
        CatLink_Converge(ra, rb)
    end
end

function CatDist(a, b)
    local x, y, z = a[1] - b[1], a[2] - b[2], a[3] - b[3]
    return sqrt(x * x + y * y + z * z)
end

function CatMid(a, b)
    return { (a[1] + b[1]) / 2, (a[2] + b[2]) / 2, (a[3] + b[3]) / 2 }
end

function CatLink_Converge(ra, rb)
    local mid = CatMid(SobGroup_GetPosition(ra.g), SobGroup_GetPosition(rb.g))
    SobGroup_MoveToPoint(ra.p, ra.g, mid)
    SobGroup_MoveToPoint(rb.p, rb.g, mid)
end

function CatLink_Dequeue(id)
    for i = 1, getn(CatLinkQueue) do
        if CatLinkQueue[i] == id then tremove(CatLinkQueue, i) return end
    end
end

-- the pair (or a lone Acolyte) stops linking
function CatLink_Cancel(rec, id)
    local pid = rec.link and rec.link.partner
    rec.link = nil
    CatLink_Dequeue(id)
    if pid then
        CatLink_Dequeue(pid)
        if CatShips[pid] then CatShips[pid].link = nil end
    end
end

function CatLink_Tick(rec, id, now)
    local l = rec.link
    if not l.partner then
        if now - l.since > CAT_LINK_WAIT then
            print("CATACLYSM link: No Ships To Link With")
            CatLink_Cancel(rec, id)
        end
        return
    end
    local other = CatShips[l.partner]
    if not other or not other.link or SobGroup_Empty(other.g) == 1 then
        CatLink_Cancel(rec, id)
        return
    end
    if not l.lead then return end
    if now - l.since > CAT_LINK_TIMEOUT then
        print("CATACLYSM link: the pair never met")
        CatLink_Cancel(rec, id)
        return
    end
    local pa, pb = SobGroup_GetPosition(rec.g), SobGroup_GetPosition(other.g)
    if CatDist(pa, pb) > CAT_LINK_DIST then
        CatLink_Converge(rec, other)
        return
    end
    -- the pair has met: one ACV in their place
    local kills = {}
    for c = 0, 11 do kills[c] = rec.kills[c] + other.kills[c] end
    local health = (SobGroup_HealthPercentage(rec.g) + SobGroup_HealthPercentage(other.g)) / 2
    local new = CatSpawn(rec.p, "smt_acv", CatMid(pa, pb), kills, { rec.kills, other.kills })
    SobGroup_SetHealth(new, health)
    CatLink_Dequeue(id)
    CatLink_Dequeue(l.partner)
    CatLink_Remove(rec)
    CatLink_Remove(other)
    print("CATACLYSM link: two Acolytes linked into an ACV (health " .. health .. ")")
end

function CatLink_Remove(rec)
    rec.gone = 1
    rec.link = nil
    SobGroup_Despawn(rec.g)
end

-- spawn one ship at a point into a new group; its Create picks up the kills
function CatSpawn(p, shiptype, pos, kills, parts)
    CatSerial = CatSerial + 1
    local grp, vol = "cat_spawn" .. CatSerial, "cat_spawnvol" .. CatSerial
    SobGroup_CreateIfNotExist(grp)
    SobGroup_Clear(grp)
    Volume_Delete(vol)
    Volume_AddSphere(vol, pos, 1)
    tinsert(CatPending, { group = grp, kills = kills, parts = parts })
    SobGroup_SpawnNewShipInSobGroup(p, shiptype, "cat_squad" .. CatSerial, grp, vol)
    Volume_Delete(vol)
    return grp
end

function CatUnlink_Start(g, p, id)
    local rec = CatShips[id]
    if not rec or rec.gone or SobGroup_Empty(g) == 1 then return end
    local pos, health = SobGroup_GetPosition(g), SobGroup_HealthPercentage(g)
    -- each Acolyte: its own kills (none for a built ACV) plus half of what the ACV earned
    local parts = rec.parts or {}
    local own = {}
    for k = 1, 2 do
        own[k] = {}
        for c = 0, 11 do own[k][c] = (parts[k] and parts[k][c]) or 0 end
    end
    local kills = { {}, {} }
    for c = 0, 11 do
        local gained = floor((rec.kills[c] - own[1][c] - own[2][c]) / 2)
        kills[1][c] = own[1][c] + gained
        kills[2][c] = own[2][c] + gained
    end
    for k = 1, 2 do
        local side = (k * 2 - 3) * CAT_LINK_DIST
        local new = CatSpawn(p, "smt_acolyte", { pos[1] + side, pos[2], pos[3] }, kills[k], nil)
        SobGroup_SetHealth(new, health)
    end
    rec.gone = 1
    SobGroup_Despawn(g)
    print("CATACLYSM link: ACV unlinked into two Acolytes")
end
