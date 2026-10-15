"""Low-res rough-cut frames for shot blends (every Nth frame, global numbering).
blender -b shot.blend -P render_animatic.py -- <frames_dir> [step] [percent] [samples]"""
import bpy, sys, os
a = sys.argv[sys.argv.index("--") + 1:]
out, step, pct, spp = a[0], int(a[1]) if len(a) > 1 else 3, int(a[2]) if len(a) > 2 else 33, int(a[3]) if len(a) > 3 else 8
sc = bpy.context.scene
sc.render.engine = "CYCLES"; sc.cycles.samples = spp; sc.cycles.use_denoising = True
sc.render.use_persistent_data = True; sc.render.resolution_percentage = pct; sc.render.use_motion_blur = False
sc.frame_step = step
sc.render.filepath = os.path.join(out, "f_")
sc.render.image_settings.file_format = "PNG"
bpy.ops.render.render(animation=True)
