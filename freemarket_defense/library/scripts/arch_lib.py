"""arch_lib: parameterised procedural ARCHITECTURE + CITY generators (white-model style).

Every generator draws into a genkit.MB (`gen(mb, **params)`), in local space:
metres, Z up, origin = ground centre of footprint, FRONT FACES +X.
Wrap with genkit.MB().build(...) or compose (city_block calls building generators).

Facades have real recessed openings: wall faces with holes, reveals, LIB_Glass pane at the
back of the recess, LIB_Dark frame + mullions, white sills.  See `facade()` / `W()`.
"""
import math
import random

from mathutils import Vector

from genkit import (ACCENT, BODY, DARK, FACE_PX, FACE_NY, FONT_BLACK, FONT_BOLD, GLASS, LIGHT, METAL, MB,
                    TAU)

R = math.radians


# ================================================================== facade core
def W(u0, v0, u1, v1, kind="win", mv=0, mh=0, m=None, arch=None, sill=True, depth=None, frame=True):
    """Opening spec. kind: win | shop | door | glassdoor | vent | blank.  arch: None|'round'|'pointed'."""
    return dict(r=(u0, v0, u1, v1), kind=kind, mv=mv, mh=mh, m=m, arch=arch, sill=sill, depth=depth,
                frame=frame)


def _newell(pts):
    n = Vector((0, 0, 0))
    for i in range(len(pts)):
        a, b = Vector(pts[i]), Vector(pts[(i + 1) % len(pts)])
        n.x += (a.y - b.y) * (a.z + b.z)
        n.y += (a.z - b.z) * (a.x + b.x)
        n.z += (a.x - b.x) * (a.y + b.y)
    return n


def oface(mb, pts, toward_dir, m):
    """Add polygon oriented so its normal points along toward_dir."""
    if _newell(pts).dot(Vector(toward_dir)) < 0:
        pts = pts[::-1]
    mb.add(pts, [tuple(range(len(pts)))], m)


def _uniq(xs, eps=1e-4):
    out = []
    for x in sorted(xs):
        if not out or x - out[-1] > eps:
            out.append(x)
    return out


def _arch_pts(u0, v0, u1, v1, arch, seg=10):
    """Arch curve from left spring to right spring; returns (spring_v, pts)."""
    w = u1 - u0
    uc = (u0 + u1) / 2
    if arch == "pointed":
        vs = v1 - w * math.sqrt(3) / 2
        L = [(u1 + w * math.cos(a), vs + w * math.sin(a))
             for a in [math.pi - (math.pi / 3) * k / seg for k in range(seg + 1)]]
        Rr = [(u0 + w * math.cos(a), vs + w * math.sin(a))
              for a in [math.pi / 3 - (math.pi / 3) * k / seg for k in range(1, seg + 1)]]
        return vs, L + Rr
    r = w / 2
    vs = v1 - r
    return vs, [(uc + r * math.cos(a), vs + r * math.sin(a))
                for a in [math.pi - math.pi * k / (2 * seg) for k in range(2 * seg + 1)]]


def _back_mat(o):
    k = o["kind"]
    if o["m"]:
        return o["m"]
    return {"win": GLASS, "shop": GLASS, "glassdoor": GLASS, "door": DARK, "vent": DARK}.get(k, BODY)


def facade(mb, w, h, ops, depth=0.2, wall=BODY, frame=DARK, fw=0.07, sill_m=BODY):
    """Wall in local XZ plane (y=0), outward normal -Y, u along +X [0,w], v along +Z [0,h].
    Returns the top-edge vertices in world space (for roof caps)."""
    ops = [o for o in ops if o["r"][0] > -1e-6 and o["r"][2] < w + 1e-6 and o["r"][3] < h + 1e-6
           and o["r"][1] > -1e-6]
    us = _uniq([0.0, w] + [o["r"][0] for o in ops] + [o["r"][2] for o in ops])
    vs = _uniq([0.0, h] + [o["r"][1] for o in ops] + [o["r"][3] for o in ops])
    nu, nv = len(us) - 1, len(vs) - 1
    own = [[-1] * nv for _ in range(nu)]
    for k, o in enumerate(ops):
        u0, v0, u1, v1 = o["r"]
        for i in range(nu):
            uc = (us[i] + us[i + 1]) / 2
            if not (u0 < uc < u1):
                continue
            for j in range(nv):
                vc = (vs[j] + vs[j + 1]) / 2
                if v0 < vc < v1:
                    own[i][j] = k
    out = (0, -1, 0)
    for i in range(nu):
        for j in range(nv):
            k = own[i][j]
            a, b, c, d = us[i], us[i + 1], vs[j], vs[j + 1]
            if k < 0:
                mb.add([(a, 0, c), (b, 0, c), (b, 0, d), (a, 0, d)], [(0, 1, 2, 3)], wall)
                continue
            o = ops[k]
            if o["arch"]:
                continue
            dp = o["depth"] or depth
            # reveals where the neighbour cell is not the same opening
            if i == 0 or own[i - 1][j] != k:
                oface(mb, [(a, 0, c), (a, dp, c), (a, dp, d), (a, 0, d)], (1, 0, 0), wall)
            if i == nu - 1 or own[i + 1][j] != k:
                oface(mb, [(b, 0, c), (b, dp, c), (b, dp, d), (b, 0, d)], (-1, 0, 0), wall)
            if j == 0 or own[i][j - 1] != k:
                oface(mb, [(a, 0, c), (b, 0, c), (b, dp, c), (a, dp, c)], (0, 0, 1), wall)
            if j == nv - 1 or own[i][j + 1] != k:
                oface(mb, [(a, 0, d), (b, 0, d), (b, dp, d), (a, dp, d)], (0, 0, -1), wall)
            mb.add([(a, dp, c), (b, dp, c), (b, dp, d), (a, dp, d)], [(0, 1, 2, 3)], _back_mat(o))
    for o in ops:
        u0, v0, u1, v1 = o["r"]
        dp = o["depth"] or depth
        if o["arch"]:
            _arch_opening(mb, o, dp, wall, frame, fw)
        elif o["frame"] and o["kind"] in ("win", "shop", "door", "glassdoor"):
            _frame(mb, u0, v0, u1, v1, dp, fw if o["kind"] != "shop" else fw * 1.3, frame,
                   o["mv"], o["mh"], bottom=o["kind"] not in ("door", "glassdoor"))
        if o["sill"] and o["kind"] == "win" and v0 > 0.3:
            mb.bb(u0 - 0.07, -0.08, v0 - 0.09, u1 + 0.07, -0.001, v0, sill_m)
    return [mb.world((u, 0, h)) for u in us]


def _frame(mb, u0, v0, u1, v1, dp, fw, m, mv=0, mh=0, bottom=True, fd=0.06):
    yf, yb = dp - fd, dp - 0.004
    i0, i1, j0, j1 = u0 + fw, u1 - fw, v0 + (fw if bottom else 0), v1 - fw
    O = [(u0, yf, v0), (u1, yf, v0), (u1, yf, v1), (u0, yf, v1)]
    I = [(i0, yf, j0), (i1, yf, j0), (i1, yf, j1), (i0, yf, j1)]
    sides = [(0, 1), (1, 2), (2, 3), (3, 0)]
    for s, (p, q) in enumerate(sides):
        if s == 0 and not bottom:
            continue
        oface(mb, [O[p], O[q], I[q], I[p]], (0, -1, 0), m)
    Ib = [(x, dp, z) for (x, y, z) in I]
    cen = ((i0 + i1) / 2, (j0 + j1) / 2)
    for s, (p, q) in enumerate(sides):
        if s == 0 and not bottom:
            continue
        mid = ((I[p][0] + I[q][0]) / 2, (I[p][2] + I[q][2]) / 2)
        oface(mb, [I[p], I[q], Ib[q], Ib[p]], (cen[0] - mid[0], 0, cen[1] - mid[1]), m)
    t = fw * 0.75
    for k in range(mv):
        x = i0 + (i1 - i0) * (k + 1) / (mv + 1)
        mb.bb(x - t / 2, yf + 0.01, j0, x + t / 2, yb, j1, m)
    for k in range(mh):
        z = j0 + (j1 - j0) * (k + 1) / (mh + 1)
        mb.bb(i0, yf + 0.01, z - t / 2, i1, yb, z + t / 2, m)


def _arch_opening(mb, o, dp, wall, frame, fw):
    u0, v0, u1, v1 = o["r"]
    vs, arc = _arch_pts(u0, v0, u1, v1, o["arch"])
    uc = (u0 + u1) / 2
    apex = len(arc) // 2
    # spandrel fills (wall plane)
    left = [(u0, 0, vs)] + [(x, 0, z) for x, z in arc[1:apex + 1]] + [(u0, 0, v1)]
    right = [(x, 0, z) for x, z in arc[apex:-1]] + [(u1, 0, vs), (u1, 0, v1)]
    oface(mb, left, (0, -1, 0), wall)
    oface(mb, right, (0, -1, 0), wall)
    outline = [(u0, v0), (u1, v0)] + list(reversed(arc))
    # clean duplicate spring points
    ol = []
    for p in outline:
        if not ol or (abs(p[0] - ol[-1][0]) > 1e-5 or abs(p[1] - ol[-1][1]) > 1e-5):
            ol.append(p)
    if abs(ol[0][0] - ol[-1][0]) < 1e-5 and abs(ol[0][1] - ol[-1][1]) < 1e-5:
        ol.pop()
    ol = [(u0, v0), (u1, v0)] + [p for p in ol[2:]]
    C = (uc, (v0 + vs) / 2)
    n = len(ol)
    for k in range(n):
        (xa, za), (xb, zb) = ol[k], ol[(k + 1) % n]
        mx, mz = (xa + xb) / 2, (za + zb) / 2
        oface(mb, [(xa, 0, za), (xb, 0, zb), (xb, dp, zb), (xa, dp, za)], (C[0] - mx, 0, C[1] - mz), wall)
    oface(mb, [(x, dp, z) for x, z in ol], (0, -1, 0), _back_mat(o))
    if o["frame"]:
        path = [(x, dp - 0.03, z) for x, z in ol]
        mb.sweep(path, [(-fw * 0.5, -0.03), (fw * 0.5, -0.03), (fw * 0.5, 0.03), (-fw * 0.5, 0.03)], frame,
                 closed=True, up=(0, 1, 0))
        if o["mv"]:
            mb.bb(uc - fw * 0.35, dp - 0.05, v0, uc + fw * 0.35, dp - 0.005, v1 - 0.05, frame)
        if o["mh"] or o["mv"]:
            mb.bb(u0, dp - 0.05, vs - fw * 0.35, u1, dp - 0.005, vs + fw * 0.35, frame)
    if o["sill"] and o["kind"] == "win" and v0 > 0.3:
        mb.bb(u0 - 0.07, -0.08, v0 - 0.09, u1 + 0.07, -0.001, v0, BODY)


# side keys -> (rotation deg, origin fn, width key)
_SIDES = [("ny", 0, lambda W, D: (-W / 2, -D / 2), 0), ("px", 90, lambda W, D: (W / 2, -D / 2), 1),
          ("py", 180, lambda W, D: (W / 2, D / 2), 0), ("nx", 270, lambda W, D: (-W / 2, D / 2), 1)]


def side_frame(W, D, key):
    """(loc, rz, width) of the facade frame for a side of a W x D footprint."""
    for k, rot, org, wi in _SIDES:
        if k == key:
            x, y = org(W, D)
            return (x, y), R(rot), (W, D)[wi]


def block(mb, W, D, H, z0=0.0, sides=None, cap=True, depth=0.2, wall=BODY, frame=DARK):
    """Closed rectangular mass with a facade on each side.  sides: {'px': ops or fn(width)->ops, ...}"""
    sides = sides or {}
    tops = []
    for key, rot, org, wi in _SIDES:
        width = (W, D)[wi]
        ops = sides.get(key, [])
        if callable(ops):
            ops = ops(width)
        x, y = org(W, D)
        with mb.at((x, y, z0), rz=R(rot)):
            t = facade(mb, width, H, ops, depth, wall, frame)
        tops += t[:-1]
    if cap:
        old = mb.M
        from mathutils import Matrix
        mb.M = Matrix.Identity(4)
        mb.add(tops, [tuple(range(len(tops)))], wall)
        mb.M = old


def row(width, z, wh, n=None, ww=1.3, bay=None, margin=0.9, kind="win", mv=1, mh=0, arch=None, skip=(),
        sill=True, frame=True):
    """A row of n evenly spaced openings across width."""
    if n is None:
        n = max(1, int(round((width - 2 * margin) / (bay or ww * 2.3))))
    if n <= 0:
        return []
    pitch = (width - 2 * margin) / n
    out = []
    for i in range(n):
        if i in skip:
            continue
        c = margin + pitch * (i + 0.5)
        out.append(W(c - ww / 2, z, c + ww / 2, z + wh, kind, mv, mh, arch=arch, sill=sill, frame=frame))
    return out


def floors(width, nf, fh, z0=0.0, sill_h=0.9, wh=1.6, f0=0, **kw):
    out = []
    for f in range(f0, nf):
        out += row(width, z0 + f * fh + sill_h, wh, **kw)
    return out


def at_u(u, z, ww, wh, **kw):
    return W(u - ww / 2, z, u + ww / 2, z + wh, **kw)


# ================================================================== roofs & bits
def gable_roof(mb, W, D, H, pitch=38, over=0.45, over_g=0.35, t=0.2, axis="y", m=BODY, fill_m=BODY):
    """Ridge along local Y (axis='y') or X. Returns ridge height."""
    if axis == "x":
        with mb.at(rz=R(90)):
            return gable_roof(mb, D, W, H, pitch, over, over_g, t, "y", m, fill_m)
    tp = math.tan(R(pitch))
    hw = W / 2
    zr = H + hw * tp
    mb.prism_xz([(-hw, H), (hw, H), (0, zr - 0.02)], -D / 2, D / 2, fill_m)
    tc = t / math.cos(R(pitch))
    xo = hw + over

    def zin(x):
        return H + (hw - abs(x)) * tp

    pts = [(-xo, zin(-xo) + tc), (0, zr + tc), (xo, zin(xo) + tc), (xo, zin(xo)), (0, zr), (-xo, zin(-xo))]
    mb.prism_xz(pts, -D / 2 - over_g, D / 2 + over_g, m)
    return zr + tc


def hip_roof(mb, W, D, H, pitch=30, over=0.5, t=0.25, m=BODY):
    tp = math.tan(R(pitch))
    swap = W > D
    if swap:
        with mb.at(rz=R(90)):
            return hip_roof(mb, D, W, H, pitch, over, t, m)
    We, De = W / 2 + over, D / 2 + over
    ze = H + t - over * tp
    zr = H + t + (W / 2) * tp
    rl = De - We
    v = [(-We, -De, ze - 0.2), (We, -De, ze - 0.2), (We, De, ze - 0.2), (-We, De, ze - 0.2),
         (-We, -De, ze), (We, -De, ze), (We, De, ze), (-We, De, ze),
         (0, -rl, zr), (0, rl, zr)]
    f = [(0, 3, 2, 1), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7),
         (5, 6, 9, 8), (7, 4, 8, 9), (4, 5, 8), (6, 7, 9)]
    mb.add(v, f, m)
    return zr


def pyramid_roof(mb, W, D, H, rise, over=0.3, t=0.2, m=BODY, apex=None):
    We, De = W / 2 + over, D / 2 + over
    ze = H
    v = [(-We, -De, ze - t), (We, -De, ze - t), (We, De, ze - t), (-We, De, ze - t),
         (-We, -De, ze), (We, -De, ze), (We, De, ze), (-We, De, ze), (0, 0, H + rise)]
    f = [(0, 3, 2, 1), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7),
         (4, 5, 8), (5, 6, 8), (6, 7, 8), (7, 4, 8)]
    mb.add(v, f, m)
    return H + rise


def parapet(mb, W, D, H, h=0.9, t=0.3, out=0.06, coping=0.06, m=BODY):
    """Parapet ring on top of a W x D block (slightly proud of the facade)."""
    x, y = W / 2 + out, D / 2 + out
    mb.bb(-x, -y, H, x, -y + t, H + h, m)
    mb.bb(-x, y - t, H, x, y, H + h, m)
    mb.bb(-x, -y + t - 0.001, H, -x + t, y - t + 0.001, H + h - 0.002, m)
    mb.bb(x - t, -y + t - 0.001, H, x, y - t + 0.001, H + h - 0.002, m)
    if coping:
        c = coping
        mb.bb(-x - c, -y - c, H + h, x + c, -y + t + c, H + h + 0.08, m)
        mb.bb(-x - c, y - t - c, H + h, x + c, y + c, H + h + 0.08, m)
        mb.bb(-x - c, -y + t + c - 0.001, H + h + 0.001, -x + t + c, y - t - c + 0.001, H + h + 0.079, m)
        mb.bb(x - t - c, -y + t + c - 0.001, H + h + 0.001, x + c, y - t - c + 0.001, H + h + 0.079, m)


def cornice(mb, W, D, z, h=0.5, out=0.35, m=BODY, steps=2):
    for k in range(steps):
        o = out * (k + 1) / steps
        hh = h / steps
        mb.bb(-W / 2 - o, -D / 2 - o, z + k * hh, W / 2 + o, D / 2 + o, z + (k + 1) * hh, m)


def band(mb, W, D, z, h=0.25, out=0.06, m=BODY):
    mb.bb(-W / 2 - out, -D / 2 - out, z, W / 2 + out, D / 2 + out, z + h, m)


def rooftop_units(mb, W, D, H, rnd, n=3, m=BODY):
    for _ in range(n):
        w, d, h = rnd.uniform(1.5, 3.5), rnd.uniform(1.5, 3), rnd.uniform(1.0, 2.2)
        x = rnd.uniform(-W / 2 + w / 2 + 1, W / 2 - w / 2 - 1)
        y = rnd.uniform(-D / 2 + d / 2 + 1, D / 2 - d / 2 - 1)
        mb.bb(x - w / 2, y - d / 2, H, x + w / 2, y + d / 2, H + h, m)
        if rnd.random() < 0.5:
            mb.cyl(min(w, d) * 0.3, 0.25, (x, y, H + h), DARK, n=12)


def stairs(mb, x0, n, rise, tread, width, z0=0.0, back=1.0, m=BODY, yc=0.0):
    """Straight stair rising toward -X, first riser at x0 + n*tread (front), top landing at x0."""
    pts = [(x0 - back, z0), (x0 + n * tread, z0)]
    for i in range(n):
        x = x0 + (n - i) * tread
        pts.append((x, z0 + (i + 1) * rise))
        pts.append((x - tread, z0 + (i + 1) * rise))
    pts[-1] = (x0 - back, z0 + n * rise)
    mb.prism_xz(pts, yc - width / 2, yc + width / 2, m)


def column(mb, h, r, loc=(0, 0, 0), order="doric", m=BODY, n=16):
    x, y, z = loc
    pl = r * 1.35
    mb.bb(x - pl, y - pl, z, x + pl, y + pl, z + r * 0.3, m)
    ch = r * (0.9 if order == "doric" else 1.1)
    prof = [(r * 1.25, 0.0), (r * 1.25, r * 0.12), (r * 1.1, r * 0.22), (r * 1.02, r * 0.32), (r, r * 0.4),
            (r * 0.97, h * 0.35), (r * 0.86, h - ch - r * 0.3), (r * 0.9, h - ch - r * 0.3 + 0.04),
            (r * 0.9, h - ch - r * 0.25), (r * 1.2 if order == "doric" else r * 1.05, h - r * 0.55),
            (r * 1.2, h - r * 0.42), (0, h - r * 0.42)]
    mb.lathe(prof, m, n=n, loc=(x, y, z + r * 0.3 - 0.0))
    ab = r * 1.3
    mb.bb(x - ab, y - ab, z + h - r * 0.42 + r * 0.3, x + ab, y + ab, z + h + r * 0.3 - 0.12 * r, m)
    if order == "ionic":
        for s in (-1, 1):
            mb.cyl(r * 0.32, ab * 2.05, (x - ab * 1.02, y + s * ab * 0.95, z + h + r * 0.3 - r * 0.62), m,
                   n=12, rot=(0, R(90), 0))
    return z + h + r * 0.3 - 0.12 * r


def chimney(mb, x, y, z0, z1, w=0.6, d=1.0, m=BODY):
    mb.bb(x - w / 2, y - d / 2, z0, x + w / 2, y + d / 2, z1, m)
    mb.bb(x - w / 2 - 0.06, y - d / 2 - 0.06, z1, x + w / 2 + 0.06, y + d / 2 + 0.06, z1 + 0.15, m)
    for k in range(max(1, int(d / 0.45))):
        yy = y - d / 2 + (k + 0.5) * d / max(1, int(d / 0.45))
        mb.cyl(0.11, 0.35, (x, yy, z1 + 0.15), DARK, n=10)


def flagpole(mb, h=8.0, loc=(0, 0, 0), flag=True, fw=1.8, fh=1.1, m=ACCENT, seed=0):
    x, y, z = loc
    mb.cyl(0.06, h, (x, y, z), BODY, n=10, r2=0.04)
    mb.sphere(0.09, (x, y, z + h + 0.05), BODY, seg=10, rings=5)
    if flag:
        cloth(mb, fw, fh, (x + 0.05, y, z + h - fh - 0.15), m, seed=seed)


def cloth(mb, fw, fh, loc, m=ACCENT, amp=0.12, waves=1.6, nu=14, nv=4, t=0.02, seed=0):
    """Waving flag cloth in XZ plane starting at loc (hoist edge) extending +X."""
    x0, y0, z0 = loc
    rows = []
    for j in range(nv + 1):
        r_ = []
        for i in range(nu + 1):
            u = i / nu
            yy = amp * math.sin(TAU * waves * u + seed + j * 0.25) * u ** 0.7
            r_.append((x0 + u * fw, y0 + yy, z0 + j / nv * fh - u * 0.06 * fh))
        rows.append(r_)
    v, f = [], []
    for side in (-t / 2, t / 2):
        for r_ in rows:
            for (x, y, z) in r_:
                v.append((x, y + side, z))
    N = (nu + 1) * (nv + 1)
    for j in range(nv):
        for i in range(nu):
            a = j * (nu + 1) + i
            f.append((a, a + 1, a + nu + 2, a + nu + 1))
            f.append((N + a, N + a + nu + 1, N + a + nu + 2, N + a + 1))
    # edges
    for j in range(nv):
        for i in (0, nu):
            a = j * (nu + 1) + i
            b = a + nu + 1
            f.append((a, b, N + b, N + a) if i == 0 else (a, N + a, N + b, b))
    for i in range(nu):
        for j in (0, nv):
            a = j * (nu + 1) + i
            f.append((a, N + a, N + a + 1, a + 1) if j == 0 else (a, a + 1, N + a + 1, N + a))
    mb.add(v, f, m)


def awning(mb, u0, u1, z, proj=1.4, drop=0.7, val=0.28, m=ACCENT, stripes=0, m2=BODY):
    """Sloped shop awning on a facade in local facade space (wall y=0, out = -Y)."""
    def seg(a, b, mm):
        mb.add([(a, 0.02, z), (b, 0.02, z), (b, -proj, z - drop), (a, -proj, z - drop),
                (a, 0.02, z + 0.04), (b, 0.02, z + 0.04), (b, -proj, z - drop + 0.04), (a, -proj, z - drop + 0.04)],
               [(0, 1, 2, 3), (7, 6, 5, 4), (3, 2, 6, 7), (0, 3, 7, 4), (1, 5, 6, 2), (0, 4, 5, 1)], mm)
        mb.bb(a, -proj - 0.03, z - drop - val, b, -proj + 0.0, z - drop + 0.04, mm)
    if stripes:
        n = stripes
        for k in range(n):
            a = u0 + (u1 - u0) * k / n
            b = u0 + (u1 - u0) * (k + 1) / n
            seg(a, b, m if k % 2 == 0 else m2)
    else:
        seg(u0, u1, m)
    for u in (u0, u1):
        mb.add([(u, 0.02, z + 0.04), (u, -proj, z - drop + 0.04), (u, -proj, z - drop - val), (u, 0.02, z - 0.35)],
               [(0, 1, 2, 3), (3, 2, 1, 0)], m)


def sign_panel(mb, u0, u1, z0, z1, text="", m=ACCENT, tm=DARK, proud=0.15, font=FONT_BLACK, size=None):
    """Sign box on facade (local facade space)."""
    mb.bb(u0, -proud, z0, u1, 0.01, z1, m)
    if text:
        s = size or (z1 - z0) * 0.62
        mb.text(text, s, ((u0 + u1) / 2, -proud - 0.001, (z0 + z1) / 2), tm, rot=FACE_NY, depth=0.03,
                font=font)


def door_steps(mb, u, w, n=2, rise=0.15, tread=0.32):
    """steps in front of a facade door (facade space) - box stack toward -Y."""
    for i in range(n):
        mb.bb(u - w / 2 - 0.1 * (n - i), -tread * (n - i), i * rise, u + w / 2 + 0.1 * (n - i), 0.0, (i + 1) * rise,
              BODY)


# ================================================================== buildings
def house(mb, frontage=10.0, depth=8.0, storeys=2, roof="gable", porch=True, chimneys=1, fh=2.9,
          pitch=38, door_m=DARK, seed=0):
    """Detached house. roof: gable | hip | flat.  Front (door) faces +X."""
    rnd = random.Random(seed)
    P = 0.45
    Wx, Dy = depth, frontage
    H = storeys * fh + 0.25
    mb.bb(-Wx / 2 - 0.06, -Dy / 2 - 0.06, 0, Wx / 2 + 0.06, Dy / 2 + 0.06, P, BODY)  # plinth
    big = roof == "flat"
    ww, wh = (2.2, 1.9) if big else (1.2, 1.45)

    def front(w):
        ops = [W(w / 2 - 0.55, P, w / 2 + 0.55, P + 2.2, "door", mv=0, m=door_m)]
        for u in (w * 0.2, w * 0.8):
            ops.append(at_u(u, P + 0.9, ww, wh, mv=1))
        for f in range(1, storeys):
            for u in ((w * 0.2, w * 0.5, w * 0.8) if not big else (w * 0.25, w * 0.75)):
                ops.append(at_u(u, P + f * fh + 0.9, ww, wh, mv=1))
        return ops

    def side(w):
        return floors(w, storeys, fh, P, 0.9, wh, n=2 if w > 7 else 1, ww=1.0 if not big else 1.6, mv=0)

    def back(w):
        return floors(w, storeys, fh, P, 0.9, wh, n=3, ww=1.1, mv=1)

    block(mb, Wx, Dy, H, 0.0, {"px": front, "ny": side, "py": side, "nx": back}, cap=(roof != "gable"))
    mb.bb(Wx / 2, -0.9, 0, Wx / 2 + 0.5, 0.9, P - 0.15, BODY)  # step
    if roof == "gable":
        zr = gable_roof(mb, Wx, Dy, H, pitch, over=0.45, over_g=0.35)
    elif roof == "hip":
        zr = hip_roof(mb, Wx, Dy, H, pitch * 0.8, over=0.5)
    else:
        parapet(mb, Wx, Dy, H, h=0.5, t=0.25)
        zr = H + 0.5
        # cantilevered upper-floor eyebrow
        mb.bb(Wx / 2, -Dy / 2 - 0.06, P + fh - 0.05, Wx / 2 + 1.2, Dy / 2 + 0.06, P + fh + 0.2, BODY)
    for k in range(chimneys):
        y = (Dy / 2 - 1.2) * (1 if k == 0 else -1)
        x = -Wx * 0.18
        chimney(mb, x, y, H - 0.5, (zr if roof != "flat" else H) + 0.9, 0.7, 1.0)
    if porch and roof != "flat":
        px0 = Wx / 2
        mb.bb(px0, -1.8, 0, px0 + 2.0, 1.8, P, BODY)
        for s in (-1, 1):
            mb.bb(px0 + 1.75, s * 1.6 - 0.09, P, px0 + 1.93, s * 1.6 + 0.09, P + 2.55, BODY)
        zp = P + 2.55
        # small gabled porch roof
        tp = math.tan(R(32))
        mb.prism_yz([(-2.05, zp), (2.05, zp), (2.05, zp + 0.18), (0, zp + 0.18 + 2.05 * tp),
                     (-2.05, zp + 0.18)], px0 - 0.05, px0 + 2.15, BODY)
    return dict(size=(Wx, Dy, zr))


def terrace(mb, units=5, unit_w=5.6, depth=9.5, storeys=2, fh=3.0, pitch=35, bays=True, seed=0,
            accent_doors=True):
    """Row of terraced houses along Y, fronts +X; continuous gable roof, party-wall chimneys."""
    rnd = random.Random(seed)
    P = 0.4
    D = units * unit_w
    H = storeys * fh + 0.3

    def front(w):
        ops = []
        for k in range(units):
            u0 = k * unit_w
            ops.append(W(u0 + 0.8, P, u0 + 1.85, P + 2.3, "door", m=ACCENT if (accent_doors and k % 2 == 0) else DARK))
            if not bays:
                ops.append(at_u(u0 + unit_w * 0.65, P + 0.8, 1.9, 1.6, mv=2))
            for f in range(1, storeys):
                ops.append(at_u(u0 + 1.35, P + f * fh + 0.85, 1.0, 1.5, mv=0))
                ops.append(at_u(u0 + unit_w * 0.68, P + f * fh + 0.85, 1.5, 1.5, mv=1))
        return ops

    def back(w):
        return floors(w, storeys, fh, P, 0.9, 1.4, n=units * 2, ww=1.1, mv=0)

    def side(w):
        return floors(w, storeys, fh, P, 0.9, 1.4, n=1, ww=1.0, mv=0, f0=1)

    mb.bb(-depth / 2 - 0.05, -D / 2 - 0.05, 0, depth / 2 + 0.05, D / 2 + 0.05, P, BODY)
    block(mb, depth, D, H, 0, {"px": front, "nx": back, "ny": side, "py": side}, cap=False)
    zr = gable_roof(mb, depth, D, H, pitch, over=0.35, over_g=0.3)
    for k in range(units + 1):
        y = -D / 2 + k * unit_w
        y = max(-D / 2 + 0.6, min(D / 2 - 0.6, y))
        chimney(mb, -0.6, y, H, zr + 0.6, 0.8, 1.2)
        if 0 < k < units:  # party-wall pilaster strip
            mb.bb(depth / 2 - 0.01, y - 0.12, P, depth / 2 + 0.06, y + 0.12, H, BODY)
    for k in range(units):
        y0 = -D / 2 + k * unit_w
        yc = y0 + unit_w * 0.65
        mb.bb(depth / 2, y0 + 0.65, 0, depth / 2 + 0.6, y0 + 2.0, 0.15, BODY)  # step
        if bays:
            bw = 2.6
            with mb.at((depth / 2 + 0.4, yc, P)):
                block(mb, 0.8, bw, 2.6, 0, {"px": lambda w: [W(0.25, 0.7, w - 0.25, 2.25, mv=2)],
                                            "ny": lambda w: [W(0.15, 0.7, w - 0.15, 2.25, mv=0, sill=False)],
                                            "py": lambda w: [W(0.15, 0.7, w - 0.15, 2.25, mv=0, sill=False)]},
                      depth=0.08)
                mb.bb(-0.45, -bw / 2 - 0.1, 2.6, 0.5, bw / 2 + 0.1, 2.8, BODY)
    # rear garden walls
    for k in range(units + 1):
        y = -D / 2 + k * unit_w
        mb.bb(-depth / 2 - 6, y - 0.12, 0, -depth / 2, y + 0.12, 1.8, BODY)
    return dict(size=(depth + 6, D, zr))


def apartment(mb, width=32.0, depth=14.0, storeys=6, fh=3.0, balconies=True, seed=0):
    rnd = random.Random(seed)
    G = 3.8
    H = G + (storeys - 1) * fh
    bay = 4.0
    nb = int(width // bay)
    margin = (width - nb * bay) / 2

    def front(w):
        ops = [W(w / 2 - 1.2, 0, w / 2 + 1.2, 2.8, "glassdoor", mv=1)]
        for k in range(nb):
            c = margin + bay * (k + 0.5)
            if abs(c - w / 2) > 2.5:
                ops.append(at_u(c, 1.0, 2.4, 2.0, mv=1))
            for f in range(storeys - 1):
                z = G + f * fh
                if balconies and k % 2 == 0:
                    ops.append(at_u(c, z, 1.7, 2.45, kind="glassdoor", mv=1))
                else:
                    ops.append(at_u(c, z + 0.9, 1.6, 1.5, mv=1))
        return ops

    def back(w):
        return floors(w, storeys - 1, fh, G, 0.9, 1.5, n=nb, ww=1.5, mv=1) + row(w, 1.0, 1.8, n=nb, ww=1.6)

    def side(w):
        return floors(w, storeys - 1, fh, G, 0.9, 1.5, n=2, ww=1.2, mv=0) + row(w, 1.0, 1.8, n=2, ww=1.2)

    block(mb, depth, width, H, 0, {"px": front, "nx": back, "ny": side, "py": side})
    # floor bands on front
    for f in range(storeys - 1):
        mb.bb(depth / 2 - 0.01, -width / 2 - 0.05, G + f * fh - 0.18, depth / 2 + 0.05, width / 2 + 0.05,
              G + f * fh + 0.02, BODY)
    if balconies:
        for k in range(0, nb, 2):
            yc = -width / 2 + margin + bay * (k + 0.5)
            for f in range(storeys - 1):
                z = G + f * fh
                x0 = depth / 2
                mb.bb(x0, yc - 1.6, z - 0.2, x0 + 1.5, yc + 1.6, z, BODY)
                mb.bb(x0 + 1.38, yc - 1.6, z, x0 + 1.5, yc + 1.6, z + 1.05, BODY)
                for s in (-1, 1):
                    mb.bb(x0 + 0.01, yc + s * 1.6 - 0.06, z, x0 + 1.38, yc + s * 1.6 + 0.06, z + 1.05, BODY)
    # entrance canopy
    mb.bb(depth / 2, -2.4, 3.0, depth / 2 + 2.2, 2.4, 3.25, BODY)
    parapet(mb, depth, width, H, 0.8, 0.3)
    # stair / lift tower
    mb.bb(-2.5, -2.0, H, 2.5, 3.0, H + 3.0, BODY)
    rooftop_units(mb, depth - 4, width - 4, H, rnd, 3)
    return dict(size=(depth + 2.2, width, H + 3))


def curtain_block(mb, W_, D_, z0, H, fh, pitch=1.5, band_h=0.9, mull_m=BODY, band_m=BODY, roof=True):
    """Glass-core block with white spandrel bands per floor and vertical mullions (curtain wall)."""
    mb.bb(-W_ / 2, -D_ / 2, z0, W_ / 2, D_ / 2, z0 + H, GLASS)
    nf = max(1, int(round(H / fh)))
    fh = H / nf
    for f in range(1, nf):
        z = z0 + f * fh
        mb.bb(-W_ / 2 - 0.06, -D_ / 2 - 0.06, z - band_h / 2, W_ / 2 + 0.06, D_ / 2 + 0.06, z + band_h / 2, band_m)
    for L, other, axis in ((W_, D_, "x"), (D_, W_, "y")):
        n = max(1, int(round(L / pitch)))
        for k in range(n + 1):
            u = -L / 2 + L * k / n
            for s in (-1, 1):
                if axis == "x":
                    mb.bb(u - 0.05, s * D_ / 2 - 0.12, z0, u + 0.05, s * D_ / 2 + 0.12, z0 + H, mull_m)
                else:
                    mb.bb(s * W_ / 2 - 0.12, u - 0.05, z0, s * W_ / 2 + 0.12, u + 0.05, z0 + H, mull_m)
    if roof:
        mb.bb(-W_ / 2 - 0.15, -D_ / 2 - 0.15, z0 + H - 0.4, W_ / 2 + 0.15, D_ / 2 + 0.15, z0 + H + 0.5, band_m)


def punched_block(mb, W_, D_, z0, H, fh, ww=1.6, wh=2.0, bay=3.0, roof=True):
    nf = max(1, int(round(H / fh)))
    fh = H / nf
    fn = lambda w: floors(w, nf, fh, 0, 0.95, wh, ww=ww, bay=bay, margin=1.2, mv=1, sill=False)
    block(mb, W_, D_, H, z0, {"px": fn, "nx": fn, "py": fn, "ny": fn}, depth=0.3)
    if roof:
        parapet(mb, W_, D_, z0 + H, 1.0, 0.4, out=0.08)


def office_tower(mb, width=26.0, depth=22.0, storeys=14, fh=3.8, style="curtain", tiers=((0.65, 0.82),),
                 lobby=6.0, logo=True, seed=0):
    """tiers: ((fraction_of_height_where_setback_starts, scale), ...).  style: curtain | punched."""
    rnd = random.Random(seed)
    H = lobby + (storeys - 1) * fh
    # lobby: recessed glass with piloti columns
    ins = 1.4
    mb.bb(-depth / 2 + ins, -width / 2 + ins, 0, depth / 2 - ins, width / 2 - ins, lobby, GLASS)
    n = max(2, int(width // 6))
    for k in range(n + 1):
        y = -width / 2 + 0.5 + (width - 1.0) * k / n
        for s in (-1, 1):
            mb.bb(s * (depth / 2 - 0.5) - 0.4, y - 0.4, 0, s * (depth / 2 - 0.5) + 0.4, y + 0.4, lobby, BODY)
    m_ = max(2, int(depth // 6))
    for k in range(1, m_):
        x = -depth / 2 + 0.5 + (depth - 1.0) * k / m_
        for s in (-1, 1):
            mb.bb(x - 0.4, s * (width / 2 - 0.5) - 0.4, 0, x + 0.4, s * (width / 2 - 0.5) + 0.4, lobby, BODY)
    mb.bb(depth / 2 - ins - 0.1, -3, 0, depth / 2 + 1.5, 3, 0.1, BODY)
    mb.bb(depth / 2 - 0.5, -4.5, lobby - 1.6, depth / 2 + 3.5, 4.5, lobby - 1.3, BODY)  # entrance canopy
    # tiers
    cuts = [0.0] + [t[0] for t in tiers] + [1.0]
    scales = [1.0] + [t[1] for t in tiers]
    body_h = H - lobby
    zt = lobby
    for i in range(len(cuts) - 1):
        h = body_h * (cuts[i + 1] - cuts[i])
        h = max(fh, round(h / fh) * fh)
        if i == len(cuts) - 2:
            h = max(fh, H - zt)
        s = scales[i]
        if style == "curtain":
            curtain_block(mb, depth * s, width * s, zt, h, fh)
        else:
            punched_block(mb, depth * s, width * s, zt, h, fh)
        zt += h
    s = scales[-1]
    # mechanical penthouse
    mb.bb(-depth * s * 0.25, -width * s * 0.3, zt, depth * s * 0.25, width * s * 0.3, zt + 4.0, BODY)
    if logo:
        mb.bb(depth * s / 2 + 0.1, -width * s * 0.3, zt - 3.2, depth * s / 2 + 0.35, width * s * 0.3, zt - 0.8,
              ACCENT)
    return dict(size=(depth, width, zt + 4))


def skyscraper(mb, width=36.0, storeys=60, fh=3.9, crown="spire", taper=(1.0, 0.86, 0.72, 0.55), seed=0):
    """Supertall. crown: spire | pyramid | deco | mast."""
    lobby = 9.0
    H = lobby + storeys * fh
    w = width
    ins = 2.0
    mb.bb(-w / 2 + ins, -w / 2 + ins, 0, w / 2 - ins, w / 2 - ins, lobby, GLASS)
    for k in range(6):
        u = -w / 2 + 0.6 + (w - 1.2) * k / 5
        for s in (-1, 1):
            mb.bb(s * (w / 2 - 0.6) - 0.6, u - 0.6, 0, s * (w / 2 - 0.6) + 0.6, u + 0.6, lobby, BODY)
            mb.bb(u - 0.6, s * (w / 2 - 0.6) - 0.6, 0, u + 0.6, s * (w / 2 - 0.6) + 0.6, lobby, BODY)
    nt = len(taper)
    zt = lobby
    seg = (H - lobby) / nt
    for i, s in enumerate(taper):
        h = round(seg / fh) * fh
        curtain_block(mb, w * s, w * s, zt, h, fh, pitch=1.6)
        zt += h
    s = taper[-1] * w
    if crown == "spire":
        mb.bb(-s * 0.35, -s * 0.35, zt, s * 0.35, s * 0.35, zt + 8, BODY)
        mb.cyl(s * 0.12, 10, (0, 0, zt + 8), BODY, n=16, r2=s * 0.08)
        mb.cyl(s * 0.08, 55, (0, 0, zt + 18), BODY, n=12, r2=0.15)
        top = zt + 73
    elif crown == "pyramid":
        mb.bb(-s / 2 - 0.2, -s / 2 - 0.2, zt, s / 2 + 0.2, s / 2 + 0.2, zt + 1.2, BODY)
        mb.add([(-s / 2, -s / 2, zt + 1.2), (s / 2, -s / 2, zt + 1.2), (s / 2, s / 2, zt + 1.2),
                (-s / 2, s / 2, zt + 1.2), (0, 0, zt + 1.2 + s * 1.2)],
               [(0, 1, 4), (1, 2, 4), (2, 3, 4), (3, 0, 4), (3, 2, 1, 0)], GLASS)
        for (a, b) in (((-1, -1), (1, -1)), ((1, -1), (1, 1)), ((1, 1), (-1, 1)), ((-1, 1), (-1, -1))):
            mb.rod((a[0] * s / 2, a[1] * s / 2, zt + 1.2), (0, 0, zt + 1.2 + s * 1.2), 0.25, BODY, n=6)
        mb.cyl(0.4, 12, (0, 0, zt + 1.2 + s * 1.2 - 1), BODY, n=8, r2=0.1)
        top = zt + s * 1.2 + 12
    elif crown == "deco":
        z = zt
        for k, f in enumerate((0.85, 0.68, 0.5, 0.34)):
            hh = 6.0 - k
            mb.bb(-s * f / 2, -s * f / 2, z, s * f / 2, s * f / 2, z + hh, BODY)
            for (sx, sy) in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
                mb.cyl(0.5, 2.5, (sx * s * f / 2, sy * s * f / 2, z + hh), BODY, n=8, r2=0.05)
            # vertical slot windows on each tier
            for sgn in (-1, 1):
                for j in range(3):
                    u = (j - 1) * s * f * 0.25
                    mb.bb(sgn * s * f / 2 - 0.02, u - 0.3, z + 1, sgn * s * f / 2 + 0.03, u + 0.3, z + hh - 1, GLASS)
                    mb.bb(u - 0.3, sgn * s * f / 2 - 0.02, z + 1, u + 0.3, sgn * s * f / 2 + 0.03, z + hh - 1, GLASS)
            z += hh
        mb.cyl(s * 0.12, 20, (0, 0, z), BODY, n=12, r2=0.1)
        top = z + 20
    else:  # mast
        mb.bb(-s * 0.3, -s * 0.3, zt, s * 0.3, s * 0.3, zt + 6, BODY)
        mb.cyl(0.8, 30, (0, 0, zt + 6), DARK, n=8, r2=0.3)
        top = zt + 36
    return dict(size=(w, w, top))


def storefront(mb, frontage=7.0, depth=14.0, storeys=3, fh=3.2, sign="SHOP", awning_m=ACCENT, stripes=0,
               seed=0):
    G = 4.4
    H = G + (storeys - 1) * fh

    def front(w):
        ops = [W(0.6, 0, 1.75, 2.6, "glassdoor", mv=0),
               W(2.05, 0.55, w - 0.6, 2.9, "shop", mv=2, depth=0.35)]
        for f in range(storeys - 1):
            ops += row(w, G + f * fh + 0.9, 1.6, n=2 if w < 8 else 3, ww=1.3, margin=0.8, mv=1)
        return ops

    def back(w):
        return floors(w, storeys - 1, fh, G, 0.9, 1.5, n=2, ww=1.2, mv=0) + [W(w / 2 - 0.5, 0, w / 2 + 0.5, 2.2, "door")]

    block(mb, depth, frontage, H, 0, {"px": front, "nx": back})
    x0 = depth / 2
    with mb.at((x0, -frontage / 2, 0), rz=R(90)):
        # pilasters framing the shopfront + fascia
        for u in (0.0, frontage - 0.35):
            mb.bb(u, -0.12, 0, u + 0.35, 0.0, G - 0.1, BODY)
        sign_panel(mb, 0.25, frontage - 0.25, 3.35, 4.15, sign, ACCENT, DARK, proud=0.18)
        awning(mb, 0.4, frontage - 0.4, 3.25, proj=1.5, drop=0.75, m=awning_m, stripes=stripes)
    band(mb, depth, frontage, G - 0.1, 0.18, 0.05)
    cornice(mb, depth, frontage, H, 0.45, 0.3)
    parapet(mb, depth, frontage, H + 0.45, 0.6, 0.25, out=0.0, coping=0.04)
    return dict(size=(depth + 1.5, frontage, H + 1))


def corner_cafe(mb, size=12.0, storeys=2, fh=3.3, sign="CAFÉ", tables=3, seed=0):
    """Corner café: shopfronts on +X and -Y with wrapping striped awnings, sign, terrace tables."""
    G = 4.0
    H = G + (storeys - 1) * fh

    def shopside(w, door):
        ops = []
        if door:
            ops.append(W(w - 2.0, 0, w - 0.7, 2.6, "glassdoor"))
            ops.append(W(0.8, 0.6, w - 2.4, 3.0, "shop", mv=3, depth=0.35))
        else:
            ops.append(W(0.7, 0.6, w - 0.8, 3.0, "shop", mv=3, depth=0.35))
        for f in range(storeys - 1):
            ops += row(w, G + f * fh + 0.9, 1.6, n=3, ww=1.3, mv=1)
        return ops

    side = lambda w: floors(w, storeys - 1, fh, G, 0.9, 1.6, n=3, ww=1.3, mv=1) + row(w, 1.0, 1.8, n=2, ww=1.4)
    block(mb, size, size, H, 0, {"px": lambda w: shopside(w, True), "ny": lambda w: shopside(w, False),
                                 "py": side, "nx": side})
    band(mb, size, size, G - 0.15, 0.2, 0.06)
    cornice(mb, size, size, H, 0.5, 0.35)
    parapet(mb, size, size, H + 0.5, 0.5, 0.25, out=0.0, coping=0.04)
    for key in ("px", "ny"):
        (x, y), rz, w = side_frame(size, size, key)
        with mb.at((x, y, 0), rz=rz):
            awning(mb, 0.3, w - 0.3, 3.45, proj=1.8, drop=0.8, stripes=9)
            if key == "px":
                sign_panel(mb, w * 0.2, w * 0.8, 4.15 + 0.1, 4.15 + 0.85, sign, ACCENT, DARK, proud=0.15)
    # terrace furniture along +X
    for k in range(tables):
        y = -size / 2 + 2.0 + k * (size - 3.5) / max(1, tables - 1)
        x = size / 2 + 3.2
        cafe_table(mb, (x, y, 0), parasol=(k % 2 == 0))
    return dict(size=(size + 5, size + 2, H + 1))


def cafe_table(mb, loc, parasol=True):
    x, y, z = loc
    mb.cyl(0.35, 0.03, (x, y, z), DARK, n=12)
    mb.cyl(0.035, 0.72, (x, y, z), DARK, n=6)
    mb.cyl(0.4, 0.03, (x, y, z + 0.72), BODY, n=16)
    for a in (0, math.pi):
        cx, cy = x + 0.65 * math.cos(a), y + 0.65 * math.sin(a)
        chair(mb, (cx, cy, z), a + math.pi)
    if parasol:
        mb.cyl(0.025, 2.3, (x, y, z + 0.75), BODY, n=6)
        mb.cyl(1.3, 0.45, (x, y, z + 2.35), ACCENT, n=8, r2=0.05)


def chair(mb, loc, rz=0.0, m=DARK, seat_m=BODY):
    with mb.at(loc, rz=rz):
        for (sx, sy) in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
            mb.bb(sx * 0.19 - 0.015, sy * 0.19 - 0.015, 0, sx * 0.19 + 0.015, sy * 0.19 + 0.015, 0.45, m)
        mb.bb(-0.22, -0.22, 0.45, 0.22, 0.22, 0.49, seat_m)
        mb.bb(-0.22, -0.22, 0.49, -0.19, 0.22, 0.9, seat_m)


def classical(mb, width=24.0, depth=30.0, height=12.0, columns=6, order="doric", text="BANK", steps=8,
              pediment=True, dome=False, wings=0, wing_w=18.0, emblem=True, attic=0.0, seed=0):
    """Classical temple-front building (bank / exchange / central bank / parliament).
    Portico on +X with `columns`, pediment, frieze text, steps; optional dome and side wings (along Y)."""
    rise, tread = 0.18, 0.4
    P = steps * rise
    Wx, Dy = depth, width
    # podium
    mb.bb(-Wx / 2 - 0.4, -Dy / 2 - 0.4, 0, Wx / 2, Dy / 2 + 0.4, P, BODY)
    mb.bb(-Wx / 2 - 0.5, -Dy / 2 - 0.5, P - 0.25, Wx / 2 + 0.1, Dy / 2 + 0.5, P, BODY)
    pd = 4.5  # portico depth
    pw = min(Dy - 1.0, columns * 3.2)
    cr = min(0.75, pw / columns * 0.2)
    ch = height - 1.0
    xfront = Wx / 2 + pd
    mb.bb(Wx / 2 - 0.2, -pw / 2 - 0.8, 0, xfront, pw / 2 + 0.8, P, BODY)
    # move stairs in front of portico floor
    # (portico floor spans to xfront, so the stair starts there)
    stairs(mb, xfront, steps, rise, tread, pw + 1.6, back=0.2)

    win = lambda w: [W(u - 1.0, 2.2, u + 1.0, 8.2, "win", mv=1, mh=2, arch="round")
                     for u in [w * (k + 0.5) / max(1, int(w // 6)) for k in range(max(1, int(w // 6)))]]

    def front(w):
        ops = [W(w / 2 - 1.7, 0, w / 2 + 1.7, 6.5, "door", mv=1)]
        if w > 14:
            for u in (w / 2 - 6.0, w / 2 + 6.0):
                ops.append(W(u - 0.9, 2.0, u + 0.9, 6.8, "win", mv=1, mh=2, arch="round"))
        return ops

    block(mb, Wx, Dy, height, P, {"px": front, "ny": win, "py": win, "nx": win}, depth=0.3)
    # pilasters on long sides
    for s_ in (-1, 1):
        n = max(2, int(Wx // 6))
        for k in range(n + 1):
            x = -Wx / 2 + 0.4 + (Wx - 0.8) * k / n
            y0, y1 = s_ * Dy / 2, s_ * (Dy / 2 + 0.18)
            mb.bb(x - 0.45, min(y0, y1), P, x + 0.45, max(y0, y1), P + height - 0.2, BODY)
    # base band & entablature around main block
    band(mb, Wx, Dy, P, 1.2, 0.08)
    ztop = P + height
    # columns
    zc = P
    for k in range(columns):
        y = -pw / 2 + pw * (k + 0.5) / columns
        column(mb, ch, cr, (xfront - 1.0, y, zc), order)
    for s in (-1, 1):  # return columns at portico sides
        column(mb, ch, cr, (Wx / 2 + 1.5, s * (pw / 2 - pw / columns / 2), zc), order)
    zent = zc + ch + cr * 0.3 - 0.12 * cr
    # entablature: architrave, frieze, cornice over portico and main block
    fr_h = 2.0
    mb.bb(Wx / 2 - 0.5, -pw / 2 - 0.4, zent, xfront - 0.0, pw / 2 + 0.4, zent + 0.8, BODY)
    mb.bb(Wx / 2 - 0.5, -pw / 2 - 0.4, zent + 0.8, xfront - 0.1, pw / 2 + 0.4, zent + 0.8 + fr_h, BODY)
    mb.bb(Wx / 2 - 0.5, -pw / 2 - 0.7, zent + 0.8 + fr_h, xfront + 0.3, pw / 2 + 0.7, zent + 1.2 + fr_h, BODY)
    zco = zent + 1.2 + fr_h
    cornice(mb, Wx, Dy, ztop, 0.8, 0.45)
    if text:
        tsz = min(fr_h * 0.7, (pw * 0.85) / max(1, len(text)) / 0.8)
        mb.text(text, tsz, (xfront - 0.1, 0, zent + 0.8 + fr_h / 2), DARK, rot=FACE_PX, depth=0.08,
                font=FONT_BOLD, spacing=1.15)
    if attic > 0:
        mb.bb(-Wx / 2 + 0.3, -Dy / 2 + 0.3, ztop + 0.8, Wx / 2 - 0.3, Dy / 2 - 0.3, ztop + 0.8 + attic, BODY)
        cornice(mb, Wx - 0.6, Dy - 0.6, ztop + 0.8 + attic, 0.4, 0.25)
    if pediment:
        pitch = math.tan(R(15))
        hw = pw / 2 + 0.7
        zp = zco
        ph = hw * pitch
        mb.prism_yz([(-hw + 0.3, zp), (hw - 0.3, zp), (0, zp + ph - 0.25)], Wx / 2 - 0.5, xfront - 0.05, BODY)
        # raking cornices
        t = 0.45
        mb.prism_yz([(-hw - 0.1, zp), (0, zp + ph + 0.1), (hw + 0.1, zp), (hw - 0.6, zp), (0, zp + ph - 0.45),
                     (-hw + 0.6, zp)], Wx / 2 - 0.5, xfront + 0.3, BODY)
        if emblem:
            mb.cyl(ph * 0.33, 0.12, (xfront - 0.05, 0, zp + ph * 0.38), ACCENT, n=24, rot=(0, R(90), 0))
            mb.cyl(ph * 0.24, 0.05, (xfront + 0.07, 0, zp + ph * 0.38), BODY, n=24, rot=(0, R(90), 0))
        # roof behind pediment: low gable over main block
        mb.prism_yz([(-Dy / 2 + 0.2, ztop + 0.8), (Dy / 2 - 0.2, ztop + 0.8), (0, ztop + 0.8 + (Dy / 2) * pitch * 0.9)],
                    -Wx / 2 + 0.2, Wx / 2 - 0.5, BODY)
    zdome = ztop + 0.8 + attic
    if dome:
        dr = min(Wx, Dy) * 0.28
        # drum + peristyle
        mb.cyl(dr, 6.0, (0, 0, zdome), BODY, n=32)
        mb.cyl(dr + 1.8, 0.6, (0, 0, zdome), BODY, n=32)
        nc = 20
        for k in range(nc):
            a = TAU * k / nc
            column(mb, 5.0, 0.32, ((dr + 1.2) * math.cos(a), (dr + 1.2) * math.sin(a), zdome + 0.6), "doric", n=10)
        mb.cyl(dr + 1.8, 1.0, (0, 0, zdome + 6.0), BODY, n=32)
        mb.cyl(dr + 0.6, 0.6, (0, 0, zdome + 7.0), BODY, n=32)
        prof = [(dr + 0.2, zdome + 7.6)] + [(dr * math.cos(a), zdome + 7.6 + dr * 1.1 * math.sin(a))
                                           for a in [R(x) for x in range(0, 81, 8)]] + [(dr * 0.17, zdome + 7.6 + dr * 1.1 * math.sin(R(80)))]
        mb.lathe(prof, BODY, n=32)
        zl = zdome + 7.6 + dr * 1.1 * math.sin(R(80))
        # ribs
        for k in range(16):
            a = TAU * k / 16
            path = [((dr + 0.05) * math.cos(t_) * math.cos(a), (dr + 0.05) * math.cos(t_) * math.sin(a),
                     zdome + 7.6 + (dr * 1.1 + 0.05) * math.sin(t_)) for t_ in [R(x) for x in range(0, 81, 10)]]
            mb.sweep(path, [(-0.15, 0), (0.15, 0), (0.15, 0.18), (-0.15, 0.18)], BODY, up=(0, 0, 1))
        # lantern
        mb.cyl(dr * 0.2, 3.0, (0, 0, zl), BODY, n=16)
        for k in range(8):
            a = TAU * k / 8
            mb.bb(dr * 0.2 * math.cos(a) - 0.12, dr * 0.2 * math.sin(a) - 0.12, zl,
                  dr * 0.2 * math.cos(a) + 0.12, dr * 0.2 * math.sin(a) + 0.12, zl + 3.0, BODY)
        mb.cyl(dr * 0.24, 0.3, (0, 0, zl + 3.0), BODY, n=16)
        mb.lathe([(dr * 0.22, 0), (dr * 0.18, 0.8), (dr * 0.08, 1.4), (0.08, 1.6), (0, 1.6)], BODY, n=16,
                 loc=(0, 0, zl + 3.3))
        mb.cyl(0.08, 3.5, (0, 0, zl + 4.9), BODY, n=6)
        mb.sphere(0.3, (0, 0, zl + 8.4), METAL, seg=12, rings=6)
        top = zl + 8.7
    else:
        top = zco + (min(pw, Dy) / 2) * math.tan(R(15)) + 1
    if wings:
        wh = height * 0.85
        for s in (-1, 1):
            yc = s * (Dy / 2 + wing_w / 2 - 0.3)
            ww_ = wing_w + 0.6
            with mb.at((-1.0, yc, 0)):
                mb.bb(-Wx * 0.4 - 0.2, -ww_ / 2, 0, Wx * 0.4 + 0.2, ww_ / 2, P, BODY)
                wf = lambda w: (floors(w, 2, wh / 2, 0, 1.2, 2.8, ww=1.4, bay=3.6, margin=1.2, mv=1, mh=1))
                block(mb, Wx * 0.8, ww_, wh, P, {"px": wf, "nx": wf, "ny" if s < 0 else "py": wf}, depth=0.28)
                cornice(mb, Wx * 0.8, ww_, P + wh, 0.6, 0.35)
                parapet(mb, Wx * 0.8, ww_, P + wh + 0.6, 0.9, 0.3, out=0.1)
                band(mb, Wx * 0.8, ww_, P, 1.0, 0.07)
                # end pavilion pilasters
                for k in range(int(ww_ // 3.6) + 1):
                    y = -ww_ / 2 + 0.4 + (ww_ - 0.8) * k / int(ww_ // 3.6)
                    mb.bb(Wx * 0.4 - 0.01, y - 0.3, P + 1.0, Wx * 0.4 + 0.2, y + 0.3, P + wh, BODY)
    return dict(size=(Wx + pd + steps * tread, Dy + (2 * wing_w if wings else 0), top))


def warehouse(mb, length=40.0, width=24.0, height=9.0, doors=3, pitch=6, ribs=True, seed=0):
    """Portal-frame warehouse: ribbed cladding, low gable roof (ridge along X), dock doors on -Y."""
    Wx, Dy = length, width
    nd = doors

    def dockside(w):
        ops = []
        for k in range(nd):
            c = w * (k + 0.5) / nd
            ops.append(W(c - 2.0, 1.2, c + 2.0, 6.0, "door", mh=0, frame=False, depth=0.25))
        ops += [W(1.5, height - 1.8, w - 1.5, height - 0.8, "win", mv=int(w // 3), sill=False, depth=0.12)]
        return ops

    def end(w):
        return [W(w / 2 - 2.5, 0, w / 2 + 2.5, 5.0, "door", frame=False, depth=0.25),
                W(1.2, 0, 2.2, 2.2, "door"), W(1.5, height - 1.8, w - 1.5, height - 0.8, "win",
                                                   mv=int(w // 3), sill=False, depth=0.12)]

    def plain(w):
        return [W(1.5, height - 1.8, w - 1.5, height - 0.8, "win", mv=int(w // 3), sill=False, depth=0.12)]

    block(mb, Wx, Dy, height, 0, {"ny": dockside, "px": end, "py": plain, "nx": plain}, cap=False)
    zr = gable_roof(mb, Wx, Dy, height, pitch, over=0.3, over_g=0.3, t=0.25, axis="x")
    # roller door slats
    for k in range(nd):
        c = -Wx / 2 + Wx * (k + 0.5) / nd
        for j in range(9):
            z = 1.4 + j * 0.52
            mb.bb(c - 1.98, -Dy / 2 + 0.2, z, c + 1.98, -Dy / 2 + 0.24, z + 0.05, BODY)
        # dock leveller, bumpers, shelter
        mb.bb(c - 1.6, -Dy / 2 - 0.5, 0.95, c - 1.3, -Dy / 2 - 0.0, 1.25, DARK)
        mb.bb(c + 1.3, -Dy / 2 - 0.5, 0.95, c + 1.6, -Dy / 2 - 0.0, 1.25, DARK)
    # loading dock platform and canopy
    mb.bb(-Wx / 2 + 1, -Dy / 2 - 3.0, 0, Wx / 2 - 1, -Dy / 2 + 0.01, 1.2, BODY)
    mb.bb(-Wx / 2 + 1, -Dy / 2 - 4.0, 6.6, Wx / 2 - 1, -Dy / 2 + 0.01, 6.9, BODY)
    for k in range(nd + 1):
        x = -Wx / 2 + 1.3 + (Wx - 2.6) * k / nd
        mb.rod((x, -Dy / 2 - 3.7, 6.62), (x, -Dy / 2 + 0.02, 8.4), 0.06, DARK, n=6)
    # roof skylight strips
    tp = math.tan(R(pitch))
    for s in (-1, 1):
        for k in range(4):
            x = -Wx / 2 + Wx * (k + 0.5) / 4
            y = s * Dy / 4
            z = height + (Dy / 2 - abs(y)) * tp + 0.25 / math.cos(R(pitch))
            with mb.at((x, y, z), rot=(s * -R(pitch) * 1, 0, 0)):
                mb.bb(-Wx / 10, -1.2, 0.0, Wx / 10, 1.2, 0.08, GLASS)
    return dict(size=(Wx, Dy + 4, zr))


def factory(mb, length=48.0, width=30.0, height=8.0, teeth=6, stacks=2, stack_h=32.0, office=True, seed=0):
    """Industrial hall with north-light sawtooth roof (teeth along X), chimney stacks, office block."""
    Wx, Dy = length, width
    bayw = 6.0

    def side(w):
        n = max(1, int(w // bayw))
        return [W(w * (k + 0.5) / n - 1.6, 1.4, w * (k + 0.5) / n + 1.6, height - 1.2, "win", mv=3, mh=3, depth=0.3)
                for k in range(n)]

    def end(w):
        return [W(w / 2 - 3, 0, w / 2 + 3, 5.5, "door", frame=False, depth=0.3)] + \
               [W(1.5, 1.4, 5.0, height - 1.2, "win", mv=2, mh=3), W(w - 5.0, 1.4, w - 1.5, height - 1.2, "win", mv=2, mh=3)]

    block(mb, Wx, Dy, height, 0, {"ny": side, "py": side, "px": end, "nx": end}, depth=0.35)
    # brick piers
    for s in (-1, 1):
        n = max(1, int(Wx // bayw))
        for k in range(n + 1):
            x = -Wx / 2 + Wx * k / n
            y0, y1 = (s * Dy / 2, s * (Dy / 2 + 0.35))
            mb.bb(x - 0.35, min(y0, y1), 0, x + 0.35, max(y0, y1), height + 0.2, BODY)
    band(mb, Wx, Dy, height - 0.4, 0.6, 0.12)
    # sawtooth: vertical glazed face toward +X
    tw = Wx / teeth
    th = 3.6
    for k in range(teeth):
        x0 = -Wx / 2 + k * tw
        mb.prism_xz([(x0, height), (x0 + tw, height), (x0 + tw, height + th)], -Dy / 2, Dy / 2, BODY)
        xg = x0 + tw + 0.02
        mb.bb(x0 + tw - 0.01, -Dy / 2 + 0.6, height + 0.4, x0 + tw + 0.03, Dy / 2 - 0.6, height + th - 0.35, GLASS)
        n = int(Dy // 2.5)
        for j in range(n + 1):
            y = -Dy / 2 + 0.6 + (Dy - 1.2) * j / n
            mb.bb(x0 + tw - 0.0, y - 0.06, height + 0.4, x0 + tw + 0.08, y + 0.06, height + th - 0.35, DARK)
        mb.bb(x0 + tw - 0.12, -Dy / 2, height + th - 0.25, x0 + tw + 0.12, Dy / 2, height + th + 0.05, BODY)
    # last tooth vertical face is open to the end wall top: close it
    # chimney stacks
    for i in range(stacks):
        x = -Wx / 2 - 5.0
        y = -Dy / 4 + i * (Dy / 2) / max(1, stacks - 1) if stacks > 1 else 0
        mb.bb(x - 2.4, y - 2.4, 0, x + 2.4, y + 2.4, 3.0, BODY)
        mb.cyl(1.9, stack_h - 3, (x, y, 3.0), BODY, n=24, r2=1.25)
        for z in (stack_h - 2.2, stack_h - 5.5):
            t = (z - 3) / (stack_h - 3)
            r = 1.9 + (1.25 - 1.9) * t
            mb.cyl(r + 0.12, 0.6, (x, y, z), DARK, n=24)
        mb.cyl(1.4, 0.5, (x, y, stack_h), DARK, n=24)
    if office:
        with mb.at((Wx / 2 + 5.0, -Dy / 2 + 7.0, 0)):
            of = lambda w: floors(w, 2, 3.4, 0, 0.9, 1.6, ww=2.4, bay=3.2, margin=0.8, mv=1)
            block(mb, 10.0, 14.0, 6.8, 0,
                  {"px": lambda w: floors(w, 2, 3.4, 0, 0.9, 1.6, ww=2.4, bay=3.2, margin=0.8, mv=1, f0=1) +
                   [W(w / 2 - 1.2, 0, w / 2 + 1.2, 2.6, "glassdoor", mv=1)] + row(w, 0.9, 1.6, n=4, ww=2.0, skip=(1, 2)),
                   "ny": of, "py": of})
            parapet(mb, 10.0, 14.0, 6.8, 0.7, 0.25)
            mb.bb(5.0, -4.5, 5.2 + 1.6, 5.25, 4.5, 6.6, ACCENT)
    return dict(size=(Wx + 20, Dy, stack_h))


def port_shed(mb, length=90.0, width=32.0, height=10.0, doors=8, seed=0):
    """Long transit shed with barrel-vault roof (along X) and a row of cargo doors on -Y."""
    Wx, Dy = length, width

    def dock(w):
        return [W(w * (k + 0.5) / doors - 2.5, 0, w * (k + 0.5) / doors + 2.5, 6.0, "door", frame=False, depth=0.3)
                for k in range(doors)] + [W(2.0, height - 2.2, w - 2.0, height - 0.9, "win", mv=int(w // 3), sill=False,
                                            depth=0.15)]

    def end(w):
        return [W(w / 2 - 4, 0, w / 2 + 4, 7.0, "door", frame=False, depth=0.3),
                W(2.0, 1.0, 3.2, 3.0, "win", mv=0), W(w - 3.2, 1.0, w - 2.0, 3.0, "win", mv=0)]

    block(mb, Wx, Dy, height, 0, {"ny": dock, "py": dock, "px": end, "nx": end}, cap=False)
    # barrel vault
    rise = Dy * 0.16
    n = 16
    prof_out, prof_in = [], []
    for k in range(n + 1):
        t = k / n
        y = -Dy / 2 - 0.4 + (Dy + 0.8) * t
        z = height + rise * (1 - (2 * t - 1) ** 2)
        prof_out.append((y, z + 0.35))
        prof_in.append((y, z))
    mb.prism_yz(prof_out + list(reversed(prof_in)), -Wx / 2 - 0.4, Wx / 2 + 0.4, BODY)
    # gable infill (arched end walls)
    infill = [(-Dy / 2, height)] + [(y, z - 0.02) for y, z in prof_in[1:-1] if abs(y) < Dy / 2] + [(Dy / 2, height)]
    mb.prism_yz(infill, -Wx / 2, Wx / 2, BODY)
    # roof ribs
    for k in range(1, 12):
        x = -Wx / 2 + Wx * k / 12
        mb.prism_yz([(y, z + 0.33) for y, z in prof_in] + [(y, z + 0.55) for y, z in reversed(prof_in)], x - 0.15,
                    x + 0.15, BODY)
    # apron edge / quay kerb along -Y
    mb.bb(-Wx / 2 - 4, -Dy / 2 - 8, 0, Wx / 2 + 4, -Dy / 2 - 7.6, 0.25, BODY)
    for k in range(doors):
        x = -Wx / 2 + Wx * (k + 0.5) / doors
        for j in range(10):
            z = 0.3 + j * 0.55
            mb.bb(x - 2.45, -Dy / 2 + 0.25, z, x + 2.45, -Dy / 2 + 0.3, z + 0.05, BODY)
        mb.cyl(0.25, 0.6, (x + 5.0, -Dy / 2 - 7.2, 0), DARK, n=10, r2=0.18)  # bollards
    return dict(size=(Wx + 8, Dy + 8, height + rise + 0.5))


def gas_station(mb, canopy=(14.0, 20.0), height=5.2, islands=2, pumps_per=2, kiosk=True, price="3.49", seed=0):
    cw, cd = canopy  # x, y
    # forecourt slab
    mb.bb(-cw / 2 - 14, -cd / 2 - 4, 0, cw / 2 + 4, cd / 2 + 4, 0.06, BODY)
    # canopy
    th = 1.1
    mb.bb(-cw / 2, -cd / 2, height, cw / 2, cd / 2, height + th, BODY)
    mb.bb(-cw / 2 - 0.05, -cd / 2 - 0.05, height + 0.25, cw / 2 + 0.05, cd / 2 + 0.05, height + th - 0.2, ACCENT)
    for i in range(islands):
        y = -cd / 2 + cd * (i + 0.5) / islands
        mb.bb(-cw * 0.35, y - 0.6, 0.06, cw * 0.35, y + 0.6, 0.25, BODY)
        mb.bb(-0.35, y - 0.35, 0.25, 0.35, y + 0.35, height, BODY)  # column
        for k in range(pumps_per):
            x = -cw * 0.22 + cw * 0.44 * k / max(1, pumps_per - 1)
            with mb.at((x, y, 0.25)):
                mb.bb(-0.45, -0.3, 0, 0.45, 0.3, 1.85, BODY)
                mb.bb(-0.47, -0.32, 1.55, 0.47, 0.32, 1.95, ACCENT)
                for s in (-1, 1):
                    mb.bb(-0.3, s * 0.3 - 0.01, 1.05, 0.3, s * 0.3 + 0.01, 1.45, GLASS)
                    mb.bb(-0.38, s * 0.31 - 0.06 * (s < 0), 0.6, -0.26, s * 0.31 + 0.06 * (s > 0), 0.9, DARK)
                    mb.rod((-0.32, s * 0.36, 0.75), (-0.45, s * 0.5, 0.2), 0.025, DARK, n=6)
        # lights under canopy
        for k in range(3):
            x = -cw / 2 + cw * (k + 0.5) / 3
            mb.bb(x - 0.6, y - 0.6, height - 0.02, x + 0.6, y + 0.6, height + 0.01, LIGHT)
    if kiosk:
        with mb.at((-cw / 2 - 8.0, cd * 0.12, 0.06)):
            kf = lambda w: [W(1.0, 0.0, w - 1.0, 3.0, "shop", mv=int(w // 2.2), depth=0.15),
                            ]
            block(mb, 8.0, 12.0, 4.0, 0, {"px": lambda w: [W(w / 2 - 1.0, 0, w / 2 + 1.0, 2.5, "glassdoor", mv=1),
                                                           W(1.0, 0.6, w / 2 - 1.5, 3.0, "shop", mv=2),
                                                           W(w / 2 + 1.5, 0.6, w - 1.0, 3.0, "shop", mv=2)],
                                          "ny": lambda w: [W(1.0, 0.6, w - 1.0, 3.0, "shop", mv=2)]})
            mb.bb(-4.3, -6.3, 4.0, 4.6, 6.3, 4.9, BODY)
            mb.bb(4.0, -6.35, 4.1, 4.65, 6.35, 4.7, ACCENT)
    # price pylon
    with mb.at((cw / 2 + 2.5, -cd / 2 - 2.0, 0)):
        mb.bb(-0.35, -0.9, 0, 0.35, 0.9, 7.0, BODY)
        mb.bb(-0.4, -0.95, 5.0, 0.4, 0.95, 7.0, ACCENT)
        for j in range(3):
            z = 1.4 + j * 1.15
            mb.bb(0.34, -0.75, z, 0.38, 0.75, z + 0.85, DARK)
            mb.text(price, 0.5, (0.385, 0, z + 0.42), LIGHT, rot=FACE_PX, depth=0.01, font=FONT_BOLD)
    return dict(size=(cw + 18, cd + 8, 7))



def church(mb, length=26.0, width=12.0, wall_h=9.0, tower_h=24.0, spire_h=16.0, pitch=52, seed=0):
    Wx, Dy = length, width
    win = lambda w: [W(w * (k + 0.5) / 5 - 0.65, 2.0, w * (k + 0.5) / 5 + 0.65, 7.2, "win", mv=1, arch="pointed")
                     for k in range(5)]
    block(mb, Wx, Dy, wall_h, 0, {"ny": win, "py": win,
                                  "nx": lambda w: [W(w / 2 - 1.6, 2.0, w / 2 + 1.6, 8.0, "win", mv=1, mh=1, arch="pointed")]},
          cap=False, depth=0.35)
    gable_roof(mb, Wx, Dy, wall_h, pitch, over=0.4, over_g=0.3, axis="x")
    # buttresses
    for s in (-1, 1):
        for k in range(6):
            x = -Wx / 2 + Wx * k / 5
            y0 = s * Dy / 2
            mb.add([(x - 0.4, y0, 0), (x + 0.4, y0, 0), (x + 0.4, y0 + s * 1.0, 0), (x - 0.4, y0 + s * 1.0, 0),
                    (x - 0.4, y0, wall_h - 1.5), (x + 0.4, y0, wall_h - 1.5), (x + 0.4, y0 + s * 0.3, wall_h - 2.2),
                    (x - 0.4, y0 + s * 0.3, wall_h - 2.2)],
                   [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)] if s < 0 else
                   [(0, 1, 2, 3), (7, 6, 5, 4), (4, 5, 1, 0), (5, 6, 2, 1), (6, 7, 3, 2), (7, 4, 0, 3)], BODY)
    # tower at +X
    ts = 6.0
    tx = Wx / 2 + ts / 2 - 0.5
    with mb.at((tx, 0, 0)):
        tw = lambda w: [W(w / 2 - 0.9, tower_h - 6.0, w / 2 + 0.9, tower_h - 2.0, "vent", mv=1, arch="pointed"),
                        W(w / 2 - 0.5, tower_h - 13.0, w / 2 + 0.5, tower_h - 10.5, "win", mv=0, arch="round")]
        block(mb, ts, ts, tower_h, 0, {"px": lambda w: tw(w) + [W(w / 2 - 1.1, 0, w / 2 + 1.1, 4.4, "door", mv=1, arch="pointed"),
                                                                W(w / 2 - 0.5, 6.5, w / 2 + 0.5, 9.0, "win", arch="pointed")],
                                       "ny": tw, "py": tw, "nx": tw}, depth=0.4)
        band(mb, ts, ts, tower_h - 7.0, 0.3, 0.1)
        cornice(mb, ts, ts, tower_h, 0.6, 0.3)
        # corner pinnacles
        for (sx, sy) in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
            mb.cyl(0.35, 2.5, (sx * (ts / 2 - 0.1), sy * (ts / 2 - 0.1), tower_h + 0.6), BODY, n=8, r2=0.02)
        # octagonal spire
        mb.cyl(ts * 0.48, spire_h, (0, 0, tower_h + 0.6), BODY, n=8, r2=0.05)
        z = tower_h + 0.6 + spire_h
        mb.bb(-0.06, -0.06, z - 0.2, 0.06, 0.06, z + 1.8, DARK)
        mb.bb(-0.06, -0.55, z + 0.9, 0.06, 0.55, z + 1.05, DARK)
    # rose / apse at -X
    mb.cyl(Dy * 0.36, wall_h - 1.0, (-Wx / 2, 0, 0), BODY, n=20)
    mb.cyl(Dy * 0.36 + 0.3, Dy * 0.32, (-Wx / 2, 0, wall_h - 1.0), BODY, n=20, r2=0.3)
    return dict(size=(Wx + ts + Dy * 0.4, Dy + 2, tower_h + spire_h + 3))


def clock_face(mb, r, loc, rz=0.0, hour=10, minute=8):
    """Clock dial facing +X (before rz)."""
    with mb.at(loc, rz=rz):
        mb.cyl(r + 0.15, 0.14, (0, 0, 0), BODY, n=24, rot=(0, R(90), 0))
        mb.cyl(r, 0.06, (0.14, 0, 0), LIGHT, n=24, rot=(0, R(90), 0))
        for k in range(12):
            a = TAU * k / 12
            mb.box((0.03, 0.08, r * 0.18), (0.21, r * 0.82 * math.sin(a), r * 0.82 * math.cos(a)), DARK,
                   rot=(-a, 0, 0))
        for ang, L, t in ((TAU * (hour % 12 + minute / 60) / 12, r * 0.5, 0.12), (TAU * minute / 60, r * 0.78, 0.08)):
            mb.box((0.03, t, L), (0.23, L / 2 * math.sin(ang), L / 2 * math.cos(ang)), DARK, rot=(-ang, 0, 0))


def town_hall(mb, width=32.0, depth=18.0, storeys=3, fh=4.0, tower_h=34.0, seed=0):
    Wx, Dy = depth, width
    H = storeys * fh

    def front(w):
        ops = [W(w / 2 - 1.4, 0, w / 2 + 1.4, 4.2, "door", mv=1, arch="round")]
        n = 8
        for k in range(n):
            u = w * (k + 0.5) / n
            if abs(u - w / 2) < 3.5:
                continue
            ops.append(W(u - 0.8, 1.0, u + 0.8, 3.4, "win", mv=1, arch="round"))
        ops += floors(w, storeys, fh, 0, 0.9, 2.2, ww=1.4, n=n, mv=1, mh=1, f0=1)
        return ops

    side = lambda w: [W(w * (k + .5) / 4 - 0.8, 1.0, w * (k + .5) / 4 + 0.8, 3.4, "win", mv=1, arch="round") for k in range(4)] + \
        floors(w, storeys, fh, 0, 0.9, 2.2, ww=1.4, n=4, mv=1, mh=1, f0=1)
    mb.bb(-Wx / 2 - 0.3, -Dy / 2 - 0.3, 0, Wx / 2 + 0.3, Dy / 2 + 0.3, 0.6, BODY)
    block(mb, Wx, Dy, H, 0.6, {"px": front, "ny": side, "py": side, "nx": side}, cap=False, depth=0.3)
    band(mb, Wx, Dy, 0.6 + fh - 0.3, 0.35, 0.1)
    cornice(mb, Wx, Dy, H + 0.6, 0.6, 0.4)
    zr = hip_roof(mb, Wx, Dy, H + 1.2, 28, over=0.2)
    # entrance steps + balcony
    stairs(mb, Wx / 2, 4, 0.15, 0.35, 5.0, back=0.1)
    mb.bb(Wx / 2, -3.0, 0.6 + fh, Wx / 2 + 1.4, 3.0, 0.6 + fh + 0.25, BODY)
    mb.bb(Wx / 2 + 1.25, -3.0, 0.6 + fh + 0.25, Wx / 2 + 1.4, 3.0, 0.6 + fh + 1.2, BODY)
    # central clock tower (in front half)
    ts = 6.0
    with mb.at((Wx / 2 - ts / 2 - 0.3, 0, 0)):
        tw = lambda w: [W(w / 2 - 0.9, tower_h - 7.0, w / 2 + 0.9, tower_h - 2.5, "vent", mv=1, arch="round")]
        block(mb, ts, ts, tower_h, 0.0, {"px": tw, "ny": tw, "py": tw, "nx": tw}, depth=0.35)
        cornice(mb, ts, ts, tower_h - 12.5, 0.4, 0.2)
        cornice(mb, ts, ts, tower_h, 0.6, 0.35)
        for k, (sx, sy, rz) in enumerate(((1, 0, 0), (0, -1, -math.pi / 2), (-1, 0, math.pi), (0, 1, math.pi / 2))):
            clock_face(mb, 1.8, (sx * (ts / 2), sy * (ts / 2), tower_h - 10.0), rz)
        # cupola
        zc = tower_h + 0.6
        mb.bb(-ts * 0.32, -ts * 0.32, zc, ts * 0.32, ts * 0.32, zc + 3.2, BODY)
        for (sx, sy) in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
            pass
        mb.cyl(ts * 0.5, 0.4, (0, 0, zc + 3.2), BODY, n=8)
        mb.lathe([(ts * 0.42, 0), (ts * 0.4, 0.8), (ts * 0.3, 2.0), (ts * 0.12, 3.0), (0.05, 3.4), (0, 3.4)], BODY,
                 n=8, loc=(0, 0, zc + 3.6))
        flagpole(mb, 4.0, (0, 0, zc + 7.0), flag=True, fw=1.6, fh=1.0)
    return dict(size=(Wx + 3, Dy, tower_h + 12))


def school(mb, wing_a=40.0, wing_b=26.0, depth=12.0, storeys=2, fh=3.8, sign="SCHOOL", seed=0):
    """L-shaped school: ribbon windows, entrance canopy with sign, flagpole."""
    H = storeys * fh
    rib = lambda w: [W(1.0, f * fh + 1.0, w - 1.0, f * fh + 3.0, "win", mv=int((w - 2) // 1.8), sill=False, depth=0.25)
                     for f in range(storeys)]

    def main_front(w):
        return [W(1.0, f * fh + 1.0, w / 2 - 3.0, f * fh + 3.0, "win", mv=int((w / 2 - 4) // 1.8), sill=False)
                for f in range(storeys)] + \
            [W(w / 2 + 3.0, f * fh + 1.0, w - 1.0, f * fh + 3.0, "win", mv=int((w / 2 - 4) // 1.8), sill=False)
             for f in range(storeys)] + [W(w / 2 - 2.2, 0, w / 2 + 2.2, 3.0, "glassdoor", mv=3),
                                         W(w / 2 - 2.2, fh + 0.4, w / 2 + 2.2, H - 0.4, "win", mv=3, mh=1, sill=False)]

    # wing A along Y (front faces +X)
    with mb.at((0, 0, 0)):
        block(mb, depth, wing_a, H, 0, {"px": main_front, "nx": rib, "py": rib})
        parapet(mb, depth, wing_a, H, 0.7, 0.3)
        for f in range(1, storeys):
            mb.bb(depth / 2 - 0.01, -wing_a / 2, f * fh - 0.15, depth / 2 + 0.25, wing_a / 2, f * fh + 0.25, BODY)
    # wing B along -X at the -Y end
    with mb.at((-depth / 2 - wing_b / 2 + 0.01, -wing_a / 2 + depth / 2, 0)):
        block(mb, wing_b, depth, H, 0, {"ny": rib, "py": rib, "nx": rib})
        parapet(mb, wing_b, depth, H, 0.7, 0.3)
    # canopy + sign
    mb.bb(depth / 2, -4.0, 3.4, depth / 2 + 3.5, 4.0, 3.8, BODY)
    for s in (-1, 1):
        mb.bb(depth / 2 + 3.1, s * 3.7 - 0.12, 0, depth / 2 + 3.35, s * 3.7 + 0.12, 3.4, BODY)
    mb.bb(depth / 2 + 3.5, -4.0, 3.3, depth / 2 + 3.6, 4.0, 3.9, ACCENT)
    mb.text(sign, 0.42, (depth / 2 + 3.6, 0, 3.6), DARK, rot=FACE_PX, depth=0.03, font=FONT_BLACK, spacing=1.2)
    flagpole(mb, 9.0, (depth / 2 + 7.0, 6.0, 0), seed=seed)
    mb.cyl(0.6, 0.3, (depth / 2 + 7.0, 6.0, 0), BODY, n=12)
    return dict(size=(depth + wing_b + 8, wing_a, H + 1))


def hospital(mb, width=48.0, depth=18.0, storeys=8, fh=3.6, podium=(60.0, 36.0, 2), seed=0):
    rnd = random.Random(seed)
    pw, pd, pf = podium
    PH = pf * 4.2
    # podium
    pod = lambda w: floors(w, pf, 4.2, 0, 1.0, 2.4, ww=3.0, bay=4.0, margin=1.5, mv=2, sill=False)
    block(mb, pd, pw, PH, 0, {"px": lambda w: [W(w / 2 - 3.5, 0, w / 2 + 3.5, 3.2, "glassdoor", mv=4)] +
                                  [o for o in pod(w) if abs((o["r"][0] + o["r"][2]) / 2 - w / 2) > 5],
                              "ny": pod, "py": pod, "nx": pod})
    parapet(mb, pd, pw, PH, 0.6, 0.3)
    # tower
    TH = storeys * fh
    tw = lambda w: floors(w, storeys, fh, 0, 0.8, 1.8, ww=2.2, bay=3.0, margin=1.2, mv=1, sill=False)
    with mb.at((-pd / 2 + depth / 2 + 3, 0, PH)):
        block(mb, depth, width, TH, 0, {"px": tw, "nx": tw, "ny": tw, "py": tw})
        for f in range(1, storeys):
            band(mb, depth, width, f * fh - 0.15, 0.3, 0.05)
        parapet(mb, depth, width, TH, 0.8, 0.3)
        # red cross panel (accent) on +X near top
        with mb.at((depth / 2 + 0.06, 0, TH - 4.0), rz=R(90)):
            mb.bb(-3.2, -0.2, -3.2, 3.2, 0.0, 3.2, BODY)
            mb.bb(-0.8, -0.32, -2.5, 0.8, -0.18, 2.5, ACCENT)
            mb.bb(-2.5, -0.33, -0.8, 2.5, -0.19, 0.8, ACCENT)
        # helipad
        hz = TH + 0.2
        mb.cyl(7.5, 0.4, (0, 0, TH), BODY, n=32)
        mb.ring(5.6, 6.2, hz + 0.2, hz + 0.23, ACCENT, n=40)
        mb.text("H", 6.0, (0, 0, hz + 0.2), DARK, rot=(0, 0, R(90)), depth=0.04, font=FONT_BLACK)
        for k in range(8):
            a = TAU * k / 8
            mb.rod((7.6 * math.cos(a), 7.6 * math.sin(a), TH - 2.0), (7.4 * math.cos(a), 7.4 * math.sin(a), TH), 0.12,
                   BODY, n=6)
    # ambulance canopy
    with mb.at((pd / 2, pw / 2 - 8, 0)):
        mb.bb(0, -5, 3.8, 8, 5, 4.3, BODY)
        mb.bb(0, -5.05, 4.3, 8.05, 5.05, 4.75, ACCENT)
        for (x, y) in ((7.6, -4.6), (7.6, 4.6)):
            mb.cyl(0.2, 3.8, (x, y, 0), BODY, n=10)
    return dict(size=(pd + 8, pw, PH + TH + 1))


def castle(mb, size=44.0, wall_h=10.0, wall_t=3.0, tower_r=4.2, tower_h=16.0, keep=(14.0, 24.0), roofs=False,
           seed=0):
    """Medieval castle: square curtain wall, round corner towers, gatehouse on +X, central keep."""
    s = size / 2

    def merlons(x0, y0, x1, y1, z, t, mh=1.1, mw=0.9, gap=0.75):
        L = math.hypot(x1 - x0, y1 - y0)
        n = int(L // (mw + gap))
        dx, dy = (x1 - x0) / L, (y1 - y0) / L
        for k in range(n):
            a = (k + 0.5) * L / n
            cx, cy = x0 + dx * a, y0 + dy * a
            with mb.at((cx, cy, z), rz=math.atan2(dy, dx)):
                mb.bb(-mw / 2, -t / 2, 0, mw / 2, t / 2, mh, BODY)

    # walls (slight batter: base plinth)
    for (x0, y0, x1, y1) in ((-s, -s, s, -s), (s, s, -s, s), (-s, s, -s, -s)):
        dx, dy = x1 - x0, y1 - y0
        L = math.hypot(dx, dy)
        with mb.at(((x0 + x1) / 2, (y0 + y1) / 2, 0), rz=math.atan2(dy, dx)):
            mb.bb(-L / 2, -wall_t / 2, 0, L / 2, wall_t / 2, wall_h, BODY)
            mb.bb(-L / 2, -wall_t / 2 - 0.5, 0, L / 2, wall_t / 2 + 0.5, 1.2, BODY)
            mb.bb(-L / 2, -wall_t / 2 - 0.15, wall_h - 0.4, L / 2, wall_t / 2 + 0.15, wall_h, BODY)
            for k in range(int(L // 6)):
                x = -L / 2 + (k + 0.5) * L / int(L // 6)
                mb.bb(x - 0.12, -wall_t / 2 - 0.02, 4.0, x + 0.12, -wall_t / 2 + 0.3, 6.0, DARK)  # arrow slits
            merlons(-L / 2, -wall_t / 2 + 0.25, L / 2, -wall_t / 2 + 0.25, wall_h, 0.5)
            merlons(-L / 2, wall_t / 2 - 0.25, L / 2, wall_t / 2 - 0.25, wall_h, 0.5)
    # front wall split by gatehouse
    gw = 10.0
    for sgn in (-1, 1):
        y0, y1 = sgn * s, sgn * gw / 2
        with mb.at((s, (y0 + y1) / 2, 0), rz=R(90)):
            L = abs(y1 - y0)
            mb.bb(-L / 2, -wall_t / 2, 0, L / 2, wall_t / 2, wall_h, BODY)
            mb.bb(-L / 2, -wall_t / 2 - 0.5, 0, L / 2, wall_t / 2 + 0.5, 1.2, BODY)
            merlons(-L / 2, -wall_t / 2 + 0.25, L / 2, -wall_t / 2 + 0.25, wall_h, 0.5)
            merlons(-L / 2, wall_t / 2 - 0.25, L / 2, wall_t / 2 - 0.25, wall_h, 0.5)
    # corner towers
    for (x, y) in ((-s, -s), (s, -s), (s, s), (-s, s)):
        mb.cyl(tower_r + 0.6, 1.5, (x, y, 0), BODY, n=24, r2=tower_r)
        mb.cyl(tower_r, tower_h, (x, y, 0), BODY, n=24)
        mb.cyl(tower_r + 0.35, 1.0, (x, y, tower_h), BODY, n=24)
        if roofs:
            mb.cyl(tower_r + 0.5, tower_r * 2.2, (x, y, tower_h + 1.0), BODY, n=24, r2=0.05)
        else:
            nm = 10
            for k in range(nm):
                a = TAU * (k + 0.5) / nm
                with mb.at((x + (tower_r + 0.1) * math.cos(a), y + (tower_r + 0.1) * math.sin(a), tower_h + 1.0), rz=a):
                    mb.bb(-0.25, -0.75, 0, 0.25, 0.75, 1.2, BODY)
        for k in range(3):
            a = TAU * k / 3 + 0.4
            mb.bb(x + tower_r * math.cos(a) - 0.12, y + tower_r * math.sin(a) - 0.12, 7.0,
                  x + (tower_r + 0.03) * math.cos(a) + 0.12, y + (tower_r + 0.03) * math.sin(a) + 0.12, 9.0, DARK)
    # gatehouse
    with mb.at((s, 0, 0)):
        for sgn in (-1, 1):
            mb.cyl(3.2, tower_h + 2, (1.0, sgn * 4.2, 0), BODY, n=20)
            mb.cyl(3.5, 1.0, (1.0, sgn * 4.2, tower_h + 2), BODY, n=20)
            for k in range(8):
                a = TAU * (k + 0.5) / 8
                with mb.at((1.0 + 3.3 * math.cos(a), sgn * 4.2 + 3.3 * math.sin(a), tower_h + 3), rz=a):
                    mb.bb(-0.25, -0.7, 0, 0.25, 0.7, 1.1, BODY)
        mb.bb(-1.5, -2.0, 0, 3.0, 2.0, wall_h + 3, BODY)
        with mb.at((3.0, -2.0, 0), rz=R(90)):
            facade(mb, 4.0, wall_h + 3, [W(0.4, 0, 3.6, 6.0, "door", arch="round", frame=False, depth=1.0)], depth=1.0)
        merlons(3.0, -2, 3.0, 2, wall_h + 3, 0.5)
        # portcullis bars
        for k in range(5):
            y = -1.4 + k * 0.7
            mb.bb(3.25, y - 0.05, 0.0, 3.35, y + 0.05, 4.4, DARK)
    # keep
    kw, kh = keep
    with mb.at((-2.0, 0, 0)):
        kf = lambda w: [W(w / 2 - 0.6, kh - 8, w / 2 + 0.6, kh - 5.5, "win", arch="round", mv=0),
                        W(w / 2 - 0.4, kh - 15, w / 2 + 0.4, kh - 13, "win", arch="round", mv=0)]
        block(mb, kw, kw, kh, 0, {"px": lambda w: kf(w) + [W(w / 2 - 1.0, 3.0, w / 2 + 1.0, 6.0, "door", arch="round")],
                                  "ny": kf, "py": kf, "nx": kf}, depth=0.5)
        band(mb, kw, kw, 0, 1.5, 0.3)
        mb.bb(-kw / 2 - 0.3, -kw / 2 - 0.3, kh - 0.5, kw / 2 + 0.3, kw / 2 + 0.3, kh, BODY)
        for (x0, y0, x1, y1) in ((-1, -1, 1, -1), (1, -1, 1, 1), (1, 1, -1, 1), (-1, 1, -1, -1)):
            merlons(x0 * (kw / 2), y0 * (kw / 2), x1 * (kw / 2), y1 * (kw / 2), kh, 0.6)
        for (sx, sy) in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
            mb.cyl(1.6, kh + 4, (sx * kw / 2, sy * kw / 2, 0), BODY, n=16)
            mb.cyl(1.9, 0.6, (sx * kw / 2, sy * kw / 2, kh + 4), BODY, n=16)
            mb.cyl(1.9, 2.8, (sx * kw / 2, sy * kw / 2, kh + 4.6), BODY, n=16, r2=0.05)
        # external stair to keep door
        stairs(mb, kw / 2, 15, 0.2, 0.3, 2.0, back=0.0)
        flagpole(mb, 6.0, (0, 0, kh), fw=2.4, fh=1.5, seed=seed)
    return dict(size=(size + 2 * tower_r + 4, size + 2 * tower_r, kh + 8))


def star_fort(mb, n=5, radius=60.0, height=8.0, inner=0.62, moat=True, seed=0):
    """Bastioned trace-italienne fort: n-point star scarp with sloped walls, parapet, barracks."""
    pts_lo, pts_hi = [], []
    for k in range(2 * n):
        a = TAU * k / (2 * n) + math.pi / (2 * n)
        r = radius if k % 2 == 0 else radius * inner
        pts_lo.append((r * math.cos(a), r * math.sin(a), 0))
        rr = r - height * 0.45
        pts_hi.append((rr * math.cos(a), rr * math.sin(a), height))
    mb.loft([pts_lo, pts_hi], BODY, cap0=False, cap1=False)
    # top terrace
    mb.add(pts_hi, [tuple(range(len(pts_hi)))], BODY)
    # parapet ring along the outer edge (thin walls)
    for k in range(2 * n):
        p, q = Vector(pts_hi[k]), Vector(pts_hi[(k + 1) % (2 * n)])
        d = (q - p)
        L = d.length
        mid = (p + q) / 2
        nrm = Vector((d.y, -d.x, 0)).normalized()
        if nrm.dot(mid) < 0:
            nrm = -nrm
        mid = mid - nrm * 0.9
        with mb.at((mid.x, mid.y, height), rz=math.atan2(d.y, d.x)):
            mb.bb(-L / 2 + 0.6, -0.6, 0, L / 2 - 0.6, 0.6, 1.3, BODY)
    # inner parade ground (sunk) + barracks
    ri = radius * inner - height * 0.45 - 6
    for k in range(n):
        a = TAU * k / n + math.pi / n + math.pi / (2 * n)
        with mb.at((ri * 0.62 * math.cos(a), ri * 0.62 * math.sin(a), height), rz=a + math.pi / 2):
            block(mb, 16, 6, 4.0, 0, {"ny": lambda w: row(w, 0.9, 1.5, n=5, ww=1.0, mv=0),
                                      "py": lambda w: row(w, 0.9, 1.5, n=5, ww=1.0, mv=0)}, cap=False, depth=0.15)
            gable_roof(mb, 16, 6, 4.0, 35, over=0.3, over_g=0.3, axis="x")
    # gate on +X
    a = math.pi / (2 * n)
    mb.bb(radius * inner - height * 0.45 - 1, -3, height, radius * inner - height * 0.45 + 3, 3, height + 4.5, BODY)
    flagpole(mb, 14.0, (0, 0, height), fw=4.0, fh=2.4, seed=seed)
    if moat:
        pts = []
        for k in range(2 * n):
            a = TAU * k / (2 * n) + math.pi / (2 * n)
            r = (radius if k % 2 == 0 else radius * inner) + 9
            pts.append((r * math.cos(a), r * math.sin(a)))
        mb.prism(pts, 0.0, 0.05, GLASS)
        # glacis ring outside moat
    return dict(size=(2 * radius + 18, 2 * radius + 18, height + 14))


def barn(mb, length=20.0, width=12.0, wall_h=4.5, silo=True, silo_h=15.0, door_m=ACCENT, seed=0):
    """Gambrel-roof barn (ridge along X, big doors on +X gable) with an optional silo."""
    Wx, Dy = length, width

    def endw(w):
        return [W(w / 2 - 2.2, 0, w / 2 + 2.2, 4.2, "door", m=door_m, frame=False, depth=0.15)]

    side = lambda w: row(w, 1.6, 1.0, n=4, ww=1.0, mv=1, mh=1)
    block(mb, Wx, Dy, wall_h, 0, {"px": endw, "ny": side, "py": side, "nx": endw}, cap=False, depth=0.15)
    # gambrel profile (YZ) extruded along X
    hw = Dy / 2
    k1y, k1z = hw * 0.62, wall_h + 2.6
    rz_ = wall_h + 4.4
    o = 0.4
    outer = [(-hw - o, wall_h - 0.3), (-k1y, k1z), (0, rz_), (k1y, k1z), (hw + o, wall_h - 0.3)]
    inner = [(hw + o - 0.05, wall_h - 0.55), (k1y - 0.1, k1z - 0.25), (0, rz_ - 0.25), (-k1y + 0.1, k1z - 0.25),
             (-hw - o + 0.05, wall_h - 0.55)]
    mb.prism_yz(outer + inner, -Wx / 2 - 0.35, Wx / 2 + 0.35, BODY)
    fill = [(-hw, wall_h), (hw, wall_h), (k1y - 0.12, k1z - 0.3), (0, rz_ - 0.3), (-k1y + 0.12, k1z - 0.3)]
    mb.prism_yz(fill, -Wx / 2, Wx / 2, BODY)
    # door X-bracing + hayloft door on +X
    with mb.at((Wx / 2, 0, 0)):
        for (y0, y1) in ((-2.2, 0), (0, 2.2)):
            mb.rod((0.18, y0 + 0.15, 0.15), (0.18, y1 - 0.15, 4.05), 0.08, BODY, n=4)
            mb.rod((0.18, y1 - 0.15, 0.15), (0.18, y0 + 0.15, 4.05), 0.08, BODY, n=4)
            mb.bb(0.0, y0, 0, 0.2, y0 + 0.14, 4.2, BODY)
            mb.bb(0.0, y1 - 0.14, 0, 0.2, y1, 4.2, BODY)
        mb.bb(0.0, -2.2, 4.06, 0.2, 2.2, 4.2, BODY)
        mb.bb(-0.05, -1.0, wall_h + 0.9, 0.08, 1.0, wall_h + 2.6, door_m)
        mb.bb(0.0, -1.1, wall_h + 0.8, 0.12, 1.1, wall_h + 0.95, BODY)
        mb.bb(0.0, -0.1, rz_ - 0.9, 1.2, 0.1, rz_ - 0.7, DARK)  # hay hoist beam
    # cupola on ridge
    mb.bb(-1.0, -1.0, rz_ - 0.3, 1.0, 1.0, rz_ + 1.4, BODY)
    pyramid_roof(mb, 2.0, 2.0, rz_ + 1.4, 1.2, over=0.25, t=0.12)
    if silo:
        sr = 2.8
        with mb.at((-Wx / 2 + 3.0, -Dy / 2 - sr - 1.0, 0)):
            mb.cyl(sr, silo_h, (0, 0, 0), BODY, n=28)
            for z in range(2, int(silo_h), 2):
                mb.cyl(sr + 0.05, 0.12, (0, 0, z), BODY, n=28)
            mb.sphere(sr + 0.1, (0, 0, silo_h), BODY, seg=28, rings=8, zmin=0.0)
            for z in range(1, int(silo_h), 1):
                mb.bb(sr - 0.05, -0.3, z, sr + 0.25, 0.3, z + 0.05, DARK)
            mb.bb(sr + 0.2, -0.32, 0.5, sr + 0.26, -0.27, silo_h, DARK)
            mb.bb(sr + 0.2, 0.27, 0.5, sr + 0.26, 0.32, silo_h, DARK)
    return dict(size=(Wx + 1, Dy + 8, max(rz_ + 3, silo_h + 3)))


def silo_group(mb, n=3, r=3.5, h=24.0, seed=0):
    """Grain elevator: row of concrete silos + head house + elevator leg."""
    for k in range(n):
        y = (k - (n - 1) / 2) * (2 * r + 0.1)
        mb.cyl(r, h, (0, y, 0), BODY, n=28)
        mb.cyl(r * 1.02, 0.4, (0, y, h), BODY, n=28)
        mb.cyl(r * 0.98, 1.4, (0, y, h + 0.4), BODY, n=28, r2=0.6)
    L = n * (2 * r + 0.1)
    mb.bb(-r * 0.6, -L / 2, h, r * 0.6, L / 2, h + 3.5, BODY)
    with mb.at((0, -L / 2 - 3.0, 0)):
        block(mb, 6, 6, h + 8, 0, {"px": lambda w: floors(w, 4, (h + 8) / 4, 0, 2.0, 1.4, n=1, ww=1.0, mv=0)})
        pyramid_roof(mb, 6, 6, h + 8, 1.0, 0.2)
    mb.rod((0, -L / 2 - 3.0, h + 6), (0, -L / 2 - 14.0, 3.0), 0.5, BODY, n=8)
    mb.bb(-1, -L / 2 - 16, 0, 1, -L / 2 - 12, 3.0, BODY)
    return dict(size=(2 * r, L + 16, h + 9))


# ================================================================== CITY: roads
# Roads run along X.  Asphalt top at z=0 (LIB_Dark), sidewalks top +0.15, kerb strip +0.17,
# lane paint (LIB_Light) 8 mm proud.  Dash period 6 m: use lengths that are multiples of 6 to tile.
KERB = 0.25


def _paint(mb, x0, y0, x1, y1):
    mb.bb(x0, y0, 0.0, x1, y1, 0.008, LIGHT)


def _dashes(mb, x0, x1, y, w=0.15, dash=3.0, period=6.0):
    n = int(round((x1 - x0) / period))
    for k in range(n):
        a = x0 + k * period + (period - dash) / 2
        _paint(mb, a, y - w / 2, a + dash, y + w / 2)


def lane_marks(mb, x0, x1, lanes, lane_w, style="dashed"):
    rw = lanes * lane_w
    for s in (-1, 1):
        _paint(mb, x0, s * (rw / 2 - 0.35) - 0.06, x1, s * (rw / 2 - 0.35) + 0.06)  # edge lines
    if lanes == 1:
        return
    half = lanes // 2
    if lanes % 2 == 0:
        if lanes >= 4 or style == "double":
            for s in (-1, 1):
                _paint(mb, x0, s * 0.15 - 0.06, x1, s * 0.15 + 0.06)
        elif style == "solid":
            _paint(mb, x0, -0.07, x1, 0.07)
        else:
            _dashes(mb, x0, x1, 0.0)
    for k in range(1, half):
        for s in (-1, 1):
            _dashes(mb, x0, x1, s * k * lane_w, 0.12)


def road_straight(mb, length=24.0, lanes=2, lane_w=3.5, sidewalk=3.0, style="dashed", seed=0):
    rw = lanes * lane_w
    L = length
    mb.bb(-L / 2, -rw / 2, -0.3, L / 2, rw / 2, 0.0, DARK)
    for s in (-1, 1):
        y0 = s * rw / 2
        mb.bb(-L / 2, y0, -0.3, L / 2, y0 + s * KERB, 0.17, BODY)
        if sidewalk > 0:
            mb.bb(-L / 2, y0 + s * KERB, -0.3, L / 2, y0 + s * (KERB + sidewalk), 0.15, BODY)
            # paving joints (subtle grooves would be micro-detail; use expansion strips every 6 m)
            for k in range(int(L // 6) + 1):
                x = -L / 2 + k * 6
                if -L / 2 < x < L / 2:
                    mb.bb(x - 0.02, min(y0 + s * KERB, y0 + s * (KERB + sidewalk)), 0.15,
                          x + 0.02, max(y0 + s * KERB, y0 + s * (KERB + sidewalk)), 0.152, DARK)
    lane_marks(mb, -L / 2, L / 2, lanes, lane_w, style)
    return dict(size=(L, rw + 2 * (KERB + sidewalk), 0.17))


def _corner_kerb(mb, rw2, E, r, sidewalk, sx, sy):
    """Sidewalk + kerb in the quadrant (sx, sy) of an intersection, rounded corner of radius r."""
    def arc(rad, n=8):
        c = rw2 + r
        return [(c + rad * math.cos(a), c + rad * math.sin(a)) for a in
                [math.pi + (math.pi / 2) * k / n for k in range(n + 1)]]
    k = KERB
    kpath = [(E, rw2 + k / 2)] + list(reversed(arc(r - k / 2))) + [(rw2 + k / 2, E)]
    kpath = [(sx * x, sy * y, 0) for x, y in reversed(kpath)] if sx * sy < 0 else [(sx * x, sy * y, 0) for x, y in kpath]
    mb.sweep(kpath, [(-k / 2, -0.3), (k / 2, -0.3), (k / 2, 0.17), (-k / 2, 0.17)], BODY)
    poly = [(E, rw2 + k), (E, E), (rw2 + k, E)] + arc(r - k)
    poly = [(sx * x, sy * y) for x, y in poly]
    mb.prism(poly, -0.3, 0.15, BODY)


def road_intersection(mb, lanes=2, lane_w=3.5, sidewalk=3.0, arm=6.0, corner_r=4.0, crosswalks=True,
                      arms=4, seed=0):
    """4-way (arms=4) or T (arms=3, the -Y arm closed) junction.  Arms extend `arm` m beyond the corners."""
    rw = lanes * lane_w
    rw2 = rw / 2
    E = rw2 + KERB + sidewalk + arm
    mb.bb(-E, -E, -0.3, E, E, 0.0, DARK)
    for sx in (-1, 1):
        for sy in (-1, 1):
            if arms == 3 and sy < 0:
                continue
            _corner_kerb(mb, rw2, E, corner_r, sidewalk, sx, sy)
    if arms == 3:
        mb.bb(-E, -E, -0.3, E, -rw2 - KERB, 0.15, BODY)
        mb.bb(-E, -rw2 - KERB, -0.3, E, -rw2, 0.17, BODY)
    cw0, cw1 = rw2 + 1.0, rw2 + 4.0
    dirs = [(1, 0), (-1, 0), (0, 1)] + ([(0, -1)] if arms == 4 else [])
    for (dx, dy) in dirs:
        rot = math.atan2(dy, dx)
        with mb.at(rz=rot):
            if crosswalks:
                n = int(rw / 1.0)
                for k in range(n):
                    y = -rw2 + 0.25 + k * (rw - 0.5) / n
                    _paint(mb, cw0, y, cw1, y + 0.5)
                _paint(mb, cw1 + 0.6, -rw2 + 0.3, cw1 + 1.0, 0.0)  # stop line (inbound half)
            x0 = cw1 + 1.2
            if lanes >= 2:
                for k in range(int((E - x0) // 3)):
                    a = x0 + k * 3.0
                    if a + 1.5 <= E:
                        _paint(mb, a, -0.075, a + 1.5, 0.075)
    return dict(size=(2 * E, 2 * E, 0.17))


def roundabout(mb, island_r=8.0, ring_w=8.0, lanes=2, lane_w=3.5, sidewalk=3.0, arm=14.0, seed=0):
    rw = lanes * lane_w
    Ro = island_r + ring_w
    E = Ro + arm
    mb.cyl(Ro, 0.3, (0, 0, -0.3), DARK, n=64)
    for k in range(4):
        with mb.at(rz=k * math.pi / 2):
            mb.bb(Ro * 0.7, -rw / 2, -0.3, E, rw / 2, -0.0005, DARK)
            # arm sidewalks start where they meet the outer sidewalk ring
            Ro2 = Ro + KERB + sidewalk
            yo = rw / 2 + KERB + sidewalk
            xs = math.sqrt(max(Ro2 ** 2 - yo ** 2, 0)) - 0.5
            for s in (-1, 1):
                mb.bb(xs, s * rw / 2, -0.3, E, s * (rw / 2 + KERB), 0.17, BODY)
                mb.bb(xs, s * (rw / 2 + KERB), -0.3, E, s * yo, 0.15, BODY)
            # splitter island
            mb.prism([(Ro + 0.8, 0), (Ro + 8, -0.9), (Ro + 8, 0.9)], -0.3, 0.17, BODY)
            # give-way dashes
            for j in range(int(rw / 2 / 0.9)):
                y = 0.3 + j * 0.9
                _paint(mb, Ro + 0.4, y, Ro + 0.7, y + 0.5)
            for j in range(int((E - Ro - 9) // 3)):
                a = Ro + 9 + j * 3
                _paint(mb, a, -0.075, a + 1.5, 0.075)
            # outer sidewalk arc between this arm and the next
            d1 = math.asin(min(1, yo / Ro2)) + 0.03
            arc = math.pi / 2 - 2 * d1
            if arc > 0:
                with mb.at(rz=d1):
                    mb.ring(Ro, Ro + KERB, -0.3, 0.17, BODY, n=16, arc=arc)
                    mb.ring(Ro + KERB, Ro2, -0.3, 0.15, BODY, n=16, arc=arc)
    # island
    mb.ring(island_r - KERB, island_r, -0.3, 0.17, BODY, n=48)
    mb.cyl(island_r - KERB, 0.45, (0, 0, -0.3), BODY, n=48)
    mb.lathe([(island_r - KERB - 0.3, 0.15), (island_r * 0.6, 0.6), (island_r * 0.25, 0.85), (0, 0.9)], BODY, n=32)
    # circulating lane divider
    rm = island_r + ring_w / 2
    nd = int(TAU * rm / 6)
    for k in range(nd):
        a = TAU * k / nd
        with mb.at((rm * math.cos(a), rm * math.sin(a), 0), rz=a + math.pi / 2):
            _paint(mb, -1.5, -0.075, 1.5, 0.075)
    tree(mb, "round", 7.0, seed=seed, loc=(0, 0, 0.8))
    return dict(size=(2 * E, 2 * E, 8))


def parking_lot(mb, bays=10, rows=2, bay_w=2.6, bay_d=5.0, aisle=6.5, trees=True, lamps=True, seed=0):
    """Surface car park: bays along X, rows of two facing bays around aisles."""
    L = bays * bay_w + 4.0
    D = rows * (2 * bay_d + aisle) + 2.0
    mb.bb(-L / 2, -D / 2, -0.3, L / 2, D / 2, 0.0, DARK)
    # perimeter kerb
    for (x0, y0, x1, y1) in ((-L / 2 - 0.3, -D / 2 - 0.3, L / 2 + 0.3, -D / 2), (-L / 2 - 0.3, D / 2, L / 2 + 0.3, D / 2 + 0.3),
                             (-L / 2 - 0.3, -D / 2, -L / 2, D / 2), (L / 2, -D / 2, L / 2 + 0.3, D / 2)):
        mb.bb(x0, y0, -0.3, x1, y1, 0.17, BODY)
    y = -D / 2 + 1.0
    for r in range(rows):
        for half in range(2):
            y0 = y + half * (bay_d + aisle)
            for k in range(bays + 1):
                x = -bays * bay_w / 2 + k * bay_w
                _paint(mb, x - 0.06, y0, x + 0.06, y0 + bay_d)
            _paint(mb, -bays * bay_w / 2, y0 + (bay_d if half == 0 else 0) - 0.06, bays * bay_w / 2,
                   y0 + (bay_d if half == 0 else 0) + 0.06)
            for k in range(bays):
                x = -bays * bay_w / 2 + (k + 0.5) * bay_w
                yy = y0 + (0.5 if half == 0 else bay_d - 0.65)
                mb.bb(x - 0.8, yy, 0, x + 0.8, yy + 0.15, 0.12, BODY)  # wheel stop
        # aisle arrows
        ya = y + bay_d + aisle / 2
        for k in (-1, 1):
            arrow_2d(mb, (k * L / 4, ya), 0.0 if k < 0 else math.pi, 2.4, 0.3)
        y += 2 * bay_d + aisle
        # island between double rows
        if r < rows - 1:
            pass
    if trees or lamps:
        for s in (-1, 1):
            x = s * (L / 2 - 1.2)
            if lamps:
                street_lamp(mb, 8.0, loc=(x, 0, 0), rz=0 if s < 0 else math.pi, double=True)
    # P sign
    with mb.at((L / 2 + 1.2, -D / 2 + 1.0, 0)):
        mb.cyl(0.05, 2.6, (0, 0, 0), BODY, n=8)
        mb.bb(-0.05, -0.45, 2.0, 0.05, 0.45, 2.9, ACCENT)
        mb.text("P", 0.7, (0.051, 0, 2.45), BODY, rot=FACE_PX, depth=0.02, font=FONT_BLACK)
    return dict(size=(L, D, 8))


def arrow_2d(mb, loc, rz, length=2.4, width=0.3, z=0.0, m=LIGHT, head=None):
    head = head or width * 3
    hl = head * 0.9
    pts = [(-length / 2, -width / 2), (length / 2 - hl, -width / 2), (length / 2 - hl, -head / 2), (length / 2, 0),
           (length / 2 - hl, head / 2), (length / 2 - hl, width / 2), (-length / 2, width / 2)]
    with mb.at((loc[0], loc[1], z), rz=rz):
        mb.prism(pts, 0.0, 0.008, m)


# ================================================================== CITY: furniture
def street_lamp(mb, h=8.0, arm=1.8, kind="modern", double=False, loc=(0, 0, 0), rz=0.0):
    """Lamp post; luminaire reaches toward +X (the road) before rz."""
    with mb.at(loc, rz=rz):
        if kind == "classic":
            mb.lathe([(0.22, 0), (0.22, 0.25), (0.16, 0.35), (0.14, 0.9), (0.1, 1.0), (0.08, 1.1), (0.07, h * 0.5),
                      (0.06, h - 0.9), (0.1, h - 0.8), (0, h - 0.8)], DARK, n=12)
            mb.lathe([(0.12, h - 0.8), (0.25, h - 0.6), (0.3, h - 0.1), (0.2, h)], GLASS, n=8)
            mb.lathe([(0.34, h - 0.05), (0.36, h), (0.2, h + 0.25), (0.04, h + 0.4), (0, h + 0.45)], DARK, n=8)
            mb.cyl(0.12, 0.4, (0, 0, h - 0.6), LIGHT, n=8)
            return
        mb.cyl(0.16, 0.6, (0, 0, 0), BODY, n=12)
        mb.cyl(0.1, h, (0, 0, 0.6), BODY, n=12, r2=0.06)
        for s in ((1, -1) if double else (1,)):
            path = [(0, 0, h - 0.6)] + [(s * arm * (1 - math.cos(a)), 0, h - 0.6 + 0.6 * math.sin(a))
                                        for a in [R(x) for x in range(10, 91, 20)]]
            path = [(0, 0, h - 0.8)] + [(s * arm * math.sin(a), 0, h - 0.8 + 0.6 * (1 - math.cos(a)) + 0.0)
                                        for a in [R(x) for x in (20, 45, 70, 90)]]
            mb.sweep(path, [(-0.045, -0.045), (0.045, -0.045), (0.045, 0.045), (-0.045, 0.045)], BODY)
            with mb.at((s * arm, 0, h - 0.2)):
                mb.bb(-0.1 if s > 0 else -0.65, -0.18, -0.08, 0.65 if s > 0 else 0.1, 0.18, 0.06, BODY)
                mb.bb(-0.05 if s > 0 else -0.6, -0.13, -0.1, 0.6 if s > 0 else 0.05, 0.13, -0.079, LIGHT)


def traffic_light(mb, kind="mast", arm=6.0, loc=(0, 0, 0), rz=0.0):
    """Signal heads face +X.  kind: mast (arm over the road toward +Y) | post."""
    def head(x, y, z):
        with mb.at((x, y, z)):
            mb.bb(-0.15, -0.17, -0.5, 0.15, 0.17, 0.5, DARK)
            mb.bb(-0.17, -0.3, -0.58, -0.14, 0.3, 0.58, DARK)  # back plate
            for k in range(3):
                zz = 0.32 - k * 0.32
                mb.cyl(0.11, 0.02, (0.15, 0, zz), LIGHT, n=12, rot=(0, R(90), 0))
                mb.bb(0.15, -0.14, zz + 0.1, 0.32, 0.14, zz + 0.13, DARK)  # visor
    with mb.at(loc, rz=rz):
        mb.cyl(0.2, 0.4, (0, 0, 0), DARK, n=12)
        if kind == "mast":
            mb.cyl(0.12, 6.4, (0, 0, 0), DARK, n=12, r2=0.1)
            mb.rod((0, 0, 6.0), (0, arm, 6.0), 0.08, DARK, n=8)
            mb.rod((0, 0, 4.8), (0, arm * 0.45, 6.0), 0.04, DARK, n=6)
            for y in (arm * 0.5, arm * 0.95):
                mb.bb(-0.02, y - 0.02, 5.6, 0.02, y + 0.02, 6.0, DARK)
                head(0.0, y, 5.0)
            head(0.2, 0, 3.0)
        else:
            mb.cyl(0.08, 3.6, (0, 0, 0), DARK, n=10)
            head(0.15, 0, 3.0)
            mb.bb(0.05, -0.15, 1.3, 0.3, 0.15, 1.75, DARK)  # pedestrian button / head
            mb.bb(0.3, -0.1, 1.4, 0.31, 0.1, 1.65, LIGHT)


def bench(mb, length=1.8, loc=(0, 0, 0), rz=0.0, back=True):
    """Park bench, sitter faces +X."""
    with mb.at(loc, rz=rz):
        for y in (-length / 2 + 0.12, length / 2 - 0.12):
            mb.add([(-0.25, y - 0.03, 0), (0.25, y - 0.03, 0), (0.22, y - 0.03, 0.42), (-0.2, y - 0.03, 0.42),
                    (-0.25, y + 0.03, 0), (0.25, y + 0.03, 0), (0.22, y + 0.03, 0.42), (-0.2, y + 0.03, 0.42)],
                   [(0, 1, 2, 3), (7, 6, 5, 4), (0, 4, 5, 1), (1, 5, 6, 2), (2, 6, 7, 3), (3, 7, 4, 0)], DARK)
            if back:
                mb.rod((-0.2, y, 0.4), (-0.32, y, 0.85), 0.03, DARK, n=6)
        for k in range(4):
            x = -0.2 + k * 0.13
            mb.bb(x - 0.055, -length / 2, 0.42, x + 0.055, length / 2, 0.46, BODY)
        if back:
            for k in range(3):
                z = 0.55 + k * 0.12
                xx = -0.24 - (z - 0.4) * 0.27
                mb.box((0.035, length, 0.09), (xx, 0, z), BODY, rot=(0, R(-15), 0))


def bin_(mb, loc=(0, 0, 0), kind="round"):
    with mb.at(loc):
        if kind == "round":
            mb.cyl(0.28, 0.9, (0, 0, 0), DARK, n=16, r2=0.3)
            mb.cyl(0.32, 0.08, (0, 0, 0.9), DARK, n=16)
            mb.lathe([(0.3, 0.98), (0.22, 1.08), (0.0, 1.1)], DARK, n=16)
            mb.bb(-0.15, -0.31, 0.75, 0.15, -0.29, 0.86, BODY)
        else:  # wheelie bin
            mb.add([(-0.3, -0.28, 0.05), (0.3, -0.28, 0.05), (0.33, 0.3, 0.05), (-0.33, 0.3, 0.05),
                    (-0.36, -0.33, 1.0), (0.36, -0.33, 1.0), (0.36, 0.38, 1.0), (-0.36, 0.38, 1.0)],
                   [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)], DARK)
            mb.bb(-0.38, -0.36, 1.0, 0.38, 0.42, 1.06, ACCENT)
            for s in (-1, 1):
                mb.cyl(0.1, 0.06, (s * 0.3, 0.3, 0.1), DARK, n=10, rot=(0, R(90), 0))


def hydrant(mb, loc=(0, 0, 0), m=ACCENT):
    with mb.at(loc):
        mb.lathe([(0.16, 0), (0.16, 0.06), (0.12, 0.08), (0.12, 0.55), (0.15, 0.58), (0.15, 0.62), (0.11, 0.66),
                  (0.08, 0.76), (0.03, 0.8), (0, 0.8)], m, n=14)
        for a in (0, math.pi):
            mb.cyl(0.05, 0.09, (0.11 * math.cos(a), 0.11 * math.sin(a), 0.42), m, n=8,
                   rot=(0, R(90), a))
        mb.cyl(0.07, 0.1, (0.11, 0, 0.36), m, n=8, rot=(0, R(90), 0))
        mb.cyl(0.035, 0.06, (0, 0, 0.8), m, n=5)


def tree(mb, kind="round", h=8.0, seed=0, loc=(0, 0, 0), canopy_m=BODY, trunk_m=BODY, detail=1.0):
    """Stylised white-model tree. kind: round | tall | conifer | small | wide."""
    rnd = random.Random(seed)
    x, y, z = loc
    if kind == "conifer":
        mb.cyl(h * 0.03, h * 0.25, (x, y, z), trunk_m, n=8, r2=h * 0.02)
        tiers = 5
        for k in range(tiers):
            t = k / tiers
            r = h * 0.24 * (1 - t * 0.75)
            zz = z + h * (0.18 + t * 0.62)
            mb.cyl(r, h * 0.3, (x, y, zz), canopy_m, n=12, r2=r * 0.15)
        mb.cyl(h * 0.06, h * 0.12, (x, y, z + h * 0.88), canopy_m, n=8, r2=0.0)
        return
    shapes = {"round": (0.42, 0.33, 0.55, 7), "tall": (0.3, 0.18, 0.62, 6), "small": (0.4, 0.3, 0.5, 5),
              "wide": (0.36, 0.45, 0.5, 9)}
    trunk_f, cr_f, cz_f, nb = shapes.get(kind, shapes["round"])
    tr = h * 0.035
    th = h * trunk_f
    mb.cyl(tr, th + h * 0.1, (x, y, z), trunk_m, n=10, r2=tr * 0.7)
    # branches
    for k in range(3):
        a = TAU * k / 3 + rnd.uniform(-0.3, 0.3)
        mb.rod((x, y, z + th * 0.85), (x + math.cos(a) * h * cr_f * 0.5, y + math.sin(a) * h * cr_f * 0.5,
                                      z + th + h * 0.15), tr * 0.45, trunk_m, n=6)
    cz = z + h * cz_f + h * 0.05
    R_ = h * cr_f
    sph = [((x, y, cz + R_ * 0.1), R_ * 0.8)]
    vert = 1.6 if kind == "tall" else 1.0
    for k in range(nb):
        a = TAU * k / nb + rnd.uniform(-0.3, 0.3)
        rr = R_ * rnd.uniform(0.45, 0.7)
        d = R_ * rnd.uniform(0.35, 0.55)
        sph.append(((x + math.cos(a) * d, y + math.sin(a) * d, cz + rnd.uniform(-0.35, 0.45) * R_ * vert), rr))
    sph.append(((x, y, cz + R_ * 0.55 * vert), R_ * 0.55))
    if kind == "tall":
        sph = [((p[0], p[1], cz + (p[2] - cz) * 1.6), r) for p, r in sph]
    mb.blob(sph, canopy_m, voxel=h / 38 * detail, noise=h * 0.05, noise_scale=h * 0.1, smooth=3, seed=seed)


def bus_stop(mb, length=4.2, seed=0):
    """Bus shelter facing +X (kerb side), glass back + ends, bench, ad panel, stop pole."""
    d, h = 1.6, 2.6
    mb.bb(-d / 2 - 0.1, -length / 2 - 0.1, 0, d / 2 + 0.3, length / 2 + 0.1, 0.03, BODY)
    # frame posts
    for (xx, yy) in ((-d / 2, -length / 2), (-d / 2, length / 2), (d / 2, -length / 2), (d / 2, length / 2),
                     (-d / 2, 0)):
        mb.bb(xx - 0.05, yy - 0.05, 0, xx + 0.05, yy + 0.05, h, DARK)
    mb.bb(-d / 2 - 0.15, -length / 2 - 0.2, h, d / 2 + 0.3, length / 2 + 0.2, h + 0.15, BODY)
    mb.bb(-d / 2 - 0.1, -length / 2 - 0.15, h + 0.15, d / 2 + 0.25, length / 2 + 0.15, h + 0.2, BODY)
    # glass back + side panels
    mb.bb(-d / 2 - 0.015, -length / 2 + 0.05, 0.15, -d / 2 + 0.015, length / 2 - 0.05, h - 0.1, GLASS)
    for s in (-1, 1):
        mb.bb(-d / 2 + 0.05, s * length / 2 - 0.015, 0.15, d / 2 - 0.35, s * length / 2 + 0.015, h - 0.1, GLASS)
    # ad panel at +Y end, lit face
    mb.bb(-0.05, length / 2 + 0.05, 0.2, d / 2, length / 2 + 0.25, 2.2, DARK)
    mb.bb(-0.0, length / 2 + 0.249, 0.3, d / 2 - 0.08, length / 2 + 0.26, 2.1, LIGHT)
    bench(mb, length * 0.55, (-d / 2 + 0.35, 0, 0), 0.0, back=False)
    # stop sign pole
    with mb.at((d / 2 + 0.6, -length / 2 - 0.6, 0)):
        mb.cyl(0.04, 3.0, (0, 0, 0), DARK, n=8)
        mb.cyl(0.32, 0.05, (0.02, 0, 2.7), ACCENT, n=20, rot=(0, R(90), 0))
        mb.text("BUS", 0.18, (0.075, 0, 2.7), BODY, rot=FACE_PX, depth=0.01, font=FONT_BLACK)
        mb.bb(0.02, -0.25, 1.7, 0.06, 0.25, 2.3, BODY)
    return dict(size=(d + 1.2, length + 1.2, 3.1))


# ================================================================== CITY: block, plaza, park
def city_block(mb, w=84.0, d=60.0, style="mixed", sidewalk=4.0, seed=0):
    """Sidewalked block filled with buildings whose fronts face the surrounding streets.
    style: downtown | mixed | residential.  Footprint w (X) by d (Y)."""
    rnd = random.Random(seed)
    # plinth / sidewalk with kerb
    mb.bb(-w / 2, -d / 2, -0.3, w / 2, d / 2, 0.15, BODY)
    for (x0, y0, x1, y1) in ((-w / 2 - KERB, -d / 2 - KERB, w / 2 + KERB, -d / 2), (-w / 2 - KERB, d / 2, w / 2 + KERB, d / 2 + KERB),
                             (-w / 2 - KERB, -d / 2, -w / 2, d / 2), (w / 2, -d / 2, w / 2 + KERB, d / 2)):
        mb.bb(x0, y0, -0.3, x1, y1, 0.17, BODY)
    sw = sidewalk
    iw, idp = w - 2 * sw, d - 2 * sw   # buildable
    z = 0.15
    maxdep = min(iw, idp) / 2 - 1.0

    def place(fn, cx, cy, rz, **kw):
        with mb.at((cx, cy, z), rz=rz):
            fn(mb, **kw)

    if style == "downtown":
        c = min(26.0, maxdep * 2 * 0.9)
        corners = [(1, 1), (1, -1), (-1, -1), (-1, 1)]
        kinds = rnd.sample(["tower_c", "tower_c2", "midrise", "sky"], 4)
        for (sx, sy), k in zip(corners, kinds):
            cx, cy = sx * (iw / 2 - c / 2), sy * (idp / 2 - c / 2)
            rz = 0.0 if sx > 0 else math.pi
            if k == "sky":
                place(skyscraper, cx, cy, rz, width=c - 2, storeys=rnd.choice([34, 40, 46]), crown=rnd.choice(["spire", "deco", "mast"]),
                      taper=(1.0, 0.82, 0.64))
            elif k == "midrise":
                place(office_tower, cx, cy, rz, width=c - 1, depth=c - 1, storeys=rnd.randint(7, 10), tiers=(), logo=True)
            else:
                place(office_tower, cx, cy, rz, width=c - 1, depth=c - 1, storeys=rnd.randint(14, 22),
                      tiers=((0.6, 0.8),), logo=rnd.random() < 0.6)
        # infill between corners on the long sides
        mid = iw - 2 * c
        if mid > 10:
            for sy in (-1, 1):
                place(office_tower, 0, sy * (idp / 2 - 9), sy * -math.pi / 2 if sy < 0 else math.pi / 2,
                      width=mid - 2, depth=16.0, storeys=rnd.randint(5, 8), tiers=(), logo=False)
        return dict(size=(w, d, 200))
    # mixed / residential: corner buildings + rows along each edge
    c = 12.0 if style == "mixed" else 0.0
    if style == "mixed":
        for i, (sx, sy) in enumerate(((1, -1), (1, 1), (-1, 1), (-1, -1))):
            cx, cy = sx * (iw / 2 - c / 2), sy * (idp / 2 - c / 2)
            rz = {(1, -1): 0.0, (1, 1): math.pi / 2, (-1, 1): math.pi, (-1, -1): -math.pi / 2}[(sx, sy)]
            if i % 2 == 0:
                place(corner_cafe, cx, cy, rz, size=c, tables=2, sign=rnd.choice(["CAFÉ", "BAR", "DELI"]))
            else:
                place(apartment, cx, cy, rz, width=c, depth=c, storeys=rnd.randint(4, 6), balconies=False)
    # edges: (centre of edge line, outward rotation, length available)
    edges = [((iw / 2, 0), 0.0, idp - 2 * c), ((0, idp / 2), math.pi / 2, iw - 2 * c),
             ((-iw / 2, 0), math.pi, idp - 2 * c), ((0, -idp / 2), -math.pi / 2, iw - 2 * c)]
    for (ex, ey), rz, L in edges:
        if L < 6:
            continue
        # build a sequence of frontages filling L
        seq = []
        rem = L
        while rem > 5.5:
            if style == "residential":
                f = rnd.choice([11.0, 12.0, 13.0])
            else:
                f = rnd.choice([7.0, 8.0, 9.0, 14.0])
            f = min(f, rem)
            if rem - f < 5.5:
                f = rem
            seq.append(f)
            rem -= f
        u = -L / 2
        for f in seq:
            uc = u + f / 2
            u += f
            # local edge frame: front faces outward (+X of the building = outward)
            dxu, dyu = -math.sin(rz), math.cos(rz)  # along-edge direction
            nx_, ny_ = math.cos(rz), math.sin(rz)
            if style == "residential":
                dep = min(9.0, maxdep - 6)
                cx = ex + dxu * uc - nx_ * (dep / 2 + 4.5)
                cy = ey + dyu * uc - ny_ * (dep / 2 + 4.5)
                place(house, cx, cy, rz, frontage=f - 2.5, depth=dep, storeys=rnd.choice([1, 2, 2]),
                      roof=rnd.choice(["gable", "hip", "gable"]), porch=rnd.random() < 0.5, seed=rnd.randint(0, 99),
                      chimneys=rnd.choice([0, 1]))
                # front garden hedge / fence + tree
                fence(mb_=mb, p0=(ex + dxu * (uc - f / 2 + 0.3) - nx_ * 0.5, ey + dyu * (uc - f / 2 + 0.3) - ny_ * 0.5, z),
                      p1=(ex + dxu * (uc - 1.4) - nx_ * 0.5, ey + dyu * (uc - 1.4) - ny_ * 0.5, z), kind="rail")
                tree(mb, rnd.choice(["round", "small"]), rnd.uniform(5, 7), seed=rnd.randint(0, 999), detail=2.2,
                     loc=(ex + dxu * (uc + f * 0.3) - nx_ * 2.5, ey + dyu * (uc + f * 0.3) - ny_ * 2.5, z))
            else:
                if f >= 13:
                    dep = min(14.0, maxdep)
                    cx, cy = ex + dxu * uc - nx_ * dep / 2, ey + dyu * uc - ny_ * dep / 2
                    place(apartment, cx, cy, rz, width=f, depth=dep, storeys=rnd.randint(4, 6), balconies=rnd.random() < 0.5)
                else:
                    dep = min(14.0, maxdep)
                    cx, cy = ex + dxu * uc - nx_ * dep / 2, ey + dyu * uc - ny_ * dep / 2
                    place(storefront, cx, cy, rz, frontage=f, depth=dep, storeys=rnd.randint(2, 4),
                          sign=rnd.choice(["SHOP", "BAKERY", "BOOKS", "MARKET", "TOYS", "HARDWARE"]),
                          stripes=rnd.choice([0, 0, 7]))
    # street trees along the sidewalk
    if style != "residential":
        for (ex, ey), rz, L in edges:
            dxu, dyu = -math.sin(rz), math.cos(rz)
            nx_, ny_ = math.cos(rz), math.sin(rz)
            n = int((L + 2 * c) // 16)
            for k in range(n):
                uc = -(L + 2 * c) / 2 + (k + 0.5) * (L + 2 * c) / n
                tx, ty = ex + dxu * uc + nx_ * (sw - 1.2), ey + dyu * uc + ny_ * (sw - 1.2)
                if k % 2 == 0:
                    tree(mb, "small", 6.0, seed=seed * 31 + k, loc=(tx, ty, z), detail=2.2)
                else:
                    street_lamp(mb, 7.0, 1.4, loc=(tx, ty, z), rz=rz)
    return dict(size=(w, d, 30))


def fence(mb_, p0, p1, kind="picket", h=1.0):
    """Fence between two points.  kind: picket | security | rail."""
    mb = mb_
    p0, p1 = Vector(p0), Vector(p1)
    d = p1 - p0
    L = d.length
    if L < 0.2:
        return
    rz = math.atan2(d.y, d.x)
    with mb.at(tuple(p0), rz=rz):
        if kind == "picket":
            n = int(L / 0.14)
            for k in range(n):
                x = (k + 0.5) * L / n
                mb.add([(x - 0.04, -0.012, 0), (x + 0.04, -0.012, 0), (x + 0.04, -0.012, h - 0.08), (x, -0.012, h),
                        (x - 0.04, -0.012, h - 0.08),
                        (x - 0.04, 0.012, 0), (x + 0.04, 0.012, 0), (x + 0.04, 0.012, h - 0.08), (x, 0.012, h),
                        (x - 0.04, 0.012, h - 0.08)],
                       [(0, 1, 2, 3, 4), (9, 8, 7, 6, 5), (0, 5, 6, 1), (1, 6, 7, 2), (2, 7, 8, 3), (3, 8, 9, 4),
                        (4, 9, 5, 0)], BODY)
            for zz in (0.25, h - 0.3):
                mb.bb(0, 0.012, zz, L, 0.05, zz + 0.08, BODY)
            for k in range(int(L // 2.4) + 1):
                x = min(L - 0.05, k * 2.4 + 0.05)
                mb.bb(x - 0.05, 0.012, 0, x + 0.05, 0.1, h - 0.05, BODY)
        elif kind == "rail":
            for k in range(int(L // 2.0) + 1):
                x = min(L - 0.05, k * 2.0 + 0.05)
                mb.bb(x - 0.05, -0.05, 0, x + 0.05, 0.05, h, BODY)
            for zz in (h * 0.45, h - 0.1):
                mb.bb(0, -0.03, zz, L, 0.03, zz + 0.08, BODY)


def plaza_fountain(mb, size=30.0, basin_r=5.0, seed=0):
    """Paved square with a tiered fountain, benches, planters with trees and lamps."""
    rnd = random.Random(seed)
    s = size / 2
    mb.bb(-s, -s, -0.3, s, s, 0.12, BODY)
    # paving bands (slightly raised strips)
    for k in range(-2, 3):
        mb.bb(k * size / 5 - 0.1, -s, 0.12, k * size / 5 + 0.1, s, 0.125, LIGHT)
        mb.bb(-s, k * size / 5 - 0.1, 0.12, s, k * size / 5 + 0.1, 0.125, LIGHT)
    z = 0.12
    # fountain
    mb.ring(basin_r - 0.35, basin_r, z, z + 0.55, BODY, n=48)
    mb.ring(basin_r - 0.45, basin_r + 0.1, z + 0.55, z + 0.65, BODY, n=48)
    mb.cyl(basin_r - 0.34, 0.38, (0, 0, z), GLASS, n=48)
    mb.lathe([(0.7, z), (0.6, z + 0.5), (0.35, z + 0.8), (0.3, z + 1.4)] +
             [(basin_r * 0.42, z + 1.55), (basin_r * 0.45, z + 1.75), (basin_r * 0.4, z + 1.8), (0.3, z + 1.7)] +
             [(0.22, z + 2.4), (basin_r * 0.22, z + 2.55), (basin_r * 0.24, z + 2.7), (basin_r * 0.2, z + 2.75),
              (0.15, z + 2.7), (0.12, z + 3.3), (0.2, z + 3.4), (0.0, z + 3.6)], BODY, n=32)
    mb.cyl(basin_r * 0.41, 0.06, (0, 0, z + 1.68), GLASS, n=32)
    mb.cyl(basin_r * 0.19, 0.06, (0, 0, z + 2.65), GLASS, n=24)
    # water jets (glassy thin cones)
    for k in range(8):
        a = TAU * k / 8
        mb.rod((basin_r * 0.75 * math.cos(a), basin_r * 0.75 * math.sin(a), z + 0.38),
               (basin_r * 0.5 * math.cos(a), basin_r * 0.5 * math.sin(a), z + 1.4), 0.05, GLASS, n=6, r2=0.02)
    # benches facing fountain + planters with trees at corners + lamps
    for k in range(4):
        a = TAU * k / 4
        for o in (-1, 1):
            r = basin_r + 3.2
            bx, by = r * math.cos(a) - o * 2.0 * math.sin(a), r * math.sin(a) + o * 2.0 * math.cos(a)
            bench(mb, 1.8, (bx, by, z), a + math.pi)
        cx, cy = (s - 3.0) * math.cos(a + math.pi / 4) * 1.41, (s - 3.0) * math.sin(a + math.pi / 4) * 1.41
        mb.bb(cx - 1.6, cy - 1.6, z, cx + 1.6, cy + 1.6, z + 0.6, BODY)
        mb.bb(cx - 1.35, cy - 1.35, z + 0.6, cx + 1.35, cy + 1.35, z + 0.62, DARK)
        tree(mb, "round", 7.5, seed=seed + k, loc=(cx, cy, z + 0.6))
        lx, ly = (s - 1.0) * math.cos(a), (s - 1.0) * math.sin(a)
        street_lamp(mb, 4.5, kind="classic", loc=(lx, ly, z))
    return dict(size=(size, size, 9))


def park(mb, w=60.0, d=44.0, trees=14, pond=True, seed=0):
    """Park: raised lawns, cross paths, pond, trees, benches, lamps."""
    rnd = random.Random(seed)
    pw = 3.0
    mb.bb(-w / 2, -d / 2, -0.3, w / 2, d / 2, 0.05, LIGHT)  # path surface
    lawns = [(-w / 2 + 0.6, -d / 2 + 0.6, -pw / 2, -pw / 2), (pw / 2, -d / 2 + 0.6, w / 2 - 0.6, -pw / 2),
             (-w / 2 + 0.6, pw / 2, -pw / 2, d / 2 - 0.6), (pw / 2, pw / 2, w / 2 - 0.6, d / 2 - 0.6)]
    for (x0, y0, x1, y1) in lawns:
        mb.bb(x0, y0, -0.3, x1, y1, 0.18, BODY)
    # circular centre with pond
    mb.cyl(7.0, 0.04, (0, 0, 0.05), LIGHT, n=40)
    if pond:
        mb.ring(4.6, 5.0, 0.0, 0.35, BODY, n=40)
        mb.cyl(4.62, 0.2, (0, 0, 0.0), GLASS, n=40)
    placed = []
    for k in range(trees * 4):
        if len(placed) >= trees:
            break
        (x0, y0, x1, y1) = lawns[k % 4]
        x, y = rnd.uniform(x0 + 2.5, x1 - 2.5), rnd.uniform(y0 + 2.5, y1 - 2.5)
        if math.hypot(x, y) < 10 or any(math.hypot(x - a, y - b) < 6 for a, b in placed):
            continue
        placed.append((x, y))
        tree(mb, rnd.choice(["round", "round", "wide", "tall", "conifer"]), rnd.uniform(6, 10), seed=rnd.randint(0, 9999),
             loc=(x, y, 0.18))
    for k in range(4):
        a = TAU * k / 4 + math.pi / 4
        bench(mb, 1.8, (8.2 * math.cos(a), 8.2 * math.sin(a), 0.05), a + math.pi)
    for (x, y) in ((w / 4, 0), (-w / 4, 0), (0, d / 4), (0, -d / 4)):
        street_lamp(mb, 4.0, kind="classic", loc=(x, y + (pw / 2 + 0.4 if x else 0), 0.05) if x else (x + pw / 2 + 0.4, y, 0.05))
    return dict(size=(w, d, 10))


# ================================================================== CITY: bridges (span along X)
def _deck(mb, x0, x1, width, z, thick=2.2, lanes=2, parapet="solid"):
    """Bridge deck with road surface (top at z), lane paint and parapets."""
    rw = lanes * 3.5
    mb.bb(x0, -width / 2, z - thick, x1, width / 2, z - 0.05, BODY)
    mb.bb(x0, -rw / 2, z - 0.06, x1, rw / 2, z, DARK)
    with mb.at((0, 0, z)):
        L = x1 - x0
        n = int(L // 6)
        for k in range(n):
            a = x0 + k * 6 + 1.5
            _paint(mb, a, -0.075, a + 3.0, 0.075)
        for s in (-1, 1):
            _paint(mb, x0, s * (rw / 2 - 0.35) - 0.06, x1, s * (rw / 2 - 0.35) + 0.06)
    for s in (-1, 1):
        mb.bb(x0, s * rw / 2, z - 0.1, x1, s * (width / 2 - 0.6), z + 0.15, BODY)  # footway
        if parapet == "solid":
            mb.bb(x0, s * (width / 2 - 0.6), z - 0.1, x1, s * width / 2, z + 1.1, BODY)
        else:
            mb.bb(x0, s * (width / 2 - 0.1), z + 1.0, x1, s * width / 2, z + 1.12, BODY)
            n = int((x1 - x0) // 2.0)
            for k in range(n + 1):
                x = x0 + (x1 - x0) * k / n
                mb.bb(x - 0.05, s * (width / 2 - 0.1), z + 0.15, x + 0.05, s * width / 2, z + 1.0, BODY)


def beam_bridge(mb, span=30.0, spans=3, width=12.0, clearance=9.0, seed=0):
    L = span * spans
    z = clearance + 2.2
    _deck(mb, -L / 2, L / 2, width, z, 2.2)
    for s in (-1, 1):  # girders
        mb.bb(-L / 2, s * width * 0.22 - 1.0, z - 3.4, L / 2, s * width * 0.22 + 1.0, z - 2.1, BODY)
    for k in range(1, spans):
        x = -L / 2 + k * span
        mb.bb(x - 1.0, -width * 0.18, 0, x + 1.0, width * 0.18, z - 4.4, BODY)       # pier wall
        mb.bb(x - 1.3, -width / 2 + 0.5, z - 4.4, x + 1.3, width / 2 - 0.5, z - 3.4, BODY)  # cap
        mb.bb(x - 1.8, -width * 0.25, 0, x + 1.8, width * 0.25, 0.8, BODY)  # footing
    for s in (-1, 1):  # abutments + wing walls
        x = s * L / 2
        mb.bb(x - s * 2.5, -width / 2 - 0.5, 0, x + s * 3.5, width / 2 + 0.5, z - 2.2, BODY)
        for t in (-1, 1):
            mb.bb(x, t * (width / 2 + 0.5) - 0.4, 0, x + s * 8.0, t * (width / 2 + 0.5) + 0.4, z - 2.0, BODY)
    return dict(size=(L + 16, width + 2, z + 1.1))


def arch_bridge(mb, span=120.0, rise=30.0, width=16.0, approach=24.0, seed=0):
    """Open-spandrel concrete deck-arch bridge."""
    z = rise + 3.0
    L = span + 2 * approach
    _deck(mb, -L / 2, L / 2, width, z, 1.6, parapet="rail")

    def az(x):
        return rise * (1 - (2 * x / span) ** 2)

    path = [(x, 0, az(x)) for x in [-span / 2 + span * k / 40 for k in range(41)]]
    for s in (-1, 1):
        y = s * (width / 2 - 2.2)
        mb.sweep([(p[0], y, p[2]) for p in path], [(-1.1, -1.4), (1.1, -1.4), (1.1, 1.4), (-1.1, 1.4)], BODY)
    # skewbacks / abutments
    for s in (-1, 1):
        mb.bb(s * span / 2 - 4, -width / 2, -1, s * span / 2 + 4, width / 2, 3.0, BODY)
    # spandrel columns + crossbeams
    n = int(span // 8)
    for k in range(1, n):
        x = -span / 2 + span * k / n
        a = az(x)
        if z - 1.6 - a < 1.2:
            continue
        for s in (-1, 1):
            y = s * (width / 2 - 2.2)
            mb.bb(x - 0.6, y - 0.8, a, x + 0.6, y + 0.8, z - 1.6, BODY)
        mb.bb(x - 0.5, -width / 2 + 2.2, z - 2.4, x + 0.5, width / 2 - 2.2, z - 1.6, BODY)
    # approach piers
    for s in (-1, 1):
        for k in range(1, int(approach // 12) + 1):
            x = s * (span / 2 + k * 12)
            if abs(x) >= L / 2 - 1:
                continue
            for t in (-1, 1):
                mb.bb(x - 0.8, t * (width / 2 - 2.2) - 0.9, 0, x + 0.8, t * (width / 2 - 2.2) + 0.9, z - 1.6, BODY)
        mb.bb(s * L / 2 - 3, -width / 2 - 0.5, 0, s * L / 2 + 3, width / 2 + 0.5, z - 1.6, BODY)
    return dict(size=(L + 6, width + 1, z + 1.2))


def masonry_bridge(mb, arches=3, span=14.0, pier=3.0, rise=None, width=8.0, spring=2.0, seed=0):
    """Historic stone multi-arch bridge (semicircular arches)."""
    r = span / 2
    rise = rise or r
    L = arches * span + (arches - 1) * pier + 2 * 6.0
    H = spring + rise + 1.6
    x = -L / 2
    pts = [(x, 0)]
    x += 6.0
    for k in range(arches):
        pts.append((x, 0))
        pts.append((x, spring))
        for j in range(1, 16):
            a = math.pi - math.pi * j / 16
            pts.append((x + r + r * math.cos(a), spring + rise * math.sin(a)))
        pts.append((x + span, spring))
        pts.append((x + span, 0))
        x += span + (pier if k < arches - 1 else 0)
    pts.append((L / 2, 0))
    pts.append((L / 2, H))
    pts.append((-L / 2, H))
    mb.prism_xz(pts, -width / 2, width / 2, BODY)
    # cutwaters on piers + string course + parapets + roadway
    x = -L / 2 + 6.0 + span
    for k in range(arches - 1):
        for s in (-1, 1):
            mb.prism([(x, s * width / 2), (x + pier, s * width / 2), (x + pier / 2, s * (width / 2 + pier * 0.7))],
                     0, spring + 1.0, BODY)
        x += span + pier
    mb.bb(-L / 2, -width / 2 - 0.2, H - 1.0, L / 2, width / 2 + 0.2, H - 0.75, BODY)
    for s in (-1, 1):
        y0, y1 = s * width / 2, s * (width / 2 - 0.45)
        mb.bb(-L / 2, min(y0, y1), H, L / 2, max(y0, y1), H + 1.0, BODY)
        y0, y1 = s * (width / 2 + 0.1), s * (width / 2 - 0.55)
        mb.bb(-L / 2, min(y0, y1), H + 1.0, L / 2, max(y0, y1), H + 1.15, BODY)
    mb.bb(-L / 2, -width / 2 + 0.45, H - 0.02, L / 2, width / 2 - 0.45, H + 0.03, DARK)
    return dict(size=(L, width + 2 * pier * 0.7, H + 1.2))


def suspension_bridge(mb, main=300.0, side_f=0.35, width=22.0, deck_h=40.0, sag_f=0.1, hanger=10.0, seed=0):
    """Suspension bridge: two portal towers, catenary main cables, hangers, anchorages.  Span along X."""
    side = main * side_f
    sag = main * sag_f
    top = deck_h + 2.0 + sag
    xa = main / 2 + side
    _deck(mb, -xa, xa, width, deck_h, 3.0, lanes=4, parapet="rail")
    ly = width / 2 + 1.2
    # towers
    for s in (-1, 1):
        x = s * main / 2
        for t in (-1, 1):
            y = t * ly
            b0, b1 = (2.2, 3.0), (1.5, 2.2)
            ring0 = [(x - b0[0], y - b0[1], 0), (x + b0[0], y - b0[1], 0), (x + b0[0], y + b0[1], 0), (x - b0[0], y + b0[1], 0)]
            ring1 = [(x - b1[0], y - b1[1], top + 3), (x + b1[0], y - b1[1], top + 3), (x + b1[0], y + b1[1], top + 3),
                     (x - b1[0], y + b1[1], top + 3)]
            mb.loft([ring0, ring1], BODY)
            mb.bb(x - 2.0, y - 1.4, top + 3, x + 2.0, y + 1.4, top + 4.2, BODY)  # saddle
        for zz, hh in ((deck_h - 5.0, 3.5), ((deck_h + top) / 2, 3.0), (top - 1.0, 4.0)):
            mb.bb(x - 1.6, -ly, zz - hh / 2, x + 1.6, ly, zz + hh / 2, BODY)
        mb.bb(x - 6, -ly - 5, 0, x + 6, ly + 5, 4.0, BODY)  # pier footing
    # anchorages
    for s in (-1, 1):
        x = s * xa
        mb.bb(x - s * 2, -width / 2 - 4, 0, x + s * 22, width / 2 + 4, deck_h + 2.0, BODY)
        mb.add([(x + s * 22, -width / 2 - 4, deck_h + 2.0), (x + s * 22, width / 2 + 4, deck_h + 2.0),
                (x + s * 34, width / 2 + 4, 0), (x + s * 34, -width / 2 - 4, 0),
                (x + s * 22, -width / 2 - 4, 0), (x + s * 22, width / 2 + 4, 0)],
               [(0, 1, 2, 3) if s > 0 else (3, 2, 1, 0), (0, 3, 4) if s > 0 else (4, 3, 0),
                (1, 5, 2) if s > 0 else (2, 5, 1)], BODY)
    # main cables
    zc0 = deck_h + 2.0

    def cz_main(x):
        return zc0 + sag * (2 * x / main) ** 2

    zt = top + 4.2
    cab = [(-0.55, -0.55), (0.55, -0.55), (0.55, 0.55), (-0.55, 0.55)]
    cab = [(0.6 * math.cos(a), 0.6 * math.sin(a)) for a in [TAU * k / 8 for k in range(8)]]
    for t in (-1, 1):
        y = t * ly
        path = [(x, y, cz_main(x) + (zt - top - 2.0) * (2 * x / main) ** 2) for x in
                [-main / 2 + main * k / 60 for k in range(61)]]
        mb.sweep(path, cab, BODY, cap=True)
        for s in (-1, 1):
            p0 = (s * main / 2, y, zt)
            p1 = (s * xa, y, deck_h + 1.5)
            sp = []
            for k in range(13):
                u = k / 12
                sp.append((p0[0] + (p1[0] - p0[0]) * u, y, p0[2] + (p1[2] - p0[2]) * u - side * 0.05 * 4 * u * (1 - u)))
            mb.sweep(sp, cab, BODY)
            # side-span hangers
            for k in range(1, int(side // hanger)):
                u = k * hanger / side
                xx = p0[0] + (p1[0] - p0[0]) * u
                zz = p0[2] + (p1[2] - p0[2]) * u - side * 0.05 * 4 * u * (1 - u)
                if zz - deck_h > 1.0:
                    mb.rod((xx, y, deck_h), (xx, y, zz), 0.1, DARK, n=4)
        # main-span hangers
        for k in range(1, int(main // hanger)):
            xx = -main / 2 + k * hanger
            zz = cz_main(xx) + (zt - top - 2.0) * (2 * xx / main) ** 2
            mb.rod((xx, y, deck_h), (xx, y, zz), 0.1, DARK, n=4)
    return dict(size=(2 * xa + 68, width + 12, top + 5))


# ================================================================== CITY: walls, fences, barriers, border
def wall_segment(mb, length=12.0, h=2.4, t=0.3, pilasters=3.0, seed=0):
    mb.bb(-length / 2, -t / 2 - 0.15, 0, length / 2, t / 2 + 0.15, 0.3, BODY)
    mb.bb(-length / 2, -t / 2, 0, length / 2, t / 2, h, BODY)
    mb.bb(-length / 2 - 0.05, -t / 2 - 0.06, h, length / 2 + 0.05, t / 2 + 0.06, h + 0.1, BODY)
    n = int(length // pilasters)
    for k in range(n + 1):
        x = -length / 2 + 0.2 + (length - 0.4) * k / n
        mb.bb(x - 0.2, -t / 2 - 0.08, 0, x + 0.2, t / 2 + 0.08, h + 0.2, BODY)
        mb.bb(x - 0.25, -t / 2 - 0.12, h + 0.2, x + 0.25, t / 2 + 0.12, h + 0.3, BODY)
    return dict(size=(length + 0.5, t + 0.3, h + 0.3))


def picket_fence(mb, length=10.0, h=1.0, seed=0):
    fence(mb, (-length / 2, 0, 0), (length / 2, 0, 0), "picket", h)
    return dict(size=(length, 0.2, h))


def security_fence(mb, length=12.0, h=3.0, post=3.0, barbed=True, seed=0):
    """Weld-mesh security fence with concertina wire."""
    n = int(length // post)
    for k in range(n + 1):
        x = -length / 2 + length * k / n
        mb.bb(x - 0.05, -0.05, 0, x + 0.05, 0.05, h + 0.4, DARK)
        mb.bb(x - 0.2, -0.2, -0.0, x + 0.2, 0.2, 0.15, BODY)
        mb.rod((x, 0, h + 0.4), (x, -0.45, h + 0.75), 0.03, DARK, n=4)
    for z in (0.1, h * 0.33, h * 0.66, h - 0.02):
        mb.bb(-length / 2, -0.015, z, length / 2, 0.015, z + 0.04, DARK)
    nv = int(length / 0.2)
    for k in range(nv + 1):
        x = -length / 2 + length * k / nv
        mb.bb(x - 0.008, -0.008, 0.1, x + 0.008, 0.008, h, DARK)
    if barbed:
        turns = int(length * 1.5)
        pts = []
        for k in range(turns * 10 + 1):
            a = TAU * k / 10
            x = -length / 2 + length * k / (turns * 10)
            pts.append((x + 0.12 * math.cos(a), -0.25 + 0.3 * math.sin(a), h + 0.65 + 0.3 * math.cos(a)))
        mb.sweep(pts, [(0.015 * math.cos(b), 0.015 * math.sin(b)) for b in [TAU * j / 4 for j in range(4)]], DARK)
    return dict(size=(length, 1.0, h + 1.0))


def border_wall(mb, length=20.0, h=6.0, gap=0.12, slat=0.15, seed=0):
    """Steel bollard border wall with concrete footing and top plate."""
    mb.bb(-length / 2, -0.6, 0, length / 2, 0.6, 0.4, BODY)
    n = int(length / (slat + gap))
    for k in range(n):
        x = -length / 2 + (k + 0.5) * length / n
        mb.bb(x - slat / 2, -slat / 2, 0.4, x + slat / 2, slat / 2, h, DARK)
    mb.bb(-length / 2, -0.25, h, length / 2, 0.25, h + 0.6, DARK)
    return dict(size=(length, 1.2, h + 0.6))


def jersey_barrier(mb, length=3.8, m=BODY, loc=(0, 0, 0), rz=0.0):
    prof = [(-0.3, 0), (0.3, 0), (0.3, 0.08), (0.2, 0.33), (0.1, 0.81), (-0.1, 0.81), (-0.2, 0.33), (-0.3, 0.08)]
    with mb.at(loc, rz=rz):
        mb.prism_yz(prof, -length / 2, length / 2, m)


def boom_gate(mb, length=5.5, loc=(0, 0, 0), rz=0.0, open_=False):
    """Boom barrier: pedestal at loc, striped arm along +Y."""
    with mb.at(loc, rz=rz):
        mb.bb(-0.25, -0.25, 0, 0.25, 0.25, 1.05, BODY)
        mb.bb(-0.27, -0.27, 0.9, 0.27, 0.27, 1.1, ACCENT)
        mb.bb(-0.35, -0.5, 0.82, 0.35, -0.25, 1.05, DARK)  # counterweight
        n = 7
        ang = R(80) if open_ else 0.0
        with mb.at((0, 0.2, 0.95), rot=(ang, 0, 0)):
            for k in range(n):
                y0 = length * k / n
                mb.bb(-0.06, y0, -0.06, 0.06, y0 + length / n, 0.06, ACCENT if k % 2 == 0 else BODY)
        if not open_:
            mb.bb(-0.05, length + 0.1, 0, 0.05, length + 0.3, 0.95, BODY)


def checkpoint_booth(mb, seed=0):
    """Guard booth + boom gate + jersey barriers (gate spans a lane toward +Y)."""
    s = 2.4
    with mb.at((0, -1.5, 0)):
        mb.bb(-s / 2 - 0.3, -s / 2 - 0.3, 0, s / 2 + 0.3, s / 2 + 0.3, 0.2, BODY)
        bw = lambda w: [W(0.3, 1.0, w - 0.3, 2.2, "win", mv=1, sill=False, depth=0.08)]
        block(mb, s, s, 2.7, 0.2, {"px": bw, "ny": bw, "nx": bw,
                                   "py": lambda w: [W(0.4, 0, 1.3, 2.1, "door", depth=0.08), W(1.5, 1.0, w - 0.2, 2.2, "win", sill=False, depth=0.08)]},
              depth=0.08)
        mb.bb(-s / 2 - 0.5, -s / 2 - 0.5, 2.9, s / 2 + 0.5, s / 2 + 0.5, 3.15, BODY)
        mb.bb(-s / 2 - 0.52, -s / 2 - 0.52, 2.92, s / 2 + 0.52, s / 2 + 0.52, 3.07, ACCENT)
        mb.cyl(0.18, 0.25, (0, 0, 3.15), LIGHT, n=10)
    boom_gate(mb, 5.0, (1.2, -0.2, 0))
    mb.bb(-10.5, -0.3, -0.3, 6.0, 5.8, 0.0, DARK)  # lane
    for y in (-0.3, 5.8):
        _paint(mb, -10.5, y - 0.06 + (0.1 if y < 0 else -0.1), 6.0, y + 0.06 + (0.1 if y < 0 else -0.1))
    _paint(mb, 0.2, -0.2, 0.6, 5.7)
    for k in range(2):
        jersey_barrier(mb, 3.8, BODY, (-2.2 - k * 4.0, -3.4, 0))
        jersey_barrier(mb, 3.8, BODY, (-2.2 - k * 4.0, 6.0, 0))
    with mb.at((3.0, -3.2, 0)):
        mb.cyl(0.04, 2.4, (0, 0, 0), DARK, n=8)
        mb.cyl(0.4, 0.04, (0.03, 0, 2.2), ACCENT, n=8, rot=(0, R(90), 0))
        mb.text("STOP", 0.2, (0.075, 0, 2.2), BODY, rot=FACE_PX, depth=0.01, font=FONT_BLACK)
    return dict(size=(14, 12, 3.4))


def border_checkpoint(mb, lanes=2, lane_w=4.5, seed=0):
    """Border crossing: canopy over lanes, booths on islands, boom gates, flags, sign."""
    n = lanes
    W_ = n * lane_w + (n + 1) * 2.2
    D_ = 16.0
    mb.bb(-D_ / 2 - 12, -W_ / 2 - 2, -0.3, D_ / 2 + 12, W_ / 2 + 2, 0.0, DARK)
    for k in range(n + 1):
        y = -W_ / 2 + k * (lane_w + 2.2) + 1.1
        mb.bb(-D_ / 2 - 2, y - 1.0, 0, D_ / 2 + 2, y + 1.0, 0.2, BODY)
        mb.prism([(D_ / 2 + 2, y - 1.0), (D_ / 2 + 5, y), (D_ / 2 + 2, y + 1.0)], 0, 0.2, BODY)
        mb.bb(-0.5, y - 0.6, 0, 0.5, y + 0.6, 6.0, BODY)  # canopy column
        if k < n:
            with mb.at((-2.5, y + 0.0, 0.2)):
                bw = lambda w: [W(0.25, 0.9, w - 0.25, 2.1, "win", mv=1, sill=False, depth=0.06)]
                block(mb, 2.2, 1.8, 2.5, 0, {"px": bw, "nx": bw, "py": bw, "ny": bw}, depth=0.06)
                mb.bb(-1.3, -1.1, 2.5, 1.3, 1.1, 2.7, BODY)
            boom_gate(mb, lane_w - 0.6, (D_ / 2 - 1.0, y + 1.0, 0.2))
            # lane arrow
            arrow_2d(mb, (-D_ / 2 - 6, y + 1.1 + lane_w / 2), math.pi, 3.0, 0.35)
    mb.bb(-D_ / 2, -W_ / 2 - 1, 6.0, D_ / 2, W_ / 2 + 1, 7.0, BODY)
    mb.bb(D_ / 2, -W_ / 2 - 1.02, 6.1, D_ / 2 + 0.06, W_ / 2 + 1.02, 6.9, ACCENT)
    mb.bb(-D_ / 2 - 0.06, -W_ / 2 - 1.02, 6.1, -D_ / 2, W_ / 2 + 1.02, 6.9, ACCENT)
    mb.text("BORDER CONTROL", 0.55, (D_ / 2 + 0.061, 0, 6.5), BODY, rot=FACE_PX, depth=0.02, font=FONT_BLACK)
    for s in (-1, 1):
        flagpole(mb, 9.0, (D_ / 2 + 6, s * (W_ / 2 + 1.0), 0), fw=2.4, fh=1.5, seed=seed + s)
    for s in (-1, 1):
        with mb.at((0, s * (W_ / 2 + 7.0), 0), rz=0.0):
            for k in range(3):
                x = -D_ / 2 - 6 + k * 6.6
                with mb.at((x + 3.0, 0, 0)):
                    security_fence(mb, 6.6, 3.0, 3.3, barbed=True)
    return dict(size=(D_ + 24, W_ + 16, 9.5))


# ================================================================== CITY: energy & industry
def _lattice_tower(mb, h, b0, b1, panels, m=DARK, r=0.08, levels=None):
    """4-leg tapered lattice tower; legs from +-b0 at z=0 to +-b1 at z=h; X-bracing."""
    zs = levels or [h * k / panels for k in range(panels + 1)]

    def half(z):
        t = z / h
        return b0 + (b1 - b0) * t
    corners = [(-1, -1), (1, -1), (1, 1), (-1, 1)]
    for (sx, sy) in corners:
        mb.rod((sx * b0, sy * b0, 0), (sx * b1, sy * b1, h), r * 1.6, m, n=4)
    for i in range(len(zs) - 1):
        z0, z1 = zs[i], zs[i + 1]
        a0, a1 = half(z0), half(z1)
        for k in range(4):
            (sx, sy), (tx, ty) = corners[k], corners[(k + 1) % 4]
            p0 = (sx * a0, sy * a0, z0)
            q0 = (tx * a0, ty * a0, z0)
            p1 = (sx * a1, sy * a1, z1)
            q1 = (tx * a1, ty * a1, z1)
            mb.rod(p0, q1, r, m, n=4)
            mb.rod(q0, p1, r, m, n=4)
            mb.rod(p1, q1, r, m, n=4)


def power_pylon(mb, h=42.0, arm=7.0, m=BODY, seed=0):
    """Lattice transmission tower (double circuit, 3 cross-arm levels).  Line runs along X."""
    body_h = h - 6
    b0, b1 = 4.0, 1.1
    _lattice_tower(mb, body_h, b0, b1, 7, m, 0.07)
    for s in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
        mb.bb(s[0] * b0 - 0.5, s[1] * b0 - 0.5, 0, s[0] * b0 + 0.5, s[1] * b0 + 0.5, 0.4, BODY)
    # earth-wire peak
    for (sx, sy) in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
        mb.rod((sx * b1, sy * b1, body_h), (0, 0, h), 0.08, m, n=4)
    ends = []
    for i, zf in enumerate((0.62, 0.78, 0.94)):
        z = body_h * zf
        L = arm * (1.0 if i != 1 else 1.25)
        a = b0 + (b1 - b0) * zf
        for sy in (-1, 1):
            tip = (0, sy * (a + L), z)
            for sx in (-1, 1):
                mb.rod((sx * a, sy * a, z), tip, 0.07, m, n=4)
                mb.rod((sx * a, sy * a, z + 2.0), tip, 0.06, m, n=4)
            mb.cyl(0.18, 2.6, (0, sy * (a + L - 0.2), z - 2.6), DARK, n=8)
            for k in range(6):
                mb.cyl(0.32, 0.08, (0, sy * (a + L - 0.2), z - 2.4 + k * 0.4), DARK, n=10)
            ends.append((0, sy * (a + L - 0.2), z - 2.6))
    return dict(size=(2 * b0 + 1, 2 * (b0 + arm * 1.25), h), ends=ends)


def power_line(mb, pylons=3, spacing=110.0, sag=5.0, seed=0):
    ends_all = []
    for k in range(pylons):
        x = (k - (pylons - 1) / 2) * spacing
        with mb.at((x, 0, 0)):
            info = power_pylon(mb)
        ends_all.append([(x + e[0], e[1], e[2]) for e in info["ends"]])
    prof = [(0.09 * math.cos(a), 0.09 * math.sin(a)) for a in [TAU * j / 6 for j in range(6)]]
    for k in range(pylons - 1):
        for e0, e1 in zip(ends_all[k], ends_all[k + 1]):
            pts = []
            for j in range(25):
                u = j / 24
                pts.append((e0[0] + (e1[0] - e0[0]) * u, e0[1], e0[2] - sag * 4 * u * (1 - u)))
            mb.sweep(pts, prof, DARK)
    return dict(size=(spacing * (pylons - 1) + 10, 30, 42))


def wind_turbine(mb, hub_h=90.0, rotor_r=58.0, blade_angle=0.0, seed=0):
    """Rotor faces +X (rotor plane YZ)."""
    mb.cyl(6.0, 1.0, (0, 0, -0.5), BODY, n=24)  # foundation
    mb.cyl(2.3, hub_h - 2.0, (0, 0, 0), BODY, n=24, r2=1.45)
    with mb.at((0, 0, hub_h)):
        # nacelle
        mb.lathe([(0.0, -7.0), (1.3, -6.9), (1.9, -6.0), (2.0, -1.0), (1.8, 2.5), (1.5, 3.2), (0, 3.3)], BODY, n=20,
                 rot=(0, R(90), 0))
        mb.bb(-1.0, -0.8, -2.2, 1.0, 0.8, -1.4, BODY)
        mb.lathe([(0, 0), (1.5, 0.05), (1.6, 0.8), (1.3, 2.0), (0.7, 3.0), (0, 3.4)], BODY, n=20, rot=(0, R(90), 0),
                 loc=(3.2, 0, 0))
        for b in range(3):
            ang = blade_angle + TAU * b / 3
            with mb.at((4.4, 0, 0), rot=(ang, 0, 0)):
                secs = []
                for k in range(14):
                    t = k / 13
                    r = 1.2 + (rotor_r - 1.2) * t
                    if t < 0.08:
                        c, th = 2.2, 2.2
                    else:
                        c = 4.6 * (1 - t) ** 0.75 + 0.5 if t > 0.18 else 2.2 + (t - 0.08) * 24
                        th = max(0.12, c * (0.42 - 0.3 * t))
                    tw = R(14) * (1 - t)
                    ring = []
                    for j in range(12):
                        a = TAU * j / 12
                        yy = 0.5 * c * math.cos(a) + (0.15 * c if t > 0.1 else 0)
                        xx = 0.5 * th * math.sin(a) * (1.0 if math.sin(a) > 0 else 0.7)
                        ring.append((xx * math.cos(tw) - yy * math.sin(tw), xx * math.sin(tw) + yy * math.cos(tw), r))
                    secs.append(ring)
                mb.loft(secs, BODY)
    return dict(size=(12, 2 * rotor_r, hub_h + rotor_r))


def pumpjack(mb, tilt=8.0, seed=0):
    """Nodding-donkey oil pump, horsehead toward +X."""
    mb.bb(-6.0, -1.0, 0, 4.5, 1.0, 0.4, BODY)            # skid
    mb.bb(3.4, -1.2, 0, 6.2, 1.2, 0.3, BODY)             # wellhead pad
    piv = (0.6, 0, 5.4)
    for sx in (-1, 1):
        for sy in (-1, 1):
            mb.rod((piv[0] + sx * 1.6, sy * 0.9, 0.4), (piv[0], sy * 0.18, piv[2] - 0.3), 0.12, BODY, n=6)
    mb.rod((piv[0] - 2.2, 0, 0.4), (piv[0], 0, piv[2] - 0.3), 0.1, BODY, n=6)
    mb.cyl(0.3, 0.7, (piv[0], -0.35, piv[2]), DARK, n=12, rot=(R(-90), 0, 0))
    t = R(tilt)
    with mb.at(piv, rot=(0, t, 0)):
        mb.bb(-4.2, -0.22, -0.05, 3.6, 0.22, 0.5, BODY)
        # horsehead (arc sector), accent
        pts = [(3.4, 1.2), (3.4, -1.0)]
        for k in range(10):
            a = R(-50 + 100 * k / 9)
            pts.append((3.4 + 1.6 * math.cos(a) * 0.9, 0.2 + 2.0 * math.sin(a)))
        pts = [(3.3, 1.5), (3.3, -1.6)] + [(3.3 + 1.0 * math.cos(a), 2.2 * math.sin(a))
                                            for a in [R(-90 + 180 * k / 12) for k in range(13)]][1:-1] + []
        mb.prism_xz(pts, -0.35, 0.35, ACCENT)
        mb.bb(-4.4, -0.35, -0.3, -3.6, 0.35, 0.6, BODY)  # equaliser
    # bridle + polished rod down to wellhead
    hx = piv[0] + 4.3 * math.cos(t)
    hz = piv[2] - 4.3 * math.sin(t)
    for s in (-1, 1):
        mb.rod((hx + 0.05, s * 0.2, hz), (hx + 0.05, s * 0.2, 2.2), 0.025, DARK, n=4)
    mb.bb(hx - 0.1, -0.3, 2.1, hx + 0.2, 0.3, 2.25, DARK)
    mb.cyl(0.05, 2.0, (hx + 0.05, 0, 0.3), BODY, n=6)
    mb.cyl(0.22, 1.1, (hx + 0.05, 0, 0.3), DARK, n=10)
    mb.cyl(0.32, 0.12, (hx + 0.05, 0, 1.0), DARK, n=10)
    mb.rod((hx + 0.05, 0, 0.7), (hx + 1.2, 0, 0.7), 0.08, DARK, n=6)
    # gearbox, cranks, counterweights, pitman arms
    gx = -3.4
    mb.bb(gx - 0.9, -0.6, 0.4, gx + 0.9, 0.6, 2.2, BODY)
    for s in (-1, 1):
        with mb.at((gx, s * 0.75, 1.7), rot=(0, R(35), 0)):
            mb.bb(-0.2, -0.08, -0.2, 1.8, 0.08, 0.2, BODY)
            mb.prism_xz([(1.2, -0.9), (2.4, -0.6), (2.4, 0.6), (1.2, 0.9)], -0.12, 0.12, DARK)
        cx = gx + 1.8 * math.cos(R(35))
        cz = 1.7 - 1.8 * math.sin(R(35))
        bx = piv[0] - 4.0 * math.cos(t)
        bz = piv[2] + 4.0 * math.sin(t)
        mb.rod((cx, s * 0.92, cz), (bx, s * 0.3, bz), 0.07, BODY, n=6)
    mb.bb(gx - 2.4, -0.5, 0.4, gx - 1.2, 0.5, 1.3, DARK)  # motor
    return dict(size=(12, 2.5, 8))


def oil_derrick(mb, h=42.0, seed=0):
    """Drilling rig: substructure, lattice derrick, crown block, doghouse, catwalk, pipe rack, mud tanks."""
    sub = 8.0
    _lattice_tower(mb, sub, 5.0, 5.0, 2, BODY, 0.12)
    mb.bb(-5.6, -5.6, sub, 5.6, 5.6, sub + 0.5, BODY)  # drill floor
    with mb.at((0, 0, sub + 0.5)):
        _lattice_tower(mb, h - sub, 3.6, 1.0, 9, BODY, 0.09)
        z = h - sub
        mb.bb(-1.5, -1.5, z, 1.5, 1.5, z + 1.6, BODY)  # crown block
        mb.bb(-1.8, -1.8, z * 0.55, 2.8, 1.8, z * 0.55 + 0.2, BODY)  # monkey board
        mb.cyl(0.6, 2.0, (0, 0, z * 0.7), DARK, n=10)  # travelling block
        mb.rod((0, 0, z * 0.7 + 2.0), (0, 0, z), 0.04, DARK, n=4)
        mb.cyl(0.15, 6.0, (0, 0, 0.0), DARK, n=8)  # kelly / pipe
        with mb.at((-3.4, 3.0, 0)):
            block(mb, 3.6, 2.6, 2.8, 0, {"px": lambda w: [W(0.4, 1.0, w - 0.4, 2.0, "win", mv=1, sill=False, depth=0.06)],
                                         "ny": lambda w: [W(0.4, 0, 1.3, 2.1, "door", depth=0.06)]}, depth=0.06)
    # V-door catwalk ramp toward +X
    mb.add([(5.6, -0.8, sub + 0.5), (5.6, 0.8, sub + 0.5), (20, 0.8, 1.2), (20, -0.8, 1.2),
            (5.6, -0.8, sub + 0.2), (5.6, 0.8, sub + 0.2), (20, 0.8, 0.9), (20, -0.8, 0.9)],
           [(3, 2, 1, 0), (4, 5, 6, 7), (0, 3, 7, 4), (1, 2, 6, 5), (0, 1, 5, 4), (3, 7, 6, 2)], BODY)
    mb.bb(20, -2.0, 0, 30, 2.0, 1.2, BODY)  # catwalk / pipe deck
    for k in range(6):
        mb.cyl(0.2, 9.0, (21 + 0.0, -1.5 + k * 0.6, 1.4), DARK, n=8, rot=(0, R(90), 0))
    for k in range(3):  # mud tanks
        mb.bb(-6.0, -10.5 - k * 4.2, 0, 6.0, -7.0 - k * 4.2, 3.0, BODY)
    mb.bb(-12, -4, 0, -7, 4, 3.2, BODY)  # engines / generators
    for k in range(3):
        mb.cyl(0.25, 1.8, (-9.5 + k * 1.2, 3.0, 3.2), DARK, n=8)
    return dict(size=(36, 22, h + 2))


def refinery_tank(mb, r=16.0, h=14.0, bund=True, seed=0):
    """Large cylindrical storage tank with spiral stair, wind girder, roof, bund wall."""
    mb.cyl(r + 0.6, 0.4, (0, 0, 0), BODY, n=64)
    mb.cyl(r, h, (0, 0, 0.4), BODY, n=64)
    for z in range(3, int(h), 3):
        mb.cyl(r + 0.06, 0.1, (0, 0, 0.4 + z), BODY, n=64)
    mb.ring(r, r + 0.9, h + 0.1, h + 0.3, BODY, n=64)  # wind girder / walkway
    mb.lathe([(r + 0.05, h + 0.4), (r * 0.6, h + 0.4 + r * 0.06), (0.8, h + 0.4 + r * 0.1), (0, h + 0.4 + r * 0.1)],
             BODY, n=64)
    # handrail on the girder
    mb.ring(r + 0.8, r + 0.86, h + 1.3, h + 1.38, DARK, n=64)
    # spiral stair: ribbon + rail around 120 degrees
    n = 30
    a0, a1 = R(-80), R(40)
    steps = [((r + 0.55) * math.cos(a0 + (a1 - a0) * k / n), (r + 0.55) * math.sin(a0 + (a1 - a0) * k / n),
              0.4 + (h - 0.0) * k / n) for k in range(n + 1)]
    mb.sweep(steps, [(-0.5, -0.1), (0.5, -0.1), (0.5, 0.05), (-0.5, 0.05)], DARK)
    rail = [((r + 1.05) * math.cos(a0 + (a1 - a0) * k / n), (r + 1.05) * math.sin(a0 + (a1 - a0) * k / n),
             0.4 + h * k / n + 1.0) for k in range(n + 1)]
    mb.sweep(rail, [(-0.04, -0.04), (0.04, -0.04), (0.04, 0.04), (-0.04, 0.04)], DARK)
    for k in range(0, n + 1, 3):
        p = rail[k]
        mb.rod((p[0], p[1], p[2] - 1.0), p, 0.03, DARK, n=4)
    # nozzles / pipes
    for k in range(2):
        a = R(200 + k * 25)
        mb.rod(((r - 0.1) * math.cos(a), (r - 0.1) * math.sin(a), 1.2), ((r + 4) * math.cos(a), (r + 4) * math.sin(a), 1.2),
               0.35, DARK, n=10)
    if bund:
        b = r + 6
        for (x0, y0, x1, y1) in ((-b, -b, b, -b + 0.5), (-b, b - 0.5, b, b), (-b, -b, -b + 0.5, b), (b - 0.5, -b, b, b)):
            mb.bb(x0, y0, 0, x1, y1, 1.4, BODY)
    return dict(size=(2 * r + 12, 2 * r + 12, h + 2.5))


def storage_spheres(mb, n=2, r=8.0, seed=0):
    """LPG storage spheres on legs."""
    for k in range(n):
        x = (k - (n - 1) / 2) * (2 * r + 6)
        zc = r + 3.0
        mb.sphere(r, (x, 0, zc), BODY, seg=32, rings=16)
        mb.torus(r * 1.0, 0.25, (x, 0, zc), BODY, n=48, nr=6)
        nl = 8
        for j in range(nl):
            a = TAU * (j + 0.5) / nl
            px, py = x + r * 0.98 * math.cos(a), r * 0.98 * math.sin(a)
            mb.cyl(0.35, zc, (px, py, 0), BODY, n=8)
            mb.bb(px - 0.6, py - 0.6, 0, px + 0.6, py + 0.6, 0.3, BODY)
        # stair to top
        pts = [(x + (r + 1.2) * math.cos(a), (r + 1.2) * math.sin(a), 0.2 + (zc + r * 0.7) * (a - R(-100)) / R(150))
               for a in [R(-100 + 150 * j / 20) for j in range(21)]]
        mb.sweep(pts, [(-0.45, -0.1), (0.45, -0.1), (0.45, 0.05), (-0.45, 0.05)], DARK)
        mb.cyl(1.4, 0.4, (x, 0, zc + r - 0.2), BODY, n=16)
    return dict(size=(n * (2 * r + 6), 2 * r + 4, 2 * r + 4))


def refinery_unit(mb, seed=0):
    """Distillation columns with platforms + pipe rack + furnace + flare stack (LIB_Fire flame)."""
    from genkit import FIRE
    cols = [(0.0, 0.0, 2.6, 46.0), (9.0, 2.0, 1.8, 34.0), (-8.0, -1.0, 1.5, 26.0)]
    for (x, y, r, h) in cols:
        mb.cyl(r + 0.4, 3.0, (x, y, 0), BODY, n=24, r2=r)
        mb.cyl(r, h - 3.0, (x, y, 3.0), BODY, n=24)
        mb.sphere(r, (x, y, h), BODY, seg=24, rings=6, zmin=0.0)
        for z in range(8, int(h), 8):
            mb.ring(r, r + 1.2, z, z + 0.15, DARK, n=24)
            mb.ring(r + 1.12, r + 1.2, z + 1.0, z + 1.08, DARK, n=24)
        mb.bb(x + r, y - 0.35, 3, x + r + 0.08, y + 0.35, h, DARK)  # ladder
        mb.rod((x, y, h + r * 0.6), (x, y - 12, h * 0.6), 0.35, BODY, n=8)
    # pipe rack along Y at x=-2..2, y from -14 to -40
    for k in range(6):
        y = -12 - k * 6
        for s in (-1, 1):
            mb.bb(s * 3 - 0.2, y - 0.2, 0, s * 3 + 0.2, y + 0.2, 7.0, BODY)
        mb.bb(-3.4, y - 0.25, 6.8, 3.4, y + 0.25, 7.2, BODY)
        mb.bb(-3.4, y - 0.25, 4.3, 3.4, y + 0.25, 4.6, BODY)
    for j in range(7):
        x = -2.8 + j * 0.9
        mb.cyl(0.3 if j % 2 else 0.22, 32.0, (x, -10.0, 7.5), BODY if j % 3 else DARK, n=10, rot=(R(90), 0, 0))
        mb.cyl(0.25, 32.0, (x, -10.0, 5.0), BODY, n=10, rot=(R(90), 0, 0))
    # furnace box
    mb.bb(-18, -16, 0, -8, -6, 10, BODY)
    mb.cyl(1.0, 14, (-13, -11, 10), BODY, n=12)
    # flare stack
    fx, fy = 18.0, -24.0
    mb.cyl(1.4, 2.0, (fx, fy, 0), BODY, n=12)
    mb.cyl(0.6, 60, (fx, fy, 0), BODY, n=12, r2=0.45)
    for z in (20, 40):
        for k in range(3):
            a = TAU * k / 3
            mb.rod((fx, fy, z), (fx + 12 * math.cos(a), fy + 12 * math.sin(a), 0), 0.04, DARK, n=4)
    mb.blob([((fx, fy, 61.5), 1.2), ((fx + 0.4, fy, 63.0), 0.9), ((fx + 0.9, fy, 64.3), 0.55)], FIRE, voxel=0.12,
            noise=0.25, noise_scale=0.8, smooth=2, seed=seed)
    return dict(size=(40, 44, 66))
