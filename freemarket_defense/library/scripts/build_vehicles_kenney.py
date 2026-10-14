"""vehicles_kenney: Kenney Car Kit, Train Kit and Watercraft Kit as white-model vehicles.

All vehicles face +X. Car wheels / train bogies stay separate child objects with their origin at
the wheel centre (spin about local Y). Kenney's toy proportions are kept but rescaled so a sedan
is ~4.3 m long and ~2 m wide (width scaled separately: 1.3 vs 1.7 on length/height, which keeps
wheels round). Trains: 1 Kenney unit = 2.6 m (loco ~6 m, short/stylised). Boats: rescaled to a
plausible length per type (stylised proportions).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pack_import as pi  # noqa: E402

CAT = "vehicles_kenney"
LIC = "CC0 1.0"
CAR = ("kenney_car_kit", "Kenney Car Kit", "https://kenney.nl/assets/car-kit")
TRN = ("kenney_train_kit", "Kenney Train Kit", "https://kenney.nl/assets/train-kit")
WAT = ("kenney_watercraft", "Kenney Watercraft Kit", "https://kenney.nl/assets/watercraft-kit")
CAR_ROT = 90  # kit models drive along -Y (verified: rear showed at +X with -90)
specs = []


def add(pack, model, name, tags, notes="", **kw):
    d, src, url = pack
    sp = dict(name=name, file=pi.kenney(d, model), profile="vehicle", tags=["vehicle"] + tags,
              notes=notes, source=src, license=LIC, url=url)
    sp.update(kw)
    specs.append(sp)


CARS = {
    "sedan": ["car", "sedan"], "sedan-sports": ["car", "sports"], "hatchback-sports": ["car", "hatchback"],
    "suv": ["car", "suv"], "suv-luxury": ["car", "suv", "luxury"], "taxi": ["car", "taxi"],
    "police": ["car", "police", "government"], "ambulance": ["van", "ambulance", "emergency"],
    "firetruck": ["truck", "firetruck", "emergency"], "van": ["van", "commercial"],
    "delivery": ["van", "delivery", "logistics"], "delivery-flat": ["truck", "delivery", "flatbed"],
    "truck": ["truck", "logistics"], "truck-flat": ["truck", "flatbed"],
    "garbage-truck": ["truck", "garbage", "municipal"], "race": ["car", "race"],
    "race-future": ["car", "race", "futuristic"], "tractor": ["tractor", "farm", "agriculture"],
    "tractor-police": ["tractor", "police"], "tractor-shovel": ["tractor", "loader", "construction"],
}
for m, tags in CARS.items():
    add(CAR, m, m.replace("-", "_"), tags, "Car Kit vehicle; wheels are separate children",
        scale=(1.3, 1.7, 1.7), rot_z=CAR_ROT, parts=True, dark_lum=0.47)
for m in ["cone", "box"]:
    add(CAR, m, f"car_kit_{m}", ["prop"], "Car Kit prop", scale=1.7, profile="prop")

TRAINS = ["train-diesel-a", "train-diesel-b", "train-diesel-box-a", "train-locomotive-a",
          "train-locomotive-passenger-a", "train-electric-bullet-a", "train-electric-city-a",
          "train-electric-double-a", "train-electric-subway-a", "train-electric-square-a",
          "train-tram-classic", "train-tram-modern", "train-tram-round",
          "train-carriage-box", "train-carriage-coal", "train-carriage-container-red",
          "train-carriage-flatbed", "train-carriage-lumber", "train-carriage-tank", "train-carriage-wood"]
for m in TRAINS:
    t = ["train", "rail"] + (["tram"] if "tram" in m else []) + (["freight", "wagon"] if "carriage" in m else ["locomotive"])
    add(TRN, m, m.replace("-", "_"), t, "Train Kit (stylised short); bogies are separate children",
        scale=2.6, rot_z=CAR_ROT, parts=True, dark_lum=0.47)

BOATS = {  # model: (target length m, tags)
    "boat-row-small": (3.5, ["boat", "rowboat"]), "boat-row-large": (5, ["boat", "rowboat"]),
    "boat-speed-a": (7, ["boat", "speedboat"]), "boat-speed-d": (7, ["boat", "speedboat"]),
    "boat-speed-g": (7, ["boat", "speedboat"]), "boat-fishing-small": (9, ["boat", "fishing"]),
    "boat-sail-a": (8, ["boat", "sailboat"]), "boat-sail-b": (8, ["boat", "sailboat"]),
    "boat-tug-a": (12, ["boat", "tug", "port"]), "boat-tow-a": (12, ["boat", "tow"]),
    "boat-house-a": (12, ["boat", "houseboat"]), "boat-fan": (6, ["boat", "airboat"]),
    "ship-small": (25, ["ship", "sailing_ship", "trade"]), "ship-large": (35, ["ship", "sailing_ship", "trade"]),
    "ship-cargo-a": (60, ["ship", "cargo", "trade", "shipping"]), "ship-cargo-b": (60, ["ship", "cargo", "trade", "shipping"]),
    "ship-cargo-c": (60, ["ship", "cargo", "trade", "shipping"]), "ship-ocean-liner": (90, ["ship", "liner", "cruise"]),
    "ship-ocean-liner-small": (70, ["ship", "liner", "cruise"]),
}
for m, (L, tags) in BOATS.items():
    add(WAT, m, m.replace("-", "_"), ["watercraft"] + tags, f"Watercraft Kit (stylised), rescaled to {L} m long",
        rot_z=CAR_ROT, target={"axis": 0, "size": L})

if __name__ == "__main__":
    pi.build(CAT, specs, cols=10)
