"""People via MakeHuman (MPFB2, CC0 assets): proper body shapes, professional skin weights,
CC0 clothes/hair/shoes, posed from CMU motion capture through MakeHuman's CMU-matching rig.

make_person(name, sex, age, build, mode, outfit..., weapon) -> one baked static mesh (+gear),
facing +X, feet on z=0.

Requires the MPFB extension installed for Blender 4.2 (see setup_mpfb.sh).
"""
import os
import math
import zlib
import random
import importlib
import bpy
from mathutils import Vector, Matrix, Euler
from lib import pbr, join, apply_mods, box
from figure import _capsule, _ellipsoid, carbine, GRIP, FOREGRIP
import mocap
from mfigure import CASUAL, WALK, TALK, TACTICAL, _frame

MP = "bl_ext.user_default.mpfb"
_ready = {}


def _mpfb():
    if not _ready:
        bpy.ops.preferences.addon_enable(module=MP)
        _ready["HS"] = importlib.import_module(MP + ".services.humanservice").HumanService
        _ready["LS"] = importlib.import_module(MP + ".services.locationservice").LocationService
        _ready["OS"] = importlib.import_module(MP + ".services.objectservice").ObjectService
        _ready["TS"] = importlib.import_module(MP + ".services.targetservice").TargetService
    return _ready


def _asset(kind, name):
    d = os.path.join(_mpfb()["LS"].get_user_data(), kind, name)
    return os.path.join(d, name + ".mhclo")


OUTFITS = {
    "male": ["male_casualsuit01", "male_casualsuit02", "male_casualsuit03", "male_casualsuit04",
             "male_casualsuit05", "male_casualsuit06", "male_worksuit01", "male_elegantsuit01"],
    "female": ["female_casualsuit01", "female_casualsuit02", "female_sportsuit01", "female_elegantsuit01"],
}
HAIR = {"male": ["short01", "short02", "short03", "short04", "afro01", None],
        "female": ["bob01", "bob02", "ponytail01", "long01", "braid01", "short02"]}
SHOES = ["shoes01", "shoes02", "shoes03", "shoes04", "shoes05", "shoes06"]

LEAF_END = {"Head": "Head_end", "LeftToeBase": "LeftToeBase_end", "RightToeBase": "RightToeBase_end",
            "LeftHandFinger1": "LeftHandIndex1_end", "RightHandFinger1": "RightHandIndex1_end",
            "LThumb": "LThumb_end", "RThumb": "RThumb_end"}
MOCAP_NAME = {"LeftHandFinger1": "LeftHandIndex1", "RightHandFinger1": "RightHandIndex1"}


def _make_body(sex, age, build, rng, height=None):
    S = _mpfb()
    HS = S["HS"]
    macros = S["TS"].get_default_macro_info_dict()
    macros["gender"] = 1.0 if sex == "male" else 0.0
    # MakeHuman age: 0 = 1 yr, 0.1875 = 11 yrs, 0.5 = 25 yrs, 1 = 90 yrs
    macros["age"] = {"child": rng.uniform(0.12, 0.2), "teen": rng.uniform(0.25, 0.33),
                     "adult": rng.uniform(0.45, 0.62), "older": rng.uniform(0.75, 0.9)}[age]
    w, m = {"slim": (0.3, 0.45), "average": (0.5, 0.5), "heavy": (0.8, 0.45), "athletic": (0.45, 0.8)}[build]
    macros["weight"] = min(1, max(0, w + rng.uniform(-0.08, 0.08)))
    macros["muscle"] = min(1, max(0, m + rng.uniform(-0.08, 0.08)))
    macros["height"] = height if height is not None else rng.uniform(0.35, 0.7)
    macros["proportions"] = rng.uniform(0.4, 0.7)
    r = [rng.random() for _ in range(3)]
    macros["race"] = {"asian": r[0] / sum(r), "caucasian": r[1] / sum(r), "african": r[2] / sum(r)}
    body = HS.create_human(mask_helpers=True, detailed_helpers=True, extra_vertex_groups=True,
                           feet_on_ground=True, scale=0.1, macro_detail_dict=macros)
    return body


def _dress(body, sex, age, outfit, rng):
    HS = _mpfb()["HS"]
    items = []
    o = outfit or {}
    suit = o.get("suit", rng.choice(OUTFITS[sex]))
    if age == "child":  # adult outfits refit to children well enough in white
        suit = o.get("suit", rng.choice(OUTFITS["male" if sex == "male" else "female"][:4]))
    hair = o.get("hair", rng.choice(HAIR[sex]))
    shoes = o.get("shoes", rng.choice(SHOES))
    for kind, n in (("clothes", suit), ("clothes", shoes), ("hair", hair)):
        if not n:
            continue
        p = _asset(kind, n)
        if os.path.exists(p):
            items.append(HS.add_mhclo_asset(p, body, asset_type="Clothes" if kind == "clothes" else "Hair",
                                            subdiv_levels=0, material_type="MAKESKIN"))
    eyes = os.path.join(_mpfb()["LS"].get_user_data(), "eyes", "low-poly", "low-poly.mhclo")
    if os.path.exists(eyes):
        items.append(HS.add_mhclo_asset(eyes, body, asset_type="Eyes", subdiv_levels=0, material_type="MAKESKIN"))
    if o.get("hat"):
        items.append(HS.add_mhclo_asset(_asset("clothes", o["hat"]), body, asset_type="Clothes", subdiv_levels=0,
                                        material_type="MAKESKIN"))
    return [i for i in items if i]


UPRIGHT = {"LowerBack": 0.35, "Spine": 0.45, "Spine1": 0.5, "Neck": 0.75, "Neck1": 0.8, "Head": 0.8}
FINGER_CURL = {"LeftFingerBase": 0.35, "RightFingerBase": 0.35, "LeftHandFinger1": 0.7, "RightHandFinger1": 0.7,
               "LThumb": 0.25, "RThumb": 0.25}
KEEP_REST = {"LHipJoint", "RHipJoint", "LeftShoulder", "RightShoulder", "LThumb", "RThumb",
             "LeftFingerBase", "RightFingerBase", "LeftHandFinger1", "RightHandFinger1"}


def _mocap_key(n):
    return MOCAP_NAME.get(n, n)


def _pose_rig(rig, M):
    """Walk the hierarchy: aim each bone along the mocap direction of its own segment, placing the aim
    point at the bone's CURRENT posed head + direction * bone length (so body proportions are kept)."""
    bones = rig.data.bones
    pb = rig.pose.bones
    tg = {}

    def empty(key):
        e = bpy.data.objects.new(f"_t_{rig.name}_{key}", None)
        bpy.context.scene.collection.objects.link(e)
        tg[key] = e
        return e

    def seg_dir(b):
        kids = [ch for ch in b.children if (ch.head_local - b.tail_local).length < 1e-3]
        a = _mocap_key(b.name)
        z = _mocap_key(kids[0].name) if kids else LEAF_END.get(b.name)
        if a not in M or not z or z not in M:
            return None
        d = M[z] - M[a]
        return d.normalized() if d.length > 1e-6 else None

    order = []

    def walk(b):
        order.append(b)
        for c in b.children:
            walk(c)
    for b in bones:
        if b.parent is None:
            walk(b)
    twist = {"Hips": ("LeftUpLeg", "Hips"), "LowerBack": ("LeftUpLeg", "Hips"), "Spine1": ("LeftArm", "Spine1")}
    for b in order:
        if b.name in KEEP_REST:  # structural bones keep the body's own shape (no hunched shoulders / knock knees)
            continue
        d = seg_dir(b)
        if d is None:
            continue
        # damp lean: spine follows mocap partly, neck/head stay mostly upright (mocap head data is noisy)
        upright = UPRIGHT.get(b.name, 0.0)
        if upright:
            d = (d * (1 - upright) + Vector((0, 0, 1)) * upright).normalized()
        bpy.context.view_layer.update()
        head_w = rig.matrix_world @ pb[b.name].head
        e = empty(b.name)
        e.location = head_w + d * b.length
        c = pb[b.name].constraints.new("DAMPED_TRACK")
        c.target = e
        if b.name in twist and twist[b.name][0] in M:
            lj, rj = twist[b.name]
            side = M[lj] - M[rj] if lj != "LeftArm" else M["LeftArm"] - M["RightArm"]
            rest = b.matrix_local.to_3x3()
            lw = rig.matrix_world.to_3x3() @ (bones["LeftUpLeg" if lj == "LeftUpLeg" else "LeftArm"].head_local - b.head_local)
            if lj == "LeftArm":
                lw = rig.matrix_world.to_3x3() @ (bones["LeftArm"].head_local - bones["RightArm"].head_local)
            else:
                lw = rig.matrix_world.to_3x3() @ (bones["LeftUpLeg"].head_local - bones["RightUpLeg"].head_local)
            R = rig.matrix_world.to_3x3() @ rest
            cands = {"TRACK_X": R.col[0], "TRACK_NEGATIVE_X": -R.col[0], "TRACK_Z": R.col[2], "TRACK_NEGATIVE_Z": -R.col[2]}
            ax = max(cands, key=lambda k: cands[k].normalized().dot(lw.normalized()))
            e2 = empty(b.name + "_tw")
            e2.location = head_w + side.normalized() * 0.3
            lt = pb[b.name].constraints.new("LOCKED_TRACK")
            lt.target, lt.track_axis, lt.lock_axis = e2, ax, "LOCK_Y"
    # relaxed hands: curl finger bones about their local X axis (sign chosen per side so they close inward)
    from mathutils import Quaternion
    for bn, ang in FINGER_CURL.items():
        if bn in pb:
            pb[bn].rotation_mode = "QUATERNION"
            pb[bn].rotation_quaternion = Quaternion((1, 0, 0), ang * CURL_SIGN)
    bpy.context.view_layer.update()
    return tg


CURL_SIGN = 1.0


def _soldier_kit(name, coll, baked, JW, acc):
    """Plate carrier fitted to the measured chest surface, helmet fitted to the measured head."""
    import numpy as np
    P = np.concatenate([np.array([v.co[:] for v in o.data.vertices]) for o in baked[:2]])  # body + main outfit
    Rc = _frame(Vector(), JW["LeftArm"] - JW["RightArm"], JW["Neck"] - JW["Spine"])
    fx, fy, fz = (np.array(Rc.col[i][:]) for i in range(3))
    cc = JW["Spine1"].lerp(JW["Neck"], 0.35)
    rel = P - np.array(cc[:])
    u, v_, w = rel @ fx, rel @ fy, rel @ fz
    # narrow sternum/spine column only (arms and hands excluded), robust percentiles
    band = (w > -0.16) & (w < 0.04) & (np.abs(v_) < 0.06) & (np.abs(u) < 0.25)
    if band.sum() > 20:
        front = float(np.percentile(u[band][u[band] > 0], 92)) if (u[band] > 0).any() else 0.11
        back = float(np.percentile(u[band][u[band] < 0], 8)) if (u[band] < 0).any() else -0.1
    else:
        front, back = 0.11, -0.1
    vestm = pbr("FigVest", (0.62, 0.62, 0.6), rough=0.75)
    out = []
    for k, (x, th) in enumerate(((front + 0.012, 0.035), (back - 0.012, 0.035))):
        pl = box(f"{name}_plate{k}", (th, 0.27, 0.3), (0, 0, 0), coll, 0.015, vestm)
        pl.data.transform(Matrix.Translation(cc + Rc @ Vector((x, 0, -0.07))) @ Rc.to_4x4())
        out.append(pl)
    for i, yy in enumerate((-0.08, 0.0, 0.08)):
        po = box(f"{name}_pouch{i}", (0.04, 0.062, 0.08), (0, 0, 0), coll, 0.01, vestm)
        po.data.transform(Matrix.Translation(cc + Rc @ Vector((front + 0.045, yy, -0.15))) @ Rc.to_4x4())
        out.append(po)
    # helmet: sphere fit to head points above the neck joint
    hd0, hd1 = JW["Head"], JW["HeadTop"]
    up = (hd1 - hd0).normalized()
    relh = P - np.array(hd0[:])
    hpts = P[(relh @ np.array(up[:]) > 0.02) & (np.linalg.norm(relh, axis=1) < 0.26)]
    hc = Vector(hpts.mean(0)) if len(hpts) else hd0.lerp(hd1, 0.6)
    top = max((Vector(p) - hc).dot(up) for p in hpts) if len(hpts) else 0.12
    Rh = _frame(Vector(), JW["LeftArm"] - JW["RightArm"], up)
    hm = _ellipsoid(f"{name}_helmet", Vector(), (0.135, 0.125, 0.12), coll, acc)
    centre = hc + up * (top - 0.105)
    hm.data.transform(Matrix.Translation(centre + Rh @ Vector((-0.01, 0, 0))) @ Rh.to_4x4())
    lim_c = centre + up * -0.03
    for v in hm.data.vertices:
        r = v.co - lim_c
        front_f = max(0.0, (Rh.transposed() @ r).x / 0.13)
        if r.dot(up) < 0.05 * front_f:
            v.co -= up * (r.dot(up) - 0.05 * front_f)
    out.append(hm)
    a0, a1 = JW["LeftArm"], JW["LeftForeArm"]
    out.append(_capsule(f"{name}_band", a0.lerp(a1, 0.4), a0.lerp(a1, 0.58), 0.06, 0.056, coll, acc))
    return out


def make_person(name, sex=None, age="adult", build=None, mode="casual", weapon=None, soldier=None,
                coll=None, accent=(0.95, 0.38, 0.06), pick=None, outfit=None, height=None,
                skin_col=(0.86, 0.85, 0.83), cloth_cols=None, gun_col=(0.035, 0.037, 0.04)):
    coll = coll or bpy.context.scene.collection
    rng = random.Random(zlib.crc32(name.encode()))
    sex = sex or rng.choice(["male", "female"])
    build = build or rng.choice(["slim", "average", "average", "heavy", "athletic"])
    soldier = (weapon is not None) if soldier is None else soldier
    S = _mpfb()
    body = _make_body(sex, age, build, rng, height)
    if soldier:
        outfit = dict(outfit or {})
        outfit.setdefault("suit", "male_worksuit01" if sex == "male" else "female_sportsuit01")
        outfit.setdefault("hair", "short02" if sex == "male" else "short02")
        outfit.setdefault("shoes", "shoes06")
    rig = _mpfb()["HS"].add_builtin_rig(body, "cmu_mb", import_weights=True)
    items = _dress(body, sex, age, outfit, rng)  # after the rig, so clothes get bound to it
    # face +X: MakeHuman characters face -Y
    rig.rotation_euler = (0, 0, math.radians(90))
    bpy.context.view_layer.update()

    lib_ = {"casual": CASUAL, "walk": WALK, "talk": TALK, "tactical": TACTICAL}[mode]
    clip, t = pick or lib_[rng.randrange(len(lib_))]
    t = min(0.95, max(0.05, t + rng.uniform(-0.03, 0.03)))
    hz = (rig.matrix_world @ rig.data.bones["Head"].tail_local).z
    M = mocap.pose(clip, t, hz / 0.97)
    tg = _pose_rig(rig, M)

    gear = []
    gun = pbr("FigGun", gun_col, rough=0.45)
    acc = pbr(f"FigAcc_{accent}", accent, rough=0.5)

    def wpos(bn, tail=False):
        b = rig.pose.bones[bn]
        return rig.matrix_world @ (b.tail if tail else b.head)

    if weapon:
        shL, shR = wpos("LeftArm"), wpos("RightArm")
        neck, spine = wpos("Neck"), wpos("Spine")
        Rc = _frame(Vector(), shL - shR, neck - spine)
        chest_c = wpos("Spine1").lerp(neck, 0.5)
        if weapon == "held":
            pitch = math.radians(rng.uniform(22, 38))
            ryaw = math.radians(rng.uniform(8, 20))
            butt = chest_c + Rc @ Vector((0.13, -0.16, 0.05))
            fwd = Rc @ Vector((1, 0, 0))
            Mr = Matrix.Translation(butt) @ Euler((0, pitch, math.atan2(fwd.y, fwd.x) + ryaw)).to_matrix().to_4x4()
            g = carbine(f"{name}_rifle", coll, gun)
            g.data.transform(Mr)
            gear.append(g)
            for side, tgt in (("Right", Mr @ GRIP), ("Left", Mr @ FOREGRIP)):
                fa = rig.pose.bones[f"{side}ForeArm"]
                for c in list(fa.constraints):
                    fa.constraints.remove(c)
                for c in list(rig.pose.bones[f"{side}Arm"].constraints):
                    rig.pose.bones[f"{side}Arm"].constraints.remove(c)
                e = bpy.data.objects.new(f"_ik_{name}_{side}", None)
                e.location = tgt
                bpy.context.scene.collection.objects.link(e)
                pole = bpy.data.objects.new(f"_pole_{name}_{side}", None)
                sgn = 1 if side == "Left" else -1
                pole.location = wpos(f"{side}Arm") + Rc @ Vector((-0.3, sgn * 0.5, -0.6))
                bpy.context.scene.collection.objects.link(pole)
                ik = fa.constraints.new("IK")
                ik.target, ik.pole_target, ik.chain_count = e, pole, 2
                ik.pole_angle = math.radians(-90)
                tg[e.name], tg[pole.name] = e, pole
        elif weapon == "slung":
            d = Rc @ Vector((0.3, 0.55, -0.78))
            top = Rc @ Vector((1, 0, 0.2))
            yv = top.cross(d).normalized()
            Rr = Matrix((d.normalized(), yv, d.normalized().cross(yv))).transposed()
            Mr = Matrix.Translation(chest_c + Rc @ Vector((0.19, -0.19, 0.03))) @ Rr.to_4x4()
            g = carbine(f"{name}_rifle", coll, gun)
            g.data.transform(Mr)
            gear += [g, _capsule(f"{name}_sling", Mr @ Vector((0.05, 0, 0)), shL + Vector((0, 0, 0.06)), 0.012, 0.012, coll, gun),
                     _capsule(f"{name}_sling2", shL + Vector((0, 0, 0.06)), Mr @ Vector((0.7, 0, 0)), 0.012, 0.012, coll, gun)]
        bpy.context.view_layer.update()
        if weapon == "one_hand":
            w_, f_ = wpos("RightHand"), wpos("RightHand", tail=True)
            fwd = Rc @ Vector((1, 0, 0))
            R = Euler((0, math.radians(55), math.atan2(fwd.y, fwd.x))).to_matrix().to_4x4()
            Mr = Matrix.Translation(w_.lerp(f_, 0.5)) @ R @ Matrix.Translation(-GRIP)
            g = carbine(f"{name}_rifle", coll, gun)
            g.data.transform(Mr)
            gear.append(g)

    # remember joints for gear placement after baking
    bpy.context.view_layer.update()
    JW = {n: wpos(n) for n in ("LeftArm", "RightArm", "Neck", "Spine", "Spine1", "Head", "LeftForeArm")}
    JW["HeadTop"] = wpos("Head", tail=True)

    # bake every deformed mesh (body + clothes + hair) to static geometry
    bpy.context.view_layer.update()
    meshes = [body] + items
    baked = []
    dg = bpy.context.evaluated_depsgraph_get()
    skin = pbr(f"FigSkin_{skin_col}", skin_col, rough=0.55)
    cols = cloth_cols or [(0.8, 0.79, 0.77), (0.72, 0.72, 0.71), (0.66, 0.66, 0.65)]
    for i, m in enumerate(meshes):
        ev = m.evaluated_get(dg)
        me = bpy.data.meshes.new_from_object(ev)
        o = bpy.data.objects.new(f"{name}_{i}", me)
        coll.objects.link(o)
        o.matrix_world = m.matrix_world.copy()
        me.materials.clear()
        if i == 0:
            me.materials.append(skin)
        else:
            nm = m.name.lower()
            c = (0.5, 0.49, 0.47) if any(k in nm for k in ("hair", "short", "bob", "long", "braid", "afro", "ponytail")) \
                else ((0.9, 0.9, 0.9) if "low-poly" in nm else cols[(i - 1) % len(cols)])
            me.materials.append(pbr(f"FigCloth_{c}", c, rough=0.75))
        for p in me.polygons:
            p.use_smooth = True
        me.transform(o.matrix_world)
        o.matrix_world = Matrix.Identity(4)
        baked.append(o)
    # clean up the MakeHuman objects, rig and target empties
    doomed = {o.name for o in [rig] + meshes + list(tg.values()) + list(rig.children_recursive) if o}
    for n in doomed:
        if n in bpy.data.objects:
            bpy.data.objects.remove(bpy.data.objects[n])
    if soldier:
        gear += _soldier_kit(name, coll, baked, JW, acc)
    fig = join(baked + gear, name)
    zmin = min((fig.matrix_world @ v.co).z for v in fig.data.vertices)
    fig.data.transform(Matrix.Translation((0, 0, -zmin)))
    gi = {i for i, m in enumerate(fig.data.materials) if m == gun}
    for p in fig.data.polygons:
        p.use_smooth = p.material_index not in gi
    fig["clip"] = f"{clip}@{t:.2f}"
    fig["desc"] = f"{sex}/{age}/{build}"
    return fig
