import bpy, math, os
from mathutils import Vector
from lib import pbr
HDRI = os.path.join(os.path.dirname(__file__), "..", "assets", "hdri", "kloofendal_48d_partly_cloudy_puresky_2k.hdr")
def studio(out, target=(0,0,1), dist=12, views=[(35,20)], res=(960,540), samples=24, lens=50):
    sc = bpy.context.scene
    w = bpy.data.worlds.new("W"); sc.world = w; w.use_nodes = True
    nt = w.node_tree; env = nt.nodes.new("ShaderNodeTexEnvironment")
    env.image = bpy.data.images.load(os.path.abspath(HDRI))
    nt.links.new(env.outputs[0], nt.nodes["Background"].inputs[0])
    nt.nodes["Background"].inputs[1].default_value = 1.0
    sun = bpy.data.objects.new("Sun", bpy.data.lights.new("Sun", "SUN")); sc.collection.objects.link(sun)
    sun.data.energy = 4; sun.data.angle = math.radians(1.5); sun.rotation_euler = (math.radians(50), 0, math.radians(30))
    bpy.ops.mesh.primitive_plane_add(size=200); g = bpy.context.object
    g.data.materials.append(pbr("Ground", (0.18, 0.16, 0.12), rough=0.9))
    cam = bpy.data.objects.new("Cam", bpy.data.cameras.new("Cam")); sc.collection.objects.link(cam)
    cam.data.lens = lens; sc.camera = cam
    sc.render.engine = "CYCLES"; sc.cycles.samples = samples; sc.cycles.use_denoising = True
    sc.render.resolution_x, sc.render.resolution_y = res
    sc.view_settings.view_transform = "AgX"; sc.view_settings.look = "AgX - Punchy"
    t = Vector(target)
    for i, (az, el) in enumerate(views):
        a, e = math.radians(az), math.radians(el)
        cam.location = t + Vector((math.cos(a)*math.cos(e), math.sin(a)*math.cos(e), math.sin(e))) * dist
        d = t - cam.location
        cam.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()
        sc.render.filepath = f"{out}_{i}.png"
        bpy.ops.render.render(write_still=True)
