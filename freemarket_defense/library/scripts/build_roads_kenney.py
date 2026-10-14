"""roads_kenney: Kenney City Kit (Roads) tiles + Train Kit rail pieces.

Road tiles use the same 8 m grid as city_buildings_kenney (1 Kenney tile = 8 m), origin at tile
centre, so tiles snap on an 8 m grid. Asphalt (source lum ~0.53) -> LIB_Dark via dark_lum=0.56, kerbs / pavement / markings -> LIB_Body.
Rail pieces: 1 Train Kit unit = 2.6 m (matches vehicles_kenney trains).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pack_import as pi  # noqa: E402

CAT = "roads_kenney"
LIC = "CC0 1.0"
RD = ("kenney_city_roads", "Kenney City Kit (Roads)", "https://kenney.nl/assets/city-kit-roads")
TRN = ("kenney_train_kit", "Kenney Train Kit", "https://kenney.nl/assets/train-kit")
specs = []

ROADS = ["road-straight", "road-straight-half", "road-straight-barrier", "road-bend", "road-bend-sidewalk",
         "road-bend-square", "road-curve", "road-curve-intersection", "road-curve-pavement", "road-crossroad",
         "road-crossroad-line", "road-crossroad-path", "road-crossing", "road-intersection",
         "road-intersection-line", "road-intersection-path", "road-roundabout", "road-end", "road-end-round",
         "road-side", "road-side-entry", "road-side-exit", "road-split", "road-square",
         "road-driveway-single", "road-driveway-double", "road-slant", "road-slant-high", "road-slant-curve",
         "road-slant-flat", "road-bridge", "bridge-pillar", "bridge-pillar-wide",
         "tile-low", "tile-high", "tile-slant"]
for m in ROADS:
    d, src, url = RD
    specs.append(dict(name=m.replace("-", "_"), file=pi.kenney(d, m), scale=8.0, rot_z=0, profile="road", dark_lum=0.56,
                      tags=["road", "tile", "street", "city"], notes="Road tile, 8 m grid", source=src,
                      license=LIC, url=url, el=40))

RAIL = ["railroad-straight", "railroad-curve", "railroad-corner-small", "railroad-corner-large",
        "railroad-straight-hill-complete", "railroad-rail-straight", "track", "track-detailed"]
for m in RAIL:
    d, src, url = TRN
    specs.append(dict(name=m.replace("-", "_"), file=pi.kenney(d, m), scale=2.6, rot_z=-90, profile="road",
                      tags=["rail", "railway", "track"], notes="Rail piece (Train Kit, 1 unit = 2.6 m)",
                      source=src, license=LIC, url=url, el=40))

if __name__ == "__main__":
    pi.build(CAT, specs, cols=9)
