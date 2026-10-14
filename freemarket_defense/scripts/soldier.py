"""Animated soldiers: three.js 'Soldier.glb' (Mixamo rig: Idle/Walk/Run) + Poly Haven rifle,
held with two-bone IK so the hands stay on the weapon while the body animation plays.

Each soldier gets a root empty whose +X is the facing direction.
"""
import os
import math
import bpy
from mathutils import Vector, Matrix, Euler
from lib import empty, link, parent, pbr

HERE = os.path.dirname(__file__)
SOLDIER = os.path.join(HERE, "..", "assets", "models", "Soldier.glb")
RIFLE = os.path.join(HERE, "..", "assets", "models", "bolt_action_rifle_7_62", "bolt_action_rifle_7_62_1k.gltf")

_T = {}


def _template():
    if _T:
        return _T
    lib = bpy.data.collections.new("_SoldierLib")
    bpy.context.scene.collection.children.link(lib)
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=os.path.abspath(SOLDIER))
    new = [o for o in bpy.data.objects if o not in before]
    for o in new:
        for c in o.users_collection:
            c.objects.unlink(o)
        lib.objects.link(o)
    ico = bpy.data.objects.get("Icosphere")
    new = [o for o in new if o != ico]
    if ico:
        bpy.data.objects.remove(ico)
    arm = [o for o in new if o.type == "ARMATURE"][0]
    meshes = [o for o in bpy.data.objects if o.type == "MESH" and o.parent == arm]
    # recolour the sci-fi body suit to a muted field palette (multiply tint)
    for m in bpy.data.materials:
        if m.name.startswith("VanguardBody"):
            nt = m.node_tree
            bsdf = [n for n in nt.nodes if n.type == "BSDF_PRINCIPLED"][0]
            src = bsdf.inputs["Base Color"].links[0].from_socket if bsdf.inputs["Base Color"].is_linked else None
            if src:
                mix = nt.nodes.new("ShaderNodeMix")
                mix.data_type = "RGBA"
                mix.blend_type = "MULTIPLY"
                mix.inputs["Factor"].default_value = 0.75
                mix.inputs[7].default_value = (0.42, 0.48, 0.32, 1)
                nt.links.new(src, mix.inputs[6])
                nt.links.new(mix.outputs[2], bsdf.inputs["Base Color"])
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=os.path.abspath(RIFLE))
    rifle = [o for o in bpy.data.objects if o not in before]
    for o in rifle:
        for c in o.users_collection:
            c.objects.unlink(o)
        lib.objects.link(o)
    # synthetic black furniture instead of the varnished wood stock
    for o in rifle:
        for slot in getattr(o, "material_slots", []):
            m = slot.material
            if not m or m.get("_tinted"):
                continue
            m["_tinted"] = True
            nt = m.node_tree
            bs = [n for n in nt.nodes if n.type == "BSDF_PRINCIPLED"]
            if not bs or not bs[0].inputs["Base Color"].is_linked:
                continue
            src = bs[0].inputs["Base Color"].links[0].from_socket
            hsv = nt.nodes.new("ShaderNodeHueSaturation")
            hsv.inputs["Saturation"].default_value = 0.15
            hsv.inputs["Value"].default_value = 0.45
            nt.links.new(src, hsv.inputs["Color"])
            nt.links.new(hsv.outputs[0], bs[0].inputs["Base Color"])
    lib.hide_render = True
    lib.hide_viewport = True
    # facing: toe - foot in rest pose
    b = arm.data.bones
    fwd = (arm.matrix_world @ b["mixamorig:LeftToeBase"].head_local) - (arm.matrix_world @ b["mixamorig:LeftFoot"].head_local)
    fwd.z = 0
    fwd.normalize()
    _T.update(lib=lib, arm=arm, meshes=meshes, rifle=rifle, fwd=fwd)
    return _T


def make_soldier(name, loc=(0, 0, 0), heading=0.0, action="Walk", offset=0, speed=1.0, armed=True,
                 coll=None, rifle_pose="ready"):
    """heading: radians, 0 = facing +X.  action: Idle | Walk | Run."""
    T = _template()
    coll = coll or bpy.context.scene.collection
    root = empty(name, loc, coll)
    root.rotation_euler = (0, 0, heading)

    arm = T["arm"].copy()
    arm.data = T["arm"].data  # shared armature data is fine (pose is per object)
    coll.objects.link(arm)
    arm.animation_data_clear()
    # rotate the armature so its forward aligns with root +X
    f = T["fwd"]
    arm.parent = root
    arm.matrix_parent_inverse = Matrix.Identity(4)
    arm.location = (0, 0, 0)
    from mathutils import Quaternion
    q0 = T["arm"].matrix_world.to_quaternion()
    arm.rotation_mode = "QUATERNION"
    arm.rotation_quaternion = Quaternion((0, 0, 1), -math.atan2(f.y, f.x)) @ q0
    arm.scale = T["arm"].matrix_world.to_scale()
    for m in T["meshes"]:
        mc = m.copy()
        coll.objects.link(mc)
        mc.parent = arm
        mc.matrix_parent_inverse = m.matrix_parent_inverse.copy()
        for mod in mc.modifiers:
            if mod.type == "ARMATURE":
                mod.object = arm

    # animation via NLA so each soldier can be time-offset
    act = bpy.data.actions.get(f"{action}_Character")
    ad = arm.animation_data_create()
    tr = ad.nla_tracks.new()
    L = act.frame_range[1] - act.frame_range[0]
    st = tr.strips.new(action, int(-offset), act)
    st.repeat = 60
    st.scale = 1.0 / speed
    st.extrapolation = "HOLD"

    if armed:
        bpy.context.view_layer.update()
        rest = arm.data.pose_position
        arm.data.pose_position = "REST"
        bpy.context.view_layer.update()
        rr = empty(f"{name}_Rifle", (0, 0, 0), coll)
        rr.empty_display_size = 0.1
        # rifle frame in root space: low ready, muzzle forward-down, across the chest
        if rifle_pose == "ready":
            m_root = Matrix.Translation((0.55, 0.05, 1.15)) @ Euler((0, math.radians(13),
                                                                     math.radians(25)), "XYZ").to_matrix().to_4x4()
        else:  # "patrol": muzzle up-forward
            m_root = Matrix.Translation((0.26, -0.06, 1.2)) @ Euler((math.radians(-10), math.radians(-35),
                                                                     math.radians(8)), "XYZ").to_matrix().to_4x4()
        rr.parent = arm
        rr.parent_type = "BONE"
        rr.parent_bone = "mixamorig:Spine1"
        bpy.context.view_layer.update()
        rr.matrix_world = root.matrix_world @ m_root
        for o in T["rifle"]:
            oc = o.copy()
            coll.objects.link(oc)
            oc.parent = rr
            oc.matrix_parent_inverse = Matrix.Identity(4)
            oc.matrix_basis = o.matrix_world.copy()
        # IK targets on the rifle (rifle space: stock -X, muzzle +X)
        tgt_r = empty(f"{name}_IK_R", (-0.33, 0.0, -0.05), coll)
        tgt_l = empty(f"{name}_IK_L", (-0.1, 0.0, -0.05), coll)
        for t in (tgt_r, tgt_l):
            t.parent = rr
            t.empty_display_size = 0.05
        pole_r = empty(f"{name}_Pole_R", (-0.1, -0.6, -0.5), coll)
        pole_l = empty(f"{name}_Pole_L", (0.1, 0.6, -0.5), coll)
        for p_ in (pole_r, pole_l):
            p_.parent = root
        bpy.context.view_layer.update()
        # side of body: Mixamo "Right" is the character's right (−Y in root space when facing +X)
        for side, tgt, pole in (("Right", tgt_r, pole_r), ("Left", tgt_l, pole_l)):
            pb = arm.pose.bones[f"mixamorig:{side}ForeArm"]
            ik = pb.constraints.new("IK")
            ik.target = tgt
            ik.pole_target = pole
            ik.pole_angle = math.radians(-90)
            ik.chain_count = 2
            ik.use_tail = True
        arm.data.pose_position = rest
    root["arm"] = arm.name
    return root


def place_on_path(root, f0, f1, p0, p1):
    """Move a soldier root linearly between two points, facing the direction of travel."""
    d = Vector(p1) - Vector(p0)
    root.rotation_euler = (0, 0, math.atan2(d.y, d.x))
    root.location = p0
    root.keyframe_insert("location", frame=f0)
    root.location = p1
    root.keyframe_insert("location", frame=f1)
    for fc in root.animation_data.action.fcurves:
        for k in fc.keyframe_points:
            k.interpolation = "LINEAR"
