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

PAINT, GLASS, METAL, ACCENT, INTERIOR, SEAT = 0, 1, 2, 3, 4, 5

# Two detail levels off the same geometry. "minimal" keeps every silhouette
# station (the nose, the widest point and the shoulder especially) and drops
# only resolution and bolt-on detail, so the two read identically at distance.
MINIMAL_STATIONS = (0, 2, 4, 5, 7, 8, 9, 11, 13, 15)
LOD = {
    "full": dict(fuse_n=12, stations=None, skid_sides=6, strut_sides=5,
                 coarse_path=False, driveshaft=True, rotor_head=True,
                 interior_scale=0.92),
    # a coarser hull cuts further inside the section, so the interior shell
    # has to shrink with it to stay buried
    "minimal": dict(fuse_n=8, stations=MINIMAL_STATIONS, skid_sides=4,
                    strut_sides=4, coarse_path=True, driveshaft=False,
                    rotor_head=False, interior_scale=0.84),
}
D = LOD["full"]

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
    def __init__(self, accept=None):
        self.groups = {}
        self.accept = accept          # keep only faces whose material passes

    def _g(self, mat):
        return self.groups.setdefault(mat, {"pos": [], "nrm": [], "idx": []})

    def tri(self, a, b, c, mat):
        if mat is None:
            return                    # face suppressed (e.g. open cabin top)
        if self.accept is not None and not self.accept(mat):
            return
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
    """rings: list of equal-length point loops, ordered along the sweep.

    mat_for(station, quad_index, face_centre) picks the material per face, so
    a region like the canopy can be described by where it actually is rather
    than by which vertex indices happen to fall inside it.
    """
    n = len(rings[0])
    for k in range(len(rings) - 1):
        a, c = rings[k], rings[k + 1]
        for i in range(n):
            j = (i + 1) % n
            b.quad(a[i], c[i], c[j], a[j],
                   mat_for(k, i, mid(a[i], c[i], c[j], a[j])))
    if cap_start:
        ctr = mid(*rings[0])
        for i in range(n):
            q, r = rings[0][i], rings[0][(i + 1) % n]
            b.tri(ctr, q, r, mat_for(-1, i, mid(ctr, q, r)))
    if cap_end:
        ctr = mid(*rings[-1])
        for i in range(n):
            q, r = rings[-1][(i + 1) % n], rings[-1][i]
            b.tri(ctr, q, r, mat_for(len(rings), i, mid(ctr, q, r)))


def extrude(b, axis, centers, coords_list, mat, cap_start=True, cap_end=True,
            mat_for=None, up=Y_AXIS):
    """Loft `coords_list` sections along a straight `axis` through `centers`."""
    u, v = frame(axis, up)
    rings = [ring(c, u, v, cd) for c, cd in zip(centers, coords_list)]
    stitch(b, rings, mat_for or (lambda k, i, c: mat), cap_start, cap_end)


def decimate(path, radii):
    """Halve a swept path, always keeping the last point exactly once."""
    idx = list(range(0, len(path), 2))
    if idx[-1] != len(path) - 1:
        idx.append(len(path) - 1)
    return [path[i] for i in idx], [radii[i] for i in idx]


def sweep(b, path, radii, sides, mat, roll=0.0, cap=True):
    """Round tube following a polyline, frames parallel-transported."""
    assert all(dot(sub(path[k + 1], path[k]), sub(path[k + 1], path[k])) > 1e-12
               for k in range(len(path) - 1)), "repeated point in swept path"
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
    stitch(b, rings, lambda k, i, c: mat, cap, cap)


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

# Glazing, in two regions.
#
# Forward of WINDSCREEN_AFT the nose is a BUBBLE: the whole dome is glass, all
# the way round and up over the top, down to the chin. That is the view a pilot
# actually flies on -- forward and down through the nose -- so nothing opaque
# may cross it. Aft of that the doors carry a window band with painted skin
# below, and the roof goes solid from there back.
WINDSCREEN_AFT = -0.10  # where the bubble ends and the doors begin
DOOR_AFT = 0.38         # back of the door glass
CHIN_DROP = 0.28        # bubble glazing stops at cabin floor level, like the
                        # real aircraft's painted lower nose. Below the floor
                        # there is nothing to see, and glazing there just lets
                        # you look straight under the cabin and out the far side.
SILL_DROP = 0.06        # door window sill, and the cabin tub rim
DOOR_HEADER = 0.62      # door glass stops this far up the section
ACCENT_DROP = 0.46      # belly stripe, below the painted lower nose
ACCENT_AFT = 1.00       # ...and stops where the pod does


def skin_material(c):
    """Material for a hull face, from where its centre sits on the body."""
    _, y, z = c
    z = min(max(z, SECTIONS[0][0]), SECTIONS[-1][0])
    w, ht, hb, cy = section_at(z)
    if z < WINDSCREEN_AFT:
        if y > cy - CHIN_DROP:
            return GLASS                    # the whole nose dome
    elif z < DOOR_AFT and cy - SILL_DROP < y < cy + DOOR_HEADER * ht:
        return GLASS                        # door window
    if z < ACCENT_AFT and y < cy - ACCENT_DROP:
        return ACCENT
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


SKIN = 0.050            # fuselage wall thickness
GLASS_INSET = 0.008     # glazing sits this far inside the outer skin
GLASS_T = 0.034         # glazing thickness
POD_END_Z = SECTIONS[9][0]      # 0.890: the wall, and the cabin, stop here


def _loft_indexed(stations):
    """The outer loft as an INDEXED mesh: vertices, then faces as index tuples.

    The flat-shaded Builder duplicates every face corner, which throws away
    edge sharing. Giving the hull real wall thickness needs to know which edges
    lie on the boundary of an opening, so the loft is built indexed first and
    only flattened into the Builder once the solid is complete.
    """
    u, v = frame(Z_AXIS)
    n = D["fuse_n"]
    verts, rings = [], []
    for (z, w, ht, hb, cy) in stations:
        base = len(verts)
        verts.extend(ring((0.0, cy, z), u, v, oval(ht, hb, w, n, 0.9)))
        rings.append(list(range(base, base + n)))
    faces = []
    for k in range(len(rings) - 1):
        a, c = rings[k], rings[k + 1]
        for i in range(n):
            j = (i + 1) % n
            faces.append((a[i], c[i], c[j], a[j]))
    nose = len(verts)
    verts.append(mid(*(verts[i] for i in rings[0])))
    faces += [(nose, rings[0][i], rings[0][(i + 1) % n]) for i in range(n)]
    tail = len(verts)
    verts.append(mid(*(verts[i] for i in rings[-1])))
    faces += [(tail, rings[-1][(i + 1) % n], rings[-1][i]) for i in range(n)]
    return verts, faces, rings, nose


def _vertex_normals(verts, faces):
    acc = [(0.0, 0.0, 0.0)] * len(verts)
    for f in faces:
        nf = cross(sub(verts[f[1]], verts[f[0]]), sub(verts[f[2]], verts[f[0]]))
        ln = math.sqrt(dot(nf, nf))
        if ln < 1e-12:
            continue
        nf = mul(nf, 1.0 / ln)
        for i in f:
            acc[i] = add(acc[i], nf)
    out = []
    for a in acc:
        ln = math.sqrt(dot(a, a))
        out.append(mul(a, 1.0 / ln) if ln > 1e-12 else (0.0, 0.0, 0.0))
    return out


def _poly(b, pts, mat):
    for k in range(1, len(pts) - 1):
        b.tri(pts[0], pts[k], pts[k + 1], mat)


def hull_surfaces():
    """Outer and inner ring sets, for fitting things inside the cabin."""
    stations = (SECTIONS if D["stations"] is None
                else [SECTIONS[i] for i in D["stations"]])
    verts, faces, rings, _ = _loft_indexed(stations)
    nrm = _vertex_normals(verts, faces)
    inner = [sub(p, mul(nv, SKIN)) for p, nv in zip(verts, nrm)]
    outer_r = [(stations[k][0], [verts[i] for i in r]) for k, r in enumerate(rings)]
    inner_r = [(stations[k][0], [inner[i] for i in r]) for k, r in enumerate(rings)]
    return outer_r, inner_r


def build_hull(body, canopy):
    """The fuselage as a watertight solid with a real wall.

    Cutting windows out of a single-surface shell leaves an open edge you can
    see straight through -- a paper-thin skin, which is no use in a game. So
    the hull carries an outer skin, an inner skin offset inward by SKIN, and a
    rim stitched through every opening joining the two. The inner skin doubles
    as the cabin wall, so it is exactly the right shape and cannot intersect
    the body. The glazing is a second closed solid that fills each opening.
    """
    stations = (SECTIONS if D["stations"] is None
                else [SECTIONS[i] for i in D["stations"]])
    verts, faces, rings, nose = _loft_indexed(stations)
    mats = [skin_material(mid(*(verts[i] for i in f))) for f in faces]
    nrm = _vertex_normals(verts, faces)

    inner = [sub(p, mul(nv, SKIN)) for p, nv in zip(verts, nrm)]
    g_out = [sub(p, mul(nv, GLASS_INSET)) for p, nv in zip(verts, nrm)]
    g_in = [sub(p, mul(nv, GLASS_INSET + GLASS_T)) for p, nv in zip(verts, nrm)]

    pod_last = next(k for k, st in enumerate(stations) if st[0] == POD_END_Z)
    pod_v = {nose}
    for r in rings[:pod_last + 1]:
        pod_v.update(r)
    in_pod = [all(i in pod_v for i in f) for f in faces]
    glass = [m == GLASS for m in mats]

    edge = {}
    for fi, f in enumerate(faces):
        for k in range(len(f)):
            a, c = f[k], f[(k + 1) % len(f)]
            edge.setdefault((min(a, c), max(a, c)), []).append(fi)

    def neighbour(fi, a, c):
        other = [g for g in edge[(min(a, c), max(a, c))] if g != fi]
        return other[0] if other else None

    # opaque skin, inside and out
    for fi, f in enumerate(faces):
        if glass[fi]:
            continue
        _poly(body, [verts[i] for i in f], mats[fi])
        if in_pod[fi]:
            _poly(body, [inner[i] for i in reversed(f)], INTERIOR)

    # Bulkhead closing the inner skin where the pod ends. Wound to face into
    # the cabin, the same way the inner skin it closes does: wound the other
    # way it still seals the hole, and leaves a ring of twelve edges that two
    # faces walk the same way round, which is a solid turned inside out along
    # that ring.
    r = rings[pod_last]
    n = len(r)
    ctr = mid(*(inner[i] for i in r))
    for i in range(n):
        body.tri(ctr, inner[r[i]], inner[r[(i + 1) % n]], INTERIOR)

    # window frames: rim from outer skin through to inner skin
    for fi, f in enumerate(faces):
        if glass[fi] or not in_pod[fi]:
            continue
        for k in range(len(f)):
            a, c = f[k], f[(k + 1) % len(f)]
            o = neighbour(fi, a, c)
            if o is not None and glass[o]:
                body.quad(verts[a], inner[a], inner[c], verts[c], PAINT)

    # glazing: its own closed solid, inset so it beds into the frame
    for fi, f in enumerate(faces):
        if not glass[fi]:
            continue
        _poly(canopy, [g_out[i] for i in f], GLASS)
        _poly(canopy, [g_in[i] for i in reversed(f)], GLASS)
        for k in range(len(f)):
            a, c = f[k], f[(k + 1) % len(f)]
            o = neighbour(fi, a, c)
            if o is None or not glass[o]:
                canopy.quad(g_out[a], g_in[a], g_in[c], g_out[c], GLASS)


# --------------------------------------------------------------------------
# the rest of the airframe
# --------------------------------------------------------------------------

def box(b, lo, hi, mat):
    """Axis-aligned box between two opposite corners."""
    cy = (lo[1] + hi[1]) / 2
    cz = (lo[2] + hi[2]) / 2
    extrude(b, X_AXIS, [(lo[0], cy, cz), (hi[0], cy, cz)],
            [rect((hi[1] - lo[1]) / 2, (hi[2] - lo[2]) / 2)] * 2, mat)


def _hull_rings():
    """Inner skin rings -- the cabin wall, which is what furniture must clear."""
    return hull_surfaces()[1]


def _section_polygon(z, rings):
    """The hull's cross-section at z -- a linear blend of the two it lies between."""
    for k in range(len(rings) - 1):
        z0, z1 = rings[k][0], rings[k + 1][0]
        if z0 <= z <= z1:
            t = (z - z0) / (z1 - z0) if z1 > z0 else 0.0
            return [(a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)
                    for a, b in zip(rings[k][1], rings[k + 1][1])]
    return None


def hull_half_width(y, z, rings):
    """How wide the hull is at height y, station z. Zero outside the section."""
    poly = _section_polygon(z, rings)
    if poly is None:
        return 0.0
    xs = []
    n = len(poly)
    for i in range(n):
        x0, y0 = poly[i]
        x1, y1 = poly[(i + 1) % n]
        if (y0 > y) != (y1 > y):
            xs.append(x0 + (x1 - x0) * (y - y0) / (y1 - y0))
    return max(xs) if xs else 0.0


def fit_half_width(y0, y1, z0, z1, margin=0.92):
    """Widest half-width that still fits everywhere in a y/z box.

    Interior parts are sized from this rather than by hand: the cabin is widest
    at its waist and much narrower at floor height, so a number picked off the
    section's maximum puts furniture through the wall.
    """
    rings = _hull_rings()
    zs = [z0 + (z1 - z0) * i / 4.0 for i in range(5)]
    return margin * min(hull_half_width(y, z, rings) for y in (y0, y1) for z in zs)


PILOT_EYE = (0.26, 1.32, 0.22)      # right seat, eye height


def _ray_tri(o, d, a, b, c):
    """Moller-Trumbore. Returns the hit distance along d, or None."""
    e1, e2 = sub(b, a), sub(c, a)
    pv = cross(d, e2)
    det = dot(e1, pv)
    if abs(det) < 1e-12:
        return None
    inv = 1.0 / det
    tv = sub(o, a)
    u = dot(tv, pv) * inv
    if u < 0.0 or u > 1.0:
        return None
    qv = cross(tv, e1)
    v = dot(d, qv) * inv
    if v < 0.0 or u + v > 1.0:
        return None
    t = dot(e2, qv) * inv
    return t if t > 1e-4 else None


def assert_forward_view(hull, canopy):
    """Nothing opaque in the fuselage may stand between pilot and view ahead.

    Cast through the forward cone rather than inspecting face positions: a
    positional test cannot tell a window frame (opaque, and correct) from a
    painted panel across the windscreen (opaque, and wrong).

    `hull` must be the fuselage ALONE. An earlier version of this check took
    the whole body, which let the cabin's inner skin -- part of the fuselage --
    be mistaken for a fitting and absorb every ray, so the check passed even
    with the nose painted solid. Cabin fittings are deliberately excluded: an
    instrument panel in the way is correct, a painted windscreen is not.
    """
    def faces_of(builder):
        out = []
        for g in builder.groups.values():
            pos, idx = g["pos"], g["idx"]
            out += [(pos[idx[k]], pos[idx[k + 1]], pos[idx[k + 2]])
                    for k in range(0, len(idx), 3)]
        return out

    solid, glazing = faces_of(hull), faces_of(canopy)
    blocked = 0
    for az in range(-45, 46, 9):
        for el in range(-15, 16, 6):
            a, e = math.radians(az), math.radians(el)
            d = (math.sin(a) * math.cos(e), math.sin(e), -math.cos(a) * math.cos(e))
            near_solid = min((t for t in (_ray_tri(PILOT_EYE, d, *f) for f in solid)
                              if t is not None), default=1e9)
            near_glass = min((t for t in (_ray_tri(PILOT_EYE, d, *f) for f in glazing)
                              if t is not None), default=1e9)
            blocked += near_solid < near_glass
    assert blocked == 0, (f"{blocked} rays from the pilot's eye hit opaque hull "
                          f"before any glazing: the forward view is blocked")


def assert_watertight(builder, what):
    """Every edge must be walked by exactly two faces, once each way round.

    This is the check that keeps paper-thin surfaces out of the asset: an open
    surface has edges used once, and those are the edges you can see straight
    through in game. Welding is by position because the flat-shaded Builder
    duplicates every face corner.

    Once each way round is the part that matters, and it is the part this used
    to miss. Counting an edge without caring which way each face walked it
    passes a lid put on back to front just as happily as a lid put on
    properly: both faces are there, both use the edge, the count is two. What
    you get is a surface that is closed and inside out in one patch, which
    looks right, weighs right, and is not a solid. A ring of twelve such edges
    sat in this model until a CAD exporter, which cannot be fooled by that,
    refused to write the body out.
    """
    edges = {}
    for g in builder.groups.values():
        pos, idx = g["pos"], g["idx"]
        for k in range(0, len(idx), 3):
            tri = [tuple(round(v, 5) for v in pos[idx[k + j]]) for j in range(3)]
            for j in range(3):
                a, c = tri[j], tri[(j + 1) % 3]
                edges[(a, c)] = edges.get((a, c), 0) + 1
    open_edges = [e for e, n in edges.items() if edges.get((e[1], e[0]), 0) != n]
    assert not open_edges, (f"{what} is not watertight: {len(open_edges)} edge(s) "
                            f"are not walked by two faces once each way, so it "
                            f"is closed but inside out somewhere, e.g. "
                            f"{open_edges[0]}")


def assert_inside_cabin(builder, what):
    """Fitting interior parts by eye is how you get furniture sticking out of
    the fuselage: a box wide enough at the pod's waist is far too wide at floor
    height. Check every vertex against the cabin wall at its own z."""
    rings = _hull_rings()
    for g in builder.groups.values():
        for (x, y, z) in g["pos"]:
            poly = _section_polygon(z, rings)
            assert poly is not None, f"{what}: z={z:.3f} is beyond the cabin"
            hit, n = False, len(poly)
            for i in range(n):
                x0, y0 = poly[i]
                x1, y1 = poly[(i + 1) % n]
                if (y0 > y) != (y1 > y) and x < x0 + (x1 - x0) * (y - y0) / (y1 - y0):
                    hit = not hit
            assert hit, (f"{what}: vertex ({x:+.2f},{y:+.2f},{z:+.2f}) pokes "
                         f"through the cabin wall")


def build_cabin(b):
    """Cabin fittings. The compartment itself is the hull's inner skin, so
    there is no separate tub to keep from intersecting the body."""
    fw = fit_half_width(0.78, 0.84, -0.52, 0.42)
    box(b, (-fw, 0.78, -0.52), (fw, 0.84, 0.42), INTERIOR)       # floor
    cw = fit_half_width(0.84, 0.99, 0.02, 0.42)
    box(b, (-cw, 0.84, 0.02), (cw, 0.99, 0.42), SEAT)            # bench cushion
    sw = fit_half_width(0.97, 1.46, 0.36, 0.52)
    for sx in (-1, 1):                                           # seat backs
        box(b, (sx * 0.045, 0.97, 0.36), (sx * sw, 1.46, 0.52), SEAT)
    # rear bulkhead: without it you see daylight straight out the back of the
    # cabin through the windscreen
    bw = fit_half_width(0.88, 1.50, 0.58, 0.64)
    box(b, (-bw, 0.88, 0.58), (bw, 1.50, 0.64), INTERIOR)
    box(b, (-0.26, 1.02, -0.46), (0.26, 1.34, -0.38), INTERIOR)  # panel
    box(b, (-0.035, 0.84, -0.10), (0.035, 1.16, -0.02), METAL)   # cyclic post
    box(b, (-0.30, 1.16, -0.09), (0.30, 1.22, -0.03), METAL)     # T-bar cyclic


def build_body(b, canopy):
    hull = Builder()
    build_hull(hull, canopy)
    assert_forward_view(hull, canopy)
    b.merge(hull)
    cabin = Builder()
    build_cabin(cabin)
    assert_inside_cabin(cabin, "cabin")
    b.merge(cabin)

    # main rotor mast, rising out of the transmission deck
    extrude(b, Y_AXIS,
            [(0.0, 1.52, MAST_Z), (0.0, 1.92, MAST_Z), (0.0, HUB_Y - 0.10, MAST_Z)],
            [oval(0.175, 0.175, 0.150, 6), oval(0.105, 0.105, 0.100, 6),
             oval(0.078, 0.078, 0.078, 6)],
            METAL)

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

    # tail rotor driveshaft cover, riding the spine of the tailcone.
    # Extruding along +Z gives (u, v) = (Y, X), so rect() is (half height, half width).
    spine_z = (0.95, 1.90, 2.80, 3.70, 4.30)
    spine_w = (0.058, 0.054, 0.050, 0.046, 0.042)
    if D["driveshaft"]:
        extrude(b, Z_AXIS,
                [(0.0, section_at(z)[3] + section_at(z)[1] - 0.030, z) for z in spine_z],
                [rect(0.044, w) for w in spine_w],
                METAL)

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
        if D["coarse_path"]:
            path, radii = decimate(path, radii)
        sweep(b, path, radii, D["skid_sides"], METAL, roll=0.5)

        # two arched cross-struts per side, swept so the bend is smooth
        for z in (-0.52, 0.56):
            bw, bht, bhb, bcy = section_at(z)
            belly = bcy - bhb
            path = [(sx * 0.20, belly + 0.10, z), (sx * 0.46, belly + 0.02, z),
                    (sx * 0.72, belly - 0.20, z), (sx * 0.88, belly - 0.38, z),
                    (x, 0.052, z)]
            radii = [0.062, 0.058, 0.053, 0.048, 0.044]
            if D["coarse_path"]:
                path, radii = decimate(path, radii)
            sweep(b, path, radii, D["strut_sides"], METAL)


def rotor_blade(b, sign, length, chord_root, chord_tip, thick, cone, mat,
                root=0.22, sweep_back=0.0):
    """Blade along +/-X: coned up, tapered in chord and closed with a tip.

    Stations ride outboard at 0 / 55 / 92 / 100 % span; the outer two drift aft
    by `sweep_back` so the tip has a little sweep instead of ending square.
    """
    axis = (sign, 0.0, 0.0)
    tip = length * sign
    spans = (0.0, 0.55, 0.92, 1.0)
    chords = (chord_root,
              chord_root * 0.55 + chord_tip * 0.45,
              chord_tip,
              chord_tip * 0.55)
    thicks = (1.0, 0.88, 0.72, 0.40)
    centers, sections = [], []
    for t, chord, tk in zip(spans, chords, thicks):
        x = root * sign + (tip - root * sign) * t
        centers.append((x, cone * t, sweep_back * max(0.0, (t - 0.5) / 0.5)))
        sections.append(rect(thick / 2 * tk, chord / 2))
    extrude(b, axis, centers, sections, mat)


def build_main_rotor():
    b = Builder()
    # teetering head: a short drum plus the crossbar the blades hang off
    extrude(b, Y_AXIS, [(0.0, -0.10, 0.0), (0.0, 0.08, 0.0)],
            [oval(0.105, 0.105, 0.105, 6), oval(0.088, 0.088, 0.088, 6)], METAL)
    extrude(b, X_AXIS, [(-0.26, 0.0, 0.0), (0.26, 0.0, 0.0)],
            [rect(0.050, 0.058), rect(0.050, 0.058)], METAL)
    # swashplate below the head, and a pitch link up to each blade root
    if D["rotor_head"]:
        extrude(b, Y_AXIS, [(0.0, -0.30, 0.0), (0.0, -0.24, 0.0)],
                [oval(0.150, 0.150, 0.150, 6), oval(0.160, 0.160, 0.160, 6)], METAL)
        for sign in (1, -1):
            extrude(b, Y_AXIS,
                    [(sign * 0.135, -0.27, 0.115), (sign * 0.150, 0.02, 0.085)],
                    [rect(0.024, 0.024), rect(0.024, 0.024)], METAL)
    r = MAIN_ROTOR_D / 2
    for sign in (1, -1):
        rotor_blade(b, sign, r, 0.215, 0.165, 0.042, 0.14, METAL, sweep_back=0.05)
    return b


def build_tail_rotor():
    b = Builder()
    extrude(b, Y_AXIS, [(0.0, -0.055, 0.0), (0.0, 0.055, 0.0)],
            [oval(0.070, 0.070, 0.070, 5), oval(0.070, 0.070, 0.070, 5)], METAL)
    r = TAIL_ROTOR_D / 2
    for sign in (1, -1):
        rotor_blade(b, sign, r, 0.145, 0.115, 0.030, 0.0, METAL, root=0.105)
    return b


# --------------------------------------------------------------------------
# glTF / GLB writing
# --------------------------------------------------------------------------

MATERIALS = [
    {"name": "Paint", "pbrMetallicRoughness": {
        "baseColorFactor": [0.839, 0.263, 0.196, 1.0],
        "metallicFactor": 0.0, "roughnessFactor": 0.55}},
    {"name": "Glass",
     "alphaMode": "BLEND",
     "doubleSided": False,
     "pbrMetallicRoughness": {
        "baseColorFactor": [0.502, 0.624, 0.690, 0.100],
        "metallicFactor": 0.0, "roughnessFactor": 0.06}},
    {"name": "Metal", "pbrMetallicRoughness": {
        "baseColorFactor": [0.180, 0.184, 0.204, 1.0],
        "metallicFactor": 0.60, "roughnessFactor": 0.45}},
    {"name": "Accent", "pbrMetallicRoughness": {
        "baseColorFactor": [0.925, 0.918, 0.898, 1.0],
        "metallicFactor": 0.0, "roughnessFactor": 0.60}},
    {"name": "Interior", "doubleSided": True, "pbrMetallicRoughness": {
        "baseColorFactor": [0.286, 0.298, 0.325, 1.0],
        "metallicFactor": 0.0, "roughnessFactor": 0.85}},
    {"name": "Seat", "pbrMetallicRoughness": {
        "baseColorFactor": [0.478, 0.443, 0.408, 1.0],
        "metallicFactor": 0.0, "roughnessFactor": 0.90}},
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


def build_file(out, lod):
    global D
    D = LOD[lod]
    g = Gltf()
    body, canopy = Builder(), Builder()
    build_body(body, canopy)
    main_rotor, tail_rotor = build_main_rotor(), build_tail_rotor()

    s = math.sin(math.pi / 4)
    nodes = [
        {"name": "Helicopter", "children": [1, 2, 3, 4]},
        {"name": "Body", "mesh": g.mesh("Body", body)},
        {"name": "Canopy", "mesh": g.mesh("Canopy", canopy)},
        {"name": "MainRotor", "mesh": g.mesh("MainRotorHead", main_rotor),
         "translation": [0.0, HUB_Y - 0.08, MAST_Z]},
        {"name": "TailRotor", "mesh": g.mesh("TailRotorHead", tail_rotor),
         "translation": list(TAIL_HUB),
         "rotation": [0.0, 0.0, s, s]},          # local +Y -> world +X
    ]
    for name, bl in (("Body", body), ("Canopy", canopy),
                     ("MainRotor", main_rotor), ("TailRotor", tail_rotor)):
        assert_watertight(bl, name)
    size = write_glb(out, g, nodes, [0])
    tris = body.tris() + canopy.tris() + main_rotor.tris() + tail_rotor.tris()
    print(f"{out}: {lod:8s} {tris:5d} triangles "
          f"({canopy.tris()} glazed), {size / 1024:.1f} KB")


def main():
    out = Path(sys.argv[1] if len(sys.argv) > 1
               else "assets/models/helicopter_lowpoly.glb")
    build_file(out, "full")
    build_file(out.with_name(out.stem + "_min" + out.suffix), "minimal")


if __name__ == "__main__":
    main()
