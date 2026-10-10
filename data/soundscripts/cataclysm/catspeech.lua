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
    CatSpeech_Announcers = { FLEET = 1, MAKAAN = 1, EMPEROR = 1 }   -- raceHelper()'s actors

    -- the last ship the logic reported was Somtaaw: decides events without a ship (research complete, build paused,
    -- hyperspace ...). The handlers fire for the local player's ships; Race_ID / currentRace don't help in the
    -- campaign (Players Patch writes player:racelist.lua only from skirmish setup, so its default list has no Somtaaw)
    CatSpeech_LastSmt = nil

    function CatSpeech_IsSomtaaw(ship)
        if ship ~= nil and ship ~= "" then
            local p = strsub(strupper(ship), 1, 4)
            if p == "SMT_" or p == "SOM_" then
                CatSpeech_LastSmt = 1
                return 1
            end
            CatSpeech_LastSmt = nil
            return nil
        end
        if CatSpeech_LastSmt ~= nil then
            return 1
        end
        if Race_ID ~= nil and currentRace ~= nil and Race_ID[currentRace] == "Somtaaw" then
            return 1
        end
        return nil
    end

    -- for a Somtaaw ship: the replacement event, actor, count, or nil (nothing to play)
    function CatSpeech_Route(event, actor)
        local key = strupper(event)
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

    function CatSpeech_Play(event, actor, count, freq)
        if CatSpeech_IsSomtaaw(CatSpeech_Ship) == nil then
            return playSpeechActor(event, actor, count, freq)
        end
        local e, a, c = CatSpeech_Route(event, actor)
        if e == nil then
            return 0
        end
        return playSpeechActor(e, a, c, freq)
    end

    function CatSpeech_PlayLinked(event, actor, count, freq, link)
        if CatSpeech_IsSomtaaw(CatSpeech_Ship) == nil then
            return playSpeechActorLinked(event, actor, count, freq, link)
        end
        local e, a, c = CatSpeech_Route(event, actor)
        if e == nil then
            return 0
        end
        return playSpeechActorLinked(e, a, c, freq, link)
    end

    -- construction complete: Cataclysm's Fleet Command names the new ship ("Acolyte. Construction completed.");
    -- returns 1 when handled
    function CatSpeech_Built(builtItem)
        local t = CatSpeech_Type[strupper(builtItem or "")]
        if t ~= nil then
            playSpeechActor("CAT_BUILT_" .. t, "cat_fleet", 0, 0.5)
            return 1
        end
        return nil
    end

    -- ship destroyed: Fleet Command reports it ("Acolyte destroyed"); returns 1 when handled
    function CatSpeech_Destroyed(shipName)
        local t = CatSpeech_Type[strupper(shipName or "")]
        if t ~= nil then
            playSpeechActor("CAT_DESTROYED_" .. t, "cat_fleet", 0, 0.5)
            return 1
        end
        return nil
    end
end
