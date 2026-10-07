-- Phase 0.1 smoke test mission script. Loads the same HW1 emulation layer Gearbox's HW1 port uses.

dofilepath("data:scripts/SCAR/SCAR_Util.lua")
dofilepath("data:scripts/SCAR/KASUtil.lua")
dofilepath("data:scripts/SCAR/SinglePlayerFlow.lua")
dofilepath("data:scripts/SCAR/SinglePlayerNIS.lua")
dofilepath("data:scripts/SCAR/SinglePlayerHyperspace.lua")
dofilepath("data:scripts/SCAR/SpecialFlags.lua")

ObjectiveID_Test = 0

function OnStartOrLoad()
    print("CATACLYSM m00_test: OnStartOrLoad")
    -- Phase 0.4: speech files are looked up as <path><string id>.wav
    Sound_SpeechSubtitlePath("speech:missions/cataclysm/")
end

function OnInit()
    print("CATACLYSM m00_test: OnInit")
    Camera_Interpolate("here", "Camera_Startpos", 0)
    Rule_AddInterval("Rule_PostObjective", 3)
end

function Rule_PostObjective()
    print("CATACLYSM m00_test: rule fired, ships in Scouts = " .. SobGroup_Count("Scouts"))
    ObjectiveID_Test = Objective_Add("$2100000", OT_Primary)
    -- Phase 0.4 checks: a stock HWRM string (does Objective_Add localise at all?) and a speech line + subtitle
    Objective_Add("$3492", OT_Secondary)
    local t = Subtitle_AddSkippable(Actor_HW1_FleetIntel, "$2100001", 30)
    print("CATACLYSM m00_test: Subtitle_AddSkippable returned " .. t)
    Rule_Remove("Rule_PostObjective")
    Rule_AddInterval("Rule_CheckWin", 1)
end

function Rule_CheckWin()
    if SobGroup_Count("Enemies") == 0 then
        print("CATACLYSM m00_test: frigate destroyed")
        Objective_SetState(ObjectiveID_Test, OS_Complete)
        Rule_Remove("Rule_CheckWin")
    end
end
