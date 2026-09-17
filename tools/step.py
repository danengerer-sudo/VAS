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


class Facet:
    """One triangle, straight out, for a face that would not come apart."""

    __slots__ = ("tri",)

    def __init__(self, tri):
        self.tri = tri


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


def _walk_ring(k0, e0, quads, edge_faces):
    """Step from quad to quad across opposite edges until the ring closes.

    A cylinder's wall is a ring of quadrilaterals joined along the edges that
    run the length of it. Leaving a quad by one edge and coming out of the next
    one by the edge opposite is what goes round the cylinder rather than up it,
    so a walk that started up the cylinder runs into the flat end and stops,
    which is how the wrong pair of edges rules itself out.
    """
    seq, rails = [], []
    k, e = k0, e0
    for _ in range(4096):
        pts = quads[k]
        key = _ekey(pts[e], pts[(e + 1) % 4])
        seq.append(k)
        rails.append((pts[e], pts[(e + 1) % 4]))
        nxt = [q for q in edge_faces.get(key, ()) if q != k]
        if len(nxt) != 1 or nxt[0] not in quads:
            return None
        k2 = nxt[0]
        if k2 == k0:
            if key != _ekey(quads[k0][(e0 + 2) % 4], quads[k0][(e0 + 3) % 4]):
                return None               # came back in by the wrong side
            return seq, rails
        if k2 in seq:
            return None                   # a figure of eight, not a ring
        p2 = quads[k2]
        at = None
        for a in range(4):
            if _ekey(p2[a], p2[(a + 1) % 4]) == key:
                at = a
                break
        if at is None:
            return None
        k, e = k2, (at + 2) % 4
    return None


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
    pts = [p for f in faces for L in f.loops for p in L.pts]
    if not pts:
        return 0.0
    return max(max(p[i] for p in pts) - min(p[i] for p in pts) for i in range(3))


def _as_cylinder(faces, seq, rails, close):
    """A ring of quads measured against being a cylinder. None if it is not."""
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
    ends = [_ring_order(L[1], axis, cx, cy, i, j) for L in levels]
    if any(e is None or len(e) != len(seq) for e in ends):
        return None
    for e in ends:
        sides = [S.length(S.sub(e[(k + 1) % len(e)], e[k])) for k in range(len(e))]
        if max(sides) - min(sides) > close:
            return None                   # a circle's sides are all the same
    centre = _on_axis(ends[0][0], _at(cx, cy, 0.0, i, j, axis), axis)
    return centre, axis, radius, abs(levels[1][0] - levels[0][0]), ends


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
    """One end's corners, deduplicated and put in order round the circle."""
    seen, out = set(), []
    for p in pts:
        k = S.snap(p)
        if k in seen:
            continue
        seen.add(k)
        out.append(p)
    out.sort(key=lambda p: math.atan2(p[j] - cy, p[i] - cx))
    return out or None


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


def _facets(tris):
    return [Facet(t) for t in tris]


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
          "a taper, a cylinder cut off at an angle and a sixteen sided star.")
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
