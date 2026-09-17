#!/usr/bin/env python3
"""Will it hold. Linear static stress analysis, in plain Python.

    python3 tools/fea.py --selftest
    python3 tools/fea.py part.stl --fix -z --push +z 0 0 -500 --material 6082

Give it a solid, say which face is bolted down and which way you are pushing,
and it comes back with how far the part moves, how hard the material is
working, and how much of the yield strength that is.

**What it does.** It fills the part with little rectangular bricks, works out
how each one resists being squashed and sheared, and solves the whole lot at
once for the shape the part settles into under load. That is the finite
element method, and for linear elastic material under a load that does not
move, it is the same method a commercial package uses.

**What it is not, said plainly, because a stress number nobody qualifies is
worse than no stress number.**

    It fills the part with bricks on a grid, so a curved or slanted surface
    comes out as a staircase. Stiffness and deflection barely notice. Peak
    stress at a fillet does, and reads low, because the grid rounds the corner
    off. Do not size a fillet with this.

    It is linear. The material never yields, nothing buckles, nothing touches
    anything else, and a part loaded past yield reports a stress it would
    never actually reach. The factor of safety it prints is the honest use of
    that: above one, elastic and fine; near or below one, get a real analysis.

    It is static. No vibration, no fatigue, no impact.

**Why the numbers can be trusted as far as that.** Because they are checked
against answers worked out another way. A bar in tension stretches by FL/AE
and that is exact for these elements, so the test demands it exactly. A patch
of elements given a uniform stretch must report uniform stress. A part moved
without being deformed must report no stress at all. A cantilever must come
within a few percent of the beam formula and get closer as the mesh gets
finer. Every one of those is in the selftest, and each fails if the piece of
the method it covers is broken.
"""
import math
import struct
import sys
import time
from array import array
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))


# ------------------------------------------------------------------ material

class Material:
    """What a material does under load. Three numbers and a name.

    E is how stiff it is, nu is how much it bulges sideways when squashed,
    yield_ is the stress at which it stops springing back. Densities are here
    so a part can be weighed, which is the other question everybody asks.
    """

    __slots__ = ("name", "E", "nu", "yield_", "density")

    def __init__(self, name, E, nu, yield_, density):
        self.name, self.E, self.nu = name, E, nu
        self.yield_, self.density = yield_, density


# N/mm2 (which is MPa), and kg per cubic millimetre.
MATERIALS = {
    "6082": Material("6082-T6 aluminium", 70000.0, 0.33, 260.0, 2.70e-6),
    "6061": Material("6061-T6 aluminium", 68900.0, 0.33, 276.0, 2.70e-6),
    "304": Material("304 stainless", 193000.0, 0.29, 215.0, 8.00e-6),
    "mild": Material("mild steel S275", 210000.0, 0.30, 275.0, 7.85e-6),
    "4140": Material("4140 steel, quenched", 205000.0, 0.29, 655.0, 7.85e-6),
    "abs": Material("ABS", 2200.0, 0.35, 40.0, 1.04e-6),
    "pla": Material("PLA, printed solid", 3500.0, 0.36, 50.0, 1.24e-6),
    "nylon": Material("Nylon 6", 2700.0, 0.39, 45.0, 1.14e-6),
}


# ---------------------------------------------------------------- the bricks

class Grid:
    """The part, as a box of little bricks, some of them material.

    A brick is in if the middle of it is inside the surface. That is decided
    by firing a ray and counting how many times it crosses the skin: an odd
    number means it started inside. One ray does a whole row of bricks at
    once, which is what makes this quick enough to be worth doing.
    """

    __slots__ = ("lo", "step", "n", "solid", "count")

    def __init__(self, lo, step, n, solid):
        self.lo, self.step, self.n, self.solid = lo, step, n, solid
        self.count = sum(1 for s in solid if s)

    # ---- where things are ----

    def cell(self, i, j, k):
        return i + self.n[0] * (j + self.n[1] * k)

    def node(self, i, j, k):
        return i + (self.n[0] + 1) * (j + (self.n[1] + 1) * k)

    def nodes(self):
        return (self.n[0] + 1) * (self.n[1] + 1) * (self.n[2] + 1)

    def at(self, i, j, k):
        """Where a node is, in the part's own coordinates."""
        return (self.lo[0] + i * self.step[0],
                self.lo[1] + j * self.step[1],
                self.lo[2] + k * self.step[2])

    def volume(self):
        return self.count * self.step[0] * self.step[1] * self.step[2]

    def thinnest(self, keep=0.10):
        """How many bricks thick the part is, where it is thin.

        The one number that decides whether an answer is worth having. A wall
        one brick thick cannot bend, whatever the brick can do, and the same
        part meshed one brick finer comes back several times floppier with
        nothing on screen to say why.

        Not the thinnest run anywhere: a grid laid over a curve always clips a
        corner off somewhere and leaves one brick on its own, so the thinnest
        run is one on every part ever made and a warning that always fires is
        a warning nobody reads. Every brick is asked how thick the part is
        where it stands, which is the shortest unbroken run of material
        through it in any of the three directions, and what comes back is the
        figure a tenth of the part is thinner than.
        """
        n = self.n
        thick = {}
        for axis in range(3):
            for a in range(n[(axis + 1) % 3]):
                for b in range(n[(axis + 2) % 3]):
                    run = []
                    for c in range(n[axis] + 1):
                        on = False
                        if c < n[axis]:
                            here = [0, 0, 0]
                            here[axis] = c
                            here[(axis + 1) % 3] = a
                            here[(axis + 2) % 3] = b
                            at = self.cell(*here)
                            on = bool(self.solid[at])
                        if on:
                            run.append(at)
                        else:
                            for cell in run:
                                got = thick.get(cell)
                                if got is None or len(run) < got:
                                    thick[cell] = len(run)
                            run = []
        if not thick:
            return 0
        ranked = sorted(thick.values())
        return ranked[min(len(ranked) - 1, int(len(ranked) * keep))]


def voxelise(tris, across=20, most=40000):
    """A triangle mesh into a grid of bricks.

    `across` is how many bricks fit along the longest side of the part, which
    is the one number that decides how long everything afterwards takes. The
    bricks are cubes: a brick longer one way than another is a brick that is
    stiffer one way than another for no physical reason.
    """
    if not tris:
        raise ValueError("there is no geometry to analyse")
    lo = [min(p[i] for t in tris for p in t) for i in range(3)]
    hi = [max(p[i] for t in tris for p in t) for i in range(3)]
    span = [hi[i] - lo[i] for i in range(3)]
    longest = max(span)
    if longest <= 0:
        raise ValueError("that part has no size")
    if across < 2:
        raise ValueError("a part two bricks across is not an analysis")
    step = longest / float(across)
    n = [max(1, int(math.ceil(span[i] / step))) for i in range(3)]
    if n[0] * n[1] * n[2] > most:
        raise ValueError(
            f"{n[0]} by {n[1]} by {n[2]} is {n[0]*n[1]*n[2]:,} bricks, and this "
            f"solves them in Python. Ask for fewer across, or cut the part down "
            f"to the bit you care about.")
    # Centred on the part, so the grid covers all of it and the leftover, when
    # the bricks do not divide the part exactly, is split evenly between the
    # two ends. Offsetting by half a brick instead looks like it keeps the
    # surface off the brick faces and really just slides the grid off the end
    # of the part: a hundred millimetre bar got ninety five millimetres of
    # grid, and the missing five were at the end everything was measured from.
    start = [lo[i] - (n[i] * step - span[i]) * 0.5 for i in range(3)]

    # One ray per row of bricks, along x, crossings sorted, alternate spans in.
    solid = bytearray(n[0] * n[1] * n[2])
    rows = _crossings(tris, start, step, n)
    for (j, k), xs in rows.items():
        if len(xs) < 2:
            continue
        xs.sort()
        for a in range(0, len(xs) - 1, 2):
            x0, x1 = xs[a], xs[a + 1]
            i0 = int(math.ceil((x0 - start[0]) / step - 0.5))
            i1 = int(math.floor((x1 - start[0]) / step - 0.5))
            # The x direction keeps its middle: the ray is along x, so there
            # is no edge to run along there, only ends to fall between.
            for i in range(max(0, i0), min(n[0] - 1, i1) + 1):
                solid[i + n[0] * (j + n[1] * k)] = 1
    return Grid(tuple(start), (step, step, step), tuple(n), solid)


def _crossings(tris, start, step, n):
    """Where each row's ray goes through the skin.

    Rays are fired through the middle of every row, so one never runs exactly
    along an edge, which is the case that counts a crossing twice and turns
    the inside of a part into stripes.
    """
    # Not down the middle of the row. A part modelled on round numbers has
    # its triangles split corner to corner, and a ray through the exact middle
    # of a square face runs along that split and is counted by the triangle on
    # both sides of it. Two crossings where there is one, and the whole row
    # comes out as air: a hundred millimetre bar voxelised to nothing. Nudged
    # by a fraction of a brick that is not a round number, a ray never lands
    # on an edge or a corner of geometry built out of round numbers, and a
    # thousandth of a brick makes no difference to which bricks are material.
    OFF_Y, OFF_Z = 0.5 + 0.0013972, 0.5 - 0.0021791
    rows = {}
    for tri in tris:
        ylo = min(p[1] for p in tri); yhi = max(p[1] for p in tri)
        zlo = min(p[2] for p in tri); zhi = max(p[2] for p in tri)
        j0 = max(0, int((ylo - start[1]) / step - 0.5))
        j1 = min(n[1] - 1, int((yhi - start[1]) / step + 0.5))
        k0 = max(0, int((zlo - start[2]) / step - 0.5))
        k1 = min(n[2] - 1, int((zhi - start[2]) / step + 0.5))
        for k in range(k0, k1 + 1):
            z = start[2] + (k + OFF_Z) * step
            for j in range(j0, j1 + 1):
                y = start[1] + (j + OFF_Y) * step
                x = _hit_x(tri, y, z)
                if x is not None:
                    rows.setdefault((j, k), []).append(x)
    return rows


def _hit_x(tri, y, z):
    """Where a ray along x at (y, z) goes through this triangle, or None.

    Worked in the yz plane: the triangle projects to a triangle there, and if
    the point is inside it the crossing is the plane's x at that point."""
    (ax, ay, az), (bx, by, bz), (cx, cy, cz) = tri
    d = (by - ay) * (cz - az) - (bz - az) * (cy - ay)
    if abs(d) < 1e-14:
        return None                      # edge on to the ray; another will do
    u = ((y - ay) * (cz - az) - (z - az) * (cy - ay)) / d
    v = ((by - ay) * (z - az) - (bz - az) * (y - ay)) / d
    if u < 0.0 or v < 0.0 or u + v > 1.0:
        return None
    return ax + u * (bx - ax) + v * (cx - ax)


# ------------------------------------------------------------- one brick's stiffness

def hooke(E, nu):
    """How stress follows strain for a material that is the same in every
    direction. Six by six, in the usual order: three stretches then three
    shears."""
    if not (0.0 <= nu < 0.5):
        raise ValueError("Poisson's ratio has to be between 0 and a half")
    if E <= 0:
        raise ValueError("a material with no stiffness is not a material")
    f = E / ((1.0 + nu) * (1.0 - 2.0 * nu))
    g = E / (2.0 * (1.0 + nu))
    D = [[0.0] * 6 for _ in range(6)]
    for i in range(3):
        for j in range(3):
            D[i][j] = f * (nu if i != j else (1.0 - nu))
    for i in range(3, 6):
        D[i][i] = g
    return D


CORNERS = [(-1, -1, -1), (1, -1, -1), (1, 1, -1), (-1, 1, -1),
           (-1, -1, 1), (1, -1, 1), (1, 1, 1), (-1, 1, 1)]
GAUSS = (-1.0 / math.sqrt(3.0), 1.0 / math.sqrt(3.0))


def shape_gradients(a, b, c, g, h, r):
    """How each corner's influence changes with position, at one point inside
    the brick. The brick is a by b by c and the point is given in the square
    minus one to one that every brick is worked out in."""
    out = []
    for (xi, eta, zeta) in CORNERS:
        out.append((xi * (1 + eta * h) * (1 + zeta * r) / 8.0 * (2.0 / a),
                    eta * (1 + xi * g) * (1 + zeta * r) / 8.0 * (2.0 / b),
                    zeta * (1 + xi * g) * (1 + eta * h) / 8.0 * (2.0 / c)))
    return out


def strain_matrix(a, b, c, g, h, r):
    """Six strains out of twenty four corner movements."""
    B = [[0.0] * 24 for _ in range(6)]
    for i, (dx, dy, dz) in enumerate(shape_gradients(a, b, c, g, h, r)):
        x, y, z = 3 * i, 3 * i + 1, 3 * i + 2
        B[0][x] = dx
        B[1][y] = dy
        B[2][z] = dz
        B[3][x] = dy; B[3][y] = dx
        B[4][y] = dz; B[4][z] = dy
        B[5][x] = dz; B[5][z] = dx
    return B


def bend_gradients(a, b, c, g, h, r):
    """Three extra ways a brick is allowed to bend, that its eight corners
    cannot describe between them.

    A brick with only its corners to work with cannot bend. Asked to, it
    shears instead, and shearing is stiff, so it comes out far stiffer than
    the thing it is standing in for: a cantilever one brick thick reads two
    thirds as floppy as the beam formula says it is, and the error only goes
    away with a mesh nobody has time to solve.

    Adding a bulge in each direction, pinned to zero at the faces, lets it
    bend properly. They belong to the brick and to nothing else, so they are
    folded back out before the brick joins the rest of the part, and the part
    never knows they were there. The bulges integrate to nothing across the
    brick, which is what keeps a uniform stretch coming out exactly uniform.
    """
    return [(-4.0 * g / a, 0.0, 0.0),
            (0.0, -4.0 * h / b, 0.0),
            (0.0, 0.0, -4.0 * r / c)]


def bend_matrix(a, b, c, g, h, r):
    """Six strains out of the nine numbers describing those bulges."""
    B = [[0.0] * 9 for _ in range(6)]
    for m, (dx, dy, dz) in enumerate(bend_gradients(a, b, c, g, h, r)):
        x, y, z = 3 * m, 3 * m + 1, 3 * m + 2
        B[0][x] = dx
        B[1][y] = dy
        B[2][z] = dz
        B[3][x] = dy; B[3][y] = dx
        B[4][y] = dz; B[4][z] = dy
        B[5][x] = dz; B[5][z] = dx
    return B


def _solve_small(A, B):
    """A small dense solve, for folding the bulges back out. Gauss Jordan with
    partial pivoting, on a nine by nine, done once for the whole model."""
    n = len(A)
    m = len(B[0])
    M = [list(A[i]) + list(B[i]) for i in range(n)]
    for col in range(n):
        best = max(range(col, n), key=lambda r: abs(M[r][col]))
        if abs(M[best][col]) < 1e-300:
            raise ValueError("the brick's own bending is singular")
        M[col], M[best] = M[best], M[col]
        piv = M[col][col]
        M[col] = [v / piv for v in M[col]]
        for r in range(n):
            if r == col:
                continue
            f = M[r][col]
            if f:
                M[r] = [M[r][k] - f * M[col][k] for k in range(n + m)]
    return [row[n:] for row in M]


class Brick:
    """Everything about one brick of material: how stiff it is, and how to get
    a stress back out of it once the part has been solved."""

    __slots__ = ("a", "b", "c", "D", "k", "pull")

    def __init__(self, a, b, c, E, nu):
        self.a, self.b, self.c = a, b, c
        self.D = D = hooke(E, nu)
        Kuu = [[0.0] * 24 for _ in range(24)]
        Kua = [[0.0] * 9 for _ in range(24)]
        Kaa = [[0.0] * 9 for _ in range(9)]
        weight = (a / 2.0) * (b / 2.0) * (c / 2.0)
        for g in GAUSS:
            for h in GAUSS:
                for r in GAUSS:
                    Bu = strain_matrix(a, b, c, g, h, r)
                    Ba = bend_matrix(a, b, c, g, h, r)
                    DBu = [[sum(D[i][q] * Bu[q][col] for q in range(6))
                            for col in range(24)] for i in range(6)]
                    DBa = [[sum(D[i][q] * Ba[q][col] for q in range(6))
                            for col in range(9)] for i in range(6)]
                    for i in range(24):
                        for q in range(6):
                            v = Bu[q][i]
                            if not v:
                                continue
                            v *= weight
                            row, dq = Kuu[i], DBu[q]
                            for j in range(24):
                                row[j] += v * dq[j]
                            row, dq = Kua[i], DBa[q]
                            for j in range(9):
                                row[j] += v * dq[j]
                    for i in range(9):
                        for q in range(6):
                            v = Ba[q][i]
                            if not v:
                                continue
                            v *= weight
                            row, dq = Kaa[i], DBa[q]
                            for j in range(9):
                                row[j] += v * dq[j]
        # Fold the bulges out: what is left is twenty four by twenty four and
        # joins the rest of the part like any ordinary brick.
        KauT = [[Kua[i][m] for i in range(24)] for m in range(9)]
        self.pull = [[-v for v in row] for row in _solve_small(Kaa, KauT)]
        self.k = [[Kuu[i][j] + sum(Kua[i][m] * self.pull[m][j] for m in range(9))
                   for j in range(24)] for i in range(24)]

    def stress(self, ue, g, h, r):
        """The six stresses somewhere inside this brick."""
        Bu = strain_matrix(self.a, self.b, self.c, g, h, r)
        Ba = bend_matrix(self.a, self.b, self.c, g, h, r)
        al = [sum(self.pull[m][j] * ue[j] for j in range(24)) for m in range(9)]
        strain = [sum(Bu[q][j] * ue[j] for j in range(24))
                  + sum(Ba[q][m] * al[m] for m in range(9)) for q in range(6)]
        return [sum(self.D[i][q] * strain[q] for q in range(6)) for i in range(6)]


def brick_stiffness(a, b, c, E, nu):
    """One brick's resistance to being pushed about, with its bending fixed."""
    return Brick(a, b, c, E, nu).k


# ------------------------------------------------------------------ the study

class Study:
    """One question: this part, this material, held here, pushed there."""

    def __init__(self, grid, material, name="part"):
        self.grid = grid
        self.material = material
        self.name = name
        self.fixed = {}                    # degree of freedom -> where it is held
        self.load = {}                     # node number -> [fx, fy, fz]
        self.u = None                      # what came out
        self.iterations = 0
        self.seconds = 0.0
        self._brick = None
        self._f = None

    # ---- saying which bit ----

    def pick(self, where):
        """The nodes on one face of the part's bounding box, named the way a
        person names it: -z is the bottom, +x is the right hand end."""
        g = self.grid
        axis = {"x": 0, "y": 1, "z": 2}.get(where[-1:].lower())
        if axis is None or where[:1] not in "+-":
            raise ValueError(f"'{where}' is not a face: say -z, +x and so on")
        wanted = g.n[axis] if where[0] == "+" else 0
        out = []
        for k in range(g.n[2] + 1):
            for j in range(g.n[1] + 1):
                for i in range(g.n[0] + 1):
                    if (i, j, k)[axis] != wanted:
                        continue
                    if self._touching(i, j, k):
                        out.append(g.node(i, j, k))
        if not out:
            raise ValueError(f"there is no material on the {where} face")
        return out

    def _touching(self, i, j, k):
        """Is this node a corner of any brick that is actually material. The
        grid's bounding box has air in the corners of it, and holding air down
        holds nothing."""
        g = self.grid
        for di in (-1, 0):
            for dj in (-1, 0):
                for dk in (-1, 0):
                    a, b, c = i + di, j + dj, k + dk
                    if 0 <= a < g.n[0] and 0 <= b < g.n[1] and 0 <= c < g.n[2]:
                        if g.solid[g.cell(a, b, c)]:
                            return True
        return False

    def hold(self, where, axes="xyz", to=(0.0, 0.0, 0.0)):
        """Hold this face. All three ways by default, which is a bolted joint.

        `axes` narrows it: "x" alone is a roller, free to slide in the plane
        and only stopped from going through. That is not a detail. Bolting a
        bar's end down in all three directions stops it contracting sideways
        as it stretches, which puts a stress raiser right where the answer was
        supposed to be simple, and a test that expected FL/AE then fails for a
        reason that is nothing to do with the solver.

        `to` says where it is held, so a face can be pressed a set distance
        rather than pushed with a set force."""
        want = [i for i, ax in enumerate("xyz") if ax in axes.lower()]
        if not want:
            raise ValueError("hold it in at least one direction")
        for nd in self.pick(where):
            for c in want:
                self.fixed[3 * nd + c] = to[c]
        return self

    def face_cells(self, where):
        """The bricks with a face on that side of the part, and which four of
        their corners are on it."""
        g = self.grid
        axis = {"x": 0, "y": 1, "z": 2}.get(where[-1:].lower())
        if axis is None or where[:1] not in "+-":
            raise ValueError(f"'{where}' is not a face: say -z, +x and so on")
        top = where[0] == "+"
        # The end of the part, not every face that happens to point this way.
        # A stepped part has upward faces at three different heights, and
        # "pushed on the top" means the top, not all of them spread with a
        # share each. It also has to mean the same thing here as it does when
        # a face is held, or holding and pushing the same face are two
        # different faces and the analysis quietly answers a question nobody
        # asked.
        edge = g.n[axis] - 1 if top else 0
        out = []
        for k in range(g.n[2]):
            for j in range(g.n[1]):
                for i in range(g.n[0]):
                    if not g.solid[g.cell(i, j, k)]:
                        continue
                    if (i, j, k)[axis] != edge:
                        continue
                    corner = []
                    for di, dj, dk in ((0,0,0),(1,0,0),(1,1,0),(0,1,0),
                                       (0,0,1),(1,0,1),(1,1,1),(0,1,1)):
                        step = (di, dj, dk)[axis]
                        if step == (1 if top else 0):
                            corner.append(g.node(i + di, j + dj, k + dk))
                    out.append(corner)
        if not out:
            raise ValueError(f"there is no material on the {where} face")
        return out

    def push(self, where, force):
        """Spread a force, in newtons, evenly over a face.

        Over the face's area rather than over its corners. Sharing it equally
        between nodes sounds the same and is not: a corner node carries a
        quarter of a brick of area and one in the middle carries a whole one,
        so equal shares press four times too hard round the rim, and a bar
        that should have been in plain tension comes out with a ring of stress
        round the end of it."""
        quads = self.face_cells(where)
        share = [force[i] / float(len(quads)) / 4.0 for i in range(3)]
        for corner in quads:
            for nd in corner:
                got = self.load.setdefault(nd, [0.0, 0.0, 0.0])
                for i in range(3):
                    got[i] += share[i]
        return self

    def gravity(self, g=9810.0, direction=(0.0, 0.0, -1.0)):
        """The part's own weight, in the same units as everything else:
        newtons and millimetres, so g is 9810 mm per second squared."""
        m = self.material.density * self.grid.step[0] * self.grid.step[1] \
            * self.grid.step[2]
        grid = self.grid
        each = m * g / 8.0
        for k in range(grid.n[2]):
            for j in range(grid.n[1]):
                for i in range(grid.n[0]):
                    if not grid.solid[grid.cell(i, j, k)]:
                        continue
                    for di, dj, dk in ((0,0,0),(1,0,0),(1,1,0),(0,1,0),
                                       (0,0,1),(1,0,1),(1,1,1),(0,1,1)):
                        nd = grid.node(i + di, j + dj, k + dk)
                        got = self.load.setdefault(nd, [0.0, 0.0, 0.0])
                        for c in range(3):
                            got[c] += each * direction[c]
        return self

    def weight(self):
        """Kilograms."""
        return self.grid.volume() * self.material.density

    # ---- putting it together ----

    def _elements(self):
        g = self.grid
        out = []
        for k in range(g.n[2]):
            for j in range(g.n[1]):
                for i in range(g.n[0]):
                    if g.solid[g.cell(i, j, k)]:
                        out.append((i, j, k))
        return out

    def _dofs_of(self, i, j, k):
        g = self.grid
        out = []
        for di, dj, dk in ((0,0,0),(1,0,0),(1,1,0),(0,1,0),
                           (0,0,1),(1,0,1),(1,1,1),(0,1,1)):
            nd = g.node(i + di, j + dj, k + dk)
            out += [3 * nd, 3 * nd + 1, 3 * nd + 2]
        return out

    def assemble(self):
        """Every brick's stiffness added into one big sparse matrix.

        Sparse and stored by rows, because the matrix for even a small part
        has millions of entries that are all zero and only tens of thousands
        that are not, and holding the zeros is the difference between this
        running and this not."""
        g = self.grid
        ke = self.brick().k
        n = 3 * g.nodes()
        rows = [dict() for _ in range(n)]
        for (i, j, k) in self._elements():
            dofs = self._dofs_of(i, j, k)
            for a in range(24):
                row = rows[dofs[a]]
                kea = ke[a]
                for b in range(24):
                    v = kea[b]
                    if v:
                        d = dofs[b]
                        row[d] = row.get(d, 0.0) + v
        indptr = array('i', [0] * (n + 1))
        indices = array('i')
        data = array('d')
        for i in range(n):
            for col in sorted(rows[i]):
                indices.append(col)
                data.append(rows[i][col])
            indptr[i + 1] = len(indices)
        return indptr, indices, data, n

    # ---- solving it ----

    def solve(self, tol=1e-8, most=20000, watch=None):
        """The shape the part settles into. Conjugate gradients, which walks
        downhill on the energy and is the standard way to solve a stiffness
        matrix without ever writing down its inverse."""
        started = time.time()
        g = self.grid
        if not self.grid.count:
            raise ValueError("the grid caught none of the part; ask for more "
                             "bricks across it")
        if not self.fixed:
            raise ValueError("nothing is holding the part, so there is no "
                             "answer: it would accelerate away rather than "
                             "deform. Hold a face first.")
        if not self.load and not any(self.fixed.values()):
            raise ValueError("nothing is pushing on the part")

        indptr, indices, data, n = self.assemble()
        free = bytearray(n)
        live = 0
        for i in range(n):
            if indptr[i + 1] > indptr[i]:
                free[i] = 1
                live += 1
        for dof in self.fixed:
            if dof < n:
                free[dof] = 0
        if not live:
            raise ValueError("no brick of the part is attached to anything")

        f = array('d', [0.0] * n)
        for nd, v in self.load.items():
            for c in range(3):
                f[3 * nd + c] = v[c]

        # A face held somewhere other than where it started is a load like any
        # other: put it in place, see what force that takes, and solve for the
        # rest of the part against it.
        held = array('d', [0.0] * n)
        moved = False
        for dof, value in self.fixed.items():
            if dof < n and value:
                held[dof] = value
                moved = True
        if moved:
            for i in range(n):
                if not free[i]:
                    continue
                s = 0.0
                for k in range(indptr[i], indptr[i + 1]):
                    s += data[k] * held[indices[k]]
                f[i] -= s
        for i in range(n):
            if not free[i]:
                f[i] = 0.0

        # Everything a part could do without deforming has to be held, or the
        # matrix is singular and the answer is whatever the solver drifted to.
        loose = self._unattached(free)
        if loose:
            raise ValueError(
                f"{loose} brick(s) of the part are not joined to anything that "
                f"is held, so they would fly off rather than take load. Either "
                f"the part is in pieces or the face being held is the wrong one.")

        diag = array('d', [1.0] * n)
        for i in range(n):
            if free[i]:
                for k in range(indptr[i], indptr[i + 1]):
                    if indices[k] == i:
                        diag[i] = data[k] if data[k] > 0 else 1.0
                        break

        u = array('d', held)
        r = array('d', f)
        z = array('d', [r[i] / diag[i] if free[i] else 0.0 for i in range(n)])
        p = array('d', z)
        rz = sum(r[i] * z[i] for i in range(n))
        target = math.sqrt(sum(f[i] * f[i] for i in range(n))) * tol
        if target <= 0:
            raise ValueError("the load adds up to nothing")
        ap = array('d', [0.0] * n)
        step = 0
        while step < most:
            step += 1
            for i in range(n):
                if not free[i]:
                    ap[i] = 0.0
                    continue
                s = 0.0
                for k in range(indptr[i], indptr[i + 1]):
                    s += data[k] * p[indices[k]]
                ap[i] = s
            pap = sum(p[i] * ap[i] for i in range(n))
            if pap <= 0:
                raise ValueError("the stiffness matrix is not positive: the "
                                 "part is not properly held")
            alpha = rz / pap
            for i in range(n):
                u[i] += alpha * p[i]
                r[i] -= alpha * ap[i]
            size = math.sqrt(sum(r[i] * r[i] for i in range(n)))
            if watch and step % 25 == 0:
                watch(step, size / target)
            if size < target:
                break
            for i in range(n):
                z[i] = r[i] / diag[i] if free[i] else 0.0
            rz2 = sum(r[i] * z[i] for i in range(n))
            beta = rz2 / rz
            rz = rz2
            for i in range(n):
                p[i] = z[i] + beta * p[i]
        else:
            raise ValueError(f"it did not settle after {most} steps; the part "
                             f"is probably barely held")
        self.u = u
        self.iterations = step
        self.seconds = time.time() - started
        self._f = f
        return u

    def _unattached(self, free):
        """Bricks with no path through the material to anything held.

        A part in two pieces with only one of them bolted down has no answer,
        and a solver asked for one returns a large confident number."""
        g = self.grid
        seen = bytearray(g.n[0] * g.n[1] * g.n[2])
        stack = []
        for nd in {dof // 3 for dof in self.fixed}:
            rest = nd
            i = rest % (g.n[0] + 1); rest //= (g.n[0] + 1)
            j = rest % (g.n[1] + 1); k = rest // (g.n[1] + 1)
            for di in (-1, 0):
                for dj in (-1, 0):
                    for dk in (-1, 0):
                        a, b, c = i + di, j + dj, k + dk
                        if 0 <= a < g.n[0] and 0 <= b < g.n[1] and 0 <= c < g.n[2]:
                            if g.solid[g.cell(a, b, c)] and not seen[g.cell(a, b, c)]:
                                seen[g.cell(a, b, c)] = 1
                                stack.append((a, b, c))
        while stack:
            a, b, c = stack.pop()
            for da, db, dc in ((1,0,0),(-1,0,0),(0,1,0),(0,-1,0),(0,0,1),(0,0,-1)):
                x, y, z = a + da, b + db, c + dc
                if not (0 <= x < g.n[0] and 0 <= y < g.n[1] and 0 <= z < g.n[2]):
                    continue
                at = g.cell(x, y, z)
                if g.solid[at] and not seen[at]:
                    seen[at] = 1
                    stack.append((x, y, z))
        return g.count - sum(seen)


# ------------------------------------------------------------------ the answer

    # ---- what came out ----

    def pin(self, node, axes="xyz", to=(0.0, 0.0, 0.0)):
        """Hold one node, for when a face is the wrong shape to name."""
        for c, ax in enumerate("xyz"):
            if ax in axes.lower():
                self.fixed[3 * node + c] = to[c]
        return self

    def nearest(self, point):
        """The node closest to somewhere, which is how a person points at a
        part: not by number."""
        g = self.grid
        at = [int(round((point[c] - g.lo[c]) / g.step[c])) for c in range(3)]
        at = [min(max(at[c], 0), g.n[c]) for c in range(3)]
        return g.node(*at)

    def moved(self, node):
        """How far one node went, in each direction."""
        if self.u is None:
            raise ValueError("it has not been solved yet")
        return (self.u[3 * node], self.u[3 * node + 1], self.u[3 * node + 2])

    def edge_nodes(self):
        """Every node on the outside of the grid. What a patch test holds."""
        g = self.grid
        out = []
        for k in range(g.n[2] + 1):
            for j in range(g.n[1] + 1):
                for i in range(g.n[0] + 1):
                    if (i in (0, g.n[0]) or j in (0, g.n[1])
                            or k in (0, g.n[2])):
                        out.append(((i, j, k), g.node(i, j, k)))
        return out

    def movement(self):
        """How far every node moved, and the worst of it."""
        u = self.u
        if u is None:
            raise ValueError("it has not been solved yet")
        worst, where = 0.0, 0
        for nd in range(self.grid.nodes()):
            d = math.sqrt(u[3*nd]**2 + u[3*nd+1]**2 + u[3*nd+2]**2)
            if d > worst:
                worst, where = d, nd
        return worst, where

    def brick(self):
        """The one brick every brick in this part is a copy of."""
        if getattr(self, "_brick", None) is None:
            g = self.grid
            self._brick = Brick(g.step[0], g.step[1], g.step[2],
                                self.material.E, self.material.nu)
        return self._brick

    def stresses(self):
        """How hard the material is working in each brick: the worst of its
        eight corners.

        Not the middle. The middle of a brick in pure bending reads zero,
        because the middle of it is the neutral axis, and a beam bent double
        then comes back looking unstressed. Not the points inside it either,
        which is where the arithmetic is most accurate and is not where the
        material is working hardest: on a cantilever one brick thick those
        points read a little over half the stress the beam formula gives, and
        they are right about a place nobody asked about. The corners are where
        the surface is, which is where a part cracks."""
        if self.u is None:
            raise ValueError("it has not been solved yet")
        brick = self.brick()
        out = {}
        for (i, j, k) in self._elements():
            dofs = self._dofs_of(i, j, k)
            ue = [self.u[d] for d in dofs]
            worst = 0.0
            for (g, h, r) in CORNERS:
                v = von_mises(brick.stress(ue, float(g), float(h), float(r)))
                if v > worst:
                    worst = v
            out[(i, j, k)] = worst
        return out

    def report(self):
        """The three numbers anybody actually wants, and what they mean."""
        worst, where = self.movement()
        stress = self.stresses()
        peak = max(stress.values()) if stress else 0.0
        hot = max(stress, key=stress.get) if stress else None
        pushed = math.sqrt(sum(sum(v[c] for v in self.load.values()) ** 2
                               for c in range(3)))
        strain_energy = 0.5 * sum(self.u[i] * self._f[i]
                                  for i in range(len(self.u)))
        return {
            "material": self.material.name,
            "weight_kg": self.weight(),
            "bricks": self.grid.count,
            "brick_mm": self.grid.step[0],
            "thinnest_wall_bricks": self.grid.thinnest(),
            "load_N": pushed,
            "worst_movement_mm": worst,
            "worst_movement_at": self.grid_at(where),
            "peak_stress_MPa": peak,
            "peak_stress_at": self.centre_of(hot) if hot else None,
            "yield_MPa": self.material.yield_,
            "factor_of_safety": (self.material.yield_ / peak) if peak > 0 else float("inf"),
            "strain_energy_Nmm": strain_energy,
            "steps": self.iterations,
            "seconds": self.seconds,
        }

    def field(self):
        """The answer as a picture: which bricks are material and how hard
        each is working, so something with a screen can colour the part in."""
        stress = self.stresses()
        g = self.grid
        cells, values = [], []
        for (i, j, k), v in stress.items():
            cells.append(g.cell(i, j, k))
            values.append(v)
        return {"lo": list(g.lo), "step": list(g.step), "n": list(g.n),
                "cells": cells, "stress": values}

    def grid_at(self, node):
        g = self.grid
        rest = node
        i = rest % (g.n[0] + 1); rest //= (g.n[0] + 1)
        j = rest % (g.n[1] + 1); k = rest // (g.n[1] + 1)
        return g.at(i, j, k)

    def centre_of(self, cell):
        g = self.grid
        i, j, k = cell
        return (g.lo[0] + (i + 0.5) * g.step[0],
                g.lo[1] + (j + 0.5) * g.step[1],
                g.lo[2] + (k + 0.5) * g.step[2])


def von_mises(s):
    """One number for how close a stress state is to yielding. The one a
    material's yield strength is measured against, so the two can be compared
    without anybody having to think about which direction anything is in."""
    xx, yy, zz, xy, yz, zx = s
    return math.sqrt(0.5 * ((xx - yy) ** 2 + (yy - zz) ** 2 + (zz - xx) ** 2)
                     + 3.0 * (xy * xy + yz * yz + zx * zx))


# ----------------------------------------------------------------- the tests

def selftest():
    fail = []

    def near(what, got, want, tol):
        if abs(got - want) > tol:
            fail.append(f"{what}: got {got:.8g}, wanted {want:.8g} "
                        f"(out by {abs(got - want):.3g})")

    def within(what, got, want, pct):
        if want == 0 or abs(got - want) / abs(want) > pct / 100.0:
            fail.append(f"{what}: got {got:.6g}, wanted {want:.6g}, which is "
                        f"{abs(got - want) / abs(want) * 100:.1f}% out and the "
                        f"limit is {pct}%")

    import solid as S

    # ---- the material, against what it is defined to be ----
    D = hooke(210000.0, 0.3)
    for i in range(6):
        for j in range(6):
            if abs(D[i][j] - D[j][i]) > 1e-9:
                fail.append("the material behaves differently depending on "
                            "which way round you ask")
    # Squeeze it equally from every side and it should resist by its bulk
    # modulus, which is E over three times one minus twice Poisson's ratio.
    s = [sum(D[i][j] * (1.0 if j < 3 else 0.0) for j in range(6)) for i in range(3)]
    near("the bulk modulus", s[0] / 3.0, 210000.0 / (3 * (1 - 2 * 0.3)) , 1e-6)

    # ---- one brick on its own ----
    brick = Brick(2.0, 3.0, 5.0, 210000.0, 0.3)
    worst = max(abs(brick.k[i][j] - brick.k[j][i])
                for i in range(24) for j in range(24))
    if worst > 1e-6:
        fail.append(f"a brick is not symmetric, out by {worst:.3g}")
    for comp in range(3):
        move = [1.0 if d % 3 == comp else 0.0 for d in range(24)]
        force = max(abs(sum(brick.k[i][j] * move[j] for j in range(24)))
                    for i in range(24))
        if force > 1e-6:
            fail.append(f"sliding a brick along axis {comp} takes {force:.3g} "
                        f"of force, and moving something without deforming it "
                        f"should take none")

    # ---- the bricks the part is cut into ----
    bar = S.box(100.0, 10.0, 10.0)
    g = voxelise(bar.tris, across=10)
    if g.n != (10, 1, 1):
        fail.append(f"a hundred by ten by ten bar ten across came out {g.n}")
    near("the bricks add up to the part", g.volume(), 100.0 * 10.0 * 10.0, 1e-6)
    holed = difference_volume_check(S)
    if holed:
        fail.append(holed)

    # An L is a part that does not fill its own bounding box, so a study that
    # quietly analyses the air beside it has more bricks in it than the part
    # has, and comes out stiffer than the part is for a reason nothing else
    # here would see.
    ell = S.prism([(0, 0), (60, 0), (60, 12), (12, 12), (12, 60), (0, 60)], 10.0)
    corner = voxelise(ell.tris, across=10)
    lonely = Study(corner, MATERIALS["mild"], "L")
    if len(lonely._elements()) != corner.count:
        fail.append(f"the study has {len(lonely._elements())} bricks in it and "
                    f"the part is {corner.count}, so it is analysing air")
    if not (0.25 < corner.volume() / (60.0 * 60.0 * 10.0) < 0.75):
        fail.append(f"an L bracket filled {corner.volume() / 36000.0:.0%} of "
                    f"its own bounding box, which is not what an L looks like")
    for what, fn in (("no geometry", lambda: voxelise([], across=10)),
                     ("two bricks across", lambda: voxelise(bar.tris, across=1)),
                     ("more bricks than it can solve",
                      lambda: voxelise(bar.tris, across=400))):
        try:
            fn()
            fail.append(f"{what} was allowed")
        except ValueError:
            pass

    # ---- a bar pulled straight, which has an exact answer ----
    mild = MATERIALS["mild"]
    # Twenty square, not ten: an end face two bricks across has nine nodes on
    # it, four of them corners carrying a quarter of a brick of area each and
    # one in the middle carrying a whole one. A face four nodes across cannot
    # tell an even pressure from an even share between nodes, and a bar that
    # cannot tell the difference cannot test it.
    L, W, H, F = 100.0, 20.0, 20.0, 10000.0
    thick = S.box(L, W, H)
    pull = Study(voxelise(thick.tris, across=10), mild, "bar")
    pull.hold("-x", "x").hold("-y", "y").hold("-z", "z")
    pull.push("+x", (F, 0.0, 0.0))
    pull.solve(tol=1e-10)
    area = W * H
    stretch = F * L / (area * mild.E)
    near("a bar in tension stretches by FL over AE",
         pull.moved(pull.nearest((L, 0.0, 0.0)))[0], stretch, stretch * 1e-6)
    near("and pulls in sideways by Poisson's ratio times that",
         pull.moved(pull.nearest((L, W, H)))[1],
         -mild.nu * (F / area) * W / mild.E, stretch * 1e-6)
    sig = pull.stresses()
    near("and the stress in it is the load over the area",
         min(sig.values()), F / area, 1e-6)
    near("everywhere, not just on average", max(sig.values()), F / area, 1e-6)
    near("and the energy in it is half the load times the stretch",
         pull.report()["strain_energy_Nmm"], 0.5 * F * stretch, 1e-6)

    # Twice the load, twice everything. It is a linear analysis and if it is
    # not linear it is not the analysis it says it is.
    twice = Study(voxelise(thick.tris, across=10), mild, "bar")
    twice.hold("-x", "x").hold("-y", "y").hold("-z", "z")
    twice.push("+x", (2 * F, 0.0, 0.0))
    twice.solve(tol=1e-10)
    near("twice the load moves it twice as far",
         twice.moved(twice.nearest((L, 0.0, 0.0)))[0], 2 * stretch,
         stretch * 1e-6)

    # ---- the patch test, which every element has to pass ----
    #
    # Hold the whole outside of a block to a uniform stretch worked out by
    # hand, and the inside has to follow it exactly and report exactly the
    # stress that stretch implies. An element that cannot do this cannot be
    # trusted anywhere, because every small enough piece of every real part
    # is in a state like this one.
    block = voxelise(S.box(30.0, 20.0, 20.0).tris, across=6)
    A = [[1.0e-4, 3.0e-5, -2.0e-5],
         [5.0e-6, -7.0e-5, 4.0e-5],
         [-3.0e-5, 2.0e-5, 6.0e-5]]
    shift = (0.01, -0.02, 0.03)

    def field(p):
        return tuple(sum(A[r][c] * p[c] for c in range(3)) + shift[r]
                     for r in range(3))

    patch = Study(block, mild, "patch")
    for (i, j, k), nd in patch.edge_nodes():
        patch.pin(nd, "xyz", field(block.at(i, j, k)))
    patch.solve(tol=1e-12, most=50000)
    off = 0.0
    for k in range(block.n[2] + 1):
        for j in range(block.n[1] + 1):
            for i in range(block.n[0] + 1):
                want = field(block.at(i, j, k))
                got = patch.moved(block.node(i, j, k))
                off = max(off, max(abs(got[c] - want[c]) for c in range(3)))
    if off > 1e-9:
        fail.append(f"the patch test: the inside of the block is {off:.3g} mm "
                    f"off the stretch its outside was held to")
    # Worked out here from Lame's two constants rather than by asking the same
    # table of material behaviour that is being tested. Checking a thing
    # against itself passes whatever is wrong with it: the shear stiffness
    # could be five percent out and this would have agreed.
    lam = mild.E * mild.nu / ((1 + mild.nu) * (1 - 2 * mild.nu))
    mu = mild.E / (2 * (1 + mild.nu))
    e = [[0.5 * (A[r][c] + A[c][r]) for c in range(3)] for r in range(3)]
    trace = e[0][0] + e[1][1] + e[2][2]
    sig = [lam * trace + 2 * mu * e[0][0], lam * trace + 2 * mu * e[1][1],
           lam * trace + 2 * mu * e[2][2],
           2 * mu * e[0][1], 2 * mu * e[1][2], 2 * mu * e[0][2]]
    want = von_mises(sig)
    near("the shear stiffness is E over twice one plus Poisson's ratio",
         hooke(mild.E, mild.nu)[3][3], mu, 1e-9)
    near("and the stretch stiffness has Lame's constants in it",
         hooke(mild.E, mild.nu)[0][0], lam + 2 * mu, 1e-9)
    got = patch.stresses()
    near("the patch test: the stress is the same everywhere",
         max(got.values()) - min(got.values()), 0.0, 1e-6)
    near("the patch test: and it is the stress that stretch implies",
         max(got.values()), want, 1e-6)

    # A part moved and turned without being deformed carries no stress.
    rigid = Study(block, mild, "rigid")
    turn = 1e-4
    for (i, j, k), nd in rigid.edge_nodes():
        p = block.at(i, j, k)
        rigid.pin(nd, "xyz", (2.0 - turn * p[1], 3.0 + turn * p[0], 5.0))
    rigid.solve(tol=1e-12, most=50000)
    near("a part carried about without being bent carries no stress",
         max(rigid.stresses().values()), 0.0, 1e-6)

    # ---- a cantilever, against the beam formula ----
    #
    # Not exact, and not meant to be: a beam formula assumes the end is free
    # to pull in as it bends and this one is bolted flat, which is genuinely
    # stiffer. A few percent stiffer is right. Sixty percent stiffer is the
    # element unable to bend, which is what it does without the bulges.
    P = 100.0
    # The slender bar, not the fat one the tension test needed.
    CL, CW, CH = 100.0, 10.0, 10.0
    stiff = mild.E * (CW * CH ** 3 / 12.0)
    shear = P * CL / ((5.0 / 6.0) * CW * CH * (mild.E / (2 * (1 + mild.nu))))
    beam = P * CL ** 3 / (3.0 * stiff) + shear
    tips = []
    for across in (10, 20):
        arm = Study(voxelise(bar.tris, across=across), mild, "cantilever")
        arm.hold("-x")
        arm.push("+x", (0.0, 0.0, -P))
        arm.solve(tol=1e-9, most=60000)
        tips.append(abs(arm.moved(arm.nearest((CL, CW / 2, CH / 2)))[2]))
        if across == 20:
            peak = max(arm.stresses().values())
            within("the stress at the root of a cantilever",
                   peak, P * CL * (CH / 2) / (CW * CH ** 3 / 12.0), 20.0)
    for across, tip in zip((10, 20), tips):
        if not (0.94 * beam <= tip <= 1.02 * beam):
            fail.append(f"a cantilever {across} bricks long deflects {tip:.6f} "
                        f"and the beam formula says {beam:.6f}: "
                        f"{tip / beam * 100:.0f}% of it")

    # ---- and it says when the mesh is too coarse to believe ----
    #
    # A wall one brick thick cannot bend, so the same part meshed one brick
    # finer comes back several times floppier. That is not a bug in the
    # solver and it is not something to leave the reader to work out.
    thin_part = S.difference(S.box(60.0, 60.0, 30.0),
                             S.box(50.0, 50.0, 40.0, at=(5.0, 5.0, 5.0)))
    coarse = voxelise(thin_part.tris, across=10)
    if coarse.thinnest() > 2:
        fail.append(f"a five millimetre wall meshed at six millimetre bricks "
                    f"came out {coarse.thinnest()} bricks thick")
    solid_bar = voxelise(S.box(40.0, 40.0, 40.0).tris, across=8)
    if solid_bar.thinnest() != 8:
        fail.append(f"a solid cube eight bricks across says its thinnest wall "
                    f"is {solid_bar.thinnest()} bricks")
    warned = say({"material": "x", "weight_kg": 0.1, "bricks": 10,
                  "brick_mm": 1.0, "load_N": 1.0, "worst_movement_mm": 0.1,
                  "peak_stress_MPa": 1.0, "yield_MPa": 10.0,
                  "factor_of_safety": 10.0, "steps": 1, "seconds": 0.1,
                  "thinnest_wall_bricks": 1})
    if "CAREFUL" not in warned:
        fail.append("a part one brick thick was reported without a word about it")

    # ---- symmetry ----
    #
    # A symmetric part pushed symmetrically has to answer symmetrically. It is
    # the cheapest check there is on the assembly being right, because getting
    # a node's neighbours wrong shows up here and almost nowhere else.
    plate = voxelise(S.box(40.0, 40.0, 5.0).tris, across=8)
    sym = Study(plate, mild, "plate")
    sym.hold("-z")
    sym.push("+z", (0.0, 0.0, -500.0))
    sym.solve(tol=1e-9, most=60000)
    worst = 0.0
    for j in range(plate.n[1] + 1):
        for i in range(plate.n[0] + 1):
            a = sym.moved(plate.node(i, j, plate.n[2]))
            b = sym.moved(plate.node(plate.n[0] - i, j, plate.n[2]))
            worst = max(worst, abs(a[2] - b[2]))
    near("a symmetric part answers symmetrically", worst, 0.0, 1e-9)

    # ---- and what it refuses ----
    loose = Study(voxelise(bar.tris, across=10), mild, "bar")
    loose.push("+x", (F, 0.0, 0.0))
    for what, fn, says in (
            ("a part nothing is holding", lambda: loose.solve(), "holding"),
            ("a part nothing is pushing",
             lambda: Study(voxelise(bar.tris, across=10), mild)
             .hold("-x").solve(), "pushing"),
            ("Poisson's ratio of a half", lambda: hooke(210000.0, 0.5), "half"),
            ("a material with no stiffness", lambda: hooke(0.0, 0.3), "material"),
    ):
        try:
            fn()
            fail.append(f"{what} was allowed")
        except ValueError as e:
            if says not in str(e):
                fail.append(f"{what} was refused for an unclear reason: {e}")

    # Two pieces with only one of them bolted down is not an analysis, and a
    # solver asked for one gives a large confident answer.
    apart = S.box(10.0, 10.0, 10.0)
    far = S.box(10.0, 10.0, 10.0, at=(30.0, 0.0, 0.0))
    both = Solid_of(S, apart, far)
    split = Study(voxelise(both, across=8), mild, "two pieces")
    split.hold("-x")
    split.push("+x", (100.0, 0.0, 0.0))
    try:
        split.solve()
        fail.append("a part in two pieces with one of them loose was solved "
                    "anyway")
    except ValueError as e:
        if "joined" not in str(e):
            fail.append(f"a part in two pieces was refused unclearly: {e}")

    if fail:
        print("SELFTEST FAILED")
        for f in fail:
            print(f"  {f}")
        return 1
    print("selftest ok: a bar pulled straight stretches by FL over AE to the "
          "last digit and carries exactly F over A, twice the load moves it "
          "exactly twice as far, a block held to a uniform stretch reports "
          "that stretch exactly everywhere inside it, a part carried about "
          "without being bent carries no stress, a cantilever comes within a "
          "few percent of the beam formula from one brick thick upwards and "
          "its root stress within a fifth, a symmetric part answers "
          "symmetrically, and a part that is loose, unloaded or in two pieces "
          "is refused rather than answered.")
    return 0


def Solid_of(S, a, b):
    """Two solids side by side, not joined, as one pile of triangles."""
    return list(a.tris) + list(b.tris)


def difference_volume_check(S):
    """A part with a hole in it has to come out lighter than one without."""
    plate = S.box(40.0, 20.0, 10.0)
    holed = S.difference(plate, S.cylinder(6.0, 30.0, segments=32,
                                           at=(20.0, 10.0, -5.0)))
    a = voxelise(plate.tris, across=16)
    b = voxelise(holed.tris, across=16)
    if not (b.volume() < a.volume() * 0.95):
        return (f"a plate with a hole through it voxelised to "
                f"{b.volume():.0f} and the solid one to {a.volume():.0f}, so "
                f"the hole was not seen")
    return ""


def analyse(path, material="6082", across=16, holds=("-z",), pushes=(),
            part=None, weight=False, watch=None):
    """Read a part file, hold it, push it, and answer. The whole thing in one
    call, for anything that wants an answer rather than a toolkit."""
    import solid as S
    if material not in MATERIALS:
        raise ValueError(f"'{material}' is not a material here. "
                         f"There is: {', '.join(sorted(MATERIALS))}")
    pieces = S.read_any(path)
    if part:
        want = part.lower()
        stem = want.rsplit(".", 1)[0]
        chosen = [(nm, s) for nm, s in pieces
                  if nm.lower() in (want, stem) or nm.lower() + ".stl" == want]
        if not chosen:
            raise ValueError(
                f"there is no part called '{part}' in that file. It holds: "
                + ", ".join(nm for nm, _ in pieces))
        pieces = chosen
    elif len(pieces) > 1:
        # The biggest one. An assembly analysed as though it were one solid
        # welds every part to every other and answers a question about a thing
        # that does not exist.
        pieces = [max(pieces, key=lambda p: len(p[1].tris))]
    name, solid = pieces[0]
    grid = voxelise(solid.tris, across=across)
    study = Study(grid, MATERIALS[material], name)
    for face in holds:
        study.hold(face)
    for face, fx, fy, fz in pushes:
        study.push(face, (float(fx), float(fy), float(fz)))
    if weight:
        study.gravity()
    study.solve(watch=watch)
    return study


def say(report, unit="mm"):
    """The answer, in sentences, because a wall of numbers is not an answer."""
    fos = report["factor_of_safety"]
    verdict = ("it is nowhere near yielding" if fos >= 4
               else "there is room in it" if fos >= 2
               else "it holds, but not by much" if fos >= 1.25
               else "it is on the edge of yielding" if fos >= 1.0
               else "IT YIELDS")
    lines = [
        f"{report['material']}, {report['weight_kg'] * 1000:.0f} g, "
        f"{report['bricks']:,} bricks of {report['brick_mm']:.2f} {unit}",
        f"pushed with {report['load_N']:.0f} N",
        f"it moves {report['worst_movement_mm']:.4f} {unit} at the worst point",
        f"the material works hardest at {report['peak_stress_MPa']:.1f} MPa, "
        f"against a yield of {report['yield_MPa']:.0f}",
        f"factor of safety {fos:.2f}: {verdict}",
        f"solved in {report['steps']} steps, {report['seconds']:.1f} s",
    ]
    thin = report.get("thinnest_wall_bricks", 9)
    if thin < 3:
        lines.insert(1, f"CAREFUL: the thinnest wall is {thin} brick"
                        f"{'' if thin == 1 else 's'} across. A wall that thin "
                        f"cannot bend properly however good the brick is, so "
                        f"this reads stiffer than the part is. Ask for more "
                        f"bricks across before believing it.")
    return "\n".join(lines)


def main():
    if "--selftest" in sys.argv:
        return selftest()
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        print(__doc__.strip().splitlines()[0])
        print("\n    python3 tools/fea.py part.stl --fix -z --push +z 0 0 -500"
              " --material 6082 --across 16")
        print("    python3 tools/fea.py --selftest")
        print("\n  materials: " + ", ".join(sorted(MATERIALS)))
        return 2

    def option(flag, count=1):
        out = []
        for i, a in enumerate(sys.argv):
            if a == flag:
                out.append(sys.argv[i + 1:i + 1 + count])
        return out

    holds = [h[0] for h in option("--fix")] or ["-z"]
    pushes = [(p[0], p[1], p[2], p[3]) for p in option("--push", 4)]
    material = (option("--material") or [["6082"]])[0][0]
    across = int((option("--across") or [["16"]])[0][0])
    try:
        study = analyse(args[0], material=material, across=across,
                        holds=holds, pushes=pushes,
                        weight="--weight" in sys.argv,
                        part=(option("--part") or [[None]])[0][0])
    except (ValueError, OSError, KeyError) as e:
        print(f"no answer: {e}")
        return 1
    print(f"{study.name}")
    print(say(study.report()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
