-- Cataclysm-HWRM: Cataclysm's own voices for the Somtaaw (Kiith Somtaaw Fleet Command and the per-ship-type unit barks).
-- Loaded at the end of each Players Patch speech logic file (tools/install_cr.py appends a dofilepath line to
-- soundscripts/speechlogic/{commands,status,chatter}.lua). Lua 4, like those files.
--
-- HWRM speech: the logic handlers (CommandAttackGiven(shipname, ...), StatusDamaged(shipName), ...) call
-- playSpeechActor(event, actor, voiceCount, frequency) / playSpeechActorLinked(..., link). The announcer actor comes
-- from raceHelper() ("Fleet" for us); unit barks from a pilot class ("Fighter_" with voiceCount 3 -> folder Fighter_1-3).
-- Cataclysm recorded its barks per ship type instead (its speech event variable = ShipType), so for Somtaaw ships:
--   * every handler is wrapped to remember the ship it was called for (CatSpeech_Ship);
--   * the play functions are wrapped: an announcer call plays from "cat_fleet" (flat, as stock "fleet"), a pilot call
--     from the speaking ship's own voice ("cat<ship>_" with count 1 -> folder cat<ship>_1), only for events
--     tools/make_unitspeech.py wrote (catspeech_gen.lua); an event Cataclysm has no line for plays nothing (as in
--     Cataclysm), never a Hiigaran voice;
--   * construction complete / ship destroyed play Cataclysm's "<ship>. Construction completed." / "<ship> destroyed"
--     (the stock logic only knows its own ship types).
-- Other races are untouched.

if CatSpeech_Loaded == nil then
    CatSpeech_Loaded = 1
    CatSpeech_Orig = {}
    CatSpeech_Ship = ""
    dofilepath("data:soundscripts/cataclysm/catspeech_gen.lua")   -- CatSpeech_Folders / _Lines / _Fleet / _Type

    CatSpeech_Play = playSpeechActor
    CatSpeech_PlayLinked = playSpeechActorLinked

    CatSpeech_Announcers = { FLEET = 1, MAKAAN = 1, EMPEROR = 1 }   -- raceHelper()'s actors

    function CatSpeech_IsSomtaaw(ship)
        if ship ~= nil and ship ~= "" then
            local s = strlower(ship)
            if strsub(s, 1, 4) == "smt_" or strsub(s, 1, 4) == "som_" then
                return 1
            end
            return nil
        end
        if Race_ID ~= nil and currentRace ~= nil and Race_ID[currentRace] == "Somtaaw" then
            return 1
        end
        return nil
    end

    -- the Somtaaw replacement for a call: event, actor, count; or nil (play nothing)
    function CatSpeech_Route(event, actor)
        local key = strupper(event)
        if CatSpeech_Announcers[strupper(actor or "")] ~= nil then
            if CatSpeech_Fleet[key] ~= nil then
                return CatSpeech_Fleet[key], "cat_fleet", 0
            end
            return nil
        end
        local base = CatSpeech_Folders[strlower(CatSpeech_Ship or "")]
        if base ~= nil and CatSpeech_Lines[base] ~= nil and CatSpeech_Lines[base][key] ~= nil then
            return key, base, 1
        end
        return nil
    end

    playSpeechActor = function(event, actor, count, freq)
        if CatSpeech_IsSomtaaw(CatSpeech_Ship) == nil then
            return %CatSpeech_Play(event, actor, count, freq)
        end
        local e, a, c = CatSpeech_Route(event, actor)
        if e == nil then
            return 0
        end
        return %CatSpeech_Play(e, a, c, freq)
    end

    if CatSpeech_PlayLinked ~= nil then
        playSpeechActorLinked = function(event, actor, count, freq, link)
            if CatSpeech_IsSomtaaw(CatSpeech_Ship) == nil then
                return %CatSpeech_PlayLinked(event, actor, count, freq, link)
            end
            local e, a, c = CatSpeech_Route(event, actor)
            if e == nil then
                return 0
            end
            return %CatSpeech_PlayLinked(e, a, c, freq, link)
        end
    end

    -- Cataclysm's per-ship-type announcements (CAT_BUILT_<x> / CAT_DESTROYED_<x> in cat_fleet)
    function CatSpeech_Announce(prefix, ship)
        local t = CatSpeech_Type[strlower(ship or "")]
        if t ~= nil then
            return %CatSpeech_Play(prefix .. "_" .. t, "cat_fleet", 0, 0.5)
        end
        return 0
    end
end

-- wrap the handlers this file defined (each logic file appends this file; wrapped ones are skipped)
function CatSpeech_Wrap(name, shipArg)
    local f = getglobal(name)
    if f == nil or CatSpeech_Orig[name] ~= nil then
        return
    end
    CatSpeech_Orig[name] = f
    setglobal(name, function(a1, a2, a3, a4, a5, a6)
        local prev = CatSpeech_Ship
        local args = { a1, a2, a3, a4, a5, a6 }
        CatSpeech_Ship = args[%shipArg] or ""
        local r = CatSpeech_Orig[%name](a1, a2, a3, a4, a5, a6)
        CatSpeech_Ship = prev
        return r
    end)
end

CatSpeech_Handlers = {
    "BattleChatMisc", "ChatterMisc", "ChatterMiscHighPriority",
    "CommandAttackGiven", "CommandCancelOrder", "CommandCaptureGiven", "CommandCombatMan", "CommandConstructionStarted",
    "CommandDefenseFieldChanged", "CommandDockGiven", "CommandEngagementRangeChanged",
    "CommandEngagementRangeForceChanged", "CommandGuardGiven", "CommandHotKeyGroupSelected", "CommandHyperspaceGiven",
    "CommandLaunchGiven", "CommandMoveAttackGiven", "CommandMoveGiven", "CommandMoveToSobGiven", "CommandMultiplay",
    "CommandParadeGiven", "CommandResourceGiven", "CommandRetireGiven", "CommandShipsSelected",
    "CommandStrikeGroupFormed", "CommandTacticsChanged", "CommandWayPointMoveGiven",
    "StatusAttackComplete", "StatusBuildAvailable", "StatusCaptureComplete", "StatusCloud", "StatusCriticallyDamaged",
    "StatusDamaged", "StatusHyperspaceExit", "StatusInMineField", "StatusRepairs", "StatusResources",
    "StatusRetaliating", "StatusShipDocked", "StatusTakingHeavyDamage",
    "StatusTakingLightDamage", "StatusUnderAttack", "StatusUnderFireNeedOrders",
}
for i = 1, getn(CatSpeech_Handlers) do
    CatSpeech_Wrap(CatSpeech_Handlers[i], 1)
end
CatSpeech_Wrap("StatusSubsystem", 2)               -- (ssname, shipName, event)

-- construction complete: Cataclysm's Fleet Command names the new ship
if getglobal("CommandConstructionComplete") ~= nil and CatSpeech_Orig["CommandConstructionComplete"] == nil then
    CatSpeech_Orig["CommandConstructionComplete"] = CommandConstructionComplete
    CommandConstructionComplete = function(buildingShip, builtItem, buildType)
        if CatSpeech_IsSomtaaw(builtItem) ~= nil and CatSpeech_Type[strlower(builtItem or "")] ~= nil then
            return CatSpeech_Announce("CAT_BUILT", builtItem)
        end
        local prev = CatSpeech_Ship
        CatSpeech_Ship = buildingShip or ""
        local r = CatSpeech_Orig["CommandConstructionComplete"](buildingShip, builtItem, buildType)
        CatSpeech_Ship = prev
        return r
    end
end

-- ship destroyed: Fleet Command reports it ("Acolyte destroyed"); hotkey group defeats go through the normal path
if getglobal("StatusShipDestroyed") ~= nil and CatSpeech_Orig["StatusShipDestroyed"] == nil then
    CatSpeech_Orig["StatusShipDestroyed"] = StatusShipDestroyed
    StatusShipDestroyed = function(shipName, code)
        local prev = CatSpeech_Ship
        CatSpeech_Ship = shipName or ""
        local r = 0
        if CatSpeech_IsSomtaaw(shipName) ~= nil and CatSpeech_Type[strlower(shipName or "")] ~= nil then
            if code ~= nil and code > 0 then
                r = CatSpeech_Orig["StatusShipDestroyed"](shipName, code)   -- the group's defeat line
            end
            r = CatSpeech_Announce("CAT_DESTROYED", shipName)
        else
            r = CatSpeech_Orig["StatusShipDestroyed"](shipName, code)
        end
        CatSpeech_Ship = prev
        return r
    end
end
