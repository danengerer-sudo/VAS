"""People for the white diorama style: Blender Studio 'Human Base Meshes' (CC0) bodies,
auto-rigged, posed from CMU motion capture, with sculpted clothing.

make_human(name, sex="male"|"female", age="adult"|"child", mode, weapon, ...)
  mode: "casual" | "walk" | "talk"   (motion-capture library, see mfigure.py lists)
  weapon: None | "held" | "slung" | "one_hand"   (soldier gear added when weapon or soldier=True)
Result: one static mesh object, facing +X, feet on z=0.
"""
import os
import math
import zlib
import random
import bpy
import bmesh
import numpy as np
from mathutils import Vector, Matrix, Euler
from lib import pbr, join, apply_mods, box
from figure import _capsule, _ellipsoid, _two_bone, carbine, GRIP, FOREGRIP
import mocap
from mfigure import CASUAL, WALK, TALK, _frame

HERE = os.path.dirname(os.path.abspath(__file__))
BUNDLE = os.path.join(HERE, "..", "assets", "packs", "human_base_meshes", "human-base-meshes-bundle-v1.4.1",
                      "human_base_meshes_bundle.blend")
SRC = {"male": "GEO-body_male_realistic", "female": "GEO-body_female_realistic"}
_base = {}

# ------------------------------------------------------------------ base mesh + joints


def _load_base(sex):
    """Load the sculpt once, apply one multires level, rotate to face +X. Returns (mesh data, joints)."""
    if sex in _base:
        return _base[sex]
    name = SRC[sex]
    with bpy.data.libraries.load(BUNDLE) as (src, dst):
        dst.objects = [name, name + ".eye.L", name + ".eye.R"]
    objs = [o for o in dst.objects if o]
    for o in objs:
        bpy.context.scene.collection.objects.link(o)
    body = objs[0]
    for m in body.modifiers:
        if m.type == "MULTIRES":
            m.levels = m.render_levels = min(1, m.total_levels)
    apply_mods(body)
    for e in objs[1:]:
        apply_mods(e)
    body = join(objs, f"_base_{sex}")
    # face +X (the sculpt faces -Y)
    body.data.transform(Matrix.Rotation(math.radians(90), 4, "Z"))
    body.data.update()
    me = body.data
    bpy.context.scene.collection.objects.unlink(body)
    J = _find_joints(me)
    _base[sex] = (me, J)
    return _base[sex]


def _find_joints(me):
    """Estimate joint centres on an A-posed body (facing +X, Y = left) from slices + anthropometry."""
    V = np.array([v.co[:] for v in me.vertices])
    H = V[:, 2].max()
    J = {}

    def slice_c(z0, z1, cond):
        m = (V[:, 2] >= z0) & (V[:, 2] <= z1) & cond
        return Vector(V[m].mean(0)) if m.any() else None

    for side, s in (("L", 1), ("R", -1)):
        legs = (V[:, 1] * s > 0.005) & (np.abs(V[:, 1]) < 0.16 * H)
        knee = slice_c(0.275 * H, 0.295 * H, legs)
        ank = slice_c(0.035 * H, 0.055 * H, legs & (V[:, 0] < 0.02 * H))
        thigh = slice_c(0.44 * H, 0.46 * H, legs)
        hip = Vector((thigh.x, thigh.y * 0.95, 0.515 * H))
        foot = V[(V[:, 2] < 0.03 * H) & (V[:, 1] * s > 0) & (np.abs(V[:, 1]) < 0.16 * H)]
        tip = Vector(foot[np.argmax(foot[:, 0])])
        heel = Vector(foot[np.argmin(foot[:, 0])])
        ball = heel.lerp(tip, 0.72)
        ball.z = 0.025 * H
        ank.z = 0.045 * H
        J[f"hip{side}"], J[f"knee{side}"], J[f"ankle{side}"], J[f"ball{side}"] = hip, knee, ank, ball
        J[f"toe{side}"] = Vector((tip.x, ball.y, 0.02 * H))
        # arm: points out at the side, PCA axis of the arm band
        arm = V[(V[:, 1] * s > 0.13 * H) & (V[:, 2] > 0.42 * H) & (V[:, 2] < 0.8 * H)]
        c = arm.mean(0)
        u, sv, vt = np.linalg.svd(arm - c)
        ax = vt[0]
        if ax[2] < 0:
            ax = -ax  # point up toward the shoulder
        ax = Vector(ax)
        # shoulder: where the axis reaches z = 0.815 H
        t = (0.815 * H - c[2]) / ax.z
        sh = Vector(c) + ax * t
        sh.y = s * min(abs(sh.y), 0.115 * H)
        down = -ax
        J[f"shoulder{side}"] = sh
        J[f"elbow{side}"] = sh + down * 0.186 * H
        J[f"wrist{side}"] = sh + down * (0.186 + 0.146) * H
        J[f"finger{side}"] = sh + down * (0.186 + 0.146 + 0.09) * H
    cx = (J["hipL"].x + J["hipR"].x) / 2
    J["pelvis"] = Vector((cx, 0, 0.535 * H))
    J["spine"] = Vector((cx - 0.005 * H, 0, 0.62 * H))
    J["chest"] = Vector((cx - 0.01 * H, 0, 0.72 * H))
    J["neck"] = Vector((cx - 0.005 * H, 0, 0.83 * H))
    J["head"] = Vector((cx + 0.005 * H, 0, 0.885 * H))
    J["headtop"] = Vector((cx + 0.005 * H, 0, H))
    J["_H"] = H
    return J


# ------------------------------------------------------------------ skeleton

BONES = [  # name, head joint, tail joint, parent
    ("pelvis", "pelvis", "spine", None), ("spine", "spine", "chest", "pelvis"), ("chest", "chest", "neck", "spine"),
    ("neck", "neck", "head", "chest"), ("head", "head", "headtop", "neck"),
    ("thigh.L", "hipL", "kneeL", "pelvis"), ("shin.L", "kneeL", "ankleL", "thigh.L"),
    ("foot.L", "ankleL", "ballL", "shin.L"), ("toe.L", "ballL", "toeL", "foot.L"),
    ("thigh.R", "hipR", "kneeR", "pelvis"), ("shin.R", "kneeR", "ankleR", "thigh.R"),
    ("foot.R", "ankleR", "ballR", "shin.R"), ("toe.R", "ballR", "toeR", "foot.R"),
    ("clav.L", "chest", "shoulderL", "chest"), ("upper_arm.L", "shoulderL", "elbowL", "clav.L"),
    ("forearm.L", "elbowL", "wristL", "upper_arm.L"), ("hand.L", "wristL", "fingerL", "forearm.L"),
    ("clav.R", "chest", "shoulderR", "chest"), ("upper_arm.R", "shoulderR", "elbowR", "clav.R"),
    ("forearm.R", "elbowR", "wristR", "upper_arm.R"), ("hand.R", "wristR", "fingerR", "forearm.R"),
]


def _rig(obj, J):
    arm_d = bpy.data.armatures.new(obj.name + "_rig")
    arm = bpy.data.objects.new(obj.name + "_rig", arm_d)
    bpy.context.scene.collection.objects.link(arm)
    vl = bpy.context.view_layer
    for o in vl.objects:
        o.select_set(False)
    vl.objects.active = arm
    arm.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    eb = arm_d.edit_bones
    for n, h, t, p in BONES:
        b = eb.new(n)
        b.head, b.tail = J[h], J[t]
        if n in ("pelvis", "spine", "chest"):
            b.align_roll(Vector((1, 0, 0)))  # bone X axis -> character's left, so locked-track twist starts neutral
        if p:
            b.parent = eb[p]
            b.use_connect = n not in ("thigh.L", "thigh.R", "clav.L", "clav.R")
    bpy.ops.object.mode_set(mode="OBJECT")
    _skin(obj, J)
    obj.parent = arm
    mod = obj.modifiers.new("Armature", "ARMATURE")
    mod.object = arm
    return arm


def _seg_dist(P, a, b):
    ab = b - a
    t = np.clip(((P - a) @ ab) / max(ab @ ab, 1e-9), 0, 1)
    return np.linalg.norm(P - (a + t[:, None] * ab), axis=1)


def _skin(obj, J):
    """Distance-to-bone skinning with sharp falloff + neighbourhood smoothing (bone heat fails on these sculpts)."""
    me = obj.data
    P = np.array([v.co[:] for v in me.vertices])
    names = [b[0] for b in BONES]
    D = np.stack([_seg_dist(P, np.array(J[h][:]), np.array(J[t][:])) for (n, h, t, p) in BONES], 1)
    # keep limbs separate: a left-side vertex never takes right-side bones and vice versa
    side = np.where(P[:, 1] > 0.02, 1, np.where(P[:, 1] < -0.02, -1, 0))
    for i, n in enumerate(names):
        if n.endswith(".L"):
            D[side == -1, i] = 1e3
        elif n.endswith(".R"):
            D[side == 1, i] = 1e3
    # clavicles only influence the shoulder top a little
    for i, n in enumerate(names):
        if n.startswith("clav"):
            D[:, i] *= 1.6
    W = 1.0 / np.maximum(D, 0.004) ** 5
    W /= W.sum(1, keepdims=True)
    # neighbour smoothing (graph Laplacian) for soft joints
    bm = bmesh.new()
    bm.from_mesh(me)
    edges = np.array([(e.verts[0].index, e.verts[1].index) for e in bm.edges])
    bm.free()
    n = len(P)
    for _ in range(6):
        acc = np.zeros_like(W)
        cnt = np.zeros(n)
        np.add.at(acc, edges[:, 0], W[edges[:, 1]])
        np.add.at(acc, edges[:, 1], W[edges[:, 0]])
        np.add.at(cnt, edges[:, 0], 1)
        np.add.at(cnt, edges[:, 1], 1)
        W = 0.5 * W + 0.5 * acc / np.maximum(cnt, 1)[:, None]
    W[W < 0.01] = 0
    W /= W.sum(1, keepdims=True)
    for i, nme in enumerate(names):
        g = obj.vertex_groups.new(name=nme)
        idx = np.nonzero(W[:, i] > 0)[0]
        for k in idx:
            g.add([int(k)], float(W[k, i]), "REPLACE")


# ------------------------------------------------------------------ retarget mocap onto this body

CHAINS = [  # (mocap from, mocap to, body from, body to)
    ("Hips", "Spine1", "pelvis", "chest"), ("Spine1", "Neck1", "chest", "neck"), ("Neck1", "Head", "neck", "head"),
    ("Head", "Head_end", "head", "headtop"),
    ("Hips", "LeftUpLeg", "pelvis", "hipL"), ("LeftUpLeg", "LeftLeg", "hipL", "kneeL"),
    ("LeftLeg", "LeftFoot", "kneeL", "ankleL"), ("LeftFoot", "LeftToeBase", "ankleL", "ballL"),
    ("LeftToeBase", "LeftToeBase_end", "ballL", "toeL"),
    ("Hips", "RightUpLeg", "pelvis", "hipR"), ("RightUpLeg", "RightLeg", "hipR", "kneeR"),
    ("RightLeg", "RightFoot", "kneeR", "ankleR"), ("RightFoot", "RightToeBase", "ankleR", "ballR"),
    ("RightToeBase", "RightToeBase_end", "ballR", "toeR"),
    ("Spine1", "LeftArm", "chest", "shoulderL"), ("LeftArm", "LeftForeArm", "shoulderL", "elbowL"),
    ("LeftForeArm", "LeftHand", "elbowL", "wristL"), ("LeftHand", "LeftHandIndex1", "wristL", "fingerL"),
    ("Spine1", "RightArm", "chest", "shoulderR"), ("RightArm", "RightForeArm", "shoulderR", "elbowR"),
    ("RightForeArm", "RightHand", "elbowR", "wristR"), ("RightHand", "RightHandIndex1", "wristR", "fingerR"),
]


def _retarget(M, J):
    """Body-proportioned joint targets: directions from mocap, lengths from the body."""
    T = {"pelvis": Vector((0, 0, J["pelvis"].z))}
    for mf, mt, bf, bt in CHAINS:
        if mt not in M:
            mt = mt.replace("_end", "")
        d = (M[mt] - M[mf])
        if d.length < 1e-6:
            d = J[bt] - J[bf]
        if bf in ("chest",) and bt.startswith("shoulder"):
            T[bt] = T[bf] + d.normalized() * (J[bt] - J[bf]).length
        else:
            T[bt] = T[bf] + d.normalized() * (J[bt] - J[bf]).length
    # spine midpoint for the spine bone
    T["spine"] = T["pelvis"].lerp(T["chest"], 0.47)
    return T


def _pose(arm, T):
    """Aim every bone at its retargeted tail; twist pelvis/chest by the hip/shoulder lines."""
    tg = {}
    for k, v in T.items():
        e = bpy.data.objects.new(f"_t_{arm.name}_{k}", None)
        e.location = v
        bpy.context.scene.collection.objects.link(e)
        tg[k] = e
    pb = arm.pose.bones
    c = pb["pelvis"].constraints.new("COPY_LOCATION")
    c.target = tg["pelvis"]
    for n, h, t, p in BONES:
        if n == "spine":
            t = "chest"
        d = pb[n].constraints.new("DAMPED_TRACK")
        d.target = tg[t]
        if n in ("pelvis", "chest"):
            lt = pb[n].constraints.new("LOCKED_TRACK")
            lt.target = tg["hipL" if n == "pelvis" else "shoulderL"]
            lt.track_axis = "TRACK_X"
            lt.lock_axis = "LOCK_Y"
    bpy.context.view_layer.update()
    return tg


# ------------------------------------------------------------------ clothing via region weights


def _region_weights(obj):
    """Per-vertex weights summed over bone groups."""
    vg = {g.index: g.name for g in obj.vertex_groups}
    n = len(obj.data.vertices)
    W = {}
    for v in obj.data.vertices:
        for g in v.groups:
            W.setdefault(vg[g.group], np.zeros(n))[v.index] = g.weight
    z = np.zeros(n)
    return lambda *names: sum((W.get(nm, z) for nm in names), z.copy())


def _clothe(obj, outfit, rng):
    """Inflate + smooth clothed regions (hides anatomy, reads as fabric), feet become shoes, head gets hair."""
    R = _region_weights(obj)
    sleeve = outfit.get("sleeves", "long")
    torso = R("pelvis", "spine", "chest", "clav.L", "clav.R")
    legs = R("thigh.L", "thigh.R") + R("shin.L", "shin.R") * (1.0 if outfit.get("trousers", True) else 0.0)
    arms_u = R("upper_arm.L", "upper_arm.R")
    arms_f = R("forearm.L", "forearm.R") * (1.0 if sleeve == "long" else 0.0)
    cloth = np.clip(torso + legs + arms_u + arms_f, 0, 1)
    # crisp cuffs: push weights toward 0/1
    cloth = np.clip((cloth - 0.35) * 3.0, 0, 1)
    feet = np.clip((R("foot.L", "foot.R", "toe.L", "toe.R") - 0.3) * 3, 0, 1)
    headw = R("head")
    co = np.array([v.co[:] for v in obj.data.vertices])
    hz = co[:, 2]
    hair = np.zeros(len(co))
    if outfit.get("hair", True):
        Hz = hz.max()
        hair = np.clip((hz - (Hz - 0.13 + outfit.get("hairline", 0.0))) / 0.03, 0, 1) * (headw > 0.5)
    for name, w in (("cloth", cloth), ("shoes", feet), ("hair", hair)):
        g = obj.vertex_groups.new(name="_" + name)
        for i in np.nonzero(w > 0.001)[0]:
            g.add([int(i)], float(w[i]), "REPLACE")
    d = obj.modifiers.new("cloth_d", "DISPLACE")
    d.strength = outfit.get("bulk", 0.014)
    d.mid_level = 0
    d.vertex_group = "_cloth"
    s = obj.modifiers.new("cloth_s", "SMOOTH")
    s.factor = 0.9
    s.iterations = 18
    s.vertex_group = "_cloth"
    d2 = obj.modifiers.new("shoe_d", "DISPLACE")
    d2.strength = 0.012
    d2.mid_level = 0
    d2.vertex_group = "_shoes"
    s2 = obj.modifiers.new("shoe_s", "SMOOTH")
    s2.factor = 1.0
    s2.iterations = 30
    s2.vertex_group = "_shoes"
    if outfit.get("hair", True):
        d3 = obj.modifiers.new("hair_d", "DISPLACE")
        d3.strength = outfit.get("hair_vol", 0.012)
        d3.mid_level = 0
        d3.vertex_group = "_hair"
        s3 = obj.modifiers.new("hair_s", "SMOOTH")
        s3.factor = 1.0
        s3.iterations = 12
        s3.vertex_group = "_hair"


# ------------------------------------------------------------------ child proportions


def _childify(me, J, age_h):
    """Re-proportion an adult: bigger head, shorter legs, slimmer; then scale to target height."""
    H = J["_H"]
    neck_z = J["neck"].z
    hip_z = J["pelvis"].z

    def f(p):
        p = p.copy()
        if p.z > neck_z:  # head ~25% larger about the neck base
            c = Vector((J["neck"].x, 0, neck_z))
            p = c + (p - c) * 1.28
        elif p.z < hip_z:  # legs 12% shorter
            p.z *= 0.88
            p.z += hip_z * 0.0
        if p.z >= hip_z * 0.88 and p.z <= neck_z:
            p.z = hip_z * 0.88 + (p.z - hip_z) * 0.97
        # slimmer torso/limbs
        p.x *= 0.92
        p.y *= 0.92
        return p

    for v in me.vertices:
        v.co = f(v.co)
    J2 = {k: (f(v) if isinstance(v, Vector) else v) for k, v in J.items()}
    newH = max(v.co.z for v in me.vertices)
    s = age_h / newH
    me.transform(Matrix.Diagonal((s, s, s, 1)))
    J2 = {k: (v * s if isinstance(v, Vector) else v) for k, v in J2.items()}
    J2["_H"] = age_h
    return J2


# ------------------------------------------------------------------ main entry


def make_human(name, sex=None, age="adult", mode="casual", weapon=None, soldier=None, coll=None,
               accent=(0.95, 0.38, 0.06), pick=None, height=None, outfit=None,
               body_col=(0.86, 0.85, 0.83), gun_col=(0.035, 0.037, 0.04), keep_rig=False):
    coll = coll or bpy.context.scene.collection
    rng = random.Random(zlib.crc32(name.encode()))
    sex = sex or rng.choice(["male", "female"])
    soldier = (weapon is not None) if soldier is None else soldier
    me0, J0 = _load_base(sex)
    me = me0.copy()
    J = dict(J0)
    if age == "child":
        J = _childify(me, J, height or rng.uniform(1.05, 1.45))
    else:
        target = height or (rng.uniform(1.72, 1.9) if sex == "male" else rng.uniform(1.6, 1.75))
        s = target / J["_H"]
        bulk_x = rng.uniform(0.94, 1.1)  # build variation
        me.transform(Matrix.Diagonal((s * bulk_x, s * bulk_x, s, 1)))
        J = {k: (Vector((v.x * s * bulk_x, v.y * s * bulk_x, v.z * s)) if isinstance(v, Vector) else v)
             for k, v in J.items()}
        J["_H"] = target
    obj = bpy.data.objects.new(name, me)
    coll.objects.link(obj)

    lib_ = {"casual": CASUAL, "walk": WALK, "talk": TALK}[mode]
    clip, t = pick or lib_[rng.randrange(len(lib_))]
    t = min(0.95, max(0.05, t + rng.uniform(-0.08, 0.08)))
    M = mocap.pose(clip, t, J["_H"])
    T = _retarget(M, J)

    # weapon handling adjusts the arm targets before posing
    gear = []
    gun = pbr("FigGun", gun_col, rough=0.45)
    acc = pbr(f"FigAcc_{accent}", accent, rough=0.5)
    Rc = _frame(Vector(), T["shoulderL"] - T["shoulderR"], T["neck"] - T["spine"])
    chest_c = T["chest"].lerp(T["neck"], 0.2)
    if weapon == "held":
        pitch = math.radians(rng.uniform(22, 40))
        ryaw = math.radians(rng.uniform(8, 22))
        butt = chest_c + Rc @ Vector((0.12, -0.16, 0.06))
        fwd = Rc @ Vector((1, 0, 0))
        Mr = Matrix.Translation(butt) @ Euler((0, pitch, math.atan2(fwd.y, fwd.x) + ryaw)).to_matrix().to_4x4()
        g = carbine(f"{name}_rifle", coll, gun)
        g.data.transform(Mr)
        gear.append(g)
        for side, tgt in (("R", Mr @ GRIP), ("L", Mr @ FOREGRIP)):
            s_, e_, w_ = T[f"shoulder{side}"], T[f"elbow{side}"], T[f"wrist{side}"]
            ua, fa = (J[f"elbow{side}"] - J[f"shoulder{side}"]).length, (J[f"wrist{side}"] - J[f"elbow{side}"]).length
            el, hand = _two_bone(s_, tgt, ua, fa, e_ + (e_ - (s_ + w_) / 2) * 2 + Vector((0, 0, -0.3)))
            fdir = (tgt + Mr.to_3x3() @ Vector((0.06, 0, 0)) - hand)
            T[f"elbow{side}"], T[f"wrist{side}"] = el, hand
            T[f"finger{side}"] = hand + (hand - el).normalized() * 0.09
    elif weapon == "slung":
        d = Rc @ Vector((0.3, 0.55, -0.78))
        top = Rc @ Vector((1, 0, 0.2))
        yv = top.cross(d).normalized()
        Rr = Matrix((d.normalized(), yv, d.normalized().cross(yv))).transposed()
        Mr = Matrix.Translation(chest_c + Rc @ Vector((0.17, -0.19, 0.04))) @ Rr.to_4x4()
        g = carbine(f"{name}_rifle", coll, gun)
        g.data.transform(Mr)
        gear += [g, _capsule(f"{name}_sling", Mr @ Vector((0.05, 0, 0)), T["shoulderL"] + Vector((0, 0, 0.05)), 0.012, 0.012, coll, gun),
                 _capsule(f"{name}_sling2", T["shoulderL"] + Vector((0, 0, 0.05)), Mr @ Vector((0.7, 0, 0)), 0.012, 0.012, coll, gun)]
    elif weapon == "one_hand":
        w_, f_ = T["wristR"], T["fingerR"]
        fwd = Rc @ Vector((1, 0, 0))
        R = Euler((0, math.radians(55), math.atan2(fwd.y, fwd.x))).to_matrix().to_4x4()
        Mr = Matrix.Translation(w_.lerp(f_, 0.45)) @ R @ Matrix.Translation(-GRIP)
        g = carbine(f"{name}_rifle", coll, gun)
        g.data.transform(Mr)
        gear.append(g)

    arm = _rig(obj, J)
    outfit = dict(outfit or {})
    outfit.setdefault("sleeves", rng.choice(["long", "long", "short"]) if not soldier else "long")
    outfit.setdefault("hairline", rng.uniform(-0.02, 0.03) if sex == "male" else rng.uniform(-0.05, -0.01))
    outfit.setdefault("hair_vol", 0.01 if sex == "male" else 0.022)
    outfit.setdefault("bulk", 0.016 if soldier else rng.uniform(0.01, 0.016))
    if not outfit.get("none"):
        _clothe(obj, outfit, rng)
    tg = _pose(arm, T)
    # bake: armature first, then clothing modifiers already on the stack (armature added by parent_set is first)
    mods = obj.modifiers
    arm_mod = [m for m in mods if m.type == "ARMATURE"][0]
    if mods[0] != arm_mod:
        mods.move(mods.find(arm_mod.name), 0)
    apply_mods(obj)
    obj.parent = None
    obj.matrix_world = Matrix.Identity(4)
    if not keep_rig:
        for e in tg.values():
            bpy.data.objects.remove(e)
        bpy.data.objects.remove(arm)
    # ground the lowest point
    zmin = min(v.co.z for v in obj.data.vertices)
    obj.data.transform(Matrix.Translation((0, 0, -zmin)))
    for g in gear:
        g.data.transform(Matrix.Translation((0, 0, -zmin)))
    for k in T:
        T[k] = T[k] - Vector((0, 0, zmin))

    obj.data.materials.clear()
    obj.data.materials.append(pbr(f"Fig_{body_col}", body_col, rough=0.55))
    for p in obj.data.polygons:
        p.use_smooth = True

    if soldier:
        vestm = pbr(f"FigVest_{body_col}", tuple(c * 0.9 for c in body_col), rough=0.7)
        Rc = _frame(Vector(), T["shoulderL"] - T["shoulderR"], T["neck"] - T["spine"])
        cc = T["chest"].lerp(T["neck"], 0.15)
        for k, xx in enumerate((1, -1)):
            pl = box(f"{name}_plate{k}", (0.05, 0.28, 0.3), (0, 0, 0), coll, 0.02, vestm)
            depth = 0.11 if xx > 0 else 0.1
            pl.data.transform(Matrix.Translation(cc + Rc @ Vector((xx * depth, 0, -0.06))) @ Rc.to_4x4())
            gear.append(pl)
        for i, yy in enumerate((-0.085, 0.0, 0.085)):
            po = box(f"{name}_pouch{i}", (0.045, 0.065, 0.085), (0, 0, 0), coll, 0.01, vestm)
            po.data.transform(Matrix.Translation(cc + Rc @ Vector((0.15, yy, -0.14))) @ Rc.to_4x4())
            gear.append(po)
        Rh = _frame(Vector(), T["shoulderL"] - T["shoulderR"], T["headtop"] - T["head"])
        hc = T["head"].lerp(T["headtop"], 0.55)
        hm = _ellipsoid(f"{name}_helmet", Vector(), (0.135, 0.125, 0.12), coll, acc)
        hm.data.transform(Matrix.Translation(hc + Rh @ Vector((-0.015, 0, 0.0))) @ Rh.to_4x4())
        lim_c = hc + Rh @ Vector((0, 0, -0.035))
        nz = Rh @ Vector((0, 0, 1))
        for v in hm.data.vertices:
            rel = v.co - lim_c
            front = max(0.0, (Rh.transposed() @ rel).x / 0.13)
            if rel.dot(nz) < 0.05 * front:
                v.co -= nz * (rel.dot(nz) - 0.05 * front)
        gear.append(hm)
        ua0, ua1 = T["shoulderL"], T["elbowL"]
        gear.append(_capsule(f"{name}_band", ua0.lerp(ua1, 0.42), ua0.lerp(ua1, 0.6), 0.058, 0.055, coll, acc))
    if gear:
        obj = join([obj] + gear, name)
        gi = {i for i, m in enumerate(obj.data.materials) if m == gun}
        for p in obj.data.polygons:
            p.use_smooth = p.material_index not in gi
    obj["clip"] = f"{clip}@{t:.2f}"
    obj["sex"], obj["age"] = sex, age
    return obj
