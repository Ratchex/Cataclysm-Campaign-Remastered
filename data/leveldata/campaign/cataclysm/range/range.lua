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

-- TEST (user: weaker weapon copies for Mission01's 10 % teams): do ion beams fire at 10 % WEAPON damage? The normal
-- Taiidan ion frigate fires at our Processor, its 10 % copy (tai_ioncannonfrigate_d10, tools/make_variants.py) at our
-- Ramming Frigate; each target's loss is logged every 5 s. (Found before: SobGroup_SetDamageMultiplier compounds and
-- stops beams below ~0.5.)
RANGE_BEAM_TEST = 1
RangeBeamStart = nil
RangeBeamLog = 0
RangeBeamHP = nil
function Range_BeamSay(text)
    print("CATACLYSM range beam test: " .. text)
    if Subtitle_Message then Subtitle_Message("BEAM TEST: " .. text, 6) end
end
function Range_BeamHP(g)
    return SobGroup_HealthPercentage(g) * SobGroup_MaxHealthTotal(g)
end
function Range_BeamTest()
    local t = Universe_GameTime()
    if RangeBeamStart == nil then
        RangeBeamStart = t
        SobGroup_CreateIfNotExist("TestTargetA")
        SobGroup_CreateIfNotExist("TestTargetB")
        SobGroup_FillShipsByType("TestTargetA", "Player_Ships0", "smt_processor")
        SobGroup_FillShipsByType("TestTargetB", "Player_Ships0", "smt_rammingfrigate")
    end
    local s = t - RangeBeamStart
    if s < 15 then return end
    local a, b = Range_BeamHP("TestTargetA"), Range_BeamHP("TestTargetB")
    if RangeBeamHP == nil then
        RangeBeamHP = { a, b }
        RangeBeamLog = s + 5
        SobGroup_Attack(1, "TargetIon", "TestTargetA")
        SobGroup_Attack(1, "TargetIon10", "TestTargetB")
        Range_BeamSay("normal ion frigate on the Processor, its 10% copy (to its right) on the Ramming Frigate")
        return
    end
    if s >= RangeBeamLog then
        RangeBeamLog = s + 5
        print("CATACLYSM range beam test: t+" .. floor(s) .. " Processor lost " .. floor(RangeBeamHP[1] - a) ..
              ", Ramming Frigate lost " .. floor(RangeBeamHP[2] - b) .. " in 5 s")
        RangeBeamHP = { a, b }
    end
    if s >= 90 then
        Range_BeamSay("done")
        Rule_Remove("Range_BeamTest")
    end
end
