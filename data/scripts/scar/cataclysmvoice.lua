-- Cataclysm's speech queue: every voice line the mission side plays goes through CatVoice_Event, nothing else calls
-- Subtitle_AddSkippable (tools/check_voice.py fails the build if anything does). Mission dialogue (kasfSpeechEvent),
-- Fleet Command / Tactical Officer lines (modules online, technologies, autolaunch) and the pilots' barks (link,
-- mimic, kamikaze, ...) are queued and played by the exe's rules:
--
-- cataclysm.exe FUN_00522560 (queue a line), FUN_00522e60 (pick the next), FUN_00521eb0 (play / finish), decompiled
-- in Cataclysm-decomp/out/speech_ev.c, speech_q.c, speech_upd.c; every call's event code and wait in
-- out/speech_calls.tsv. An event code is the line's flags | actor | event number (low 11 bits):
--   actor 0x1000 Fleet Command, 0x2000 the Tactical Officer, 0x800 a pilot, 0x8000 other fleets;
--   0x10000000 a mission line (kasfSpeechEvent), 0x1000000 a status report, 0x2000000 a command report,
--   0x4000000 chatter; 0x60000000 may play during a cutscene.
-- Rules:
--   channel: Fleet Command and the Tactical Officer share channel 1; status reports (and actor 0x200000) channel 2;
--     everything else (pilots, other fleets) channel 0. Each channel plays one line at a time; channels play
--     together.
--   wait: a line given a wait (> 0: the exe's 5 s) is taken only if its channel is free within that long, and
--     dropped if it hasn't started that long after; a 0 s wait plays now or never; a mission line (-1) never expires.
--   a line repeating the one its channel is speaking (same event and variable) is dropped; 10 waiting per channel.
--   next line: the highest flag class (top 4 bits: mission lines first), then the event's priority (the sentence
--     table's first column: KAS_SpeechPriority, tools/build_speech.py), then the earliest expiry (never first).
--   while a mission line plays, status reports are refused and the other speech is ducked (the exe scales its
--     volume; HWRM's Sound_EnterIntelEvent, SpeechVolDuckingLevel).
--   during a cutscene only lines flagged 0x60000000 are taken.
-- The engine's own speech (data/soundscripts/speechlogic: selection and order acknowledgements, Fleet Command's
-- reports) runs in HWRM's speech system, which this queue can't see: while channel 1 speaks, Fleet Command's actor
-- there ("cat_fleet") is muted (Sound_SetMuteActor), so its reports are dropped instead of waiting up to 5 s.
-- Not ported: the exe's 1.5 s gap rule between a channel's lines (FUN_00521eb0, decompile unclear).

CAT_VOICE_CHANNELS = 3
CAT_VOICE_QUEUE = 10
CAT_VOICE_FLEET_ACTOR = "cat_fleet"   -- the speech logic's Fleet Command (install_cr.py raceHelper)
CatVoice = { queue = {}, playing = {}, intel = 0, muted = nil }
for c = 0, CAT_VOICE_CHANNELS - 1 do CatVoice.queue[c] = {} end

function CatVoice_Bits(code, bit)
    return mod(floor(code / bit), 2)
end

function CatVoice_Channel(code)
    local actor = mod(floor(code / 2048), 1024) * 2048       -- code & 0x3ff800
    if actor == 4096 or actor == 8192 then return 1 end
    if CatVoice_Bits(code, 16777216) == 1 or actor == 2097152 then return 2 end
    return 0
end

-- the speaking actor (the subtitle's): Fleet Command for 0x1000, else Fleet Intel's slot (HWRM has no Tactical
-- Officer; pilots and other fleets spoke there before this queue too)
function CatVoice_Actor(code)
    if CatVoice_Bits(code, 4096) == 1 then return Actor_HW1_FleetCommand end
    return Actor_HW1_FleetIntel
end

-- the recording for event / variable: one of the event's variations at random, of those this variable has
-- (FUN_005223c0 with variation -1; the exe weights them by the phrase table's probability)
function CatVoice_Phrase(ev, variable)
    local e = KAS_SpeechEvents and KAS_SpeechEvents["sect" .. ev]
    if e == nil or variable == nil or variable < 0 or variable >= e[2] then return nil end
    local ids = {}
    for v = 0, e[1] - 1 do
        local i = KAS_SpeechBankBase.sect + e[3] + v * e[2] + variable
        if KAS_SpeechDurations[i] then tinsert(ids, i) end
    end
    if getn(ids) > 0 then return ids[random(1, getn(ids))] end
    return KAS_SpeechBankBase.sect + e[3] + variable
end

function CatVoice_NisPlaying()
    if NISGetAnyPlayingHandle == nil then return nil end
    local h = NISGetAnyPlayingHandle()
    return h ~= NISHandle_Invalid and NISComplete(h) == 0
end

-- Queue a line (FUN_00522560). code: the exe's event code; variable: the event's variable; wait: seconds (-1 never
-- expires, 0 now or never, the exe's 5); opts.actor: the subtitle actor instead of CatVoice_Actor. Returns the entry,
-- or nil when dropped.
function CatVoice_Event(code, variable, wait, opts)
    if code < 0 then code = code + 4294967296 end
    local ev = mod(code, 2048)
    local now = Universe_GameTime()
    local why = nil
    if CatVoice_NisPlaying() and CatVoice_Bits(code, 536870912) == 0 and CatVoice_Bits(code, 1073741824) == 0 then
        why = "cutscene"
    elseif CatVoice.intel > 0 and CatVoice_Bits(code, 16777216) == 1 then
        why = "status during a mission line"
    end
    local c = CatVoice_Channel(code)
    local p = CatVoice.playing[c]
    if why == nil and wait > 0 and p and p.ends > now + wait then why = "channel busy " .. (p.ends - now) .. "s" end
    if why == nil and p and p.code == code and p.var == variable then why = "repeat" end
    if why == nil and getn(CatVoice.queue[c]) >= CAT_VOICE_QUEUE then why = "queue full" end
    local id = nil
    if why == nil then
        id = CatVoice_Phrase(ev, variable)
        if id == nil then why = "no line for variable " .. tostring(variable) end
    end
    if why then
        print("CKAS voice " .. ev .. "/" .. tostring(variable) .. " dropped (" .. why .. ")")
        return nil
    end
    local q = { code = code, ev = ev, var = variable, id = id, actor = (opts and opts.actor) or CatVoice_Actor(code),
                pri = KAS_SpeechPriority["sect" .. ev] or 0, class = floor(code / 268435456),
                expiry = -1, secs = (KAS_SpeechDurations[id] or 2000) / 1000, done = nil }
    if wait >= 0 then q.expiry = now + wait end
    tinsert(CatVoice.queue[c], q)
    CatVoice_Update()
    if Rule_Exists("CatVoice_Update") == 0 then Rule_AddInterval("CatVoice_Update", 0.1) end
    return q
end

-- the next line (FUN_00522e60): expired ones go, then the highest class, priority, earliest expiry
function CatVoice_Next(c, now)
    local list, best, keep = CatVoice.queue[c], nil, {}
    for i = 1, getn(list) do
        local q = list[i]
        if q.expiry >= 0 and q.expiry < now then
            q.done = 1
            print("CKAS voice " .. q.ev .. "/" .. q.var .. " expired")
        else
            tinsert(keep, q)
            if best == nil or q.class > best.class or (q.class == best.class and (q.pri > best.pri
               or (q.pri == best.pri and q.expiry < best.expiry))) then
                best = q
            end
        end
    end
    CatVoice.queue[c] = keep
    return best
end

function CatVoice_Update()
    local now = Universe_GameTime()
    local busy = 0
    for c = 0, CAT_VOICE_CHANNELS - 1 do
        local p = CatVoice.playing[c]
        if p and now >= p.ends then          -- finished (FUN_00521eb0: the stream done)
            p.done = 1
            if p.class == 1 then
                CatVoice.intel = CatVoice.intel - 1
                if CatVoice.intel == 0 then Sound_ExitIntelEvent() end
            end
            CatVoice.playing[c] = nil
            p = nil
        end
        if p == nil then
            local q = CatVoice_Next(c, now)
            if q then
                for i = 1, getn(CatVoice.queue[c]) do
                    if CatVoice.queue[c][i] == q then tremove(CatVoice.queue[c], i) break end
                end
                local t = Subtitle_AddSkippable(q.actor, "$" .. q.id, q.secs)
                if t and t > q.secs then q.secs = t end
                q.ends = now + q.secs
                CatVoice.playing[c] = q
                if q.class == 1 then
                    if CatVoice.intel == 0 then Sound_EnterIntelEvent() end
                    CatVoice.intel = CatVoice.intel + 1
                end
                print("CKAS voice " .. q.ev .. "/" .. q.var .. " -> $" .. q.id .. " on channel " .. c .. " (" .. q.secs .. "s)")
            end
        end
        if CatVoice.playing[c] or getn(CatVoice.queue[c]) > 0 then busy = 1 end
    end
    -- the engine's Fleet Command can't wait for channel 1: silent while it speaks
    local mute = CatVoice.playing[1] ~= nil
    if mute ~= CatVoice.muted then
        CatVoice.muted = mute
        if mute then Sound_SetMuteActor(CAT_VOICE_FLEET_ACTOR) else Sound_SetMuteActor("") end
    end
    if busy == 0 and Rule_Exists("CatVoice_Update") == 1 then Rule_Remove("CatVoice_Update") end
end
