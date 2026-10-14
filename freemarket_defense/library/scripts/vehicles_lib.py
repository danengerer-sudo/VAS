"""Procedural vehicle generators for the asset library (white architectural-model style).

Conventions (see ../CONVENTIONS.md): metres, Z up, vehicles face +X, origin at ground level under the
centre of the footprint, materials LIB_Body / LIB_Accent / LIB_Dark / LIB_Glass / LIB_Light / LIB_Metal only.

Every generator has the signature  fn(coll=None, name=..., **variant_params) -> root empty.
The root empty sits at the world origin; children are joined meshes:
  <name>_body            everything static
  <name>_wheel_XX        one object per wheel (origin at the axle, spin about local Y) where it matters
  other named movable parts (e.g. boom, bucket, drum, rotor) where cheap.

Colour slots: most generators take `paint` (material key for the main bodywork: "body" or "accent")
and some take `trim` / `livery` switches.  Material keys: body, accent, dark, glass, light, metal.
"""
import math
import os
import sys

import bpy
import bmesh
from mathutils import Vector, Matrix

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.normpath(os.path.join(HERE, "..", "..", "scripts")))
from lib import (box, cylinder, lathe, loft, extrude_profile, bevel, join, apply_mods, pbr,  # noqa: E402
                 empty, parent, mesh_obj, set_mat)


# =====================================================================  materials
def mats():
    return {
        "body": pbr("LIB_Body", (0.82, 0.81, 0.79), rough=0.55),
        "accent": pbr("LIB_Accent", (0.95, 0.38, 0.06), rough=0.5),
        "dark": pbr("LIB_Dark", (0.035, 0.037, 0.04), rough=0.6),
        "glass": pbr("LIB_Glass", (0.08, 0.09, 0.1), rough=0.08, spec=0.6),
        "light": pbr("LIB_Light", (1.0, 1.0, 1.0), rough=0.2, emission=((1.0, 1.0, 1.0), 0.0)),
        "metal": pbr("LIB_Metal", (0.8, 0.6, 0.2), rough=0.3, metal=1.0),
    }


def clamp(v, a, b):
    return max(a, min(b, v))


def lerp(a, b, t):
    return a + (b - a) * t


# =====================================================================  kit: part collector
class Kit:
    """Collects parts for one asset; finish() applies modifiers and joins them into a few objects."""

    def __init__(self, name, coll=None):
        self.name = name
        self.coll = coll or bpy.context.scene.collection
        self.m = mats()
        self.parts = []
        self.groups = {}
        self.root = empty(name, coll=self.coll)
        self.root.empty_display_size = 1.0

    def mat(self, k):
        return self.m[k] if isinstance(k, str) else k

    def add(self, o, group=None):
        if group:
            self.groups.setdefault(group, []).append(o)
        else:
            self.parts.append(o)
        return o

    # ---- primitives
    def box(self, size, loc, mat="body", bev=0.0, rot=(0, 0, 0), group=None, seg=2):
        o = box(f"{self.name}_p", size, loc, self.coll, 0, self.mat(mat), rot)
        if bev:
            bevel(o, bev, seg)
        return self.add(o, group)

    def cyl(self, r, depth, loc, rot=(0, 0, 0), mat="body", verts=24, bev=0.0, r2=None, group=None):
        o = cylinder(f"{self.name}_c", r, depth, loc, rot, verts, self.coll, self.mat(mat), 0.0, r2)
        if bev:
            bevel(o, bev, 2, angle=50)
        return self.add(o, group)

    def cylx(self, r, depth, loc, **kw):
        return self.cyl(r, depth, loc, rot=(0, math.pi / 2, 0), **kw)

    def cyly(self, r, depth, loc, **kw):
        return self.cyl(r, depth, loc, rot=(math.pi / 2, 0, 0), **kw)

    def tube(self, p0, p1, r, mat="body", verts=12, group=None, r2=None):
        p0, p1 = Vector(p0), Vector(p1)
        d = p1 - p0
        o = cylinder(f"{self.name}_t", r, d.length, (p0 + p1) / 2, (0, 0, 0), verts, self.coll, self.mat(mat),
                     0.0, r2)
        o.rotation_mode = "QUATERNION"
        o.rotation_quaternion = d.normalized().to_track_quat("Z", "Y")
        return self.add(o, group)

    def beam(self, p0, p1, w, h, mat="body", bev=0.0, group=None, up=(0, 0, 1)):
        """Rectangular beam from p0 to p1 (w across, h in the 'up'-ish direction)."""
        p0, p1 = Vector(p0), Vector(p1)
        d = p1 - p0
        o = box(f"{self.name}_b", (w, h, d.length), (0, 0, 0), self.coll, 0, self.mat(mat))
        z = d.normalized()
        upv = Vector(up)
        if abs(z.dot(upv)) > 0.98:
            upv = Vector((1, 0, 0))
        x = upv.cross(z).normalized()
        y = z.cross(x)
        m = Matrix((x, y, z)).transposed().to_4x4()
        m.translation = (p0 + p1) / 2
        o.matrix_basis = m
        if bev:
            bevel(o, bev, 2)
        return self.add(o, group)

    def prof(self, pts, depth, plane="XZ", loc=(0, 0, 0), mat="body", bev=0.0, group=None, rot=(0, 0, 0)):
        o = extrude_profile(f"{self.name}_e", pts, depth, plane, self.coll, self.mat(mat), loc)
        o.rotation_euler = rot
        if bev:
            bevel(o, bev, 2)
        return self.add(o, group)

    def lathe(self, profile, axis="X", loc=(0, 0, 0), mat="body", verts=32, group=None, rot=(0, 0, 0)):
        o = lathe(f"{self.name}_l", profile, verts, self.coll, self.mat(mat), axis, loc)
        o.rotation_euler = rot
        return self.add(o, group)

    def mesh(self, verts, faces, mat="body", group=None, smooth=False):
        o = mesh_obj(f"{self.name}_m", verts, faces, self.coll, smooth)
        set_mat(o, self.mat(mat))
        return self.add(o, group)

    # ---- finishing
    def _merge(self, objs, nm, origin=None):
        objs = [o for o in objs if o is not None]
        for o in objs:
            if o.modifiers:
                apply_mods(o)
            if o.rotation_mode != "XYZ":
                pass
        o = join(objs, nm) if len(objs) > 1 else objs[0]
        o.name = nm
        o.data.name = nm
        # bake transform, then set origin
        o.data.transform(o.matrix_basis)
        o.matrix_basis = Matrix.Identity(4)
        if origin == "center":
            vs = [v.co for v in o.data.vertices]
            mn = Vector([min(v[i] for v in vs) for i in range(3)])
            mx = Vector([max(v[i] for v in vs) for i in range(3)])
            c = (mn + mx) / 2
        elif origin is not None:
            c = Vector(origin)
        else:
            c = Vector()
        if c.length:
            o.data.transform(Matrix.Translation(-c))
            o.location = c
        o.parent = self.root
        return o

    def finish(self, origins=None, recenter_xy=True, recenter_z=True):
        origins = origins or {}
        self._merge(self.parts, f"{self.name}_body")
        for g, objs in self.groups.items():
            self._merge(objs, f"{self.name}_{g}", origins.get(g, "center"))
        if recenter_xy:
            recenter(self.root, recenter_z)
        return self.root


def recenter(root, z=True):
    """Shift children so the root sits at the centre of the XY footprint, z=0 at the lowest point."""
    bpy.context.view_layer.update()
    kids = [o for o in root.children if o.type == "MESH"]
    pts = [o.matrix_world @ v.co for o in kids for v in o.data.vertices]
    if not pts:
        return
    mn = Vector([min(p[i] for p in pts) for i in range(3)])
    mx = Vector([max(p[i] for p in pts) for i in range(3)])
    off = Vector(((mn.x + mx.x) / 2, (mn.y + mx.y) / 2, mn.z)) - root.location
    if abs(off.z) < 0.02 or not z:
        off.z = 0.0
    root["_off"] = list(off)
    for o in root.children:
        if o.name.endswith("_body") and o.type == "MESH" and o.location.length < 1e-6:
            o.data.transform(Matrix.Translation(-off))
        else:
            o.location -= off


def combine(name, coll, parts):
    """parts: list of (generator, kwargs, dx, suffix). Builds each and re-parents under one root."""
    root = empty(name, coll=coll or bpy.context.scene.collection)
    root.empty_display_size = 1.0
    for fn, kw, dx, suf in parts:
        sub = fn(coll=coll, name=f"{name}_{suf}", **kw)
        for o in list(sub.children):
            o.parent = root
            o.location.x += dx
        bpy.data.objects.remove(sub)
    recenter(root)
    return root


# =====================================================================  wheels
def wheel(k, R, W, loc, rim=0.62, style="alloy", group=None, verts=32, hub="body", dual=False):
    """Tyre (LIB_Dark) + rim. loc = axle centre. Outer face toward the side of loc.y."""
    x, y, z = loc
    side = 1 if y >= 0 else -1
    group = group or f"wheel_{'F' if x > 0 else 'R'}{'L' if side > 0 else 'R'}_{abs(int(x * 100))}"
    offs = [0.0] if not dual else [-W * 0.52, W * 0.52]
    for oi, oy in enumerate(offs):
        yc = y + side * oy
        h = W / 2
        Rr = R * rim
        S = R - Rr
        tyre = [(-h * 0.86, Rr), (-h, Rr + 0.12 * S), (-h * 1.03, Rr + 0.55 * S), (-h * 0.97, R - 0.14 * S),
                (-h * 0.82, R - 0.03 * S), (-h * 0.55, R), (h * 0.55, R), (h * 0.82, R - 0.03 * S),
                (h * 0.97, R - 0.14 * S), (h * 1.03, Rr + 0.55 * S), (h, Rr + 0.12 * S), (h * 0.86, Rr)]
        k.lathe(tyre, "Y", (x, yc, z), "dark", verts, group)
        outer = (oi == len(offs) - 1)
        s = side
        if style == "alloy":
            rp = [(-h * 0.55, 0.0), (-h * 0.55, Rr * 0.3), (-h * 0.75, Rr * 0.9), (-h * 0.86, Rr * 1.01),
                  (h * 0.86, Rr * 1.01), (h * 0.75, Rr * 0.9), (h * 0.55, Rr * 0.3), (h * 0.55, 0.0)]
            k.lathe(rp, "Y", (x, yc, z), hub, verts, group)
            if outer:
                k.cyly(Rr * 0.2, 0.02, (x, yc + s * h * 0.56, z), mat="dark", verts=16, group=group)
                for i in range(5):
                    a = 2 * math.pi * i / 5 + 0.3
                    rr = Rr * 0.6
                    k.box((Rr * 0.26, 0.02, Rr * 0.42), (x + rr * math.cos(a), yc + s * h * 0.55, z + rr * math.sin(a)),
                          "dark", rot=(0, -a + math.pi / 2, 0), group=group)
        else:  # steel / truck wheel: deep dish, dark centre with nut ring
            rp = [(-h * 0.35, 0.0), (-h * 0.35, Rr * 0.55), (-h * 0.7, Rr * 0.75), (-h * 0.86, Rr * 1.01),
                  (h * 0.86, Rr * 1.01), (h * 0.7, Rr * 0.75), (h * 0.35, Rr * 0.55), (h * 0.35, 0.0)]
            k.lathe(rp, "Y", (x, yc, z), hub, verts, group)
            if outer:
                k.cyly(Rr * 0.3, 0.06, (x, yc + s * h * 0.36, z), mat="dark", verts=16, group=group)
                k.cyly(Rr * 0.12, 0.1, (x, yc + s * h * 0.4, z), mat=hub, verts=12, group=group)
    return group


# =====================================================================  body loft
# half ring index layout (from bottom centre, up the +Y side, to the top centre)
#  0 bottom centre, 1-3 bottom corner, 4 mid side, 5 upper side, 6 belt,
#  7-11 greenhouse (fractions GF), 12 side top, 13-14 roof corner, 15-16 roof crown, 17 top centre
GF = (0.1, 0.3, 0.55, 0.8, 0.93)
NH = 18
NR = 2 * NH - 2
J = {"bot": 0, "rock0": 1, "rock": 3, "mid": 4, "up": 5, "belt": 6, "g0": 7, "g1": 11, "top": 12,
     "roof": 14, "crown": 17}


def ridx(k, side):
    return k if side > 0 else (NR - k) % NR


def _ring_half(zb, zs, H, w, wt, rb=0.1, flare=0.0):
    rb = clamp(min(rb, (zs - zb) * 0.35), 0.01, 0.3)
    gh = max(H - zs, 0.02)
    rr = clamp(gh * 0.28, 0.006, 0.07)
    c = clamp(gh * 0.1, 0.003, 0.035)
    zt = max(H - rr - c, zs + 0.005)
    wb = w * 0.975
    wt = min(wt, wb)
    pts = [(0.0, zb), (w - rb, zb), (w - rb * 0.29, zb + rb * 0.29), (w, zb + rb),
           (w + flare, zb + (zs - zb) * 0.5), (w * 0.997, zb + (zs - zb) * 0.86), (w * 0.985, zs)]
    for f in GF:
        pts.append((lerp(wb, wt, f), zs + (zt - zs) * f))
    pts.append((wt, zt))
    pts.append((wt - rr * 0.29, zt + rr * 0.71))
    pts.append((wt - rr, zt + rr))
    pts.append((max(wt * 0.55, 0.01), zt + rr + c * 0.75))
    pts.append((max(wt * 0.25, 0.005), zt + rr + c * 0.96))
    pts.append((0.0, H))
    return pts


def _interp_keys(keys, x):
    if x <= keys[0][0]:
        return keys[0][1:]
    for a, b in zip(keys, keys[1:]):
        if a[0] <= x <= b[0]:
            t = (x - a[0]) / (b[0] - a[0]) if b[0] > a[0] else 0.0
            return tuple(a[i] + (b[i] - a[i]) * t for i in range(1, len(a)))
    return keys[-1][1:]


class Shell:
    """Lofted body shell from side/plan keys (x ascending):  (x, z_bottom, z_belt, z_top, half_w, half_w_top).
    Gives a grid of rings so glass / livery patches can follow the surface exactly."""

    def __init__(self, keys, step=0.05, extra_x=(), rb=0.1, flare=0.0):
        self.keys = keys
        x0, x1 = keys[0][0], keys[-1][0]
        xs = set()
        n = max(2, int(round((x1 - x0) / step)))
        for i in range(n + 1):
            xs.add(round(x0 + (x1 - x0) * i / n, 4))
        for kk in keys:
            xs.add(round(kk[0], 4))
        for e in extra_x:
            if x0 <= e <= x1:
                xs.add(round(e, 4))
        xs = sorted(xs)
        clean = [xs[0]]
        for v in xs[1:]:
            if v - clean[-1] > 0.004:
                clean.append(v)
            else:
                # prefer exact requested values
                if v in [round(e, 4) for e in extra_x]:
                    clean[-1] = v
        self.xs = clean
        self.rings = []
        for x in self.xs:
            zb, zs, H, w, wt = _interp_keys(keys, x)
            half = _ring_half(zb, zs, H, w, wt, rb, flare)
            full = [(x, y, z) for (y, z) in half] + [(x, -y, z) for (y, z) in reversed(half[1:-1])]
            self.rings.append([Vector(p) for p in full])

    def build(self, k, mat="body", name="shell"):
        o = loft(f"{k.name}_{name}", [[tuple(p) for p in r] for r in self.rings], k.coll, smooth=True,
                 mat=k.mat(mat))
        return o

    def _normal(self, i, j):
        r = self.rings
        a = r[min(i + 1, len(r) - 1)][j] - r[max(i - 1, 0)][j]
        b = r[i][(j + 1) % NR] - r[i][(j - 1) % NR]
        n = a.cross(b)
        p = r[i][j]
        out = Vector((0, p.y, p.z - (r[i][0].z + r[i][NH - 1].z) / 2))
        if n.length < 1e-9:
            n = out
        n.normalize()
        if n.dot(out) < 0:
            n = -n
        return n

    def patch(self, k, x0, x1, j0, j1, side=1, mat="glass", off=0.006, group=None, solid=0.0):
        """Surface patch between stations x0..x1 and half-ring indices j0..j1 (on one side, or
        side=0 for a patch that crosses the top centre: j0..(mirror of j0))."""
        ii = [i for i, x in enumerate(self.xs) if x0 - 1e-4 <= x <= x1 + 1e-4]
        if len(ii) < 2:
            return None
        if side == 0:
            jj = list(range(j0, NR - j0 + 1))
        elif side > 0:
            jj = list(range(j0, j1 + 1))
        else:
            jj = [ridx(j, -1) for j in range(j1, j0 - 1, -1)]
        verts, faces = [], []
        for i in ii:
            for j in jj:
                verts.append(tuple(self.rings[i][j] + self._normal(i, j) * off))
        nj = len(jj)
        for a in range(len(ii) - 1):
            for b in range(nj - 1):
                p = a * nj + b
                faces.append((p, p + nj, p + nj + 1, p + 1))
        o = mesh_obj(f"{k.name}_patch", verts, faces, k.coll, smooth=True)
        # orient outward
        me = o.data
        me.update()
        i_mid, j_mid = ii[len(ii) // 2], jj[nj // 2]
        if me.polygons and me.polygons[0].normal.dot(self._normal(ii[0], jj[0])) < 0:
            for poly in me.polygons:
                poly.flip()
        set_mat(o, k.mat(mat))
        if solid:
            s = o.modifiers.new("Solid", "SOLIDIFY")
            s.thickness = solid
            s.offset = -1
        return k.add(o, group)


def arch_cutters(k, wheels, w, depth=0.32, gap=0.045, name="cut"):
    """Closed cylinders for boolean wheel-arch cuts. wheels: list of (x, R)."""
    cs = []
    for (x, R) in wheels:
        for s in (1, -1):
            c = cylinder(f"{k.name}_{name}", R + gap, depth + 0.4, (x, s * (w - depth / 2 + 0.2), R),
                         (math.pi / 2, 0, 0), 40, k.coll, k.m["dark"])
            cs.append(c)
    return cs


def boolean(obj, cutters, op="DIFFERENCE"):
    if not cutters:
        return obj
    cut = join(cutters, f"{obj.name}_cutter") if len(cutters) > 1 else cutters[0]
    cut.data.transform(cut.matrix_basis)
    cut.matrix_basis = Matrix.Identity(4)
    m = obj.modifiers.new("Bool", "BOOLEAN")
    m.operation = op
    m.solver = "EXACT"
    m.object = cut
    try:
        m.material_mode = "TRANSFER"
    except Exception:
        pass
    apply_mods(obj)
    bpy.data.objects.remove(cut)
    return obj


def smooth_sharp(obj, angle=38):
    me = obj.data
    for p in me.polygons:
        p.use_smooth = True
    try:
        me.set_sharp_from_angle(angle=math.radians(angle))
    except Exception:
        pass


def tri_count(objs):
    dg = bpy.context.evaluated_depsgraph_get()
    n = 0
    for o in objs:
        if o.type != "MESH":
            continue
        me = o.evaluated_get(dg).to_mesh()
        me.calc_loop_triangles()
        n += len(me.loop_triangles)
        o.evaluated_get(dg).to_mesh_clear()
    return n


# =====================================================================  cars
CAR_SPECS = {
    # x keys rear->front: (x, zb, zs(belt), H(top), w, wt)
    "sedan": dict(
        L=4.8, wb=2.80, xw=0.05, R=0.33, tw=0.225, rb=0.12,
        keys=[(-2.40, 0.42, 0.80, 0.86, 0.80, 0.70), (-2.33, 0.32, 0.86, 0.96, 0.88, 0.78),
              (-2.15, 0.29, 0.90, 1.02, 0.91, 0.80), (-1.50, 0.28, 0.92, 1.06, 0.92, 0.80),
              (-0.80, 0.28, 0.93, 1.42, 0.92, 0.66), (0.40, 0.28, 0.92, 1.45, 0.92, 0.68),
              (1.25, 0.28, 0.90, 0.99, 0.91, 0.80), (2.12, 0.29, 0.80, 0.85, 0.89, 0.78),
              (2.30, 0.31, 0.73, 0.79, 0.85, 0.73), (2.37, 0.34, 0.66, 0.73, 0.80, 0.68),
              (2.40, 0.40, 0.58, 0.66, 0.73, 0.62)],
        windshield=(0.48, 1.17), backlight=(-1.43, -0.86),
        side=[(-0.98, -0.09), (0.01, 1.08)], mirror_x=1.02),
    "hatch": dict(
        L=4.05, wb=2.55, xw=0.0, R=0.315, tw=0.205, rb=0.11,
        keys=[(-2.025, 0.40, 0.84, 0.94, 0.78, 0.66), (-1.96, 0.30, 0.90, 1.20, 0.85, 0.66),
              (-1.86, 0.28, 0.92, 1.42, 0.86, 0.64), (-1.62, 0.28, 0.93, 1.50, 0.87, 0.64),
              (0.30, 0.28, 0.92, 1.50, 0.87, 0.66), (1.05, 0.28, 0.90, 1.00, 0.87, 0.76),
              (1.80, 0.29, 0.82, 0.86, 0.84, 0.74), (1.97, 0.32, 0.72, 0.78, 0.80, 0.68),
              (2.025, 0.40, 0.62, 0.70, 0.74, 0.62)],
        windshield=(0.36, 1.00), backlight=(-1.94, -1.66),
        side=[(-1.55, -0.12), (-0.04, 0.98)], mirror_x=0.92),
    "suv": dict(
        L=4.75, wb=2.85, xw=0.0, R=0.385, tw=0.255, rb=0.14,
        keys=[(-2.375, 0.50, 1.00, 1.08, 0.88, 0.76), (-2.30, 0.40, 1.04, 1.40, 0.94, 0.78),
              (-2.20, 0.38, 1.06, 1.70, 0.95, 0.78), (-1.95, 0.38, 1.07, 1.78, 0.95, 0.78),
              (0.45, 0.38, 1.06, 1.80, 0.95, 0.80), (1.25, 0.38, 1.04, 1.16, 0.95, 0.86),
              (2.10, 0.40, 0.98, 1.04, 0.93, 0.84), (2.30, 0.44, 0.90, 0.96, 0.89, 0.78),
              (2.375, 0.52, 0.78, 0.86, 0.82, 0.72)],
        windshield=(0.52, 1.18), backlight=(-2.27, -2.0),
        side=[(-1.9, -1.08), (-0.98, -0.12), (-0.02, 1.08)], mirror_x=1.12, cladding=True),
    "pickup": dict(
        L=5.6, wb=3.55, xw=0.25, R=0.40, tw=0.265, rb=0.12,
        keys=[(-2.80, 0.55, 1.18, 1.22, 0.96, 0.92), (-2.74, 0.48, 1.22, 1.26, 0.99, 0.95),
              (-0.85, 0.48, 1.24, 1.28, 1.00, 0.96), (-0.75, 0.48, 1.24, 1.84, 1.00, 0.82),
              (0.95, 0.48, 1.22, 1.88, 1.00, 0.84), (1.65, 0.48, 1.20, 1.36, 1.00, 0.92),
              (2.55, 0.50, 1.16, 1.28, 0.98, 0.92), (2.75, 0.55, 1.06, 1.20, 0.95, 0.88),
              (2.80, 0.62, 0.95, 1.10, 0.90, 0.84)],
        windshield=(1.05, 1.60), backlight=(-0.78, -0.76),
        side=[(-0.66, 0.30), (0.40, 1.52)], mirror_x=1.55, bed=(-2.72, -0.92)),
}


def _car(kind, coll=None, name=None, paint="body", livery=None, roofsign=False, lightbar=False,
         cladding=None):
    sp = CAR_SPECS[kind]
    name = name or f"car_{kind}"
    k = Kit(name, coll)
    keys = sp["keys"]
    L, R, tw = sp["L"], sp["R"], sp["tw"]
    w = max(kk[4] for kk in keys)
    xr, xf = sp["xw"] - sp["wb"] / 2, sp["xw"] + sp["wb"] / 2
    extra = []
    for a, b in [sp["windshield"], sp["backlight"]] + sp["side"]:
        extra += [a, b]
    liv = (xr + R + 0.12, xf - R - 0.12)
    extra += list(liv)
    sh = Shell(keys, step=0.04, extra_x=extra, rb=sp["rb"])
    body = sh.build(k, paint)
    # bed cut (pickup)
    cutters = arch_cutters(k, [(xr, R), (xf, R)], w)
    if sp.get("bed"):
        b0, b1 = sp["bed"]
        zfl = 0.98
        cb = box(f"{name}_bedcut", (b1 - b0, 2 * (w - 0.075), 1.0), ((b0 + b1) / 2, 0, zfl + 0.5), k.coll, 0,
                 k.m["dark"])
        cutters.append(cb)
    boolean(body, cutters)
    smooth_sharp(body, 40)
    bevel(body, 0.012, 2, 40, harden=False)
    k.add(body)

    # ---- glass
    ws, bl = sp["windshield"], sp["backlight"]
    sh.patch(k, ws[0], ws[1], J["roof"], 0, side=0)
    if bl[1] - bl[0] > 0.05:
        sh.patch(k, bl[0], bl[1], J["roof"], 0, side=0)
    for s in (1, -1):
        for a, b in sp["side"]:
            sh.patch(k, a, b, J["g0"], J["g1"], side=s)
    zb_r, zs_r, H_r, w_r, wt_r = keys[0][1:]
    if kind in ("hatch", "suv"):
        pass
    if kind == "pickup":
        # rear cab window (vertical), small box panel
        zs_c = keys[3][2]
        k.box((0.02, 1.25, 0.34), (keys[3][0] - 0.005, 0, zs_c + 0.33), "glass")
        # bed rails & tailgate detail
        k.box((0.04, 1.7, 0.1), (keys[0][0] + 0.005, 0, 1.06), "dark", 0.01)
    # ---- livery / cladding
    if livery:
        lm = "accent" if paint != "accent" else "body"
        for s in (1, -1):
            sh.patch(k, liv[0], liv[1], J["mid"], J["up"], side=s, mat=lm, off=0.004)
        if livery == "full":
            pass
    if cladding if cladding is not None else sp.get("cladding"):
        for s in (1, -1):
            sh.patch(k, xr + R + 0.1, xf - R - 0.1, J["rock0"], J["rock"], side=s, mat="dark", off=0.004)

    # ---- front / rear details
    kf, kr = keys[-1], keys[0]
    xn = kf[0]
    zb_f, zs_f, H_f, w_f, wt_f = kf[1:]
    # grille / intake
    k.box((0.04, w_f * 1.1, (zs_f - zb_f) * 0.32), (xn + 0.005, 0, zb_f + (zs_f - zb_f) * 0.28), "dark", 0.008)
    # headlights: slim units at the corners
    for s in (1, -1):
        k.box((0.1, w_f * 0.46, 0.1), (xn - 0.03, s * w_f * 0.66, zs_f - 0.03), "dark", 0.015)
        k.box((0.1, w_f * 0.34, 0.06), (xn - 0.015, s * w_f * 0.7, zs_f - 0.03), "light", 0.012)
        # tail lights
        k.box((0.06, wt_r * 0.4, 0.07), (kr[0] + 0.012, s * (kr[4] * 0.72), kr[2] - 0.06), "dark", 0.01)
    # rear bumper dark strip and plate recess
    k.box((0.05, kr[4] * 1.5, 0.08), (kr[0] + 0.01, 0, kr[1] + 0.1), "dark", 0.01)
    # mirrors
    mx = sp["mirror_x"]
    zb_m, zs_m, H_m, w_m, wt_m = _interp_keys(keys, mx)
    for s in (1, -1):
        k.box((0.06, 0.08, 0.04), (mx - 0.02, s * (w_m - 0.0), zs_m + 0.05), "dark")
        k.box((0.12, 0.17, 0.11), (mx - 0.04, s * (w_m + 0.1), zs_m + 0.09), paint, 0.025)
        k.box((0.012, 0.13, 0.08), (mx - 0.1, s * (w_m + 0.1), zs_m + 0.09), "glass")
    # roof sign / light bar
    Htop = max(kk[3] for kk in keys)
    xroof = (ws[0] + (bl[1] if bl[1] - bl[0] > 0.05 else keys[1][0])) / 2
    if kind == "pickup":
        xroof = (keys[3][0] + ws[0]) / 2
    if roofsign:
        k.box((0.24, 0.62, 0.05), (xroof, 0, Htop + 0.015), "dark", 0.01)
        k.prof([(-0.28, 0), (0.28, 0), (0.24, 0.26), (-0.24, 0.26)], 0.16, "YZ", (xroof, 0, Htop + 0.035),
               "accent", 0.025)
        k.box((0.18, 0.5, 0.06), (xroof, 0, Htop + 0.18), "light", 0.01)
    if lightbar:
        k.box((0.28, 1.15, 0.06), (xroof + 0.25, 0, Htop + 0.03), "dark", 0.012)
        for s in (1, -1):
            k.box((0.24, 0.5, 0.09), (xroof + 0.25, s * 0.29, Htop + 0.1), "accent" if s > 0 else "light", 0.03)
        k.box((0.25, 0.08, 0.07), (xroof + 0.25, 0, Htop + 0.09), "dark", 0.01)
        # push bar
        k.box((0.06, w_f * 1.1, 0.06), (xn + 0.09, 0, zb_f + 0.18), "dark", 0.012)
        k.box((0.06, w_f * 0.7, 0.06), (xn + 0.09, 0, zs_f - 0.08), "dark", 0.012)
        for s in (1, -1):
            k.box((0.06, 0.06, zs_f - zb_f - 0.14), (xn + 0.09, s * w_f * 0.32, (zs_f + zb_f) / 2 + 0.02), "dark",
                  0.012)

    # ---- wheels
    for x in (xr, xf):
        for s in (1, -1):
            wheel(k, R, tw, (x, s * (w - tw / 2 - 0.015), R), group=f"wheel_{'F' if x == xf else 'R'}{'L' if s > 0 else 'R'}")
    return k.finish()


def car_sedan(coll=None, name="car_sedan", paint="body", **kw):
    return _car("sedan", coll, name, paint, **kw)


def car_hatchback(coll=None, name="car_hatchback", paint="body", **kw):
    return _car("hatch", coll, name, paint, **kw)


def car_suv(coll=None, name="car_suv", paint="body", **kw):
    return _car("suv", coll, name, paint, **kw)


def car_pickup(coll=None, name="car_pickup", paint="body", **kw):
    return _car("pickup", coll, name, paint, **kw)


def car_taxi(coll=None, name="car_taxi", paint="body", base="sedan"):
    return _car(base, coll, name, paint, livery="band", roofsign=True)


def car_security(coll=None, name="car_security", paint="body", base="sedan"):
    return _car(base, coll, name, paint, livery="band", lightbar=True)


# =====================================================================  shared truck parts
def frame(k, x0, x1, z0=0.62, h=0.26, gap=0.42, group=None):
    for s in (1, -1):
        k.box((x1 - x0, 0.09, h), ((x0 + x1) / 2, s * gap, z0 + h / 2), "dark", group=group)
    for x in (x0 + 0.1, (x0 + x1) / 2, x1 - 0.1):
        k.box((0.08, 2 * gap, 0.12), (x, 0, z0 + h / 2), "dark", group=group)


def axle(k, x, R, tw, w_out, dual=False, style="steel", hub="body", rim=0.58, prefix=""):
    yo = w_out - (tw * 1.02 + tw / 2 if dual else tw / 2) - 0.01
    k.cyly(0.07, 2 * yo, (x, 0, R), mat="dark", verts=12)
    for s in (1, -1):
        wheel(k, R, tw, (x, s * yo, R), rim=rim, style=style, hub=hub, dual=dual,
              group=f"{prefix}wheel_{'L' if s > 0 else 'R'}_{x:+.2f}".replace(".", "_"))


def side_glass(k, pts, y, mat="glass", t=0.012):
    """Flat window prism (pts in XZ) sitting on a flat side at |y|; both sides if y>0."""
    for s in (1, -1):
        k.prof(pts, t, "XZ", (0, s * (y + t / 2 - 0.002), 0), mat)


def plate(k, x0, x1, z0, z1, y, mat="accent", t=0.01):
    side_glass(k, [(x0, z0), (x1, z0), (x1, z1), (x0, z1)], y, mat, t)


def mirror_arm(k, x, y, z, s, h=0.42):
    k.box((0.05, 0.25, 0.05), (x, s * (y + 0.1), z + h * 0.8), "dark")
    k.box((0.05, 0.05, 0.05), (x, s * (y + 0.02), z + h * 0.1), "dark")
    k.box((0.05, 0.05, h * 0.85), (x, s * (y + 0.2), z + h * 0.4), "dark")
    k.box((0.08, 0.2, h), (x - 0.02, s * (y + 0.26), z + h * 0.45), "dark", 0.02)


def headlamp(k, x, y, z, wy=0.3, hz=0.14, mat="light"):
    k.box((0.08, wy + 0.05, hz + 0.05), (x - 0.03, y, z), "dark", 0.015)
    k.box((0.08, wy, hz), (x - 0.015, y, z), mat, 0.012)


def cab_over(k, xf, w=1.24, H=3.15, depth=2.15, zb=1.0, paint="body", roof_spoiler=False, sleeper=False):
    """European flat-front cab. Front face at xf, cab floor at zb."""
    xr = xf - depth
    pts = [(xr, zb), (xf, zb), (xf + 0.02, zb + 0.55), (xf, zb + 0.95), (xf - 0.2, H - 0.12),
           (xf - 0.32, H), (xr, H)]
    cab = k.prof(pts, 2 * w, "XZ", (0, 0, 0), paint)
    for v in cab.data.vertices:
        if v.co.z > zb + 1.0:
            v.co.y *= 0.975
    bevel(cab, 0.07, 3, 30)
    # windshield
    a = (xf, zb + 0.98)
    b = (xf - 0.19, H - 0.18)
    ang = math.atan2(b[0] - a[0], b[1] - a[1])
    L = math.dist(a, b)
    k.box((0.02, 2 * w * 0.9, L - 0.08), ((a[0] + b[0]) / 2 + 0.012, 0, (a[1] + b[1]) / 2), "glass",
          rot=(0, ang, 0))
    # door windows
    yw = w * 0.975
    side_glass(k, [(xf - 1.05, zb + 1.0), (xf - 0.1, zb + 1.0), (xf - 0.27, H - 0.28), (xf - 1.05, H - 0.28)], yw)
    # door seam
    for s in (1, -1):
        k.box((0.015, 0.01, zb + 0.9 - zb), (xf - 1.12, s * (w + 0.001), zb + 0.5), "dark")
    # grille, bumper, lamps, steps
    k.box((0.04, 1.5, 0.6), (xf + 0.02, 0, zb + 0.6), "dark", 0.01)
    for i in range(4):
        k.box((0.03, 1.42, 0.03), (xf + 0.045, 0, zb + 0.38 + i * 0.14), paint)
    k.box((0.25, 2 * w + 0.02, 0.38), (xf - 0.02, 0, zb - 0.12), "dark", 0.03)
    for s in (1, -1):
        headlamp(k, xf + 0.1, s * (w - 0.3), zb - 0.08, 0.36, 0.14)
        k.box((0.5, 0.3, 0.04), (xf - 0.55, s * (w - 0.12), zb - 0.35), "dark")
        k.box((0.5, 0.3, 0.04), (xf - 0.55, s * (w - 0.12), zb - 0.75), "dark")
        mirror_arm(k, xf - 0.1, w, zb + 1.1, s)
    k.box((0.08, 2 * w * 0.9, 0.12), (xf - 0.25, 0, H - 0.02), "dark", 0.02)  # sun visor
    if roof_spoiler:
        sp = k.prof([(xr + 0.1, H), (xf - 0.45, H), (xr + 0.15, H + 0.75)], 2 * w * 0.9, "XZ", (0, 0, 0), paint)
        bevel(sp, 0.05, 2)
    return cab


def shell_cab(k, keys, xs_window, paint="body", windshield=None, R_front=None, x_front_axle=None,
              mirror_x=None, cut_w=None, grille=True):
    """Conventional (hooded) cab from Shell keys."""
    extra = []
    for a, b in xs_window + ([windshield] if windshield else []):
        extra += [a, b]
    sh = Shell(keys, step=0.05, extra_x=extra, rb=0.08)
    body = sh.build(k, paint)
    w = max(kk[4] for kk in keys)
    if R_front:
        boolean(body, arch_cutters(k, [(x_front_axle, R_front)], cut_w or w, depth=0.36))
    smooth_sharp(body, 40)
    bevel(body, 0.015, 2, 40, harden=False)
    k.add(body)
    if windshield:
        sh.patch(k, windshield[0], windshield[1], J["roof"], 0, side=0)
    for s in (1, -1):
        for a, b in xs_window:
            sh.patch(k, a, b, J["g0"], J["g1"] - 1, side=s)
    kf = keys[-1]
    xn, zb_f, zs_f, H_f, w_f, wt_f = kf
    if grille:
        k.box((0.04, w_f * 1.2, (H_f - zb_f) * 0.55), (xn + 0.01, 0, zb_f + (H_f - zb_f) * 0.45), "dark", 0.01)
    for s in (1, -1):
        headlamp(k, xn + 0.02, s * w_f * 0.78, zs_f - 0.05, 0.3, 0.13)
    if mirror_x:
        zb_m, zs_m, H_m, w_m, wt_m = _interp_keys(keys, mirror_x)
        for s in (1, -1):
            mirror_arm(k, mirror_x, w_m, zs_m, s, 0.4)
    return sh


# =====================================================================  vans
def van_delivery(coll=None, name="van_delivery", paint="body", livery=True):
    k = Kit(name, coll)
    R, tw = 0.37, 0.235
    xr, xf = -1.695, 1.97
    keys = [(-2.965, 0.47, 1.20, 2.52, 0.98, 0.92), (-2.93, 0.40, 1.20, 2.62, 1.0, 0.95),
            (1.00, 0.40, 1.18, 2.62, 1.0, 0.95), (1.30, 0.40, 1.16, 2.48, 1.0, 0.93),
            (1.55, 0.40, 1.13, 2.12, 1.0, 0.90), (2.30, 0.40, 1.06, 1.22, 0.99, 0.88),
            (2.78, 0.42, 0.96, 1.07, 0.96, 0.84), (2.92, 0.45, 0.82, 0.95, 0.91, 0.78),
            (2.965, 0.50, 0.70, 0.84, 0.85, 0.72)]
    ws = (1.58, 2.27)
    dw = (1.40, 2.24)
    seams = [(0.06, 0.08), (-2.92, -2.9)]
    extra = list(ws) + list(dw) + [x for a in seams for x in a] + [-2.6, 0.9]
    sh = Shell(keys, step=0.05, extra_x=extra, rb=0.1)
    body = sh.build(k, paint)
    boolean(body, arch_cutters(k, [(xr, R), (xf, R)], 1.0))
    smooth_sharp(body, 40)
    bevel(body, 0.012, 2, 40, harden=False)
    k.add(body)
    sh.patch(k, ws[0], ws[1], J["roof"], 0, side=0)
    for s in (1, -1):
        sh.patch(k, dw[0], dw[1], J["g0"], 9, side=s)
        sh.patch(k, 0.06, 0.08, J["rock"], 10, side=s, mat="dark", off=0.003)  # sliding door seam
        if livery:
            sh.patch(k, -2.6, 0.9, J["g0"], 10, side=s, mat="accent" if paint != "accent" else "body", off=0.004)
        sh.patch(k, xr + R + 0.1, xf - R - 0.1, J["rock0"], J["rock"], side=s, mat="dark", off=0.004)
    # rear: windows, door split, bumper, lamps
    k.box((0.02, 0.012, 1.8), (-2.97, 0, 1.45), "dark")
    for s in (1, -1):
        k.box((0.02, 0.68, 0.5), (-2.968, s * 0.43, 2.0), "glass", 0.01)
        k.box((0.05, 0.1, 0.5), (-2.95, s * 0.93, 1.25), "dark", 0.01)
    k.box((0.18, 1.96, 0.22), (-2.93, 0, 0.5), "dark", 0.03)
    k.box((0.2, 1.9, 0.26), (2.93, 0, 0.55), "dark", 0.04)
    k.box((0.04, 1.0, 0.18), (2.965, 0, 0.84), "dark", 0.01)
    for s in (1, -1):
        headlamp(k, 2.92, s * 0.66, 0.9, 0.34, 0.14)
        zb_m, zs_m, H_m, w_m, wt_m = _interp_keys(keys, 2.18)
        mirror_arm(k, 2.18, w_m, zs_m - 0.05, s, 0.3)
    for x in (xr, xf):
        for s in (1, -1):
            wheel(k, R, tw, (x, s * (1.0 - tw / 2 - 0.015), R), style="steel",
                  group=f"wheel_{'F' if x > 0 else 'R'}{'L' if s > 0 else 'R'}")
    return k.finish()


def _cutaway_cab(k, x0, paint, R, xa):
    keys = [(x0, 0.66, 1.30, 2.50, 1.0, 0.93), (x0 + 0.85, 0.66, 1.30, 2.55, 1.0, 0.93),
            (x0 + 1.10, 0.66, 1.27, 2.28, 1.0, 0.92), (x0 + 1.85, 0.66, 1.18, 1.40, 0.99, 0.88),
            (x0 + 2.60, 0.66, 1.10, 1.25, 0.96, 0.84), (x0 + 2.75, 0.68, 0.98, 1.12, 0.92, 0.80),
            (x0 + 2.80, 0.72, 0.88, 1.02, 0.86, 0.74)]
    return shell_cab(k, keys, [(x0 + 0.25, x0 + 1.82)], paint, (x0 + 1.13, x0 + 1.82), R, xa, x0 + 1.95), keys


def truck_box(coll=None, name="truck_box", paint="body", livery=True):
    k = Kit(name, coll)
    x0 = 0.95
    xa, xb = 2.95, -2.05
    R, tw = 0.42, 0.235
    _cutaway_cab(k, x0, paint, R, xa)
    frame(k, -3.65, 3.5, 0.55, 0.24, 0.45)
    # box body
    bx0, bx1, bz0, bz1, bw = -3.75, 0.85, 1.05, 3.5, 1.26
    k.box((bx1 - bx0, 2 * bw, bz1 - bz0), ((bx0 + bx1) / 2, 0, (bz0 + bz1) / 2), paint, 0.04)
    k.box((bx1 - bx0 - 0.1, 2 * bw + 0.05, 0.16), ((bx0 + bx1) / 2, 0, bz0 + 0.05), "dark", 0.02)
    k.box((bx1 - bx0 + 0.02, 2 * bw + 0.04, 0.1), ((bx0 + bx1) / 2, 0, bz1 - 0.04), paint, 0.02)
    n = 7
    for i in range(n + 1):
        x = bx0 + 0.05 + (bx1 - bx0 - 0.1) * i / n
        k.box((0.07, 2 * bw + 0.03, bz1 - bz0 - 0.1), (x, 0, (bz0 + bz1) / 2), paint, 0.01)
    if livery:
        plate(k, bx0 + 0.45, bx1 - 0.45, bz0 + 0.45, bz1 - 0.35, bw + 0.012, "accent" if paint != "accent" else "body")
    # rear roll-up door, bumper
    k.box((0.03, 2 * bw - 0.2, bz1 - bz0 - 0.3), (bx0 - 0.005, 0, (bz0 + bz1) / 2), paint, 0.01)
    for i in range(9):
        k.box((0.02, 2 * bw - 0.24, 0.015), (bx0 - 0.02, 0, bz0 + 0.3 + i * 0.25), "dark")
    k.box((0.12, 2.2, 0.12), (bx0 + 0.15, 0, 0.5), "dark", 0.02)
    for s in (1, -1):
        k.box((0.06, 0.06, 0.45), (bx0 + 0.15, s * 0.7, 0.75), "dark")
        k.box((0.04, 0.12, 0.25), (bx0 - 0.02, s * (bw - 0.12), bz0 + 0.35), "dark", 0.01)
    axle(k, xa, R, tw, 1.0, False)
    axle(k, xb, R, tw, 1.15, True)
    return k.finish()


def truck_armored(coll=None, name="truck_armored_cit", paint="body", livery=True):
    """Cash-in-transit armoured truck: conventional cab + armoured box with small ports."""
    k = Kit(name, coll)
    R, tw = 0.47, 0.255
    xa, xb = 2.55, -1.85
    keys = [(0.62, 0.90, 1.62, 2.42, 1.06, 0.92), (1.55, 0.90, 1.62, 2.46, 1.06, 0.93),
            (2.10, 0.88, 1.58, 1.80, 1.06, 1.0), (3.15, 0.82, 1.50, 1.66, 1.04, 0.97),
            (3.38, 0.80, 1.38, 1.58, 1.0, 0.93), (3.45, 0.84, 1.24, 1.48, 0.95, 0.88)]
    shell_cab(k, keys, [(0.82, 2.05)], paint, (1.60, 2.06), R, xa, 2.05, cut_w=1.06)
    frame(k, -3.4, 3.3, 0.62, 0.26, 0.45)
    k.box((0.25, 2.2, 0.36), (3.48, 0, 0.82), "dark", 0.04)
    bx0, bx1, bz0, bz1, bw = -3.45, 0.55, 1.0, 3.05, 1.22
    k.box((bx1 - bx0, 2 * bw, bz1 - bz0), ((bx0 + bx1) / 2, 0, (bz0 + bz1) / 2), paint, 0.09)
    m = "accent" if paint != "accent" else "body"
    if livery:
        plate(k, bx0 + 0.15, bx1 - 0.15, 1.75, 2.05, bw + 0.006, m)
        k.box((bx1 - bx0 - 0.4, 1.6, 0.03), ((bx0 + bx1) / 2, 0, bz1 + 0.005), m, 0.01)
    for s in (1, -1):
        # side door + ports + small windows
        side_glass(k, [(-1.0, 1.15), (-0.98, 1.15), (-0.98, 2.85), (-1.0, 2.85)], bw, "dark")
        side_glass(k, [(-0.1, 1.15), (-0.08, 1.15), (-0.08, 2.85), (-0.1, 2.85)], bw, "dark")
        side_glass(k, [(-0.75, 2.3), (-0.35, 2.3), (-0.35, 2.6), (-0.75, 2.6)], bw, "glass", 0.02)
        k.cyly(0.05, 0.05, (-0.55, s * (bw + 0.01), 1.45), mat="dark", verts=12)
        k.cyly(0.05, 0.05, (-2.6, s * (bw + 0.01), 1.45), mat="dark", verts=12)
        k.box((0.6, 0.25, 0.05), (-0.55, s * (bw - 0.05), 0.75), "dark", 0.01)
    # rear doors, bumper, roof hatch & beacon
    k.box((0.03, 0.02, 1.8), (bx0 - 0.01, 0, 2.0), "dark")
    k.box((0.03, 0.3, 0.2), (bx0 - 0.01, 0.4, 2.5), "glass")
    k.box((0.2, 2.25, 0.2), (bx0 + 0.05, 0, 0.62), "dark", 0.03)
    k.box((0.6, 0.6, 0.08), (-1.6, 0, bz1 + 0.03), "dark", 0.02)
    k.cyl(0.09, 0.14, (0.2, 0, bz1 + 0.07), mat="light", verts=16)
    k.cyl(0.11, 0.04, (0.2, 0, bz1 + 0.01), mat="dark", verts=16)
    axle(k, xa, R, tw, 1.05, False)
    axle(k, xb, R, tw, 1.2, True)
    return k.finish()


# =====================================================================  bus
def bus_city(coll=None, name="bus_city", paint="body", livery=True):
    k = Kit(name, coll)
    R, tw = 0.5, 0.29
    xa, xb = 3.45, -2.45
    w = 1.275
    keys = [(-6.0, 0.42, 1.05, 2.95, 1.24, 1.16), (-5.94, 0.33, 1.05, 3.05, 1.275, 1.2),
            (5.92, 0.33, 1.05, 3.05, 1.275, 1.2), (6.0, 0.40, 1.05, 2.96, 1.24, 1.16)]
    door = [(4.35, 5.55), (-0.05, 1.25)]
    wins = [(-5.6, -4.25), (-4.15, -2.85), (-2.75, -1.45), (-1.35, -0.15), (1.35, 2.55), (2.65, 4.25),
            (5.65, 5.85)]
    extra = [x for a in door + wins for x in a] + [-5.7, 5.7]
    sh = Shell(keys, step=0.1, extra_x=extra, rb=0.12)
    body = sh.build(k, paint)
    boolean(body, arch_cutters(k, [(xa, R), (xb, R)], w, depth=0.4, gap=0.06))
    smooth_sharp(body, 40)
    bevel(body, 0.012, 2, 40, harden=False)
    k.add(body)
    for s in (1, -1):
        for a, b in wins:
            sh.patch(k, a, b, J["g0"], 10, side=s)
        if livery:
            sh.patch(k, -5.7, 5.7, J["mid"], J["up"], side=s, mat="accent" if paint != "accent" else "body",
                     off=0.004)
    # doors only on the kerb side (right, -Y)
    for a, b in door:
        sh.patch(k, a, b, J["rock"], 10, side=-1, off=0.01)
        sh.patch(k, (a + b) / 2 - 0.01, (a + b) / 2 + 0.01, J["rock"], 10, side=-1, mat="dark", off=0.014)
    # front: windscreen, destination sign, lamps, bumper
    k.box((0.03, 2.3, 1.55), (6.0, 0, 1.95), "glass", 0.02)
    k.box((0.03, 1.9, 0.26), (6.0, 0, 2.86), "dark", 0.02)
    k.box((0.04, 0.02, 1.5), (6.012, 0, 1.95), "dark")
    k.box((0.16, 2.4, 0.3), (6.0, 0, 0.5), "dark", 0.04)
    for s in (1, -1):
        headlamp(k, 6.04, s * 0.9, 0.88, 0.3, 0.12)
        k.box((0.05, 0.05, 0.4), (6.15, s * 1.0, 2.75), "dark")
        k.box((0.3, 0.05, 0.05), (6.05, s * 1.0, 2.95), "dark")
        k.box((0.08, 0.16, 0.4), (6.3, s * 1.0, 2.5), "dark", 0.02)
    # rear
    k.box((0.03, 1.6, 0.6), (-6.0, 0, 2.3), "glass", 0.02)
    k.box((0.03, 1.8, 0.5), (-6.0, 0, 1.0), "dark", 0.02)
    k.box((0.16, 2.4, 0.26), (-6.0, 0, 0.48), "dark", 0.04)
    for s in (1, -1):
        k.box((0.04, 0.12, 0.4), (-6.0, s * 1.1, 1.0), "dark", 0.01)
    # roof pods
    k.box((2.6, 1.7, 0.28), (-0.5, 0, 3.15), paint, 0.08)
    k.box((1.6, 1.4, 0.22), (-4.6, 0, 3.12), paint, 0.06)
    axle(k, xa, R, tw, w - 0.02, False, hub="body")
    axle(k, xb, R, tw, w - 0.02, True, hub="body")
    return k.finish()


# =====================================================================  semi tractor & trailers
TRACTOR_FW = -2.55   # fifth wheel x (pre-recenter)
FW_Z = 1.26


def semi_tractor(coll=None, name="semi_tractor", paint="body", livery=False, fairing=True):
    """US-style conventional sleeper tractor, 6x4."""
    k = Kit(name, coll)
    R, tw = 0.52, 0.29
    xa, xb1, xb2 = 2.35, -2.0, -3.3
    keys = [(-1.00, 0.95, 2.05, 3.36, 1.20, 1.08), (-0.95, 0.92, 2.05, 3.42, 1.24, 1.12),
            (1.00, 0.92, 2.04, 3.40, 1.24, 1.10), (1.40, 0.92, 1.98, 2.24, 1.22, 1.06),
            (1.95, 0.90, 1.55, 2.12, 1.18, 0.86), (3.30, 0.74, 1.40, 1.92, 1.12, 0.80),
            (3.52, 0.70, 1.30, 1.84, 1.05, 0.76), (3.60, 0.74, 1.20, 1.74, 0.97, 0.72)]
    sh = shell_cab(k, keys, [(0.30, 1.37)], paint, (1.04, 1.37), R, xa, None, cut_w=1.24, grille=False)
    for s in (1, -1):
        sh.patch(k, -0.75, -0.35, 8, 9, side=s)  # sleeper bunk window
        sh.patch(k, 0.22, 0.24, J["rock"], J["g0"] - 1, side=s, mat="dark", off=0.003)  # door seam
        if livery:
            sh.patch(k, -0.9, 0.15, J["mid"], J["belt"], side=s, mat="accent" if paint != "accent" else "body",
                     off=0.004)
    # grille + bumper
    k.box((0.06, 1.12, 0.78), (3.60, 0, 1.33), paint, 0.03)
    k.box((0.04, 0.96, 0.66), (3.625, 0, 1.33), "dark", 0.01)
    for i in range(6):
        k.box((0.03, 0.96, 0.025), (3.645, 0, 1.06 + i * 0.11), paint)
    k.box((0.3, 2.42, 0.36), (3.62, 0, 0.62), paint, 0.06)
    for s in (1, -1):
        headlamp(k, 3.45, s * 0.84, 1.3, 0.28, 0.14)
        mirror_arm(k, 1.62, 1.12, 1.95, s, 0.55)
    # fairing + cab extenders
    if fairing:
        fp = [(-0.95, 3.40), (0.95, 3.40), (0.6, 3.6), (0.0, 3.85), (-0.6, 3.98), (-0.95, 4.0)]
        f = k.prof(fp, 2.2, "XZ", (0, 0, 0), paint)
        for v in f.data.vertices:
            if v.co.z > 3.5:
                v.co.y *= 0.96
        bevel(f, 0.06, 3, 30)
        for s in (1, -1):
            k.box((0.35, 0.03, 2.4), (-1.12, s * 1.2, 2.45), paint, 0.01)
    # chassis
    frame(k, -3.9, 3.4, 0.62, 0.3, 0.44)
    for s in (1, -1):
        k.lathe([(-0.65, 0.0), (-0.65, 0.28), (-0.62, 0.32), (0.62, 0.32), (0.65, 0.28), (0.65, 0.0)], "X",
                (0.25, s * 0.92, 0.72), paint, 24)
        for xx in (-0.22, 0.72):
            k.box((0.05, 0.08, 0.66), (xx, s * 0.92, 0.72), "dark")
        k.box((0.5, 0.36, 0.05), (1.62, s * 1.06, 0.5), "dark")  # steps
        k.box((0.5, 0.36, 0.05), (1.62, s * 1.06, 0.82), "dark")
        k.cyl(0.075, 2.5, (-1.17, s * 1.0, 2.75), mat=paint, verts=16)  # stacks
        k.cyl(0.085, 0.8, (-1.17, s * 1.0, 1.9), mat="dark", verts=16)
        k.box((0.4, 0.5, 0.45), (-0.75, s * 0.9, 0.7), "dark", 0.02)  # battery / tool box
        for xx in (xb1 + 0.75, xb2 - 0.62):
            k.box((0.03, 0.6, 0.65), (xx, s * 0.95, 0.62), "dark")  # mud flaps
        k.box((2.2, 0.62, 0.04), ((xb1 + xb2) / 2, s * 0.98, 1.12), "dark", 0.01)  # rear fenders
    k.box((1.6, 1.1, 0.05), (-1.65, 0, 0.95), "dark")  # deck plate
    k.box((0.95, 0.95, 0.1), (TRACTOR_FW, 0, FW_Z - 0.05), "dark", 0.02)  # fifth wheel
    k.box((0.6, 0.8, 0.22), (TRACTOR_FW, 0, FW_Z - 0.2), "dark")
    k.box((0.12, 2.0, 0.1), (-3.9, 0, 0.9), "dark")
    axle(k, xa, R, tw, 1.24, False, hub="body")
    axle(k, xb1, R, tw, 1.24, True, hub="body")
    axle(k, xb2, R, tw, 1.24, True, hub="body")
    root = k.finish()
    root["fifth_wheel_x"] = TRACTOR_FW - root["_off"][0]
    return root


def _trailer_running_gear(k, x_front, x_rear, deck_z, R=0.52, tw=0.29, w=1.27):
    xa1, xa2 = x_rear + 1.9, x_rear + 3.2
    axle(k, xa1, R, tw, w - 0.03, True, hub="body")
    axle(k, xa2, R, tw, w - 0.03, True, hub="body")
    # suspension sub-frame
    for s in (1, -1):
        k.box((3.0, 0.12, deck_z - R - 0.15), ((xa1 + xa2) / 2, s * 0.5, (deck_z + R + 0.12) / 2), "dark")
    # rear underride guard
    k.box((0.12, 2.3, 0.14), (x_rear + 0.2, 0, 0.55), "dark", 0.02)
    for s in (1, -1):
        k.box((0.1, 0.1, deck_z - 0.6), (x_rear + 0.3, s * 0.75, (deck_z + 0.6) / 2), "dark")
    # landing gear
    xl = x_front - 2.4
    for s in (1, -1):
        k.box((0.14, 0.14, deck_z - 0.15), (xl, s * 0.95, (deck_z + 0.15) / 2 + 0.05), "dark", 0.01)
        k.box((0.35, 0.3, 0.06), (xl, s * 0.95, 0.04), "dark", 0.01)
    k.cyly(0.03, 1.9, (xl, 0, 0.55), mat="dark", verts=8)
    k.box((0.25, 0.1, 0.25), (xl, -1.1, deck_z - 0.35), "dark")
    # kingpin
    k.cyl(0.05, 0.1, (x_front - 0.91, 0, FW_Z - 0.04 + 0.05), mat="dark", verts=12)
    return xa1, xa2


def trailer_box(coll=None, name="trailer_box_40ft", paint="body", livery=False, skirts=True, length=12.19):
    """Dry-van box trailer (default 40 ft). Kingpin 0.91 m behind the front wall."""
    k = Kit(name, coll)
    L, w = length, 1.27
    xf, xr = L / 2, -L / 2
    z0, z1 = FW_Z + 0.04, 4.0
    k.box((L, 2 * w, z1 - z0), (0, 0, (z0 + z1) / 2), paint, 0.04)
    k.box((L - 0.04, 2 * w + 0.03, 0.2), (0, 0, z0 + 0.06), "dark", 0.015)
    for s in (1, -1):
        k.box((L + 0.01, 0.05, 0.1), (0, s * (w - 0.01), z1 - 0.045), paint, 0.015)
    n = int(L / 1.2)
    for i in range(1, n):
        x = xr + L * i / n
        k.box((0.06, 2 * w + 0.022, z1 - z0 - 0.2), (x, 0, (z0 + z1) / 2 + 0.02), paint, 0.008)
    for s in (1, -1):
        k.box((0.1, 0.1, z1 - z0), (xr + 0.05, s * (w - 0.04), (z0 + z1) / 2), paint, 0.02)
        k.box((0.1, 0.1, z1 - z0), (xf - 0.05, s * (w - 0.04), (z0 + z1) / 2), paint, 0.02)
    if livery:
        plate(k, xr + 1.0, xf - 1.0, z0 + 0.45, z1 - 0.35, w + 0.012, "accent" if paint != "accent" else "body")
    # rear doors
    k.box((0.02, 0.02, z1 - z0 - 0.3), (xr - 0.01, 0, (z0 + z1) / 2), "dark")
    for yy in (-0.95, -0.35, 0.35, 0.95):
        k.cyl(0.02, z1 - z0 - 0.35, (xr - 0.04, yy, (z0 + z1) / 2), mat="dark", verts=8)
    for s in (1, -1):
        k.box((0.05, 0.14, 0.3), (xr - 0.02, s * (w - 0.15), z0 + 0.3), "dark", 0.01)
    # front: kingpin plate shadow
    k.box((2.0, 2.2, 0.08), (xf - 1.0, 0, z0 - 0.04), "dark")
    # under-carriage: cross members
    for s in (1, -1):
        k.box((L - 0.6, 0.1, 0.25), (0, s * 0.5, z0 - 0.12), "dark")
    xa1, xa2 = _trailer_running_gear(k, xf, xr, z0)
    if skirts:
        for s in (1, -1):
            sx0, sx1 = max(xa1, xa2) + 0.85, xf - 2.75
            k.box((sx1 - sx0, 0.02, 0.85), ((sx0 + sx1) / 2, s * (w - 0.05), z0 - 0.45), "dark", 0.005)
    root = k.finish()
    root["kingpin_x"] = xf - 0.91 - root["_off"][0]
    return root


def trailer_tanker(coll=None, name="trailer_tanker", paint="body", livery=True, length=12.2):
    k = Kit(name, coll)
    L, w = length, 1.27
    xf, xr = L / 2, -L / 2
    r, zc = 1.12, FW_Z + 1.12 + 0.12
    prof = [(xr + 0.05, 0.0), (xr + 0.05, 0.4), (xr + 0.13, 0.85), (xr + 0.3, 1.06), (xr + 0.5, r), (xf - 0.5, r),
            (xf - 0.3, 1.06), (xf - 0.13, 0.85), (xf - 0.05, 0.4), (xf - 0.05, 0.0)]
    t = k.lathe(prof, "X", (0, 0, 0), paint, 48)
    t.data.transform(Matrix.Scale(0.86, 4, (0, 0, 1)))
    t.location = (0, 0, zc)
    zt = zc + r * 0.86
    # rings / accent band
    for xx in [xr + 0.55 + i * (L - 1.1) / 5 for i in range(6)]:
        o = k.lathe([(xx - 0.04, 0), (xx - 0.04, r + 0.02), (xx + 0.04, r + 0.02), (xx + 0.04, 0)], "X", (0, 0, 0),
                    paint, 48)
        o.data.transform(Matrix.Scale(0.86, 4, (0, 0, 1)))
        o.location = (0, 0, zc)
    if livery:
        o = k.lathe([(-2.6, 0), (-2.6, r + 0.012), (2.6, r + 0.012), (2.6, 0)], "X", (0, 0, 0),
                    "accent" if paint != "accent" else "body", 48)
        o.data.transform(Matrix.Scale(0.86, 4, (0, 0, 1)))
        o.location = (0, 0, zc)
    # walkway, rails, manholes
    k.box((L - 1.6, 0.5, 0.05), (0, 0, zt + 0.04), "dark")
    for i in range(4):
        k.cyl(0.25, 0.1, (-3.6 + i * 2.4, 0, zt + 0.06), mat=paint, verts=20)
    for s in (1, -1):
        k.cyl(0.02, L - 1.8, (0, s * 0.35, zt + 0.42), rot=(0, math.pi / 2, 0), mat="dark", verts=8)
        for i in range(8):
            k.cyl(0.02, 0.4, (xr + 1.0 + i * (L - 2.0) / 7, s * 0.35, zt + 0.22), mat="dark", verts=8)
    # ladder at rear
    for s in (1, -1):
        k.box((0.04, 0.04, zt - 1.0), (xr + 0.02, s * 0.25, (zt + 1.0) / 2), "dark")
    for i in range(7):
        k.box((0.03, 0.5, 0.03), (xr + 0.02, 0, 1.2 + i * (zt - 1.2) / 7), "dark")
    # chassis + saddles + pipe cabinet
    for s in (1, -1):
        k.box((L - 0.4, 0.12, 0.25), (0, s * 0.5, FW_Z + 0.02), "dark")
        k.box((3.0, 0.4, 0.45), (0.0, s * 1.0, FW_Z - 0.05), "dark", 0.02)
        k.cyl(0.06, 3.2, (0.0, s * 1.05, FW_Z - 0.35), rot=(0, math.pi / 2, 0), mat=paint, verts=10)
    k.box((2.0, 1.6, 0.6), (xf - 1.0, 0, FW_Z + 0.25), "dark")
    _trailer_running_gear(k, xf, xr, FW_Z + 0.1)
    root = k.finish()
    root["kingpin_x"] = xf - 0.91 - root["_off"][0]
    return root


def trailer_flatbed(coll=None, name="trailer_flatbed", paint="body", load="lumber", length=12.19):
    k = Kit(name, coll)
    L, w = length, 1.27
    xf, xr = L / 2, -L / 2
    dz = FW_Z + 0.32
    k.box((L, 2 * w, 0.1), (0, 0, dz - 0.05), paint, 0.02)
    k.box((L, 2 * w + 0.04, 0.16), (0, 0, dz - 0.16), "dark", 0.01)
    # gooseneck beams
    for s in (1, -1):
        k.prof([(xr, dz - 0.25), (xf, dz - 0.25), (xf, dz - 0.5), (xf - 3.0, dz - 0.5), (xf - 4.5, dz - 0.75),
                (xr + 0.3, dz - 0.6)], 0.12, "XZ", (0, s * 0.5, 0), "dark")
    k.box((0.1, 2 * w, 1.6), (xf - 0.1, 0, dz + 0.8), "dark", 0.02)  # headboard
    for i in range(5):
        k.box((0.12, 2 * w - 0.1, 0.04), (xf - 0.1, 0, dz + 0.25 + i * 0.32), paint)
    for i in range(14):
        for s in (1, -1):
            k.box((0.06, 0.04, 0.08), (xr + 0.4 + i * (L - 0.8) / 13, s * (w + 0.02), dz - 0.08), paint)
    # load
    xa = xr + 0.4
    if load == "lumber":
        bl = 2.3
        n = int((L - 0.6) / (bl + 0.1))
        for i in range(n):
            xc = xr + 0.35 + bl / 2 + i * (bl + 0.1)
            for lev in range(2):
                for s in (1, -1):
                    k.box((bl, 1.15, 0.6), (xc, s * 0.6, dz + 0.06 + 0.3 + lev * 0.68), paint, 0.02)
                k.box((bl - 0.1, 2.3, 0.07), (xc, 0, dz + 0.04 + lev * 0.68), "dark")
            for dx in (-0.6, 0.6):
                k.box((0.05, 2 * w + 0.02, 0.02), (xc + dx, 0, dz + 1.42), "dark")
                for s in (1, -1):
                    k.box((0.05, 0.02, 1.4), (xc + dx, s * (w - 0.04), dz + 0.71), "dark")
    elif load == "crates":
        sizes = [(2.0, 2.1, 1.6), (2.0, 2.1, 1.6), (1.6, 2.2, 1.2), (1.6, 2.2, 1.2), (2.4, 2.3, 1.9)]
        x = xf - 0.35
        for (a, b, c) in sizes:
            k.box((a, b, c), (x - a / 2, 0, dz + c / 2), paint, 0.03)
            for d in (-a * 0.3, a * 0.3):
                k.box((0.05, b + 0.02, 0.05), (x - a / 2 + d, 0, dz + c + 0.01), "dark")
                for s in (1, -1):
                    k.box((0.05, 0.02, c), (x - a / 2 + d, s * (b / 2 + 0.01), dz + c / 2), "dark")
            x -= a + 0.15
    elif load == "pipes":
        for row in range(3):
            for j in range(5 - row):
                yy = (j - (4 - row) / 2) * 0.46
                k.cylx(0.22, L - 1.2, (-0.2, yy, dz + 0.24 + row * 0.4), mat=paint, verts=20)
        for xx in (-4, 0, 4):
            k.box((0.1, 2.4, 0.06), (xx, 0, dz + 1.3), "dark")
    _trailer_running_gear(k, xf, xr, dz - 0.25)
    root = k.finish()
    root["kingpin_x"] = xf - 0.91 - root["_off"][0]
    return root


def semi_truck(coll=None, name="semi_truck_box", trailer="box", paint="body", livery=True, **tkw):
    """Tractor coupled to a trailer (separate objects: <name>_tractor_* and <name>_trailer_*)."""
    root = empty(name, coll=coll or bpy.context.scene.collection)
    tr = semi_tractor(coll=coll, name=f"{name}_tractor", paint=paint)
    fn = {"box": trailer_box, "tanker": trailer_tanker, "flatbed": trailer_flatbed}[trailer]
    kw = dict(paint=paint, **tkw)
    if trailer in ("box", "tanker"):
        kw["livery"] = livery
    tl = fn(coll=coll, name=f"{name}_trailer", **kw)
    dx = tr["fifth_wheel_x"] - tl["kingpin_x"]
    for sub, d in ((tr, 0.0), (tl, dx)):
        for o in list(sub.children):
            o.parent = root
            o.location.x += d
        bpy.data.objects.remove(sub)
    bpy.context.view_layer.update()
    recenter(root)
    return root


# =====================================================================  rigid trucks
def _rigid_chassis(k, xf, xr, axles, R=0.53, tw=0.3, w=1.25):
    frame(k, xr, xf - 0.3, 0.65, 0.3, 0.44)
    for i, x in enumerate(axles):
        axle(k, x, R, tw, w, dual=(i > 0), hub="body")
    k.box((0.12, 2.2, 0.14), (xr + 0.1, 0, 0.55), "dark", 0.02)


def truck_dump(coll=None, name="truck_dump", paint="body", bin_paint=None):
    k = Kit(name, coll)
    xf, xr = 4.2, -4.3
    axles = [3.15, -1.55, -2.9]
    cab_over(k, xf, 1.24, 3.15, 2.05, 1.05, paint)
    _rigid_chassis(k, xf, xr, axles)
    bp = bin_paint or paint
    # dump body: tapered bin, open top
    x0, x1, zf, zt = -4.35, 1.85, 1.3, 2.75
    outer = [(x0, zf + 0.25), (x0 + 0.5, zf), (x1, zf), (x1, zt + 0.25), (x0, zt)]
    ob = k.prof(outer, 2.5, "XZ", (0, 0, 0), bp)
    inner = box(f"{name}_bincut", (x1 - x0 - 0.2, 2.3, 2.0), ((x0 + x1) / 2 - 0.05 + 0.3, 0, zf + 0.2 + 1.0),
                k.coll, 0, k.m["dark"])
    boolean(ob, [inner])
    bevel(ob, 0.03, 2, 30)
    # canopy over cab and ribs
    k.prof([(x1, zt + 0.25), (x1 + 0.9, zt + 0.35), (x1 + 0.9, zt + 0.42), (x1 - 0.1, zt + 0.42)], 2.4, "XZ",
           (0, 0, 0), bp, 0.02)
    for i in range(5):
        xx = x0 + 0.8 + i * (x1 - x0 - 1.2) / 4
        for s in (1, -1):
            k.box((0.1, 0.06, zt - zf - 0.1), (xx, s * 1.27, (zt + zf) / 2 - 0.05), bp, 0.01)
    for s in (1, -1):
        k.box((x1 - x0, 0.08, 0.1), ((x0 + x1) / 2, s * 1.28, zt - 0.05), bp, 0.01)
    k.box((x1 - x0 - 0.3, 1.1, 0.2), ((x0 + x1) / 2, 0, zf - 0.12), "dark")
    k.cyl(0.12, 1.0, (x1 + 0.1, 0, 1.6), mat="dark", verts=16)  # ram
    return k.finish()


def truck_mixer(coll=None, name="truck_mixer", paint="body", drum_paint=None, drum_stripes=True):
    k = Kit(name, coll)
    xf, xr = 4.2, -4.4
    axles = [3.15, -1.55, -2.9]
    cab_over(k, xf, 1.24, 3.15, 2.05, 1.05, paint)
    _rigid_chassis(k, xf, xr, axles)
    dp = drum_paint or paint
    # drum: axis tilted up toward the rear
    tilt = math.radians(14)
    Ld = 4.6
    prof = [(0.0, 0.0), (0.0, 0.55), (0.3, 0.95), (1.5, 1.22), (2.6, 1.22), (3.9, 0.85), (4.45, 0.42),
            (4.6, 0.36), (4.6, 0.0)]
    pivot = Vector((1.6, 0, 1.95))
    drum = k.lathe([(-x, r) for (x, r) in prof], "X", (0, 0, 0), dp, 40, group="drum")
    mats_ = []
    if drum_stripes:
        # helical fin stripe painted on the drum
        verts, faces = [], []
        N = 140
        turns = 2.2
        for i in range(N + 1):
            t = i / N
            xx = 0.35 + t * 4.0
            # radius along profile
            rr = None
            for (a, ra), (b, rb_) in zip(prof, prof[1:]):
                if a <= xx <= b and b > a:
                    rr = ra + (rb_ - ra) * (xx - a) / (b - a)
            rr = (rr or 1.0) + 0.012
            ang = turns * 2 * math.pi * t
            for d in (-0.12, 0.12):
                verts.append((-(xx + d), rr * math.cos(ang), rr * math.sin(ang)))
        for i in range(N):
            a = 2 * i
            faces.append((a, a + 2, a + 3, a + 1))
        k.mesh(verts, faces, "accent" if dp != "accent" else "dark", group="drum", smooth=True)
    for o in k.groups["drum"]:
        o.matrix_basis = Matrix.Translation(pivot) @ Matrix.Rotation(-tilt, 4, "Y") @ o.matrix_basis
    # drum supports, chute, water tank, ladder
    k.box((0.3, 1.4, 0.75), (1.75, 0, 1.3), "dark", 0.02)
    k.prof([(-2.7, 1.0), (-2.4, 1.0), (-2.6, 2.6), (-2.85, 2.6)], 1.4, "XZ", (0, 0, 0), "dark", 0.02)
    tail = pivot + Matrix.Rotation(-tilt, 3, "Y") @ Vector((-4.6, 0, 0))
    k.box((0.6, 0.7, 0.5), (tail.x - 0.1, 0, tail.z - 0.5), "dark", 0.03)
    ch = k.box((1.3, 0.45, 0.06), (tail.x - 0.75, 0, tail.z - 0.95), "dark", rot=(0, math.radians(20), 0))
    k.cyl(0.32, 1.6, (1.95, 0, 1.02), rot=(math.pi / 2, 0, 0), mat=paint, verts=24)
    for s in (1, -1):
        k.box((3.8, 0.06, 0.12), (-0.6, s * 1.15, 1.05), "dark")
    for i in range(9):
        k.box((0.04, 0.5, 0.04), (tail.x + 0.35, -0.75, 0.6 + i * 0.25), "dark")
    for s in (1, -1):
        k.box((0.05, 0.05, 2.2), (tail.x + 0.35, -0.75 + s * 0.25, 1.65), "dark")
    root = k.finish(origins={"drum": tuple(pivot)})
    return root


# =====================================================================  industrial
def _corrugated(k, x0, x1, y, z0, z1, side, pitch=0.28, depth=0.036, mat="body", axis="x"):
    """Trapezoidal corrugated wall panel. axis='x': runs along X at |y|, bulging outward (side=+-1).
    axis='y': runs along Y at x=y (end wall), bulging toward +X if side>0."""
    n = max(2, int(round((x1 - x0) / pitch)))
    p = (x1 - x0) / n
    line = []
    for i in range(n):
        a = x0 + i * p
        line += [(a, 0.0), (a + p * 0.18, depth), (a + p * 0.5, depth), (a + p * 0.68, 0.0)]
    line.append((x1, 0.0))
    poly = line + [(x1, -0.02), (x0, -0.02)]
    if axis == "x":
        pts = [(u, y + side * v) for (u, v) in poly]
    else:
        pts = [(y + side * v, u) for (u, v) in poly]
    if side < 0 if axis == "x" else side > 0:
        pts = list(reversed(pts))
    o = k.prof(pts, z1 - z0, "XY", (0, 0, (z0 + z1) / 2), mat)
    return o


def container(coll=None, name="container_20ft", length=6.058, paint="body", frame="body"):
    """ISO container: corrugated sides/ends/doors, corner castings (LIB_Dark), locking bars. Doors at -X."""
    k = Kit(name, coll)
    L, W, H = length, 2.438, 2.591
    xr, xf, w = -L / 2, L / 2, W / 2
    c = 0.16  # corner post size
    zb, zt = 0.16, H - 0.11
    for s in (1, -1):
        _corrugated(k, xr + c, xf - c, s * (w - 0.04), zb, zt, s, mat=paint)
        # rails
        k.box((L, 0.16, 0.16), (0, s * (w - 0.08), 0.08), frame, 0.012)
        k.box((L, 0.12, 0.11), (0, s * (w - 0.06), H - 0.055), frame, 0.012)
    _corrugated(k, -w + c, w - c, xf - 0.04, zb, zt, 1, 0.26, 0.04, paint, axis="y")
    k.box((0.16, W, 0.16), (xf - 0.08, 0, 0.08), frame, 0.012)
    k.box((0.16, W, 0.12), (xf - 0.08, 0, H - 0.06), frame, 0.012)
    k.box((0.16, W, 0.2), (xr + 0.08, 0, 0.1), frame, 0.012)
    k.box((0.16, W, 0.22), (xr + 0.08, 0, H - 0.11), frame, 0.012)
    # roof + floor
    k.box((L - 0.1, W - 0.12, 0.04), (0, 0, H - 0.04), paint, 0.01)
    k.box((L - 0.1, W - 0.1, 0.1), (0, 0, 0.1), "dark")
    # corner posts and castings
    for sx in (1, -1):
        for sy in (1, -1):
            k.box((c, c, H), (sx * (L / 2 - c / 2), sy * (w - c / 2), H / 2), frame, 0.01)
            for zz in (0.06, H - 0.06):
                k.box((0.18, 0.165, 0.12), (sx * (L / 2 - 0.088), sy * (w - 0.08), zz), "dark", 0.008)
    # doors (two leaves, vertical corrugation) + locking bars
    for s in (1, -1):
        _corrugated(k, 0.01 if s > 0 else -w + c, w - c if s > 0 else -0.01, xr + 0.04, 0.2, H - 0.22, -1,
                    0.3, 0.025, paint, axis="y")
    k.box((0.03, 0.02, H - 0.42), (xr + 0.005, 0, H / 2), "dark")
    for yy in (-0.85, -0.3, 0.3, 0.85):
        k.cyl(0.022, H - 0.35, (xr - 0.035, yy, H / 2), mat="dark", verts=8)
        k.box((0.04, 0.05, 0.07), (xr - 0.02, yy, 0.3), "dark")
        k.box((0.04, 0.05, 0.07), (xr - 0.02, yy, H - 0.3), "dark")
        k.box((0.04, 0.2, 0.04), (xr - 0.06, yy + 0.1, 1.2), "dark")
    for s in (1, -1):
        for zz in (0.5, 1.3, 2.1):
            k.box((0.05, 0.12, 0.08), (xr - 0.01, s * (w - 0.16), zz), "dark")
    if L < 7:
        for s in (1, -1):
            for xx in (-1.0, 1.0):
                k.box((0.35, 0.02, 0.1), (xx, s * w, 0.08), "dark")
    return k.finish()


def container_40ft(coll=None, name="container_40ft", paint="body", **kw):
    return container(coll, name, 12.192, paint, **kw)


def forklift(coll=None, name="forklift", paint="body", fork_height=0.1):
    k = Kit(name, coll)
    Rf, Rr = 0.33, 0.26
    xa, xb = 0.55, -1.0
    w = 0.58
    # chassis side profile
    pts = [(-1.55, 0.3), (0.85, 0.3), (0.9, 0.55), (0.78, 0.95), (0.25, 0.98), (0.0, 1.05), (-0.95, 1.05),
           (-1.45, 1.0), (-1.62, 0.8)]
    ch = k.prof(pts, 2 * w * 0.86, "XZ", (0, 0, 0), paint)
    bevel(ch, 0.04, 2, 30)
    # fenders over front wheels
    for s in (1, -1):
        k.prof([(xa - 0.42, 0.62), (xa + 0.42, 0.62), (xa + 0.38, 0.72), (xa - 0.38, 0.72)], 0.32, "XZ",
               (0, s * (w - 0.1), 0), paint, 0.02)
    # counterweight (rounded)
    cw = k.prof([(-1.62, 0.25), (-0.95, 0.25), (-0.95, 1.12), (-1.35, 1.12), (-1.62, 0.95), (-1.7, 0.6)],
                2 * w, "XZ", (0, 0, 0), paint)
    bevel(cw, 0.1, 3, 30)
    k.box((0.04, 0.6, 0.12), (-1.69, 0, 0.6), "dark", 0.01)
    # seat, steering, hood
    k.box((0.42, 0.48, 0.12), (-0.45, 0, 1.12), "dark", 0.04)
    k.box((0.12, 0.48, 0.5), (-0.68, 0, 1.38), "dark", 0.04)
    k.box((0.4, 0.5, 0.25), (0.15, 0, 1.12), "dark", 0.05)
    k.tube((0.15, 0, 1.15), (0.0, 0, 1.55), 0.025, "dark")
    k.cyl(0.17, 0.03, (0.0, 0, 1.56), rot=(0, math.radians(-35), 0), mat="dark", verts=20)
    # overhead guard
    gz = 2.15
    for (x0, x1) in ((0.55, 0.5), (-1.05, -1.0)):
        for s in (1, -1):
            k.tube((x0, s * (w - 0.06), 0.95), (x1, s * (w - 0.06), gz), 0.035, "dark", 10)
    k.box((1.75, 2 * w - 0.05, 0.06), (-0.25, 0, gz), "dark", 0.015)
    for i in range(6):
        k.box((0.06, 2 * w - 0.12, 0.06), (-0.95 + i * 0.28, 0, gz + 0.05), paint, 0.01)
    # mast
    mx = 0.98
    for s in (1, -1):
        k.box((0.1, 0.08, 2.3), (mx, s * 0.36, 1.25), "dark", 0.01)
        k.box((0.08, 0.06, 2.15), (mx + 0.07, s * 0.29, 1.35), "dark", 0.01)
    for zz in (0.25, 1.3, 2.35):
        k.box((0.08, 0.8, 0.08), (mx, 0, zz), "dark", 0.01)
    k.tube((mx - 0.05, 0, 0.35), (mx - 0.05, 0, 1.9), 0.05, "body", 12)
    # carriage + forks
    fz = fork_height
    k.box((0.06, 0.95, 0.5), (mx + 0.15, 0, fz + 0.3), paint, 0.01)
    for i in range(4):
        k.box((0.03, 0.03, 0.9), (mx + 0.19, -0.33 + i * 0.22, fz + 0.75), "dark")
    k.box((0.04, 0.95, 0.03), (mx + 0.19, 0, fz + 1.2), "dark")
    for s in (1, -1):
        k.box((1.1, 0.12, 0.045), (mx + 0.75, s * 0.3, fz + 0.02), "dark", 0.008)
        k.box((0.05, 0.12, 0.45), (mx + 0.21, s * 0.3, fz + 0.22), "dark", 0.008)
    for x, R, tw in ((xa, Rf, 0.22), (xb, Rr, 0.18)):
        for s in (1, -1):
            wheel(k, R, tw, (x, s * (w - tw / 2), R), rim=0.55, style="steel",
                  group=f"wheel_{'F' if x > 0 else 'R'}{'L' if s > 0 else 'R'}")
    return k.finish()


def wheel_loader(coll=None, name="wheel_loader", paint="body"):
    """Articulated wheel loader (~CAT 950 class)."""
    k = Kit(name, coll)
    R, tw = 0.8, 0.6
    xa, xb = 1.6, -1.7
    w = 1.3
    # rear frame: engine hood, fenders, counterweight
    k.prof([(-3.7, 0.7), (-0.5, 0.7), (-0.5, 1.55), (-1.3, 1.6), (-3.4, 1.6), (-3.75, 1.3)], 1.6, "XZ", (0, 0, 0),
           "dark", 0.03)
    hood = k.prof([(-3.75, 1.45), (-1.2, 1.45), (-1.2, 2.45), (-3.3, 2.3), (-3.75, 2.1)], 1.5, "XZ", (0, 0, 0),
                  paint)
    for v in hood.data.vertices:
        if v.co.z > 2.0:
            v.co.y *= 0.88
    bevel(hood, 0.07, 3, 30)
    k.box((0.06, 1.2, 0.5), (-3.76, 0, 1.75), "dark", 0.02)
    k.cyl(0.07, 0.5, (-2.5, 0.3, 2.6), mat="dark", verts=12)
    cw = k.prof([(-4.05, 0.75), (-3.55, 0.75), (-3.55, 1.5), (-3.95, 1.5), (-4.1, 1.2)], 2.3, "XZ", (0, 0, 0),
                paint)
    bevel(cw, 0.08, 3, 30)
    for s in (1, -1):
        k.prof([(xb - 1.0, 1.55), (xb - 0.75, 1.75), (xb + 0.8, 1.75), (xb + 1.05, 1.5)], 0.75, "XZ",
               (0, s * (w + 0.0), 0), paint, 0.03)
    # cab
    cz0, cz1 = 1.6, 3.45
    cab = k.prof([(-1.55, cz0), (0.3, cz0), (0.4, cz1 - 0.15), (0.25, cz1), (-1.5, cz1), (-1.6, cz1 - 0.1)],
                 1.55, "XZ", (0, 0, 0), "glass")
    bevel(cab, 0.05, 2, 30)
    k.box((2.05, 1.7, 0.12), (-0.62, 0, cz1 + 0.04), paint, 0.04)
    for (xx, zz) in ((0.3, 0), (-1.52, 0)):
        for s in (1, -1):
            k.box((0.1, 0.1, cz1 - cz0), (xx + (0.05 if xx > 0 else 0), s * 0.75, (cz0 + cz1) / 2), paint, 0.02)
    k.box((1.95, 1.62, 0.3), (-0.62, 0, cz0 + 0.12), paint, 0.03)
    # front frame
    k.prof([(-0.4, 0.75), (2.3, 0.75), (2.6, 1.1), (2.5, 1.5), (0.5, 1.6), (-0.4, 1.4)], 1.1, "XZ", (0, 0, 0),
           "dark", 0.03)
    for s in (1, -1):
        k.prof([(xa - 0.95, 1.5), (xa - 0.7, 1.72), (xa + 0.75, 1.72), (xa + 1.0, 1.45)], 0.75, "XZ",
               (0, s * w, 0), paint, 0.03)
    # lift arms (+ linkage), pivots
    p0 = Vector((0.75, 0, 2.15))
    p1 = Vector((3.45, 0, 0.75))
    for s in (1, -1):
        a0 = Vector((p0.x, s * 0.62, p0.z))
        mid = Vector((2.4, s * 0.62, 1.95))
        a1 = Vector((p1.x, s * 0.62, p1.z))
        k.beam(a0, mid, 0.16, 0.42, paint, 0.03)
        k.beam(mid, a1, 0.16, 0.36, paint, 0.03)
        k.tube((0.6, s * 0.75, 1.2), (2.2, s * 0.75, 1.75), 0.09, "dark", 12)  # lift cylinders
    k.beam((2.4, -0.62, 1.95), (2.4, 0.62, 1.95), 0.2, 0.25, paint, 0.02)
    k.tube((1.2, 0, 2.45), (2.75, 0, 2.6), 0.1, "dark", 12)  # tilt cylinder
    k.beam((2.75, 0, 2.6), (3.2, 0, 1.2), 0.18, 0.3, paint, 0.02)  # Z-bar
    # bucket
    bpts = [(3.25, 0.1), (3.35, 1.45), (3.55, 1.55), (3.75, 1.2), (3.75, 1.15), (3.45, 1.05), (3.55, 0.35),
            (3.85, 0.15), (4.55, 0.06), (4.6, 0.0), (3.4, 0.0)]
    bk = k.prof(bpts, 3.0, "XZ", (0, 0, 0), paint)
    bevel(bk, 0.02, 2, 30)
    for s in (1, -1):
        k.prof([(3.3, 0.02), (4.55, 0.02), (3.6, 1.5), (3.3, 1.45)], 0.06, "XZ", (0, s * 1.48, 0), paint, 0.01)
    k.box((0.25, 3.0, 0.04), (4.5, 0, 0.02), "dark")
    for x in (xa, xb):
        k.cyly(0.15, 2 * w - 0.2, (x, 0, R), mat="dark", verts=12)
        for s in (1, -1):
            wheel(k, R, tw, (x, s * (w - tw / 2 + 0.15), R), rim=0.55, style="steel",
                  group=f"wheel_{'F' if x > 0 else 'R'}{'L' if s > 0 else 'R'}")
    # tread lugs: chevrons as dark bars on tyres are too fine for library scale; skip.
    return k.finish()


def crane_mobile(coll=None, name="crane_mobile", paint="body", boom_paint=None, boom_angle=0.0, extend=0.0):
    """All-terrain mobile crane, 4 axles. boom_angle in degrees (0 = transport), extend 0..1."""
    k = Kit(name, coll)
    bp = boom_paint or paint
    R, tw = 0.62, 0.42
    w = 1.27
    axles = [3.9, 2.25, -1.6, -3.25]
    # carrier
    k.prof([(-5.6, 0.75), (5.2, 0.75), (5.5, 1.0), (5.5, 1.55), (-5.5, 1.55), (-5.7, 1.3)], 2 * w, "XZ",
           (0, 0, 0), paint, 0.06)
    k.box((10.6, 2 * w + 0.02, 0.2), (-0.1, 0, 0.88), "dark")
    # carrier cab (front left), low
    cx = 5.6
    cab = k.prof([(cx - 1.7, 1.5), (cx, 1.5), (cx - 0.05, 2.1), (cx - 0.45, 3.15), (cx - 1.7, 3.15)], 1.0, "XZ",
                 (0, 0.75, 0), paint)
    bevel(cab, 0.06, 2, 30)
    a, b = (cx - 0.05, 2.15), (cx - 0.42, 3.05)
    k.box((0.02, 0.85, math.dist(a, b) - 0.05), ((a[0] + b[0]) / 2 + 0.015, 0.75, (a[1] + b[1]) / 2), "glass",
          rot=(0, math.atan2(b[0] - a[0], b[1] - a[1]), 0))
    k.prof([(cx - 1.6, 2.15), (cx - 0.15, 2.15), (cx - 0.47, 2.95), (cx - 1.6, 2.95)], 0.02, "XZ",
           (0, 1.255, 0), "glass")
    headlamp(k, 5.52, 1.0, 1.25, 0.3, 0.12)
    headlamp(k, 5.52, -1.0, 1.25, 0.3, 0.12)
    k.box((0.2, 2 * w, 0.3), (5.55, 0, 0.85), "dark", 0.03)
    # outrigger boxes
    for x in (4.75, -4.6):
        k.box((0.5, 2 * w + 0.06, 0.35), (x, 0, 1.15), "dark", 0.02)
    # superstructure on turntable at x=-2.4
    tx = -2.4
    k.cyl(1.1, 0.25, (tx, 0, 1.68), mat="dark", verts=32)
    k.prof([(tx - 2.4, 1.8), (tx + 1.3, 1.8), (tx + 1.3, 2.6), (tx - 2.4, 2.6)], 2.3, "XZ", (0, 0, 0), paint, 0.06)
    k.box((1.0, 2.4, 1.0), (tx - 2.5, 0, 2.3), paint, 0.06)  # counterweight
    k.box((1.0, 2.2, 0.6), (tx - 2.5, 0, 2.95), "dark", 0.04)
    # operator cab on the left of the boom
    oc = k.prof([(tx - 0.5, 1.9), (tx + 1.25, 1.9), (tx + 1.3, 2.9), (tx + 1.0, 3.2), (tx - 0.5, 3.2)], 0.85,
                "XZ", (0, -0.95, 0), paint)
    bevel(oc, 0.05, 2, 30)
    k.box((0.02, 0.7, 0.75), (tx + 1.29, -0.95, 2.55), "glass", rot=(0, math.radians(-3), 0))
    k.prof([(tx - 0.2, 2.25), (tx + 1.1, 2.25), (tx + 1.1, 3.0), (tx - 0.2, 3.0)], 0.02, "XZ", (0, -1.38, 0),
           "glass")
    # boom (group) pivot
    piv = Vector((tx - 0.9, 0.25, 2.9))
    secs = [(10.2, 0.9, 0.95), (9.5, 0.78, 0.82), (9.5, 0.66, 0.7), (9.5, 0.55, 0.58)]
    ext = 0.0
    x0 = -0.6
    for i, (Ls, bw, bh) in enumerate(secs):
        start = x0 + (0 if i == 0 else 0.4 + i * 0.3 + extend * (i * 8.6))
        k.box((Ls, bw, bh), (start + Ls / 2, 0, 0), bp, 0.04, group="boom")
    tip = x0 + 0.4 + 3 * 0.3 + extend * 3 * 8.6 + secs[-1][0]
    k.box((0.7, 0.7, 0.8), (tip - 0.05, 0, -0.1), bp, 0.04, group="boom")
    for yy in (-0.15, 0.15):
        k.cyly(0.28, 0.08, (tip + 0.15, yy, -0.15), mat="dark", verts=20, group="boom")
    hook_drop = 1.2
    k.tube((tip + 0.3, 0, -0.3), (tip + 0.3, 0, -0.3 - hook_drop), 0.02, "dark", 6, group="boom")
    k.box((0.3, 0.3, 0.45), (tip + 0.3, 0, -0.45 - hook_drop), "accent", 0.04, group="boom")
    k.tube((1.2, 0, -0.45), (3.2, 0, -1.75), 0.14, "dark", 12, group="boom")  # luffing ram (approx)
    for o in k.groups["boom"]:
        o.matrix_basis = (Matrix.Translation(piv) @ Matrix.Rotation(math.radians(boom_angle), 4, "Y").inverted()
                          @ o.matrix_basis)
    k.box((0.4, 0.5, 0.5), (tx + 0.3, 0.25, 2.65), "dark", 0.02)
    if boom_angle < 5:
        k.box((0.3, 1.0, 1.25), (4.6, 0.25, 2.05), "dark", 0.02)  # boom rest
    else:  # outriggers deployed
        for x in (4.75, -4.6):
            for sy in (1, -1):
                k.box((0.3, 2.2, 0.25), (x, sy * (w + 1.0), 1.15), "dark", 0.02)
                k.box((0.22, 0.22, 1.0), (x, sy * (w + 2.0), 0.6), "dark", 0.02)
                k.cyl(0.35, 0.08, (x, sy * (w + 2.0), 0.04), mat="dark", verts=20)
    for x in axles:
        axle(k, x, R, tw, w, False, hub="body")
    return k.finish(origins={"boom": tuple(piv)})


def crane_gantry(coll=None, name="crane_sts_gantry", paint="body", boom_up=False, with_container=True):
    """Ship-to-shore container gantry crane. Boom points +X (over the water). Origin at the centre of the
    leg footprint (the boom overhangs: outreach ~52 m, backreach ~18 m). Rails run along Y."""
    k = Kit(name, coll)
    span, gauge = 30.5, 17.0
    hx, hy = span / 2, gauge / 2
    zt = 44.0  # girder underside
    leg = 1.6
    for sx in (1, -1):
        for sy in (1, -1):
            k.beam((sx * hx, sy * hy, 1.4), (sx * hx, sy * hy, zt + 0.5), leg, leg, paint, 0.08)
        # sill beam with bogies
        k.box((2.0, gauge + 4.0, 1.2), (sx * hx, 0, 1.4), paint, 0.08)
        for sy in (1, -1):
            for dy in (-1.2, 1.2):
                k.box((1.4, 1.8, 0.9), (sx * hx, sy * (hy + 1.5) + dy, 0.45), "dark", 0.05)
        # upper cross-beam (Y) under girder and portal beam
        k.box((leg, gauge + leg, 2.2), (sx * hx, 0, zt - 0.6), paint, 0.06)
        k.box((leg * 0.8, gauge, 1.6), (sx * hx, 0, 14.0), paint, 0.06)
        # diagonal bracing in the Y plane above the portal beam
        k.beam((sx * hx, hy, 14.8), (sx * hx, -hy, zt - 1.7), 0.6, 0.6, paint, 0.03)
    for sy in (1, -1):
        # portal beams along X at mid height + diagonals
        k.box((span + leg, leg * 0.8, 1.8), (0, sy * hy, 14.0), paint, 0.06)
        k.beam((-hx, sy * hy, 14.9), (hx, sy * hy, zt - 1.7), 0.7, 0.7, paint, 0.03)
    # main girders + boom (two box girders at y=+-3)
    gy = 3.0
    xb0, xb1 = -hx - 18.0, hx + 2.0
    for sy in (1, -1):
        k.box((xb1 - xb0, 1.4, 3.2), ((xb0 + xb1) / 2, sy * gy, zt + 1.6), paint, 0.08)
    for xx in (xb0 + 1, -hx, hx):
        k.box((1.2, 2 * gy + 1.4, 1.2), (xx, 0, zt + 2.6), paint, 0.05)
    # boom (separate object, pivot at waterside)
    piv = Vector((hx + 2.0, 0, zt + 1.6))
    bl = 52.0
    for sy in (1, -1):
        k.box((bl, 1.3, 3.0), (piv.x + bl / 2, sy * gy, piv.z - 0.1), paint, 0.08, group="boom")
    for i in range(6):
        k.box((1.0, 2 * gy, 0.8), (piv.x + 4 + i * (bl - 6) / 5, 0, piv.z - 1.2), paint, 0.04, group="boom")
    k.box((1.0, 2 * gy + 1.3, 3.0), (piv.x + bl - 0.5, 0, piv.z - 0.1), paint, 0.06, group="boom")
    ang = math.radians(80 if boom_up else 0)
    for o in k.groups["boom"]:
        o.matrix_basis = Matrix.Translation(piv) @ Matrix.Rotation(-ang, 4, "Y") @ Matrix.Translation(-piv) @ o.matrix_basis
    # A-frame apex + stays
    apex_z = zt + 26.0
    ax = hx - 2.0
    for sy in (1, -1):
        k.beam((ax + 4.0, sy * gy, zt + 3.2), (ax, sy * gy * 0.6, apex_z), 1.1, 1.1, paint, 0.05)
        k.beam((ax - 9.0, sy * gy, zt + 3.2), (ax, sy * gy * 0.6, apex_z), 1.1, 1.1, paint, 0.05)
        k.beam((ax, sy * gy * 0.6, apex_z), (xb0 + 1.0, sy * gy, zt + 3.2), 0.35, 0.35, paint)
        if not boom_up:
            for frac in (0.55, 1.0):
                k.beam((ax, sy * gy * 0.6, apex_z - 0.5), (piv.x + bl * frac - 1.0, sy * gy, zt + 3.0), 0.3, 0.3,
                       paint, group=None)
    k.box((1.6, 2 * gy * 0.6 + 1.1, 1.6), (ax, 0, apex_z), paint, 0.06)
    # machinery house at backreach
    k.box((12.0, 2 * gy + 3.0, 5.0), (xb0 + 9.0, 0, zt + 5.7), paint, 0.12)
    k.box((12.2, 2 * gy + 3.2, 0.3), (xb0 + 9.0, 0, zt + 8.3), "dark", 0.04)
    for i in range(5):
        k.box((1.0, 0.05, 1.2), (xb0 + 4.5 + i * 2.2, gy + 1.53, zt + 6.0), "dark")
    # trolley + operator cab + spreader with container
    if not boom_up:
        tx = hx + 16.0
        k.box((6.0, 2 * gy + 1.0, 1.6), (tx, 0, zt + 0.0), paint, 0.06)
        cab = k.box((3.2, 2.4, 2.6), (tx + 1.4, gy + 1.4, zt - 2.2), paint, 0.1)
        k.box((0.05, 2.0, 1.6), (tx + 3.02, gy + 1.4, zt - 2.0), "glass")
        k.box((2.6, 2.0, 0.05), (tx + 1.4, gy + 1.4, zt - 3.52), "glass")
        sz = 14.0
        for dx in (-1.5, 1.5):
            for dy in (-0.8, 0.8):
                k.tube((tx + dx, dy, zt - 0.8), (tx + dx * 2.5, dy * 1.2, sz + 3.0), 0.05, "dark", 6)
        k.box((12.2, 2.5, 0.45), (tx, 0, sz + 2.85), "dark", 0.04)
        if with_container:
            k.box((12.19, 2.44, 2.59), (tx, 0, sz + 1.3), "accent", 0.05)
    # ladders/stair towers on a landside leg
    root = k.finish(origins={"boom": tuple(piv)}, recenter_xy=False)
    return root


# =====================================================================  sea  (z = 0 is the waterline)
def _cr(keys, x):
    """Catmull-Rom interpolation of key tuples (x ascending) -> tuple of remaining values."""
    xs = [kk[0] for kk in keys]
    if x <= xs[0]:
        return keys[0][1:]
    if x >= xs[-1]:
        return keys[-1][1:]
    for i in range(len(keys) - 1):
        if xs[i] <= x <= xs[i + 1]:
            break
    t = (x - xs[i]) / (xs[i + 1] - xs[i])
    ip, i2 = max(i - 1, 0), min(i + 2, len(keys) - 1)
    out = []
    for j in range(1, len(keys[0])):
        p0, p1, p2, p3 = keys[ip][j], keys[i][j], keys[i + 1][j], keys[i2][j]
        out.append(0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t * t
                          + (-p0 + 3 * p1 - 3 * p2 + p3) * t ** 3))
    return tuple(out)


def _hull_ring(x, B, zk, zd, p, n=40, camber=0.15, flat=0.0):
    """U/V-shaped hull section: deck edge at (+-B, zd), keel at zk; p = fullness (2 = V/round, 8 = boxy)."""
    pts = []
    half = []
    m = n // 2
    for i in range(m + 1):
        a = math.pi / 2 * i / m  # 0 at keel .. pi/2 at deck edge
        y = B * (math.sin(a) ** (2 / p)) if a > 0 else 0.0
        z = zd - (zd - zk) * (math.cos(a) ** (2 / p))
        half.append((y, z))
    # starboard (-y) from deck edge to keel, then port (+y) keel to deck edge, then deck back over the top
    for (y, z) in reversed(half):
        pts.append((x, -y, z))
    for (y, z) in half[1:]:
        pts.append((x, y, z))
    for f in (0.66, 0.33, 0.0, -0.33, -0.66):
        pts.append((x, B * f, zd + camber * (1 - f * f)))
    return pts


def _hull(k, keys, step, n=40, paint="body", bottom="dark", deck="body", boot=0.0, name="hull", sheer_mat=None):
    x0, x1 = keys[0][0], keys[-1][0]
    xs, x = [], x0
    while x < x1 - 1e-6:
        xs.append(x)
        x += step(x) if callable(step) else step
    xs.append(x1)
    secs = []
    for x in xs:
        B, zk, zd, p = _cr(keys, x)
        secs.append(_hull_ring(x, max(B, 0.02), zk, zd, max(p, 1.5), n))
    o = loft(f"{k.name}_{name}", secs, k.coll, smooth=True)
    o.data.materials.append(k.mat(paint))
    o.data.materials.append(k.mat(bottom))
    o.data.materials.append(k.mat(deck))
    for poly in o.data.polygons:
        c = poly.center
        if c.z < boot:
            poly.material_index = 1
        elif poly.normal.z > 0.85:
            poly.material_index = 2
    smooth_sharp(o, 40)
    return k.add(o)


def boxes_mesh(k, items, mat, group=None, bev=0.0):
    """One mesh holding many axis-aligned boxes: items = [(cx,cy,cz,sx,sy,sz)]."""
    verts, faces = [], []
    for (cx, cy, cz, sx, sy, sz) in items:
        b = len(verts)
        hx, hy, hz = sx / 2, sy / 2, sz / 2
        verts += [(cx - hx, cy - hy, cz - hz), (cx + hx, cy - hy, cz - hz), (cx + hx, cy + hy, cz - hz),
                  (cx - hx, cy + hy, cz - hz), (cx - hx, cy - hy, cz + hz), (cx + hx, cy - hy, cz + hz),
                  (cx + hx, cy + hy, cz + hz), (cx - hx, cy + hy, cz + hz)]
        faces += [(b, b + 3, b + 2, b + 1), (b + 4, b + 5, b + 6, b + 7), (b, b + 1, b + 5, b + 4),
                  (b + 1, b + 2, b + 6, b + 5), (b + 2, b + 3, b + 7, b + 6), (b + 3, b, b + 4, b + 7)]
    if not items:
        return None
    o = k.mesh(verts, faces, mat, group)
    if bev:
        bevel(o, bev, 1, 40, harden=False)
    return o


def ship_container(coll=None, name="ship_container", paint="body", stacks=True, length=160.0, seed=3,
                   funnel_band=True):
    """Feeder/Panamax-style container ship, bridge aft. z=0 = waterline, draft ~8 m."""
    import random
    rnd = random.Random(seed)
    k = Kit(name, coll)
    L = length
    s = L / 160.0
    keys = [(-80 * s, 10.0, 1.2, 6.0, 3.0), (-76 * s, 11.6, -3.5, 5.6, 4.0), (-66 * s, 12.5, -7.2, 5.2, 6.0),
            (-40 * s, 12.6, -8.0, 5.0, 8.0), (40 * s, 12.6, -8.0, 5.0, 8.0), (58 * s, 12.0, -8.0, 5.4, 5.0),
            (70 * s, 9.2, -7.4, 6.6, 3.2), (77 * s, 5.0, -5.6, 7.8, 2.4), (80.5 * s, 0.6, -1.0, 8.4, 2.0)]
    _hull(k, keys, lambda x: 0.6 if x > 60 * s or x < -70 * s else 3.0, 44, paint, "dark", "body", boot=0.4)
    # bulbous bow
    k.lathe([(-5.0, 0.0), (-4.0, 1.4), (-1.5, 2.1), (1.0, 2.1), (2.6, 1.5), (3.4, 0.6), (3.6, 0.0)], "X",
            (77 * s, 0, -5.4), "dark", 24)
    # boot-top line and accent sheer stripe
    # forecastle bulwark and mast
    k.cyl(0.35, 10.0, (72 * s, 0, 12.0), mat="body", verts=12)
    k.box((1.0, 4.0, 0.3), (72 * s, 0, 15.5), "body")
    for sy in (1, -1):
        k.cyl(1.0, 0.6, (76 * s, sy * 3.5, 4.0), rot=(0, math.radians(70), sy * math.radians(20)), mat="dark",
              verts=16)
    # breakwater
    k.box((1.0, 24.0, 3.2), (61 * s, 0, 6.8), paint, 0.1)
    # accommodation block + bridge (aft)
    ax0, ax1 = -63 * s, -52 * s
    zz = 5.2
    k.box((ax1 - ax0, 20.0, 18.0), ((ax0 + ax1) / 2, 0, zz + 9.0), paint, 0.25)
    k.box((ax1 - ax0 + 1.0, 25.2, 3.4), ((ax0 + ax1) / 2 + 0.5, 0, zz + 19.7), paint, 0.2)  # bridge deck + wings
    k.box((ax1 - ax0 + 1.2, 25.4, 0.35), ((ax0 + ax1) / 2 + 0.5, 0, zz + 21.55), "dark", 0.05)
    k.box((0.2, 24.0, 1.6), (ax1 + 1.0, 0, zz + 19.9), "glass")
    for sy in (1, -1):
        k.box((ax1 - ax0 - 1.0, 0.2, 1.4), ((ax0 + ax1) / 2, sy * 12.6, zz + 19.9), "glass")
    for lev in range(5):
        for sy in (1, -1):
            k.box((ax1 - ax0 - 2.0, 0.15, 0.9), ((ax0 + ax1) / 2, sy * 10.0, zz + 3.0 + lev * 3.0), "dark")
        k.box((0.15, 16.0, 0.9), (ax1 + 0.02, 0, zz + 3.0 + lev * 3.0), "dark")
    k.box((3.0, 3.0, 6.0), ((ax0 + ax1) / 2 - 1.0, 0, zz + 24.5), paint, 0.1)  # radar mast base
    k.box((0.4, 6.0, 0.3), ((ax0 + ax1) / 2 - 1.0, 0, zz + 27.2), "dark")
    # funnel
    fx = -68 * s
    k.prof([(-3.5, 0), (3.0, 0), (2.4, 12.0), (-3.0, 12.0), (-3.9, 6.0)], 6.0, "XZ", (fx, 0, zz + 4.0), paint, 0.3)
    if funnel_band:
        k.prof([(-3.67, 0), (2.83, 0), (2.62, 3.0), (-3.4, 3.0)], 6.12, "XZ", (fx, 0, zz + 11.0), "accent")
    k.box((5.0, 5.2, 0.4), (fx - 0.3, 0, zz + 16.1), "dark", 0.1)
    # deck: hatch covers and container stacks
    bay = 13.0
    nb = int((58 * s - (-50 * s)) // bay)
    bx0 = -50 * s
    hatch = []
    for i in range(nb):
        xc = bx0 + bay * (i + 0.5)
        hatch.append((xc, 0, 5.6, 12.4, 23.0, 0.8))
    boxes_mesh(k, hatch, "body")
    if stacks:
        cont = {"body": [], "accent": [], "dark": []}
        lash = []
        for i in range(nb):
            xc = bx0 + bay * (i + 0.5)
            t = i / max(nb - 1, 1)
            tiers = 6 if 0.15 < t < 0.85 else (5 if t >= 0.85 else 6)
            if i == nb - 1:
                tiers = 4
            rows = 9
            for r in range(rows):
                y = (r - (rows - 1) / 2) * 2.5
                h = tiers - (1 if r in (0, rows - 1) and rnd.random() < 0.5 else 0) - (rnd.random() < 0.15)
                for tt in range(max(h, 1)):
                    c = rnd.random()
                    m = "accent" if c < 0.22 else ("dark" if c < 0.32 else "body")
                    cont[m].append((xc, y, 6.0 + 1.3 + tt * 2.62, 12.19, 2.42, 2.59))
            lash.append((xc - 6.35, 0, 6.0 + 3.5, 0.3, 22.0, 7.0))
        for m, items in cont.items():
            boxes_mesh(k, items, m)
        boxes_mesh(k, lash, "dark")
    # rails along deck edge (thin)
    for sy in (1, -1):
        k.box((110 * s, 0.1, 1.0), (4 * s, sy * 12.55, 5.6), "dark")
    return k.finish(recenter_z=False)


def tugboat(coll=None, name="tugboat", paint="body", hull_paint=None):
    """Harbour tug ~28 m. z=0 waterline."""
    k = Kit(name, coll)
    hp = hull_paint or paint
    keys = [(-14.0, 4.6, 0.6, 3.0, 3.0), (-12.5, 5.0, -2.0, 2.8, 3.5), (-6.0, 5.2, -3.6, 2.8, 4.0),
            (4.0, 5.1, -3.8, 3.0, 3.6), (9.5, 4.2, -3.4, 3.6, 2.8), (12.8, 2.4, -2.4, 4.3, 2.2),
            (14.0, 0.4, -0.5, 4.6, 2.0)]
    _hull(k, keys, 0.4, 40, hp, "dark", "body", boot=0.25)
    # heavy rubber fendering along the sheer + bow fender
    xs = [x * 0.5 for x in range(-27, 28)]
    for sy in (1, -1):
        for x0, x1 in zip(xs, xs[1:]):
            B0, _, zd0, _ = _cr(keys, x0)
            B1, _, zd1, _ = _cr(keys, x1)
            a = Vector((x0, sy * (B0 + 0.15), zd0 - 0.45))
            b = Vector((x1, sy * (B1 + 0.15), zd1 - 0.45))
            k.beam(a, b, 0.5, 0.6, "dark")
    k.cyl(0.9, 3.6, (13.6, 0, 3.4), rot=(math.pi / 2, 0, 0), mat="dark", verts=20)
    k.cyl(0.6, 4.5, (-14.0, 0, 2.6), rot=(math.pi / 2, 0, 0), mat="dark", verts=20)
    # bulwark
    for sy in (1, -1):
        k.box((16.0, 0.2, 0.9), (-4.5, sy * 4.95, 3.3), paint, 0.04)
    # deckhouse + raised wheelhouse
    k.box((10.0, 6.4, 2.6), (2.5, 0, 4.2), paint, 0.12)
    for sy in (1, -1):
        for i in range(4):
            k.box((0.9, 0.1, 0.7), (-1.5 + i * 2.3, sy * 3.22, 4.5), "glass")
    k.box((4.6, 5.8, 2.4), (4.4, 0, 6.7), paint, 0.1)
    k.box((0.6, 6.4, 0.25), (6.7, 0, 8.0), paint, 0.05)  # visor
    wh = k.box((4.5, 6.0, 2.8), (4.4, 0, 9.3), "glass", 0.08)
    for (xx, yy) in ((6.62, 3.0), (6.62, -3.0), (2.18, 3.0), (2.18, -3.0)):
        k.box((0.2, 0.2, 2.8), (xx, yy, 9.3), paint, 0.02)
    k.box((0.15, 6.05, 1.0), (6.66, 0, 8.4), paint)
    k.box((4.9, 6.4, 0.35), (4.4, 0, 10.85), paint, 0.08)
    # mast + funnels
    k.box((0.6, 0.6, 4.0), (3.4, 0, 12.9), paint, 0.05)
    k.box((0.3, 3.0, 0.25), (3.4, 0, 14.2), "dark")
    k.box((0.25, 1.6, 0.25), (3.4, 0, 13.3), "dark")
    for sy in (1, -1):
        k.prof([(-1.0, 0), (1.0, 0), (0.75, 3.6), (-1.0, 3.8)], 0.9, "XZ", (0.0, sy * 2.1, 5.4), paint, 0.08)
        k.box((1.4, 0.95, 0.3), (-0.12, sy * 2.1, 9.3), "dark", 0.05)
        k.box((1.3, 0.92, 0.6), (-0.1, sy * 2.1, 8.0), "accent")
    # towing winch, H-bitt, staple
    k.cyl(0.8, 2.6, (-5.5, 0, 3.8), rot=(math.pi / 2, 0, 0), mat="dark", verts=20)
    k.box((1.0, 3.6, 1.6), (-5.5, 0, 3.6), paint, 0.06)
    k.box((0.4, 2.0, 1.4), (-10.0, 0, 3.6), "dark", 0.04)
    for sy in (1, -1):
        k.beam((-8.5, sy * 4.2, 3.0), (-8.5, sy * 2.2, 6.0), 0.35, 0.35, paint, 0.03)
    k.beam((-8.5, -2.4, 6.0), (-8.5, 2.4, 6.0), 0.35, 0.35, paint, 0.03)
    return k.finish(recenter_z=False)


def boat_fishing(coll=None, name="boat_fishing", paint="body", hull_paint=None):
    """Small inshore trawler / fishing boat ~12 m, wheelhouse forward, gantry aft. z=0 waterline."""
    k = Kit(name, coll)
    hp = hull_paint or paint
    keys = [(-6.0, 2.0, 0.3, 1.3, 3.0), (-5.0, 2.25, -0.9, 1.25, 3.0), (-1.0, 2.4, -1.3, 1.3, 2.8),
            (2.5, 2.25, -1.3, 1.5, 2.5), (4.8, 1.4, -1.0, 1.95, 2.1), (6.0, 0.15, -0.2, 2.3, 2.0)]
    _hull(k, keys, 0.2, 36, hp, "dark", "body", boot=0.2)
    # bulwark/gunwale cap following the sheer
    xs = [x * 0.4 for x in range(-15, 15)]
    for sy in (1, -1):
        for x0, x1 in zip(xs, xs[1:]):
            B0, _, zd0, _ = _cr(keys, x0)
            B1, _, zd1, _ = _cr(keys, x1)
            k.beam((x0, sy * (B0 - 0.03), zd0 + 0.3), (x1, sy * (B1 - 0.03), zd1 + 0.3), 0.08, 0.6, hp)
            k.beam((x0, sy * (B0 + 0.01), zd0 + 0.62), (x1, sy * (B1 + 0.01), zd1 + 0.62), 0.14, 0.07, "dark")
    # wheelhouse forward
    k.prof([(0.2, 0), (3.3, 0), (3.6, 1.0), (3.3, 2.1), (0.2, 2.1)], 2.6, "XZ", (0, 0, 1.4), paint, 0.06)
    k.box((3.5, 2.8, 0.15), (1.8, 0, 3.55), paint, 0.04)
    a, b = (3.6, 2.45), (3.32, 3.4)
    k.box((0.03, 2.2, math.dist(a, b) - 0.1), ((a[0] + b[0]) / 2 + 0.02, 0, (a[1] + b[1]) / 2), "glass",
          rot=(0, math.atan2(b[0] - a[0], b[1] - a[1]), 0))
    for sy in (1, -1):
        k.box((2.4, 0.03, 0.7), (1.85, sy * 1.31, 3.0), "glass")
    k.box((0.03, 0.9, 0.9), (0.18, 0.5, 2.6), "dark")
    # mast, boom, gantry, net drum, fish hold hatch
    k.cyl(0.08, 4.5, (0.0, 0, 4.4), mat="body", verts=12)
    k.tube((0.0, 0, 3.0), (-4.5, 0, 4.2), 0.06, "body", 10)
    k.tube((0.0, 0, 6.5), (-4.5, 0, 4.2), 0.015, "dark", 6)
    k.box((0.25, 1.0, 0.15), (0.0, 0, 5.8), "dark")
    for sy in (1, -1):
        k.tube((-5.6, sy * 1.6, 1.4), (-5.6, sy * 1.2, 4.2), 0.08, "body", 10)
    k.tube((-5.6, -1.2, 4.2), (-5.6, 1.2, 4.2), 0.08, "body", 10)
    k.cyl(0.5, 1.8, (-4.3, 0, 2.0), rot=(math.pi / 2, 0, 0), mat="dark", verts=20)
    k.box((1.2, 1.2, 0.25), (-1.8, 0, 1.55), paint, 0.04)
    k.box((0.8, 0.5, 0.15), (2.0, 0, 3.7), "dark", 0.02)  # radar
    # buoys / fenders
    for sy in (1, -1):
        for xx in (-2.0, 0.5):
            k.cyl(0.13, 0.5, (xx, sy * 2.42, 0.95), mat="accent", verts=12)
    return k.finish(recenter_z=False)


# =====================================================================  air
def _airfoil(n=12, t=0.12):
    up, lo = [], []
    for i in range(n + 1):
        x = 0.5 * (1 + math.cos(math.pi * i / n))
        yt = 5 * t * (0.2969 * math.sqrt(x) - 0.1260 * x - 0.3516 * x ** 2 + 0.2843 * x ** 3 - 0.1036 * x ** 4)
        up.append((x, yt + 0.01 * t * 4 * x * (1 - x)))
    for i in range(1, n):
        x = 0.5 * (1 - math.cos(math.pi * i / n))
        yt = 5 * t * (0.2969 * math.sqrt(x) - 0.1260 * x - 0.3516 * x ** 2 + 0.2843 * x ** 3 - 0.1036 * x ** 4)
        lo.append((x, -yt + 0.01 * t * 4 * x * (1 - x)))
    return up + lo


def _wing(k, secs, mat="body", vertical=False, t=(0.12, 0.1), mirror=True, group=None):
    """secs: list of (le_x, chord, span_pos, z_or_y_offset). Horizontal wing: span along Y, offset = z.
    Vertical: span along Z, offset = y."""
    objs = []
    for s in ((1, -1) if mirror and not vertical else (1,)):
        rings = []
        for i, (le, c, sp, off) in enumerate(secs):
            tt = t[0] + (t[1] - t[0]) * i / max(len(secs) - 1, 1)
            af = _airfoil(12, tt)
            if vertical:
                rings.append([(le - u * c, off + v * c, sp) for (u, v) in af])
            else:
                rings.append([(le - u * c, s * sp, off + v * c) for (u, v) in af])
        o = loft(f"{k.name}_wing", rings, k.coll, smooth=True, mat=k.mat(mat))
        smooth_sharp(o, 50)
        objs.append(k.add(o, group))
    return objs


def _fuselage(k, keys, n=40, step=0.25, paint="body", glass=None, stripe=None, p=2.0, name="fuselage"):
    x0, x1 = keys[0][0], keys[-1][0]
    xs, x = [], x0
    while x < x1 - 1e-6:
        xs.append(x)
        x += step if x0 + 1.5 < x < x1 - 2.5 else step * 0.35
    xs.append(x1)
    secs = []
    for x in xs:
        hw, bot, top = _cr(keys, x)
        hw = max(hw, 0.01)
        cz = (top + bot) / 2
        h = max((top - bot) / 2, 0.01)
        ring = superellipse(0, 0, cz, hw, h, h, n, p, x)
        secs.append([(x, yy, zz) for (_, yy, zz) in ring])
    o = loft(f"{k.name}_{name}", secs, k.coll, smooth=True, mat=k.mat(paint))
    o.data.materials.append(k.mat("glass"))
    o.data.materials.append(k.mat("accent"))
    for poly in o.data.polygons:
        c = poly.center
        hw, bot, top = _cr(keys, c.x)
        zr = (c.z - bot) / max(top - bot, 1e-3)
        yr = abs(c.y) / max(hw, 1e-3)
        if glass and glass[0] < c.x < glass[1] and glass[2] < zr < glass[3] and poly.normal.x > -0.2:
            poly.material_index = 1
        if stripe and stripe[0] < c.x < stripe[1] and stripe[2] < zr < stripe[3]:
            poly.material_index = 2
    smooth_sharp(o, 60)
    return k.add(o)


from lib import superellipse  # noqa: E402


def _nacelle(k, front, y, z, L, R, mat="body", lip="body"):
    prof = [(0.0, R * 0.8), (0.04 * L, R * 0.95), (0.15 * L, R), (0.6 * L, R * 0.96), (0.85 * L, R * 0.78),
            (0.95 * L, R * 0.62), (0.95 * L, R * 0.4), (1.08 * L, 0.0)]
    k.lathe([(front - a, r) for (a, r) in prof], "X", (0, y, z), mat, 28)
    k.cylx(R * 0.8, 0.04, (front - 0.12 * L, y, z), mat="dark", verts=28)


def _gear_leg(k, x, y, ztop, R, tw, n_wheels=2, axle_y=0.0, group=None):
    k.tube((x, y, ztop), (x, y, R), 0.08 if R > 0.4 else 0.05, "dark", 10)
    if n_wheels == 1:
        offs = [0.0]
    else:
        offs = [-(tw / 2 + 0.03), tw / 2 + 0.03]
    k.cyly(0.05, (tw + 0.1) * len(offs), (x, y, R), mat="dark", verts=8)
    for o in offs:
        k.lathe([(-tw / 2, R * 0.5), (-tw / 2, R * 0.85), (-tw * 0.4, R), (tw * 0.4, R), (tw / 2, R * 0.85),
                 (tw / 2, R * 0.5)], "Y", (x, y + o, R), "dark", 20)
        k.cyly(R * 0.55, tw * 0.9, (x, y + o, R), mat="body", verts=16)


def airliner(coll=None, name="plane_airliner", paint="body", livery=True):
    """Narrow-body twinjet (A320 class): 37.6 m long, 34.1 m span (with sharklets), gear down."""
    k = Kit(name, coll)
    keys = [(-18.8, 0.2, 5.0, 5.25), (-18.3, 0.45, 4.7, 5.42), (-15.5, 1.15, 3.6, 5.62), (-12.0, 1.78, 2.4, 5.72),
            (-8.0, 1.98, 1.77, 5.73), (13.0, 1.98, 1.77, 5.73), (15.0, 1.95, 1.8, 5.66), (16.6, 1.76, 1.9, 5.35),
            (17.8, 1.3, 2.15, 4.85), (18.5, 0.7, 2.6, 4.3), (18.8, 0.05, 3.2, 3.5)]
    _fuselage(k, keys, 48, 0.4, paint, glass=(15.9, 17.25, 0.6, 0.78),
              stripe=(-11.5, 15.0, 0.3, 0.36) if livery else None)
    lm = "accent" if livery else paint
    # cabin windows + doors
    wins = []
    for i in range(int((12.2 + 11.5) / 0.53)):
        x = -11.5 + i * 0.53
        if abs(x - 2.0) < 0.6 or abs(x - (-0.3)) < 0.3:
            continue
        for sy in (1, -1):
            wins.append((x, sy * 1.965, 4.25, 0.22, 0.04, 0.3))
    for (xd, wd) in ((14.4, 0.85), (-13.6, 0.85), (2.0, 0.6)):
        for sy in (1, -1):
            for (dx, dz, sx, sz) in ((-wd / 2, 0, 0.04, 1.85), (wd / 2, 0, 0.04, 1.85)):
                wins.append((xd + dx, sy * 1.97, 3.75, sx, 0.03, sz))
            wins.append((xd, sy * 1.97, 4.66, wd, 0.03, 0.04))
            wins.append((xd, sy * 1.97, 2.84, wd, 0.03, 0.04))
    boxes_mesh(k, wins, "dark")
    # wing (root, kink, tip)
    tan = math.tan(math.radians(27))
    zr = 2.25
    dih = math.tan(math.radians(5))
    ws = [(3.5, 6.6, 0.5, zr), (3.5 - (6.3 - 1.95) * tan, 3.5 - (6.3 - 1.95) * tan + 3.1, 6.3, zr + 6.3 * dih),
          (3.5 - (16.6 - 1.95) * tan, 1.55, 16.6, zr + 16.6 * dih)]
    _wing(k, ws, paint, t=(0.14, 0.1))
    # sharklets
    tip_le, tip_c, tip_y, tip_z = ws[-1]
    for sy in (1, -1):
        rings = []
        for (h, c, dx, dy) in ((0.0, 1.4, 0.0, 0.0), (0.5, 1.0, -0.35, 0.2), (2.4, 0.6, -1.45, 0.35)):
            af = _airfoil(10, 0.09)
            rings.append([(tip_le - 0.1 + dx - u * c, sy * (tip_y + dy) + v * c * 0.5, tip_z + h) for (u, v) in af])
        o = loft(f"{name}_sharklet", rings, k.coll, smooth=True, mat=k.mat(lm))
        k.add(o)
    # flap-track fairings
    for yy in (3.5, 7.5, 10.5, 13.5):
        for sy in (1, -1):
            le = 3.5 - (yy - 1.95) * tan
            c = max(6.6 - (yy - 1.95) * 0.35, 2.0)
            k.lathe([(0, 0), (0.3, 0.14), (1.4, 0.16), (2.0, 0.0)], "X", (le - c * 0.55, sy * yy, zr + yy * dih - 0.15),
                    "body", 10, rot=(0, 0, math.pi))
    # engines
    for sy in (1, -1):
        ey = 5.75
        le = 3.5 - (ey - 1.95) * tan
        wz = zr + ey * dih
        _nacelle(k, le + 2.6, sy * ey, wz - 1.3, 4.4, 1.05, paint)
        k.prof([(le + 1.6, wz - 0.3), (le - 1.2, wz - 0.1), (le - 1.6, wz - 0.4), (le + 1.6, wz - 0.95)], 0.35,
               "XZ", (0, sy * ey, 0), paint, 0.03)
    # belly fairing
    k.lathe([(-4.5, 0.0), (-4.0, 0.9), (-1.0, 1.5), (3.0, 1.5), (5.0, 1.0), (5.8, 0.0)], "X", (0, 0, 1.95),
            paint, 24).scale = (1, 1.2, 0.45)
    # tail: horizontal stabiliser + fin
    st = math.tan(math.radians(32))
    _wing(k, [(-13.0, 3.6, 0.3, 4.6), (-13.0 - 6.0 * st, 1.4, 6.3, 4.6 + 6.0 * 0.1)], paint, t=(0.11, 0.09))
    ft = math.tan(math.radians(36))
    _wing(k, [(-11.0, 6.2, 5.2, 0.0), (-11.0 - 6.4 * ft, 2.1, 11.75, 0.0)], lm, vertical=True, t=(0.12, 0.1))
    # landing gear
    _gear_leg(k, -1.0, 3.8, 2.4, 0.57, 0.36)
    _gear_leg(k, -1.0, -3.8, 2.4, 0.57, 0.36)
    _gear_leg(k, 13.5, 0.0, 2.0, 0.37, 0.2)
    return k.finish()


def plane_bizjet(coll=None, name="plane_bizjet", paint="body", livery=True):
    """Light/midsize business jet: rear-mounted engines, T-tail. 15.6 m long, 14.4 m span."""
    k = Kit(name, coll)
    keys = [(-7.75, 0.08, 2.05, 2.18), (-7.4, 0.28, 1.88, 2.3), (-5.0, 0.68, 1.15, 2.42), (-2.5, 0.86, 0.78, 2.5),
            (4.0, 0.86, 0.76, 2.5), (5.3, 0.84, 0.78, 2.4), (6.5, 0.7, 0.86, 2.08), (7.35, 0.42, 1.05, 1.75),
            (7.8, 0.03, 1.3, 1.42)]
    _fuselage(k, keys, 40, 0.3, paint, glass=(5.0, 6.15, 0.58, 0.8),
              stripe=(-6.0, 6.8, 0.4, 0.46) if livery else None)
    lm = "accent" if livery else paint
    wins = []
    for i in range(5):
        for sy in (1, -1):
            wins.append((-1.6 + i * 0.85, sy * 0.85, 1.85, 0.3, 0.04, 0.32))
    boxes_mesh(k, wins, "dark", bev=0.06)
    tan = math.tan(math.radians(22))
    zr, dih = 0.95, math.tan(math.radians(3))
    _wing(k, [(1.6, 2.9, 0.4, zr), (1.6 - 6.9 * tan, 1.05, 7.0, zr + 7.0 * dih)], paint, t=(0.13, 0.1))
    tip_le = 1.6 - 6.9 * tan
    for sy in (1, -1):
        rings = []
        for (h, c, dx) in ((0.0, 0.9, 0.0), (1.0, 0.45, -0.7)):
            af = _airfoil(10, 0.09)
            rings.append([(tip_le + dx - u * c, sy * 7.0 + v * c * 0.5, zr + 7.0 * dih + h) for (u, v) in af])
        k.add(loft(f"{name}_winglet", rings, k.coll, smooth=True, mat=k.mat(lm)))
    for sy in (1, -1):
        _nacelle(k, -3.1, sy * 1.42, 2.15, 2.7, 0.48, paint)
        k.prof([(-3.9, 1.95), (-5.0, 1.95), (-5.0, 2.3), (-4.0, 2.3)], 0.9, "XZ", (0, sy * 0.85, 0), paint, 0.03)
    ft = math.tan(math.radians(40))
    _wing(k, [(-5.0, 2.9, 2.0, 0.0), (-5.0 - 2.35 * ft, 1.6, 4.4, 0.0)], lm, vertical=True, t=(0.12, 0.1))
    hx = -5.0 - 2.35 * ft
    st = math.tan(math.radians(30))
    _wing(k, [(hx + 0.1, 1.6, 0.05, 4.35), (hx - 2.6 * st, 0.75, 2.7, 4.45)], paint, t=(0.1, 0.08))
    _gear_leg(k, -0.6, 1.5, 0.9, 0.3, 0.17, 1)
    _gear_leg(k, -0.6, -1.5, 0.9, 0.3, 0.17, 1)
    _gear_leg(k, 5.4, 0.0, 0.85, 0.2, 0.12, 2)
    return k.finish()


def drone_cargo(coll=None, name="drone_cargo", paint="body", package=True, rotors=6):
    """Hexacopter delivery drone (~2.4 m across rotors) carrying an accent parcel."""
    k = Kit(name, coll)
    zc = 0.85
    body = k.lathe([(-0.45, 0.0), (-0.4, 0.14), (-0.2, 0.22), (0.25, 0.22), (0.45, 0.12), (0.5, 0.0)], "X",
                   (0, 0, zc), paint, 24)
    body.scale = (1, 1.15, 0.7)
    k.cyl(0.18, 0.06, (0, 0, zc + 0.16), mat="dark", verts=20)
    for i in range(rotors):
        a = 2 * math.pi * (i + 0.5) / rotors
        r = 0.95
        px, py = r * math.cos(a), r * math.sin(a)
        k.tube((0.15 * math.cos(a), 0.15 * math.sin(a), zc), (px, py, zc + 0.05), 0.03, "dark", 10)
        k.cyl(0.06, 0.12, (px, py, zc + 0.1), mat=paint, verts=16)
        k.cyl(0.015, 0.05, (px, py, zc + 0.18), mat="dark", verts=8)
        rot = a * 1.7
        for b in (0, math.pi):
            k.box((0.4, 0.05, 0.008), (px + 0.2 * math.cos(rot + b), py + 0.2 * math.sin(rot + b), zc + 0.19),
                  "dark", rot=(0.12 if b == 0 else -0.12, 0, rot + b), group=f"rotor_{i}")
    for sy in (1, -1):
        k.tube((0.15, sy * 0.12, zc - 0.1), (0.25, sy * 0.4, 0.03), 0.015, "dark", 8)
        k.tube((-0.15, sy * 0.12, zc - 0.1), (-0.25, sy * 0.4, 0.03), 0.015, "dark", 8)
        k.tube((0.4, sy * 0.4, 0.02), (-0.4, sy * 0.4, 0.02), 0.02, "dark", 8)
    k.box((0.12, 0.08, 0.06), (0.47, 0, zc - 0.03), "glass", 0.02)
    if package:
        k.box((0.4, 0.34, 0.3), (0, 0, zc - 0.36), "accent", 0.02)
        k.box((0.3, 0.3, 0.05), (0, 0, zc - 0.18), "dark")
    return k.finish(origins={f"rotor_{i}": (0.95 * math.cos(2 * math.pi * (i + 0.5) / rotors),
                                            0.95 * math.sin(2 * math.pi * (i + 0.5) / rotors), zc + 0.19)
                             for i in range(rotors)})


# =====================================================================  two-wheelers
def _thin_wheel(k, x, R, tr, z=None, spokes=16, hub_w=0.1, group=None, rim_mat="body", disc=False):
    z = R if z is None else z
    import itertools
    prof = []
    for i in range(13):
        a = math.pi * 2 * i / 12
        prof.append((tr * math.sin(a), R - tr + tr * math.cos(a)))
    k.lathe(prof, "Y", (x, 0, z), "dark", 40, group)
    rr = R - 2 * tr
    k.lathe([(-tr * 0.6, rr - 0.03), (-tr * 0.6, rr), (tr * 0.6, rr), (tr * 0.6, rr - 0.03)], "Y", (x, 0, z), rim_mat,
            40, group)
    k.cyly(0.03, hub_w, (x, 0, z), mat="dark", verts=12, group=group)
    if disc:
        k.cyly(rr - 0.02, 0.02, (x, 0, z), mat=rim_mat, verts=32, group=group)
        return
    for i in range(spokes):
        a = 2 * math.pi * i / spokes
        sy = hub_w / 2 * (1 if i % 2 else -1)
        k.tube((x, sy, z), (x + (rr - 0.02) * math.cos(a), 0, z + (rr - 0.02) * math.sin(a)), 0.0025, "dark", 4,
               group)


def bicycle(coll=None, name="bicycle", paint="body"):
    k = Kit(name, coll)
    R = 0.35
    ra, fa = Vector((-0.5, 0, R)), Vector((0.53, 0, R))
    bb = Vector((-0.07, 0, 0.29))
    st = Vector((-0.23, 0, 0.84))
    ht, hb = Vector((0.40, 0, 0.88)), Vector((0.44, 0, 0.73))
    r = 0.017
    k.tube(st, ht, r, paint)
    k.tube(bb, hb, r * 1.25, paint)
    k.tube(bb, st, r * 1.1, paint)
    k.tube(hb + Vector((0.0, 0, -0.02)), ht + Vector((-0.01, 0, 0.04)), r * 1.4, paint)
    for sy in (1, -1):
        k.tube(bb + Vector((0, sy * 0.02, 0)), ra + Vector((0, sy * 0.06, 0)), r * 0.65, paint)
        k.tube(st + Vector((0.01, sy * 0.015, -0.04)), ra + Vector((0, sy * 0.06, 0)), r * 0.6, paint)
        k.tube(hb + Vector((0, sy * 0.03, 0)), fa + Vector((0, sy * 0.05, 0)), r * 0.75, paint)
    # seat post + saddle
    sp = st + (st - bb).normalized() * 0.14
    k.tube(st, sp, 0.013, "dark")
    k.lathe([(-0.14, 0.0), (-0.13, 0.06), (-0.05, 0.075), (0.06, 0.04), (0.14, 0.02), (0.15, 0.0)], "X",
            (sp.x - 0.02, 0, sp.z + 0.025), "dark", 16).scale = (1, 1, 0.35)
    # stem, bars
    top = ht + Vector((-0.01, 0, 0.1))
    k.tube(ht, top, 0.014, "dark")
    k.tube(top, top + Vector((0.08, 0, 0.01)), 0.012, "dark")
    bar = top + Vector((0.08, 0, 0.01))
    pts = [Vector((bar.x - 0.08, 0.27, bar.z + 0.02)), Vector((bar.x, 0.2, bar.z)), Vector((bar.x, -0.2, bar.z)),
           Vector((bar.x - 0.08, -0.27, bar.z + 0.02))]
    for a, b in zip(pts, pts[1:]):
        k.tube(a, b, 0.011, "dark", 8)
    for sy in (1, -1):
        k.tube(Vector((bar.x - 0.08, sy * 0.27, bar.z + 0.02)), Vector((bar.x - 0.13, sy * 0.28, bar.z + 0.03)),
               0.017, "dark", 8)
    # drivetrain
    k.cyly(0.1, 0.006, (bb.x, -0.07, bb.z), mat="dark", verts=28)
    k.cyly(0.035, 0.006, (ra.x, -0.07, ra.z), mat="dark", verts=16)
    for zz, a, b in ((0.1, bb, ra), (-0.1, bb, ra)):
        k.tube((a.x, -0.07, a.z + zz), (b.x, -0.07, b.z + zz * 0.35), 0.004, "dark", 4)
    for sy, ang in ((-1, 0.6), (1, 0.6 + math.pi)):
        p = Vector((bb.x + 0.17 * math.cos(ang), sy * 0.09, bb.z - 0.17 * math.sin(ang)))
        k.tube((bb.x, sy * 0.08, bb.z), p, 0.01, "dark", 6)
        k.box((0.09, 0.08, 0.02), (p.x, sy * 0.14, p.z), "dark")
    _thin_wheel(k, ra.x, R, 0.016, group="wheel_R")
    _thin_wheel(k, fa.x, R, 0.016, group="wheel_F")
    # kickstand-free; fenders
    return k.finish()


def motorbike(coll=None, name="motorbike", paint="body"):
    k = Kit(name, coll)
    R = 0.31
    ra, fa = Vector((-0.71, 0, R)), Vector((0.72, 0, R))
    # tyres + wheels (chunky)
    for (a, tw, g) in ((ra, 0.18, "wheel_R"), (fa, 0.12, "wheel_F")):
        h = tw / 2
        k.lathe([(-h * 0.7, 0.21), (-h, 0.24), (-h, 0.28), (-h * 0.6, R), (h * 0.6, R), (h, 0.28), (h, 0.24),
                 (h * 0.7, 0.21)], "Y", tuple(a), "dark", 32, g)
        k.lathe([(-h * 0.7, 0.0), (-h * 0.7, 0.03), (-h * 0.75, 0.2), (-h * 0.72, 0.215), (h * 0.72, 0.215),
                 (h * 0.75, 0.2), (h * 0.7, 0.03), (h * 0.7, 0.0)], "Y", tuple(a), "dark", 32, g)
        for i in range(5):
            ang = 2 * math.pi * i / 5
            k.tube(a + Vector((0.04 * math.cos(ang), 0, 0.04 * math.sin(ang))),
                   a + Vector((0.2 * math.cos(ang + 0.3), 0, 0.2 * math.sin(ang + 0.3))), 0.012, "body", 6, g)
        k.cyly(0.15, 0.006, (a.x, 0.07 if g == "wheel_F" else -0.08, a.z), mat="body", verts=24, group=g)
    # fork + triple clamp + bars
    head = Vector((0.5, 0, 0.98))
    for sy in (1, -1):
        k.tube(head + Vector((0.02, sy * 0.09, 0.08)), fa + Vector((0, sy * 0.09, 0)), 0.024, "dark", 10)
        k.tube(head + Vector((-0.02, sy * 0.09, 0.0)), head + Vector((0.08, sy * 0.09, -0.32)), 0.035, "body", 10)
    k.box((0.08, 0.26, 0.04), (head.x + 0.02, 0, head.z + 0.06), "dark", 0.01)
    bar = head + Vector((-0.04, 0, 0.14))
    for sy in (1, -1):
        k.tube(bar, bar + Vector((-0.1, sy * 0.36, 0.03)), 0.012, "dark", 8)
        k.tube(bar + Vector((-0.1, sy * 0.36, 0.03)), bar + Vector((-0.12, sy * 0.44, 0.035)), 0.02, "dark", 8)
        k.tube(bar + Vector((-0.05, sy * 0.28, 0.02)), bar + Vector((-0.08, sy * 0.33, 0.2)), 0.006, "dark", 6)
        k.box((0.02, 0.09, 0.05), (bar.x - 0.08, sy * 0.34, bar.z + 0.22), "dark", 0.01)
    # headlight + instruments
    k.lathe([(-0.12, 0.0), (-0.1, 0.07), (-0.02, 0.1), (0.04, 0.1), (0.04, 0.0)], "X",
            (head.x + 0.12, 0, head.z - 0.05), "dark", 20)
    k.cylx(0.088, 0.01, (head.x + 0.165, 0, head.z - 0.05), mat="light", verts=20)
    k.cyl(0.05, 0.03, (bar.x + 0.02, 0, bar.z + 0.04), rot=(0, math.radians(-30), 0), mat="dark", verts=16)
    # front fender
    for i in range(6):
        a0, a1 = math.radians(40 + i * 18), math.radians(40 + (i + 1) * 18)
        k.beam(fa + Vector((0.36 * math.cos(a0), 0, 0.36 * math.sin(a0) - 0.0)),
               fa + Vector((0.36 * math.cos(a1), 0, 0.36 * math.sin(a1))), 0.14, 0.012, paint)
    # frame: trellis-like main beams
    piv = Vector((-0.17, 0, 0.5))
    for sy in (1, -1):
        k.tube(head + Vector((-0.04, sy * 0.05, -0.05)), Vector((-0.12, sy * 0.13, 0.72)), 0.024, "dark", 10)
        k.tube(Vector((-0.12, sy * 0.13, 0.72)), piv + Vector((0, sy * 0.12, 0)), 0.024, "dark", 10)
        k.tube(piv + Vector((0, sy * 0.12, 0)), ra + Vector((0, sy * 0.11, 0)), 0.026, "dark", 10)  # swingarm
        k.tube(Vector((-0.12, sy * 0.1, 0.78)), Vector((-0.75, sy * 0.06, 0.88)), 0.015, "dark", 8)  # subframe
    k.tube(Vector((-0.3, 0, 0.78)), Vector((-0.4, 0, 0.45)), 0.03, "body", 10)  # shock
    # engine
    k.box((0.42, 0.3, 0.32), (0.05, 0, 0.42), "dark", 0.04)
    k.box((0.25, 0.42, 0.14), (0.02, 0, 0.36), "dark", 0.04)
    cyl = k.box((0.2, 0.26, 0.28), (0.2, 0, 0.66), "body", 0.03, rot=(0, math.radians(-25), 0))
    for i in range(5):
        k.box((0.24, 0.3, 0.012), (0.2 + 0.02 * i * 0.42, 0, 0.58 + i * 0.045), "body", rot=(0, math.radians(-25), 0))
    k.box((0.1, 0.33, 0.14), (0.25, 0, 0.8), "dark", 0.02, rot=(0, math.radians(-25), 0))
    # exhaust
    k.tube(Vector((0.3, -0.06, 0.6)), Vector((0.35, -0.08, 0.28)), 0.024, "dark", 10)
    k.tube(Vector((0.35, -0.08, 0.28)), Vector((-0.2, -0.17, 0.3)), 0.024, "dark", 10)
    k.lathe([(0.0, 0.0), (0.0, 0.05), (0.03, 0.06), (0.4, 0.055), (0.42, 0.0)], "X", (0, 0, 0), "body", 16) \
        .matrix_basis = Matrix.Translation((-0.2, -0.18, 0.36)) @ Matrix.Rotation(math.radians(168), 4, "Z") @ \
        Matrix.Rotation(math.radians(-12), 4, "Y")
    # tank, seat, tail
    tank = k.lathe([(-0.32, 0.0), (-0.3, 0.1), (-0.15, 0.17), (0.12, 0.18), (0.26, 0.12), (0.3, 0.0)], "X",
                   (0.18, 0, 0.9), paint, 24)
    tank.scale = (1, 1.0, 0.72)
    tank.rotation_euler = (0, math.radians(8), 0)
    seat = k.lathe([(-0.32, 0.0), (-0.3, 0.1), (0.0, 0.13), (0.22, 0.12), (0.26, 0.0)], "X", (-0.4, 0, 0.88),
                   "dark", 20)
    seat.scale = (1, 1.0, 0.45)
    seat.rotation_euler = (0, math.radians(-5), 0)
    tail = k.prof([(-0.6, 0.86), (-0.58, 0.97), (-0.98, 1.0), (-0.98, 0.95)], 0.18, "XZ", (0, 0, 0), paint, 0.02)
    k.box((0.04, 0.12, 0.05), (-0.99, 0, 0.96), "dark", 0.01)
    k.tube(Vector((-0.85, 0, 0.92)), Vector((-0.95, 0, 0.7)), 0.01, "dark", 6)
    k.box((0.02, 0.16, 0.12), (-0.96, 0, 0.66), "body")
    # side panels/radiator
    for sy in (1, -1):
        k.box((0.18, 0.04, 0.22), (0.32, sy * 0.15, 0.6), paint, 0.02, rot=(0, math.radians(-20), 0))
        k.box((0.06, 0.12, 0.02), (-0.15, sy * 0.2, 0.38), "dark")  # foot pegs
    return k.finish()


# =====================================================================  registry
# (asset name, function, kwargs, tags, notes)
REGISTRY = [
    ("car_hatchback", car_hatchback, {}, ["car", "hatchback", "compact"], "Compact hatchback, ~4.05 m."),
    ("car_sedan", car_sedan, {}, ["car", "sedan"], "Mid-size sedan, ~4.8 m."),
    ("car_suv", car_suv, {}, ["car", "suv"], "SUV with dark lower cladding."),
    ("car_pickup", car_pickup, {}, ["car", "pickup", "truck"], "Crew-cab pickup with dark bed liner."),
    ("car_taxi", car_taxi, {}, ["car", "taxi", "accent"], "Sedan + accent roof sign and door band."),
    ("car_security", car_security, {}, ["car", "police", "security", "accent"],
     "Sedan + accent door band, light bar (accent/light), push bar."),
    ("van_delivery", van_delivery, {}, ["van", "delivery", "accent"], "High-roof delivery van with accent brand panel."),
    ("truck_box", truck_box, {}, ["truck", "box truck", "delivery", "accent"], "Box truck with accent brand panel, roll-up door."),
    ("truck_armored_cit", truck_armored, {}, ["truck", "armoured", "cash-in-transit", "bank", "accent"],
     "Cash-in-transit armoured truck: conventional cab, armoured box, gun ports, accent band."),
    ("bus_city", bus_city, {}, ["bus", "city bus", "public transport", "accent"], "12 m low-floor city bus, doors on right (-Y) side."),
    ("semi_tractor", semi_tractor, {}, ["truck", "semi", "tractor", "lorry"], "US-style conventional sleeper tractor 6x4; fifth wheel x in root['fifth_wheel_x']."),
    ("trailer_box_40ft", trailer_box, {}, ["trailer", "semi", "box", "dry van"], "40 ft dry-van trailer; kingpin x in root['kingpin_x']."),
    ("trailer_tanker", trailer_tanker, {}, ["trailer", "semi", "tanker", "fuel", "accent"], "Fuel tanker trailer, elliptical tank, accent band."),
    ("trailer_flatbed_lumber", trailer_flatbed, {"load": "lumber"}, ["trailer", "semi", "flatbed", "lumber"], "Flatbed trailer with strapped lumber bundles (load='lumber'|'crates'|'pipes')."),
    ("trailer_flatbed_crates", trailer_flatbed, {"load": "crates"}, ["trailer", "semi", "flatbed", "crates"], "Flatbed trailer with strapped crates."),
    ("semi_truck_box", semi_truck, {"trailer": "box", "livery": True}, ["truck", "semi", "lorry", "accent"], "Tractor + 40 ft box trailer with accent brand panel (separate tractor/trailer objects)."),
    ("semi_truck_tanker", semi_truck, {"trailer": "tanker"}, ["truck", "semi", "tanker", "fuel", "accent"], "Tractor + tanker trailer."),
    ("truck_dump", truck_dump, {}, ["truck", "dump", "construction"], "8x4-style 3-axle dump truck, cab-over."),
    ("truck_mixer", truck_mixer, {}, ["truck", "cement mixer", "construction", "accent"], "Cement mixer; drum is a separate object (origin at drum pivot) with accent helix stripe."),
    ("container_20ft", container, {}, ["container", "shipping", "iso", "20ft", "trade"], "ISO 20 ft container 6.06x2.44x2.59; doors at -X. paint='body'|'accent', frame=..."),
    ("container_40ft", container_40ft, {}, ["container", "shipping", "iso", "40ft", "trade"], "ISO 40 ft container 12.19x2.44x2.59; doors at -X."),
    ("container_20ft_accent", container, {"paint": "accent"}, ["container", "shipping", "iso", "20ft", "accent"], "20 ft container in accent colour (brand)."),
    ("container_40ft_accent", container_40ft, {"paint": "accent"}, ["container", "shipping", "iso", "40ft", "accent"], "40 ft container in accent colour (brand)."),
    ("forklift", forklift, {}, ["industrial", "forklift", "warehouse", "logistics"], "Counterbalance forklift; forks at +X. fork_height param."),
    ("wheel_loader", wheel_loader, {}, ["industrial", "construction", "loader"], "Articulated wheel loader, ~950 class."),
    ("crane_mobile", crane_mobile, {}, ["industrial", "crane", "construction"], "4-axle all-terrain crane, boom stowed (boom is a separate object, origin at its pivot)."),
    ("crane_mobile_raised", crane_mobile, {"boom_angle": 50, "extend": 0.35}, ["industrial", "crane", "construction"], "Mobile crane with boom raised 50 deg, partly extended, outriggers deployed."),
    ("crane_sts_gantry", crane_gantry, {}, ["industrial", "port", "crane", "gantry", "trade", "accent"], "Ship-to-shore container gantry crane; boom over +X; origin at leg-footprint centre; carries an accent 40ft box."),
    ("ship_container", ship_container, {}, ["ship", "sea", "container ship", "trade", "port", "accent"], "160 m container ship, bridge aft, ~450 stacked 40ft boxes (body/accent/dark), accent funnel band. z=0 = waterline (draft 8 m)."),
    ("ship_container_empty", ship_container, {"stacks": False}, ["ship", "sea", "container ship", "trade"], "Container ship without deck cargo. z=0 = waterline."),
    ("tugboat", tugboat, {}, ["ship", "sea", "tug", "port", "accent"], "28 m harbour tug, heavy fendering. z=0 = waterline."),
    ("boat_fishing", boat_fishing, {}, ["boat", "sea", "fishing", "trawler"], "12 m inshore fishing boat. z=0 = waterline."),
    ("plane_airliner", airliner, {}, ["aircraft", "airliner", "jet", "travel", "accent"], "Narrow-body twinjet (A320 class) 37.6 m, span 34 m, gear down, accent tail/sharklets/cheatline."),
    ("plane_bizjet", plane_bizjet, {}, ["aircraft", "business jet", "private jet", "wealth", "accent"], "Business jet, rear engines, T-tail, accent fin."),
    ("drone_cargo", drone_cargo, {}, ["aircraft", "drone", "delivery", "logistics", "accent"], "Hexacopter delivery drone with accent parcel; rotors are separate objects."),
    ("bicycle", bicycle, {}, ["two-wheeler", "bicycle", "bike", "commute"], "City/road bicycle, 700c wheels, spoked."),
    ("bicycle_accent", bicycle, {"paint": "accent"}, ["two-wheeler", "bicycle", "bike", "accent"], "Bicycle with accent frame."),
    ("motorbike", motorbike, {}, ["two-wheeler", "motorbike", "motorcycle"], "Naked standard motorbike ~2.1 m."),
    ("motorbike_accent", motorbike, {"paint": "accent"}, ["two-wheeler", "motorbike", "motorcycle", "accent"], "Motorbike with accent tank/tail."),
]
