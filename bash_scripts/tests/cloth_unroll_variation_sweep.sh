#!/usr/bin/env bash
# ============================================================================
# cloth_unroll 变体生成实验（variation_axes_plain_zh.md §6.2 第 9 步）。
#
# 每个 seed 两格：
#   oracle   physical demo 全程（run.motion=unroll）：抓平铺段的自由端、贴桌面沿拉动方向拖到卷筒放空、松手
#            → 必须 unrolled=True 且 diverged=False。同时录斜视机位 visual_s<seed>.mp4：
#            支架位置、圈数、支架在 −y 还是 +y 侧（pull_side 镜像）应逐 seed 不同。
#            PBD 布一格便宜，所以不单设 visual 组，视频就是 oracle 格的副产品。
#   shove    对照组：run.motion=shove，朝横梁推、走满可用余量 → 只记录；预期 unrolled=False
#            （回收比 ≈ 0：布堆起来，卷筒一点没放料）。
#
# 变体参数来自 task 配置末尾的 variation 块，由 run.randomize_layout=true run.seed=<seed>
# 触发；demo 打印一行
#   cloth_unroll variant seed=… side=… turns=… pitch=… bar_height=… center_x=… center_y=… spread_max=…
#     flat_mm=… pull_mm=… grasp_y=… end_y=…
# 与一行 `cloth_unroll checks …`（十行可行性判据读数）。本脚本解析 variant 行进汇总表。
#
# **成本**：PBD 布约 1000 步、2500 粒子；1.2 那条布带实测一格 19–29 s，本任务行程长一倍，
# 预期半分钟级。首格跑完把耗时写回这里。**默认无头。** VIEWER=1 可开窗。
#
# 用法：
#   bash bash_scripts/tests/cloth_unroll_variation_sweep.sh oracle          # seed 0–9
#   SEEDS="0 1 2" bash bash_scripts/tests/cloth_unroll_variation_sweep.sh shove
#   SEEDS="0 1 2" bash bash_scripts/tests/cloth_unroll_variation_sweep.sh overpull   # 扯断对照
#   bash bash_scripts/tests/cloth_unroll_variation_sweep.sh                 # 三组
#
# 可调环境变量：
#   SEEDS="0 1 2 3 4 5 6 7 8 9"
#   BACKEND=gpu
#   TIMEOUT_S=1200
#   VIEWER=0
#   OUTDIR=runs/cloth_unroll_variation/<时间戳>
#   TOPOGYM_VENV=.venv-gs121
#
# 产出：<OUTDIR>/<group>_s<seed>.log、visual_s<seed>.mp4、summary.csv。
# 退出码：任一 oracle 格非 unrolled=True，或任一格 RAISED/TIMEOUT，即非 0。
# shove 格不计入退出码。刻意不用 set -e。
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
OUTDIR="${OUTDIR:-runs/cloth_unroll_variation/$(date +%Y%m%d_%H%M%S)}"

VIEWER_ARGS=()
[[ "$VIEWER" == "1" ]] && VIEWER_ARGS=(run.viewer=true)

SUITES=(oracle shove overpull)
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

# 离线门先过：变体块的包络、派生、拒绝率；判据两侧、96 角点十行。约一分钟。
if ! python -B tests/check_variant_rng.py > "$OUTDIR/offline.log" 2>&1; then
  echo "[error] tests/check_variant_rng.py 未通过，见 $OUTDIR/offline.log" >&2
  exit 1
fi
if ! python -B tests/check_cloth_unroll_geometry.py >> "$OUTDIR/offline.log" 2>&1; then
  echo "[error] tests/check_cloth_unroll_geometry.py 未通过，见 $OUTDIR/offline.log" >&2
  exit 1
fi

FAIL=0
declare -A VARIANT ORACLE SHOVE OVER SINGLE RECOVERED ONBAR OVERPULL TAILGAP TORN

run_state() {
  local code="$1" log="$2"
  if [[ "$code" == "124" ]]; then echo "TIMEOUT"; return; fi
  grep -qaiE "^Traceback" "$log" && { echo "RAISED"; return; }
  echo "ok"
}

variant_line() { grep -aF "cloth_unroll variant seed=" "$1" | tail -1; }
result_line()  { grep -aF "cloth_unroll result" "$1" | tail -1; }
field()        { grep -aoE "$2=[^ ]+" <<< "$1" | head -1 | sed "s/$2=//"; }

run_cell() {
  local group="$1" seed="$2"; shift 2
  local tag="${group}_s${seed}" log="$OUTDIR/${group}_s${seed}.log"
  echo
  echo "==================== $tag ===================="
  local start; start=$(date +%s)
  local common=(python -B -m demos.deformation.cloth_unroll_physical_demo
                env.genesis.backend="$BACKEND" run.viewer=false "${VIEWER_ARGS[@]}"
                run.randomize_layout=true "run.seed=$seed")
  local cmd=()
  case "$group" in
    oracle)
      cmd=("${common[@]}" run.motion=unroll
           recording=default "recording.path=$OUTDIR/visual_s${seed}.mp4" recording.camera=oblique) ;;
    shove)
      cmd=("${common[@]}" run.motion=shove) ;;
    overpull)
      cmd=("${common[@]}" run.motion=overpull) ;;
  esac
  timeout "${TIMEOUT_S}s" "${cmd[@]}" "$@" 2>&1 | tee "$log"
  local code=${PIPESTATUS[0]}
  local dur=$(( $(date +%s) - start ))
  local state; state="$(run_state "$code" "$log")"
  local v; v="$(variant_line "$log")"
  [[ -n "$v" ]] && VARIANT[$seed]="${v#cloth_unroll variant }"
  local r; r="$(result_line "$log")"

  local verdict=""
  case "$group" in
    oracle)
      if [[ "$state" != "ok" ]]; then verdict="FAIL $state"; FAIL=1
      elif grep -qaF "unrolled=True" <<< "$r" && grep -qaF "diverged=False" <<< "$r" && ! grep -qaF "torn=True" <<< "$r"; then verdict="PASS"
      elif grep -qaF "aborted reason=" "$log"; then verdict="FAIL $(grep -aoE 'aborted reason=[a-z_]+' "$log" | tail -1 | sed 's/aborted reason=//')"; FAIL=1
      else verdict="FAIL gates=$(field "$r" gates) diverged=$(field "$r" diverged)"; FAIL=1; fi
      ORACLE[$seed]="$verdict"
      SINGLE[$seed]="$(field "$r" single_layer_frac)"
      RECOVERED[$seed]="$(field "$r" recovered_frac)"
      ONBAR[$seed]="$(field "$r" on_bar)"
      TORN[$seed]="$(field "$r" torn)"
      OVERPULL[$seed]="$(field "$r" over_pull_mm)"
      TAILGAP[$seed]="$(field "$r" tail_gap_mm)" ;;
    shove)
      if [[ "$state" != "ok" ]]; then verdict="$state"
      elif grep -qaF "unrolled=True" <<< "$r"; then verdict="success(!)"
      else verdict="failed recovered=$(field "$r" recovered_frac)"; fi
      SHOVE[$seed]="$verdict" ;;
    overpull)
      if [[ "$state" != "ok" ]]; then verdict="$state"
      elif grep -qaF "unrolled=True" <<< "$r"; then verdict="success(!)"
      elif grep -qaF "torn=True" <<< "$r"; then verdict="failed torn over_pull=$(field "$r" over_pull_mm)"
      else verdict="failed not_torn gates=$(field "$r" gates)"; fi
      OVER[$seed]="$verdict" ;;
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
echo "seed,side,turns,pitch,bar_height,center_x,center_y,spread_max,flat_mm,pull_mm,grasp_y,end_y,single_layer_frac,recovered_frac,on_bar,torn,over_pull_mm,tail_gap_mm,oracle,shove,overpull" > "$csv"
n_shove=0; n_shove_failed=0
for seed in $SEEDS; do
  v="${VARIANT[$seed]:-}"
  f() { field "$v" "$1"; }
  printf '  seed %-3s side=%s turns=%s pitch=%s bar_h=%s center=(%s,%s) spread_max=%s flat=%s pull=%s grasp_y=%s end_y=%s | single=%s recovered=%s on_bar=%s torn=%s over_pull=%s tail_gap=%s | oracle=%s shove=%s overpull=%s\n' \
    "$seed" "$(f side)" "$(f turns)" "$(f pitch)" "$(f bar_height)" "$(f center_x)" "$(f center_y)" "$(f spread_max)" \
    "$(f flat_mm)" "$(f pull_mm)" "$(f grasp_y)" "$(f end_y)" \
    "${SINGLE[$seed]:--}" "${RECOVERED[$seed]:--}" "${ONBAR[$seed]:--}" "${TORN[$seed]:--}" "${OVERPULL[$seed]:--}" "${TAILGAP[$seed]:--}" \
    "${ORACLE[$seed]:--}" "${SHOVE[$seed]:--}" "${OVER[$seed]:--}"
  echo "$seed,$(f side),$(f turns),$(f pitch),$(f bar_height),$(f center_x),$(f center_y),$(f spread_max),$(f flat_mm),$(f pull_mm),$(f grasp_y),$(f end_y),${SINGLE[$seed]:-},${RECOVERED[$seed]:-},${ONBAR[$seed]:-},${TORN[$seed]:-},${OVERPULL[$seed]:-},${TAILGAP[$seed]:-},$(csv_field "${ORACLE[$seed]:-}"),$(csv_field "${SHOVE[$seed]:-}"),$(csv_field "${OVER[$seed]:-}")" >> "$csv"
  if [[ -n "${SHOVE[$seed]:-}" ]]; then
    n_shove=$((n_shove + 1)); [[ "${SHOVE[$seed]}" == failed* ]] && n_shove_failed=$((n_shove_failed + 1))
  fi
done
if [[ $n_shove -gt 0 ]]; then
  echo "  shove 判失败: $n_shove_failed / $n_shove（预期全部：朝横梁推不放料，回收比 ≈ 0）"
fi
n_over=0; n_over_torn=0
for seed in $SEEDS; do
  if [[ -n "${OVER[$seed]:-}" ]]; then
    n_over=$((n_over + 1)); [[ "${OVER[$seed]}" == "failed torn"* ]] && n_over_torn=$((n_over_torn + 1))
  fi
done
if [[ $n_over -gt 0 ]]; then
  echo "  overpull 扯断判失败: $n_over_torn / $n_over（预期全部：多拉 1.6 倍，胶水断、尾端离辊）"
fi
echo
echo "怎么读："
echo "  oracle   全部 PASS 才说明 oracle 覆盖了包络；FAIL 的 seed 看其 log 的 result 行（gates、attach_error_mm、"
echo "           arm_pos_err_mm）与 variant 行（side=−1、center_x 大、end_y 接近可达门、1 圈松卷的格最可能出问题）；"
echo "           aborted reason=material_already_released / layers_came_apart 是起始态守卫，卷在静置时自己散了。"
echo "  视频     打开 $OUTDIR/visual_s*.mp4：支架位置、圈数、支架在哪一侧应逐 seed 不同，且无穿模。"
echo "  shove    应全部 failed；success(!) 说明朝横梁推也判成功，判据有问题。"
echo "  overpull 应全部 failed torn；not_torn 说明 tear_allowance 太大，success(!) 说明判据没读尾端。"
echo "summary: $csv"
echo "日志: $OUTDIR"
exit $FAIL
