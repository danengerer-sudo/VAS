"""genkit: shared procedural-modelling kit for the arch / commerce / fx generators.

* MB  - a mesh builder.  Generators append geometry (boxes, cylinders, lathes, sweeps,
        facades with real recessed windows ...) with a material name per part, under a
        transform stack (`with mb.at(loc, rz=...)`).  `mb.build(name)` makes ONE multi-material
        object (welded, smooth-by-angle, optional live Bevel modifier).  Because every generator
        draws into an MB, generators compose (a city block calls the building generators).
* mat() - LIB_* house materials (+ LIB_Fire, warm emissive for FX).
* Category - packaging per CONVENTIONS.md: collection `<cat>/<name>`, asset_mark + tags,
        thumbnail via thumb.py, catalog JSON, contact sheet, saves build/<cat>.blend.
"""
import json
import math
import os
import random
import sys
import traceback
from contextlib import contextmanager

import bmesh
import bpy
from mathutils import Euler, Matrix, Vector

HERE = os.path.dirname(os.path.abspath(__file__))
LIBROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.normpath(os.path.join(LIBROOT, "..", "scripts")))
import lib  # noqa: E402  (shared helpers: pbr, bevel ...)
import thumb  # noqa: E402

FONT_DIR = "/usr/share/fonts/opentype/inter/"
FONT_BOLD = FONT_DIR + "Inter-Bold.otf"
FONT_BLACK = FONT_DIR + "Inter-Black.otf"
FONT_SEMI = FONT_DIR + "Inter-SemiBold.otf"

TAU = math.pi * 2
FACE_PX = (math.pi / 2, 0, math.pi / 2)   # text/decal rotation: readable from +X
FACE_NY = (math.pi / 2, 0, 0)             # readable from -Y

# ------------------------------------------------------------------ materials
BODY, ACCENT, DARK, GLASS, LIGHT, METAL, FIRE = (
    "LIB_Body", "LIB_Accent", "LIB_Dark", "LIB_Glass", "LIB_Light", "LIB_Metal", "LIB_Fire")


def mat(name):
    m = bpy.data.materials.get(name)
    if m:
        return m
    if name == BODY:
        return lib.pbr(name, (0.82, 0.81, 0.79), rough=0.6, spec=0.35)
    if name == ACCENT:
        return lib.pbr(name, (0.95, 0.38, 0.06), rough=0.5, spec=0.4)
    if name == DARK:
        return lib.pbr(name, (0.035, 0.037, 0.04), rough=0.5, spec=0.4)
    if name == GLASS:
        return lib.pbr(name, (0.08, 0.09, 0.1), rough=0.08, spec=0.6)
    if name == LIGHT:
        return lib.pbr(name, (1.0, 1.0, 1.0), rough=0.4, emission=((1.0, 1.0, 1.0), 0.0))
    if name == METAL:
        return lib.pbr(name, (0.8, 0.6, 0.2), rough=0.28, metal=1.0)
    if name == FIRE:
        # warm emissive for FX cores; strength tuned to read under the bright white-style sun
        return lib.pbr(name, (1.0, 0.55, 0.18), rough=0.6, emission=((1.0, 0.42, 0.08), 6.0))
    raise ValueError("not a LIB material: " + name)


# ------------------------------------------------------------------ mesh builder
def _xf(loc=(0, 0, 0), rz=0.0, rot=None, scale=1.0):
    r = Euler(rot) if rot is not None else Euler((0, 0, rz))
    s = scale if isinstance(scale, (tuple, list, Vector)) else (scale, scale, scale)
    return Matrix.LocRotScale(Vector(loc), r, Vector(s))


class MB:
    def __init__(self):
        self.v = []
        self.f = []
        self.fm = []
        self.mats = []
        self.M = Matrix.Identity(4)

    # -- transform stack
    @contextmanager
    def at(self, loc=(0, 0, 0), rz=0.0, rot=None, scale=1.0, M=None):
        old = self.M
        self.M = old @ (M if M is not None else _xf(loc, rz, rot, scale))
        try:
            yield self
        finally:
            self.M = old

    def mi(self, m):
        if m not in self.mats:
            self.mats.append(m)
        return self.mats.index(m)

    def add(self, verts, faces, m):
        base = len(self.v)
        M = self.M
        self.v.extend(M @ Vector(p) for p in verts)
        flip = M.to_3x3().determinant() < 0
        idx = self.mi(m)
        for fc in faces:
            fc = tuple(base + i for i in fc)
            self.f.append(tuple(reversed(fc)) if flip else fc)
            self.fm.append(idx)
        return base

    def world(self, p):
        return self.M @ Vector(p)

    # -- primitives (all in local space)
    def bb(self, x0, y0, z0, x1, y1, z1, m=BODY):
        """Axis-aligned box from min/max corners."""
        x0, x1 = min(x0, x1), max(x0, x1)
        y0, y1 = min(y0, y1), max(y0, y1)
        z0, z1 = min(z0, z1), max(z0, z1)
        v = [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0),
             (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)]
        f = [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]
        return self.add(v, f, m)

    def box(self, size, loc=(0, 0, 0), m=BODY, rz=0.0, rot=None):
        """Box of size centred at loc."""
        sx, sy, sz = [s / 2 for s in size]
        with self.at(loc, rz, rot):
            self.bb(-sx, -sy, -sz, sx, sy, sz, m)

    def cbox(self, size, loc=(0, 0, 0), m=BODY, rz=0.0):
        """Box of size standing on loc (loc = centre of bottom face)."""
        self.box(size, (loc[0], loc[1], loc[2] + size[2] / 2), m, rz)

    def cyl(self, r, h, loc=(0, 0, 0), m=BODY, n=16, r2=None, cap=True, cap_top=None, rot=None):
        """Cylinder/cone along local +Z from loc (base centre) up h."""
        r2 = r if r2 is None else r2
        cap_top = cap if cap_top is None else cap_top
        v, f = [], []
        for z, rr in ((0, r), (h, r2)):
            for i in range(n):
                a = TAU * i / n
                v.append((rr * math.cos(a), rr * math.sin(a), z))
        for i in range(n):
            j = (i + 1) % n
            f.append((i, j, n + j, n + i))
        if cap:
            f.append(tuple(reversed(range(n))))
        if cap_top:
            if r2 > 1e-6:
                f.append(tuple(range(n, 2 * n)))
        with self.at(loc, rot=rot):
            self.add(v, f, m)

    def rod(self, p0, p1, r, m=BODY, n=8, r2=None, cap=True):
        """Cylinder between two points."""
        p0, p1 = Vector(p0), Vector(p1)
        d = p1 - p0
        L = d.length
        if L < 1e-6:
            return
        q = d.normalized().to_track_quat("Z", "Y" if abs(d.normalized().y) < 0.99 else "X")
        M = Matrix.Translation(p0) @ q.to_matrix().to_4x4()
        with self.at(M=M):
            self.cyl(r, L, (0, 0, 0), m, n, r2, cap)

    def sphere(self, r, loc=(0, 0, 0), m=BODY, seg=16, rings=8, scale=(1, 1, 1), zmin=-1.0):
        """UV sphere; zmin in [-1,1] cuts the bottom (dome when zmin=0)."""
        v, f = [], []
        a0 = math.asin(max(-1, min(1, zmin)))
        ring_angles = [a0 + (math.pi / 2 - a0) * k / rings for k in range(rings + 1)]
        for a in ring_angles[:-1]:
            for i in range(seg):
                t = TAU * i / seg
                v.append((r * math.cos(a) * math.cos(t) * scale[0], r * math.cos(a) * math.sin(t) * scale[1],
                          r * math.sin(a) * scale[2]))
        top = len(v)
        v.append((0, 0, r * scale[2]))
        nr = rings
        for k in range(nr - 1):
            for i in range(seg):
                j = (i + 1) % seg
                f.append((k * seg + i, k * seg + j, (k + 1) * seg + j, (k + 1) * seg + i))
        k = nr - 1
        for i in range(seg):
            j = (i + 1) % seg
            f.append((k * seg + i, k * seg + j, top))
        if zmin <= -0.999:
            bot = len(v)
            v.append((0, 0, -r * scale[2]))
            # ring 0 is at -90deg only if a0=-pi/2 -> degenerate ring; acceptable (merged later)
        else:
            f.append(tuple(reversed(range(seg))))
        with self.at(loc):
            self.add(v, f, m)

    def lathe(self, prof, m=BODY, n=24, loc=(0, 0, 0), rot=None, arc=TAU):
        """Revolve [(r, z), ...] around local Z. r==0 points collapse to the axis."""
        v, f = [], []
        full = abs(arc - TAU) < 1e-6
        ns = n if full else n + 1
        ids = []
        for k, (r, z) in enumerate(prof):
            if r < 1e-6:
                ids.append([len(v)] * ns)
                v.append((0, 0, z))
            else:
                row = []
                for i in range(ns):
                    a = arc * i / n
                    row.append(len(v))
                    v.append((r * math.cos(a), r * math.sin(a), z))
                ids.append(row)
        for k in range(len(prof) - 1):
            for i in range(n):
                j = (i + 1) % ns if full else i + 1
                q = [ids[k][i], ids[k][j], ids[k + 1][j], ids[k + 1][i]]
                q2 = []
                for x in q:
                    if x not in q2:
                        q2.append(x)
                if len(q2) >= 3:
                    f.append(tuple(q2))
        with self.at(loc, rot=rot):
            self.add(v, f, m)

    def prism(self, pts, z0, z1, m=BODY, cap=True):
        """Extrude closed XY polygon from z0 to z1."""
        area = sum(pts[i][0] * pts[(i + 1) % len(pts)][1] - pts[(i + 1) % len(pts)][0] * pts[i][1]
                   for i in range(len(pts)))
        if area < 0:
            pts = list(reversed(pts))
        n = len(pts)
        v = [(x, y, z0) for x, y in pts] + [(x, y, z1) for x, y in pts]
        f = [(i, (i + 1) % n, n + (i + 1) % n, n + i) for i in range(n)]
        if cap:
            f.append(tuple(reversed(range(n))))
            f.append(tuple(range(n, 2 * n)))
        self.add(v, f, m)

    def prism_xz(self, pts, y0, y1, m=BODY):
        """Profile in XZ plane, extruded along Y from y0 to y1."""
        with self.at(M=Matrix(((1, 0, 0, 0), (0, 0, 1, 0), (0, 1, 0, 0), (0, 0, 0, 1)))):
            self.prism(pts, y0, y1, m)

    def prism_yz(self, pts, x0, x1, m=BODY):
        """Profile in YZ plane (a=y, b=z), extruded along X from x0 to x1."""
        with self.at(M=Matrix(((0, 0, 1, 0), (1, 0, 0, 0), (0, 1, 0, 0), (0, 0, 0, 1)))):
            self.prism(pts, x0, x1, m)

    def quad(self, pts, m=BODY):
        self.add(pts, [tuple(range(len(pts)))], m)

    def ring(self, r0, r1, z0, z1, m=BODY, n=32, arc=TAU, a0=0.0):
        """Annulus / arc segment prism (thick ring)."""
        full = abs(arc - TAU) < 1e-6
        ns = n if full else n + 1
        v = []
        for z in (z0, z1):
            for r in (r0, r1):
                for i in range(ns):
                    a = a0 + arc * i / n
                    v.append((r * math.cos(a), r * math.sin(a), z))
        B0, B1, T0, T1 = 0, ns, 2 * ns, 3 * ns
        f = []
        for i in range(n):
            j = (i + 1) % ns if full else i + 1
            f.append((T0 + i, T1 + i, T1 + j, T0 + j))       # top
            f.append((B0 + i, B0 + j, B1 + j, B1 + i))       # bottom
            f.append((B1 + i, B1 + j, T1 + j, T1 + i))       # outer
            f.append((B0 + j, B0 + i, T0 + i, T0 + j))       # inner
        if not full:
            f.append((B0, B1, T1, T0))
            f.append((B0 + n, T0 + n, T1 + n, B1 + n))
        self.add(v, f, m)

    def torus(self, R, r, loc=(0, 0, 0), m=BODY, n=32, nr=8, arc=TAU, rot=None):
        v, f = [], []
        full = abs(arc - TAU) < 1e-6
        ns = n if full else n + 1
        for i in range(ns):
            a = arc * i / n
            for k in range(nr):
                b = TAU * k / nr
                rr = R + r * math.cos(b)
                v.append((rr * math.cos(a), rr * math.sin(a), r * math.sin(b)))
        for i in range(n):
            j = (i + 1) % ns if full else i + 1
            for k in range(nr):
                l2 = (k + 1) % nr
                f.append((i * nr + k, j * nr + k, j * nr + l2, i * nr + l2))
        with self.at(loc, rot=rot):
            self.add(v, f, m)

    def sweep(self, path, prof, m=BODY, closed=False, cap=True, up=(0, 0, 1), scales=None):
        """Sweep 2D profile [(side, up), ...] (closed polygon) along 3D path."""
        path = [Vector(p) for p in path]
        n = len(path)
        upv = Vector(up)
        v = []
        for i, p in enumerate(path):
            if closed:
                t = (path[(i + 1) % n] - path[i - 1])
            else:
                t = path[min(i + 1, n - 1)] - path[max(i - 1, 0)]
            t.normalize()
            s = t.cross(upv)
            if s.length < 1e-6:
                s = t.cross(Vector((1, 0, 0)))
            s.normalize()
            u = s.cross(t).normalized()
            k = scales[i] if scales else 1.0
            for a, b in prof:
                v.append(p + s * a * k + u * b * k)
        np_ = len(prof)
        f = []
        segs = n if closed else n - 1
        for i in range(segs):
            i2 = (i + 1) % n
            for j in range(np_):
                j2 = (j + 1) % np_
                f.append((i * np_ + j, i * np_ + j2, i2 * np_ + j2, i2 * np_ + j))
        if cap and not closed:
            f.append(tuple(range(np_)))
            f.append(tuple(reversed(range((n - 1) * np_, n * np_))))
        # orientation: make sure the first side face points away from the path
        if f:
            fc = f[0]
            pa, pb, pc = Vector(v[fc[0]]), Vector(v[fc[1]]), Vector(v[fc[2]])
            nrm = (pb - pa).cross(pc - pa)
            cen = (pa + pb + pc) / 3
            if nrm.dot(cen - path[0]) < 0:
                f = [tuple(reversed(x)) for x in f]
        self.add(v, f, m)

    def loft(self, rings, m=BODY, cap0=True, cap1=True):
        n = len(rings[0])
        v = [p for r in rings for p in r]
        f = []
        for k in range(len(rings) - 1):
            for i in range(n):
                j = (i + 1) % n
                f.append((k * n + i, k * n + j, (k + 1) * n + j, (k + 1) * n + i))
        if cap0:
            f.append(tuple(reversed(range(n))))
        if cap1:
            b = (len(rings) - 1) * n
            f.append(tuple(range(b, b + n)))
        self.add(v, f, m)

    def text(self, s, size, loc=(0, 0, 0), m=DARK, rot=(0, 0, 0), depth=0.02, font=FONT_BOLD,
             align="CENTER", valign="CENTER", spacing=1.0):
        """Text as mesh, lying in local XY (facing +Z) before `rot`. depth = total thickness, back at 0."""
        cu = bpy.data.curves.new("_txt", "FONT")
        cu.body = s
        cu.size = size
        cu.extrude = depth / 2
        cu.align_x = align
        cu.align_y = valign
        cu.space_character = spacing
        cu.font = bpy.data.fonts.load(font, check_existing=True)
        cu.resolution_u = 4
        ob = bpy.data.objects.new("_txt", cu)
        bpy.context.scene.collection.objects.link(ob)
        dg = bpy.context.evaluated_depsgraph_get()
        me = bpy.data.meshes.new_from_object(ob.evaluated_get(dg))
        verts = [(p.co.x, p.co.y, p.co.z + depth / 2) for p in me.vertices]
        faces = [tuple(p.vertices) for p in me.polygons]
        bpy.data.objects.remove(ob)
        bpy.data.curves.remove(cu)
        bpy.data.meshes.remove(me)
        with self.at(loc, rot=rot):
            self.add(verts, faces, m)

    def mesh_data(self, me, m=None, M=None):
        """Append an existing bpy mesh (materials by slot names or forced m)."""
        verts = [p.co.copy() for p in me.vertices]
        names = [s.name if s else BODY for s in me.materials] or [m or BODY]
        with self.at(M=M if M is not None else Matrix.Identity(4)):
            base = len(self.v)
            Mx = self.M
            self.v.extend(Mx @ p for p in verts)
            flip = Mx.to_3x3().determinant() < 0
            for p in me.polygons:
                fc = tuple(base + i for i in p.vertices)
                self.f.append(tuple(reversed(fc)) if flip else fc)
                nm = m or names[min(p.material_index, len(names) - 1)]
                self.fm.append(self.mi(nm))

    def blob(self, spheres, m=BODY, voxel=None, noise=0.0, noise_scale=1.0, smooth=4, seed=0,
             squash_bottom=None):
        """Union of spheres -> voxel remesh -> noise displace -> smooth.  spheres: [(center, r)]."""
        tmp = MB()
        for c, r in spheres:
            tmp.sphere(r, c, m, seg=20, rings=10)
            # close the bottom pole hole
        ob = tmp.build("_blob", merge=1e-4, smooth_angle=None)
        size = max(ob.dimensions)
        rm = ob.modifiers.new("R", "REMESH")
        rm.mode = "VOXEL"
        rm.voxel_size = voxel or size / 45
        if noise > 0:
            tex = bpy.data.textures.new("_blobtex", "CLOUDS")
            tex.noise_scale = noise_scale
            tex.noise_depth = 1
            dm = ob.modifiers.new("D", "DISPLACE")
            dm.texture = tex
            dm.strength = noise
            dm.mid_level = 0.5
            dm.texture_coords = "OBJECT"
            em = bpy.data.objects.new("_blobtexco", None)
            bpy.context.scene.collection.objects.link(em)
            em.location = (seed * 13.37, seed * 7.1, seed * 3.3)
            dm.texture_coords_object = em
        if smooth:
            sm = ob.modifiers.new("S", "SMOOTH")
            sm.factor = 0.6
            sm.iterations = smooth
        dg = bpy.context.evaluated_depsgraph_get()
        me = bpy.data.meshes.new_from_object(ob.evaluated_get(dg))
        if squash_bottom is not None:
            for p in me.vertices:
                if p.co.z < squash_bottom:
                    p.co.z = squash_bottom
        self.mesh_data(me, m)
        bpy.data.meshes.remove(me)
        bpy.data.objects.remove(ob)
        if noise > 0:
            bpy.data.objects.remove(em)
            bpy.data.textures.remove(tex)

    # -- output
    def build(self, name, bevel=0.0, seg=1, angle=35, merge=1e-4, smooth_angle=35, coll=None):
        me = bpy.data.meshes.new(name)
        me.from_pydata([tuple(p) for p in self.v], [], self.f)
        me.polygons.foreach_set("material_index", self.fm)
        me.validate(clean_customdata=False)
        if merge:
            bm = bmesh.new()
            bm.from_mesh(me)
            bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=merge)
            bmesh.ops.dissolve_degenerate(bm, edges=bm.edges, dist=merge * 0.5)
            bm.to_mesh(me)
            bm.free()
        for mn in self.mats:
            me.materials.append(mat(mn))
        if smooth_angle:
            me.set_sharp_from_angle(angle=math.radians(smooth_angle))
        ob = bpy.data.objects.new(name, me)
        (coll or bpy.context.scene.collection).objects.link(ob)
        if bevel > 0:
            b = ob.modifiers.new("Bevel", "BEVEL")
            b.width = bevel
            b.segments = seg
            b.limit_method = "ANGLE"
            b.angle_limit = math.radians(angle)
            b.harden_normals = True
            b.use_clamp_overlap = True
        return ob


# ------------------------------------------------------------------ helpers
def tri_count(objs):
    dg = bpy.context.evaluated_depsgraph_get()
    n = 0
    for o in objs:
        if o.type == "MESH":
            ev = o.evaluated_get(dg)
            me = ev.to_mesh()
            me.calc_loop_triangles()
            n += len(me.loop_triangles)
            ev.to_mesh_clear()
    return n


def bounds(objs):
    dg = bpy.context.evaluated_depsgraph_get()
    pts = []
    for o in objs:
        if o.type != "MESH":
            continue
        for c in o.evaluated_get(dg).bound_box:
            pts.append(o.matrix_world @ Vector(c))
    mn = Vector([min(p[i] for p in pts) for i in range(3)])
    mx = Vector([max(p[i] for p in pts) for i in range(3)])
    return mn, mx


def argv_opts():
    a = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    o = {"only": None, "nothumb": False}
    for x in a:
        if x.startswith("--only="):
            o["only"] = set(x[7:].split(","))
        if x == "--nothumb":
            o["nothumb"] = True
    return o


class Category:
    def __init__(self, name, source="procedural", license="original"):
        self.name = name
        self.source, self.license = source, license
        self.opts = argv_opts()
        for o in list(bpy.data.objects):
            bpy.data.objects.remove(o)
        for c in list(bpy.data.collections):
            bpy.data.collections.remove(c)
        self.root = bpy.data.collections.new(name)
        bpy.context.scene.collection.children.link(self.root)
        self.entries = []
        self.failed = []
        self.cursor = [0.0, 0.0, 0.0]  # x, y, row depth
        self.row_w = 0.0
        self.thumb_dir = os.path.join(LIBROOT, "thumbs", name)
        self.blend = os.path.join(LIBROOT, "build", name + ".blend")
        self.catalog = os.path.join(LIBROOT, "catalog", name + ".json")
        os.makedirs(os.path.join(LIBROOT, "catalog"), exist_ok=True)
        os.makedirs(os.path.join(LIBROOT, "build"), exist_ok=True)

    def add(self, name, fn, tags=(), notes="", az=-35, el=22, fill=1.0, lens=50):
        if self.opts["only"] and name not in self.opts["only"]:
            return
        print(f"[{self.name}] building {name}", flush=True)
        try:
            objs = fn()
            if not isinstance(objs, (list, tuple)):
                objs = [objs]
        except Exception:
            traceback.print_exc()
            self.failed.append(name)
            return
        coll = bpy.data.collections.new(f"{self.name}/{name}")
        self.root.children.link(coll)
        rootob = objs[0]
        for o in objs:
            for c in list(o.users_collection):
                c.objects.unlink(o)
            coll.objects.link(o)
            if o is not rootob and o.parent is None:
                o.parent = rootob
            if o.type == "MESH":
                o.data.name = f"{name}_{o.name}"
        rootob.name = name
        bpy.context.view_layer.update()
        mn, mx = bounds(objs)
        dims = [round(mx[i] - mn[i], 3) for i in range(3)]
        tris = tri_count(objs)
        coll.asset_mark()
        for t in [self.name] + list(tags):
            coll.asset_data.tags.new(t, skip_if_exists=True)
        coll.asset_data.description = notes
        tpath = os.path.join(self.thumb_dir, name + ".jpg")
        if not self.opts["nothumb"]:
            thumb.thumbnail(objs, tpath, azimuth=az, elevation=el, lens=lens, fill=fill)
            self._preview(coll, tpath)
        # lay the asset out on a grid in the .blend; instance_offset keeps the asset origin
        w, d = dims[0] + 6, dims[1] + 6
        if self.cursor[0] > 400:
            self.cursor = [0.0, self.cursor[1] + self.cursor[2], 0.0]
        pos = Vector((self.cursor[0] + w / 2, self.cursor[1] + d / 2, 0))
        rootob.location = pos
        coll.instance_offset = pos
        self.cursor[0] += w
        self.cursor[2] = max(self.cursor[2], d)
        self.entries.append({
            "name": name, "category": self.name, "collection": coll.name,
            "file": f"build/{self.name}.blend", "source": self.source, "license": self.license,
            "dims_m": dims, "tags": [self.name] + list(tags),
            "notes": (notes + f" | ~{tris} tris").strip(" |"),
            "thumb": f"thumbs/{self.name}/{name}.jpg",
        })
        print(f"   dims {dims} tris {tris}", flush=True)

    def _preview(self, coll, path):
        try:
            img = bpy.data.images.load(path)
            img.scale(128, 128)
            prev = coll.preview_ensure()
            prev.image_size = (128, 128)
            prev.image_pixels_float = list(img.pixels)
            bpy.data.images.remove(img)
        except Exception as e:  # preview is a nicety
            print("preview failed", e)

    def finish(self, cols=6):
        # merge into an existing catalog when building a subset
        entries = self.entries
        if self.opts["only"] and os.path.exists(self.catalog):
            old = json.load(open(self.catalog))
            names = {e["name"] for e in entries}
            order = [e["name"] for e in old]
            merged = {e["name"]: e for e in old}
            merged.update({e["name"]: e for e in entries})
            entries = [merged[n] for n in order if n in merged] + [e for e in entries if e["name"] not in order]
        else:
            json.dump(entries, open(self.catalog, "w"), indent=1)
        if self.opts["only"]:
            json.dump(entries, open(self.catalog, "w"), indent=1)
        items = [(os.path.join(LIBROOT, e["thumb"]), e["name"]) for e in entries]
        thumb.contact_sheet(items, os.path.join(LIBROOT, "thumbs", f"{self.name}_sheet.jpg"), cols=cols,
                            title=f"{self.name}  ({len(entries)} assets)")
        # strip the thumbnail studio before saving
        for o in list(bpy.data.objects):
            if o.name.startswith("Thumb"):
                bpy.data.objects.remove(o)
        sc = bpy.context.scene
        if "_thumb_studio" in sc:
            del sc["_thumb_studio"]
        if not self.opts["only"]:
            bpy.ops.wm.save_as_mainfile(filepath=self.blend, compress=True)
        else:
            # subset build: write a scratch file so the full build stays authoritative
            bpy.ops.wm.save_as_mainfile(filepath=self.blend.replace(".blend", "_partial.blend"), compress=True)
        print(f"[{self.name}] done: {len(self.entries)} built, failed: {self.failed}", flush=True)
