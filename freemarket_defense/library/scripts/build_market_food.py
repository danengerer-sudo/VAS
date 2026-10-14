"""market_food: shop / supermarket fittings (Kenney Mini Market) and food & packaged goods (Kenney Food Kit).

Mini Market: 1 unit = 2.2 m (shelf 1.9 m, counter 1.3 m). Food Kit: x0.4 (tabletop scale: apple ~8 cm,
loaf ~18 cm, milk carton ~24 cm) - food items are ~real size, so scale them up in a shot when used
as hero props. The source colours are kept in the `orig_color` attribute (useful for food).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pack_import as pi  # noqa: E402

CAT = "market_food"
MM = ("kenney_mini_market", "Kenney Mini Market", "https://kenney.nl/assets/mini-market")
FK = ("kenney_food_kit", "Kenney Food Kit", "https://kenney.nl/assets/food-kit")
MARKET = {
    "shelf-boxes": ["shelf", "supermarket"], "shelf-bags": ["shelf", "supermarket"], "shelf-end": ["shelf", "supermarket"],
    "cash-register": ["checkout", "counter", "till"], "freezer": ["freezer", "fridge"],
    "freezers-standing": ["freezer", "fridge"], "display-fruit": ["display", "produce", "stall"],
    "display-bread": ["display", "bakery"], "shopping-cart": ["cart", "trolley"], "shopping-basket": ["basket"],
    "bottle-return": ["machine", "recycling"], "column": ["architecture"], "wall": ["architecture", "wall"],
    "wall-window": ["architecture", "wall", "window"], "wall-door-rotate": ["architecture", "wall", "door"],
    "wall-corner": ["architecture", "wall"], "floor": ["architecture", "floor"], "fence": ["fence", "barrier"],
}
FOOD = {
    "apple": "produce", "banana": "produce", "orange": "produce", "lemon": "produce", "pear": "produce",
    "pineapple": "produce", "watermelon": "produce", "grapes": "produce", "strawberry": "produce",
    "carrot": "produce", "tomato": "produce", "cabbage": "produce", "broccoli": "produce", "corn": "produce",
    "onion": "produce", "pumpkin": "produce", "eggplant": "produce", "mushroom": "produce", "paprika": "produce",
    "bread": "bakery", "loaf": "bakery", "loaf-baguette": "bakery", "loaf-round": "bakery", "croissant": "bakery",
    "cake": "bakery", "cupcake": "bakery", "donut": "bakery", "muffin": "bakery", "pie": "bakery",
    "cheese": "dairy", "egg": "dairy", "carton": "packaged", "carton-small": "packaged", "can": "packaged",
    "can-small": "packaged", "bag": "packaged", "bag-flat": "packaged", "bottle-ketchup": "packaged",
    "bottle-oil": "packaged", "honey": "packaged", "peanut-butter": "packaged", "soda-bottle": "drinks",
    "soda-can": "drinks", "wine-red": "drinks", "wine-white": "drinks", "cup-coffee": "drinks", "mug": "drinks",
    "barrel": "packaged", "pizza-box": "packaged", "candy-bar": "packaged", "chocolate": "packaged",
    "burger": "fast_food", "fries": "fast_food", "hot-dog": "fast_food", "pizza": "fast_food", "sandwich": "fast_food",
    "taco": "fast_food", "ice-cream": "fast_food", "soda": "fast_food",
    "meat-raw": "butcher", "meat-ribs": "butcher", "fish": "butcher", "whole-ham": "butcher", "sausage": "butcher",
    "plate": "tableware", "pot": "kitchen", "frying-pan": "kitchen", "cutting-board": "kitchen",
}
specs = []
for m, tags in MARKET.items():
    specs.append(dict(name="market_" + m.replace("-", "_").replace("_rotate", ""), file=pi.kenney(MM[0], m),
                      scale=2.2, rot_z=90, profile="prop", dark_lum=0.2, tags=["market", "shop", "retail"] + tags,
                      notes="Mini Market, 1 unit = 2.2 m", source=MM[1], license="CC0 1.0", url=MM[2]))
for m, grp in FOOD.items():
    specs.append(dict(name="food_" + m.replace("-", "_"), file=pi.kenney(FK[0], m), scale=0.4, rot_z=90,
                      profile="prop", tags=["food", grp], notes="Food Kit, x0.4 (real size); orig colours in orig_color",
                      source=FK[1], license="CC0 1.0", url=FK[2]))

if __name__ == "__main__":
    pi.build(CAT, specs, cols=10)
