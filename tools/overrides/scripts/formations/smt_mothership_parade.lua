-- Cataclysm-HWRM: the Kuun-Lan's parade, Cataclysm's parade_smothership.script by tools/make_parade.py
-- (generated): paradeSlot(type, offset, heading, direction of growth, size of growth); port: strike craft,
-- starboard: frigates, aft: capital ships, nothing at the bow (Cataclysm: it interferes with crystal
-- harvesting)

paradeSlot("smt_scout", {840, -490, 962.5}, {0, 0, 1}, {1, 0, 0}, 70);   -- SLOT_SRECON
paradeSlot("smt_acolyte", {840, -420, 700}, {0, 0, 1}, {1, 0, 0}, 70);   -- SLOT_SACOLYTE
paradeSlot("smt_acv", {840, -315, 437.5}, {0, 0, 1}, {1, 0, 0}, 70);   -- SLOT_SACV
paradeSlot("smt_sentinel", {840, -210, 175}, {0, 0, 1}, {1, 0, 0}, 70);   -- SLOT_SSENTINEL
paradeSlot("smt_worker", {840, 0, -350}, {0, 0, 1}, {1, 0, 0}, 140);   -- SLOT_SWORKER
paradeSlot("smt_mimic", {-840, -700, 787.5}, {0, 0, 1}, {-1, 0, 0}, 70);   -- SLOT_SMIMIC
paradeSlot("smt_rammingfrigate", {-840, -350, 262.5}, {0, 0, 1}, {-1, 0, 0}, 210);   -- SLOT_SRAMMINGFRIGATE
paradeSlot("smt_multibeamfrigate", {-840, -175, 0}, {0, 0, 1}, {-1, 0, 0}, 210);   -- SLOT_SMULTIBEAMFRIGATE
paradeSlot("smt_hivefrigate", {-840, 0, -262.5}, {0, 0, 1}, {-1, 0, 0}, 210);   -- SLOT_SHIVEFRIGATE
paradeSlot("smt_destroyer", {-840, 175, -525}, {0, 0, 1}, {-1, 0, 0}, 210);   -- SLOT_SDESTROYER
paradeSlot("smt_carrier", {-0, -175, -1750}, {0, 0, 1}, {1, 0, 0}, 700);   -- SLOT_SCARRIER0
paradeSlot("smt_dreadnought", {-840, -350, -1225}, {0, 0, 1}, {-0.9701, -0.2425, 0}, 721.543);   -- SLOT_SDREADNOUGHT
paradeSlot("smt_processor", {840, -350, -875}, {0, 0, 1}, {0.9701, -0.2425, 0}, 721.543);   -- SLOT_SPROCESSOR

-- everything else (Cataclysm's SLOT_Misc: salvaged ships and the rest)
paradeSlot("misc", {875, 0, -3500}, {0, 0, 1}, {-1, 0, 0}, 175);
