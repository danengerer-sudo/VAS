"""Place library assets in any scene.

    from libload import place
    place("buildings", "bank_classical", (x, y, 0), rot_z)

Appends the asset collection once (self-contained .blend, no external links) and
returns a collection-instance empty, so repeats cost almost nothing.
"""
import os
import bpy

LIB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
_cache = {}


def asset(category, name):
    key = f"{category}/{name}"
    if key in _cache:
        return _cache[key]
    path = os.path.join(LIB, "build", f"{category}.blend")
    with bpy.data.libraries.load(path, link=False) as (src, dst):
        if key not in src.collections:
            raise KeyError(f"{key} not in {path}")
        dst.collections = [key]
    coll = dst.collections[0]
    holder = bpy.data.collections.get("_LibAssets")
    if holder is None:
        holder = bpy.data.collections.new("_LibAssets")
        bpy.context.scene.collection.children.link(holder)
        bpy.context.view_layer.layer_collection.children["_LibAssets"].exclude = True
    holder.children.link(coll)
    _cache[key] = coll
    return coll


def place(category, name, loc=(0, 0, 0), rot_z=0.0, scale=1.0, coll=None):
    src = asset(category, name)
    e = bpy.data.objects.new(f"{name}", None)
    e.instance_type = "COLLECTION"
    e.instance_collection = src
    e.location = loc
    e.rotation_euler = (0, 0, rot_z)
    e.scale = (scale,) * 3
    (coll or bpy.context.scene.collection).objects.link(e)
    return e
