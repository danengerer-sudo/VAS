"""Shared modeling / material helpers for the Free Market Defense video."""
import math
import bpy
import bmesh
from mathutils import Vector, Matrix

ASSETS = None  # set by caller


# ---------------------------------------------------------------- objects
def link(obj, coll=None):
    (coll or bpy.context.scene.collection).objects.link(obj)
    return obj


def mesh_obj(name, verts, faces, coll=None, smooth=False):
    me = bpy.data.meshes.new(name)
    me.from_pydata([tuple(v) for v in verts], [], faces)
    me.validate()
    me.update()
    if smooth:
        for p in me.polygons:
            p.use_smooth = True
    return link(bpy.data.objects.new(name, me), coll)


def empty(name, loc=(0, 0, 0), coll=None):
    e = bpy.data.objects.new(name, None)
    e.location = loc
    e.empty_display_size = 0.5
    return link(e, coll)


def parent(child, par, keep=False):
    mw = child.matrix_world.copy()
    child.parent = par
    if keep:
        child.matrix_world = mw
    return child


def bevel(obj, width=0.02, segments=2, angle=35, harden=True):
    m = obj.modifiers.new("Bevel", "BEVEL")
    m.width = width
    m.segments = segments
    m.limit_method = "ANGLE"
    m.angle_limit = math.radians(angle)
    m.harden_normals = harden
    if harden:
        for p in obj.data.polygons:
            p.use_smooth = True
    return m


def weighted_normals(obj):
    m = obj.modifiers.new("WN", "WEIGHTED_NORMAL")
    m.keep_sharp = True
    return m


def subsurf(obj, levels=2):
    m = obj.modifiers.new("Sub", "SUBSURF")
    m.levels = levels
    m.render_levels = levels
    return m


def set_mat(obj, mat):
    obj.data.materials.clear()
    obj.data.materials.append(mat)
    return obj


def add_mat(obj, mat):
    obj.data.materials.append(mat)
    return len(obj.data.materials) - 1


# ---------------------------------------------------------------- primitives
def box(name, size, loc=(0, 0, 0), coll=None, bev=0.0, mat=None, rot=(0, 0, 0)):
    sx, sy, sz = [s / 2 for s in size]
    v = [(-sx, -sy, -sz), (sx, -sy, -sz), (sx, sy, -sz), (-sx, sy, -sz),
         (-sx, -sy, sz), (sx, -sy, sz), (sx, sy, sz), (-sx, sy, sz)]
    f = [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]
    o = mesh_obj(name, v, f, coll)
    o.location = loc
    o.rotation_euler = rot
    if bev:
        bevel(o, bev)
    if mat:
        set_mat(o, mat)
    return o


def cylinder(name, r, depth, loc=(0, 0, 0), rot=(0, 0, 0), verts=24, coll=None,
             mat=None, bev=0.0, r2=None, smooth=True):
    """Cylinder along local Z, centered."""
    r2 = r if r2 is None else r2
    v, f = [], []
    for i in range(verts):
        a = 2 * math.pi * i / verts
        v.append((r * math.cos(a), r * math.sin(a), -depth / 2))
    for i in range(verts):
        a = 2 * math.pi * i / verts
        v.append((r2 * math.cos(a), r2 * math.sin(a), depth / 2))
    for i in range(verts):
        j = (i + 1) % verts
        f.append((i, j, verts + j, verts + i))
    f.append(tuple(reversed(range(verts))))
    f.append(tuple(range(verts, 2 * verts)))
    o = mesh_obj(name, v, f, coll)
    if smooth:
        for p in o.data.polygons[:verts]:
            p.use_smooth = True
        o.data.polygons[verts].use_smooth = False
        o.data.polygons[verts + 1].use_smooth = False
    o.location = loc
    o.rotation_euler = rot
    if bev:
        bevel(o, bev, angle=50)
    if mat:
        set_mat(o, mat)
    return o


def lathe(name, profile, verts=32, coll=None, mat=None, axis="X", loc=(0, 0, 0), smooth=True):
    """Revolve a (axial, radius) profile around an axis."""
    v, f = [], []
    n = len(profile)
    for i in range(verts):
        a = 2 * math.pi * i / verts
        c, s = math.cos(a), math.sin(a)
        for (x, r) in profile:
            if axis == "X":
                v.append((x, r * c, r * s))
            elif axis == "Y":
                v.append((r * c, x, r * s))
            else:
                v.append((r * c, r * s, x))
    for i in range(verts):
        j = (i + 1) % verts
        for k in range(n - 1):
            a, b = i * n + k, j * n + k
            f.append((a, a + 1, b + 1, b) if axis != "Y" else (a, b, b + 1, a + 1))
    o = mesh_obj(name, v, f, coll, smooth=smooth)
    me = o.data
    bm = bmesh.new()
    bm.from_mesh(me)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-5)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(me)
    bm.free()
    o.location = loc
    if mat:
        set_mat(o, mat)
    return o


def extrude_profile(name, pts2d, depth, plane="XZ", coll=None, mat=None, loc=(0, 0, 0), center=True):
    """Extrude a closed 2D polygon (CCW) along the remaining axis."""
    n = len(pts2d)
    off = -depth / 2 if center else 0
    v = []
    for d in (off, off + depth):
        for (a, b) in pts2d:
            if plane == "XZ":
                v.append((a, d, b))
            elif plane == "XY":
                v.append((a, b, d))
            else:  # YZ
                v.append((d, a, b))
    f = [tuple(range(n)), tuple(range(2 * n - 1, n - 1, -1))]
    for i in range(n):
        j = (i + 1) % n
        f.append((i, j, n + j, n + i))
    o = mesh_obj(name, v, f, coll)
    bm = bmesh.new()
    bm.from_mesh(o.data)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(o.data)
    bm.free()
    o.location = loc
    if mat:
        set_mat(o, mat)
    return o


def loft(name, sections, coll=None, cap_start=True, cap_end=True, smooth=True, mat=None):
    """Loft a list of closed rings (each a list of 3D points, same count)."""
    n = len(sections[0])
    v = [p for s in sections for p in s]
    f = []
    for si in range(len(sections) - 1):
        for i in range(n):
            j = (i + 1) % n
            a, b = si * n + i, si * n + j
            f.append((a, b, b + n, a + n))
    if cap_start:
        f.append(tuple(reversed(range(n))))
    if cap_end:
        base = (len(sections) - 1) * n
        f.append(tuple(range(base, base + n)))
    o = mesh_obj(name, v, f, coll, smooth=smooth)
    bm = bmesh.new()
    bm.from_mesh(o.data)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-6)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(o.data)
    bm.free()
    if mat:
        set_mat(o, mat)
    return o


def superellipse(cx, cy, cz, half_w, half_h_top, half_h_bot, n=32, p=2.5, x=0.0, axis="X"):
    """Ring in the YZ plane (for X-axis lofts) with separate top/bottom heights."""
    pts = []
    for i in range(n):
        a = 2 * math.pi * i / n
        c, s = math.cos(a), math.sin(a)
        yy = half_w * math.copysign(abs(c) ** (2 / p), c)
        hh = half_h_top if s >= 0 else half_h_bot
        zz = hh * math.copysign(abs(s) ** (2 / p), s)
        pts.append((x, cy + yy, cz + zz))
    return pts


def join(objs, name=None):
    objs = [o for o in objs if o]
    ctx = bpy.context.copy()
    for o in bpy.context.view_layer.objects:
        o.select_set(False)
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    with bpy.context.temp_override(active_object=objs[0], selected_editable_objects=objs,
                                   selected_objects=objs):
        bpy.ops.object.join()
    if name:
        objs[0].name = name
    return objs[0]


def apply_mods(obj):
    dg = bpy.context.evaluated_depsgraph_get()
    ev = obj.evaluated_get(dg)
    me = bpy.data.meshes.new_from_object(ev)
    obj.modifiers.clear()
    old = obj.data
    obj.data = me
    bpy.data.meshes.remove(old)


# ---------------------------------------------------------------- materials
def _nodes(mat):
    mat.use_nodes = True
    nt = mat.node_tree
    return nt, nt.nodes, nt.links


def pbr(name, color, rough=0.5, metal=0.0, spec=0.5, emission=None, alpha=None, transmission=0.0,
        ior=1.45, coat=0.0):
    m = bpy.data.materials.get(name)
    if m:
        return m
    m = bpy.data.materials.new(name)
    nt, n, l = _nodes(m)
    b = n["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*color, 1)
    b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = metal
    b.inputs["Specular IOR Level"].default_value = spec
    b.inputs["IOR"].default_value = ior
    b.inputs["Transmission Weight"].default_value = transmission
    b.inputs["Coat Weight"].default_value = coat
    if emission:
        b.inputs["Emission Color"].default_value = (*emission[0], 1)
        b.inputs["Emission Strength"].default_value = emission[1]
    if alpha is not None:
        b.inputs["Alpha"].default_value = alpha
    return m


def painted_metal(name, base, base2=None, rough=0.55, dirt=0.35, scale=1.0, camo=None,
                  stripe=None):
    """Matte military paint: subtle mottling, edge wear, grime toward the bottom.

    camo: list of extra (r,g,b) colors for a blotchy camouflage pattern.
    stripe: (color, zmin, zmax) band in object space (agency livery band).
    """
    m = bpy.data.materials.get(name)
    if m:
        return m
    m = bpy.data.materials.new(name)
    nt, n, l = _nodes(m)
    b = n["Principled BSDF"]
    tc = n.new("ShaderNodeTexCoord")

    # mottling
    noise = n.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 3.0 * scale
    noise.inputs["Detail"].default_value = 8
    noise.inputs["Roughness"].default_value = 0.6
    l.new(tc.outputs["Object"], noise.inputs["Vector"])
    ramp = n.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].color = (*base, 1)
    ramp.color_ramp.elements[1].color = (*(base2 or [c * 0.8 for c in base]), 1)
    ramp.color_ramp.elements[0].position = 0.35
    ramp.color_ramp.elements[1].position = 0.7
    l.new(noise.outputs["Fac"], ramp.inputs["Fac"])
    col = ramp.outputs["Color"]

    if camo:
        cn = n.new("ShaderNodeTexNoise")
        cn.inputs["Scale"].default_value = 0.55 * scale
        cn.inputs["Detail"].default_value = 3
        cn.inputs["Roughness"].default_value = 0.55
        cn.inputs["Distortion"].default_value = 0.6
        l.new(tc.outputs["Object"], cn.inputs["Vector"])
        cmr = n.new("ShaderNodeMapRange")
        cmr.inputs["From Min"].default_value = 0.38
        cmr.inputs["From Max"].default_value = 0.62
        l.new(cn.outputs["Fac"], cmr.inputs["Value"])
        cr = n.new("ShaderNodeValToRGB")
        cr.color_ramp.interpolation = "CONSTANT"
        els = cr.color_ramp.elements
        els[0].color = (1, 1, 1, 0)
        els[0].position = 0.0
        els[1].position = 0.5
        els[1].color = (*camo[0], 1)
        for i, c in enumerate(camo[1:]):
            e = els.new(0.72 + 0.1 * i)
            e.color = (*c, 1)
        l.new(cmr.outputs[0], cr.inputs["Fac"])
        mix = n.new("ShaderNodeMix")
        mix.data_type = "RGBA"
        l.new(cr.outputs["Alpha"], mix.inputs["Factor"])
        l.new(col, mix.inputs[6])
        l.new(cr.outputs["Color"], mix.inputs[7])
        col = mix.outputs[2]

    if stripe:
        sc, z0, z1 = stripe
        sep = n.new("ShaderNodeSeparateXYZ")
        l.new(tc.outputs["Object"], sep.inputs[0])
        g0 = n.new("ShaderNodeMath"); g0.operation = "GREATER_THAN"; g0.inputs[1].default_value = z0
        g1 = n.new("ShaderNodeMath"); g1.operation = "LESS_THAN"; g1.inputs[1].default_value = z1
        l.new(sep.outputs["Z"], g0.inputs[0]); l.new(sep.outputs["Z"], g1.inputs[0])
        mul = n.new("ShaderNodeMath"); mul.operation = "MULTIPLY"
        l.new(g0.outputs[0], mul.inputs[0]); l.new(g1.outputs[0], mul.inputs[1])
        mix = n.new("ShaderNodeMix"); mix.data_type = "RGBA"
        l.new(mul.outputs[0], mix.inputs["Factor"])
        l.new(col, mix.inputs[6])
        mix.inputs[7].default_value = (*sc, 1)
        col = mix.outputs[2]

    # grime: darker / browner toward bottom + cavity-like noise
    sep = n.new("ShaderNodeSeparateXYZ")
    l.new(tc.outputs["Object"], sep.inputs[0])
    gn = n.new("ShaderNodeTexNoise")
    gn.inputs["Scale"].default_value = 14 * scale
    gn.inputs["Detail"].default_value = 10
    l.new(tc.outputs["Object"], gn.inputs["Vector"])
    zr = n.new("ShaderNodeMapRange")
    zr.inputs["From Min"].default_value = 0.3
    zr.inputs["From Max"].default_value = 1.4
    zr.inputs["To Min"].default_value = 1.0
    zr.inputs["To Max"].default_value = 0.0
    l.new(sep.outputs["Z"], zr.inputs["Value"])
    gm = n.new("ShaderNodeMath"); gm.operation = "MULTIPLY"
    l.new(zr.outputs[0], gm.inputs[0]); l.new(gn.outputs["Fac"], gm.inputs[1])
    gm2 = n.new("ShaderNodeMath"); gm2.operation = "MULTIPLY"; gm2.inputs[1].default_value = dirt * 1.6
    gm2.use_clamp = True
    l.new(gm.outputs[0], gm2.inputs[0])
    mixd = n.new("ShaderNodeMix"); mixd.data_type = "RGBA"
    l.new(gm2.outputs[0], mixd.inputs["Factor"])
    l.new(col, mixd.inputs[6])
    mixd.inputs[7].default_value = (0.11, 0.085, 0.06, 1)
    col = mixd.outputs[2]

    # edge wear via pointiness-free AO-ish trick: use Bevel node normals for crisp edges
    bev = n.new("ShaderNodeBevel")
    bev.inputs["Radius"].default_value = 0.015
    l.new(bev.outputs["Normal"], b.inputs["Normal"])

    l.new(col, b.inputs["Base Color"])
    rn = n.new("ShaderNodeMapRange")
    rn.inputs["To Min"].default_value = rough - 0.12
    rn.inputs["To Max"].default_value = rough + 0.15
    l.new(gn.outputs["Fac"], rn.inputs["Value"])
    l.new(rn.outputs[0], b.inputs["Roughness"])
    b.inputs["Specular IOR Level"].default_value = 0.4
    return m


def glass(name="Glass", tint=(0.05, 0.08, 0.1)):
    m = bpy.data.materials.get(name)
    if m:
        return m
    m = pbr(name, tint, rough=0.03, metal=0.0, spec=0.8)
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Coat Weight"].default_value = 1.0
    return m


def image_tex_mat(name, folder, scale=1.0, disp=False):
    """Poly Haven texture set → material using object-space box mapping by world xy."""
    import os, glob
    m = bpy.data.materials.get(name)
    if m:
        return m
    m = bpy.data.materials.new(name)
    nt, n, l = _nodes(m)
    b = n["Principled BSDF"]
    tc = n.new("ShaderNodeTexCoord")
    mp = n.new("ShaderNodeMapping")
    mp.inputs["Scale"].default_value = (scale, scale, scale)
    l.new(tc.outputs["UV"], mp.inputs["Vector"])

    def tex(pattern, colorspace):
        fs = glob.glob(os.path.join(folder, pattern))
        if not fs:
            return None
        t = n.new("ShaderNodeTexImage")
        t.image = bpy.data.images.load(fs[0], check_existing=True)
        t.image.colorspace_settings.name = colorspace
        l.new(mp.outputs[0], t.inputs["Vector"])
        return t

    d = tex("*diff*", "sRGB")
    if d:
        l.new(d.outputs["Color"], b.inputs["Base Color"])
    r = tex("*rough*", "Non-Color")
    if r:
        l.new(r.outputs["Color"], b.inputs["Roughness"])
    nm = tex("*nor_gl*", "Non-Color")
    if nm:
        nn = n.new("ShaderNodeNormalMap")
        l.new(nm.outputs["Color"], nn.inputs["Color"])
        l.new(nn.outputs["Normal"], b.inputs["Normal"])
    b.inputs["Specular IOR Level"].default_value = 0.3
    return m


def text_decal(name, text, size, mat, loc, rot, coll=None, extrude=0.002, font=None, align="CENTER"):
    cu = bpy.data.curves.new(name, "FONT")
    cu.body = text
    cu.size = size
    cu.extrude = extrude
    cu.align_x = align
    cu.align_y = "CENTER"
    if font:
        cu.font = bpy.data.fonts.load(font, check_existing=True)
    o = link(bpy.data.objects.new(name, cu), coll)
    o.location = loc
    o.rotation_euler = rot
    o.data.materials.append(mat)
    return o


def keyframe(obj, frame, loc=None, rot=None, scale=None, interp=None):
    if loc is not None:
        obj.location = loc
        obj.keyframe_insert("location", frame=frame)
    if rot is not None:
        obj.rotation_euler = rot
        obj.keyframe_insert("rotation_euler", frame=frame)
    if scale is not None:
        obj.scale = scale
        obj.keyframe_insert("scale", frame=frame)


def set_interp(obj, interp="LINEAR"):
    ad = obj.animation_data
    if ad and ad.action:
        for fc in ad.action.fcurves:
            for k in fc.keyframe_points:
                k.interpolation = interp
