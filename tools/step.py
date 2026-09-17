#!/usr/bin/env python3
"""STEP out: the part as surfaces, so every other CAD package can open it.

    python3 tools/step.py --selftest
    python3 tools/step.py assembly.glb assembly.step

**Why this is not just another mesh format.** An STL or a GLB is a bag of
triangles. Send one to a machine shop and a bore twenty millimetres across
arrives as sixty four little flat strips: nothing to put a tolerance on,
nothing to pick up as a hole, nothing a CAM package can drive a boring bar
round. STEP is different in kind. It carries surfaces, and the surfaces carry
their own identity: this face is a plane, that face is a cylinder of radius
ten about this axis. That is what the rest of the world means by CAD data.

**How a mesh kernel can honestly write one.** Two steps, and the first one was
already built for another reason.

    The flat faces come back for free. Every flat face of the part arrives
    here already put back together as one polygon with holes in it, because
    the kernel merges coplanar triangles as a matter of course. A polygon with
    holes, on a plane, is exactly what STEP calls an advanced face, so the
    whole top of a plate goes out as one planar face rather than four hundred
    triangles.

    The round faces are recognised. A cylinder leaves a closed ring of flat
    quadrilaterals behind it. This walks those rings, fits a circle to their
    corners, and where the fit is exact and the ring is regular and has enough
    sides to mean it, replaces the ring with one real cylindrical surface and
    replaces the polygons that capped it with real circles. The bore that went
    in as a cylinder comes out as a cylinder.

**Where it stops, said plainly.** Only planes and cylinders are recognised. A
fillet, a sphere, a cone or a swept profile goes out as the flat facets it was
tessellated into: valid STEP, a valid closed solid, openable and printable and
quotable, but faceted. A ring with fewer than twelve sides is left alone on
purpose, because a hexagonal boss is a hexagon and nobody wants it turned into
a circle. So a part built from boxes and cylinders, which is most brackets,
plates, spacers and housings, exports as true CAD. A part with a fillet on it
exports as a faceted solid with true planes and cylinders everywhere else.

**Why the numbers can be trusted.** Because the file is read back and checked,
by a reader that shares no code with the writer, and the check is the volume.
The volume of a closed B-rep can be worked out from the surfaces alone, by the
divergence theorem: every planar face contributes its own area times its
distance from the origin, and every cylindrical face contributes two thirds pi
r squared h, with the sign coming from which way the face is facing. If a
point moved, a loop wound backwards, a face faced the wrong way or a cylinder
came out the wrong radius, that number is wrong. The selftest demands it match
the exact volume worked out by hand: not the mesh's volume, the real one, so a
recognised cylinder has to have recovered the true radius rather than the
tessellated one. On top of that it demands the shell be closed in the way STEP
means it: every edge used by exactly two faces, once each way round.
"""
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import solid as S

SIDES = 12          # fewer sides than this is a polygon, not a rough circle
SCHEMA = "AUTOMOTIVE_DESIGN { 1 0 10303 214 3 1 1 1 }"
UNITS = {"mm": (".MILLI.", 1.0), "cm": (".CENTI.", 10.0), "m": ("$", 1000.0),
         "in": (None, 25.4)}


# --------------------------------------------------------------- the pieces

class Loop:
    """One boundary of one face: its corners in order, or a whole circle.

    A loop that has been recognised as a circle keeps its corners anyway. They
    are what says which way round it goes, and which point the circle should
    start at, and having them means nothing downstream has to special case it.
    """

    __slots__ = ("pts", "circle")

    def __init__(self, pts, circle=None):
        self.pts = list(pts)
        self.circle = circle          # (centre, axis, radius) or None


class Flat:
    """A planar face: one outer loop, then a loop for each hole in it."""

    __slots__ = ("normal", "loops")

    def __init__(self, normal, loops):
        self.normal = normal
        self.loops = loops

    @property
    def bounds(self):
        return [(L, False) for L in self.loops]


class Round:
    """A cylindrical face, and the two circles that cap it.

    Both of its boundaries are loops that belong to the flat faces at either
    end, used here the other way round. That is not a shortcut: an edge in a
    closed solid is used by exactly two faces, once each way, and sharing the
    loop is what makes that true by construction rather than by hope.
    """

    __slots__ = ("centre", "axis", "radius", "height", "same_sense", "ends")

    def __init__(self, centre, axis, radius, height, same_sense, ends):
        self.centre = centre
        self.axis = axis
        self.radius = radius
        self.height = height
        self.same_sense = same_sense
        self.ends = ends

    @property
    def bounds(self):
        return [(L, True) for L in self.ends]


# ------------------------------------------------------------- flat faces

def _newell(pts):
    """The best fit normal of a polygon, which beats any three of its corners.

    Three corners of a face that happens to have a very thin bit on it give a
    normal that is mostly rounding error. Newell's sum weighs every corner, so
    the thin bit cannot shout down the rest of the face.
    """
    nx = ny = nz = 0.0
    n = len(pts)
    for k in range(n):
        x0, y0, z0 = pts[k]
        x1, y1, z1 = pts[(k + 1) % n]
        nx += (y0 - y1) * (z0 + z1)
        ny += (z0 - z1) * (x0 + x1)
        nz += (x0 - x1) * (y0 + y1)
    return S.normalise((nx, ny, nz))


def _sort_loops(loops, n):
    """One plane's loops into faces: which loop is an outline, which is a hole.

    Signed area says which is which, because the loops come out of the kernel
    wound so that an outline goes one way round the normal and a hole goes the
    other. One plane can hold more than one separate face, so a hole belongs to
    the smallest outline that contains it.
    """
    i, j = S._frame(n)
    flat = [[(p[i], p[j]) for p in L] for L in loops]
    areas = [S._area2(f) for f in flat]
    if any(a == 0.0 for a in areas):
        return None
    outer = [k for k, a in enumerate(areas) if a > 0]
    holes = [k for k, a in enumerate(areas) if a < 0]
    if not outer:
        return None
    mine = {k: [] for k in outer}
    for h in holes:
        owner = None
        for k in outer:
            if S._inside_loop(flat[h][0], flat[k]) and (
                    owner is None or areas[k] < areas[owner]):
                owner = k
        if owner is None:
            return None                   # a hole in nothing
        mine[owner].append(h)
    made = []
    for k in outer:
        face = _upright_normal(n, loops[k])
        made.append(Flat(face, [Loop(loops[k])] + [Loop(loops[h])
                                                   for h in mine[k]]))
    return made


def _upright_normal(n, outline):
    """The face's own normal, taken from its outline, if it agrees with the
    plane it was grouped onto. A face whose outline says something different
    is a face whose outline is not to be trusted, so the plane wins."""
    fit = _newell(outline)
    return fit if S.dot(fit, n) > 0.9 else n


def flat_faces(tris, tol=1e-6):
    """Every flat face of a solid, as an outline and its holes.

    This is the same walk the kernel does when it merges coplanar triangles,
    stopped one step earlier: it wants the filled triangles, and STEP wants the
    outline they would have been filled from. A face that will not come apart
    is handed back as its own triangles instead, and its corners are pinned so
    that the faces around it keep every corner it has, which is what stops the
    solid coming apart at that one face.
    """
    groups = S._by_plane(tris, tol)
    outlines = [S._outlines(g, pl[0]) for pl, g in groups]
    faces, loose = [], []
    for _ in range(4):
        pinned = set()
        for k, (_pl, g) in enumerate(groups):
            if outlines[k] is None:
                pinned.update(p for t in g for p in t)
        short = S._straighten(outlines, pinned, tol)
        faces, loose, trouble = [], [], []
        for k, (pl, g) in enumerate(groups):
            if short[k] is None:
                loose += g
                continue
            made = _sort_loops(short[k], pl[0])
            if made is None:
                trouble.append(k)
                continue
            faces += made
        if not trouble:
            break
        for k in trouble:
            outlines[k] = None
    return faces, loose


# --------------------------------------------------------- round faces

def _ekey(a, b):
    a, b = S.snap(a), S.snap(b)
    return (a, b) if a <= b else (b, a)


def _across(k, e, quads, edge_faces):
    """Out of this quad by this edge and into the next one, if there is one.

    Leaving a quad by one edge and coming out of the next by the edge opposite
    is what goes round a cylinder rather than up it, so a walk that started up
    the cylinder runs into the flat end and stops, which is how the wrong pair
    of edges rules itself out.
    """
    pts = quads[k]
    key = _ekey(pts[e], pts[(e + 1) % 4])
    nxt = [q for q in edge_faces.get(key, ()) if q != k]
    if len(nxt) != 1 or nxt[0] not in quads:
        return None, key
    k2 = nxt[0]
    p2 = quads[k2]
    for a in range(4):
        if _ekey(p2[a], p2[(a + 1) % 4]) == key:
            return (k2, (a + 2) % 4), key
    return None, key


def _quad_chain(k0, e0, quads, edge_faces):
    """Every quad joined to this one along the edges that run the wall's
    length. Returns (faces, rails, closed), or None if it doubles back.

    Closed is a ring all the way round something. Open is a run that stops,
    which is what a bore with a slot or a cross hole through it leaves behind.
    """
    seq, rails, closed = [k0], [], False
    k, e = k0, e0
    while True:
        rails.append((quads[k][e], quads[k][(e + 1) % 4]))
        nxt, key = _across(k, e, quads, edge_faces)
        if nxt is None:
            break
        k2, e2 = nxt
        if k2 == k0:
            if key != _ekey(quads[k0][(e0 + 2) % 4], quads[k0][(e0 + 3) % 4]):
                return None               # came back in by the wrong side
            closed = True
            break
        if k2 in seq:
            return None                   # a figure of eight, not a ring
        seq.append(k2)
        k, e = k2, e2
        if len(seq) > 4096:
            return None
    if closed:
        return seq, rails, True
    # It ran into the end of the wall. Go the other way from where it started.
    k, e = k0, (e0 + 2) % 4
    while True:
        rails.insert(0, (quads[k][e], quads[k][(e + 1) % 4]))
        nxt, _key = _across(k, e, quads, edge_faces)
        if nxt is None:
            return seq, rails, False
        k2, e2 = nxt
        if k2 in seq:
            return None
        seq.insert(0, k2)
        k, e = k2, e2
        if len(seq) > 4096:
            return None


def _walk_ring(k0, e0, quads, edge_faces):
    """The chain from this quad, but only when it goes all the way round."""
    got = _quad_chain(k0, e0, quads, edge_faces)
    return (got[0], got[1]) if got and got[2] else None


def _fit_circle(flat):
    """Least squares circle through points already flattened to two axes.

    The linear form of it: every point satisfies x squared plus y squared
    equals twice cx x plus twice cy y plus a constant, which is three unknowns
    and no iteration.
    """
    n = len(flat)
    sx = sy = sxx = syy = sxy = sz = szx = szy = 0.0
    for x, y in flat:
        z = x * x + y * y
        sx += x
        sy += y
        sxx += x * x
        syy += y * y
        sxy += x * y
        sz += z
        szx += z * x
        szy += z * y
    m = [[sxx, sxy, sx], [sxy, syy, sy], [sx, sy, float(n)]]
    rhs = [szx / 2.0, szy / 2.0, sz / 2.0]
    sol = _solve3(m, rhs)
    if sol is None:
        return None
    cx, cy, c = sol
    r2 = c * 2.0 + cx * cx + cy * cy
    if r2 <= 0:
        return None
    return cx, cy, math.sqrt(r2)


def _solve3(m, rhs):
    a = [row[:] + [rhs[k]] for k, row in enumerate(m)]
    for col in range(3):
        piv = max(range(col, 3), key=lambda r: abs(a[r][col]))
        if abs(a[piv][col]) < 1e-18:
            return None
        a[col], a[piv] = a[piv], a[col]
        for r in range(3):
            if r == col:
                continue
            f = a[r][col] / a[col][col]
            for c in range(col, 4):
                a[r][c] -= f * a[col][c]
    return [a[k][3] / a[k][k] for k in range(3)]


def _loop_about(pts, axis):
    """A closed loop's signed area about an axis: positive is anticlockwise."""
    total = (0.0, 0.0, 0.0)
    n = len(pts)
    for k in range(n):
        total = tuple(total[i] + c for i, c in
                      enumerate(S.cross(pts[k], pts[(k + 1) % n])))
    return S.dot(total, axis) / 2.0


def _same_level(pts, axis, tol):
    """Corners grouped by how far along the axis they sit."""
    levels = []
    for p in pts:
        t = S.dot(p, axis)
        for L in levels:
            if abs(L[0] - t) <= tol:
                L[1].append(p)
                break
        else:
            levels.append((t, [p]))
    return sorted(levels)


def _ring_loop(faces, want, skip):
    """The one loop, on a face that is not part of the ring, that is exactly
    this ring of corners. None unless there is exactly one and it matches
    corner for corner: a cap that has anything else going on at its edge is a
    cap this has no business rewriting."""
    found = None
    for k, f in enumerate(faces):
        if k in skip or not isinstance(f, Flat):
            continue
        for L in f.loops:
            if len(L.pts) != len(want) or {S.snap(p) for p in L.pts} != want:
                continue
            if found is not None:
                return None
            found = L
    return found


def round_faces(faces, least_sides=SIDES, tol=1e-6):
    """Rings of flat quads that are really cylinders, turned into cylinders.

    Every test here has to pass, and each one is guarding against a different
    way of being wrong: the ring has to close, its long edges have to be
    parallel and the same length or it is a cone or a twist, its corners have
    to sit on one circle to within a rounding error, the sides have to be all
    the same length or it is some other polygon, there have to be enough of
    them to mean a circle rather than a hexagon, and the two rings of corners
    have to be whole loops of the faces that cap them, so that turning them
    into circles leaves nothing dangling.

    Which of them earn their keep, measured rather than assumed, by taking
    each one out on its own and seeing whether the selftest notices:

        Enough sides, and the corners sitting on one circle, are the two that
        stand alone. Take either out and a hexagonal boss or a sixteen sided
        star comes back as a rod.

        The rest are belt and braces, and the controls say so honestly. A
        taper or a cylinder cut off at an angle is thrown out before those
        tests are reached, because its ends are not whole loops of anything,
        so no single shape makes any one of them the only thing standing. Take
        the lot out together and the selftest does notice. They stay because
        each is a cheap necessary condition, and the cost of the conjunction
        being too weak is a part that comes back from the shop round when it
        should have been tapered.
    """
    quads, edge_faces = {}, {}
    for k, f in enumerate(faces):
        for L in f.loops:
            pts = L.pts
            for a in range(len(pts)):
                edge_faces.setdefault(
                    _ekey(pts[a], pts[(a + 1) % len(pts)]), []).append(k)
        if len(f.loops) == 1 and len(f.loops[0].pts) == 4:
            quads[k] = f.loops[0].pts

    span = _span(faces) or 1.0
    close = span * tol
    taken, made = set(), []
    for k0 in sorted(quads):
        if k0 in taken:
            continue
        for e0 in (0, 1):
            got = _walk_ring(k0, e0, quads, edge_faces)
            if not got:
                continue
            seq, rails = got
            if len(seq) < least_sides or any(k in taken for k in seq):
                continue
            cyl = _as_cylinder(faces, seq, rails, close)
            if cyl is None:
                continue
            centre, axis, radius, height, ends = cyl
            caps = []
            for want in ends:
                L = _ring_loop(faces, {S.snap(p) for p in want}, set(seq))
                if L is None:
                    break
                caps.append(L)
            if len(caps) != 2:
                continue
            out = _outward(faces[seq[0]], centre, axis)
            for L in caps:
                L.circle = (_on_axis(L.pts[0], centre, axis), axis, radius)
            made.append(Round(centre, axis, radius, height, out, caps))
            taken.update(seq)
            break
    if not made:
        return faces, 0
    kept = [f for k, f in enumerate(faces) if k not in taken]
    return kept + made, len(made)


def _span(faces):
    """How big the thing is, which is what every tolerance here is a fraction
    of. Asked through `bounds` rather than `loops` so it can be asked of a
    cylindrical face as readily as a flat one."""
    pts = [p for f in faces for L, _flip in f.bounds for p in L.pts]
    if not pts:
        return 0.0
    return max(max(p[i] for p in pts) - min(p[i] for p in pts) for i in range(3))


def _as_cylinder(faces, seq, rails, close):
    """A ring of quads measured against being a cylinder. None if it is not."""
    return _fit_cylinder(faces, seq, rails, close, True)


def _at(u, v, t, i, j, axis):
    """A point back in three dimensions from its two flattened coordinates."""
    p = [0.0, 0.0, 0.0]
    p[i] = u
    p[j] = v
    k = 3 - i - j
    p[k] = 0.0
    off = t - S.dot(p, axis)
    return (p[0] + axis[0] * off, p[1] + axis[1] * off, p[2] + axis[2] * off)


def _on_axis(p, anywhere, axis):
    """The point on the axis level with p, which is where a circle's centre
    has to be for the circle to pass through p."""
    d = S.sub(p, anywhere)
    along = S.dot(d, axis)
    return (anywhere[0] + axis[0] * along, anywhere[1] + axis[1] * along,
            anywhere[2] + axis[2] * along)


def _ring_order(pts, axis, cx, cy, i, j):
    """One end's corners, deduplicated and put in order round the circle.

    Turned so that the widest gap between neighbours comes last. A ring all
    the way round has no gap worth the name and this only picks a different
    corner to start at, which nothing downstream minds. An arc that does not
    go all the way round has exactly one gap, where it stops, and putting it
    last is what makes its corners a run rather than a run with the gap
    somewhere in the middle of it.
    """
    seen, out = set(), []
    for p in pts:
        k = S.snap(p)
        if k in seen:
            continue
        seen.add(k)
        out.append(p)
    if not out:
        return None
    out.sort(key=lambda p: math.atan2(p[j] - cy, p[i] - cx))
    n = len(out)
    gaps = [(math.hypot(out[(k + 1) % n][i] - out[k][i],
                        out[(k + 1) % n][j] - out[k][j]), k) for k in range(n)]
    at = max(gaps)[1]
    return out[at + 1:] + out[:at + 1]


def _outward(quad, centre, axis):
    """Is the material outside this cylinder or inside it: a boss or a bore.

    Taken from a wall facet, which already knows which way it faces, by asking
    whether it faces away from the axis or towards it.
    """
    pts = quad.loops[0].pts
    mid = tuple(sum(p[k] for p in pts) / len(pts) for k in range(3))
    off = S.sub(mid, _on_axis(mid, centre, axis))
    return S.dot(quad.normal, off) > 0


# -------------------------------------------------------------- the file

def num(x):
    """A real number the way part 21 wants it: always with a decimal point."""
    if x == 0.0:
        return "0."
    s = f"{x:.12G}"
    if "E" in s:
        m, _, e = s.partition("E")
        if "." not in m:
            m += "."
        return f"{m}E{int(e)}"
    return s if "." in s else s + "."


def txt(s):
    return "'" + str(s).replace("'", "''") + "'"


class Doc:
    """The data section, one numbered line at a time, with the things that
    repeat said once."""

    def __init__(self):
        self.lines = []
        self.known = {}

    def add(self, body, key=None):
        if key is not None and key in self.known:
            return self.known[key]
        n = len(self.lines) + 1
        self.lines.append(f"#{n}={body};")
        if key is not None:
            self.known[key] = n
        return n

    def point(self, p):
        return self.add(
            f"CARTESIAN_POINT('',({num(p[0])},{num(p[1])},{num(p[2])}))",
            ("P",) + S.snap(p))

    def direction(self, d):
        d = S.normalise(d)
        return self.add(
            f"DIRECTION('',({num(d[0])},{num(d[1])},{num(d[2])}))",
            ("D",) + S.snap(d))

    def placement(self, origin, axis, ref):
        return self.add(f"AXIS2_PLACEMENT_3D('',#{self.point(origin)},"
                        f"#{self.direction(axis)},#{self.direction(ref)})")


def _perp(n):
    """Any direction at right angles to this one, chosen so it never comes out
    as nothing."""
    other = (0.0, 0.0, 1.0) if abs(n[2]) < 0.9 else (1.0, 0.0, 0.0)
    return S.normalise(S.cross(other, n))


def _shell(doc, faces, body):
    """One body's faces into a closed shell. Raises if the shell is not closed.

    The check is the one STEP itself relies on: every edge belongs to exactly
    two faces and is walked once each way. A shell that fails it is a shell
    some other package will refuse or quietly repair, and quietly repaired is
    the worst of the three.
    """
    edges, used = {}, {}

    def vertex(p):
        return doc.add(f"VERTEX_POINT('',#{doc.point(p)})",
                       ("V", body) + S.snap(p))

    def line_edge(a, b):
        key = ("L", body) + _ekey(a, b)
        if key not in edges:
            d = S.sub(b, a)
            direc = doc.direction(d)
            vec = doc.add(f"VECTOR('',#{direc},{num(S.length(d))})")
            line = doc.add(f"LINE('',#{doc.point(a)},#{vec})")
            edges[key] = (doc.add(f"EDGE_CURVE('',#{vertex(a)},#{vertex(b)},"
                                  f"#{line},.T.)"), S.snap(a))
            used[key] = [0, 0]
        eid, first = edges[key]
        forward = S.snap(a) == first
        used[key][0 if forward else 1] += 1
        return eid, forward

    def circle_edge(loop):
        centre, axis, radius = loop.circle
        start = loop.pts[0]
        key = ("C", body, S.snap(centre), S.snap(axis), round(radius, 7))
        if key not in edges:
            place = doc.placement(centre, axis, S.sub(start, centre))
            curve = doc.add(f"CIRCLE('',#{place},{num(radius)})")
            v = vertex(start)
            edges[key] = (doc.add(f"EDGE_CURVE('',#{v},#{v},#{curve},.T.)"),
                          None)
            used[key] = [0, 0]
        return edges[key][0], key

    def bound(L, flip):
        if L.circle:
            eid, key = circle_edge(L)
            ccw = _loop_about(L.pts, L.circle[1]) > 0
            if flip:
                ccw = not ccw
            used[key][0 if ccw else 1] += 1
            oe = doc.add(f"ORIENTED_EDGE('',*,*,#{eid},{'.T.' if ccw else '.F.'})")
            return doc.add(f"EDGE_LOOP('',(#{oe}))")
        pts = L.pts[::-1] if flip else L.pts
        oes = []
        for k in range(len(pts)):
            eid, fwd = line_edge(pts[k], pts[(k + 1) % len(pts)])
            oes.append(doc.add(
                f"ORIENTED_EDGE('',*,*,#{eid},{'.T.' if fwd else '.F.'})"))
        return doc.add("EDGE_LOOP('',(" + ",".join(f"#{o}" for o in oes) + "))")

    made = []
    for f in faces:
        bs = []
        for k, (L, flip) in enumerate(f.bounds):
            lid = bound(L, flip)
            kind = ("FACE_OUTER_BOUND" if k == 0 and isinstance(f, Flat)
                    else "FACE_BOUND")
            bs.append(doc.add(f"{kind}('',#{lid},.T.)"))
        if isinstance(f, Round):
            place = doc.placement(f.centre, f.axis, _perp(f.axis))
            surf = doc.add(f"CYLINDRICAL_SURFACE('',#{place},{num(f.radius)})")
            sense = ".T." if f.same_sense else ".F."
        else:
            here = f.loops[0]
            on = here.circle[0] if here.circle else here.pts[0]
            surf = doc.add(
                f"PLANE('',#{doc.placement(on, f.normal, _perp(f.normal))})")
            sense = ".T."
        made.append(doc.add("ADVANCED_FACE('',(" +
                            ",".join(f"#{b}" for b in bs) +
                            f"),#{surf},{sense})"))

    bad = sum(1 for c in used.values() if c != [1, 1])
    if bad:
        raise ValueError(f"{bad} edge(s) are not used by exactly two faces, "
                         f"once each way, so this is not a closed solid")
    return doc.add("CLOSED_SHELL('',(" + ",".join(f"#{m}" for m in made) + "))")


def _facet_faces(tris):
    """Triangles as faces of their own, for anything not recognised."""
    return [Flat(S.normalise(S.cross(S.sub(t[1], t[0]), S.sub(t[2], t[0]))),
                 [Loop(list(t))]) for t in tris]


def body_faces(solid, rounds=True, tol=1e-6, least_sides=SIDES):
    """One solid's surfaces, and a line about what came out of it."""
    tris = solid.tris if hasattr(solid, "tris") else list(solid)
    faces, loose = flat_faces(tris, tol)
    faces += _facet_faces(loose)
    turned = 0
    if rounds:
        faces, turned = round_faces(faces, least_sides, tol)
    flats = sum(1 for f in faces if isinstance(f, Flat))
    return faces, {"flat": flats, "round": turned, "loose": len(loose)}


def write_step(parts, path, name="assembly", unit="mm", rounds=True,
               tol=1e-6, least_sides=SIDES, who="Brainchild Engineering"):
    """An assembly out to one STEP file, each part a named component.

    `parts` is a list of (name, solid), the same as the GLB writer takes, so
    anything that can be looked at in the viewer can be sent to a shop.
    """
    if not parts:
        raise ValueError("an assembly with nothing in it is not an assembly")
    if unit not in UNITS:
        raise ValueError(f"unit {unit!r} is not one of {sorted(UNITS)}")
    doc = Doc()
    ac = doc.add("APPLICATION_CONTEXT('automotive design')")
    doc.add("APPLICATION_PROTOCOL_DEFINITION('international standard',"
            f"'automotive_design',2000,#{ac})")
    pc = doc.add(f"PRODUCT_CONTEXT('',#{ac},'mechanical')")
    pdc = doc.add(f"PRODUCT_DEFINITION_CONTEXT('part definition',#{ac},'design')")
    ctx = _context(doc, unit)
    root = doc.placement((0.0, 0.0, 0.0), (0.0, 0.0, 1.0), (1.0, 0.0, 0.0))

    tally = {"flat": 0, "round": 0, "loose": 0}
    made = []
    for who_num, (part, body) in enumerate(parts):
        faces, count = body_faces(body, rounds, tol, least_sides)
        for k in tally:
            tally[k] += count[k]
        shell = _shell(doc, faces, who_num)
        msb = doc.add(f"MANIFOLD_SOLID_BREP({txt(part)},#{shell})")
        rep = doc.add(f"ADVANCED_BREP_SHAPE_REPRESENTATION({txt(part)},"
                      f"(#{root},#{msb}),#{ctx})")
        made.append((part, _product(doc, part, pc, pdc, rep)))

    if len(made) == 1:
        top = None
    else:
        top = _product(doc, name, pc, pdc,
                       doc.add(f"SHAPE_REPRESENTATION({txt(name)},(#{root}),"
                               f"#{ctx})"))
        for k, (part, kid) in enumerate(made):
            _hang(doc, k + 1, part, top, kid, root)

    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    head = [
        "ISO-10303-21;",
        "HEADER;",
        f"FILE_DESCRIPTION(({txt(name)}),'2;1');",
        f"FILE_NAME({txt(Path(path).name)},{txt(stamp)},({txt(who)}),"
        f"({txt(who)}),'VAS solid kernel','VAS','');",
        f"FILE_SCHEMA(({txt(SCHEMA)}));",
        "ENDSEC;",
        "DATA;",
    ]
    Path(path).write_text("\n".join(head + doc.lines +
                                    ["ENDSEC;", "END-ISO-10303-21;", ""]),
                          encoding="utf-8")
    return _say(parts, tally, unit)


def _say(parts, tally, unit):
    bits = [f"{len(parts)} part(s)", f"{tally['flat']} flat face(s)"]
    if tally["round"]:
        bits.append(f"{tally['round']} real cylinder(s)")
    if tally["loose"]:
        bits.append(f"{tally['loose']} triangle(s) that stayed faceted")
    return (", ".join(bits) + f", in {unit}, every edge shared by exactly two "
            "faces")


def _context(doc, unit):
    prefix, _ = UNITS[unit]
    if prefix is None:                    # inches are not an SI unit
        mm = doc.add("(LENGTH_UNIT()NAMED_UNIT(*)SI_UNIT(.MILLI.,.METRE.))")
        factor = doc.add(f"LENGTH_MEASURE_WITH_UNIT(LENGTH_MEASURE(25.4),#{mm})")
        dim = doc.add("DIMENSIONAL_EXPONENTS(1.,0.,0.,0.,0.,0.,0.)")
        length = doc.add(f"(CONVERSION_BASED_UNIT('INCH',#{factor})"
                         f"LENGTH_UNIT()NAMED_UNIT(#{dim}))")
    else:
        length = doc.add(f"(LENGTH_UNIT()NAMED_UNIT(*)SI_UNIT({prefix},.METRE.))")
    angle = doc.add("(NAMED_UNIT(*)PLANE_ANGLE_UNIT()SI_UNIT($,.RADIAN.))")
    solid = doc.add("(NAMED_UNIT(*)SI_UNIT($,.STERADIAN.)SOLID_ANGLE_UNIT())")
    unc = doc.add(f"UNCERTAINTY_MEASURE_WITH_UNIT(LENGTH_MEASURE(1.E-07),"
                  f"#{length},'distance_accuracy_value','confusion accuracy')")
    return doc.add(
        f"(GEOMETRIC_REPRESENTATION_CONTEXT(3)"
        f"GLOBAL_UNCERTAINTY_ASSIGNED_CONTEXT((#{unc}))"
        f"GLOBAL_UNIT_ASSIGNED_CONTEXT((#{length},#{angle},#{solid}))"
        f"REPRESENTATION_CONTEXT('',''))")


def _product(doc, part, pc, pdc, rep):
    prod = doc.add(f"PRODUCT({txt(part)},{txt(part)},'',(#{pc}))")
    doc.add(f"PRODUCT_RELATED_PRODUCT_CATEGORY('part','',(#{prod}))")
    pdf = doc.add(f"PRODUCT_DEFINITION_FORMATION('','',#{prod})")
    pd = doc.add(f"PRODUCT_DEFINITION('design','',#{pdf},#{pdc})")
    pds = doc.add(f"PRODUCT_DEFINITION_SHAPE('','',#{pd})")
    doc.add(f"SHAPE_DEFINITION_REPRESENTATION(#{pds},#{rep})")
    return pd, rep


def _hang(doc, n, part, top, kid, root):
    """One component hung under the assembly, where it belongs and unmoved."""
    nauo = doc.add(f"NEXT_ASSEMBLY_USAGE_OCCURRENCE('{n}',{txt(part)},'',"
                   f"#{top[0]},#{kid[0]},$)")
    pds = doc.add(f"PRODUCT_DEFINITION_SHAPE('','',#{nauo})")
    idt = doc.add(f"ITEM_DEFINED_TRANSFORMATION('','',#{root},#{root})")
    rel = doc.add(f"(REPRESENTATION_RELATIONSHIP('','',#{kid[1]},#{top[1]})"
                  f"REPRESENTATION_RELATIONSHIP_WITH_TRANSFORMATION(#{idt})"
                  f"SHAPE_REPRESENTATION_RELATIONSHIP())")
    doc.add(f"CONTEXT_DEPENDENT_SHAPE_REPRESENTATION(#{rel},#{pds})")


# ------------------------------------------------------------ reading back

def read_entities(text):
    """The data section as a table of entity number to (name, arguments).

    Written from the part 21 grammar rather than from the writer above, on
    purpose: a reader that shares the writer's assumptions cannot catch the
    writer being wrong about them.
    """
    body = text.split("DATA;", 1)[1].rsplit("ENDSEC;", 1)[0]
    out = {}
    for stmt in _statements(body):
        if "=" not in stmt:
            continue
        num_, _, rest = stmt.partition("=")
        num_ = num_.strip()
        if not num_.startswith("#"):
            continue
        rest = rest.strip()
        if rest.startswith("("):
            parts = []
            for sub in _split(rest[1:-1]):
                parts.append(sub)
            out[int(num_[1:])] = ("COMPLEX", parts)
            continue
        head, _, args = rest.partition("(")
        out[int(num_[1:])] = (head.strip().upper(), _split(args.rsplit(")", 1)[0]))
    return out


def _statements(body):
    out, cur, quote, depth = [], [], False, 0
    for ch in body:
        if quote:
            cur.append(ch)
            if ch == "'":
                quote = False
            continue
        if ch == "'":
            quote = True
            cur.append(ch)
        elif ch == "(":
            depth += 1
            cur.append(ch)
        elif ch == ")":
            depth -= 1
            cur.append(ch)
        elif ch == ";" and depth == 0:
            out.append("".join(cur).strip())
            cur = []
        else:
            cur.append(ch)
    return out


def _split(args):
    out, cur, quote, depth = [], [], False, 0
    for ch in args:
        if quote:
            cur.append(ch)
            if ch == "'":
                quote = False
            continue
        if ch == "'":
            quote = True
            cur.append(ch)
        elif ch in "([":
            depth += 1
            cur.append(ch)
        elif ch in ")]":
            depth -= 1
            cur.append(ch)
        elif ch == "," and depth == 0:
            out.append("".join(cur).strip())
            cur = []
        else:
            cur.append(ch)
    if cur or out:
        out.append("".join(cur).strip())
    return out


class Back:
    """A STEP file read back, and the questions worth asking of it."""

    def __init__(self, text):
        self.e = read_entities(text)

    def of(self, ref):
        return self.e[int(str(ref).strip().lstrip("#"))]

    def refs(self, arg):
        return [a for a in _split(arg.strip()[1:-1]) if a.startswith("#")]

    def point(self, ref):
        name, args = self.of(ref)
        if name == "VERTEX_POINT":
            return self.point(args[1])
        vals = _split(args[1].strip()[1:-1])
        return tuple(float(v) for v in vals)

    def direction(self, ref):
        _name, args = self.of(ref)
        return S.normalise(tuple(float(v)
                                 for v in _split(args[1].strip()[1:-1])))

    def placement(self, ref):
        _name, args = self.of(ref)
        return (self.point(args[1]), self.direction(args[2]),
                self.direction(args[3]))

    def shells(self):
        out = []
        for name, args in self.e.values():
            if name == "MANIFOLD_SOLID_BREP":
                out.append(args[1])
        return out

    def faces(self, shell):
        _name, args = self.of(shell)
        return self.refs(args[1])

    def loop_points(self, bound_ref):
        """A boundary's corners in the order the file says to walk them, or
        the circle it is, chased all the way down to the vertices."""
        _name, args = self.of(bound_ref)
        loop, sense = args[1], args[2] == ".T."
        _lname, largs = self.of(loop)
        oriented = self.refs(largs[1])
        runs = []
        for oe in oriented:
            _oname, oargs = self.of(oe)
            edge, forward = oargs[3], oargs[4] == ".T."
            _ename, eargs = self.of(edge)
            v1, v2, curve, same = eargs[1], eargs[2], eargs[3], eargs[4] == ".T."
            cname, cargs = self.of(curve)
            if cname == "CIRCLE":
                centre, axis, _ref = self.placement(cargs[1])
                way = forward == same
                runs.append(("circle", centre, axis if way else
                             tuple(-c for c in axis), float(cargs[2])))
            else:
                runs.append(("line", self.point(v1 if forward else v2)))
        if not sense:
            runs = runs[::-1]
            runs = [(r[0], r[1], tuple(-c for c in r[2]), r[3])
                    if r[0] == "circle" else r for r in runs]
        return runs

    def volume(self):
        """The solid's volume from its surfaces alone, by the divergence
        theorem. Nothing here is tessellated: a plane contributes its own area
        times how far it sits from the origin, and a cylinder contributes two
        thirds pi r squared h. So this is the volume of what the file actually
        describes, not of the mesh it was written from."""
        total = 0.0
        for shell in self.shells():
            for face in self.faces(shell):
                _name, args = self.of(face)
                bounds, surf = self.refs(args[1]), args[2]
                sense = args[3] == ".T."
                sname, sargs = self.of(surf)
                if sname == "PLANE":
                    origin, axis, _r = self.placement(sargs[1])
                    n = axis if sense else tuple(-c for c in axis)
                    area = sum(self._area(self.loop_points(b), n) for b in bounds)
                    total += S.dot(n, origin) * area / 3.0
                elif sname == "CYLINDRICAL_SURFACE":
                    _o, axis, _r = self.placement(sargs[1])
                    radius = float(sargs[2])
                    tops = []
                    for b in bounds:
                        runs = self.loop_points(b)
                        tops.append(S.dot(runs[0][1], axis))
                    h = abs(tops[0] - tops[1]) if len(tops) == 2 else 0.0
                    s = 1.0 if sense else -1.0
                    total += s * 2.0 * math.pi * radius * radius * h / 3.0
                else:
                    raise ValueError(f"a surface this cannot measure: {sname}")
        return total

    def _area(self, runs, n):
        if len(runs) == 1 and runs[0][0] == "circle":
            _k, _c, axis, r = runs[0]
            return math.pi * r * r * (1.0 if S.dot(axis, n) > 0 else -1.0)
        pts = [r[1] for r in runs]
        return _loop_about(pts, n)

    def edge_uses(self):
        """Every edge, and how many times it is walked each way round."""
        seen = {}
        for shell in self.shells():
            for face in self.faces(shell):
                _name, args = self.of(face)
                for b in self.refs(args[1]):
                    _bn, bargs = self.of(b)
                    flip = bargs[2] != ".T."
                    _ln, largs = self.of(bargs[1])
                    for oe in self.refs(largs[1]):
                        _on, oargs = self.of(oe)
                        fwd = (oargs[4] == ".T.") != flip
                        key = int(oargs[3].lstrip("#"))
                        seen.setdefault(key, [0, 0])[0 if fwd else 1] += 1
        return seen

    def cylinders(self):
        out = []
        for shell in self.shells():
            for face in self.faces(shell):
                _name, args = self.of(face)
                sname, sargs = self.of(args[2])
                if sname == "CYLINDRICAL_SURFACE":
                    out.append((face, float(sargs[2]), args[3] == ".T.",
                                self.placement(sargs[1])))
        return out

    def cylinder_winding(self):
        """Whether each cylinder's two circles run the way its facing says.

        A cylindrical face covers the whole way round, so its lower circle has
        to run one way and its upper one the other. Get that backwards and the
        file still opens, still looks right, and describes a solid turned
        inside out at that face, which is exactly the sort of thing that is
        found by a machinist and not by a picture.
        """
        bad = []
        for face, _r, sense, (_o, axis, _ref) in self.cylinders():
            _name, args = self.of(face)
            ends = []
            for b in self.refs(args[1]):
                runs = self.loop_points(b)
                if len(runs) != 1 or runs[0][0] != "circle":
                    bad.append("a cylinder is not bounded by two whole circles")
                    ends = []
                    break
                ends.append((S.dot(runs[0][1], axis), S.dot(runs[0][2], axis)))
            if len(ends) != 2:
                if not bad:
                    bad.append("a cylinder does not have two ends")
                continue
            ends.sort()
            want = 1.0 if sense else -1.0
            if ends[0][1] * want <= 0 or ends[1][1] * want >= 0:
                bad.append("a cylinder's circles run the wrong way for the "
                           "way the face is facing, so the solid is inside "
                           "out at that face")
        return bad


def volume_of(path):
    return Back(Path(path).read_text(encoding="utf-8")).volume()


# ---------------------------------------------- walls that are part of a bore

def arcs(faces, least_sides=SIDES, tol=1e-6):
    """Walls that sit on a cylinder without going all the way round it.

    A bore with a slot or a cross hole through it leaves an arc rather than a
    ring, and the STEP writer leaves that as facets: a cylindrical face
    bounded by arcs rather than by two whole circles is a bigger piece of work
    and it is not built yet.

    For pointing at, the arc is enough, and the difference is the difference
    between a useful answer and a useless one. He taps the wall of the
    bearing bore and hears "the 26 mm bore, 12 deep", which is what it is,
    rather than "a flat face 1.4 by 12", which is true and no help to anybody.

    The same tests as a full ring, minus the ones about capping, plus one that
    replaces counting sides: a facet has to turn through a small enough angle
    that a whole circle of them would take at least `least_sides`. That is
    what stops the two flats either side of a hexagon's corner reading as a
    piece of a very large bore.
    """
    close = (_span(faces) or 1.0) * tol
    taken, out = set(), []
    for seq, rails, closed in chains(faces):
            for run, fit in _arc_runs(faces, seq, rails, close, closed):
                if any(k in taken for k in run):
                    continue
                centre, axis, radius, _height, ends = fit
                step = S.length(S.sub(ends[0][1], ends[0][0]))
                if step >= 2.0 * radius:
                    continue              # a chord that long is not an arc
                per = 2.0 * math.asin(min(1.0, step / (2.0 * radius)))
                if per <= 0 or 2.0 * math.pi / per < least_sides:
                    continue              # too coarse to mean a circle
                rail = S.length(S.sub(rails[0][1], rails[0][0]))
                out.append({"faces": set(run), "centre": centre, "axis": axis,
                            "radius": radius, "height": rail,
                            "same_sense": _outward(faces[run[0]], centre, axis),
                            "sweep": math.degrees(per * len(run))})
                taken.update(run)
    return out


def chains(faces):
    """Every run of quads joined along the edges that run their length.

    Handed out rather than kept private because it is the thing worth testing
    on its own: whether a run that happens to start halfway along an arc is
    still found whole depends on nothing else, and going through a part to
    reach it makes it a matter of which quad the walk happened to begin at.
    """
    quads, edge_faces = {}, {}
    for k, f in enumerate(faces):
        for L, _flip in f.bounds:
            pts = L.pts
            for a in range(len(pts)):
                edge_faces.setdefault(
                    _ekey(pts[a], pts[(a + 1) % len(pts)]), []).append(k)
        if isinstance(f, Flat) and len(f.loops) == 1 and len(f.loops[0].pts) == 4:
            quads[k] = f.loops[0].pts
    seen, out = set(), []
    for k0 in sorted(quads):
        for e0 in (0, 1):
            got = _quad_chain(k0, e0, quads, edge_faces)
            if not got or len(got[0]) < LEAST_ARC:
                continue
            if frozenset(got[0]) in seen:
                continue
            seen.add(frozenset(got[0]))
            out.append(got)
    return out


LEAST_ARC = 4           # fewer facets than this is not enough of a curve


def _fit_cylinder(faces, seq, rails, close, closed):
    """A chain of quads measured against sitting on one cylinder.

    Shared by the writer, which wants rings it can turn into real cylindrical
    faces, and by the pointing, which will take an arc. A closed chain has as
    many corners at each end as it has faces; an open one has one more,
    because it has two loose ends.
    """
    axis = S.normalise(S.sub(rails[0][1], rails[0][0]))
    height = S.length(S.sub(rails[0][1], rails[0][0]))
    if height <= 0:
        return None
    for a, b in rails[1:]:
        d = S.sub(b, a)
        if abs(S.length(d) - height) > close:
            return None                   # not the same length: not a cylinder
        if abs(abs(S.dot(S.normalise(d), axis)) - 1.0) > 1e-9:
            return None                   # not parallel: a cone or a twist

    pts = []
    for k in seq:
        pts += faces[k].loops[0].pts
    i, j = S._frame(axis)
    fit = _fit_circle([(p[i], p[j]) for p in pts])
    if fit is None:
        return None
    cx, cy, radius = fit
    if radius <= close:
        return None
    for p in pts:
        if abs(math.hypot(p[i] - cx, p[j] - cy) - radius) > close:
            return None                   # the corners are not on one circle

    levels = _same_level(pts, axis, close)
    if len(levels) != 2 or any(len(L[1]) != 2 * len(seq) for L in levels):
        return None                       # not two flat ends, or not a ring
    want = len(seq) if closed else len(seq) + 1
    ends = [_ring_order(L[1], axis, cx, cy, i, j) for L in levels]
    if any(e is None or len(e) != want for e in ends):
        return None
    for e in ends:
        n = len(e)
        sides = [S.length(S.sub(e[(k + 1) % n], e[k]))
                 for k in range(n if closed else n - 1)]
        if max(sides) - min(sides) > close:
            return None                   # a circle's sides are all the same
    centre = _on_axis(ends[0][0], _at(cx, cy, 0.0, i, j, axis), axis)
    return centre, axis, radius, abs(levels[1][0] - levels[0][0]), ends


def _arc_runs(faces, seq, rails, close, closed, least=LEAST_ARC):
    """The longest runs of this chain whose corners sit on one circle.

    A chain does not have to be all one thing, and on a real part it usually
    is not. The bearing bore's wall and the walls of the slot cut through it
    are all twelve millimetre quads joined along their long edges, so the walk
    goes round the bore, into the slot, across it and back round the other
    side, and closes. Asking whether the whole of that is a cylinder gets the
    answer no, which is true and throws the bore away with it.

    So: every run that fits one circle and cannot be made longer at either
    end. Turning a closed chain to start somewhere convenient is not good
    enough, and the selftest says why: a start chosen for not beginning an arc
    can still be a few facets into one, and the arc before it comes out short.
    What he is told he is pointing at cannot depend on which quad a walk
    happened to begin at, so every start is tried and the answer is the same
    from all of them.
    """
    n = len(seq)
    if n < least:
        return []
    # A ring that goes all the way round and was not written as a cylinder,
    # because its ends are not whole loops of anything, is still a bore to
    # point at. It is one arc of three hundred and sixty degrees, not n of
    # them overlapping.
    if closed:
        whole = _fit_cylinder(faces, seq, rails, close, True)
        if whole is not None:
            return [(list(seq), whole)]

    def fit(k, m):
        if m > n or (not closed and k + m > n):
            return None
        idx = [(k + i) % n for i in range(m)]
        return _fit_cylinder(faces, [seq[i] for i in idx],
                             [rails[i] for i in idx], close, False)

    def longest(k):
        best, m = None, least
        while True:
            got = fit(k, m)
            if got is None:
                return best
            best, m = (m, got), m + 1

    grown = {}
    for k in range(n if closed else n - least + 1):
        got = longest(k)
        if got:
            grown[k] = got
    out = []
    for k in sorted(grown):
        m, got = grown[k]
        back = grown.get((k - 1) % n) if closed else grown.get(k - 1)
        if back and back[0] >= m + 1:
            continue                      # the run starting before this covers it
        out.append(([seq[(k + i) % n] for i in range(m)], got))
    return out


# ------------------------------------------------- pointing at a feature

# Which way is which, in the words the viewer uses for its own standard
# views, so that what this calls the front is the face he sees when he taps
# Front. Engineering sits the part on the xy plane with z up.
FACING = (((1.0, 0.0, 0.0), "the right", "+X"),
          ((-1.0, 0.0, 0.0), "the left", "-X"),
          ((0.0, 1.0, 0.0), "the back", "+Y"),
          ((0.0, -1.0, 0.0), "the front", "-Y"),
          ((0.0, 0.0, 1.0), "the top", "+Z"),
          ((0.0, 0.0, -1.0), "the underside", "-Z"))


def facing(n):
    """What to call this direction, or None if it is not a square one."""
    for d, word, axis in FACING:
        if S.dot(n, d) > 0.9999:
            return word, axis
    return None, None


def mm(x):
    """A length the way somebody says it out loud: 12, not 12.000000."""
    s = f"{x:.2f}"
    return s.rstrip("0").rstrip(".") if "." in s else s


def surfaces(parts, rounds=True, tol=1e-6, least_sides=SIDES):
    """Every part's faces, worked out once and kept so they can be pointed at.

    The same faces the STEP writer uses, which is the point of doing it this
    way: what he taps is a face the file has a name for, so "make this bore
    fourteen" means one number in one place rather than a description somebody
    has to guess their way back to.
    """
    out = []
    for name, body in parts:
        faces, _count = body_faces(body, rounds, tol, least_sides)
        out.append((name, faces, arcs(faces, least_sides, tol)))
    return out


def _face_span(faces):
    return _span(faces) or 1.0


def _on_flat(f, p, near):
    """Is this point on this planar face, holes and all.

    A point on the edge between two faces is strictly inside neither, and a
    finger on a phone lands on edges all the time: the wall of a bore that has
    come out as facets is a fan of strips a millimetre wide, so most of what
    he can hit is edge. So a point just outside the outline still counts, and
    ranks worse than one properly inside it, which lets the face he actually
    meant win when both are in the running.
    """
    n = f.normal
    off = abs(S.dot(n, p) - S.dot(n, f.loops[0].pts[0]))
    if off > near:
        return None
    i, j = S._frame(n)
    flat = (p[i], p[j])
    out = [(q[i], q[j]) for q in f.loops[0].pts]
    if not S._inside_loop(flat, out):
        edge = _to_edge(flat, out)
        if edge > near:
            return None
        return math.hypot(off, edge)
    for hole in f.loops[1:]:
        ring = [(q[i], q[j]) for q in hole.pts]
        if S._inside_loop(flat, ring) and _to_edge(flat, ring) > near:
            return None                   # down the hole, not on the face
    return off


def _to_edge(p, loop):
    """How far this point is from the outline, measured on the flat."""
    best = None
    for k in range(len(loop)):
        a, b = loop[k], loop[(k + 1) % len(loop)]
        dx, dy = b[0] - a[0], b[1] - a[1]
        run = dx * dx + dy * dy
        t = 0.0 if run <= 0 else max(0.0, min(1.0, (
            (p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / run))
        away = math.hypot(p[0] - (a[0] + dx * t), p[1] - (a[1] + dy * t))
        if best is None or away < best:
            best = away
    return best if best is not None else float("inf")


def _on_round(f, p, near):
    """Is this point on this cylindrical face.

    The tap lands on a triangle, and a triangle of a round wall is a chord:
    it sits inside the true surface by a fraction of the radius. So the
    distance allowed has to be wider than that sag, which is what the caller's
    tolerance is scaled from.
    """
    t = S.dot(S.sub(p, f.centre), f.axis)
    if t < -near or t > f.height + near:
        return None
    off = S.sub(S.sub(p, f.centre), tuple(c * t for c in f.axis))
    out = abs(S.length(off) - f.radius)
    return out if out <= near else None


def point_at(kept, point, normal=None, part=None, near=None):
    """Which face of which part the finger is on. None if it is on none.

    `kept` is what `surfaces` handed back. The point is in the part's own
    coordinates, z up, the same numbers that are in the part's script.
    """
    if near is None:
        span = max((_face_span(f) for _n, f, _a in kept), default=1.0)
        near = max(span * 1e-3, 1e-4)
    best = None
    for name, faces, round_bits in kept:
        if part and name != part:
            continue
        for k, f in enumerate(faces):
            if isinstance(f, Round):
                off = _on_round(f, point, near)
                out = None
            else:
                off = _on_flat(f, point, near)
                out = f.normal
            if off is None:
                continue
            # A point on an edge is on two faces. The one he meant is the one
            # he can see, which is the one facing back at him.
            agrees = 1.0 if normal is None or out is None else S.dot(out, normal)
            if agrees < 0.2 and normal is not None and out is not None:
                continue
            rank = (off, -agrees)
            if best is None or rank < best[0]:
                # A facet that is one slice of a bore is answered for by the
                # bore. Nobody points at a strip a millimetre wide; they point
                # at the hole it is part of.
                part_of = next((a for a in round_bits if k in a["faces"]), None)
                best = (rank, name, k, f, part_of)
    if best is None:
        return None
    if best[4] is not None:
        return describe_arc(best[1], best[4], best[2])
    return describe(best[1], best[3], best[2])


def describe_arc(part, a, index=0):
    """A bore that something else has cut through, said as the bore it is."""
    axis, c, r = a["axis"], a["centre"], a["radius"]
    b = tuple(c[k] + axis[k] * a["height"] for k in range(3))
    word, ax = facing(axis)
    if word is None:
        word, ax = facing(tuple(-q for q in axis))
    along = f"along {ax}" if ax else "along " + ", ".join(mm(q) for q in axis)
    kind = "boss" if a["same_sense"] else "bore"
    what = "a round post" if a["same_sense"] else "a bore"
    said = (f"{what} on {part}, {mm(2 * r)} mm across and {mm(a['height'])} mm "
            f"long, {along}, from ({mm(c[0])}, {mm(c[1])}, {mm(c[2])}) to "
            f"({mm(b[0])}, {mm(b[1])}, {mm(b[2])}). Something else cuts "
            f"through it: only {round(a['sweep'])} degrees of the wall is "
            f"here")
    return {"part": part, "index": index, "kind": kind, "said": said,
            "short": f"\u2300{mm(2 * r)} {kind}, {mm(a['height'])} deep",
            "diameter": 2 * r, "depth": a["height"], "axis": list(axis),
            "from": list(c), "to": list(b), "sweep": a["sweep"],
            "interrupted": True}


def describe(part, f, index=0):
    """One face, said in a sentence with its numbers in it.

    Written to be pasted into a request, which is the whole reason it exists:
    a tap that produces "the 12 mm bore through the top of Bearing block, from
    z 48 down to z 8" is a request somebody can act on without asking which
    one he meant.
    """
    if isinstance(f, Round):
        a, b = f.centre, tuple(f.centre[k] + f.axis[k] * f.height
                               for k in range(3))
        word, axis = facing(f.axis)
        if word is None:
            word, axis = facing(tuple(-c for c in f.axis))
        along = f"along {axis}" if axis else (
            "along " + ", ".join(mm(c) for c in f.axis))
        kind = "boss" if f.same_sense else "bore"
        what = ("a round post" if f.same_sense else "a bore")
        said = (f"{what} on {part}, {mm(2 * f.radius)} mm across and "
                f"{mm(f.height)} mm long, {along}, from "
                f"({mm(a[0])}, {mm(a[1])}, {mm(a[2])}) to "
                f"({mm(b[0])}, {mm(b[1])}, {mm(b[2])})")
        return {"part": part, "index": index, "kind": kind, "said": said,
                "short": f"\u2300{mm(2 * f.radius)} {kind}, {mm(f.height)} deep",
                "diameter": 2 * f.radius, "depth": f.height,
                "axis": list(f.axis), "from": list(a), "to": list(b)}

    pts = f.loops[0].pts
    i, j = S._frame(f.normal)
    w = max(q[i] for q in pts) - min(q[i] for q in pts)
    h = max(q[j] for q in pts) - min(q[j] for q in pts)
    word, axis = facing(f.normal)
    which = f"facing {word} ({axis})" if word else (
        "facing " + ", ".join(mm(c) for c in f.normal))
    off = S.dot(f.normal, pts[0])
    holes = len(f.loops) - 1
    said = (f"a flat face on {part}, {mm(w)} by {mm(h)} mm, {which}, "
            f"{mm(abs(off))} mm from the origin along that direction")
    if holes:
        said += f", with {holes} hole(s) in it"
    return {"part": part, "index": index, "kind": "flat", "said": said,
            "short": f"flat face, {mm(w)} \u00d7 {mm(h)}",
            "normal": list(f.normal), "size": [w, h], "holes": holes,
            "at": list(pts[0])}


# --------------------------------------------------------------- selftest

def _ring(n, r, z):
    return [(r * math.cos(2 * math.pi * k / n),
             r * math.sin(2 * math.pi * k / n), z) for k in range(n)]


def _star(n, big, small, z):
    return [((big if k % 2 == 0 else small) * math.cos(2 * math.pi * k / n),
             (big if k % 2 == 0 else small) * math.sin(2 * math.pi * k / n), z)
            for k in range(n)]


def _prism_volume(n, r):
    """A regular n sided prism's cross section, for a unit height."""
    return n * 0.5 * r * r * math.sin(2 * math.pi / n)


def _cap(ring, up):
    """A ring of corners closed off with a lid, by ear clipping it.

    Fanning a lid from one of its own corners is only right for an outline
    that bulges outwards everywhere. A star fanned that way gets triangles
    that stick out past its own points and lie over each other, and the worst
    of it is that they still add up to the right volume, so the mistake
    survives every check that only weighs the thing.
    """
    flat = [(p[0], p[1]) for p in ring]
    back = {f: p for f, p in zip(flat, ring)}
    if S.signed_area(flat) < 0:
        flat = flat[::-1]
    out = []
    for a, b, c in S.ear_clip(flat):
        t = (back[a], back[b], back[c])
        out.append(t if up else (t[0], t[2], t[1]))
    return out


def _band(bot, top):
    """A solid from two matching rings: a wall between them and a cap on each.

    Built here rather than in the kernel because these are shapes nobody wants
    to design with. They exist to be things that look like a cylinder to a
    careless eye and are not one.
    """
    tris, n = [], len(bot)
    for k in range(n):
        a, b = bot[k], bot[(k + 1) % n]
        c, d = top[k], top[(k + 1) % n]
        tris += [(a, b, d), (a, d, c)]
    return S.Solid(tris + _cap(bot, False) + _cap(top, True))


def selftest():
    import tempfile
    fail = []

    # A tenth of a micron on a metre. Tighter than that is not a claim this
    # can honestly make: the kernel rounds every coordinate to seven decimal
    # places, so a radius fitted through sixty four of those corners is known
    # to about a hundredth of a micron and no better.
    def near(what, got, want, tol=1e-7):
        if abs(got - want) > tol * max(1.0, abs(want)):
            fail.append(f"{what}: got {got:.9f}, wanted {want:.9f} "
                        f"(out by {abs(got - want):.9f})")

    def check(what, parts, want, rounds=True, cylinders=None, flats=None):
        # What went in has to be a sound solid first. A test shape that is
        # quietly broken makes every number below meaningless, and the volume
        # on its own will not say so: a lid fanned the wrong way over a
        # concave outline weighs exactly the right amount.
        for _name, body in parts:
            wrong = body.check()
            if wrong:
                fail.append(f"{what} was not a sound solid before it was "
                            f"exported, so nothing below it means anything: "
                            f"{wrong[0]}")
                return None
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "part.step"
            try:
                write_step(parts, path, name=what, rounds=rounds)
            except ValueError as e:
                fail.append(f"{what} would not go out as STEP: {e}")
                return None
            text = path.read_text(encoding="utf-8")
            if not text.startswith("ISO-10303-21;"):
                fail.append(f"{what} is not a part 21 file")
            if "END-ISO-10303-21;" not in text:
                fail.append(f"{what} was cut off")
            back = Back(text)
            near(f"{what}: the volume the file describes", back.volume(), want)
            bad = [k for k, c in back.edge_uses().items() if c != [1, 1]]
            if bad:
                fail.append(f"{what}: {len(bad)} edge(s) are not walked by two "
                            f"faces, once each way, so the shell is not closed")
            for why in back.cylinder_winding():
                fail.append(f"{what}: {why}")
            got = len(back.cylinders())
            if cylinders is not None and got != cylinders:
                fail.append(f"{what}: {got} cylindrical face(s), "
                            f"wanted {cylinders}")
            if flats is not None:
                n = sum(1 for sh in back.shells() for f in back.faces(sh))
                if n != flats:
                    fail.append(f"{what}: {n} face(s) in all, wanted {flats}")
            return back

    # A box. Six faces, no more, and every corner where it was.
    box = S.box(30.0, 20.0, 10.0)
    check("a box", [("Box", box)], 30.0 * 20.0 * 10.0, cylinders=0, flats=6)

    # A plate with a bore through it. The bore has to come back as one real
    # cylinder of the true radius, which is the whole point: the file's volume
    # is then the exact one, not the tessellated one the mesh has.
    plate = S.difference(S.box(40.0, 40.0, 8.0),
                         S.cylinder(6.0, 40.0, 64, at=(20.0, 20.0, -10.0)))
    want = 40.0 * 40.0 * 8.0 - math.pi * 36.0 * 8.0
    back = check("a plate with a bore through it", [("Plate", plate)], want,
                 cylinders=1, flats=7)
    if back:
        r = back.cylinders()[0][1]
        near("the bore's radius", r, 6.0)
        if back.cylinders()[0][2]:
            fail.append("a bore is facing outwards, so the hole is a peg")

    # The same plate with recognition turned off. Now the file must hold the
    # mesh exactly, tessellation error and all, which is the control that says
    # the exactness above came from recognising the cylinder and not from a
    # tolerance quietly swallowing the difference.
    rough = S.Solid(plate.tris).volume()
    check("the same plate, left faceted", [("Plate", plate)], rough,
          rounds=False, cylinders=0)
    if abs(rough - want) < 1e-6:
        fail.append("the faceted plate and the true plate have the same "
                    "volume, so the test above proves nothing")

    # A rod: a cylinder and nothing else. Two flat ends and one round side.
    rod = S.cylinder(5.0, 25.0, 64)
    check("a rod", [("Rod", rod)], math.pi * 25.0 * 25.0, cylinders=1, flats=3)

    # Four things that leave a ring of flat quads behind them exactly the way
    # a cylinder does, and are not cylinders. Each one is here because a
    # recogniser that skipped one of its tests would turn it into one, and a
    # part that comes back from the shop round when it was meant to be
    # tapered, or slanted, or a hexagon, is scrap.
    hexy = S.cylinder(8.0, 12.0, 6)
    check("a hexagonal boss", [("Hex", hexy)], _prism_volume(6, 8.0) * 12.0,
          cylinders=0, flats=8)

    # A taper. Its walls are quads, its corners do lie on circles, and its
    # long edges lean in towards the axis instead of running parallel.
    cone = _band(_ring(32, 12.0, 0.0), _ring(32, 6.0, 25.0))
    k = _prism_volume(32, 1.0)
    check("a tapered boss", [("Taper", cone)],
          25.0 * k * (144.0 + 72.0 + 36.0) / 3.0, cylinders=0)

    # A cylinder cut off at an angle. Parallel walls, corners on a circle,
    # every side the same length, and the long edges are all different
    # lengths, which is the only thing that says it is not a plain cylinder.
    slant = _band(_ring(64, 10.0, 0.0),
                  [(x, y, 20.0 + 0.3 * x) for x, y, _z in _ring(64, 10.0, 0.0)])
    check("a cylinder cut off at an angle", [("Slant", slant)],
          _prism_volume(64, 10.0) * 20.0, cylinders=0)

    # A star. Sixteen sides, plenty to be mistaken for a rough circle, and its
    # corners are on two circles rather than one.
    star = _band(_star(16, 10.0, 6.0, 0.0), _star(16, 10.0, 6.0, 15.0))
    check("a star shaped post", [("Star", star)],
          16 * 0.5 * 10.0 * 6.0 * math.sin(2 * math.pi / 16) * 15.0,
          cylinders=0)

    # A blind hole: the cylinder is capped by a flat bottom inside the part,
    # so one of its circles is the outline of a face rather than a hole in one.
    blind = S.difference(S.box(30.0, 30.0, 20.0),
                         S.cylinder(4.0, 12.0, 64, at=(15.0, 15.0, 8.0)))
    check("a blind hole", [("Blind", blind)],
          30.0 * 30.0 * 20.0 - math.pi * 16.0 * 12.0, cylinders=1)

    # A tube. Two cylinders, one facing out and one facing in, and the volume
    # is the difference between them.
    tube = S.difference(S.cylinder(10.0, 30.0, 64),
                        S.cylinder(7.0, 50.0, 64, at=(0.0, 0.0, -10.0)))
    check("a tube", [("Tube", tube)], math.pi * (100.0 - 49.0) * 30.0,
          cylinders=2)

    # An assembly. Two parts, named, each a solid of its own, and the file has
    # to keep them apart rather than welding them into one lump.
    post = S.cylinder(6.0, 40.0, 64, at=(20.0, 20.0, 8.0))
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "asm.step"
        write_step([("Plate", plate), ("Post", post)], path, name="Assembly")
        text = path.read_text(encoding="utf-8")
        back = Back(text)
        if len(back.shells()) != 2:
            fail.append(f"an assembly of two parts went out as "
                        f"{len(back.shells())} solid(s)")
        near("the assembly's volume", back.volume(),
             want + math.pi * 36.0 * 40.0)
        if text.count("NEXT_ASSEMBLY_USAGE_OCCURRENCE") != 2:
            fail.append("the parts are not hung under an assembly, so they "
                        "open as loose bodies with no tree")
        for part in ("Plate", "Post"):
            if f"PRODUCT('{part}'" not in text:
                fail.append(f"{part} lost its name on the way out")

    # Inches. The numbers stay as they are and the unit says what they mean:
    # scaling the geometry instead would be the classic way to lose a part.
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "in.step"
        write_step([("Box", box)], path, unit="in")
        text = path.read_text(encoding="utf-8")
        if "CONVERSION_BASED_UNIT('INCH'" not in text:
            fail.append("an inch file does not say it is in inches")
        near("an inch file's numbers", Back(text).volume(), 6000.0)

    # An empty assembly, and a unit nobody has heard of.
    for bad, why in (([], "nothing in it"), (None, "nothing in it")):
        try:
            write_step(bad or [], "/dev/null")
            fail.append("an assembly with nothing in it was written out")
        except ValueError:
            pass
    try:
        write_step([("Box", box)], "/dev/null", unit="furlong")
        fail.append("a unit nobody has heard of was accepted")
    except ValueError:
        pass

    # Pointing at a feature. The tap lands on a triangle, which for a round
    # wall is a chord sitting inside the true surface, so this is also the
    # test that the allowance for that sag is wide enough to find the face and
    # not so wide that it finds the wrong one.
    kept = surfaces([("Plate", plate)])
    top = point_at(kept, (5.0, 5.0, 8.0), (0.0, 0.0, 1.0))
    if not top or top["kind"] != "flat":
        fail.append(f"tapping the top of a plate found {top}")
    else:
        if "the top" not in top["said"] or "+Z" not in top["said"]:
            fail.append(f"the top of a plate is not called the top: {top['said']}")
        if top["holes"] != 1:
            fail.append(f"the top of a plate with a bore in it reports "
                        f"{top['holes']} hole(s)")
        if abs(top["size"][0] - 40.0) > 1e-6 or abs(top["size"][1] - 40.0) > 1e-6:
            fail.append(f"a 40 by 40 face measures {top['size']}")

    # The bore's wall, tapped where the mesh actually is: on a chord, a
    # little inside the true cylinder.
    inside = 6.0 * math.cos(math.pi / 64)
    bore = point_at(kept, (20.0 + inside, 20.0, 4.0), (-1.0, 0.0, 0.0))
    if not bore or bore["kind"] != "bore":
        fail.append(f"tapping the wall of a bore found {bore}")
    else:
        near("the bore he tapped is that wide", bore["diameter"], 12.0)
        near("and that deep", bore["depth"], 8.0)
        if "\u2300" not in bore["short"]:
            fail.append(f"a bore is not offered as a diameter: {bore['short']}")

    side = point_at(kept, (40.0, 20.0, 4.0), (1.0, 0.0, 0.0))
    if not side or "the right" not in (side.get("said") or ""):
        fail.append(f"tapping the right hand face found {side}")
    if point_at(kept, (20.0, 20.0, 400.0), (0.0, 0.0, 1.0)) is not None:
        fail.append("tapping a long way off the part still found a face")
    # Straight down the middle of the hole is not the wall of the hole.
    if point_at(kept, (20.0, 20.0, 8.0), (0.0, 0.0, 1.0)) is not None:
        fail.append("tapping down the middle of a hole found the face the "
                    "hole is in, which is the one place it is not")

    # A bore with a slot cut into it, which is what a clamp is and what most
    # real bores are: something else goes through them. The ring of facets
    # never closes, so it is not written as a cylinder, but he still has to be
    # able to point at it and be told it is a bore.
    clamp = S.difference(plate, S.box(4.0, 16.0, 20.0, at=(18.0, -1.0, -6.0)))
    check("a plate with a slot into its bore", [("Clamp", clamp)],
          S.Solid(clamp.tris).volume(), cylinders=0)
    held = surfaces([("Clamp", clamp)])
    holes = held[0][2]
    if len(holes) != 1:
        fail.append(f"a bore with a slot into it was found {len(holes)} time(s), "
                    f"wanted once")
    else:
        near("the interrupted bore is that wide", 2 * holes[0]["radius"], 12.0)
        # Worked out rather than eyeballed: the slot is 4 wide across a bore
        # 12 across, so it takes twice asin(2/6) out of the wall, which is 39
        # degrees, and the facets either side of that round it out by one
        # step. A range wide enough to pass a wall found in two halves and
        # reported as the bigger half is a range that is not checking this.
        want = 360.0 - 2.0 * math.degrees(math.asin(2.0 / 6.0))
        if abs(holes[0]["sweep"] - want) > 12.0:
            fail.append(f"a bore with a 4 mm slot into it has "
                        f"{holes[0]['sweep']:.0f} degrees of wall, wanted about "
                        f"{want:.0f}")
    # Tapped on the chord, where the mesh is, on the far side from the slot.
    turn = math.pi / 2
    wall = point_at(held, (20.0 + inside * math.cos(turn),
                           20.0 + inside * math.sin(turn), 4.0),
                    (-math.cos(turn), -math.sin(turn), 0.0))
    if not wall or wall["kind"] != "bore":
        fail.append(f"tapping the wall of an interrupted bore found {wall}")
    else:
        near("and he is told how wide it is", wall["diameter"], 12.0)
        if not wall.get("interrupted"):
            fail.append("an interrupted bore does not say that it is")

    # Tapped right on the join between two facets of that bore, which is most
    # of what a finger can actually hit: the wall is a fan of strips about a
    # millimetre wide. A point on the edge between two faces is strictly
    # inside neither of them.
    slice_ = held[0][1][sorted(holes[0]["faces"])[1]].loops[0].pts
    seam = [q for q in slice_ if abs(q[2] - slice_[0][2]) > 1e-9]
    if len(seam) < 2:
        fail.append("a facet of a bore's wall does not have two ends")
    else:
        # With the way the surface faces there, which is what a real tap
        # carries: a corner of a facet is also a corner of the face at the end
        # of the bore, and nothing but the facing can separate the two.
        which = held[0][1][sorted(holes[0]["faces"])[1]].normal
        for where, on in (("the join between two facets",
                           tuple((seam[0][k] + slice_[0][k]) / 2.0
                                 for k in range(3))),
                          ("the exact corner of a facet", slice_[0])):
            edge = point_at(held, on, which)
            if not edge or edge["kind"] != "bore":
                fail.append(f"tapping {where} of a bore found "
                            f"{edge and edge.get('short')}")

    # The other half of that: a hexagonal pocket is a hexagon. Any four
    # corners of a regular polygon sit on a circle, so a run of facets fitting
    # one proves nothing on its own. What says a hexagon is a hexagon is how
    # far each of its walls turns through: sixty degrees is a corner, and a
    # circle made of corners like that would have six sides.
    hexhole = S.difference(S.box(40.0, 40.0, 8.0),
                           S.cylinder(8.0, 40.0, 6, at=(20.0, 20.0, -10.0)))
    if surfaces([("Hexpocket", hexhole)])[0][2]:
        fail.append("a hexagonal pocket was called a bore")
    # And with a slot into it, so that its walls are a run rather than a ring
    # and the only thing left standing between it and being called a bore is
    # how far each wall turns.
    hexslot = S.difference(hexhole,
                           S.box(4.0, 16.0, 20.0, at=(18.0, -1.0, -6.0)))
    if surfaces([("Hexslot", hexslot)])[0][2]:
        fail.append("a hexagonal pocket with a slot into it was called a bore")
    if surfaces([("Star", star)])[0][2]:
        fail.append("a star shaped post was called a bore")

    # An arc found whole no matter where its chain happens to begin. Asked of
    # the chain directly, because going through a part to reach it makes the
    # answer depend on which quad the walk started at, which is the one thing
    # this is meant to be independent of.
    ring = [c for c in chains(held[0][1]) if c[2] and len(c[0]) > 8]
    if not ring:
        fail.append("a bore with a slot into it left no closed chain of quads, "
                    "so the test below is testing nothing")
    else:
        seq, rails, _closed = ring[0]
        n, close = len(seq), (_span(held[0][1]) or 1.0) * 1e-6
        widest = max(len(r) for r, _f in
                     _arc_runs(held[0][1], seq, rails, close, True))
        for turn in range(n):
            spun = [seq[(turn + i) % n] for i in range(n)]
            spunr = [rails[(turn + i) % n] for i in range(n)]
            got = _arc_runs(held[0][1], spun, spunr, close, True)
            if max((len(r) for r, _f in got), default=0) != widest:
                fail.append(f"a chain begun {turn} quad(s) round finds an arc "
                            f"of a different length, so what he is told he is "
                            f"pointing at depends on where a walk started")
                break

    # Two parts touching. The finger is on one of them, and which one it is
    # cannot be settled by position alone.
    both = surfaces([("Plate", plate), ("Post", post)])
    got = point_at(both, (20.0 + inside, 20.0, 20.0), (1.0, 0.0, 0.0))
    if not got or got["part"] != "Post":
        fail.append(f"tapping the post where it stands proud found {got}")
    only = point_at(both, (5.0, 5.0, 8.0), (0.0, 0.0, 1.0), part="Post")
    if only is not None:
        fail.append("asking about one part answered about another")

    if fail:
        print("SELFTEST FAILED")
        for f in fail:
            print(f"  {f}")
        return 1
    print("selftest ok: a box, a plate with a bore, a rod, a blind hole, a "
          "tube and a two part assembly all go out as STEP and come back "
          "describing exactly the volume worked out by hand, with every edge "
          "walked by two faces once each way and every cylinder facing and "
          "wound the way its solid needs. The bores come back as real "
          "cylinders of the true radius rather than facets, the parts keep "
          "their names and hang under an assembly, and with recognition "
          "switched off the file carries the mesh exactly as it was. Four "
          "things that leave the same ring of flat quads behind them as a "
          "cylinder does, and are not one, are left alone: a hexagonal boss, "
          "a taper, a cylinder cut off at an angle and a sixteen sided star. "
          "A tap lands on the right face and says what it is in a sentence "
          "with the numbers in it: which part, how wide, how deep, which way "
          "it faces and where it is, so a request can name it rather than "
          "describe it. A bore with a slot cut into it, which is what most "
          "real bores are, is still a bore when he points at it, while a "
          "hexagonal pocket and a star stay what they are.")
    return 0


def main():
    if "--selftest" in sys.argv:
        return selftest()
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    if len(args) != 2:
        print(__doc__.strip().splitlines()[0])
        print("  python3 tools/step.py <part.glb|.stl> <out.step> "
              "[--unit mm|cm|m|in] [--faceted]")
        return 2
    source, out = args
    unit = "mm"
    for k, a in enumerate(sys.argv):
        if a == "--unit" and k + 1 < len(sys.argv):
            unit = sys.argv[k + 1]
    try:
        parts = S.read_any(source)
    except (OSError, ValueError) as e:
        print(f"no answer: {e}")
        return 1
    if not isinstance(parts, list):
        parts = [(Path(source).stem, parts)]
    try:
        print(write_step(parts, out, name=Path(out).stem, unit=unit,
                         rounds="--faceted" not in sys.argv))
    except (ValueError, OSError) as e:
        print(f"no answer: {e}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
