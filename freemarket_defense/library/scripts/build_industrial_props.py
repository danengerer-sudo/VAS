"""industrial_props: factory / logistics props (Kenney Factory Kit, City Kit Industrial details, Survival Kit).

Factory Kit: 1 unit = 1.6 m (conveyor 0.64 m high, 1.6 m wide). City Kit Industrial details: 8 m/tile
(shipping container 7.5). Survival Kit: x3 (barrel 1 m). Stripe/warning colours -> LIB_Accent.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pack_import as pi  # noqa: E402

CAT = "industrial_props"
P = {
    "fac": ("kenney_factory_kit", "Kenney Factory Kit 3.0", "https://kenney.nl/assets/factory-kit", 1.6),
    "ind": ("kenney_city_industrial", "Kenney City Kit (Industrial) 2.0", "https://kenney.nl/assets/city-kit-industrial", 8.0),
    "sur": ("kenney_survival_kit", "Kenney Survival Kit", "https://kenney.nl/assets/survival-kit", 3.0),
}
ITEMS = {
    "fac": {
        "conveyor": ["conveyor"], "conveyor-long": ["conveyor"], "conveyor-stripe": ["conveyor"],
        "conveyor-corner": ["conveyor"], "conveyor-sides": ["conveyor"], "conveyor-bars-high": ["conveyor"],
        "conveyor-bars-high-slope": ["conveyor"], "robot-arm-a": ["robot", "automation"],
        "robot-arm-b": ["robot", "automation"], "machine": ["machine"], "machine-window": ["machine"],
        "machine-fortified": ["machine"], "machine-bed": ["machine"], "scanner-high": ["machine", "scanner"],
        "scanner-low": ["machine", "scanner"], "hopper-round": ["hopper"], "hopper-square": ["hopper"],
        "hopper-high-round": ["hopper"], "crane": ["crane"], "crane-lift": ["crane"], "crane-magnet": ["crane"],
        "piston-round": ["machine"], "piston-square": ["machine"], "cog-a": ["cog", "gear"], "cog-b": ["cog", "gear"],
        "pipe-large": ["pipe"], "pipe-large-bend": ["pipe"], "pipe-large-valve": ["pipe", "valve"],
        "pipe-glass-large": ["pipe"], "box-large": ["box", "crate"], "box-small": ["box"], "box-long": ["box"],
        "box-wide": ["box"], "screen-wide": ["screen", "monitor"], "screen-panel-wide": ["screen", "control_panel"],
        "lever-double": ["lever", "control"], "button-floor-round": ["button"], "catwalk-straight": ["catwalk"],
        "catwalk-stairs": ["catwalk", "stairs"], "structure-tall": ["structure"], "structure-wall": ["structure", "wall"],
        "structure-window": ["structure", "wall"], "structure-doorway-wide": ["structure", "door"],
        "door-wide-closed": ["door"], "warning-traffic": ["warning", "barrier"], "warning-orange": ["warning"],
        "cone": ["cone"], "floor": ["floor"],
    },
    "ind": {
        "chimney-basic": ["chimney"], "chimney-large": ["chimney"], "chimney-medium": ["chimney"],
        "detail-tank": ["tank"], "detail-tank-large": ["tank"], "water-tower": ["water_tower"],
        "windmill": ["wind_turbine", "energy"], "windmill-low": ["wind_turbine", "energy"],
        "shipping-container-a": ["container", "shipping", "trade"], "shipping-container-b": ["container", "shipping", "trade"],
        "shipping-container-c": ["container", "shipping", "trade"], "solar-panel-flat": ["solar", "energy"],
        "solar-panel-landscape": ["solar", "energy"], "solar-panel-portrait-group": ["solar", "energy"],
    },
    "sur": {
        "barrel": ["barrel"], "barrel-open": ["barrel"], "box": ["crate"], "box-large": ["crate"],
        "box-open": ["crate"], "box-large-open": ["crate"], "bucket": ["bucket"], "chest": ["chest", "treasure"],
        "workbench": ["workbench", "craft"], "workbench-anvil": ["workbench", "anvil", "craft"],
        "workbench-grind": ["workbench", "craft"], "tent": ["tent"], "tent-canvas": ["tent"],
        "resource-planks": ["resource", "lumber"], "resource-wood": ["resource", "lumber"],
        "resource-stone": ["resource", "stone"], "tool-axe": ["tool"], "tool-hammer": ["tool"],
        "tool-pickaxe": ["tool"], "tool-shovel": ["tool"], "tool-hoe": ["tool"], "structure-metal": ["shed"],
        "metal-panel": ["panel"],
    },
}
SCALE_OVR = {"shipping-container-a": 7.5, "shipping-container-b": 7.5, "shipping-container-c": 7.5}
specs = []
for pk, items in ITEMS.items():
    d, src, url, s = P[pk]
    for m, tags in items.items():
        nm = {"fac": "factory_", "ind": "", "sur": ""}[pk] + m.replace("-", "_")
        if pk == "sur" and m.startswith("box"):
            nm = "crate" + m[3:].replace("-", "_")
        sc = SCALE_OVR.get(m, s)
        specs.append(dict(name=nm, file=pi.kenney(d, m), scale=sc, rot_z=90, profile="prop",
                          tags=["industrial", "prop"] + tags, notes=f"{src}, scale x{sc}", source=src,
                          license="CC0 1.0", url=url))

if __name__ == "__main__":
    pi.build(CAT, specs, cols=10)
