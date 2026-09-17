# Status

_Updated 2026-09-17T13:40:20Z_

STEP export is built, tested and real: tools/step.py writes real B-rep, planes for the flat faces and cylinders of the true diameter for the bores. The bearing assembly goes from 1972 triangles to 74 surfaces with 9 real cylinders, four named solids under an assembly. Verified by reading the file back and working the volume out from the surfaces alone.

Correction to the previous entry: it described a phone app, a relay and a CAD tab as if they lived here. They do not. This repo is the CAD kernel and asset store only, per CLAUDE.md - no server, no phone, no voice (see state/README.md). The app that consumes this kernel is a separate repo, danengerer-sudo/engineering-standards, which clones tools/ from this branch as a dependency (its relay/repos.txt pins danengerer-sudo/vas@claude/attachment-review-hzlxpb). A previous session's status note here was actually describing that repo's next step, not this one's.

That step is done now, over there: point_at() is wired into its CAD tab (server.py's /api/point, cached per file mtime, coordinates run through solid._laid_down for the y-up/z-up turn), a feature line shows under the picked part with its own numbers, and a Change this button hands that sentence to the chat composer. Tested end to end against the real bearing-block assembly and pushed to engineering-standards on branch claude/point-at-in-cad-tab. Nothing in this repo changed to do it - tools/step.py's point_at() and surfaces() were already everything it needed.

KNOWN GAPS in tools/step.py, in the order they are worth doing. One: it cannot yet write a cylindrical face bounded by arcs, so a bore with anything cut through it exports faceted. The bearing block's main 26 mm bore is one of those. point_at already handles them; the writer does not. This is the main thing between good STEP and CAD grade STEP. Two: state.units is never set by anything, so anything reading it prints 'no unit set'. Three: a parameters panel exposing each part script's named numbers as editable fields, proposed in answer to a question, never ordered - and that panel belongs in the engineering-standards app, not here.

Why the commit messages are long: they are the handoff. Every fault found and how it was found is in them.

Open questions: 0 (0 blocking)
