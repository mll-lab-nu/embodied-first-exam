#!/usr/bin/env bash
# ============================================================================
# cloth_fold 变体生成实验（variation_axes_plain_zh.md §6.2 第 11 步）。
#
# 每个 seed 三格：
#   oracle        physical demo 全程（run.motion=fold）：抓指令说的那个角、绕对角线转半圈放到对角、松手
#                 → 必须 folded=True 且 diverged=False。同时录斜视机位 visual_s<seed>.mp4：
#                 布的位置、抓哪个角、捏取点离角尖多远应逐 seed 不同。
#                 PBD 布一格便宜，所以不单设 visual 组，视频就是 oracle 格的副产品。
#   drag          对照组：run.motion=drag，同一条弧线的俯视投影、手全程贴桌面不抬 → 只记录；
#                 预期 folded=False（两层率 ≈ 0.2：布被推皱而不是折起来）。
#   fixed_corner  对照组：run.motion=fixed_corner，无视指令永远折 far_left → 只记录；
#                 预期只有抽到 corner=far_left 的 seed 成功（约 1/4），其余每个粒子都不在指令的目标位。
#   fixed_fold    对照组：run.motion=fixed_fold，无视指令的折痕位置永远角对角折 → 只记录；
#                 预期只有抽到 fold_fraction=1.0 的 seed 成功（约 1/3）。这两条对照各打指令里的
#                 一个量：一个是抓哪个角，一个是折到哪。
#
# 变体参数来自 task 配置末尾的 variation 块，由 run.randomize_layout=true run.seed=<seed>
# 触发；demo 打印一行
#   cloth_fold variant seed=… corner=… fold_fraction=… center_x=… center_y=… slack=… material_mm=…
#     radius_mm=… steps=… grasp_x=… grasp_y=… target_x=… target_y=… far_reach=…
# 与一行 `cloth_fold checks …`（四行可行性判据读数）。本脚本解析 variant 行进汇总表。
#
# **成本**：PBD 布约 4225 粒子、每格约 600 步；cloth_unpleat 实测一格 14–29 s，本任务预期 20–40 s。
# 首格跑完把耗时写回这里。**默认无头。** VIEWER=1 可开窗。
#
# 用法：
#   bash bash_scripts/tests/cloth_fold_variation_sweep.sh oracle          # seed 0–9
#   SEEDS="0 1 2" bash bash_scripts/tests/cloth_fold_variation_sweep.sh drag
#   bash bash_scripts/tests/cloth_fold_variation_sweep.sh                 # 三组
#
# 可调环境变量：
#   SEEDS="0 1 2 3 4 5 6 7 8 9"
#   BACKEND=gpu
#   TIMEOUT_S=1200
#   VIEWER=0
#   OUTDIR=runs/cloth_fold_variation/<时间戳>
#   TOPOGYM_VENV=.venv-gs121
#
# 产出：<OUTDIR>/<group>_s<seed>.log、visual_s<seed>.mp4、summary.csv。
# 退出码：任一 oracle 格非 folded=True，或任一格 RAISED/TIMEOUT，即非 0。
# drag / fixed_corner 格不计入退出码。刻意不用 set -e。
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
TIMEOUT_S="${TIMEOUT_S:-1200}"
VIEWER="${VIEWER:-0}"
OUTDIR="${OUTDIR:-runs/cloth_fold_variation/$(date +%Y%m%d_%H%M%S)}"

VIEWER_ARGS=()
[[ "$VIEWER" == "1" ]] && VIEWER_ARGS=(run.viewer=true)

SUITES=(oracle drag fixed_corner fixed_fold)
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

# 离线门先过：变体块的包络、派生、拒绝率；判据两侧、96 角点五行。约一分钟。
if ! python -B tests/check_variant_rng.py > "$OUTDIR/offline.log" 2>&1; then
  echo "[error] tests/check_variant_rng.py 未通过，见 $OUTDIR/offline.log" >&2
  exit 1
fi
if ! python -B tests/check_cloth_fold_geometry.py >> "$OUTDIR/offline.log" 2>&1; then
  echo "[error] tests/check_cloth_fold_geometry.py 未通过，见 $OUTDIR/offline.log" >&2
  exit 1
fi

FAIL=0
declare -A VARIANT ORACLE DRAG FIXED FIXEDFOLD ERRMM TWOLAYER OFFFRAC

run_state() {
  local code="$1" log="$2"
  if [[ "$code" == "124" ]]; then echo "TIMEOUT"; return; fi
  grep -qaiE "^Traceback" "$log" && { echo "RAISED"; return; }
  echo "ok"
}

variant_line() { grep -aF "cloth_fold variant seed=" "$1" | tail -1; }
result_line()  { grep -aF "cloth_fold result" "$1" | tail -1; }
field()        { grep -aoE "$2=[^ ]+" <<< "$1" | head -1 | sed "s/$2=//"; }

run_cell() {
  local group="$1" seed="$2"; shift 2
  local tag="${group}_s${seed}" log="$OUTDIR/${group}_s${seed}.log"
  echo
  echo "==================== $tag ===================="
  local start; start=$(date +%s)
  local common=(python -B -m demos.deformation.cloth_fold_physical_demo
                env.genesis.backend="$BACKEND" run.viewer=false "${VIEWER_ARGS[@]}"
                run.randomize_layout=true "run.seed=$seed")
  local cmd=()
  case "$group" in
    oracle)
      cmd=("${common[@]}" run.motion=fold
           recording=default "recording.path=$OUTDIR/visual_s${seed}.mp4" recording.camera=oblique) ;;
    drag)
      cmd=("${common[@]}" run.motion=drag) ;;
    fixed_corner)
      cmd=("${common[@]}" run.motion=fixed_corner) ;;
    fixed_fold)
      cmd=("${common[@]}" run.motion=fixed_fold) ;;
  esac
  timeout "${TIMEOUT_S}s" "${cmd[@]}" "$@" 2>&1 | tee "$log"
  local code=${PIPESTATUS[0]}
  local dur=$(( $(date +%s) - start ))
  local state; state="$(run_state "$code" "$log")"
  local v; v="$(variant_line "$log")"
  [[ -n "$v" ]] && VARIANT[$seed]="${v#cloth_fold variant }"
  local r; r="$(result_line "$log")"

  local verdict=""
  case "$group" in
    oracle)
      if [[ "$state" != "ok" ]]; then verdict="FAIL $state"; FAIL=1
      elif grep -qaF "folded=True" <<< "$r" && grep -qaF "diverged=False" <<< "$r"; then verdict="PASS"
      else verdict="FAIL gates=$(field "$r" gates) diverged=$(field "$r" diverged)"; FAIL=1; fi
      ORACLE[$seed]="$verdict"
      ERRMM[$seed]="$(field "$r" particle_err_mean_mm)"
      OFFFRAC[$seed]="$(field "$r" off_target_frac)"
      TWOLAYER[$seed]="$(field "$r" two_layer_frac)" ;;
    drag)
      if [[ "$state" != "ok" ]]; then verdict="$state"
      elif grep -qaF "folded=True" <<< "$r"; then verdict="success(!)"
      else verdict="failed two_layer=$(field "$r" two_layer_frac)"; fi
      DRAG[$seed]="$verdict" ;;
    fixed_corner)
      if [[ "$state" != "ok" ]]; then verdict="$state"
      elif grep -qaF "folded=True" <<< "$r"; then verdict="success"
      else verdict="failed err_mm=$(field "$r" particle_err_mean_mm)"; fi
      FIXED[$seed]="$verdict" ;;
    fixed_fold)
      if [[ "$state" != "ok" ]]; then verdict="$state"
      elif grep -qaF "folded=True" <<< "$r"; then verdict="success"
      else verdict="failed err_mm=$(field "$r" particle_err_mean_mm)"; fi
      FIXEDFOLD[$seed]="$verdict" ;;
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
# CSV 字段按 RFC 4180 加引号。判定器的 `gates=` 在多条门同时挂时是逗号连接的，
# 不加引号会让那一行多出几列、按列解析的读者读到错位的值（2026-09-08）。
csv_field() { printf '"%s"' "${1//\"/\"\"}"; }
echo "seed,corner,fold_fraction,center_x,center_y,slack,material_mm,radius_mm,steps,far_reach,particle_err_mean_mm,off_target_frac,two_layer_frac,oracle,drag,fixed_corner,fixed_fold" > "$csv"
n_drag=0; n_drag_failed=0; n_fixed=0; n_fixed_ok=0; n_fixed_far_left=0
n_ff=0; n_ff_ok=0; n_ff_full=0
for seed in $SEEDS; do
  v="${VARIANT[$seed]:-}"
  f() { field "$v" "$1"; }
  printf '  seed %-3s corner=%-10s fold=%s center=(%s,%s) slack=%s material=%s radius=%s steps=%s far_reach=%s | err=%s off=%s two_layer=%s | oracle=%s drag=%s fixed_corner=%s fixed_fold=%s\n' \
    "$seed" "$(f corner)" "$(f fold_fraction)" "$(f center_x)" "$(f center_y)" "$(f slack)" \
    "$(f material_mm)" "$(f radius_mm)" "$(f steps)" "$(f far_reach)" \
    "${ERRMM[$seed]:--}" "${OFFFRAC[$seed]:--}" "${TWOLAYER[$seed]:--}" \
    "${ORACLE[$seed]:--}" "${DRAG[$seed]:--}" "${FIXED[$seed]:--}" "${FIXEDFOLD[$seed]:--}"
  echo "$seed,$(f corner),$(f fold_fraction),$(f center_x),$(f center_y),$(f slack),$(f material_mm),$(f radius_mm),$(f steps),$(f far_reach),${ERRMM[$seed]:-},${OFFFRAC[$seed]:-},${TWOLAYER[$seed]:-},$(csv_field "${ORACLE[$seed]:-}"),$(csv_field "${DRAG[$seed]:-}"),$(csv_field "${FIXED[$seed]:-}"),$(csv_field "${FIXEDFOLD[$seed]:-}")" >> "$csv"
  if [[ -n "${DRAG[$seed]:-}" ]]; then
    n_drag=$((n_drag + 1)); [[ "${DRAG[$seed]}" == failed* ]] && n_drag_failed=$((n_drag_failed + 1))
  fi
  if [[ -n "${FIXED[$seed]:-}" ]]; then
    n_fixed=$((n_fixed + 1)); [[ "${FIXED[$seed]}" == success ]] && n_fixed_ok=$((n_fixed_ok + 1))
    [[ "$(f corner)" == "far_left" ]] && n_fixed_far_left=$((n_fixed_far_left + 1))
  fi
  if [[ -n "${FIXEDFOLD[$seed]:-}" ]]; then
    n_ff=$((n_ff + 1)); [[ "${FIXEDFOLD[$seed]}" == success ]] && n_ff_ok=$((n_ff_ok + 1))
    [[ "$(f fold_fraction)" == "1.00" ]] && n_ff_full=$((n_ff_full + 1))
  fi
done
if [[ $n_drag -gt 0 ]]; then
  echo "  drag 判失败: $n_drag_failed / $n_drag（预期全部：贴桌面拖只推皱布，两层率 ≈ 0.2）"
fi
if [[ $n_fixed -gt 0 ]]; then
  echo "  fixed_corner 成功: $n_fixed_ok / $n_fixed（预期 = 抽到 far_left 的 seed 数 $n_fixed_far_left：无视指令只在指令恰好是 far_left 时对）"
fi
if [[ $n_ff -gt 0 ]]; then
  echo "  fixed_fold 成功: $n_ff_ok / $n_ff（预期 = 抽到 fold_fraction=1.00 的 seed 数 $n_ff_full：无视折痕位置只在指令恰好是角对角时对）"
fi
echo
echo "怎么读："
echo "  oracle   全部 PASS 才说明 oracle 覆盖了包络；FAIL 的 seed 看其 log 的 result 行（gates、attach_error_mm、"
echo "           arm_pos_err_mm、arm_tilt_deg）与 variant 行（near_* 角、far_reach 接近 0.740 的格最可能出问题）。"
echo "           另看 oracle 成功率是否随 fold_fraction 单调递减 —— 这是这条轴能不能当难度统计量的判据。"
echo "  视频     打开 $OUTDIR/visual_s*.mp4：布的位置、抓哪个角、折到多远应逐 seed 不同，且无穿模。"
echo "  drag     应全部 failed；success(!) 说明贴桌面拖也判成功，判据有问题。"
echo "  fixed_corner  成功数应等于抽到 far_left 的 seed 数；多出来的 success 说明折错角也判成功，判据有问题。"
echo "  fixed_fold    成功数应等于抽到 fold_fraction=1.00 的 seed 数；多出来的 success 说明折错距离也判成功，判据有问题。"
echo "summary: $csv"
echo "日志: $OUTDIR"
exit $FAIL
