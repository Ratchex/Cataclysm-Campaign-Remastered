"""Ship variants: a copy of a ship type with other weapons, for a weapon upgrade HWRM can't make per ship.

Cataclysm upgrades a ship's guns one ship at a time (tools/make_upgrades.py: WEAPON_ENERGY, a gun projectile ->
energy once TECH_ENERGY is researched and that ship is upgraded). HWRM weapons are per ship type, so the upgraded
ship is swapped for a variant type with the upgraded weapons while it is docked (shiprules.lua CatVariant_*:
invisible in the hangar, the user's choice), and after the research the build list offers the variant instead
(new ships come upgraded). Everything else treats a variant as its base type (shiprules.lua CatVariantBase: class,
name, abilities, upgrades, Link; cataclysmkas.lua: mission scripts selecting the base type get the variants too).

install_base.py builds each variant's data/ship folder from its base's (weapons replaced, .madstate functions
renamed); make_shipcode.py hooks it like any ship; make_race.py lists it to build; this writes
data/scripts/cataclysm/variants_gen.lua for both Lua states (ship code and mission).
"""
import os
import re
import shutil

HERE = os.path.dirname(os.path.abspath(__file__))
MOD = os.path.dirname(HERE)
DATA = os.path.join(MOD, "data")
STOCK_HW1 = r"C:\Modding\Cataclysm-decomp\reference\hwrm\HW1Ships\ship"

# variant: (base type, upgrade that calls for it, {base weapon: variant weapon}, research the build entry needs)
# SHELVED (user, 2026-10-09): VARIANTS is empty, so nothing is built, swapped or offered; the WEAPON_ENERGY upgrade
# is still recorded per ship (for the damage conversion). Swapping a *docked* ship failed in game: SobGroup_Despawn
# does nothing to a docked ship (the engine relaunched the old one), a ship spawned and SobGroup_DockSobGroupInstant'ed
# in the same tick never ran its ship code (never came out), new builds count as docked inside the Kuun-Lan (swapped
# and hidden at once: building broke), and a group name kept after a ship's code ends is given to later ships
# (removing by the kept name removed every Acolyte). Untried: swapping in open space at the hangar exit (as Link's
# spawn / despawn, which work), or building the variant directly after the research (KAS_VariantBuildWatch).
VARIANTS = {}
SHELVED = {
    # Energy Cannons (TECH_ENERGY): the Acolyte's normal gun becomes data/weapon/cat_acolyteenergy (their energy
    # cannon Ksh_KineticAutoGun1, SmallEnergyCannon bolts, as a normal weapon). Their Super Acolyte pulsars were tried
    # first: a 10 degree forward cone and 0.06 accuracy against fighters, so they hardly fired.
    "smt_acolyte_e": ("smt_acolyte", "WEAPON_ENERGY", {"Ksh_KineticAutoGun": "cat_acolyteenergy"}, "TECH_ENERGY"),
}


# Mimic disguises (Cataclysm: a Mimic projects the image of a small ship, FUN_005b8d70 / FUN_005b88f0: it renders
# that ship's model in its owner's team colours, so that side ignores it: "None of the mines can track a mimic when
# it imitates an enemy ship", Mission04). Shown on the Mimic itself: its model holds every target's (tools/
# make_mimic.py), chosen from the "Mimic" menu (one button per disguise, as Cataclysm's "Select Mimic Type"),
# shiprules.lua CatMimic_*. Single Mimics copy fighters (strR1TECH_MIMICinfo: "fighters, micro-class ships, and small
# asteroids"; asteroids and crates: later).
# target ship type: (menu label, colour scheme of the impersonated faction: make_colours.py)
DISGUISES = {
    "tai_interceptor": ("Taiidan Interceptor", 2),
    "tai_attackbomber": ("Taiidan Attack Bomber", 2),
    "tai_defender": ("Taiidan Defender", 2),
    "kus_interceptor": ("Kushan Interceptor", 6),
    "kus_attackbomber": ("Kushan Attack Bomber", 6),
    "bst_acolyte": ("Beast Acolyte", 1),
    "smt_acolyte": ("Acolyte", 0),
}


def base_of(ship):
    return VARIANTS[ship][0] if ship in VARIANTS else ship


def build(variant):
    """data/ship/<variant>/ from data/ship/<base>/ (files renamed, weapons replaced, .madstate functions renamed).
    Returns the data/ paths written ('/' separated), for install_base.py's manifest."""
    base, _, weapons, _ = VARIANTS[variant]
    src, dst = os.path.join(DATA, "ship", base), os.path.join(DATA, "ship", variant)
    if os.path.isdir(dst):
        shutil.rmtree(dst)
    os.makedirs(dst)
    written = []
    for fn in sorted(os.listdir(src)):
        if not fn.lower().startswith(base + "."):
            continue                                   # their spare files (smt_worker_old.ship ...)
        out = variant + fn[len(base):]
        data = open(os.path.join(src, fn), "rb").read()
        if fn.endswith(".ship"):
            text = data.decode("latin-1")
            for old, new in weapons.items():
                text, n = re.subn(r'(StartShipWeaponConfig\(NewShipType,\s*")' + re.escape(old) + '"',
                                  r"\g<1>" + new + '"', text)
                if not n:
                    raise SystemExit(f"{variant}: no {old} weapon on {base}")
            data = text.encode("latin-1")
        elif fn.endswith(".madstate"):                 # <SHIP>_<State>_OnSet: named after the ship type
            text = data.decode("latin-1")
            data = re.sub(r"\b" + base.upper() + "_", variant.upper() + "_", text).encode("latin-1")
        open(os.path.join(dst, out), "wb").write(data)
        written.append(f"ship/{variant}/{out}")
    return written


def disguise_states():
    """target -> the Mimic's mad state showing that disguise (its model's Disguise_<target> joint: tools/make_mimic.py).
    NIS00 is the Mimic itself; SobGroup_SetMadState passes on only the engine's state names, and of the numbered NIS
    states only NIS00-02 (the stock madstates' too: NIS03 and up never reached ours), so then the dock path states,
    which the engine sets only on ships with dock paths (the Mimic has none)."""
    assert len(DISGUISES) <= len(DISGUISE_STATES), "more disguises than mad states"
    return {t: DISGUISE_STATES[k] for k, t in enumerate(sorted(DISGUISES))}


DISGUISE_STATES = ["NIS01", "NIS02"] + [f"DockPathOpen{n}" for n in range(1, 6)] + \
    [f"DockPathClosed{n}" for n in range(1, 6)]


def write_lua():
    """data/scripts/cataclysm/variants_gen.lua: CatVariantBase (variant -> base) and CatVariants (base -> list of
    { type, upgrade, research that offers it to build })."""
    out = ["-- Generated by tools/ship_variants.py: ship type variants (see that tool)", "CatVariantBase = {"]
    out += [f'    ["{v}"] = "{b}",' for v, (b, _, _, _) in sorted(VARIANTS.items())]
    out += ["}"]
    # Mimic disguises: { target, label, scheme, button, state } (the menu button's ability name: mimic_<target>;
    # the Mimic's mad state showing it, disguise_states)
    states = disguise_states()
    out.append("CatDisguises = {")
    out += [f'    {{ target = "{t}", label = "{lbl}", scheme = {sc}, button = "mimic_{t}", state = "{states[t]}" }},'
            for t, (lbl, sc) in sorted(DISGUISES.items())]
    out += ["}", "CatVariants = {"]
    bases = sorted({b for b, _, _, _ in VARIANTS.values()})
    for b in bases:
        items = [f'{{ type = "{v}", upgrade = "{u}", tech = "{t}" }}' for v, (bb, u, _, t) in sorted(VARIANTS.items())
                 if bb == b]
        out.append(f'    ["{b}"] = {{ {", ".join(items)} }},')
    out.append("}")
    path = os.path.join(DATA, "scripts", "cataclysm", "variants_gen.lua")
    with open(path, "w", newline="\n") as f:
        f.write("\n".join(out) + "\n")
    return path
