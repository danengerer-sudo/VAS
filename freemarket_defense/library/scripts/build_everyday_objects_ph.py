"""everyday_objects_ph: Poly Haven (CC0) everyday objects, 1k glTF, converted to white-model materials.

Poly Haven models are already real-world metres. Textures are dropped: each original material is
mapped as a whole to a LIB_* material from its mean albedo (very dark -> LIB_Dark, the dominant
colour -> LIB_Body, other strongly coloured materials -> LIB_Accent, glass -> LIB_Glass). The mean
albedo per face is kept in the `orig_color` attribute. Directional objects are turned to face +X.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pack_import as pi  # noqa: E402

CAT = "everyday_objects_ph"
# id: (rot_z, tags)
ITEMS = {
    "CashRegister_01": (90, ["shop", "retail", "checkout", "money"]),
    "CoffeeCart_01": (90, ["shop", "cafe", "cart", "street_vendor"]),
    "Barrel_01": (0, ["barrel", "container"]), "barrel_03": (0, ["barrel", "container"]),
    "cardboard_box_01": (0, ["box", "logistics", "parcel"]), "wooden_crate_01": (0, ["crate", "logistics", "trade"]),
    "wooden_crate_02": (0, ["crate", "logistics", "trade"]), "plastic_crate_01": (0, ["crate", "market", "produce"]),
    "street_lamp_01": (90, ["street", "streetlight", "lamp"]), "street_lamp_02": (90, ["street", "streetlight", "lamp"]),
    "fire_hydrant": (90, ["street", "hydrant"]), "metal_trash_can": (0, ["street", "bin", "waste"]),
    "concrete_road_barrier": (0, ["street", "barrier", "construction"]),
    "modular_street_seating": (90, ["street", "bench", "seating"]), "painted_wooden_bench": (90, ["bench", "park", "seating"]),
    "wooden_picnic_table": (0, ["table", "park", "seating"]), "metal_office_desk": (90, ["office", "desk"]),
    "modern_arm_chair_01": (90, ["office", "chair", "armchair"]), "SchoolDesk_01": (90, ["school", "desk"]),
    "SchoolChair_01": (90, ["school", "chair"]), "WoodenChair_01": (90, ["home", "chair"]),
    "dining_chair_02": (90, ["home", "chair"]), "plastic_monobloc_chair_01": (90, ["chair", "cafe", "outdoor"]),
    "wooden_stool_01": (0, ["stool"]), "Sofa_01": (90, ["home", "sofa"]), "mid_century_lounge_chair": (90, ["home", "armchair"]),
    "coffee_table_round_01": (0, ["home", "table"]), "drawer_cabinet": (90, ["office", "cabinet"]),
    "Shelf_01": (90, ["shelf", "storage"]), "steel_frame_shelves_01": (90, ["shelf", "storage", "warehouse"]),
    "wooden_display_shelves_01": (90, ["shelf", "shop", "display"]), "hand_truck": (90, ["logistics", "trolley", "warehouse"]),
    "tool_cart": (90, ["workshop", "tools", "cart"]), "portable_generator": (90, ["industrial", "generator", "energy"]),
    "propane_tank": (0, ["industrial", "gas", "tank"]), "metal_toolbox": (90, ["workshop", "tools"]),
    "Drill_01": (90, ["tools", "drill"]), "sledgehammer_01": (90, ["tools", "hammer"]), "wooden_ladder": (90, ["tools", "ladder"]),
    "Television_01": (90, ["electronics", "tv", "media"]), "classic_laptop": (90, ["electronics", "laptop", "office"]),
    "Camera_01": (90, ["electronics", "camera", "media"]), "Megaphone_01": (90, ["megaphone", "protest", "announcement"]),
    "korean_public_payphone_01": (90, ["street", "payphone", "telecom"]), "exterior_aircon_unit": (90, ["building", "aircon"]),
    "utility_box_01": (90, ["street", "utility"]), "security_camera_01": (90, ["security", "surveillance", "camera"]),
    "WetFloorSign_01": (90, ["sign", "cleaning"]), "Lantern_01": (0, ["lamp", "lantern"]),
    "lightbulb_01": (0, ["lightbulb", "idea", "innovation"]), "wall_clock": (90, ["clock", "time"]),
    "food_apple_01": (0, ["food", "produce"]), "bananas": (0, ["food", "produce"]), "croissant": (0, ["food", "bakery"]),
    "wine_bottles_01": (0, ["drinks", "bottle"]), "wicker_basket_01": (0, ["basket", "market"]),
    "trashbag": (0, ["waste", "bag"]), "water_manhole_cover": (0, ["street", "manhole"]),
    "wheelchair_01": (90, ["health", "wheelchair"]), "old_tyre": (0, ["tyre", "junk"]),
    "cement_bag": (0, ["construction", "bag"]), "vintage_suitcase": (90, ["travel", "suitcase"]),
    "potted_plant_01": (0, ["plant", "home", "office"]),
}
specs = []
for pid, (rot, tags) in ITEMS.items():
    nm = pid.lower()
    nm = nm[:-3] if nm.endswith("_01") else nm
    specs.append(dict(name=nm, file=f"polyhaven/{pid}/{pid}_1k.gltf", scale=1.0, rot_z=rot, profile="prop",
                      per_face=False, dark_lum=0.16, tags=["polyhaven", "everyday"] + tags,
                      notes="Poly Haven 1k glTF, textures dropped (white model)", source=f"Poly Haven: {pid}",
                      license="CC0 1.0", url=f"https://polyhaven.com/a/{pid}"))

if __name__ == "__main__":
    pi.build(CAT, specs, cols=8)
