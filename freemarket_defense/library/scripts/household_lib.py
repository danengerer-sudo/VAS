"""household_lib: procedural HOUSEHOLD props for the white-model style (donkey, TV, hall pass, tools...).

Generators draw into a genkit.MB in local space: metres, Z up, origin at ground centre, front faces +X.
The donkey is a capsule/ellipsoid assembly voxel-remeshed into one smooth sculpt (same technique as
scripts/mfigure.py); everything else is hard-surface with live bevels.
"""
import math
import os
import sys

import bpy
from mathutils import Euler, Matrix, Vector

from genkit import ACCENT, BODY, DARK, FACE_PX, FACE_NY, FONT_BLACK, FONT_BOLD, FONT_SEMI, GLASS, LIGHT, METAL, MB, TAU, mat

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.normpath(os.path.join(HERE, "..", "..", "scripts")))
from lib import apply_mods, join  # noqa: E402
from figure import _capsule, _ellipsoid, carbine  # noqa: E402

R = math.radians
SC = lambda: bpy.context.scene.collection  # noqa: E731


# ------------------------------------------------------------------ small helpers
def rrect(w, h, r, n=4, cx=0.0, cy=0.0):
    """Rounded rectangle (XY) points, CCW."""
    r = min(r, w / 2 - 1e-4, h / 2 - 1e-4)
    pts = []
    for (sx, sy, a0) in ((1, 1, 0), (-1, 1, 90), (-1, -1, 180), (1, -1, 270)):
        c = (cx + sx * (w / 2 - r), cy + sy * (h / 2 - r))
        for k in range(n + 1):
            a = R(a0 + 90 * k / n)
            pts.append((c[0] + r * math.cos(a), c[1] + r * math.sin(a)))
    return pts


def rbox(mb, w, d, h, r, z0=0.0, m=BODY, n=4, cx=0.0, cy=0.0):
    """Box with rounded vertical edges (w along X, d along Y), standing on z0."""
    mb.prism(rrect(w, d, r, n, cx, cy), z0, z0 + h, m)


def rplate_yz(mb, w, h, t, r, x0=0.0, cz=0.0, m=BODY, n=5):
    """Rounded plate in the YZ plane (w along Y, h along Z, thickness t along +X from x0), centred at (y=0, z=cz)."""
    mb.prism_yz(rrect(w, h, r, n, 0.0, cz), x0, x0 + t, m)


def text_width(s, size, font=FONT_BOLD):
    cu = bpy.data.curves.new("_tw", "FONT")
    cu.body = s
    cu.size = size
    cu.font = bpy.data.fonts.load(font, check_existing=True)
    ob = bpy.data.objects.new("_tw", cu)
    bpy.context.scene.collection.objects.link(ob)
    bpy.context.view_layer.update()
    w = ob.dimensions.x
    bpy.data.objects.remove(ob)
    bpy.data.curves.remove(cu)
    return w


def fit_size(s, max_w, max_size, font=FONT_BOLD):
    w = text_width(s, 1.0, font)
    return min(max_size, max_w / max(w, 1e-6))


def text_px(mb, s, size, x, z, m=DARK, depth=0.006, font=FONT_BOLD, y=0.0, spacing=1.0):
    """Extruded text readable from +X, lying on the plane x (grows toward +X by depth)."""
    mb.text(s, size, (x, y, z), m, rot=FACE_PX, depth=depth, font=font, spacing=spacing)


def _frame(y, z):
    """Rotation matrix with given (unnormalised) up z and side y axes."""
    z = z.normalized()
    y = (y - z * y.dot(z)).normalized()
    x = y.cross(z)
    return Matrix((x, y, z)).transposed()


def _dir(yaw, pitch):
    """Unit vector from yaw (about Z, + toward +Y) and pitch (+ up), from +X."""
    return Vector((math.cos(pitch) * math.cos(yaw), math.cos(pitch) * math.sin(yaw), math.sin(pitch)))


# ================================================================== donkey
def donkey(mb, pose="standing", voxel=0.012):
    """Stylised donkey, side-on facing +X, 1.1 m at the withers.

    pose: "standing" (head turned ~60 deg toward -Y, looking over its shoulder) or "grazing" (head down).
    Body parts are capsules / ellipsoids -> voxel remesh -> corrective smooth, then hooves + eyes added.
    """
    coll = SC()
    body = mat(BODY)
    soft = []

    def cap(p0, p1, r0, r1, seg=20):
        soft.append(_capsule("_dk", Vector(p0), Vector(p1), r0, r1, coll, body, seg))

    def ell(c, r, Rm=None):
        o = _ellipsoid("_dk", Vector(), (1, 1, 1), coll, body)
        Rm = Rm or Matrix.Identity(3)
        o.data.transform(Matrix.Translation(Vector(c)) @ Rm.to_4x4() @ Matrix.Diagonal((*r, 1)))
        soft.append(o)

    UP = Vector((0, 0, 1))
    # ---- torso: barrel + chest + rump + withers
    ell((-0.08, 0, 0.80), (0.50, 0.235, 0.245))
    ell((0.36, 0, 0.80), (0.21, 0.19, 0.24))              # chest
    ell((-0.46, 0, 0.84), (0.20, 0.215, 0.235))           # rump
    ell((0.30, 0, 0.95), (0.19, 0.13, 0.15))              # withers / shoulder mass
    ell((-0.42, 0, 0.93), (0.17, 0.15, 0.12))             # croup
    # ---- legs (long for a donkey: ~half the height), slight knee / hock angles
    for sy in (1, -1):
        y = 0.135 * sy
        # front
        cap((0.34, y, 0.74), (0.37, y * 0.95, 0.46), 0.082, 0.052)     # forearm
        cap((0.37, y * 0.95, 0.46), (0.37, y * 0.9, 0.10), 0.05, 0.040)  # cannon
        ell((0.37, y * 0.95, 0.46), (0.06, 0.055, 0.065))                # knee
        # rear
        cap((-0.40, y * 1.05, 0.80), (-0.35, y, 0.50), 0.10, 0.06)       # thigh
        cap((-0.35, y, 0.50), (-0.47, y * 0.93, 0.32), 0.06, 0.046)      # gaskin -> hock
        ell((-0.47, y * 0.93, 0.32), (0.06, 0.05, 0.06))                 # hock
        cap((-0.47, y * 0.93, 0.32), (-0.43, y * 0.9, 0.10), 0.046, 0.040)  # rear cannon
        # fetlock stub down into the hoof
        cap((0.37, y * 0.9, 0.10), (0.37, y * 0.9, 0.05), 0.045, 0.045)
        cap((-0.43, y * 0.9, 0.10), (-0.43, y * 0.9, 0.05), 0.045, 0.045)

    # ---- neck + head
    neck0 = Vector((0.44, 0, 0.93))
    if pose == "grazing":
        nyaw, npitch, nlen = R(0), R(-40), 0.52
        hyaw, hpitch = R(0), R(-78)
    else:
        nyaw, npitch, nlen = R(-22), R(48), 0.50
        hyaw, hpitch = R(-60), R(-22)
    nd = _dir(nyaw, npitch)
    neck1 = neck0 + nd * nlen
    cap(neck0 - nd * 0.08, neck1, 0.155, 0.105)
    # mane ridge: short upright crest along the neck top
    side_n = nd.cross(UP).normalized()
    up_n = side_n.cross(nd).normalized()
    for t in (0.15, 0.4, 0.65, 0.88):
        c = neck0.lerp(neck1, t) + up_n * (0.155 - 0.05 * t + 0.03)
        ell(c, (0.075, 0.025, 0.06), _frame(side_n, up_n))
    hd = _dir(hyaw, hpitch)
    side_h = hd.cross(UP).normalized()
    up_h = side_h.cross(hd).normalized()
    Rh = _frame(side_h, up_h)
    Rh = Matrix((hd, side_h, up_h)).transposed()  # columns: x=along head, y=side, z=up
    skull = neck1 + hd * 0.10
    ell(skull, (0.17, 0.12, 0.14), Rh)                         # skull / cheeks
    cap(skull + hd * 0.05 - up_h * 0.01, neck1 + hd * 0.50 - up_h * 0.03, 0.105, 0.078)  # muzzle (slightly down)
    ell(neck1 + hd * 0.50 - up_h * 0.03, (0.085, 0.085, 0.075), Rh)   # nose end
    ell(neck1 + hd * 0.26 - up_h * 0.07, (0.14, 0.085, 0.07), Rh)     # jaw
    # ---- ears: long, upright, splayed
    ear_base = skull + hd * 0.0 + up_h * 0.11
    for sy in (1, -1):
        ed = (up_h * 1.0 + side_h * 0.42 * sy - hd * 0.18).normalized()
        c = ear_base + side_h * 0.045 * sy + ed * 0.14
        ell(c, (0.055, 0.03, 0.15), Matrix((ed.cross(side_h).normalized(), side_h, ed)).transposed() if False else
            _frame(side_h * sy, ed) @ Matrix.Rotation(0, 3, 'Z'))
    # ---- tail: thin with a tuft
    cap((-0.63, 0, 0.92), (-0.68, 0.02, 0.48), 0.035, 0.026)
    ell((-0.69, 0.025, 0.40), (0.05, 0.05, 0.11))

    # ---- remesh into one sculpt
    sculpt = join(soft, "_donkey_sculpt")
    rm = sculpt.modifiers.new("Remesh", "REMESH")
    rm.mode = "VOXEL"
    rm.voxel_size = voxel
    sm = sculpt.modifiers.new("Smooth", "CORRECTIVE_SMOOTH")
    sm.iterations = 6
    sm.use_only_smooth = True
    apply_mods(sculpt)
    mb.mesh_data(sculpt.data, BODY)
    bpy.data.objects.remove(sculpt)

    # ---- hard details: hooves (dark) and eyes (dark)
    for sy in (1, -1):
        y = 0.135 * sy * 0.9
        for x in (0.37, -0.43):
            mb.cyl(0.058, 0.07, (x + 0.01, y, 0.0), DARK, n=20, r2=0.05)
    eye_c = skull + hd * 0.08 + up_h * 0.035
    for sy in (1, -1):
        mb.sphere(0.024, eye_c + side_h * 0.105 * sy, DARK, seg=14, rings=7)


def donkey_build(name, pose="standing"):
    mb = MB()
    donkey(mb, pose)
    ob = mb.build(name, merge=1e-5, smooth_angle=None)
    for p in ob.data.polygons:
        p.use_smooth = True
    return ob
