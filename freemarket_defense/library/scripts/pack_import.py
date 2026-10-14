"""pack_import: convert downloaded CC0 packs (Kenney, Poly Haven ...) into library categories.

Each build_<category>.py lists its assets as dicts and calls `build(category, specs)`:

    {"name": "shop_a",                 # asset name (collection <category>/<name>)
     "file": "<pack>/<rel path>",      # relative to assets/packs/
     "scale": 8.0 | (sx, sy, sz),      # applied in the file's own axes (before rot_z)
     "rot_z": 90,                      # degrees, applied after scale (to make the front face +X)
     "profile": "building",            # material remap profile, see classify()
     "tags": [...], "notes": "...",
     "source": "Kenney City Kit (Commercial)", "license": "CC0 1.0",
     "parts": False,                   # keep sub-objects (e.g. car wheels) as children
     "target": None}                   # optional {"axis": 0|1|2, "size": m}: rescale so that bbox
                                       # extent on that axis (after rot) equals size

Material remap: every face gets one of the LIB_* materials, chosen from the colour the source
asset shows on that face (Kenney colour-atlas texture sampled at the face's UV centroid, or the
material's base colour / mean texture colour).  The original colour is kept as a CORNER colour
attribute `orig_color` (sRGB byte) so a scene can show the pack's own palette if wanted, and the
original material name is stored on the object as custom property `orig_materials`.
"""
import colorsys
import json
import math
import os
import sys
import traceback

import bpy
import numpy as np
from mathutils import Matrix, Vector

HERE = os.path.dirname(os.path.abspath(__file__))
LIBROOT = os.path.dirname(HERE)
PACKS = os.path.normpath(os.path.join(LIBROOT, "..", "assets", "packs"))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.normpath(os.path.join(LIBROOT, "..", "scripts")))
import lib  # noqa: E402
import thumb  # noqa: E402

MAX_TRIS = 150000
BODY, ACCENT, DARK, GLASS, LIGHT, METAL = (
    "LIB_Body", "LIB_Accent", "LIB_Dark", "LIB_Glass", "LIB_Light", "LIB_Metal")


def mat(name):
    m = bpy.data.materials.get(name)
    if m:
        return m
    if name == BODY:
        return lib.pbr(name, (0.82, 0.81, 0.79), rough=0.6, spec=0.35)
    if name == ACCENT:
        return lib.pbr(name, (0.95, 0.38, 0.06), rough=0.5, spec=0.4)
    if name == DARK:
        return lib.pbr(name, (0.035, 0.037, 0.04), rough=0.5, spec=0.4)
    if name == GLASS:
        return lib.pbr(name, (0.08, 0.09, 0.1), rough=0.08, spec=0.6)
    if name == LIGHT:
        return lib.pbr(name, (1.0, 1.0, 1.0), rough=0.4, emission=((1.0, 1.0, 1.0), 0.0))
    if name == METAL:
        return lib.pbr(name, (0.8, 0.6, 0.2), rough=0.28, metal=1.0)
    raise KeyError(name)


# ------------------------------------------------------------------ colour helpers
def lin2srgb(c):
    c = max(0.0, min(1.0, c))
    return c * 12.92 if c <= 0.0031308 else 1.055 * c ** (1 / 2.4) - 0.055


_img_cache = {}
BLOCK_AVG = True


def _img_array(img):
    key = img.name
    if key not in _img_cache:
        w, h = img.size
        a = np.empty(w * h * 4, dtype=np.float32)
        img.pixels.foreach_get(a)
        a = a.reshape(h, w, 4)
        if img.colorspace_settings.name != "sRGB" and img.is_float:
            a[..., :3] = np.where(a[..., :3] <= 0.0031308, a[..., :3] * 12.92,
                                  1.055 * np.clip(a[..., :3], 0, 1) ** (1 / 2.4) - 0.055)
        if BLOCK_AVG and w == h and w % 16 == 0:
            # Kenney colour atlases: 16x16 grid of gradient swatches -> one flat colour per swatch
            b = w // 16
            m = a.reshape(16, b, 16, b, 4).mean(axis=(1, 3))
            a = np.repeat(np.repeat(m, b, axis=0), b, axis=1).astype(np.float32)
        _img_cache[key] = a
    return _img_cache[key]


def _base_image(m):
    """Image feeding the Base Color of a material (searching upstream), or None."""
    if not m or not m.use_nodes:
        return None
    bsdf = next((n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED"), None)
    if not bsdf:
        return None
    todo = [bsdf.inputs["Base Color"]]
    seen = set()
    while todo:
        sock = todo.pop()
        for l in sock.links:
            n = l.from_node
            if n.name in seen:
                continue
            seen.add(n.name)
            if n.type == "TEX_IMAGE" and n.image:
                return n.image
            todo.extend(n.inputs)
    return None


def _mat_color(m):
    """Representative sRGB colour of a material (mean of its base texture, else base colour)."""
    if m is None:
        return (0.8, 0.8, 0.8)
    img = _base_image(m)
    if img is not None and img.size[0] > 0:
        a = _img_array(img)
        step = max(1, a.shape[0] // 64)
        sub = a[::step, ::step, :3].reshape(-1, 3)
        return tuple(float(x) for x in sub.mean(0))
    bsdf = next((n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED"), None) if m.use_nodes else None
    c = bsdf.inputs["Base Color"].default_value if bsdf else m.diffuse_color
    return tuple(lin2srgb(c[i]) for i in range(3))


def face_colors(ob, per_face=True):
    """(N,3) sRGB colour per polygon and (N,) area."""
    me = ob.data
    n = len(me.polygons)
    areas = np.empty(n, dtype=np.float32)
    me.polygons.foreach_get("area", areas)
    midx = np.empty(n, dtype=np.int32)
    me.polygons.foreach_get("material_index", midx)
    mats = [s.material for s in ob.material_slots] or [None]
    cols = np.zeros((n, 3), dtype=np.float32)
    mcols = [np.array(_mat_color(m), dtype=np.float32) for m in mats]
    for i, mc in enumerate(mcols):
        cols[midx == i] = mc
    if per_face and me.uv_layers.active:
        uv = np.empty(len(me.loops) * 2, dtype=np.float32)
        me.uv_layers.active.data.foreach_get("uv", uv)
        uv = uv.reshape(-1, 2)
        ls = np.empty(n, dtype=np.int32)
        lt = np.empty(n, dtype=np.int32)
        me.polygons.foreach_get("loop_start", ls)
        me.polygons.foreach_get("loop_total", lt)
        sums = np.add.reduceat(uv, ls, axis=0) if n else uv[:0]
        cen = sums / lt[:, None]
        for i, m in enumerate(mats):
            img = _base_image(m)
            sel = midx == i
            if img is None or not sel.any():
                continue
            a = _img_array(img)
            h, w = a.shape[:2]
            x = (np.mod(cen[sel, 0], 1.0) * w).astype(int).clip(0, w - 1)
            y = (np.mod(cen[sel, 1], 1.0) * h).astype(int).clip(0, h - 1)
            cols[sel] = a[y, x, :3]
    return cols, areas, midx, mats


# ------------------------------------------------------------------ classification
def _hsv(c):
    return colorsys.rgb_to_hsv(*[float(x) for x in c])


def _lum(c):
    return 0.299 * c[0] + 0.587 * c[1] + 0.114 * c[2]


def classify(cols, areas, profile, matnames=None, dark_lum=0.30):
    """Return list of LIB names, one per row of cols.

    profiles
      building : blue -> glass; dark -> dark; dominant colour + neutrals -> body; other saturated -> accent
      vehicle  : light blue/very light cyan -> glass; dark -> dark; dominant -> body; others -> accent
      prop     : no glass by colour (only by material name); otherwise as building
      road     : dark asphalt -> dark; everything else body (signs/lines/kerbs); saturated -> accent
      mono     : everything body except dark -> dark (glass by name)
    """
    n = len(cols)
    out = [None] * n
    hsv = [_hsv(c) for c in cols]
    lum = [_lum(c) for c in cols]
    for i in range(n):
        nm = (matnames[i] if matnames else "").lower()
        h, s, v = hsv[i]
        hd = h * 360
        if "glass" in nm or "window" in nm:
            out[i] = GLASS
        elif "emiss" in nm or "light" in nm and "lightwood" not in nm:
            out[i] = LIGHT if profile != "mono" else BODY
        elif lum[i] < dark_lum:
            out[i] = DARK
        elif profile in ("building",) and 190 <= hd <= 250 and s > 0.15:
            out[i] = GLASS
        elif profile == "vehicle" and 185 <= hd <= 260 and s > 0.05 and v > 0.85 and s < 0.45:
            out[i] = GLASS
    # dominant colour among remaining saturated faces
    rest = [i for i in range(n) if out[i] is None]
    if profile in ("mono",):
        for i in rest:
            out[i] = BODY
        return out
    bins = {}
    for i in rest:
        h, s, v = hsv[i]
        if s < 0.22:
            continue
        key = (int(h * 18) % 18, int(s * 3), int(v * 3))
        bins.setdefault(key, [0.0, np.zeros(3)])
        bins[key][0] += areas[i]
        bins[key][1] += cols[i] * areas[i]
    neutral_area = sum(areas[i] for i in rest if hsv[i][1] < 0.22)
    dom = None
    if bins:
        k = max(bins, key=lambda k: bins[k][0])
        # if neutral (white/grey) surfaces dominate, the saturated colours are all accents
        if bins[k][0] > 0.5 * neutral_area or profile == "vehicle":
            dom = bins[k][1] / max(bins[k][0], 1e-9)
    for i in rest:
        h, s, v = hsv[i]
        if s < 0.22:
            out[i] = BODY
        elif dom is not None and np.linalg.norm(cols[i] - dom) < 0.16:
            out[i] = BODY
        else:
            out[i] = ACCENT
    return out


def remap(ob, profile, per_face=True, overrides=None, dark_lum=0.30):
    """Replace ob's materials by LIB_* according to profile; keep the original colours as attribute."""
    me = ob.data
    if len(me.polygons) == 0:
        return
    if per_face:
        import bmesh
        bm = bmesh.new()
        bm.from_mesh(me)
        bmesh.ops.join_triangles(bm, faces=bm.faces[:], angle_face_threshold=math.radians(2),
                                 angle_shape_threshold=math.radians(60), cmp_materials=True)
        bm.to_mesh(me)
        bm.free()
    cols, areas, midx, mats = face_colors(ob, per_face)
    names = [(mats[k].name if mats[k] else "") for k in midx]
    cls = classify(cols, areas, profile, names, dark_lum=dark_lum)
    if overrides:  # {orig material name substring: LIB name}
        for i, nm in enumerate(names):
            for sub, lm in overrides.items():
                if sub in nm:
                    cls[i] = lm
    ob["orig_materials"] = ",".join(sorted({m.name for m in mats if m}))
    # original colour as corner attribute
    attr = me.color_attributes.new("orig_color", "BYTE_COLOR", "CORNER")
    lt = np.empty(len(me.polygons), dtype=np.int32)
    me.polygons.foreach_get("loop_total", lt)
    lc = np.repeat(cols, lt, axis=0)
    lc = np.concatenate([lc, np.ones((len(lc), 1), dtype=np.float32)], 1)
    # BYTE_COLOR .color is linear in the API; convert sRGB -> linear
    lin = np.where(lc[:, :3] <= 0.04045, lc[:, :3] / 12.92, ((lc[:, :3] + 0.055) / 1.055) ** 2.4)
    lc[:, :3] = lin
    attr.data.foreach_set("color", lc.ravel())
    used = sorted(set(cls), key=[BODY, ACCENT, DARK, GLASS, LIGHT, METAL].index)
    me.materials.clear()
    for u in used:
        me.materials.append(mat(u))
    idx = np.array([used.index(c) for c in cls], dtype=np.int32)
    me.polygons.foreach_set("material_index", idx)
    me.update()


# ------------------------------------------------------------------ import / normalise
def import_file(path):
    before = set(bpy.data.objects)
    ext = os.path.splitext(path)[1].lower()
    if ext in (".glb", ".gltf"):
        bpy.ops.import_scene.gltf(filepath=path, import_shading="NORMALS")
    elif ext == ".obj":
        bpy.ops.wm.obj_import(filepath=path)
    elif ext == ".fbx":
        bpy.ops.import_scene.fbx(filepath=path)
    else:
        raise ValueError(path)
    return [o for o in bpy.data.objects if o not in before]


def bounds(objs):
    """World-space bounds from vertex data (object.bound_box can be stale right after mesh edits)."""
    mn = Vector((1e18, 1e18, 1e18))
    mx = Vector((-1e18, -1e18, -1e18))
    for o in objs:
        if o.type != "MESH" or len(o.data.vertices) == 0:
            continue
        co = np.empty(len(o.data.vertices) * 3, dtype=np.float64)
        o.data.vertices.foreach_get("co", co)
        co = co.reshape(-1, 3)
        M = np.array(o.matrix_world)
        w = co @ M[:3, :3].T + M[:3, 3]
        mn = Vector(np.minimum(np.array(mn), w.min(0)))
        mx = Vector(np.maximum(np.array(mx), w.max(0)))
    return mn, mx


def tri_count(objs):
    n = 0
    for o in objs:
        if o.type == "MESH":
            o.data.calc_loop_triangles()
            n += len(o.data.loop_triangles)
    return n


def normalise(objs, name, scale=1.0, rot_z=0.0, parts=False, target=None, wheel_hint="wheel"):
    """Bake transforms, scale/rotate, put origin at ground centre. Returns [root, *children]."""
    meshes = [o for o in objs if o.type == "MESH"]
    others = [o for o in objs if o.type != "MESH"]
    sc = scale if isinstance(scale, (tuple, list)) else (scale, scale, scale)
    M = Matrix.Rotation(math.radians(rot_z), 4, "Z") @ Matrix.Diagonal((*sc, 1.0))
    seen = set()
    for o in meshes:
        if o.data.users > 1 or o.data.name in seen:
            o.data = o.data.copy()
        seen.add(o.data.name)
        mw = o.matrix_world.copy()
        o.parent = None
        o.data.transform(M @ mw)
        if (M @ mw).determinant() < 0:
            o.data.flip_normals()
        o.matrix_world = Matrix.Identity(4)
    for o in others:
        bpy.data.objects.remove(o)
    if target:
        mn, mx = bounds(meshes)
        ext = mx[target["axis"]] - mn[target["axis"]]
        f = target["size"] / ext
        for o in meshes:
            o.data.transform(Matrix.Scale(f, 4))
    mn, mx = bounds(meshes)
    off = Vector((-(mn.x + mx.x) / 2, -(mn.y + mx.y) / 2, -mn.z))
    for o in meshes:
        o.data.transform(Matrix.Translation(off))
    if not parts or len(meshes) == 1:
        if len(meshes) > 1:
            bpy.ops.object.select_all(action="DESELECT")
            for o in meshes:
                o.select_set(True)
            bpy.context.view_layer.objects.active = meshes[0]
            bpy.ops.object.join()
        root = meshes[0]
        root.name = name
        root.data.name = name
        return [root]
    # keep parts: largest is the root, the rest get their own origin at their bbox centre
    meshes.sort(key=lambda o: -len(o.data.vertices))
    wheels = [o for o in meshes if wheel_hint in o.name.lower()]
    body = [o for o in meshes if o not in wheels]
    if len(body) > 1:
        bpy.ops.object.select_all(action="DESELECT")
        for o in body:
            o.select_set(True)
        bpy.context.view_layer.objects.active = body[0]
        bpy.ops.object.join()
    root = body[0]
    root.name = name
    root.data.name = name
    out = [root]
    for i, w in enumerate(wheels):
        a, b = bounds([w])
        c = (a + b) / 2
        w.data.transform(Matrix.Translation(-c))
        w.location = c
        w.parent = root
        w.name = f"{name}_wheel_{i}"
        w.data.name = w.name
        out.append(w)
    return out


# ------------------------------------------------------------------ category builder
def argv_opts():
    a = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    o = {"only": None, "nothumb": False}
    for x in a:
        if x.startswith("--only="):
            o["only"] = set(x[7:].split(","))
        if x == "--nothumb":
            o["nothumb"] = True
    return o


def _preview(coll, path):
    try:
        img = bpy.data.images.load(path)
        img.scale(128, 128)
        prev = coll.preview_ensure()
        prev.image_size = (128, 128)
        prev.image_pixels_float = list(img.pixels)
        bpy.data.images.remove(img)
    except Exception as e:
        print("preview failed", e)


def build(category, specs, cols=8, title=None):
    opts = argv_opts()
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    root = bpy.data.collections.new(category)
    sc.collection.children.link(root)
    thumb_dir = os.path.join(LIBROOT, "thumbs", category)
    blend = os.path.join(LIBROOT, "build", category + ".blend")
    catalog = os.path.join(LIBROOT, "catalog", category + ".json")
    os.makedirs(os.path.dirname(catalog), exist_ok=True)
    os.makedirs(os.path.dirname(blend), exist_ok=True)
    entries, failed = [], []
    cursor = [0.0, 0.0, 0.0]
    thumb.setup_studio()
    sc.render.threads_mode = "FIXED"
    sc.render.threads = 2
    for sp in specs:
        name = sp["name"]
        if opts["only"] and name not in opts["only"]:
            continue
        print(f"[{category}] {name}", flush=True)
        try:
            path = os.path.join(PACKS, sp["file"])
            objs = import_file(path)
            for o in objs:  # imports land in the active (scene) collection
                for c in list(o.users_collection):
                    c.objects.unlink(o)
                sc.collection.objects.link(o)
            objs = normalise(objs, name, sp.get("scale", 1.0), sp.get("rot_z", 0.0),
                             sp.get("parts", False), sp.get("target"))
            for o in objs:
                remap(o, sp.get("profile", "prop"), sp.get("per_face", True), sp.get("overrides"),
                      sp.get("dark_lum", 0.30))
                ntri = tri_count([o])
                if ntri > MAX_TRIS:
                    dm = o.modifiers.new("Decimate", "DECIMATE")
                    dm.ratio = MAX_TRIS * 0.9 / ntri
                    bpy.context.view_layer.objects.active = o
                    bpy.ops.object.modifier_apply(modifier=dm.name)
                for cb in sp.get("post", []):
                    cb(o)
        except Exception:
            traceback.print_exc()
            failed.append(name)
            continue
        coll = bpy.data.collections.new(f"{category}/{name}")
        root.children.link(coll)
        for o in objs:
            for c in list(o.users_collection):
                c.objects.unlink(o)
            coll.objects.link(o)
        bpy.context.view_layer.update()
        mn, mx = bounds(objs)
        dims = [round(mx[i] - mn[i], 3) for i in range(3)]
        tris = tri_count(objs)
        tags = [category] + list(sp.get("tags", []))
        coll.asset_mark()
        for t in tags:
            coll.asset_data.tags.new(t, skip_if_exists=True)
        notes = sp.get("notes", "")
        coll.asset_data.description = notes
        coll["source"] = sp["source"]
        coll["license"] = sp.get("license", "CC0 1.0")
        tpath = os.path.join(thumb_dir, name + ".jpg")
        if not opts["nothumb"]:
            thumb.thumbnail(objs, tpath, azimuth=sp.get("az", -35), elevation=sp.get("el", 22),
                            fill=sp.get("fill", 1.0))
            _preview(coll, tpath)
        # grid layout in the .blend; instance_offset keeps the asset origin
        w, d = dims[0] + 4, dims[1] + 4
        if cursor[0] > 300:
            cursor[:] = [0.0, cursor[1] + cursor[2], 0.0]
        pos = Vector((cursor[0] + w / 2, cursor[1] + d / 2, 0))
        objs[0].location += pos
        coll.instance_offset = pos
        cursor[0] += w
        cursor[2] = max(cursor[2], d)
        entries.append({
            "name": name, "category": category, "collection": coll.name,
            "file": f"build/{category}.blend", "source": sp["source"],
            "license": sp.get("license", "CC0 1.0"), "dims_m": dims, "tags": tags,
            "notes": (notes + f" | ~{tris} tris | src {sp['file']}").strip(" |"),
            "thumb": f"thumbs/{category}/{name}.jpg",
            "source_url": sp.get("url", ""),
        })
        print(f"   dims {dims} tris {tris}", flush=True)
    if opts["only"] and os.path.exists(catalog):
        old = json.load(open(catalog))
        new = {e["name"]: e for e in entries}
        names = [e["name"] for e in old]
        entries = [new.get(e["name"], e) for e in old] + [e for e in entries if e["name"] not in names]
    json.dump(entries, open(catalog, "w"), indent=1)
    items = [(os.path.join(LIBROOT, e["thumb"]), e["name"]) for e in entries]
    thumb.contact_sheet(items, os.path.join(LIBROOT, "thumbs", f"{category}_sheet.jpg"), cols=cols,
                        title=title or f"{category}  ({len(entries)} assets)")
    for o in list(bpy.data.objects):
        if o.name.startswith("Thumb"):
            bpy.data.objects.remove(o)
    if "_thumb_studio" in sc:
        del sc["_thumb_studio"]
    for _ in range(3):
        bpy.data.orphans_purge(do_local_ids=True, do_linked_ids=True, do_recursive=True)
    bpy.context.preferences.filepaths.save_version = 0
    out = blend if not opts["only"] else blend.replace(".blend", "_partial.blend")
    bpy.ops.wm.save_as_mainfile(filepath=out, compress=True)
    print(f"[{category}] done: {len(entries)} assets, failed: {failed}", flush=True)
    return entries, failed


def kenney(pack_dir, model, fmt="GLB format"):
    return f"{pack_dir}/raw/Models/{fmt}/{model}.glb"
