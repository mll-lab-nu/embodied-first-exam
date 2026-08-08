#!/usr/bin/env bash
# ============================================================================
# 跨生成物理稳定性 sweep（测量器）。
# 对某任务扫 SEED × DIFFICULTY，每格 headless 跑 demo，按"物理崩没崩"分类，
# 打印一张矩阵 + 汇总。头条指标是 CRASH（物理不稳），不是 FAIL（任务没成功但物理没崩）。
#
# 现在就能对**确定性 layout** 跑（基线：单一场景在重复/难度下稳不稳）。
# 等 layout_randomization 落地后，设 RANDOMIZE=1 才真正"跨种子"有意义
# （demo 需已接 --randomize-layout / --difficulty；没接时本脚本自动不传这俩）。
#
# 用法：
#   bash bash_scripts/tests/stability_sweep.sh                 # 全部任务，默认 seeds
#   bash bash_scripts/tests/stability_sweep.sh untangle        # 只测 untangle
#   SEEDS="0 1 2 3 4 5" RANDOMIZE=1 bash bash_scripts/tests/stability_sweep.sh cable_routing
#
# 可调环境变量（都有默认值）：
#   SEEDS="0 1 2 3 4"            扫哪些 seed
#   DIFFICULTIES="default"       扫哪些难度（仅 RANDOMIZE=1 时生效并传 --difficulty）
#   RANDOMIZE=0                  1=传 --randomize-layout（需 demo 已支持）；0=确定性基线
#   BACKEND=gpu                  计算后端
#   TIMEOUT_S=1200               单格墙钟超时（秒）；超时算 TIMEOUT
#   OUTDIR=runs/stability/<时间戳>
#   TOPOGYM_VENV=.venv           未激活 venv 时自动 source
# ============================================================================
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$REPO"

if [[ -z "${VIRTUAL_ENV:-}" ]]; then
  VENV="${TOPOGYM_VENV:-$REPO/.venv}"
  [[ -f "$VENV/bin/activate" ]] && source "$VENV/bin/activate"
fi

SEEDS="${SEEDS:-0 1 2 3 4}"
DIFFICULTIES="${DIFFICULTIES:-default}"
RANDOMIZE="${RANDOMIZE:-0}"
BACKEND="${BACKEND:-gpu}"
TIMEOUT_S="${TIMEOUT_S:-1200}"
OUTDIR="${OUTDIR:-runs/stability/$(date +%Y%m%d_%H%M%S)}"
mkdir -p "$OUTDIR"

# task -> demo 模块 + 该任务 headless 稳定跑所需的额外参数（沿用 record_all_tasks.sh 的已知可跑法；
# untangle/cable 加 --probe 以便捕捉"进程没崩但绳子飞出"的物理 blowup）。
declare -A TASKS=(
  [untangle]="prototypes.untangle_physical_handle_demo"
  [untangle_continuous]="prototypes.untangle_continuous_physical_pinch_demo"
  [cable_routing]="prototypes.cable_routing_physical_handle_demo --allow-target-lag --probe"
  [stacked_plate]="prototypes.stacked_plate_physical_rotate_demo"
  [peeling]="prototypes.peeling_physical_demo --run-oracle"
)
ORDER=(untangle untangle_continuous cable_routing stacked_plate peeling)
SELECTED=( "$@" ); [[ ${#SELECTED[@]} -eq 0 ]] && SELECTED=( "${ORDER[@]}" )

if ! python -c "import topogym" 2>/dev/null; then
  echo "[error] 无法 import topogym。先激活正确 venv（或设 TOPOGYM_VENV）。" >&2
  exit 1
fi

# RANDOMIZE=0 时难度无意义（demo 不吃 --difficulty），只跑一格 "(det)"。
if [[ "$RANDOMIZE" == "0" ]]; then DIFF_LIST=("(det)"); else read -ra DIFF_LIST <<< "$DIFFICULTIES"; fi

# 分类：参数 = 退出码 + 日志路径。回显一个类别词。头条关注 CRASH*。
classify() {
  local code="$1" log="$2"
  if [[ "$code" == "124" ]]; then echo "TIMEOUT"; return; fi
  if [[ "$code" == "139" ]] || grep -qiE "Segmentation fault|core dumped" "$log"; then echo "CRASH-segv"; return; fi
  # PBD 物理 blowup（进程没崩）：cable probe 的 FLYOUT、rope_jump 大跳、untangle 单粒子弹到求解域角(zmax=100)/drift 巨大
  if grep -qE "FLYOUT|rope_jump=[0-9]{2,}(\.|$| )|rope_spread=[0-9]{3,}|zmax=100\.0|drift=1[0-9][0-9]" "$log"; then echo "CRASH-phys"; return; fi
  if [[ "$code" != "0" ]]; then
    grep -qiE "Traceback|Error" "$log" && { echo "ERROR-raised"; return; }
    echo "ERROR-code$code"; return
  fi
  # 退出 0：取"顶层" success=（前导空格，避开 task_success=/physical_success=）
  local s; s="$(grep -oE " success=(True|False)" "$log" | tail -1)"
  case "$s" in
    *True)  echo "OK" ;;
    *False) echo "FAIL" ;;
    *)      echo "DONE?" ;;   # 退出 0 但没打印 success=（如某些 demo）
  esac
}

declare -A CELL
crash_total=0; run_total=0
for task in "${SELECTED[@]}"; do
  spec="${TASKS[$task]:-}"
  if [[ -z "$spec" ]]; then echo "[skip] 未知 task: $task（可选：${ORDER[*]}）" >&2; continue; fi
  read -ra parts <<< "$spec"; module="${parts[0]}"; extra=("${parts[@]:1}")
  for seed in $SEEDS; do
    for diff in "${DIFF_LIST[@]}"; do
      rflags=()
      if [[ "$RANDOMIZE" != "0" ]]; then rflags=(--randomize-layout --difficulty "$diff"); fi
      log="$OUTDIR/${task}_seed${seed}_${diff}.log"
      start=$(date +%s)
      # EXTRA_ARGS：附加到每次运行的 CLI 参数（如 FEM 后端：
      #   EXTRA_ARGS="--env-config configs/env_configs/world_tabletop_fem_v1.yaml --rope-model fem_ipc_tube"）
      read -ra extra_env <<< "${EXTRA_ARGS:-}"
      timeout "${TIMEOUT_S}s" python -m "$module" "${extra[@]}" "${extra_env[@]}" \
        --seed "$seed" --backend "$BACKEND" "${rflags[@]}" >"$log" 2>&1
      code=$?
      dur=$(( $(date +%s) - start ))
      cls="$(classify "$code" "$log")"
      CELL["$task|$seed|$diff"]="$cls"
      run_total=$((run_total+1))
      [[ "$cls" == CRASH* ]] && crash_total=$((crash_total+1))
      printf '  %-14s seed=%-3s diff=%-8s -> %-12s (%ss, code=%s)\n' "$task" "$seed" "$diff" "$cls" "$dur" "$code"
    done
  done
done

echo
echo "==================== 稳定性矩阵 ===================="
for task in "${SELECTED[@]}"; do
  [[ -z "${TASKS[$task]:-}" ]] && continue
  echo "# $task  (RANDOMIZE=$RANDOMIZE)"
  printf '    %-6s' "seed\\diff"
  for diff in "${DIFF_LIST[@]}"; do printf ' %-12s' "$diff"; done; echo
  for seed in $SEEDS; do
    printf '    %-6s' "$seed"
    for diff in "${DIFF_LIST[@]}"; do printf ' %-12s' "${CELL["$task|$seed|$diff"]:-?}"; done; echo
  done
  echo
done

echo "==================== 汇总 ===================="
echo "  跑了 $run_total 格；物理崩溃(CRASH*) $crash_total 格。"
echo "  日志目录: $OUTDIR"
# 只在有物理崩溃时退出非 0（任务 FAIL 但物理不崩不算稳定性失败）。
[[ "$crash_total" -eq 0 ]] && echo "  [ok] 无物理崩溃" || echo "  [fail] 有物理崩溃，见上方矩阵 + 日志"
exit $(( crash_total > 0 ? 1 : 0 ))
