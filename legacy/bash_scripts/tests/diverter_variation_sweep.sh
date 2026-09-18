#!/usr/bin/env bash
# ============================================================================
# diverter_route_ball 变体生成实验（variation_axes_plain_zh.md §6.2 第 2 步）。
#
# 回答两个问题，每个 seed 三格：
#   visual   inspect demo 建场景不步进，录一帧静态画面 → 人眼看 visual_s<seed>.mp4：
#            死路侧（封闭端墙）、挡板初始相位、目标垫有无、张角、分岔口位置、拨杆长、
#            球起点是否逐 seed 不同，有无穿模。
#   oracle   physical demo，oracle 规则 → 必须 task_success=True。这是「oracle 在包络
#            内每个变体都可解」的直接证据；同时读 rotate 行的 max_lag / target_error，
#            看是否随张角单调增长（步数已按扫掠角推导，预期不增长）。
#   fixed    physical demo，fixed_direction 对照规则（永远封右侧）→ 只记录成败；
#            死路侧独立随机后期望成功率接近 1/2，落在 0.3–0.7 之间即防捷径成立。
#
# 变体参数来自 task 配置末尾的 variation 块，由 run.randomize_layout=true run.seed=<seed>
# 触发；demo 打印一行
#   diverter_route_ball variant seed=… dead_end=… init_sealed=… rotate_needed=… pad=…
#     angle_deg=… lever_r=… fork_x=… speed=… release_x=…
# 本脚本解析它进汇总表。
#
# **默认无头。** VIEWER=1 可开窗，但不加 run.keep_open。
#
# 用法：
#   bash bash_scripts/tests/diverter_variation_sweep.sh                    # 全部三组，seed 0–9
#   SEEDS="0 1 2" bash bash_scripts/tests/diverter_variation_sweep.sh visual
#   bash bash_scripts/tests/diverter_variation_sweep.sh oracle fixed
#
# 可调环境变量：
#   SEEDS="0 1 2 3 4 5 6 7 8 9"
#   BACKEND=gpu
#   TIMEOUT_S=900
#   VIEWER=0
#   OUTDIR=runs/diverter_variation/<时间戳>
#   TOPOGYM_VENV=.venv-gs121-nyx
#   SKIP_OFFLINE=1  跳过离线门（13–14 分钟）。只在你刚跑过 tests/check_variant_rng.py
#                   与本任务几何门时用；默认 0，照跑。
#
# 产出：<OUTDIR>/<group>_s<seed>.log、visual_s<seed>.mp4、summary.csv。
# 退出码：任一 oracle 格非 task_success=True，或任一格 RAISED/TIMEOUT，即非 0。
# fixed 格不计入退出码。刻意不用 set -e。
# ============================================================================
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$REPO"

if [[ -z "${VIRTUAL_ENV:-}" ]]; then
  for candidate in "${TOPOGYM_VENV:-}" "$REPO/.venv-gs121-nyx" "$REPO/.venv-gs121" "$REPO/.venv-gs110" "$REPO/.venv"; do
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
OUTDIR="${OUTDIR:-runs/diverter_variation/$(date +%Y%m%d_%H%M%S)}"

VIEWER_ARGS=()
[[ "$VIEWER" == "1" ]] && VIEWER_ARGS=(run.viewer=true)

SUITES=(visual oracle fixed)
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

# 离线门先过：变体块的包络、派生区间、拒绝率、规则的 2×2、判据一致性。几十秒。
# SKIP_OFFLINE=1 跳过这一段（2026-09-09）。默认仍然跑：不知情的调用方保持原来的安全性。
# 实测这一段 13–14 分钟（13 个任务的包络全跑一遍），而本脚本真正的物理只占 5–12 分钟；
# 调用方刚手工跑过同一个门时，重复跑就是纯等待。跳过时把原因写进 offline.log，
# 免得事后看目录以为门没跑过。
if [[ "${SKIP_OFFLINE:-0}" == "1" ]]; then
  echo "SKIP_OFFLINE=1：调用方声明已跑过 tests/check_variant_rng.py 与本任务几何门，本轮跳过" \
    > "$OUTDIR/offline.log"
elif ! python -B tests/check_variant_rng.py > "$OUTDIR/offline.log" 2>&1; then
  echo "[error] tests/check_variant_rng.py 未通过，见 $OUTDIR/offline.log" >&2
  exit 1
fi
if [[ "${SKIP_OFFLINE:-0}" != "1" ]] && ! python -B tests/check_diverter_geometry.py >> "$OUTDIR/offline.log" 2>&1; then
  echo "[error] tests/check_diverter_geometry.py 未通过，见 $OUTDIR/offline.log" >&2
  exit 1
fi

FAIL=0
declare -A VARIANT ORACLE FIXED VISUAL LAG

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

variant_line() { grep -aF "diverter_route_ball variant seed=" "$1" | tail -1; }
result_line()  { grep -aF "diverter_route_ball_physical_route_demo result" "$1" | tail -1; }
rotate_line()  { grep -aF "diverter_route_ball rotate " "$1" | tail -1; }

run_cell() {
  local group="$1" seed="$2"; shift 2
  local tag="${group}_s${seed}" log="$OUTDIR/${group}_s${seed}.log"
  echo
  echo "==================== $tag ===================="
  local start; start=$(date +%s)
  local cmd=()
  case "$group" in
    visual)
      cmd=(python -B -m demos.connectivity.diverter_route_ball_inspect_demo
           env.genesis.backend="$BACKEND" "${VIEWER_ARGS[@]}"
           run.randomize_layout=true "run.seed=$seed" run.static_only=true
           recording=default "recording.path=$OUTDIR/visual_s${seed}.mp4" recording.camera=oblique) ;;
    oracle)
      cmd=(python -B -m demos.connectivity.diverter_route_ball_physical_route_demo
           env.genesis.backend="$BACKEND" "${VIEWER_ARGS[@]}"
           run.randomize_layout=true "run.seed=$seed" run.oracle_mode=oracle) ;;
    fixed)
      cmd=(python -B -m demos.connectivity.diverter_route_ball_physical_route_demo
           env.genesis.backend="$BACKEND" "${VIEWER_ARGS[@]}"
           run.randomize_layout=true "run.seed=$seed" run.oracle_mode=fixed_direction) ;;
  esac
  timeout "${TIMEOUT_S}s" "${cmd[@]}" "$@" 2>&1 | tee "$log"
  local code=${PIPESTATUS[0]}
  local dur=$(( $(date +%s) - start ))
  local state; state="$(run_state "$code" "$log")"
  local v; v="$(variant_line "$log")"
  [[ -n "$v" ]] && VARIANT[$seed]="${v#diverter_route_ball variant }"

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
      LAG[$seed]="$(rotate_line "$log" | grep -aoE 'max_lag=[^ ]+' | sed 's/max_lag=//')" ;;
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
echo "seed,dead_end,init_sealed,rotate_needed,pad,angle_deg,lever_r,fork_x,speed,release_x,max_lag,visual,oracle,fixed" > "$csv"
n_fixed=0; n_fixed_ok=0
for seed in $SEEDS; do
  v="${VARIANT[$seed]:-}"
  f() { echo "$v" | grep -aoE "$1=[^ ]+" | sed "s/$1=//"; }
  printf '  seed %-3s dead=%-5s sealed=%-5s rot=%-5s pad=%-5s a=%-6s r=%-6s fork=%-7s v=%-5s rel=%-7s lag=%-6s | visual=%s oracle=%s fixed=%s\n' \
    "$seed" "$(f dead_end)" "$(f init_sealed)" "$(f rotate_needed)" "$(f pad)" "$(f angle_deg)" "$(f lever_r)" \
    "$(f fork_x)" "$(f speed)" "$(f release_x)" "${LAG[$seed]:--}" \
    "${VISUAL[$seed]:--}" "${ORACLE[$seed]:--}" "${FIXED[$seed]:--}"
  echo "$seed,$(f dead_end),$(f init_sealed),$(f rotate_needed),$(f pad),$(f angle_deg),$(f lever_r),$(f fork_x),$(f speed),$(f release_x),${LAG[$seed]:-},${VISUAL[$seed]:-},${ORACLE[$seed]:-},${FIXED[$seed]:-}" >> "$csv"
  if [[ -n "${FIXED[$seed]:-}" ]]; then
    n_fixed=$((n_fixed + 1)); [[ "${FIXED[$seed]}" == "success" ]] && n_fixed_ok=$((n_fixed_ok + 1))
  fi
done
if [[ $n_fixed -gt 0 ]]; then
  echo "  fixed_direction 成功率: $n_fixed_ok / $n_fixed（期望接近 1/2；0.3–0.7 内即防捷径成立）"
fi
echo
echo "怎么读："
echo "  visual   打开 $OUTDIR/visual_s*.mp4：死路端墙、挡板相位、目标垫、张角、分岔口位置、拨杆长、球起点应逐 seed 不同，且无穿模。"
echo "  oracle   全部 PASS 才说明 oracle 覆盖了包络；FAIL 的 seed 看其 log 的 result 行与 variant 行，"
echo "           判断是几何（张角 / 可达）还是执行（max_lag / target_error）问题。lag 列不应随张角增长。"
echo "  fixed    成功率远离 1/2 说明死路侧的分布让「永远封右」有系统性优势，需回看包络。"
echo "summary: $csv"
echo "日志: $OUTDIR"
exit $FAIL
