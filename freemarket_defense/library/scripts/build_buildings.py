"""Build category `buildings` -> build/buildings.blend, thumbs/buildings/*, catalog/buildings.json.

blender -b --factory-startup -P scripts/build_buildings.py [-- --only=a,b --nothumb]
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import arch_lib as A  # noqa: E402
from genkit import MB, Category  # noqa: E402

cat = Category("buildings")


def gen(name, fn, bevel=0.03, **kw):
    def _():
        mb = MB()
        fn(mb, **kw)
        return mb.build(name, bevel=bevel)
    return _


def call(fn, **kw):
    return "arch_lib.%s(%s)" % (fn.__name__, ", ".join(f"{k}={v!r}" for k, v in kw.items()))


def add(name, fn, tags, notes="", bevel=0.03, az=-35, el=22, **kw):
    cat.add(name, gen(name, fn, bevel, **kw), tags=tags, notes=(notes + " " + call(fn, **kw)).strip(), az=az, el=el)


# --- houses
add("house_gable", A.house, ["house", "residential", "suburb"], "Detached 2-storey house, gable roof, porch.",
    roof="gable", storeys=2)
add("house_hip", A.house, ["house", "residential", "suburb"], "Detached house, hip roof.", roof="hip", storeys=2,
    porch=True, frontage=11.0, depth=9.0, seed=1)
add("house_flat_modern", A.house, ["house", "residential", "modern"], "Modern flat-roof house, large windows.",
    roof="flat", storeys=2, porch=False, chimneys=0, frontage=12.0, depth=9.0)
add("cottage_1storey", A.house, ["house", "residential", "rural"], "Single-storey cottage.", roof="gable",
    storeys=1, frontage=9.0, depth=7.0, porch=True, pitch=42)
add("terraced_row", A.terrace, ["house", "terrace", "row", "residential"], "Row of terraced houses (bay windows).",
    units=5)
add("apartment_block", A.apartment, ["apartment", "residential", "housing"], "Mid-rise apartment block with balconies.",
    storeys=6)
add("apartment_tall", A.apartment, ["apartment", "residential", "housing"], "Taller slab block.", storeys=10,
    width=24.0, balconies=True, seed=3)
# --- offices
add("office_tower_curtain", A.office_tower, ["office", "tower", "commercial", "downtown"],
    "Glass curtain-wall office tower with a setback; accent logo band.", storeys=16, style="curtain")
add("office_tower_punched", A.office_tower, ["office", "tower", "commercial", "downtown"],
    "Office tower with punched windows, two setbacks.", storeys=14, style="punched",
    tiers=((0.55, 0.85), (0.85, 0.65)), width=28.0, depth=24.0)
add("office_midrise", A.office_tower, ["office", "commercial"], "Low office block (6 storeys).",
    storeys=6, style="curtain", tiers=(), width=36.0, depth=18.0, logo=True)
add("skyscraper_spire", A.skyscraper, ["skyscraper", "tower", "downtown", "finance"], "Supertall with spire crown.",
    crown="spire")
add("skyscraper_deco", A.skyscraper, ["skyscraper", "tower", "downtown", "finance"], "Art-deco stepped crown.",
    crown="deco", storeys=50, taper=(1.0, 0.82, 0.66))
add("skyscraper_pyramid", A.skyscraper, ["skyscraper", "tower", "downtown", "finance"], "Glass pyramid crown.",
    crown="pyramid", storeys=44, width=32.0, taper=(1.0, 0.9, 0.8))
# --- commerce
add("storefront_shop", A.storefront, ["shop", "retail", "storefront", "high street"],
    "Shop: display window, accent awning + sign panel.", sign="SHOP")
add("storefront_market", A.storefront, ["shop", "retail", "storefront"], "Shop with striped awning, 2 storeys.",
    sign="MARKET", storeys=2, frontage=9.0, stripes=7)
add("corner_cafe", A.corner_cafe, ["cafe", "retail", "corner", "high street"], "Corner café, striped awnings, terrace.")
add("bank_classical", A.classical, ["bank", "finance", "classical", "iconic"],
    "Classical bank: steps, columns, pediment with accent emblem, frieze text, bronze doors.", text="BANK")
add("stock_exchange", A.classical, ["exchange", "finance", "classical", "iconic"], "Stock exchange: 8 columns, ionic.",
    text="STOCK EXCHANGE", columns=8, width=34.0, depth=30.0, height=15.0, order="ionic")
add("central_bank", A.classical, ["central bank", "finance", "government", "classical"],
    "Central bank: portico, attic storey, side wings.", text="CENTRAL BANK", columns=6, width=26.0, depth=28.0,
    height=13.0, wings=1, attic=3.0, order="ionic")
add("parliament_dome", A.classical, ["parliament", "government", "dome", "classical"],
    "Parliament: domed central block with wings.", text="", columns=8, width=34.0, depth=30.0, height=14.0,
    dome=True, wings=1, wing_w=28.0, emblem=True)
# --- industry / logistics
add("warehouse", A.warehouse, ["warehouse", "logistics", "industrial"], "Portal-frame warehouse with dock doors.")
add("factory_sawtooth", A.factory, ["factory", "industrial", "manufacturing"],
    "Factory: sawtooth north-light roof, chimney stacks, office block.")
add("port_terminal_shed", A.port_shed, ["port", "shed", "logistics", "trade"], "Barrel-vault transit shed.")
add("gas_station", A.gas_station, ["gas station", "fuel", "retail", "energy"], "Canopy, pumps, kiosk, price pylon.")
# --- civic
add("church", A.church, ["church", "civic", "religion", "town"], "Gothic-ish church: spire, pointed windows.")
add("town_hall", A.town_hall, ["town hall", "civic", "government", "clock"], "Town hall with clock tower.")
add("school", A.school, ["school", "civic", "education"], "L-shaped school, ribbon windows, flag.")
add("hospital", A.hospital, ["hospital", "civic", "health"], "Hospital tower + podium, accent cross, helipad.")
# --- history / rural
add("castle", A.castle, ["castle", "history", "medieval", "fortification"], "Curtain walls, towers, gatehouse, keep.")
add("castle_roofed", A.castle, ["castle", "history", "medieval"], "Castle variant with conical tower roofs.",
    roofs=True, size=36.0)
add("star_fort", A.star_fort, ["fort", "history", "fortification", "early modern"], "Bastioned star fort with moat.",
    el=35)
add("farm_barn_silo", A.barn, ["farm", "barn", "rural", "agriculture"], "Gambrel barn with accent doors + silo.")
add("grain_silos", A.silo_group, ["farm", "silo", "agriculture", "industrial"], "Grain elevator silo row.")

cat.finish(cols=6)
