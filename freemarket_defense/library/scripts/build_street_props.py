"""street_props: street furniture from Kenney City Kits (Roads, Commercial, Suburban), Holiday Kit, Survival Kit.

Real-world sizes (per-pack scale): city-kit props 8 m/tile except where noted; holiday kit x1.4;
survival kit x3. Directional props (signs, benches, awnings) face +X.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pack_import as pi  # noqa: E402

CAT = "street_props"
P = {
    "rd": ("kenney_city_roads", "Kenney City Kit (Roads)", "https://kenney.nl/assets/city-kit-roads"),
    "com": ("kenney_city_commercial", "Kenney City Kit (Commercial) 2.1", "https://kenney.nl/assets/city-kit-commercial"),
    "sub": ("kenney_city_suburban", "Kenney City Kit (Suburban) 2.0", "https://kenney.nl/assets/city-kit-suburban"),
    "hol": ("kenney_holiday_kit", "Kenney Holiday Kit", "https://kenney.nl/assets/holiday-kit"),
    "sur": ("kenney_survival_kit", "Kenney Survival Kit", "https://kenney.nl/assets/survival-kit"),
}
# (pack, model, scale, rot_z, tags, profile)
ITEMS = [
    ("rd", "light-square", 10, 90, ["streetlight", "lamp"], "prop"),
    ("rd", "light-square-double", 10, 90, ["streetlight", "lamp"], "prop"),
    ("rd", "light-curved", 10, 90, ["streetlight", "lamp"], "prop"),
    ("rd", "light-curved-double", 10, 90, ["streetlight", "lamp"], "prop"),
    ("rd", "traffic-light", 8, 90, ["traffic_light", "traffic"], "prop"),
    ("rd", "traffic-light-hanging", 8, 90, ["traffic_light", "traffic"], "prop"),
    ("rd", "road-sign-stop", 6, 90, ["sign", "traffic", "stop"], "prop"),
    ("rd", "road-sign-warning", 6, 90, ["sign", "traffic"], "prop"),
    ("rd", "road-sign-street", 6, 90, ["sign", "street_name"], "prop"),
    ("rd", "road-sign-empty", 6, 90, ["sign", "blank"], "prop"),
    ("rd", "sign-highway", 8, 90, ["sign", "highway", "gantry"], "prop"),
    ("rd", "sign-highway-wide", 8, 90, ["sign", "highway", "gantry"], "prop"),
    ("rd", "construction-cone", 8, 0, ["construction", "cone", "traffic"], "prop"),
    ("rd", "construction-barrier", 8, 90, ["construction", "barrier"], "prop"),
    ("rd", "construction-fence", 8, 90, ["construction", "fence"], "prop"),
    ("rd", "construction-light", 8, 90, ["construction", "light"], "prop"),
    ("rd", "dumpster", 5, 90, ["dumpster", "bin", "waste"], "prop"),
    ("rd", "electricity-pole", 15, 90, ["utility_pole", "power"], "prop"),
    ("rd", "electricity-pole-wide", 15, 90, ["utility_pole", "power"], "prop"),
    ("com", "detail-awning", 8, 90, ["awning", "shopfront", "brand"], "prop"),
    ("com", "detail-awning-wide", 8, 90, ["awning", "shopfront", "brand"], "prop"),
    ("com", "detail-overhang", 8, 90, ["awning", "shopfront"], "prop"),
    ("com", "detail-overhang-wide", 8, 90, ["awning", "shopfront"], "prop"),
    ("com", "detail-parasol-a", 8, 90, ["parasol", "cafe", "market"], "prop"),
    ("com", "detail-parasol-b", 8, 90, ["parasol", "cafe", "market"], "prop"),
    ("sub", "fence", 5, 0, ["fence", "garden"], "prop"),
    ("sub", "fence-low", 5, 0, ["fence", "garden"], "prop"),
    ("sub", "fence-2x2", 5, 0, ["fence", "garden", "enclosure"], "prop"),
    ("sub", "planter", 5, 0, ["planter", "garden", "plant"], "prop"),
    ("sub", "tree-large", 8, 0, ["tree", "nature"], "prop"),
    ("sub", "tree-small", 8, 0, ["tree", "nature"], "prop"),
    ("sub", "driveway-long", 8, 0, ["driveway", "ground"], "road"),
    ("sub", "path-stones-long", 8, 0, ["path", "ground"], "road"),
    ("hol", "bench", 1.4, 90, ["bench", "park", "seating"], "prop"),
    ("hol", "bench-short", 1.4, 90, ["bench", "park", "seating"], "prop"),
    ("hol", "lantern", 1.4, 90, ["lamp", "lantern", "park"], "prop"),
    ("hol", "tree", 1.6, 0, ["tree", "pine", "nature"], "prop"),
    ("hol", "tree-decorated", 1.6, 0, ["tree", "christmas", "holiday"], "prop"),
    ("hol", "rocks-large", 1.4, 0, ["rocks", "nature"], "prop"),
    ("hol", "rocks-small", 1.4, 0, ["rocks", "nature"], "prop"),
    ("hol", "present-a-cube", 1.0, 0, ["gift", "present", "box"], "prop"),
    ("hol", "present-b-rectangle", 1.0, 0, ["gift", "present", "box"], "prop"),
    ("hol", "snowman", 1.4, 90, ["snowman", "winter"], "prop"),
    ("sur", "signpost", 4, 90, ["sign", "signpost", "wood"], "prop"),
    ("sur", "signpost-single", 4, 90, ["sign", "signpost", "wood"], "prop"),
    ("sur", "fence", 3, 0, ["fence", "wood"], "prop"),
    ("sur", "fence-fortified", 3, 0, ["fence", "wall", "fortified"], "prop"),
    ("sur", "tree", 3, 0, ["tree", "nature"], "prop"),
    ("sur", "tree-tall", 3, 0, ["tree", "nature"], "prop"),
    ("sur", "tree-autumn", 3, 0, ["tree", "nature"], "prop"),
    ("sur", "rock-a", 3, 0, ["rock", "nature"], "prop"),
    ("sur", "campfire-pit", 3, 0, ["campfire", "fire"], "prop"),
]
NATURE = {"tree", "rocks", "rock", "planter", "campfire"}
specs = []
for pk, m, s, r, tags, prof in ITEMS:
    d, src, url = P[pk]
    nm = (pk + "_" if m in ("fence", "tree") else "") + m.replace("-", "_")
    specs.append(dict(name=nm, file=pi.kenney(d, m), scale=s, rot_z=r, profile=prof, tags=["street", "prop"] + tags,
                      notes=f"{src}, scale x{s}", source=src, license="CC0 1.0", url=url,
                      accent_as=pi.DARK if NATURE & set(tags) else None))

if __name__ == "__main__":
    pi.build(CAT, specs, cols=10)
