#!/usr/bin/env bash
# ============================================================================
# band_untwist 变体生成实验（variation_axes_plain_zh.md §6.2 第 4 步）。
#
# 每个 seed 三格：
#   visual    inspect demo 建场景不沉降，录几帧静态画面 → 人眼看 visual_s<seed>.mp4：
#             8 字朝向、位置、两叶大小、交叉夹角、绳头间距是否逐 seed 不同，有无穿模。
#   oracle    physical demo，oracle 抓压在上面那股的绳头 → 必须 terminal=True。
#             这是「oracle 在包络内每个变体都可解」的直接证据；over_end=1 的格必须抓端 1。
#   wrong_end physical demo，对照规则抓下面那股 → 只记录；预期 failure_label=wrong_end（1 → 2）。
#
# 变体参数来自 task 配置末尾的 variation 块，由 run.randomize_layout=true run.seed=<seed>
# 触发；demo 打印一行
#   band_untwist variant seed=… over_end=… heading=… cx=… cy=… half_angle=… r_closed=…
#     r_open=… end_gap=… ramp=… lift_pred=…
# 本脚本解析它进汇总表。
#
# **成本**：FEM 绳。4090 实测（2026-09-03）oracle 一格 ≈ 5 min，wrong_end ≈ 5 min，visual ≈ 25 s。
# 十个 seed 三组全跑约 1.7 h；wrong_end 建议 SEEDS="0 1 2"。
# **默认无头。** VIEWER=1 可开窗，但不加 run.keep_open。
#
# 用法：
#   bash bash_scripts/tests/band_untwist_variation_sweep.sh visual oracle          # seed 0–9
#   SEEDS="0 1 2" bash bash_scripts/tests/band_untwist_variation_sweep.sh wrong_end
#   bash bash_scripts/tests/band_untwist_variation_sweep.sh                       # 全部三组
#
# 可调环境变量：
#   SEEDS="0 1 2 3 4 5 6 7 8 9"
#   BACKEND=gpu
#   TIMEOUT_S=1800
#   VIEWER=0
#   OUTDIR=runs/band_untwist_variation/<时间戳>
#   TOPOGYM_VENV=.venv-gs121
#
# 产出：<OUTDIR>/<group>_s<seed>.log、visual_s<seed>.mp4、summary.csv。
# 退出码：任一 oracle 格非 terminal=True，或任一格 RAISED/TIMEOUT，即非 0。
# wrong_end 格不计入退出码。刻意不用 set -e。
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
TIMEOUT_S="${TIMEOUT_S:-1800}"
VIEWER="${VIEWER:-0}"
OUTDIR="${OUTDIR:-runs/band_untwist_variation/$(date +%Y%m%d_%H%M%S)}"

VIEWER_ARGS=()
[[ "$VIEWER" == "1" ]] && VIEWER_ARGS=(run.viewer=true)

SUITES=(visual oracle wrong_end)
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

# 离线门先过：变体块的包络、派生区间、拒绝率；8 字几何、计数、规划器、256 角点。几十秒。
if ! python -B tests/check_variant_rng.py > "$OUTDIR/offline.log" 2>&1; then
  echo "[error] tests/check_variant_rng.py 未通过，见 $OUTDIR/offline.log" >&2
  exit 1
fi
if ! python -B tests/check_band_untwist_geometry.py >> "$OUTDIR/offline.log" 2>&1; then
  echo "[error] tests/check_band_untwist_geometry.py 未通过，见 $OUTDIR/offline.log" >&2
  exit 1
fi

FAIL=0
declare -A VARIANT ORACLE WRONG VISUAL GRASPED

run_state() {
  local code="$1" log="$2"
  if [[ "$code" == "124" ]]; then echo "TIMEOUT"; return; fi
  grep -qaiE "^Traceback" "$log" && { echo "RAISED"; return; }
  # physical demo 用退出码表达 solved 与否（wrong_end 预期非 0），不算异常
  echo "ok"
}

variant_line() { grep -aF "band_untwist variant seed=" "$1" | tail -1; }
result_line()  { grep -aF "band_untwist_result" "$1" | tail -1; }
move_line()    { grep -aF "band_untwist_move" "$1" | head -1; }

run_cell() {
  local group="$1" seed="$2"; shift 2
  local tag="${group}_s${seed}" log="$OUTDIR/${group}_s${seed}.log"
  echo
  echo "==================== $tag ===================="
  local start; start=$(date +%s)
  local cmd=()
  case "$group" in
    visual)
      cmd=(python -B -m demos.entangle.band_untwist_inspect_demo
           env.genesis.backend="$BACKEND" "${VIEWER_ARGS[@]}"
           run.randomize_layout=true "run.seed=$seed" run.static_only=true
           recording=default "recording.path=$OUTDIR/visual_s${seed}.mp4" recording.camera=oblique) ;;
    oracle)
      cmd=(python -B -m demos.entangle.band_untwist_physical_pinch_demo
           env.genesis.backend="$BACKEND" "${VIEWER_ARGS[@]}"
           run.randomize_layout=true "run.seed=$seed" run.oracle_mode=oracle) ;;
    wrong_end)
      cmd=(python -B -m demos.entangle.band_untwist_physical_pinch_demo
           env.genesis.backend="$BACKEND" "${VIEWER_ARGS[@]}"
           run.randomize_layout=true "run.seed=$seed" run.oracle_mode=wrong_end) ;;
  esac
  timeout "${TIMEOUT_S}s" "${cmd[@]}" "$@" 2>&1 | tee "$log"
  local code=${PIPESTATUS[0]}
  local dur=$(( $(date +%s) - start ))
  local state; state="$(run_state "$code" "$log")"
  local v; v="$(variant_line "$log")"
  [[ -n "$v" ]] && VARIANT[$seed]="${v#band_untwist variant }"

  local verdict=""
  case "$group" in
    visual)
      if [[ "$state" == "ok" && -s "$OUTDIR/visual_s${seed}.mp4" ]]; then verdict="ok (看 mp4)"; else verdict="FAIL $state"; FAIL=1; fi
      VISUAL[$seed]="$verdict" ;;
    oracle)
      if [[ "$state" != "ok" ]]; then verdict="FAIL $state"; FAIL=1
      elif result_line "$log" | grep -qaF "terminal=True"; then verdict="PASS"
      else verdict="FAIL $(result_line "$log" | grep -aoE 'failure_label=[A-Za-z_]+' | sed 's/failure_label=//')"; FAIL=1; fi
      ORACLE[$seed]="$verdict"
      GRASPED[$seed]="$(move_line "$log" | grep -aoE 'end=[01]' | sed 's/end=//')" ;;
    wrong_end)
      if [[ "$state" != "ok" ]]; then verdict="$state"
      elif result_line "$log" | grep -qaF "terminal=True"; then verdict="terminal(!)"
      else verdict="$(result_line "$log" | grep -aoE 'failure_label=[A-Za-z_]+' | sed 's/failure_label=//')"; fi
      WRONG[$seed]="$verdict" ;;
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
echo "seed,over_end,heading,cx,cy,half_angle,r_closed,r_open,end_gap,lift_pred,grasped,visual,oracle,wrong_end" > "$csv"
n_wrong=0; n_wrong_label=0; n_mirror=0; n_mirror_ok=0
for seed in $SEEDS; do
  v="${VARIANT[$seed]:-}"
  f() { echo "$v" | grep -aoE "$1=[^ ]+" | sed "s/$1=//"; }
  printf '  seed %-3s over_end=%-2s heading=%-6s cx=%-7s cy=%-7s half=%-5s r_c=%-6s r_o=%-6s gap=%-6s lift=%-5s grasped=%-2s | visual=%s oracle=%s wrong_end=%s\n' \
    "$seed" "$(f over_end)" "$(f heading)" "$(f cx)" "$(f cy)" "$(f half_angle)" "$(f r_closed)" "$(f r_open)" \
    "$(f end_gap)" "$(f lift_pred)" "${GRASPED[$seed]:--}" \
    "${VISUAL[$seed]:--}" "${ORACLE[$seed]:--}" "${WRONG[$seed]:--}"
  echo "$seed,$(f over_end),$(f heading),$(f cx),$(f cy),$(f half_angle),$(f r_closed),$(f r_open),$(f end_gap),$(f lift_pred),${GRASPED[$seed]:-},${VISUAL[$seed]:-},${ORACLE[$seed]:-},${WRONG[$seed]:-}" >> "$csv"
  if [[ -n "${ORACLE[$seed]:-}" && "$(f over_end)" == "1" ]]; then
    n_mirror=$((n_mirror + 1)); [[ "${GRASPED[$seed]:-}" == "1" && "${ORACLE[$seed]}" == "PASS" ]] && n_mirror_ok=$((n_mirror_ok + 1))
  fi
  if [[ -n "${WRONG[$seed]:-}" ]]; then
    n_wrong=$((n_wrong + 1)); [[ "${WRONG[$seed]}" == "wrong_end" ]] && n_wrong_label=$((n_wrong_label + 1))
  fi
done
if [[ $n_mirror -gt 0 ]]; then
  echo "  镜像格（over_end=1）: $n_mirror_ok / $n_mirror 抓了端 1 且成功（planner 只读实测 over 端，这是镜像轴生效的证据）"
fi
if [[ $n_wrong -gt 0 ]]; then
  echo "  wrong_end 判 wrong_end: $n_wrong_label / $n_wrong（预期全部：抓错端后 1 → 2）"
fi
echo
echo "怎么读："
echo "  visual    打开 $OUTDIR/visual_s*.mp4：8 字朝向、位置、两叶大小、交叉夹角、绳头间距应逐 seed 不同，且无穿模。"
echo "  oracle    全部 PASS 才说明 oracle 覆盖了包络；FAIL 的 seed 看其 log 的 band_untwist_after_move 行"
echo "            （grasped / reason / self_crossings / ends_on_table）与 variant 行（lift_pred 大的格抬得最高，r_o 大的格弧最长）。"
echo "  wrong_end 应全部 wrong_end；terminal(!) 说明抓错端也解开了，判据或几何有问题。"
echo "summary: $csv"
echo "日志: $OUTDIR"
exit $FAIL
