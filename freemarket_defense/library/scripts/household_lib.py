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
    ell((-0.08, 0, 0.78), (0.52, 0.25, 0.27))
    ell((0.38, 0, 0.78), (0.22, 0.20, 0.26))              # chest
    ell((-0.48, 0, 0.82), (0.21, 0.225, 0.25))            # rump
    ell((0.30, 0, 0.93), (0.19, 0.13, 0.13))              # withers / shoulder mass (flat, not horse-like)
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
        nyaw, npitch, nlen = R(0), R(-38), 0.46
        hyaw, hpitch = R(0), R(-76)
    else:
        nyaw, npitch, nlen = R(-22), R(50), 0.44
        hyaw, hpitch = R(-60), R(-20)
    nd = _dir(nyaw, npitch)
    neck1 = neck0 + nd * nlen
    cap(neck0 - nd * 0.08, neck1, 0.16, 0.115)
    # mane ridge: short upright crest along the neck top
    side_n = nd.cross(UP).normalized()
    up_n = side_n.cross(nd).normalized()
    for t in (0.15, 0.4, 0.65, 0.88):
        c = neck0.lerp(neck1, t) + up_n * (0.155 - 0.05 * t + 0.03)
        ell(c, (0.075, 0.025, 0.06), _frame(side_n, up_n))
    hd = _dir(hyaw, hpitch)
    side_h = hd.cross(UP).normalized()
    up_h = side_h.cross(hd).normalized()
    Rh = Matrix((hd, side_h, up_h)).transposed()  # columns: x=along head, y=side, z=up
    skull = neck1 + hd * 0.10
    ell(skull, (0.19, 0.125, 0.15), Rh)                        # skull / cheeks (big donkey head)
    cap(skull + hd * 0.05 - up_h * 0.01, neck1 + hd * 0.52 - up_h * 0.045, 0.115, 0.088)  # muzzle (slightly down)
    ell(neck1 + hd * 0.52 - up_h * 0.045, (0.10, 0.095, 0.085), Rh)   # big rounded nose end
    ell(neck1 + hd * 0.28 - up_h * 0.08, (0.15, 0.09, 0.07), Rh)      # jaw
    # ---- ears: long, upright, splayed
    ear_base = skull - hd * 0.01 + up_h * 0.12
    for sy in (1, -1):
        ed = (up_h * 1.0 + side_h * 0.48 * sy - hd * 0.2).normalized()
        c = ear_base + side_h * 0.05 * sy + ed * 0.17
        ell(c + ed * 0.015, (0.03, 0.068, 0.21), _frame(side_h * sy, ed))
        ell(c + ed * 0.06, (0.026, 0.052, 0.13), _frame(side_h * sy, ed))  # keeps the tip wide (spoon)
    # ---- tail: thin with a tuft
    cap((-0.64, 0, 0.90), (-0.69, 0.02, 0.46), 0.035, 0.026)

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
    mb.sphere(0.05, (-0.70, 0.025, 0.37), DARK, seg=16, rings=8, scale=(1, 1, 2.2))   # dark tail tuft
    eye_c = skull + hd * 0.09 + up_h * 0.04
    for sy in (1, -1):
        mb.sphere(0.025, eye_c + side_h * 0.11 * sy, DARK, seg=14, rings=7)


def donkey_build(name, pose="standing"):
    mb = MB()
    donkey(mb, pose)
    ob = mb.build(name, merge=1e-5, smooth_angle=None)
    for p in ob.data.polygons:
        p.use_smooth = True
    return ob


# ================================================================== television
def tv(mb, stand=True, wall=False, diag_in=55):
    """Flat-screen TV, screen facing +X.  stand=True: on a centre pedestal, origin ground centre.
    wall=True: no stand, back of the set at x=0 (wall contact), screen centre 1.5 m up."""
    W = diag_in * 0.0254 * 16 / math.sqrt(16 ** 2 + 9 ** 2)     # 55" -> 1.218 m
    Hs = W * 9 / 16
    bez = 0.008
    Wt, Ht = W + 2 * bez, Hs + 2 * bez + 0.012              # thin bezel, slightly deeper chin
    depth = 0.045
    if wall:
        x0, zc = 0.0, 1.5
        mb.box((0.025, 0.4, 0.3), (0.0125, 0, zc), DARK)     # wall bracket
    else:
        x0, zc = -0.03, 0.09 + Ht / 2
    # body: thin slab, rounded corners
    rplate_yz(mb, Wt, Ht, depth, 0.012, x0, zc, DARK, n=3)
    # screen: glossy dark glass sunk 1 mm into the front face
    mb.box((0.004, W, Hs), (x0 + depth - 0.001, 0, zc + 0.006), GLASS)
    # back bulge (electronics) and ports
    rplate_yz(mb, W * 0.55, Hs * 0.55, 0.045, 0.02, x0 - 0.045, zc - 0.03, DARK, n=3)
    # tiny logo / IR window on the chin
    mb.box((0.002, 0.06, 0.006), (x0 + depth + 0.001, 0, zc - Ht / 2 + 0.012), BODY)
    if stand and not wall:
        # centre pedestal: slim neck + flat oval foot
        with mb.at((0.02, 0, 0), scale=(0.55, 1.0, 1.0)):
            mb.lathe([(0.0, 0.0), (0.22, 0.0), (0.21, 0.015), (0.05, 0.02), (0.0, 0.02)], DARK, n=32)
        mb.box((0.03, 0.26, 0.10), (x0 + 0.015, 0, 0.065), DARK)
        mb.box((0.06, 0.14, 0.02), (0.0, 0, 0.03), DARK)
    return W, Ht


def tv_boxed(mb, size=(1.35, 0.2, 0.8)):
    """Cardboard carton for the TV standing on its long edge, long side facing +X, with an accent stripe."""
    L, D, H = size
    # carton body: long axis along Y so the printed face (with the stripe) faces +X
    rbox(mb, D, L, H, 0.006, 0.0, BODY, n=2)
    # packing tape seam across the top and down the sides
    mb.box((D + 0.002, 0.05, 0.004), (0, 0, H + 0.001), BODY)
    # accent stripe band around the carton (slightly proud so it catches light)
    for x, n in ((D / 2 + 0.0015, 1), (-D / 2 - 0.0015, 1)):
        mb.box((0.003, L + 0.003, 0.09), (x, 0, H * 0.3), ACCENT)
    for y in (L / 2 + 0.0015, -L / 2 - 0.0015):
        mb.box((D + 0.003, 0.003, 0.09), (0, y, H * 0.3), ACCENT)
    # printed TV silhouette + text on the +X face
    mb.box((0.002, 0.62, 0.35), (D / 2 + 0.001, -0.18, H * 0.62), DARK)
    mb.box((0.002, 0.58, 0.31), (D / 2 + 0.0025, -0.18, H * 0.62 + 0.004), BODY)
    text_px(mb, f'{55}"', 0.11, D / 2 + 0.001, H * 0.66, DARK, 0.003, FONT_BLACK, y=0.36)
    text_px(mb, "4K  UHD", 0.045, D / 2 + 0.001, H * 0.53, DARK, 0.003, FONT_BOLD, y=0.36)
    text_px(mb, "THIS WAY UP", 0.03, D / 2 + 0.001, H * 0.12, DARK, 0.003, FONT_SEMI, y=0.45)
    mb.box((0.002, 0.012, 0.05), (D / 2 + 0.001, 0.45, H * 0.07 + 0.04), DARK)    # up arrow stem
    mb.prism_yz([(0.42, H * 0.1), (0.48, H * 0.1), (0.45, H * 0.14)], D / 2 + 0.001, D / 2 + 0.003, DARK)
    # hand-hold cutouts on the short ends
    for y in (L / 2, -L / 2):
        mb.box((0.03, 0.006, 0.03), (0, y, H * 0.75), DARK)


# ================================================================== hall pass
def hall_pass(mb, scale=1.0):
    """Chunky laminated hall pass on a lanyard; ~0.25 m tall overall at scale 1, standing, facing +X."""
    with mb.at(scale=scale):
        pw, ph, pt = 0.12, 0.15, 0.014
        zc = ph / 2
        rplate_yz(mb, pw, ph, pt, 0.012, -pt / 2, zc, ACCENT, n=4)
        # laminate edge: thin lighter border proud of the face
        rplate_yz(mb, pw + 0.006, ph + 0.006, 0.002, 0.014, -pt / 2 - 0.002, zc, BODY, n=4)
        rplate_yz(mb, pw + 0.006, ph + 0.006, 0.002, 0.014, pt / 2, zc, BODY, n=4)
        # text, two lines, extruded
        text_px(mb, "HALL", 0.04, pt / 2, zc + 0.028, DARK, 0.006, FONT_BLACK)
        text_px(mb, "PASS", 0.04, pt / 2, zc - 0.018, DARK, 0.006, FONT_BLACK)
        # thin rule and a small room number line
        mb.box((0.004, 0.08, 0.003), (pt / 2 + 0.002, 0, zc - 0.045), DARK)
        text_px(mb, "RM 101", 0.014, pt / 2, zc - 0.058, DARK, 0.004, FONT_SEMI)
        # clip + grommet at the top
        mb.cyl(0.006, pt + 0.004, (-pt / 2 - 0.002, 0, ph - 0.014), BODY, n=12, rot=(0, R(90), 0))
        mb.box((0.012, 0.022, 0.022), (0, 0, ph + 0.008), DARK)
        # lanyard: flat strap rising from the clip, draped into a loop above
        strap = [(-0.008, 0.0), (0.008, 0.0), (0.008, 0.004), (-0.008, 0.004)]
        path = [(0.0, 0.0, ph + 0.018), (0.0, 0.008, ph + 0.05), (0.0, 0.025, ph + 0.07),
                (0.0, 0.03, ph + 0.082)]
        mb.sweep(path, strap, DARK)
        path2 = [(0.0, 0.0, ph + 0.018), (0.0, -0.008, ph + 0.05), (0.0, -0.025, ph + 0.07),
                 (0.0, -0.03, ph + 0.082)]
        mb.sweep(path2, strap, DARK)
        mb.torus(0.03, 0.004, (0, 0, ph + 0.082), DARK, n=20, nr=8, rot=(0, R(90), 0))


# ================================================================== hand tools / small props (lying on the ground)
def hammer(mb, L=0.33):
    """Claw hammer lying flat, handle along -X, head at +X. Wood (BODY) handle, steel (DARK) head."""
    z = 0.017                                   # head centre height (head rests on the ground)
    x0, x1 = -L + 0.065, L * 0.0 - 0.03         # handle span along X; head centred at x = -0.015
    xh = -0.015
    # handle: oval-ish prism with rounded corners, lying just above the ground, grip end slightly thicker
    mb.prism_yz(rrect(0.027, 0.025, 0.01, 3, 0.0, z), x0, xh, BODY)
    mb.prism_yz(rrect(0.031, 0.029, 0.011, 3, 0.0, z), x0 + 0.1, x0 + 0.004, BODY)
    # head: eye block over the handle end, face toward +Y, claw toward -Y
    mb.box((0.034, 0.036, 0.034), (xh, 0.0, z), DARK)
    mb.cyl(0.0155, 0.03, (xh, 0.018, z), DARK, n=20, rot=(R(-90), 0, 0))           # neck of the face
    mb.cyl(0.018, 0.012, (xh, 0.048, z), DARK, n=20, rot=(R(-90), 0, 0))           # striking face
    # claw: two flat prongs toward -Y that curve back toward the handle (-X), with a narrow V gap between them
    for sx in (1, -1):
        path = [(xh + 0.006 * sx, -0.014, z), (xh + 0.008 * sx - 0.012, -0.036, z), (xh + 0.010 * sx - 0.03, -0.052, z),
                (xh + 0.012 * sx - 0.046, -0.06, z)]
        prof = [(-0.0035, -0.012), (0.0035, -0.012), (0.0035, 0.012), (-0.0035, 0.012)]
        mb.sweep(path, prof, DARK, scales=[1.0, 0.95, 0.8, 0.5])
    mb.box((0.028, 0.012, 0.03), (xh, -0.016, z), DARK)   # claw root wedge


def kitchen_knife(mb, L=0.33):
    """Chef's knife lying flat on its side, tip at +X. Blade BODY, handle DARK, rivets BODY."""
    bl, hl = 0.21, L - 0.21
    t = 0.0025
    # blade profile in XY (lying flat), heel at x=0, tip at x=bl, spine along +y side
    pts = [(0.0, 0.0), (0.0, 0.047), (0.09, 0.047), (bl, 0.044), (bl * 0.96, 0.03), (bl * 0.8, 0.012),
           (bl * 0.5, 0.0)]
    pts = [(x, y - 0.02) for x, y in pts]
    pts.reverse()
    mb.prism(pts, 0.0, t, BODY)
    # bolster + handle (thicker, dark, rounded)
    mb.prism(rrect(0.012, 0.04, 0.004, 3, -0.006, 0.0), 0.0, 0.014, DARK)
    mb.prism(rrect(hl, 0.036, 0.012, 4, -hl / 2 - 0.01, 0.0), 0.0, 0.018, DARK)
    for x in (-0.03, -0.065, -0.1):
        mb.cyl(0.004, 0.019, (x, 0, 0.0), BODY, n=12)
    # spine edge is not sharp: tiny chamfer handled by the live bevel


def car_keys(mb):
    """Key fob + two keys on a split ring, lying flat."""
    # split ring
    mb.torus(0.016, 0.0018, (0, 0, 0.0025), DARK, n=28, nr=8)
    # fob: rounded dark slab with accent buttons and a short loop
    with mb.at((0.045, 0.0, 0), rz=R(-12)):
        rbox(mb, 0.07, 0.034, 0.011, 0.012, 0.0, DARK)
        mb.cyl(0.004, 0.002, (0.012, 0.0, 0.011), ACCENT, n=12)
        mb.cyl(0.004, 0.002, (0.0, 0.0, 0.011), BODY, n=12)
        mb.box((0.012, 0.006, 0.002), (-0.015, 0.0, 0.011), ACCENT)
        mb.torus(0.007, 0.0015, (-0.038, 0, 0.004), DARK, n=16, nr=6)
    # keys: bow + blade, one metal (gold), one body-white
    for i, (ang, m) in enumerate(((R(150), METAL), (R(195), BODY))):
        with mb.at((0, 0, 0.001 + i * 0.0025), rz=ang):
            mb.lathe([(0, 0), (0.013, 0), (0.013, 0.0022), (0, 0.0022)], m, n=20, loc=(0.02, 0, 0))
            mb.lathe([(0, 0), (0.005, 0), (0.005, 0.0024), (0, 0.0024)], DARK, n=12, loc=(0.02, 0, -0.0001))  # hole
            mb.box((0.045, 0.008, 0.0022), (0.052, 0.0, 0.0011), m)
            for k in range(5):
                mb.box((0.004, 0.003, 0.0022), (0.036 + k * 0.008, 0.0045, 0.0011), m)


def book(mb, h=0.24, w=0.16, t=0.035, title="LIBERTY"):
    """Hardback lying flat, spine toward -Y, cover ACCENT with DARK title. Head of the book toward +X."""
    cw, ct = w + 0.006, 0.004
    # page block (slightly inset)
    mb.box((h - 0.004, w - 0.004, t - 2 * ct), (0.0, 0.004, t / 2), BODY)
    # covers
    rbox(mb, h + 0.004, cw, ct, 0.004, 0.0, ACCENT, cx=0.0, cy=0.003)
    rbox(mb, h + 0.004, cw, ct, 0.004, t - ct, ACCENT, cx=0.0, cy=0.003)
    # spine: rounded strip along -Y edge
    mb.prism_yz([(-w / 2 - 0.004, 0.0), (-w / 2 - 0.004, t), (-w / 2 - 0.012, t * 0.75), (-w / 2 - 0.012, t * 0.25)],
                -h / 2 - 0.002, h / 2 + 0.002, ACCENT)
    # title on the front cover (readable from +Z, head toward +X) and spine bands
    mb.text(title, fit_size(title, w * 0.7, 0.03, FONT_BLACK), (0.02, 0.0, t + 0.0024), DARK, rot=(0, 0, R(90)),
            depth=0.0015, font=FONT_BLACK)
    # thin embossed frame line around the cover
    fr = rrect(h - 0.03, w - 0.03, 0.006, 3, 0.0, 0.003)
    mb.prism(fr, t, t + 0.0012, DARK)
    mb.prism(rrect(h - 0.036, w - 0.036, 0.005, 3, 0.0, 0.003), t + 0.0012, t + 0.0024, ACCENT)
    for x in (h * 0.38, -h * 0.38):
        mb.box((0.004, 0.009, t * 0.5), (x, -w / 2 - 0.011, t / 2), DARK)


def rifle_prop(mb):
    """The figure.py carbine laid flat on its side on the ground (muzzle +X), all DARK."""
    g = carbine("_rifle", SC(), mat(DARK))
    me = g.data
    # rifle space: butt x=0, muzzle +x, bore z=0, sights up.  Lay on its right side: rotate -90 about X.
    M = Euler((R(-90), 0, 0)).to_matrix().to_4x4()
    me.transform(M)
    zmin = min(v.co.z for v in me.vertices)
    xs = [v.co.x for v in me.vertices]
    me.transform(Matrix.Translation((-(max(xs) + min(xs)) / 2, 0, -zmin)))
    mb.mesh_data(me, DARK)
    bpy.data.objects.remove(g)


# ================================================================== jail cell (tiny)
def jail_cell_tiny(mb, w=0.5, d=0.5, h=0.5, spacing=0.06, placard="NOT GUILTY"):
    """Small cage of bars, front +X, interior empty. Placard (ACCENT) with DARK text hangs on the front."""
    br = 0.006
    rail = 0.018
    # floor-less: just a bottom frame + top frame
    for z in (rail / 2, h - rail / 2):
        mb.box((w, rail, rail), (0, d / 2 - rail / 2, z), DARK)
        mb.box((w, rail, rail), (0, -d / 2 + rail / 2, z), DARK)
        mb.box((rail, d, rail), (w / 2 - rail / 2, 0, z), DARK)
        mb.box((rail, d, rail), (-w / 2 + rail / 2, 0, z), DARK)
    # corner posts
    for x in (w / 2 - rail / 2, -w / 2 + rail / 2):
        for y in (d / 2 - rail / 2, -d / 2 + rail / 2):
            mb.box((rail, rail, h), (x, y, h / 2), DARK)
    # bars
    n = int(round((w - 2 * rail) / spacing))
    for i in range(1, n):
        y = -w / 2 + rail + i * (w - 2 * rail) / n
        for x in (w / 2 - rail / 2, -w / 2 + rail / 2):
            mb.cyl(br, h - 2 * rail, (x, y, rail), DARK, n=10)
    m = int(round((d - 2 * rail) / spacing))
    for i in range(1, m):
        x = -d / 2 + rail + i * (d - 2 * rail) / m
        for y in (d / 2 - rail / 2, -d / 2 + rail / 2):
            mb.cyl(br, h - 2 * rail, (x, y, rail), DARK, n=10)
    # door outline on the front: a thin frame + hinges + a little lock box
    mb.box((0.006, 0.006, h * 0.72), (w / 2 + 0.004, 0.11, h * 0.46), DARK)
    mb.box((0.006, 0.006, h * 0.72), (w / 2 + 0.004, -0.11, h * 0.46), DARK)
    mb.box((0.006, 0.226, 0.006), (w / 2 + 0.004, 0, h * 0.82), DARK)
    mb.box((0.006, 0.226, 0.006), (w / 2 + 0.004, 0, h * 0.10), DARK)
    mb.box((0.016, 0.02, 0.03), (w / 2 + 0.01, -0.095, h * 0.5), DARK)
    for z in (h * 0.25, h * 0.7):
        mb.cyl(0.006, 0.03, (w / 2 + 0.006, 0.112, z - 0.015), DARK, n=10)
    # placard hanging on the front bars (ACCENT) with DARK text, slightly tilted
    pw, ph = 0.2, 0.075
    x_p = w / 2 + 0.012
    zc = h * 0.62
    with mb.at((x_p, 0, zc), rot=(R(0), R(-4), 0)):
        rplate_yz(mb, pw, ph, 0.006, 0.008, 0.0, 0.0, ACCENT, n=3)
        rplate_yz(mb, pw - 0.014, ph - 0.014, 0.0015, 0.005, 0.006, 0.0, BODY, n=3)
        text_px(mb, placard, fit_size(placard, pw - 0.03, 0.03, FONT_BLACK), 0.0075, 0.0, DARK, 0.004, FONT_BLACK)
        # two strings up to the top rail
        for y in (-0.07, 0.07):
            mb.rod((0.0, y, ph / 2), (-0.012, y, h - zc - rail / 2), 0.0015, DARK, n=6)


# ================================================================== gun safe
def gun_safe(mb, w=0.6, d=0.55, h=1.5, open_deg=0.0):
    """Steel gun safe, door on +X. open_deg swings the door about its +Y hinge (100 = wide open, shelf visible)."""
    t = 0.03                                      # wall thickness
    door_t = 0.05
    x_front = d / 2 - door_t
    if open_deg > 0:
        # hollow body: back, sides, top, bottom; interior shelf + a rifle rack bar
        mb.bb(-d / 2, -w / 2, 0, -d / 2 + t, w / 2, h, BODY)
        mb.bb(-d / 2, -w / 2, 0, x_front, -w / 2 + t, h, BODY)
        mb.bb(-d / 2, w / 2 - t, 0, x_front, w / 2, h, BODY)
        mb.bb(-d / 2, -w / 2, 0, x_front, w / 2, t + 0.02, BODY)
        mb.bb(-d / 2, -w / 2, h - t, x_front, w / 2, h, BODY)
        mb.bb(-d / 2 + t, -w / 2 + t, 0.52, x_front - 0.02, w / 2 - t, 0.54, BODY)    # shelf
        mb.bb(-d / 2 + t, -w / 2 + t, h - t - 0.22, x_front - 0.02, w / 2 - t, h - t - 0.2, BODY)  # top shelf
        mb.bb(-d / 2 + t, -w / 2 + t, 0.54, -d / 2 + t + 0.01, w / 2 - t, h - t - 0.22, DARK)  # felt back
        mb.bb(-d / 2 + t, -w / 2 + t, t + 0.02, -d / 2 + t + 0.01, w / 2 - t, 0.52, DARK)
        mb.bb(x_front - 0.02, -w / 2 + t, 0.60, x_front - 0.01, w / 2 - t, 0.62, DARK)  # rack bar
        # door frame lip
        mb.bb(x_front - 0.01, -w / 2, 0, x_front, w / 2, 0.06, DARK)
    else:
        mb.bb(-d / 2, -w / 2, 0, x_front, w / 2, h, BODY)
    # plinth
    mb.bb(-d / 2 + 0.02, -w / 2 + 0.02, 0, x_front - 0.02, w / 2 - 0.02, 0.05, DARK)
    # door: slab + raised panel, dial, handle, hinges, embossed brand strip.  Built hinge-local then rotated.
    hinge = Vector((x_front, w / 2 - 0.02, 0))
    with mb.at(hinge, rz=R(open_deg)):
        dw = w - 0.03
        mb.bb(0, -dw + 0.005, 0.06, door_t, -0.005 + 0.0, h - 0.0, BODY)     # door spans y: -dw .. 0 (hinge at y=0)
        # recessed panel line (dark groove rectangle) and outer bevel ridge
        g = 0.006
        mb.bb(door_t, -dw + 0.05, 0.11, door_t + 0.002, -dw + 0.05 + g, h - 0.05, DARK)
        mb.bb(door_t, -0.05 - g, 0.11, door_t + 0.002, -0.05, h - 0.05, DARK)
        mb.bb(door_t, -dw + 0.05, 0.11, door_t + 0.002, -0.05, 0.11 + g, DARK)
        mb.bb(door_t, -dw + 0.05, h - 0.05 - g, door_t + 0.002, -0.05, h - 0.05, DARK)
        # combination dial (DARK) with a BODY pointer ring, at chest height
        cy, cz = -dw * 0.5, h * 0.62
        mb.lathe([(0, 0), (0.07, 0), (0.07, 0.012), (0.06, 0.03), (0.0, 0.03)], DARK, n=32,
                 loc=(door_t, cy, cz), rot=(0, R(90), 0))
        mb.lathe([(0.03, 0), (0.05, 0), (0.05, 0.004), (0.03, 0.004)], BODY, n=32,
                 loc=(door_t + 0.03, cy, cz), rot=(0, R(90), 0))
        for k in range(12):
            a = TAU * k / 12
            mb.box((0.003, 0.003, 0.012), (door_t + 0.031, cy + 0.062 * math.cos(a), cz + 0.062 * math.sin(a)), BODY,
                   rot=(a - R(90), 0, 0))
        # 3-spoke handle below the dial
        hc = (door_t + 0.035, cy, cz - 0.18)
        mb.cyl(0.03, 0.055, (door_t, cy, cz - 0.18), DARK, n=24, rot=(0, R(90), 0))
        for k in range(3):
            a = TAU * k / 3 + R(90)
            mb.rod(hc, (hc[0], hc[1] + 0.12 * math.cos(a), hc[2] + 0.12 * math.sin(a)), 0.011, DARK, n=12)
            mb.sphere(0.016, (hc[0], hc[1] + 0.12 * math.cos(a), hc[2] + 0.12 * math.sin(a)), DARK, seg=14, rings=7)
        # locking bolts along the free edge (visible when open)
        for z in (0.3, 0.55, 0.8, 1.05, 1.3):
            mb.cyl(0.014, 0.03, (door_t / 2, -dw + 0.005, z), DARK, n=14, rot=(R(90), 0, 0))
        # brand plate
        mb.bb(door_t, -dw * 0.5 - 0.11, h - 0.16, door_t + 0.004, -dw * 0.5 + 0.11, h - 0.11, DARK)
        text_px(mb, "SENTINEL", 0.024, door_t + 0.004, h - 0.135, BODY, 0.002, FONT_BLACK, y=-dw * 0.5)
        # hinges on the y=0 edge
        for z in (0.2, h / 2, h - 0.2):
            mb.cyl(0.018, 0.12, (door_t / 2, 0.0, z - 0.06), DARK, n=14)


# ================================================================== front door
def front_door(mb, wall_w=3.0, wall_h=3.0, wall_t=0.25, door_h=2.1, door_w=0.9):
    """Section of wall (3x3 m) with a framed front door, knocker, letter slot, doormat and a step. Faces +X."""
    xf = wall_t / 2
    # wall with opening (built as 3 slabs) + a simple base skirt and top cornice line
    ow, oh = door_w + 0.1, door_h + 0.06
    mb.bb(-xf, -wall_w / 2, 0, xf, -ow / 2, wall_h, BODY)
    mb.bb(-xf, ow / 2, 0, xf, wall_w / 2, wall_h, BODY)
    mb.bb(-xf, -ow / 2, oh, xf, ow / 2, wall_h, BODY)
    # frame (casing) proud of the wall, DARK
    fw, ft = 0.08, 0.03
    mb.bb(xf, -ow / 2 - fw, 0, xf + ft, -ow / 2, oh + fw, DARK)
    mb.bb(xf, ow / 2, 0, xf + ft, ow / 2 + fw, oh + fw, DARK)
    mb.bb(xf, -ow / 2 - fw, oh, xf + ft, ow / 2 + fw, oh + fw, DARK)
    # jambs inside the opening
    mb.bb(-xf + 0.02, -ow / 2, 0, xf, -ow / 2 + 0.05, oh, DARK)
    mb.bb(-xf + 0.02, ow / 2 - 0.05, 0, xf, ow / 2, oh, DARK)
    mb.bb(-xf + 0.02, -ow / 2, oh - 0.05, xf, ow / 2, oh, DARK)
    # threshold / step
    mb.bb(xf - 0.02, -ow / 2 - 0.05, 0, xf + 0.18, ow / 2 + 0.05, 0.04, BODY)
    # door slab, set back a little in the jamb, with 4 raised panels
    xd = xf - 0.06
    dt = 0.045
    mb.bb(xd - dt, -door_w / 2, 0.04, xd, door_w / 2, door_h, BODY)
    for (y0, y1) in ((-door_w / 2 + 0.09, -0.04), (0.04, door_w / 2 - 0.09)):
        for (z0, z1) in ((0.16, 0.85), (1.0, 1.95)):
            mb.bb(xd, y0 + 0.012, z0 + 0.012, xd + 0.012, y1 - 0.012, z1 - 0.012, BODY)
            mb.bb(xd, y0, z0, xd + 0.002, y1, z1, DARK)       # shadow line around each panel
    # knocker (ring on a boss), letter slot, knob
    mb.cyl(0.035, 0.012, (xd + 0.012, 0, 1.45), METAL, n=24, rot=(0, R(90), 0))
    mb.torus(0.045, 0.008, (xd + 0.03, 0, 1.41), METAL, n=28, nr=10, rot=(0, R(90), 0))
    mb.bb(xd + 0.012, -0.13, 1.0, xd + 0.018, 0.13, 1.04, METAL)
    mb.bb(xd + 0.018, -0.11, 1.008, xd + 0.02, 0.11, 1.032, DARK)
    mb.cyl(0.012, 0.05, (xd + 0.012, -door_w / 2 + 0.08, 1.02), METAL, n=16, rot=(0, R(90), 0))
    mb.sphere(0.03, (xd + 0.065, -door_w / 2 + 0.08, 1.02), METAL, seg=18, rings=9)
    mb.cyl(0.02, 0.006, (xd + 0.012, -door_w / 2 + 0.08, 1.02), DARK, n=16, rot=(0, R(90), 0))
    # house number
    text_px(mb, "1776", 0.07, xf + ft, oh + 0.03 + 0.02, BODY, 0.006, FONT_BLACK)
    # porch light beside the door
    mb.bb(xf, ow / 2 + 0.16, 2.0, xf + 0.03, ow / 2 + 0.24, 2.08, DARK)
    mb.lathe([(0, 0), (0.05, 0), (0.05, 0.14), (0.03, 0.17), (0.0, 0.19)], LIGHT, n=16, loc=(xf + 0.08, ow / 2 + 0.2, 1.84))
    mb.lathe([(0.0, 0.0), (0.06, 0.0), (0.0, 0.03)], DARK, n=16, loc=(xf + 0.08, ow / 2 + 0.2, 2.03))
    mb.lathe([(0.0, 0.0), (0.06, 0.0), (0.06, 0.012), (0.0, 0.012)], DARK, n=16, loc=(xf + 0.08, ow / 2 + 0.2, 1.83))
    # doormat (DARK with BODY lettering) on the step's far side
    mw, md = 0.75, 0.45
    rbox(mb, md, mw, 0.018, 0.02, 0.0, DARK, cx=xf + 0.18 + md / 2 + 0.02)
    mb.text("WELCOME", fit_size("WELCOME", mw * 0.8, 0.09, FONT_BLACK), (xf + 0.18 + md / 2 + 0.02, 0, 0.018), BODY,
            rot=(0, 0, R(-90)), depth=0.004, font=FONT_BLACK)
    # skirting / plinth course on the wall
    mb.bb(xf, -wall_w / 2, 0, xf + 0.02, -ow / 2 - fw, 0.3, BODY)
    mb.bb(xf, ow / 2 + fw, 0, xf + 0.02, wall_w / 2, 0.3, BODY)


# ================================================================== living room
def sofa(mb, loc=(0, 0, 0), rz=0.0, w=2.1, d=0.92, seats=3):
    with mb.at(loc, rz):
        # frame: base, back, arms; cushions proud.  Front faces +X (local)
        mb.bb(-d / 2, -w / 2, 0.08, d / 2, w / 2, 0.40, BODY)                     # base
        mb.bb(-d / 2, -w / 2, 0.40, -d / 2 + 0.22, w / 2, 0.85, BODY)             # back
        for y0, y1 in ((-w / 2, -w / 2 + 0.16), (w / 2 - 0.16, w / 2)):
            mb.bb(-d / 2, y0, 0.40, d / 2 - 0.05, y1, 0.62, BODY)                # arms
        sw = (w - 0.32) / seats
        for i in range(seats):
            yc = -w / 2 + 0.16 + sw * (i + 0.5)
            mb.box((d - 0.3, sw - 0.02, 0.14), (0.06, yc, 0.47), BODY)           # seat cushion
            mb.box((0.14, sw - 0.03, 0.42), (-d / 2 + 0.28, yc, 0.64), BODY, rot=(0, R(-8), 0))  # back cushion
        for x in (-d / 2 + 0.08, d / 2 - 0.08):
            for y in (-w / 2 + 0.08, w / 2 - 0.08):
                mb.cyl(0.025, 0.08, (x, y, 0.0), DARK, n=12, r2=0.02)             # feet


def coffee_table(mb, loc=(0, 0, 0), rz=0.0, w=1.1, d=0.55, h=0.42):
    with mb.at(loc, rz):
        mb.box((d, w, 0.035), (0, 0, h - 0.0175), BODY)
        mb.box((d - 0.1, w - 0.1, 0.02), (0, 0, 0.15), BODY)                      # lower shelf
        for x in (-d / 2 + 0.05, d / 2 - 0.05):
            for y in (-w / 2 + 0.06, w / 2 - 0.06):
                mb.box((0.04, 0.04, h - 0.035), (x, y, (h - 0.035) / 2), DARK)
        # a couple of things on it: a mug and a remote (small, read as "lived in")
        mb.lathe([(0, 0), (0.04, 0), (0.04, 0.09), (0.034, 0.09), (0.034, 0.01), (0, 0.01)], BODY, n=20, loc=(0.1, -0.3, h))
        mb.torus(0.03, 0.006, (0.14, -0.3, h + 0.05), BODY, n=16, nr=6, rot=(0, R(90), 0))
        rbox(mb, 0.045, 0.16, 0.018, 0.012, h, DARK, cx=-0.08, cy=0.2)


def side_table(mb, loc=(0, 0, 0), rz=0.0, r=0.25, h=0.55):
    with mb.at(loc, rz):
        mb.cyl(r, 0.03, (0, 0, h - 0.03), BODY, n=32)
        mb.cyl(0.035, h - 0.03, (0, 0, 0.0), DARK, n=16)
        mb.lathe([(0, 0), (0.18, 0), (0.18, 0.02), (0.05, 0.04), (0, 0.04)], DARK, n=32)


def floor_lamp(mb, loc=(0, 0, 0), h=1.7):
    with mb.at(loc):
        mb.lathe([(0, 0), (0.16, 0), (0.16, 0.02), (0.04, 0.04), (0, 0.04)], DARK, n=32)
        mb.cyl(0.014, h - 0.4, (0, 0, 0.04), DARK, n=12)
        mb.lathe([(0.16, 0), (0.22, 0), (0.22, 0.004), (0.165, 0.34), (0.16, 0.34)], BODY, n=36, loc=(0, 0, h - 0.4))
        mb.lathe([(0.0, 0.0), (0.05, 0.0), (0.04, 0.10), (0.0, 0.10)], LIGHT, n=16, loc=(0, 0, h - 0.34))
        for k in range(3):
            a = TAU * k / 3
            mb.rod((0, 0, h - 0.38), (0.16 * math.cos(a), 0.16 * math.sin(a), h - 0.4), 0.003, DARK, n=6)


def rug(mb, loc=(0, 0, 0), rz=0.0, w=2.4, d=1.7, border=0.12):
    with mb.at(loc, rz):
        mb.box((d, w, 0.012), (0, 0, 0.006), ACCENT)
        mb.box((d - 2 * border, w - 2 * border, 0.004), (0, 0, 0.012 + 0.002), BODY)


def tv_stand(mb, loc=(0, 0, 0), rz=0.0, w=1.4, d=0.42, h=0.5):
    with mb.at(loc, rz):
        mb.bb(-d / 2, -w / 2, 0.06, d / 2, w / 2, h, BODY)
        mb.bb(d / 2 - 0.002, -w / 2 + 0.03, 0.1, d / 2 + 0.004, -0.015, h - 0.04, DARK)
        mb.bb(d / 2 - 0.002, 0.015, 0.1, d / 2 + 0.004, w / 2 - 0.03, h - 0.04, DARK)
        mb.bb(d / 2 - 0.002, -w / 2 + 0.03 + 0.004, 0.104, d / 2 + 0.006, -0.019, h - 0.044, BODY)
        mb.bb(d / 2 - 0.002, 0.019, 0.104, d / 2 + 0.006, w / 2 - 0.034, h - 0.044, BODY)
        for y in (-0.33, 0.33):
            mb.box((0.02, 0.09, 0.012), (d / 2 + 0.008, y, h / 2 + 0.03), DARK)
        for x in (-d / 2 + 0.05, d / 2 - 0.05):
            for y in (-w / 2 + 0.05, w / 2 - 0.05):
                mb.cyl(0.02, 0.06, (x, y, 0.0), DARK, n=10)


def living_room_set(mb, with_stand=True):
    """Sofa / coffee table / side table / rug / floor lamp laid out around the TV position at the origin.
    The TV spot at x=0 (1.4 m wide, facing -X) is left clear; the sofa sits at x=-3.1 facing +X toward it."""
    sofa(mb, (-3.1, 0, 0), rz=0.0)
    rug(mb, (-1.75, 0, 0), rz=0.0, w=2.6, d=1.8)
    coffee_table(mb, (-1.9, 0, 0), rz=0.0)
    side_table(mb, (-3.1, 1.45, 0))
    floor_lamp(mb, (-3.1, -1.5, 0))
    # a plant pot on the side table and a book to make it lived-in
    mb.lathe([(0, 0), (0.08, 0), (0.09, 0.09), (0.0, 0.09)], DARK, n=20, loc=(-3.1, 1.45, 0.55))
    for k in range(7):
        a = TAU * k / 7
        mb.rod((-3.1, 1.45, 0.62), (-3.1 + 0.12 * math.cos(a), 1.45 + 0.12 * math.sin(a), 0.80 + 0.04 * (k % 2)),
               0.012, BODY, n=6)
        mb.sphere(0.035, (-3.1 + 0.12 * math.cos(a), 1.45 + 0.12 * math.sin(a), 0.80 + 0.04 * (k % 2)), BODY, seg=10,
                  rings=5, scale=(1, 0.6, 0.35))
    if with_stand:
        tv_stand(mb, (0.0, 0, 0), rz=R(180))     # drawers face -X toward the sofa


# ================================================================== floating labels
def label(mb, text, w=0.5, h=0.18, t=0.03):
    """Rounded floating label plate (BODY) with DARK text, standing on the ground facing +X; bottom at z=0."""
    rplate_yz(mb, w, h, t, 0.03, -t / 2, h / 2, BODY, n=5)
    size = fit_size(text, w - 0.08, h * 0.5, FONT_BLACK)
    text_px(mb, text, size, t / 2, h / 2 - 0.002, DARK, 0.008, FONT_BLACK)
    # thin dark edge line inset on the face so the plate reads as a "tag" in white-on-white scenes
    inner = rrect(w - 0.03, h - 0.03, 0.022, 5)
    mb.prism_yz([(y, z + h / 2) for y, z in inner], t / 2, t / 2 + 0.0015, DARK)
    mb.prism_yz([(y, z + h / 2) for y, z in rrect(w - 0.038, h - 0.038, 0.018, 5)], t / 2 + 0.0015, t / 2 + 0.0025, BODY)
