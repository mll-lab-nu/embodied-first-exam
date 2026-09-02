#!/usr/bin/env bash
# ============================================================================
# gate_cage_ball 变体生成实验（variation_axes_plain_zh.md §6.2 第 3 步）。
#
# 每个 seed 四格：
#   visual   inspect demo 建场景不步进，录一帧静态画面 → 人眼看 visual_s<seed>.mp4：
#            封闭区长度、球起点、轨道左右位置、停放架位置是否逐 seed 不同，有无穿模。
#   oracle   physical demo，oracle 触发规则 → 必须 success=True。这是「oracle 在包络
#            内每个变体都可解」的直接证据。
#   greedy   physical demo，greedy 对照规则（到位就插，不看球）→ 只记录成败；
#            臂先到的实例失败、球先到的实例可能侥幸，期望落在中间。
#   fixed    physical demo，fixed_delay 对照规则（开始后固定秒数就插，不看球）→ 只记录；
#            起点与球速逐 seed 变后期望落在中间，这是「不感知」策略的上限。
#
# 变体参数来自 task 配置末尾的 variation 块，由 run.randomize_layout=true run.seed=<seed>
# 触发；demo 打印一行
#   gate_cage_ball variant seed=… speed=… flat_end_y=… release_y=… center_x=… rack_x=…
#     rack_y=… entry_delay=… window=… hover_wait=… slack=…
# 本脚本解析它进汇总表。hover_wait > 0 = 臂先到（必须悬停等球），< 0 = 球先到。
#
# **默认无头。** VIEWER=1 可开窗，但不加 run.keep_open。
#
# 用法：
#   bash bash_scripts/tests/gate_cage_ball_variation_sweep.sh                    # 全部三组，seed 0–9
#   SEEDS="0 1 2" bash bash_scripts/tests/gate_cage_ball_variation_sweep.sh visual
#   bash bash_scripts/tests/gate_cage_ball_variation_sweep.sh oracle greedy fixed
#
# 可调环境变量：
#   SEEDS="0 1 2 3 4 5 6 7 8 9"
#   BACKEND=gpu
#   TIMEOUT_S=900
#   VIEWER=0
#   OUTDIR=runs/gate_cage_ball_variation/<时间戳>
#   TOPOGYM_VENV=.venv-gs121
#
# 产出：<OUTDIR>/<group>_s<seed>.log、visual_s<seed>.mp4、summary.csv。
# 退出码：任一 oracle 格非 task_success=True，或任一格 RAISED/TIMEOUT，即非 0。
# greedy / fixed 格不计入退出码。刻意不用 set -e。
# ============================================================================
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$REPO"

if [[ -z "${VIRTUAL_ENV:-}" ]]; then
  for candidate in "${TOPOGYM_VENV:-}" "$REPO/.venv-gs121" "$REPO/.venv-gs110" "$REPO/.venv"; do
    [[ -z "$candidate" ]] && continue
    if [[ -f "$candidate/bin/activate" ]]; then
      # shellcheck disable=SC1091
      source "$candidate/bin/activate"
      break
    fi
  done
fi

SEEDS="${SEEDS:-0 1 2 3 4 5 6 7 8 9}"
BACKEND="${BACKEND:-gpu}"
TIMEOUT_S="${TIMEOUT_S:-900}"
VIEWER="${VIEWER:-0}"
OUTDIR="${OUTDIR:-runs/gate_cage_ball_variation/$(date +%Y%m%d_%H%M%S)}"

VIEWER_ARGS=()
[[ "$VIEWER" == "1" ]] && VIEWER_ARGS=(run.viewer=true)

SUITES=(visual oracle greedy fixed)
if [[ $# -gt 0 ]]; then SELECTED=("$@"); else SELECTED=("${SUITES[@]}"); fi
for name in "${SELECTED[@]}"; do
  case " ${SUITES[*]} " in
    *" $name "*) ;;
    *) echo "[error] 未知组 '$name'；可选：${SUITES[*]}" >&2; exit 1 ;;
  esac
done

if ! python -c "import topogym" 2>/dev/null; then
  echo "[error] 无法 import topogym。请先激活项目 venv（或设 TOPOGYM_VENV）。" >&2
  exit 1
fi
if ! python -c "import genesis" 2>/dev/null; then
  echo "[error] 无法 import genesis。本脚本要建真实场景，必须在项目 venv 里跑。" >&2
  exit 1
fi
mkdir -p "$OUTDIR"

# 离线门先过：变体块的包络、派生区间、拒绝率、时序公式一致、三条规则。几十秒。
if ! python -B tests/check_variant_rng.py > "$OUTDIR/offline.log" 2>&1; then
  echo "[error] tests/check_variant_rng.py 未通过，见 $OUTDIR/offline.log" >&2
  exit 1
fi
if ! python -B tests/check_gate_cage_ball_geometry.py >> "$OUTDIR/offline.log" 2>&1; then
  echo "[error] tests/check_gate_cage_ball_geometry.py 未通过，见 $OUTDIR/offline.log" >&2
  exit 1
fi

FAIL=0
declare -A VARIANT ORACLE GREEDY FIXED VISUAL HOVER

run_state() {
  local code="$1" log="$2"
  if [[ "$code" == "124" ]]; then echo "TIMEOUT"; return; fi
  if [[ "$code" != "0" ]]; then
    grep -qaF "Viewer closed." "$log" && { echo "ok"; return; }
    grep -qaiE "^Traceback" "$log" && { echo "RAISED"; return; }
    echo "code$code"; return
  fi
  echo "ok"
}

variant_line() { grep -aF "gate_cage_ball variant seed=" "$1" | tail -1; }
result_line()  { grep -aF "gate_cage_ball_physical_gate_demo result" "$1" | tail -1; }

run_cell() {
  local group="$1" seed="$2"; shift 2
  local tag="${group}_s${seed}" log="$OUTDIR/${group}_s${seed}.log"
  echo
  echo "==================== $tag ===================="
  local start; start=$(date +%s)
  local cmd=()
  case "$group" in
    visual)
      cmd=(python -B -m demos.connectivity.gate_cage_ball_inspect_demo
           env.genesis.backend="$BACKEND" "${VIEWER_ARGS[@]}"
           run.randomize_layout=true "run.seed=$seed" run.static_only=true
           recording=default "recording.path=$OUTDIR/visual_s${seed}.mp4" recording.camera=oblique) ;;
    oracle)
      cmd=(python -B -m demos.connectivity.gate_cage_ball_physical_gate_demo
           env.genesis.backend="$BACKEND" "${VIEWER_ARGS[@]}"
           run.randomize_layout=true "run.seed=$seed" run.trigger=oracle) ;;
    greedy)
      cmd=(python -B -m demos.connectivity.gate_cage_ball_physical_gate_demo
           env.genesis.backend="$BACKEND" "${VIEWER_ARGS[@]}"
           run.randomize_layout=true "run.seed=$seed" run.trigger=greedy) ;;
    fixed)
      cmd=(python -B -m demos.connectivity.gate_cage_ball_physical_gate_demo
           env.genesis.backend="$BACKEND" "${VIEWER_ARGS[@]}"
           run.randomize_layout=true "run.seed=$seed" run.trigger=fixed_delay) ;;
  esac
  timeout "${TIMEOUT_S}s" "${cmd[@]}" "$@" 2>&1 | tee "$log"
  local code=${PIPESTATUS[0]}
  local dur=$(( $(date +%s) - start ))
  local state; state="$(run_state "$code" "$log")"
  local v; v="$(variant_line "$log")"
  [[ -n "$v" ]] && VARIANT[$seed]="${v#gate_cage_ball variant }"

  local verdict=""
  case "$group" in
    visual)
      if [[ "$state" == "ok" && -s "$OUTDIR/visual_s${seed}.mp4" ]]; then verdict="ok (看 mp4)"; else verdict="FAIL $state"; FAIL=1; fi
      VISUAL[$seed]="$verdict" ;;
    oracle)
      if [[ "$state" != "ok" ]]; then verdict="FAIL $state"; FAIL=1
      elif result_line "$log" | grep -qaF "success=True"; then verdict="PASS"
      else verdict="FAIL $(result_line "$log" | grep -aoE 'failure=[A-Za-z_]+')"; FAIL=1; fi
      ORACLE[$seed]="$verdict"
      HOVER[$seed]="$(result_line "$log" | grep -aoE 'hover=[^ ]+' | sed 's/hover=//')" ;;
    greedy)
      if [[ "$state" != "ok" ]]; then verdict="$state"
      elif result_line "$log" | grep -qaF "success=True"; then verdict="success"
      else verdict="$(result_line "$log" | grep -aoE 'failure=[A-Za-z_]+' | sed 's/failure=//')"; fi
      GREEDY[$seed]="$verdict" ;;
    fixed)
      if [[ "$state" != "ok" ]]; then verdict="$state"
      elif result_line "$log" | grep -qaF "success=True"; then verdict="success"
      else verdict="$(result_line "$log" | grep -aoE 'failure=[A-Za-z_]+' | sed 's/failure=//')"; fi
      FIXED[$seed]="$verdict" ;;
  esac
  echo "---- $tag (${dur}s): $verdict"
}

echo "outdir=$OUTDIR backend=$BACKEND seeds=[$SEEDS] groups=[${SELECTED[*]}]"

for group in "${SELECTED[@]}"; do
  for seed in $SEEDS; do
    run_cell "$group" "$seed"
  done
done

echo
echo "==================== 汇总 ===================="
csv="$OUTDIR/summary.csv"
echo "seed,speed,flat_end_y,release_y,center_x,rack_x,rack_y,entry_delay,window,hover_wait,slack,hover,visual,oracle,greedy,fixed" > "$csv"
n_fixed=0; n_fixed_ok=0; n_greedy=0; n_greedy_ok=0
for seed in $SEEDS; do
  v="${VARIANT[$seed]:-}"
  f() { echo "$v" | grep -aoE "$1=[^ ]+" | sed "s/$1=//"; }
  printf '  seed %-3s v=%-5s flat=%-7s rel=%-7s cx=%-7s rack=%-7s/%-7s entry=%-5s win=%-5s wait=%-6s slack=%-6s hover=%-12s | visual=%s oracle=%s greedy=%s fixed=%s\n' \
    "$seed" "$(f speed)" "$(f flat_end_y)" "$(f release_y)" "$(f center_x)" "$(f rack_x)" "$(f rack_y)" \
    "$(f entry_delay)" "$(f window)" "$(f hover_wait)" "$(f slack)" "${HOVER[$seed]:--}" \
    "${VISUAL[$seed]:--}" "${ORACLE[$seed]:--}" "${GREEDY[$seed]:--}" "${FIXED[$seed]:--}"
  echo "$seed,$(f speed),$(f flat_end_y),$(f release_y),$(f center_x),$(f rack_x),$(f rack_y),$(f entry_delay),$(f window),$(f hover_wait),$(f slack),${HOVER[$seed]:-},${VISUAL[$seed]:-},${ORACLE[$seed]:-},${GREEDY[$seed]:-},${FIXED[$seed]:-}" >> "$csv"
  if [[ -n "${GREEDY[$seed]:-}" ]]; then
    n_greedy=$((n_greedy + 1)); [[ "${GREEDY[$seed]}" == "success" ]] && n_greedy_ok=$((n_greedy_ok + 1))
  fi
  if [[ -n "${FIXED[$seed]:-}" ]]; then
    n_fixed=$((n_fixed + 1)); [[ "${FIXED[$seed]}" == "success" ]] && n_fixed_ok=$((n_fixed_ok + 1))
  fi
done
if [[ $n_greedy -gt 0 ]]; then
  echo "  greedy 成功率: $n_greedy_ok / $n_greedy（期望落在中间：臂先到的格失败，球先到的格可能侥幸）"
fi
if [[ $n_fixed -gt 0 ]]; then
  echo "  fixed_delay 成功率: $n_fixed_ok / $n_fixed（期望落在中间；这是不感知球的策略的上限）"
fi
echo
echo "怎么读："
echo "  visual   打开 $OUTDIR/visual_s*.mp4：封闭区长度、球起点、轨道位置、停放架位置应逐 seed 不同，且无穿模。"
echo "  oracle   全部 PASS 才说明 oracle 覆盖了包络；FAIL 的 seed 看其 log 的 result 行（failure / trigger_reason / plate_yaw）"
echo "           与 variant 行（slack 接近 0 的格是时序最紧的）。"
echo "  greedy   成败应与 wait 列的正负对应：wait>0（臂先到）失败，wait<0 可能成功。"
echo "  fixed    成功率既不该是 0 也不该是 10；两者都不按分数回调包络。"
echo "summary: $csv"
echo "日志: $OUTDIR"
exit $FAIL
