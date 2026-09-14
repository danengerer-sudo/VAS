#!/usr/bin/env python3
"""Generate a low-poly helicopter GLB.

Reference aircraft: Robinson R22 (light two-seat piston helicopter, round
bubble cabin). Real dimensions used as the basis for this model:

    fuselage length        6.30 m
    main rotor diameter    7.67 m
    tail rotor diameter    1.07 m
    overall height         2.72 m
    cabin width            0.91 m
    skid track             1.90 m

The fuselage is ONE lofted surface -- bubble, tailcone and fin are stations of
a single sweep, so there are no seams where parts butt together. Everything
else (skids, struts, blades, mast) is a swept tube or a lofted slab built by
the same stitching routine, which keeps the winding rule in exactly one place.

Model conventions:
    +Y up, nose points toward -Z, origin on the ground between the skids.
    Flat shaded (per-face normals), no UVs, four materials.
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
SKID_TRACK = 1.90

NOSE_Z = -1.30
TAIL_Z = NOSE_Z + FUSELAGE_LEN          # +5.00, fin trailing edge

MAST_Z = 0.22
HUB_Y = 2.62                            # top of the rotor head == OVERALL_H
TAIL_HUB = (-0.25, 1.44, 4.25)

PAINT, GLASS, METAL, ACCENT = 0, 1, 2, 3

X_AXIS, Y_AXIS, Z_AXIS = (1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)


# --------------------------------------------------------------------------
# vector helpers
# --------------------------------------------------------------------------

def add(a, b):
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def mul(a, s):
    return (a[0] * s, a[1] * s, a[2] * s)


def dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def cross(a, b):
    return (a[1] * b[2] - a[2] * b[1],
            a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0])


def norm(a):
    ln = math.sqrt(dot(a, a))
    return (a[0] / ln, a[1] / ln, a[2] / ln)


def mid(*pts):
    n = len(pts)
    return tuple(sum(p[i] for p in pts) / n for i in range(3))


def lerp(a, b, t):
    return a + (b - a) * t


# --------------------------------------------------------------------------
# flat-shaded mesh builder: one vertex per face corner, faces wound CCW
# --------------------------------------------------------------------------

class Builder:
    def __init__(self):
        self.groups = {}

    def _g(self, mat):
        return self.groups.setdefault(mat, {"pos": [], "nrm": [], "idx": []})

    def tri(self, a, b, c, mat):
        n = cross(sub(b, a), sub(c, a))
        ln = math.sqrt(dot(n, n))
        if ln < 1e-12:
            return
        n = (n[0] / ln, n[1] / ln, n[2] / ln)
        g = self._g(mat)
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

    def tris(self):
        return sum(len(g["idx"]) // 3 for g in self.groups.values())


# --------------------------------------------------------------------------
# the one winding rule: rings are built in a (u, v) frame with
# cross(u, v) == -sweep_direction, then stitched front-to-back.
# --------------------------------------------------------------------------

def frame(tangent, up=Y_AXIS):
    """Orthonormal (u, v) across `tangent`, with cross(u, v) == -tangent."""
    t = norm(tangent)
    ref = up if abs(dot(t, up)) < 0.95 else Z_AXIS
    u = norm(sub(ref, mul(t, dot(ref, t))))
    return u, cross(u, t)


def ring(center, u, v, coords):
    """coords: (u_amount, v_amount) pairs walking the section anticlockwise."""
    return [add(center, add(mul(u, a), mul(v, b))) for (a, b) in coords]


def oval(ru_pos, ru_neg, rv, n, fullness=1.0):
    """n points round a section; ru_pos/ru_neg allow a different top and bottom."""
    out = []
    for i in range(n):
        t = 2.0 * math.pi * i / n
        cu, sv = math.cos(t), math.sin(t)
        a = (ru_pos if cu >= 0 else ru_neg) * math.copysign(abs(cu) ** fullness, cu)
        b = rv * math.copysign(abs(sv) ** fullness, sv)
        out.append((a, b))
    return out


def rect(half_u, half_v):
    return [(half_u, half_v), (-half_u, half_v),
            (-half_u, -half_v), (half_u, -half_v)]


def stitch(b, rings, mat_for, cap_start=True, cap_end=True):
    """rings: list of equal-length point loops, ordered along the sweep."""
    n = len(rings[0])
    for k in range(len(rings) - 1):
        a, c = rings[k], rings[k + 1]
        for i in range(n):
            j = (i + 1) % n
            b.quad(a[i], c[i], c[j], a[j], mat_for(k, i))
    if cap_start:
        ctr = mid(*rings[0])
        for i in range(n):
            b.tri(ctr, rings[0][i], rings[0][(i + 1) % n], mat_for(-1, i))
    if cap_end:
        ctr = mid(*rings[-1])
        for i in range(n):
            b.tri(ctr, rings[-1][(i + 1) % n], rings[-1][i], mat_for(len(rings), i))


def extrude(b, axis, centers, coords_list, mat, cap_start=True, cap_end=True,
            mat_for=None, up=Y_AXIS):
    """Loft `coords_list` sections along a straight `axis` through `centers`."""
    u, v = frame(axis, up)
    rings = [ring(c, u, v, cd) for c, cd in zip(centers, coords_list)]
    stitch(b, rings, mat_for or (lambda k, i: mat), cap_start, cap_end)


def sweep(b, path, radii, sides, mat, roll=0.0, cap=True):
    """Round tube following a polyline, frames parallel-transported."""
    tangents = []
    for k in range(len(path)):
        if k == 0:
            tangents.append(norm(sub(path[1], path[0])))
        elif k == len(path) - 1:
            tangents.append(norm(sub(path[-1], path[-2])))
        else:
            tangents.append(norm(sub(path[k + 1], path[k - 1])))

    rings, u = [], None
    for k, (p, t) in enumerate(zip(path, tangents)):
        if u is None:
            u, _ = frame(t)
        else:
            u = norm(sub(u, mul(t, dot(u, t))))   # parallel transport
        v = cross(u, t)
        r = radii[k]
        coords = [(r * math.cos(2 * math.pi * (i + roll) / sides),
                   r * math.sin(2 * math.pi * (i + roll) / sides))
                  for i in range(sides)]
        rings.append(ring(p, u, v, coords))
    stitch(b, rings, lambda k, i: mat, cap, cap)


# --------------------------------------------------------------------------
# fuselage: one loft, nose -> bubble -> tailcone -> fin
# (z, half_width, height_above_axis, height_below_axis, axis_height)
# --------------------------------------------------------------------------

SECTIONS = [
    (-1.300, 0.150, 0.150, 0.145, 0.985),   # blunt rounded nose
    (-1.190, 0.310, 0.300, 0.290, 1.005),
    (-1.010, 0.440, 0.440, 0.410, 1.030),
    (-0.760, 0.535, 0.555, 0.510, 1.060),
    (-0.420, 0.580, 0.640, 0.565, 1.090),
    (-0.050, 0.590, 0.670, 0.585, 1.100),   # widest and tallest: the seats
    ( 0.300, 0.555, 0.645, 0.545, 1.130),
    ( 0.580, 0.495, 0.575, 0.475, 1.165),
    ( 0.790, 0.435, 0.495, 0.395, 1.245),   # rear of the pod
    ( 0.890, 0.235, 0.275, 0.215, 1.335),   # hard shoulder: pod ends, boom starts
    ( 1.070, 0.172, 0.188, 0.162, 1.360),
    ( 1.900, 0.146, 0.156, 0.136, 1.385),   # slim near-constant tailcone
    ( 2.800, 0.130, 0.140, 0.122, 1.405),
    ( 3.650, 0.117, 0.127, 0.109, 1.425),
    ( 4.350, 0.107, 0.117, 0.101, 1.440),
    ( 4.700, 0.095, 0.105, 0.091, 1.450),   # cone end; the fin carries on aft
]

FUSE_N = 10
LOWER_QUADS = {3, 4, 5, 6}      # lower half of the section
WINDSCREEN_QUADS = {1, 2, 7, 8}
DOOR_QUADS = {2, 7}


def fuselage_material(k, i):
    if k < 0:
        return GLASS                        # nose cap
    if k >= len(SECTIONS):
        return PAINT                        # tailcone end cap
    z = SECTIONS[k][0]
    if z < -0.30 and i in WINDSCREEN_QUADS:
        return GLASS                        # wraparound windscreen
    if z < 0.25 and i in DOOR_QUADS:
        return GLASS                        # door windows
    if z < 1.00 and i in LOWER_QUADS:
        return ACCENT                       # white lower half, pod only
    return PAINT


def section_at(z):
    """Interpolate the loft profile, for mounting things onto the body."""
    for k in range(len(SECTIONS) - 1):
        z0, z1 = SECTIONS[k][0], SECTIONS[k + 1][0]
        if z0 <= z <= z1:
            t = (z - z0) / (z1 - z0)
            return tuple(lerp(SECTIONS[k][j], SECTIONS[k + 1][j], t)
                         for j in range(1, 5))
    raise ValueError(z)


def build_fuselage(b):
    u, v = frame(Z_AXIS)
    rings = [ring((0.0, cy, z), u, v, oval(ht, hb, w, FUSE_N, 0.9))
             for (z, w, ht, hb, cy) in SECTIONS]
    stitch(b, rings, fuselage_material)


# --------------------------------------------------------------------------
# the rest of the airframe
# --------------------------------------------------------------------------

def build_body():
    b = Builder()
    build_fuselage(b)

    # main rotor mast, rising out of the transmission deck
    extrude(b, Y_AXIS,
            [(0.0, 1.52, MAST_Z), (0.0, 1.92, MAST_Z), (0.0, HUB_Y - 0.10, MAST_Z)],
            [oval(0.175, 0.175, 0.150, 6), oval(0.105, 0.105, 0.100, 6),
             oval(0.078, 0.078, 0.078, 6)],
            METAL, cap_start=False)

    # horizontal stabiliser: tapered slab on the tailcone
    w, ht, hb, cy = section_at(2.80)
    extrude(b, X_AXIS,
            [(-0.62, cy - 0.05, 2.80), (0.0, cy - 0.02, 2.80), (0.62, cy - 0.05, 2.80)],
            [rect(0.022, 0.110), rect(0.036, 0.165), rect(0.022, 0.110)],
            PAINT)

    # vertical fin: swept tapered plate, root buried in the tailcone.
    # Extruding along +Y gives (u, v) = (Z, -X), so rect() is (half chord, half thickness).
    extrude(b, Y_AXIS,
            [(0.0, 1.300, 4.350), (0.0, 1.760, 4.500), (0.0, 2.200, 4.680)],
            [rect(0.500, 0.048), rect(0.420, 0.042), rect(0.320, 0.030)],
            PAINT)

    # ventral fin / tail skid under the cone
    extrude(b, Y_AXIS,
            [(0.0, 1.050, 4.720), (0.0, 1.380, 4.630)],
            [rect(0.170, 0.030), rect(0.250, 0.042)],
            PAINT)

    # tail rotor gearbox fairing, blended into the left side of the fin
    extrude(b, X_AXIS,
            [(-0.06, TAIL_HUB[1], TAIL_HUB[2]), (TAIL_HUB[0] + 0.02, TAIL_HUB[1], TAIL_HUB[2])],
            [oval(0.150, 0.150, 0.130, 6), oval(0.095, 0.095, 0.090, 6)],
            METAL)

    # skids: one continuous tube per side, front toe curving up
    for sx in (-1.0, 1.0):
        x = sx * SKID_TRACK / 2
        path = [(x, 0.290, -1.300), (x, 0.145, -1.120), (x, 0.058, -0.900),
                (x, 0.052, 0.880), (x, 0.075, 1.060), (x, 0.130, 1.190)]
        radii = [0.040, 0.052, 0.058, 0.058, 0.050, 0.038]
        sweep(b, path, radii, 6, METAL, roll=0.5)

        # two arched cross-struts per side, swept so the bend is smooth
        for z in (-0.52, 0.56):
            bw, bht, bhb, bcy = section_at(z)
            belly = bcy - bhb
            path = [(sx * 0.20, belly + 0.10, z), (sx * 0.46, belly + 0.02, z),
                    (sx * 0.72, belly - 0.20, z), (sx * 0.88, belly - 0.38, z),
                    (x, 0.052, z)]
            radii = [0.052, 0.048, 0.044, 0.040, 0.038]
            sweep(b, path, radii, 5, METAL)

    return b


def rotor_blade(b, sign, length, chord_root, chord_tip, thick, cone, mat):
    """Tapered blade along +/-X with a little coning, rooted near the hub."""
    axis = (sign, 0.0, 0.0)
    root, tip = 0.22 * sign, length * sign
    extrude(b, axis,
            [(root, 0.0, 0.0), (tip * 0.55, cone * 0.55, 0.0), (tip, cone, 0.0)],
            [rect(thick / 2, chord_root / 2),
             rect(thick / 2 * 0.85, (chord_root * 0.55 + chord_tip * 0.45) / 2),
             rect(thick / 2 * 0.7, chord_tip / 2)],
            mat)


def build_main_rotor():
    b = Builder()
    # teetering head: a short drum plus the crossbar the blades hang off
    extrude(b, Y_AXIS, [(0.0, -0.10, 0.0), (0.0, 0.08, 0.0)],
            [oval(0.105, 0.105, 0.105, 6), oval(0.088, 0.088, 0.088, 6)], METAL)
    extrude(b, X_AXIS, [(-0.26, 0.0, 0.0), (0.26, 0.0, 0.0)],
            [rect(0.050, 0.058), rect(0.050, 0.058)], METAL)
    r = MAIN_ROTOR_D / 2
    for sign in (1, -1):
        rotor_blade(b, sign, r, 0.28, 0.20, 0.045, 0.14, METAL)
    return b


def build_tail_rotor():
    b = Builder()
    extrude(b, Y_AXIS, [(0.0, -0.055, 0.0), (0.0, 0.055, 0.0)],
            [oval(0.070, 0.070, 0.070, 5), oval(0.070, 0.070, 0.070, 5)], METAL)
    r = TAIL_ROTOR_D / 2
    for sign in (1, -1):
        rotor_blade(b, sign, r, 0.125, 0.095, 0.028, 0.0, METAL)
    return b


# --------------------------------------------------------------------------
# glTF / GLB writing
# --------------------------------------------------------------------------

MATERIALS = [
    {"name": "Paint", "pbrMetallicRoughness": {
        "baseColorFactor": [0.839, 0.263, 0.196, 1.0],
        "metallicFactor": 0.0, "roughnessFactor": 0.55}},
    {"name": "Glass", "pbrMetallicRoughness": {
        "baseColorFactor": [0.094, 0.129, 0.169, 1.0],
        "metallicFactor": 0.10, "roughnessFactor": 0.15}},
    {"name": "Metal", "pbrMetallicRoughness": {
        "baseColorFactor": [0.180, 0.184, 0.204, 1.0],
        "metallicFactor": 0.60, "roughnessFactor": 0.45}},
    {"name": "Accent", "pbrMetallicRoughness": {
        "baseColorFactor": [0.925, 0.918, 0.898, 1.0],
        "metallicFactor": 0.0, "roughnessFactor": 0.60}},
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
        acc = {"bufferView": self._view(data, 34962), "componentType": 5126,
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
        self.accessors.append({"bufferView": self._view(data, 34963),
                               "componentType": 5123, "count": len(idx),
                               "type": "SCALAR"})
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
    out += struct.pack("<III", 0x46546C67, 2,
                       12 + 8 + len(js) + 8 + len(gltf.bin))
    out += struct.pack("<II", len(js), 0x4E4F534A) + js
    out += struct.pack("<II", len(gltf.bin), 0x004E4942) + bytes(gltf.bin)
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_bytes(out)
    return len(out)


def main():
    out = sys.argv[1] if len(sys.argv) > 1 else "assets/models/helicopter_lowpoly.glb"
    g = Gltf()
    body, main_rotor, tail_rotor = build_body(), build_main_rotor(), build_tail_rotor()

    s = math.sin(math.pi / 4)
    nodes = [
        {"name": "Helicopter", "children": [1, 2, 3]},
        {"name": "Body", "mesh": g.mesh("Body", body)},
        {"name": "MainRotor", "mesh": g.mesh("MainRotorHead", main_rotor),
         "translation": [0.0, HUB_Y - 0.08, MAST_Z]},
        {"name": "TailRotor", "mesh": g.mesh("TailRotorHead", tail_rotor),
         "translation": list(TAIL_HUB),
         "rotation": [0.0, 0.0, s, s]},          # local +Y -> world +X
    ]
    size = write_glb(out, g, nodes, [0])
    tris = body.tris() + main_rotor.tris() + tail_rotor.tris()
    print(f"{out}: {tris} triangles, {size} bytes")


if __name__ == "__main__":
    main()
