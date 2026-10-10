-- Cataclysm-HWRM: the Worker's / Processor's repair beam, drawn by shiprules.lua CatBeam_Set between two volumes
-- (FX_PlayEffectBetweenPoints, re-spawned as the ends move). Stock pro_tech_beam_link's layout (a beam stretched
-- between its two points), our white beam texture (data/art/fx/cat/cat_repairbeam.tga; the stock ion beam one is blue) tinted repair green, scrolling from the repairer to the target.
fx = {
style = "STYLE_BEAM",
properties = {
property_00 = {
name = "Duration",
type = "VARTYPE_FLOAT",
value = 5,
},
property_01 = {
name = "Loop",
type = "VARTYPE_BOOL",
value = 1,
},
property_02 = {
name = "Blending",
type = "VARTYPE_INT",
value = 2,
},
property_03 = {
name = "Texture",
type = "VARTYPE_STRING",
value = "DATA:ART/FX/CAT/CAT_REPAIRBEAM.TGA",
},
property_04 = {
name = "SelfIlluminated",
type = "VARTYPE_BOOL",
value = 1,
},
property_05 = {
name = "Offset",
type = "VARTYPE_ARRAY_TIMEVECTOR3",
value = {
entry_00 = {
0,
0,
0,
0,
},
entry_01 = {
1,
0,
0,
0,
},
},
},
property_06 = {
name = "Length",
type = "VARTYPE_ARRAY_TIMEFLOAT",
value = {
0,
1,
1,
1,
},
},
property_07 = {
name = "Noise",
type = "VARTYPE_ARRAY_TIMEFLOAT",
value = {
0,
0,
1,
0,
},
},
property_08 = {
name = "Segments",
type = "VARTYPE_ARRAY_TIMEFLOAT",
value = {
0,
1,
1,
1,
},
},
property_09 = {
name = "Texture_U_Offset",
type = "VARTYPE_ARRAY_TIMEFLOAT",
value = {
0,
0,
1,
-10,
},
},
property_10 = {
name = "Texture_U_Repeat",
type = "VARTYPE_ARRAY_TIMEFLOAT",
value = {
0,
2,
1,
2,
},
},
property_11 = {
name = "Width",
type = "VARTYPE_ARRAY_TIMEFLOAT",
value = {
0,
8,
1,
8,
},
},
property_12 = {
name = "Colour",
type = "VARTYPE_ARRAY_TIMECOLOUR",
value = {
entry_00 = {
0,
0.35,
1,
0.5,
0.8,
},
entry_01 = {
1,
0.35,
1,
0.5,
0.8,
},
},
},
property_13 = {
name = "Arc",
type = "VARTYPE_ARRAY_TIMEVECTOR3",
value = {
entry_00 = {
0,
0,
0,
0,
},
entry_01 = {
1,
0,
0,
0,
},
},
},
property_14 = {
name = "LengthEpsilon",
type = "VARTYPE_FLOAT",
value = 0,
},
property_15 = {
name = "WidthEpsilon",
type = "VARTYPE_FLOAT",
value = 0,
},
property_16 = {
name = "LineDistance",
type = "VARTYPE_FLOAT",
value = -1,
},
},
}
