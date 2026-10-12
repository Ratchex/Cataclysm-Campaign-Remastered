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
