#!/usr/bin/env bash
# ============================================================================
# rope_unwinding 变体生成实验（variation_axes_plain_zh.md §6.2 第 7 步）。
#
# 每个 seed 三格：
#   visual     physical demo 只走第一个航点（run.max_waypoints=1：抓插头、抬起就停），录像 →
#              人眼看 visual_s<seed>.mp4：柱 / 端子 / 靶心位置、圈数、缠绕方向（cw 是镜像布局）、
#              圈距是否逐 seed 不同，有无穿模。没有 inspect demo，所以走 physical demo。
#   oracle     physical demo 全程：反向环绕 start_turns 圈解到 0、放到 C → 必须 task_success=True。
#              这是「oracle 在包络内每个变体都可解」的直接证据。
#   wrong_way  对照组：task.winding.orbit_direction=same，轨道与缠绕同向 → 只记录；预期
#              task_success=False 且 winding_number=±2·start_turns（任务书 §2.5 的失败对照例）。
#
# 变体参数来自 task 配置末尾的 variation 块，由 run.randomize_layout=true run.seed=<seed>
# 触发；demo 打印一行
#   rope_unwinding variant seed=… start_turns=… direction=… post_x=… post_y=… s_x=… s_y=…
#     c_x=… c_y=… climb=… wind_z_start=… plug_x=… plug_y=… slack=… detour=… waypoints=…
# 本脚本解析它进汇总表。位置是物理位置（cw 格已镜像）。
#
# **成本**：FEM 绳。4090 实测（2026-08-27）start_turns 1 / 2 / 3 一格 ≈ 8 / 13 / 18 min；
# visual ≈ 2 min。十个 seed 的 oracle 约 2 h；wrong_way 建议 SEEDS="0 1 2"。
# **默认无头。** VIEWER=1 可开窗。
#
# 用法：
#   bash bash_scripts/tests/rope_unwinding_variation_sweep.sh visual oracle        # seed 0–9
#   SEEDS="0 1 2" bash bash_scripts/tests/rope_unwinding_variation_sweep.sh wrong_way
#   bash bash_scripts/tests/rope_unwinding_variation_sweep.sh                     # 全部三组
#
# 可调环境变量：
#   SEEDS="0 1 2 3 4 5 6 7 8 9"
#   BACKEND=gpu
#   TIMEOUT_S=2400
#   VIEWER=0
#   OUTDIR=runs/rope_unwinding_variation/<时间戳>
#   TOPOGYM_VENV=.venv-gs121
#
# 产出：<OUTDIR>/<group>_s<seed>.log、visual_s<seed>.mp4、summary.csv。
# 退出码：任一 oracle 格非 task_success=True，或任一格 RAISED/TIMEOUT，即非 0。
# wrong_way 格不计入退出码。刻意不用 set -e。
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
TIMEOUT_S="${TIMEOUT_S:-2400}"
VIEWER="${VIEWER:-0}"
OUTDIR="${OUTDIR:-runs/rope_unwinding_variation/$(date +%Y%m%d_%H%M%S)}"

VIEWER_ARGS=()
[[ "$VIEWER" == "1" ]] && VIEWER_ARGS=(run.viewer=true)

SUITES=(visual oracle wrong_way)
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

# 离线门先过：变体块的包络、派生、拒绝率；出生螺旋、oracle、拓扑、1536 角点。约两分钟。
if ! python -B tests/check_variant_rng.py > "$OUTDIR/offline.log" 2>&1; then
  echo "[error] tests/check_variant_rng.py 未通过，见 $OUTDIR/offline.log" >&2
  exit 1
fi
if ! python -B tests/check_rope_unwinding_geometry.py >> "$OUTDIR/offline.log" 2>&1; then
  echo "[error] tests/check_rope_unwinding_geometry.py 未通过，见 $OUTDIR/offline.log" >&2
  exit 1
fi

FAIL=0
declare -A VARIANT ORACLE WRONG VISUAL WINDING PLACE CONTACT

run_state() {
  local code="$1" log="$2"
  if [[ "$code" == "124" ]]; then echo "TIMEOUT"; return; fi
  grep -qaiE "^Traceback" "$log" && { echo "RAISED"; return; }
  echo "ok"
}

variant_line() { grep -aF "rope_unwinding variant seed=" "$1" | tail -1; }
result_line()  { grep -aF "rope_winding_physical_handle_demo result" "$1" | tail -1; }
field()        { grep -aoE "$2=[^ ]+" <<< "$1" | head -1 | sed "s/$2=//"; }

run_cell() {
  local group="$1" seed="$2"; shift 2
  local tag="${group}_s${seed}" log="$OUTDIR/${group}_s${seed}.log"
  echo
  echo "==================== $tag ===================="
  local start; start=$(date +%s)
  local common=(python -B -m demos.routing.rope_unwinding_physical_handle_demo
                env.genesis.backend="$BACKEND" run.viewer=false "${VIEWER_ARGS[@]}"
                run.randomize_layout=true "run.seed=$seed")
  local cmd=()
  case "$group" in
    visual)
      cmd=("${common[@]}" run.max_waypoints=1
           recording=default "recording.path=$OUTDIR/visual_s${seed}.mp4" recording.camera=oblique) ;;
    oracle)
      cmd=("${common[@]}") ;;
    wrong_way)
      cmd=("${common[@]}" task.winding.orbit_direction=same) ;;
  esac
  timeout "${TIMEOUT_S}s" "${cmd[@]}" "$@" 2>&1 | tee "$log"
  local code=${PIPESTATUS[0]}
  local dur=$(( $(date +%s) - start ))
  local state; state="$(run_state "$code" "$log")"
  local v; v="$(variant_line "$log")"
  [[ -n "$v" ]] && VARIANT[$seed]="${v#rope_unwinding variant }"
  local r; r="$(result_line "$log")"

  local verdict=""
  case "$group" in
    visual)
      if [[ "$state" == "ok" && -s "$OUTDIR/visual_s${seed}.mp4" ]]; then verdict="ok (看 mp4)"; else verdict="FAIL $state"; FAIL=1; fi
      VISUAL[$seed]="$verdict" ;;
    oracle)
      if [[ "$state" != "ok" ]]; then verdict="FAIL $state"; FAIL=1
      elif grep -qaF "task_success=True" <<< "$r"; then verdict="PASS"
      else verdict="FAIL $(field "$r" failure_reason)"; FAIL=1; fi
      ORACLE[$seed]="$verdict"
      WINDING[$seed]="$(grep -a 'rope_winding_verify' "$log" | tail -1 | grep -aoE 'winding_number=[^ ]+' | sed 's/winding_number=//')"
      PLACE[$seed]="$(field "$r" placement_error_xy)"
      CONTACT[$seed]="$(grep -aoE 'contact_nodes=[0-9]+' "$log" | tail -1 | sed 's/contact_nodes=//')" ;;
    wrong_way)
      # 同向轨道把绳越缠越多：多数格在第二圈被 post_contact 守卫中止（贴柱数超过出生值的
      # safety_contact_growth 倍），此时没有 verify 行，读数取最后一次 turn_complete 的闭合计数。
      local w; w="$(grep -a 'rope_winding_verify' "$log" | tail -1 | grep -aoE 'winding_number=[^ ]+' | sed 's/winding_number=//')"
      [[ -z "$w" ]] && w="$(grep -a 'turn_complete' "$log" | tail -1 | grep -aoE 'winding_topological=[^ ]+' | sed 's/winding_topological=//')"
      if [[ "$state" != "ok" ]]; then verdict="$state"
      elif grep -qaF "task_success=True" <<< "$r"; then verdict="success(!)"
      elif grep -qaF "post_contact_safety_abort" "$log"; then verdict="failed abort winding=$w"
      else verdict="failed winding=$w"; fi
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
# CSV 字段按 RFC 4180 加引号。判定器的 `gates=` 在多条门同时挂时是逗号连接的，
# 不加引号会让那一行多出几列、按列解析的读者读到错位的值（2026-09-08）。
csv_field() { printf '"%s"' "${1//\"/\"\"}"; }
echo "seed,start_turns,direction,post_x,post_y,s_x,s_y,c_x,c_y,climb,wind_z_start,plug_x,plug_y,slack,detour,waypoints,winding,placement_xy,contact_nodes,visual,oracle,wrong_way" > "$csv"
n_wrong=0; n_wrong_failed=0
for seed in $SEEDS; do
  v="${VARIANT[$seed]:-}"
  f() { field "$v" "$1"; }
  printf '  seed %-3s T=%-2s %-4s post=(%s,%s) S=(%s,%s) C=(%s,%s) climb=%s wz=%s plug=(%s,%s) slack=%s detour=%s wp=%s | winding=%s place=%s contact=%s | visual=%s oracle=%s wrong_way=%s\n' \
    "$seed" "$(f start_turns)" "$(f direction)" "$(f post_x)" "$(f post_y)" "$(f s_x)" "$(f s_y)" "$(f c_x)" "$(f c_y)" \
    "$(f climb)" "$(f wind_z_start)" "$(f plug_x)" "$(f plug_y)" "$(f slack)" "$(f detour)" "$(f waypoints)" \
    "${WINDING[$seed]:--}" "${PLACE[$seed]:--}" "${CONTACT[$seed]:--}" \
    "${VISUAL[$seed]:--}" "${ORACLE[$seed]:--}" "${WRONG[$seed]:--}"
  echo "$seed,$(f start_turns),$(f direction),$(f post_x),$(f post_y),$(f s_x),$(f s_y),$(f c_x),$(f c_y),$(f climb),$(f wind_z_start),$(f plug_x),$(f plug_y),$(f slack),$(f detour),$(f waypoints),${WINDING[$seed]:-},${PLACE[$seed]:-},${CONTACT[$seed]:-},$(csv_field "${VISUAL[$seed]:-}"),$(csv_field "${ORACLE[$seed]:-}"),$(csv_field "${WRONG[$seed]:-}")" >> "$csv"
  if [[ -n "${WRONG[$seed]:-}" ]]; then
    n_wrong=$((n_wrong + 1)); [[ "${WRONG[$seed]}" == failed* ]] && n_wrong_failed=$((n_wrong_failed + 1))
  fi
done
if [[ $n_wrong -gt 0 ]]; then
  echo "  wrong_way 判失败: $n_wrong_failed / $n_wrong（预期全部：同向轨道读 ±2·start_turns）"
fi
echo
echo "怎么读："
echo "  visual    打开 $OUTDIR/visual_s*.mp4：柱 / 端子 / 靶心位置、圈数、方向（cw 为镜像）应逐 seed 不同，且无穿模。"
echo "  oracle    全部 PASS 才说明 oracle 覆盖了包络；FAIL 的 seed 看其 log 的 result 行（failure_reason、"
echo "            completed_waypoints）与 variant 行（cw、detour=1、post_x 大的格最可能出问题）；contact_nodes 是"
echo "            终态柱面接触粒子数（解下的绳堆在柱脚时会高）。"
echo "  wrong_way 应全部 failed；success(!) 说明同向轨道也判成功，判据有问题。"
echo "summary: $csv"
echo "日志: $OUTDIR"
exit $FAIL
