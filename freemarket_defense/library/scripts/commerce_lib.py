"""commerce_lib: parameterised procedural MONEY / TRADE / OFFICE props (white-model style).

Generators draw into a genkit.MB in local space: metres, Z up, origin ground centre, front faces +X.
Real-world sizes (a coin is 26.5 mm) - scale the instance in the scene for hero shots, or use the
`*_icon` generators which are already display-sized.
"""
import math
import random

from mathutils import Vector

from genkit import ACCENT, BODY, DARK, FACE_PX, FACE_NY, FONT_BLACK, FONT_BOLD, FONT_SEMI, GLASS, LIGHT, METAL, MB, TAU

R = math.radians


def rrect(w, h, r, n=4, cx=0.0, cy=0.0):
    """Rounded rectangle (XY) points, CCW."""
    r = min(r, w / 2 - 1e-4, h / 2 - 1e-4)
    pts = []
    for (sx, sy, a0) in ((1, 1, 0), (-1, 1, 90), (-1, -1, 180), (1, -1, 270)):
        c = (cx + sx * (w / 2 - r), cy + sy * (h / 2 - r))
        for k in range(n + 1):
            a = R(a0 + 90 * k / n)
            pts.append((c[0] + r * math.cos(a), c[1] + r * math.sin(a)))
    return pts


def rbox(mb, w, d, h, r, z0=0.0, m=BODY, n=4, cx=0.0, cy=0.0):
    """Box with rounded vertical edges (w along X, d along Y)."""
    mb.prism(rrect(w, d, r, n, cx, cy), z0, z0 + h, m)


# ================================================================== money
def coin(mb, d=0.0265, t=0.0022, loc=(0, 0, 0), rot=None, m=METAL, n=24, face=True, symbol="$"):
    """Coin lying flat (axis Z), bottom at loc."""
    r = d / 2
    prof = [(0, 0), (r * 0.86, 0), (r * 0.98, 0.0002), (r, t * 0.15), (r, t * 0.85), (r * 0.98, t - 0.0002),
            (r * 0.88, t), (r * 0.84, t * 0.88), (0, t * 0.88)]
    with mb.at(loc, rot=rot):
        mb.lathe(prof, m, n=n)
        if face and symbol:
            mb.text(symbol, d * 0.5, (0, 0, t * 0.88), m, depth=t * 0.15, font=FONT_BLACK)


def coin_stack(mb, n=12, d=0.0265, t=0.0022, jitter=0.0008, seed=0, loc=(0, 0, 0), face_top=True):
    rnd = random.Random(seed)
    x, y, z = loc
    for k in range(n):
        coin(mb, d, t, (x + rnd.uniform(-jitter, jitter), y + rnd.uniform(-jitter, jitter), z + k * t),
             rot=(0, 0, rnd.uniform(0, TAU)), n=20, face=(k == n - 1 and face_top))


def coin_stacks(mb, stacks=(14, 9, 18, 6, 11), d=0.0265, seed=0):
    """A small row/cluster of coin stacks (rising savings)."""
    for i, n in enumerate(stacks):
        coin_stack(mb, n, d, seed=seed + i, loc=((i - (len(stacks) - 1) / 2) * d * 1.15, 0, 0))


def coin_pile(mb, n=120, d=0.0265, t=0.0022, radius=0.12, height=0.05, seed=0):
    """Scattered heap of coins: mound-shaped, random tilts."""
    rnd = random.Random(seed)
    placed = []
    for k in range(n):
        rr = radius * math.sqrt(rnd.random())
        a = rnd.uniform(0, TAU)
        x, y = rr * math.cos(a), rr * math.sin(a)
        zt = height * max(0.0, 1 - (rr / radius) ** 2)
        z = rnd.uniform(0, zt)
        tilt = rnd.uniform(0, R(35)) * (1 if zt > t * 2 else 0.3)
        coin(mb, d, t, (x, y, z), rot=(tilt * math.cos(a + 1), tilt * math.sin(a + 1), rnd.uniform(0, TAU)), n=16,
             face=(rnd.random() < 0.15))
        placed.append((x, y, z))


def banknote_bundle(mb, loc=(0, 0, 0), rz=0.0, w=0.156, d=0.066, h=0.011, band=True, top=True, value="100"):
    """Bundle of 100 notes with paper band (accent), long side along X."""
    with mb.at(loc, rz=rz):
        mb.bb(-w / 2, -d / 2, 0, w / 2, d / 2, h, BODY)
        if top:
            # printed top note: border + oval + value
            z = h + 0.0001
            bw = 0.004
            for (x0, y0, x1, y1) in ((-w / 2 + 0.003, -d / 2 + 0.003, w / 2 - 0.003, -d / 2 + 0.003 + bw * 0.4),
                                     (-w / 2 + 0.003, d / 2 - 0.003 - bw * 0.4, w / 2 - 0.003, d / 2 - 0.003),
                                     (-w / 2 + 0.003, -d / 2 + 0.003, -w / 2 + 0.003 + bw * 0.4, d / 2 - 0.003),
                                     (w / 2 - 0.003 - bw * 0.4, -d / 2 + 0.003, w / 2 - 0.003, d / 2 - 0.003)):
                mb.bb(x0, y0, h, x1, y1, z + 0.0002, DARK)
            mb.ring(0.017, 0.019, h, h + 0.0003, DARK, n=24)
            mb.text(value, 0.012, (w / 2 - 0.022, d / 2 - 0.014, h), DARK, depth=0.0003, font=FONT_BLACK)
            mb.text(value, 0.009, (-w / 2 + 0.018, -d / 2 + 0.011, h), DARK, depth=0.0003, font=FONT_BLACK)
        if band:
            mb.bb(-0.018, -d / 2 - 0.0004, -0.0004, 0.018, d / 2 + 0.0004, h + 0.0005, ACCENT)


def banknote(mb, loc=(0, 0, 0), rz=0.0, curl=0.004, value="100"):
    """Single note, gently curled."""
    w, d = 0.156, 0.066
    with mb.at(loc, rz=rz):
        rows = []
        nu = 10
        for i in range(nu + 1):
            x = -w / 2 + w * i / nu
            z = curl * (2 * i / nu - 1) ** 2
            rows.append(x)
        v, f = [], []
        for i in range(nu + 1):
            x = rows[i]
            z = curl * (2 * i / nu - 1) ** 2
            for y in (-d / 2, d / 2):
                v.append((x, y, z))
                v.append((x, y, z + 0.0003))
        for i in range(nu):
            a = i * 4
            b = a + 4
            f += [(a, b, b + 2, a + 2), (a + 1, a + 3, b + 3, b + 1), (a, a + 1, b + 1, b), (a + 2, b + 2, b + 3, a + 3)]
        f += [(0, 2, 3, 1), (nu * 4, nu * 4 + 1, nu * 4 + 3, nu * 4 + 2)]
        mb.add(v, f, BODY)
        mb.ring(0.016, 0.018, 0.0003, 0.0006, DARK, n=20)
        mb.text(value, 0.011, (w / 2 - 0.022, d / 2 - 0.013, curl * 0.5), DARK, depth=0.0003, font=FONT_BLACK)


def cash_stack(mb, cols=3, rows=2, layers=4, seed=0):
    """Neat brick of bundles (cols along X, rows along Y)."""
    w, d, h = 0.156, 0.066, 0.011
    for l in range(layers):
        for i in range(cols):
            for j in range(rows):
                banknote_bundle(mb, ((i - (cols - 1) / 2) * (w + 0.002), (j - (rows - 1) / 2) * (d + 0.002), l * (h + 0.0006)),
                                top=(l == layers - 1))


def cash_pallet(mb, layers=8, seed=0):
    """Pallet stacked with cash bundles (~1.2 x 0.8 m footprint)."""
    pallet(mb)
    w, d, h = 0.156, 0.066, 0.011
    cols, rows = 7, 11
    z0 = 0.144
    lay = 0.11  # each "layer" is a block of 10 bundles visually merged
    for l in range(layers):
        for i in range(cols):
            for j in range(rows):
                x = (i - (cols - 1) / 2) * (w + 0.004)
                y = (j - (rows - 1) / 2) * (d + 0.004)
                with mb.at((x, y, z0 + l * lay)):
                    mb.bb(-w / 2, -d / 2, 0, w / 2, d / 2, lay - 0.003, BODY)
                    mb.bb(-0.018, -d / 2 - 0.0005, -0.0005, 0.018, d / 2 + 0.0005, lay - 0.0025, ACCENT)
    # top printed notes on the top layer only (cheap: dark value text)
    return


def briefcase_cash(mb, open_deg=100, seed=0):
    """Open hard-shell briefcase filled with bundles; hinge along -X edge, opens toward -X."""
    W, D, H = 0.46, 0.33, 0.06   # inner half-shell depth
    t = 0.008
    # bottom shell (tray)
    rbox(mb, W, D, 0.01, 0.02, 0.0, DARK)
    for (x0, y0, x1, y1) in ((-W / 2, -D / 2, W / 2, -D / 2 + t), (-W / 2, D / 2 - t, W / 2, D / 2),
                             (-W / 2, -D / 2 + t, -W / 2 + t, D / 2 - t), (W / 2 - t, -D / 2 + t, W / 2, D / 2 - t)):
        mb.bb(x0, y0, 0.005, x1, y1, H, DARK)
    # fill: bundles in 2 layers (top printed)
    w, d, h = 0.156, 0.066, 0.011
    for l in range(4):
        for i in range(2):
            for j in range(4):
                banknote_bundle(mb, ((i - 0.5) * (w + 0.03), (j - 1.5) * (d + 0.008), 0.012 + l * (h + 0.0006)),
                                top=(l == 3))
    # inner lining rim
    mb.bb(-W / 2 + t, -D / 2 + t, H - 0.006, W / 2 - t, -D / 2 + t + 0.004, H, BODY)
    # lid (rotated about hinge at x=-W/2, z=H)
    with mb.at((-W / 2, 0, H), rot=(0, -R(open_deg), 0)):
        with mb.at((W / 2, 0, 0)):
            rbox(mb, W, D, H * 0.7, 0.02, 0.0, DARK)
            mb.bb(-W / 2 + t, -D / 2 + t, -0.001, W / 2 - t, D / 2 - t, 0.001, BODY)  # lining
    # handle + latches on +X side
    for s in (-1, 1):
        mb.bb(W / 2 - 0.004, s * 0.09 - 0.012, H - 0.02, W / 2 + 0.006, s * 0.09 + 0.012, H, METAL)
    mb.torus(0.045, 0.008, (W / 2 + 0.012, 0, H - 0.01), DARK, n=16, nr=6, arc=math.pi, rot=(R(90), 0, R(90)))


def gold_bar(mb, loc=(0, 0, 0), rz=0.0, L=0.255, Wd=0.08, H=0.045, taper=0.012, stamp=True):
    """Standard 400-oz good-delivery style bar (trapezoid), long side along X."""
    x0, y0 = L / 2, Wd / 2
    x1, y1 = L / 2 - taper, Wd / 2 - taper
    v = [(-x0, -y0, 0), (x0, -y0, 0), (x0, y0, 0), (-x0, y0, 0),
         (-x1, -y1, H), (x1, -y1, H), (x1, y1, H), (-x1, y1, H)]
    f = [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]
    with mb.at(loc, rz=rz):
        mb.add(v, f, METAL)
        if stamp:
            mb.text("999.9", 0.016, (0.0, 0.006, H), METAL, depth=0.0008, font=FONT_BOLD)
            mb.text("FINE GOLD", 0.008, (0.0, -0.012, H), METAL, depth=0.0006, font=FONT_BOLD)


def gold_pyramid(mb, base=5):
    """Classic stepped pyramid of bars, all along X."""
    L, Wd, H = 0.255, 0.08, 0.045
    for l in range(base):
        n = base - l
        for i in range(n):
            gold_bar(mb, (0, (i - (n - 1) / 2) * (Wd + 0.003), l * H), stamp=(l == base - 1))


def gold_pallet(mb, layers=6, seed=0):
    pallet(mb)
    L, Wd, H = 0.255, 0.08, 0.045
    z0 = 0.144
    for l in range(layers):
        if l % 2 == 0:
            for i in range(4):
                for j in range(9):
                    gold_bar(mb, ((i - 1.5) * (L + 0.02), (j - 4) * (Wd + 0.008), z0 + l * H), stamp=(l == layers - 1))
        else:
            for i in range(13):
                for j in range(3):
                    gold_bar(mb, ((i - 6) * (Wd + 0.008), (j - 1) * (L + 0.02), z0 + l * H), rz=R(90),
                             stamp=(l == layers - 1))


# ================================================================== vault / bank fixtures
def vault_door(mb, r=1.2, depth=0.7, open_deg=0.0, bolts=16):
    """Round bank vault door in a wall panel; faces +X, hinge on +Y side."""
    T = 0.6
    s = r + 0.9
    # wall with round opening: build as frame of 4 boxes around a ring collar
    mb.bb(-T, -s - 0.6, 0, 0, s + 0.6, 2 * s + 0.4, BODY)  # wall slab (door sits proud in front)
    zc = s + 0.2
    with mb.at((0, 0, zc), rot=(0, R(90), 0)):
        mb.ring(r + 0.03, r + 0.42, 0.0, 0.3, DARK, n=48)  # frame collar
    hinge = (0.3 + 0.1, r + 0.55)
    with mb.at((hinge[0], hinge[1], zc), rz=R(open_deg)):
        with mb.at((-hinge[0], -hinge[1], 0)):
            with mb.at((0.3, 0, 0), rot=(0, R(90), 0)):
                # door: stepped cylinder (front at +local Z after rot -> +X)
                prof = [(0, -depth), (r - 0.15, -depth), (r - 0.05, -depth * 0.8), (r - 0.05, -0.1), (r, -0.05),
                        (r, 0.12), (r - 0.08, 0.2), (r * 0.72, 0.22), (r * 0.7, 0.28), (0, 0.28)]
                mb.lathe(prof, BODY, n=48)
                mb.ring(r * 0.55, r * 0.6, 0.28, 0.3, DARK, n=40)
                # bolts around the rim (radial, protruding from the edge)
                for k in range(bolts):
                    a = TAU * k / bolts
                    p0 = ((r - 0.1) * math.cos(a), (r - 0.1) * math.sin(a), -0.25)
                    p1 = ((r + 0.22) * math.cos(a), (r + 0.22) * math.sin(a), -0.25)
                    if open_deg > 0:
                        mb.rod(p0, p1, 0.06, METAL, n=10)
                # handwheel
                mb.cyl(0.12, 0.25, (0, 0, 0.28), METAL, n=16)
                mb.torus(0.45, 0.04, (0, 0, 0.5), METAL, n=32, nr=8)
                for k in range(3):
                    a = TAU * k / 3
                    mb.rod((0, 0, 0.5), (0.45 * math.cos(a), 0.45 * math.sin(a), 0.5), 0.03, METAL, n=6)
                    mb.sphere(0.05, (0.53 * math.cos(a), 0.53 * math.sin(a), 0.5), METAL, seg=10, rings=5)
                # time lock dial
                mb.cyl(0.12, 0.05, (0, -r * 0.42, 0.28), DARK, n=16)
        # hinge arm
        mb.bb(-0.2, -0.25, -0.5, 0.25, 0.25, 0.5, DARK)
        mb.cyl(0.18, 1.6, (0, 0, -0.8), DARK, n=16)
    # bolts sockets when closed (visible studs in the frame)
    if open_deg == 0:
        with mb.at((0.3, 0, zc), rot=(0, R(90), 0)):
            for k in range(bolts):
                a = TAU * k / bolts
                mb.cyl(0.05, 0.05, ((r + 0.25) * math.cos(a), (r + 0.25) * math.sin(a), 0.0), METAL, n=10)


def safe(mb, w=0.6, d=0.6, h=0.9, open_=False):
    """Floor safe, door on +X."""
    rbox(mb, d, w, h, 0.03, 0.05, BODY)
    for (sx, sy) in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
        mb.cyl(0.03, 0.05, (sx * (d / 2 - 0.06), sy * (w / 2 - 0.06), 0), DARK, n=8)
    x = d / 2
    mb.bb(x - 0.01, -w / 2 + 0.05, 0.1, x + 0.004, w / 2 - 0.05, h + 0.0, DARK)
    mb.bb(x, -w / 2 + 0.07, 0.12, x + 0.04, w / 2 - 0.07, h - 0.02, BODY)
    with mb.at((x + 0.04, 0.05, 0.62), rot=(0, R(90), 0)):
        mb.cyl(0.07, 0.03, (0, 0, 0), DARK, n=24)
        mb.cyl(0.04, 0.03, (0, 0, 0.03), DARK, n=16)
        for k in range(24):
            a = TAU * k / 24
            mb.bb(0.065 * math.cos(a) - 0.002, 0.065 * math.sin(a) - 0.002, 0.03, 0.065 * math.cos(a) + 0.002,
                  0.065 * math.sin(a) + 0.002, 0.034, LIGHT)
    with mb.at((x + 0.04, 0.05, 0.4), rot=(0, R(90), 0)):
        mb.cyl(0.03, 0.04, (0, 0, 0), METAL, n=12)
        for k in range(3):
            a = TAU * k / 3 + 0.3
            mb.rod((0, 0, 0.03), (0.1 * math.cos(a), 0.1 * math.sin(a), 0.03), 0.01, METAL, n=6)
            mb.sphere(0.016, (0.1 * math.cos(a), 0.1 * math.sin(a), 0.03), METAL, seg=8, rings=4)
    for z in (0.25, h - 0.15):
        mb.bb(x + 0.01, -w / 2 + 0.03, z - 0.04, x + 0.05, -w / 2 + 0.07, z + 0.04, DARK)


def atm(mb):
    """Freestanding ATM, user faces from +X."""
    rbox(mb, 0.7, 0.75, 1.75, 0.04, 0.0, BODY)
    # sloped fascia with recessed screen
    x = 0.35
    mb.bb(x - 0.05, -0.33, 0.9, x + 0.2, 0.33, 0.96, BODY)  # shelf
    mb.add([(x, -0.33, 1.05), (x, 0.33, 1.05), (x, 0.33, 1.55), (x, -0.33, 1.55),
            (x + 0.06, -0.33, 1.05), (x + 0.06, 0.33, 1.05), (x - 0.02, 0.33, 1.55), (x - 0.02, -0.33, 1.55)],
           [(4, 5, 6, 7), (0, 4, 7, 3), (1, 2, 6, 5), (0, 1, 5, 4), (3, 7, 6, 2)], DARK)
    with mb.at((x + 0.02, 0, 1.3), rot=(0, R(-9), 0)):
        mb.bb(0.0, -0.2, -0.14, 0.012, 0.2, 0.14, GLASS)
        for i in range(4):
            mb.bb(0.0, -0.31, 0.1 - i * 0.07, 0.015, -0.27, 0.13 - i * 0.07, BODY)
            mb.bb(0.0, 0.27, 0.1 - i * 0.07, 0.015, 0.31, 0.13 - i * 0.07, BODY)
    # keypad on shelf
    for i in range(4):
        for j in range(3):
            mb.bb(x + 0.03 + i * 0.03, -0.06 + j * 0.04, 0.96, x + 0.055 + i * 0.03, -0.035 + j * 0.04, 0.975, DARK)
    mb.bb(x + 0.0, 0.12, 0.98, x + 0.04, 0.25, 1.02, DARK)  # card slot
    mb.bb(x - 0.01, -0.15, 0.72, x + 0.01, 0.15, 0.78, DARK)  # cash slot
    # accent header with ATM text
    mb.bb(-0.36, -0.38, 1.6, 0.37, 0.38, 1.85, ACCENT)
    mb.text("ATM", 0.13, (0.371, 0, 1.725), BODY, rot=FACE_PX, depth=0.005, font=FONT_BLACK)
    mb.bb(-0.36, -0.38, 0.0, 0.36, 0.38, 0.06, DARK)


def cash_register(mb):
    """Point-of-sale: cash drawer, touch screen on stand, card reader, receipt printer.  Customer side +X."""
    rbox(mb, 0.42, 0.42, 0.11, 0.01, 0.0, DARK)
    mb.bb(0.205, -0.17, 0.02, 0.212, 0.17, 0.09, BODY)  # drawer face
    mb.bb(0.212, -0.04, 0.05, 0.22, 0.04, 0.06, METAL)
    mb.cyl(0.04, 0.12, (-0.05, 0, 0.11), DARK, n=12)
    with mb.at((-0.05, 0, 0.26), rot=(0, R(-70), 0)):
        rbox(mb, 0.24, 0.36, 0.025, 0.012, -0.0125, DARK)
        mb.bb(-0.105, -0.165, 0.0125, 0.105, 0.165, 0.014, GLASS)
    # customer display
    mb.cyl(0.012, 0.18, (-0.15, 0.12, 0.11), DARK, n=8)
    with mb.at((-0.15, 0.12, 0.31), rot=(0, R(80), 0)):
        rbox(mb, 0.06, 0.12, 0.02, 0.006, -0.01, DARK)
        mb.bb(-0.022, -0.05, 0.01, 0.022, 0.05, 0.011, LIGHT)
    # printer
    rbox(mb, 0.14, 0.12, 0.12, 0.02, 0.11, BODY, cx=0.12, cy=-0.13)
    mb.bb(0.12 - 0.002, -0.17, 0.23, 0.14, -0.09, 0.235, DARK)
    mb.add([(0.14, -0.165, 0.232), (0.14, -0.095, 0.232), (0.2, -0.095, 0.29), (0.2, -0.165, 0.29)],
           [(0, 1, 2, 3), (3, 2, 1, 0)], LIGHT)
    # card reader
    with mb.at((0.15, 0.13, 0.11), rot=(0, R(-25), 0)):
        rbox(mb, 0.07, 0.13, 0.03, 0.01, 0.0, DARK)
        mb.bb(-0.025, -0.05, 0.03, 0.025, 0.01, 0.031, GLASS)


def shop_counter(mb, length=2.4, register=True):
    """Shop counter with glass display front (customer side +X)."""
    h, d = 0.95, 0.65
    mb.bb(-d / 2, -length / 2, 0, d / 2, length / 2, 0.1, DARK)  # kick plinth
    mb.bb(-d / 2, -length / 2, 0.1, d / 2 - 0.05, length / 2, h - 0.04, BODY)
    # display window on the customer face
    mb.bb(d / 2 - 0.06, -length / 2 + 0.08, 0.35, d / 2 - 0.04, length / 2 - 0.08, h - 0.1, GLASS)
    mb.bb(d / 2 - 0.05, -length / 2, 0.1, d / 2, length / 2, 0.35, BODY)
    mb.bb(d / 2 - 0.05, -length / 2, h - 0.1, d / 2, length / 2, h - 0.04, BODY)
    for y in (-length / 2 + 0.04, 0, length / 2 - 0.04):
        mb.bb(d / 2 - 0.05, y - 0.04, 0.35, d / 2, y + 0.04, h - 0.1, BODY)
    mb.bb(-d / 2 - 0.02, -length / 2 - 0.02, h - 0.04, d / 2 + 0.03, length / 2 + 0.02, h, BODY)  # top
    # goods in the display
    for k in range(6):
        y = -length / 2 + 0.25 + k * (length - 0.5) / 5
        mb.bb(-0.05, y - 0.08, 0.45, 0.15, y + 0.08, 0.55 + 0.04 * (k % 3), ACCENT if k % 2 else BODY)
    if register:
        with mb.at((-0.05, length * 0.25, h), rz=math.pi):
            cash_register(mb)


def market_stall(mb, w=3.0, d=1.6, seed=0):
    """Market stall: trestle table with produce crates, posts, gabled striped canopy (accent)."""
    rnd = random.Random(seed)
    h = 0.85
    mb.bb(-d / 2, -w / 2, h - 0.04, d / 2, w / 2, h, BODY)
    for (sx, sy) in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
        mb.bb(sx * (d / 2 - 0.05) - 0.03, sy * (w / 2 - 0.05) - 0.03, 0, sx * (d / 2 - 0.05) + 0.03,
              sy * (w / 2 - 0.05) + 0.03, 2.3, DARK)
    mb.bb(d / 2 - 0.02, -w / 2, 0.15, d / 2, w / 2, h - 0.04, BODY)  # front skirt
    # crates with produce (front row tilted toward the customer +X)
    for i in range(4):
        y = -w / 2 + 0.4 + i * (w - 0.8) / 3
        for j in range(2):
            x = -0.32 + j * 0.62
            with mb.at((x, y, h), rot=(0, R(-12) if j == 1 else 0, 0)):
                mb.bb(-0.22, -0.3, 0, 0.22, 0.3, 0.14, BODY)
                m = ACCENT if (i + j) % 2 == 0 else (BODY if (i + j) % 3 else DARK)
                for k in range(14):
                    px, py = rnd.uniform(-0.17, 0.17), rnd.uniform(-0.25, 0.25)
                    mb.sphere(0.045, (px, py, 0.14 + rnd.uniform(0.0, 0.04)), m, seg=8, rings=4)
    # canopy: gable fabric with scalloped valance, alternating stripes
    zc, ridge = 2.3, 2.75
    n = 6
    for k in range(n):
        y0 = -w / 2 - 0.1 + (w + 0.2) * k / n
        y1 = -w / 2 - 0.1 + (w + 0.2) * (k + 1) / n
        m = ACCENT if k % 2 == 0 else BODY
        for s in (-1, 1):
            mb.add([(0, y0, ridge), (0, y1, ridge), (s * (d / 2 + 0.3), y1, zc), (s * (d / 2 + 0.3), y0, zc),
                    (0, y0, ridge + 0.02), (0, y1, ridge + 0.02), (s * (d / 2 + 0.3), y1, zc + 0.02),
                    (s * (d / 2 + 0.3), y0, zc + 0.02)],
                   [(0, 1, 2, 3), (7, 6, 5, 4), (3, 2, 6, 7), (0, 3, 7, 4), (1, 5, 6, 2), (0, 4, 5, 1)], m)
            # valance scallop
            for j in range(2):
                ya = y0 + (y1 - y0) * j / 2
                yb = y0 + (y1 - y0) * (j + 1) / 2
                xs = s * (d / 2 + 0.31)
                mb.add([(xs, ya, zc + 0.02), (xs, yb, zc + 0.02), (xs, yb, zc - 0.12), (xs, (ya + yb) / 2, zc - 0.22),
                        (xs, ya, zc - 0.12)], [(0, 1, 2, 3, 4), (4, 3, 2, 1, 0)], m)
    # price sign
    with mb.at((d / 2 + 0.02, w / 2 - 0.5, h + 0.05)):
        mb.bb(0, -0.2, 0, 0.02, 0.2, 0.25, DARK)
        mb.text("$2", 0.13, (0.021, 0, 0.125), LIGHT, rot=FACE_PX, depth=0.003, font=FONT_BOLD)


def chalkboard_sign(mb, text1="SALE", text2="$4.99"):
    """A-frame sidewalk chalkboard, readable from +X."""
    h, w = 1.0, 0.6
    a = R(12)
    for s in (-1, 1):
        with mb.at((s * 0.0, 0, 0), rot=(0, s * a, 0)):
            with mb.at((s * 0.02, 0, 0)):
                mb.bb(-0.015, -w / 2, 0, 0.015, w / 2, h, BODY)
                mb.bb(s * 0.015 - 0.002 if s > 0 else -0.017, -w / 2 + 0.05, 0.1, s * 0.017 if s > 0 else -0.013,
                      w / 2 - 0.05, h - 0.05, DARK)
                if s > 0:
                    mb.text(text1, 0.12, (0.02, 0, 0.72), LIGHT, rot=FACE_PX, depth=0.002, font=FONT_BLACK)
                    mb.text(text2, 0.14, (0.02, 0, 0.45), LIGHT, rot=FACE_PX, depth=0.002, font=FONT_BOLD)
                    mb.bb(0.018, -0.18, 0.3, 0.019, 0.18, 0.31, LIGHT)


def price_tag(mb, text="$9.99"):
    """Hanging swing tag (display sized: 0.3 m) - icon prop."""
    pts = [(-0.12, -0.07), (0.1, -0.07), (0.16, 0.0), (0.1, 0.07), (-0.12, 0.07)]
    with mb.at((0, 0, 0.2), rot=(R(90), 0, R(90))):
        mb.prism(pts, -0.004, 0.004, ACCENT)
        mb.text(text, 0.055, (-0.015, 0, 0.004), BODY, depth=0.002, font=FONT_BLACK)
    with mb.at((0, 0.13, 0.2), rot=(0, R(90), 0)):
        mb.ring(0.012, 0.02, -0.005, 0.005, BODY, n=16)


def shopping_cart(mb):
    """Wire shopping cart, pushes toward +X (handle at -X)."""
    L, W0, W1, z0, z1 = 0.9, 0.5, 0.55, 0.45, 0.95
    r = 0.006
    # basket outline rings
    def rect(x0, x1, y0, y1, z):
        return [(x0, -y0, z), (x1, -y1, z), (x1, y1, z), (x0, y0, z)]
    bot = rect(-L / 2 + 0.05, L / 2 - 0.12, W0 / 2 - 0.06, W0 / 2 - 0.06, z0)
    top = rect(-L / 2, L / 2, W1 / 2, W1 / 2 - 0.03, z1)
    for ring_ in (bot, top):
        for k in range(4):
            mb.rod(ring_[k], ring_[(k + 1) % 4], r * 1.6, BODY, n=6)
    # vertical wires on sides + front
    n = 14
    for k in range(n + 1):
        u = k / n
        for s in (-1, 1):
            p0 = (bot[0][0] + (bot[1][0] - bot[0][0]) * u, s * (W0 / 2 - 0.06), z0)
            p1 = (top[0][0] + (top[1][0] - top[0][0]) * u, s * (W1 / 2 - 0.015 * u * 2), z1)
            mb.rod(p0, p1, r, BODY, n=4)
    for k in range(9):
        u = k / 8
        y0 = -(W0 / 2 - 0.06) + (W0 - 0.12) * u
        y1 = -(W1 / 2 - 0.03) + (W1 - 0.06) * u
        mb.rod((L / 2 - 0.12, y0, z0), (L / 2, y1, z1), r, BODY, n=4)
        mb.rod((-L / 2 + 0.05, y0, z0), (-L / 2, y0 * 1.08, z1), r, BODY, n=4)
    for k in range(1, 4):
        z = z0 + (z1 - z0) * k / 4
        t = k / 4
        x0 = -L / 2 + 0.05 * (1 - t)
        x1 = L / 2 - 0.12 * (1 - t)
        yy = W0 / 2 - 0.06 + (W1 / 2 - W0 / 2 + 0.03) * t
        for s in (-1, 1):
            mb.rod((x0, s * yy, z), (x1, s * yy, z), r, BODY, n=4)
    for k in range(7):  # basket floor
        y = -(W0 / 2 - 0.06) + (W0 - 0.12) * k / 6
        mb.rod((-L / 2 + 0.05, y, z0), (L / 2 - 0.12, y, z0), r, BODY, n=4)
    # chassis + wheels
    for s in (-1, 1):
        mb.rod((-L / 2 + 0.02, s * 0.2, 0.12), (L / 2 - 0.1, s * 0.16, 0.12), 0.012, DARK, n=6)
        mb.rod((-L / 2 + 0.02, s * 0.2, 0.12), (-L / 2 + 0.06, s * (W0 / 2 - 0.06), z0), 0.012, DARK, n=6)
        mb.rod((-L / 2 - 0.02, s * (W1 / 2 - 0.02), z1), (-L / 2 - 0.1, s * (W1 / 2 - 0.02), z1 + 0.08), 0.01, BODY, n=6)
        for x in (-L / 2 + 0.06, L / 2 - 0.12):
            mb.cyl(0.06, 0.03, (x, s * (0.2 if x < 0 else 0.16) - 0.015, 0.062), DARK, n=16, rot=(R(-90), 0, 0))
            mb.bb(x - 0.02, s * (0.2 if x < 0 else 0.16) - 0.01, 0.06, x + 0.02, s * (0.2 if x < 0 else 0.16) + 0.01, 0.13,
                  DARK)
    mb.rod((-L / 2 - 0.1, -W1 / 2 + 0.02, z1 + 0.08), (-L / 2 - 0.1, W1 / 2 - 0.02, z1 + 0.08), 0.017, ACCENT, n=10)


def shopping_bag(mb, w=0.32, d=0.16, h=0.4, loc=(0, 0, 0), rz=0.0, m=BODY, handle_m=DARK, logo=None):
    with mb.at(loc, rz=rz):
        mb.add([(-d / 2, -w / 2, 0), (d / 2, -w / 2, 0), (d / 2, w / 2, 0), (-d / 2, w / 2, 0),
                (-d / 2, -w / 2, h), (d / 2, -w / 2, h), (d / 2, w / 2, h), (-d / 2, w / 2, h),
                (-d / 2 + 0.01, -w / 2 + 0.01, h), (d / 2 - 0.01, -w / 2 + 0.01, h), (d / 2 - 0.01, w / 2 - 0.01, h),
                (-d / 2 + 0.01, w / 2 - 0.01, h),
                (-d / 2 + 0.01, -w / 2 + 0.01, 0.01), (d / 2 - 0.01, -w / 2 + 0.01, 0.01), (d / 2 - 0.01, w / 2 - 0.01, 0.01),
                (-d / 2 + 0.01, w / 2 - 0.01, 0.01)],
               [(0, 3, 2, 1), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7),
                (4, 5, 9, 8), (5, 6, 10, 9), (6, 7, 11, 10), (7, 4, 8, 11),
                (8, 9, 13, 12), (9, 10, 14, 13), (10, 11, 15, 14), (11, 8, 12, 15), (12, 13, 14, 15)], m)
        for s in (-1, 1):
            pts = [(s * (d / 2 - 0.004), -0.06 + 0.12 * k / 8, h + 0.11 * math.sin(math.pi * k / 8)) for k in range(9)]
            mb.sweep(pts, [(0.004 * math.cos(a), 0.004 * math.sin(a)) for a in [TAU * j / 5 for j in range(5)]],
                     handle_m)
        if logo:
            mb.text(logo, 0.07, (d / 2 + 0.0005, 0, h * 0.55), DARK if m != DARK else BODY, rot=FACE_PX, depth=0.002,
                    font=FONT_BLACK)


def shopping_bags(mb):
    shopping_bag(mb, loc=(0, -0.12, 0), rz=R(10), m=ACCENT, handle_m=BODY, logo="SALE")
    shopping_bag(mb, 0.28, 0.14, 0.34, loc=(0.05, 0.2, 0), rz=R(-15), m=BODY, logo="$")
    shopping_bag(mb, 0.22, 0.12, 0.3, loc=(0.22, 0.0, 0), rz=R(30), m=DARK, handle_m=DARK)


def cardboard_box(mb, size=(0.4, 0.3, 0.3), loc=(0, 0, 0), rz=0.0, open_=False, tape=True, label=True):
    """Shipping carton.  Flap seam + tape strip; open_ shows the flaps up."""
    w, d, h = size
    with mb.at(loc, rz=rz):
        if not open_:
            mb.bb(-w / 2, -d / 2, 0, w / 2, d / 2, h, BODY)
            mb.bb(-w / 2 - 0.0005, -0.002, h - 0.0005, w / 2 + 0.0005, 0.002, h + 0.0008, DARK)  # seam
            if tape:
                mb.bb(-w / 2 - 0.001, -0.025, h - 0.06, w / 2 + 0.001, 0.025, h + 0.001, LIGHT)
            if label:
                mb.bb(w / 2, -d * 0.3, h * 0.35, w / 2 + 0.001, d * 0.1, h * 0.6, LIGHT)
                for k in range(3):
                    mb.bb(w / 2 + 0.0005, -d * 0.27, h * (0.4 + k * 0.06), w / 2 + 0.0015, d * 0.0, h * (0.42 + k * 0.06),
                          DARK)
        else:
            t = 0.004
            mb.bb(-w / 2, -d / 2, 0, w / 2, d / 2, t, BODY)
            for (x0, y0, x1, y1) in ((-w / 2, -d / 2, w / 2, -d / 2 + t), (-w / 2, d / 2 - t, w / 2, d / 2),
                                     (-w / 2, -d / 2 + t, -w / 2 + t, d / 2 - t), (w / 2 - t, -d / 2 + t, w / 2, d / 2 - t)):
                mb.bb(x0, y0, 0, x1, y1, h, BODY)
            for s in (-1, 1):  # long flaps hinged outward on Y sides
                with mb.at((0, s * d / 2, h), rot=(s * R(-120), 0, 0)):
                    mb.bb(-w / 2, -t / 2, 0, w / 2, t / 2, d / 2, BODY)
                with mb.at((s * w / 2, 0, h), rot=(0, s * R(110), 0)):
                    mb.bb(-t / 2, -d / 2 + 0.01, 0, t / 2, d / 2 - 0.01, w * 0.35, BODY)


def box_pile(mb, seed=0):
    rnd = random.Random(seed)
    specs = [((0.6, 0.4, 0.4), (0, 0, 0), 0.0), ((0.5, 0.4, 0.35), (0.05, 0.45, 0), R(8)),
             ((0.4, 0.3, 0.3), (-0.02, 0.05, 0.4), R(-10)), ((0.3, 0.25, 0.22), (0.05, 0.4, 0.35), R(25)),
             ((0.45, 0.35, 0.3), (0.55, 0.1, 0), R(-4))]
    for (sz, lc, rz) in specs:
        cardboard_box(mb, sz, lc, rz)
    cardboard_box(mb, (0.4, 0.35, 0.3), (0.0, -0.55, 0), R(15), open_=True)


def pallet(mb, loc=(0, 0, 0), rz=0.0, L=1.2, W=0.8):
    """EUR pallet 1200 x 800 x 144 mm (long side along X)."""
    with mb.at(loc, rz=rz):
        for y in (-W / 2 + 0.05, 0, W / 2 - 0.05):  # bottom boards
            mb.bb(-L / 2, y - 0.05, 0, L / 2, y + 0.05, 0.022, BODY)
        for x in (-L / 2 + 0.072, 0, L / 2 - 0.072):  # blocks
            for y in (-W / 2 + 0.05, 0, W / 2 - 0.05):
                mb.bb(x - 0.072, y - 0.05, 0.022, x + 0.072, y + 0.05, 0.1, BODY)
        for x in (-L / 2 + 0.05, 0, L / 2 - 0.05):  # stringer boards
            mb.bb(x - 0.05, -W / 2, 0.1, x + 0.05, W / 2, 0.122, BODY)
        n = 5
        for k in range(n):
            y = -W / 2 + 0.07 + (W - 0.14) * k / (n - 1)
            mb.bb(-L / 2, y - 0.07 if k in (0, n - 1) else y - 0.05, 0.122, L / 2, y + 0.07 if k in (0, n - 1) else y + 0.05,
                  0.144, BODY)


def pallet_stack(mb, n=6):
    for k in range(n):
        pallet(mb, (0.005 * ((k * 7) % 3 - 1), 0.006 * ((k * 5) % 3 - 1), k * 0.1445))


def pallet_boxes(mb, layers=3, wrapped=False, seed=0):
    """Pallet loaded with cartons."""
    rnd = random.Random(seed)
    pallet(mb)
    bw, bd, bh = 0.4, 0.4, 0.3
    for l in range(layers):
        for i in range(3):
            for j in range(2):
                cardboard_box(mb, (bw - 0.005, bd - 0.005, bh), ((i - 1) * bw, (j - 0.5) * bd, 0.144 + l * bh),
                              tape=(l == layers - 1), label=(i == 2))


def shelving(mb, bays=2, levels=4, bay_w=2.7, depth=1.1, height=4.5, seed=0):
    """Warehouse pallet racking: dark uprights, accent beams, cartons on levels.  Front +X."""
    rnd = random.Random(seed)
    L = bays * bay_w
    for k in range(bays + 1):
        y = -L / 2 + k * bay_w
        for x in (-depth / 2, depth / 2):
            mb.bb(x - 0.04, y - 0.05, 0, x + 0.04, y + 0.05, height, DARK)
        for z in [0.3 + j * (height - 0.4) / 6 for j in range(7)]:
            mb.bb(-depth / 2, y - 0.015, z, depth / 2, y + 0.015, z + 0.03, DARK)
        for j in range(6):
            z0 = 0.3 + j * (height - 0.4) / 6
            z1 = 0.3 + (j + 1) * (height - 0.4) / 6
            mb.rod((-depth / 2, y, z0), (depth / 2, y, z1), 0.012, DARK, n=4)
    lv = height / levels
    for l in range(levels):
        z = 0.1 + l * lv if l > 0 else 0.12
        if l > 0:
            for x in (-depth / 2, depth / 2):
                mb.bb(x - 0.05, -L / 2, z - 0.12, x + 0.05, L / 2, z, ACCENT)
        for b in range(bays):
            yc = -L / 2 + (b + 0.5) * bay_w
            for p in (-0.65, 0.65):
                if rnd.random() < 0.15:
                    continue
                with mb.at((0, yc + p, z), rz=R(90)):
                    pallet(mb, (0, 0, 0), 0.0)
                    nh = rnd.randint(1, 3) if l < levels - 1 else rnd.randint(1, 2)
                    for hh in range(nh):
                        for i in range(3):
                            for j in range(2):
                                cardboard_box(mb, (0.39, 0.39, 0.3), ((i - 1) * 0.4, (j - 0.5) * 0.4, 0.144 + hh * 0.3),
                                              tape=False, label=(j == 1 and i == 1))


# ================================================================== justice / office
def scales_of_justice(mb, tilt=0.0):
    """Balance scales (METAL), beam along Y; tilt (rad) lowers the +Y pan."""
    mb.lathe([(0.14, 0), (0.14, 0.03), (0.1, 0.05), (0.06, 0.07), (0.03, 0.09), (0, 0.09)], METAL, n=32)
    mb.lathe([(0.022, 0.09), (0.018, 0.3), (0.016, 0.5), (0.025, 0.52), (0.03, 0.55), (0.0, 0.58)], METAL, n=16)
    mb.sphere(0.03, (0, 0, 0.6), METAL, seg=16, rings=8)
    zb = 0.55
    hb = 0.22
    with mb.at((0, 0, zb), rot=(tilt, 0, 0)):
        mb.add([(-0.008, -hb, -0.006), (0.008, -hb, -0.006), (0.008, hb, -0.006), (-0.008, hb, -0.006),
                (-0.008, -hb, 0.006), (0.008, -hb, 0.006), (0.008, hb, 0.006), (-0.008, hb, 0.006)],
               [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)], METAL)
        for s in (-1, 1):
            mb.sphere(0.012, (0, s * hb, 0), METAL, seg=10, rings=5)
    for s in (-1, 1):
        ey = s * hb * math.cos(tilt)
        ez = zb + s * hb * math.sin(tilt)
        pz = ez - 0.25
        for k in range(3):
            a = TAU * k / 3
            mb.rod((0, ey, ez), (0.07 * math.cos(a), ey + 0.07 * math.sin(a), pz), 0.0015, METAL, n=4)
        mb.lathe([(0.0, pz - 0.025), (0.05, pz - 0.022), (0.075, pz - 0.008), (0.08, pz), (0.077, pz + 0.002),
                  (0.07, pz - 0.006), (0.045, pz - 0.017), (0.0, pz - 0.019)], METAL, n=24)


def gavel(mb):
    """Judge's gavel resting on its sound block."""
    mb.lathe([(0.075, 0), (0.075, 0.018), (0.07, 0.024), (0.0, 0.024)], DARK, n=32)
    with mb.at((0.0, 0.0, 0.024 + 0.032), rot=(0, 0, R(25))):
        with mb.at((0, 0, 0), rot=(R(90), 0, 0)):
            mb.lathe([(0, -0.062), (0.028, -0.06), (0.032, -0.05), (0.032, 0.05), (0.028, 0.06), (0, 0.062)], DARK,
                     n=20)
            for z in (-0.04, 0.04):
                mb.cyl(0.0335, 0.008, (0, 0, z - 0.004), METAL, n=20)
        mb.rod((0.0, 0.0, 0.0), (0.24, 0.0, -0.03), 0.009, DARK, n=10, r2=0.011)
        mb.sphere(0.013, (0.245, 0, -0.031), DARK, seg=10, rings=5)


def contract(mb, loc=(0, 0, 0), rz=0.0, title="CONTRACT", signed=True, lines=16):
    """A4 sheet with title, text lines (LIB_Dark) and signature."""
    w, h = 0.21, 0.297
    with mb.at(loc, rz=rz):
        mb.bb(-h / 2, -w / 2, 0, h / 2, w / 2, 0.0004, BODY)
        if title:
            mb.text(title, 0.016, (h / 2 - 0.03, 0, 0.0004), DARK, rot=(0, 0, R(90)), depth=0.0002, font=FONT_BLACK)
        rnd = random.Random(len(title or "") + lines)
        for k in range(lines):
            x = h / 2 - 0.06 - k * 0.0115
            if k % 6 == 5:
                continue
            lw = w - 0.05 - (rnd.uniform(0, 0.08) if k % 6 == 4 else 0)
            mb.bb(x - 0.0018, -w / 2 + 0.025, 0.0004, x + 0.0018, -w / 2 + 0.025 + lw, 0.0006, DARK)
        if signed:
            pts = [(-h / 2 + 0.035 + 0.004 * math.sin(k * 1.3), w / 2 - 0.09 + k * 0.0045, 0.0005) for k in range(14)]
            pts = [(-h / 2 + 0.035 + 0.006 * math.sin(k * 1.9) + 0.002 * math.cos(k * 3.1), w / 2 - 0.1 + k * 0.005,
                    0.0006) for k in range(15)]
            mb.sweep(pts, [(-0.0006, -0.0001), (0.0006, -0.0001), (0.0006, 0.0001), (-0.0006, 0.0001)], DARK)
            mb.bb(-h / 2 + 0.025, w / 2 - 0.105, 0.0004, -h / 2 + 0.0265, w / 2 - 0.02, 0.0006, DARK)
            mb.cyl(0.012, 0.0012, (-h / 2 + 0.035, -w / 2 + 0.04, 0.0004), ACCENT, n=20)  # seal


def document_stack(mb, n=12, seed=0):
    rnd = random.Random(seed)
    for k in range(n):
        contract(mb, (rnd.uniform(-0.006, 0.006), rnd.uniform(-0.006, 0.006), k * 0.0006), rnd.uniform(-0.05, 0.05),
                 title="CONTRACT" if k == n - 1 else "", signed=(k == n - 1), lines=16 if k == n - 1 else 0)
    # a loose sheet + pen
    contract(mb, (0.06, 0.2, 0.0), R(-18), title="INVOICE", signed=False, lines=12)
    pen(mb, (0.02, 0.12, 0.012), R(30))


def pen(mb, loc=(0, 0, 0), rz=0.0):
    with mb.at(loc, rz=rz):
        mb.rod((-0.07, 0, 0), (0.06, 0, 0), 0.0055, DARK, n=12)
        mb.rod((0.06, 0, 0), (0.075, 0, 0), 0.0055, METAL, n=12, r2=0.001)
        mb.bb(-0.06, 0.004, 0.002, -0.02, 0.0065, 0.004, METAL)


def credit_card(mb, loc=(0, 0, 0), rot=None, m=ACCENT):
    """ISO card 85.6 x 54 mm lying flat, long side along X."""
    w, h, t = 0.0856, 0.054, 0.00076
    with mb.at(loc, rot=rot):
        mb.prism(rrect(w, h, 0.003, 4), 0, t, m)
        mb.prism(rrect(0.011, 0.009, 0.0012, 2, -w / 2 + 0.017, 0.004), t, t + 0.00012, METAL)
        mb.text("4000 1234 5678 9010", 0.0042, (-0.004, -0.008, t), BODY, depth=0.0001, font=FONT_SEMI)
        mb.text("VALUED CUSTOMER", 0.0028, (-w / 2 + 0.023, -0.019, t), BODY, depth=0.0001, font=FONT_SEMI)
        mb.cyl(0.0055, 0.0001, (w / 2 - 0.012, -0.017, t), DARK, n=16)
        mb.cyl(0.0055, 0.00012, (w / 2 - 0.019, -0.017, t), BODY, n=16)


def credit_cards_fan(mb):
    for k, m in enumerate((DARK, BODY, ACCENT)):
        credit_card(mb, (0.0, k * 0.008, k * 0.001), rot=(0, 0, R(-18 + k * 18)), m=m)


def smartphone(mb, loc=(0, 0, 0), rot=None, standing=False):
    """Phone with blank glass screen; lying flat (screen up) or standing (screen faces +X)."""
    w, h, t = 0.0715, 0.147, 0.0082
    if standing:
        rot = (0, R(75), 0)
        loc = (-0.01, 0, h / 2 * math.sin(R(75)) + 0.004)
    with mb.at(loc, rot=rot):
        with mb.at((0, 0, -t / 2), rot=(0, 0, R(90))):
            mb.prism(rrect(w, h, 0.009, 5), 0, t, BODY)
            mb.prism(rrect(w - 0.003, h - 0.003, 0.0075, 5), t, t + 0.0003, GLASS)
            mb.prism(rrect(0.022, 0.005, 0.0024, 3, 0, h / 2 - 0.009), t + 0.0003, t + 0.0004, DARK)
            for k in range(3):
                mb.cyl(0.0055, 0.0012, (-w / 2 + 0.012 + (k % 2) * 0.012, h / 2 - 0.012 - (k // 2) * 0.012, -0.0012),
                       DARK, n=16)
    if standing:
        mb.bb(-0.03, -0.04, 0, 0.03, 0.04, 0.004, DARK)


def laptop(mb, open_deg=110, w=0.32, d=0.22):
    """Open laptop, screen faces +X (user at +X)."""
    t = 0.008
    rbox(mb, d, w, t * 1.6, 0.008, 0.0, BODY)
    mb.bb(-d / 2 + 0.02, -w / 2 + 0.025, t * 1.6, d / 2 - 0.085, w / 2 - 0.025, t * 1.6 + 0.0004, DARK)  # keyboard well
    for i in range(5):
        for j in range(13):
            x = -d / 2 + 0.028 + i * 0.0205
            y = -w / 2 + 0.032 + j * 0.0197
            mb.bb(x, y, t * 1.6 + 0.0004, x + 0.016, y + 0.016, t * 1.6 + 0.0014, BODY)
    mb.bb(d / 2 - 0.075, -0.05, t * 1.6, d / 2 - 0.015, 0.05, t * 1.6 + 0.0003, DARK)  # trackpad
    with mb.at((-d / 2 + 0.004, 0, t * 1.6), rot=(0, R(90 - open_deg), 0)):
        mb.bb(-0.0, -w / 2, 0, 0.006, w / 2, d - 0.01, BODY)
        mb.bb(0.006, -w / 2 + 0.01, 0.012, 0.0068, w / 2 - 0.01, d - 0.022, GLASS)
        mb.cyl(0.0015, 0.0008, (0.0068, 0, d - 0.016), DARK, n=8, rot=(0, R(90), 0))


def desk(mb, w=1.6, d=0.8, h=0.75, drawers=True):
    """Office desk, user side -X (faces +X toward visitors)."""
    mb.bb(-d / 2, -w / 2, h - 0.03, d / 2, w / 2, h, BODY)
    for (sx, sy) in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
        if drawers and sy > 0:
            continue
        mb.bb(sx * (d / 2 - 0.04) - 0.025, sy * (w / 2 - 0.04) - 0.025, 0, sx * (d / 2 - 0.04) + 0.025,
              sy * (w / 2 - 0.04) + 0.025, h - 0.03, DARK)
    mb.bb(d / 2 - 0.06, -w / 2 + 0.06, h - 0.35, d / 2 - 0.04, w / 2 - 0.06, h - 0.03, BODY)  # modesty panel
    if drawers:
        mb.bb(-d / 2 + 0.02, w / 2 - 0.45, 0.02, d / 2 - 0.02, w / 2 - 0.02, h - 0.03, BODY)
        for k in range(3):
            z = 0.06 + k * 0.22
            mb.bb(-d / 2 + 0.015, w / 2 - 0.43, z, -d / 2 + 0.02, w / 2 - 0.04, z + 0.2, BODY)
            mb.bb(-d / 2 + 0.005, w / 2 - 0.3, z + 0.15, -d / 2 + 0.015, w / 2 - 0.17, z + 0.165, METAL)


def office_chair(mb, loc=(0, 0, 0), rz=0.0):
    """Swivel office chair; sitter faces +X."""
    with mb.at(loc, rz=rz):
        for k in range(5):
            a = TAU * k / 5
            p = (0.3 * math.cos(a), 0.3 * math.sin(a), 0.07)
            mb.rod((0, 0, 0.1), p, 0.02, DARK, n=6)
            mb.sphere(0.03, (p[0], p[1], 0.03), DARK, seg=10, rings=5)
        mb.cyl(0.03, 0.3, (0, 0, 0.1), METAL, n=12)
        mb.cyl(0.04, 0.08, (0, 0, 0.36), DARK, n=12)
        rbox(mb, 0.48, 0.48, 0.07, 0.08, 0.42, DARK)
        rbox(mb, 0.44, 0.44, 0.02, 0.07, 0.49, DARK)
        mb.rod((-0.15, 0, 0.45), (-0.27, 0, 0.6), 0.025, DARK, n=6)
        with mb.at((-0.25, 0, 0.58), rot=(0, R(-12), 0)):
            mb.prism_yz(rrect(0.44, 0.55, 0.08, 4, 0, 0.3), -0.035, 0.035, DARK)
        for s in (-1, 1):
            mb.rod((-0.05, s * 0.22, 0.45), (-0.05, s * 0.24, 0.65), 0.015, DARK, n=6)
            mb.bb(-0.18, s * 0.24 - 0.03, 0.64, 0.12, s * 0.24 + 0.03, 0.67, DARK)


def office_desk_set(mb):
    desk(mb)
    office_chair(mb, (-0.75, -0.1, 0), 0.0)
    with mb.at((0.0, -0.15, 0.75), rz=math.pi):
        laptop(mb)
    contract(mb, (0.1, 0.45, 0.75), R(10), "REPORT", signed=False, lines=10)
    smartphone(mb, (0.15, 0.25, 0.75 + 0.004), rot=(0, 0, R(20)))


def lectern(mb, text="", m_front=ACCENT, mic=True):
    """Speaker's podium, audience at +X."""
    prof_b = rrect(0.5, 0.7, 0.04, 3)
    mb.prism(rrect(0.65, 0.8, 0.04, 3), 0, 0.06, DARK)
    mb.loft([[(x, y, 0.06) for x, y in rrect(0.48, 0.66, 0.04, 3)],
             [(x * 1.12, y * 1.1, 1.0) for x, y in rrect(0.48, 0.66, 0.04, 3)]], BODY)
    with mb.at((0, 0, 1.0), rot=(0, R(-14), 0)):
        mb.prism(rrect(0.62, 0.8, 0.03, 3), 0, 0.05, BODY)
    # front accent panel
    with mb.at((0.27, 0, 0.55), rot=(0, R(-3.4), 0)):
        mb.bb(0, -0.26, -0.3, 0.012, 0.26, 0.3, m_front)
        mb.cyl(0.12, 0.004, (0.012, 0, 0.05), BODY, n=32, rot=(0, R(90), 0))
        if text:
            mb.text(text, 0.07, (0.017, 0, -0.18), BODY, rot=FACE_PX, depth=0.002, font=FONT_BLACK)
    if mic:
        pts = [(0.2 + 0.0, 0.18, 1.08)] + [(0.2 + 0.12 * math.sin(R(a)), 0.18, 1.08 + 0.3 * (1 - math.cos(R(a))) * 0.6 + 0.0)
                                            for a in range(15, 91, 15)]
        mb.sweep(pts, [(0.004 * math.cos(a), 0.004 * math.sin(a)) for a in [TAU * j / 6 for j in range(6)]], DARK)
        mb.rod(pts[-1], (pts[-1][0] + 0.05, pts[-1][1], pts[-1][2] - 0.01), 0.011, DARK, n=10, r2=0.013)


def flag_on_pole(mb, h=6.0, fw=2.2, fh=1.4, base=True, emblem=True, seed=0):
    """Outdoor flagpole with waving cloth (LIB_Accent) and optional white emblem disc."""
    import arch_lib as A
    if base:
        mb.cyl(0.35, 0.25, (0, 0, 0), BODY, n=16)
        mb.cyl(0.25, 0.1, (0, 0, 0.25), BODY, n=16)
    mb.cyl(0.05, h, (0, 0, 0), BODY, n=12, r2=0.035)
    mb.sphere(0.08, (0, 0, h + 0.06), METAL, seg=12, rings=6)
    A.cloth(mb, fw, fh, (0.04, 0, h - fh - 0.1), ACCENT, amp=0.15, waves=1.4, seed=seed, t=0.012)
    if emblem:
        # emblem disc following the cloth wave approximately at its hoist-third
        u = 0.3
        yy = 0.15 * math.sin(TAU * 1.4 * u + seed + 0.5) * u ** 0.7
        with mb.at((0.04 + u * fw, yy - 0.012, h - 0.1 - fh / 2 - 0.03), rot=(R(90), 0, 0)):
            mb.cyl(fh * 0.2, 0.004, (0, 0, -0.002), BODY, n=24)


def flag_row(mb, n=3, spacing=3.0, h=8.0, seed=0):
    for k in range(n):
        with mb.at((0, (k - (n - 1) / 2) * spacing, 0)):
            flag_on_pole(mb, h, 2.4, 1.5, seed=seed + k)


def flag_indoor(mb):
    """Indoor flag stand (for press-room / office scenes)."""
    import arch_lib as A
    mb.lathe([(0.2, 0), (0.2, 0.04), (0.12, 0.08), (0.04, 0.12), (0.03, 0.14), (0, 0.14)], METAL, n=24)
    mb.cyl(0.018, 2.4, (0, 0, 0.1), DARK, n=10)
    mb.lathe([(0.03, 0), (0.05, 0.08), (0.0, 0.2)], METAL, n=12, loc=(0, 0, 2.5))
    # hanging (draped) cloth
    rows = []
    fw, fh = 0.9, 1.5
    nu, nv = 8, 8
    v, f = [], []
    for j in range(nv + 1):
        for i in range(nu + 1):
            u = i / nu
            t = j / nv
            yy = 0.06 * math.sin(math.pi * 3 * u) * (1 - t) ** 0.5 + 0.02 * u
            v.append((0.02 + u * fw * (0.55 + 0.45 * (1 - t)), yy, 2.42 - t * fh))
    for j in range(nv):
        for i in range(nu):
            a = j * (nu + 1) + i
            f.append((a, a + 1, a + nu + 2, a + nu + 1))
            f.append((a + nu + 1, a + nu + 2, a + 1, a))
    mb.add(v, f, ACCENT)


# ================================================================== data / icons (display sized)
def bar_chart(mb, values=(3, 5, 4, 7, 9), bar_w=0.6, gap=0.35, scale=0.4, base=True, highlight=-1, labels=True):
    """3D bar chart; bars along Y, height = value*scale.  highlight: index of an LIB_Accent bar (-1 = all accent)."""
    n = len(values)
    L = n * bar_w + (n + 1) * gap
    mx = max(values) * scale
    if base:
        mb.bb(-bar_w, -L / 2, 0, bar_w, L / 2, 0.06, BODY)
        mb.bb(-bar_w - 0.02, -L / 2 - 0.02, 0.06, -bar_w + 0.04, L / 2 + 0.02, mx * 1.12, BODY)  # back wall
        for k in range(1, 5):
            z = mx * 1.1 * k / 4
            mb.bb(-bar_w + 0.04, -L / 2, z - 0.006, -bar_w + 0.045, L / 2, z + 0.006, DARK)
    for i, v in enumerate(values):
        y = -L / 2 + gap + bar_w / 2 + i * (bar_w + gap)
        m = ACCENT if (highlight < 0 or i == highlight) else BODY
        mb.bb(-bar_w / 2, y - bar_w / 2, 0.06, bar_w / 2, y + bar_w / 2, 0.06 + v * scale, m)
        if labels:
            mb.text(f"{v:g}", bar_w * 0.4, (bar_w / 2 + 0.001, y, 0.06 + v * scale - bar_w * 0.35), DARK if m == BODY else BODY,
                    rot=FACE_PX, depth=0.005, font=FONT_BLACK)


def line_chart(mb, values=(2, 3, 2.5, 4, 3.6, 5.5, 7), step=0.6, scale=0.35, thick=0.08, base=True, markers=True):
    """Ribbon line chart (curtain under the line) along Y, values up Z."""
    n = len(values)
    L = (n - 1) * step
    if base:
        mb.bb(-0.4, -L / 2 - 0.3, 0, 0.4, L / 2 + 0.3, 0.05, BODY)
        for k in range(n):
            y = -L / 2 + k * step
            mb.bb(-0.3, y - 0.006, 0.05, 0.3, y + 0.006, 0.056, DARK)
    pts = [(0.0, -L / 2 + k * step, 0.05 + v * scale) for k, v in enumerate(values)]
    # smooth via subdivision (Catmull-Rom)
    sm = []
    for k in range(n - 1):
        p0 = Vector(pts[max(k - 1, 0)])
        p1, p2 = Vector(pts[k]), Vector(pts[k + 1])
        p3 = Vector(pts[min(k + 2, n - 1)])
        for s in range(6):
            t = s / 6
            sm.append(0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t * t +
                             (-p0 + 3 * p1 - 3 * p2 + p3) * t ** 3))
    sm.append(Vector(pts[-1]))
    # curtain (light accent wall) from base to line
    v, f = [], []
    for p in sm:
        v += [(-0.01, p.y, 0.05), (-0.01, p.y, p.z), (0.01, p.y, p.z), (0.01, p.y, 0.05)]
    for k in range(len(sm) - 1):
        a, b = 4 * k, 4 * (k + 1)
        f += [(a, b, b + 1, a + 1), (a + 3, a + 2, b + 2, b + 3)]
    f += [(0, 1, 2, 3), (4 * (len(sm) - 1) + 3, 4 * (len(sm) - 1) + 2, 4 * (len(sm) - 1) + 1, 4 * (len(sm) - 1))]
    mb.add(v, f, BODY)
    mb.sweep([tuple(p) for p in sm], [(-thick, -thick * 0.6), (thick, -thick * 0.6), (thick, thick * 0.6),
                                      (-thick, thick * 0.6)], ACCENT)
    if markers:
        for p in pts:
            mb.sphere(thick * 1.5, p, ACCENT, seg=16, rings=8)
    # end arrow head
    d = (sm[-1] - sm[-3]).normalized()
    with mb.at(tuple(sm[-1])):
        tip = d * 0.35
        mb.rod((0, 0, 0), tuple(tip), thick * 2.6, ACCENT, n=12, r2=0.001)


def pie_chart(mb, values=(45, 25, 18, 12), r=1.0, h=0.25, explode=0.12, mats=(ACCENT, BODY, DARK, BODY)):
    """Pie chart: slices as arc prisms, first slice exploded and taller."""
    tot = float(sum(values))
    a = 0.0
    for i, v in enumerate(values):
        arc = TAU * v / tot
        mid = a + arc / 2
        off = explode if i == 0 else 0.0
        hh = h * (1.35 if i == 0 else 1.0)
        nseg = max(3, int(48 * v / tot))
        pts = [(0, 0)] + [(r * math.cos(a + arc * k / nseg), r * math.sin(a + arc * k / nseg)) for k in range(nseg + 1)]
        with mb.at((off * math.cos(mid), off * math.sin(mid), 0)):
            mb.prism(pts, 0, hh, mats[i % len(mats)])
            if i == 0:
                mb.text(f"{int(round(100 * v / tot))}%", r * 0.18, (r * 0.62 * math.cos(mid), r * 0.62 * math.sin(mid), hh),
                        BODY, rot=(0, 0, mid - math.pi / 2), depth=0.01, font=FONT_BLACK)
        a += arc


def currency_icon(mb, symbol="$", size=1.0, depth=0.25, m=METAL, base=True):
    """Big standing currency symbol (Inter Black), faces +X."""
    zc = size * 0.55 + (0.08 if base else 0)
    mb.text(symbol, size, (-depth / 2, 0, zc), m, rot=FACE_PX, depth=depth, font=FONT_BLACK)
    if base:
        mb.cyl(size * 0.42, 0.08, (0, 0, 0), DARK, n=40)


def coin_icon(mb, symbol="$", r=0.5, t=0.09, m=METAL):
    """Display-size coin standing on edge, face toward +X."""
    with mb.at((0, 0, r), rot=(0, R(90), 0)):
        mb.lathe([(0, -t / 2), (r * 0.9, -t / 2), (r, -t * 0.35), (r, t * 0.35), (r * 0.9, t / 2), (r * 0.82, t / 2),
                  (r * 0.8, t * 0.38), (0, t * 0.38)], m, n=48)
        with mb.at((0, 0, 0), rot=(0, math.pi, 0)):
            mb.lathe([(r * 0.82, t / 2), (r * 0.8, t * 0.38), (0, t * 0.38)], m, n=48)
        mb.ring(r * 0.72, r * 0.75, t * 0.38, t * 0.46, m, n=48)
        mb.text(symbol, r * 0.95, (0, 0, t * 0.38), m, rot=(0, 0, R(-90)), depth=t * 0.22, font=FONT_BLACK)


def percent_arrow(mb, up=True, size=1.0, m=ACCENT):
    """Chunky trend arrow (up/down) for economy graphics, in the XZ plane facing +X... drawn in YZ."""
    s = size
    pts = [(-0.12, 0), (0.12, 0), (0.12, 0.6), (0.3, 0.6), (0.0, 1.0), (-0.3, 0.6), (-0.12, 0.6)]
    pts = [(x * s, y * s) for x, y in pts]
    ang = R(-35 if up else 215)
    with mb.at((0, 0, 0.55 * s), rot=(ang, 0, 0)):
        with mb.at((0, 0, -0.5 * s)):
            mb.prism_yz(pts, -0.08 * s, 0.08 * s, m)
