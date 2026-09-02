#!/usr/bin/env bash
# ============================================================================
# linkbar_rotate_to_zone 变体生成实验（variation_axes_plain_zh.md §6.2 第 1 步）。
#
# 回答两个问题，每个 seed 三格：
#   visual   inspect demo 建场景不步进，录一帧静态画面 → 人眼看 visual_s<seed>.mp4：
#            两块颜色区在固定导轨上的位置（同侧/异侧、相邻/分开）、颜色、横梁初始角
#            是否逐 seed 不同，有无穿模，导轨长度是否固定。
#   oracle   physical demo，oracle 规则 → 必须 task_success=True。这是「oracle 在包络
#            内每个变体都可解」的直接证据。
#   nearest  physical demo，nearest_zone 对照规则 → 只记录成败；两区位置独立随机后
#            期望成功率接近 1/2，落在 0.3–0.7 之间即防捷径成立。
#
# 变体参数来自 generation/layout_randomization.py 的 linkbar 注册条目，由
# run.randomize_layout=true run.seed=<seed> 触发；demo 打印一行
#   linkbar_rotate_to_zone variant seed=… target=… assignment=… color_1_deg=… color_2_deg=… init_deg=… gap_deg=… same_side=…
# 本脚本解析它进汇总表。gap_deg 是两色块之间的净角距（0 = 相邻）。
#
# **默认无头。** VIEWER=1 可开窗，但不加 run.keep_open。
#
# 用法：
#   bash bash_scripts/tests/linkbar_variation_sweep.sh                    # 全部三组，seed 0–9
#   SEEDS="0 1 2" bash bash_scripts/tests/linkbar_variation_sweep.sh visual
#   bash bash_scripts/tests/linkbar_variation_sweep.sh oracle nearest
#
# 可调环境变量：
#   SEEDS="0 1 2 3 4 5 6 7 8 9"
#   BACKEND=gpu
#   TIMEOUT_S=900
#   VIEWER=0
#   OUTDIR=runs/linkbar_variation/<时间戳>
#   TOPOGYM_VENV=.venv-gs110
#
# 产出：<OUTDIR>/<group>_s<seed>.log、visual_s<seed>.mp4、summary.csv。
# 退出码：任一 oracle 格非 task_success=True，或任一格 RAISED/TIMEOUT，即非 0。
# nearest 格不计入退出码。刻意不用 set -e。
# ============================================================================
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$REPO"

if [[ -z "${VIRTUAL_ENV:-}" ]]; then
  for candidate in "${TOPOGYM_VENV:-}" "$REPO/.venv-gs110" "$REPO/.venv"; do
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
OUTDIR="${OUTDIR:-runs/linkbar_variation/$(date +%Y%m%d_%H%M%S)}"

VIEWER_ARGS=()
[[ "$VIEWER" == "1" ]] && VIEWER_ARGS=(run.viewer=true)

SUITES=(visual oracle nearest)
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

# 离线门先过：注册条目的包络、确定性、黄金值。几秒钟。
if ! python -B tests/check_variant_rng.py > "$OUTDIR/offline.log" 2>&1; then
  echo "[error] tests/check_variant_rng.py 未通过，见 $OUTDIR/offline.log" >&2
  exit 1
fi

FAIL=0
declare -A VARIANT ORACLE NEAREST VISUAL

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

variant_line() { grep -aF "linkbar_rotate_to_zone variant seed=" "$1" | tail -1; }
result_line()  { grep -aF "linkbar_rotate_to_zone result" "$1" | tail -1; }

run_cell() {
  local group="$1" seed="$2"; shift 2
  local tag="${group}_s${seed}" log="$OUTDIR/${group}_s${seed}.log"
  echo
  echo "==================== $tag ===================="
  local start; start=$(date +%s)
  local cmd=()
  case "$group" in
    visual)
      cmd=(python -B -m demos.connectivity.linkbar_rotate_to_zone_inspect_demo
           env.genesis.backend="$BACKEND" "${VIEWER_ARGS[@]}"
           run.randomize_layout=true "run.seed=$seed" run.static_only=true
           recording=default "recording.path=$OUTDIR/visual_s${seed}.mp4" recording.camera=oblique) ;;
    oracle)
      cmd=(python -B -m demos.connectivity.linkbar_rotate_to_zone_physical_demo
           env.genesis.backend="$BACKEND" "${VIEWER_ARGS[@]}"
           run.randomize_layout=true "run.seed=$seed" run.oracle_mode=oracle) ;;
    nearest)
      cmd=(python -B -m demos.connectivity.linkbar_rotate_to_zone_physical_demo
           env.genesis.backend="$BACKEND" "${VIEWER_ARGS[@]}"
           run.randomize_layout=true "run.seed=$seed" run.oracle_mode=nearest_zone) ;;
  esac
  timeout "${TIMEOUT_S}s" "${cmd[@]}" "$@" 2>&1 | tee "$log"
  local code=${PIPESTATUS[0]}
  local dur=$(( $(date +%s) - start ))
  local state; state="$(run_state "$code" "$log")"
  local v; v="$(variant_line "$log")"
  [[ -n "$v" ]] && VARIANT[$seed]="${v#linkbar_rotate_to_zone variant }"

  local verdict=""
  case "$group" in
    visual)
      if [[ "$state" == "ok" && -s "$OUTDIR/visual_s${seed}.mp4" ]]; then verdict="ok (看 mp4)"; else verdict="FAIL $state"; FAIL=1; fi
      VISUAL[$seed]="$verdict" ;;
    oracle)
      if [[ "$state" != "ok" ]]; then verdict="FAIL $state"; FAIL=1
      elif result_line "$log" | grep -qaF "task_success=True"; then verdict="PASS"
      else verdict="FAIL $(result_line "$log" | grep -aoE 'failure=[a-z_]+')"; FAIL=1; fi
      ORACLE[$seed]="$verdict" ;;
    nearest)
      if [[ "$state" != "ok" ]]; then verdict="$state"
      elif result_line "$log" | grep -qaF "task_success=True"; then verdict="success"
      else verdict="$(result_line "$log" | grep -aoE 'failure=[a-z_]+' | sed 's/failure=//')"; fi
      NEAREST[$seed]="$verdict" ;;
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
echo "seed,target,assignment,color_1_deg,color_2_deg,init_deg,gap_deg,same_side,visual,oracle,nearest" > "$csv"
n_near=0; n_near_ok=0
for seed in $SEEDS; do
  v="${VARIANT[$seed]:-}"
  f() { echo "$v" | grep -aoE "$1=[^ ]+" | sed "s/$1=//"; }
  printf '  seed %-3s target=%-7s assignment=%-28s c1=%-7s c2=%-7s init=%-7s gap=%-6s same_side=%-5s | visual=%s oracle=%s nearest=%s\n' \
    "$seed" "$(f target)" "$(f assignment)" "$(f color_1_deg)" "$(f color_2_deg)" "$(f init_deg)" \
    "$(f gap_deg)" "$(f same_side)" \
    "${VISUAL[$seed]:--}" "${ORACLE[$seed]:--}" "${NEAREST[$seed]:--}"
  echo "$seed,$(f target),$(f assignment),$(f color_1_deg),$(f color_2_deg),$(f init_deg),$(f gap_deg),$(f same_side),${VISUAL[$seed]:-},${ORACLE[$seed]:-},${NEAREST[$seed]:-}" >> "$csv"
  if [[ -n "${NEAREST[$seed]:-}" ]]; then
    n_near=$((n_near + 1)); [[ "${NEAREST[$seed]}" == "success" ]] && n_near_ok=$((n_near_ok + 1))
  fi
done
if [[ $n_near -gt 0 ]]; then
  echo "  nearest_zone 成功率: $n_near_ok / $n_near（期望接近 1/2；0.3–0.7 内即防捷径成立）"
fi
echo
echo "怎么读："
echo "  visual   打开 $OUTDIR/visual_s*.mp4：两区在导轨上的位置、颜色、横梁初始角应逐 seed 不同，导轨长度固定，且无穿模。"
echo "  oracle   全部 PASS 才说明 oracle 覆盖了包络；FAIL 的 seed 看其 log 的 result 行与 variant 行，"
echo "           判断是几何（区角/初始角组合）还是执行（max_lag / release_drift）问题。"
echo "  nearest  成功率远离 1/2 说明两区角的分布让「转最近」有系统性优势，需回看包络。"
echo "summary: $csv"
echo "日志: $OUTDIR"
exit $FAIL
