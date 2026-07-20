#!/usr/bin/env bash
# ============================================================================
# 回放自校验（路线图 W5）：把一条已录的 H5 用其 seed 重建环境、开环回放录下的
# 动作，检查回放 eef 轨迹是否忠实跟踪录下的轨迹（硬门），并报告任务成功率。
# 不渲染，只跑物理，比录制快。
#
# 用法：
#   bash bash_scripts/tests/replay_dataset.sh <path/to.h5>
#   bash bash_scripts/tests/replay_dataset.sh          # 不给路径则取 runs/dataset_tests 下最新的 *.h5
#
# 可调环境变量：
#   BACKEND=gpu           计算后端（gpu/cuda/cpu）
#   POS_TOL=0.03          eef 轨迹跟踪硬门容差（米）
#   STEPS_PER_TARGET=     每个录下的位姿目标给多少物理步去收敛（默认取 steps_per_action=20）
#   REQUIRE_SUCCESS=1     把"回放到 success"也升级成硬门（默认只报告）
#   TOPOGYM_VENV=.venv    未激活 venv 时自动 source 的路径
#
# 硬门失败退出码非 0（适合 CI）。
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
POS_TOL="${POS_TOL:-0.03}"

H5="${1:-}"
if [[ -z "$H5" ]]; then
  H5="$(ls -t runs/dataset_tests/*/*.h5 2>/dev/null | head -1 || true)"
  if [[ -z "$H5" ]]; then
    echo "[error] 未给 H5 路径，且 runs/dataset_tests 下也没有 *.h5。" >&2
    echo "  用法: bash bash_scripts/tests/replay_dataset.sh <path/to.h5>" >&2
    exit 2
  fi
  echo "[replay] 未给路径，取最新: $H5"
fi
if [[ ! -s "$H5" ]]; then
  echo "[error] 文件不存在或为空: $H5" >&2
  exit 2
fi
if ! python -c "import topogym" 2>/dev/null; then
  echo "[error] 无法 import topogym。请先激活正确的 venv（或设 TOPOGYM_VENV）。" >&2
  exit 1
fi

args=(--pos-tol "$POS_TOL" --backend "$BACKEND")
if [[ -n "${STEPS_PER_TARGET:-}" ]]; then
  args+=(--steps-per-target "$STEPS_PER_TARGET")
fi
if [[ "${REQUIRE_SUCCESS:-0}" == "1" ]]; then
  args+=(--require-success)
fi

echo "[replay] backend=$BACKEND pos_tol=$POS_TOL steps_per_target=${STEPS_PER_TARGET:-auto} require_success=${REQUIRE_SUCCESS:-0}"
echo "==================== replay: $H5 ===================="
python -m topogym.data.replay "$H5" "${args[@]}"
rc=$?
echo
if [[ $rc -eq 0 ]]; then
  echo "[ok] 回放自校验通过: $H5"
else
  echo "[fail] 回放自校验未通过（详见上方 [fail] 行）: $H5"
fi
exit $rc
