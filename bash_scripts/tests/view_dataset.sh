#!/usr/bin/env bash
# ============================================================================
# 把一个已录的 H5 里存的 obs 图像（front/wrist rgb）还原出来看——用于人眼判断
# 任务物理上是否达标。产出两样：
#   1. <task>_<cam>.mp4        该相机所有帧还原成的视频（policy 实际看到的视角）
#   2. <task>_<cam>_sheet.png  均匀抽 12 帧拼成的速览图（一眼看整段进程）
# 注意：这看的是"数据里 policy 的视角"（front/wrist、每 10 物理步一帧），
# 和 --record-video 的 oblique 电影机位不同——那个更适合纯欣赏，这个才是数据本身。
#
# 用法：
#   bash bash_scripts/tests/view_dataset.sh <path/to.h5>
#   FRAMES=all bash bash_scripts/tests/view_dataset.sh <path/to.h5>   # 额外导出每一步的 PNG
#
# 环境变量：FPS=10  播放帧率；  FRAMES=all  额外把每帧存成 PNG；  TOPOGYM_VENV=.venv-gs121-nyx
# ============================================================================
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$REPO"

if [[ -z "${VIRTUAL_ENV:-}" ]]; then
  VENV="${TOPOGYM_VENV:-$REPO/.venv-gs121-nyx}"
  if [[ -f "$VENV/bin/activate" ]]; then
    # shellcheck disable=SC1091
    source "$VENV/bin/activate"
  fi
fi

FPS="${FPS:-10}"
H5="${1:-}"
if [[ -z "$H5" ]]; then
  echo "用法: bash bash_scripts/tests/view_dataset.sh <path/to.h5>" >&2
  exit 2
fi
if [[ ! -s "$H5" ]]; then
  echo "[error] 文件不存在或为空: $H5" >&2
  exit 2
fi
if ! python -c "import h5py, imageio" 2>/dev/null; then
  echo "[error] 需要 h5py + imageio。venv 里装一下：pip install imageio imageio-ffmpeg" >&2
  exit 1
fi

python - "$H5" "$FPS" <<'PY'
import os
import sys
from pathlib import Path
import numpy as np
import h5py
import imageio.v2 as imageio

dump_frames = os.environ.get("FRAMES", "").lower() in ("1", "all", "true")

path, fps = Path(sys.argv[1]), int(sys.argv[2])
outdir = path.parent
with h5py.File(path, "r") as f:
    ep = f["episode_0"]
    ts = sorted((k for k in ep if k.startswith("timestep_")), key=lambda x: int(x.split("_")[1]))
    status = ep["setup"].attrs.get("status", b"?")
    status = status.decode() if isinstance(status, bytes) else status
    cams = [c.decode() if isinstance(c, bytes) else c
            for c in ep["setup"].attrs.get("camera_names", [])]
    print(f"episode status={status}  frames={len(ts)}  cameras={cams}")
    for cam in cams:
        key = f"obs/{cam}_rgb"
        if key not in ep[ts[0]]:
            continue
        frames = np.stack([ep[k][key][()] for k in ts]).astype(np.uint8)  # (T,H,W,3)

        # 1) 还原视频
        mp4 = outdir / f"{path.stem}_{cam}.mp4"
        try:
            imageio.mimwrite(mp4, list(frames), fps=fps)
            print(f"  video -> {mp4}  ({frames.shape[0]} frames @ {fps}fps, {frames.shape[1]}x{frames.shape[2]})")
        except Exception as exc:
            print(f"  [warn] 视频写入失败（缺 ffmpeg?）: {exc}")

        # 2) 速览拼图：均匀抽 12 帧，4 列 x 3 行
        n, cols = 12, 4
        rows = n // cols
        idx = np.linspace(0, len(frames) - 1, n).astype(int)
        sample = frames[idx]  # (12,H,W,3)
        H, W = sample.shape[1], sample.shape[2]
        sheet = (
            sample.reshape(rows, cols, H, W, 3)
            .transpose(0, 2, 1, 3, 4)
            .reshape(rows * H, cols * W, 3)
        )
        png = outdir / f"{path.stem}_{cam}_sheet.png"
        imageio.imwrite(png, sheet)
        print(f"  sheet -> {png}  (帧号 {idx.tolist()})")

        # 3) 可选：每一步一张 PNG
        if dump_frames:
            fdir = outdir / f"{path.stem}_{cam}_frames"
            fdir.mkdir(exist_ok=True)
            for i in range(len(frames)):
                imageio.imwrite(fdir / f"frame_{i:04d}.png", frames[i])
            print(f"  frames -> {fdir}/frame_XXXX.png  ({len(frames)} 张 PNG)")
PY
