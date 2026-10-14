"""fx_lib: stylised FX for the white-model style (frozen explosion stages, smoke, fire, map graphics).

Billows are unions of spheres -> voxel remesh -> noise displace -> smooth (genkit.MB.blob), so they read
as sculpted white clouds.  Fire cores use LIB_Fire (warm emissive, added to the house palette for FX);
swap to LIB_Accent if you want a non-emissive faction-coloured blast.
Origin: ground centre.  Map graphics lie on the ground (z ~ 0) and are display sized.
"""
import math
import random

from mathutils import Vector

from genkit import ACCENT, BODY, DARK, FACE_PX, FIRE, FONT_BLACK, FONT_BOLD, GLASS, LIGHT, MB, TAU

R = math.radians


def _puffs(rnd, center, radius, n, spread=1.0, flat=1.0, rmin=0.35, rmax=0.65, zbias=0.0):
    cx, cy, cz = center
    out = [((cx, cy, cz), radius * 0.75)]
    for k in range(n):
        a = rnd.uniform(0, TAU)
        e = rnd.uniform(-0.4, 1.0) + zbias
        d = radius * spread * rnd.uniform(0.45, 0.85)
        out.append(((cx + d * math.cos(a) * math.cos(e), cy + d * math.sin(a) * math.cos(e),
                     cz + d * math.sin(e) * flat), radius * rnd.uniform(rmin, rmax)))
    return out


def debris(mb, n=20, radius=6.0, height=4.0, size=0.4, seed=0, m=DARK, airborne=True):
    """Flying (or fallen) chunks."""
    rnd = random.Random(seed)
    for k in range(n):
        a = rnd.uniform(0, TAU)
        rr = radius * rnd.uniform(0.3, 1.0)
        z = rnd.uniform(0.5, height) if airborne else 0.0
        s = size * rnd.uniform(0.4, 1.0)
        mb.box((s, s * rnd.uniform(0.5, 1), s * rnd.uniform(0.3, 0.8)),
               (rr * math.cos(a), rr * math.sin(a), z + s * 0.3), m,
               rot=(rnd.uniform(0, 3), rnd.uniform(0, 3), rnd.uniform(0, 3)))
        if airborne and rnd.random() < 0.6:  # short smoke trail behind the chunk
            d = Vector((math.cos(a), math.sin(a), 0.6)).normalized()
            p = Vector((rr * math.cos(a), rr * math.sin(a), z + s * 0.3))
            mb.rod(tuple(p - d * s * 0.6), tuple(p - d * s * 4.0), s * 0.25, BODY, n=6, r2=s * 0.05)


def explosion(mb, stage="fireball", size=10.0, seed=0):
    """Frozen explosion.  stage: ignition | fireball | billow | dissipating.  size ~ fireball diameter (m)."""
    rnd = random.Random(seed)
    s = size
    if stage == "ignition":
        core = _puffs(rnd, (0, 0, s * 0.18), s * 0.2, 7, rmin=0.4, rmax=0.7)
        mb.blob(core, FIRE, voxel=s / 60, noise=s * 0.03, noise_scale=s * 0.08, smooth=3, seed=seed, squash_bottom=0.0)
        # flash spikes
        for k in range(10):
            a, e = rnd.uniform(0, TAU), rnd.uniform(0.05, 1.2)
            d = Vector((math.cos(a) * math.cos(e), math.sin(a) * math.cos(e), math.sin(e)))
            p0 = Vector((0, 0, s * 0.18))
            mb.rod(tuple(p0), tuple(p0 + d * s * rnd.uniform(0.4, 0.75)), s * 0.035, FIRE, n=6, r2=0.0)
        mb.blob(_puffs(rnd, (0, 0, 0.0), s * 0.25, 10, flat=0.25, spread=1.6), BODY, voxel=s / 70, noise=s * 0.02,
                noise_scale=s * 0.06, smooth=3, seed=seed + 1, squash_bottom=0.0)
        debris(mb, 10, s * 0.5, s * 0.5, s * 0.03, seed)
    elif stage == "fireball":
        core = _puffs(rnd, (0, 0, s * 0.42), s * 0.42, 12, rmin=0.4, rmax=0.65)
        mb.blob(core, FIRE, voxel=s / 55, noise=s * 0.045, noise_scale=s * 0.09, smooth=3, seed=seed, squash_bottom=0.0)
        # smoke starting to wrap the top / sides
        cap = []
        for k in range(9):
            a = TAU * k / 9 + rnd.uniform(-0.2, 0.2)
            e = rnd.uniform(0.3, 1.1)
            d = s * 0.46
            cap.append(((d * math.cos(a) * math.cos(e), d * math.sin(a) * math.cos(e), s * 0.42 + d * math.sin(e)),
                        s * rnd.uniform(0.16, 0.24)))
        mb.blob(cap, BODY, voxel=s / 60, noise=s * 0.035, noise_scale=s * 0.07, smooth=3, seed=seed + 2)
        mb.blob(_puffs(rnd, (0, 0, 0), s * 0.35, 14, flat=0.2, spread=2.0), BODY, voxel=s / 60, noise=s * 0.03,
                noise_scale=s * 0.08, smooth=3, seed=seed + 3, squash_bottom=0.0)
        debris(mb, 18, s * 0.9, s * 0.9, s * 0.035, seed)
    elif stage == "billow":
        # mushroom: stem column + big cap, fire glowing low inside
        stem = [((rnd.uniform(-0.05, 0.05) * s, rnd.uniform(-0.05, 0.05) * s, s * (0.1 + 0.12 * k)), s * (0.2 - 0.012 * k))
                for k in range(8)]
        capc = (0, 0, s * 1.15)
        cap = _puffs(rnd, capc, s * 0.5, 16, flat=0.55, spread=1.2, rmin=0.35, rmax=0.55)
        mb.blob(stem + cap, BODY, voxel=s / 55, noise=s * 0.05, noise_scale=s * 0.09, smooth=3, seed=seed)
        mb.blob(_puffs(rnd, (0, 0, s * 0.12), s * 0.2, 6), FIRE, voxel=s / 60, noise=s * 0.03, noise_scale=s * 0.07,
                smooth=2, seed=seed + 5, squash_bottom=0.0)
        mb.blob(_puffs(rnd, (0, 0, 0), s * 0.45, 16, flat=0.18, spread=2.2), BODY, voxel=s / 55, noise=s * 0.03,
                noise_scale=s * 0.08, smooth=3, seed=seed + 4, squash_bottom=0.0)
        debris(mb, 14, s * 1.2, s * 0.15, s * 0.04, seed, airborne=False)
    else:  # dissipating
        pts = []
        for k in range(18):
            z = s * rnd.uniform(0.3, 1.7)
            a = rnd.uniform(0, TAU)
            d = s * rnd.uniform(0.0, 0.7) * (0.5 + z / (2 * s))
            pts.append(((d * math.cos(a) + z * 0.25, d * math.sin(a), z), s * rnd.uniform(0.12, 0.25)))
        mb.blob(pts, BODY, voxel=s / 50, noise=s * 0.06, noise_scale=s * 0.08, smooth=4, seed=seed)
        mb.blob(_puffs(rnd, (0, 0, 0), s * 0.5, 14, flat=0.15, spread=2.4, rmin=0.25, rmax=0.5), BODY, voxel=s / 50,
                noise=s * 0.03, noise_scale=s * 0.1, smooth=3, seed=seed + 1, squash_bottom=0.0)
        scorch(mb, s * 0.9, seed)
        debris(mb, 18, s * 1.0, s * 0.1, s * 0.04, seed, airborne=False)


def smoke_column(mb, height=40.0, base_r=2.5, lean=0.35, fire=True, seed=0):
    """Rising plume that widens and drifts toward +X (lean = drift per metre of height)."""
    rnd = random.Random(seed)
    pts = []
    n = 16
    for k in range(n):
        t = k / (n - 1)
        z = height * t
        r = base_r * (1 + 2.2 * t)
        x = lean * z * t
        for j in range(2):
            pts.append(((x + rnd.uniform(-0.3, 0.3) * r, rnd.uniform(-0.3, 0.3) * r, z + r * 0.4), r * rnd.uniform(0.6, 0.85)))
    mb.blob(pts, BODY, voxel=height / 90, noise=base_r * 0.35, noise_scale=base_r * 0.9, smooth=3, seed=seed,
            squash_bottom=0.0)
    if fire:
        fire_patch(mb, base_r * 1.2, base_r * 1.6, seed=seed)


def dust_cloud(mb, radius=12.0, height=4.0, seed=0):
    rnd = random.Random(seed)
    pts = []
    for k in range(26):
        a = rnd.uniform(0, TAU)
        d = radius * math.sqrt(rnd.random()) * 0.8
        r = height * rnd.uniform(0.35, 0.7) * (1.2 - d / radius * 0.6)
        pts.append(((d * math.cos(a), d * math.sin(a), r * 0.5), r))
    mb.blob(pts, BODY, voxel=radius / 70, noise=height * 0.12, noise_scale=height * 0.4, smooth=4, seed=seed,
            squash_bottom=0.0)


def flame(mb, h=2.0, r=0.5, loc=(0, 0, 0), lean=0.0, seed=0, m=FIRE):
    """Single teardrop flame tongue."""
    x, y, z = loc
    sph = []
    n = 18
    for k in range(n):
        t = k / (n - 1)
        sph.append(((x + lean * t * t * h, y, z + r * 0.5 + t * (h - r * 1.5)), r * (1 - 0.75 * t ** 0.8)))
    return sph


def fire_patch(mb, radius=2.0, height=4.0, n=9, seed=0, smoke=False):
    """Cluster of flame tongues (LIB_Fire)."""
    rnd = random.Random(seed)
    sph = []
    for k in range(n):
        a = rnd.uniform(0, TAU)
        d = radius * math.sqrt(rnd.random()) * 0.7
        h = height * rnd.uniform(0.5, 1.0) * (1.1 - d / radius * 0.5)
        sph += flame(mb, h, radius * rnd.uniform(0.18, 0.3), (d * math.cos(a), d * math.sin(a), 0),
                     lean=rnd.uniform(0, 0.3), seed=seed + k)
    mb.blob(sph, FIRE, voxel=max(radius, height) / 60, noise=radius * 0.05, noise_scale=radius * 0.3, smooth=2,
            seed=seed, squash_bottom=0.0)
    if smoke:
        smoke_column(mb, height * 6, radius * 0.9, 0.25, fire=False, seed=seed + 9)


def building_on_fire(mb, w=12.0, d=10.0, h=12.0, seed=0):
    """Damaged block with flames from windows/roof and a smoke plume."""
    import arch_lib as A
    rnd = random.Random(seed)
    fn = lambda wd: A.floors(wd, 3, h / 3, 0, 0.9, 1.6, ww=1.4, bay=3.0, margin=1.0, mv=0)
    A.block(mb, d, w, h, 0, {"px": fn, "ny": fn, "py": fn, "nx": fn}, cap=False)
    # broken roof slab (only part remains) + collapsed corner rubble
    mb.bb(-d / 2, -w / 2, h - 0.3, d / 2, 0.0, h, BODY)
    mb.add([(-d / 2, 0, h - 0.3), (d / 2, 0, h - 0.3), (d / 2, w * 0.25, h - 1.8), (-d / 2, w * 0.3, h - 2.5)],
           [(0, 1, 2, 3), (3, 2, 1, 0)], DARK)
    rubble(mb, 5.0, 2.0, seed=seed, loc=(d * 0.2, w * 0.55, 0))
    # flames from some windows on +X and -Y, roof fire
    for k in range(4):
        side = k % 2
        u = rnd.uniform(0.2, 0.8)
        fz = h / 3 * rnd.randint(1, 2) + 1.0
        if side == 0:
            loc = (d / 2 + 0.3, -w / 2 + u * w, fz)
        else:
            loc = (-d / 2 + u * d, -w / 2 - 0.3, fz)
        sph = flame(mb, 2.4, 0.6, loc, lean=0.3, seed=seed + k)
        mb.blob(sph, FIRE, voxel=0.08, noise=0.08, noise_scale=0.5, smooth=2, seed=seed + k)
        # scorch above window
        if side == 0:
            mb.bb(d / 2 - 0.0, loc[1] - 0.8, fz + 1.7, d / 2 + 0.01, loc[1] + 0.8, fz + 2.6, DARK)
        else:
            mb.bb(loc[0] - 0.8, -w / 2 - 0.01, fz + 1.7, loc[0] + 0.8, -w / 2, fz + 2.6, DARK)
    with mb.at((0, w * 0.15, h - 2.0)):
        fire_patch(mb, 3.5, 5.0, n=8, seed=seed)
        smoke_column(mb, 45.0, 3.0, 0.4, fire=False, seed=seed + 3)


def muzzle_flash(mb, length=0.8, petals=4, seed=0):
    """Star-shaped flash pointing +X; origin = muzzle point (not ground)."""
    rnd = random.Random(seed)
    mb.rod((0, 0, 0), (length * 0.75, 0, 0), length * 0.16, FIRE, n=12, r2=0.0)
    mb.sphere(length * 0.12, (length * 0.06, 0, 0), FIRE, seg=12, rings=6, scale=(1.4, 1, 1))
    for k in range(petals):
        a = TAU * k / petals + R(45)
        d = Vector((0.7, math.cos(a), math.sin(a))).normalized()
        mb.rod((length * 0.04, 0, 0), tuple(d * length * 0.42), length * 0.07, FIRE, n=8, r2=0.0)
    for k in range(petals):  # small side-port jets
        a = TAU * k / petals
        d = Vector((0.15, math.cos(a), math.sin(a))).normalized()
        mb.rod((0, 0, 0), tuple(d * length * 0.22), length * 0.035, FIRE, n=6, r2=0.0)


def rubble(mb, radius=6.0, height=2.5, n=None, seed=0, loc=(0, 0, 0)):
    """Rubble/debris pile: mound core + broken slabs, blocks and rebar."""
    rnd = random.Random(seed)
    x0, y0, z0 = loc
    n = n or int(radius * 9)
    core = [((x0 + rnd.uniform(-0.4, 0.4) * radius, y0 + rnd.uniform(-0.4, 0.4) * radius, z0), radius * rnd.uniform(0.35, 0.55))
            for k in range(6)]
    mb.blob(core, BODY, voxel=radius / 30, noise=radius * 0.08, noise_scale=radius * 0.25, smooth=2, seed=seed,
            squash_bottom=z0)
    # scale mound height: handled by sphere radii; chunks on top
    for k in range(n):
        a = rnd.uniform(0, TAU)
        d = radius * math.sqrt(rnd.random()) * 0.95
        zz = z0 + max(0.0, height * (1 - (d / radius) ** 2)) * rnd.uniform(0.5, 1.0)
        s = radius * rnd.uniform(0.06, 0.18)
        if rnd.random() < 0.3:  # slab
            mb.box((s * 2.5, s * 1.6, s * 0.3), (x0 + d * math.cos(a), y0 + d * math.sin(a), zz), BODY,
                   rot=(rnd.uniform(-0.8, 0.8), rnd.uniform(-0.8, 0.8), rnd.uniform(0, 3)))
        else:
            mb.box((s, s * rnd.uniform(0.6, 1.2), s * rnd.uniform(0.5, 1)), (x0 + d * math.cos(a), y0 + d * math.sin(a), zz),
                   BODY if rnd.random() < 0.75 else DARK, rot=(rnd.uniform(0, 3), rnd.uniform(0, 3), rnd.uniform(0, 3)))
    for k in range(int(n / 6)):
        a = rnd.uniform(0, TAU)
        d = radius * rnd.uniform(0.0, 0.6)
        p = Vector((x0 + d * math.cos(a), y0 + d * math.sin(a), z0 + height * 0.5))
        q = p + Vector((rnd.uniform(-1, 1), rnd.uniform(-1, 1), rnd.uniform(0.3, 1.0))).normalized() * radius * 0.35
        mb.rod(tuple(p), tuple(q), 0.03, DARK, n=4)


def scorch(mb, radius=4.0, seed=0, z=0.004, m=DARK):
    """Irregular flat scorch splat with radial streaks."""
    rnd = random.Random(seed)
    n = 40
    pts = []
    for k in range(n):
        a = TAU * k / n
        r = radius * (0.7 + 0.12 * math.sin(3 * a + seed) + 0.08 * math.sin(7 * a + 2 * seed) + 0.1 * rnd.random())
        if rnd.random() < 0.18:
            r *= rnd.uniform(1.15, 1.45)
        pts.append((r * math.cos(a), r * math.sin(a)))
    mb.prism(pts, 0.0, z, m)


def crater(mb, radius=5.0, depth=1.8, seed=0):
    """Impact crater built ABOVE ground: raised ejecta rim, dark scorched bowl floor at z~0 (no ground cut needed)."""
    rnd = random.Random(seed)
    rim = depth * 0.7
    prof = [(0.0, 0.02), (radius * 0.5, 0.05), (radius * 0.72, rim * 0.45), (radius * 0.9, rim * 0.95), (radius, rim),
            (radius * 1.12, rim * 0.8), (radius * 1.4, rim * 0.3), (radius * 1.75, 0.0)]
    mb.lathe(prof, BODY, n=48)
    mb.cyl(radius * 0.62, 0.06, (0, 0, 0.0), DARK, n=40)
    scorch(mb, radius * 0.75, seed, z=0.07)
    for k in range(int(radius * 6)):
        a = rnd.uniform(0, TAU)
        d = radius * rnd.uniform(1.0, 2.4)
        s = radius * rnd.uniform(0.03, 0.09)
        mb.box((s, s, s * 0.7), (d * math.cos(a), d * math.sin(a), s * 0.25 + (rim * 0.5 if d < radius * 1.4 else 0)),
               BODY if rnd.random() < 0.7 else DARK, rot=(rnd.uniform(0, 3), rnd.uniform(0, 3), rnd.uniform(0, 3)))


def impact_marks(mb, n=6, area=6.0, seed=0):
    """Scatter of small scorch splats / bullet strikes on the ground."""
    rnd = random.Random(seed)
    for k in range(n):
        x, y = rnd.uniform(-area / 2, area / 2), rnd.uniform(-area / 2, area / 2)
        with mb.at((x, y, 0)):
            scorch(mb, rnd.uniform(0.25, 0.8), seed + k)
            mb.lathe([(0.0, 0.0), (0.05, 0.004), (0.09, 0.03), (0.13, 0.012), (0.17, 0.004)], DARK, n=12)


def tracer(mb, length=6.0, r=0.06, n=1, spread=1.5, seed=0):
    """Tracer round(s) flying +X: bright capsule head + tapering glow trail (LIB_Fire)."""
    rnd = random.Random(seed)
    for k in range(n):
        y, z = (rnd.uniform(-spread, spread), rnd.uniform(-spread * 0.3, spread * 0.3)) if n > 1 else (0, 0)
        x0 = rnd.uniform(-2, 2) if n > 1 else 0
        mb.rod((x0 - length / 2, y, 1.5 + z), (x0 + length / 2 - r * 3, y, 1.5 + z), r * 0.3, FIRE, n=8, r2=r)
        mb.rod((x0 + length / 2 - r * 3, y, 1.5 + z), (x0 + length / 2, y, 1.5 + z), r, FIRE, n=8, r2=r * 0.3)


# ================================================================== map graphics
def map_arrow(mb, path=((0, 0), (12, 4), (24, 2)), width=1.6, height=0.4, head=3.2, m=ACCENT, taper=0.6):
    """Thick 3D campaign arrow on the ground following a 2D path (smoothed), head at the end."""
    pts = [Vector((p[0], p[1], 0)) for p in path]
    sm = []
    n = len(pts)
    for k in range(n - 1):
        p0, p1, p2, p3 = pts[max(k - 1, 0)], pts[k], pts[k + 1], pts[min(k + 2, n - 1)]
        for s in range(10):
            t = s / 10
            sm.append(0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t * t +
                             (-p0 + 3 * p1 - 3 * p2 + p3) * t ** 3))
    sm.append(pts[-1])
    # cut back the body by head length
    L = 0
    lens = [0]
    for k in range(1, len(sm)):
        L += (sm[k] - sm[k - 1]).length
        lens.append(L)
    body = [p for p, l in zip(sm, lens) if l <= L - head * 0.9]
    tip_dir = (sm[-1] - body[-1]).normalized()
    scales = [taper + (1 - taper) * (l / (L - head)) for l in lens[:len(body)]]
    mb.sweep([tuple(p) for p in body], [(-width / 2, 0), (width / 2, 0), (width / 2, height), (-width / 2, height)], m,
             scales=None)
    base = body[-1]
    side = Vector((-tip_dir.y, tip_dir.x, 0))
    hw = width * 1.25
    tri = [base + side * hw, base + tip_dir * head, base - side * hw]
    mb.prism([(p.x, p.y) for p in tri], 0, height, m)


def territory_line(mb, pts=((-20, -12), (8, -16), (22, 0), (10, 16), (-14, 14), (-24, 0)), closed=True, w=0.5,
                   h=0.15, dash=2.5, gap=1.5, m=ACCENT, fill=False):
    """Dashed territory/boundary line (raised ribbon) along a polygon; fill=True adds a thin tint plate."""
    P = [Vector((x, y, 0)) for x, y in pts]
    segs = list(zip(P, P[1:] + ([P[0]] if closed else [])))
    carry = 0.0
    for a, b in segs:
        d = b - a
        L = d.length
        u = d / L
        t = carry
        while t < L:
            e = min(L, t + dash)
            p, q = a + u * t, a + u * e
            with mb.at((p.x, p.y, 0), rz=math.atan2(u.y, u.x)):
                mb.bb(0, -w / 2, 0, (q - p).length, w / 2, h, m)
            t += dash + gap
        carry = t - L
    if fill:
        mb.prism([(p.x, p.y) for p in P], 0, 0.01, LIGHT)


def range_ring(mb, radius=20.0, w=0.4, h=0.12, ticks=36, inner=True, m=ACCENT):
    """Weapon/range ring: solid outer ring with tick marks + dashed inner ring + centre."""
    mb.ring(radius - w / 2, radius + w / 2, 0, h, m, n=128)
    for k in range(ticks):
        a = TAU * k / ticks
        L = w * (4 if k % 9 == 0 else 2)
        with mb.at((0, 0, 0), rz=a):
            mb.bb(radius - w / 2 - L, -w * 0.25, 0, radius - w / 2, w * 0.25, h, m)
    if inner:
        nd = 48
        for k in range(nd):
            if k % 2:
                continue
            with mb.at(rz=TAU * k / nd):
                mb.ring(radius * 0.5 - w * 0.3, radius * 0.5 + w * 0.3, 0, h * 0.8, m, n=4, arc=TAU / nd)
    mb.cyl(w * 1.5, h * 1.5, (0, 0, 0), m, n=24)


def radar_circle(mb, radius=20.0, rings=4, sweep_deg=40.0, m=ACCENT):
    """Radar scope on the ground: concentric rings, crosshair, filled sweep wedge."""
    for k in range(1, rings + 1):
        r = radius * k / rings
        mb.ring(r - 0.12, r + 0.12, 0, 0.08, m if k == rings else BODY, n=96)
    for a in (0, math.pi / 2):
        with mb.at(rz=a):
            mb.bb(-radius, -0.06, 0, radius, 0.06, 0.06, BODY)
    sw = R(sweep_deg)
    nseg = 16
    pts = [(0, 0)] + [(radius * math.cos(sw * k / nseg), radius * math.sin(sw * k / nseg)) for k in range(nseg + 1)]
    mb.prism(pts, 0, 0.05, m)
    mb.bb(0, -0.15, 0, radius, 0.15, 0.12, m)  # leading edge
    mb.cyl(0.6, 0.15, (0, 0, 0), m, n=24)
    for (x, y) in ((radius * 0.55, radius * 0.3), (-radius * 0.4, radius * 0.6), (-radius * 0.2, -radius * 0.7)):
        mb.cyl(0.5, 0.15, (x, y, 0), DARK, n=16)  # blips


def pin_marker(mb, h=3.0, m=ACCENT, shadow=True):
    """Map pin standing on its tip (inverted teardrop with white dot), facing +X."""
    r = h * 0.3
    zc = h - r
    prof = [(0.0, 0.0)]
    for k in range(1, 10):
        t = k / 10
        prof.append((r * math.sin(t * math.pi * 0.5) ** 1.6 * 0.95 * t ** 0.3, t * (zc - r * 0.2)))
    for k in range(0, 13):
        a = R(-60 + 150 * k / 12)
        prof.append((r * math.cos(a), zc + r * math.sin(a)))
    prof.append((0.0, h))
    mb.lathe(prof, m, n=32)
    with mb.at((0, 0, zc), rot=(0, R(90), 0)):
        mb.cyl(r * 0.42, r * 0.2, (0, 0, r * 0.84), BODY, n=24)
    if shadow:
        mb.cyl(r * 0.6, 0.02, (0, 0, 0), DARK, n=24)


def label_board(mb, text="LABEL", sub="", w=None, h=1.0, z=4.0, stem=True, m=BODY, accent=True):
    """Floating sign board (readable from +X) on a thin stem, accent stripe on the left."""
    w = w or max(2.0, len(text) * h * 0.62 + 0.8)
    t = 0.12
    with mb.at((0, 0, z)):
        mb.bb(-t / 2, -w / 2, -h / 2, t / 2, w / 2, h / 2, m)
        if accent:
            mb.bb(t / 2 - 0.01, -w / 2, -h / 2, t / 2 + 0.01, -w / 2 + 0.22, h / 2, ACCENT)
        mb.text(text, h * (0.5 if not sub else 0.42), (t / 2 + 0.001, 0.11, h * (0.0 if not sub else 0.12)), DARK,
                rot=FACE_PX, depth=0.02, font=FONT_BLACK)
        if sub:
            mb.text(sub, h * 0.22, (t / 2 + 0.001, 0.11, -h * 0.25), DARK, rot=FACE_PX, depth=0.02, font=FONT_BOLD)
    if stem:
        mb.cyl(0.03, z - h / 2, (0, 0, 0), DARK, n=8)
        mb.cyl(0.25, 0.03, (0, 0, 0), DARK, n=16)
