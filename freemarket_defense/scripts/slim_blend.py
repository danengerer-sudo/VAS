"""Re-save a .blend without orphan MakeHuman textures/materials. blender -b file.blend -P slim_blend.py"""
import bpy, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mhuman import purge_mpfb_data
before = os.path.getsize(bpy.data.filepath)
purge_mpfb_data()
bpy.ops.wm.save_mainfile(compress=True)
print("SLIM", os.path.basename(bpy.data.filepath), round(before / 1e6), "->", round(os.path.getsize(bpy.data.filepath) / 1e6), "MB")
