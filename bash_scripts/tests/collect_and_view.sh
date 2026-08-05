#!/usr/bin/env bash
# ============================================================================
# 一条命令跑通"采集 -> 出视频 + 每帧 PNG"：录一条某任务的数据集，然后立刻把它
# 存的 obs 图像还原成视频、速览拼图，并导出每一步的 PNG，供人眼判断物理达标。
#
# 用法：
#   bash bash_scripts/tests/collect_and_view.sh              # 默认 untangle
#   bash bash_scripts/tests/collect_and_view.sh untangle
#   bash bash_scripts/tests/collect_and_view.sh swap
#
# 可调环境变量：
#   BACKEND=gpu   SEED=0   EVERY=10   FPS=10   TOPOGYM_VENV=.venv
#
# 产物都在 <OUTDIR>=runs/dataset_tests/<时间戳>/ 下：
#   <task>_seed<seed>.h5              数据集
#   <task>_seed<seed>_front.mp4       front 相机还原视频（policy 视角）
#   <task>_seed<seed>_front_sheet.png 12 帧速览拼图
#   <task>_seed<seed>_front_frames/   每一步一张 PNG（frame_0000.png ...）
#   （wrist 相机同理）
# ============================================================================
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$REPO"

if [[ -z "${VIRTUAL_ENV:-}" ]]; then
  VENV="${TOPOGYM_VENV:-$REPO/.venv}"
  if [[ -f "$VENV/bin/activate" ]]; then
    # shellcheck disable=SC1091
    source "$VENV/bin/activate"
  fi
fi

BACKEND="${BACKEND:-gpu}"
SEED="${SEED:-0}"
EVERY="${EVERY:-10}"
FPS="${FPS:-10}"
TASK="${1:-untangle}"

# task -> demo 模块（+ 额外参数）。与 verify_dataset_recording.sh 保持一致。
declare -A TASKS=(
  [swap]="prototypes.swap_physical_grasp_demo"
  [untangle]="prototypes.untangle_physical_handle_demo"
  [untangle_continuous]="prototypes.untangle_continuous_physical_pinch_demo"
  [cable_routing]="prototypes.cable_routing_physical_handle_demo --allow-target-lag"
)
spec="${TASKS[$TASK]:-}"
if [[ -z "$spec" ]]; then
  echo "[error] 未知 task: $TASK（可选：${!TASKS[*]}）" >&2
  exit 2
fi
read -ra parts <<< "$spec"
module="${parts[0]}"
extra=("${parts[@]:1}")

if ! python -c "import topogym, h5py, imageio" 2>/dev/null; then
  echo "[error] 需要 topogym + h5py + imageio。激活 venv 并 pip install imageio imageio-ffmpeg" >&2
  exit 1
fi

OUTDIR="runs/dataset_tests/$(date +%Y%m%d_%H%M%S)"
mkdir -p "$OUTDIR"
H5="$OUTDIR/${TASK}_seed${SEED}.h5"

echo "==================== 1/2 采集: $TASK ===================="
echo "[collect] backend=$BACKEND seed=$SEED every=$EVERY -> $H5"
python -m "$module" "${extra[@]}" \
  --seed "$SEED" \
  --backend "$BACKEND" \
  --record-dataset "$H5" \
  --dataset-every-n-steps "$EVERY" \
  2>&1 | tee "$OUTDIR/$TASK.log"
code=${PIPESTATUS[0]}
if [[ $code -ne 0 ]]; then
  echo "[fail] 采集退出码=$code（详见 $OUTDIR/$TASK.log）" >&2
  exit $code
fi
if [[ ! -s "$H5" ]]; then
  echo "[fail] 未生成 H5: $H5" >&2
  exit 1
fi

echo
echo "==================== 2/2 出图: $TASK ===================="
FPS="$FPS" FRAMES=all bash "$SCRIPT_DIR/view_dataset.sh" "$H5"

echo
echo "全部产物在: $OUTDIR"
