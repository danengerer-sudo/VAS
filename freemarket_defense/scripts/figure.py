"""Static posed mannequin soldiers for the white diorama style.

No rig: joint positions are laid out per pose and the arms are solved with
two-bone IK straight onto the rifle's grip and handguard, so the hands are
always exactly on the weapon. Body space: +X forward, +Y left, Z up, feet on z=0.
"""
import math
import bpy
from mathutils import Vector, Matrix, Euler, Quaternion
from lib import lathe, box, cylinder, extrude_profile, pbr, link, join, bevel, empty

H_SHOULDER = 1.45
UPPER_ARM, FOREARM = 0.31, 0.29
THIGH, SHIN = 0.45, 0.44


def _capsule(name, p0, p1, r0, r1, coll, mat, seg=16):
    p0, p1 = Vector(p0), Vector(p1)
    L = max((p1 - p0).length, 1e-4)
    prof = []
    for i in range(6):
        a = -math.pi / 2 + (math.pi / 2) * i / 5
        prof.append((r0 * math.sin(a), r0 * math.cos(a)))
    for i in range(6):
        a = (math.pi / 2) * i / 5
        prof.append((L + r1 * math.sin(a), r1 * math.cos(a)))
    prof[0] = (prof[0][0], 0.0)
    prof[-1] = (prof[-1][0], 0.0)
    o = lathe(name, prof, seg, coll, mat, axis="Z")
    q = (p1 - p0).to_track_quat("Z", "Y")
    o.data.transform(Matrix.Translation(p0) @ q.to_matrix().to_4x4())
    return o


def _ellipsoid(name, c, r, coll, mat, rot=(0, 0, 0)):
    o = _capsule(name, (0, 0, -1e-3), (0, 0, 1e-3), 1.0, 1.0, coll, mat, 20)
    o.data.transform(Matrix.Translation(c) @ Euler(rot).to_matrix().to_4x4() @ Matrix.Diagonal((*r, 1)))
    return o


def _two_bone(s, t, a, b, pole):
    """Return elbow/knee position for root s, end t, segment lengths a, b, bending toward pole."""
    s, t, pole = Vector(s), Vector(t), Vector(pole)
    d = t - s
    dist = min(d.length, a + b - 1e-3)
    dn = d.normalized()
    x = (a * a - b * b + dist * dist) / (2 * dist)
    h = math.sqrt(max(a * a - x * x, 0.0))
    perp = (pole - s) - dn * (pole - s).dot(dn)
    perp = perp.normalized() if perp.length > 1e-6 else Vector((0, 0, -1))
    end = s + dn * dist
    return s + dn * x + perp * h, end


def carbine(name, coll, mat):
    """M4-like carbine in rifle space: butt at x=0, muzzle at +x, bore at z=0."""
    parts = [
        extrude_profile(name + "_stock", [(0.0, -0.075), (0.02, -0.085), (0.19, -0.02), (0.19, 0.03), (0.0, 0.03)],
                        0.045, "XZ", coll, mat),
        cylinder(name + "_tube", 0.016, 0.12, (0.2, 0, 0.0), (0, math.pi / 2, 0), 12, coll, mat),
        box(name + "_rcv", (0.26, 0.05, 0.075), (0.36, 0, -0.005), coll, 0.008, mat),
        box(name + "_rail", (0.2, 0.03, 0.015), (0.37, 0, 0.04), coll, 0.0, mat),
        box(name + "_optic", (0.1, 0.04, 0.05), (0.36, 0, 0.07), coll, 0.008, mat),
        cylinder(name + "_hg", 0.028, 0.24, (0.6, 0, 0.0), (0, math.pi / 2, 0), 8, coll, mat),
        cylinder(name + "_brl", 0.009, 0.16, (0.79, 0, 0.0), (0, math.pi / 2, 0), 10, coll, mat),
        box(name + "_fsp", (0.015, 0.012, 0.05), (0.72, 0, 0.035), coll, 0.0, mat),
    ]
    mag = box(name + "_mag", (0.065, 0.03, 0.15), (0.0, 0, -0.075), coll, 0.006, mat)
    mag.data.transform(Matrix.Translation((0.41, 0, -0.04)) @ Euler((0, math.radians(-12), 0)).to_matrix().to_4x4())
    grip = box(name + "_grip", (0.04, 0.032, 0.1), (0.0, 0, -0.05), coll, 0.005, mat)
    grip.data.transform(Matrix.Translation((0.27, 0, -0.035)) @ Euler((0, math.radians(18), 0)).to_matrix().to_4x4())
    parts += [mag, grip]
    for p in parts:  # bake object transforms so join keeps them
        p.data.transform(p.matrix_basis)
        p.matrix_basis = Matrix.Identity(4)
    g = join(parts, name)
    return g


# rifle-space anchor points
GRIP = Vector((0.27, 0, -0.07))      # right hand
FOREGRIP = Vector((0.58, 0, -0.035))  # left hand
BUTT = Vector((0.0, 0, -0.01))

POSES = {
    # yaw: torso twist (rad, + = left shoulder back); rifle: (butt position, pitch, yaw)
    "ready":   dict(feet=((0.02, 0.13), (-0.08, -0.14)), lean=0.06, yaw=-0.45,
                    rifle=((0.13, -0.17, 1.33), math.radians(32), math.radians(10)), head=(0, 0.05, 0)),
    "aim":     dict(feet=((0.18, 0.15), (-0.2, -0.12)), lean=0.08, yaw=-0.75,
                    rifle=((0.1, -0.12, 1.42), math.radians(1), math.radians(5)), head=(0, 0.12, -0.25)),
    "patrol":  dict(feet=((0.28, 0.1), (-0.26, -0.1)), lean=0.07, yaw=-0.35,
                    rifle=((0.14, -0.17, 1.32), math.radians(36), math.radians(14)), head=(0, 0.02, 0)),
    "rest":    dict(feet=((0.0, 0.14), (0.0, -0.14)), lean=0.0, yaw=-0.15,
                    rifle=((0.14, -0.14, 0.98), math.radians(-50), math.radians(70)), head=(0, 0.0, 0)),
    "civilian": dict(feet=((0.02, 0.12), (-0.02, -0.12)), lean=0.0, yaw=0.0, rifle=None, head=(0, 0.0, 0)),
}


def make_figure(name, pose="ready", coll=None, accent=None, loc=(0, 0, 0), heading=0.0,
                body_col=(0.86, 0.85, 0.83), gun_col=(0.035, 0.037, 0.04), civ_col=None):
    coll = coll or bpy.context.scene.collection
    P = POSES[pose]
    body = pbr(f"Fig_{body_col}", body_col, rough=0.55)
    vestm = pbr(f"FigVest_{body_col}", tuple(c * 0.92 for c in body_col), rough=0.7)
    acc = pbr(f"FigAcc_{accent}", accent, rough=0.5) if accent else body
    gun = pbr("FigGun", gun_col, rough=0.45)
    cloth = pbr(f"FigCiv_{civ_col}", civ_col, rough=0.7) if civ_col else body
    parts = []

    lean, yaw = P["lean"], P["yaw"]
    pelvis = Vector((0, 0, 0.98))
    # chest frame: lean forward, twist by yaw
    R = Euler((0, lean, yaw)).to_matrix()
    chest = pelvis + R @ Vector((0, 0, 0.33))
    neck = pelvis + R @ Vector((0, 0, 0.53))
    sh_r = pelvis + R @ Vector((0, -0.2, H_SHOULDER - 0.98))
    sh_l = pelvis + R @ Vector((0, 0.2, H_SHOULDER - 0.98))
    hd = neck + Euler(P["head"]).to_matrix() @ Vector((0.0, 0, 0.14))

    # ---- legs
    hips = (Vector((0, 0.1, 0.94)), Vector((0, -0.1, 0.94)))
    for k, (hip, (fx, fy)) in enumerate(zip(hips, P["feet"])):
        foot = Vector((fx, fy, 0.09))
        knee, ank = _two_bone(hip, foot, THIGH, SHIN, hip + Vector((1.0, 0, -0.4)))
        parts += [_capsule(f"{name}_th{k}", hip, knee, 0.1, 0.075, coll, body),
                  _capsule(f"{name}_sh{k}", knee, ank, 0.072, 0.055, coll, body)]
        # rounded boot: heel-to-toe capsule, slightly flattened, toe a touch narrower
        heel = Vector((ank.x - 0.05, ank.y, 0.052))
        toe = Vector((ank.x + 0.15, ank.y, 0.042))
        boot = _capsule(f"{name}_boot{k}", heel, toe, 0.052, 0.042, coll, body)
        parts.append(boot)

    # ---- torso
    parts.append(_ellipsoid(f"{name}_pelvis", pelvis + Vector((0, 0, 0.02)), (0.13, 0.17, 0.12), coll,
                            cloth if civ_col else body, (0, lean * 0.5, yaw * 0.4)))
    parts.append(_ellipsoid(f"{name}_abd", pelvis + R @ Vector((0, 0, 0.17)), (0.12, 0.16, 0.15), coll,
                            cloth if civ_col else body, (0, lean, yaw * 0.7)))
    parts.append(_ellipsoid(f"{name}_chest", chest, (0.135, 0.205, 0.2), coll, cloth if civ_col else body, (0, lean, yaw)))
    if not civ_col:
        for k, xx in enumerate((0.1, -0.1)):
            plate = box(f"{name}_plate{k}", (0.07, 0.31, 0.34), (0, 0, 0), coll, 0.03, vestm)
            plate.data.transform(Matrix.Translation(chest + R @ Vector((xx, 0, -0.04))) @ R.to_4x4())
            parts.append(plate)
        for i, yy in enumerate((-0.09, 0.0, 0.09)):
            pouch = box(f"{name}_pouch{i}", (0.06, 0.075, 0.12), (0, 0, 0), coll, 0.012, vestm)
            pouch.data.transform(Matrix.Translation(chest + R @ Vector((0.15, yy, -0.12))) @ R.to_4x4())
            parts.append(pouch)
    parts.append(_capsule(f"{name}_neck", neck - R @ Vector((0, 0, 0.06)), neck + Vector((0, 0, 0.05)), 0.05, 0.05, coll, body))
    for k, s in enumerate((sh_r, sh_l)):
        parts.append(_ellipsoid(f"{name}_delt{k}", s + Vector((0, 0, -0.01)), (0.065, 0.06, 0.06), coll, cloth if civ_col else body))

    # ---- head + helmet
    parts.append(_ellipsoid(f"{name}_head", hd, (0.105, 0.095, 0.12), coll, body))
    if not civ_col:
        hm = _ellipsoid(f"{name}_helmet", hd + Vector((-0.012, 0, 0.012)), (0.132, 0.124, 0.13), coll, acc)
        # cut the lower half off the helmet so it sits like a shell
        bm_cut = [v for v in hm.data.vertices]
        for v in bm_cut:
            lim = hd.z - 0.03 + 0.05 * max(0.0, (v.co.x - hd.x) / 0.13)  # brow higher in front
            if v.co.z < lim:
                v.co.z = lim
        parts.append(hm)

    # ---- rifle + arms
    if P["rifle"]:
        (bx, by, bz), pitch, ryaw = P["rifle"]
        M = Matrix.Translation(Vector((bx, by, bz)) - Vector((0, 0, 0))) @ \
            Euler((0, pitch, ryaw)).to_matrix().to_4x4() @ Matrix.Translation(-BUTT)
        g = carbine(f"{name}_rifle", coll, gun)
        g.data.transform(M)
        parts.append(g)
        targets = (M @ GRIP, M @ FOREGRIP)
    else:
        targets = (Vector((0.05, -0.27, 0.86)), Vector((0.05, 0.27, 0.86)))
    for k, (s, t) in enumerate(zip((sh_r, sh_l), targets)):
        side = -1 if k == 0 else 1
        pole = s + Vector((-0.3, side * 0.6, -0.8))
        el, hand = _two_bone(s, t, UPPER_ARM, FOREARM, pole)
        sleeve = cloth if civ_col else body
        parts += [_capsule(f"{name}_ua{k}", s, el, 0.068, 0.056, coll, sleeve),
                  _capsule(f"{name}_fa{k}", el, hand, 0.055, 0.043, coll, sleeve),
                  _ellipsoid(f"{name}_hand{k}", hand + (hand - el).normalized() * 0.03, (0.055, 0.04, 0.05), coll, body)]
        if accent and k == 1 and not civ_col:
            parts.append(_capsule(f"{name}_band", s.lerp(el, 0.42), s.lerp(el, 0.6), 0.072, 0.066, coll, acc))
    acc_parts = [p for p in parts if p.data.materials and p.data.materials[0] in (acc, gun) and acc is not body]
    acc_parts += [p for p in parts if p.data.materials and p.data.materials[0] == gun and p not in acc_parts]
    soft = [p for p in parts if p not in acc_parts]
    torso_mat = cloth if civ_col else body
    sculpt = join(soft, name + "_body")
    rm = sculpt.modifiers.new("Remesh", "REMESH")
    rm.mode = "VOXEL"
    rm.voxel_size = 0.013
    sm = sculpt.modifiers.new("Smooth", "CORRECTIVE_SMOOTH")
    sm.iterations = 6
    sm.use_only_smooth = True
    from lib import apply_mods
    apply_mods(sculpt)
    sculpt.data.materials.clear()
    sculpt.data.materials.append(body)
    if civ_col:
        # clothes: everything between knees and neck gets the outfit colour
        sculpt.data.materials.append(cloth)
        for p in sculpt.data.polygons:
            z = p.center.z
            p.material_index = 1 if 0.45 < z < 1.52 and not (p.center.y ** 2 > 0.09 and z < 1.1) else 0
    fig = join([sculpt] + acc_parts, name)
    flat_idx = {i for i, m in enumerate(fig.data.materials) if m == gun}
    for p in fig.data.polygons:
        p.use_smooth = p.material_index not in flat_idx
    fig.location = loc
    fig.rotation_euler = (0, 0, heading)
    return fig
