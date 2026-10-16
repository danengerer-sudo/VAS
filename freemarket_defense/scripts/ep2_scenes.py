"""v2 scene builder: one Blender file per SET, several BEATS (camera setups) per set, cut at beat
boundaries. Run inside Blender by ep2.py:

    blender -b --factory-startup -P ep2_scenes.py -- set.json out_dir storyboard_pct

set.json = {"id": "street", "set": "street", "sun": [elev, rot], "beats": [beat, ...]}
beat = {"id": 8, "frame_start": .., "frame_end": .., "cam": [[x,y,z],[x,y,z]], "look": [[..],[..]],
        "lens": 40, "fstop": 2.8|null, "focus": "ObjName"|[x,y,z]|null, "show": {"ObjName": [[f0,f1],...]}}

Composition rules baked in: every beat names a lens, the camera has a foreground element where the
set provides one, close-ups use depth of field, and camera moves end on the subject.
"""
import os
import sys
import json
import math
import random
import bpy
from mathutils import Vector

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "library", "scripts"))
from libload import place, asset
from lib import pbr, box, text_decal
from mhuman import make_person
from figure import carbine

argv = sys.argv[sys.argv.index("--") + 1:]
SPEC = json.load(open(argv[0]))
OUT = argv[1]
PCT = int(argv[2]) if len(argv) > 2 else 40
ACCENT = (0.95, 0.38, 0.06)
RED = (0.62, 0.04, 0.03)
GOLD = (1.0, 0.8, 0.0)
FONT = "/usr/share/fonts/opentype/inter/Inter-Bold.otf"
D = math.pi / 2
FPS = 24
rng = random.Random(SPEC["id"])

bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene
NAMED = {}  # name -> object, for focus targets and show/hide keys


def has(cat, name):
    try:
        asset(cat, name)
        return True
    except Exception as e:
        print("WARN missing asset", cat, name, e)
        return False


def put(cat, name, loc, rot_z=0, scale=1.0, key=None):
    o = place(cat, name, loc, rot_z, scale)
    if key:
        NAMED[key] = o
    return o


def person(name, x, y, hd, mode="casual", weapon=None, z=0.0, **kw):
    p = make_person(name, mode=mode, weapon=weapon, **kw)
    p.location = (x, y, z)
    p.rotation_euler = (0, 0, hd)
    NAMED[name] = p
    return p


def lying(name, x, y, hd, **kw):
    """A figure on the ground (on its side)."""
    p = make_person(name, mode="casual", **kw)
    p.location = (x, y, 0.28)
    p.rotation_euler = (math.radians(90), 0, hd)
    NAMED[name] = p
    return p


def plate(text, loc, rot_z=0, size=0.12, col=(0.03, 0.03, 0.035), key=None):
    pl = box(f"lbl_{text}", (0.012, size * 0.62 * len(text) + size * 0.9, size * 1.9), loc, None,
             min(0.012, size * 0.2), pbr("LIB_Body", (0.82, 0.81, 0.79), rough=0.5))
    pl.rotation_euler = (0, 0, rot_z)
    t = text_decal(f"txt_{text}", text, size, pbr("LIB_Dark", col, rough=0.5), (0.013, 0, 0), (D, 0, D), None, font=FONT)
    t.parent = pl
    if key:
        NAMED[key] = pl
    return pl


def slab(name, dims, loc, col=(0.82, 0.81, 0.79), rough=0.6, rot=(0, 0, 0), key=None):
    o = box(name, dims, loc, None, 0.01, pbr(f"M_{name}", col, rough=rough))
    o.rotation_euler = rot
    if key:
        NAMED[key] = o
    return o


def disc(name, r, loc, col, key=None):
    bpy.ops.mesh.primitive_circle_add(vertices=48, radius=r, fill_type="NGON", location=loc)
    o = bpy.context.active_object
    o.name = name
    o.data.materials.append(pbr(f"M_{name}", col, rough=0.7))
    if key:
        NAMED[key] = o
    return o


def ground(col=(0.56, 0.55, 0.52), size=600):
    me = bpy.data.meshes.new("Ground")
    s = size
    me.from_pydata([(-s, -s, -0.02), (s, -s, -0.02), (s, s, -0.02), (-s, s, -0.02)], [], [(0, 1, 2, 3)])
    g = bpy.data.objects.new("Ground", me)
    sc.collection.objects.link(g)
    m = bpy.data.materials.new("EpGround")
    m.use_nodes = True
    nt = m.node_tree
    b = nt.nodes["Principled BSDF"]
    tc = nt.nodes.new("ShaderNodeTexCoord")
    n1 = nt.nodes.new("ShaderNodeTexNoise")
    n1.inputs["Scale"].default_value = 0.05
    nt.links.new(tc.outputs["Object"], n1.inputs["Vector"])
    rmp = nt.nodes.new("ShaderNodeValToRGB")
    rmp.color_ramp.elements[0].color = (*[c * 0.85 for c in col], 1)
    rmp.color_ramp.elements[1].color = (*col, 1)
    nt.links.new(n1.outputs["Fac"], rmp.inputs["Fac"])
    nt.links.new(rmp.outputs["Color"], b.inputs["Base Color"])
    b.inputs["Roughness"].default_value = 0.9
    g.data.materials.append(m)
    return g


def rifle_in(name, loc, rot=(0, 0, 0), key=None):
    g = carbine(name, sc.collection, pbr("FigGun", (0.035, 0.037, 0.04), rough=0.45))
    g.location = loc
    g.rotation_euler = rot
    if key:
        NAMED[key] = g
    return g


# ----------------------------------------------------------------------------- the house lot (shared)
def house_lot(cx=0, cy=0, car=True, fence=True):
    """house_gable (10.6 deep) at cy+13 -> front face ~cy+7.6, porch ~cy+6.5. Path along x=cx. Picket fence
    at cy+1.5 with a 4 m gate gap. Road tile (13.5 wide) centred cy-9 -> kerb at cy-2.25. Driveway at cx+5.5."""
    put("buildings", "house_gable", (cx, cy + 13, 0), -D, key="house")
    for i in range(-2, 3):
        put("city", "road_straight_2lane", (cx + i * 24, cy - 9, 0))
    if fence:
        for x in (-7, 7):
            if has("city", "fence_picket"):
                put("city", "fence_picket", (cx + x, cy + 1.5, 0), 0)
    put("city", "tree_round", (cx - 9, cy + 5, 0.15), 1.0)
    put("city", "tree_small", (cx + 10, cy + 6, 0.15), 2.0)
    put("buildings", "house_hip", (cx - 20, cy + 14, 0), -D)
    put("buildings", "cottage_1storey", (cx + 20, cy + 13.5, 0), -D)
    put("buildings", "house_gable", (cx - 14, cy - 28, 0), D)
    put("buildings", "cottage_1storey", (cx + 18, cy - 29, 0), D)
    if car:
        put("vehicles", "car_sedan", (cx + 5.5, cy - 3.2, 0), math.radians(90), key="car")
    put("city", "street_lamp", (cx - 12, cy - 2.8, 0.15), D)
    if has("symbols", "flag_ancap_porch"):
        put("symbols", "flag_ancap_porch", (cx + 3.4, cy + 7.6, 0), -D)

# ----------------------------------------------------------------------------- sets
def crowd():
    """Rows of identical obedient figures facing a podium with a megaphone; town hall behind."""
    put("buildings", "town_hall", (30, 0, 0), math.pi, key="hall")
    put("commerce", "lectern", (14, 0, 1.2), math.pi, key="lectern")
    slab("podium", (6, 8, 1.2), (14, 0, 0.6))
    if has("everyday_objects_ph", "megaphone"):
        put("everyday_objects_ph", "megaphone", (13.6, 0.0, 2.25), math.pi, 2.0, key="mega")
    put("commerce", "flag_on_pole", (16, -3.2, 1.2), 0)
    put("commerce", "flag_on_pole", (16, 3.2, 1.2), 0)
    person("Speaker", 14.2, 0, math.pi, "talk", z=1.2)
    k = 0
    for row in range(7):
        for col in range(-4, 5):
            x = 8 - row * 1.6 + rng.uniform(-0.1, 0.1)
            y = col * 1.3 + rng.uniform(-0.1, 0.1)
            person(f"C{k}", x, y, 0.0, "casual", pick=0, height=1.74)
            k += 1
    for i in range(-3, 4):
        put("city", "tree_round", (-6 + rng.uniform(-2, 2), i * 7, 0.15), rng.uniform(0, 6))


def dome():
    put("buildings", "parliament_dome", (0, 0, 0), -D, key="dome")
    for x, y in [(-30, -40), (30, -42), (-44, -20), (44, -24), (-20, -46), (18, -48)]:
        put("city", "tree_round", (x, y, 0), rng.uniform(0, 6))
    doc = put("commerce", "contract", (-10, -50, 2.0), 0, 12.0, key="doc")
    doc.rotation_euler = (math.radians(80), 0, math.radians(-170))
    plate("2ND AMENDMENT", (-10, -52.6, 1.1), math.radians(-170), 0.5, key="doclabel")
    person("D1", -13.5, -55, math.radians(70), "talk")
    person("D2", -7.0, -55.5, math.radians(110), "casual")
    person("D3", -10.5, -57, math.radians(95), "talk", age="child")
    person("Lone", -40, -70, math.radians(70), "casual")
    for i in range(6):
        person(f"V{i}", -30 + i * 9 + rng.uniform(-2, 2), -24 + rng.uniform(-4, 4), rng.uniform(0, 6.3),
               rng.choice(["casual", "walk"]))


def nap():
    """A person on their lot: house, car, belongings, the fence marking the boundary; a stranger outside it."""
    house_lot(0, 0)
    person("Owner", -1.2, 2.4, math.radians(-100), "casual")
    put("household", "tv_flatscreen", (2.2, 3.4, 0), math.radians(-100), key="tv")
    put("household", "hammer", (-2.4, 3.2, 0.0), math.radians(20))
    put("vehicles", "bicycle", (-3.6, 3.0, 0), math.radians(-80))
    person("Stranger", 0.4, -0.6, math.radians(95), "casual")
    plate("NON-AGGRESSION PRINCIPLE", (-0.4, 5.6, 2.2), -D, 0.16, key="naplabel")


def street():
    """The lot with the wrongs staged on it: thief with a TV, car thief, squatter on the lawn, a punch,
    plus (shown only on their beats) the car driving off, the house on fire, the shooting."""
    house_lot(0, 0)
    hd = math.radians(-95)
    person("Thief", 0.3, 4.5, hd, "walk")
    if has("household", "tv_boxed"):
        b = put("household", "tv_boxed", (0.3 + 0.4 * math.cos(hd), 4.5 + 0.4 * math.sin(hd), 0.62), hd, key="tvbox")
        b.rotation_euler = (math.radians(6), 0, hd)
    person("OwnerDoor", -0.9, 6.8, math.radians(-60), "talk")
    person("CarThief", 4.3, -3.0, math.radians(10), "tactical", pick=2)
    person("CarOwner", 5.0, -5.0, math.radians(0), "talk")
    if has("everyday_objects_ph", "vintage_suitcase"):
        put("everyday_objects_ph", "vintage_suitcase", (-5.3, 4.0, 0), math.radians(20), 0.9)
    put("commerce", "cardboard_box", (-3.2, 4.6, 0.45), math.radians(35))
    put("commerce", "cardboard_box_open", (-3.4, 4.4, 1.0), math.radians(10), 0.8)
    person("Squatter", -4.3, 5.0, math.radians(-70), "casual", pick=5)
    person("Puncher", -9.0, -1.2, math.radians(0), "punch")
    person("Punched", -7.9, -1.1, math.radians(180), "casual", pick=3)
    put("vehicles", "car_sedan", (14, -7.0, 0), 0, key="car_gone")
    if has("fx", "fire_patch"):
        put("fx", "fire_patch", (-1.5, 7.3, 4.8), 0, 1.2, key="fire1")
        put("fx", "fire_patch", (2.3, 7.3, 2.2), 1.0, 1.0, key="fire2")
    if has("fx", "smoke_column"):
        put("fx", "smoke_column", (0, 11, 9.0), 0, 0.3, key="smoke")
    person("Shooter", 2.0, -17.0, math.radians(90), "tactical", "held", pick=1)
    lying("Victim", 2.6, -13.5, math.radians(20))
    if has("fx", "muzzle_flash"):
        put("fx", "muzzle_flash", (2.0, -16.1, 1.3), math.radians(90), 0.8, key="flash")
    disc("blood", 0.45, (2.8, -13.3, 0.0), RED, key="blood")


def defense():
    """Homeowner at the door with a rifle; intruder on the path backing off; child beside the owner."""
    house_lot(0, 0, car=False)
    put("household", "front_door", (0, 7.3, 0), -D, key="door")
    person("Home", 0.0, 5.4, math.radians(-90), "tactical", "held", pick=0)
    person("Kid", -1.0, 5.9, math.radians(-80), "casual", age="child")
    person("Intruder", 0.3, 2.6, math.radians(90), "tactical", "one_hand", pick=3)
    person("Runner", -6, -4.5, math.radians(190), "walk", pick=2)


def basement():
    """Concrete basement: stairs, crates, a gun safe with the rifle inside, one hanging bulb."""
    slab("floor", (9, 9, 0.05), (0, 0, -0.03), (0.55, 0.54, 0.52), 0.9)
    slab("wallN", (9, 0.3, 2.6), (0, 4.5, 1.3), (0.78, 0.77, 0.75))
    slab("wallW", (0.3, 9, 2.6), (-4.5, 0, 1.3), (0.78, 0.77, 0.75))
    slab("wallE", (0.3, 9, 2.6), (4.5, 0, 1.3), (0.78, 0.77, 0.75))
    slab("ceiling", (9, 9, 0.2), (0, 0, 2.7), (0.7, 0.7, 0.68))
    put("household", "gun_safe_open", (-3.6, 2.0, 0), math.radians(0), key="safe")
    rifle_in("safe_rifle", (-3.55, 2.0, 0.55), (0, math.radians(-82), 0), key="rifle")
    if has("furniture_interior", "stairs"):
        put("furniture_interior", "stairs", (3.2, 3.0, 0), math.radians(180), 1.0, key="stairs")
    for n, (x, y, r) in [("wooden_crate", (2.5, -2.8, 20)), ("wooden_crate_02", (1.6, -3.3, -10)), ("cardboard_box", (-2.0, -3.4, 15))]:
        if has("everyday_objects_ph", n):
            put("everyday_objects_ph", n, (x, y, 0), math.radians(r))
    put("commerce", "cardboard_box", (-1.2, -3.6, 0.5), math.radians(35))
    put("commerce", "cardboard_box", (-1.4, -3.5, 1.05), math.radians(10), 0.8)
    if has("everyday_objects_ph", "wooden_ladder"):
        put("everyday_objects_ph", "wooden_ladder", (4.1, -1.0, 0), math.radians(90))
    bulb = bpy.data.objects.new("Bulb", bpy.data.lights.new("Bulb", "POINT"))
    bulb.data.energy = 600
    bulb.data.color = (1.0, 0.85, 0.65)
    bulb.data.shadow_soft_size = 0.15
    bulb.location = (-1.5, 1.0, 2.3)
    sc.collection.objects.link(bulb)
    cord = slab("cord", (0.02, 0.02, 0.5), (-1.5, 1.0, 2.45), (0.1, 0.1, 0.1))
    if has("everyday_objects_ph", "lightbulb"):
        b = put("everyday_objects_ph", "lightbulb", (-1.5, 1.0, 2.1), 0, 1.0)
        b.rotation_euler = (math.pi, 0, 0)
    # the hand that comes for it: an accent figure at the top of the stairs / at the safe
    person("Taker", -2.6, 1.4, math.radians(170), "tactical", pick=1, accent=ACCENT)


def hall():
    """Inside the front hall looking at the door; enforcers bursting in."""
    slab("floor", (6, 10, 0.05), (0, 0, -0.03), (0.5, 0.47, 0.43), 0.5)
    slab("wallL", (0.25, 10, 2.7), (-1.6, 0, 1.35), (0.84, 0.83, 0.81))
    slab("wallR", (0.25, 10, 2.7), (1.6, 0, 1.35), (0.84, 0.83, 0.81))
    slab("ceiling", (6, 10, 0.2), (0, 0, 2.8), (0.8, 0.8, 0.78))
    put("household", "front_door", (0, 3.5, 0), -D, key="door")  # door wall across the hall at y=3.5
    if has("furniture_interior", "side_table"):
        put("furniture_interior", "side_table", (-1.2, 0.5, 0), 0)
    if has("furniture_interior", "lamp_round_table"):
        put("furniture_interior", "lamp_round_table", (-1.2, 0.5, 0.75), 0)
    if has("furniture_interior", "coat_rack_standing"):
        put("furniture_interior", "coat_rack_standing", (1.2, 2.3, 0), 0)
    plate("NOTICE: SURRENDER YOUR FIREARM", (0.0, 3.3, 1.55), -D, 0.05, key="notice")
    # enforcers coming through the (open) door: we hide the door leaf by placing them in front of the wall
    person("E1", 0.1, 2.3, math.radians(-90), "tactical", "held", pick=0, accent=ACCENT)
    person("E2", -0.7, 3.2, math.radians(-80), "tactical", "held", pick=1, accent=ACCENT)
    person("E3", 0.9, 3.4, math.radians(-100), "tactical", "slung", pick=2, accent=ACCENT)
    person("Resident", 0.2, -1.6, math.radians(90), "talk", pick=2)
    sun_in = bpy.data.objects.new("Doorlight", bpy.data.lights.new("Doorlight", "AREA"))
    sun_in.data.energy = 250
    sun_in.data.size = 2.2
    sun_in.location = (0, 3.2, 1.6)
    sun_in.rotation_euler = (math.radians(90), 0, 0)
    sun_in.visible_camera = False
    sc.collection.objects.link(sun_in)


def jail():
    """A person-sized cell; the cop outside; a gavel desk for the 'law = force' beat."""
    slab("floor", (14, 14, 0.05), (0, 0, -0.03), (0.6, 0.6, 0.58), 0.9)
    cell = put("household", "jail_cell_tiny", (0, 0, 0), 0, 5.2, key="cell")
    person("Inmate", 0.2, -0.3, math.radians(-70), "casual", pick=6)
    person("Guard", -3.6, 0.6, math.radians(0), "tactical", "slung", pick=0, accent=ACCENT)
    put("commerce", "desk", (6, -6, 0), math.radians(-30), key="desk")
    put("commerce", "gavel", (6.1, -6.1, 0.758), math.radians(10), 1.5, key="gavel")
    put("commerce", "scales_of_justice", (5.4, -5.5, 0.758), math.radians(-30), 0.9)
    person("Cop1", 9.0, -3.6, math.radians(-140), "tactical", "held", pick=1, accent=ACCENT)
    person("Cop2", 10.2, -5.4, math.radians(-160), "tactical", "slung", pick=2, accent=ACCENT)
    slab("wallback", (0.3, 30, 4), (13, 0, 2), (0.8, 0.79, 0.77))


def lawn():
    """Cop walking up the path; the resident down on the lawn with a small red accent."""
    house_lot(0, 0)
    person("Cop", 0.2, -0.5, math.radians(90), "walk", "held", pick=3, accent=ACCENT)
    put("vehicles", "car_security", (-6, -7.0, 0), 0)
    lying("Down", -2.6, 4.0, math.radians(-30))
    disc("blood", 0.35, (-2.2, 3.8, 0.0), RED, key="blood")
    person("Cop2", -1.4, 5.0, math.radians(-120), "tactical", "held", pick=0, accent=ACCENT)
    person("Neighbor", 10.5, 2.5, math.radians(190), "casual")


def table():
    """A long table; objects appear one by one; an accent hand reaches for the TV."""
    slab("floor", (10, 10, 0.02), (0, 0, -0.01), (0.5, 0.47, 0.43), 0.5)
    slab("wall", (0.2, 10, 3.2), (3.5, 0, 1.6))
    slab("wallback", (10, 0.2, 3.2), (0, 4.5, 1.6))
    slab("table", (1.2, 3.6, 0.06), (0, 0, 0.78), (0.74, 0.73, 0.7), 0.4)
    for y in (-1.6, 1.6):
        slab(f"leg{y}", (0.08, 0.08, 0.75), (0, y, 0.375), (0.3, 0.3, 0.3))
    Z = 0.81
    put("household", "tv_flatscreen", (0.1, -1.2, Z), math.radians(-90), 0.55, key="i_tv")
    put("household", "car_keys", (-0.1, -0.35, Z), math.radians(20), 1.6, key="i_car")
    put("household", "hammer", (0.15, 0.25, Z), math.radians(-25), 1.2, key="i_this")
    put("household", "book", (-0.2, 0.85, Z), math.radians(15), 1.3, key="i_that")
    put("commerce", "smartphone", (0.2, 1.35, Z), math.radians(-10), 1.4, key="i_other")
    put("household", "rifle_prop", (-0.35, 0.3, Z), math.radians(95), 0.9, key="i_rifle")
    person("Reacher", -0.95, -1.2, math.radians(0), "reach", accent=ACCENT)
    plate("NON-AGGRESSION PRINCIPLE", (0, 1.95, 1.05), -D, 0.07, key="tableplate")
    person("Owner", 1.8, 0.6, math.radians(180), "casual", pick=1)


def kid():
    """A child at a school desk; chalkboard behind reads the whole philosophy."""
    slab("floor", (10, 10, 0.02), (0, 0, -0.01), (0.5, 0.47, 0.43), 0.5)
    slab("wall", (0.2, 10, 3.2), (3.0, 0, 1.6))
    put("everyday_objects_ph", "schooldesk", (0, 0, 0), math.radians(180), key="desk")
    put("everyday_objects_ph", "schoolchair", (-0.7, 0, 0), math.radians(180))
    person("Pupil", -0.55, 0.0, math.radians(180), "casual", age="child", pick=2)
    slab("board", (0.08, 2.2, 1.4), (2.6, 0.2, 1.55), (0.13, 0.18, 0.15), 0.8, key="board")
    slab("boardframe", (0.06, 2.4, 1.6), (2.66, 0.2, 1.55), (0.45, 0.33, 0.22), 0.6)
    plate("DON'T HIT.  DON'T STEAL.", (2.5, 0.2, 1.7), math.radians(180), 0.09, key="rule")
    put("household", "book", (0.0, 0.1, 0.78), math.radians(5), 1.0)


def own():
    """A person in their yard with everything they own around them (and the donkey)."""
    house_lot(0, 0, car=False)
    person("Me", 0.0, 2.8, math.radians(-90), "casual", pick=1)
    put("household", "tv_flatscreen", (2.0, 3.6, 0), math.radians(-120))
    put("household", "rifle_prop", (1.2, 1.9, 0.0), math.radians(60))
    put("household", "hammer", (-1.0, 1.8, 0.0), math.radians(20))
    put("vehicles", "motorbike", (-3.5, 2.6, 0), math.radians(-110))
    put("vehicles", "bicycle", (3.8, 2.6, 0), math.radians(-80))
    put("vehicles", "car_pickup", (5.5, -2.8, 0), math.radians(90))
    if has("household", "donkey"):
        put("household", "donkey", (-2.4, 5.4, 0), math.radians(-60))
    put("commerce", "gold_bar", (0.9, 3.4, 0.0), 0, 1.5)
    put("commerce", "cash_stack", (-0.6, 3.6, 0.0), 0, 1.6)
    if has("symbols", "flag_ancap_pole"):
        put("symbols", "flag_ancap_pole", (-5.2, 5.4, 0), 0, 0.8)
    person("Partner", 1.4, 4.8, math.radians(-110), "talk", pick=4)
    person("Child", -1.2, 5.0, math.radians(-70), "casual", age="child")


SETS = dict(crowd=crowd, dome=dome, nap=nap, street=street, defense=defense, basement=basement, hall=hall,
            jail=jail, lawn=lawn, table=table, kid=kid, own=own)
INTERIOR = {"basement", "hall", "table", "kid", "jail"}

if SPEC["set"] not in INTERIOR:
    ground()
SETS[SPEC["set"]]()

# ----------------------------------------------------------------------------- sky, sun
w = bpy.data.worlds.new("Sky")
sc.world = w
w.use_nodes = True
elev, rot = SPEC.get("sun") or (22, 140)
sky = w.node_tree.nodes.new("ShaderNodeTexSky")
sky.sky_type = "NISHITA"
sky.sun_elevation = math.radians(elev)
sky.sun_rotation = math.radians(rot)
sky.sun_disc = False
w.node_tree.links.new(sky.outputs[0], w.node_tree.nodes["Background"].inputs[0])
w.node_tree.nodes["Background"].inputs[1].default_value = 0.12 if SPEC["set"] in INTERIOR else 0.18
sun = bpy.data.objects.new("Sun", bpy.data.lights.new("Sun", "SUN"))
sc.collection.objects.link(sun)
sun.data.energy = 2.5 if SPEC["set"] in INTERIOR else 6.0
sun.data.color = (1.0, 0.9, 0.78)
sun.data.angle = math.radians(1.5)
sun.rotation_euler = (math.radians(90 - elev - 2), 0, math.radians(rot - 190))
if SPEC["set"] in INTERIOR:
    fill = bpy.data.objects.new("Fill", bpy.data.lights.new("Fill", "AREA"))
    fill.data.energy = 150
    fill.data.size = 6
    fill.location = (0, 0, 2.5)
    fill.rotation_euler = (0, 0, 0)
    sc.collection.objects.link(fill)

# ----------------------------------------------------------------------------- camera: one setup per beat
cam = bpy.data.objects.new("Cam", bpy.data.cameras.new("Cam"))
sc.collection.objects.link(cam)
sc.camera = cam
cam.data.clip_end = 3000
cam.data.dof.use_dof = True
tgt = bpy.data.objects.new("CamTarget", None)
sc.collection.objects.link(tgt)
con = cam.constraints.new("TRACK_TO")
con.target = tgt
con.track_axis = "TRACK_NEGATIVE_Z"
con.up_axis = "UP_Y"
cam.data.dof.focus_object = None


def key(idb, path, frame, value, interp, idx=-1):
    """Keyframe idb.<path> (path may be dotted, e.g. 'dof.focus_distance') and set its interpolation."""
    owner, attr = (idb.path_resolve(path.rsplit(".", 1)[0]), path.rsplit(".", 1)[1]) if "." in path else (idb, path)
    if idx >= 0:
        getattr(owner, attr)[idx] = value
    else:
        setattr(owner, attr, value)
    idb.keyframe_insert(path, frame=frame, index=idx)
    fc = idb.animation_data.action.fcurves.find(path, index=max(idx, 0))
    if fc:
        k = fc.keyframe_points[-1]
        k.interpolation = interp
        k.easing = "EASE_IN_OUT"


def resolve(p):
    if isinstance(p, str):
        o = NAMED.get(p) or bpy.data.objects.get(p)
        if o is None:
            print("WARN focus object missing", p)
            return None
        return o.matrix_world.translation.copy() + Vector((0, 0, 0.0))
    return Vector(p)


beats = SPEC["beats"]
for b in beats:
    f0, f1 = b["frame_start"], b["frame_end"]
    c0, c1 = Vector(b["cam"][0]), Vector(b["cam"][1])
    l0, l1 = Vector(b["look"][0]), Vector(b["look"][1])
    for f, c, l, interp in ((f0, c0, l0, "BEZIER"), (f1, c1, l1, "CONSTANT")):
        for i in range(3):
            key(cam, "location", f, c[i], interp, i)
            key(tgt, "location", f, l[i], interp, i)
    key(cam.data, "lens", f0, float(b.get("lens", 40)), "CONSTANT")
    fstop = b.get("fstop")
    key(cam.data, "dof.aperture_fstop", f0, float(fstop) if fstop else 22.0, "CONSTANT")
    foc = b.get("focus")
    rack = isinstance(foc, list) and len(foc) == 2 and all(isinstance(x, (str, list)) for x in foc)
    for f, c, l in ((f0, c0, l0), (f1, c1, l1)):
        fc_ = (foc[0] if f == f0 else foc[1]) if rack else foc
        fp = resolve(fc_) if fc_ else l
        dist = (fp - c).length if fp is not None else 10.0
        key(cam.data, "dof.focus_distance", f, dist, "BEZIER" if f == f0 else "CONSTANT")

# show/hide windows: {"name": [[f0, f1], ...]}; an object listed anywhere is hidden outside its windows
shows = {}
for b in beats:
    for name, wins in (b.get("show") or {}).items():
        shows.setdefault(name, []).extend(wins)
first, last = beats[0]["frame_start"], beats[-1]["frame_end"]


def set_hidden(o, frame, hidden):
    for ob in [o] + list(o.children_recursive):
        ob.hide_render = hidden
        ob.hide_viewport = hidden
        ob.keyframe_insert("hide_render", frame=frame)
        ob.keyframe_insert("hide_viewport", frame=frame)


for name, wins in shows.items():
    o = NAMED.get(name) or bpy.data.objects.get(name)
    if o is None:
        print("WARN show target missing", name)
        continue
    set_hidden(o, first - 1, True)
    for a, z in sorted(wins):
        set_hidden(o, a, False)
        set_hidden(o, z + 1, True)

sc.frame_start, sc.frame_end = first, last
sc.render.fps = FPS

# ----------------------------------------------------------------------------- render settings, save, storyboard
r = sc.render
r.engine = "BLENDER_EEVEE_NEXT"
r.resolution_x, r.resolution_y, r.resolution_percentage = 1920, 1080, 100
e = sc.eevee
e.taa_render_samples = 32
e.use_shadows = True
for k, v in (("use_raytracing", True), ("ray_tracing_method", "SCREEN"), ("use_fast_gi", True)):
    if hasattr(e, k):
        setattr(e, k, v)
sc.view_settings.view_transform = "AgX"
sc.view_settings.look = "AgX - Medium High Contrast"
r.image_settings.file_format = "PNG"
r.filepath = "//frames/f_"
bpy.ops.file.pack_all()
try:
    from mhuman import purge_mpfb_data
    purge_mpfb_data()
except Exception as ex:
    print("WARN purge", ex)
blend = os.path.join(OUT, f"{SPEC['id']}.blend")
bpy.ops.wm.save_as_mainfile(filepath=blend, compress=True)
print("SAVED", blend, round(os.path.getsize(blend) / 1e6), "MB")

if PCT > 0:
    r.engine = "CYCLES"
    sc.cycles.samples = 12
    sc.cycles.use_denoising = True
    r.resolution_percentage = PCT
    sb = os.path.join(OUT, "storyboard")
    os.makedirs(sb, exist_ok=True)
    for b in beats:
        mid = (b["frame_start"] + b["frame_end"]) // 2
        sc.frame_set(mid)
        r.filepath = os.path.join(sb, f"beat_{int(b['id']):02d}.png")
        bpy.ops.render.render(write_still=True)
        print("STILL", r.filepath)
