"""Kuun-Lan modules as HW2 subsystems (Cataclysm Remastered's Kuun-Lan as the template), from Cataclysm's
smothership<module>.shp/.geo:
  data/subsystem/smt_kl_<key>/smt_kl_<key>.subs + .hod   the module on the Kuun-Lan (hardpoint HARDPOINTS[key])
  data/ship/smt_kl_<key>_dummy/...                       the same module as a loose ship: jettisoned modules, and
                                                         Cataclysm's sMothership<Module> ship types in levels/NIS
Models: tools/build_kuunlan.sh (core + modules, HODOR) into build/ships/. All modules share the Kuun-Lan's frame
(Cataclysm docks them at the origin; Support modules at SUPPORT1-12). Each non-Support module is recentred on its
hardpoint (HWRM draws its health bar there); its loose dummy keeps the shared frame.

What each module does (Cataclysm english.script str*ModuleInfo): research modules list their techs (TECH_MODULE,
used by make_race.py for RequiredSubSystems = the module's typeString); the Hangar is required to build ships;
Command Center and Resource Processing are part of the core model (CORE_PARTS: on the Kuun-Lan in every mission;
the core takes the Workers' drop-offs). Missions start with the modules their .mission includes
(build_mission.py -> KAS_StartModules); none are innate, as the story removes some (Lower Spine and Ore Canister
from Mission 4, Lower Engines from Mission 5).

Usage: make_modules.py   (after tools/build_kuunlan.sh)
"""
import os
import re
import shutil

DECOMP = r"C:\Modding\Cataclysm-decomp"
MOD = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SECT = os.path.join(DECOMP, "extracted", "big", "race_sect")
BUILD = os.path.join(MOD, "build", "ships")
HEALTH_SCALE = 5   # Cataclysm module hit points -> HWRM (Cataclysm Remastered's modules: 60000-90000); provisional

# key: (Cataclysm ship, displayed name, typeString, isResearch, buildable, required tech)
MODULES = {
    "engineslower": ("sMothershipEnginesLower", "Lower Engines", "LowerEngines", 0, False, ""),
    "enginesupper": ("sMothershipEnginesUpper", "Upper Engines", "UpperEngines", 0, False, ""),
    "lowerspine":   ("sMothershipLowerSpine", "Lower Spine", "LowerSpine", 0, False, ""),
    "orecanarmour": ("sMothershipOreCanArmour", "Ore Canister", "OreCanister", 0, False, ""),
    "dockingbay":   ("sMothershipDockingBay", "Hangar Module", "Hangar", 1, True, ""),
    "weapons":      ("sMothershipWeapons", "Weapons Module", "WeaponsModule", 1, True, ""),
    "armour":       ("sMothershipArmour", "Armor Module", "ArmourModule", 1, True, ""),
    "micro":        ("sMothershipMicro", "Engineering Module", "EngineeringModule", 1, True, ""),
    "special":      ("sMothershipSpecial", "Adv. Engineering Module", "AdvEngineeringModule", 1, True, ""),
    "support":      ("sMothershipSupport", "Support Module", "SupportModule", 0, True, "TECH_SUPPORT_SYSTEMS"),
    "biggun":       ("sMothershipBigGun", "Siege Cannon", "SiegeCannon", 0, True, "TECH_BIG_GUN"),
}

# Cataclysm sMothership<part> objects that are part of the core model, not modules (on the Kuun-Lan in every mission;
# merged into its mesh by tools/build_kuunlan.sh). Resource Processing was where Workers unload: the core does that.
CORE_PARTS = {"command": "sMothershipCommand", "engineering": "sMothershipEngineering"}

# hardpoint joints on the core (geo2dae.py --hardpoint specs; the Support model sits on the port side of the
# spine, its pair partner turned about Y). The others at their module's centre, where tools/build_kuunlan.sh
# recentred the module (geo2dae.py --origin auto -> origin.txt): HWRM draws a subsystem's health bar at its
# hardpoint (at the shared origin, every module's bar sat in the middle of the Kuun-Lan: user)
def _origin(key):
    p = os.path.join(BUILD, f"smt_kl_{key}", "origin.txt")
    return "@" + open(p).read().strip() if os.path.exists(p) else ""


HARDPOINTS = {k: [f"Hardpoint_KL_{k}" + _origin(k)] for k in MODULES if k != "support"}
HARDPOINTS["support"] = [f"Hardpoint_KL_support{n}@dok:SUPPORT{n}" + ("@flip" if n % 2 == 0 else "")
                         for n in range(1, 13)]

# research module of each tech (the module info texts in Cataclysm's english.script)
TECH_MODULE = {}
for _key, _techs in {
    "dockingbay": "DRIVE_FIGHTER ADRIVE_FIGHTER LINK DRIVE_FRIGATE ADRIVE_FRIGATE DRIVE_DESTROYER ADRIVE_DESTROYER",
    "armour": "ARMOUR2 ARMOUR3 FORCE_FIELD1 FORCE_FIELD2 FORCE_FIELD3",
    "micro": "SALVAGE MIMIC SUPPORT_SYSTEMS AFTERBURNER REPAIR INFECT",
    "special": "MICRO_SHIP REPAIRBOTS PHASED_TELEMETRY ADVANCED_SENSORS BEAST_VACCINE CRYSTAL_HARVEST",
    "weapons": "ION MISSILE BIG_GUN ENERGY EMP EXPLOSIVE_CHARGE REPULSE",
}.items():
    for _t in _techs.split():
        TECH_MODULE["TECH_" + _t] = _key


def subsystem(key):
    return f"smt_kl_{key}"


def joints(key):
    return [spec.split("@")[0] for spec in HARDPOINTS[key]]


def hardpoint_lines():
    """StartShipHardPointConfig lines for the Kuun-Lan .ship (after LoadModel): one slot per module, empty at
    spawn (missions create their modules), destroyable."""
    out = []
    for key in MODULES:
        for j in joints(key):
            label = MODULES[key][1] + (" " + j[len("Hardpoint_KL_support"):] if key == "support" else "")
            out.append(f'StartShipHardPointConfig(NewShipType,"{label}","{j}","System","Generic","Destroyable",'
                       f'"","{subsystem(key)}","","","","","","","");')
    return out


def shp(name):
    vals = {}
    for line in open(os.path.join(SECT, name.lower() + ".shp"), encoding="latin-1"):
        m = re.match(r"\s*(\w+)\s+([-\d.]+)", line.split(";")[0])
        if m:
            vals[m.group(1).lower()] = float(m.group(2))
    return vals


SUBS = """-- {name}: Cataclysm {cat} ({disp}), generated by tools/make_modules.py
NewSubSystemType=StartSubSystemConfig();
NewSubSystemType["displayedName"]="{disp}";
NewSubSystemType["sobDescription"]="{disp}";
NewSubSystemType["tacticalIcon"]="hexagon";
NewSubSystemType["tacticalIconMinSize"]=0.0035;
NewSubSystemType["tacticalIconMinFadeSize"]=0.0045;
NewSubSystemType["tacticalIconMaxFadeSize"]=0.008;
NewSubSystemType["groupMergeSize"]=0.001;
NewSubSystemType["mouseOverMinFadeSize"]=0.045;
NewSubSystemType["mouseOverMaxFadeSize"]=0.1;
NewSubSystemType["maxhealth"]={health};
NewSubSystemType["regentime"]=250;
NewSubSystemType["nlips"]=0;
NewSubSystemType["nlipsRange"]=0;
NewSubSystemType["nlipsFar"]=0;
NewSubSystemType["nlipsFarRange"]=0;
NewSubSystemType["meshRenderLimit"]=0.004;
NewSubSystemType["minimumZoomFactor"]=0.68;
NewSubSystemType["selectionLimit"]=5000;
NewSubSystemType["preciseATILimit"]=5000;
NewSubSystemType["selectionPriority"]=37.5;
NewSubSystemType["type"]="System";
NewSubSystemType["typeString"]="{type}";
NewSubSystemType["collateralDamage"]=100;
NewSubSystemType["inactiveTimeAfterDamage"]=10;
NewSubSystemType["activateHealthPercentage"]=0.1;
NewSubSystemType["costToBuild"]={cost};
NewSubSystemType["timeToBuild"]={time};
NewSubSystemType["isResearch"]={research};
NewSubSystemType["visible"]=1;
LoadHODFile(NewSubSystemType, 1);
NewSubSystemType["BuildFamily"]="SubSystem_Smt";
NewSubSystemType["AttackFamily"]="SubSystem";
NewSubSystemType["DockFamily"]="CantDock";
NewSubSystemType["DisplayFamily"]="SubSystemModule";
NewSubSystemType["ArmourFamily"]="SubSystemArmour";
{extra}"""

DUMMY = """-- {name}: Cataclysm {cat} ({disp}) as a loose ship (jettisoned modules; module ship types in levels/NIS),
-- generated by tools/make_modules.py. Origin = the Kuun-Lan's (Cataclysm modules share its frame).
NewShipType = StartShipConfig()
NewShipType.displayedName="{disp}"
NewShipType.sobDescription="{disp}"
NewShipType.maxhealth={health}
NewShipType.regentime=0
NewShipType.minRegenTime=0
NewShipType.sideArmourDamage=1
NewShipType.rearArmourDamage=1
NewShipType.isTransferable=0
NewShipType.defaultROE="Passive"
NewShipType.defaultStance="Passive"
NewShipType.mass=1000
NewShipType.collisionMultiplier=1
NewShipType.thrusterMaxSpeed=40
NewShipType.mainEngineMaxSpeed=40
NewShipType.rotationMaxSpeed=10
NewShipType.thrusterAccelTime=5
NewShipType.thrusterBrakeTime=5
NewShipType.mainEngineAccelTime=5
NewShipType.mainEngineBrakeTime=5
NewShipType.rotationAccelTime=1
NewShipType.rotationBrakeTime=1
NewShipType.thrusterUsage=1
NewShipType.accelerationAngle=40
NewShipType.mirrorAngle=0
NewShipType.secondaryTurnAngle=0
NewShipType.maxBankingAmount=0
NewShipType.descendPitch=0
NewShipType.goalReachEpsilon=50
NewShipType.slideMoveRange=0
NewShipType.controllerType="Ship"
NewShipType.tumbleStaticX=0
NewShipType.tumbleStaticY=0
NewShipType.tumbleStaticZ=0
NewShipType.tumbleDynamicX=0
NewShipType.tumbleDynamicY=0
NewShipType.tumbleDynamicZ=0
NewShipType.tumbleSpecialDynamicX=0
NewShipType.tumbleSpecialDynamicY=0
NewShipType.tumbleSpecialDynamicZ=0
NewShipType.relativeMoveFactor=1
NewShipType.swayUpdateTime=0
NewShipType.swayOffsetRandomX=0
NewShipType.swayOffsetRandomY=0
NewShipType.swayOffsetRandomZ=0
NewShipType.swayBobbingFactor=0
NewShipType.swayRotateFactor=0
NewShipType.dustCloudDamageTime=160
NewShipType.nebulaDamageTime=35
NewShipType.MinimalFamilyToFindPathAround="SuperCap"
NewShipType.BuildFamily="NonCombat_Smt"
NewShipType.AttackFamily="Utility"
NewShipType.DockFamily="CantDock"
NewShipType.AvoidanceFamily="Utility"
NewShipType.DisplayFamily="Utility"
NewShipType.AutoFormationFamily="SuperCap"
NewShipType.CollisionFamily="Big"
NewShipType.ArmourFamily="HeavyArmour"
NewShipType.AttackPriorityMultiplier=0.5
NewShipType.buildCost={cost}
NewShipType.buildTime={time}
NewShipType.buildPriorityOrder=10
NewShipType.retaliationRange=0
NewShipType.visualRange=1000
NewShipType.prmSensorRange=1000
NewShipType.secSensorRange=1000
NewShipType.detectionStrength=1
NewShipType.TOIcon="Square"
NewShipType.TOScale=1
NewShipType.TODistanceFade0=9000
NewShipType.TODistanceDisappear0=7000
NewShipType.TODistanceFade1=4500
NewShipType.TODistanceDisappear1=3500
NewShipType.TODistanceFade2=12000
NewShipType.TODistanceDisappear2=35000
NewShipType.TOGroupScale=1
NewShipType.TOGroupMergeSize=0
NewShipType.mouseOverMinFadeSize=0.045
NewShipType.mouseOverMaxFadeSize=0.1
NewShipType.healthBarStyle=1
NewShipType.nlips=0
NewShipType.nlipsRange=0
NewShipType.nlipsFar=0
NewShipType.nlipsFarRange=0
NewShipType.SMRepresentation="HardDot"
NewShipType.meshRenderLimit=13000
NewShipType.dotRenderLimit=10
NewShipType.visibleInSecondary=1
NewShipType.minLOD=1
NewShipType.minimumZoomFactor=0.75
NewShipType.selectionLimit=150000
NewShipType.preciseATILimit=0
NewShipType.selectionPriority=50
NewShipType.militaryUnit=0
addAbility(NewShipType,"MoveCommand",1,0);
LoadModel(NewShipType,1);
NewShipType.battleScarCoverage=2
NewShipType.sobDieTime=2
NewShipType.sobSpecialDieTime=2
NewShipType.specialDeathSpeed=40
NewShipType.chanceOfSpecialDeath=0
NewShipType.deadSobFadeTime=1
"""


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="latin-1", newline="\n") as f:
        f.write(text)


def main():
    for key, (cat, disp, typ, research, _, _) in MODULES.items():
        v = shp(cat)
        hod = os.path.join(BUILD, subsystem(key), subsystem(key) + ".hod")
        name = subsystem(key)
        fields = dict(name=name, cat=cat, disp=disp, type=typ, research=research,
                      health=int(v.get("maxhealth", 5000) * HEALTH_SCALE), cost=int(v.get("buildcost", 1000)),
                      time=int(v.get("buildtime", 60)))
        extra = ('AddSubSystemMultiplier(NewSubSystemType, "ResourceDropOffRate", "ThisShipOnly", "Linear", 1, 0, 0);\n'
                 if typ == "Resourcing" else "")
        write(os.path.join(MOD, "data", "subsystem", name, name + ".subs"), SUBS.format(extra=extra, **fields))
        shutil.copyfile(hod, os.path.join(MOD, "data", "subsystem", name, name + ".hod"))
        dummy = name + "_dummy"
        fields["name"] = dummy
        write(os.path.join(MOD, "data", "ship", dummy, dummy + ".ship"), DUMMY.format(**fields))
        # the loose module: its unshifted build (in the Kuun-Lan's frame) if the subsystem's was recentred
        loose = os.path.join(BUILD, dummy, dummy + ".hod")
        shutil.copyfile(loose if os.path.exists(loose) else hod, os.path.join(MOD, "data", "ship", dummy, dummy + ".hod"))
    print(f"{len(MODULES)} Kuun-Lan modules: subsystems smt_kl_* and dummy ships smt_kl_*_dummy")


if __name__ == "__main__":
    import sys
    if "--list-builds" in sys.argv:          # for tools/build_kuunlan.sh
        print(" ".join(f"{k}={v[0].lower()}" for k, v in MODULES.items()))
    elif "--list-core" in sys.argv:          # core parts merged into the Kuun-Lan's mesh
        print(" ".join(f"race_sect/{v.lower()}" for v in CORE_PARTS.values()))
    elif "--list-hardpoints" in sys.argv:
        print(" ".join(spec for k in MODULES for spec in HARDPOINTS[k]))
    else:
        main()
