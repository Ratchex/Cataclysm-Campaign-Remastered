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

RANGE_GRANT_ALL = 1      -- 1: every Cataclysm tech researched at the start, the placed ships upgraded with it;
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
    if RANGE_GRANT_ALL == 1 then Rule_AddInterval("Range_Upgrade", 2) end
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

-- the ships placed with the level were created before the research: upgrade them (kasfShipsUpgrade)
function Range_Upgrade()
    Rule_Remove("Range_Upgrade")
    K_498c70("Player_Ships0")
    print("CATACLYSM range: placed ships upgraded")
end
