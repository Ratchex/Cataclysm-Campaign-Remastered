-- Cataclysm-HWRM: Cataclysm's own voices for the Somtaaw (Kiith Somtaaw Fleet Command and the per-ship-type unit barks).
--
-- HWRM speech: the logic handlers (CommandAttackGiven(shipname, ...), StatusDamaged(shipName), ...) in
-- soundscripts/speechlogic/{commands,status,chatter}.lua call playSpeechActor(event, actor, voiceCount, frequency) /
-- playSpeechActorLinked(..., link). The announcer actor comes from raceHelper() ("Fleet" for us); unit barks from a
-- pilot class ("Fighter_" with voiceCount 3 -> folder Fighter_1-3). Cataclysm recorded its barks per ship type (its
-- speech event variable = ShipType).
--
-- That environment does not allow redefining a global function ("Cannot overwrite function") and has no getn, so
-- tools/install_cr.py patch_speech_logic() edits the Players Patch files instead: this file is loaded at the top of
-- each, every handler first stores its ship in CatSpeech_Ship, the play calls go through CatSpeech_Play /
-- CatSpeech_PlayLinked, and construction-complete / ship-destroyed first ask CatSpeech_Built / CatSpeech_Destroyed.
-- For Somtaaw ships an announcer call plays from "cat_fleet" (flat, as stock "fleet"), a pilot call from the speaking
-- ship's own voice ("cat<ship>_" with count 1 -> folder cat<ship>_1), only for events tools/make_unitspeech.py wrote
-- (catspeech_gen.lua); an event Cataclysm has no line for plays nothing. Other races play exactly as before.
-- Only functions the stock logic itself uses (strupper, strsub) are used here.

if CatSpeech_Loaded == nil then
    CatSpeech_Loaded = 1
    CatSpeech_Ship = ""
    dofilepath("data:soundscripts/cataclysm/catspeech_gen.lua")   -- CatSpeech_Folders / _Lines / _Fleet / _Type
    CatSpeech_Announcers = { FLEET = 1, MAKAAN = 1, EMPEROR = 1, CAT_FLEET = 1 }   -- raceHelper()'s actors

    -- a Somtaaw ship; or, without a ship, the player's race (Race_ID from player:racelist.lua, written at mission
    -- start by cataclysmkas.lua SpeechRaceHelper)
    function CatSpeech_IsSomtaaw(ship)
        if ship ~= nil and ship ~= "" then
            local p = strsub(strupper(ship), 1, 4)
            if p == "SMT_" or p == "SOM_" then
                return 1
            end
            return nil
        end
        if Race_ID ~= nil and currentRace ~= nil and Race_ID[currentRace] == "Somtaaw" then
            return 1
        end
        return nil
    end

    -- a ship whose attack order is its kamikaze (no guns: the Mimic): its pilot's last words come from the ship
    -- rules (line 167, shiprules.lua CatKamikaze_Tick) instead of the attack acknowledgement (user: not over it)
    CatSpeech_Kamikaze = { SMT_MIMIC = 1 }
    function CatSpeech_SilentAttack(ship)
        if ship ~= nil and CatSpeech_Kamikaze[strupper(ship)] ~= nil then
            return 1
        end
        return nil
    end

    -- ship events Cataclysm's Fleet Command says instead of the ship (user: the Guard order, "Escorts assigned.")
    -- and the group keys (user: "Stand by. Group n." when the group's key is pressed)
    CatSpeech_ToFleet = { COMMAND_GUARD = "COMMAND_GUARD_1", COMMAND_CAP_GUARD = "COMMAND_GUARD_1",
        COMMAND_SELECTGROUP01 = "COMMAND_SELECTGROUP01", COMMAND_SELECTGROUP02 = "COMMAND_SELECTGROUP02",
        COMMAND_SELECTGROUP03 = "COMMAND_SELECTGROUP03", COMMAND_SELECTGROUP04 = "COMMAND_SELECTGROUP04",
        COMMAND_SELECTGROUP05 = "COMMAND_SELECTGROUP05", COMMAND_SELECTGROUP06 = "COMMAND_SELECTGROUP06",
        COMMAND_SELECTGROUP07 = "COMMAND_SELECTGROUP07", COMMAND_SELECTGROUP08 = "COMMAND_SELECTGROUP08",
        COMMAND_SELECTGROUP09 = "COMMAND_SELECTGROUP09", COMMAND_SELECTGROUP10 = "COMMAND_SELECTGROUP10" }

    -- Repeat limits, as Cataclysm's speech queue (HW1 SpeechEvent.c): a Fleet Command line is dropped while the same
    -- line is still playing (user: construction complete / destroyed / "Group n reports hostiles" spam), so its
    -- repeat interval (the play call's frequency: HWRM's only throttle, no clock here) is at least its own length;
    -- warnings about a hotkey group under attack wait SPEECH_WARNING_TIME, 30 s (Cataclysm soundevent.script)
    CatSpeech_WarningTime = 30
    CatSpeech_Warnings = { STATUS_ASSIGNEDGROUPUNDERATTACK_REPORT_G = 1 }
    -- Ship barks (selection, orders: Cataclysm FUN_00522560 queues them with no wait, 0 s, on the pilots' channel and
    -- drops one that repeats the last queued event; user: selection / order spam): the same, with a ship voice's
    -- line (base: its folder) at least its own length (catspeech_gen.lua CatSpeech_Lines)
    function CatSpeech_Freq(key, freq, base)
        local f = freq or 0
        if CatSpeech_Secs ~= nil and CatSpeech_Secs[key] ~= nil and CatSpeech_Secs[key] + 0.5 > f then
            f = CatSpeech_Secs[key] + 0.5
        end
        if base ~= nil and CatSpeech_Lines[base] ~= nil and CatSpeech_Lines[base][key] ~= nil
           and CatSpeech_Lines[base][key] + 0.5 > f then
            f = CatSpeech_Lines[base][key] + 0.5
        end
        if CatSpeech_Warnings[strsub(key, 1, 40)] ~= nil and CatSpeech_WarningTime > f then
            f = CatSpeech_WarningTime
        end
        return f
    end

    -- for a Somtaaw ship: the replacement event, actor, count, or nil (nothing to play)
    function CatSpeech_Route(event, actor)
        local key = strupper(event)
        if CatSpeech_ToFleet[key] ~= nil and CatSpeech_Fleet[CatSpeech_ToFleet[key]] ~= nil then
            return CatSpeech_Fleet[CatSpeech_ToFleet[key]], "cat_fleet", 0
        end
        if actor ~= nil and CatSpeech_Announcers[strupper(actor)] ~= nil then
            if CatSpeech_Fleet[key] ~= nil then
                return CatSpeech_Fleet[key], "cat_fleet", 0
            end
            return nil
        end
        local base = CatSpeech_Folders[strupper(CatSpeech_Ship or "")]
        if base ~= nil and CatSpeech_Lines[base] ~= nil and CatSpeech_Lines[base][key] ~= nil then
            return key, base, 1
        end
        return nil
    end

    -- raceHelper() returned the Somtaaw announcer (patched in by install_cr.py): always Cataclysm's Fleet Command
    function CatSpeech_IsCatFleet(actor)
        if actor ~= nil and strupper(actor) == "CAT_FLEET" then
            return 1
        end
        return nil
    end

    function CatSpeech_Play(event, actor, count, freq)
        if CatSpeech_IsCatFleet(actor) ~= nil then
            local key = strupper(event)
            if CatSpeech_Fleet[key] ~= nil then
                return playSpeechActor(CatSpeech_Fleet[key], "cat_fleet", 0, CatSpeech_Freq(CatSpeech_Fleet[key], freq))
            end
            return 0
        end
        if CatSpeech_IsSomtaaw(CatSpeech_Ship) == nil then
            return playSpeechActor(event, actor, count, freq)
        end
        local e, a, c = CatSpeech_Route(event, actor)
        if e == nil then
            return 0
        end
        return playSpeechActor(e, a, c, CatSpeech_Freq(e, freq, a))
    end

    function CatSpeech_PlayLinked(event, actor, count, freq, link)
        if CatSpeech_IsCatFleet(actor) ~= nil then
            local key = strupper(event)
            if CatSpeech_Fleet[key] ~= nil then
                return playSpeechActorLinked(CatSpeech_Fleet[key], "cat_fleet", 0, CatSpeech_Freq(CatSpeech_Fleet[key], freq), link)
            end
            return 0
        end
        if CatSpeech_IsSomtaaw(CatSpeech_Ship) == nil then
            return playSpeechActorLinked(event, actor, count, freq, link)
        end
        local e, a, c = CatSpeech_Route(event, actor)
        if e == nil then
            return 0
        end
        return playSpeechActorLinked(e, a, c, CatSpeech_Freq(e, freq, a), link)
    end

    -- construction complete: Cataclysm's Fleet Command names the new ship ("Acolyte. Construction completed.");
    -- returns 1 when handled
    function CatSpeech_Built(builtItem)
        local key = strupper(builtItem or "")
        if CatSpeech_Module[key] ~= nil then          -- a Kuun-Lan module: "Hangar module is now online."
            -- played by the mission runtime (cataclysmkas.lua CatModuleTick), which can wait for Fleet Intel's
            -- briefing as Cataclysm's queue does (user: it played over mission dialogue)
            return 1
        end
        local t = CatSpeech_Type[key]
        if t ~= nil then
            playSpeechActor("CAT_BUILT_" .. t, "cat_fleet", 0, CatSpeech_Freq("CAT_BUILT_" .. t, 0.5))
            return 1
        end
        return nil
    end

    -- a ship type can now be built: "<ship> is now available for construction" (only when the engine names it;
    -- it often reports "" and the stock generic line is not Cataclysm's: nothing plays then)
    function CatSpeech_Available(shipName)
        local t = CatSpeech_Type[strupper(shipName or "")]
        if t ~= nil then
            playSpeechActor("CAT_AVAILABLE_" .. t, "cat_fleet", 0, CatSpeech_Freq("CAT_AVAILABLE_" .. t, 0.5))
            return 1
        end
        return nil
    end

    -- ship destroyed: Fleet Command reports it ("Acolyte destroyed"); returns 1 when handled
    function CatSpeech_Destroyed(shipName)
        local t = CatSpeech_Type[strupper(shipName or "")]
        if t ~= nil then
            playSpeechActor("CAT_DESTROYED_" .. t, "cat_fleet", 0, CatSpeech_Freq("CAT_DESTROYED_" .. t, 0.5))
            return 1
        end
        return nil
    end

    -- a repair order given (chatter.lua CE_CMD_REPAIR, a speechFile entry the engine played in the stock support
    -- pilot voice; install_cr.py makes it call this): routed like the handlers, so a Somtaaw ship says Cataclysm's
    -- "Repairs underway." and other races play the stock line as before
    function CatSpeech_CommandRepair(shipname, targetname)
        CatSpeech_Ship = shipname or ""
        CatSpeech_Play("COMMAND_STARTEDREPAIRS", NameSupportPilot, NumSupportPilots, Frequency_Command)
    end
end
