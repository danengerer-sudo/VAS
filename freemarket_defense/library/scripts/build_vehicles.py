"""Build all procedural vehicles into build/vehicles.blend + thumbs + catalog.

Usage:
  blender -b --factory-startup -P scripts/build_vehicles.py              # full build
  blender -b --factory-startup -P scripts/build_vehicles.py -- car_sedan,bus_city   # subset, no .blend/catalog
"""
import json
import os
import sys
import time

import bpy
from mathutils import Vector

HERE = os.path.dirname(os.path.abspath(__file__))
LIB = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import vehicles_lib as V  # noqa: E402
from thumb import thumbnail, contact_sheet  # noqa: E402

CAT = "vehicles"
argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
only = set(argv[0].split(",")) if argv and argv[0] else None

# clean factory scene
for o in list(bpy.data.objects):
    bpy.data.objects.remove(o)
V.mats()


def bounds(objs):
    dg = bpy.context.evaluated_depsgraph_get()
    pts = []
    for o in objs:
        if o.type != "MESH":
            continue
        ev = o.evaluated_get(dg)
        for v in ev.data.vertices:
            pts.append(o.matrix_world @ v.co)
    mn = Vector([min(p[i] for p in pts) for i in range(3)])
    mx = Vector([max(p[i] for p in pts) for i in range(3)])
    return mn, mx


entries, sheet = [], []
for (name, fn, kw, tags, notes) in V.REGISTRY:
    if only and name not in only:
        continue
    t0 = time.time()
    coll = bpy.data.collections.new(f"{CAT}/{name}")
    bpy.context.scene.collection.children.link(coll)
    root = fn(coll=coll, name=name, **kw)
    objs = list(coll.all_objects)
    mn, mx = bounds(objs)
    dims = [round(mx[i] - mn[i], 2) for i in range(3)]
    tris = V.tri_count(objs)
    coll.asset_mark()
    for t in ["vehicle"] + tags:
        coll.asset_data.tags.new(t)
    coll.asset_data.description = notes
    thumb = os.path.join(LIB, "thumbs", CAT, f"{name}.jpg")
    thumbnail([root], thumb)
    sheet.append((thumb, f"{name}  {dims[0]}m"))
    print(f"[vehicles] {name}: dims={dims} tris={tris} ctr=({(mn.x+mx.x)/2:.2f},{(mn.y+mx.y)/2:.2f}) "
          f"zmin={mn.z:.3f} {time.time()-t0:.1f}s", flush=True)
    entries.append({"name": name, "category": CAT, "collection": coll.name, "file": f"build/{CAT}.blend",
                    "source": "procedural", "license": "original", "dims_m": dims,
                    "tags": ["vehicle"] + tags, "thumb": f"thumbs/{CAT}/{name}.jpg", "notes": notes + f" ~{tris // 1000}k tris.",
                    "generator": f"scripts/vehicles_lib.py:{fn.__name__}"})

if only:
    contact_sheet(sheet, os.path.join(LIB, "thumbs", "_test_vehicles_sheet.jpg"), cols=4, title="test")
else:
    os.makedirs(os.path.join(LIB, "build"), exist_ok=True)
    os.makedirs(os.path.join(LIB, "catalog"), exist_ok=True)
    # remove thumbnail studio objects before saving
    for o in list(bpy.data.objects):
        if o.name.startswith("Thumb"):
            bpy.data.objects.remove(o)
    bpy.context.scene.pop("_thumb_studio", None)
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(LIB, "build", f"{CAT}.blend"))
    with open(os.path.join(LIB, "catalog", f"{CAT}.json"), "w") as f:
        json.dump(entries, f, indent=1)
    contact_sheet(sheet, os.path.join(LIB, "thumbs", f"{CAT}_sheet.jpg"), cols=6, title="Vehicles")
print("[vehicles] done", len(entries))
