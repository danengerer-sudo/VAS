"""Ground height lookup without rebuilding the scene (ray cast down onto the terrain)."""
import bpy
from mathutils import Vector


def ground_z(x, y):
    t = bpy.data.objects["Terrain"]
    inv = t.matrix_world.inverted()
    ok, loc, _, _ = t.ray_cast(inv @ Vector((x, y, 500)), Vector((0, 0, -1)))
    return (t.matrix_world @ loc).z if ok else 0.0
