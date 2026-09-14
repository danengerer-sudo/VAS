#!/usr/bin/env python3
"""
Procedural low-poly sedan -> glTF 2.0 binary (.glb).

Pure standard library: no numpy, no trimesh, no Blender. Run it, get a model.

    python3 tools/make_sedan.py [-o models/sedan_lowpoly.glb] [--color RRGGBB]

Conventions (glTF 2.0): right-handed, +Y up, metres, front of the car faces -Z.
The mesh is flat shaded (every triangle carries its own face normal), which is
what gives the faceted low-poly look under any lighting.

HOW THE SHAPE IS BUILT
----------------------
The car is three volumes, not one blob, because that is what gives a car its
hard character lines:

  lower body   a loft along Z whose cross-section is an 11-point ring. Each
               ring point rides its own "rail" -- a piecewise-linear function
               of Z -- so the floor, sill, side panel, shoulder crease,
               beltline and deck crown are each continuous edges running the
               length of the car. Creases fall out of the ring, not out of
               luck.
  greenhouse   a separate 4-point loft sitting on the deck, buried a few cm
               into it so the windscreen and backlight emerge cleanly.
  wheels       a profile revolved about X, instanced by four nodes.

Wheel arches are real openings, not a tucked-in rocker. Ring points 1/2 (and
their mirrors 8/9) ride a height h(z) that bulges up over each axle following a
circular arc, so the side panel is cut away and the gap is closed by a wheel
well ceiling and an inner fender wall. h(z) collapses back to the sill line
between the arches, which keeps the loft's topology constant everywhere.
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
    return (a[1] * b[2] - a[2] * b[1],
            a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0])


def dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def unit(v):
    m = math.sqrt(dot(v, v))
    return (0.0, 1.0, 0.0) if m < 1e-12 else (v[0] / m, v[1] / m, v[2] / m)


def lerp(a, b, t):
    return (a[0] + (b[0] - a[0]) * t,
            a[1] + (b[1] - a[1]) * t,
            a[2] + (b[2] - a[2]) * t)


def centroid(pts):
    n = float(len(pts))
    return (sum(p[0] for p in pts) / n,
            sum(p[1] for p in pts) / n,
            sum(p[2] for p in pts) / n)


class Rail:
    """A piecewise-linear function of z, clamped outside its range.

    One rail per body feature line, so reshaping the car means editing a
    handful of (z, value) pairs rather than a wall of vertex coordinates."""

    def __init__(self, points):
        self.points = sorted(points)

    def __call__(self, z):
        pts = self.points
        if z <= pts[0][0]:
            return pts[0][1]
        if z >= pts[-1][0]:
            return pts[-1][1]
        for (z0, v0), (z1, v1) in zip(pts, pts[1:]):
            if z0 <= z <= z1:
                return v0 if z1 == z0 else v0 + (v1 - v0) * (z - z0) / (z1 - z0)
        return pts[-1][1]


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

        `ref` is a point on the inside of the surface, which lets every face
        work out its own outward direction instead of relying on me getting
        the vertex order right several hundred times."""
        if dot(unit(cross(sub(b, a), sub(c, a))), sub(centroid([a, b, c, d]), ref)) < 0:
            a, b, c, d = d, c, b, a
        self.tri(material, a, b, c)
        self.tri(material, a, c, d)

    def fan(self, material, loop, ref):
        mid = centroid(loop)
        for i in range(len(loop)):
            a, b = loop[i], loop[(i + 1) % len(loop)]
            if dot(unit(cross(sub(b, mid), sub(a, mid))), sub(mid, ref)) < 0:
                a, b = b, a
            self.tri(material, mid, b, a)

    def tri_count(self):
        return sum(len(v) for v in self.groups.values())


def box(mesh, material, centre, size, faces=None):
    cx, cy, cz = centre
    hx, hy, hz = size[0] * 0.5, size[1] * 0.5, size[2] * 0.5

    def v(sx, sy, sz):
        return (cx + sx * hx, cy + sy * hy, cz + sz * hz)

    sides = {
        "-x": (v(-1, -1, -1), v(-1, -1, 1), v(-1, 1, 1), v(-1, 1, -1)),
        "+x": (v(1, -1, -1), v(1, -1, 1), v(1, 1, 1), v(1, 1, -1)),
        "-y": (v(-1, -1, -1), v(1, -1, -1), v(1, -1, 1), v(-1, -1, 1)),
        "+y": (v(-1, 1, -1), v(1, 1, -1), v(1, 1, 1), v(-1, 1, 1)),
        "-z": (v(-1, -1, -1), v(1, -1, -1), v(1, 1, -1), v(-1, 1, -1)),
        "+z": (v(-1, -1, 1), v(1, -1, 1), v(1, 1, 1), v(-1, 1, 1)),
    }
    faces = faces or {}
    for key, q in sides.items():
        mesh.quad(faces.get(key, material), q[0], q[1], q[2], q[3], centre)


def panel(mesh, material, corners, ref, u0, u1, v0, v1, lift):
    """Inset sub-panel of a quad, pushed out along the host face normal.

    Corner order (a, b, c, d): u runs a->b and d->c, v runs a->d and b->c.
    The inset leaves a strip of body colour all the way around, which is what
    turns a flat window into a window with pillars and a frame."""
    a, b, c, d = corners
    n = unit(cross(sub(b, a), sub(c, a)))
    if dot(n, sub(centroid(corners), ref)) < 0:
        n = mul(n, -1.0)

    def p(u, v):
        return lerp(lerp(a, b, u), lerp(d, c, u), v)

    pts = [add(p(*uv), mul(n, lift)) for uv in
           ((u0, v0), (u1, v0), (u1, v1), (u0, v1))]
    mesh.quad(material, pts[0], pts[1], pts[2], pts[3], ref)


# ==========================================================================
# LOWER BODY
# ==========================================================================

NOSE_Z, TAIL_Z = -2.28, 2.28
AXLES = (-1.38, 1.32)          # wheelbase 2.70
ARCH_R, ARCH_CY = 0.42, 0.31   # arch arc: radius and centre height
SILL_FLAT = 0.34               # sill height where there is no arch

# Rails, front (-Z) to back (+Z). Values are half-widths or heights in metres.
FLOOR_W = Rail([(-2.28, 0.58), (-2.05, 0.64), (-1.85, 0.655),
                (1.85, 0.655), (2.05, 0.645), (2.28, 0.60)])
FLOOR_Y = Rail([(-2.28, 0.40), (-2.10, 0.30), (-1.90, 0.235), (-1.75, 0.215),
                (1.75, 0.215), (1.90, 0.24), (2.10, 0.32), (2.28, 0.42)])
SILL_Y = Rail([(-2.28, 0.46), (-2.05, 0.36), (-1.85, 0.34),
               (1.85, 0.34), (2.05, 0.37), (2.28, 0.48)])
# ARCH_W (the sill and arch lip) sits slightly inboard of SIDE_W (the shoulder
# crease), so the flank leans out on the way up and then tucks in above the
# crease. That change of direction is what makes the crease catch light.
ARCH_W = Rail([(-2.28, 0.785), (-2.15, 0.858), (-2.00, 0.882),
               (2.00, 0.882), (2.15, 0.860), (2.28, 0.805)])
# The end tapers are deliberately shallow. Pull them in much harder and the
# plan view turns into a wedge with a beak instead of a car.
SIDE_W = Rail([(-2.28, 0.80), (-2.15, 0.875), (-2.00, 0.90),
               (2.00, 0.90), (2.15, 0.878), (2.28, 0.82)])
CREASE_Y = Rail([(-2.28, 0.66), (-2.05, 0.74), (-1.75, 0.80),
                 (0.60, 0.82), (1.95, 0.84), (2.28, 0.80)])
BELT_W = Rail([(-2.28, 0.72), (-2.16, 0.790), (-2.00, 0.845), (-1.00, 0.862),
               (1.20, 0.862), (2.00, 0.85), (2.15, 0.80), (2.28, 0.74)])
BELT_Y = Rail([(-2.28, 0.865), (-2.08, 0.910), (-1.60, 0.950), (-1.00, 0.975),
               (-0.65, 0.985), (0.85, 0.985), (1.50, 0.980), (2.00, 0.965),
               (2.28, 0.935)])
CROWN = Rail([(-2.28, 0.010), (-1.65, 0.022), (-0.95, 0.018),
              (0.90, 0.012), (1.85, 0.016), (2.28, 0.008)])

# ring index -> material of the edge leaving that index
EDGE_MATERIAL = ["underbody", "underbody", "paint", "paint", "paint",
                 "paint", "paint", "paint", "underbody", "underbody",
                 "underbody"]
CEILING_EDGES = (1, 8)  # wheel-well ceilings: outward is down, not away from the axis


def arch_height(z):
    """Sill line, bulged up into an arc over each axle."""
    h = SILL_Y(z)
    for za in AXLES:
        d = z - za
        if abs(d) < ARCH_R:
            h = max(h, ARCH_CY + math.sqrt(ARCH_R * ARCH_R - d * d))
    return h


def body_ring(z):
    fw, fy = FLOOR_W(z), FLOOR_Y(z)
    h, aw, sw = arch_height(z), ARCH_W(z), SIDE_W(z)
    cy = CREASE_Y(z)
    bw, by = BELT_W(z), BELT_Y(z)
    return [
        (+fw, fy, z),            # 0  floor edge
        (+fw, h, z),             # 1  inner fender wall top
        (+aw, h, z),             # 2  sill / arch lip
        (+sw, cy, z),            # 3  shoulder crease
        (+bw, by, z),            # 4  beltline
        (0.0, by + CROWN(z), z),  # 5  deck crown
        (-bw, by, z),            # 6
        (-sw, cy, z),            # 7
        (-aw, h, z),             # 8
        (-fw, h, z),             # 9
        (-fw, fy, z),            # 10
    ]


def body_z_samples(arch_segments):
    """Section positions: fixed ones for the ends and deck, plus arc samples
    through each arch so the opening is evenly faceted."""
    zs = {-2.28, -2.15, -2.02, -1.86, -0.90, 0.10, 0.85, 1.80, 1.98, 2.15, 2.28}
    theta0 = math.asin((SILL_FLAT - ARCH_CY) / ARCH_R)
    span = math.pi - 2.0 * theta0
    for za in AXLES:
        for i in range(arch_segments + 1):
            th = theta0 + span * i / arch_segments
            zs.add(round(za + ARCH_R * math.cos(th), 5))
    return sorted(zs)


def build_lower_body(mesh, arch_segments):
    zs = body_z_samples(arch_segments)
    rings = [body_ring(z) for z in zs]

    for i in range(len(rings) - 1):
        ri, rj, zm = rings[i], rings[i + 1], (zs[i] + zs[i + 1]) * 0.5
        axis = (0.0, (FLOOR_Y(zm) + BELT_Y(zm)) * 0.5, zm)
        for k in range(11):
            k2 = (k + 1) % 11
            # a wheel-well ceiling sits above the axis, so "away from the axis"
            # would flip it upward; push its reference well overhead instead
            ref = (0.0, 3.0, zm) if k in CEILING_EDGES else axis
            mesh.quad(EDGE_MATERIAL[k], ri[k], ri[k2], rj[k2], rj[k], ref)

    mesh.fan("paint", rings[0], (0.0, 0.62, zs[0] + 1.0))
    mesh.fan("paint", rings[-1], (0.0, 0.62, zs[-1] - 1.0))


# ==========================================================================
# GREENHOUSE
# ==========================================================================

# (z, roof height, roof half-width, base half-width); base height is CABIN_Y0.
# The end sections are deliberately below the deck so the screens emerge from
# it instead of meeting it in a coincident seam.
CABIN_Y0 = 0.90
CABIN = [
    (-1.00, 0.945, 0.80, 0.820),  # windscreen base, buried in the cowl
    (-0.18, 1.462, 0.70, 0.850),  # roof front  -> screen raked 58 deg
    (+0.42, 1.475, 0.70, 0.850),  # B-pillar
    (+0.96, 1.460, 0.69, 0.850),  # roof rear
    (+1.56, 0.945, 0.75, 0.820),  # backlight base, buried in the deck
]
GLASS_LIFT = 0.010


GLASS_SILL_Y = 1.045     # absolute height of the door-glass lower edge
GLASS_ROOF_INSET = 0.045  # painted strip left between glass and roof edge


def cabin_at(z):
    """(roof height, roof half-width, base half-width) of the greenhouse at z."""
    for a, b in zip(CABIN, CABIN[1:]):
        if a[0] <= z <= b[0]:
            t = (z - a[0]) / (b[0] - a[0])
            return tuple(a[i] + (b[i] - a[i]) * t for i in (1, 2, 3))
    return CABIN[0][1:] if z < CABIN[0][0] else CABIN[-1][1:]


def side_point(s, z, y):
    """A point on the greenhouse flank at longitudinal position z, height y."""
    yt, wt, wb = cabin_at(z)
    u = (y - CABIN_Y0) / (yt - CABIN_Y0)
    return (s * (wb + (wt - wb) * u), y, z)


def door_glass(mesh, s, z0, z1):
    """One continuous window from z0 to z1, faceted to follow the flank.

    Insetting a single loft quad would chop the glass off at the roof corners
    and leave an A-pillar half a metre thick; walking the section breaks
    instead lets one window run forward into the raked screen band, which is
    where a real door window goes."""
    breaks = [z0] + [c[0] for c in CABIN if z0 < c[0] < z1] + [z1]
    for za, zb in zip(breaks, breaks[1:]):
        edges = [(side_point(s, z, GLASS_SILL_Y),
                  side_point(s, z, cabin_at(z)[0] - GLASS_ROOF_INSET))
                 for z in (za, zb)]
        (a0, a1), (b0, b1) = edges
        ref = (0.0, 1.15, (za + zb) * 0.5)
        n = unit(cross(sub(a1, a0), sub(b1, a0)))
        if dot(n, sub(centroid([a0, a1, b1, b0]), ref)) < 0:
            n = mul(n, -1.0)
        q = [add(p, mul(n, GLASS_LIFT)) for p in (a0, a1, b1, b0)]
        mesh.quad("glass", q[0], q[1], q[2], q[3], ref)


def cabin_ring(sec):
    z, yt, wt, wb = sec
    return [(+wb, CABIN_Y0, z), (+wt, yt, z), (-wt, yt, z), (-wb, CABIN_Y0, z)]


def build_cabin(mesh):
    rings = [cabin_ring(s) for s in CABIN]

    def axis(i):
        return (0.0, (CABIN_Y0 + CABIN[i][1]) * 0.5,
                (CABIN[i][0] + CABIN[i + 1][0]) * 0.5)

    for i in range(len(rings) - 1):
        ri, rj, ref = rings[i], rings[i + 1], axis(i)
        for k in range(4):
            mesh.quad("paint", ri[k], ri[(k + 1) % 4], rj[(k + 1) % 4], rj[k], ref)
    mesh.quad("paint", *rings[0], ref=(0.0, 1.1, CABIN[0][0] + 1.0))
    mesh.quad("paint", *rings[-1], ref=(0.0, 1.1, CABIN[-1][0] - 1.0))

    def roof_quad(i):
        (zi, yi, wi, _), (zj, yj, wj, _) = CABIN[i], CABIN[i + 1]
        return ((+wi, yi, zi), (-wi, yi, zi), (-wj, yj, zj), (+wj, yj, zj))

    # windscreen and backlight: u across the car, v along Z. v starts late at
    # the buried end so the glass begins exactly where the body lets it show.
    panel(mesh, "glass", roof_quad(0), axis(0), 0.07, 0.93, 0.14, 0.93, GLASS_LIFT)
    panel(mesh, "glass", roof_quad(3), axis(3), 0.07, 0.93, 0.07, 0.86, GLASS_LIFT)
    # door glass; the gap between the two runs is the B-pillar, and what is
    # left ahead of and behind them is the A- and C-pillar
    for s in (+1, -1):
        door_glass(mesh, s, -0.62, 0.38)
        door_glass(mesh, s, 0.46, 1.32)


# ==========================================================================
# LAMPS, GRILLE, BUMPER DETAIL, MIRRORS
# ==========================================================================


def face_quad(mesh, material, z, out, x0, y0, x1, y1, lift=0.008):
    zz = z + out * lift
    ref = (0.0, (y0 + y1) * 0.5, z - out)
    mesh.quad(material, (x0, y0, zz), (x1, y0, zz), (x1, y1, zz), (x0, y1, zz), ref)


def build_details(mesh):
    # Lamps are shallow boxes standing 15 mm proud rather than flat decals, so
    # they catch their own highlight and cast a silhouette. The box sides are
    # dark, which reads as a bezel.
    for s in (+1, -1):
        box(mesh, "trim", (s * 0.505, 0.69, NOSE_Z + 0.010), (0.39, 0.14, 0.05),
            faces={"-z": "headlight"})
        box(mesh, "trim", (s * 0.500, 0.805, TAIL_Z - 0.010), (0.40, 0.13, 0.05),
            faces={"+z": "taillight"})

    box(mesh, "trim", (0.0, 0.69, NOSE_Z + 0.012), (0.60, 0.14, 0.05))   # grille

    # Bumpers are body-coloured volumes standing 40 mm proud, each with a dark
    # rubbing strip. Painting a dark band straight onto the end cap instead
    # just merges with the underbody shadow into one black bar.
    # deep enough to skirt the kicked-up end of the floor pan behind them
    box(mesh, "paint", (0.0, 0.465, NOSE_Z - 0.005), (1.48, 0.17, 0.07))
    box(mesh, "paint", (0.0, 0.480, TAIL_Z + 0.005), (1.52, 0.17, 0.07))
    face_quad(mesh, "trim", NOSE_Z - 0.035, -1, -0.70, 0.435, 0.70, 0.475)
    face_quad(mesh, "trim", TAIL_Z + 0.035, +1, -0.72, 0.450, 0.72, 0.490)

    face_quad(mesh, "plate", TAIL_Z, +1, -0.18, 0.62, 0.18, 0.72)
    box(mesh, "trim", (-0.44, 0.40, TAIL_Z - 0.02), (0.11, 0.07, 0.12))  # exhaust

    for s in (+1, -1):  # door mirrors, on a stalk just ahead of the door glass
        box(mesh, "trim", (s * 0.795, 1.030, -0.72), (0.12, 0.050, 0.050))
        box(mesh, "paint", (s * 0.895, 1.062, -0.72), (0.15, 0.090, 0.085))


def build_body(arch_segments):
    mesh = Mesh("Body")
    build_lower_body(mesh, arch_segments)
    build_cabin(mesh)
    build_details(mesh)
    return mesh


# ==========================================================================
# WHEEL -- a profile revolved about X, built at the origin so four nodes can
# share it. Symmetric enough that no node needs a mirroring negative scale.
# ==========================================================================

WHEEL_X, WHEEL_R = 0.775, 0.355
TYRE_PROFILE = [(-0.103, 0.215), (-0.086, 0.355),
                (0.086, 0.355), (0.103, 0.215)]
RIM_LIP, HUB_R, HUB_X = 0.178, 0.084, 0.050


def build_wheel(segments):
    mesh = Mesh("Wheel")
    origin = (0.0, 0.0, 0.0)

    def pt(i, x, r):
        a = 2.0 * math.pi * i / segments
        return (x, r * math.sin(a), r * math.cos(a))

    for i in range(segments):
        j = (i + 1) % segments
        for (x0, r0), (x1, r1) in zip(TYRE_PROFILE, TYRE_PROFILE[1:]):
            mesh.quad("tire", pt(i, x0, r0), pt(i, x1, r1),
                      pt(j, x1, r1), pt(j, x0, r0), origin)
        # rim lip, then a dish that falls away inboard -- the recess is what
        # keeps the wheel from reading as a printed disc
        mesh.quad("rim", pt(i, 0.103, 0.215), pt(i, 0.103, RIM_LIP),
                  pt(j, 0.103, RIM_LIP), pt(j, 0.103, 0.215), origin)
        mesh.quad("trim", pt(i, 0.103, RIM_LIP), pt(i, HUB_X, HUB_R),
                  pt(j, HUB_X, HUB_R), pt(j, 0.103, RIM_LIP), origin)

    mesh.fan("rim", [pt(i, HUB_X, HUB_R) for i in range(segments)], origin)
    mesh.fan("trim", [pt(i, -0.103, 0.215) for i in range(segments)], origin)
    return mesh


# --------------------------------------------------------------------------
# materials
# --------------------------------------------------------------------------


def materials(paint_rgb):
    return {
        "paint": dict(base=paint_rgb + [1.0], metallic=0.25, roughness=0.34),
        "underbody": dict(base=[0.070, 0.072, 0.080, 1.0], metallic=0.0, roughness=0.95),
        "glass": dict(base=[0.058, 0.079, 0.104, 1.0], metallic=0.30, roughness=0.06),
        "trim": dict(base=[0.055, 0.058, 0.064, 1.0], metallic=0.30, roughness=0.45),
        "tire": dict(base=[0.045, 0.045, 0.050, 1.0], metallic=0.0, roughness=0.93),
        "rim": dict(base=[0.780, 0.800, 0.840, 1.0], metallic=0.95, roughness=0.22),
        "plate": dict(base=[0.780, 0.775, 0.740, 1.0], metallic=0.0, roughness=0.60),
        "headlight": dict(base=[0.900, 0.915, 0.880, 1.0], metallic=0.0,
                          roughness=0.10, emissive=[0.40, 0.40, 0.33]),
        "taillight": dict(base=[0.620, 0.045, 0.050, 1.0], metallic=0.0,
                          roughness=0.16, emissive=[0.42, 0.03, 0.03]),
    }


# --------------------------------------------------------------------------
# glTF / GLB writing
# --------------------------------------------------------------------------


class GLB:
    def __init__(self):
        self.buf = bytearray()
        self.views = []
        self.accessors = []

    def view(self, data, target):
        while len(self.buf) % 4:
            self.buf.append(0)
        off = len(self.buf)
        self.buf.extend(data)
        self.views.append({"buffer": 0, "byteOffset": off,
                           "byteLength": len(data), "target": target})
        return len(self.views) - 1

    def vec3(self, values):
        data = bytearray()
        for v in values:
            data.extend(struct.pack("<fff", *v))
        self.accessors.append({
            "bufferView": self.view(data, 34962),
            "componentType": 5126,
            "count": len(values),
            "type": "VEC3",
            "min": [min(v[i] for v in values) for i in range(3)],
            "max": [max(v[i] for v in values) for i in range(3)],
        })
        return len(self.accessors) - 1

    def indices(self, values):
        big = max(values) > 65535
        fmt, ctype = ("<I", 5125) if big else ("<H", 5123)
        data = bytearray()
        for v in values:
            data.extend(struct.pack(fmt, v))
        self.accessors.append({
            "bufferView": self.view(data, 34963),
            "componentType": ctype,
            "count": len(values),
            "type": "SCALAR",
        })
        return len(self.accessors) - 1


def primitives(glb, mesh, mat_index):
    """Weld each material group into one indexed primitive. Position AND
    normal form the weld key, so shared corners stay split and hard-edged."""
    out = []
    for name in sorted(mesh.groups):
        lookup, positions, normals, idx = {}, [], [], []
        for a, b, c, n in mesh.groups[name]:
            for p in (a, b, c):
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
            "attributes": {"POSITION": glb.vec3(positions),
                           "NORMAL": glb.vec3(normals)},
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
        entry = {"name": name,
                 "pbrMetallicRoughness": {
                     "baseColorFactor": [round(c, 4) for c in m["base"]],
                     "metallicFactor": m["metallic"],
                     "roughnessFactor": m["roughness"]},
                 "doubleSided": False}
        if "emissive" in m:
            entry["emissiveFactor"] = m["emissive"]
        gltf_materials.append(entry)

    nodes = [{"name": "Sedan", "children": [1, 2, 3, 4, 5]},
             {"name": "Body", "mesh": 0}]
    for name, x, z in (("Wheel_FL", +WHEEL_X, AXLES[0]),
                       ("Wheel_FR", -WHEEL_X, AXLES[0]),
                       ("Wheel_RL", +WHEEL_X, AXLES[1]),
                       ("Wheel_RR", -WHEEL_X, AXLES[1])):
        nodes.append({"name": name, "mesh": 1, "translation": [x, WHEEL_R, z]})

    gltf = {
        "asset": {"version": "2.0", "generator": "VAS make_sedan.py"},
        "scene": 0,
        "scenes": [{"name": "Scene", "nodes": [0]}],
        "nodes": nodes,
        "meshes": [{"name": "Body", "primitives": primitives(glb, body, mat_index)},
                   {"name": "Wheel", "primitives": primitives(glb, wheel, mat_index)}],
        "materials": gltf_materials,
        "accessors": glb.accessors,
        "bufferViews": glb.views,
        "buffers": [{"byteLength": len(glb.buf)}],
    }

    json_chunk = json.dumps(gltf, separators=(",", ":")).encode("utf-8")
    json_chunk += b" " * (-len(json_chunk) % 4)
    bin_chunk = bytes(glb.buf) + b"\x00" * (-len(glb.buf) % 4)

    total = 12 + 8 + len(json_chunk) + 8 + len(bin_chunk)
    with open(path, "wb") as f:
        f.write(struct.pack("<III", 0x46546C67, 2, total))
        f.write(struct.pack("<II", len(json_chunk), 0x4E4F534A))
        f.write(json_chunk)
        f.write(struct.pack("<II", len(bin_chunk), 0x004E4942))
        f.write(bin_chunk)
    return total


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("-o", "--out", default="models/sedan_lowpoly.glb")
    ap.add_argument("--color", default="B4231F",
                    help="body paint as sRGB hex RRGGBB (default B4231F)")
    ap.add_argument("--wheel-segments", type=int, default=12,
                    help="sides per wheel; lower is chunkier and cheaper")
    ap.add_argument("--arch-segments", type=int, default=7,
                    help="facets per wheel arch opening")
    args = ap.parse_args()

    hexcode = args.color.lstrip("#")
    srgb = [int(hexcode[i:i + 2], 16) / 255.0 for i in (0, 2, 4)]
    paint = [round(c ** 2.2, 4) for c in srgb]  # glTF wants linear

    body = build_body(args.arch_segments)
    wheel = build_wheel(args.wheel_segments)

    if os.path.dirname(args.out):
        os.makedirs(os.path.dirname(args.out), exist_ok=True)
    size = write_glb(args.out, body, wheel, materials(paint))

    print("wrote %s" % args.out)
    print("  triangles : %d drawn  (body %d + 4 x %d wheel)"
          % (body.tri_count() + wheel.tri_count() * 4,
             body.tri_count(), wheel.tri_count()))
    print("  materials : %d" % len(set(body.groups) | set(wheel.groups)))
    print("  file size : %.1f KB" % (size / 1024.0))


if __name__ == "__main__":
    main()
