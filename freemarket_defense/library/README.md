# Asset library

756 assets in 14 categories, all CC0 or original. Conventions: [CONVENTIONS.md](CONVENTIONS.md).

| category | assets | source | sheet |
|---|---|---|---|
| `buildings` | 33 | procedural | [sheet](thumbs/buildings_sheet.jpg) |
| `city` | 45 | procedural | [sheet](thumbs/city_sheet.jpg) |
| `city_buildings_kenney` | 76 | Kenney City Kit (Commercial) 2.1, Kenney City Kit (Industrial) 2.0, Ke | [sheet](thumbs/city_buildings_kenney_sheet.jpg) |
| `commerce` | 57 | procedural | [sheet](thumbs/commerce_sheet.jpg) |
| `everyday_objects_ph` | 63 | Poly Haven: Barrel_01, Poly Haven: Camera_01, Poly Haven: CashRegister | [sheet](thumbs/everyday_objects_ph_sheet.jpg) |
| `furniture_interior` | 91 | Kenney Furniture Kit | [sheet](thumbs/furniture_interior_sheet.jpg) |
| `fx` | 22 | procedural | [sheet](thumbs/fx_sheet.jpg) |
| `industrial_props` | 84 | Kenney City Kit (Industrial) 2.0, Kenney Factory Kit 3.0, Kenney Survi | [sheet](thumbs/industrial_props_sheet.jpg) |
| `market_food` | 86 | Kenney Food Kit, Kenney Mini Market | [sheet](thumbs/market_food_sheet.jpg) |
| `military` | 3 | procedural | [sheet](thumbs/military_sheet.jpg) |
| `roads_kenney` | 44 | Kenney City Kit (Roads), Kenney Train Kit | [sheet](thumbs/roads_kenney_sheet.jpg) |
| `street_props` | 52 | Kenney City Kit (Commercial) 2.1, Kenney City Kit (Roads), Kenney City | [sheet](thumbs/street_props_sheet.jpg) |
| `vehicles` | 39 | procedural | [sheet](thumbs/vehicles_sheet.jpg) |
| `vehicles_kenney` | 61 | Kenney Car Kit, Kenney Train Kit, Kenney Watercraft Kit | [sheet](thumbs/vehicles_kenney_sheet.jpg) |

## Using it
```python
sys.path += ['library/scripts', 'scripts']
from libload import place
place('buildings', 'bank_classical', (x, y, 0), rot_z)   # appends once, instances after
from mhuman import make_person                           # people (MakeHuman + mocap)
make_person('P1', sex='female', age='adult', mode='walk', weapon=None)
```

- `build/<category>.blend` are generated (not committed): run `scripts/build_<category>.py` to rebuild.
- Catalog entries (`catalog/*.json`) list dims, tags, source, license, and the generator call for procedural assets.
- People: `scripts/mhuman.py` (needs the MPFB extension + MakeHuman CC0 system assets, see `scripts/setup_mpfb.sh`).
- Motion-capture library: CMU (free for any use), curated poses in `scripts/mfigure.py` (CASUAL / TALK / WALK / TACTICAL).
