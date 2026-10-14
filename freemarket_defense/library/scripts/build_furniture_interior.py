"""furniture_interior: Kenney Furniture Kit (office / home interior) as white-model furniture.

Scale 1 Kenney unit = 1.9 m (desk 0.72 m high, door 1.9 m, chair seat ~0.45 m). Fronts face +X.
Wood / fabric -> LIB_Body, metal frames / screens -> LIB_Dark, glass -> LIB_Glass, lamp shades -> LIB_Light.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pack_import as pi  # noqa: E402

CAT = "furniture_interior"
FUR = ("kenney_furniture_kit", "Kenney Furniture Kit", "https://kenney.nl/assets/furniture-kit")
ROT = 90  # kit models face -Y (verified on contact sheet)
ITEMS = {
    "desk": ["office", "desk"], "deskCorner": ["office", "desk"], "chairDesk": ["office", "chair"],
    "computerScreen": ["office", "computer", "screen"], "computerKeyboard": ["office", "computer"],
    "laptop": ["office", "computer"], "bookcaseClosed": ["office", "shelf"], "bookcaseClosedDoors": ["office", "cabinet"],
    "bookcaseClosedWide": ["office", "shelf"], "bookcaseOpen": ["office", "shelf"], "bookcaseOpenLow": ["office", "shelf"],
    "books": ["office", "books"],
    "coatRackStanding": ["home"], "trashcan": ["office", "bin"], "speaker": ["electronics"], "radio": ["electronics"],
    "chair": ["home", "chair"], "chairCushion": ["home", "chair"], "chairModernCushion": ["home", "chair"],
    "chairModernFrameCushion": ["home", "chair"], "chairRounded": ["home", "chair"], "stoolBar": ["home", "stool"],
    "stoolBarSquare": ["home", "stool"], "bench": ["home", "bench"], "benchCushion": ["home", "bench"],
    "table": ["home", "table"], "tableCloth": ["home", "table"], "tableRound": ["home", "table"],
    "tableGlass": ["home", "table"], "tableCross": ["home", "table"], "tableCoffee": ["home", "table"],
    "tableCoffeeGlass": ["home", "table"], "sideTable": ["home", "table"], "sideTableDrawers": ["home", "table"],
    "loungeSofa": ["home", "sofa"], "loungeSofaLong": ["home", "sofa"], "loungeSofaCorner": ["home", "sofa"],
    "loungeChair": ["home", "armchair"], "loungeChairRelax": ["home", "armchair"], "loungeDesignChair": ["home", "armchair"],
    "loungeDesignSofa": ["home", "sofa"], "loungeSofaOttoman": ["home", "ottoman"],
    "bedSingle": ["home", "bed"], "bedDouble": ["home", "bed"], "bedBunk": ["home", "bed"],
    "cabinetBedDrawer": ["home", "nightstand"], "cabinetTelevision": ["home", "tv_stand"],
    "televisionModern": ["home", "tv", "electronics"], "televisionVintage": ["home", "tv", "electronics"],
    "lampRoundFloor": ["home", "lamp"], "lampSquareFloor": ["home", "lamp"], "lampRoundTable": ["home", "lamp"],
    "lampSquareCeiling": ["home", "lamp"], "ceilingFan": ["home"], "pottedPlant": ["home", "plant"],
    "plantSmall1": ["home", "plant"], "rugRectangle": ["home", "rug"], "rugRound": ["home", "rug"],
    "kitchenCabinet": ["kitchen", "cabinet"], "kitchenCabinetDrawer": ["kitchen", "cabinet"],
    "kitchenCabinetUpper": ["kitchen", "cabinet"], "kitchenSink": ["kitchen"], "kitchenStove": ["kitchen", "appliance"],
    "kitchenStoveElectric": ["kitchen", "appliance"], "kitchenFridge": ["kitchen", "appliance"],
    "kitchenFridgeLarge": ["kitchen", "appliance"], "kitchenMicrowave": ["kitchen", "appliance"],
    "kitchenCoffeeMachine": ["kitchen", "appliance", "coffee"], "kitchenBlender": ["kitchen", "appliance"],
    "toaster": ["kitchen", "appliance"], "kitchenBar": ["kitchen", "counter"], "hoodModern": ["kitchen"],
    "washer": ["laundry", "appliance"], "dryer": ["laundry", "appliance"], "washerDryerStacked": ["laundry", "appliance"],
    "bathtub": ["bathroom"], "shower": ["bathroom"], "toilet": ["bathroom"], "bathroomSink": ["bathroom"],
    "bathroomCabinet": ["bathroom"], "bathroomMirror": ["bathroom"],
    "wall": ["architecture", "wall"], "wallWindow": ["architecture", "wall", "window"],
    "wallDoorway": ["architecture", "wall", "door"], "wallDoorwayWide": ["architecture", "wall", "door"],
    "doorway": ["architecture", "door"], "doorwayOpen": ["architecture", "door"], "wallCorner": ["architecture", "wall"],
    "floorFull": ["architecture", "floor"], "stairs": ["architecture", "stairs"], "stairsOpen": ["architecture", "stairs"],
}
specs = []
for m, tags in ITEMS.items():
    snake = "".join("_" + c.lower() if c.isupper() else c for c in m)
    specs.append(dict(name=snake, file=pi.kenney(FUR[0], m, "GLTF format"), scale=1.9, rot_z=ROT, profile="prop",
                      per_face=False, tags=["furniture", "interior"] + tags, notes="Furniture Kit, 1 unit = 1.9 m",
                      source=FUR[1], license="CC0 1.0", url=FUR[2]))

if __name__ == "__main__":
    pi.build(CAT, specs, cols=10)
