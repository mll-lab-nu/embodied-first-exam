#!/usr/bin/env bash
# ============================================================================
# swap_crossing_sign 变体生成实验（2026-09-11 重做：2–3 根绳 × 1–2 个交叉，计划 valiant-soaring-pretzel）。
#
# 每个 seed 四组：
#   visual        oracle 格再带录像 → 人眼看 visual_s<seed>.mp4：绳数、交叉数、出线后的弯、交叉位置、
#                 插头位置是否逐 seed 不同，出生时每个交叉谁在上是否与 word 一致。
#   oracle        physical demo：每步用实测中心线重新规划、执行第一步，直到每个交叉都翻过来
#                 → 必须 terminal=True（label=none）。gt_match=True 说明判定器读到的出生交叉表
#                 = 生成器声明的（防捷径轴生效的前提）。
#   restack_same  对照：先把交叉全撤掉，再按出生原样搭回去 → 预期 terminal=False、label=unchanged。
#   flip_nearest  对照：只翻离插头最近的那个交叉 → 1 个交叉的格预期成功，2 个交叉的格预期 label=partial_flip；
#                 成功格数应当等于抽到 1 个交叉的格数。
#
# 变体参数来自 task 配置末尾的 variation 块，由 run.randomize_layout=true run.seed=<seed>
# 触发；demo 打印一行
#   swap_crossing_sign variant seed=… ropes=… crossings=… word=… frac=… window_u=… bows_mm=…
#     spacing=… cy=… x_end=… planned_moves=… lift_pred=…
# 本脚本解析它进汇总表。demo 在某一步要求的抬升超过工作区顶时打印 WARNING，汇总表记成 lift_warn 列。
#
# **成本**：FEM 绳每步 150–200 s；1 个交叉的格 2–3 步（6.5–10 min），2 个交叉的格 3–5 步（10–17 min）。
# 十个 seed 四组约 8 h；对照组建议 SEEDS="0 1 2 3"。
# **默认无头。** VIEWER=1 可开窗，但不加 run.keep_open。
#
# 用法：
#   bash bash_scripts/tests/swap_crossing_sign_variation_sweep.sh oracle                 # seed 0–9
#   SEEDS="0 1 2" bash bash_scripts/tests/swap_crossing_sign_variation_sweep.sh restack_same flip_nearest
#   bash bash_scripts/tests/swap_crossing_sign_variation_sweep.sh                        # 全部四组
#
# 可调环境变量：
#   SEEDS="0 1 2 3 4 5 6 7 8 9"
#   BACKEND=gpu
#   TIMEOUT_S=2400
#   VIEWER=0
#   OUTDIR=runs/swap_crossing_sign_variation/<时间戳>
#   TOPOGYM_VENV=.venv-gs121-nyx
#   SKIP_OFFLINE=1  跳过离线门（13 个任务的 check_variant_rng 约 15 分钟）。只在你刚跑过
#                   tests/check_variant_rng.py 与本任务两道门时用；默认 0，照跑。
#
# 产出：<OUTDIR>/<group>_s<seed>.log、visual_s<seed>.mp4、summary.csv。
# 退出码：任一 oracle / visual 格非 terminal=True，或任一格 RAISED/TIMEOUT，即非 0。
# 对照组格不计入退出码。刻意不用 set -e。
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
TIMEOUT_S="${TIMEOUT_S:-2400}"
VIEWER="${VIEWER:-0}"
OUTDIR="${OUTDIR:-runs/swap_crossing_sign_variation/$(date +%Y%m%d_%H%M%S)}"

VIEWER_ARGS=()
[[ "$VIEWER" == "1" ]] && VIEWER_ARGS=(run.viewer=true)

SUITES=(visual oracle restack_same flip_nearest)
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

# 离线门先过：变体块（check_variant_rng）、本任务几何门（全部解析顶点）、planner 门（抽样布局有解的比例）。
# SKIP_OFFLINE=1 跳过这一段；跳过时把原因写进 offline.log，免得事后看目录以为门没跑过。
if [[ "${SKIP_OFFLINE:-0}" == "1" ]]; then
  echo "SKIP_OFFLINE=1：调用方声明已跑过 tests/check_variant_rng.py 与本任务两道门，本轮跳过" \
    > "$OUTDIR/offline.log"
else
  for gate in tests/check_variant_rng.py tests/check_swap_crossing_sign_geometry.py tests/check_swap_crossing_sign_planner.py; do
    if ! python -B "$gate" >> "$OUTDIR/offline.log" 2>&1; then
      echo "[error] $gate 未通过，见 $OUTDIR/offline.log" >&2
      exit 1
    fi
  done
fi

FAIL=0
declare -A VARIANT ORACLE RESTACK NEAREST VISUAL GT LIFTWARN MOVES

run_state() {
  local code="$1" log="$2"
  if [[ "$code" == "124" ]]; then echo "TIMEOUT"; return; fi
  grep -qaiE "^Traceback" "$log" && { echo "RAISED"; return; }
  # physical demo 用退出码表达 solved 与否（对照组预期非 0），不算异常
  echo "ok"
}

variant_line() { grep -aF "swap_crossing_sign variant seed=" "$1" | tail -1; }
result_line()  { grep -aF "swap_crossing_sign_result" "$1" | tail -1; }
start_line()   { grep -aF "swap_crossing_sign_start" "$1" | tail -1; }
field()        { echo "$1" | grep -aoE "$2=[^ ]+" | head -1 | sed "s/$2=//"; }

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
    oracle|restack_same|flip_nearest)
      cmd+=("run.oracle_mode=$group") ;;
  esac
  timeout "${TIMEOUT_S}s" "${cmd[@]}" "$@" 2>&1 | tee "$log"
  local code=${PIPESTATUS[0]}
  local dur=$(( $(date +%s) - start ))
  local state; state="$(run_state "$code" "$log")"
  local v; v="$(variant_line "$log")"
  [[ -n "$v" ]] && VARIANT[$seed]="${v#swap_crossing_sign variant }"

  local r; r="$(result_line "$log")"
  local terminal; terminal="$(field "$r" terminal)"
  local label; label="$(field "$r" label)"
  local verdict=""
  case "$group" in
    visual|oracle)
      if [[ "$state" != "ok" ]]; then verdict="FAIL $state"; FAIL=1
      elif [[ "$terminal" == "True" && ( "$group" == "oracle" || -s "$OUTDIR/visual_s${seed}.mp4" ) ]]; then verdict="PASS"
      else verdict="FAIL ${label:-no_result}"; FAIL=1; fi
      [[ "$group" == "visual" ]] && VISUAL[$seed]="$verdict" || ORACLE[$seed]="$verdict"
      MOVES[$seed]="$(field "$r" moves)" ;;
    restack_same)
      if [[ "$state" != "ok" ]]; then verdict="$state"; else verdict="${label:-no_result}"; fi
      RESTACK[$seed]="$verdict" ;;
    flip_nearest)
      if [[ "$state" != "ok" ]]; then verdict="$state"
      elif [[ "$terminal" == "True" ]]; then verdict="success"
      else verdict="${label:-no_result}"; fi
      NEAREST[$seed]="$verdict" ;;
  esac
  GT[$seed]="$(field "$(start_line "$log")" gt_match)"
  if grep -qaF "workspace ceiling" "$log"; then LIFTWARN[$seed]="yes"; else LIFTWARN[$seed]="${LIFTWARN[$seed]:-no}"; fi
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
echo "seed,ropes,crossings,word,frac,window_u,bows_mm,spacing,cy,x_end,planned_moves,lift_pred,gt_match,lift_warn,moves,visual,oracle,restack_same,flip_nearest" > "$csv"
n_one=0; n_near_ok=0; n_near=0; n_restack=0; n_restack_ok=0
for seed in $SEEDS; do
  v="${VARIANT[$seed]:-}"
  crossings="$(field "$v" crossings)"
  printf '  seed %-3s ropes=%-2s crossings=%-2s word=%-7s frac=%-12s planned=%-4s gt=%-5s warn=%-3s | visual=%s oracle=%s restack_same=%s flip_nearest=%s\n' \
    "$seed" "$(field "$v" ropes)" "$crossings" "$(field "$v" word)" "$(field "$v" frac)" "$(field "$v" planned_moves)" \
    "${GT[$seed]:--}" "${LIFTWARN[$seed]:--}" "${VISUAL[$seed]:--}" "${ORACLE[$seed]:--}" "${RESTACK[$seed]:--}" "${NEAREST[$seed]:--}"
  echo "$seed,$(field "$v" ropes),$crossings,\"$(field "$v" word)\",$(field "$v" frac),$(field "$v" window_u),$(field "$v" bows_mm),$(field "$v" spacing),$(field "$v" cy),$(field "$v" x_end),$(field "$v" planned_moves),$(field "$v" lift_pred),${GT[$seed]:-},${LIFTWARN[$seed]:-},${MOVES[$seed]:-},${VISUAL[$seed]:-},${ORACLE[$seed]:-},${RESTACK[$seed]:-},${NEAREST[$seed]:-}" >> "$csv"
  if [[ -n "${NEAREST[$seed]:-}" ]]; then
    n_near=$((n_near + 1))
    expect="partial_flip"; [[ "$crossings" == "1" ]] && { expect="success"; n_one=$((n_one + 1)); }
    [[ "${NEAREST[$seed]}" == "$expect" ]] && n_near_ok=$((n_near_ok + 1))
  fi
  if [[ -n "${RESTACK[$seed]:-}" ]]; then
    n_restack=$((n_restack + 1)); [[ "${RESTACK[$seed]}" == "unchanged" ]] && n_restack_ok=$((n_restack_ok + 1))
  fi
done
[[ $n_restack -gt 0 ]] && echo "  restack_same 判 unchanged: $n_restack_ok / $n_restack（预期全部）"
[[ $n_near -gt 0 ]] && echo "  flip_nearest 符合预期: $n_near_ok / $n_near（1 个交叉的 $n_one 格应成功，其余应判 partial_flip）"
echo
echo "怎么读："
echo "  visual        打开 $OUTDIR/visual_s*.mp4：绳数、交叉数、出线后的弯、交叉位置应逐 seed 不同。"
echo "  oracle        全部 PASS 才说明 oracle 覆盖了包络；FAIL 的 seed 看 log 里的 swap_crossing_sign_after_move 行"
echo "                （每步后的交叉表 now=[...]）与开局的 planned=[...]；label 说明终态差在哪。"
echo "  restack_same  应全部 unchanged；成功说明判据有问题。"
echo "  flip_nearest  1 个交叉的格应成功、2 个交叉的格应 partial_flip——量出「两个都要翻」这条判据在起作用。"
echo "summary: $csv"
echo "日志: $OUTDIR"
exit $FAIL
