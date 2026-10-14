#!/bin/bash
# Install MakeHuman MPFB2 + CC0 system assets for headless Blender 4.2, and the CMU mocap clips we use.
set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
P="$ROOT/assets/packs/mpfb"; mkdir -p "$P"
curl -sSL -A Mozilla -o "$P/mpfb.zip" "https://extensions.blender.org/download/sha256:c075b3e9b94b8e5556a5f03f4653602d02ea306de08126e8f55ed6dee28a2dad/add-on-mpfb-v2.0.18.zip?repository=%2Fapi%2Fv1%2Fextensions%2F&blender_version_min=4.2.0"
curl -sSL -A Mozilla -o "$P/sysassets.zip" https://files.makehumancommunity.org/asset_packs/makehuman_system_assets/makehuman_system_assets_cc0.zip
EXT=~/.config/blender/4.2/extensions/user_default; mkdir -p "$EXT"; rm -rf "$EXT/mpfb"; unzip -q -o "$P/mpfb.zip" -d "$EXT/mpfb"
U=~/.config/blender/4.2/extensions/.user/user_default/mpfb/data; mkdir -p "$U"; unzip -q -o "$P/sysassets.zip" -d "$U"
# CMU mocap (BVH release, sparse checkout of the clips listed in mfigure.py)
M="$ROOT/assets/mocap"; mkdir -p "$M"; T=$(mktemp -d)
git clone -q --depth 1 --filter=blob:none --no-checkout https://github.com/una-dinosauria/cmu-mocap.git "$T/cmu"
for c in 02_01 07_01 07_04 08_04 08_11 13_07 16_15 17_03 17_04 18_08 18_09 19_08 22_18 35_01 39_01 40_10 40_11 76_04 77_01 77_02 77_04 79_36 86_09; do
  d=$(printf "%03d" $((10#${c%%_*}))); (cd "$T/cmu" && git checkout -q HEAD -- "data/$d/$c.bvh") && cp "$T/cmu/data/$d/$c.bvh" "$M/"
done
echo "MPFB + assets + mocap installed"
