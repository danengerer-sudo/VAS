"""Procedural main battle tank (Abrams-like silhouette).

Axes: +X forward, +Y left, +Z up. Origin on the ground under the hull center.
Returns a root empty; turret / gun / wheels / track links are named children so
the scene script can animate them (see animate_drive).
"""
import math
import bpy
from mathutils import Vector
from lib import *


def _convex_hull(pts):
    pts = sorted(set(pts))
    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
    lo, up = [], []
    for p in pts:
        while len(lo) >= 2 and cross(lo[-2], lo[-1], p) <= 0:
            lo.pop()
        lo.append(p)
    for p in reversed(pts):
        while len(up) >= 2 and cross(up[-2], up[-1], p) <= 0:
            up.pop()
        up.append(p)
    return lo[:-1] + up[:-1]


def build_tank(name="Tank", coll=None, livery="SENTINEL", livery_color=(0.9, 0.35, 0.05)):
    coll = coll or bpy.context.scene.collection
    paint = painted_metal(f"{name}_Paint", (0.115, 0.125, 0.068), (0.09, 0.1, 0.055), rough=0.62,
                          camo=[(0.10, 0.07, 0.042), (0.022, 0.022, 0.02)], scale=0.9, dirt=0.45)
    dark = pbr("TankDarkMetal", (0.035, 0.035, 0.033), rough=0.55, metal=0.7)
    rubber = pbr("Rubber", (0.025, 0.025, 0.025), rough=0.85)
    steel = pbr("WornSteel", (0.32, 0.31, 0.29), rough=0.38, metal=1.0)
    glassm = glass("SightGlass", (0.02, 0.05, 0.06))
    lightm = pbr("HeadLight", (0.8, 0.8, 0.75), rough=0.1, emission=((1, 0.95, 0.8), 0.0))
    decal = pbr(f"{name}_Decal", livery_color, rough=0.6)
    decal_w = pbr("DecalWhite", (0.7, 0.7, 0.66), rough=0.6)
    black = pbr("MatteBlack", (0.01, 0.01, 0.01), rough=0.9)

    root = empty(name, coll=coll)
    parts = []

    def P(o):
        parent(o, root)
        parts.append(o)
        return o

    # ---------------- hull
    lower = extrude_profile(f"{name}_LowerHull",
                            [(-3.8, 0.55), (3.25, 0.55), (3.92, 1.06), (3.92, 1.12), (-3.8, 1.12)],
                            2.2, "XZ", coll, paint)
    bevel(lower, 0.03)
    P(lower)
    upper = extrude_profile(f"{name}_UpperHull",
                            [(-3.95, 1.02), (3.96, 1.02), (4.0, 1.12), (2.55, 1.46), (-3.85, 1.46),
                             (-3.97, 1.38)],
                            3.62, "XZ", coll, paint)
    bevel(upper, 0.035)
    P(upper)

    # side skirts: panels with small gaps, front one tapered
    for side in (1, -1):
        y = side * 1.83
        xs = [-3.7, -2.55, -1.45, -0.35, 0.75, 1.85, 2.95]
        for i in range(len(xs) - 1):
            x0, x1 = xs[i] + 0.012, xs[i + 1] - 0.012
            pts = [(x0, 0.56), (x1, 0.56), (x1, 1.17), (x0, 1.17)]
            sk = extrude_profile(f"{name}_Skirt", pts, 0.07, "XZ", coll, paint, loc=(0, y, 0))
            bevel(sk, 0.012)
            P(sk)
        # tapered front skirt
        sk = extrude_profile(f"{name}_SkirtFront",
                             [(2.97, 0.56), (3.55, 0.64), (3.95, 0.95), (3.98, 1.17), (2.97, 1.17)],
                             0.07, "XZ", coll, paint, loc=(0, y, 0))
        bevel(sk, 0.012)
        P(sk)
        # rear mud flap
        P(box(f"{name}_Flap", (0.35, 0.07, 0.55), (-3.85, y, 0.85), coll, 0.01, rubber))
        # fender lip on top of skirts
        P(box(f"{name}_Fender", (7.6, 0.24, 0.03), (0.15, side * 1.73, 1.19), coll, 0.008, paint))
        # livery number on skirt
        P(text_decal(f"{name}_Lbl", livery + " DEFENSE CO.", 0.16, decal_w,
                     (-1.0, side * 1.871, 0.86), (math.radians(90), 0, math.pi if side > 0 else 0),
                     coll, font="/usr/share/fonts/opentype/inter/Inter-Bold.otf"))
        P(box(f"{name}_Band", (1.0, 0.004, 0.09), (1.15 if side > 0 else -3.15, side * 1.868, 0.86),
              coll, 0, decal))

    # rear grille / engine deck
    for i in range(9):
        P(box(f"{name}_Grille", (0.06, 1.7, 0.02), (-3.3 + i * 0.12, 0, 1.47), coll, 0, dark))
    P(box(f"{name}_RearPlate", (0.04, 1.5, 0.28), (-3.97, 0, 1.2), coll, 0.005, dark))
    # driver hatch & periscopes
    P(cylinder(f"{name}_DrvHatch", 0.32, 0.06, (2.45, 0, 1.47), coll=coll, mat=paint, bev=0.01))
    for k in (-1, 0, 1):
        p = box(f"{name}_Peri", (0.08, 0.16, 0.07), (2.75, k * 0.2, 1.43), coll, 0.005, glassm)
        p.rotation_euler = (0, math.radians(-15), 0)
        P(p)
    # headlights / tow hooks
    for side in (1, -1):
        P(box(f"{name}_LightHousing", (0.12, 0.3, 0.14), (3.92, side * 1.45, 1.22), coll, 0.01, paint))
        P(cylinder(f"{name}_Light", 0.045, 0.03, (3.98, side * 1.52, 1.23), (0, math.pi / 2, 0),
                   coll=coll, mat=lightm))
        P(cylinder(f"{name}_Light2", 0.035, 0.03, (3.98, side * 1.39, 1.23), (0, math.pi / 2, 0),
                   coll=coll, mat=lightm))
        P(box(f"{name}_Tow", (0.18, 0.08, 0.12), (3.9, side * 0.75, 0.7), coll, 0.01, dark))

    # ---------------- running gear
    wheel_r = 0.31
    wheels = []
    road_x = [-2.85, -1.9, -0.95, 0.0, 0.95, 1.9, 2.85]
    circles = [(x, 0.36, wheel_r) for x in road_x] + [(-3.55, 0.78, 0.31), (3.6, 0.76, 0.3)] + \
              [(-1.6, 1.0, 0.1), (0.4, 1.02, 0.1), (2.2, 1.02, 0.1)]
    for side in (1, -1):
        y = side * 1.42
        for (x, z, r) in circles:
            w = lathe(f"{name}_Wheel", [(-0.27, 0.0), (-0.27, r * 0.45), (-0.25, r * 0.8),
                                        (-0.23, r), (-0.04, r), (-0.03, r * 0.82), (0.03, r * 0.82),
                                        (0.04, r), (0.23, r), (0.25, r * 0.8), (0.27, r * 0.45),
                                        (0.27, 0.0)], verts=28, coll=coll, mat=dark, axis="Y")
            w.location = (x, y, z)
            # rubber tyres on road wheels
            if r > 0.2:
                hub = cylinder(f"{name}_Hub", r * 0.35, 0.58, (0, 0, 0), (math.pi / 2, 0, 0), 12,
                               coll, paint)
                parent(hub, w)
            P(w)
            wheels.append(w)
        # drive sprocket teeth (rear)
        for t in range(11):
            a = 2 * math.pi * t / 11
            tooth = box(f"{name}_Tooth", (0.08, 0.5, 0.1), (math.cos(a) * 0.33, 0, math.sin(a) * 0.33),
                        coll, 0.0, dark)
            tooth.rotation_euler = (0, -a, 0)
            parent(tooth, wheels[-5])

    # track: hull path around wheels, links arrayed along a cyclic curve
    pts = []
    for (x, z, r) in circles:
        rr = r + 0.045
        for i in range(48):
            a = 2 * math.pi * i / 48
            pts.append((round(x + rr * math.cos(a), 5), round(z + rr * math.sin(a), 5)))
    hull = _convex_hull(pts)
    tracks = []
    for side in (1, -1):
        cu = bpy.data.curves.new(f"{name}_TrackPath", "CURVE")
        cu.dimensions = "2D"
        sp = cu.splines.new("POLY")
        sp.points.add(len(hull) - 1)
        for i, (x, z) in enumerate(reversed(hull)):
            sp.points[i].co = (x, z, 0, 1)
        sp.use_cyclic_u = True
        path = link(bpy.data.objects.new(f"{name}_TrackPath", cu), coll)
        path.location = (0, side * 1.42, 0)
        path.rotation_euler = (math.pi / 2, 0, 0)
        P(path)
        path.hide_render = True
        # path length
        L = 0
        hp = list(reversed(hull))
        for i in range(len(hp)):
            a, b = hp[i], hp[(i + 1) % len(hp)]
            L += math.dist(a, b)
        pitch = 0.155
        count = int(L / pitch)
        pitch = L / count
        # single link: shoe with grouser and centre guide horns
        shoe = box(f"{name}_TrackLink", (pitch * 0.92, 0.045, 0.63), (0, 0, 0), coll, 0.0, rubber)
        g = box("g", (0.04, 0.03, 0.63), (0, -0.035, 0), coll, 0, dark)
        horn = box("h", (0.06, 0.08, 0.05), (0, 0.06, 0), coll, 0, dark)
        link_o = join([shoe, g, horn], f"{name}_TrackLink")
        bevel(link_o, 0.006, 1)
        link_o.location = (0, side * 1.42, 0)
        arr = link_o.modifiers.new("Array", "ARRAY")
        arr.count = count
        arr.relative_offset_displace = (0, 0, 0)
        arr.use_relative_offset = False
        arr.use_constant_offset = True
        arr.constant_offset_displace = (pitch, 0, 0)
        cm = link_o.modifiers.new("Curve", "CURVE")
        cm.object = path
        cm.deform_axis = "POS_X"
        # put the link on the path start
        link_o.parent = path
        link_o.location = (0, 0, 0)
        link_o["pitch"] = pitch
        link_o["length"] = L
        tracks.append(link_o)

    # ---------------- turret
    turret = empty(f"{name}_Turret", (-0.35, 0, 1.46), coll)
    parent(turret, root)
    tprof = [(2.25, 0.55), (1.65, 1.78), (-1.55, 1.85), (-2.35, 1.55), (-2.35, -1.55), (-1.55, -1.85),
             (1.65, -1.78), (2.25, -0.55)]
    tb = extrude_profile(f"{name}_TurretBody", tprof, 0.66, "XY", coll, paint, center=False)
    for v in tb.data.vertices:
        if v.co.z > 0.5:
            v.co.y *= 0.94
            if v.co.x > 1.0:
                v.co.x -= 0.32
            else:
                v.co.x *= 0.97
    bevel(tb, 0.04)
    parent(tb, turret)
    ring = cylinder(f"{name}_Ring", 1.05, 0.1, (0.1, 0, 0.0), coll=coll, mat=dark)
    parent(ring, turret)
    # bustle rack
    for z in (0.2, 0.55):
        parent(box(f"{name}_Rack", (0.05, 3.0, 0.05), (-2.95, 0, z), coll, 0.01, dark), turret)
    for yy in (-1.45, -0.7, 0, 0.7, 1.45):
        parent(box(f"{name}_RackPost", (0.6, 0.04, 0.04), (-2.65, yy, 0.55), coll, 0.0, dark), turret)
        parent(box(f"{name}_RackPostV", (0.04, 0.04, 0.4), (-2.95, yy, 0.37), coll, 0.0, dark), turret)
    # stowage in rack: crates / bags
    parent(box(f"{name}_Stow1", (0.5, 0.9, 0.35), (-2.65, 0.8, 0.2), coll, 0.04,
               pbr("Canvas", (0.12, 0.11, 0.07), rough=0.95)), turret)
    parent(box(f"{name}_Stow2", (0.5, 0.7, 0.3), (-2.65, -0.65, 0.18), coll, 0.03,
               pbr("Canvas", (0.12, 0.11, 0.07), rough=0.95)), turret)
    parent(box(f"{name}_Can", (0.17, 0.35, 0.47), (-2.65, 0.1, 0.25), coll, 0.02,
               pbr("CanGreen", (0.05, 0.08, 0.04), rough=0.5, metal=0.4)), turret)
    # side bins
    for side in (1, -1):
        bn = box(f"{name}_Bin", (1.5, 0.3, 0.42), (-0.9, side * 1.95, 0.4), coll, 0.02, paint)
        parent(bn, turret)
        # smoke grenade launchers (6 tubes)
        for i in range(6):
            tu = cylinder(f"{name}_Smoke", 0.045, 0.22, (1.6 - (i % 3) * 0.12, side * (1.72 + 0.0), 0.48 + (i // 3) * 0.1),
                          (0, math.radians(-75), side * math.radians(35)), 10, coll, dark)
            parent(tu, turret)
        # livery emblem: shield
        sh = extrude_profile(f"{name}_Shield", [(-0.2, 0.22), (0.2, 0.22), (0.2, -0.02), (0, -0.25), (-0.2, -0.02)],
                             0.01, "XZ", coll, decal)
        sh.location = (0.0, side * 1.82, 0.36)
        sh.rotation_euler = (0, 0, side * math.radians(1.3))
        sh.scale = (0.8, 1, 0.8)
        parent(sh, turret)
        tx = text_decal(f"{name}_ShieldTxt", livery[0], 0.22, decal_w,
                        (0.0, side * 1.83, 0.39), (math.radians(90), 0, math.pi if side > 0 else 0),
                        coll, font="/usr/share/fonts/opentype/inter/Inter-Bold.otf")
        parent(tx, turret)
        # antenna
        ant = cylinder(f"{name}_Antenna", 0.008, 2.6, (-2.0, side * 1.3, 1.93), (0, math.radians(-6), 0), 6,
                       coll, black)
        parent(ant, turret)
        parent(cylinder(f"{name}_AntBase", 0.05, 0.12, (-2.0, side * 1.3, 0.68), coll=coll, mat=dark), turret)

    # gunner's primary sight
    gps = box(f"{name}_GPS", (0.55, 0.45, 0.38), (1.0, -0.85, 0.83), coll, 0.03, paint)
    parent(gps, turret)
    parent(box(f"{name}_GPSGlass", (0.02, 0.35, 0.22), (1.28, -0.85, 0.85), coll, 0.0, glassm), turret)
    # CITV (commander's independent thermal viewer)
    parent(cylinder(f"{name}_CITVb", 0.2, 0.3, (0.6, 0.95, 0.81), coll=coll, mat=paint, bev=0.01), turret)
    citv = box(f"{name}_CITV", (0.4, 0.38, 0.32), (0.6, 0.95, 1.1), coll, 0.03, paint)
    parent(citv, turret)
    parent(box(f"{name}_CITVg", (0.02, 0.28, 0.18), (0.81, 0.95, 1.1), coll, 0.0, glassm), turret)
    # commander cupola + M2
    parent(cylinder(f"{name}_Cupola", 0.45, 0.22, (-0.4, -0.75, 0.76), coll=coll, mat=paint, bev=0.02), turret)
    for i in range(6):
        a = math.radians(-60 + i * 30)
        pp = box(f"{name}_CupPeri", (0.08, 0.14, 0.08), (-0.4 + 0.44 * math.cos(a), -0.75 + 0.44 * math.sin(a), 0.80),
                 coll, 0.0, glassm)
        pp.rotation_euler = (0, 0, a)
        parent(pp, turret)
    parent(cylinder(f"{name}_CupHatch", 0.36, 0.05, (-0.45, -0.75, 0.89), coll=coll, mat=paint, bev=0.01), turret)
    mg = _machine_gun(f"{name}_M2", coll, dark, steel, scale=1.0)
    mg.location = (-0.05, -0.75, 1.0)
    parent(mg, turret)
    # loader hatch + M240
    parent(cylinder(f"{name}_LdrHatch", 0.36, 0.06, (-0.4, 0.8, 0.69), coll=coll, mat=paint, bev=0.01), turret)
    mg2 = _machine_gun(f"{name}_M240", coll, dark, steel, scale=0.75)
    mg2.location = (-0.1, 1.15, 0.83)
    parent(mg2, turret)
    # wind sensor mast
    parent(cylinder(f"{name}_Wind", 0.015, 0.45, (-1.6, 0, 0.88), coll=coll, mat=black), turret)

    # ---------------- gun
    gun = empty(f"{name}_Gun", (1.78, 0, 0.36), coll)
    parent(gun, turret)
    mant = extrude_profile(f"{name}_Mantlet", [(-0.1, -0.25), (0.42, -0.2), (0.42, 0.2), (-0.1, 0.25)],
                           0.9, "XZ", coll, paint)
    bevel(mant, 0.03)
    parent(mant, gun)
    barrel = lathe(f"{name}_Barrel",
                   [(0.3, 0.0), (0.3, 0.2), (0.6, 0.19), (0.62, 0.135), (2.2, 0.128), (2.22, 0.14), (2.3, 0.14),
                    (2.32, 0.125), (3.05, 0.118), (3.15, 0.17), (3.75, 0.17), (3.85, 0.112), (5.1, 0.102),
                    (5.12, 0.115), (5.3, 0.115), (5.3, 0.07), (5.0, 0.062), (5.0, 0.0)],
                   verts=32, coll=coll, mat=paint)
    parent(barrel, gun)
    parent(cylinder(f"{name}_Coax", 0.03, 0.4, (0.35, 0.33, 0.05), (0, math.pi / 2, 0), 10, coll, dark), gun)

    root["wheels"] = [w.name for w in wheels]
    root["tracks"] = [t.name for t in tracks]
    root["turret"] = turret.name
    root["gun"] = gun.name
    return root


def _machine_gun(name, coll, dark, steel, scale=1.0):
    s = scale
    root = empty(name, coll=coll)
    parts = [
        box(name + "_rcv", (0.55 * s, 0.11 * s, 0.13 * s), (0, 0, 0), coll, 0.01, dark),
        cylinder(name + "_brl", 0.022 * s, 0.95 * s, (0.72 * s, 0, 0.02 * s), (0, math.pi / 2, 0), 12, coll, steel),
        cylinder(name + "_jkt", 0.04 * s, 0.25 * s, (0.38 * s, 0, 0.02 * s), (0, math.pi / 2, 0), 12, coll, dark),
        box(name + "_grips", (0.1 * s, 0.14 * s, 0.1 * s), (-0.33 * s, 0, -0.02 * s), coll, 0.01, dark),
        box(name + "_box", (0.2 * s, 0.12 * s, 0.14 * s), (0.02 * s, 0.13 * s, -0.04 * s), coll, 0.01,
            pbr("AmmoGreen", (0.06, 0.08, 0.04), rough=0.6, metal=0.3)),
        cylinder(name + "_post", 0.025 * s, 0.25 * s, (-0.05 * s, 0, -0.17 * s), (0, 0, 0), 10, coll, dark),
    ]
    for p in parts:
        parent(p, root)
    return root


def animate_drive(root, f0, f1, distance, turret_keys=None, gun_keys=None):
    """Spin wheels & scroll track links for a hull that moves `distance` metres
    between frames f0..f1 (caller animates root location)."""
    for wn in root["wheels"]:
        w = bpy.data.objects[wn]
        r = max(0.1, w.dimensions.z / 2)
        w.rotation_euler = (0, 0, 0)
        w.keyframe_insert("rotation_euler", frame=f0)
        w.rotation_euler = (0, distance / r, 0)
        w.keyframe_insert("rotation_euler", frame=f1)
        set_interp(w, "LINEAR")
    for tn in root["tracks"]:
        t = bpy.data.objects[tn]
        t.location = (0, 0, 0)
        t.keyframe_insert("location", frame=f0)
        # curve runs clockwise seen from +Y, so the bottom run moves backward
        t.location = (distance, 0, 0)
        t.keyframe_insert("location", frame=f1)
        set_interp(t, "LINEAR")
