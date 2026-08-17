#!/usr/bin/env bash
# ============================================================================
# PBD 布料 spike 的统一跑法（类别 1 的建模方案，2026-08-17）。
#
# 四个未知量，由便宜到贵，每一个都可能改变后面的设计：
#   settle  静置基线：平整度方差 + 自发漂移，并确认重力真的作用在布上
#           （从 SETTLE_DROP_Z 高处放手；2026-08-17 那次生成在平衡位置上，
#            全程零位移，分不出「没事可做」和「没在仿真」）。
#   weld    锥度焊接 vs 硬焊：看焊接区边缘的边长应变（硬焊会把焊区变成刚性夹板，
#           实测把 4mm 绳的弯曲半径钉在 6-9mm 并触发材料内部自碰撞）。
#   speed   扫末端速度找布开始发散的线，产出速度预算护栏的常数。
#   cost    每步耗时 vs 粒子尺度（空跑计时，不跑动作）。
#   pinch   在布上合拢手指（挤压）：contact 测不到它——那一项是闭着手指往下降。
#           这是最可能导致「夹爪穿模、布飞出去」的机制，至今没测过。
#   contact 闭合手指下降到布面，验 Genesis 1.2.1 上是否仍然 native segfault。
#
# **contact 永远排在最后，而且单独一个进程。** 1.1.0 上它是 core dump 而不是
# 求解器发散（见 docs/develop/physics/peeling/peeling_segfault_debug_zh.md）。
# 每格都是独立的 python 进程，所以它崩了不会带走别的格子；本脚本刻意不用
# `set -e`，就是为了让后面的汇总仍然打得出来。
#
# 用法：
#   bash bash_scripts/tests/pbd_cloth_spike.sh                 # 全部五项
#   bash bash_scripts/tests/pbd_cloth_spike.sh settle weld     # 只跑其中几项
#   SKIP_CONTACT=1 bash bash_scripts/tests/pbd_cloth_spike.sh  # 跳过会崩的那项
#
# 可调环境变量（都有默认值）：
#   BACKEND=gpu                      计算后端（gpu/cuda/cpu）
#   DRAG_SPEEDS="0.004 0.012 0.024 0.048"   speed 扫哪些指令速度（米/步）
#   PINCH_QPOS="0.001 0.002 0.003 0.005 0.008"  pinch 扫哪些闭合半宽（米）
#   SETTLE_DROP_Z=0.050              settle 从多高放手（米）
#   PARTICLE_SIZES="0.004 0.006 0.010"      cost 扫哪些粒子尺度（米）
#   BENCH_STEPS=100                  cost 每格计时多少步
#   TIMEOUT_S=900                    单格墙钟超时（秒）
#   SKIP_CONTACT=0                   置 1 跳过 contact
#   OUTDIR=runs/cloth_spike/<时间戳>
#   TOPOGYM_VENV=.venv
#
# 每格产出 <OUTDIR>/<tag>.log，跑完打印一张汇总表并给出结论该看哪几行。
# 退出码：任何一格 TIMEOUT / RAISED / codeN 即非 0；contact 的 SEGV **不算失败**，
# 它是这一项要测的结果本身。
# ============================================================================
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$REPO"

if [[ -z "${VIRTUAL_ENV:-}" ]]; then
  VENV="${TOPOGYM_VENV:-$REPO/.venv}"
  if [[ -f "$VENV/bin/activate" ]]; then
    # shellcheck disable=SC1091
    source "$VENV/bin/activate"
  fi
fi

BACKEND="${BACKEND:-gpu}"
# 2026-08-17 扫到 0.008 全过、看门狗从未响 —— 上界在更高处。隧穿的理论门槛是
# 每子步半个粒子 = 0.003/4 子步 -> 约 0.012 米/步，所以扫参必须跨过它。
DRAG_SPEEDS="${DRAG_SPEEDS:-0.004 0.012 0.024 0.048}"
# 参照量是 particle_size/2 = 0.003（单层布的半厚），扫参跨过它。
PINCH_QPOS="${PINCH_QPOS:-0.001 0.002 0.003 0.005 0.008}"
SETTLE_DROP_Z="${SETTLE_DROP_Z:-0.050}"
PARTICLE_SIZES="${PARTICLE_SIZES:-0.004 0.006 0.010}"
BENCH_STEPS="${BENCH_STEPS:-100}"
TIMEOUT_S="${TIMEOUT_S:-900}"
SKIP_CONTACT="${SKIP_CONTACT:-0}"
OUTDIR="${OUTDIR:-runs/cloth_spike/$(date +%Y%m%d_%H%M%S)}"
mkdir -p "$OUTDIR"

# 早失败：venv 没对就别一格一格地各错一次
if ! python -c "import topogym" 2>/dev/null; then
  echo "[error] 无法 import topogym。请先激活正确的 venv（或设 TOPOGYM_VENV），再跑本脚本。" >&2
  exit 1
fi
if ! python -c "import genesis" 2>/dev/null; then
  echo "[error] 无法 import genesis。本 spike 要跑真物理，必须在项目 venv 里跑。" >&2
  exit 1
fi

ORDER=(settle weld speed pinch cost contact)
if [[ $# -gt 0 ]]; then
  SELECTED=("$@")
else
  SELECTED=("${ORDER[@]}")
fi
for name in "${SELECTED[@]}"; do
  case " ${ORDER[*]} " in
    *" $name "*) ;;
    *) echo "[error] 未知项 '$name'；可选：${ORDER[*]}" >&2; exit 1 ;;
  esac
done

declare -A RESULT=()
declare -a ROWS=()
FAIL=0

# 一格的判定。SEGV 单独识别：它正是 contact 要回答的问题，不是脚本出错。
verdict() {
  local code="$1" log="$2"
  if [[ "$code" == "124" ]]; then echo "TIMEOUT"; return; fi
  if [[ "$code" == "139" ]] || grep -qiE "Segmentation fault|core dumped" "$log"; then
    echo "SEGV"; return
  fi
  if [[ "$code" != "0" ]]; then
    grep -qiE "Traceback" "$log" && { echo "RAISED"; return; }
    echo "code$code"; return
  fi
  echo "ok"
}

# 从 stdout 抓这一项的结论行。抓不到就退回 verdict 本身。
summarize() {
  local test="$1" log="$2" state="$3"
  if [[ "$state" != "ok" ]]; then
    # 崩了也尽量报出最后一行进度：contact 每步都 flush，最后一行就是崩溃时的净空。
    local last
    last="$(grep -E '^\[cloth_' "$log" | tail -1)"
    [[ -n "$last" ]] && { echo "$state | 最后一行: $last"; return; }
    echo "$state"; return
  fi
  local line
  case "$test" in
    cost) line="$(grep -E '^pbd_cloth_spike bench' "$log" | tail -1)" ;;
    *)    line="$(grep -E "^pbd_cloth_spike $test " "$log" | tail -1)" ;;
  esac
  [[ -z "$line" ]] && line="ok（未找到结论行，见日志）"
  echo "$line"
}

run_cell() {
  local tag="$1"; shift
  local test="$1"; shift
  local log="$OUTDIR/$tag.log"
  echo
  echo "==================== $tag ===================="
  local start; start=$(date +%s)
  timeout "${TIMEOUT_S}s" python -B -m tests.pbd_cloth_spike \
    env.genesis.backend="$BACKEND" "$@" 2>&1 | tee "$log"
  local code=${PIPESTATUS[0]}
  local dur=$(( $(date +%s) - start ))
  local state; state="$(verdict "$code" "$log")"
  RESULT[$tag]="$state"
  ROWS+=("$tag|${dur}s|$(summarize "$test" "$log" "$state")")
  # contact 的 SEGV 是结论不是故障；其余任何非 ok 都算失败。
  if [[ "$state" != "ok" ]] && ! { [[ "$test" == "contact" ]] && [[ "$state" == "SEGV" ]]; }; then
    FAIL=1
  fi
}

echo "outdir=$OUTDIR  backend=$BACKEND  timeout=${TIMEOUT_S}s"
echo "顺序: ${SELECTED[*]}（contact 永远最后，且单独一个进程）"

for name in "${SELECTED[@]}"; do
  case "$name" in
    settle)
      # 从高处放手：落不落下来，是「布有没有物理」这个问题的直接答案。
      run_cell "settle" settle run.test=settle run.verbose=true \
        "task.cloth.z=$SETTLE_DROP_Z"
      ;;
    weld)
      # 同一个动作，只改焊接权重。两行的 worst_edge_strain 对比就是结论。
      run_cell "weld_taper" weld run.test=weld run.taper=true  run.verbose=true
      run_cell "weld_hard"  weld run.test=weld run.taper=false run.verbose=true
      ;;
    speed)
      for speed in $DRAG_SPEEDS; do
        run_cell "speed_$speed" speed run.test=speed "run.drag_speed=$speed"
      done
      ;;
    cost)
      for size in $PARTICLE_SIZES; do
        run_cell "cost_ps$size" cost \
          "run.bench_steps=$BENCH_STEPS" "task.cloth.particle_size=$size"
      done
      ;;
    pinch)
      for qpos in $PINCH_QPOS; do
        run_cell "pinch_q$qpos" pinch run.test=pinch "run.pinch_qpos=$qpos"
      done
      ;;
    contact)
      if [[ "$SKIP_CONTACT" == "1" ]]; then
        echo; echo "[skip] contact（SKIP_CONTACT=1）"
        continue
      fi
      run_cell "contact" contact run.test=contact run.verbose=true
      ;;
  esac
done

echo
echo "==================== 汇总 ===================="
for row in "${ROWS[@]}"; do
  IFS='|' read -r tag dur line <<< "$row"
  printf '  %-16s %-7s %s\n' "$tag" "$dur" "$line"
done

echo
echo "怎么读："
echo "  settle      **先看 gravity=**：fell 才说明布真的在被仿真，STATIC 则后面"
echo "              所有判据阈值都不成立，先查为什么重力没作用上去。"
echo "              然后 flatness_var / peak_above_table 才是 1.1 平整度的基线。"
echo "  remesh      日志里 pbd_cloth_spike remesh 那行的 order_preserved："
echo "              NO = 重网格化打乱了顶点顺序，所有需要追踪材料点的判据"
echo "              （折线位置、层归属、材料守恒）都要换实现方式。"
echo "  weld        比两行的 worst_edge_strain：硬焊明显更大 = 焊区确实成了刚性夹板，"
echo "              锥度权重要保留；两行接近则这条护栏可以简化。"
echo "  speed       第一个出现 blowup=（非 none）或 completed=False 的速度就是上界；"
echo "              对照同一行的 tunnel_threshold 判断是不是隧穿导致的。"
echo "  pinch       第一个 blowup= 非 none 的 qpos 就是闭合间隙的下限；"
echo "              ratio<1 那几档都能过 = 装饰性闭合可以用，夹爪不必全程张开。"
echo "  cost        per_step 随 particle_size 的变化 = 布料规模下的每步成本，"
echo "              用来估一次对折 episode 的墙钟时间。"
echo "  contact     SEGV = 1.2.1 上仍然会崩，'保留真实接触再加固'这条路不可用；"
echo "              ok  = 可以重新考虑让手指真的碰布，reached_clearance 是它撑到的净空。"
echo
echo "结论请写进 docs/develop/physics/cloth/pbd_cloth_spike_zh.md（形式同"
echo "fem_ipc_step_cost_zh.md：含被排除的假设）。"
echo "日志: $OUTDIR"
exit $FAIL
