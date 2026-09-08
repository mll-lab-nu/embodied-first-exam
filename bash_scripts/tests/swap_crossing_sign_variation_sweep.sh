#!/usr/bin/env bash
# ============================================================================
# swap_crossing_sign 变体生成实验（variation_axes_plain_zh.md §6.2 第 5 步）。
#
# 每个 seed 三格：
#   visual        oracle 格再带录像（本任务没有 inspect demo；两步走完，视频即证据）→ 人眼看
#                 visual_s<seed>.mp4：交叉位置、车道间距、左右平移、线长是否逐 seed 不同，
#                 出生时哪根在上是否随 sign 变。
#   oracle        physical demo，两步 separate + cover → 必须 terminal=True。
#                 这是「oracle 在包络内每个变体都可解」的直接证据；sign 轴生效的证据是
#                 gt_match=True（判定器读到的出生符号 = 抽到的符号）且 move 1 抓的是在上那根。
#   restack_same  对照规则：第二步把同一根放回去 → 只记录；预期 terminal=False、sign_flipped=False。
#
# 变体参数来自 task 配置末尾的 variation 块，由 run.randomize_layout=true run.seed=<seed>
# 触发；demo 打印一行
#   swap_crossing_sign variant seed=… sign=… frac=… spacing=… cy=… x_end=… lift_pred=…
# 本脚本解析它进汇总表。demo 在 planner 要求的抬升超过工作区顶 0.40 时打印 WARNING，
# 汇总表记成 lift_warn 列。
#
# **成本**：FEM 绳两步。band_untwist 一步 ≈ 5 min（4090），本任务预计一格 8–10 min。
# 十个 seed 三组全跑约 4–5 h；restack_same 建议 SEEDS="0 1 2"。
# **默认无头。** VIEWER=1 可开窗，但不加 run.keep_open。
#
# 用法：
#   bash bash_scripts/tests/swap_crossing_sign_variation_sweep.sh oracle                 # seed 0–9
#   SEEDS="0 1 2" bash bash_scripts/tests/swap_crossing_sign_variation_sweep.sh restack_same
#   bash bash_scripts/tests/swap_crossing_sign_variation_sweep.sh                        # 全部三组
#
# 可调环境变量：
#   SEEDS="0 1 2 3 4 5 6 7 8 9"
#   BACKEND=gpu
#   TIMEOUT_S=1800
#   VIEWER=0
#   OUTDIR=runs/swap_crossing_sign_variation/<时间戳>
#   TOPOGYM_VENV=.venv-gs121
#
# 产出：<OUTDIR>/<group>_s<seed>.log、visual_s<seed>.mp4、summary.csv。
# 退出码：任一 oracle / visual 格非 terminal=True，或任一格 RAISED/TIMEOUT，即非 0。
# restack_same 格不计入退出码。刻意不用 set -e。
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
OUTDIR="${OUTDIR:-runs/swap_crossing_sign_variation/$(date +%Y%m%d_%H%M%S)}"

VIEWER_ARGS=()
[[ "$VIEWER" == "1" ]] && VIEWER_ARGS=(run.viewer=true)

SUITES=(visual oracle restack_same)
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

# 离线门先过：变体块的包络、拒绝率；braid 几何七行、符号与位置、规划器、32 角点。
if ! python -B tests/check_variant_rng.py > "$OUTDIR/offline.log" 2>&1; then
  echo "[error] tests/check_variant_rng.py 未通过，见 $OUTDIR/offline.log" >&2
  exit 1
fi
if ! python -B tests/check_swap_crossing_sign_geometry.py >> "$OUTDIR/offline.log" 2>&1; then
  echo "[error] tests/check_swap_crossing_sign_geometry.py 未通过，见 $OUTDIR/offline.log" >&2
  exit 1
fi

FAIL=0
declare -A VARIANT ORACLE RESTACK VISUAL GT SEPSTRAND LIFTWARN

run_state() {
  local code="$1" log="$2"
  if [[ "$code" == "124" ]]; then echo "TIMEOUT"; return; fi
  grep -qaiE "^Traceback" "$log" && { echo "RAISED"; return; }
  # physical demo 用退出码表达 solved 与否（restack_same 预期非 0），不算异常
  echo "ok"
}

variant_line() { grep -aF "swap_crossing_sign variant seed=" "$1" | tail -1; }
result_line()  { grep -aF "swap_crossing_sign_result" "$1" | tail -1; }
start_line()   { grep -aF "swap_crossing_sign_start" "$1" | tail -1; }
move_line()    { grep -aF "swap_crossing_sign_move 1/" "$1" | head -1; }

run_cell() {
  local group="$1" seed="$2"; shift 2
  local tag="${group}_s${seed}" log="$OUTDIR/${group}_s${seed}.log"
  echo
  echo "==================== $tag ===================="
  local start; start=$(date +%s)
  local cmd=(python -B -m demos.entangle.swap_crossing_sign_physical_pinch_demo
             env.genesis.backend="$BACKEND" "${VIEWER_ARGS[@]}"
             run.randomize_layout=true "run.seed=$seed")
  case "$group" in
    visual)
      cmd+=(run.oracle_mode=oracle recording=default "recording.path=$OUTDIR/visual_s${seed}.mp4" recording.camera=oblique) ;;
    oracle)
      cmd+=(run.oracle_mode=oracle) ;;
    restack_same)
      cmd+=(run.oracle_mode=restack_same) ;;
  esac
  timeout "${TIMEOUT_S}s" "${cmd[@]}" "$@" 2>&1 | tee "$log"
  local code=${PIPESTATUS[0]}
  local dur=$(( $(date +%s) - start ))
  local state; state="$(run_state "$code" "$log")"
  local v; v="$(variant_line "$log")"
  [[ -n "$v" ]] && VARIANT[$seed]="${v#swap_crossing_sign variant }"

  local verdict=""
  local terminal_ok=0
  result_line "$log" | grep -qaF "terminal=True" && terminal_ok=1
  case "$group" in
    visual)
      if [[ "$state" == "ok" && "$terminal_ok" == "1" && -s "$OUTDIR/visual_s${seed}.mp4" ]]; then verdict="PASS (看 mp4)"
      elif [[ "$state" != "ok" ]]; then verdict="FAIL $state"; FAIL=1
      else verdict="FAIL $(result_line "$log" | grep -aoE 'sign_flipped=[A-Za-z]+ separated_seen=[A-Za-z]+')"; FAIL=1; fi
      VISUAL[$seed]="$verdict" ;;
    oracle)
      if [[ "$state" != "ok" ]]; then verdict="FAIL $state"; FAIL=1
      elif [[ "$terminal_ok" == "1" ]]; then verdict="PASS"
      else verdict="FAIL $(result_line "$log" | grep -aoE 'sign_flipped=[A-Za-z]+ separated_seen=[A-Za-z]+ final_crossings=[0-9]+')"; FAIL=1; fi
      ORACLE[$seed]="$verdict" ;;
    restack_same)
      if [[ "$state" != "ok" ]]; then verdict="$state"
      elif [[ "$terminal_ok" == "1" ]]; then verdict="terminal(!)"
      else verdict="$(result_line "$log" | grep -aoE 'sign_flipped=[A-Za-z]+' )"; fi
      RESTACK[$seed]="$verdict" ;;
  esac
  if [[ "$group" != "restack_same" ]]; then
    GT[$seed]="$(start_line "$log" | grep -aoE 'gt_match=[A-Za-z]+' | sed 's/gt_match=//')"
    SEPSTRAND[$seed]="$(move_line "$log" | grep -aoE 'strand=[0-9]+' | head -1 | sed 's/strand=//')"
    if grep -qaF "above the" "$log" && grep -qaF "workspace ceiling" "$log"; then LIFTWARN[$seed]="yes"; else LIFTWARN[$seed]="no"; fi
  fi
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
echo "seed,sign,frac,spacing,cy,x_end,lift_pred,gt_match,sep_strand,lift_warn,visual,oracle,restack_same" > "$csv"
n_gt=0; n_gt_ok=0; n_sep=0; n_sep_ok=0; n_restack=0; n_restack_fail=0
for seed in $SEEDS; do
  v="${VARIANT[$seed]:-}"
  f() { echo "$v" | grep -aoE "$1=[^ ]+" | sed "s/$1=//"; }
  sign="$(f sign)"
  printf '  seed %-3s sign=%-3s frac=%-7s spacing=%-7s cy=%-8s x_end=%-7s lift=%-6s gt=%-5s sep=%-2s warn=%-3s | visual=%s oracle=%s restack_same=%s\n' \
    "$seed" "$sign" "$(f frac)" "$(f spacing)" "$(f cy)" "$(f x_end)" "$(f lift_pred)" \
    "${GT[$seed]:--}" "${SEPSTRAND[$seed]:--}" "${LIFTWARN[$seed]:--}" \
    "${VISUAL[$seed]:--}" "${ORACLE[$seed]:--}" "${RESTACK[$seed]:--}"
  echo "$seed,$sign,$(f frac),$(f spacing),$(f cy),$(f x_end),$(f lift_pred),${GT[$seed]:-},${SEPSTRAND[$seed]:-},${LIFTWARN[$seed]:-},${VISUAL[$seed]:-},${ORACLE[$seed]:-},${RESTACK[$seed]:-}" >> "$csv"
  if [[ -n "${GT[$seed]:-}" ]]; then
    n_gt=$((n_gt + 1)); [[ "${GT[$seed]}" == "True" ]] && n_gt_ok=$((n_gt_ok + 1))
  fi
  # sign=+1 → 出生在 -y 车道那根（strand 0）在上，move 1 应抓 strand 0；sign=-1 → strand 1。
  if [[ -n "${SEPSTRAND[$seed]:-}" && -n "$sign" ]]; then
    n_sep=$((n_sep + 1))
    expect=0; [[ "$sign" == "-1" ]] && expect=1
    [[ "${SEPSTRAND[$seed]}" == "$expect" ]] && n_sep_ok=$((n_sep_ok + 1))
  fi
  if [[ -n "${RESTACK[$seed]:-}" ]]; then
    n_restack=$((n_restack + 1)); [[ "${RESTACK[$seed]}" == "sign_flipped=False" ]] && n_restack_fail=$((n_restack_fail + 1))
  fi
done
[[ $n_gt -gt 0 ]] && echo "  gt_match: $n_gt_ok / $n_gt（判定器读到的出生符号 = 抽到的 sign）"
[[ $n_sep -gt 0 ]] && echo "  move 1 抓在上那根: $n_sep_ok / $n_sep（planner 只读实测 over 股，这是 sign 轴生效的证据）"
[[ $n_restack -gt 0 ]] && echo "  restack_same 判 sign_flipped=False: $n_restack_fail / $n_restack（预期全部）"
echo
echo "怎么读："
echo "  visual        打开 $OUTDIR/visual_s*.mp4：交叉位置、间距、左右平移、线长应逐 seed 不同，出生上下随 sign。"
echo "  oracle        全部 PASS 才说明 oracle 覆盖了包络；FAIL 的 seed 看其 log 的 swap_crossing_sign_after_move 行"
echo "                （crossings / min_sep / separated_seen）与 variant 行（lift_pred 大的格抬得最高）；warn=yes 的格"
echo "                planner 要的抬升超过 0.40 m 顶（cover 步弧长随第一根放下的形状变）。"
echo "  restack_same  应全部 sign_flipped=False；terminal(!) 说明放回同一根也判翻转，判据有问题。"
echo "summary: $csv"
echo "日志: $OUTDIR"
exit $FAIL
