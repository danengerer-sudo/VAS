"""Style test: re-skin the existing scene as a white 'architectural model' diorama.

- every surface matte white (bevel-normal detail kept, image textures dropped)
- faction colour only on livery (Sentinel orange, Aegis blue, Tidewater teal)
- soldiers become jointed mannequins with block rifles (same rig + IK)
- pale sky, low warm sun, mist for depth

blender -b render/scene.blend -P scripts/style_white.py -- OUT_PREFIX frame,frame,...
"""
import sys
import os
import math
import bpy
from mathutils import Vector, Matrix

sys.path.insert(0, os.path.dirname(__file__))
from lib import lathe, box, cylinder, pbr, link

argv = sys.argv[sys.argv.index("--") + 1:]
OUT = argv[0]
FRAMES = [int(f) for f in argv[1].split(",")]
sc = bpy.context.scene

WHITE = (0.82, 0.81, 0.79)
CHARCOAL = (0.035, 0.037, 0.04)
ACCENTS = {"Tank_Decal": (0.95, 0.38, 0.06), "SENTINEL_Accent": (0.95, 0.38, 0.06),
           "Heli_Decal": (0.06, 0.32, 0.9), "Boat_Decal": (0.0, 0.5, 0.42),
           "NavRed": (0.8, 0.02, 0.02), "NavGreen": (0.02, 0.6, 0.05)}
DARK = {"DecalWhite", "SignText"}
GLASS_LIKE = ("Glass",)


def flat(bsdf, col, rough=0.62):
    for name in ("Base Color", "Roughness", "Emission Color", "Emission Strength", "Specular IOR Level",
                 "Metallic", "Coat Weight", "Transmission Weight"):
        for l in list(bsdf.inputs[name].links):
            bsdf.id_data.links.remove(l)
    bsdf.inputs["Base Color"].default_value = (*col, 1)
    bsdf.inputs["Roughness"].default_value = rough
    bsdf.inputs["Metallic"].default_value = 0.0
    bsdf.inputs["Specular IOR Level"].default_value = 0.35
    bsdf.inputs["Emission Strength"].default_value = 0.0
    bsdf.inputs["Coat Weight"].default_value = 0.0
    bsdf.inputs["Transmission Weight"].default_value = 0.0
    # keep bevel-node normals (crisp edges); drop image normal maps
    for l in list(bsdf.inputs["Normal"].links):
        if l.from_node.type != "BEVEL":
            bsdf.id_data.links.remove(l)


for m in bpy.data.materials:
    if not m.use_nodes:
        continue
    bs = [n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED"]
    if not bs:
        continue
    b = bs[0]
    if m.name in ("Ground", "Water", "Wake"):
        continue
    if m.name in ACCENTS:
        flat(b, ACCENTS[m.name], 0.55)
        if m.name.startswith("Nav"):
            b.inputs["Emission Color"].default_value = (*ACCENTS[m.name], 1)
            b.inputs["Emission Strength"].default_value = 4.0
    elif m.name in DARK:
        flat(b, CHARCOAL, 0.6)
    elif any(g in m.name for g in GLASS_LIKE):
        flat(b, (0.08, 0.09, 0.1), 0.08)
    elif m.name in ("Rubber", "TankDarkMetal", "HeliDark", "BoatDark", "MatteBlack", "Interior"):
        flat(b, (0.55, 0.55, 0.54), 0.7)  # light grey so running gear reads but stays quiet
    else:
        flat(b, WHITE)

# ground: white with a slightly darker road
g = bpy.data.materials["Ground"]
nt = g.node_tree
b = nt.nodes["Principled BSDF"]
for inp in ("Base Color", "Roughness", "Normal"):
    for l in list(b.inputs[inp].links):
        nt.links.remove(l)
# reuse the road mask node chain: find the MapRange that outputs the road falloff (To Min 1 / To Max 0, From 3.4)
road = [n for n in nt.nodes if n.type == "MAP_RANGE" and abs(n.inputs["From Min"].default_value - 3.4) < 1e-3][0]
landx = [n for n in nt.nodes if n.type == "MAP_RANGE" and abs(n.inputs["From Min"].default_value - 52) < 1e-3][0]
mul = nt.nodes.new("ShaderNodeMath"); mul.operation = "MULTIPLY"
nt.links.new(road.outputs[0], mul.inputs[0]); nt.links.new(landx.outputs[0], mul.inputs[1])
mx = nt.nodes.new("ShaderNodeMix"); mx.data_type = "RGBA"
nt.links.new(mul.outputs[0], mx.inputs["Factor"])
mx.inputs[6].default_value = (0.5, 0.48, 0.44, 1)
mx.inputs[7].default_value = (0.36, 0.35, 0.33, 1)
# monochrome surface interest: soft tonal mottling + fine relief
geo = [n for n in nt.nodes if n.type == "NEW_GEOMETRY"][0]
mot = nt.nodes.new("ShaderNodeTexNoise"); mot.inputs["Scale"].default_value = 0.08; mot.inputs["Detail"].default_value = 5
nt.links.new(geo.outputs["Position"], mot.inputs["Vector"])
motr = nt.nodes.new("ShaderNodeMapRange"); motr.inputs["From Min"].default_value = 0.35; motr.inputs["From Max"].default_value = 0.65
motr.inputs["To Min"].default_value = 0.88; motr.inputs["To Max"].default_value = 1.08
nt.links.new(mot.outputs["Fac"], motr.inputs["Value"])
tone = nt.nodes.new("ShaderNodeMix"); tone.data_type = "RGBA"; tone.blend_type = "MULTIPLY"
tone.inputs["Factor"].default_value = 1.0
nt.links.new(mx.outputs[2], tone.inputs[6])
cmb = nt.nodes.new("ShaderNodeCombineColor")
for i in range(3):
    nt.links.new(motr.outputs[0], cmb.inputs[i])
nt.links.new(cmb.outputs[0], tone.inputs[7])
nt.links.new(tone.outputs[2], b.inputs["Base Color"])
b.inputs["Roughness"].default_value = 0.85
fine = nt.nodes.new("ShaderNodeTexNoise"); fine.inputs["Scale"].default_value = 2.2; fine.inputs["Detail"].default_value = 8
fine.inputs["Roughness"].default_value = 0.65
nt.links.new(geo.outputs["Position"], fine.inputs["Vector"])
grit = nt.nodes.new("ShaderNodeTexVoronoi"); grit.inputs["Scale"].default_value = 9.0
nt.links.new(geo.outputs["Position"], grit.inputs["Vector"])
hsum = nt.nodes.new("ShaderNodeMath"); hsum.operation = "MULTIPLY_ADD"; hsum.inputs[1].default_value = 0.35
nt.links.new(grit.outputs["Distance"], hsum.inputs[0]); nt.links.new(fine.outputs["Fac"], hsum.inputs[2])
gb = nt.nodes.new("ShaderNodeBump"); gb.inputs["Strength"].default_value = 0.45; gb.inputs["Distance"].default_value = 0.08
nt.links.new(hsum.outputs[0], gb.inputs["Height"])
nt.links.new(gb.outputs[0], b.inputs["Normal"])
b.inputs["Specular IOR Level"].default_value = 0.2

# water: pale slate, keep the ripple bump
w = bpy.data.materials["Water"]
wb = w.node_tree.nodes["Principled BSDF"]
for l in list(wb.inputs["Base Color"].links):
    w.node_tree.links.remove(l)
wb.inputs["Base Color"].default_value = (0.13, 0.2, 0.25, 1)
wb.inputs["Roughness"].default_value = 0.18
bump = [n for n in w.node_tree.nodes if n.type == "BUMP"][0]
bump.inputs["Strength"].default_value = 0.12

# drop the grass/bush clutter; keep trees (they read as white model trees)
for o in bpy.data.objects:
    if o.type == "EMPTY" and o.instance_collection and "rooibos" in o.instance_collection.name:
        o.hide_render = True

# ---------------------------------------------------------------- figures
# hide the rigged soldiers and their scanned rifles; posed figurines are placed per frame below
from figure import make_figure
for o in bpy.data.objects:
    if o.type == "ARMATURE" and o.users_collection and o.users_collection[0].name == "People":
        for ch in o.children_recursive:
            ch.hide_render = True
        o.hide_render = True
    if o.name.endswith("_Rifle"):
        for ch in o.children_recursive:
            ch.hide_render = True
POSE_OF = {"Patrol0": "patrol", "Patrol1": "patrol", "Patrol2": "ready", "Guard0": "ready", "Guard1": "rest",
           "Guard2": "aim", "Runner": "ready", "Crew0": "aim", "Crew1": "ready"}
FIG_COLL = bpy.data.collections.new("Figures")
sc.collection.children.link(FIG_COLL)


def place_figures():
    for o in list(FIG_COLL.objects):
        bpy.data.objects.remove(o)
    for root_name, pose in POSE_OF.items():
        root = bpy.data.objects.get(root_name)
        if not root:
            continue
        f = make_figure(root_name + "_fig", pose, FIG_COLL, accent=ACCENTS["Tank_Decal"])
        f.matrix_world = root.matrix_world.copy()


# ---------------------------------------------------------------- light & sky
wd = sc.world
nt = wd.node_tree
for n in list(nt.nodes):
    if n.type not in ("OUTPUT_WORLD",):
        nt.nodes.remove(n)
out = [n for n in nt.nodes if n.type == "OUTPUT_WORLD"][0]
sky = nt.nodes.new("ShaderNodeTexSky")
sky.sky_type = "NISHITA"
sky.sun_elevation = math.radians(22)
sky.sun_rotation = math.radians(150)
sky.sun_disc = False
sky.air_density = 1.4
sky.dust_density = 2.0
bg_light = nt.nodes.new("ShaderNodeBackground")
bg_light.inputs[1].default_value = 0.13
nt.links.new(sky.outputs[0], bg_light.inputs[0])
# what the camera sees: soft pale gradient
tc = nt.nodes.new("ShaderNodeTexCoord")
sep = nt.nodes.new("ShaderNodeSeparateXYZ")
nt.links.new(tc.outputs["Generated"], sep.inputs[0])
grad = nt.nodes.new("ShaderNodeValToRGB")
grad.color_ramp.elements[0].position = 0.0
grad.color_ramp.elements[0].color = (0.78, 0.8, 0.83, 1)
grad.color_ramp.elements[1].position = 0.6
grad.color_ramp.elements[1].color = (0.38, 0.5, 0.68, 1)
nt.links.new(sep.outputs["Z"], grad.inputs[0])
bg_cam = nt.nodes.new("ShaderNodeBackground")
bg_cam.inputs[1].default_value = 1.0
nt.links.new(grad.outputs[0], bg_cam.inputs[0])
lp = nt.nodes.new("ShaderNodeLightPath")
mix = nt.nodes.new("ShaderNodeMixShader")
nt.links.new(lp.outputs["Is Camera Ray"], mix.inputs[0])
nt.links.new(bg_light.outputs[0], mix.inputs[1])
nt.links.new(bg_cam.outputs[0], mix.inputs[2])
nt.links.new(mix.outputs[0], out.inputs[0])

sun = bpy.data.objects["Sun"]
sun.rotation_euler = (math.radians(68), 0, math.radians(-60))
sun.data.energy = 7.5
sun.data.color = (1.0, 0.92, 0.82)
sun.data.angle = math.radians(2.0)

# mist for depth (compositor)
sc.view_layers[0].use_pass_mist = True
wd.mist_settings.start = 30
wd.mist_settings.depth = 2600
wd.mist_settings.falloff = "QUADRATIC"
sc.use_nodes = True
ct = sc.node_tree
for n in list(ct.nodes):
    ct.nodes.remove(n)
rl = ct.nodes.new("CompositorNodeRLayers")
mx = ct.nodes.new("CompositorNodeMixRGB")
mx.inputs[2].default_value = (0.78, 0.8, 0.83, 1)
mul = ct.nodes.new("CompositorNodeMath"); mul.operation = "MULTIPLY"; mul.inputs[1].default_value = 0.55
ct.links.new(rl.outputs["Mist"], mul.inputs[0])
ct.links.new(mul.outputs[0], mx.inputs[0])
ct.links.new(rl.outputs["Image"], mx.inputs[1])
co = ct.nodes.new("CompositorNodeComposite")
ct.links.new(mx.outputs[0], co.inputs[0])

sc.view_settings.view_transform = "AgX"
sc.view_settings.look = "AgX - Medium High Contrast"
sc.view_settings.exposure = -0.15
r = sc.render
r.resolution_x, r.resolution_y, r.resolution_percentage = 1280, 720, 100
r.use_motion_blur = False
sc.cycles.samples = 48
sc.cycles.adaptive_threshold = 0.02

marks = sorted(sc.timeline_markers, key=lambda m: m.frame)
for f in ([] if os.environ.get("NO_RENDER") else FRAMES):
    sc.frame_set(f)
    place_figures()
    sc.camera = [m for m in marks if m.frame <= f][-1].camera
    r.filepath = f"{OUT}_{f:04d}.png"
    bpy.ops.render.render(write_still=True)
    print("RENDERED", f)
