# Status

_Updated 2026-09-17T13:14:38Z_

STEP export is built, tested and live on the phone: the CAD tab's 'Send to a shop' button writes real B-rep with planes where the flat faces are and cylinders of the true diameter where the bores are. The bearing assembly goes from 1972 triangles to 74 surfaces with 9 real cylinders, four named solids under an assembly. Verified by reading the file back and working the volume out from the surfaces alone.

NEXT, and the only thing half done: the pointing layer in tools/step.py works and is NOT yet wired into the app. point_at() takes a spot on a part and says what is there in a sentence with the numbers in it, so a request can name a feature rather than describe it. To finish it: add /api/point to relay/server.py (same shape as /api/step, cache surfaces() per file mtime, convert the viewer's coordinates with solid._laid_down because the viewer is y up and the part is z up), show the feature under the picked part in the CAD tab, and give it a Change this button that attaches that sentence to whatever he says next. That is the whole of 'edit by pointing and saying'.

KNOWN GAPS, in the order they are worth doing. One: STEP cannot yet write a cylindrical face bounded by arcs, so a bore with anything cut through it exports faceted. The bearing block's main 26 mm bore is one of those. Pointing already handles them; the writer does not. This is the main thing between good STEP and CAD grade STEP. Two: state.units is never set by anything, so the viewer, the measurements and the BOM all read 'no unit set'. Three: a parameters panel exposing each part script's named numbers as editable fields. Proposed in answer to a question, never ordered.

Why the commit messages are long: they are the handoff. Every fault found and how it was found is in them.

Open questions: 0 (0 blocking)
