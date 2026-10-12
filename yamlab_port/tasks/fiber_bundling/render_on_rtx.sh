#!/bin/bash
# For the lead: render the saved oracle runs on an RTX host (ws/ws3, Isaac Sim 5.1 + Isaac Lab 2.3.2 + YAMLab deps).
#   render_on_rtx.sh <yamlab_clone> <outdir>
# Needs this folder (tools/, yamlab_task/, assets/, out/vef/actions.npy, out/eaf/actions.npy) on the host.
set -e
Y=${1:?yamlab clone}; O=${2:?output dir}
HERE=$(cd "$(dirname "$0")" && pwd)
bash "$HERE/install.sh" "$Y" "$HERE/assets"
export PYTHONPATH=$Y
unset YAMLAB_STRIP_CAMERAS
python "$HERE/tools/replay.py" --task FiberBundling-VeryEasy-v0 --actions "$HERE/out/vef/actions.npy" \
    --out "$O/very_easy" --device cpu --enable_cameras --frame_every 2 --reference "$HERE/out/vef/states.npz"
python "$HERE/tools/replay.py" --task FiberBundling-Easier-v0 --actions "$HERE/out/eaf/actions.npy" \
    --out "$O/easier" --device cpu --enable_cameras --frame_every 2 --reference "$HERE/out/eaf/states.npz"
# -> <O>/<tier>/{top.mp4,left_wrist.mp4,frames_top/,frames_left_wrist/,replay_metrics.json}
