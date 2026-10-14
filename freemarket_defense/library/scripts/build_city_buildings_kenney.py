"""city_buildings_kenney: Kenney City Kits (Commercial, Suburban, Industrial) as white-model buildings.

Scale: all Kenney city kits share a 1-unit tile grid; we use 1 tile = 8 m (a 3-storey commercial
block is ~10 m tall, a suburban bungalow ~6.6 m to the ridge), so buildings tile with roads_kenney.
Fronts (doors) face +X.
Run: blender -b --factory-startup -P build_city_buildings_kenney.py [-- --only=a,b --nothumb]
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pack_import as pi  # noqa: E402

CAT = "city_buildings_kenney"
TILE = 8.0
LIC = "CC0 1.0"
specs = []

COM = ("kenney_city_commercial", "Kenney City Kit (Commercial) 2.1",
       "https://kenney.nl/assets/city-kit-commercial")
SUB = ("kenney_city_suburban", "Kenney City Kit (Suburban) 2.0",
       "https://kenney.nl/assets/city-kit-suburban")
IND = ("kenney_city_industrial", "Kenney City Kit (Industrial) 2.0",
       "https://kenney.nl/assets/city-kit-industrial")


def add(pack, model, name, tags, notes=""):
    d, src, url = pack
    specs.append(dict(name=name, file=pi.kenney(d, model), scale=TILE, rot_z=90, profile="building",
                      tags=tags, notes=notes, source=src, license=LIC, url=url))


for c in "abcdefghijklmn":
    add(COM, f"building-{c}", f"shop_building_{c}", ["building", "commercial", "shop", "office", "city"],
        "Commercial block with ground-floor shopfront")
for c in "abcde":
    add(COM, f"building-skyscraper-{c}", f"skyscraper_{c}", ["building", "skyscraper", "office", "tower", "city", "corporate"],
        "Office tower")
for c in "abcdefghijklmn":
    add(COM, f"low-detail-building-{c}", f"lowdetail_building_{c}", ["building", "low_detail", "background", "city"],
        "Low-detail background building (cheap for crowds of buildings)")
for c in "ab":
    add(COM, f"low-detail-building-wide-{c}", f"lowdetail_building_wide_{c}", ["building", "low_detail", "background", "city"],
        "Low-detail wide background building")
for c in "abcdefghijklmnopqrstu":
    add(SUB, f"building-type-{c}", f"house_{c}", ["building", "house", "suburban", "residential", "home"],
        "Suburban house (garden plot included)")
for c in "abcdefghijklmnopqrst":
    add(IND, f"building-{c}", f"factory_building_{c}", ["building", "industrial", "factory", "warehouse"],
        "Industrial building / factory hall")

if __name__ == "__main__":
    pi.build(CAT, specs, cols=10)
