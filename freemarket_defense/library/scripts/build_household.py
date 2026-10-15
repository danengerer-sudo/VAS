"""Build category `household` -> build/household.blend, thumbs/household/*, catalog/household.json.

blender -b --factory-startup -P scripts/build_household.py [-- --only=a,b --nothumb]
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import household_lib as H  # noqa: E402
from genkit import MB, Category  # noqa: E402

cat = Category("household")


def add(name, body, tags, notes, bevel=0.0, seg=1, az=-35, el=22, fill=1.0, lens=50, merge=2e-6):
    def _():
        mb = MB()
        body(mb)
        return mb.build(name, bevel=bevel, seg=seg, merge=merge)
    cat.add(name, _, tags=tags, notes=notes, az=az, el=el, fill=fill, lens=lens)


# --- the donkey (punchline)
cat.add("donkey", lambda: H.donkey_build("donkey", "standing"), ["donkey", "animal", "ass", "mule", "farm"],
        "Stylised donkey, 1.1 m at the withers, facing +X, head turned ~60 deg toward -Y (over its shoulder at the viewer). "
        "Voxel-remeshed sculpt. household_lib.donkey(mb, pose='standing')", az=-55, el=18)
cat.add("donkey_grazing", lambda: H.donkey_build("donkey_grazing", "grazing"), ["donkey", "animal", "ass", "grazing", "farm"],
        "Same donkey with its head down grazing. household_lib.donkey(mb, pose='grazing')", az=-50, el=18)

# --- television
add("tv_flatscreen", lambda mb: H.tv(mb, stand=True), ["tv", "television", "screen", "living room", "electronics"],
    "55-inch flat screen (1.23 m wide) on a pedestal stand, screen = LIB_Glass (dark, glossy), facing +X. household_lib.tv(mb)",
    bevel=0.002, seg=2, az=-30, el=15)
add("tv_wall", lambda mb: H.tv(mb, wall=True), ["tv", "television", "screen", "wall mount", "electronics"],
    "55-inch TV wall-mounted: back of the set at x=0 (wall contact), screen centre 1.5 m up, facing +X. household_lib.tv(mb, wall=True)",
    bevel=0.002, seg=2, az=-30, el=10)
add("tv_boxed", lambda mb: H.tv_boxed(mb), ["tv", "box", "carton", "cardboard", "delivery", "purchase"],
    "Cardboard carton for the TV, 1.35 x 0.2 x 0.8 m standing, accent stripe + printed face toward +X. household_lib.tv_boxed(mb)",
    bevel=0.004, az=-35, el=18)

# --- hall pass
add("hall_pass", lambda mb: H.hall_pass(mb), ["hall pass", "school", "permission", "lanyard", "gag"],
    "Chunky laminated HALL PASS (accent, dark embossed text) on a lanyard, ~0.26 m tall, facing +X. household_lib.hall_pass(mb)",
    bevel=0.0008, seg=2, el=12, az=-25)
add("hall_pass_giant", lambda mb: H.hall_pass(mb, scale=1.2 / 0.26), ["hall pass", "school", "permission", "giant", "gag"],
    "The hall pass scaled to 1.2 m for a gag. household_lib.hall_pass(mb, scale=4.6)", bevel=0.004, seg=2, el=12, az=-25)

# --- small props (lying flat on the ground)
add("hammer", lambda mb: H.hammer(mb), ["hammer", "tool", "claw hammer", "weapon"],
    "Claw hammer 0.33 m lying flat, head at +X (dark steel, body-colour handle). household_lib.hammer(mb)",
    bevel=0.0015, seg=2, el=30)
add("kitchen_knife", lambda mb: H.kitchen_knife(mb), ["knife", "chef's knife", "kitchen", "tool", "weapon"],
    "Chef's knife 0.33 m lying flat, tip at +X, dark handle with rivets. household_lib.kitchen_knife(mb)",
    bevel=0.0008, seg=2, el=35)
add("car_keys", lambda mb: H.car_keys(mb), ["keys", "car keys", "fob", "key ring", "weapon"],
    "Key fob (dark, accent button) + two keys on a split ring, lying flat. household_lib.car_keys(mb)",
    bevel=0.0006, seg=2, el=40, fill=1.1)
add("book", lambda mb: H.book(mb), ["book", "hardback", "reading", "shelf"],
    "Hardback 0.24 x 0.16 x 0.035 m lying flat, accent cover with dark title 'LIBERTY', spine toward -Y, head toward -X. household_lib.book(mb, title=...)",
    bevel=0.0008, seg=2, el=35)
add("rifle_prop", lambda mb: H.rifle_prop(mb), ["rifle", "carbine", "gun", "weapon", "prop"],
    "figure.py carbine laid flat on its side on the ground, muzzle +X, all dark. household_lib.rifle_prop(mb)",
    bevel=0.002, seg=2, el=35, fill=1.0)

# --- tiny jail cell
add("jail_cell_tiny", lambda mb: H.jail_cell_tiny(mb), ["jail", "cell", "cage", "bars", "not guilty", "gag"],
    "0.5 m cage of dark bars (0.06 m spacing), interior empty (for the hammer), 'NOT GUILTY' accent placard on the front. "
    "household_lib.jail_cell_tiny(mb)", bevel=0.0015, az=-30, el=20)

# --- gun safe
add("gun_safe", lambda mb: H.gun_safe(mb), ["safe", "gun safe", "steel", "storage", "security"],
    "1.5 m steel gun safe, door closed (+X), dial, 3-spoke handle, hinges. household_lib.gun_safe(mb)", bevel=0.004, seg=2, az=-40, el=15)
add("gun_safe_open", lambda mb: H.gun_safe(mb, open_deg=100), ["safe", "gun safe", "steel", "storage", "open", "empty"],
    "Gun safe with the door swung 100 deg open, empty interior with shelves and rack bar. household_lib.gun_safe(mb, open_deg=100)",
    bevel=0.004, seg=2, az=-25, el=15)

# --- front door
add("front_door", lambda mb: H.front_door(mb), ["door", "front door", "house", "wall", "knocker", "doormat"],
    "3 x 3 m wall section with a framed 2.1 m front door, knocker, letter slot, knob, porch light, '1776', WELCOME doormat. Faces +X. "
    "household_lib.front_door(mb)", bevel=0.006, seg=2, az=-35, el=12)

# --- living room
add("living_room_set", lambda mb: H.living_room_set(mb), ["living room", "sofa", "furniture", "rug", "lamp", "interior"],
    "3-seat sofa, coffee table, side table (plant), floor lamp, accent rug, laid out around a TV stand at the origin. "
    "TV NOT included: put tv_flatscreen on the stand top (z=0.5) at x=0 rotated 180 (facing -X toward the sofa). "
    "household_lib.living_room_set(mb, with_stand=True)", bevel=0.03, seg=2, az=-70, el=30, fill=1.0)

# --- floating labels
for key, txt in (("rifle", "RIFLE"), ("hammer", "HAMMER"), ("knife", "KNIFE"), ("keys", "CAR KEYS"), ("2a", "2ND AMENDMENT")):
    add(f"label_{key}", (lambda t: (lambda mb: H.label(mb, t)))(txt), ["label", "tag", "caption", "text", key],
        f"Floating label plate 0.5 x 0.18 m (body) with dark text '{txt}', facing +X, bottom at z=0. household_lib.label(mb, text)",
        bevel=0.003, seg=2, az=-20, el=10)

cat.finish(cols=6)
