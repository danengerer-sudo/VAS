#!/usr/bin/env python3
"""Generate a low-poly helicopter GLB.

Reference aircraft: Robinson R22 (light two-seat piston helicopter, round
bubble cabin). Real dimensions used as the basis for this model:

    fuselage length        6.30 m
    main rotor diameter    7.67 m
    tail rotor diameter    1.07 m
    overall height         2.72 m
    cabin width            0.91 m
    cabin height           1.07 m
    skid track             1.90 m

Model conventions:
    +Y up, nose points toward -Z, origin on the ground between the skids.
    Flat shaded (per-face normals), no UVs, three materials.
    MainRotor / TailRotor are separate nodes that both spin about local +Y.

Writes a self-contained binary glTF (.glb) with no external dependencies.
"""

import json
import math
import struct
import sys
from pathlib import Path

# --------------------------------------------------------------------------
# reference dimensions (metres)
# --------------------------------------------------------------------------
FUSELAGE_LEN = 6.30
MAIN_ROTOR_D = 7.67
TAIL_ROTOR_D = 1.07
OVERALL_H = 2.72
CABIN_W = 0.91
SKID_TRACK = 1.90

NOSE_Z = -1.60                      # nose tip
TAIL_Z = NOSE_Z + FUSELAGE_LEN      # +4.70, trailing edge of the fin

PAINT, GLASS, METAL = 0, 1, 2

# --------------------------------------------------------------------------
# tiny mesh builder: flat-shaded, one vertex per face corner
# --------------------------------------------------------------------------


class Builder:
    def __init__(self):
        self.groups = {}  # material -> {"pos": [...], "nrm": [...], "idx": [...]}

    def _g(self, mat):
        return self.groups.setdefault(mat, {"pos": [], "nrm": [], "idx": []})

    def tri(self, a, b, c, mat):
        # authored clockwise for readability; glTF front faces are CCW
        b, c = c, b
        g = self._g(mat)
        n = face_normal(a, b, c)
        if n is None:
            return
        base = len(g["pos"])
        for v in (a, b, c):
            g["pos"].append(v)
            g["nrm"].append(n)
        g["idx"] += [base, base + 1, base + 2]

    def quad(self, a, b, c, d, mat):
        self.tri(a, b, c, mat)
        self.tri(a, c, d, mat)

    def merge(self, other):
        for mat, g in other.groups.items():
            dst = self._g(mat)
            off = len(dst["pos"])
            dst["pos"] += g["pos"]
            dst["nrm"] += g["nrm"]
            dst["idx"] += [i + off for i in g["idx"]]


def sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def cross(a, b):
    return (a[1] * b[2] - a[2] * b[1],
            a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0])


def face_normal(a, b, c):
    n = cross(sub(b, a), sub(c, a))
    ln = math.sqrt(n[0] ** 2 + n[1] ** 2 + n[2] ** 2)
    if ln < 1e-12:
        return None
    return (n[0] / ln, n[1] / ln, n[2] / ln)


# --------------------------------------------------------------------------
# primitives
# --------------------------------------------------------------------------


def ellipsoid(b, center, radii, segs, rings, mat_for):
    """UV ellipsoid, flat shaded. mat_for(point) picks the material per face."""
    cx, cy, cz = center
    rx, ry, rz = radii

    def p(i, j):
        phi = math.pi * j / rings          # 0 = top
        theta = 2.0 * math.pi * i / segs
        return (cx + rx * math.sin(phi) * math.sin(theta),
                cy + ry * math.cos(phi),
                cz + rz * math.sin(phi) * math.cos(theta))

    top = (cx, cy + ry, cz)
    bot = (cx, cy - ry, cz)
    for i in range(segs):
        i2 = (i + 1) % segs
        for j in range(rings):
            if j == 0:
                a, c_, d = top, p(i2, 1), p(i, 1)
                mat = mat_for(mid(a, c_, d))
                b.tri(a, c_, d, mat)
            elif j == rings - 1:
                a, c_, d = p(i, j), p(i2, j), bot
                mat = mat_for(mid(a, c_, d))
                b.tri(a, c_, d, mat)
            else:
                v0, v1, v2, v3 = p(i, j), p(i2, j), p(i2, j + 1), p(i, j + 1)
                mat = mat_for(mid(v0, v1, v2, v3))
                b.quad(v0, v1, v2, v3, mat)


def mid(*pts):
    n = len(pts)
    return (sum(p[0] for p in pts) / n,
            sum(p[1] for p in pts) / n,
            sum(p[2] for p in pts) / n)


# right-handed loop bases: cross(u, v) == sweep axis
TUBE_BASIS = {
    "x": ((0, 1, 0), (0, 0, 1)),
    "y": ((0, 0, 1), (1, 0, 0)),
    "z": ((1, 0, 0), (0, 1, 0)),
}


def tube(b, rings, sides, mat, cap_start=True, cap_end=True, roll=0.5,
         axis="z"):
    """rings: list of (center_xyz, r_u, r_v) swept along +axis."""
    u, v = TUBE_BASIS[axis]
    loops = []
    for (c, ru, rv) in rings:
        loop = []
        for i in range(sides):
            t = 2.0 * math.pi * (i + roll) / sides
            su, cv = math.sin(t) * ru, math.cos(t) * rv
            loop.append(tuple(c[k] + u[k] * su + v[k] * cv for k in range(3)))
        loops.append(loop)

    for k in range(len(loops) - 1):
        lo, hi = loops[k], loops[k + 1]
        for i in range(sides):
            i2 = (i + 1) % sides
            b.quad(lo[i], lo[i2], hi[i2], hi[i], mat)

    if cap_start:
        c = mid(*loops[0])
        for i in range(sides):
            b.tri(c, loops[0][(i + 1) % sides], loops[0][i], mat)
    if cap_end:
        c = mid(*loops[-1])
        last = loops[-1]
        for i in range(sides):
            b.tri(c, last[i], last[(i + 1) % sides], mat)


def box(b, center, size, mat, taper=1.0):
    """Axis-aligned box; taper scales the +Y face in X and Z."""
    cx, cy, cz = center
    hx, hy, hz = size[0] / 2, size[1] / 2, size[2] / 2
    tx, tz = hx * taper, hz * taper
    v = [
        (cx - hx, cy - hy, cz - hz), (cx + hx, cy - hy, cz - hz),
        (cx + hx, cy - hy, cz + hz), (cx - hx, cy - hy, cz + hz),
        (cx - tx, cy + hy, cz - tz), (cx + tx, cy + hy, cz - tz),
        (cx + tx, cy + hy, cz + tz), (cx - tx, cy + hy, cz + tz),
    ]
    b.quad(v[0], v[3], v[2], v[1], mat)   # bottom
    b.quad(v[4], v[5], v[6], v[7], mat)   # top
    b.quad(v[0], v[1], v[5], v[4], mat)   # -Z
    b.quad(v[2], v[3], v[7], v[6], mat)   # +Z
    b.quad(v[1], v[2], v[6], v[5], mat)   # +X
    b.quad(v[3], v[0], v[4], v[7], mat)   # -X


def blade(b, length, root_w, tip_w, thick, mat, x_sign=1):
    """Flat tapered blade lying in the XZ plane, rooted at the origin."""
    x0, x1 = 0.18 * x_sign, length * x_sign
    hz0, hz1 = root_w / 2, tip_w / 2
    ht = thick / 2
    v = [
        (x0, -ht, -hz0), (x1, -ht, -hz1), (x1, -ht, hz1), (x0, -ht, hz0),
        (x0, ht, -hz0), (x1, ht, -hz1), (x1, ht, hz1), (x0, ht, hz0),
    ]
    if x_sign > 0:
        b.quad(v[0], v[3], v[2], v[1], mat)
        b.quad(v[4], v[5], v[6], v[7], mat)
        b.quad(v[0], v[1], v[5], v[4], mat)
        b.quad(v[2], v[3], v[7], v[6], mat)
        b.quad(v[1], v[2], v[6], v[5], mat)
        b.quad(v[3], v[0], v[4], v[7], mat)
    else:
        b.quad(v[1], v[2], v[3], v[0], mat)
        b.quad(v[7], v[6], v[5], v[4], mat)
        b.quad(v[4], v[5], v[1], v[0], mat)
        b.quad(v[6], v[7], v[3], v[2], mat)
        b.quad(v[5], v[6], v[2], v[1], mat)
        b.quad(v[7], v[4], v[0], v[3], mat)


# --------------------------------------------------------------------------
# the helicopter
# --------------------------------------------------------------------------

CABIN_C = (0.0, 1.08, -0.62)
CABIN_R = (CABIN_W / 2 + 0.09, 0.64, 1.031)  # faceted nose lands at NOSE_Z
HUB_Y = 2.62
BOOM_Y = 1.34
TAIL_HUB = (-0.30, 1.72, 4.18)


def cabin_material(p):
    """Glazing wraps the nose and lower front of the bubble, paint on top."""
    dy = (p[1] - CABIN_C[1]) / CABIN_R[1]
    dz = (p[2] - CABIN_C[2]) / CABIN_R[2]
    if dz < -0.30 and dy < 0.40:
        return GLASS
    return PAINT


def build_body():
    b = Builder()

    # round bubble cabin -- 8 segments x 5 rings keeps it chunky
    ellipsoid(b, CABIN_C, CABIN_R, segs=8, rings=5, mat_for=cabin_material)

    # tapered tail boom, hexagonal
    tube(b, [
        ((0.0, 1.26, 0.10), 0.24, 0.24),
        ((0.0, 1.32, 1.30), 0.17, 0.17),
        ((0.0, BOOM_Y, 2.90), 0.13, 0.13),
        ((0.0, 1.44, 3.95), 0.11, 0.11),
    ], sides=6, mat=PAINT, cap_start=False, cap_end=True)

    # vertical fin, swept up to carry the tail rotor
    fin = [
        (0.0, 1.40, 3.55), (0.0, 1.40, 4.32),
        (0.0, 2.16, TAIL_Z), (0.0, 2.16, 4.34),
    ]
    fin_t = 0.07
    v_out = [(x + fin_t / 2, y, z) for (x, y, z) in fin]
    v_in = [(x - fin_t / 2, y, z) for (x, y, z) in fin]
    b.quad(v_out[0], v_out[1], v_out[2], v_out[3], PAINT)
    b.quad(v_in[3], v_in[2], v_in[1], v_in[0], PAINT)
    for i in range(4):
        j = (i + 1) % 4
        b.quad(v_in[i], v_in[j], v_out[j], v_out[i], PAINT)

    # lower fin / tail skid guard (overlaps the fin root so it stays attached)
    box(b, (0.0, 1.22, 4.22), (0.07, 0.46, 0.58), PAINT, taper=1.0)

    # horizontal stabiliser
    box(b, (0.0, 1.40, 3.05), (1.30, 0.07, 0.34), PAINT)

    # tail rotor gearbox fairing
    box(b, (-0.16, 1.72, 4.18), (0.30, 0.26, 0.26), METAL)

    # main rotor mast
    tube(b, [
        ((0.0, 1.42, -0.10), 0.10, 0.10),
        ((0.0, HUB_Y - 0.06, -0.10), 0.07, 0.07),
    ], sides=6, mat=METAL, cap_start=False, cap_end=True, axis="y")

    # engine / transmission hump behind the cabin
    box(b, (0.0, 1.22, 0.16), (0.74, 0.52, 0.86), PAINT, taper=0.72)

    # skids: tube fore/aft with the front curled up, plus two arched struts
    for sx in (-1, 1):
        x = sx * SKID_TRACK / 2
        tube(b, [
            ((x, 0.20, -1.42), 0.055, 0.055),
            ((x, 0.06, -1.12), 0.06, 0.06),
            ((x, 0.06, 1.18), 0.06, 0.06),
            ((x, 0.10, 1.34), 0.055, 0.055),
        ], sides=4, mat=METAL, roll=0.125)

        for sz in (-0.58, 0.62):
            b.merge(strut(x, sz))

    return b


def strut(skid_x, z):
    """Arched cross-tube from the belly down to one skid."""
    b = Builder()
    inner_x = 0.30 * (1 if skid_x > 0 else -1)
    pts = [
        (inner_x, 0.62, z),
        (skid_x * 0.62, 0.46, z),
        (skid_x * 0.92, 0.18, z),
        (skid_x, 0.08, z),
    ]
    r = 0.05
    for k in range(len(pts) - 1):
        a, c = pts[k], pts[k + 1]
        quad_link(b, a, c, r, METAL)
    return b


def quad_link(b, a, c, r, mat):
    """Square-section strut between two points (roughly in the XY plane)."""
    d = sub(c, a)
    ln = math.sqrt(d[0] ** 2 + d[1] ** 2 + d[2] ** 2)
    if ln < 1e-9:
        return
    d = (d[0] / ln, d[1] / ln, d[2] / ln)
    up = (0.0, 0.0, 1.0)
    side = cross(d, up)
    sl = math.sqrt(side[0] ** 2 + side[1] ** 2 + side[2] ** 2)
    side = (side[0] / sl, side[1] / sl, side[2] / sl)

    def corners(p):
        out = []
        for (ss, us) in ((1, 1), (-1, 1), (-1, -1), (1, -1)):
            out.append(tuple(p[k] + side[k] * r * ss + up[k] * r * us
                             for k in range(3)))
        return out

    lo, hi = corners(a), corners(c)
    for i in range(4):
        j = (i + 1) % 4
        b.quad(lo[i], lo[j], hi[j], hi[i], mat)
    b.quad(lo[3], lo[2], lo[1], lo[0], mat)
    b.quad(hi[0], hi[1], hi[2], hi[3], mat)


def build_main_rotor():
    """Authored around the hub origin; spins about local +Y."""
    b = Builder()
    tube(b, [
        ((0.0, -0.06, 0.0), 0.11, 0.11),
        ((0.0, 0.10, 0.0), 0.09, 0.09),
    ], sides=6, mat=METAL, axis="y")
    r = MAIN_ROTOR_D / 2
    blade(b, r, 0.30, 0.22, 0.05, METAL, x_sign=1)
    blade(b, r, 0.30, 0.22, 0.05, METAL, x_sign=-1)
    return b


def build_tail_rotor():
    """Authored flat in local XZ so it also spins about local +Y."""
    b = Builder()
    tube(b, [
        ((0.0, -0.05, 0.0), 0.07, 0.07),
        ((0.0, 0.05, 0.0), 0.07, 0.07),
    ], sides=6, mat=METAL, axis="y")
    r = TAIL_ROTOR_D / 2
    blade(b, r, 0.13, 0.10, 0.03, METAL, x_sign=1)
    blade(b, r, 0.13, 0.10, 0.03, METAL, x_sign=-1)
    return b


# --------------------------------------------------------------------------
# glTF / GLB writing
# --------------------------------------------------------------------------

MATERIALS = [
    {
        "name": "Paint",
        "pbrMetallicRoughness": {
            "baseColorFactor": [0.871, 0.259, 0.196, 1.0],
            "metallicFactor": 0.0,
            "roughnessFactor": 0.55,
        },
    },
    {
        "name": "Glass",
        "pbrMetallicRoughness": {
            "baseColorFactor": [0.106, 0.149, 0.196, 1.0],
            "metallicFactor": 0.10,
            "roughnessFactor": 0.15,
        },
    },
    {
        "name": "Metal",
        "pbrMetallicRoughness": {
            "baseColorFactor": [0.157, 0.161, 0.176, 1.0],
            "metallicFactor": 0.60,
            "roughnessFactor": 0.45,
        },
    },
]


class Gltf:
    def __init__(self):
        self.bin = bytearray()
        self.views = []
        self.accessors = []
        self.meshes = []

    def _view(self, data, target):
        while len(self.bin) % 4:
            self.bin.append(0)
        off = len(self.bin)
        self.bin += data
        self.views.append({"buffer": 0, "byteOffset": off,
                           "byteLength": len(data), "target": target})
        return len(self.views) - 1

    def vec3(self, values, with_bounds):
        data = bytearray()
        for v in values:
            data += struct.pack("<3f", *v)
        view = self._view(data, 34962)
        acc = {"bufferView": view, "componentType": 5126,
               "count": len(values), "type": "VEC3"}
        if with_bounds:
            acc["min"] = [min(v[i] for v in values) for i in range(3)]
            acc["max"] = [max(v[i] for v in values) for i in range(3)]
        self.accessors.append(acc)
        return len(self.accessors) - 1

    def indices(self, idx):
        data = bytearray()
        for i in idx:
            data += struct.pack("<H", i)
        view = self._view(data, 34963)
        self.accessors.append({"bufferView": view, "componentType": 5123,
                               "count": len(idx), "type": "SCALAR"})
        return len(self.accessors) - 1

    def mesh(self, name, builder):
        prims = []
        for mat in sorted(builder.groups):
            g = builder.groups[mat]
            if not g["idx"]:
                continue
            assert len(g["pos"]) < 65536, "needs 32-bit indices"
            prims.append({
                "attributes": {"POSITION": self.vec3(g["pos"], True),
                               "NORMAL": self.vec3(g["nrm"], False)},
                "indices": self.indices(g["idx"]),
                "material": mat,
            })
        self.meshes.append({"name": name, "primitives": prims})
        return len(self.meshes) - 1


def write_glb(path, gltf, nodes, scene_nodes):
    while len(gltf.bin) % 4:
        gltf.bin.append(0)

    doc = {
        "asset": {"version": "2.0",
                  "generator": "make_helicopter.py (low-poly R22)"},
        "scene": 0,
        "scenes": [{"name": "Scene", "nodes": scene_nodes}],
        "nodes": nodes,
        "meshes": gltf.meshes,
        "materials": MATERIALS,
        "accessors": gltf.accessors,
        "bufferViews": gltf.views,
        "buffers": [{"byteLength": len(gltf.bin)}],
    }

    js = json.dumps(doc, separators=(",", ":")).encode("utf-8")
    js += b" " * ((4 - len(js) % 4) % 4)

    out = bytearray()
    out += struct.pack("<III", 0x46546C67, 2, 12 + 8 + len(js) + 8 + len(gltf.bin))
    out += struct.pack("<II", len(js), 0x4E4F534A) + js
    out += struct.pack("<II", len(gltf.bin), 0x004E4942) + bytes(gltf.bin)
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_bytes(out)
    return len(out)


def main():
    out = sys.argv[1] if len(sys.argv) > 1 else "assets/models/helicopter_lowpoly.glb"

    g = Gltf()
    body = build_body()
    main_rotor = build_main_rotor()
    tail_rotor = build_tail_rotor()

    body_mesh = g.mesh("Body", body)
    main_mesh = g.mesh("MainRotorBlades", main_rotor)
    tail_mesh = g.mesh("TailRotorBlades", tail_rotor)

    s = math.sin(math.pi / 4)
    nodes = [
        {"name": "Helicopter", "children": [1, 2, 3]},
        {"name": "Body", "mesh": body_mesh},
        {"name": "MainRotor", "mesh": main_mesh,
         "translation": [0.0, HUB_Y, -0.10]},
        {"name": "TailRotor", "mesh": tail_mesh,
         "translation": list(TAIL_HUB),
         "rotation": [0.0, 0.0, s, s]},   # local +Y -> world +X
    ]

    size = write_glb(out, g, nodes, [0])

    tris = sum(len(gr["idx"]) // 3
               for m in (body, main_rotor, tail_rotor)
               for gr in m.groups.values())
    verts = sum(len(gr["pos"])
                for m in (body, main_rotor, tail_rotor)
                for gr in m.groups.values())
    print(f"{out}: {tris} triangles, {verts} vertices, {size} bytes")


if __name__ == "__main__":
    main()
