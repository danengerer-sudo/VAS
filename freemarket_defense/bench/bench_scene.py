"""Build the render benchmark: a white-style town street (library assets + MakeHuman people),
EEVEE settings, a 48-frame camera dolly. Saves bench.blend (self-contained)."""
import os, sys, math, random
import bpy
from mathutils import Vector
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))
sys.path.insert(0, os.path.join(HERE, "..", "library", "scripts"))
from libload import place
from lib import pbr

bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene
rng = random.Random(4)
D = math.pi / 2

# ground: warm light grey, procedural mottling + fine relief (no image textures)
me = bpy.data.meshes.new("Ground")
s = 400
me.from_pydata([(-s, -s, -0.02), (s, -s, -0.02), (s, s, -0.02), (-s, s, -0.02)], [], [(0, 1, 2, 3)])
g = bpy.data.objects.new("Ground", me); sc.collection.objects.link(g)
m = bpy.data.materials.new("BenchGround"); m.use_nodes = True
nt = m.node_tree; b = nt.nodes["Principled BSDF"]
tc = nt.nodes.new("ShaderNodeTexCoord"); n1 = nt.nodes.new("ShaderNodeTexNoise")
n1.inputs["Scale"].default_value = 0.05; nt.links.new(tc.outputs["Object"], n1.inputs["Vector"])
rmp = nt.nodes.new("ShaderNodeValToRGB")
rmp.color_ramp.elements[0].color = (0.46, 0.45, 0.42, 1); rmp.color_ramp.elements[1].color = (0.56, 0.55, 0.52, 1)
nt.links.new(n1.outputs["Fac"], rmp.inputs["Fac"]); nt.links.new(rmp.outputs["Color"], b.inputs["Base Color"])
n2 = nt.nodes.new("ShaderNodeTexNoise"); n2.inputs["Scale"].default_value = 3.0; n2.inputs["Detail"].default_value = 8
nt.links.new(tc.outputs["Object"], n2.inputs["Vector"])
bump = nt.nodes.new("ShaderNodeBump"); bump.inputs["Strength"].default_value = 0.25
nt.links.new(n2.outputs["Fac"], bump.inputs["Height"]); nt.links.new(bump.outputs["Normal"], b.inputs["Normal"])
b.inputs["Roughness"].default_value = 0.9
g.data.materials.append(m)

# street along X
for i in range(-4, 5):
    place("city", "road_straight_2lane", (i * 24, 0, 0))
north = [("buildings", "bank_classical"), ("buildings", "storefront_shop"), ("buildings", "corner_cafe"),
         ("buildings", "storefront_market"), ("buildings", "office_midrise"), ("buildings", "terraced_row")]
south = [("buildings", "apartment_block"), ("buildings", "storefront_shop"), ("buildings", "house_gable"),
         ("buildings", "office_tower_punched"), ("buildings", "storefront_market"), ("buildings", "house_hip")]
x = -60
for cat, n in north:
    place(cat, n, (x, 22, 0), -D); x += 26
x = -55
for cat, n in south:
    place(cat, n, (x, -22, 0), D); x += 24
for k, (cat, n) in enumerate([("buildings", "skyscraper_deco"), ("buildings", "office_tower_curtain"),
                              ("buildings", "skyscraper_spire"), ("buildings", "apartment_tall")]):
    place(cat, n, (-40 + k * 45, 75, 0), -D)
for i in range(-5, 6):
    place("city", rng.choice(["tree_round", "tree_small", "tree_wide"]), (i * 12 + 4, 9.2, 0.15), rng.uniform(0, 6))
    place("city", rng.choice(["tree_round", "tree_small"]), (i * 12 - 2, -9.2, 0.15), rng.uniform(0, 6))
    if i % 2 == 0:
        place("city", "street_lamp", (i * 12, 7.2, 0.15), -D)
        place("city", "street_lamp", (i * 12 + 6, -7.2, 0.15), D)
place("city", "bus_stop", (8, -8.0, 0.15), D)
place("city", "bench", (-14, 8.0, 0.15), -D)
place("commerce", "market_stall", (-2, 9.5, 0.15), -D)
place("commerce", "atm", (-58, 12.2, 0.15), -D)
for (n, x_, y_, r) in [("car_sedan", -30, -2.0, 0), ("car_taxi", -8, 2.0, math.pi), ("bus_city", 18, -2.0, 0),
                       ("truck_armored_cit", -52, 2.0, math.pi), ("van_delivery", 40, 2.0, math.pi),
                       ("car_suv", 60, -2.0, 0), ("car_hatchback", -70, -2.0, 0)]:
    place("vehicles", n, (x_, y_, 0), r)

# people (MakeHuman, baked)
try:
    from mhuman import make_person
    C = bpy.data.collections.new("People"); sc.collection.children.link(C)
    spots = [(-20, 8.0, -1.6, "walk"), (-16, 8.4, -1.5, "talk"), (-15, 7.8, 2.0, "talk"), (-6, 8.6, -2.5, "casual"),
             (0, 7.9, 3.0, "casual"), (6, 8.2, -1.6, "walk"), (12, -8.3, 1.4, "casual"), (9, -8.8, 1.7, "talk"),
             (20, -8.0, 1.6, "walk"), (-30, -8.5, 0.0, "walk"), (-34, -8.0, 3.1, "walk"), (30, 8.3, 3.0, "casual"),
             (-45, 8.0, -1.6, "walk"), (45, -8.3, 1.5, "talk")]
    for k, (x_, y_, hd, mode) in enumerate(spots):
        age = "child" if k in (3, 9) else "adult"
        p = make_person(f"P{k}", None, age, None, mode, None, coll=C)
        p.location = (x_, y_, 0.15); p.rotation_euler = (0, 0, hd)
except Exception as e:
    print("PEOPLE SKIPPED", e)

# light: low warm sun + Nishita sky for fill
w = bpy.data.worlds.new("Sky"); sc.world = w; w.use_nodes = True
sky = w.node_tree.nodes.new("ShaderNodeTexSky"); sky.sky_type = "NISHITA"
sky.sun_elevation = math.radians(24); sky.sun_rotation = math.radians(140); sky.sun_disc = False
w.node_tree.links.new(sky.outputs[0], w.node_tree.nodes["Background"].inputs[0])
w.node_tree.nodes["Background"].inputs[1].default_value = 0.18
sun = bpy.data.objects.new("Sun", bpy.data.lights.new("Sun", "SUN")); sc.collection.objects.link(sun)
sun.data.energy = 6.0; sun.data.color = (1.0, 0.9, 0.78); sun.data.angle = math.radians(1.5)
sun.rotation_euler = (math.radians(66), 0, math.radians(-50))

# camera: slow dolly down the street
cam = bpy.data.objects.new("Cam", bpy.data.cameras.new("Cam")); sc.collection.objects.link(cam); sc.camera = cam
cam.data.lens = 28
tgt = bpy.data.objects.new("CamTarget", None); sc.collection.objects.link(tgt)
con = cam.constraints.new("TRACK_TO"); con.target = tgt; con.track_axis = "TRACK_NEGATIVE_Z"; con.up_axis = "UP_Y"
for f, cl, tl in ((1, (-42, -4.5, 3.2), (-8, 5, 3.0)), (48, (-38, -4.0, 3.3), (-4, 5.5, 3.0))):
    cam.location = cl; cam.keyframe_insert("location", frame=f)
    tgt.location = tl; tgt.keyframe_insert("location", frame=f)
for o in (cam, tgt):
    for fc in o.animation_data.action.fcurves:
        for k in fc.keyframe_points:
            k.interpolation = "LINEAR"
sc.frame_start, sc.frame_end = 1, 48
sc.render.fps = 24

# render settings: EEVEE (Next) 1080p
r = sc.render
r.engine = "BLENDER_EEVEE_NEXT"
r.resolution_x, r.resolution_y, r.resolution_percentage = 1920, 1080, 100
e = sc.eevee
e.taa_render_samples = 32
e.use_shadows = True
e.shadow_ray_count = 2
e.shadow_step_count = 6
for k, v in (("use_raytracing", True), ("ray_tracing_method", "SCREEN"), ("use_fast_gi", True),
             ("fast_gi_method", "GLOBAL_ILLUMINATION"), ("use_volumetric_shadows", False)):
    if hasattr(e, k):
        setattr(e, k, v)
if hasattr(e, "ray_tracing_options"):
    e.ray_tracing_options.use_denoise = True
sc.view_settings.view_transform = "AgX"
sc.view_settings.look = "AgX - Medium High Contrast"
r.image_settings.file_format = "PNG"
r.filepath = "//out/frame_"
bpy.ops.file.pack_all()
bpy.ops.wm.save_as_mainfile(filepath=os.path.join(HERE, "bench.blend"), compress=True)
print("SAVED", os.path.getsize(os.path.join(HERE, "bench.blend")) // 1e6, "MB")
