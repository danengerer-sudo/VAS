"""Build category `fx` -> build/fx.blend, thumbs/fx/*, catalog/fx.json.

blender -b --factory-startup -P scripts/build_fx.py [-- --only=a,b --nothumb]
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fx_lib as F  # noqa: E402
from genkit import MB, Category  # noqa: E402

cat = Category("fx")


def add(name, body, tags, notes, bevel=0.0, az=-35, el=22, fill=1.0, lift=0.0):
    def _():
        mb = MB()
        body(mb)
        return mb.build(name, bevel=bevel)
    cat.add(name, _, tags=tags, notes=notes, az=az, el=el, fill=fill, lift=lift)


for st in ("ignition", "fireball", "billow", "dissipating"):
    add(f"explosion_{st}", (lambda s: (lambda mb: F.explosion(mb, s, 10.0, seed=3)))(st),
        ["explosion", "blast", st, "war"], f"Frozen explosion stage '{st}' (~10 m fireball). fx_lib.explosion(mb, stage, size, seed)")
add("smoke_column", lambda mb: F.smoke_column(mb), ["smoke", "plume", "fire"],
    "40 m plume drifting +X with fire at base. fx_lib.smoke_column(mb, height, base_r, lean, fire)")
add("dust_cloud", lambda mb: F.dust_cloud(mb), ["dust", "cloud", "impact"], "Low wide dust billow. fx_lib.dust_cloud(mb, radius, height)",
    el=25)
add("fire_patch", lambda mb: F.fire_patch(mb), ["fire", "flames"], "Cluster of flame tongues (LIB_Fire). fx_lib.fire_patch(mb, radius, height, n)")
add("building_on_fire", lambda mb: F.building_on_fire(mb), ["fire", "building", "damage", "war"],
    "Damaged block with window flames, roof fire and smoke plume. fx_lib.building_on_fire(mb, w, d, h)", bevel=0.02)
add("muzzle_flash", lambda mb: F.muzzle_flash(mb), ["muzzle flash", "gunfire", "weapon"],
    "0.8 m star flash pointing +X; origin = muzzle (not ground). fx_lib.muzzle_flash(mb, length)", az=-60, lift=0.5)
add("rubble_pile", lambda mb: F.rubble(mb), ["rubble", "debris", "destruction"], "Debris mound with slabs + rebar. fx_lib.rubble(mb, radius, height)",
    bevel=0.02)
add("debris_field", lambda mb: F.debris(mb, 40, 8.0, 0.0, 0.5, seed=2, airborne=False), ["debris", "destruction"],
    "Scattered chunks on the ground. fx_lib.debris(mb, n, radius, airborne=False)", bevel=0.01, el=35)
add("crater", lambda mb: F.crater(mb), ["crater", "impact", "shell", "war"],
    "Crater built above ground (raised rim, scorched floor). fx_lib.crater(mb, radius, depth)", el=35)
add("impact_marks", lambda mb: F.impact_marks(mb), ["scorch", "impact", "marks"], "Scorch splats + strike rings. fx_lib.impact_marks(mb, n, area)",
    el=50)
add("tracer", lambda mb: F.tracer(mb, n=1), ["tracer", "gunfire", "bullet"], "Single tracer flying +X. fx_lib.tracer(mb, length, r)", az=-70)
add("tracer_burst", lambda mb: F.tracer(mb, n=5, seed=4), ["tracer", "gunfire", "burst"], "Five tracers. fx_lib.tracer(mb, n=5)", az=-70)
add("map_arrow", lambda mb: F.map_arrow(mb), ["map", "arrow", "advance", "campaign"],
    "Thick curved arrow on the ground, accent. fx_lib.map_arrow(mb, path, width, height, head)", el=45, bevel=0.03)
add("map_arrow_straight", lambda mb: F.map_arrow(mb, ((0, 0), (20, 0)), 2.0, 0.5, 4.0), ["map", "arrow"],
    "fx_lib.map_arrow(mb, ((0,0),(20,0)), 2.0, 0.5, 4.0)", el=45, bevel=0.03)
add("territory_boundary", lambda mb: F.territory_line(mb, fill=True), ["map", "territory", "border", "boundary"],
    "Dashed accent boundary with light tint plate. fx_lib.territory_line(mb, pts, closed, fill)", el=55)
add("range_ring", lambda mb: F.range_ring(mb), ["map", "range", "ring", "radius"], "Range ring with ticks. fx_lib.range_ring(mb, radius)",
    el=50)
add("radar_circle", lambda mb: F.radar_circle(mb), ["map", "radar", "scope", "detection"], "Radar scope with sweep wedge + blips. fx_lib.radar_circle(mb, radius, rings, sweep_deg)",
    el=55)
add("pin_marker", lambda mb: F.pin_marker(mb), ["map", "pin", "location", "marker"], "3 m map pin. fx_lib.pin_marker(mb, h)",
    bevel=0.0, az=-20)
add("label_board", lambda mb: F.label_board(mb, "LABEL", "subtitle"), ["label", "sign", "annotation", "callout"],
    "Floating label on a stem, readable from +X. fx_lib.label_board(mb, text, sub, h, z)", bevel=0.01, az=-20)

cat.finish(cols=6)
