# helicopter_lowpoly.glb

A low-poly helicopter for real-time use, with a transparent windscreen and a
modelled cabin behind it. Regenerate both detail levels with:

    python3 tools/make_helicopter.py assets/models/helicopter_lowpoly.glb

| File | Triangles | Size | Use |
|---|---|---|---|
| `helicopter_lowpoly.glb` | 1326 | 107 KB | hero / close-up |
| `helicopter_lowpoly_min.glb` | 802 | 67 KB | distance LOD |

Both come off the same geometry — `minimal` drops resolution and bolt-on detail
(driveshaft cover, swashplate, pitch links) but keeps every silhouette station,
so the two read identically at distance.

## Real-world reference

Modelled on the **Robinson R22** — the small round-bubble two-seat piston
helicopter.

| Dimension | Real R22 | This model |
|---|---|---|
| Fuselage length (nose → fin trailing edge) | 6.30 m | 6.30 m |
| Main rotor diameter | 7.67 m | 7.67 m |
| Tail rotor diameter | 1.07 m | 1.07 m |
| Overall height (to rotor head) | 2.72 m | 2.69 m |
| Skid track | ~1.90 m | 1.90 m |

## Asset facts

- Units are **metres**, **+Y up**, **nose toward −Z**, origin on the ground
  centred between the skids — so it drops straight onto a ground plane at y=0.
- Flat shaded (per-face normals), no UVs or textures. Recolour by editing the
  `baseColorFactor` values in `tools/make_helicopter.py`.
- The fuselage is **one lofted surface** — bubble, tailcone and fin sweep are
  stations of a single profile table (`SECTIONS`), so there are no seams where
  parts butt together. Edit that table to reshape the body.

### Glazing and cabin

The windscreen is **real transparency**: the `Glass` material is `alphaMode:
BLEND` at 22% opacity, which every engine honours (no extension required). It
lives on its own `Canopy` node so you can hide, swap or re-sort it
independently of the body.

Glazing comes in two regions, set by `WINDSCREEN_AFT`:

- **The nose is a bubble.** Forward of `WINDSCREEN_AFT` the *entire* dome is
  glass — all the way round and up over the top, down to the chin. That is the
  view a pilot actually flies on, forward and down through the nose, so nothing
  opaque may cross it. The build asserts this.
- **Aft of that the doors carry a window band**, with painted skin below and a
  solid roof from there back.

Behind it is an actual cabin compartment — floor, bench cushion, two seat
backs, instrument panel, rear bulkhead and the R22's T-bar cyclic, inside an
open-topped tub. The tub is the hull's own sections shrunk about their axis and
wound inside-out, so what you see through the glass is its interior. Without
it, transparent glazing would show daylight straight through the fuselage.

Interior parts size themselves from `fit_half_width()`, which measures the hull
at the part's own height, and `assert_inside_hull()` fails the build if
anything pokes through the skin.

### Materials

| Name | Used for |
|---|---|
| `Paint` | roof aft of the bubble, door skin, boom, fin, stabiliser |
| `Glass` | the whole nose bubble plus door windows — alpha blended, own node |
| `Metal` | rotors, mast pylon, skids, driveshaft cover, cyclic |
| `Accent` | belly stripe |
| `Interior` | cabin tub, floor, bulkhead, instrument panel |
| `Seat` | bench cushion and seat backs |

### Nodes

    Helicopter
    ├── Body         opaque hull + cabin
    ├── Canopy       glazing only (transparent)
    ├── MainRotor    spins about local +Y
    └── TailRotor    spins about local +Y (node is pre-rotated 90° about Z)

Both rotors spin about their **own local +Y**, so one routine drives both:

    heli.getObjectByName('MainRotor').rotation.y += 18 * dt;
    heli.getObjectByName('TailRotor').rotation.y += 90 * dt;

If your engine treats **+Z** as model-forward (e.g. Unity), yaw the root 180°.
