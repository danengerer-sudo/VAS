# helicopter_lowpoly.glb

A minimal low-poly helicopter for real-time use. Regenerate with:

    python3 tools/make_helicopter.py assets/models/helicopter_lowpoly.glb

## Real-world reference

Modelled on the **Robinson R22** — the small round-bubble two-seat piston
helicopter. Published dimensions and what the model uses:

| Dimension | Real R22 | This model |
|---|---|---|
| Fuselage length (nose → fin trailing edge) | 6.30 m | 6.30 m |
| Main rotor diameter | 7.67 m | 7.67 m |
| Tail rotor diameter | 1.07 m | 1.07 m |
| Overall height (to rotor head) | 2.72 m | 2.72 m |
| Cabin width | 0.91 m | 1.18 m (bubble outer) |
| Skid track | ~1.90 m | 1.90 m |

## Asset facts

- 938 triangles, ~76 KB, single self-contained `.glb`.
- The fuselage is **one lofted surface** — bubble, tailcone and fin sweep are
  stations of a single profile table (`SECTIONS` in the generator), so there
  are no seams where parts butt together. Edit that table to reshape the body.
- Units are **metres**, **+Y up**, **nose toward −Z**, origin on the ground
  centred between the skids — so it drops straight onto a ground plane at y=0.
- Flat shaded (per-face normals), no UVs or textures. Recolour by editing the
  four `baseColorFactor` values in `tools/make_helicopter.py`.

### Materials

| Name | Used for |
|---|---|
| `Paint` | upper fuselage, boom, fin, stabiliser |
| `Glass` | wraparound windscreen and door windows (opaque tint, no alpha blending) |
| `Metal` | rotors, mast pylon, skids, gearbox fairing |
| `Accent` | white lower half of the cabin pod |

### Nodes

    Helicopter
    ├── Body
    ├── MainRotor    spins about local +Y
    └── TailRotor    spins about local +Y (node is pre-rotated 90° about Z)

Both rotors spin about their **own local +Y**, so one animation routine drives
both. In Three.js:

    heli.getObjectByName('MainRotor').rotation.y += 18 * dt;
    heli.getObjectByName('TailRotor').rotation.y += 90 * dt;

If your engine treats **+Z** as model-forward (e.g. Unity), yaw the root 180°.
