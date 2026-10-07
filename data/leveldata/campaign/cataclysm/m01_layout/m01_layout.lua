-- Phase 0.2 check: Cataclysm Mission01's converted layout with no mission logic. Somtaaw/Beast/etc. ships are
-- Kus_Scout placeholders; the player gets a stand-in mothership at StartPointPlayer.
dofilepath("data:scripts/SCAR/SCAR_Util.lua")

function OnStartOrLoad()
    print("CATACLYSM m01_layout: OnStartOrLoad")
end

AllGroups = {
    "FleetIntel",
    "Objectives",
    "KushanFlankFrigates",
    "TaiidanBombers",
    "TaiidanCarrier",
    "TaiidanResourcers",
    "TaiidanCarrierDefense",
    "TaiidanResourcerDefense",
    "KushanMainGuardFrigates",
    "KushanMainGuardCorvettes",
    "TaiHInt1",
    "KushanCarriers",
    "TaiidanMainCarrier",
    "TaiidanMissileDestroyers",
    "KushanMainGuardDestroyers",
    "KushanMainGuardFighters1",
    "TaiidanDestroyer",
    "TaiidanCarrier2",
    "TaiidanC2Interceptor1",
    "TaiidanC2Interceptor2",
    "TaiidanC2MGCorv1",
    "TaiidanPunishmentFrigate1",
    "TaiidanPunishmentFrigate2",
    "TaiidanPunishmentFrigate3",
    "TaiidanDefendCruiser",
    "TaiidanProxAttackAbomb1",
    "TaiidanProxAttackHInt1",
    "TaiICFrig1",
    "TaiidanProxAttackMGCorv1",
    "KushanProxDefend1",
    "KushanProxDefend2",
    "PesterHInt1",
    "TaiidanReinforcement1",
    "TaiidanHInt2",
    "Music",
    "KushanProximityArray",
}

function OnInit()
    print("CATACLYSM m01_layout: OnInit")
    -- layout check only: show every team through the fog of war
    for _, g in AllGroups do
        FOW_RevealGroup(g, 1)
    end
    Rule_AddInterval("Rule_Report", 2)
end

function Rule_Report()
    for _, g in { "KushanFlankFrigates", "TaiidanBombers", "TaiidanCarrier", "TaiidanMainCarrier", "KushanProximityArray" } do
        print("CATACLYSM m01_layout: group " .. g .. " = " .. SobGroup_Count(g))
    end
    Rule_Remove("Rule_Report")
end
