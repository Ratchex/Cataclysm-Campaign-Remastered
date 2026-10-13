-- Unit test range: Somtaaw ships and systems tried out away from the missions (hand-written; level: range.level).
-- The Cataclysm runtime (cataclysmkas.lua: ability buttons, upgrades, RU trickle, research) runs as in the missions,
-- without a mission script. Switches below; this script reloads on going back to the menu.

dofilepath("data:scripts/SCAR/SCAR_Util.lua")
dofilepath("data:scripts/SCAR/KASUtil.lua")
dofilepath("data:scripts/SCAR/SinglePlayerFlow.lua")
dofilepath("data:scripts/SCAR/SinglePlayerNIS.lua")
dofilepath("data:scripts/SCAR/SinglePlayerHyperspace.lua")
dofilepath("data:scripts/SCAR/SpecialFlags.lua")
dofilepath("data:scripts/scar/cataclysmkas_stubs.lua")
dofilepath("data:scripts/scar/cataclysmkas.lua")
dofilepath("data:scripts/scar/cataclysmspeech.lua")
dofilepath("data:scripts/scar/cataclysmships.lua")
dofilepath("data:scripts/scar/cataclysmtech.lua")

RANGE_GRANT_ALL = 0      -- 1: every Cataclysm tech researched at the start, the placed ships upgraded with it;
                         -- 0: every tech researchable, none done (to test researching and upgrading)

-- every module the player can have (tools/make_modules.py), so all research and building is possible
KAS_StartModules = { "smt_kl_dockingbay", "smt_kl_engineslower", "smt_kl_enginesupper", "smt_kl_lowerspine",
                     "smt_kl_orecanarmour", "smt_kl_weapons", "smt_kl_armour", "smt_kl_micro", "smt_kl_special" }

function OnStartOrLoad()
    print("CATACLYSM range: OnStartOrLoad")
    Sound_SpeechSubtitlePath(KAS_SpeechPath)
end

function OnInit()
    print("CATACLYSM range: OnInit, grant all " .. RANGE_GRANT_ALL)
    KAS_StartEngine()
    KAS_CreateStartModules()
    local i = 1
    while i <= getn(KAS_Techs) do
        Player_UnrestrictResearchOption(0, KAS_Techs[i])
        if RANGE_GRANT_ALL == 1 then Player_GrantResearchOption(0, KAS_Techs[i]) end
        i = i + 1
    end
    Camera_Interpolate("here", "Camera_Startpos", 0)
    Rule_AddInterval("Range_CoordSys", 1)
    Rule_AddInterval("Range_Damage", 2)
    if RANGE_GRANT_ALL == 1 then Rule_AddInterval("Range_Upgrade", 2) end
    if RANGE_BEAM_TEST == 1 then Rule_AddInterval("Range_BeamTest", 1) end
    if RANGE_CRUISER_TEST == 1 then Rule_AddInterval("Range_Cruiser", 1) end
end

-- SobGroup_GetCoordSys's layout: its 9 numbers beside the engine's own columns, for the tilted Recon
function Range_CoordSys()
    Rule_Remove("Range_CoordSys")
    local m = SobGroup_GetCoordSys("Recon")
    local s = "CATACLYSM range: Recon coordsys"
    for i = 1, getn(m) do s = s .. " " .. m[i] end
    for c = 0, 2 do
        local v = Matrix3_GetVector3FromCol(m, c)
        s = s .. " | col" .. c .. " " .. v[1] .. " " .. v[2] .. " " .. v[3]
    end
    print(s)
end

-- the Workers at half health: something for the repair beams to heal
function Range_Damage()
    Rule_Remove("Range_Damage")
    SobGroup_SetHealth("Workers", 0.5)
    print("CATACLYSM range: Workers at half health")
end

-- the ships placed with the level were created before the research: upgrade them (kasfShipsUpgrade)
function Range_Upgrade()
    Rule_Remove("Range_Upgrade")
    K_498c70("Player_Ships0")
    print("CATACLYSM range: placed ships upgraded")
end

-- TEST (user): the damage multiplier stepped down 0.1 at a time, where do ion beams cut out? The normal Taiidan ion
-- frigate fires at our Processor from 15 s; every RANGE_STEP s its multiplier goes 1.0, 0.9 ... 0.1 (set as the ratio
-- to the last: SobGroup_SetDamageMultiplier compounds), each step on screen and logged with the Processor's loss.
RANGE_BEAM_TEST = 0           -- done: beams fire at 0.5, cut out at 0.4 (user, 2026-10-12)
RANGE_STEP = 20
RangeBeamStart = nil
RangeBeamMult = 1
RangeBeamNext = 0
RangeBeamHP = nil
function Range_BeamSay(text)
    print("CATACLYSM range beam test: " .. text)
    if Subtitle_Message then Subtitle_Message("BEAM TEST: " .. text, 8) end
end
function Range_BeamTest()
    local t = Universe_GameTime()
    if RangeBeamStart == nil then
        RangeBeamStart = t
        SobGroup_CreateIfNotExist("TestTarget")
        SobGroup_FillShipsByType("TestTarget", "Player_Ships0", "smt_processor")
    end
    local s = t - RangeBeamStart
    if s < 15 then return end
    local hp = SobGroup_HealthPercentage("TestTarget") * SobGroup_MaxHealthTotal("TestTarget")
    if RangeBeamHP == nil then
        RangeBeamHP, RangeBeamNext = hp, s + RANGE_STEP
        SobGroup_Attack(1, "TargetIon", "TestTarget")
        Range_BeamSay("ion frigate attacking the Processor, multiplier 1.0")
        return
    end
    if s >= RangeBeamNext then
        print("CATACLYSM range beam test: at multiplier " .. RangeBeamMult .. " the Processor lost " ..
              floor(RangeBeamHP - hp) .. " in " .. RANGE_STEP .. " s")
        RangeBeamHP, RangeBeamNext = hp, s + RANGE_STEP
        local new = floor(RangeBeamMult * 10 - 1 + 0.5) / 10
        if new < 0.1 then
            Range_BeamSay("done")
            Rule_Remove("Range_BeamTest")
            return
        end
        SobGroup_SetDamageMultiplier("TargetIon", new / RangeBeamMult)
        RangeBeamMult = new
        SobGroup_Attack(1, "TargetIon", "TestTarget")
        Range_BeamSay("multiplier now " .. new)
    end
end

-- Mission01's crippled heavy cruiser: its turrets track slowly and snap, its ion cannons not at all (user). The right
-- one is held at 20 % health as Mission01 does (kasfTeamSetPercentDamaged(20) whenever its whole-number average is over
-- 20: it regenerates, Cataclysm's repair factor 0 has no HWRM equivalent), the left one left whole. Approach both.
RANGE_CRUISER_TEST = 0       -- (done: firing while moving, cataclysmkas.lua KAS_MoveFireTick)
-- then what only Mission01 does to it once it is the objective, one at a time (side turrets slow and snapping there):
-- 1 = its damage factor 50 % (kasfShipsSetDamageFactor: cataclysmkas.lua K_493980's groups, the ship rules make it a
-- x5 damage multiplier on the 10 % copy; ruled out, user); 2 = and its flight, kasfPatrolPath on an open path
-- (cataclysmkas.lua K_4929d0: move orders point to point, back and forth), away from the Kuun-Lan (the cause, user);
-- 3 = and Offensive ROE (0) instead of the runtime's Defensive (1, every 5 s: KAS_TeamsDefensive), re-set each second
-- (no change, user); 4 = the flight as Gearbox's patrols, SobGroup_FollowPath (an attack-move) on a level path, in place
-- of the move orders (Defensive again; no change, user); 5 = the sound cruiser flies the same way beside it (control:
-- do moving cruisers track badly anyway, or only the crippled one? Anyway, user); 6 = the crippled one first attacks
-- the player's ships for 8 s (a ship in combat turns later moves into "firing while moving", user's own destroyer),
-- then flees with the move orders (step 2; still snapping, user); 7 = the same, fleeing with FollowPath (an attack-move;
-- still snapping); 8 = a move given while an attack is the ship's current command keeps the attack and moves it
-- (HWRM FUN_006808df: "firing while moving"): each second with players near, attack them, and a second later move on
-- along the flight (current order logged; turrets and flight correct, user); 9 = steps 1-2 again, the flight by the
-- runtime's patrol, which now does step 8 itself (cataclysmkas.lua KAS_MoveFireTick)
RANGE_CRUISER_STEP = 9
function Range_Cruiser()
    if SobGroup_Count("TargetCruiserCrippled") == 0 then return end
    if RANGE_CRUISER_STEP >= 1 and RangeCruiserDmgf == nil then
        RangeCruiserDmgf = 1
        KAS_Team = "TargetCruiserCrippled"
        K_493980("TargetCruiserCrippled", 50)
        print("CATACLYSM range: crippled cruiser: damage factor 50")
    end
    if RANGE_CRUISER_STEP == 8 then
        Range_CruiserMoveAttack()
        return
    end
        if RANGE_CRUISER_STEP >= 6 and RANGE_CRUISER_STEP <= 7 and RangeCruiserFlee == nil then
        SobGroup_CreateIfNotExist("RangeNear")
        SobGroup_Clear("RangeNear")
        SobGroup_FillProximitySobGroup("RangeNear", "Player_Ships0", "TargetCruiserCrippled", 6000)
        if RangeCruiserEngage == nil and SobGroup_Count("RangeNear") == 0 then
            -- (waits for the player's ships within 6000)
        elseif RangeCruiserEngage == nil then
            RangeCruiserEngage = Universe_GameTime()
            SobGroup_Attack(1, "TargetCruiserCrippled", "Player_Ships0")
            print("CATACLYSM range: crippled cruiser: attacking for 8 s")
        elseif Universe_GameTime() - RangeCruiserEngage >= 8 then
            RangeCruiserFlee = 1
            KAS_Paths = KAS_Paths or {}
            KAS_Paths["RangeFlee"] = { {1500, 0, 12000}, {1500, 0, 24000}; closed = 0 }
            KAS_Team = "TargetCruiserCrippled"
            if RANGE_CRUISER_STEP >= 7 then
                SobGroup_FollowPath("TargetCruiserCrippled", "RangeFleePath", 1, 1, 0)
                print("CATACLYSM range: crippled cruiser: now fleeing with FollowPath")
            else
                K_4929d0("RangeFlee")
                print("CATACLYSM range: crippled cruiser: now fleeing with move orders")
            end
        end
    end
        if RANGE_CRUISER_STEP >= 4 and RANGE_CRUISER_STEP <= 7 and RangeCruiserFlee == nil then
        RangeCruiserFlee = 1
        SobGroup_FollowPath("TargetCruiserCrippled", "RangeFleePath", 1, 1, 0)
        print("CATACLYSM range: crippled cruiser: FollowPath RangeFleePath")
    end
    if RANGE_CRUISER_STEP >= 5 and RangeCruiserSoundFlee == nil then
        RangeCruiserSoundFlee = 1
        SobGroup_FollowPath("TargetCruiserSound", "RangeFleeSoundPath", 1, 1, 0)
        print("CATACLYSM range: sound cruiser: FollowPath RangeFleeSoundPath")
    end
    if RANGE_CRUISER_STEP >= 5 and RangeDestroyerFlee == nil and SobGroup_Count("TargetDestroyer") > 0 then
        RangeDestroyerFlee = 1
        SobGroup_FollowPath("TargetDestroyer", "RangeFleeDestroyerPath", 1, 1, 0)
        print("CATACLYSM range: Kushan destroyer: FollowPath RangeFleeDestroyerPath")
    end
        if RANGE_CRUISER_STEP >= 2 and RangeCruiserFlee == nil then
        RangeCruiserFlee = 1
        KAS_Paths = KAS_Paths or {}
        KAS_Paths["RangeFlee"] = { {1500, 0, 12000}, {1500, 0, 24000}; closed = 0 }
        KAS_Team = "TargetCruiserCrippled"
        K_4929d0("RangeFlee")
        print("CATACLYSM range: crippled cruiser: fleeing along RangeFlee")
    end
    if RANGE_CRUISER_STEP == 3 then SobGroup_SetROE("TargetCruiserCrippled", 0) end
    local h = floor(SobGroup_HealthPercentage("TargetCruiserCrippled") * 100)
    if h > 20 then
        SobGroup_SetHealth("TargetCruiserCrippled", 0.2)
        print("CATACLYSM range: crippled cruiser " .. h .. "% -> 20%")
    end
end

RangeMA = { phase = "attack", leg = 2 }
RangeMAPoints = { {1500, 0, 12000}, {1500, 0, 24000} }
function Range_CruiserMoveAttack()
    local g = "TargetCruiserCrippled"
    SobGroup_CreateIfNotExist("RangeNear")
    SobGroup_Clear("RangeNear")
    SobGroup_FillProximitySobGroup("RangeNear", "Player_Ships0", g, 6000)
    local p, w = SobGroup_GetPosition(g), RangeMAPoints[RangeMA.leg]
    if sqrt((p[1] - w[1]) * (p[1] - w[1]) + (p[3] - w[3]) * (p[3] - w[3])) < 800 then
        RangeMA.leg = 3 - RangeMA.leg
        w = RangeMAPoints[RangeMA.leg]
    end
    local before = SobGroup_GetCurrentOrder(g)
    if SobGroup_Count("RangeNear") > 0 and RangeMA.phase == "attack" then
        SobGroup_Attack(1, g, "RangeNear")
        RangeMA.phase = "move"
    else
        SobGroup_MoveToPoint(1, g, w)
        RangeMA.phase = "attack"
    end
    print("CATACLYSM range: cruiser order " .. before .. " -> " .. RangeMA.phase .. " next (attack " .. COMMAND_Attack
          .. ", move " .. COMMAND_Move .. ", idle " .. COMMAND_Idle .. "), near " .. SobGroup_Count("RangeNear"))
end
