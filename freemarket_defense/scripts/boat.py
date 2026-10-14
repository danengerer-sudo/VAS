"""Procedural fast patrol / assault boat (CB90-like). +X forward, z=0 is the waterline."""
import math
import bpy
from lib import *
from heli import _interp
from tank import _machine_gun


def build_boat(name="Boat", coll=None, livery="TIDEWATER MARITIME", livery_color=(0.0, 0.42, 0.36)):
    coll = coll or bpy.context.scene.collection
    hullp = painted_metal(f"{name}_Hull", (0.075, 0.085, 0.09), (0.06, 0.068, 0.072), rough=0.45,
                          scale=0.35, dirt=0.15)
    deckp = painted_metal(f"{name}_Deck", (0.05, 0.055, 0.055), (0.04, 0.045, 0.045), rough=0.85,
                          scale=1.5, dirt=0.1)
    antifoul = pbr("Antifoul", (0.12, 0.025, 0.02), rough=0.6)
    dark = pbr("BoatDark", (0.02, 0.02, 0.02), rough=0.5, metal=0.5)
    steel = pbr("WornSteel", (0.32, 0.31, 0.29), rough=0.38, metal=1.0)
    rubber = pbr("Rubber", (0.025, 0.025, 0.025), rough=0.85)
    glassm = glass("BridgeGlass", (0.02, 0.035, 0.045))
    decal = pbr(f"{name}_Decal", livery_color, rough=0.5)
    white = pbr("DecalWhite", (0.7, 0.7, 0.66), rough=0.6)
    font = "/usr/share/fonts/opentype/inter/Inter-Bold.otf"

    root = empty(name, coll=coll)

    def P(o, par=None):
        parent(o, par or root)
        return o

    #        x     keel_z chine_y chine_z sheer_y sheer_z
    keys = [(8.0, 1.05, 0.04, 1.35, 0.08, 2.05),
            (7.2, 0.25, 0.62, 0.72, 0.95, 1.95),
            (5.5, -0.35, 1.30, 0.18, 1.62, 1.78),
            (3.0, -0.70, 1.80, -0.15, 2.00, 1.58),
            (0.0, -0.80, 2.00, -0.30, 2.10, 1.45),
            (-4.0, -0.75, 2.00, -0.30, 2.10, 1.38),
            (-8.0, -0.62, 1.92, -0.25, 2.02, 1.32)]
    secs = []
    x = 8.0
    xs = []
    while x > -8.0:
        xs.append(x)
        x -= 0.2 if x > 3 else 0.5
    xs.append(-8.0)
    for x in xs:
        kz, cy, cz, sy, sz = _interp(keys, x)
        ring = []
        # starboard (−y) bottom → side → deck → port side → bottom
        prof = [(0.0, kz), (cy * 0.5, kz + (cz - kz) * 0.42), (cy, cz), (cy + 0.05, cz + 0.06),
                (sy, sz - 0.25), (sy, sz)]
        deck_c = sz + 0.05
        half = [(-y, z) for (y, z) in prof]                    # starboard side, keel up
        top = [(-sy * 0.5, deck_c - 0.01), (0.0, deck_c), (sy * 0.5, deck_c - 0.01)]
        port = [(y, z) for (y, z) in reversed(prof)][:-1]       # port side, sheer down (skip keel)
        for (y, z) in half + top + port:
            ring.append((x, y, z))
        secs.append(ring)
    hull = loft(f"{name}_HullMesh", secs, coll, smooth=False)
    add_mat(hull, hullp)
    add_mat(hull, deckp)
    add_mat(hull, antifoul)
    add_mat(hull, decal)
    for p in hull.data.polygons:
        c, nz = p.center, p.normal.z
        if nz > 0.9 and c.z > 1.0:
            p.material_index = 1
        elif c.z < 0.05:
            p.material_index = 2
    bevel(hull, 0.03, 2, 30)
    weighted_normals(hull)
    P(hull)

    # rub rail along the sheer, fenders
    for side in (1, -1):
        for i in range(len(xs) - 1):
            x0, x1 = xs[i], xs[i + 1]
            if x0 > 7.4:
                continue
            _, _, _, sy0, sz0 = _interp(keys, x0)
            _, _, _, sy1, sz1 = _interp(keys, x1)
            a, b = (x0, side * (sy0 + 0.04), sz0 - 0.12), (x1, side * (sy1 + 0.04), sz1 - 0.12)
            mid = [(a[k] + b[k]) / 2 for k in range(3)]
            L = math.dist(a, b)
            r = box(f"{name}_Rail", (L + 0.02, 0.12, 0.16), mid, coll, 0.0, rubber)
            r.rotation_euler = (0, math.atan2(b[2] - a[2], -(b[0] - a[0])) if False else 0,
                                math.atan2(b[1] - a[1], b[0] - a[0]))
            P(r)
        P(text_decal(f"{name}_Lbl", livery, 0.3, white, (1.4, side * 2.115, 0.85),
                     (math.radians(90), math.radians(-4) * side, math.pi if side > 0 else 0), coll, font=font))
        P(text_decal(f"{name}_Num", "TM-07", 0.55, white, (6.1, side * 1.55, 1.35),
                     (math.radians(90), 0, math.pi + math.radians(14) if side > 0 else math.radians(-14)), coll,
                     font=font))
        for k, dx in enumerate((0.0, 0.42)):
            _, _, _, sy, _ = _interp(keys, 4.4 + dx)
            st = box(f"{name}_Stripe", (0.3 if k == 0 else 0.1, 0.01, 1.7), (4.4 + dx, side * (sy + 0.005), 0.75),
                     coll, 0.0, decal)
            st.rotation_euler = (side * math.radians(-6), math.radians(-28), side * math.radians(-12))
            P(st)
        # guard rail stanchions
        for xx in [-7.5, -6.0, -4.5, 2.8, 4.2, 5.6]:
            _, _, _, sy, sz = _interp(keys, xx)
            P(cylinder(f"{name}_Stanchion", 0.022, 0.7, (xx, side * (sy - 0.1), sz + 0.4), coll=coll, mat=steel))
        P(cylinder(f"{name}_RailTop", 0.022, 2.9, (4.2, side * 1.8, 2.02), (0, math.pi / 2, side * math.radians(-6)),
                   coll=coll, mat=steel))
        P(cylinder(f"{name}_RailTopA", 0.022, 3.0, (-6.0, side * 1.98, 1.72), (0, math.pi / 2, 0), coll=coll, mat=steel))

    # ------------------------------------------------ cabin / wheelhouse
    cab = extrude_profile(f"{name}_Cabin", [(-2.8, 1.3), (2.2, 1.3), (2.75, 2.35), (2.15, 3.35), (-2.5, 3.35),
                                            (-2.8, 3.05)], 3.3, "XZ", coll, hullp)
    for v in cab.data.vertices:
        if v.co.z > 2.5:
            v.co.y *= 0.86
    bevel(cab, 0.05, 2)
    P(cab)
    # windscreen panes on the raked front face
    ang = math.atan2(2.75 - 2.15, 3.35 - 2.35)
    for k, yy in enumerate((-0.95, 0.0, 0.95)):
        w = box(f"{name}_Wind", (0.03, 0.88, 0.85), (2.47, yy * 0.97, 2.86), coll, 0.0, glassm)
        w.rotation_euler = (0, -ang, 0)
        P(w)
    for side in (1, -1):
        for xx in (-1.6, -0.3, 1.0):
            w = box(f"{name}_SideWin", (1.05, 0.03, 0.62), (xx, side * 1.48, 2.78), coll, 0.0, glassm)
            w.rotation_euler = (side * math.radians(-11), 0, 0)
            P(w)
    # roof gear: mast, radar, lights, searchlight
    P(box(f"{name}_RoofBox", (1.6, 1.6, 0.25), (-0.8, 0, 3.47), coll, 0.04, hullp))
    P(cylinder(f"{name}_Mast", 0.08, 2.1, (-1.2, 0, 4.5), coll=coll, mat=hullp))
    P(box(f"{name}_Yard", (0.12, 1.6, 0.08), (-1.2, 0, 5.1), coll, 0.01, hullp))
    rad = empty(f"{name}_Radar", (-1.2, 0, 5.6), coll)
    P(rad)
    parent(box(f"{name}_RadarBar", (0.25, 1.7, 0.2), (0, 0, 0.0), coll, 0.04,
               pbr("RadarWhite", (0.55, 0.56, 0.55), rough=0.4)), rad)
    parent(cylinder(f"{name}_RadarPed", 0.12, 0.2, (0, 0, -0.18), coll=coll, mat=dark), rad)
    for yy in (0.7, -0.7):
        P(cylinder(f"{name}_Whip", 0.012, 2.4, (-2.2, yy, 4.6), (0, math.radians(-10), 0), 6, coll, dark))
    P(cylinder(f"{name}_MastLight", 0.06, 0.1, (-1.2, 0, 5.58 + 0.25), coll=coll,
               mat=pbr("MastLight", (1, 1, 1), emission=((1, 1, 0.9), 4.0))))
    sl = cylinder(f"{name}_Search", 0.17, 0.3, (1.3, 0.9, 3.55), (0, math.pi / 2, 0), 20, coll, dark)
    P(sl)
    P(cylinder(f"{name}_SearchLens", 0.15, 0.02, (1.46, 0.9, 3.55), (0, math.pi / 2, 0), 20, coll, glassm))
    # life raft canisters behind cabin
    for yy in (0.7, -0.7):
        P(cylinder(f"{name}_Raft", 0.32, 1.0, (-3.6, yy, 1.85), (0, math.pi / 2, 0), 20, coll,
                   pbr("RaftWhite", (0.6, 0.6, 0.58), rough=0.5), bev=0.03))

    # ------------------------------------------------ weapons
    def gun_mount(x, z, scale=1.0):
        mount = empty(f"{name}_Mount", (x, 0, z), coll)
        P(mount)
        parent(cylinder(f"{name}_Ped", 0.12, 0.7, (0, 0, 0.35), coll=coll, mat=dark), mount)
        sh = extrude_profile(f"{name}_Shield", [(-0.7, 0), (0.7, 0), (0.6, 0.55), (-0.6, 0.55)], 0.04, "YZ",
                             coll, hullp, loc=(0.35, 0, 0.6))
        parent(sh, mount)
        g = _machine_gun(f"{name}_HMG", coll, dark, steel, scale)
        g.location = (0, 0, 0.88)
        parent(g, mount)
        return mount

    gun_mount(4.5, 1.62, 1.1)
    m2 = gun_mount(-6.4, 1.38, 1.0)
    m2.rotation_euler = (0, 0, math.pi)
    # ammo boxes on deck
    for xx, yy in ((-5.2, 1.2), (-5.4, -1.1), (3.6, 1.1)):
        P(box(f"{name}_Ammo", (0.45, 0.25, 0.3), (xx, yy, 1.55), coll, 0.02,
              pbr("AmmoGreen", (0.06, 0.08, 0.04), rough=0.6, metal=0.3)))

    # waterjet housings
    for yy in (0.8, -0.8):
        P(box(f"{name}_Jet", (0.6, 0.65, 0.55), (-8.2, yy, 0.0), coll, 0.06, dark))
    P(box(f"{name}_Transom", (0.05, 3.6, 0.5), (-8.05, 0, 1.1), coll, 0.0, rubber))

    root["radar"] = rad.name
    return root
