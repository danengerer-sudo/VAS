"""Build category `city` -> build/city.blend, thumbs/city/*, catalog/city.json.

blender -b --factory-startup -P scripts/build_city.py [-- --only=a,b --nothumb]
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import arch_lib as A  # noqa: E402
from genkit import MB, Category  # noqa: E402

cat = Category("city")


def call(fn, kw):
    return "arch_lib.%s(%s)" % (fn.__name__, ", ".join(f"{k}={v!r}" for k, v in kw.items()))


def add(name, fn, tags, notes="", bevel=0.03, az=-35, el=22, fill=1.0, **kw):
    def _():
        mb = MB()
        fn(mb, **kw)
        return mb.build(name, bevel=bevel)
    cat.add(name, _, tags=tags, notes=(notes + " " + call(fn, kw)).strip(), az=az, el=el, fill=fill)


def add_fn(name, body, tags, notes, bevel=0.02, az=-35, el=22, fill=1.0):
    """body(mb) for generators that take loc/rz (furniture)."""
    def _():
        mb = MB()
        body(mb)
        return mb.build(name, bevel=bevel)
    cat.add(name, _, tags=tags, notes=notes, az=az, el=el, fill=fill)


# --- layouts
add("city_block_mixed", A.city_block, ["block", "city", "street", "mixed use"],
    "84x60 m block: corner cafés/apartments, shop rows, street trees+lamps, sidewalk+kerb.", style="mixed", seed=1,
    el=35)
add("city_block_downtown", A.city_block, ["block", "city", "downtown", "towers", "finance"],
    "Downtown block: corner towers + skyscraper + infill offices.", style="downtown", w=90.0, d=70.0, seed=2, el=40, az=-60)
add("city_block_residential", A.city_block, ["block", "suburb", "houses", "residential"],
    "Suburban block: detached houses facing all streets, picket fences, trees.", style="residential", w=96.0,
    d=64.0, seed=3, el=40)
# --- roads
add("road_straight_2lane", A.road_straight, ["road", "street", "tile"], "24 m tile, dashed centre line; tiles in 6 m.",
    bevel=0.01, el=35)
add("road_straight_4lane", A.road_straight, ["road", "avenue", "tile"], "4-lane avenue tile, double centre line.",
    bevel=0.01, el=35, lanes=4, length=24.0)
add("road_intersection", A.road_intersection, ["road", "junction", "crosswalk", "tile"],
    "4-way junction: rounded kerbs, zebra crossings, stop lines.", bevel=0.01, el=45)
add("road_t_junction", A.road_intersection, ["road", "junction", "tile"], "T-junction (closed -Y side).", bevel=0.01,
    el=45, arms=3)
add("roundabout", A.roundabout, ["road", "roundabout", "junction"], "Roundabout with planted island + tree, 4 arms.",
    bevel=0.01, el=45)
add("parking_lot", A.parking_lot, ["parking", "car park", "lot"], "20-bay surface car park, wheel stops, lamps, P sign.",
    bevel=0.01, el=45)
add("plaza_fountain", A.plaza_fountain, ["plaza", "square", "fountain", "public space"],
    "Paved square with tiered fountain, benches, planted trees, classic lamps.", el=32)
add("park", A.park, ["park", "green", "trees", "pond"], "Park: lawns, paths, pond, trees, benches.", el=38)
# --- furniture
add_fn("street_lamp", lambda mb: A.street_lamp(mb, 8.0), ["street lamp", "lighting", "street furniture"],
       "Modern lamp post, luminaire toward +X (LIB_Light lens). arch_lib.street_lamp(mb, h=8)")
add_fn("street_lamp_double", lambda mb: A.street_lamp(mb, 9.0, double=True), ["street lamp", "lighting"],
       "Double-arm lamp. arch_lib.street_lamp(mb, 9, double=True)")
add_fn("street_lamp_classic", lambda mb: A.street_lamp(mb, 4.2, kind="classic"), ["street lamp", "lighting", "old town"],
       "Classic lantern post. arch_lib.street_lamp(mb, 4.2, kind='classic')")
add_fn("traffic_light_mast", lambda mb: A.traffic_light(mb, "mast"), ["traffic light", "signal", "junction"],
       "Mast-arm signal, heads face +X, arm over +Y. arch_lib.traffic_light(mb, 'mast', arm=6)")
add_fn("traffic_light_post", lambda mb: A.traffic_light(mb, "post"), ["traffic light", "signal"],
       "Post-mounted signal. arch_lib.traffic_light(mb, 'post')")
add("bus_stop", A.bus_stop, ["bus stop", "shelter", "transit", "street furniture"],
    "Glass shelter, bench, lit ad panel, accent stop roundel.", bevel=0.015)
add_fn("bench", lambda mb: A.bench(mb, 1.8), ["bench", "street furniture", "park"], "Park bench. arch_lib.bench(mb, 1.8)",
       bevel=0.008)
add_fn("bin_round", lambda mb: A.bin_(mb), ["bin", "litter", "street furniture"], "Litter bin. arch_lib.bin_(mb)",
       bevel=0.008)
add_fn("bin_wheelie", lambda mb: A.bin_(mb, kind="wheelie"), ["bin", "wheelie bin"],
       "Wheelie bin, accent lid. arch_lib.bin_(mb, kind='wheelie')", bevel=0.008)
add_fn("fire_hydrant", lambda mb: A.hydrant(mb), ["hydrant", "street furniture"], "Fire hydrant (LIB_Accent).",
       bevel=0.005)
for kind, h in (("round", 8.0), ("tall", 11.0), ("wide", 9.0), ("small", 5.5), ("conifer", 12.0)):
    add_fn(f"tree_{kind}", (lambda k, hh: (lambda mb: A.tree(mb, k, hh, seed=7)))(kind, h),
           ["tree", "vegetation", "park", kind], f"Stylised white tree. arch_lib.tree(mb, '{kind}', h={h}, seed=7)",
           bevel=0.0)
# --- bridges
add("bridge_beam", A.beam_bridge, ["bridge", "beam bridge", "road", "infrastructure"],
    "3-span girder bridge; params span, spans, width, clearance.", el=20)
add("bridge_arch", A.arch_bridge, ["bridge", "arch bridge", "infrastructure"],
    "Open-spandrel concrete deck arch; params span, rise, width, approach.", el=18)
add("bridge_masonry", A.masonry_bridge, ["bridge", "stone", "history", "arch"],
    "Historic 3-arch stone bridge; params arches, span, pier, width.", el=18)
add("bridge_suspension", A.suspension_bridge, ["bridge", "suspension bridge", "infrastructure", "iconic"],
    "Suspension bridge, 300 m main span; params main, side_f, width, deck_h, sag_f.", el=10, az=-20, fill=1.7,
    bevel=0.05)
# --- walls, fences, border
add("wall_concrete", A.wall_segment, ["wall", "boundary"], "12 m wall with pilasters + coping.", bevel=0.015)
add("fence_picket", A.picket_fence, ["fence", "picket", "garden"], "10 m picket fence.", bevel=0.005)
add("fence_security", A.security_fence, ["fence", "security", "border", "barbed wire"],
    "Weld-mesh security fence with concertina wire.", bevel=0.0)
add("border_wall", A.border_wall, ["wall", "border", "bollard"], "6 m steel bollard border wall.", bevel=0.01)
add_fn("jersey_barrier", lambda mb: A.jersey_barrier(mb), ["barrier", "concrete", "checkpoint"],
       "Concrete jersey barrier 3.8 m. arch_lib.jersey_barrier(mb)", bevel=0.01)
add("checkpoint_booth", A.checkpoint_booth, ["checkpoint", "booth", "boom gate", "border", "security"],
    "Guard booth, striped boom gate, jersey barriers, stop sign.", bevel=0.015)
add("border_checkpoint", A.border_checkpoint, ["border", "checkpoint", "customs", "trade", "iconic"],
    "Border crossing canopy over lanes with booths, gates, fences, flags.", bevel=0.02, el=28)
# --- energy / industry
add("wind_turbine", A.wind_turbine, ["wind turbine", "energy", "renewable"], "90 m hub, 58 m blades, rotor faces +X.",
    bevel=0.0, az=-50)
add("power_pylon", A.power_pylon, ["pylon", "power", "electricity", "grid"], "42 m lattice transmission tower.",
    bevel=0.0)
add("power_line", A.power_line, ["power line", "pylon", "electricity", "grid"], "3 pylons with sagging conductors.",
    bevel=0.0, el=10, az=-20, fill=1.6)
add("oil_pumpjack", A.pumpjack, ["oil", "pumpjack", "energy", "extraction"], "Nodding donkey; accent horsehead.",
    bevel=0.01)
add("oil_derrick", A.oil_derrick, ["oil", "drilling rig", "derrick", "energy"], "Drilling rig with lattice derrick.",
    bevel=0.0)
add("refinery_tank", A.refinery_tank, ["oil", "tank", "refinery", "storage"], "Storage tank, spiral stair, bund wall.",
    bevel=0.02)
add("storage_spheres", A.storage_spheres, ["gas", "lpg", "refinery", "storage"], "Pair of LPG spheres on legs.",
    bevel=0.0)
add("refinery_unit", A.refinery_unit, ["oil", "refinery", "industry", "flare"],
    "Distillation columns, pipe rack, furnace, flare stack with LIB_Fire flame.", bevel=0.0)

cat.finish(cols=6)
