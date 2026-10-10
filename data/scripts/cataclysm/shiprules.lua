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
-- The Link / Unlink animation (sacolyte.mad, played through the .madstate's NIS00 / NIS01): Cataclysm puts both
-- Acolytes on one spot (here each 50 off it: see CatLink_Pose), the first rolled 180 degrees about its forward axis (right and up vectors negated), and
-- their Link clips slide each body in from 50 above its own deck (so one comes from above, one from below); the ACV
-- replaces them when the clips end or after 2 s, with the second one's orientation. Unlink places the Acolytes 50
-- either side of the ACV along its up axis (the second rolled) and their Unlink clips start them inside it.
CAT_LINK_ANIM = 1.6       -- the Link clip: Cataclysm swaps in the ACV when both clips end (its 2 s timer is a fallback);
                          -- the bodies end overlapping, as its ACV model is made, so a later swap shows them clipping
CAT_UNLINK_ANIM = 3.4     -- Unlink clip 2.27 s, the lower one then turning upright for 1 s: the new Acolytes stay put
                          -- until it ends (Cataclysm: 3 s)
CAT_LINK_OFFSET = 50 * 0.35
CAT_HOLD_SPEED = 0.01     -- speed multiplier of a ship held still for an animation

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
-- volley = 1 would let the weapons fire only for CAT_VOLLEY_WINDOW seconds after the ship's volley command (tried);
-- the Acolyte's fire in normal attacks, as Cataclysm's launchers do (FUN_005b3870; user: fine)
CatUpgradeWeapons = {
    smt_acolyte = { ORDINANCE = { ab = "AB_UseSpecialWeaponsInNormalAttack", volley = 0 } },
}
CAT_VOLLEY_WINDOW = 3

-- every tick (the engine may reset it, e.g. on docking)
function CatUpgradeWeapons_Tick(rec, id, now)
    local w = CatUpgradeWeapons[rec.t]
    if not w then return end
    for ability, spec in w do
        local on = 0
        if rec.up[ability] and (spec.volley ~= 1 or (rec.volleyUntil and now < rec.volleyUntil)) then on = 1 end
        if getglobal(spec.ab) then SobGroup_AbilityActivate(rec.g, getglobal(spec.ab), on) end
        if on ~= (rec.weaponsOn[ability] or 0) then
            rec.weaponsOn[ability] = on
            print("CATACLYSM upgrade: " .. ability .. " weapons " .. on .. " on ship " .. id)
        end
    end
end

-- A ship's native command (custom command, tools/make_abilities.py) works only once the ship has the upgrade it
-- needs, if any: otherwise the engine still spent its energy on a press the script ignored (user)
function CatNative_Tick(rec)
    if not rec.native or rec.native.upgrade == "" or not AB_Custom then return end
    local on = 0
    if rec.up[rec.native.upgrade] then on = 1 end
    SobGroup_AbilityActivate(rec.g, AB_Custom, on)
end

-- Ship scripts keep their Lua state from one game to the next (a restarted mission found the last one's pending link
-- spawns): a game clock gone backwards is a new game, so everything recorded is dropped
function CatSession(now)
    if CatLastTime and now < CatLastTime - 1 then
        print("CATACLYSM ship rules: new game (clock " .. CatLastTime .. " -> " .. now .. "), records cleared")
        CatShips, CatPending, CatLinkQueue, CatChainNext, CatLinkSwaps = {}, {}, {}, {}, {}
    end
    CatLastTime = now
end

function CatShip_Create(g, p, id, t)
    CatSession(Universe_GameTime())
    local real = t
    t = (CatVariantBase and CatVariantBase[t]) or t      -- a variant (variants_gen.lua) is its base type here
    local kills = {}
    for i = 0, 11 do kills[i] = 0 end
    -- g, the engine's custom-code group, is one name per ship type that holds whichever ship's code is running: a
    -- ship acting on another (the Link pair, kill credit) needs that one's own group, kept here
    local own = "cat_ship_" .. id
    SobGroup_CreateIfNotExist(own)
    SobGroup_Clear(own)
    SobGroup_SobGroupAdd(own, g)
    local rec = { g = own, p = p, t = t, real = real, cls = CatClass[t] or CAT_FIGHTER, kills = kills, rank = 0,
                  spd = 1, dmg = 1, next = 0, att = "cat_att_" .. id }
    CatShips[id] = rec
    -- its button abilities (tools/make_abilities.py): the mission script fills cat_cmd_<name> on a press
    rec.buttons = {}
    for i = 1, getn(CatAbilities) do
        local a = CatAbilities[i]
        -- on its own type too: a disguise (smt_mimic_<target>) has Unmimic, which its base smt_mimic lacks
        if a.native == 0 and (strfind(", " .. a.types .. ",", ", " .. t .. ",", 1, 1) or
                              strfind(", " .. a.types .. ",", ", " .. real .. ",", 1, 1)) then
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
    for i = 1, getn(CatAbilities) do
        local a = CatAbilities[i]
        if a.native == 1 and strfind(", " .. a.types .. ",", ", " .. t .. ",", 1, 1) then rec.native = a end
    end
end

-- A ship spawned by a link/unlink (CatSpawn) takes over its pilots' kills, and any pin / hold. Matched on its first
-- update: at creation g is still empty, so the match found nothing (the pins never ran).
CAT_PENDING_LIFE = 5
function CatShip_Adopt(rec, g, now)
    rec.adopted = 1
    if rec.real == "smt_mimic" then rec.mimicShow = 2 end   -- its disguises hidden (CatMimic_Tick)
    local i = 1
    while i <= getn(CatPending) do
        local pend = CatPending[i]
        if now - pend.since > CAT_PENDING_LIFE then
            tremove(CatPending, i)                -- its ship never showed up
        elseif SobGroup_GroupInGroup(g, pend.group) == 1 then
            for c = 0, 11 do rec.kills[c] = pend.kills[c] end
            rec.parts = pend.parts
            rec.hold, rec.pin = pend.hold, pend.pin
            if pend.linking then                  -- standing in for the Link clip (CatLink_Pose)
                rec.linking = pend.linking
                tinsert(pend.linking.recs, rec)
            end
            if pend.up then                       -- a variant swap: the same ship, already upgraded
                rec.up, rec.armour, rec.launchFrom = pend.up, pend.armour, pend.launchFrom
            end
            tremove(CatPending, i)
            CatShip_UpdateRank(rec, 0)
            return
        else
            i = i + 1
        end
    end
end

function CatShip_Update(g, p, id)
    local now = Universe_GameTime()
    CatSession(now)
    if getn(CatLinkSwaps) > 0 then CatLinkSwap_Tick(now) end
    local rec = CatShips[id]
    if not rec then return end
    if not rec.adopted and SobGroup_Empty(g) == 0 then CatShip_Adopt(rec, g, now) end
    -- a ship swapped for its variant: SobGroup_Despawn did nothing while it was docked (the engine relaunched it), so
    -- it stays hidden and removes itself once out. Only through its own g: a group name kept after a ship's code
    -- ends is given to other ships (a removal list of old names removed every Acolyte)
    if rec.swapped then
        if SobGroup_Empty(g) == 0 then
            SobGroup_SetHidden(g, 1)
            if SobGroup_IsDocked(g) ~= 1 then SobGroup_Despawn(g) end
        end
        return
    end
    if rec.pin then
        local pin = rec.pin
        if now < pin.t then
            if SobGroup_Empty(g) == 0 then
                if not pin.frozen then
                    pin.frozen = 1
                    CatFreeze(g, 0)
                end
                if not pin.traced then
                    pin.traced = 1
                    CatTrace("pin " .. id .. " from " .. now .. " to " .. pin.t)
                end
                local f = pin.from
                if f and now < f.t1 then          -- gliding into the pose
                    local k = (now - f.t0) / (f.t1 - f.t0)
                    k = k * k * (3 - 2 * k)
                    CatPlace(g, CatLerp(f.pos, pin.pos, k), CatBlendXf(f.xf, pin.xf, k))
                else
                    CatPlace(g, pin.pos, pin.xf)
                end
            end
        else
            rec.pin = nil
            CatTrace("pin " .. id .. " released at " .. now)
            if pin.frozen then CatFreeze(g, 1) end
            if pin.after then SobGroup_MoveToPoint(rec.p, g, pin.after) end
        end
    end
    if rec.link and rec.filled then CatLink_Tick(rec, id, now) end     -- every update: the approach needs it
    -- repair beams: every update (make_shipcode.py FAST: 0.05 s), so the beams follow their ships
    if (rec.t == "smt_worker" or rec.t == "smt_processor") and rec.filled and rec.p and SobGroup_Empty(g) == 0 then
        CatRepair_Tick(rec, g, id, now)
        if rec.t == "smt_processor" then CatProcessor_Tick(rec, g, id, now) end
    end
    if now < rec.next then return end
    rec.next = now + CAT_TICK
    if SobGroup_Empty(g) == 1 then return end
    -- our own group (CatShip_Create): filled here, where g surely holds this ship (filled at creation, the level's
    -- ships' groups came out empty)
    SobGroup_CreateIfNotExist(rec.g)
    if SobGroup_Empty(rec.g) == 1 then
        SobGroup_SobGroupAdd(rec.g, g)
        if not rec.filled then
            rec.filled = 1
            CatTrace("ship " .. id .. " own group " .. rec.g .. ": " .. SobGroup_Count(rec.g) .. " ship(s)")
        end
    end
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
    if rec.real == "smt_mimic" then CatMimic_Tick(rec, g, id, now) end
    if CatKamikazeScream[rec.t] then CatKamikaze_Tick(rec, g, id) end
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
                else
                    print("CATACLYSM ability " .. b.name .. ": ship " .. id .. " pressed but no longer selected")
                end
            end
        else
            b.pressed = nil
        end
    end
    CatUpgradeWeapons_Tick(rec, id, now)
    CatNative_Tick(rec)
    CatGated_Tick(rec)
    CatUpgrade_Instant(rec, id)
    if rec.upg then CatUpgrade_Tick(rec, id, now) end
    if rec.gone then return end
    if rec.launchFrom and SobGroup_IsDocked(g) == 1 then
        SobGroup_Launch(g, rec.launchFrom)
        rec.launchFrom = nil
    end
    if not rec.upg and CatVariant_Wanted(rec) ~= rec.real and SobGroup_IsDocked(g) == 1 then
        CatVariant_Swap(rec, id, nil)
    end
end

function CatShip_Destroy(g, p, id)
    local rec = CatShips[id]
    if not rec then return end
    CatShips[id] = nil
    if rec.gone or rec.linking then return end   -- linked or unlinked away, not killed
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
    if rec.hold then                      -- held still for the Link / Unlink animation
        if Universe_GameTime() < rec.hold then spd = CAT_HOLD_SPEED else rec.hold = nil end
    end
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
            getglobal(a.handler)(g, p, id, name)    -- the name: one handler for several buttons (Mimic menu)
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
    if why == "docked" and CatVariant_Wanted(rec) ~= rec.real then
        local launch = rec.upg and 1      -- the Upgrade command docked it: the variant goes back out
        rec.upg = nil
        CatVariant_Swap(rec, id, launch)
    end
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
        if CatVariant_Wanted(rec) ~= rec.real then
            CatVariant_Swap(rec, id, 1)           -- the variant launches once docked in its place
            return
        end
        SobGroup_CreateIfNotExist("cat_dockedwith")
        SobGroup_Clear("cat_dockedwith")
        SobGroup_GetSobGroupDockedWithGroup(rec.g, "cat_dockedwith")
        SobGroup_Launch(rec.g, "cat_dockedwith")
    end
end

-- Fire Missiles (strMenuSpecialFireMissilesDesc), the Acolyte's native command once it has the ORDINANCE upgrade:
-- its energy bar is the missile cooldown (tools/make_abilities.py ENERGY). HWRM scripts can't fire weapons, so the
-- volley opens the launchers for CAT_VOLLEY_WINDOW (CatUpgradeWeapons: one missile each) and keeps the Acolyte on its
-- current target.
function CatVolley_Start(g, p, id)
    local rec = CatShips[id]
    if rec then rec.volleyUntil = Universe_GameTime() + CAT_VOLLEY_WINDOW end
    SobGroup_CreateIfNotExist("cat_volley_target")
    SobGroup_Clear("cat_volley_target")
    SobGroup_GetCommandTargets("cat_volley_target", g, COMMAND_Attack or 2)
    if SobGroup_Empty("cat_volley_target") == 0 then SobGroup_Attack(p, g, "cat_volley_target") end
    print("CATACLYSM ability volley: ship " .. id .. " on " .. SobGroup_Count("cat_volley_target") .. " targets")
end

-- Link / Unlink

-- a unit bark for the mission script to play (ship code can't reach the speech system): the human's ship goes into
-- the named group cat_say_<Cataclysm speech event>, cataclysmkas.lua CatSayTick plays it in that ship type's voice
function CatSay(event, g, p)
    if p ~= 0 then return end
    local grp = "cat_say_" .. event
    SobGroup_CreateIfNotExist(grp)
    SobGroup_SobGroupAdd(grp, g)
end

function CatLink_Start(g, p, id)
    local rec = CatShips[id]
    if not rec or rec.link or rec.gone then return end
    CatSay(156, g, p)                                  -- "Initiating link protocol."
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

-- The partner waits (both flying to one point, collision avoidance kept them bouncing apart); the lead flies to its
-- slot under it (CatLink_Pose), first to a point CAT_LINK_APPROACH behind the slot along the partner's heading, so it
-- comes in from behind pointing the right way. Returns the slot, or nil.
CAT_LINK_APPROACH = 300
CAT_LINK_NEAR = 120       -- this close to the approach point / the slot counts as there
CAT_LINK_GLIDE = 0.8      -- seconds the lead glides from where it is into the clip's start pose
CAT_LINK_STOPPED = 5      -- the lead is swapped for its stand-in only once its speed is below this (stopped)
CAT_LINK_SETTLE = 3       -- ...or once it has been at its slot this long (a fighter that never quite stops)
function CatLink_Converge(ra, rb, now)
    if not rb.link.waiting then
        rb.link.waiting = 1
        SobGroup_Stop(rb.p, rb.g)
    end
    local xf = SobGroup_GetCoordSys(rb.g)
    if getn(xf) ~= 9 then return nil end
    local l = ra.link
    local slot = CatAdd(SobGroup_GetPosition(rb.g), CatUpAxis(xf), -2 * CAT_LINK_OFFSET)
    local target = slot
    if not l.final then
        local ap = CatAdd(slot, CatCol(xf, 2), -CAT_LINK_APPROACH)
        if CatDist(SobGroup_GetPosition(ra.g), ap) < CAT_LINK_NEAR then l.final = 1 else target = ap end
    end
    if not l.ordered or now - l.ordered > 0.5 or l.orderedFinal ~= l.final then
        SobGroup_MoveToPoint(ra.p, ra.g, target)
        l.ordered, l.orderedFinal = now, l.final
    end
    return slot
end

function CatLink_Dequeue(id)
    for i = 1, getn(CatLinkQueue) do
        if CatLinkQueue[i] == id then tremove(CatLinkQueue, i) return end
    end
end

-- the pair (or a lone Acolyte) stops linking
function CatLink_Cancel(rec, id)
    local pid = rec.link and rec.link.partner
    local posed = rec.link and rec.link.anim
    rec.link = nil
    CatLink_Dequeue(id)
    CatLink_Unpose(rec, posed)
    if pid then
        CatLink_Dequeue(pid)
        local other = CatShips[pid]
        if other then
            posed = posed or (other.link and other.link.anim)
            other.link = nil
            CatLink_Unpose(other, posed)
        end
    end
end

-- a ship whose pair broke up mid-animation: free to move, back in its rest pose (.madstate DockPathClosed4)
function CatLink_Unpose(rec, posed)
    if rec.pin and rec.pin.frozen and SobGroup_Empty(rec.g) == 0 then CatFreeze(rec.g, 1) end
    rec.hold, rec.pin = nil, nil
    if posed and not rec.gone and SobGroup_Empty(rec.g) == 0 then SobGroup_SetMadState(rec.g, "DockPathClosed4") end
end

-- Ship orientations: SobGroup_GetCoordSys gives a 3x3 matrix as 9 numbers, its columns the ship's right, up and
-- forward axes, stored row by row: column c is entries c+1, c+4, c+7 (checked in game against the engine's
-- Matrix3_GetVector3FromCol, which the ship script state lacks: range.lua Range_CoordSys)
function CatByColumn(m)
    return 0
end

-- the orientation rolled 180 degrees about its forward axis: right and up negated
function CatRoll(m)
    local r = {}
    for i = 1, 9 do r[i] = m[i] end
    if CatByColumn(m) == 1 then
        for i = 1, 6 do r[i] = -m[i] end
    else
        for i = 0, 2 do
            r[i * 3 + 1], r[i * 3 + 2] = -m[i * 3 + 1], -m[i * 3 + 2]
        end
    end
    return r
end

function CatUpAxis(m)
    if CatByColumn(m) == 1 then return { m[4], m[5], m[6] } end
    return { m[2], m[5], m[8] }
end

function CatCol(m, c)
    return { m[c + 1], m[c + 4], m[c + 7] }
end

function CatLerp(a, b, k)
    return { a[1] + (b[1] - a[1]) * k, a[2] + (b[2] - a[2]) * k, a[3] + (b[3] - a[3]) * k }
end

function CatAdd(a, v, s)
    return { a[1] + v[1] * s, a[2] + v[2] * s, a[3] + v[3] * s }
end

function CatCross(a, b)
    return { a[2] * b[3] - a[3] * b[2], a[3] * b[1] - a[1] * b[3], a[1] * b[2] - a[2] * b[1] }
end

function CatNorm(v)
    local n = sqrt(v[1] * v[1] + v[2] * v[2] + v[3] * v[3])
    if n < 0.0001 then return nil end
    return { v[1] / n, v[2] / n, v[3] / n }
end

-- an orientation between a and b (k 0..1): forward and up blended, made square again (right = up x forward)
function CatBlendXf(a, b, k)
    local f = CatNorm(CatLerp(CatCol(a, 2), CatCol(b, 2), k))
    local u = CatLerp(CatCol(a, 1), CatCol(b, 1), k)
    if not f then return b end
    local r = CatNorm(CatCross(u, f))
    if not r then return b end
    u = CatCross(f, r)
    return { r[1], u[1], f[1], r[2], u[2], f[2], r[3], u[3], f[3] }
end

function CatPlace(g, pos, m)
    SobGroup_SetPosition(g, pos)
    SobGroup_SetTransform(g, m)
end

-- A ship pinned for an animation is put back on its spot, in its orientation, on every update of its own (the
-- Acolyte's custom code runs every CAT_PIN_TICK: tools/make_shipcode.py FAST): left alone, HWRM's flight code levels
-- the rolled one and moves both, sliding them through each other.
CAT_PIN_TICK = 0.05
function CatPin(rec, pos, m, untilT)
    rec.pin = { pos = pos, xf = m, t = untilT }
end

-- steering and movement off while pinned (between re-placements the engine still turned and moved them: jiggling)
function CatFreeze(g, on)
    SobGroup_AbilityActivate(g, AB_Move, on)
    if AB_Steering then SobGroup_AbilityActivate(g, AB_Steering, on) end
    SobGroup_SetGhost(g, 1 - on)          -- and no collisions (the Link pair still jiggled)
end

-- step-by-step log of the Link / Unlink sequence (finding a fatal engine-call error: the log shows the last step)
CAT_TRACE = 0
function CatTrace(msg)
    if CAT_TRACE == 1 then print("CATACLYSM trace: " .. msg) end
end

-- The met pair is replaced by two fresh Acolytes posed for the Link clip, which become the ACV when it has played
-- (CatLinkSwap_Tick). Fresh ships because ships that were flying keep drifting with their speed once frozen (HWRM
-- scripts can't zero it), so pinning them jittered; the Unlink ones, spawned at rest, are still.
-- Not on one spot as in Cataclysm (two ships there collide and shake): each 50 off it along the partner's up axis,
-- where its body starts (the Link clip is shifted to match: tools/build_ship.sh), the lead below and rolled.
if not CatLinkSwaps then CatLinkSwaps = {} end
-- 1: the pair is replaced by fresh Acolytes for the clip (at rest: the flying pair jittered when the pins were not
-- yet running and the lower one was really rolled); 0: the pair itself plays it
CAT_LINK_STANDINS = 1     -- (0 tried with the approach and glide: the lower one still jiggled)

function CatLink_Pose(ra, rb, now)
    local xf = SobGroup_GetCoordSys(rb.g)
    local pb = SobGroup_GetPosition(rb.g)
    local pos = pb
    if getn(xf) == 9 then pos = CatAdd(pb, CatUpAxis(xf), -CAT_LINK_OFFSET) end     -- the ACV's place
    local health = (SobGroup_HealthPercentage(ra.g) + SobGroup_HealthPercentage(rb.g)) / 2
    local kills = {}
    for c = 0, 11 do kills[c] = ra.kills[c] + rb.kills[c] end
    local sw = { p = ra.p, pos = pos, t = now + CAT_LINK_ANIM, kills = kills, parts = { ra.kills, rb.kills },
                 health = health, recs = {} }
    if getn(xf) == 9 then
        sw.xf = xf
        local pa = CatAdd(pos, CatUpAxis(xf), -CAT_LINK_OFFSET)
        if CAT_LINK_STANDINS == 1 then
            -- only the lead, stopped under its partner, is swapped (two spawns at once dropped frames, and a
            -- moving ship's swap showed); its stand-in glides the rest of the way, then both clips start together
            -- (CatLinkSwap_Tick). The partner is the real ship, pinned where it waited.
            sw.start = now + CAT_LINK_GLIDE
            sw.t = sw.start + CAT_LINK_ANIM
            sw.a = CatLink_Stand(ra, pa, xf, sw, sw.start,
                                 { pos = SobGroup_GetPosition(ra.g), xf = SobGroup_GetCoordSys(ra.g), t0 = now,
                                   t1 = sw.start })
            sw.b = CatLink_Hold(rb, pb, xf, sw, sw.start, nil)
            sw.states = { { sw.a, "NIS02" }, { sw.b, "NIS00" } }     -- below: its model shown rolled (LinkB)
        else
            sw.start = now + CAT_LINK_GLIDE
            sw.t = sw.start + CAT_LINK_ANIM
            sw.states = { { ra.g, "NIS02" }, { rb.g, "NIS00" } }
            sw.a = CatLink_Hold(ra, pa, xf, sw, sw.start,
                                { pos = SobGroup_GetPosition(ra.g), xf = SobGroup_GetCoordSys(ra.g), t0 = now, t1 = sw.start })
            sw.b = CatLink_Hold(rb, pb, xf, sw, sw.start, nil)
        end
    else
        print("CATACLYSM link: unexpected coordsys of " .. getn(xf) .. " numbers, no animation")
        sw.t = now
    end
    CatLink_Dequeue(rb.link.partner)          -- the lead's id
    CatLink_Dequeue(ra.link.partner)
    if not sw.a then
        CatLink_Remove(ra)
        CatLink_Remove(rb)
    elseif CAT_LINK_STANDINS == 1 then
        CatLink_Remove(ra)
        rb.link = nil
    else
        ra.link, rb.link = nil, nil
    end
    tinsert(CatLinkSwaps, sw)
end

-- the pair themselves posed for the Link clip: stopped, frozen, pinned (CAT_LINK_STANDINS = 0)
-- (from: glide there from that pose; the clip itself is started by CatLinkSwap_Tick at sw.start)
function CatLink_Hold(rec, at, xf, sw, start, from)
    SobGroup_Stop(rec.p, rec.g)
    CatPin(rec, at, xf, start + CAT_LINK_ANIM + 1)
    rec.pin.from = from
    rec.pin.frozen = 1
    CatFreeze(rec.g, 0)
    rec.hold = start + CAT_LINK_ANIM + 1
    CatShip_ApplyMultipliers(rec)
    rec.linking = sw
    tinsert(sw.recs, rec)
    return rec.g
end

-- a fresh Acolyte in rec's place for the Link clip: same type, kills and health, pinned and playing Link
-- (from: it appears there, in that orientation, and glides to at / xf)
function CatLink_Stand(rec, at, xf, sw, start, from)
    local first = (from and from.pos) or at
    local g = CatSpawn(rec.p, rec.real, first, rec.kills, rec.parts, start + CAT_LINK_ANIM + 1,
                       { pos = at, xf = xf, t = start + CAT_LINK_ANIM + 1, from = from }, sw)
    CatPlace(g, first, (from and from.xf) or xf)
    SobGroup_SetHealth(g, SobGroup_HealthPercentage(rec.g))
    return g
end

-- run from every ship's update: Link clips that have played become their ACV
function CatLinkSwap_Tick(now)
    local i = 1
    while i <= getn(CatLinkSwaps) do
        local sw = CatLinkSwaps[i]
        if sw.states and now >= sw.start then     -- the glide is over: both clips together
            for k = 1, getn(sw.states) do
                if SobGroup_Empty(sw.states[k][1]) == 0 then SobGroup_SetMadState(sw.states[k][1], sw.states[k][2]) end
            end
            sw.states = nil
        end
        if now >= sw.t then
            tremove(CatLinkSwaps, i)
            CatLinkSwap_Do(sw)
        else
            i = i + 1
        end
    end
end

function CatLinkSwap_Do(sw)
    if sw.a and (SobGroup_Empty(sw.a) == 1 or SobGroup_Empty(sw.b) == 1) then
        -- one was killed mid-Link: the other is an Acolyte again
        for k = 1, getn(sw.recs) do
            local rec = sw.recs[k]
            rec.linking, rec.pin, rec.hold = nil, nil, nil
            if SobGroup_Empty(rec.g) == 0 then
                CatFreeze(rec.g, 1)
                SobGroup_SetMadState(rec.g, "DockPathClosed4")
            end
        end
        print("CATACLYSM link: one of the pair was lost mid-Link")
        return
    end
    local new = CatSpawn(sw.p, "smt_acv", sw.pos, sw.kills, sw.parts)
    if sw.xf then CatPlace(new, sw.pos, sw.xf) end
    SobGroup_SetHealth(new, sw.health)
    if sw.a then
        for k = 1, getn(sw.recs) do sw.recs[k].gone = 1 end
        SobGroup_Despawn(sw.a)
        SobGroup_Despawn(sw.b)
    end
    print("CATACLYSM link: two Acolytes linked into an ACV (health " .. sw.health .. ")")
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
    local slot = CatLink_Converge(rec, other, now)
    if rec.link.final and slot and CatDist(SobGroup_GetPosition(rec.g), slot) < CAT_LINK_NEAR then
        l.nearSince = l.nearSince or now
        -- stopped under its partner (or there a while, if it keeps drifting)
        if CAT_LINK_STANDINS == 0 or SobGroup_GetActualSpeed(rec.g) < CAT_LINK_STOPPED
           or now - l.nearSince > CAT_LINK_SETTLE then
            CatLink_Pose(rec, other, now)          -- the pair has met
        end
    else
        l.nearSince = nil
    end
end

-- (SHELVED with tools/ship_variants.py: CatVariants is empty, so none of this runs; kept for a retry.)
-- Ship type variants (tools/ship_variants.py, variants_gen.lua): HWRM weapons are per ship type, so a ship whose
-- upgrades call for other weapons (WEAPON_ENERGY: the Acolyte's Energy Cannons) is swapped for its variant type
-- while docked: invisible in the hangar. The type a ship should be: the last variant whose upgrade it has.
function CatVariant_Wanted(rec)
    local list, want = CatVariants and CatVariants[rec.t], rec.t
    if list then
        for i = 1, getn(list) do
            if rec.up[list[i].upgrade] then want = list[i].type end
        end
    end
    return want
end

-- the type a new ship of player p should be built as (Unlink): the variant once its upgrade is researched
function CatVariant_ForNew(p, base)
    local list, want = CatVariants and CatVariants[base], base
    if list then
        for i = 1, getn(list) do
            if CatUpgrade_Researched(p, list[i].upgrade) == 1 then want = list[i].type end
        end
    end
    return want
end

-- the player's ship with a hangar nearest the docked ship (SobGroup_GetSobGroupDockedWithGroup found nothing for
-- Acolytes docked in the Kuun-Lan); ship code fills from the engine's Player_Ships<p> group, as their ship scripts do
CatCarrierTypes = { "smt_ms_sp", "smt_ms", "smt_carrier" }
function CatVariant_NearestCarrier(rec, out)
    local pos, best, bestd = SobGroup_GetPosition(rec.g), nil, nil
    SobGroup_CreateIfNotExist("cat_carriers")
    for i = 1, getn(CatCarrierTypes) do
        SobGroup_Clear("cat_carriers")
        SobGroup_FillShipsByType("cat_carriers", "Player_Ships" .. rec.p, CatCarrierTypes[i])
        if SobGroup_Empty("cat_carriers") == 0 then
            local d = CatDist(pos, SobGroup_GetPosition("cat_carriers"))
            if not bestd or d < bestd then best, bestd = CatCarrierTypes[i], d end
        end
    end
    if best then
        SobGroup_Clear(out)
        SobGroup_FillShipsByType(out, "Player_Ships" .. rec.p, best)
    end
end

-- the docked ship -> its wanted type, docked in the same ship (launched again if `launch`), kills, upgrades and
-- health carried over
function CatVariant_Swap(rec, id, launch)
    CatSerial = CatSerial + 1
    local carrier = "cat_carrier" .. CatSerial
    SobGroup_CreateIfNotExist(carrier)
    SobGroup_Clear(carrier)
    SobGroup_GetSobGroupDockedWithGroup(rec.g, carrier)
    if SobGroup_Empty(carrier) == 1 then CatVariant_NearestCarrier(rec, carrier) end
    if SobGroup_Empty(carrier) == 1 then
        if not rec.swapWarned then
            rec.swapWarned = 1
            print("CATACLYSM variant: ship " .. id .. " docked with nothing found: no swap to " .. CatVariant_Wanted(rec))
        end
        return
    end
    local want, health = CatVariant_Wanted(rec), SobGroup_HealthPercentage(rec.g)
    local up = {}
    for k, v in rec.up do up[k] = v end
    local new = CatSpawn(rec.p, want, SobGroup_GetPosition(carrier), rec.kills, rec.parts)
    local pend = CatPending[getn(CatPending)]
    pend.up, pend.armour = up, rec.armour
    if launch then pend.launchFrom = carrier end
    SobGroup_DockSobGroupInstant(new, carrier)
    SobGroup_SetHealth(new, health)
    rec.gone, rec.swapped = 1, Universe_GameTime()
    SobGroup_SetHidden(rec.g, 1)
    SobGroup_Despawn(rec.g)
    print("CATACLYSM variant: ship " .. id .. " (" .. rec.real .. ") -> " .. want .. (launch and ", relaunching" or ""))
end

function CatLink_Remove(rec)
    rec.gone = 1
    rec.link = nil
    SobGroup_Despawn(rec.g)
end

-- spawn one ship at a point into a new group; its Create picks up the kills
function CatSpawn(p, shiptype, pos, kills, parts, hold, pin, linking)
    CatSerial = CatSerial + 1
    local grp, vol = "cat_spawn" .. CatSerial, "cat_spawnvol" .. CatSerial
    SobGroup_CreateIfNotExist(grp)
    SobGroup_Clear(grp)
    Volume_Delete(vol)
    Volume_AddSphere(vol, pos, 1)
    tinsert(CatPending, { group = grp, kills = kills, parts = parts, hold = hold, pin = pin, linking = linking,
                          since = Universe_GameTime() })
    SobGroup_SpawnNewShipInSobGroup(p, shiptype, "cat_squad" .. CatSerial, grp, vol)
    Volume_Delete(vol)
    return grp
end

-- ---------------------------------------------------------------------------------------------------------------
-- The Mimic (Cataclysm FUN_005b8d70: mimic a ship type as its owner / unmimic). Cataclysm draws the target's model on
-- the Mimic itself (FUN_005b9640), the same ship flying on: here its model holds its body and every disguise
-- (tools/make_mimic.py, joints shown one at a time by its .madstate in the state CatDisguises[i].state; NIS00 the
-- Mimic). Lines: 165 "Roger, holographic projectors on.", 166 "Holographic field collapsed."
-- The transformation (Cataclysm FUN_005b8f30, 1.25 s): the target's model as a shell shrinking out of a sphere and
-- fading in, then the real model; Unmimic the reverse. Mesh effects (tools/make_mimicfx.py) started as the ship's
-- events (MimicIn_ / MimicOut_ / MimicTail_<target>) so they move with it: MimicIn_ on the press, the model switched
-- CAT_MIMIC_SWAP later (Cataclysm stops drawing the Mimic at 0.94 s) under MimicTail_; Unmimic switches at once
-- under MimicOut_. From one disguise to another both shells play.
-- Disguised, its target's side leaves it alone (Cataclysm: the mimic seems one of theirs): SobGroup_MakeUntargeted
-- on every update. That call (HWRM luasobgroupactions.cpp) sets nothing on the ship: it drops the ship from every
-- other ship's attack targets once, so repeating it keeps it dropped, and stopping makes it a target again.
CAT_MIMIC_SWAP = 1.0     -- make_mimicfx.py SWAP; two ship updates (CAT_TICK)

function CatNoop(g, p, id, name)
end

function CatDisguise_Find(field, value)
    for i = 1, getn(CatDisguises) do
        if CatDisguises[i][field] == value then return CatDisguises[i] end
    end
    return nil
end

function CatMimic_Tick(rec, g, id, now)
    if rec.mimicShow then                     -- a new Mimic: its disguises hidden (the first update can be early)
        SobGroup_SetMadState(g, "NIS00")
        rec.mimicShow = rec.mimicShow - 1
        if rec.mimicShow == 0 then rec.mimicShow = nil end
    end
    local m = rec.mimicAt
    if m and now >= m.t then                  -- the shell has formed: the disguise's model
        rec.mimicAt = nil
        SobGroup_SetMadState(g, m.d.state)
        FX_StartEvent(g, "MimicTail_" .. m.d.target)
        rec.disguise = m.d
        CatMimic_Disguised(rec, 1)
        CatSay(168, g, rec.p)                 -- "Disguise assumed."
        print("CATACLYSM mimic: ship " .. id .. " disguised as " .. m.d.target)
    end
    if rec.disguise then SobGroup_MakeUntargeted(g) end
end

-- the disguised Mimics, for the mission script's Unmimic button (abilities_gen.lua group cat_disguised)
function CatMimic_Disguised(rec, on)
    SobGroup_CreateIfNotExist("cat_disguised")
    if on == 1 then
        SobGroup_SobGroupAdd("cat_disguised", rec.g)
    else
        SobGroup_CreateIfNotExist("cat_disguised_left")
        SobGroup_Clear("cat_disguised_left")
        SobGroup_FillSubstract("cat_disguised_left", "cat_disguised", rec.g)
        SobGroup_Clear("cat_disguised")
        SobGroup_SobGroupAdd("cat_disguised", "cat_disguised_left")
    end
end

-- a Mimic menu button (mimic_<target>): become that disguise
function CatMimic_As(g, p, id, name)
    local rec = CatShips[id]
    local d = CatDisguise_Find("button", name)
    if not rec or rec.gone or not d or rec.mimicAt or SobGroup_Empty(g) == 1 then return end
    if rec.disguise and rec.disguise.target == d.target then return end
    CatSay(165, g, p)
    if rec.disguise then FX_StartEvent(g, "MimicOut_" .. rec.disguise.target) end
    FX_StartEvent(g, "MimicIn_" .. d.target)
    rec.mimicAt = { t = Universe_GameTime() + CAT_MIMIC_SWAP - 0.01, d = d }
end

function CatUnmimic_Start(g, p, id, name)
    local rec = CatShips[id]
    if not rec or rec.mimicAt or not rec.disguise then return end
    CatSay(166, g, p)
    SobGroup_SetMadState(g, "NIS00")
    FX_StartEvent(g, "MimicOut_" .. rec.disguise.target)
    print("CATACLYSM mimic: ship " .. id .. " drops its " .. rec.disguise.target .. " disguise")
    rec.disguise = nil
    CatMimic_Disguised(rec, 0)
end

-- ---------------------------------------------------------------------------------------------------------------
-- Kamikaze: HWRM's own Kamikaze order and damage (about the rammer's health x 7.5). The Mimic's is Cataclysm's 1000
-- through its health and armour (tools/make_mimicarmour.py). A script can't tell a kamikaze from an attack (both
-- COMMAND_Attack; IsDoingAbility AB_Kamikaze is 1 for every ship), except on a ship with no guns: the Mimic's
-- attack is its kamikaze, so its pilot's last words (line 167) as it starts.
CatKamikazeScream = { smt_mimic = 1 }

-- An attack order on one is made a kamikaze (user: its default attack; SobGroup_Kamikaze, as KAS_Kamikaze), on the
-- same targets; the order stays COMMAND_Attack, so once per order.
function CatKamikaze_Tick(rec, g, id)
    local attacking = SobGroup_GetCurrentOrder(g) == (COMMAND_Attack or 2)
    if attacking and not rec.kamiAttack then
        CatSay(167, g, rec.p)
        local t = "cat_kamit_" .. id
        SobGroup_CreateIfNotExist(t)
        SobGroup_Clear(t)
        SobGroup_GetCommandTargets(t, g, COMMAND_Attack or 2)
        if SobGroup_Empty(t) == 0 then SobGroup_Kamikaze(g, t) end
    end
    rec.kamiAttack = attacking
end

-- ---------------------------------------------------------------------------------------------------------------
-- Repair and salvage (Cataclysm: the Worker's and Processor's REPAIR, the Worker's SALVAGE ability bits, from the
-- Repair / Salvage research and upgrade): HWRM's own repair / salvage orders switched on only once the ship has the
-- ability (user)
CatGatedAbilities = { REPAIR = "AB_Repair", SALVAGE = "AB_Salvage" }

function CatGated_Tick(rec)
    local u = CatUpgradeType[rec.t]
    if not u then return end
    if not rec.gated then
        rec.gated = {}
        for i = 1, getn(u.abilities) do
            local ab = CatGatedAbilities[u.abilities[i]]
            if ab and getglobal(ab) then tinsert(rec.gated, { name = u.abilities[i], ab = getglobal(ab) }) end
        end
    end
    for i = 1, getn(rec.gated) do
        local gt = rec.gated[i]
        local on = 0
        if rec.up[gt.name] then on = 1 end
        if gt.on ~= on then
            SobGroup_AbilityActivate(rec.g, gt.ab, on)
            gt.on = on
        end
    end
end

-- The ordered repair (the Worker's and Processor's RepairCommand: install_cr.py repair_order). HWRM heals only by
-- latching onto the target's repair point (RepairByLatchingCommand), which flew the repairer onto the target and
-- dragged it along (user: "jank"). Its non-latching form (4th argument 1) approaches the target, faces it (the
-- Processor turns its side) and holds off (data/scripts/attack/*_catrepair.lua) but never heals, and keeps the
-- target to itself (SobGroup_GetCommandTargets: nothing). So, as Cataclysm (HW1 RepairCorvette.c refuelRepairShips:
-- stop in range, face the target, beam it while it is in the beam's angle): the Worker beams the damaged friendly
-- nearest to it (sworker.shp repairDistance 1500 x 0.525; no cone: CatRepair_InWorkerBeam), the Processor its side beams
-- (CatProcessor_Tick); the order ends once it sits still with nothing to heal.
CAT_REPAIR_CONE = 60        -- the repair cone's length (stock repair_beam at scale 1: estimated; its mesh is unreadable)
CAT_WORKER_REACH = 2 * CAT_REPAIR_CONE   -- the beam reaches this far past the tip (user: about twice the cone)
CAT_WORKER_TIP_OFF = 30     -- its jackhammer tip from its centre (build_ship.sh TIP)
CAT_JACK_OUT = 2.3          -- sworker.mad JackOut: 2.267 s; the cone shows once the boom is out (user)
-- how far a ship's hull is from its centre (its model's repair points, geo2dae.py; the Kuun-Lan with its modules)
CAT_REPAIR_SIZE = { smt_ms_sp = 600, smt_processor = 116, smt_rammingfrigate = 56, smt_worker = 27, smt_mimic = 11,
                    smt_acv = 9, smt_acolyte = 8, smt_scout = 6 }
CAT_REPAIR_TRACE = 1        -- TEST: log the ordered repair each second

function CatRepair_Tick(rec, g, id, now)
    local dt = now - (rec.repLast or now)
    rec.repLast = now
    if not rec.up.REPAIR or SobGroup_IsDoingAbility(g, AB_Repair) ~= 1 then
        rec.repT, rec.repIdle = nil, nil
        CatRepair_Cone(rec, g, nil, now)
        return
    end
    local busy = nil
    if rec.t == "smt_processor" then
        -- its side beams heal (CatProcessor_Tick); the order only turns its side to the target
        for i = 1, 4 do
            if rec.beams and rec.beams[i] then busy = 1 end
        end
    else
        -- HWRM keeps the order's target to itself (SobGroup_GetCommandTargets: nothing for COMMAND_Repair or any
        -- other order), but its order parks the Worker beside it: the beam takes the nearest damaged friendly ship
        -- within range
        local t = rec.repT
        if t and not CatRepair_InWorkerBeam(rec, g, id, t) then t = nil end
        if not t or now >= (rec.repScan or 0) then
            rec.repScan = now + CAT_TICK
            local best
            for k, _ in CatShips do
                local score = CatRepair_InWorkerBeam(rec, g, id, k)
                if score and (not best or score > best) then t, best = k, score end
            end
        end
        rec.repT = t
        CatRepair_Cone(rec, g, t, now)
        if t then
            busy = 1
            local tg = CatShips[t].g
            if dt > 0 then
                local rate = CAT_PROC_RATE
                if CatShips[t].t == "smt_ms_sp" then rate = 35 end
                local h = SobGroup_HealthPercentage(tg) + rate * dt / SobGroup_MaxHealthTotal(tg)
                if h > 1 then h = 1 end
                SobGroup_SetHealth(tg, h)
            end
        end
    end
    if CAT_REPAIR_TRACE == 1 and now >= (rec.repTrace or 0) then
        rec.repTrace = now + 1
        print("CATACLYSM repair " .. id .. " (" .. rec.t .. "): healing " .. (rec.repT or "none") .. ", busy " ..
              (busy or 0) .. ", speed " .. SobGroup_GetActualSpeed(g))
    end
end

-- the Worker's look while it heals: its jack out and the static repair cone from the tip (smt_worker.madstate
-- NIS02 jack out, DockPathOpen2 cone on once it is out, DockPathOpen1 cone off and jack back), not a beam to the target (user: the beam is just the mechanic)
function CatRepair_Cone(rec, g, on, now)
    if on and not rec.repCone then
        SobGroup_SetMadState(g, "NIS02")                 -- jack out
        rec.repCone = now
    elseif on and rec.repCone ~= 1 and now - rec.repCone >= CAT_JACK_OUT then
        SobGroup_SetMadState(g, "DockPathOpen2")         -- the boom is out: cone on
        rec.repCone = 1
    elseif not on and rec.repCone then
        SobGroup_SetMadState(g, "DockPathOpen1")         -- cone off, jack back
        rec.repCone = nil
    end
end

-- a damaged friendly ship within the Worker's beam range: its score, higher for nearer. No cone: HWRM's order
-- parks the Worker beside its target in no particular heading (user: with Cataclysm's 120 degree cone it only
-- repaired facing away or from below), so the nearest damaged friendly, normally the order's target, is healed.
function CatRepair_InWorkerBeam(rec, g, id, t)
    local trec = CatShips[t]
    if t == id or not trec or trec.gone or trec.p ~= rec.p or SobGroup_Empty(trec.g) == 1 then return nil end
    if SobGroup_HealthPercentage(trec.g) >= 0.999 then return nil end
    local pos = SobGroup_GetPosition(g)
    local tp = SobGroup_GetPosition(trec.g)
    local v = { tp[1] - pos[1], tp[2] - pos[2], tp[3] - pos[3] }
    local dist = sqrt(v[1] * v[1] + v[2] * v[2] + v[3] * v[3])
    local reach = CAT_WORKER_TIP_OFF + CAT_WORKER_REACH + (CAT_REPAIR_SIZE[trec.t] or 20)
    if dist > reach then return nil end
    return reach - dist
end

-- The Processor's automatic repair beams (Cataclysm FUN_005bedd0 / 005beae0, tweak.script twProcessorAutoRepair*):
-- once it has the Repair upgrade, each of its four beams (dock points Repair0-3: two each side, straight out) holds
-- one damaged friendly ship within the beam's range and cone and heals it at twRepairRate per second; a beam drops
-- a ship that is healed or leaves it and looks for the nearest other. (An ordered repair: its RepairCommand,
-- install_cr.py patch_processor.)
CAT_PROC_RANGE = 1400       -- twProcessorAutoRepairDistance 4000 (x 0.35: ship scale)
CAT_PROC_CONE = 0.7071      -- cos(twProcessorAutoRepairConeAngle 90 / 2)
CAT_PROC_RATE = 30          -- twRepairRate (35 for the capital classes: the Kuun-Lan here)
CAT_PROC_TRACE = 0          -- 1: log each heal step
CAT_PROC_BEAMS = {          -- origin (HWRM units, our model) and side (x direction) of Repair0-3 (sprocessor.mex)
    { -97.7, 25.4, -78.1, -1 }, { -106.7, -28.0, 6.3, -1 }, { 106.7, -28.0, 6.3, 1 }, { 97.7, 25.4, -78.1, 1 } }

-- The beam cones (tools/make_procbeam.py: the cone on each beam's turret joints, aimed by smt_processor.madstate).
-- The turrets move like a stock ion turret (kus_destroyerion1: AnimatedTurret, 35 degrees a second in yaw, 20 in
-- pitch, 10 % of that when pointing at the target; user: copy the destroyer's ion turret): this script turns each
-- turret's angles toward the target's current position at those rates, slowing as it closes in, and sends its
-- angle on every update; the madstate poses the clip at it (letting the clip play toward the angle lagged seconds
-- behind in game: the engine plays the clips slower than their times say). A message: beam (2 bits), band (2), yaw (8), pitch (8), each bit a switch to one of the two
-- of NIS00-02 the madstate is not in (it can't read this script's globals).
CAT_PROC_BANDS = { 500, 950, 1400 }   -- the cone's lengths (make_procbeam.py BANDS): the shortest that reaches
CAT_PROC_LEVELS = 255                 -- yaw / pitch steps over -45..45 degrees (8 bits each)
CAT_PROC_AIM_TRACE = 0                -- 1: log each message
CAT_PROC_CALIBRATE = 0                -- 1: fixed poses to read the turret's signs off in game (CatProcessor_Tick)
CAT_PROC_BEAM_DELAY = 1.0             -- seconds after a beam takes a target before its cone shows
CAT_PROC_AIM_EVERY = 0                -- seconds between a turret's messages while it turns (0: every update)
CAT_PROC_YAW_SPEED = 35               -- degrees a second (kus_destroyerion1 maxAzimuthSpeed; make_procbeam.py)
CAT_PROC_PITCH_SPEED = 20             -- (maxDeclinationSpeed)
CAT_PROC_FINE = 0.1                   -- speedMultiplierWhenPointingAtTarget
CAT_PROC_FINE_ANGLE = 5               -- degrees off the target below which the turret eases to the fine rate

-- one axis of a turret: its new angle, turned toward want at speed (easing to the fine rate near it)
function CatProcBeam_Turn(cur, want, speed, dt)
    local e = want - cur
    local ae = abs(e)
    if ae < 0.01 then return want end
    local k = ae / CAT_PROC_FINE_ANGLE
    if k < CAT_PROC_FINE then k = CAT_PROC_FINE elseif k > 1 then k = 1 end
    local step = speed * k * dt
    if step > ae then step = ae end
    if e < 0 then step = -step end
    return cur + step
end

function CatProcBeam_Aim(rec, g, i, t, o, r, u, f, now, dt)
    rec.tur = rec.tur or {}
    local tu = rec.tur[i]
    if not tu then
        tu = { yaw = 0, pitch = 0 }
        rec.tur[i] = tu
    end
    local band, wy, wp = 0, 0, 0                         -- no target: back to rest, cone off
    if t then
        if tu.t ~= t then tu.t, tu.since = t, now end
        local tp = SobGroup_GetPosition(CatShips[t].g)
        local v = { tp[1] - o[1], tp[2] - o[2], tp[3] - o[3] }
        local vx = v[1] * r[1] + v[2] * r[2] + v[3] * r[3]
        local vy = v[1] * u[1] + v[2] * u[2] + v[3] * u[3]
        local vz = v[1] * f[1] + v[2] * f[2] + v[3] * f[3]
        local n = sqrt(vx * vx + vy * vy + vz * vz)
        if n > 1 then
            -- the beam's own frame (geo2dae --turret: _Base turned 90 x side degrees about up, +Z out of its side):
            -- direction = Ry(yaw) Rx(pitch) +Z, standard right-handed rotations, the cone mesh along +Z. Confirmed by
            -- a calibration (CAT_PROC_CALIBRATE, screenshots 2026-10-10: built along -Z the cones rested pointing
            -- into the hull, yaw +40 on Beam1 swung it aft, pitch +40 on Beam2 up). Lua 4 trig is in degrees
            local side = CAT_PROC_BEAMS[i][4]
            local lx, ly, lz = -side * vz, vy, side * vx
            wy = atan2(lx, lz)
            wp = asin(-ly / n)
            if wy > 45 then wy = 45 elseif wy < -45 then wy = -45 end
            if wp > 45 then wp = 45 elseif wp < -45 then wp = -45 end
            band = 3
            if n <= CAT_PROC_BANDS[1] then band = 1 elseif n <= CAT_PROC_BANDS[2] then band = 2 end
            if now - tu.since < CAT_PROC_BEAM_DELAY then band = 0 end   -- the cone shows a second after the beam starts
            if CAT_PROC_AIM_TRACE == 1 then
                rec.aimWhy = "target " .. t .. " side " .. side .. " v(r,u,f) " .. floor(vx) .. "," .. floor(vy) .. "," ..
                             floor(vz) .. " want " .. floor(wy) .. "," .. floor(wp)
            end
        end
    else
        tu.t = nil
    end
    tu.yaw = CatProcBeam_Turn(tu.yaw, wy, CAT_PROC_YAW_SPEED, dt)
    tu.pitch = CatProcBeam_Turn(tu.pitch, wp, CAT_PROC_PITCH_SPEED, dt)
    local yq, pq = CatProcBeam_Level(tu.yaw), CatProcBeam_Level(tu.pitch)
    rec.aim = rec.aim or {}
    local last = rec.aim[i]
    if last then
        if last[1] == band and last[2] == yq and last[3] == pq then return end
        if last[1] == band and now - last[4] < CAT_PROC_AIM_EVERY then return end
    end
    rec.aim[i] = { band, yq, pq, now }
    CatProcBeam_Send(rec, g, i - 1, band, yq, pq)
end

-- one beam's message (beam 0-3, band, yaw / pitch steps) to the madstate
function CatProcBeam_Send(rec, g, beam, band, yq, pq)
    local bits = {}
    CatProcBeam_Bits(bits, beam, 2)
    CatProcBeam_Bits(bits, band, 2)
    CatProcBeam_Bits(bits, yq, 8)
    CatProcBeam_Bits(bits, pq, 8)
    if not rec.madSym then                               -- first: a sync switch (no bit)
        rec.madSym = 0
        SobGroup_SetMadState(g, "NIS00")
    end
    for k = 1, getn(bits) do
        local sym = rec.madSym + 1 + bits[k]
        if sym >= 3 then sym = sym - 3 end
        rec.madSym = sym
        SobGroup_SetMadState(g, "NIS0" .. sym)
    end
    if CAT_PROC_AIM_TRACE == 1 then
        print("CATACLYSM procbeam send beam " .. beam .. ": band " .. band .. ", yaw " .. yq .. ", pitch " .. pq ..
              " (" .. (rec.aimWhy or "") .. ")")
        rec.aimWhy = nil
    end
end

function CatProcBeam_Level(a)
    local q = floor((a + 45) / 90 * CAT_PROC_LEVELS + 0.5)
    if q < 0 then q = 0 elseif q > CAT_PROC_LEVELS then q = CAT_PROC_LEVELS end
    return q
end

function CatProcBeam_Bits(bits, v, count)
    for k = count - 1, 0, -1 do
        local p = 1
        for j = 1, k do p = p * 2 end
        if v >= p then
            tinsert(bits, 1)
            v = v - p
        else
            tinsert(bits, 0)
        end
    end
end

function CatProcessor_InBeam(t, o, d, p, me, ordered)
    local trec = CatShips[t]
    if t == me or not trec or trec.gone or trec.p ~= p or SobGroup_Empty(trec.g) == 1 then return nil end
    if SobGroup_HealthPercentage(trec.g) >= 0.999 then return nil end
    local tp = SobGroup_GetPosition(trec.g)
    local v = { tp[1] - o[1], tp[2] - o[2], tp[3] - o[3] }
    local dist = sqrt(v[1] * v[1] + v[2] * v[2] + v[3] * v[3])
    if dist > CAT_PROC_RANGE or dist < 1 then return nil end
    if not (ordered and ordered[t]) and (v[1] * d[1] + v[2] * d[2] + v[3] * d[3]) / dist < CAT_PROC_CONE then
        return nil                                   -- (an ordered target: range only; HWRM's order parks it)
    end
    return dist
end

function CatProcessor_Tick(rec, g, id, now)
    local dt = now - (rec.procLast or now)
    rec.procLast = now
    if CAT_PROC_CALIBRATE == 1 then
        -- TEST: fixed poses to read the turret's signs off in game. Beam0 (REPAIR0, upper rear, -X side) at rest,
        -- Beam1 (lower front, -X) yawed +40, Beam2 (lower front, +X) pitched +40, Beam3 (upper rear, +X) at rest, short
        if not rec.calSent and now > (rec.calAt or 0) then
            if not rec.calAt then rec.calAt = now + 3 return end
            rec.calSent = 1
            local z, y40 = CatProcBeam_Level(0), CatProcBeam_Level(40)
            CatProcBeam_Send(rec, g, 0, 3, z, z)
            CatProcBeam_Send(rec, g, 1, 3, y40, z)
            CatProcBeam_Send(rec, g, 2, 3, z, y40)
            CatProcBeam_Send(rec, g, 3, 1, z, z)
        end
        return
    end
    if not rec.up.REPAIR then return end
    local m = SobGroup_GetCoordSys(g)
    if getn(m) ~= 9 then return end
    local pos = SobGroup_GetPosition(g)
    local r, u, f = CatCol(m, 0), CatCol(m, 1), CatCol(m, 2)
    rec.beams = rec.beams or {}
    local scan = now >= (rec.procScan or 0)
    if scan then rec.procScan = now + CAT_TICK end
    local taken = {}
    for i = 1, 4 do
        if rec.beams[i] then taken[rec.beams[i]] = 1 end
    end
    for i = 1, 4 do
        local b = CAT_PROC_BEAMS[i]
        local o = { pos[1] + r[1] * b[1] + u[1] * b[2] + f[1] * b[3], pos[2] + r[2] * b[1] + u[2] * b[2] + f[2] * b[3],
                    pos[3] + r[3] * b[1] + u[3] * b[2] + f[3] * b[3] }
        local d = { r[1] * b[4], r[2] * b[4], r[3] * b[4] }
        local t = rec.beams[i]
        if t and not CatProcessor_InBeam(t, o, d, rec.p, id) then
            taken[t], t = nil, nil
        end
        if not t and scan then                       -- the nearest damaged friendly in this beam
            local best
            for k, _ in CatShips do
                if not taken[k] then
                    local dist = CatProcessor_InBeam(k, o, d, rec.p, id)
                    if dist and (not best or dist < best) then t, best = k, dist end
                end
            end
            if t then
                taken[t] = 1
                print("CATACLYSM processor " .. id .. ": beam " .. i .. " repairs ship " .. t .. " (" .. CatShips[t].real .. ")")
            end
        end
        rec.beams[i] = t
        if t and dt > 0 then
            local tg = CatShips[t].g
            local rate = CAT_PROC_RATE
            if CatShips[t].t == "smt_ms_sp" then rate = 35 end
            local h0, mx = SobGroup_HealthPercentage(tg), SobGroup_MaxHealthTotal(tg)
            local h = h0 + rate * dt / mx
            if h > 1 then h = 1 end
            SobGroup_SetHealth(tg, h)
            if CAT_PROC_TRACE == 1 then
                print("CATACLYSM processor " .. id .. ": beam " .. i .. " ship " .. t .. " health " .. h0 .. " -> " .. h ..
                      " (max " .. mx .. ", dt " .. dt .. ") now " .. SobGroup_HealthPercentage(tg))
            end
        end
        CatProcBeam_Aim(rec, g, i, t, o, r, u, f, now, dt)   -- after the heal
    end
end

function CatUnlink_Start(g, p, id)
    local rec = CatShips[id]
    if not rec or rec.gone or SobGroup_Empty(g) == 1 then return end
    CatSay(157, g, p)                                  -- "Roger, breaking link."
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
    local m = SobGroup_GetCoordSys(g)
    local up = { 0, 1, 0 }
    if getn(m) == 9 then up = CatUpAxis(m) else m = nil end
    local hold = Universe_GameTime() + CAT_UNLINK_ANIM
    for k = 1, 2 do
        local s = (3 - k * 2) * CAT_LINK_OFFSET          -- the first above, the second (rolled) below
        local at = { pos[1] + up[1] * s, pos[2] + up[2] * s, pos[3] + up[3] * s }
        -- both upright, the lower one's model shown rolled (UnlinkB), turning upright at the end
        local new = CatSpawn(p, CatVariant_ForNew(p, "smt_acolyte"), at, kills[k], nil, hold,
                             m and { pos = at, xf = m, t = hold })   -- pinned until the clips have played
        if m then CatPlace(new, at, m) end
        SobGroup_SetHealth(new, health)
        SobGroup_SetMadState(new, (k == 1 and "NIS01") or "DockPathOpen4")
    end
    rec.gone = 1
    SobGroup_Despawn(g)
    print("CATACLYSM link: ACV unlinked into two Acolytes")
end
