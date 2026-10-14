# How Free Market Defense Could Work — 3D short

A ~35 s rendered short (Blender 4.2 / Cycles), built entirely from scripts.

| Shot | Frames | Content |
|---|---|---|
| S1 | 1–96 | Aerial establishing shot + title |
| S2 | 97–216 | Checkpoint of a subscription defense agency, soldiers on patrol |
| S3 | 217–360 | Agency main battle tank on the road |
| S4 | 361–504 | Contracted helicopter crossing the coast |
| S5 | 505–624 | Maritime firm's patrol boat |
| S6 | 625–768 | Wide shot: all assets together (insurance-backed deterrence) |

## Models
- `scripts/tank.py`, `scripts/heli.py`, `scripts/boat.py` — procedural vehicles (lofted hulls, bevelled armour,
  arrayed track links on a curve, spinning rotors, livery decals).
- `scripts/soldier.py` — three.js `Soldier.glb` (Mixamo rig with Idle/Walk/Run) holding a Poly Haven rifle
  via two-bone IK.
- Props, trees, grass, rocks, HDRI sky and ground textures are CC0 from Poly Haven (`scripts/fetch_assets.py`).

## Build
```
python3 scripts/fetch_assets.py                 # + download Soldier.glb into assets/models/
blender -b --factory-startup -P scripts/scene.py -- render/scene.blend
scripts/render_all.sh                           # frames → render/frames/
python3 scripts/assemble.py                     # captions, title/end cards, MP4
```
