"""Re-export the video's procedural tank / helicopter / patrol boat into the library (category `military`),
with every material remapped onto the LIB_* palette (original name kept as a custom property).

  blender -b --factory-startup -P scripts/build_military.py
"""
import json
import os
import sys

import bpy
from mathutils import Vector

HERE = os.path.dirname(os.path.abspath(__file__))
LIB = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.normpath(os.path.join(LIB, "..", "scripts")))
import vehicles_lib as V  # noqa: E402  (LIB_* materials)
from thumb import thumbnail, contact_sheet  # noqa: E402
from tank import build_tank  # noqa: E402
from heli import build_heli  # noqa: E402
from boat import build_boat  # noqa: E402

CAT = "military"
for o in list(bpy.data.objects):
    bpy.data.objects.remove(o)
M = V.mats()


def target(mname):
    n = mname.lower()
    if n.startswith("lib_"):
        return None
    if "glass" in n:
        return "glass"
    if any(t in n for t in ("light", "navred", "navgreen", "beacon")):
        return "light"
    if "decalwhite" in n:
        return "dark"          # white lettering would vanish on a white body
    if "decal" in n:
        return "accent"
    if any(t in n for t in ("paint", "_hull", "_deck", "raftwhite", "radarwhite")):
        return "body"
    return "dark"


def remap(objs):
    for o in objs:
        if o.type not in ("MESH", "CURVE", "FONT") or not o.data:
            continue
        orig = []
        for slot in o.material_slots:
            if slot.material is None:
                continue
            t = target(slot.material.name)
            if t:
                orig.append(slot.material.name)
                if slot.link == "OBJECT":
                    slot.material = M[t]
                else:
                    o.data.materials[slot.slot_index] = M[t]
        if orig:
            o["orig_materials"] = ",".join(orig)
        if o.type == "CURVE" and o.hide_render:
            continue


ASSETS = [
    ("tank_mbt", build_tank, ["tank", "armour", "mbt"], "Abrams-like MBT. Turret/gun/wheels/tracks are named children "
     "(see scripts/tank.py animate_drive). Livery band/shield -> LIB_Accent, lettering -> LIB_Dark."),
    ("helicopter_utility", build_heli, ["helicopter", "aircraft", "utility"], "UH-60-like utility helicopter; "
     "rotors are named children (scripts/heli.py animate_rotors)."),
    ("boat_patrol", build_boat, ["boat", "sea", "patrol", "assault"], "CB90-like fast patrol boat. z=0 = waterline."),
]

entries, sheet = [], []
for name, fn, tags, notes in ASSETS:
    coll = bpy.data.collections.new(f"{CAT}/{name}")
    bpy.context.scene.collection.children.link(coll)
    root = fn(name=name, coll=coll)
    objs = list(coll.all_objects)
    remap(objs)
    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()
    pts = []
    for o in objs:
        if o.type == "MESH" and not o.hide_render:
            for c in o.evaluated_get(dg).bound_box:
                pts.append(o.matrix_world @ Vector(c))
    mn = Vector([min(p[i] for p in pts) for i in range(3)])
    mx = Vector([max(p[i] for p in pts) for i in range(3)])
    dims = [round(mx[i] - mn[i], 2) for i in range(3)]
    tris = V.tri_count([o for o in objs if not o.hide_render])
    coll.asset_mark()
    for t in ["military"] + tags:
        coll.asset_data.tags.new(t)
    coll.asset_data.description = notes
    thumb = os.path.join(LIB, "thumbs", CAT, f"{name}.jpg")
    thumbnail([root], thumb)
    sheet.append((thumb, f"{name}  {dims[0]}m"))
    used = sorted({s.material.name for o in objs if o.type in ("MESH", "FONT", "CURVE")
                   for s in o.material_slots if s.material})
    print(f"[military] {name}: dims={dims} tris={tris} mats={used}", flush=True)
    entries.append({"name": name, "category": CAT, "collection": coll.name, "file": f"build/{CAT}.blend",
                    "source": "procedural", "license": "original", "dims_m": dims, "tags": ["military"] + tags,
                    "thumb": f"thumbs/{CAT}/{name}.jpg", "notes": notes + f" ~{tris // 1000}k tris.",
                    "generator": f"../scripts/{fn.__module__}.py:{fn.__name__}"})

for o in list(bpy.data.objects):
    if o.name.startswith("Thumb"):
        bpy.data.objects.remove(o)
bpy.context.scene.pop("_thumb_studio", None)
for m in list(bpy.data.materials):  # drop the now-unused original materials
    if m.users == 0:
        bpy.data.materials.remove(m)
os.makedirs(os.path.join(LIB, "build"), exist_ok=True)
os.makedirs(os.path.join(LIB, "catalog"), exist_ok=True)
bpy.ops.wm.save_as_mainfile(filepath=os.path.join(LIB, "build", f"{CAT}.blend"))
with open(os.path.join(LIB, "catalog", f"{CAT}.json"), "w") as f:
    json.dump(entries, f, indent=1)
contact_sheet(sheet, os.path.join(LIB, "thumbs", f"{CAT}_sheet.jpg"), cols=3, title="Military")
print("[military] done", len(entries))
