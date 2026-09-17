#!/usr/bin/env python3
"""Solids, as code, so a machine can edit them and a person can read them.

This is the kernel. Everything a part is made of comes from here: a box, a
cylinder, a shape swept from a profile, and the three operations that turn
those into a real component rather than a pile of blocks.

    union        a and b
    difference   a with b taken out of it, which is every hole and slot
    intersect    only where both are

Without difference nothing here can drill a hole, and two real jobs have now
built an assembly of blocks because that is all they could build.

**What this is not.** It works on triangle meshes, not on the analytic
surfaces a commercial kernel uses. That buys a kernel small enough to read in
an afternoon and hold to a volume test. It costs STEP export, because STEP
wants surfaces and this has triangles. Say STL, say GLB, and say so plainly
when somebody asks for STEP.

**Why a mesh kernel can still be trusted.** Because the answers are checkable
against arithmetic done another way. A box is x times y times z. A cylinder
is pi r squared h, approached from below as the tessellation gets finer. A
box with a hole through it is the first minus the second. If the code and the
arithmetic disagree, the code is wrong, and the tests here say so rather than
rendering something plausible.

    python3 tools/solid.py --selftest
"""
import json
import math
import struct
import sys
from pathlib import Path

EPS = 1e-9


# --------------------------------------------------------------- the pieces

class Solid:
    """A closed surface of triangles. Nothing here checks it is closed on the
    way in; check() says whether it is, and every operation is tested to keep
    it that way."""

    __slots__ = ("tris",)

    def __init__(self, tris=None):
        self.tris = list(tris or [])

    def __len__(self):
        return len(self.tris)

    def copy(self):
        return Solid([(a, b, c) for a, b, c in self.tris])

    # ---- what it is like ----

    def volume(self):
        """The signed volume, by the divergence theorem: a sixth of the sum of
        the scalar triple products. Correct for any closed surface whatever
        shape it is, which is why it is the right thing to test against."""
        total = 0.0
        for a, b, c in self.tris:
            total += (a[0] * (b[1] * c[2] - b[2] * c[1])
                      - a[1] * (b[0] * c[2] - b[2] * c[0])
                      + a[2] * (b[0] * c[1] - b[1] * c[0]))
        return total / 6.0

    def area(self):
        total = 0.0
        for a, b, c in self.tris:
            total += length(cross(sub(b, a), sub(c, a))) / 2.0
        return total

    def bounds(self):
        pts = [p for t in self.tris for p in t]
        if not pts:
            raise ValueError("there is nothing in this solid")
        lo = tuple(min(p[i] for p in pts) for i in range(3))
        hi = tuple(max(p[i] for p in pts) for i in range(3))
        return lo, hi, tuple(hi[i] - lo[i] for i in range(3))

    def check(self, tol=1e-6):
        """What is wrong with it, in sentences. Empty means nothing is.

        Watertight and manifold is the bar: every edge used by exactly two
        triangles, each once in each direction. A mesh that fails this may
        still look perfect and will print wrong, slice wrong, and give a
        nonsense volume."""
        if not self.tris:
            return []                     # nothing at all is a fair answer:
                                          # a solid taken out of one that
                                          # contains it leaves nothing
        wrong = []
        edges = {}
        flat = 0
        for a, b, c in self.tris:
            if length(cross(sub(b, a), sub(c, a))) < tol * tol:
                flat += 1
            # Counted even so. A triangle with no area is still a face as far
            # as the edges are concerned, and leaving it out of the count
            # invents holes on either side of it that nothing else can see.
            for u, v in ((a, b), (b, c), (c, a)):
                key = (snap(u), snap(v))
                edges[key] = edges.get(key, 0) + 1
        loose = 0
        for (u, v), n in edges.items():
            if edges.get((v, u), 0) != n:
                loose += 1
        if loose:
            wrong.append(f"{loose} edge(s) are not shared by exactly two "
                         f"triangles, so it is not a closed solid")
        if flat:
            wrong.append(f"{flat} triangle(s) have no area, which nothing "
                         f"downstream should have to make an exception for")
        if self.volume() <= 0:
            wrong.append("the volume is zero or negative, so it is inside out")
        return wrong

    # ---- moving it about ----

    def moved(self, dx=0.0, dy=0.0, dz=0.0):
        return Solid([tuple((p[0] + dx, p[1] + dy, p[2] + dz) for p in t)
                      for t in self.tris])

    def scaled(self, sx=1.0, sy=None, sz=None):
        sy = sx if sy is None else sy
        sz = sx if sz is None else sz
        return Solid([tuple((p[0] * sx, p[1] * sy, p[2] * sz) for p in t)
                      for t in self.tris])

    def turned(self, axis, radians):
        """About an axis through the origin: 0 is x, 1 is y, 2 is z."""
        c, s = math.cos(radians), math.sin(radians)
        def spin(p):
            x, y, z = p
            if axis == 0:
                return (x, y * c - z * s, y * s + z * c)
            if axis == 1:
                return (x * c + z * s, y, -x * s + z * c)
            return (x * c - y * s, x * s + y * c, z)
        return Solid([tuple(spin(p) for p in t) for t in self.tris])


# --------------------------------------------------------------- primitives

def box(x, y, z, at=(0.0, 0.0, 0.0)):
    """A box with one corner at `at`, sides along the axes."""
    if min(x, y, z) <= 0:
        raise ValueError("a box needs three positive sides")
    ox, oy, oz = at
    p = [(ox, oy, oz), (ox + x, oy, oz), (ox + x, oy + y, oz), (ox, oy + y, oz),
         (ox, oy, oz + z), (ox + x, oy, oz + z), (ox + x, oy + y, oz + z),
         (ox, oy + y, oz + z)]
    faces = [(0, 2, 1), (0, 3, 2),          # bottom, facing down
             (4, 5, 6), (4, 6, 7),          # top
             (0, 1, 5), (0, 5, 4),          # front
             (1, 2, 6), (1, 6, 5),          # right
             (2, 3, 7), (2, 7, 6),          # back
             (3, 0, 4), (3, 4, 7)]          # left
    return Solid([(p[a], p[b], p[c]) for a, b, c in faces])


def cylinder(radius, height, segments=64, at=(0.0, 0.0, 0.0), axis=2):
    """A cylinder standing on `at`, along an axis, tessellated to `segments`.

    The tessellation is an approximation and the volume is always a little
    under pi r squared h, by exactly the area of the circle's inscribed
    polygon. Which is a fact the tests use rather than paper over."""
    if radius <= 0 or height <= 0:
        raise ValueError("a cylinder needs a positive radius and height")
    if segments < 3:
        raise ValueError("a cylinder needs at least three segments")
    ring = []
    for i in range(segments):
        a = 2 * math.pi * i / segments
        ring.append((radius * math.cos(a), radius * math.sin(a)))
    tris = []
    for i in range(segments):
        x0, y0 = ring[i]
        x1, y1 = ring[(i + 1) % segments]
        b0, b1 = (x0, y0, 0.0), (x1, y1, 0.0)
        t0, t1 = (x0, y0, height), (x1, y1, height)
        tris.append((b1, b0, (0.0, 0.0, 0.0)))            # bottom fan
        tris.append((t0, t1, (0.0, 0.0, height)))         # top fan
        tris.append((b0, b1, t1))                         # side
        tris.append((b0, t1, t0))
    s = Solid(tris)
    if axis == 0:
        s = s.turned(1, math.pi / 2)
    elif axis == 1:
        s = s.turned(0, -math.pi / 2)
    return s.moved(*at)


def prism(profile, height, at=(0.0, 0.0, 0.0)):
    """A closed 2D profile, in the xy plane, pushed up by `height`.

    The profile must be simple and counter-clockwise. This is how anything
    that is not a box or a cylinder gets made: an L bracket, a slot, a plate
    with a nose on it."""
    pts = [tuple(map(float, p)) for p in profile]
    if len(pts) < 3:
        raise ValueError("a profile needs at least three points")
    if pts[0] == pts[-1]:
        pts = pts[:-1]
    if signed_area(pts) < 0:
        pts = pts[::-1]
    fan = ear_clip(pts)
    tris = []
    for a, b, c in fan:                                   # bottom, facing down
        tris.append(((a[0], a[1], 0.0), (c[0], c[1], 0.0), (b[0], b[1], 0.0)))
    for a, b, c in fan:                                   # top
        tris.append(((a[0], a[1], height), (b[0], b[1], height),
                     (c[0], c[1], height)))
    for i, a in enumerate(pts):                           # the walls
        b = pts[(i + 1) % len(pts)]
        a0, b0 = (a[0], a[1], 0.0), (b[0], b[1], 0.0)
        a1, b1 = (a[0], a[1], height), (b[0], b[1], height)
        tris.append((a0, b0, b1))
        tris.append((a0, b1, a1))
    return Solid(tris).moved(*at)


def signed_area(pts):
    total = 0.0
    for i, (x0, y0) in enumerate(pts):
        x1, y1 = pts[(i + 1) % len(pts)]
        total += x0 * y1 - x1 * y0
    return total / 2.0


def ear_clip(pts):
    """A simple polygon into triangles. Slow and obvious on purpose: a profile
    is tens of points, not thousands, and a clever version that is subtly
    wrong is worse than a plain one that is right."""
    left = list(range(len(pts)))
    out = []
    guard = 0
    while len(left) > 3 and guard < 10000:
        guard += 1
        for k in range(len(left)):
            i0, i1, i2 = left[k - 1], left[k], left[(k + 1) % len(left)]
            a, b, c = pts[i0], pts[i1], pts[i2]
            if cross2(sub2(b, a), sub2(c, b)) <= 0:
                continue                                   # not convex here
            if any(inside2(pts[j], a, b, c)
                   for j in left if j not in (i0, i1, i2)):
                continue                                   # something in the ear
            out.append((a, b, c))
            left.pop(k)
            break
        else:
            break                                          # nothing clippable
    if len(left) == 3:
        out.append(tuple(pts[i] for i in left))
    return out


def sub2(a, b):
    return (a[0] - b[0], a[1] - b[1])


def cross2(a, b):
    return a[0] * b[1] - a[1] * b[0]


def inside2(p, a, b, c):
    d1 = cross2(sub2(b, a), sub2(p, a))
    d2 = cross2(sub2(c, b), sub2(p, b))
    d3 = cross2(sub2(a, c), sub2(p, c))
    return (d1 >= 0 and d2 >= 0 and d3 >= 0) or (d1 <= 0 and d2 <= 0 and d3 <= 0)


# ------------------------------------------------------------- the operations

# Binary space partitioning, which is the standard way to do this on meshes.
# The idea is old and simple: cut every triangle of one solid by the planes of
# the other until each piece is wholly inside or wholly outside, then keep the
# pieces the operation asks for.

class Plane:
    __slots__ = ("normal", "w")

    def __init__(self, normal, w):
        self.normal, self.w = normal, w

    @staticmethod
    def through(a, b, c):
        n = normalise(cross(sub(b, a), sub(c, a)))
        return Plane(n, dot(n, a))

    def flipped(self):
        return Plane((-self.normal[0], -self.normal[1], -self.normal[2]), -self.w)

    def split(self, tri, coplanar_front, coplanar_back, front, back, tol=1e-7):
        """Cut one triangle by this plane, putting the pieces where they go."""
        FRONT, BACK, SPAN = 1, 2, 3
        kinds, total = [], 0
        for p in tri:
            d = dot(self.normal, p) - self.w
            k = FRONT if d > tol else (BACK if d < -tol else 0)
            total |= k
            kinds.append(k)
        if total == 0:
            n = cross(sub(tri[1], tri[0]), sub(tri[2], tri[0]))
            (coplanar_front if dot(self.normal, n) > 0
             else coplanar_back).append(tri)
        elif total == FRONT:
            front.append(tri)
        elif total == BACK:
            back.append(tri)
        else:
            f, b = [], []
            for i in range(3):
                j = (i + 1) % 3
                ti, tj = kinds[i], kinds[j]
                pi, pj = tri[i], tri[j]
                if ti != BACK:
                    f.append(pi)
                if ti != FRONT:
                    b.append(pi)
                if (ti | tj) == SPAN:
                    di = dot(self.normal, pi) - self.w
                    dj = dot(self.normal, pj) - self.w
                    t = di / (di - dj)
                    mid = (pi[0] + (pj[0] - pi[0]) * t,
                           pi[1] + (pj[1] - pi[1]) * t,
                           pi[2] + (pj[2] - pi[2]) * t)
                    f.append(mid)
                    b.append(mid)
            for piece, out in ((f, front), (b, back)):
                for k in range(1, len(piece) - 1):
                    out.append((piece[0], piece[k], piece[k + 1]))


class Node:
    """One cell of the partition: a plane, what lies on it, and the two sides."""

    __slots__ = ("plane", "here", "front", "back")

    def __init__(self, tris=None):
        self.plane = None
        self.here = []
        self.front = None
        self.back = None
        if tris:
            self.build(tris)

    def build(self, tris):
        if not tris:
            return
        if self.plane is None:
            self.plane = Plane.through(*tris[0])
        front, back = [], []
        for t in tris:
            self.plane.split(t, self.here, self.here, front, back)
        if front:
            self.front = self.front or Node()
            self.front.build(front)
        if back:
            self.back = self.back or Node()
            self.back.build(back)

    def all(self):
        out = list(self.here)
        if self.front:
            out += self.front.all()
        if self.back:
            out += self.back.all()
        return out

    def clip(self, tris):
        """Whatever of `tris` is outside this solid."""
        if self.plane is None:
            return list(tris)
        front, back = [], []
        for t in tris:
            self.plane.split(t, front, back, front, back)
        if self.front:
            front = self.front.clip(front)
        back = self.back.clip(back) if self.back else []
        return front + back

    def clip_to(self, other):
        self.here = other.clip(self.here)
        if self.front:
            self.front.clip_to(other)
        if self.back:
            self.back.clip_to(other)

    def invert(self):
        self.here = [(t[2], t[1], t[0]) for t in self.here]
        if self.plane:
            self.plane = self.plane.flipped()
        self.front, self.back = self.back, self.front
        if self.front:
            self.front.invert()
        if self.back:
            self.back.invert()



# ------------------------------------------------------------- putting it right

# Cutting a triangle by a plane splits it and leaves its neighbour whole, so
# the neighbour's edge now has a vertex sitting in the middle of it belonging
# to nobody. A T junction. The surface is closed in the sense that its volume
# is right, and it is not closed in the sense that matters to a slicer, a
# printer, or anything that walks the edges. Every boolean here ends by
# putting them right.

def weld(tris, tol=1e-7):
    """One position per place, so two corners that are the same corner are."""
    places = max(0, int(round(-math.log10(tol))))
    out = []
    for a, b, c in tris:
        t = (snap(a, places), snap(b, places), snap(c, places))
        if (t[0] == t[1] or t[1] == t[2] or t[2] == t[0]):
            continue                                  # collapsed to a line
        # Flat, not small. A triangle whose three corners are on one line has
        # no area however far apart they are, contributes nothing to the
        # volume, and puts a third face on an edge that should have two, which
        # reads as a fault forever. Judged against its own size rather than
        # against a fixed number, so a part modelled in metres and the same
        # part in millimetres are treated the same: a real triangle has an
        # area near a quarter of its longest side squared, a collinear one has
        # none at all.
        longest = max(length(sub(t[1], t[0])), length(sub(t[2], t[1])),
                      length(sub(t[0], t[2])))
        # Only a triangle with no width at all. Deleting the merely thin ones
        # is worse than keeping them: their edges are shared with proper faces
        # either side, so taking one away leaves a hole exactly its own shape,
        # and filling that hole puts back a triangle just as thin. A zero area
        # face contributes nothing to the volume and keeps the edges paired,
        # which is the property everything downstream depends on.
        if longest <= 0 or length(cross(sub(t[1], t[0]),
                                        sub(t[2], t[0]))) <= 1e-12 * longest * longest:
            continue
        out.append(t)

    # One face per place. The partition can emit the same coplanar triangle
    # several times over, and a face that appears nine times has eight edges
    # with no partner, which reads as a hole and is the opposite of one. A
    # face that appears once each way round is an internal wall between two
    # pieces that are now one piece, and both copies go.
    net = {}
    for t in out:
        key = _facing(t)
        flip = _facing((t[0], t[2], t[1]))
        if flip in net:
            net[flip] -= 1
            if net[flip] == 0:
                del net[flip]
        else:
            net[key] = net.get(key, 0) + 1
    kept = []
    for key, n in net.items():
        # However many are left, not one of them. Keeping a single copy of a
        # face that turns up twice the same way round quietly takes an edge
        # from three users to two and calls that tidy, which turns a fault
        # somewhere upstream into a fault here instead of showing it.
        if n > 0:
            kept.extend([key] * n)
        elif n < 0:
            kept.extend([(key[0], key[2], key[1])] * (-n))
    return kept


def _facing(t):
    """The same triangle written the same way every time, keeping its winding,
    so two copies of one face compare equal."""
    i = t.index(min(t))
    return (t[i], t[(i + 1) % 3], t[(i + 2) % 3])


def _on_edge(p, a, b, tol):
    """Is p strictly between a and b, and on the line."""
    if p == a or p == b:
        return False
    ab, ap = sub(b, a), sub(p, a)
    n = length(ab)
    if n < tol:
        return False
    t = dot(ap, ab) / (n * n)
    if t <= tol or t >= 1 - tol:
        return False
    near = (a[0] + ab[0] * t, a[1] + ab[1] * t, a[2] + ab[2] * t)
    return length(sub(p, near)) <= tol


def open_edges(tris):
    """The edges used once instead of twice. These, and only these, are where
    a T junction can be."""
    used = {}
    for t in tris:
        for i in range(3):
            u, v = t[i], t[(i + 1) % 3]
            used[(u, v)] = used.get((u, v), 0) + 1
    return {e for e, n in used.items() if used.get((e[1], e[0]), 0) != n}


def heal(tris, tol=1e-7, rounds=8):
    """Split the broken edges that have a vertex sitting in the middle of them.

    Only the broken ones. The first version looked at every edge of every
    triangle against every nearby vertex, which on a plate with a hundred and
    twenty eight segment hole is millions of comparisons for the sake of a few
    hundred real faults, and took longer than anybody would wait. An edge that
    already has a partner running the other way is not broken and does not
    need looking at.

    Repeated, because splitting a triangle makes new edges which may
    themselves have vertices on them."""
    tris = weld(tris, tol)
    for _ in range(rounds):
        bad = open_edges(tris)
        if not bad:
            break
        # Every vertex, not only the ends of the broken edges. The vertex
        # sitting in the middle of a broken edge almost always belongs to the
        # triangle on the other side, whose own edges are perfectly fine, so
        # looking only at the broken ends finds nothing and the fault stays.
        # Testing is still only over the broken edges, which is what keeps it
        # quick.
        loose = sorted({p for t in tris for p in t})
        if not loose:
            break
        lo = [min(v[i] for v in loose) for i in range(3)]
        hi = [max(v[i] for v in loose) for i in range(3)]
        span = max(hi[i] - lo[i] for i in range(3)) or 1.0
        cell = span / 32.0
        grid = {}
        for v in loose:
            key = tuple(int((v[i] - lo[i]) / cell) for i in range(3))
            grid.setdefault(key, []).append(v)

        def candidates(a, b):
            k0 = [int((a[i] - lo[i]) / cell) for i in range(3)]
            k1 = [int((b[i] - lo[i]) / cell) for i in range(3)]
            found = []
            for x in range(min(k0[0], k1[0]) - 1, max(k0[0], k1[0]) + 2):
                for y in range(min(k0[1], k1[1]) - 1, max(k0[1], k1[1]) + 2):
                    for z in range(min(k0[2], k1[2]) - 1, max(k0[2], k1[2]) + 2):
                        found += grid.get((x, y, z), ())
            return found

        out, split_any = [], False
        for tri in tris:
            done = False
            for i in range(3):
                a, b, c = tri[i], tri[(i + 1) % 3], tri[(i + 2) % 3]
                if (a, b) not in bad:
                    continue
                hits = [q for q in candidates(a, b) if _on_edge(q, a, b, tol)]
                if not hits:
                    continue
                ab = sub(b, a)
                n2 = dot(ab, ab)
                hits.sort(key=lambda q: dot(sub(q, a), ab) / n2)
                chain = [a] + hits + [b]
                for k in range(len(chain) - 1):
                    out.append((chain[k], chain[k + 1], c))
                done = split_any = True
                break
            if not done:
                out.append(tri)
        tris = weld(out, tol)
        if not split_any:
            break
    return tris


def fill_holes(tris, most=64):
    """Close whatever is still open, by chaining the loose edges into loops and
    filling each one.

    After splitting the T junctions there can still be the odd hole the shape
    of a single triangle, left where two cuts landed a thousandth apart. The
    loop around a hole is the hole, and filling it with a fan is exactly right
    for the small ones, which is all that are ever left. A loop longer than
    `most` is not a rounding fault and is left alone rather than covered with
    a lid that might be wrong.
    """
    out = list(tris)
    for _ in range(8):
        bad = open_edges(out)
        if not bad:
            break
        # One walk per loop, consuming edges as it goes, so a walk that fails
        # cannot leave the rest unreachable.
        following = {}
        for u, v in bad:
            following.setdefault(u, []).append(v)
        filled = False
        while following:
            here = next(iter(following))
            start_at = here
            loop = [here]
            while True:
                nexts = following.get(here)
                if not nexts:
                    break
                step = nexts.pop()
                if not nexts:
                    del following[here]
                if step == start_at:
                    if len(loop) >= 3:
                        # The other way round. The loop runs the way the faces
                        # around the hole run, so a lid wound the same way
                        # repeats every edge of the hole instead of answering
                        # it, and the hole is left exactly as open as it was
                        # with a lid lying on top of it. It took a tube to
                        # notice: on a plate the healing had already closed
                        # everything and this never had a hole to get wrong.
                        for k in range(1, len(loop) - 1):
                            out.append((loop[0], loop[k + 1], loop[k]))
                        filled = True
                    break
                if step in loop or len(loop) >= most:
                    break
                loop.append(step)
                here = step
        if not filled:
            break
    return out


# ------------------------------------------------- one face instead of many

# A boolean leaves the top of a plate as several hundred slivers, because every
# plane of the drill cut it again on the way through. They are all the same
# face. Putting them back together is worth doing twice over: the model comes
# out the size a person would expect, and the sliver whose three corners are
# within a rounding error of a straight line stops existing rather than being
# nursed along.
#
# The method is the one a draughtsman would use. Take every triangle lying on
# one plane. An edge shared by two of them is inside the face and is no part of
# its outline, so the edges left over once the shared ones have cancelled are
# the outline: the outside of the face, and a loop around each hole in it. Then
# drop the corners that are not corners, which are the ones sitting in the
# middle of a straight run. Then fill each outline once.
#
# The one thing that must not happen is a corner disappearing from one face
# while the face next door keeps it, because that is a T junction and it is
# exactly the fault this is meant to cure. So a corner goes only when every
# face that has it agrees it is not a corner.
#
# And the answer is checked before it is accepted, face by face: the area it
# fills must be the area of the fragments it replaces, or the fragments are
# kept and nothing is claimed.


def _frame(n):
    """Two axes to read a plane's points in, right handed about its normal, so
    that counter clockwise on the flat means facing the way the face faces."""
    ax = max(range(3), key=lambda i: abs(n[i]))
    i, j = (1, 2) if ax == 0 else ((2, 0) if ax == 1 else (0, 1))
    if n[ax] < 0:
        i, j = j, i
    return i, j


def _wobble(tri, tol):
    """How far out this triangle's normal could be, in radians.

    A long thin fragment is the problem. Its corners are known to a rounding
    error like everything else, but the shorter its height the more that error
    swings the normal about: a sliver a hundredth wide and ten long has a
    normal that can be a degree out, and grouping faces by their normals
    without knowing that puts the fragments of one face on twenty planes."""
    longest = max(length(sub(tri[1], tri[0])), length(sub(tri[2], tri[1])),
                  length(sub(tri[0], tri[2])))
    twice = length(cross(sub(tri[1], tri[0]), sub(tri[2], tri[0])))
    if twice <= 0:
        return math.pi
    return tol * longest / twice


def _by_plane(tris, tol):
    """Every triangle, sorted into the flat faces they belong to.

    Biggest first, so that the triangle a plane is remembered by is the one
    whose normal is worth remembering. A face whose plane was taken from one of
    its own slivers is a face whose other fragments do not match it."""
    planes, index, groups = [], {}, []
    for t in sorted(tris, key=lambda t: -_tri_area(t)):
        n = normalise(cross(sub(t[1], t[0]), sub(t[2], t[0])))
        loose = _wobble(t, tol) > 1e-5
        key = tuple(int(math.floor(c * 200)) for c in n)
        pid = None
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for dz in (-1, 0, 1):
                    for k in index.get((key[0] + dx, key[1] + dy, key[2] + dz), ()):
                        pn, pw = planes[k]
                        # A fragment whose normal cannot be trusted is placed by
                        # where its corners are and which way it faces, which is
                        # all that can honestly be asked of it.
                        if dot(pn, n) <= (0.0 if loose else 1 - 1e-5):
                            continue
                        if max(abs(dot(pn, p) - pw) for p in t) <= tol:
                            pid = k
                            break
                    if pid is not None:
                        break
                if pid is not None:
                    break
            if pid is not None:
                break
        if pid is None:
            planes.append((n, dot(n, t[0])))
            groups.append([])
            index.setdefault(key, []).append(len(planes) - 1)
            pid = len(planes) - 1
        groups[pid].append(t)
    return list(zip(planes, groups))


def _next_around(prev, here, choices, i, j):
    """Where the outline goes next when more than one edge leaves a corner.

    Two loops can meet at a point, and taking the wrong one there joins two
    separate outlines into a figure of eight. The turn to take is the tightest
    one available going clockwise, which keeps the face on the left and keeps
    each loop to itself."""
    if len(choices) == 1 or prev is None:
        return choices[0]
    back = (prev[i] - here[i], prev[j] - here[j])
    best, turn = None, None
    for v in choices:
        d = (v[i] - here[i], v[j] - here[j])
        a = math.atan2(cross2(back, d), back[0] * d[0] + back[1] * d[1])
        cw = (-a) % (2 * math.pi)
        if cw <= 1e-12:
            cw = 2 * math.pi              # straight back the way we came, last
        if turn is None or cw < turn:
            best, turn = v, cw
    return best


def _outlines(group, n):
    """The outline of a set of coplanar triangles: the edges that were not
    shared, walked into loops. None if they will not walk."""
    i, j = _frame(n)
    count = {}
    for t in group:
        for k in range(3):
            e = (t[k], t[(k + 1) % 3])
            count[e] = count.get(e, 0) + 1
    out = {}
    for (u, v), many in count.items():
        spare = many - count.get((v, u), 0)
        if spare > 0:
            out.setdefault(u, []).extend([v] * spare)
    loops = []
    guard = sum(len(v) for v in out.values()) + 8
    while out:
        here = next(iter(out))
        start, prev, loop = here, None, [here]
        while True:
            choices = out.get(here)
            if not choices:
                return None               # the outline does not close
            step = _next_around(prev, here, choices, i, j)
            choices.remove(step)
            if not choices:
                del out[here]
            if step == start:
                break
            if len(loop) > guard:
                return None
            loop.append(step)
            prev, here = here, step
        if len(loop) >= 3:
            loops.append(loop)
    return loops or None


def _straight_at(before, here, after, tol):
    """Is this corner not a corner: how far the surface would move if it went.

    Measured as the distance from the corner to the line that would replace it,
    not as the angle between the two runs. The angle is the wrong thing to ask
    about: two corners a thousandth apart on one straight edge make an angle
    that a rounding error can swing right round, and the run reads as a bend
    when nothing has bent. The distance does not care how short the runs are."""
    a, b = sub(here, before), sub(after, here)
    if length(a) <= 0 or length(b) <= 0:
        return False
    if dot(a, b) <= 0:                    # doubling back is not a straight run
        return False
    span = sub(after, before)
    n = length(span)
    if n <= 0:
        return False
    return length(cross(a, span)) / n <= tol


def _straighten(outlines, pinned, tol):
    """Drop the corners that every face agrees are not corners.

    This is where the triangle count actually falls. The outline of a plate's
    top face comes out of the partition with a hundred and forty corners along
    four straight edges and a circle, and only thirty six of them are corners.
    A corner is only dropped if it turns up in exactly two faces, is a straight
    run in both, and belongs to no face that had to be left as it was, so the
    two faces either side of it stay in step."""
    seen, ok = {}, {}
    for loops in outlines:
        if loops is None:
            continue
        for loop in loops:
            for k, v in enumerate(loop):
                seen[v] = seen.get(v, 0) + 1
                fine = _straight_at(loop[k - 1], v, loop[(k + 1) % len(loop)], tol)
                ok[v] = ok.get(v, True) and fine
    # Two faces, or one. Two is the ordinary case: a corner in the middle of
    # an edge, and both faces either side of it agree it is not a corner. One
    # is a corner that only one face has ever heard of, which is a T junction
    # that got past the healing, and dropping it is the repair rather than a
    # risk: it is on a straight run, so the face does not change shape, and the
    # face next door stops having a corner poking into its edge.
    drop = {v for v, many in seen.items()
            if many <= 2 and ok.get(v) and v not in pinned}
    if not drop:
        return outlines
    out = []
    for loops in outlines:
        if loops is None:
            out.append(None)
            continue
        shorter = []
        for loop in loops:
            kept = [v for v in loop if v not in drop]
            if len(kept) >= 3:
                shorter.append(kept)
            # Fewer than three corners left is a loop with no area: a fold,
            # where the partition laid a scrap of one face back over itself.
            # It goes, and so does the matching notch in the face it was
            # folded off, because the corners that made the notch have just
            # been dropped from that face too. Putting it back instead, which
            # is the cautious looking thing to do, leaves the two faces
            # disagreeing about a corner, which is the one thing here that
            # must never happen.
        out.append(shorter)
    return out


def _area2(poly):
    total = 0.0
    for k, (x0, y0) in enumerate(poly):
        x1, y1 = poly[(k + 1) % len(poly)]
        total += x0 * y1 - x1 * y0
    return total / 2.0


def _inside_loop(p, poly):
    x, y = p
    inside = False
    for k in range(len(poly)):
        a, b = poly[k], poly[(k + 1) % len(poly)]
        if (a[1] > y) != (b[1] > y):
            t = (y - a[1]) / (b[1] - a[1])
            if x < a[0] + (b[0] - a[0]) * t:
                inside = not inside
    return inside


def _join_hole(o2, o3, h2, h3):
    """Cut a channel from an outline to a hole in it, so that what is left is
    one loop an ear clip can fill. The standard construction: from the hole's
    rightmost corner look right, take the first edge of the outline that is
    hit, and go to whichever of its ends can be seen from there."""
    m = max(range(len(h2)), key=lambda k: (h2[k][0], h2[k][1]))
    mx, my = h2[m]
    hit, n = None, len(o2)
    for k in range(n):
        a, b = o2[k], o2[(k + 1) % n]
        if (a[1] > my) == (b[1] > my):
            continue
        x = a[0] + (b[0] - a[0]) * (my - a[1]) / (b[1] - a[1])
        if x < mx - 1e-12:
            continue
        if hit is None or x < hit[0]:
            hit = (x, k)
    if hit is None:
        return None                       # the hole is not in this outline
    x, k = hit
    pick = k if o2[k][0] > o2[(k + 1) % n][0] else (k + 1) % n
    # A corner of the outline poking into the channel would be cut off by it.
    # If one does, go to that corner instead: the one nearest straight ahead.
    look = ((mx, my), (x, my), o2[pick])
    closest = None
    for q in range(n):
        if q == pick:
            continue
        v, before, after = o2[q], o2[q - 1], o2[(q + 1) % n]
        if cross2(sub2(v, before), sub2(after, v)) >= 0:
            continue                      # a convex corner cannot be in the way
        if not inside2(v, *look):
            continue
        dx, dy = v[0] - mx, v[1] - my
        ahead = abs(dy) / (math.hypot(dx, dy) or 1.0)
        if closest is None or ahead < closest:
            closest, pick = ahead, q
    return (o2[:pick + 1] + h2[m:] + h2[:m] + [h2[m]] + o2[pick:],
            o3[:pick + 1] + h3[m:] + h3[:m] + [h3[m]] + o3[pick:])


def _ears(poly):
    """A simple polygon into triangles, by index. None if it will not go.

    Unlike `ear_clip` this one expects a polygon that has had its holes joined
    on, so the same corner appears in it more than once and a corner sitting
    exactly on an edge is ordinary. A corner in the same place as one of the
    ear's own corners is not inside the ear."""
    left = list(range(len(poly)))
    out, guard, limit = [], 0, len(poly) * len(poly) + 16
    while len(left) > 3:
        guard += 1
        if guard > limit:
            return None
        for k in range(len(left)):
            i0, i1, i2 = left[k - 1], left[k], left[(k + 1) % len(left)]
            a, b, c = poly[i0], poly[i1], poly[i2]
            if cross2(sub2(b, a), sub2(c, b)) <= 0:
                continue                                  # not a convex corner
            blocked = False
            for q in left:
                if q in (i0, i1, i2):
                    continue
                p = poly[q]
                if p == a or p == b or p == c:
                    continue
                if inside2(p, a, b, c):
                    blocked = True
                    break
            if blocked:
                continue
            out.append((i0, i1, i2))
            left.pop(k)
            break
        else:
            return None
    if len(left) == 3:
        out.append(tuple(left))
    return out


def _tri_area(t):
    return length(cross(sub(t[1], t[0]), sub(t[2], t[0]))) / 2.0


def _fill_face(loops, n, group):
    """One flat face's outline, filled as one face. None rather than a guess."""
    if not loops:
        return []                         # the whole face was a fold
    i, j = _frame(n)
    flat = [[(p[i], p[j]) for p in loop] for loop in loops]
    areas = [_area2(f) for f in flat]
    if any(a == 0.0 for a in areas):
        return None                       # a loop with no area; do not guess
    outer = [k for k, a in enumerate(areas) if a > 0]
    holes = [k for k, a in enumerate(areas) if a < 0]
    if not outer:
        return None
    mine = {k: [] for k in outer}
    for h in holes:
        owner = None
        for k in outer:
            if _inside_loop(flat[h][0], flat[k]) and (
                    owner is None or areas[k] < areas[owner]):
                owner = k
        if owner is None:
            return None                   # a hole in nothing
        mine[owner].append(h)
    made = []
    for k in outer:
        poly2, poly3 = list(flat[k]), list(loops[k])
        for h in sorted(mine[k], key=lambda h: -max(p[0] for p in flat[h])):
            joined = _join_hole(poly2, poly3, flat[h], loops[h])
            if joined is None:
                return None
            poly2, poly3 = joined
        fan = _ears(poly2)
        if fan is None:
            return None
        for a, b, c in fan:
            made.append((poly3[a], poly3[b], poly3[c]))
    was = sum(_tri_area(t) for t in group)
    now = sum(_tri_area(t) for t in made)
    if abs(now - was) > 1e-6 * max(1.0, was):
        return None                       # not the same face; keep what worked
    return made


def merge_coplanar(tris, tol=1e-6):
    """Fragments of one flat face, put back as one face, everywhere they are.

    A face that will not come apart into an outline, or that fills to a
    different area than it had, is left exactly as it was and its corners are
    pinned so that its neighbours keep them too. So this can only ever tidy,
    and never lose."""
    groups = _by_plane(tris, tol)
    outlines = [_outlines(g, pl[0]) for pl, g in groups]
    made = [None] * len(groups)
    for _ in range(4):
        pinned = set()
        for k, (_pl, g) in enumerate(groups):
            if outlines[k] is None:
                pinned.update(p for t in g for p in t)
        short = _straighten(outlines, pinned, tol)
        trouble = []
        for k, (pl, g) in enumerate(groups):
            if short[k] is None:
                made[k] = None
                continue
            made[k] = _fill_face(short[k], pl[0], g)
            if made[k] is None:
                trouble.append(k)
        if not trouble:
            break
        for k in trouble:
            outlines[k] = None
    out = []
    for k, (_pl, g) in enumerate(groups):
        out += made[k] if made[k] is not None else g
    return out


def fuse_points(tris, at=1e-6):
    """Corners closer together than the part's own resolution are one corner.

    Hundreds of plane cuts through one face now and then leave a triangle a few
    millionths of a millimetre across on a part twenty millimetres long. It is
    a point, not a face. Left alone it is a speck that every check has to make
    an exception for, and an exception in a check is how a real fault gets
    through. Pulling its corners together onto one corner deletes it, and
    deletes the triangle on the other side of the edge it stood on, and the
    edges left over pair up with each other, which is the ordinary edge
    collapse and leaves the surface as closed as it found it.
    """
    lo, hi = _aabb(tris)
    span = max(hi[i] - lo[i] for i in range(3)) or 1.0
    speck = span * at
    same = {}
    for t in tris:
        if max(length(sub(t[1], t[0])), length(sub(t[2], t[1])),
               length(sub(t[0], t[2]))) > speck:
            continue
        for p in t[1:]:
            same[p] = t[0]
    if not same:
        return tris

    def settled(p):
        for _ in range(8):
            q = same.get(p, p)
            if q == p:
                return p
            p = q
        return p

    return [tuple(settled(p) for p in t) for t in tris]


def settle(tris, tol=1e-7):
    """Put a set of triangles in order, in the one sequence that works.

    Healing, fusing and welding all take triangles away or cut them up, and
    putting a lid on a hole is the only step that puts one back, so the lid
    goes on last and nothing runs after it that could take it off. Weld after
    filling and a lid with no width, which is exactly the lid a nearly straight
    hole needs, is thrown away again and the model is as open as it was with
    more steps in between to hide it.

    No test here depends on that order, because the healing deals with the
    holes that would show it up. The order stays because the way it fails is
    silent: the model comes out looking right and reading as open."""
    tris = heal(tris, tol)
    tris = fuse_points(tris)
    tris = weld(tris, tol)
    return fill_holes(tris)


def tidy(solid, tol=1e-7):
    """Every operation ends here, so what comes out is a solid rather than a
    picture of one.

    Settle the fragments first, because putting a face back together needs its
    fragments to agree about where their edges are. Then put the faces back
    together, and settle again, which is quick once there are hundreds of
    triangles instead of thousands.

    The merge is only kept if the volume is the volume it was. That is the
    whole guarantee: a tidier mesh that is a different shape is a bug, and this
    is the one check that cannot be fooled by geometry that looks right."""
    tris = settle(solid.tris, tol)
    plain = settle(merge_coplanar(tris, tol * 10), tol)
    return Solid(plain if _worth_keeping(tris, plain) else tris)


def _worth_keeping(tris, plain, tol=1e-6):
    """Is the tidier mesh the same solid, and actually tidier.

    Not a formality. Everything the merge does is geometry, and geometry that
    is nearly right looks exactly right in a picture. The volume of a closed
    surface does not care what it looks like."""
    was, now = Solid(tris).volume(), Solid(plain).volume()
    if abs(now - was) > tol * max(1.0, abs(was)):
        return False
    return len(plain) <= len(tris)


def _aabb(tris):
    lo = [1e30, 1e30, 1e30]
    hi = [-1e30, -1e30, -1e30]
    for t in tris:
        for p in t:
            for i in range(3):
                if p[i] < lo[i]:
                    lo[i] = p[i]
                if p[i] > hi[i]:
                    hi[i] = p[i]
    return lo, hi


def _split_by_box(tris, lo, hi, pad=1e-6):
    """Triangles that reach into that box, and those that cannot.

    A plate is twelve triangles and a drill is five hundred, and cutting all
    twelve against all five hundred planes made sixty one thousand fragments
    for one hole. A triangle nowhere near the other solid cannot be cut by it
    and does not need to go through the machinery: it comes out exactly as it
    went in, which keeps the model the size a person would expect and keeps
    the faces whole."""
    near, far = [], []
    for t in tris:
        tl = [min(p[i] for p in t) for i in range(3)]
        th = [max(p[i] for p in t) for i in range(3)]
        if all(tl[i] <= hi[i] + pad and th[i] >= lo[i] - pad for i in range(3)):
            near.append(t)
        else:
            far.append(t)
    return near, far


def _apart(alo, ahi, blo, bhi, pad=1e-9):
    """Nowhere near each other, so no operation has anything to work out."""
    return any(ahi[i] < blo[i] - pad or bhi[i] < alo[i] - pad for i in range(3))


def _near_parts(a, b, alo, ahi, blo, bhi):
    """The triangles each solid needs to put through the partition, and the
    ones it can keep untouched.

    A triangle of `a` that does not reach into `b`'s box cannot be cut by `b`
    and comes out exactly as it went in. But if that leaves nothing to cut, it
    does not follow that nothing happens: one solid can be wholly inside the
    other, touching none of its triangles, and still change it completely.
    Reading an empty list as `they do not touch` is how a block swallowed a
    cavity and reported itself solid."""
    amid, afar = _split_by_box(a.tris, blo, bhi)
    bmid, bfar = _split_by_box(b.tris, alo, ahi)
    if not amid or not bmid:
        return a.tris, [], b.tris, []
    return amid, afar, bmid, bfar


def union(a, b):
    """Everything in either."""
    alo, ahi = _aabb(a.tris)
    blo, bhi = _aabb(b.tris)
    if _apart(alo, ahi, blo, bhi):
        return tidy(Solid(a.tris + b.tris))     # they do not touch
    amid, afar, bmid, bfar = _near_parts(a, b, alo, ahi, blo, bhi)
    x, y = Node(amid), Node(bmid)
    x.clip_to(y)
    y.clip_to(x)
    y.invert()
    y.clip_to(x)
    y.invert()
    x.build(y.all())
    return tidy(Solid(afar + bfar + x.all()))


def difference(a, b):
    """What is left of `a` once `b` is taken out. Every hole is this."""
    alo, ahi = _aabb(a.tris)
    blo, bhi = _aabb(b.tris)
    if _apart(alo, ahi, blo, bhi):
        return tidy(Solid(a.tris))              # nothing to take out
    amid, afar, bmid, _bfar = _near_parts(a, b, alo, ahi, blo, bhi)
    x, y = Node(amid), Node(bmid)
    x.invert()
    x.clip_to(y)
    y.clip_to(x)
    y.invert()
    y.clip_to(x)
    y.invert()
    x.build(y.all())
    x.invert()
    return tidy(Solid(afar + x.all()))


def intersect(a, b):
    """Only where both are."""
    x, y = Node(a.tris), Node(b.tris)
    x.invert()
    y.clip_to(x)
    y.invert()
    x.clip_to(y)
    y.clip_to(x)
    x.build(y.all())
    x.invert()
    return tidy(Solid(x.all()))


# ------------------------------------------------------------------- export

def write_glb(parts, path, name="assembly"):
    """An assembly out to one GLB, each part a named node of its own.

    An STL is one anonymous heap of triangles, which is why a viewer given one
    can show you the thing and nothing else. A GLB keeps the parts apart and
    keeps their names, so the same viewer can hide the cover to look under it,
    and a bill of materials has something to be a bill of.

    `parts` is a list of (name, solid), in the order they should be listed.
    """
    if not parts:
        raise ValueError("an assembly with nothing in it is not an assembly")
    blob = bytearray()
    views, accessors, meshes, nodes = [], [], [], []

    def chunk(data, target):
        while len(blob) % 4:
            blob.append(0)
        views.append({"buffer": 0, "byteOffset": len(blob),
                      "byteLength": len(data), "target": target})
        blob.extend(data)
        return len(views) - 1

    for label, solid in parts:
        if not solid.tris:
            continue
        pos, nrm, idx = bytearray(), bytearray(), bytearray()
        lo = [1e30] * 3
        hi = [-1e30] * 3
        for k, (a, b, c) in enumerate(solid.tris):
            n = normalise(cross(sub(b, a), sub(c, a)))
            for q in (a, b, c):
                pos += struct.pack("<3f", *q)
                nrm += struct.pack("<3f", *n)
                for i in range(3):
                    lo[i] = min(lo[i], q[i])
                    hi[i] = max(hi[i], q[i])
            idx += struct.pack("<3I", k * 3, k * 3 + 1, k * 3 + 2)
        count = len(solid.tris) * 3
        # Flat shaded on purpose: a corner of a machined part belongs to faces
        # pointing different ways, and averaging those normals rounds the
        # corner off in the picture. A part should look like it was made, not
        # like it was blown up.
        accessors.append({"bufferView": chunk(pos, 34962), "componentType": 5126,
                          "count": count, "type": "VEC3", "min": lo, "max": hi})
        accessors.append({"bufferView": chunk(nrm, 34962), "componentType": 5126,
                          "count": count, "type": "VEC3"})
        # Whole numbers four bytes wide, because a part of any size at all goes
        # straight past what two bytes can count to.
        accessors.append({"bufferView": chunk(idx, 34963), "componentType": 5125,
                          "count": count, "type": "SCALAR"})
        meshes.append({"name": label, "primitives": [{
            "attributes": {"POSITION": len(accessors) - 3,
                           "NORMAL": len(accessors) - 2},
            "indices": len(accessors) - 1, "material": 0}]})
        nodes.append({"name": label, "mesh": len(meshes) - 1})

    while len(blob) % 4:
        blob.append(0)
    doc = {"asset": {"version": "2.0", "generator": "tools/solid.py"},
           "scene": 0,
           "scenes": [{"name": name, "nodes": list(range(len(nodes)))}],
           "nodes": nodes, "meshes": meshes,
           "materials": [{"name": "Steel", "pbrMetallicRoughness": {
               "baseColorFactor": [0.69, 0.71, 0.74, 1.0],
               "metallicFactor": 0.55, "roughnessFactor": 0.45}}],
           "accessors": accessors, "bufferViews": views,
           "buffers": [{"byteLength": len(blob)}]}
    js = json.dumps(doc, separators=(",", ":")).encode("utf-8")
    js += b" " * ((4 - len(js) % 4) % 4)
    out = bytearray()
    out += struct.pack("<III", 0x46546C67, 2, 12 + 8 + len(js) + 8 + len(blob))
    out += struct.pack("<II", len(js), 0x4E4F534A) + js
    out += struct.pack("<II", len(blob), 0x004E4942) + bytes(blob)
    Path(path).write_bytes(out)
    return len(out)


def read_glb(path):
    """Back out again: [(name, Solid)], so what was written can be checked
    against what was meant rather than taken on trust."""
    raw = Path(path).read_bytes()
    if len(raw) < 12 or struct.unpack_from("<I", raw, 0)[0] != 0x46546C67:
        raise ValueError("that is not a GLB")
    at, doc, blob = 12, None, b""
    while at + 8 <= len(raw):
        size, kind = struct.unpack_from("<II", raw, at)
        body = raw[at + 8:at + 8 + size]
        if kind == 0x4E4F534A:
            doc = json.loads(body.decode("utf-8"))
        elif kind == 0x004E4942:
            blob = body
        at += 8 + size + ((4 - size % 4) % 4)
    if doc is None:
        raise ValueError("that GLB has no scene in it")

    def read(index):
        acc = doc["accessors"][index]
        view = doc["bufferViews"][acc["bufferView"]]
        start = view.get("byteOffset", 0) + acc.get("byteOffset", 0)
        wide = {5126: ("<f", 4), 5125: ("<I", 4), 5123: ("<H", 2)}[acc["componentType"]]
        each = {"VEC3": 3, "SCALAR": 1}[acc["type"]]
        out = []
        for i in range(acc["count"]):
            row = [struct.unpack_from(wide[0], blob,
                                      start + (i * each + k) * wide[1])[0]
                   for k in range(each)]
            out.append(tuple(row) if each > 1 else row[0])
        return out

    parts = []
    for node in doc.get("nodes", []):
        if "mesh" not in node:
            continue
        tris = []
        for prim in doc["meshes"][node["mesh"]].get("primitives", []):
            pos = read(prim["attributes"]["POSITION"])
            idx = read(prim["indices"]) if "indices" in prim else range(len(pos))
            idx = list(idx)
            for i in range(0, len(idx) - 2, 3):
                tris.append((pos[idx[i]], pos[idx[i + 1]], pos[idx[i + 2]]))
        parts.append((node.get("name", "part"), Solid(tris)))
    return parts


def write_stl(solid, path, name="part"):
    """Binary STL, which is what a printer and a laser cutter want."""
    body = name.encode("ascii", "replace")[:79].ljust(80, b" ")
    body += struct.pack("<I", len(solid.tris))
    for a, b, c in solid.tris:
        n = normalise(cross(sub(b, a), sub(c, a)))
        body += struct.pack("<12fH", n[0], n[1], n[2],
                            a[0], a[1], a[2], b[0], b[1], b[2],
                            c[0], c[1], c[2], 0)
    Path(path).write_bytes(body)
    return len(solid.tris)


# -------------------------------------------------------------------- maths

def sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0])


def dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def length(a):
    return math.sqrt(dot(a, a))


def normalise(a):
    n = length(a) or 1.0
    return (a[0] / n, a[1] / n, a[2] / n)


def snap(p, places=7):
    return (round(p[0], places), round(p[1], places), round(p[2], places))


# ----------------------------------------------------------------- the tests

def selftest():
    fail = []

    def near(what, got, want, tol):
        if abs(got - want) > tol:
            fail.append(f"{what}: got {got:.6f}, wanted {want:.6f} "
                        f"(out by {abs(got - want):.6f})")

    # A box is the one shape whose volume nobody can argue with.
    b = box(20.0, 10.0, 4.0)
    near("a box's volume", b.volume(), 800.0, 1e-9)
    near("a box's surface area", b.area(), 2 * (200 + 80 + 40), 1e-9)
    if b.check():
        fail.append(f"a box is not a closed solid: {b.check()}")

    # Moving and turning must not change how big it is.
    near("moving does not change the volume",
         b.moved(5, -3, 11).volume(), 800.0, 1e-9)
    near("turning does not change the volume",
         b.turned(2, 0.7).turned(0, -0.3).volume(), 800.0, 1e-7)
    near("scaling changes it by the product",
         b.scaled(2, 1, 1).volume(), 1600.0, 1e-9)

    # A cylinder approaches pi r squared h from below, and the error is the
    # circle's inscribed polygon, which is arithmetic we can write down.
    for segs in (16, 64, 256):
        c = cylinder(5.0, 10.0, segments=segs)
        want = 0.5 * segs * math.sin(2 * math.pi / segs) * 25.0 * 10.0
        near(f"a cylinder of {segs} segments", c.volume(), want, 1e-6)
        if c.check():
            fail.append(f"a {segs} segment cylinder is not closed: {c.check()}")
    coarse = cylinder(5.0, 10.0, segments=16).volume()
    fine = cylinder(5.0, 10.0, segments=256).volume()
    true = math.pi * 25.0 * 10.0
    if not (coarse < fine < true):
        fail.append("the cylinder does not get closer to pi r squared h as it "
                    "gets finer, so the tessellation is wrong")

    # The whole point: a hole in a plate.
    plate = box(20.0, 10.0, 4.0)
    drill = cylinder(2.5, 20.0, segments=128, at=(10.0, 5.0, -5.0))
    holed = difference(plate, drill)
    want = 800.0 - 0.5 * 128 * math.sin(2 * math.pi / 128) * 6.25 * 4.0
    near("a plate with a hole through it", holed.volume(), want, 1e-4)


    # The same two solids joined rather than cut, at the same tessellation.
    # This is the case that found four separate faults nothing else here
    # touched: a lid wound the wrong way round, a weld that thinned a doubled
    # face instead of reporting it, a fold left lying on a face, and a corner
    # that only one of the two faces holding it had ever heard of.
    bossed = union(box(20.0, 10.0, 4.0), drill)
    near("a plate with a bar through it, joined", bossed.volume(),
         800.0 + 0.5 * 128 * math.sin(2 * math.pi / 128) * 6.25 * 16.0, 1e-3)

    # A blind hole: the depth has to matter.
    blind = difference(box(20.0, 10.0, 4.0),
                       cylinder(2.5, 2.0, segments=128, at=(10.0, 5.0, -0.001)))
    taken = 800.0 - blind.volume()
    near("a blind hole takes out only its own depth", taken,
         0.5 * 128 * math.sin(2 * math.pi / 128) * 6.25 * 1.999, 1e-3)

    # Union and intersection, against arithmetic done by hand.
    a1 = box(10.0, 10.0, 10.0)
    a2 = box(10.0, 10.0, 10.0, at=(5.0, 0.0, 0.0))
    both = union(a1, a2)
    near("two overlapping boxes joined", both.volume(), 1500.0, 1e-6)

    shared = intersect(a1, a2)
    near("where two boxes overlap", shared.volume(), 500.0, 1e-6)


    # Things that must not silently do something odd.
    apart = intersect(box(1.0, 1.0, 1.0), box(1.0, 1.0, 1.0, at=(50.0, 0, 0)))
    near("two solids that do not touch intersect in nothing",
         apart.volume(), 0.0, 1e-9)
    same = difference(box(4.0, 4.0, 4.0), box(4.0, 4.0, 4.0))
    near("a solid minus itself is nothing", same.volume(), 0.0, 1e-6)

    # An L bracket from a profile, whose area anybody can work out.
    ell = prism([(0, 0), (60, 0), (60, 10), (10, 10), (10, 50), (0, 50)], 5.0)
    near("an L shaped bracket", ell.volume(), (60 * 10 + 10 * 40) * 5.0, 1e-6)
    if ell.check():
        fail.append(f"a prism is not a closed solid: {ell.check()}")
    near("a profile wound the wrong way comes out the same",
         prism([(0, 50), (10, 50), (10, 10), (60, 10), (60, 0), (0, 0)],
               5.0).volume(), (60 * 10 + 10 * 40) * 5.0, 1e-6)

    # And a part with two holes, which is where a boolean of a boolean can go
    # wrong without anybody noticing.
    part = difference(ell, cylinder(2.0, 20.0, segments=64, at=(50, 5, -5)))
    part = difference(part, cylinder(2.0, 20.0, segments=64, at=(5, 40, -5)))
    circle = 0.5 * 64 * math.sin(2 * math.pi / 64) * 4.0
    near("an L bracket with two holes", part.volume(),
         (60 * 10 + 10 * 40) * 5.0 - 2 * circle * 5.0, 1e-3)


    # Refusals, rather than something strange.
    for what, fn in (("a box with no size", lambda: box(0, 1, 1)),
                     ("a cylinder with no radius", lambda: cylinder(0, 5)),
                     ("a cylinder of two segments", lambda: cylinder(1, 1, segments=2)),
                     ("a profile of two points", lambda: prism([(0, 0), (1, 1)], 1))):
        try:
            fn()
            fail.append(f"{what} was allowed")
        except ValueError:
            pass

    # It writes an STL a slicer will take.
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "part.stl"
        n = write_stl(part, out)
        raw = out.read_bytes()
        if len(raw) != 84 + n * 50:
            fail.append("the STL it writes is not the length an STL should be")
        if struct.unpack_from("<I", raw, 80)[0] != n:
            fail.append("the STL says it has a different number of triangles")

        # And an assembly, which is the thing an STL cannot be: several parts
        # that stay several parts, each with the name somebody gave it, so a
        # viewer can hide one and a bill of materials has something to list.
        # Read straight back and measured again, because a writer that drops a
        # part or puts the corners in the wrong order writes a file that opens
        # perfectly and is not the assembly.
        made = [("Bracket", part), ("Pin", cylinder(2.0, 30.0, segments=24)),
                ("Plate", box(30.0, 30.0, 3.0, at=(0.0, 0.0, -3.0)))]
        asm = Path(td) / "assembly.glb"
        write_glb(made, asm)
        back = read_glb(asm)
        if [nm for nm, _ in back] != [nm for nm, _ in made]:
            fail.append(f"the assembly came back as {[nm for nm, _ in back]}, "
                        f"not the parts that went in")
        for (nm, want), (_, got) in zip(made, back):
            if len(got.tris) != len(want.tris):
                fail.append(f"{nm} came back with {len(got.tris)} triangles "
                            f"instead of {len(want.tris)}")
            near(f"{nm} is the same size coming back as going in",
                 got.volume(), want.volume(), 1e-3 * max(1.0, want.volume()))
            if got.check():
                fail.append(f"{nm} is not a sound solid once it has been "
                            f"through a GLB: {got.check()[0]}")
        try:
            write_glb([], Path(td) / "nothing.glb")
            fail.append("an assembly with nothing in it was written anyway")
        except ValueError:
            pass
        try:
            read_glb(out)
            fail.append("an STL was read as a GLB")
        except ValueError:
            pass

    # ---- the same three operations on shapes that are not a plate ----
    #
    # One shape proved carefully is one shape. What follows is the same
    # machinery on solids that stress different parts of it: a void with no
    # opening, a tube, a slot cut right through, a boss standing proud, a
    # profile that is not a rectangle, and a cut at an angle to everything so
    # that no plane in it is axis aligned.
    #
    # Most of them have no volume anybody can write down in one line, which is
    # the point. Two identities hold for any two solids whatever shape they
    # are, and between them they pin down all three operations:
    #
    #     union and intersection together hold everything both hold
    #     what is left of a after b is a less what they share
    #
    # A kernel that loses a fragment, counts one twice, or leaves a face open
    # breaks one of those, and no hand arithmetic is needed to notice.

    def closed(what, made):
        wrong = made.check()
        if wrong:
            fail.append(f"{what} is not a sound solid: {wrong[0]}")

    turned_bite = box(6.0, 6.0, 6.0, at=(5.0, 5.0, 5.0)).turned(2, 0.4)
    ell30 = prism([(0, 0), (30, 0), (30, 6), (6, 6), (6, 30), (0, 30)], 5.0)
    pairs = [
        ("two boxes overlapping a corner",
         box(10.0, 10.0, 10.0), box(10.0, 10.0, 10.0, at=(5.0, 5.0, 5.0))),
        ("a box wholly inside a box",
         box(10.0, 10.0, 10.0), box(6.0, 6.0, 6.0, at=(2.0, 2.0, 2.0))),
        ("a plate and a drill through it",
         box(10.0, 10.0, 10.0), cylinder(3.0, 20.0, segments=32, at=(5, 5, -5))),
        ("a plate and a boss standing on it",
         box(10.0, 10.0, 10.0), cylinder(3.0, 4.0, segments=24, at=(5, 5, 8))),
        ("a bar and a bore down it",
         cylinder(6.0, 10.0, segments=32), cylinder(3.0, 30.0, segments=32,
                                                    at=(0, 0, -10))),
        ("a block and a slot right through it",
         box(10.0, 10.0, 10.0), box(4.0, 30.0, 4.0, at=(3.0, -10.0, 3.0))),
        ("an L profile and a hole near its corner",
         ell30, cylinder(2.0, 20.0, segments=24, at=(3.0, 3.0, -5.0))),
        ("a block and a bite taken at an angle",
         box(10.0, 10.0, 10.0), turned_bite),
    ]
    for what, one, two in pairs:
        both = union(one, two)
        shared = intersect(one, two)
        less = difference(one, two)
        other = difference(two, one)
        for name, made in ((f"{what}, joined", both),
                           (f"{what}, where they share", shared),
                           (f"{what}, the first less the second", less),
                           (f"{what}, the second less the first", other)):
            closed(name, made)
        size = max(one.volume(), two.volume())
        near(f"{what}: joined and shared hold both of them",
             both.volume() + shared.volume(),
             one.volume() + two.volume(), 1e-5 * size)
        near(f"{what}: the first less the second is the first less what "
             f"they share", less.volume(), one.volume() - shared.volume(),
             1e-5 * size)
        near(f"{what}: the second less the first is the second less what "
             f"they share", other.volume(), two.volume() - shared.volume(),
             1e-5 * size)

    closed("a plate with a hole through it", holed)
    closed("a plate with a bar through it, joined", bossed)
    closed("a plate with a blind hole", blind)
    closed("an L bracket with two holes", part)

    # A void with no way out is the case where a kernel that quietly keeps only
    # the outer shell still passes every other test.
    hollow = difference(box(10.0, 10.0, 10.0), box(6.0, 6.0, 6.0, at=(2, 2, 2)))
    near("a box with a sealed cavity in it", hollow.volume(), 1000.0 - 216.0, 1e-6)
    closed("a box with a sealed cavity in it", hollow)

    # A tube, whose wall is the difference of two inscribed polygons.
    tube = difference(cylinder(6.0, 10.0, segments=32),
                      cylinder(3.0, 30.0, segments=32, at=(0, 0, -10)))
    ring = 0.5 * 32 * math.sin(2 * math.pi / 32) * (36.0 - 9.0) * 10.0
    near("a tube's wall", tube.volume(), ring, 1e-5)
    closed("a tube", tube)

    # One operation after another after another, which is how a real part is
    # made and where an error that is too small to see compounds.
    stack = difference(box(40.0, 20.0, 6.0),
                       box(10.0, 30.0, 3.0, at=(15.0, -5.0, 3.0)))
    stack = union(stack, cylinder(4.0, 10.0, segments=32, at=(6.0, 10.0, 6.0)))
    stack = difference(stack, cylinder(2.0, 40.0, segments=32,
                                       at=(6.0, 10.0, -10.0)))
    pocket = 10.0 * 20.0 * 3.0
    boss = 0.5 * 32 * math.sin(2 * math.pi / 32) * 16.0 * 10.0
    bore = 0.5 * 32 * math.sin(2 * math.pi / 32) * 4.0 * 16.0
    near("a plate with a pocket, a boss and a bore through the boss",
         stack.volume(), 40.0 * 20.0 * 6.0 - pocket + boss - bore, 1e-4)
    closed("a plate with a pocket, a boss and a bore through the boss", stack)

    # ---- each repair on its own, where there is nothing else to credit ----
    #
    # The shapes above exercise everything at once, which is the right way to
    # find faults and the wrong way to prove that any one repair is pulling its
    # weight. These are the three that a finished model no longer shows,
    # because the earlier steps have already dealt with what they are for.

    # A box with one of its twelve faces taken out: three edges with no partner
    # and a hole exactly the shape of that face. Settling has to give the box
    # back, which it only does if the lid is wound against the hole and if
    # nothing that runs afterwards takes the lid off again.
    gapped = box(10.0, 10.0, 10.0).tris
    gapped = gapped[:3] + gapped[4:]
    if len(open_edges(gapped)) != 3:
        fail.append("taking one face off a box did not leave three edges open, "
                    "so this is not testing what it says it is")
    mended = Solid(settle(gapped))
    near("a box with one face taken out and put back", mended.volume(),
         1000.0, 1e-9)
    if mended.check():
        fail.append(f"a hole the shape of one triangle did not close: "
                    f"{mended.check()[0]}")

    # The same face twice the same way round is a fault somewhere upstream.
    # Welding hands back both of them. Keeping one looks tidier and takes the
    # edge count from three users down to two, which is how a fault stops being
    # visible without ever being fixed.
    doubled = box(1.0, 1.0, 1.0).tris[:1] * 2
    if len(weld(doubled)) != 2:
        fail.append("welding a doubled face kept only one of it, which hides "
                    "the doubling rather than showing it")

    # A corner sitting in the middle of an edge, with the face that should
    # have covered the sliver beside it missing: a hole whose three corners lie
    # on one line. Settling has to come back with the box, which it does by
    # splitting the edge rather than by covering the hole with a lid that has
    # no width.
    lid = box(10.0, 10.0, 10.0)
    top = [(0.0, 0.0, 10.0), (10.0, 0.0, 10.0), (10.0, 10.0, 10.0),
           (0.0, 10.0, 10.0)]
    on_the_edge = (5.0, 0.0, 10.0)
    tee = [t for t in lid.tris if not all(abs(q[2] - 10.0) < 1e-12 for q in t)]
    tee += [(on_the_edge, top[1], top[2]), (on_the_edge, top[2], top[3]),
            (on_the_edge, top[3], top[0])]
    if len(open_edges(tee)) != 3:
        fail.append("the hole with no width is not the hole this test means")
    flat_lid = Solid(settle(tee))
    near("a box whose lid has no width", flat_lid.volume(), 1000.0, 1e-9)
    if flat_lid.check():
        fail.append(f"a hole with three corners on one line did not close: "
                    f"{flat_lid.check()[0]}")
    # The last line of defence: a tidier mesh is only kept if it is the same
    # solid. Nothing above can show this working, because nothing above makes
    # it fire. So it is asked directly.
    if _worth_keeping(box(10.0, 10.0, 10.0).tris, box(9.0, 10.0, 10.0).tris):
        fail.append("a tidier mesh that is a different size was kept, which is "
                    "the one thing that check exists to stop")
    if not _worth_keeping(box(10.0, 10.0, 10.0).tris,
                          box(10.0, 10.0, 10.0).tris):
        fail.append("a mesh that is the same solid was thrown away")

    # A corner in the middle of an edge that only one of the two faces holding
    # that edge has ever heard of. It is on a straight run, so dropping it does
    # not change the shape of the face that has it, and it stops poking into
    # the edge of the face that does not.
    lone = (5.0, 0.0, 0.0)
    top = [(0.0, 0.0, 0.0), lone, (10.0, 0.0, 0.0), (10.0, 10.0, 0.0),
           (0.0, 10.0, 0.0)]
    side = [(10.0, 0.0, 0.0), (0.0, 0.0, 0.0), (0.0, 0.0, -10.0),
            (10.0, 0.0, -10.0)]
    tidied = _straighten([[top], [side]], set(), 1e-6)
    if lone in tidied[0][0] or len(tidied[0][0]) != 4:
        fail.append("a corner only one of the two faces knows about was kept, "
                    "which leaves the two faces disagreeing about their edge")
    if len(tidied[1][0]) != 4:
        fail.append("straightening took a real corner off a square")

    # ---- and that it stays a part a person could use ----
    #
    # Every face above is put back together from the fragments the partition
    # left it in. Without that a plate with one hole in it comes out of here as
    # fifty seven thousand triangles, most of them slivers along four straight
    # edges, and the first thing anybody would ask is what went wrong. These
    # are the numbers that say it did not, and they are the test that fails if
    # the putting back together is taken out again.
    if len(holed.tris) > 1200:
        fail.append(f"a plate with one hole in it came to {len(holed.tris)} "
                    f"triangles, which is a mesh nobody would send anywhere")
    if len(stack.tris) > 1200:
        fail.append(f"a plate with a pocket, a boss and a bore came to "
                    f"{len(stack.tris)} triangles")
    if len(box(1.0, 1.0, 1.0).tris) != 12:
        fail.append("a box is not twelve triangles")

    if fail:
        print("SELFTEST FAILED")
        for f in fail:
            print(f"  {f}")
        return 1
    print("selftest ok: a box is x times y times z, a cylinder approaches pi r "
          "squared h from below and gets closer as it gets finer, a plate with "
          "a hole through it is the one minus the other, a blind hole takes out "
          "only its own depth, an L bracket with two holes is the volume you "
          "would work out by hand, a tube's wall is the difference of two "
          "polygons, a sealed cavity is still inside the block, and on eight "
          "pairs of solids that share a corner, a bore, a slot, a boss, a "
          "profile or a cut at an angle to everything, joining and sharing "
          "hold between them exactly what both solids hold.")
    print("             Every one of them comes out closed, every edge shared "
          "by two faces, no triangle without area, and a plate with a hole in "
          "it comes to a few hundred triangles rather than fifty thousand.")
    return 0


def main():
    if "--selftest" in sys.argv:
        return selftest()
    print(__doc__.strip().splitlines()[0])
    print("\n    python3 tools/solid.py --selftest")
    return 0


if __name__ == "__main__":
    sys.exit(main())
