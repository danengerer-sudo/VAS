"""Uniform white-style thumbnails for library assets."""
import math
import os
import bpy
from mathutils import Vector

FONT = "/usr/share/fonts/opentype/inter/Inter-SemiBold.otf"


def _bounds(objs):
    pts = []
    dg = bpy.context.evaluated_depsgraph_get()
    for o in objs:
        if o.type not in ("MESH", "CURVE", "FONT"):
            continue
        for c in o.evaluated_get(dg).bound_box:
            pts.append(o.matrix_world @ Vector(c))
    if not pts:
        return Vector(), 1.0
    mn = Vector([min(p[i] for p in pts) for i in range(3)])
    mx = Vector([max(p[i] for p in pts) for i in range(3)])
    return (mn + mx) / 2, max((mx - mn).length, 0.1)


def setup_studio():
    """Call once per Blender session before thumbnail(); idempotent."""
    sc = bpy.context.scene
    if sc.get("_thumb_studio"):
        return
    sc["_thumb_studio"] = True
    w = bpy.data.worlds.new("ThumbWorld")
    sc.world = w
    w.use_nodes = True
    bg = w.node_tree.nodes["Background"]
    bg.inputs[0].default_value = (0.78, 0.8, 0.83, 1)
    bg.inputs[1].default_value = 0.55
    sun = bpy.data.objects.new("ThumbSun", bpy.data.lights.new("ThumbSun", "SUN"))
    sc.collection.objects.link(sun)
    sun.data.energy = 4.0
    sun.data.angle = math.radians(3)
    sun.data.color = (1.0, 0.95, 0.88)
    sun.rotation_euler = (math.radians(50), 0, math.radians(-35))
    me = bpy.data.meshes.new("ThumbFloor")
    s = 5000
    me.from_pydata([(-s, -s, 0), (s, -s, 0), (s, s, 0), (-s, s, 0)], [], [(0, 1, 2, 3)])
    fl = bpy.data.objects.new("ThumbFloor", me)
    sc.collection.objects.link(fl)
    m = bpy.data.materials.new("ThumbFloorMat")
    m.use_nodes = True
    m.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.55, 0.54, 0.52, 1)
    m.node_tree.nodes["Principled BSDF"].inputs["Roughness"].default_value = 0.9
    fl.data.materials.append(m)
    cam = bpy.data.objects.new("ThumbCam", bpy.data.cameras.new("ThumbCam"))
    sc.collection.objects.link(cam)
    sc.camera = cam
    r = sc.render
    r.engine = "CYCLES"
    sc.cycles.samples = 12
    sc.cycles.use_denoising = True
    sc.cycles.max_bounces = 3
    r.resolution_x = r.resolution_y = 384
    r.image_settings.file_format = "JPEG"
    r.image_settings.quality = 88
    sc.view_settings.view_transform = "AgX"
    sc.view_settings.look = "AgX - Medium High Contrast"


def thumbnail(objs, out_path, azimuth=-35, elevation=22, lens=50, fill=1.0):
    """Render objs (list) framed 3/4 view. Other mesh objects in the scene are hidden for the render."""
    setup_studio()
    sc = bpy.context.scene
    keep = set(objs) | {o for ob in objs for o in ob.children_recursive}
    hidden = []
    for o in sc.objects:
        if o.name.startswith("Thumb") or o in keep:
            continue
        if not o.hide_render:
            o.hide_render = True
            hidden.append(o)
    c, size = _bounds(list(keep))
    cam = sc.camera
    cam.data.lens = lens
    dist = size / (2 * math.tan(cam.data.angle / 2)) * 1.05 / fill
    a, e = math.radians(azimuth), math.radians(elevation)
    cam.location = c + Vector((math.cos(a) * math.cos(e), math.sin(a) * math.cos(e), math.sin(e))) * dist
    cam.rotation_euler = (c - cam.location).to_track_quat("-Z", "Y").to_euler()
    cam.data.clip_end = dist * 10
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    sc.render.filepath = out_path
    bpy.ops.render.render(write_still=True)
    for o in hidden:
        o.hide_render = False


def contact_sheet(items, out_path, cols=6, title=None):
    """items: list of (jpg_path, label). Uses PIL via Blender's bundled Python if available, else system python."""
    import subprocess, json, sys, tempfile
    spec = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
    json.dump({"items": items, "out": out_path, "cols": cols, "title": title}, spec)
    spec.close()
    code = r'''
import json,sys
from PIL import Image, ImageDraw, ImageFont
s=json.load(open(sys.argv[1])); items=s["items"]; cols=s["cols"]; T=256; L=26
rows=(len(items)+cols-1)//cols; top=44 if s["title"] else 0
sheet=Image.new("RGB",(cols*T, rows*(T+L)+top),(245,245,243)); d=ImageDraw.Draw(sheet)
f=ImageFont.truetype("/usr/share/fonts/opentype/inter/Inter-SemiBold.otf",15)
if s["title"]: d.text((12,10),s["title"],font=ImageFont.truetype("/usr/share/fonts/opentype/inter/Inter-Bold.otf",22),fill=(20,20,20))
for i,(p,lab) in enumerate(items):
    x,y=(i%cols)*T, top+(i//cols)*(T+L)
    try: sheet.paste(Image.open(p).convert("RGB").resize((T,T)),(x,y))
    except Exception as e: pass
    d.text((x+6,y+T+4),lab[:30],font=f,fill=(30,30,30))
sheet.save(s["out"],quality=88)
'''
    subprocess.check_call(["/usr/bin/python3", "-c", code, spec.name])
