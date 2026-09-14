#!/usr/bin/env python3
"""
Dependency-free preview renderer for the sedan GLB.

Parses a .glb, flattens the node hierarchy, and rasterises a flat-shaded,
z-buffered PNG so you can eyeball the model without opening a 3D app.

    python3 tools/preview_glb.py models/sedan_lowpoly.glb -o preview.png

It only understands the subset of glTF this repo produces (float VEC3
positions/normals, scalar indices, node translations) -- it is a sanity
check for the generator, not a general purpose viewer.
"""

import argparse
import json
import math
import struct
import zlib


# ---------------------------------------------------------------- glb parsing


def load_glb(path):
    data = open(path, "rb").read()
    magic, version, _ = struct.unpack("<III", data[:12])
    assert magic == 0x46546C67 and version == 2, "not a glTF 2.0 binary"
    off, gltf, blob = 12, None, b""
    while off < len(data):
        length, ctype = struct.unpack("<II", data[off:off + 8])
        chunk = data[off + 8:off + 8 + length]
        if ctype == 0x4E4F534A:
            gltf = json.loads(chunk.decode("utf-8"))
        elif ctype == 0x004E4942:
            blob = chunk
        off += 8 + length
    return gltf, blob


def read_accessor(gltf, blob, index):
    acc = gltf["accessors"][index]
    view = gltf["bufferViews"][acc["bufferView"]]
    base = view.get("byteOffset", 0) + acc.get("byteOffset", 0)
    fmt = {5123: "<H", 5125: "<I", 5126: "<f"}[acc["componentType"]]
    size = struct.calcsize(fmt)
    n = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4}[acc["type"]]
    out = []
    for i in range(acc["count"]):
        p = base + i * size * n
        vals = [struct.unpack_from(fmt, blob, p + k * size)[0] for k in range(n)]
        out.append(vals[0] if n == 1 else tuple(vals))
    return out


def collect_triangles(gltf, blob):
    """-> list of (v0, v1, v2, normal, base_color, emissive)"""
    tris = []
    for node in gltf["nodes"]:
        if "mesh" not in node:
            continue
        tx, ty, tz = node.get("translation", [0.0, 0.0, 0.0])
        for prim in gltf["meshes"][node["mesh"]]["primitives"]:
            pos = read_accessor(gltf, blob, prim["attributes"]["POSITION"])
            nrm = read_accessor(gltf, blob, prim["attributes"]["NORMAL"])
            idx = read_accessor(gltf, blob, prim["indices"])
            mat = gltf["materials"][prim["material"]]
            col = mat["pbrMetallicRoughness"]["baseColorFactor"][:3]
            emi = mat.get("emissiveFactor", [0.0, 0.0, 0.0])
            for i in range(0, len(idx), 3):
                vs = []
                for k in range(3):
                    x, y, z = pos[idx[i + k]]
                    vs.append((x + tx, y + ty, z + tz))
                tris.append((vs[0], vs[1], vs[2], nrm[idx[i]], col, emi))
    return tris


# ------------------------------------------------------------------ rendering


def render(tris, width, height, eye, target, fov_deg=32.0, up=(0.0, 1.0, 0.0)):
    def sub(a, b):
        return (a[0] - b[0], a[1] - b[1], a[2] - b[2])

    def cross(a, b):
        return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2],
                a[0] * b[1] - a[1] * b[0])

    def dot(a, b):
        return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]

    def unit(v):
        m = math.sqrt(dot(v, v)) or 1.0
        return (v[0] / m, v[1] / m, v[2] / m)

    fwd = unit(sub(target, eye))
    right = unit(cross(fwd, up))
    upv = cross(right, fwd)
    f = 1.0 / math.tan(math.radians(fov_deg) * 0.5)
    aspect = width / float(height)

    # sky gradient background
    fb = []
    for y in range(height):
        t = y / float(height - 1)
        c = (int(210 - 55 * t), int(222 - 45 * t), int(236 - 40 * t))
        fb.append([c] * width)
    zbuf = [[1e30] * width for _ in range(height)]

    key = unit((-0.45, 0.82, -0.36))
    fill = unit((0.65, 0.25, 0.55))

    for a, b, c, n, col, emi in tris:
        pts, depths = [], []
        ok = True
        for v in (a, b, c):
            d = sub(v, eye)
            cam = (dot(d, right), dot(d, upv), dot(d, fwd))
            if cam[2] < 0.05:
                ok = False
                break
            sx = (cam[0] / cam[2]) * f / aspect
            sy = (cam[1] / cam[2]) * f
            pts.append(((sx * 0.5 + 0.5) * width, (0.5 - sy * 0.5) * height))
            depths.append(cam[2])
        if not ok:
            continue

        (x0, y0), (x1, y1), (x2, y2) = pts
        area = (x1 - x0) * (y2 - y0) - (x2 - x0) * (y1 - y0)
        if area >= 0:  # back face (screen y is flipped)
            continue

        lam = max(0.0, dot(n, key)) * 0.85 + max(0.0, dot(n, fill)) * 0.22
        sky = 0.18 + 0.16 * (n[1] * 0.5 + 0.5)
        shade = [min(1.0, (col[i] ** (1 / 2.2)) * (lam + sky) + emi[i] * 0.8)
                 for i in range(3)]
        rgb = tuple(int(255 * min(1.0, max(0.0, v))) for v in shade)

        minx = max(0, int(math.floor(min(x0, x1, x2))))
        maxx = min(width - 1, int(math.ceil(max(x0, x1, x2))))
        miny = max(0, int(math.floor(min(y0, y1, y2))))
        maxy = min(height - 1, int(math.ceil(max(y0, y1, y2))))
        if minx > maxx or miny > maxy:
            continue
        inv = 1.0 / area

        for py in range(miny, maxy + 1):
            fy = py + 0.5
            row, zrow = fb[py], zbuf[py]
            for px in range(minx, maxx + 1):
                fx = px + 0.5
                w0 = ((x1 - x0) * (fy - y0) - (fx - x0) * (y1 - y0)) * inv
                w1 = ((fx - x0) * (y2 - y0) - (x2 - x0) * (fy - y0)) * inv
                if w0 < 0.0 or w1 < 0.0 or w0 + w1 > 1.0:
                    continue
                w2, w1b = w0, w1
                bary = (1.0 - w1b - w2, w1b, w2)
                z = 1.0 / max(1e-9, sum(bary[i] / depths[i] for i in range(3)))
                if z < zrow[px]:
                    zrow[px] = z
                    row[px] = rgb
    return fb


def write_png(path, fb):
    height, width = len(fb), len(fb[0])
    raw = bytearray()
    for row in fb:
        raw.append(0)
        for r, g, b in row:
            raw += bytes((r, g, b))

    def chunk(tag, payload):
        return (struct.pack(">I", len(payload)) + tag + payload
                + struct.pack(">I", zlib.crc32(tag + payload) & 0xFFFFFFFF))

    png = (b"\x89PNG\r\n\x1a\n"
           + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
           + chunk(b"IDAT", zlib.compress(bytes(raw), 6))
           + chunk(b"IEND", b""))
    open(path, "wb").write(png)


VIEWS = {
    "hero": ((5.6, 3.0, -6.2), (0.0, 0.72, -0.1)),
    "side": ((9.5, 1.35, 0.0), (0.0, 0.78, 0.0)),
    "front": ((0.9, 1.6, -8.4), (0.0, 0.80, -0.6)),
    "rear": ((-1.2, 1.9, 8.2), (0.0, 0.80, 0.6)),
    "top": ((0.02, 13.5, 0.6), (0.0, 0.7, 0.0)),
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("glb")
    ap.add_argument("-o", "--out", default="preview.png")
    ap.add_argument("-v", "--view", default="hero", choices=sorted(VIEWS))
    ap.add_argument("-w", "--width", type=int, default=640)
    ap.add_argument("-t", "--height", type=int, default=400)
    args = ap.parse_args()

    gltf, blob = load_glb(args.glb)
    tris = collect_triangles(gltf, blob)
    eye, target = VIEWS[args.view]
    fb = render(tris, args.width, args.height, eye, target)
    write_png(args.out, fb)
    print("%s  (%d triangles, view=%s)" % (args.out, len(tris), args.view))


if __name__ == "__main__":
    main()
