"""Minimal BVH reader for the CMU motion-capture library (cgspeed BVH release).

pose(clip, t) -> dict of joint name -> Vector in Blender space (metres, Z up),
normalised so the figure faces +X, pelvis above the origin, lowest foot on z=0.
"""
import os
import math
from mathutils import Vector, Matrix, Euler

HERE = os.path.dirname(os.path.abspath(__file__))
DIR = os.path.join(HERE, "..", "assets", "mocap")
_cache = {}


class Joint:
    def __init__(self, name, parent):
        self.name, self.parent = name, parent
        self.offset = Vector()
        self.channels = []
        self.children = []
        self.end = None


def _parse(path):
    tok = open(path).read().split()
    i = 0
    joints, stack, order = {}, [], []
    cur = None
    while tok[i] != "MOTION":
        t = tok[i]
        if t in ("ROOT", "JOINT"):
            cur = Joint(tok[i + 1], stack[-1] if stack else None)
            if cur.parent:
                cur.parent.children.append(cur)
            joints[cur.name] = cur
            order.append(cur)
            i += 2
        elif t == "End":
            # End Site { OFFSET x y z }
            cur_end = Vector((float(tok[i + 4]), float(tok[i + 5]), float(tok[i + 6])))
            stack[-1].end = cur_end
            i += 8
            continue
        elif t == "{":
            stack.append(cur)
            i += 1
        elif t == "}":
            stack.pop()
            i += 1
        elif t == "OFFSET":
            cur.offset = Vector((float(tok[i + 1]), float(tok[i + 2]), float(tok[i + 3])))
            i += 4
        elif t == "CHANNELS":
            n = int(tok[i + 1])
            cur.channels = tok[i + 2:i + 2 + n]
            i += 2 + n
        else:
            i += 1
    nframes = int(tok[i + 2])
    ftime = float(tok[i + 5])
    vals = list(map(float, tok[i + 6:]))
    nch = sum(len(j.channels) for j in order)
    frames = [vals[k * nch:(k + 1) * nch] for k in range(nframes)]
    return order, frames, ftime


def _load(clip):
    if clip not in _cache:
        _cache[clip] = _parse(os.path.join(DIR, clip + ".bvh"))
    return _cache[clip]


def nframes(clip):
    return len(_load(clip)[1])


def _fk(order, row):
    world = {}
    k = 0
    for j in order:
        loc = Vector(j.offset)
        rot = Matrix.Identity(3)
        for ch in j.channels:
            v = row[k]
            k += 1
            if ch == "Xposition":
                loc.x = v
            elif ch == "Yposition":
                loc.y = v
            elif ch == "Zposition":
                loc.z = v
            else:
                ax = ch[0]
                rot = rot @ Matrix.Rotation(math.radians(v), 3, ax)
        local = Matrix.Translation(loc) @ rot.to_4x4()
        world[j.name] = (world[j.parent.name] @ local) if j.parent else local
    pos = {n: m.translation.copy() for n, m in world.items()}
    for j in order:
        if j.end is not None:
            pos[j.name + "_end"] = (world[j.name] @ j.end.to_4d()).to_3d() if False else (world[j.name] @ Matrix.Translation(j.end)).translation
    return pos


def pose(clip, t=0.5, height=1.78):
    """t in [0,1] picks the moment in the clip."""
    order, frames, _ = _load(clip)
    f = min(len(frames) - 1, max(1, int(t * (len(frames) - 1))))  # frame 0 is the T-pose
    p = _fk(order, frames[f])
    # BVH Y-up, character left = +X, forward = +Z  ->  Blender X fwd, Y left, Z up
    q = {n: Vector((v.z, v.x, v.y)) for n, v in p.items()}
    # face +X: heading from the hip line (left - right is +Y when facing +X)
    hl = q["LeftUpLeg"] - q["RightUpLeg"]
    a = math.atan2(hl.y, hl.x) - math.pi / 2
    R = Matrix.Rotation(-a, 3, "Z")
    pel = q["Hips"].copy()
    q = {n: R @ (v - Vector((pel.x, pel.y, 0))) for n, v in q.items()}
    zmin = min(q[n].z for n in ("LeftToeBase", "RightToeBase", "LeftFoot", "RightFoot"))
    top = q["Head_end"].z if "Head_end" in q else q["Head"].z
    s = height / max(top - zmin, 1e-3) * 0.97
    return {n: Vector((v.x * s, v.y * s, (v.z - zmin) * s)) for n, v in q.items()}
