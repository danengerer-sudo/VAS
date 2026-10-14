#!/bin/bash
# Renders the whole timeline to render/frames/f_####.png (skips frames already on disk).
cd "$(dirname "$0")/../render"
/opt/blender_dl/blender-4.2.23-linux-x64/blender -b scene.blend -E CYCLES -o "//frames/f_####" -F PNG -x 1 \
  --python-expr "import bpy; bpy.context.scene.render.use_overwrite=False; bpy.context.scene.render.use_placeholder=True" \
  -s ${1:-1} -e ${2:-768} -a
