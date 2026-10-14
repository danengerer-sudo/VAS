# Asset library conventions

Everything here must drop straight into any video scene and take the house style
(matte white models, faction-colour accents, dark details) without per-asset fixes.

## Tooling
- Blender 4.2 LTS headless: `/opt/blender_dl/blender-4.2.23-linux-x64/blender -b --factory-startup -P script.py -- args`
- Shared helpers: `../scripts/lib.py` (box, cylinder, lathe, loft, extrude_profile, bevel, join, apply_mods...)
- Thumbnails: `scripts/thumb.py` (`thumbnail(objs, out_path)`), always use it so every thumb matches.
- 4 shared CPU cores: keep thumbnails at the defaults in thumb.py (small, low samples).

## Geometry
- Metres. Z up. Vehicles and directional things face **+X**. Origin at **ground level, centre of footprint**.
- Real-world proportions (a car ~4.5 m, a door ~2.1 m, a storey ~3.2 m).
- Moderate detail: clean silhouettes, bevelled edges (Bevel modifier or bevel geometry) so white surfaces catch light.
  No micro-detail that only matters with textures. Keep each asset under ~150k triangles (instancing for repeats).
- No image textures needed. Imported assets may keep textures, but must also work with materials overridden.

## Materials — use ONLY these material names (create with lib.pbr if missing)
| name | meaning | default colour |
|---|---|---|
| `LIB_Body` | main surfaces | (0.82, 0.81, 0.79) |
| `LIB_Accent` | faction / brand / livery colour, swapped per video | (0.95, 0.38, 0.06) |
| `LIB_Dark` | tyres, rubber, gun metal, vents, window frames | (0.035, 0.037, 0.04) |
| `LIB_Glass` | windows | (0.08, 0.09, 0.1), rough 0.08 |
| `LIB_Light` | lamps / emissive | white, emission 0 by default |
| `LIB_Metal` | gold, coins, chrome where colour matters | (0.8, 0.6, 0.2) metallic |
Imported packs: remap their materials onto these names (keep the original as a custom property if useful).

## Packaging
- Each category script (`scripts/build_<category>.py`) writes `build/<category>.blend`.
  Every asset lives in its own collection named `<category>/<asset_name>`, with `collection.asset_mark()`,
  and tags via `collection.asset_data.tags.new(...)`.
- Each asset also gets `thumbs/<category>/<asset_name>.jpg` and an entry in `catalog/<category>.json`:
  `{"name", "category", "collection", "file", "source", "license", "dims_m": [x,y,z], "tags": [...], "notes"}`.
- Plus `thumbs/<category>_sheet.jpg`: a contact sheet of the whole category, labelled.
- Sources: `procedural` (license: original), or the pack name with its license (only CC0 / public domain).
- `build/` and downloaded raw packs (`../assets/`) are not committed; scripts, thumbs and catalog are.
- Do NOT git commit; the coordinator commits.
