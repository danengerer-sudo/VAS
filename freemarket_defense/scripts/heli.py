"""Procedural utility helicopter (UH-60-like). +X forward, origin on the ground."""
import math
import bpy
from lib import *


def _interp(keys, x):
    """Piecewise-cubic (Catmull-Rom) interpolation of section parameters."""
    xs = [k[0] for k in keys]
    for i in range(len(keys) - 1):
        if xs[i] >= x >= xs[i + 1]:
            break
    i0, i1 = i, i + 1
    t = (x - xs[i0]) / (xs[i1] - xs[i0])
    ip, i2 = max(i0 - 1, 0), min(i1 + 1, len(keys) - 1)
    out = []
    for j in range(1, len(keys[0])):
        p0, p1, p2, p3 = keys[ip][j], keys[i0][j], keys[i1][j], keys[i2][j]
        out.append(0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t * t
                          + (-p0 + 3 * p1 - 3 * p2 + p3) * t ** 3))
    return out


def build_heli(name="Heli", coll=None, livery="AEGIS AIR", livery_color=(0.05, 0.25, 0.75)):
    coll = coll or bpy.context.scene.collection
    paint = painted_metal(f"{name}_Paint", (0.042, 0.048, 0.04), (0.034, 0.038, 0.032), rough=0.5,
                          scale=0.4, dirt=0.25)
    dark = pbr("HeliDark", (0.02, 0.02, 0.02), rough=0.45, metal=0.6)
    steel = pbr("WornSteel", (0.32, 0.31, 0.29), rough=0.38, metal=1.0)
    rubber = pbr("Rubber", (0.025, 0.025, 0.025), rough=0.85)
    glassm = glass("CockpitGlass", (0.03, 0.045, 0.05))
    decal = pbr(f"{name}_Decal", livery_color, rough=0.5)
    white = pbr("DecalWhite", (0.7, 0.7, 0.66), rough=0.6)
    red = pbr("NavRed", (0.5, 0.0, 0.0), emission=((1, 0.05, 0.02), 8.0))
    green = pbr("NavGreen", (0.0, 0.5, 0.0), emission=((0.05, 1, 0.1), 8.0))
    font = "/usr/share/fonts/opentype/inter/Inter-Bold.otf"

    root = empty(name, coll=coll)

    def P(o, par=None):
        parent(o, par or root)
        return o

    # ------------------------------------------------ fuselage loft
    #        x      half_w  bottom  top
    keys = [(4.85, 0.04, 1.30, 1.40),
            (4.70, 0.42, 0.95, 1.80),
            (4.30, 0.74, 0.70, 2.15),
            (3.70, 0.95, 0.58, 2.48),
            (3.00, 1.05, 0.55, 2.68),
            (2.00, 1.10, 0.55, 2.76),
            (0.00, 1.12, 0.55, 2.80),
            (-1.60, 1.10, 0.60, 2.80),
            (-2.60, 0.92, 0.95, 2.74),
            (-3.40, 0.58, 1.55, 2.62),
            (-4.20, 0.40, 1.92, 2.56),
            (-9.60, 0.24, 2.15, 2.58),
            (-10.35, 0.20, 2.22, 2.62),
            (-10.45, 0.02, 2.40, 2.45)]
    N = 48
    secs = []
    xs = []
    x = keys[0][0]
    while x > keys[-1][0]:
        xs.append(x)
        x -= 0.12 if x > -4.5 else 0.4
    xs.append(keys[-1][0])
    for x in xs:
        hw, bot, top = _interp(keys, x)
        hw = max(hw, 0.01)
        cz = (top + bot) / 2
        h = max((top - bot) / 2, 0.01)
        p = 3.2 if -3 < x < 4.2 else 2.4
        secs.append(superellipse(0, 0, cz, hw, h, h, N, p, x))
    for s, x in zip(secs, xs):
        for i in range(len(s)):
            s[i] = (x, s[i][1], s[i][2])
    fus = loft(f"{name}_Fuselage", secs, coll, smooth=True)
    gi = add_mat(fus, paint)
    gi = add_mat(fus, glassm)
    gi_band = add_mat(fus, decal)
    # glass: windscreen + chin windows + side cockpit + cabin windows
    for poly in fus.data.polygons:
        c = poly.center
        hw, bot, top = _interp(keys, max(min(c.x, 4.85), -10.45))
        zr = (c.z - bot) / max(top - bot, 1e-3)  # 0 bottom .. 1 top
        yr = abs(c.y) / max(hw, 1e-3)
        g = False
        if 3.15 < c.x < 4.72 and zr > 0.52 and yr < 0.97:
            g = True  # windscreen
        if 3.35 < c.x < 4.55 and 0.2 < zr < 0.42 and 0.35 < yr < 0.95:
            g = True  # chin bubbles
        if 2.05 < c.x < 3.1 and 0.55 < zr < 0.88 and yr > 0.8:
            g = True  # cockpit doors
        for x0 in (-1.15, 0.2):
            if x0 < c.x < x0 + 0.85 and 0.62 < zr < 0.86 and yr > 0.85:
                g = True  # cabin windows
        if g:
            poly.material_index = 1
        if -8.3 < c.x < -7.4 and yr > 0.6:
            poly.material_index = 2
    weighted_normals(fus)
    P(fus)

    # window frames (dark strips) and door seams
    for side in (1, -1):
        for xx in (2.05, 3.1, -1.15, -0.3, 0.2, 1.05):
            P(box(f"{name}_Frame", (0.05, 0.03, 0.9 if xx > 2 else 0.6),
                  (xx, side * (1.11 if xx < 2 else 1.07), 2.15 if xx < 2 else 2.05), coll, 0, dark))
        P(box(f"{name}_DoorRail", (2.6, 0.04, 0.04), (-0.2, side * 1.13, 2.62), coll, 0.005, dark))
        P(box(f"{name}_Step", (0.5, 0.1, 0.03), (1.6, side * 1.13, 0.75), coll, 0.005, dark))

    # cockpit interior hint: dark tub so the glazing doesn't look empty
    P(box(f"{name}_CockpitDark", (1.8, 1.9, 1.0), (3.2, 0, 1.25), coll, 0.0,
          pbr("Interior", (0.015, 0.015, 0.015), rough=0.8)))
    for yy in (0.45, -0.45):
        P(box(f"{name}_Seat", (0.5, 0.5, 0.9), (2.7, yy, 1.6), coll, 0.05,
              pbr("SeatGray", (0.06, 0.06, 0.055), rough=0.9)))
    P(box(f"{name}_Dash", (0.35, 1.7, 0.35), (3.85, 0, 1.75), coll, 0.03,
          pbr("Interior", (0.015, 0.015, 0.015), rough=0.8)))

    # ------------------------------------------------ upper deck: doghouse + engines
    dk = [(2.6, 0.05, 2.70, 2.82), (2.2, 0.62, 2.72, 3.20), (1.2, 0.78, 2.74, 3.38),
          (-0.8, 0.78, 2.74, 3.40), (-2.6, 0.62, 2.70, 3.18), (-3.8, 0.30, 2.58, 2.86),
          (-4.6, 0.05, 2.52, 2.6)]
    secs = []
    x = dk[0][0]
    while x > dk[-1][0]:
        hw, bot, top = _interp(dk, x)
        secs.append(superellipse(0, 0, (top + bot) / 2, max(hw, .01), (top - bot) / 2, (top - bot) / 2, 32, 3.5, x))
        for i in range(len(secs[-1])):
            secs[-1][i] = (x, secs[-1][i][1], secs[-1][i][2])
        x -= 0.15
    dh = loft(f"{name}_Doghouse", secs, coll, mat=paint)
    weighted_normals(dh)
    P(dh)
    for side in (1, -1):
        eng = lathe(f"{name}_Engine", [(1.0, 0.0), (1.0, 0.2), (0.85, 0.33), (0.3, 0.37), (-1.5, 0.37),
                                       (-1.9, 0.3), (-1.95, 0.0)], 28, coll, paint, "X")
        eng.location = (0, side * 0.82, 3.05)
        P(eng)
        P(cylinder(f"{name}_Intake", 0.2, 0.05, (1.01, side * 0.82, 3.05), (0, math.pi / 2, 0), 20, coll, dark))
        ex = lathe(f"{name}_Exhaust", [(0, 0.18), (0.7, 0.22), (0.7, 0.19), (0.02, 0.15)], 20, coll, dark, "X")
        ex.location = (-1.95, side * 0.82, 3.05)
        ex.rotation_euler = (0, 0, side * math.radians(150) + (math.pi if side < 0 else 0) * 0)
        ex.rotation_euler = (0, 0, math.pi - side * math.radians(30))
        P(ex)
    # IR jammer & antennas
    P(cylinder(f"{name}_IRJam", 0.16, 0.35, (-3.6, 0, 3.0), coll=coll, mat=dark))
    P(box(f"{name}_AntBlade", (0.35, 0.02, 0.25), (-6.0, 0, 2.7), coll, 0.0, dark))
    P(box(f"{name}_AntBlade2", (0.3, 0.02, 0.2), (1.8, 0, 0.45), coll, 0.0, dark))
    P(cylinder(f"{name}_Beacon", 0.06, 0.08, (-2.9, 0, 3.17), coll=coll, mat=red))
    # pitot tubes
    for side in (1, -1):
        P(cylinder(f"{name}_Pitot", 0.015, 0.6, (4.6, side * 0.55, 2.2), (0, math.radians(80), 0), 6, coll, steel))
    # wire cutter
    P(box(f"{name}_Cutter", (0.6, 0.03, 0.06), (4.0, 0, 2.62), coll, 0, steel)).rotation_euler = (0, math.radians(-18), 0)

    # ------------------------------------------------ tail
    pylon = extrude_profile(f"{name}_Pylon",
                            [(-9.2, 2.35), (-10.45, 2.3), (-11.15, 4.35), (-10.55, 4.45), (-9.7, 2.85)],
                            0.3, "XZ", coll, paint)
    bevel(pylon, 0.03)
    P(pylon)
    stab = extrude_profile(f"{name}_Stab", [(-9.7, -2.2), (-10.55, -2.2), (-10.6, 2.2), (-9.75, 2.2)],
                           0.08, "XY", coll, paint, loc=(0, 0, 2.5))
    bevel(stab, 0.02)
    P(stab)
    P(text_decal(f"{name}_Lbl1", livery, 0.28, white, (-6.0, 0.335, 2.37), (math.radians(90), 0, math.pi), coll, font=font))
    P(text_decal(f"{name}_Lbl2", livery, 0.28, white, (-6.0, -0.335, 2.37), (math.radians(90), 0, 0), coll, font=font))
    P(text_decal(f"{name}_Tail1", "N-417A", 0.22, white, (-10.5, 0.16, 3.2), (math.radians(90), 0, math.pi), coll, font=font))
    P(cylinder(f"{name}_NavL", 0.04, 0.06, (-10.45, 0, 2.47), (0, math.pi / 2, 0), 8, coll, red))

    # tail rotor (right side), canted
    tr = empty(f"{name}_TailRotor", (-10.75, -0.28, 3.95), coll)
    tr.rotation_euler = (0, 0, 0)
    P(tr)
    trs = empty(f"{name}_TailRotorSpin", (0, 0, 0), coll)
    parent(trs, tr)
    parent(cylinder(f"{name}_TRHub", 0.12, 0.25, (0, 0, 0), (math.pi / 2, 0, 0), 16, coll, dark), trs)
    for i in range(4):
        a = i * math.pi / 2
        bl = box(f"{name}_TRBlade", (0.2, 0.03, 1.65), (0, -0.08, 0), coll, 0.0, dark)
        bl.data.transform(__import__("mathutils").Matrix.Translation((0, 0, 0.9)))
        bl.rotation_euler = (0, a, 0)
        parent(bl, trs)
    tr.rotation_euler = (math.radians(-20), 0, 0)

    # ------------------------------------------------ stub wings + rocket pods
    for side in (1, -1):
        w = extrude_profile(f"{name}_Wing", [(0.35, 0), (-0.55, 0), (-0.45, side * 2.0), (0.15, side * 2.0)],
                            0.12, "XY", coll, paint, loc=(0, side * 1.0, 2.55))
        bevel(w, 0.02)
        P(w)
        for k, yy in enumerate((1.45, 2.55)):
            pod = lathe(f"{name}_Pod", [(0.85, 0.0), (0.82, 0.12), (0.65, 0.2), (-0.85, 0.2), (-0.9, 0.17),
                                        (-0.9, 0.0)], 20, coll, paint if k == 0 else dark, "X")
            pod.location = (-0.15, side * yy, 2.15)
            P(pod)
            P(box(f"{name}_Pylon", (0.4, 0.06, 0.22), (-0.15, side * yy, 2.4), coll, 0.01, dark))
        # door gun (minigun) poking out the cabin window
        mg = empty(f"{name}_DoorGun", (1.0, side * 1.28, 1.95), coll)
        P(mg)
        parent(cylinder(f"{name}_MGBody", 0.07, 0.45, (0, 0, 0), (0, math.pi / 2, 0), 16, coll, dark), mg)
        for b in range(6):
            a = b * math.pi / 3
            parent(cylinder(f"{name}_MGBarrel", 0.012, 0.6, (0.5, 0.04 * math.cos(a), 0.04 * math.sin(a)),
                            (0, math.pi / 2, 0), 6, coll, steel), mg)
        mg.rotation_euler = (0, math.radians(8), side * math.radians(35))

    # ------------------------------------------------ landing gear
    for side in (1, -1):
        wh = lathe(f"{name}_Wheel", [(-0.12, 0.0), (-0.12, 0.25), (-0.1, 0.36), (0.1, 0.36), (0.12, 0.25),
                                     (0.12, 0.0)], 24, coll, rubber, "Y")
        wh.location = (2.4, side * 1.45, 0.36)
        P(wh)
        P(cylinder(f"{name}_Strut", 0.06, 0.95, (2.25, side * 1.25, 0.7), (side * math.radians(-35), math.radians(-10), 0),
                   12, coll, steel))
        P(cylinder(f"{name}_Drag", 0.05, 1.0, (2.0, side * 1.3, 0.55), (0, math.radians(70), 0), 10, coll, dark))
    tw = lathe(f"{name}_TailWheel", [(-0.07, 0.0), (-0.07, 0.15), (-0.06, 0.2), (0.06, 0.2), (0.07, 0.15), (0.07, 0.0)],
               16, coll, rubber, "Y")
    tw.location = (-8.6, 0, 0.2)
    P(tw)
    P(cylinder(f"{name}_TWStrut", 0.05, 1.9, (-8.6, 0, 1.15), coll=coll, mat=steel))

    # ------------------------------------------------ main rotor
    mast = empty(f"{name}_Rotor", (0.25, 0, 3.4), coll)
    P(mast)
    parent(cylinder(f"{name}_Mast", 0.14, 0.55, (0, 0, 0.25), coll=coll, mat=dark), mast)
    spin = empty(f"{name}_RotorSpin", (0, 0, 0.52), coll)
    parent(spin, mast)
    parent(cylinder(f"{name}_Hub", 0.42, 0.18, (0, 0, 0), coll=coll, mat=dark, bev=0.02), spin)
    parent(cylinder(f"{name}_HubCap", 0.15, 0.25, (0, 0, 0.18), coll=coll, mat=steel), spin)
    import mathutils
    for i in range(4):
        a = i * math.pi / 2
        # blade: airfoil-ish flattened loft with swept tip
        bsecs = []
        for r in [0.35, 0.8, 1.2, 7.4, 7.9, 8.05]:
            ch = 0.12 if r < 0.8 else (0.53 if r < 7.5 else (0.38 if r < 8 else 0.2))
            th = 0.09 if r < 0.8 else 0.05
            droop = -0.012 * r
            sweep = 0.0 if r < 7.4 else -0.15 * (r - 7.4)
            ring = []
            for k in range(12):
                t = 2 * math.pi * k / 12
                ring.append((sweep + ch / 2 * math.cos(t), r, droop + th / 2 * math.sin(t) * (1 - 0.3 * math.cos(t))))
            bsecs.append(ring)
        bl = loft(f"{name}_Blade", bsecs, coll, mat=dark)
        bl.rotation_euler = (0, 0, a)
        parent(bl, spin)
        g = box(f"{name}_Grip", (0.25, 0.6, 0.14), (-0.55 * math.sin(a), 0.55 * math.cos(a), 0), coll, 0.02, steel)
        g.rotation_euler = (0, 0, a)
        parent(g, spin)

    root["rotor"] = spin.name
    root["tail_rotor"] = trs.name
    return root


def animate_rotors(root, f0, f1, deg_per_frame=33.0):
    """Main rotor spin; tail rotor faster. 33 deg/frame keeps 4 blades readable."""
    spin = bpy.data.objects[root["rotor"]]
    tr = bpy.data.objects[root["tail_rotor"]]
    n = f1 - f0
    spin.rotation_euler = (0, 0, 0)
    spin.keyframe_insert("rotation_euler", frame=f0)
    spin.rotation_euler = (0, 0, -math.radians(deg_per_frame * n))
    spin.keyframe_insert("rotation_euler", frame=f1)
    tr.rotation_euler = (0, 0, 0)
    tr.keyframe_insert("rotation_euler", frame=f0)
    tr.rotation_euler = (0, math.radians(deg_per_frame * 2.3 * n), 0)
    tr.keyframe_insert("rotation_euler", frame=f1)
    set_interp(spin, "LINEAR")
    set_interp(tr, "LINEAR")
