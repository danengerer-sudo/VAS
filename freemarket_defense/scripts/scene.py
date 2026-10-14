"""Build the full 'How Free Market Defense Could Work' scene and save a .blend.

Run:  blender -b --factory-startup -P scene.py -- out.blend [preview]

Timeline (24 fps)
  S1    1– 96  aerial establishing shot (title)
  S2   97–216  checkpoint: residents' defense agency on patrol
  S3  217–360  tank on the road
  S4  361–504  helicopter crossing the coast
  S5  505–624  patrol boat
  S6  625–768  wide: everything together (deterrence)
"""
import os
import sys
import math
import random
import bpy
import numpy as np
from mathutils import Vector, Matrix, Euler, noise

sys.path.insert(0, os.path.dirname(__file__))
from lib import *
from tank import build_tank, animate_drive
from heli import build_heli, animate_rotors
from boat import build_boat
from soldier import make_soldier, place_on_path

HERE = os.path.dirname(os.path.abspath(__file__))
A = os.path.join(HERE, "..", "assets")
FONT = "/usr/share/fonts/opentype/inter/Inter-Bold.otf"
SHOTS = {"S1": (1, 96), "S2": (97, 216), "S3": (217, 360), "S4": (361, 504), "S5": (505, 624),
         "S6": (625, 768)}
random.seed(7)

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
OUT = argv[0] if argv else os.path.join(HERE, "..", "render", "scene.blend")

bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene
sc.frame_start, sc.frame_end = 1, 768
sc.render.fps = 24


def coll(name):
    c = bpy.data.collections.new(name)
    sc.collection.children.link(c)
    return c


C_ENV, C_PROPS, C_VEH, C_PEOPLE, C_CAM = (coll(n) for n in ("Environment", "Props", "Vehicles", "People", "Cameras"))
LIB = coll("_AssetLib")
LIB.hide_render = True
LIB.hide_viewport = True


# ------------------------------------------------------------------ terrain
def road_y(x):
    return 4.0 * math.sin(x / 35.0)


def smooth(a, b, x):
    t = np.clip((x - a) / (b - a), 0, 1)
    return t * t * (3 - 2 * t)


def height(x, y):
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    r = np.sqrt(x * x + y * y)
    base = 1.4 + 0.35 * np.sin(x / 23.0) * np.cos(y / 31.0) + 0.25 * np.sin((x + y) / 13.0)
    hills = smooth(110, 420, r) * (18 + 16 * np.sin(x / 70.0 + 1) * np.cos(y / 90.0)) + smooth(250, 600, r) * 40
    land = base + hills * (1 - smooth(-60, 15, x))
    # flatten the road corridor
    ry = 4.0 * np.sin(x / 35.0)
    corridor = 1 - smooth(5, 18, np.abs(y - ry))
    land = land * (1 - corridor) + (1.4 + 0.2 * np.sin(x / 23.0)) * corridor
    coast = smooth(48, 92, x + 6 * np.sin(y / 27.0))
    return land * (1 - coast) + (-5.0) * coast


def build_terrain():
    n = 420
    size = 1400.0
    # denser near the middle: warp the grid coordinates
    u = np.linspace(-1, 1, n)
    g = np.sign(u) * np.abs(u) ** 1.9 * size / 2
    X, Y = np.meshgrid(g + 40, g)
    Z = height(X, Y)
    verts = np.stack([X.ravel(), Y.ravel(), Z.ravel()], 1)
    idx = np.arange(n * n).reshape(n, n)
    faces = np.stack([idx[:-1, :-1].ravel(), idx[:-1, 1:].ravel(), idx[1:, 1:].ravel(), idx[1:, :-1].ravel()], 1)
    me = bpy.data.meshes.new("Terrain")
    me.vertices.add(len(verts))
    me.vertices.foreach_set("co", verts.ravel())
    me.loops.add(faces.size)
    me.loops.foreach_set("vertex_index", faces.ravel())
    me.polygons.add(len(faces))
    me.polygons.foreach_set("loop_start", np.arange(0, faces.size, 4))
    me.polygons.foreach_set("loop_total", np.full(len(faces), 4))
    me.update()
    me.polygons.foreach_set("use_smooth", np.ones(len(faces), bool))
    o = link(bpy.data.objects.new("Terrain", me), C_ENV)
    o.data.materials.append(ground_material())
    return o


def ground_material():
    m = bpy.data.materials.new("Ground")
    m.use_nodes = True
    nt = m.node_tree
    n, l = nt.nodes, nt.links
    b = n["Principled BSDF"]
    geo = n.new("ShaderNodeNewGeometry")
    sep = n.new("ShaderNodeSeparateXYZ")
    l.new(geo.outputs["Position"], sep.inputs[0])

    def texset(folder, scale):
        import glob
        out = {}
        mp = n.new("ShaderNodeMapping")
        mp.inputs["Scale"].default_value = (scale, scale, scale)
        l.new(geo.outputs["Position"], mp.inputs["Vector"])
        for key, pat, cs in (("col", "*diff*", "sRGB"), ("rough", "*rough*", "Non-Color"), ("nor", "*nor_gl*", "Non-Color")):
            fs = glob.glob(os.path.join(A, "textures", folder, pat))
            if not fs:
                continue
            t = n.new("ShaderNodeTexImage")
            t.image = bpy.data.images.load(fs[0], check_existing=True)
            t.image.colorspace_settings.name = cs
            t.projection = "FLAT"
            l.new(mp.outputs[0], t.inputs["Vector"])
            out[key] = t.outputs["Color"]
        return out

    grass = texset("aerial_grass_rock", 1 / 6.3)
    grass_b = texset("aerial_grass_rock", 1 / 17.1)
    grass2 = texset("aerial_rocks_02", 1 / 14.0)
    road = texset("brown_mud_leaves_01", 1 / 3.5)
    sand = texset("coast_sand_01", 1 / 4.0)

    def mix(fac, a, b_):
        mx = n.new("ShaderNodeMix")
        mx.data_type = "RGBA"
        l.new(fac, mx.inputs["Factor"])
        l.new(a, mx.inputs[6])
        l.new(b_, mx.inputs[7])
        return mx.outputs[2]

    # macro variation: break up the tiling with large-scale noise
    mac = n.new("ShaderNodeTexNoise")
    mac.inputs["Scale"].default_value = 0.012
    mac.inputs["Detail"].default_value = 4
    l.new(geo.outputs["Position"], mac.inputs["Vector"])
    macr = n.new("ShaderNodeMapRange")
    macr.inputs["From Min"].default_value = 0.4
    macr.inputs["From Max"].default_value = 0.65
    l.new(mac.outputs["Fac"], macr.inputs["Value"])
    tn = n.new("ShaderNodeTexNoise")
    tn.inputs["Scale"].default_value = 0.05
    tn.inputs["Detail"].default_value = 2
    l.new(geo.outputs["Position"], tn.inputs["Vector"])
    tnr = n.new("ShaderNodeMapRange")
    tnr.inputs["From Min"].default_value = 0.45
    tnr.inputs["From Max"].default_value = 0.55
    l.new(tn.outputs["Fac"], tnr.inputs["Value"])
    for k in ("col", "rough", "nor"):
        grass[k] = mix(tnr.outputs[0], grass[k], grass_b[k])
    col = mix(macr.outputs[0], grass["col"], grass2["col"])
    rough = mix(macr.outputs[0], grass["rough"], grass2["rough"]) if "rough" in grass2 else grass["rough"]
    nor = mix(macr.outputs[0], grass["nor"], grass2["nor"])
    # tint grass toward a lusher green
    hsv = n.new("ShaderNodeHueSaturation")
    hsv.inputs["Hue"].default_value = 0.56
    hsv.inputs["Saturation"].default_value = 0.95
    hsv.inputs["Value"].default_value = 0.62
    l.new(col, hsv.inputs["Color"])
    col = hsv.outputs[0]

    # road mask: |y - 4 sin(x/35)| < ~3.2 with a noisy edge
    m1 = n.new("ShaderNodeMath"); m1.operation = "DIVIDE"; m1.inputs[1].default_value = 35.0
    l.new(sep.outputs["X"], m1.inputs[0])
    m2 = n.new("ShaderNodeMath"); m2.operation = "SINE"; l.new(m1.outputs[0], m2.inputs[0])
    m3 = n.new("ShaderNodeMath"); m3.operation = "MULTIPLY"; m3.inputs[1].default_value = 4.0
    l.new(m2.outputs[0], m3.inputs[0])
    m4 = n.new("ShaderNodeMath"); m4.operation = "SUBTRACT"
    l.new(sep.outputs["Y"], m4.inputs[0]); l.new(m3.outputs[0], m4.inputs[1])
    m5 = n.new("ShaderNodeMath"); m5.operation = "ABSOLUTE"; l.new(m4.outputs[0], m5.inputs[0])
    en = n.new("ShaderNodeTexNoise"); en.inputs["Scale"].default_value = 0.6; en.inputs["Detail"].default_value = 6
    l.new(geo.outputs["Position"], en.inputs["Vector"])
    m6 = n.new("ShaderNodeMath"); m6.operation = "MULTIPLY_ADD"
    m6.inputs[1].default_value = 1.6
    l.new(en.outputs["Fac"], m6.inputs[0]); l.new(m5.outputs[0], m6.inputs[2])
    rm = n.new("ShaderNodeMapRange")
    rm.inputs["From Min"].default_value = 3.4
    rm.inputs["From Max"].default_value = 4.6
    rm.inputs["To Min"].default_value = 1.0
    rm.inputs["To Max"].default_value = 0.0
    rm.interpolation_type = "SMOOTHSTEP"
    l.new(m6.outputs[0], rm.inputs["Value"])
    # only on land, not into the sea
    landx = n.new("ShaderNodeMapRange")
    landx.inputs["From Min"].default_value = 52
    landx.inputs["From Max"].default_value = 60
    landx.inputs["To Min"].default_value = 1
    landx.inputs["To Max"].default_value = 0
    l.new(sep.outputs["X"], landx.inputs["Value"])
    rmask = n.new("ShaderNodeMath"); rmask.operation = "MULTIPLY"
    l.new(rm.outputs[0], rmask.inputs[0]); l.new(landx.outputs[0], rmask.inputs[1])

    col = mix(rmask.outputs[0], col, road["col"])
    rough = mix(rmask.outputs[0], rough, road["rough"])
    nor = mix(rmask.outputs[0], nor, road["nor"])

    # sand by height near the shore
    sm = n.new("ShaderNodeMapRange")
    sm.inputs["From Min"].default_value = 1.0
    sm.inputs["From Max"].default_value = 0.3
    l.new(sep.outputs["Z"], sm.inputs["Value"])
    smn = n.new("ShaderNodeMath"); smn.operation = "MULTIPLY_ADD"; smn.use_clamp = True
    smn.inputs[1].default_value = 0.8
    l.new(en.outputs["Fac"], smn.inputs[0]); l.new(sm.outputs[0], smn.inputs[2])
    sxm = n.new("ShaderNodeMapRange")
    sxm.inputs["From Min"].default_value = 30
    sxm.inputs["From Max"].default_value = 45
    l.new(sep.outputs["X"], sxm.inputs["Value"])
    smm = n.new("ShaderNodeMath"); smm.operation = "MULTIPLY"
    l.new(smn.outputs[0], smm.inputs[0]); l.new(sxm.outputs[0], smm.inputs[1])
    col = mix(smm.outputs[0], col, sand["col"])
    rough = mix(smm.outputs[0], rough, sand["rough"])
    nor = mix(smm.outputs[0], nor, sand["nor"])
    # wet sand darker at the waterline
    wm = n.new("ShaderNodeMapRange")
    wm.inputs["From Min"].default_value = 0.35
    wm.inputs["From Max"].default_value = -0.1
    l.new(sep.outputs["Z"], wm.inputs["Value"])
    dk = n.new("ShaderNodeMix"); dk.data_type = "RGBA"; dk.blend_type = "MULTIPLY"
    l.new(wm.outputs[0], dk.inputs["Factor"]); l.new(col, dk.inputs[6]); dk.inputs[7].default_value = (0.45, 0.42, 0.38, 1)
    col = dk.outputs[2]

    l.new(col, b.inputs["Base Color"])
    l.new(rough, b.inputs["Roughness"])
    nm = n.new("ShaderNodeNormalMap")
    nm.inputs["Strength"].default_value = 1.2
    l.new(nor, nm.inputs["Color"])
    l.new(nm.outputs[0], b.inputs["Normal"])
    b.inputs["Specular IOR Level"].default_value = 0.25
    return m


def build_sea():
    me = bpy.data.meshes.new("Sea")
    s = 1500
    me.from_pydata([(40, -s, 0), (40 + 2 * s, -s, 0), (40 + 2 * s, s, 0), (40, s, 0)], [], [(0, 1, 2, 3)])
    o = link(bpy.data.objects.new("Sea", me), C_ENV)
    m = bpy.data.materials.new("Water")
    m.use_nodes = True
    nt = m.node_tree
    n, l = nt.nodes, nt.links
    b = n["Principled BSDF"]
    b.inputs["Base Color"].default_value = (0.006, 0.03, 0.035, 1)
    b.inputs["Roughness"].default_value = 0.04
    b.inputs["IOR"].default_value = 1.333
    b.inputs["Specular IOR Level"].default_value = 0.6
    geo = n.new("ShaderNodeNewGeometry")
    # layered waves → bump
    w1 = n.new("ShaderNodeTexNoise"); w1.inputs["Scale"].default_value = 0.09; w1.inputs["Detail"].default_value = 6
    w1.inputs["Roughness"].default_value = 0.55
    mp = n.new("ShaderNodeMapping"); mp.inputs["Scale"].default_value = (1, 2.2, 1)
    l.new(geo.outputs["Position"], mp.inputs["Vector"])
    l.new(mp.outputs[0], w1.inputs["Vector"])
    w2 = n.new("ShaderNodeTexWave"); w2.inputs["Scale"].default_value = 0.035; w2.inputs["Distortion"].default_value = 8
    w2.inputs["Detail"].default_value = 4; w2.wave_profile = "SIN"
    l.new(geo.outputs["Position"], w2.inputs["Vector"])
    w3 = n.new("ShaderNodeTexNoise"); w3.inputs["Scale"].default_value = 0.9; w3.inputs["Detail"].default_value = 3
    l.new(geo.outputs["Position"], w3.inputs["Vector"])
    # animate the wave phase
    for node, attr, f0v, f1v in ((w2, "Phase Offset", 0, 25), (w1, "W", 0, 1.5)):
        pass
    w1.noise_dimensions = "4D"
    w1.inputs["W"].default_value = 0
    w1.inputs["W"].keyframe_insert("default_value", frame=1)
    w1.inputs["W"].default_value = 6
    w1.inputs["W"].keyframe_insert("default_value", frame=768)
    w2.inputs["Phase Offset"].default_value = 0
    w2.inputs["Phase Offset"].keyframe_insert("default_value", frame=1)
    w2.inputs["Phase Offset"].default_value = 60
    w2.inputs["Phase Offset"].keyframe_insert("default_value", frame=768)
    for fc in nt.animation_data.action.fcurves:
        for k in fc.keyframe_points:
            k.interpolation = "LINEAR"
    add = n.new("ShaderNodeMath"); add.operation = "ADD"
    l.new(w1.outputs["Fac"], add.inputs[0]); l.new(w2.outputs["Fac"], add.inputs[1])
    add2 = n.new("ShaderNodeMath"); add2.operation = "MULTIPLY_ADD"; add2.inputs[1].default_value = 0.25
    l.new(w3.outputs["Fac"], add2.inputs[0]); l.new(add.outputs[0], add2.inputs[2])
    bump = n.new("ShaderNodeBump"); bump.inputs["Strength"].default_value = 0.35; bump.inputs["Distance"].default_value = 0.6
    l.new(add2.outputs[0], bump.inputs["Height"])
    l.new(bump.outputs[0], b.inputs["Normal"])
    # shallow water near shore: slightly greener/lighter + foam line
    sep = n.new("ShaderNodeSeparateXYZ"); l.new(geo.outputs["Position"], sep.inputs[0])
    sh = n.new("ShaderNodeMapRange"); sh.inputs["From Min"].default_value = 70; sh.inputs["From Max"].default_value = 140
    sh.inputs["To Min"].default_value = 1; sh.inputs["To Max"].default_value = 0
    l.new(sep.outputs["X"], sh.inputs["Value"])
    mx = n.new("ShaderNodeMix"); mx.data_type = "RGBA"
    l.new(sh.outputs[0], mx.inputs["Factor"])
    mx.inputs[6].default_value = (0.004, 0.022, 0.03, 1)
    mx.inputs[7].default_value = (0.02, 0.07, 0.065, 1)
    l.new(mx.outputs[2], b.inputs["Base Color"])
    o.data.materials.append(m)
    return o


def build_sky():
    w = bpy.data.worlds.new("Sky")
    sc.world = w
    w.use_nodes = True
    nt = w.node_tree
    env = nt.nodes.new("ShaderNodeTexEnvironment")
    env.image = bpy.data.images.load(os.path.join(A, "hdri", "kloofendal_48d_partly_cloudy_puresky_2k.hdr"))
    mp = nt.nodes.new("ShaderNodeMapping")
    tc = nt.nodes.new("ShaderNodeTexCoord")
    mp.inputs["Rotation"].default_value = (0, 0, math.radians(200))
    nt.links.new(tc.outputs["Generated"], mp.inputs["Vector"])
    nt.links.new(mp.outputs[0], env.inputs["Vector"])
    nt.links.new(env.outputs[0], nt.nodes["Background"].inputs[0])
    nt.nodes["Background"].inputs[1].default_value = 0.9
    sun = bpy.data.objects.new("Sun", bpy.data.lights.new("Sun", "SUN"))
    C_ENV.objects.link(sun)
    sun.data.energy = 4.2
    sun.data.color = (1.0, 0.9, 0.78)
    sun.data.angle = math.radians(1.2)
    sun.rotation_euler = (math.radians(58), 0, math.radians(-35))
    # thin atmospheric haze for depth
    vol = nt.nodes.new("ShaderNodeVolumePrincipled")
    vol.inputs["Density"].default_value = 0.0
    return w


# ------------------------------------------------------------------ assets
_assets = {}


def asset(name):
    """Import a Poly Haven glTF once into the hidden library; return its collection."""
    if name in _assets:
        return _assets[name]
    c = bpy.data.collections.new("A_" + name)
    LIB.children.link(c)
    before = set(bpy.data.objects)
    path = os.path.join(A, "models", name, f"{name}_1k.gltf")
    bpy.ops.import_scene.gltf(filepath=path)
    for o in set(bpy.data.objects) - before:
        for uc in o.users_collection:
            uc.objects.unlink(o)
        c.objects.link(o)
    _assets[name] = c
    return c


def inst(name, loc, rot=0.0, scale=1.0, coll_=None, sub=None):
    """Instance an asset collection. sub: only objects whose names contain this string."""
    src = asset(name)
    if sub:
        key = f"{name}:{sub}"
        if key not in _assets:
            c = bpy.data.collections.new("A_" + key)
            LIB.children.link(c)
            for o in src.objects:
                if sub in o.name:
                    c.objects.link(o)
            # recentre so the instance origin sits at the picked objects' own origin
            objs = list(c.objects)
            cen = sum((o.matrix_world.translation for o in objs), Vector()) / max(1, len(objs))
            c.instance_offset = (cen.x, cen.y, 0)
            _assets[key] = c
        src = _assets[key]
    e = bpy.data.objects.new(f"I_{name}", None)
    e.instance_type = "COLLECTION"
    e.instance_collection = src
    e.location = loc
    e.rotation_euler = (0, 0, rot)
    e.scale = (scale,) * 3
    (coll_ or C_PROPS).objects.link(e)
    return e


def ground(x, y):
    return float(height(x, y))


# ------------------------------------------------------------------ town
def build_house(x, y, rot, w, d, h, wall, roofc):
    root = empty("House", (x, y, ground(x, y) - 0.15), C_ENV)
    root.rotation_euler = (0, 0, rot)
    wallm = pbr(f"Plaster_{wall}", wall, rough=0.85)
    roofm = painted_metal(f"Roof_{roofc}", roofc, [c * 0.8 for c in roofc], rough=0.7, scale=2.0, dirt=0.3)
    win = glass("HouseGlass", (0.02, 0.025, 0.03))
    trim = pbr("Trim", (0.6, 0.58, 0.55), rough=0.6)
    b = box("Walls", (w, d, h), (0, 0, h / 2), C_ENV, 0.02, wallm)
    parent(b, root)
    roof = extrude_profile("Roof", [(-w / 2 - 0.4, h - 0.05), (w / 2 + 0.4, h - 0.05), (0, h + w * 0.38)], d + 0.6,
                           "XZ", C_ENV, roofm)
    # thickness via solidify
    sol = roof.modifiers.new("S", "SOLIDIFY"); sol.thickness = 0.12
    parent(roof, root)
    gab = extrude_profile("Gable", [(-w / 2, h), (w / 2, h), (0, h + w * 0.36)], d - 0.02, "XZ", C_ENV, wallm)
    parent(gab, root)
    # windows on the long sides
    nwin = max(2, int(w / 2.2))
    for side in (1, -1):
        for i in range(nwin):
            xx = -w / 2 + (i + 0.5) * w / nwin
            for zz in ([1.5] if h < 4 else [1.5, 4.2]):
                parent(box("Win", (1.0, 0.06, 1.2), (xx, side * d / 2, zz), C_ENV, 0, win), root)
                parent(box("Sill", (1.15, 0.12, 0.08), (xx, side * (d / 2 + 0.03), zz - 0.64), C_ENV, 0, trim), root)
    parent(box("Door", (1.0, 0.08, 2.1), (w * 0.3, -d / 2, 1.05), C_ENV, 0,
               pbr("DoorWood", (0.12, 0.06, 0.03), rough=0.6)), root)
    parent(box("Chimney", (0.6, 0.6, 1.6), (-w * 0.25, d * 0.2, h + w * 0.25), C_ENV, 0.02,
               pbr("Brick", (0.25, 0.09, 0.06), rough=0.9)), root)
    return root


def build_town():
    walls = [(0.62, 0.58, 0.5), (0.7, 0.66, 0.56), (0.55, 0.5, 0.42), (0.68, 0.62, 0.5), (0.5, 0.52, 0.5)]
    roofs = [(0.18, 0.06, 0.04), (0.1, 0.1, 0.1), (0.22, 0.09, 0.05), (0.07, 0.08, 0.09)]
    spots = []
    for gx in range(-5, 2):
        for gy in range(0, 3):
            x = -60 + gx * 16 + random.uniform(-3, 3)
            y = 34 + gy * 18 + random.uniform(-3, 3)
            spots.append((x, y))
    for (x, y) in spots:
        if random.random() < 0.15:
            continue
        w, d = random.uniform(8, 12), random.uniform(6.5, 9)
        h = random.choice([3.2, 3.2, 5.8])
        build_house(x, y, random.choice([0, math.pi / 2]) + random.uniform(-0.1, 0.1), w, d, h,
                    random.choice(walls), random.choice(roofs))
    # a couple of houses on the south side too
    for (x, y) in [(-75, -45)]:
        build_house(x, y, random.uniform(-0.2, 0.2), 10, 7.5, 3.3, random.choice(walls), random.choice(roofs))


# ------------------------------------------------------------------ vegetation
KEEP_CLEAR = [(-17.5, -13.0), (-15, -12.6), (-12.5, -12.2), (-47, -12.4), (-45.5, -11.9), (50, -22)]


def scatter_vegetation():
    trees = []
    rng = random.Random(3)
    tries = 0
    while len(trees) < 900 and tries < 60000:
        tries += 1
        r = rng.uniform(25, 420)
        a = rng.uniform(0, 2 * math.pi)
        x, y = r * math.cos(a), r * math.sin(a)
        if x > 40 + 8 * math.sin(y / 27):
            continue
        if abs(y - road_y(x)) < 11:
            continue
        if -100 < x < 5 and 22 < y < 82:  # town
            continue
        if -80 < x < 0 and -62 < y < -30:
            continue
        if -70 < x < -20 and -80 < y < -25:
            continue
        # clusters: accept by noise
        if noise.noise(Vector((x / 45, y / 45, 0.3))) < 0.05:
            continue
        trees.append((x, y))
    for (x, y) in trees:
        z = ground(x, y)
        if True:
            inst("tree_small_02", (x, y, z - 0.1), rng.uniform(0, 6.28), rng.uniform(1.6, 2.6), C_ENV)
        else:
            inst("pine_sapling_small", (x, y, z - 0.05), rng.uniform(0, 6.28), rng.uniform(3.5, 5.5), C_ENV,
                 sub=rng.choice(["_a", "_b", "_c"]))
    # bushes and grass close to the camera areas
    areas = [(-8, -4, 22, 1200), (-47, -8, 22, 1200), (52, -12, 12, 150)]
    for (cx, cy, rad, count) in areas:
        for i in range(count):
            x, y = cx + rng.uniform(-rad, rad), cy + rng.uniform(-rad, rad)
            if abs(y - road_y(x)) < 4.2 or x > 47:
                continue
            if any((x - qx) ** 2 + (y - qy) ** 2 < 5.0 ** 2 for (qx, qy) in KEEP_CLEAR):
                continue
            z = ground(x, y)
            if rng.random() < 0.93:
                inst("grass_medium_01", (x, y, z - 0.03), rng.uniform(0, 6.28), rng.uniform(1.0, 1.8), C_ENV,
                     sub=rng.choice(["large_a", "large_b", "large_c", "mid_a", "mid_b"]))
            else:
                inst("wild_rooibos_bush", (x, y, z - 0.03), rng.uniform(0, 6.28), rng.uniform(0.8, 1.4), C_ENV,
                     sub=rng.choice(["_a", "_b", "_c", "_d", "_e"]))
    # rocks along the shoreline
    for i in range(10):
        y = -120 + i * 25 + rng.uniform(-6, 6)
        x = 58 + 6 * math.sin(y / 27) + rng.uniform(-4, 4)
        inst("rock_moss_set_01", (x, y, ground(x, y) - 0.3), rng.uniform(0, 6.28), rng.uniform(0.7, 1.4), C_ENV)


# ------------------------------------------------------------------ checkpoint
def build_checkpoint():
    gx = 0.0
    gy = road_y(gx)
    z = ground(gx, gy)
    head = math.atan(4 / 35 * math.cos(gx / 35))
    # staggered barriers
    for (dx, dy) in [(-6, 2.2), (-6, 1.0), (-2, -2.2), (-2, -1.0), (2, 2.2), (2, 1.0)]:
        x, y = gx + dx, road_y(gx + dx) + dy
        inst("concrete_road_barrier", (x, y, ground(x, y) - 0.02), head + math.pi / 2, 1.0)
    # roadside barrier line
    for i in range(6):
        x = -22 + i * 1.6
        y = road_y(x) + 5.6
        inst("concrete_road_barrier", (x, y, ground(x, y) - 0.02), head, 1.0)
    # sandbag-ish crates and supplies by the guard post
    px, py = 4.5, road_y(4.5) + 5.5
    pz = ground(px, py)
    post = box("GuardPost", (3.0, 2.6, 2.6), (px + 1.5, py + 1.6, pz + 1.3), C_PROPS, 0.03,
               painted_metal("PostPaint", (0.16, 0.17, 0.12), rough=0.7, scale=2))
    parent(box("PostRoof", (3.6, 3.2, 0.15), (0, 0, 1.38), C_PROPS, 0.02, pbr("RoofDark", (0.05, 0.05, 0.05), rough=0.7)),
           post)
    parent(box("PostWin", (0.06, 1.8, 0.8), (-1.51, 0, 0.3), C_PROPS, 0, glass("HouseGlass")), post)
    inst("wooden_military_crate", (px - 1.2, py - 0.5, pz), 0.3)
    inst("wooden_military_crate", (px - 1.0, py - 0.6, pz + 0.46), 0.2)
    inst("old_military_crate", (px + 0.5, py - 1.6, pz), 1.2)
    inst("metal_jerrycan_green", (px - 2.1, py + 0.4, pz), 0.4)
    inst("metal_jerrycan_green", (px - 2.5, py + 0.35, pz), 0.1)
    inst("ammo_box", (px - 1.6, py - 1.3, pz), 0.9, 1.0)
    inst("ammo_box", (px - 1.75, py - 1.2, pz), 0.5, 1.0)
    inst("wooden_barrels_01", (px + 4.5, py + 2.5, pz), 0.4, 0.7)
    # company sign
    sx, sy = -9.0, road_y(-9.0) + 6.0
    sz = ground(sx, sy)
    for dy in (-1.4, 1.4):
        cylinder("SignPost", 0.06, 3.2, (sx, sy + dy, sz + 1.6), coll=C_PROPS, mat=pbr("WornSteel", (0.32, 0.31, 0.29), rough=0.38, metal=1.0))
    board = box("SignBoard", (0.08, 3.4, 1.5), (sx, sy, sz + 2.4), C_PROPS, 0.02, pbr("SignNavy", (0.015, 0.03, 0.06), rough=0.5))
    acc = pbr("SENTINEL_Accent", (0.9, 0.35, 0.05), rough=0.6)
    box("SignStripe", (0.09, 3.4, 0.12), (sx, sy, sz + 1.72), C_PROPS, 0, acc)
    wht = pbr("DecalWhite", (0.7, 0.7, 0.66), rough=0.6)
    for txt, size, dz in (("SENTINEL DEFENSE CO.", 0.3, 0.35), ("MEMBER DISTRICT 4", 0.2, 0.0),
                          ("Protection by subscription", 0.15, -0.3)):
        text_decal("SignText", txt, size, wht if dz > -0.2 else acc, (sx - 0.05, sy, sz + 2.4 + dz),
                   (math.radians(90), 0, -math.pi / 2), C_PROPS, font=FONT)


# ------------------------------------------------------------------ cameras
def camera(name, lens=35):
    cam = bpy.data.objects.new(name, bpy.data.cameras.new(name))
    C_CAM.objects.link(cam)
    cam.data.lens = lens
    cam.data.clip_end = 3000
    cam.data.sensor_width = 36
    tgt = empty(name + "_Target", (0, 0, 0), C_CAM)
    con = cam.constraints.new("TRACK_TO")
    con.target = tgt
    con.track_axis = "TRACK_NEGATIVE_Z"
    con.up_axis = "UP_Y"
    return cam, tgt


def keys(obj, frames_vals, attr="location", interp="BEZIER"):
    for f, v in frames_vals:
        setattr(obj, attr, v)
        obj.keyframe_insert(attr, frame=f)


def ease(obj):
    if obj.animation_data and obj.animation_data.action:
        for fc in obj.animation_data.action.fcurves:
            for k in fc.keyframe_points:
                k.interpolation = "BEZIER"
                k.easing = "AUTO"


def linear(obj):
    if obj.animation_data and obj.animation_data.action:
        for fc in obj.animation_data.action.fcurves:
            for k in fc.keyframe_points:
                k.interpolation = "LINEAR"


# ------------------------------------------------------------------ build
print("terrain...")
build_terrain()
build_sea()
build_sky()
print("town / props...")
build_town()
build_checkpoint()
print("vegetation...")
scatter_vegetation()

print("vehicles...")
tank = build_tank("Tank", C_VEH, livery="SENTINEL", livery_color=(0.9, 0.35, 0.05))
heli = build_heli("Heli", C_VEH, livery="AEGIS AIR", livery_color=(0.05, 0.25, 0.75))
boat = build_boat("Boat", C_VEH, livery="TIDEWATER MARITIME", livery_color=(0.0, 0.42, 0.36))


def road_pose(x, extra_z=0.0):
    y = road_y(x)
    return (x, y, ground(x, y) + extra_z), math.atan(4 / 35 * math.cos(x / 35))


# ---------------- tank: S1 distant drive, S3 drive past camera, S6 parked by checkpoint
tank.rotation_mode = "XYZ"


def tank_drive(f0, f1, x0, x1):
    n = 6
    for i in range(n + 1):
        f = f0 + (f1 - f0) * i / n
        x = x0 + (x1 - x0) * i / n
        p, hd = road_pose(x, -0.05)
        tank.location = p
        tank.rotation_euler = (0, 0, hd)
        tank.keyframe_insert("location", frame=f)
        tank.keyframe_insert("rotation_euler", frame=f)
    animate_drive(tank, f0, f1, abs(x1 - x0))


tank_drive(1, 96, -150, -130)
tank_drive(217, 360, -82, -40)
p, hd = road_pose(-16, -0.05)
tank.location, tank.rotation_euler = p, (0, 0, hd)
tank.keyframe_insert("location", frame=625)
tank.keyframe_insert("rotation_euler", frame=625)
tank.keyframe_insert("location", frame=768)
tank.keyframe_insert("rotation_euler", frame=768)
linear(tank)
turret = bpy.data.objects[tank["turret"]]
gun = bpy.data.objects[tank["gun"]]
keys(turret, [(217, (0, 0, 0)), (260, (0, 0, 0)), (330, (0, 0, math.radians(-28))), (360, (0, 0, math.radians(-30))),
              (625, (0, 0, math.radians(20))), (700, (0, 0, math.radians(35))), (768, (0, 0, math.radians(35)))],
     "rotation_euler")
keys(gun, [(217, (0, 0, 0)), (300, (0, math.radians(-4), 0)), (360, (0, math.radians(-3), 0))], "rotation_euler")

# ---------------- helicopter
animate_rotors(heli, 1, 768)
heli.rotation_mode = "XYZ"
# S1: far away over the hills
keys(heli, [(1, (-260, 120, 70)), (96, (-200, 90, 68))])
keys(heli, [(1, (0, math.radians(3), math.radians(-30))), (96, (0, math.radians(3), math.radians(-30)))], "rotation_euler")
# S4: from the sea, over the beach camera
keys(heli, [(361, (190, 30, 13)), (504, (15, -14, 15))])
hd4 = math.atan2(-14 - 30, 15 - 190)
keys(heli, [(361, (math.radians(-2), math.radians(9), hd4)), (504, (math.radians(-6), math.radians(8), hd4 + 0.12))],
     "rotation_euler")
# S6: hovering over the checkpoint area, slow yaw
keys(heli, [(625, (32, 22, 19)), (700, (30, 18, 20)), (768, (27, 15, 20.5))])
keys(heli, [(625, (0, math.radians(2), math.radians(200))), (768, (math.radians(2), math.radians(3), math.radians(215)))],
     "rotation_euler")
for f in (96, 504):
    pass
linear(heli)

# ---------------- boat
boat.rotation_mode = "XYZ"
wake_par = empty("BoatPath", (0, 0, 0), C_VEH)


def boat_run(f0, f1, p0, p1, bob=1.0):
    d = Vector(p1) - Vector(p0)
    hd = math.atan2(d.y, d.x)
    for f in range(f0, f1 + 1, 3):
        t = (f - f0) / (f1 - f0)
        p = Vector(p0).lerp(Vector(p1), t)
        wake_par.location = (p.x, p.y, 0.0)
        wake_par.rotation_euler = (0, 0, hd)
        wake_par.keyframe_insert("location", frame=f)
        wake_par.keyframe_insert("rotation_euler", frame=f)
    # boat itself bobs and pitches relative to the path
    for f in range(f0, f1 + 1, 4):
        boat.location = (0, 0, -0.25 + 0.12 * bob * math.sin(f * 0.37) + 0.05 * math.sin(f * 1.3))
        boat.rotation_euler = (math.radians(1.8 * bob * math.sin(f * 0.29)),
                               math.radians(-3.5 - 1.6 * bob * math.sin(f * 0.41 + 1)), 0)
        boat.keyframe_insert("location", frame=f)
        boat.keyframe_insert("rotation_euler", frame=f)


boat.parent = wake_par
boat_run(1, 96, (160, -60, 0), (160, -20, 0), 0.6)
boat_run(505, 624, (128, -130, 0), (128, -40, 0), 1.0)
boat_run(625, 768, (105, -15, 0), (105, 25, 0), 0.6)
linear(wake_par)

# wake: V-shaped foam sheet trailing the boat
wake_m = bpy.data.materials.new("Wake")
wake_m.use_nodes = True
nt = wake_m.node_tree
nn, ll = nt.nodes, nt.links
bs = nn["Principled BSDF"]
bs.inputs["Base Color"].default_value = (0.85, 0.88, 0.88, 1)
bs.inputs["Roughness"].default_value = 0.5
tcn = nn.new("ShaderNodeTexCoord")
fo = nn.new("ShaderNodeTexNoise"); fo.inputs["Scale"].default_value = 1.4; fo.inputs["Detail"].default_value = 10
fo.inputs["Roughness"].default_value = 0.7
fo.noise_dimensions = "4D"
fo.inputs["W"].default_value = 0; fo.inputs["W"].keyframe_insert("default_value", frame=1)
fo.inputs["W"].default_value = 40; fo.inputs["W"].keyframe_insert("default_value", frame=768)
for fc in nt.animation_data.action.fcurves:
    for k in fc.keyframe_points:
        k.interpolation = "LINEAR"
ll.new(tcn.outputs["Object"], fo.inputs["Vector"])
sepw = nn.new("ShaderNodeSeparateXYZ"); ll.new(tcn.outputs["UV"], sepw.inputs[0])
# UV.x = 0 at stern .. 1 far behind, UV.y = 0..1 across
fade = nn.new("ShaderNodeMapRange"); fade.inputs["To Min"].default_value = 1; fade.inputs["To Max"].default_value = 0.0
ll.new(sepw.outputs["X"], fade.inputs["Value"])
edge = nn.new("ShaderNodeMath"); edge.operation = "PINGPONG"; edge.inputs[1].default_value = 0.5
ll.new(sepw.outputs["Y"], edge.inputs[0])
edge2 = nn.new("ShaderNodeMapRange"); edge2.inputs["From Min"].default_value = 0.0; edge2.inputs["From Max"].default_value = 0.25
ll.new(edge.outputs[0], edge2.inputs["Value"])
mul = nn.new("ShaderNodeMath"); mul.operation = "MULTIPLY"
ll.new(fade.outputs[0], mul.inputs[0]); ll.new(edge2.outputs[0], mul.inputs[1])
thr = nn.new("ShaderNodeMapRange")
ll.new(fo.outputs["Fac"], thr.inputs["Value"])
thr.inputs["From Min"].default_value = 0.42
thr.inputs["From Max"].default_value = 0.62
mul2 = nn.new("ShaderNodeMath"); mul2.operation = "MULTIPLY"; mul2.use_clamp = True
ll.new(thr.outputs[0], mul2.inputs[0]); ll.new(mul.outputs[0], mul2.inputs[1])
mul3 = nn.new("ShaderNodeMath"); mul3.operation = "MULTIPLY"; mul3.inputs[1].default_value = 1.6; mul3.use_clamp = True
ll.new(mul2.outputs[0], mul3.inputs[0])
ll.new(mul3.outputs[0], bs.inputs["Alpha"])
# wake geometry: fan from the stern widening behind
wv, wf, wuv = [], [], []
NX, NY = 30, 8
for i in range(NX + 1):
    t = i / NX
    xx = -7.5 - t * 70
    half = 1.9 + t * 22
    for j in range(NY + 1):
        s_ = j / NY
        wv.append((xx, -half + 2 * half * s_, 0.06 + 0.0 * t))
for i in range(NX):
    for j in range(NY):
        a_ = i * (NY + 1) + j
        wf.append((a_, a_ + 1, a_ + NY + 2, a_ + NY + 1))
wake = mesh_obj("Wake", wv, wf, C_VEH)
uvl = wake.data.uv_layers.new(name="UV")
for poly in wake.data.polygons:
    for li in poly.loop_indices:
        vi = wake.data.loops[li].vertex_index
        i, j = divmod(vi, NY + 1)
        uvl.data[li].uv = (i / NX, j / NY)
wake.data.materials.append(wake_m)
wake.parent = wake_par
# central prop wash: brighter narrow strip
wake2 = mesh_obj("Wash", [(-7.8, -1.6, 0.08), (-40, -4.5, 0.08), (-40, 4.5, 0.08), (-7.8, 1.6, 0.08)], [(0, 1, 2, 3)], C_VEH)
uv2 = wake2.data.uv_layers.new(name="UV")
for li, uv in zip(range(4), [(0, 0.1), (1, 0.1), (1, 0.9), (0, 0.9)]):
    uv2.data[li].uv = uv
wake2.data.materials.append(wake_m)
wake2.parent = wake_par

# ---------------- people
print("people...")
soldiers = []
cx = 0.0
# S2 patrol walking toward the checkpoint along the south shoulder
walkers = [(-15.5, -3.3, 0), (-17.0, -2.4, 7), (-19.5, -3.6, 13)]
for i, (x0, dy, off) in enumerate(walkers):
    s = make_soldier(f"Patrol{i}", (0, 0, 0), 0, "Walk", offset=off, coll=C_PEOPLE)
    soldiers.append(s)
    p0 = (x0, road_y(x0) + dy, ground(x0, road_y(x0) + dy))
    x1 = x0 + 7.0
    p1 = (x1, road_y(x1) + dy, ground(x1, road_y(x1) + dy))
    place_on_path(s, 97, 216, p0, p1)
    # S6: same patrol further along
    xa, xb = x0 + 14, x0 + 22
    pa = (xa, road_y(xa) + dy, ground(xa, road_y(xa) + dy))
    pb = (xb, road_y(xb) + dy, ground(xb, road_y(xb) + dy))
    s.location = pa
    s.keyframe_insert("location", frame=625)
    s.location = pb
    s.keyframe_insert("location", frame=768)
    linear(s)
# guards at the barrier and the post
guards = [(-1.0, 3.6, -math.pi / 2 - 0.3, 0), (3.2, -3.4, math.pi / 2 + 0.4, 11), (6.5, 4.8, -math.pi / 2 + 0.6, 23)]
for i, (x, dy, hd, off) in enumerate(guards):
    y = road_y(x) + dy
    make_soldier(f"Guard{i}", (x, y, ground(x, y)), hd, "Idle", offset=off, coll=C_PEOPLE)
# boat crew (two gunners on deck)
for i, (bx, by, hd) in enumerate([(4.0, 0.0, 0.0), (-6.0, 0.0, math.pi)]):
    s = make_soldier(f"Crew{i}", (bx - 0.6 * math.cos(hd), by, 1.45), hd, "Idle", offset=i * 9, coll=C_PEOPLE)
    s.parent = boat
# a runner crossing toward the guard post in S2
r = make_soldier("Runner", (0, 0, 0), 0, "Run", offset=4, coll=C_PEOPLE)
place_on_path(r, 97, 216, (-6, -9, ground(-6, -9)), (8, 12, ground(8, 12)))

# ---------------- cameras per shot
cams = {}
c, t = camera("CamS1", 30)
keys(c, [(1, (-215, -95, 62)), (96, (-195, -82, 55))])
keys(t, [(1, (20, 10, 0)), (96, (30, 10, 0))])
linear(c); linear(t)
cams["S1"] = c

c, t = camera("CamS2", 32)
keys(c, [(97, (-17.5, -13.0, 1.45)), (216, (-12.5, -12.2, 1.6))])
keys(t, [(97, (-8.0, -1.0, 1.5)), (216, (-3.0, 0.5, 1.6))])
linear(c); linear(t)
cams["S2"] = c

c, t = camera("CamS3", 28)
p3 = (-47, road_y(-47) - 8.5, ground(-47, road_y(-47) - 8.5) + 0.7)
keys(c, [(217, p3), (360, (p3[0] + 1.5, p3[1] + 0.5, p3[2] + 0.2))])
# target follows the tank, leading slightly
tgt_tank = []
for f in range(217, 361, 12):
    sc.frame_set(f)
    tp = tank.matrix_world.translation.copy()
    t.location = (tp.x + 2.5, tp.y, tp.z + 1.6)
    t.keyframe_insert("location", frame=f)
ease(t)
linear(c)
cams["S3"] = c

c, t = camera("CamS4", 32)
p4 = (50, -22, ground(50, -22) + 1.7)
keys(c, [(361, p4), (504, (p4[0] - 2, p4[1] - 1, p4[2] + 0.2))])
for f in range(361, 505, 8):
    sc.frame_set(f)
    hp = heli.matrix_world.translation.copy()
    k = ((f - 361) / 143.0) ** 2
    t.location = (hp.x - 6 * (1 - k), hp.y, hp.z * (0.55 + 0.45 * k) - 3.0 * k)
    t.keyframe_insert("location", frame=f)
ease(t)
linear(c)
cams["S4"] = c

c, t = camera("CamS5", 40)
for f in range(505, 625, 8):
    sc.frame_set(f)
    bp = wake_par.matrix_world.translation.copy()
    c.location = (bp.x + 26 - (f - 505) * 0.02, bp.y - 16 + (f - 505) * 0.05, 5.5)
    c.keyframe_insert("location", frame=f)
    t.location = (bp.x - 1, bp.y + 3, 1.8)
    t.keyframe_insert("location", frame=f)
ease(c); ease(t)
cams["S5"] = c

c, t = camera("CamS6", 30)
keys(c, [(625, (-30, -40, 6)), (768, (-48, -62, 17))])
keys(t, [(625, (8, 0, 4)), (768, (30, 8, 4))])
ease(c); ease(t)
cams["S6"] = c

for name, (f0, f1) in SHOTS.items():
    mk = sc.timeline_markers.new(name, frame=f0)
    mk.camera = cams[name]
sc.camera = cams["S1"]

# ------------------------------------------------------------------ render settings
r = sc.render
r.engine = "CYCLES"
r.resolution_x, r.resolution_y = 960, 540
r.resolution_percentage = 100
r.use_persistent_data = True
r.use_motion_blur = True
r.motion_blur_shutter = 0.3
r.image_settings.file_format = "PNG"
r.image_settings.color_mode = "RGB"
r.filepath = os.path.join(HERE, "..", "render", "frames", "f_")
cy = sc.cycles
cy.samples = 12
cy.adaptive_threshold = 0.05
cy.use_denoising = True
cy.denoiser = "OPENIMAGEDENOISE"
cy.max_bounces = 4
cy.diffuse_bounces = 2
cy.glossy_bounces = 2
cy.transmission_bounces = 4
cy.transparent_max_bounces = 8
cy.caustics_reflective = False
cy.caustics_refractive = False
cy.texture_limit_render = "2048"
sc.view_settings.view_transform = "AgX"
sc.view_settings.look = "AgX - Medium High Contrast"
sc.view_settings.exposure = 0.0
# subtle mist pass is not used; depth comes from haze in comp (skipped for speed)

bpy.ops.wm.save_as_mainfile(filepath=os.path.abspath(OUT))
print("saved", OUT)
