"""Scene builders for episode shots (run inside Blender by episode.py).

blender -b --factory-startup -P episode_scenes.py -- shot.json out_dir preview_res_percent
Each builder fills the scene (library assets + people), then common code adds ground, sky, sun,
the camera move from the shot spec, EEVEE settings, saves <id>.blend and renders a mid preview.
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
PCT = int(argv[2]) if len(argv) > 2 else 50
ACCENT = (0.95, 0.38, 0.06)
GOLD = (1.0, 0.8, 0.0)
FONT = "/usr/share/fonts/opentype/inter/Inter-Bold.otf"
D = math.pi / 2
rng = random.Random(SPEC["id"])

bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene


def has(cat, name):
    try:
        asset(cat, name)
        return True
    except Exception as e:
        print("WARN missing asset", cat, name, e)
        return False


def person(name, x, y, hd, mode="casual", weapon=None, **kw):
    p = make_person(name, mode=mode, weapon=weapon, **kw)
    p.location = (x, y, 0)
    p.rotation_euler = (0, 0, hd)
    return p


def label(text, loc, rot_z=0, size=0.12, col=(0.03, 0.03, 0.035)):
    plate = box(f"lbl_{text}", (0.012, size * 0.62 * len(text) + size * 0.9, size * 1.9), loc, None, min(0.012, size * 0.2),
                pbr("LIB_Body", (0.82, 0.81, 0.79), rough=0.5))
    plate.rotation_euler = (0, 0, rot_z)
    t = text_decal(f"txt_{text}", text, size, pbr("LIB_Dark", col, rough=0.5), (0.013, 0, 0),
                   (D, 0, D), None, font=FONT)
    t.parent = plate
    return plate


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
    n2 = nt.nodes.new("ShaderNodeTexNoise")
    n2.inputs["Scale"].default_value = 3.0
    n2.inputs["Detail"].default_value = 8
    nt.links.new(tc.outputs["Object"], n2.inputs["Vector"])
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.2
    nt.links.new(n2.outputs["Fac"], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], b.inputs["Normal"])
    b.inputs["Roughness"].default_value = 0.9
    g.data.materials.append(m)
    return g


def town(center=(0, 0), people=True):
    """The library street used in the benchmark: shops, bank, towers, trees, cars, people."""
    cx, cy = center
    for i in range(-4, 5):
        place("city", "road_straight_2lane", (cx + i * 24, cy, 0))
    north = ["bank_classical", "storefront_shop", "corner_cafe", "storefront_market", "office_midrise", "terraced_row"]
    south = ["apartment_block", "storefront_shop", "house_gable", "office_tower_punched", "storefront_market", "house_hip"]
    x = cx - 60
    for n in north:
        place("buildings", n, (x, cy + 22, 0), -D)
        x += 26
    x = cx - 55
    for n in south:
        place("buildings", n, (x, cy - 22, 0), D)
        x += 24
    for k, n in enumerate(["skyscraper_deco", "office_tower_curtain", "skyscraper_spire", "apartment_tall"]):
        place("buildings", n, (cx - 40 + k * 45, cy + 75, 0), -D)
    for i in range(-5, 6):
        place("city", rng.choice(["tree_round", "tree_small", "tree_wide"]), (cx + i * 12 + 4, cy + 9.2, 0.15), rng.uniform(0, 6))
        place("city", rng.choice(["tree_round", "tree_small"]), (cx + i * 12 - 2, cy - 9.2, 0.15), rng.uniform(0, 6))
        if i % 2 == 0:
            place("city", "street_lamp", (cx + i * 12, cy + 7.2, 0.15), -D)
            place("city", "street_lamp", (cx + i * 12 + 6, cy - 7.2, 0.15), D)
    for (n, x_, y_, r) in [("car_sedan", -30, -2.0, 0), ("car_taxi", -8, 2.0, math.pi), ("bus_city", 18, -2.0, 0),
                           ("van_delivery", 40, 2.0, math.pi), ("car_suv", 60, -2.0, 0), ("car_hatchback", -70, -2.0, 0)]:
        place("vehicles", n, (cx + x_, cy + y_, 0), r)
    if has("symbols", "flag_ancap_pole"):
        place("symbols", "flag_ancap_pole", (cx - 48, cy + 11, 0.15))
    if people:
        spots = [(-20, 8.0, -1.6, "walk"), (-16, 8.4, -1.5, "talk"), (-15, 7.8, 2.0, "talk"), (-6, 8.6, -2.5, "casual"),
                 (0, 7.9, 3.0, "casual"), (6, 8.2, -1.6, "walk"), (12, -8.3, 1.4, "casual"), (9, -8.8, 1.7, "talk"),
                 (20, -8.0, 1.6, "walk"), (-30, -8.5, 0.0, "walk"), (-34, -8.0, 3.1, "walk"), (30, 8.3, 3.0, "casual")]
        for k, (x_, y_, hd, mode) in enumerate(spots):
            p = person(f"T{k}", cx + x_, cy + y_, hd, mode, age="child" if k in (3, 9) else "adult")
            p.location.z = 0.15


# ----------------------------------------------------------------------------- shots
def hook():
    """Classical government dome at golden hour; a floating '2ND AMENDMENT' document in front."""
    place("buildings", "parliament_dome", (0, 0, 0), -D)
    for i in range(-3, 4):
        place("city", "tree_round", (-30 + i * 2 * rng.uniform(1, 4), -30 + rng.uniform(-6, 6), 0), rng.uniform(0, 6))
    doc = place("commerce", "contract", (-88, -52, 14), 0)
    doc.rotation_euler = (math.radians(75), 0, math.radians(-120))
    doc.scale = (22, 22, 22)
    label("2ND AMENDMENT", (-86, -53.5, 10.5), math.radians(-120), 0.9)
    for k in range(6):
        person(f"H{k}", -20 + k * 4, -22 + rng.uniform(-3, 3), rng.uniform(-3, 3), rng.choice(["casual", "walk"]))


def paper():
    """A desk: the document, a gavel, a stack of papers; a second paper slides over the first (static here)."""
    place("commerce", "desk", (0, 0, 0))
    place("commerce", "office_chair", (-1.7, 1.0, 0), math.radians(35))
    Z = 0.758
    d1 = place("commerce", "contract", (0.1, 0.1, Z), math.radians(8), 1.3)
    d2 = place("commerce", "contract", (0.22, 0.02, Z + 0.004), math.radians(-14), 1.3)
    place("commerce", "gavel", (0.2, -0.45, Z), math.radians(20))
    place("commerce", "document_stack", (-0.1, 0.45, Z), math.radians(-5))
    if has("household", "hall_pass"):
        place("household", "hall_pass", (0.55, -0.22, Z), math.radians(-35))
    if has("symbols", "flag_ancap_desk"):
        place("symbols", "flag_ancap_desk", (-0.45, 0.42, Z), math.radians(-20))
    box("wall", (0.2, 8, 3.2), (-2.5, 0, 1.6), None, 0.02, pbr("LIB_Body", (0.82, 0.81, 0.79), rough=0.6))
    box("floor", (8, 8, 0.02), (0, 0, -0.01), None, 0, pbr("FloorWood", (0.5, 0.47, 0.43), rough=0.5))


def tv_shop():
    """Storefront; a person carries a boxed TV out; a couple more shoppers about."""
    place("buildings", "storefront_shop", (0, 3, 0), -D)
    place("buildings", "storefront_market", (14, 3, 0), -D)
    place("buildings", "corner_cafe", (-14, 3, 0), -D)
    for i in range(-2, 3):
        place("city", "road_straight_2lane", (i * 24, -12, 0))
    place("city", "tree_round", (-7, -3, 0.15), 1.0)
    place("city", "tree_small", (8, -3.5, 0.15), 2.0)
    place("city", "street_lamp", (4, -4, 0.15), D)
    hd = math.radians(-110)
    buyer = person("Buyer", 0.6, -2.0, hd, "walk")
    if has("household", "tv_boxed"):  # carried in front of the chest, long side across the body
        b = place("household", "tv_boxed", (0.6 + 0.4 * math.cos(hd), -2.0 + 0.4 * math.sin(hd), 0.62), hd)
        b.rotation_euler = (math.radians(6), 0, hd)
    else:
        place("commerce", "cardboard_box", (1.2, -2.4, 0.5), math.radians(30))
    person("Shop1", -4, -5.5, math.radians(20), "talk")
    person("Shop2", -4.8, -4.8, math.radians(-150), "casual")
    person("Shop3", 7, -6, math.radians(170), "walk", age="child")
    person("Shop4", 6.2, -5.4, math.radians(170), "walk")
    place("vehicles", "car_sedan", (-20, -10, 0), 0)


def door():
    """Suburban street; a small group in accent gear walks up to a house with a porch flag."""
    place("buildings", "house_gable", (4, 6, 0), -D)
    place("buildings", "house_hip", (-14, 7, 0), -D)
    place("buildings", "cottage_1storey", (22, 6.5, 0), -D)
    place("buildings", "house_gable", (-14, -16, 0), D)
    place("buildings", "cottage_1storey", (20, -24, 0), D)
    for i in range(-2, 3):
        place("city", "road_straight_2lane", (i * 24, -6, 0))
    for x in (-8, 22, 30):
        place("city", "tree_round", (x, 0.5, 0.15), rng.uniform(0, 6))
    place("city", "street_lamp", (-14, -1.0, 0.15), D)
    for x in (-8, -4, 12, 16):
        place("city", "fence_picket", (x, 2.5, 0), 0) if has("city", "fence_picket") else None
    if has("symbols", "flag_ancap_porch"):
        place("symbols", "flag_ancap_porch", (4 - 0.1, 2.8, 0), -D)
    # three enforcers on the walk, one knocking distance away; a neighbour watching
    person("E1", 2.6, -2.2, math.radians(80), "walk", "held", accent=ACCENT)
    person("E2", 4.6, -3.4, math.radians(95), "walk", "slung", accent=ACCENT)
    person("E3", 3.4, -4.6, math.radians(85), "walk", "held", accent=ACCENT)
    person("N1", -10, 0.5, math.radians(10), "casual")
    place("vehicles", "car_security", (-2, -8.2, 0), 0)


def table():
    """A table with a rifle, a hammer, a knife and car keys, each labelled; the hammer in a tiny jail cell."""
    place("commerce", "desk", (0, 0, 0))
    box("floor", (8, 8, 0.02), (0, 0, -0.01), None, 0, pbr("FloorWood", (0.5, 0.47, 0.43), rough=0.5))
    gun = pbr("FigGun", (0.035, 0.037, 0.04), rough=0.45)
    g = carbine("rifle", sc.collection, gun)
    g.location = (-0.15, -0.05, 0.775)
    g.rotation_euler = (0, 0, math.radians(-20))
    items = [("hammer", (-0.25, 0.5), 20), ("kitchen_knife", (0.4, -0.42), -35), ("car_keys", (0.42, 0.3), 0)]
    for n, (x, y), r in items:
        if has("household", n):
            place("household", n, (x, y, 0.758), math.radians(r))
        else:
            box(n, (0.3, 0.06, 0.04), (x, y, 0.778), None, 0.01, gun)
    if has("household", "jail_cell_tiny"):
        place("household", "jail_cell_tiny", (-0.25, 0.5, 0.758), math.radians(-10))
    for text, (x, y) in [("RIFLE", (-0.5, -0.25)), ("HAMMER", (-0.55, 0.72)), ("KNIFE", (0.2, -0.68)), ("CAR KEYS", (0.2, 0.52))]:
        label(text, (x, y, 0.86), math.radians(-5), 0.03)


def town_shot():
    town()


def donkey():
    """A paddock; the donkey (placeholder box until the household library lands) looks back at us."""
    ground((0.5, 0.52, 0.42))
    for i in range(-4, 5):
        place("city", "fence_picket", (i * 4, 4, 0), 0) if has("city", "fence_picket") else None
    place("city", "tree_wide", (-14, 13, 0), 0.5)
    place("city", "tree_round", (11, 10, 0), 2.0)
    place("buildings", "farm_barn_silo", (18, 14, 0), math.radians(-110))
    if has("household", "donkey_grazing"):
        place("household", "donkey_grazing", (5, 6, 0), math.radians(150))
    if has("household", "donkey"):
        place("household", "donkey", (0, 0, 0), math.radians(35))
    else:
        box("donkey_placeholder", (1.4, 0.5, 1.0), (0, 0, 0.8), None, 0.1, pbr("LIB_Body", (0.82, 0.81, 0.79)))


BUILDERS = dict(hook=hook, paper=paper, tv_shop=tv_shop, door=door, table=table, town=town_shot, donkey=donkey)
if SPEC["scene"] != "donkey":
    ground()
BUILDERS[SPEC["scene"]]()

# ----------------------------------------------------------------------------- common: sky, sun, camera, render
w = bpy.data.worlds.new("Sky")
sc.world = w
w.use_nodes = True
sky = w.node_tree.nodes.new("ShaderNodeTexSky")
sky.sky_type = "NISHITA"
sky.sun_elevation = math.radians(22)
sky.sun_rotation = math.radians(140)
sky.sun_disc = False
w.node_tree.links.new(sky.outputs[0], w.node_tree.nodes["Background"].inputs[0])
w.node_tree.nodes["Background"].inputs[1].default_value = 0.18
sun = bpy.data.objects.new("Sun", bpy.data.lights.new("Sun", "SUN"))
sc.collection.objects.link(sun)
sun.data.energy = 6.0
sun.data.color = (1.0, 0.9, 0.78)
sun.data.angle = math.radians(1.5)
sun.rotation_euler = (math.radians(66), 0, math.radians(-50))

cam = bpy.data.objects.new("Cam", bpy.data.cameras.new("Cam"))
sc.collection.objects.link(cam)
sc.camera = cam
cam.data.lens = SPEC["lens"]
cam.data.clip_end = 3000
tgt = bpy.data.objects.new("CamTarget", None)
sc.collection.objects.link(tgt)
con = cam.constraints.new("TRACK_TO")
con.target = tgt
con.track_axis = "TRACK_NEGATIVE_Z"
con.up_axis = "UP_Y"
f0, f1 = SPEC["frame_start"], SPEC["frame_end"]
for f, c, l in ((f0, SPEC["cam"][0], SPEC["look"][0]), (f1, SPEC["cam"][1], SPEC["look"][1])):
    cam.location = c
    cam.keyframe_insert("location", frame=f)
    tgt.location = l
    tgt.keyframe_insert("location", frame=f)
for o in (cam, tgt):
    for fc in o.animation_data.action.fcurves:
        for k in fc.keyframe_points:
            k.interpolation = "BEZIER"
            k.easing = "EASE_IN_OUT"
sc.frame_start, sc.frame_end = f0, f1
sc.render.fps = 24

r = sc.render
r.engine = "BLENDER_EEVEE_NEXT"
r.resolution_x, r.resolution_y, r.resolution_percentage = 1920, 1080, 100
e = sc.eevee
e.taa_render_samples = 24
e.use_shadows = True
for k, v in (("use_raytracing", True), ("ray_tracing_method", "SCREEN"), ("use_fast_gi", True)):
    if hasattr(e, k):
        setattr(e, k, v)
sc.view_settings.view_transform = "AgX"
sc.view_settings.look = "AgX - Medium High Contrast"
r.image_settings.file_format = "PNG"
r.filepath = f"//frames/f_"
bpy.ops.file.pack_all()
blend = os.path.join(OUT, f"{SPEC['id']}.blend")
bpy.ops.wm.save_as_mainfile(filepath=blend, compress=True)
print("SAVED", blend, round(os.path.getsize(blend) / 1e6), "MB")
# preview (Cycles is faster than software-EEVEE here; final frames come from the GPU box)
mid = (f0 + f1) // 2
sc.frame_set(mid)
r.engine = "CYCLES"
sc.cycles.samples = 12
sc.cycles.use_denoising = True
r.resolution_percentage = PCT
r.filepath = os.path.join(OUT, f"{SPEC['id']}_preview.png")
bpy.ops.render.render(write_still=True)
print("PREVIEW", r.filepath)
