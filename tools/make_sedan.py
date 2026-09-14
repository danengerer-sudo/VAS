#!/usr/bin/env python3
"""
Procedural low-poly sedan -> glTF 2.0 binary (.glb).

Pure standard library: no numpy, no trimesh, no Blender. Run it, get a model.

    python3 tools/make_sedan.py [-o models/sedan_lowpoly.glb] [--color RRGGBB]

Conventions (glTF 2.0): right-handed, +Y up, metres, front of the car faces -Z.
The mesh is flat shaded (every triangle carries its own face normal), which is
what gives the faceted low-poly look under any lighting.

Scene graph:

    Sedan
      Body        (paint / glass / lights / trim primitives)
      Wheel_FL    translation only, origin at the hub
      Wheel_FR
      Wheel_RL
      Wheel_RR

The four wheels reuse one mesh and each sit in their own node whose origin is
the hub centre, so a game can spin them on X and steer the front pair on Y
without touching the geometry.
"""

import argparse
import json
import math
import os
import struct

# --------------------------------------------------------------------------
# vector helpers
# --------------------------------------------------------------------------


def sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def add(a, b):
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def mul(a, s):
    return (a[0] * s, a[1] * s, a[2] * s)


def cross(a, b):
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def unit(v):
    m = math.sqrt(dot(v, v))
    return (0.0, 1.0, 0.0) if m < 1e-12 else (v[0] / m, v[1] / m, v[2] / m)


def lerp(a, b, t):
    return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t)


def centroid(pts):
    n = float(len(pts))
    return (
        sum(p[0] for p in pts) / n,
        sum(p[1] for p in pts) / n,
        sum(p[2] for p in pts) / n,
    )


# --------------------------------------------------------------------------
# mesh builder: triangle soup grouped by material, flat shaded
# --------------------------------------------------------------------------


class Mesh:
    def __init__(self, name):
        self.name = name
        self.groups = {}  # material name -> list of (a, b, c, normal)

    def tri(self, material, a, b, c):
        n = unit(cross(sub(b, a), sub(c, a)))
        self.groups.setdefault(material, []).append((a, b, c, n))

    def quad(self, material, a, b, c, d, ref):
        """Add a quad, winding it so its normal points away from `ref`.

        `ref` is a point known to lie on the inside of the surface, which lets
        every face work out its own outward direction instead of relying on
        me getting the vertex order right nine hundred times."""
        n = unit(cross(sub(b, a), sub(c, a)))
        if dot(n, sub(centroid([a, b, c, d]), ref)) < 0.0:
            a, b, c, d = d, c, b, a
        self.tri(material, a, b, c)
        self.tri(material, a, c, d)

    def fan(self, material, loop, ref):
        """Triangle fan over a closed loop, oriented away from `ref`."""
        mid = centroid(loop)
        for i in range(len(loop)):
            a, b = loop[i], loop[(i + 1) % len(loop)]
            n = unit(cross(sub(b, mid), sub(a, mid)))
            if dot(n, sub(mid, ref)) < 0.0:
                a, b = b, a
            self.tri(material, mid, b, a)

    def tri_count(self):
        return sum(len(v) for v in self.groups.values())


# --------------------------------------------------------------------------
# body shape
# --------------------------------------------------------------------------

# Cross sections lofted front (-Z) to back (+Z). Each is a hexagon, mirrored
# across X, described by three heights and three half-widths:
#
#        p2 ------ p3        yt / wt   roof line
#       /            \
#     p1              p4     ym / wm   shoulder, the widest point
#      \              /
#       p0 -------- p5       yb / wb   floor pan, tucked in under the sills
#
# Tucking the floor in well inside the shoulder is what real cars do at the
# rocker panel, and here it doubles as the reason the wheels are visible at
# all without modelling arch cutouts.
#
#         z,     yb,   ym,   yt,    wb,   wm,   wt
SECTIONS = [
    (-2.25, 0.40, 0.64, 0.78, 0.52, 0.70, 0.60),  # 0 nose
    (-2.10, 0.30, 0.66, 0.86, 0.64, 0.84, 0.78),  # 1 bumper
    (-1.70, 0.27, 0.70, 0.93, 0.68, 0.90, 0.85),  # 2 front fender
    (-0.95, 0.26, 0.72, 1.00, 0.70, 0.92, 0.84),  # 3 cowl / base of screen
    (-0.35, 0.26, 0.74, 1.44, 0.70, 0.92, 0.70),  # 4 roof front
    (+0.35, 0.26, 0.74, 1.45, 0.70, 0.92, 0.70),  # 5 roof middle (B-pillar)
    (+0.85, 0.26, 0.73, 1.42, 0.70, 0.92, 0.70),  # 6 roof rear
    (+1.45, 0.27, 0.71, 1.05, 0.70, 0.92, 0.86),  # 7 boot lid
    (+2.05, 0.29, 0.68, 1.00, 0.66, 0.88, 0.83),  # 8 rear fascia
    (+2.25, 0.40, 0.64, 0.92, 0.54, 0.72, 0.66),  # 9 tail
]

WINDSCREEN_BAND = 3  # section 3 -> 4
BACKLIGHT_BAND = 6  # section 6 -> 7
SIDE_GLASS_BANDS = (4, 5)  # front and rear door glass

WHEEL_X = 0.84
WHEEL_R = 0.34
WHEEL_HALF_W = 0.11
AXLE_FRONT_Z = -1.35
AXLE_REAR_Z = +1.35

GLASS_LIFT = 0.012  # how far glass sits proud of the body shell


def ring(sec):
    z, yb, ym, yt, wb, wm, wt = sec
    return [
        (+wb, yb, z),
        (+wm, ym, z),
        (+wt, yt, z),
        (-wt, yt, z),
        (-wm, ym, z),
        (-wb, yb, z),
    ]


def axis_point(sec):
    """A point on the centreline, inside the shell, used to orient faces."""
    z, yb, ym, yt = sec[0], sec[1], sec[2], sec[3]
    return (0.0, (yb + yt) * 0.5, z)


def bilinear(a, b, c, d):
    """Corner order a,b / d,c -> P(u, v), u across a->b, v across a->d."""

    def p(u, v):
        return lerp(lerp(a, b, u), lerp(d, c, u), v)

    return p


def panel(mesh, material, corners, ref, u0, u1, v0, v1, lift):
    """Inset sub-panel of a quad, pushed out along the host face normal.

    The inset is what leaves a strip of body colour all the way around each
    window, so the A/B/C pillars and window frames come for free."""
    a, b, c, d = corners
    n = unit(cross(sub(b, a), sub(c, a)))
    if dot(n, sub(centroid(corners), ref)) < 0.0:
        n = mul(n, -1.0)
    p = bilinear(a, b, c, d)
    pts = [p(u0, v0), p(u1, v0), p(u1, v1), p(u0, v1)]
    pts = [add(q, mul(n, lift)) for q in pts]
    mesh.quad(material, pts[0], pts[1], pts[2], pts[3], ref)


def build_body():
    mesh = Mesh("Body")
    rings = [ring(s) for s in SECTIONS]

    # ---- lofted shell -----------------------------------------------------
    for i in range(len(rings) - 1):
        ri, rj = rings[i], rings[i + 1]
        ref = lerp(axis_point(SECTIONS[i]), axis_point(SECTIONS[i + 1]), 0.5)
        for k in range(6):
            k2 = (k + 1) % 6
            # edge 5 is the floor pan: keep it dark rather than body colour
            material = "underbody" if k == 5 else "paint"
            mesh.quad(material, ri[k], ri[k2], rj[k2], rj[k], ref)

    # ---- end caps ---------------------------------------------------------
    mesh.fan("paint", rings[0], add(axis_point(SECTIONS[0]), (0.0, 0.0, 1.0)))
    mesh.fan("paint", rings[-1], add(axis_point(SECTIONS[-1]), (0.0, 0.0, -1.0)))

    # ---- glazing ----------------------------------------------------------
    def sec_corners_top(i):
        """Roof-edge quad between section i and i+1 (bonnet / screen / roof)."""
        zi, _, _, yti, _, _, wti = SECTIONS[i]
        zj, _, _, ytj, _, _, wtj = SECTIONS[i + 1]
        return ((+wti, yti, zi), (-wti, yti, zi), (-wtj, ytj, zj), (+wtj, ytj, zj))

    def sec_corners_side(i, s):
        """Shoulder-to-roof quad on side s (+1 left, -1 right)."""
        zi, _, ymi, yti, _, wmi, wti = SECTIONS[i]
        zj, _, ymj, ytj, _, wmj, wtj = SECTIONS[i + 1]
        # a,b along z at the shoulder; d,c along z at the roof => v is height
        return (
            (s * wmi, ymi, zi),
            (s * wmj, ymj, zj),
            (s * wtj, ytj, zj),
            (s * wti, yti, zi),
        )

    band_ref = lambda i: lerp(axis_point(SECTIONS[i]), axis_point(SECTIONS[i + 1]), 0.5)

    panel(mesh, "glass", sec_corners_top(WINDSCREEN_BAND), band_ref(WINDSCREEN_BAND),
          0.08, 0.92, 0.10, 0.94, GLASS_LIFT)
    panel(mesh, "glass", sec_corners_top(BACKLIGHT_BAND), band_ref(BACKLIGHT_BAND),
          0.08, 0.92, 0.06, 0.90, GLASS_LIFT)
    for i in SIDE_GLASS_BANDS:
        for s in (+1, -1):
            panel(mesh, "glass", sec_corners_side(i, s), band_ref(i),
                  0.07, 0.93, 0.52, 0.93, GLASS_LIFT)

    # ---- front and rear detail panels, laid on the flat end caps ----------
    def face_panel(material, z, out, x0, y0, x1, y1, x2, y2, x3, y3):
        zz = z + out * 0.012
        ref = (0.0, (y0 + y2) * 0.5, z - out * 0.5)
        mesh.quad(material, (x0, y0, zz), (x1, y1, zz), (x2, y2, zz), (x3, y3, zz), ref)

    fz, rz = SECTIONS[0][0], SECTIONS[-1][0]

    # grille, then bumpers as trapezoids that follow the caps' chamfered
    # lower edges (keeping every panel just inside the hexagon it sits on)
    face_panel("trim", fz, -1, -0.34, 0.50, 0.34, 0.50, 0.34, 0.64, -0.34, 0.64)
    face_panel("trim", fz, -1, -0.49, 0.405, 0.49, 0.405, 0.555, 0.50, -0.555, 0.50)
    face_panel("trim", rz, +1, -0.53, 0.405, 0.53, 0.405, 0.60, 0.50, -0.60, 0.50)

    for s in (+1, -1):
        face_panel("headlight", fz, -1,
                   s * 0.36, 0.58, s * 0.575, 0.58, s * 0.575, 0.72, s * 0.36, 0.72)
        face_panel("taillight", rz, +1,
                   s * 0.32, 0.66, s * 0.655, 0.66, s * 0.655, 0.80, s * 0.32, 0.80)

    # ---- door mirrors -----------------------------------------------------
    for s in (+1, -1):
        box(mesh, "paint", (s * 0.90, 1.02, -0.30), (0.14, 0.08, 0.07))

    return mesh


def box(mesh, material, centre, size):
    cx, cy, cz = centre
    hx, hy, hz = size[0] * 0.5, size[1] * 0.5, size[2] * 0.5
    xs, ys, zs = (cx - hx, cx + hx), (cy - hy, cy + hy), (cz - hz, cz + hz)
    v = [(x, y, z) for x in xs for y in ys for z in zs]
    # index bits: x<<2 | y<<1 | z
    faces = [
        (0, 1, 3, 2),  # -X
        (4, 6, 7, 5),  # +X
        (0, 4, 5, 1),  # -Y
        (2, 3, 7, 6),  # +Y
        (0, 2, 6, 4),  # -Z
        (1, 5, 7, 3),  # +Z
    ]
    for f in faces:
        mesh.quad(material, v[f[0]], v[f[1]], v[f[2]], v[f[3]], centre)


# --------------------------------------------------------------------------
# wheel: built at the origin, axle along X, so all four nodes can share it
# --------------------------------------------------------------------------


def build_wheel(segments=12):
    mesh = Mesh("Wheel")
    r, hw = WHEEL_R, WHEEL_HALF_W
    rim_r = 0.205
    hub_r = 0.055
    o = (0.0, 0.0, 0.0)

    def rim_pt(i, x, radius):
        a = 2.0 * math.pi * i / segments
        return (x, radius * math.sin(a), radius * math.cos(a))

    for i in range(segments):
        j = (i + 1) % segments
        # tread
        mesh.quad("tire", rim_pt(i, -hw, r), rim_pt(i, hw, r),
                  rim_pt(j, hw, r), rim_pt(j, -hw, r), o)
        # outer sidewall: annulus from the tread down to the rim
        mesh.quad("tire", rim_pt(i, hw, r), rim_pt(i, hw, rim_r),
                  rim_pt(j, hw, rim_r), rim_pt(j, hw, r), o)

    # the inner face is never seen from outside the car, so it gets one flat
    # disc instead of the full rim treatment
    mesh.fan("tire", [rim_pt(i, -hw, r) for i in range(segments)], o)
    mesh.fan("rim", [rim_pt(i, hw + 0.004, rim_r) for i in range(segments)], o)
    mesh.fan("trim", [rim_pt(i, hw + 0.010, hub_r) for i in range(segments)], o)
    return mesh


# --------------------------------------------------------------------------
# materials
# --------------------------------------------------------------------------


def materials(paint_rgb):
    return {
        "paint": dict(base=paint_rgb + [1.0], metallic=0.25, roughness=0.38),
        "underbody": dict(base=[0.055, 0.058, 0.065, 1.0], metallic=0.0, roughness=0.85),
        "glass": dict(base=[0.075, 0.105, 0.135, 1.0], metallic=0.15, roughness=0.09),
        "trim": dict(base=[0.085, 0.088, 0.095, 1.0], metallic=0.2, roughness=0.55),
        "tire": dict(base=[0.052, 0.052, 0.057, 1.0], metallic=0.0, roughness=0.92),
        "rim": dict(base=[0.80, 0.82, 0.86, 1.0], metallic=0.9, roughness=0.24),
        "headlight": dict(base=[0.93, 0.94, 0.90, 1.0], metallic=0.0, roughness=0.12,
                          emissive=[0.42, 0.41, 0.34]),
        "taillight": dict(base=[0.55, 0.05, 0.05, 1.0], metallic=0.0, roughness=0.18,
                          emissive=[0.32, 0.02, 0.02]),
    }


# --------------------------------------------------------------------------
# glTF / GLB writing
# --------------------------------------------------------------------------


class GLB:
    def __init__(self):
        self.buf = bytearray()
        self.views = []
        self.accessors = []

    def _align(self):
        while len(self.buf) % 4:
            self.buf.append(0)

    def view(self, data, target=None):
        self._align()
        off = len(self.buf)
        self.buf.extend(data)
        v = {"buffer": 0, "byteOffset": off, "byteLength": len(data)}
        if target is not None:
            v["target"] = target
        self.views.append(v)
        return len(self.views) - 1

    def vec3(self, values):
        data = bytearray()
        for v in values:
            data.extend(struct.pack("<fff", *v))
        vi = self.view(data, 34962)  # ARRAY_BUFFER
        self.accessors.append({
            "bufferView": vi,
            "componentType": 5126,  # FLOAT
            "count": len(values),
            "type": "VEC3",
            "min": [min(v[i] for v in values) for i in range(3)],
            "max": [max(v[i] for v in values) for i in range(3)],
        })
        return len(self.accessors) - 1

    def indices(self, values):
        big = max(values) > 65535 if values else False
        fmt, ctype = ("<I", 5125) if big else ("<H", 5123)
        data = bytearray()
        for v in values:
            data.extend(struct.pack(fmt, v))
        vi = self.view(data, 34963)  # ELEMENT_ARRAY_BUFFER
        self.accessors.append({
            "bufferView": vi,
            "componentType": ctype,
            "count": len(values),
            "type": "SCALAR",
        })
        return len(self.accessors) - 1


def primitives(glb, mesh, mat_index):
    """Weld each material group into indexed, flat-shaded primitives."""
    out = []
    for name in sorted(mesh.groups):
        tris = mesh.groups[name]
        lookup, positions, normals, idx = {}, [], [], []
        for a, b, c, n in tris:
            for p in (a, b, c):
                # position+normal is the weld key, so faces stay hard-edged
                key = (round(p[0], 6), round(p[1], 6), round(p[2], 6),
                       round(n[0], 5), round(n[1], 5), round(n[2], 5))
                i = lookup.get(key)
                if i is None:
                    i = len(positions)
                    lookup[key] = i
                    positions.append(p)
                    normals.append(n)
                idx.append(i)
        out.append({
            "attributes": {"POSITION": glb.vec3(positions), "NORMAL": glb.vec3(normals)},
            "indices": glb.indices(idx),
            "material": mat_index[name],
            "mode": 4,
        })
    return out


def write_glb(path, body, wheel, mats):
    glb = GLB()

    used = sorted(set(body.groups) | set(wheel.groups))
    mat_index = {name: i for i, name in enumerate(used)}
    gltf_materials = []
    for name in used:
        m = mats[name]
        entry = {
            "name": name,
            "pbrMetallicRoughness": {
                "baseColorFactor": [round(c, 4) for c in m["base"]],
                "metallicFactor": m["metallic"],
                "roughnessFactor": m["roughness"],
            },
            "doubleSided": False,
        }
        if "emissive" in m:
            entry["emissiveFactor"] = m["emissive"]
        gltf_materials.append(entry)

    meshes = [
        {"name": "Body", "primitives": primitives(glb, body, mat_index)},
        {"name": "Wheel", "primitives": primitives(glb, wheel, mat_index)},
    ]

    wheels = [
        ("Wheel_FL", [+WHEEL_X, WHEEL_R, AXLE_FRONT_Z]),
        ("Wheel_FR", [-WHEEL_X, WHEEL_R, AXLE_FRONT_Z]),
        ("Wheel_RL", [+WHEEL_X, WHEEL_R, AXLE_REAR_Z]),
        ("Wheel_RR", [-WHEEL_X, WHEEL_R, AXLE_REAR_Z]),
    ]
    nodes = [{"name": "Sedan", "children": [1, 2, 3, 4, 5]},
             {"name": "Body", "mesh": 0}]
    for name, t in wheels:
        nodes.append({"name": name, "mesh": 1, "translation": t})

    gltf = {
        "asset": {"version": "2.0", "generator": "VAS make_sedan.py"},
        "scene": 0,
        "scenes": [{"name": "Scene", "nodes": [0]}],
        "nodes": nodes,
        "meshes": meshes,
        "materials": gltf_materials,
        "accessors": glb.accessors,
        "bufferViews": glb.views,
        "buffers": [{"byteLength": len(glb.buf)}],
    }

    json_chunk = json.dumps(gltf, separators=(",", ":")).encode("utf-8")
    json_chunk += b" " * (-len(json_chunk) % 4)
    bin_chunk = bytes(glb.buf)
    bin_chunk += b"\x00" * (-len(bin_chunk) % 4)

    total = 12 + 8 + len(json_chunk) + 8 + len(bin_chunk)
    with open(path, "wb") as f:
        f.write(struct.pack("<III", 0x46546C67, 2, total))
        f.write(struct.pack("<II", len(json_chunk), 0x4E4F534A))
        f.write(json_chunk)
        f.write(struct.pack("<II", len(bin_chunk), 0x004E4942))
        f.write(bin_chunk)
    return total


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("-o", "--out", default="models/sedan_lowpoly.glb")
    ap.add_argument("--color", default="B71C1C",
                    help="body paint as hex RRGGBB (default B71C1C)")
    ap.add_argument("--wheel-segments", type=int, default=12,
                    help="sides per wheel; lower is chunkier and cheaper")
    args = ap.parse_args()

    hexcode = args.color.lstrip("#")
    srgb = [int(hexcode[i:i + 2], 16) / 255.0 for i in (0, 2, 4)]
    # glTF baseColorFactor is linear, the hex the user typed is sRGB
    paint = [round(c ** 2.2, 4) for c in srgb]

    body = build_body()
    wheel = build_wheel(args.wheel_segments)

    out = args.out
    if os.path.dirname(out):
        os.makedirs(os.path.dirname(out), exist_ok=True)
    size = write_glb(out, body, wheel, materials(paint))

    tris = body.tri_count() + wheel.tri_count() * 4
    print("wrote %s" % out)
    print("  triangles : %d  (body %d, wheels 4 x %d)"
          % (tris, body.tri_count(), wheel.tri_count()))
    print("  materials : %d" % len(set(body.groups) | set(wheel.groups)))
    print("  file size : %.1f KB" % (size / 1024.0))


if __name__ == "__main__":
    main()
