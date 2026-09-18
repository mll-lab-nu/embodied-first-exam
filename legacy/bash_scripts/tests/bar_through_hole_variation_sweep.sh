#!/usr/bin/env bash
# ============================================================================
# bar_through_hole 变体生成实验（variation_axes_plain_zh.md §6.2 第 12 步）。
#
# 每个 seed 三格：
#   visual    physical demo 的 run.inspect_only=true：建场景、home 位静置、录几帧 →
#             人眼看 visual_s<seed>.mp4：孔径、杆与面板的位置、杆长、抓点是否逐 seed 不同，有无穿模。
#             任务没有单独的 inspect demo，inspect_only 就是它的静态检查路径。
#   oracle    physical demo，run.oracle_mode=insert（抓杆 → 抬升 → 手腕对准 → 横推穿孔 → 落座）
#             → 必须 success=True。这是「oracle 在包络内每个变体都可解」的直接证据。
#   bypass    physical demo，防捷径对照：同样的起止 xy、搬运高度抬到面板顶之上 → 杆落在面板顶上，
#             threading_count = 0 → 只记录；预期 success=False。
#
# 变体参数来自 task 配置末尾的 variation 块，由 run.randomize_layout=true run.seed=<seed>
# 触发；demo 打印一行
#   bar_through_hole variant seed=… af=… rest_x=… rest_y=… panel_x=… length=… grasp_off=…
#     side_clear=… window=… push_z=…
# 本脚本解析它进汇总表，另抓 result 行的 align_tilt（手腕对准后的残差，门 1.0°）与
# finger_qpos（合爪后指位；physical.min_finger_qpos 的阈值要从这一列回填）。
#
# **成本**：纯刚体。一格 10–60 s；十个 seed 三组全跑约 15 min。
# **默认无头。** VIEWER=1 可开窗，但不加 run.keep_open。
#
# 用法：
#   bash bash_scripts/tests/bar_through_hole_variation_sweep.sh visual oracle          # seed 0–9
#   SEEDS="0 1 2" bash bash_scripts/tests/bar_through_hole_variation_sweep.sh bypass
#   bash bash_scripts/tests/bar_through_hole_variation_sweep.sh                       # 全部三组
#
# 可调环境变量：
#   SEEDS="0 1 2 3 4 5 6 7 8 9"
#   BACKEND=gpu
#   TIMEOUT_S=900
#   VIEWER=0
#   OUTDIR=runs/bar_through_hole_variation/<时间戳>
#   TOPOGYM_VENV=.venv-gs121-nyx
#   SKIP_OFFLINE=1  跳过离线门（13–14 分钟）。只在你刚跑过 tests/check_variant_rng.py
#                   与本任务几何门时用；默认 0，照跑。
#
# 产出：<OUTDIR>/<group>_s<seed>.log、visual_s<seed>.mp4、summary.csv。
# 退出码：任一 oracle 格非 success=True，或任一格 RAISED/TIMEOUT，即非 0。
# bypass 格不计入退出码。刻意不用 set -e。
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
OUTDIR="${OUTDIR:-runs/bar_through_hole_variation/$(date +%Y%m%d_%H%M%S)}"

VIEWER_ARGS=()
[[ "$VIEWER" == "1" ]] && VIEWER_ARGS=(run.viewer=true)

SUITES=(visual oracle bypass wrong_hole)
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

# 离线门先过：变体块的包络、派生、拒绝率；派生高度还原基准、横推窗口、最坏角点。几十秒。
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
if [[ "${SKIP_OFFLINE:-0}" != "1" ]] && ! python -B tests/check_bar_through_hole_geometry.py >> "$OUTDIR/offline.log" 2>&1; then
  echo "[error] tests/check_bar_through_hole_geometry.py 未通过，见 $OUTDIR/offline.log" >&2
  exit 1
fi

FAIL=0
declare -A VARIANT ORACLE BYPASS WRONGHOLE VISUAL ALIGN FINGER

run_state() {
  local code="$1" log="$2"
  if [[ "$code" == "124" ]]; then echo "TIMEOUT"; return; fi
  grep -qaiE "^Traceback" "$log" && { echo "RAISED"; return; }
  # physical demo 用退出码表达 success 与否（bypass 预期非 0），不算异常
  echo "ok"
}

variant_line() { grep -aF "bar_through_hole variant seed=" "$1" | tail -1; }
result_line()  { grep -aF "bar_through_hole_physical_insert_demo result" "$1" | tail -1; }
failure_of()   { result_line "$1" | grep -aoE 'failure_reason=[^ ]+' | sed 's/failure_reason=//'; }

run_cell() {
  local group="$1" seed="$2"; shift 2
  local tag="${group}_s${seed}" log="$OUTDIR/${group}_s${seed}.log"
  echo
  echo "==================== $tag ===================="
  local start; start=$(date +%s)
  local common=(python -B -m demos.routing.bar_through_hole_physical_insert_demo
                env.genesis.backend="$BACKEND" "${VIEWER_ARGS[@]}"
                run.randomize_layout=true "run.seed=$seed")
  local cmd=()
  case "$group" in
    visual)
      cmd=("${common[@]}" run.inspect_only=true
           recording=default "recording.path=$OUTDIR/visual_s${seed}.mp4" recording.camera=[oblique,front,topdown]) ;;
    oracle)
      cmd=("${common[@]}" run.oracle_mode=insert) ;;
    bypass)
      cmd=("${common[@]}" run.oracle_mode=bypass) ;;
    wrong_hole)
      cmd=("${common[@]}" run.oracle_mode=wrong_hole) ;;
  esac
  timeout "${TIMEOUT_S}s" "${cmd[@]}" "$@" 2>&1 | tee "$log"
  local code=${PIPESTATUS[0]}
  local dur=$(( $(date +%s) - start ))
  local state; state="$(run_state "$code" "$log")"
  local v; v="$(variant_line "$log")"
  [[ -n "$v" ]] && VARIANT[$seed]="${v#bar_through_hole variant }"

  local verdict="" n_mp4=0
  case "$group" in
    visual)
      # 多机位（2026-09-09 起 recording.camera 是三个）时，录像器给每个机位单独写一个文件、
      # 文件名加 `_<机位>` 后缀，所以这里数的是「有几个非空文件」而不是找那一个固定名字。
      n_mp4=$(find "$OUTDIR" -maxdepth 1 -name "visual_s${seed}*.mp4" -size +0 | wc -l)
      if [[ "$state" == "ok" && "$n_mp4" -ge 1 ]]; then verdict="ok (${n_mp4} 个机位)"; else verdict="FAIL $state"; FAIL=1; fi
      VISUAL[$seed]="$verdict" ;;
    oracle)
      if [[ "$state" != "ok" ]]; then verdict="FAIL $state"; FAIL=1
      elif result_line "$log" | grep -qaF " success=True"; then verdict="PASS"
      else verdict="FAIL $(failure_of "$log")"; FAIL=1; fi
      ORACLE[$seed]="$verdict"
      ALIGN[$seed]="$(result_line "$log" | grep -aoE 'align_tilt=[^ ]+' | sed 's/align_tilt=//')"
      FINGER[$seed]="$(result_line "$log" | grep -aoE 'finger_qpos=[^ ]+' | sed 's/finger_qpos=//')" ;;
    bypass)
      if [[ "$state" != "ok" ]]; then verdict="$state"
      elif result_line "$log" | grep -qaF " success=True"; then verdict="success(!)"
      else verdict="$(failure_of "$log")"; fi
      BYPASS[$seed]="$verdict" ;;
    wrong_hole)
      if [[ "$state" != "ok" ]]; then verdict="$state"
      elif result_line "$log" | grep -qaF " success=True"; then verdict="success"
      else verdict="$(failure_of "$log")"; fi
      WRONGHOLE[$seed]="$verdict" ;;
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
echo "seed,af,sides,open_index,pitch,hole_y,rest_x,rest_y,panel_x,length,grasp_off,side_clear,window,push_z,align_tilt,finger_qpos,visual,oracle,bypass,wrong_hole" > "$csv"
n_oracle=0; n_oracle_ok=0; n_bypass=0; n_bypass_failed=0; n_wrong=0; n_wrong_ok=0; n_middle=0
for seed in $SEEDS; do
  v="${VARIANT[$seed]:-}"
  f() { echo "$v" | grep -aoE "$1=[^ ]+" | sed "s/$1=//"; }
  printf '  seed %-3s af=%-6s open=%s pitch=%-6s hole_y=%-7s rest=(%s,%s) panel_x=%-6s len=%-6s grasp=%-6s side=%-6s win=%-6s push_z=%-6s align=%-8s | visual=%s oracle=%s bypass=%s wrong_hole=%s\n' \
    "$seed" "$(f af)" "$(f open_index)" "$(f pitch)" "$(f hole_y)" "$(f rest_x)" "$(f rest_y)" \
    "$(f panel_x)" "$(f length)" "$(f grasp_off)" \
    "$(f side_clear)" "$(f window)" "$(f push_z)" "${ALIGN[$seed]:--}" \
    "${VISUAL[$seed]:--}" "${ORACLE[$seed]:--}" "${BYPASS[$seed]:--}" "${WRONGHOLE[$seed]:--}"
  echo "$seed,$(f af),$(f sides),$(f open_index),$(f pitch),$(f hole_y),$(f rest_x),$(f rest_y),$(f panel_x),$(f length),$(f grasp_off),$(f side_clear),$(f window),$(f push_z),${ALIGN[$seed]:-},${FINGER[$seed]:-},${VISUAL[$seed]:-},${ORACLE[$seed]:-},${BYPASS[$seed]:-},${WRONGHOLE[$seed]:-}" >> "$csv"
  if [[ -n "${ORACLE[$seed]:-}" ]]; then
    n_oracle=$((n_oracle + 1)); [[ "${ORACLE[$seed]}" == "PASS" ]] && n_oracle_ok=$((n_oracle_ok + 1))
  fi
  if [[ -n "${BYPASS[$seed]:-}" ]]; then
    n_bypass=$((n_bypass + 1)); [[ "${BYPASS[$seed]}" != "success(!)" && "${BYPASS[$seed]}" != "RAISED" && "${BYPASS[$seed]}" != "TIMEOUT" ]] && n_bypass_failed=$((n_bypass_failed + 1))
  fi
  if [[ -n "${WRONGHOLE[$seed]:-}" ]]; then
    n_wrong=$((n_wrong + 1)); [[ "${WRONGHOLE[$seed]}" == "success" ]] && n_wrong_ok=$((n_wrong_ok + 1))
    # 中间那个孔恰好是通的那些格——wrong_hole 永远瞄中间，所以它的成功数应当正好等于这个。
    [[ "$(f open_index)" == "1" ]] && n_middle=$((n_middle + 1))
  fi
done
if [[ $n_oracle -gt 0 ]]; then
  echo "  oracle 成功: $n_oracle_ok / $n_oracle"
fi
if [[ $n_bypass -gt 0 ]]; then
  echo "  bypass 判失败: $n_bypass_failed / $n_bypass（预期全部：杆落在面板顶上，threading_count = 0）"
fi
if [[ $n_wrong -gt 0 ]]; then
  echo "  wrong_hole 成功: $n_wrong_ok / $n_wrong（预期 = 抽到中间孔的格数 $n_middle：无视画面永远瞄中间那个孔）"
fi
echo
echo "怎么读："
echo "  visual    打开 $OUTDIR/visual_s*.mp4：孔径、杆与面板位置、杆长应逐 seed 不同，且无穿模。"
echo "  oracle    全部 PASS 才说明 oracle 覆盖了包络；FAIL 的 seed 看其 log 的 failure_reason 与 variant 行"
echo "            （side_clear 小的格孔最紧，window 小的格横推的竖直余量最小）。align 列 > 1.0 会在 align_check 中止。"
echo "  bypass    应全部判失败；success(!) 说明从面板顶绕过去也算穿过，判据有问题。"
echo "  wrong_hole 成功数应正好等于 open_index=1 的格数；多出来说明瞄错孔也判成功（判据），"
echo "            或者盲孔没挡住杆（物理，见 bar_through_hole_zh.md §9.3）。"
echo "  finger    最小值与 grasp_qpos 0.008 之间取 physical.min_finger_qpos 的门（rigid_first_track_zh.md §7 第 5 条）。"
echo "summary: $csv"
echo "日志: $OUTDIR"
exit $FAIL
