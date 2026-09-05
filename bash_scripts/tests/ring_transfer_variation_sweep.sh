#!/usr/bin/env bash
# ============================================================================
# ring_transfer 变体生成实验（variation_axes_plain_zh.md §6.2 第 10 步）。
#
# 每个 seed 三格：
#   visual     physical demo 走 carry 到抬离完成（run.stop_after=clear：捏住、从出生柱正上方
#              提起、环挂在指尖下就停，exit 2），录像 → 人眼看 visual_s<seed>.mp4：两柱位置 /
#              柱距 / 朝向 / 柱高 / 粗细 / 挡头、环套在哪根柱上是否逐 seed 不同，有无穿模。
#              没有 inspect demo，所以走 physical demo。
#   oracle     physical demo 全程 carry：捏取 → 抬离出生柱 → 悬着搬到目标柱近侧 → 推过 → 放下
#              → 必须 success=True（终态只套目标柱、两顶越过、无穿模）。
#              这是「oracle 在包络内每个变体都可解」的直接证据。
#   lift_only  对照组：run.motion=lift_only，用 carry 同样的捏取与反应式抬离把环真正提离出生柱（环底越过挡头顶），
#              搬到两柱中点放下、不套目标柱 → 只记录；预期 success=False 且终态 enclosure=[]（任务书 §2.6 的失败对照例）。
#              09-05 之前它走的是 transfer 的 off 段（只抬 2 cm，环没离开出生柱，终态 = 出生态），对照不成立。
#
# 变体参数来自 task 配置末尾的 variation 块，由 run.randomize_layout=true run.seed=<seed>
# 触发；demo 打印一行
#   ring_transfer variant seed=… on_post=… height=… radius=… head_overhang=… spacing=… heading=…
#     mid_x=… mid_y=… a_x=… a_y=… b_x=… b_y=… long_axis=… pinch_side=… pinch_along=… lift_low_z=… drop_z=…
# 本脚本解析它进汇总表。
#
# **成本**：FEM 闭合环。4090 实测（2026-08-26 固定布局）carry 全程 2016 步；估一格 5–10 min，
# visual ≈ 一半。十个 seed 的 oracle 约 1–1.5 h；lift_only 建议 SEEDS="0 1 2"。
# **默认无头。** VIEWER=1 可开窗。
#
# 用法：
#   bash bash_scripts/tests/ring_transfer_variation_sweep.sh visual oracle        # seed 0–9
#   SEEDS="0 1 2" bash bash_scripts/tests/ring_transfer_variation_sweep.sh lift_only
#   bash bash_scripts/tests/ring_transfer_variation_sweep.sh                     # 全部三组
#
# 可调环境变量：
#   SEEDS="0 1 2 3 4 5 6 7 8 9"
#   BACKEND=gpu
#   TIMEOUT_S=1500
#   VIEWER=0
#   OUTDIR=runs/ring_transfer_variation/<时间戳>
#   TOPOGYM_VENV=.venv-gs121
#
# 产出：<OUTDIR>/<group>_s<seed>.log、visual_s<seed>.mp4、summary.csv。
# 退出码：任一 oracle 格非 success=True，或任一格 RAISED/TIMEOUT，即非 0。
# lift_only 格不计入退出码。刻意不用 set -e。
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
TIMEOUT_S="${TIMEOUT_S:-1500}"
VIEWER="${VIEWER:-0}"
OUTDIR="${OUTDIR:-runs/ring_transfer_variation/$(date +%Y%m%d_%H%M%S)}"

VIEWER_ARGS=()
[[ "$VIEWER" == "1" ]] && VIEWER_ARGS=(run.viewer=true)

SUITES=(visual oracle lift_only)
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

# 离线门先过：变体块的包络、派生、拒绝率；环与柱的几何、carry 十五行、256 角点。约两分钟。
if ! python -B tests/check_variant_rng.py > "$OUTDIR/offline.log" 2>&1; then
  echo "[error] tests/check_variant_rng.py 未通过，见 $OUTDIR/offline.log" >&2
  exit 1
fi
if ! python -B tests/check_ring_transfer_geometry.py >> "$OUTDIR/offline.log" 2>&1; then
  echo "[error] tests/check_ring_transfer_geometry.py 未通过，见 $OUTDIR/offline.log" >&2
  exit 1
fi

FAIL=0
declare -A VARIANT ORACLE LIFTONLY VISUAL WINDING RATIO STEPS

run_state() {
  local code="$1" log="$2"
  if [[ "$code" == "124" ]]; then echo "TIMEOUT"; return; fi
  grep -qaiE "^Traceback" "$log" && { echo "RAISED"; return; }
  echo "ok"
}

variant_line() { grep -aF "ring_transfer variant seed=" "$1" | tail -1; }
result_line()  { grep -aF "ring_transfer result " "$1" | tail -1; }
field()        { grep -aoE "$2=[^ ]+" <<< "$1" | head -1 | sed "s/$2=//"; }
winding_of()   { grep -aoE "winding=\{[^}]*\}" <<< "$1" | head -1 | sed 's/winding=//; s/ //g'; }

run_cell() {
  local group="$1" seed="$2"; shift 2
  local tag="${group}_s${seed}" log="$OUTDIR/${group}_s${seed}.log"
  echo
  echo "==================== $tag ===================="
  local start; start=$(date +%s)
  local common=(python -B -m demos.routing.ring_transfer_physical_demo
                env.genesis.backend="$BACKEND" run.viewer=false "${VIEWER_ARGS[@]}"
                run.randomize_layout=true "run.seed=$seed")
  local cmd=()
  case "$group" in
    visual)
      cmd=("${common[@]}" run.motion=carry run.stop_after=clear
           recording=default "recording.path=$OUTDIR/visual_s${seed}.mp4" recording.camera=oblique) ;;
    oracle)
      cmd=("${common[@]}" run.motion=carry) ;;
    lift_only)
      cmd=("${common[@]}" run.motion=lift_only) ;;
  esac
  timeout "${TIMEOUT_S}s" "${cmd[@]}" "$@" 2>&1 | tee "$log"
  local code=${PIPESTATUS[0]}
  local dur=$(( $(date +%s) - start ))
  local state; state="$(run_state "$code" "$log")"
  local v; v="$(variant_line "$log")"
  [[ -n "$v" ]] && VARIANT[$seed]="${v#ring_transfer variant }"
  local r; r="$(result_line "$log")"

  local verdict=""
  case "$group" in
    visual)
      # stop_after=clear 以 exit 2 结束；只要没有 Traceback / 超时且录像非空就算过。
      if [[ "$state" == "ok" && -s "$OUTDIR/visual_s${seed}.mp4" ]]; then verdict="ok (看 mp4)"; else verdict="FAIL $state"; FAIL=1; fi
      VISUAL[$seed]="$verdict" ;;
    oracle)
      if [[ "$state" != "ok" ]]; then verdict="FAIL $state"; FAIL=1
      elif grep -qaF "success=True" <<< "$r"; then verdict="PASS"
      else verdict="FAIL enclosure=$(field "$r" enclosure) top_crossed=$(grep -aoE 'top_crossed=\{[^}]*\}' <<< "$r" | sed 's/ //g')"; FAIL=1; fi
      ORACLE[$seed]="$verdict"
      WINDING[$seed]="$(winding_of "$r")"
      RATIO[$seed]="$(field "$r" length_ratio)"
      STEPS[$seed]="$(field "$r" steps)" ;;
    lift_only)
      if [[ "$state" != "ok" ]]; then verdict="$state"
      elif grep -qaF "success=True" <<< "$r"; then verdict="success(!)"
      else verdict="failed enclosure=$(field "$r" enclosure)"; fi
      LIFTONLY[$seed]="$verdict" ;;
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
echo "seed,on_post,height,radius,head_overhang,spacing,heading,mid_x,mid_y,a_x,a_y,b_x,b_y,pinch_side,pinch_along,lift_low_z,drop_z,winding,length_ratio,steps,visual,oracle,lift_only" > "$csv"
n_ctrl=0; n_ctrl_failed=0
for seed in $SEEDS; do
  v="${VARIANT[$seed]:-}"
  f() { field "$v" "$1"; }
  printf '  seed %-3s on=%s h=%s r=%s oh=%s d=%s th=%s mid=(%s,%s) A=(%s,%s) B=(%s,%s) side=%s along=%s low=%s drop=%s | winding=%s ratio=%s steps=%s | visual=%s oracle=%s lift_only=%s\n' \
    "$seed" "$(f on_post)" "$(f height)" "$(f radius)" "$(f head_overhang)" "$(f spacing)" "$(f heading)" "$(f mid_x)" "$(f mid_y)" \
    "$(f a_x)" "$(f a_y)" "$(f b_x)" "$(f b_y)" "$(f pinch_side)" "$(f pinch_along)" "$(f lift_low_z)" "$(f drop_z)" \
    "${WINDING[$seed]:--}" "${RATIO[$seed]:--}" "${STEPS[$seed]:--}" \
    "${VISUAL[$seed]:--}" "${ORACLE[$seed]:--}" "${LIFTONLY[$seed]:--}"
  echo "$seed,$(f on_post),$(f height),$(f radius),$(f head_overhang),$(f spacing),$(f heading),$(f mid_x),$(f mid_y),$(f a_x),$(f a_y),$(f b_x),$(f b_y),$(f pinch_side),$(f pinch_along),$(f lift_low_z),$(f drop_z),${WINDING[$seed]:-},${RATIO[$seed]:-},${STEPS[$seed]:-},${VISUAL[$seed]:-},${ORACLE[$seed]:-},${LIFTONLY[$seed]:-}" >> "$csv"
  if [[ -n "${LIFTONLY[$seed]:-}" ]]; then
    n_ctrl=$((n_ctrl + 1)); [[ "${LIFTONLY[$seed]}" == failed* ]] && n_ctrl_failed=$((n_ctrl_failed + 1))
  fi
done
if [[ $n_ctrl -gt 0 ]]; then
  echo "  lift_only 判失败: $n_ctrl_failed / $n_ctrl（预期全部：环提离出生柱后终态 enclosure=[]）"
fi
echo
echo "怎么读："
echo "  visual    打开 $OUTDIR/visual_s*.mp4：两柱位置 / 柱距 / 朝向 / 柱高 / 粗细、环套在哪根柱上应逐 seed 不同，且无穿模。"
echo "  oracle    全部 PASS 才说明 oracle 覆盖了包络；FAIL 的 seed 看其 log 的 result 行（enclosure、top_crossed、"
echo "            min_gap_mm）与 variant 行（柱最高 / 最粗、柱距最远、朝向 ±30 的格最可能出问题）；length_ratio 是"
echo "            终态弧长 / 出生周长（拉伸证据）。"
echo "  lift_only 应全部 failed；success(!) 说明只提离也判成功，判据有问题。"
echo "summary: $csv"
echo "日志: $OUTDIR"
exit $FAIL
