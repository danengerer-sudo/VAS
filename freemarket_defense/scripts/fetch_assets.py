"""Download CC0 assets from Poly Haven (models, HDRI, textures)."""
import json, os, sys, urllib.request
opener = urllib.request.build_opener(); opener.addheaders = [("User-Agent", "fmd-video/1.0")]
urllib.request.install_opener(opener)
ROOT = os.path.join(os.path.dirname(__file__), "..", "assets")
MODELS = ["bolt_action_rifle_7_62", "ammo_box", "wooden_military_crate", "old_military_crate",
          "metal_jerrycan_green", "concrete_road_barrier", "pine_sapling_small", "tree_small_02", "grass_medium_01", "wild_rooibos_bush",
          "coast_rocks_01", "rock_moss_set_01", "wooden_barrels_01", "modular_chainlink_fence"]
HDRI = "kloofendal_48d_partly_cloudy_puresky"
TEXTURES = ["aerial_grass_rock", "aerial_rocks_02", "brown_mud_leaves_01", "coast_sand_01"]

def get(url, dst):
    if os.path.exists(dst): return
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    for attempt in range(5):
        try:
            urllib.request.urlretrieve(url, dst + ".part"); os.replace(dst + ".part", dst); return
        except Exception as e:
            print("retry", url, e)
    raise RuntimeError(url)

def files(asset):
    return json.load(urllib.request.urlopen(f"https://api.polyhaven.com/files/{asset}"))

for m in MODELS:
    g = files(m)["gltf"]["1k"]["gltf"]
    d = os.path.join(ROOT, "models", m)
    get(g["url"], os.path.join(d, os.path.basename(g["url"])))
    for rel, inc in g["include"].items():
        get(inc["url"], os.path.join(d, rel))
    print("model", m)
h = files(HDRI)["hdri"]["2k"]["hdr"]["url"]
get(h, os.path.join(ROOT, "hdri", os.path.basename(h))); print("hdri", h)
for t in TEXTURES:
    f = files(t)
    for k in ["Diffuse", "nor_gl", "Rough", "Displacement"]:
        if k in f:
            u = f[k]["2k"]["jpg"]["url"] if "jpg" in f[k]["2k"] else f[k]["2k"]["png"]["url"]
            get(u, os.path.join(ROOT, "textures", t, os.path.basename(u)))
    print("tex", t)
