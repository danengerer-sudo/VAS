import bpy, sys, time
argv = sys.argv[sys.argv.index("--") + 1:]
out, frames = argv[0], [int(f) for f in argv[1].split(",")]
pct = int(argv[2]) if len(argv) > 2 else 50
sc = bpy.context.scene
sc.render.resolution_percentage = pct
marks = sorted(sc.timeline_markers, key=lambda m: m.frame)
for f in frames:
    sc.frame_set(f)
    cam = [m for m in marks if m.frame <= f][-1].camera
    sc.camera = cam
    sc.render.filepath = f"{out}_{f:04d}.png"
    t = time.time()
    bpy.ops.render.render(write_still=True)
    print("TIME", f, round(time.time() - t, 1))
