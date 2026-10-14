"""Figurine people posed from real motion capture (CMU library).

The body is built around the mocap joint positions (so stance, weight shift,
heel lift, shoulder drop and gestures are genuinely human), voxel-remeshed into
one smooth sculpt. Weapon handling:
  "held"     rifle placed in the chest frame, both hands solved onto it
  "slung"    rifle hangs across the chest on a sling, arms stay as captured
  "one_hand" rifle carried muzzle-down in the right hand, rest as captured
  None       unarmed (civilian)
"""
import math
import zlib
import random
import bpy
from mathutils import Vector, Matrix, Euler
from lib import pbr, join, apply_mods
from figure import _capsule, _ellipsoid, _two_bone, carbine, GRIP, FOREGRIP
import mocap

# curated moments: (clip, t) — casual/idle, walking, talking, looking around
# curated by eye from a stick-figure contact sheet of every clip (see humans pipeline notes)
CASUAL = [("77_02", t) for t in (0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9)] + \
         [("40_10", 0.2), ("40_10", 0.7), ("40_10", 0.9), ("40_11", 0.2), ("40_11", 0.3), ("40_11", 0.8),
          ("40_11", 0.9), ("86_09", 0.7), ("86_09", 0.8), ("79_36", 0.1), ("79_36", 0.2), ("76_04", 0.1),
          ("76_04", 0.2), ("18_08", 0.1), ("18_08", 0.3), ("19_08", 0.2), ("19_08", 0.5)]
TALK = [("18_09", 0.1), ("18_09", 0.2), ("18_09", 0.3), ("18_09", 0.4), ("18_08", 0.6), ("18_08", 0.2),
        ("18_08", 0.4), ("18_08", 0.7), ("18_08", 0.9), ("40_10", 0.3), ("40_10", 0.5), ("40_11", 0.5),
        ("40_11", 0.6), ("19_08", 0.3), ("19_08", 0.7)]
WALK = [(c, t) for c in ("02_01", "07_01", "07_04", "08_04", "16_15", "35_01", "39_01")
        for t in (0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8)]
TACTICAL = [("17_03", t) for t in (0.3, 0.4, 0.5, 0.6, 0.9)] + [("17_04", t) for t in (0.1, 0.2, 0.4, 0.7, 0.9)] + \
           [("76_04", 0.7), ("76_04", 0.8), ("77_01", 0.6), ("77_01", 0.8)]


def _frame(x, y, z):
    """3x3 matrix with given (unnormalised) axes, orthonormalised around z then x."""
    z = z.normalized()
    y = (y - z * y.dot(z)).normalized()
    x = y.cross(z)
    return Matrix((x, y, z)).transposed()


def make_person(name, mode="casual", weapon="held", coll=None, accent=(0.95, 0.38, 0.06), pick=None,
                body_col=(0.86, 0.85, 0.83), gun_col=(0.035, 0.037, 0.04), soldier=True, height=None):
    coll = coll or bpy.context.scene.collection
    rng = random.Random(zlib.crc32(name.encode()))
    lib_ = {"casual": CASUAL, "walk": WALK, "talk": TALK, "tactical": TACTICAL}[mode]
    clip, t = pick or lib_[rng.randrange(len(lib_))]
    t = min(0.95, max(0.05, t + rng.uniform(-0.08, 0.08)))
    J = mocap.pose(clip, t, height or rng.uniform(1.72, 1.86))

    body = pbr(f"Fig_{body_col}", body_col, rough=0.55)
    vestm = pbr(f"FigVest_{body_col}", tuple(c * 0.92 for c in body_col), rough=0.7)
    acc = pbr(f"FigAcc_{accent}", accent, rough=0.5)
    gun = pbr("FigGun", gun_col, rough=0.45)
    soft, hard = [], []

    # ---- frames
    hipL, hipR = J["LeftUpLeg"], J["RightUpLeg"]
    pelvis = (hipL + hipR) / 2 + Vector((0, 0, 0.04))
    shL, shR = J["LeftArm"], J["RightArm"]
    neck = J["Neck1"] if "Neck1" in J else J["Neck"]
    chest_c = J["Spine1"].lerp(neck, 0.25)
    up_t = neck - J["Spine"]
    Rc = _frame(None or Vector(), shL - shR, up_t) if False else _frame(Vector(), shL - shR, up_t)
    Rp = _frame(Vector(), hipL - hipR, J["Spine"] - pelvis)
    head = J["Head"]
    head_top = J.get("Head_end", head + Vector((0, 0, 0.18)))
    Rh = _frame(Vector(), shL - shR, head_top - head)

    def ell(n, c, r, R):
        o = _ellipsoid(n, Vector(), r, coll, body)
        o.data.transform(Matrix.Translation(c) @ R.to_4x4())
        return o

    # ---- torso (pelvis, belly, chest), neck, head
    soft.append(ell(f"{name}_pel", pelvis, (0.12, 0.165, 0.12), Rp))
    soft.append(ell(f"{name}_abd", J["Spine"].lerp(J["Spine1"], 0.4), (0.115, 0.155, 0.15), _frame(Vector(), shL - shR, J["Spine1"] - pelvis)))
    soft.append(ell(f"{name}_chest", chest_c, (0.13, 0.19, 0.19), Rc))
    soft.append(_capsule(f"{name}_neck", J["Neck"], head, 0.052, 0.05, coll, body))
    hc = head + (head_top - head) * 0.45
    soft.append(ell(f"{name}_head", hc, (0.1, 0.088, 0.106), Rh))
    for s in (shL, shR):
        soft.append(_ellipsoid(f"{name}_delt", s + Rc @ Vector((0, 0, -0.015)), (0.06, 0.06, 0.06), coll, body))
    if soldier:
        for k, xx in enumerate((0.1, -0.1)):
            from lib import box
            pl = box(f"{name}_plate{k}", (0.045, 0.27, 0.29), (0, 0, 0), coll, 0.02, vestm)
            pl.data.transform(Matrix.Translation(chest_c + Rc @ Vector((xx * 1.05, 0, -0.05))) @ Rc.to_4x4())
            soft.append(pl)
        for i, yy in enumerate((-0.085, 0.0, 0.085)):
            from lib import box
            po = box(f"{name}_pouch{i}", (0.045, 0.065, 0.09), (0, 0, 0), coll, 0.01, vestm)
            po.data.transform(Matrix.Translation(chest_c + Rc @ Vector((0.14, yy, -0.12))) @ Rc.to_4x4())
            soft.append(po)

    # ---- legs + boots (from mocap, so heels lift and knees bend naturally)
    for side, (h, k, a, toe) in enumerate(((hipL, J["LeftLeg"], J["LeftFoot"], J["LeftToeBase"]),
                                           (hipR, J["RightLeg"], J["RightFoot"], J["RightToeBase"]))):
        soft += [_capsule(f"{name}_th{side}", h, k, 0.095, 0.072, coll, body),
                 _capsule(f"{name}_sh{side}", k, a, 0.07, 0.052, coll, body)]
        fwd = toe - a
        fh = Vector((fwd.x, fwd.y, 0)).normalized()
        sole = max(0.045, min(a.z, toe.z + 0.06) - 0.05)  # keep a lifted heel lifted
        heel = Vector((a.x, a.y, a.z - 0.06)) - fh * 0.045
        tip = Vector((toe.x, toe.y, max(toe.z, 0.04))) + fh * 0.07
        soft.append(_capsule(f"{name}_boot{side}", heel, tip, 0.05, 0.045, coll, body))
        soft.append(_capsule(f"{name}_ank{side}", a, heel + fh * 0.05, 0.052, 0.05, coll, body))

    # ---- arms / weapon
    elL, elR = J["LeftForeArm"], J["RightForeArm"]
    wrL, wrR = J["LeftHand"], J["RightHand"]
    tipL = J.get("LeftHandIndex1", wrL + (wrL - elL).normalized() * 0.08)
    tipR = J.get("RightHandIndex1", wrR + (wrR - elR).normalized() * 0.08)
    arms = {"L": (shL, elL, wrL, tipL), "R": (shR, elR, wrR, tipR)}

    if weapon == "held":
        pitch = math.radians(rng.uniform(22, 40))
        ryaw = math.radians(rng.uniform(8, 22))
        butt = chest_c + Rc @ Vector((0.12, -0.17, 0.08 + rng.uniform(-0.04, 0.03)))
        fwd_dir = Rc @ Vector((1, 0, 0))
        heading = math.atan2(fwd_dir.y, fwd_dir.x)
        M = Matrix.Translation(butt) @ Euler((0, pitch, heading + ryaw)).to_matrix().to_4x4()
        g = carbine(f"{name}_rifle", coll, gun)
        g.data.transform(M)
        hard.append(g)
        for key, tgt in (("R", M @ GRIP), ("L", M @ FOREGRIP)):
            s, e, w, tp = arms[key]
            ua, fa = (e - s).length, (w - e).length
            el, hand = _two_bone(s, tgt, ua, fa, e + (e - (s + w) / 2) * 2 + Vector((0, 0, -0.3)))
            arms[key] = (s, el, hand, hand + (hand - el).normalized() * 0.08)
    elif weapon == "slung":
        # hanging diagonally across the front on a sling, muzzle down-left
        d = Rc @ Vector((0.3, 0.55, -0.78))          # butt high on the right, muzzle down-left
        top = Rc @ Vector((1, 0, 0.2))                 # sights face outward
        Rr = _frame(Vector(), top.cross(d), top)      # x along the barrel
        Rr = Matrix((d.normalized(), (top.cross(d)).normalized(), d.normalized().cross(top.cross(d).normalized()))).transposed()
        M = Matrix.Translation(chest_c + Rc @ Vector((0.17, -0.2, 0.05))) @ Rr.to_4x4()
        g = carbine(f"{name}_rifle", coll, gun)
        g.data.transform(M)
        hard.append(g)
        strap = _capsule(f"{name}_sling", M @ Vector((0.05, 0, 0)), shL + Vector((0, 0, 0.04)), 0.012, 0.012, coll, gun)
        strap2 = _capsule(f"{name}_sling2", shL + Vector((0, 0, 0.04)), M @ Vector((0.7, 0, 0)), 0.012, 0.012, coll, gun)
        hard += [strap, strap2]
    elif weapon == "one_hand":
        s, e, w, tp = arms["R"]
        d = (tp - w).normalized()
        down = (d + Vector((0, 0, -1.2))).normalized()
        heading = math.atan2(Rc[1][0], Rc[0][0])
        # carry by the pistol grip, muzzle forward-down
        R = Euler((0, math.radians(55), heading)).to_matrix().to_4x4()
        M = Matrix.Translation(w + down * 0.04) @ R @ Matrix.Translation(-GRIP)
        g = carbine(f"{name}_rifle", coll, gun)
        g.data.transform(M)
        hard.append(g)

    for key, (s, e, w, tp) in arms.items():
        soft += [_capsule(f"{name}_ua{key}", s, e, 0.064, 0.052, coll, body),
                 _capsule(f"{name}_fa{key}", e, w, 0.052, 0.04, coll, body)]
        hd = (tp - w)
        soft.append(_capsule(f"{name}_hand{key}", w, w + hd.normalized() * min(hd.length, 0.09), 0.045, 0.04, coll, body))
        if soldier and key == "L":
            hard.append(_capsule(f"{name}_band", s.lerp(e, 0.4), s.lerp(e, 0.58), 0.068, 0.062, coll, acc))

    if soldier:
        hm = _ellipsoid(f"{name}_helmet", Vector(), (0.128, 0.12, 0.125), coll, acc)
        hm.data.transform(Matrix.Translation(hc + Rh @ Vector((-0.012, 0, 0.022))) @ Rh.to_4x4())
        lim_c = hc + Rh @ Vector((0, 0, -0.03))
        nz = Rh @ Vector((0, 0, 1))
        for v in hm.data.vertices:
            rel = v.co - lim_c
            front = max(0.0, (Rh.transposed() @ rel).x / 0.13)
            if rel.dot(nz) < 0.05 * front:
                v.co -= nz * (rel.dot(nz) - 0.05 * front)
        hard.append(hm)

    sculpt = join(soft, name + "_body")
    rm = sculpt.modifiers.new("Remesh", "REMESH")
    rm.mode = "VOXEL"
    rm.voxel_size = 0.013
    sm = sculpt.modifiers.new("Smooth", "CORRECTIVE_SMOOTH")
    sm.iterations = 6
    sm.use_only_smooth = True
    apply_mods(sculpt)
    sculpt.data.materials.clear()
    sculpt.data.materials.append(body)
    fig = join([sculpt] + hard, name)
    gi = {i for i, m in enumerate(fig.data.materials) if m == gun}
    for p in fig.data.polygons:
        p.use_smooth = p.material_index not in gi
    fig["clip"] = f"{clip}@{t:.2f}"
    return fig
