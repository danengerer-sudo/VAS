"""Category `symbols`: ancap flag (black/gold diagonal) as pole, porch-bracket and desk variants.
Writes build/symbols.blend, thumbs/symbols/*.jpg, catalog/symbols.json, thumbs/symbols_sheet.jpg."""
import os, sys, math, json
import bpy, bmesh
from mathutils import Vector, Matrix
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, "..", "..", "scripts"))
from lib import pbr, cylinder, lathe, join
from thumb import thumbnail, contact_sheet

LIB = os.path.join(HERE, "..")
bpy.ops.wm.read_factory_settings(use_empty=True)
GOLD = (1.0, 0.8, 0.0)
BLACK = (0.018, 0.018, 0.02)


def ancap_material():
    m = bpy.data.materials.get("LIB_Ancap")
    if m:
        return m
    m = bpy.data.materials.new("LIB_Ancap")
    m.use_nodes = True
    nt = m.node_tree; n, l = nt.nodes, nt.links
    b = n["Principled BSDF"]
    uv = n.new("ShaderNodeTexCoord")
    sep = n.new("ShaderNodeSeparateXYZ"); l.new(uv.outputs["UV"], sep.inputs[0])
    d = n.new("ShaderNodeMath"); d.operation = "SUBTRACT"          # v - u : >0 upper-left (gold)
    l.new(sep.outputs["Y"], d.inputs[0]); l.new(sep.outputs["X"], d.inputs[1])
    st = n.new("ShaderNodeMath"); st.operation = "GREATER_THAN"; st.inputs[1].default_value = 0.0
    l.new(d.outputs[0], st.inputs[0])
    mx = n.new("ShaderNodeMix"); mx.data_type = "RGBA"
    l.new(st.outputs[0], mx.inputs["Factor"])
    mx.inputs[6].default_value = (*BLACK, 1); mx.inputs[7].default_value = (*GOLD, 1)
    l.new(mx.outputs[2], b.inputs["Base Color"])
    b.inputs["Roughness"].default_value = 0.6
    b.inputs["Sheen Weight"].default_value = 0.0
    return m


def cloth(name, w, h, wave=0.06, waves=1.6, nx=36, ny=18, coll=None):
    """Flag cloth hanging from its hoist edge (x=0..w along +X, z=0..-h down from top), UV 0..1."""
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    uvl = bm.loops.layers.uv.new("UV")
    V = []
    for j in range(ny + 1):
        row = []
        for i in range(nx + 1):
            u, v = i / nx, j / ny
            x = u * w
            amp = wave * u  # fixed at the hoist, free at the fly end
            y = amp * math.sin(u * waves * 2 * math.pi + v * 0.8)
            z = -h + v * h - 0.25 * amp * math.sin(u * math.pi)
            row.append(bm.verts.new((x, y, z)))
        V.append(row)
    for j in range(ny):
        for i in range(nx):
            f = bm.faces.new((V[j][i], V[j][i + 1], V[j + 1][i + 1], V[j + 1][i]))
            for lp, (ii, jj) in zip(f.loops, ((i, j), (i + 1, j), (i + 1, j + 1), (i, j + 1))):
                lp[uvl].uv = (ii / nx, jj / ny)
    bm.to_mesh(me); bm.free()
    o = bpy.data.objects.new(name, me)
    (coll or bpy.context.scene.collection).objects.link(o)
    sol = o.modifiers.new("S", "SOLIDIFY"); sol.thickness = 0.004 * max(w, 0.2); sol.offset = 0
    for p in me.polygons: p.use_smooth = True
    me.materials.append(ancap_material())
    return o


def bake(objs):
    for o in objs:
        dg = bpy.context.evaluated_depsgraph_get()
        me = bpy.data.meshes.new_from_object(o.evaluated_get(dg))
        me.transform(o.matrix_world)
        o.modifiers.clear(); o.data = me; o.matrix_world = Matrix.Identity(4)
    return join(objs)


def flag_pole(coll):
    pole_m = pbr("LIB_Body", (0.82, 0.81, 0.79), rough=0.5)
    dark = pbr("LIB_Dark", (0.035, 0.037, 0.04), rough=0.5)
    H = 6.0
    parts = [cylinder("pole", 0.045, H, (0, 0, H / 2), coll=coll, mat=pole_m),
             lathe("finial", [(0, 0.0), (0, 0.07), (0.06, 0.08), (0.14, 0.04), (0.18, 0.0)], 20, coll, pole_m, "Z", (0, 0, H)),
             cylinder("base", 0.3, 0.12, (0, 0, 0.06), coll=coll, mat=dark, bev=0.02)]
    c = cloth("cloth", 1.8, 1.2, 0.12, 1.5, coll=coll); c.location = (0.05, 0, H - 0.1)
    return bake(parts + [c])


def flag_porch(coll):
    pole_m = pbr("LIB_Body", (0.82, 0.81, 0.79), rough=0.5)
    dark = pbr("LIB_Dark", (0.035, 0.037, 0.04), rough=0.5)
    L = 1.6; ang = math.radians(40)
    pole = cylinder("pole", 0.018, L, (0, 0, 0), coll=coll, mat=pole_m)
    pole.data.transform(Matrix.Translation((0, 0, L / 2)))
    pole.rotation_euler = (0, ang, 0)
    bracket = cylinder("bracket", 0.05, 0.12, (0, 0, 0), (0, math.pi / 2, 0), 16, coll, dark)
    c = cloth("cloth", 0.9, 0.6, 0.05, 1.3, coll=coll)
    # cloth hangs from the pole: hoist edge along the pole
    c.rotation_euler = (0, ang - math.pi / 2, 0)
    c.location = (0, 0, 0)
    bpy.context.view_layer.update()
    o = bake([pole, bracket, c])
    # mount on a wall facing +X: bracket at x=0, z=2.2 m
    o.data.transform(Matrix.Translation((0, 0, 2.2)))
    return o


def flag_desk(coll):
    dark = pbr("LIB_Dark", (0.035, 0.037, 0.04), rough=0.4)
    metal = pbr("LIB_Metal", (0.8, 0.6, 0.2), rough=0.3, metal=1.0)
    parts = [cylinder("pole", 0.0025, 0.3, (0, 0, 0.165), coll=coll, mat=metal),
             cylinder("base", 0.035, 0.012, (0, 0, 0.006), coll=coll, mat=dark, bev=0.003),
             lathe("tip", [(0, 0.0), (0, 0.004), (0.006, 0.0)], 12, coll, metal, "Z", (0, 0, 0.315))]
    c = cloth("cloth", 0.15, 0.1, 0.008, 1.2, coll=coll); c.location = (0.003, 0, 0.31)
    return bake(parts + [c])


ASSETS = [("flag_ancap_pole", flag_pole, ["flag", "ancap", "symbol", "pole"]),
          ("flag_ancap_porch", flag_porch, ["flag", "ancap", "symbol", "house", "porch"]),
          ("flag_ancap_desk", flag_desk, ["flag", "ancap", "symbol", "desk", "office"])]
catalog, items = [], []
for i, (name, fn, tags) in enumerate(ASSETS):
    coll = bpy.data.collections.new(f"symbols/{name}")
    bpy.context.scene.collection.children.link(coll)
    o = fn(coll); o.name = name
    for ob in list(coll.objects):
        if ob is not o:
            bpy.data.objects.remove(ob)
    coll.asset_mark()
    for t in tags:
        coll.asset_data.tags.new(t)
    tp = os.path.join(LIB, "thumbs", "symbols", f"{name}.jpg")
    thumbnail([o], tp)
    d = o.dimensions
    catalog.append({"name": name, "category": "symbols", "collection": f"symbols/{name}", "file": "build/symbols.blend",
                    "source": "procedural", "license": "original", "dims_m": [round(d.x, 3), round(d.y, 3), round(d.z, 3)],
                    "tags": tags, "notes": "Ancap flag: gold upper-hoist triangle, black lower-fly (material LIB_Ancap, UV-driven).",
                    "thumb": f"thumbs/symbols/{name}.jpg"})
    items.append((tp, name))
    o.location.x = i * 4  # keep them apart in the file
json.dump(catalog, open(os.path.join(LIB, "catalog", "symbols.json"), "w"), indent=1)
contact_sheet(items, os.path.join(LIB, "thumbs", "symbols_sheet.jpg"), cols=3, title="symbols (3 assets)")
for ob in [o for o in bpy.data.objects if o.name.startswith("Thumb")]:
    bpy.data.objects.remove(ob)
bpy.ops.wm.save_as_mainfile(filepath=os.path.join(LIB, "build", "symbols.blend"))
print("BUILT", [a[0] for a in ASSETS])
