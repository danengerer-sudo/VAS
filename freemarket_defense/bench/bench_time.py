"""Time renders of bench.blend. Usage: blender -b bench.blend -P bench_time.py -- [quick]"""
import bpy, time, sys, os
sc = bpy.context.scene
out = os.path.join(os.path.dirname(bpy.data.filepath), "out")
os.makedirs(out, exist_ok=True)
res = []
tests = [("BLENDER_EEVEE_NEXT", 1920, 1080, 32), ("BLENDER_EEVEE_NEXT", 1920, 1080, 16),
         ("BLENDER_EEVEE_NEXT", 1280, 720, 16), ("CYCLES", 1920, 1080, 8)]
for eng, rx, ry, spp in tests:
    sc.render.engine = eng
    sc.render.resolution_x, sc.render.resolution_y = rx, ry
    if eng == "CYCLES":
        sc.cycles.samples = spp; sc.cycles.use_denoising = True; sc.render.use_persistent_data = True
    else:
        sc.eevee.taa_render_samples = spp
    ts = []
    for f in (1, 2, 3):
        sc.frame_set(f)
        sc.render.filepath = os.path.join(out, f"{eng[:5]}_{rx}_{spp}_{f:03d}.png")
        t = time.time(); bpy.ops.render.render(write_still=True); ts.append(time.time() - t)
    line = f"{eng} {rx}x{ry} samples={spp}: first {ts[0]:.1f}s, then {sum(ts[1:])/2:.1f}s/frame"
    print("BENCH", line); res.append(line)
open(os.path.join(os.path.dirname(bpy.data.filepath), "result.txt"), "w").write("\n".join(res) + "\n")
