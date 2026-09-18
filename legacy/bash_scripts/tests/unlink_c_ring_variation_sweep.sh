#!/usr/bin/env bash
# ============================================================================
# unlink_c_ring 变体生成实验（variation_axes_plain_zh.md §6.2 第 8 步）。
#
# 每个 seed 三格：
#   visual    inspect demo 建场景不沉降，录几帧静态画面 → 人眼看 visual_s<seed>.mp4：
#             开口朝向、装置绕竖轴的角度、桌上位置是否逐 seed 不同，有无穿模。
#   oracle    physical demo，gateway 正解（抬升 → 平摆对准 → 从开口滑出）→ 必须 success=True。
#             这是「oracle 在包络内每个变体都可解」的直接证据。
#   no_align  physical demo，防捷径对照：跳过对准直接搬走 → 只记录；预期 success=False。
#
# 变体参数来自 task 配置末尾的 variation 块，由 run.randomize_layout=true run.seed=<seed>
# 触发；demo 打印一行
#   unlink_c_ring variant seed=… gap=… gap_az=… yaw=… cx=… cy=… grasp_az=… side_clear=…
#     hand_clear=… reach=…
# 本脚本解析它进汇总表，另抓 result 行的 min_gap_seen（passed_through 判据的读数，
# 基线复现要看它，见 unlink_c_ring_zh.md §11.4）。
#
# **成本**：纯刚体。一格秒级到 1–2 min；十个 seed 三组全跑约半小时。
# **默认无头。** VIEWER=1 可开窗，但不加 run.keep_open。
#
# 用法：
#   bash bash_scripts/tests/unlink_c_ring_variation_sweep.sh visual oracle          # seed 0–9
#   SEEDS="0 1 2" bash bash_scripts/tests/unlink_c_ring_variation_sweep.sh no_align
#   bash bash_scripts/tests/unlink_c_ring_variation_sweep.sh                       # 全部三组
#
# 可调环境变量：
#   SEEDS="0 1 2 3 4 5 6 7 8 9"
#   BACKEND=gpu
#   TIMEOUT_S=900
#   VIEWER=0
#   OUTDIR=runs/unlink_c_ring_variation/<时间戳>
#   TOPOGYM_VENV=.venv-gs121-nyx
#   SKIP_OFFLINE=1  跳过离线门（13–14 分钟）。只在你刚跑过 tests/check_variant_rng.py
#                   与本任务几何门时用；默认 0，照跑。
#
# 产出：<OUTDIR>/<group>_s<seed>.log、visual_s<seed>.mp4、summary.csv。
# 退出码：任一 oracle 格非 success=True，或任一格 RAISED/TIMEOUT，即非 0。
# no_align 格不计入退出码。刻意不用 set -e。
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
OUTDIR="${OUTDIR:-runs/unlink_c_ring_variation/$(date +%Y%m%d_%H%M%S)}"

VIEWER_ARGS=()
[[ "$VIEWER" == "1" ]] && VIEWER_ARGS=(run.viewer=true)

SUITES=(visual oracle no_align)
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

# 离线门先过：变体块的包络、派生、拒绝率；七行不等式、32 角点、gateway 唯一性；滑出路径。几十秒。
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
if [[ "${SKIP_OFFLINE:-0}" != "1" ]] && ! python -B tests/check_c_ring_clearance.py >> "$OUTDIR/offline.log" 2>&1; then
  echo "[error] tests/check_c_ring_clearance.py 未通过，见 $OUTDIR/offline.log" >&2
  exit 1
fi
if ! python -B tests/check_gateway_slide_path.py >> "$OUTDIR/offline.log" 2>&1; then
  echo "[error] tests/check_gateway_slide_path.py 未通过，见 $OUTDIR/offline.log" >&2
  exit 1
fi

FAIL=0
declare -A VARIANT ORACLE NOALIGN VISUAL MINGAP

run_state() {
  local code="$1" log="$2"
  if [[ "$code" == "124" ]]; then echo "TIMEOUT"; return; fi
  grep -qaiE "^Traceback" "$log" && { echo "RAISED"; return; }
  # physical demo 用退出码表达 success 与否（no_align 预期非 0），不算异常
  echo "ok"
}

variant_line() { grep -aF "unlink_c_ring variant seed=" "$1" | tail -1; }
result_line()  { grep -aF "unlink_c_ring_physical_extract_demo result" "$1" | tail -1; }
failure_of()   { result_line "$1" | grep -aoE 'failure_reason=[^ ]+' | sed 's/failure_reason=//'; }

run_cell() {
  local group="$1" seed="$2"; shift 2
  local tag="${group}_s${seed}" log="$OUTDIR/${group}_s${seed}.log"
  echo
  echo "==================== $tag ===================="
  local start; start=$(date +%s)
  local cmd=()
  case "$group" in
    visual)
      cmd=(python -B -m demos.entangle.unlink_c_ring_inspect_demo
           env.genesis.backend="$BACKEND" "${VIEWER_ARGS[@]}"
           run.randomize_layout=true "run.seed=$seed" run.static_only=true
           recording=default "recording.path=$OUTDIR/visual_s${seed}.mp4" recording.camera=oblique) ;;
    oracle)
      cmd=(python -B -m demos.entangle.unlink_c_ring_physical_extract_demo
           env.genesis.backend="$BACKEND" "${VIEWER_ARGS[@]}"
           run.randomize_layout=true "run.seed=$seed" run.oracle_mode=gateway) ;;
    no_align)
      cmd=(python -B -m demos.entangle.unlink_c_ring_physical_extract_demo
           env.genesis.backend="$BACKEND" "${VIEWER_ARGS[@]}"
           run.randomize_layout=true "run.seed=$seed" run.oracle_mode=no_align) ;;
  esac
  timeout "${TIMEOUT_S}s" "${cmd[@]}" "$@" 2>&1 | tee "$log"
  local code=${PIPESTATUS[0]}
  local dur=$(( $(date +%s) - start ))
  local state; state="$(run_state "$code" "$log")"
  local v; v="$(variant_line "$log")"
  [[ -n "$v" ]] && VARIANT[$seed]="${v#unlink_c_ring variant }"

  local verdict=""
  case "$group" in
    visual)
      if [[ "$state" == "ok" && -s "$OUTDIR/visual_s${seed}.mp4" ]]; then verdict="ok (看 mp4)"; else verdict="FAIL $state"; FAIL=1; fi
      VISUAL[$seed]="$verdict" ;;
    oracle)
      if [[ "$state" != "ok" ]]; then verdict="FAIL $state"; FAIL=1
      elif result_line "$log" | grep -qaF " success=True"; then verdict="PASS"
      else verdict="FAIL $(failure_of "$log")"; FAIL=1; fi
      ORACLE[$seed]="$verdict"
      MINGAP[$seed]="$(result_line "$log" | grep -aoE 'min_gap_seen=[^ ]+' | sed 's/min_gap_seen=//')" ;;
    no_align)
      if [[ "$state" != "ok" ]]; then verdict="$state"
      elif result_line "$log" | grep -qaF " success=True"; then verdict="success(!)"
      else verdict="$(failure_of "$log")"; fi
      NOALIGN[$seed]="$verdict" ;;
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
echo "seed,gap,gap_az,yaw,cx,cy,grasp_az,side_clear,hand_clear,reach,min_gap,visual,oracle,no_align" > "$csv"
n_oracle=0; n_oracle_ok=0; n_noalign=0; n_noalign_failed=0
for seed in $SEEDS; do
  v="${VARIANT[$seed]:-}"
  f() { echo "$v" | grep -aoE "$1=[^ ]+" | sed "s/$1=//"; }
  printf '  seed %-3s gap=%-6s gap_az=%-6s yaw=%-7s cx=%-7s cy=%-7s grasp_az=%-5s side=%-6s hand=%-6s reach=%-5s min_gap=%-8s | visual=%s oracle=%s no_align=%s\n' \
    "$seed" "$(f gap)" "$(f gap_az)" "$(f yaw)" "$(f cx)" "$(f cy)" "$(f grasp_az)" \
    "$(f side_clear)" "$(f hand_clear)" "$(f reach)" "${MINGAP[$seed]:--}" \
    "${VISUAL[$seed]:--}" "${ORACLE[$seed]:--}" "${NOALIGN[$seed]:--}"
  echo "$seed,$(f gap),$(f gap_az),$(f yaw),$(f cx),$(f cy),$(f grasp_az),$(f side_clear),$(f hand_clear),$(f reach),${MINGAP[$seed]:-},${VISUAL[$seed]:-},${ORACLE[$seed]:-},${NOALIGN[$seed]:-}" >> "$csv"
  if [[ -n "${ORACLE[$seed]:-}" ]]; then
    n_oracle=$((n_oracle + 1)); [[ "${ORACLE[$seed]}" == "PASS" ]] && n_oracle_ok=$((n_oracle_ok + 1))
  fi
  if [[ -n "${NOALIGN[$seed]:-}" ]]; then
    n_noalign=$((n_noalign + 1)); [[ "${NOALIGN[$seed]}" != "success(!)" && "${NOALIGN[$seed]}" != "RAISED" && "${NOALIGN[$seed]}" != "TIMEOUT" ]] && n_noalign_failed=$((n_noalign_failed + 1))
  fi
done
if [[ $n_oracle -gt 0 ]]; then
  echo "  oracle 成功: $n_oracle_ok / $n_oracle"
fi
if [[ $n_noalign -gt 0 ]]; then
  echo "  no_align 判失败: $n_noalign_failed / $n_noalign（预期全部：开口从未对准管身，环出不来）"
fi
echo
echo "怎么读："
echo "  visual    打开 $OUTDIR/visual_s*.mp4：开口朝向、装置角度、桌上位置应逐 seed 不同，且无穿模。"
echo "  oracle    全部 PASS 才说明 oracle 覆盖了包络；FAIL 的 seed 看其 log 的 [gateway_extract <phase>] min_gap= 行"
echo "            （首次跌破 -jam_depth 的阶段）与 variant 行（side_clear 小的格开口最窄，hand_clear 小的格手最贴环）。"
echo "  no_align  应全部判失败；success(!) 说明不对准也解开了，判据或几何有问题。"
echo "summary: $csv"
echo "日志: $OUTDIR"
exit $FAIL
