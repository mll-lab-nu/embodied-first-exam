#!/usr/bin/env bash
# ============================================================================
# PBD 布料 spike 的统一跑法（类别 1 的建模方案，2026-08-17）。
#
# 六项，由便宜到贵。fold 是唯一还能推翻整个方案的一项，其余是标定护栏：
#   settle  静置基线：平整度方差 + 自发漂移，并确认重力真的作用在布上
#           （从 SETTLE_DROP_Z 高处放手；2026-08-17 那次生成在平衡位置上，
#            全程零位移，分不出「没事可做」和「没在仿真」）。
#   grip    四种「让布跟着夹爪走」的方式，在同一次垂直提起上对比：布跟上了命令
#           高度的百分之多少（followed_mm / follow_ratio），以及材料为此要拉伸
#           多少（worst_edge_strain）。2026-08-19 实测默认那种只跟上四成。
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
#   bash bash_scripts/tests/pbd_cloth_spike.sh                 # 全部六项
#   bash bash_scripts/tests/pbd_cloth_spike.sh fold            # 只跑关键那一项
#   bash bash_scripts/tests/pbd_cloth_spike.sh settle weld     # 只跑其中几项
#   SKIP_CONTACT=1 bash bash_scripts/tests/pbd_cloth_spike.sh  # 跳过会崩的那项
#
# 可调环境变量（都有默认值）：
#   BACKEND=gpu                      计算后端（gpu/cuda/cpu）
#   DRAG_SPEEDS="0.002 0.008 0.016 0.032"   speed 扫哪些指令速度（米/步）
#   PINCH_QPOS="0.0005 0.001 0.002 0.004 0.006"  pinch 扫哪些闭合半宽（米）
#   SETTLE_DROP_Z=0.050              settle 从多高放手（米）
#   ATTACH_MODES="..."               grip 扫哪几种附着方式
#   FRICTIONS="0.4:0.5 0.8:1.0 ..."  friction 扫哪几档布↔桌面摩擦
#   FOLD_STEP_COUNTS="240 600 1200"  quasistatic 扫哪几档步数
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
# 2026-08-17 那次扫参在高速端只跑了 4 步（距离固定、步数=距离/速度），发散来不及
# 发展；现在步数固定为 run.drag_steps，每档一样多。隧穿的理论门槛是每子步半个粒子
# = 0.002 / 4 子步 -> 0.008 米/步（particle_size 0.004），所以扫参跨过它。
DRAG_SPEEDS="${DRAG_SPEEDS:-0.002 0.008 0.016 0.032}"
# 参照量是 particle_size/2 = 0.002（单层布的半厚），扫参跨过它。
PINCH_QPOS="${PINCH_QPOS:-0.0005 0.001 0.002 0.004 0.006}"
SETTLE_DROP_Z="${SETTLE_DROP_Z:-0.050}"
# grip 扫哪几种附着方式。前两种是「事后改坐标」，后两种是「交给求解器」。
ATTACH_MODES="${ATTACH_MODES:-overwrite_graded overwrite_rigid link_patch link_single}"
# friction 扫哪几档「布↔桌面」摩擦，写成 "动摩擦:静摩擦" 成对给。
# 两头都要看：太小整片布被拖走，太大布像粘在桌上（docx 1.5 铺桌布就做不成）。
FRICTIONS="${FRICTIONS:-0.4:0.5 0.8:1.0 1.5:1.8}"
# quasistatic 扫哪几档步数。同一条路径切成不同份数走完 = 只有快慢不同。
FOLD_STEP_COUNTS="${FOLD_STEP_COUNTS:-240 600 1200}"
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

ORDER=(settle grip fold quasistatic negatives friction speed pinch cost contact)
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
    grip)
      # 同一次垂直提起，只改「怎么让布跟着夹爪走」。四行并排读就是结论。
      for mode in $ATTACH_MODES; do
        run_cell "grip_$mode" grip run.test=grip run.verbose=true \n          "task.grasp.attach_mode=$mode"
      done
      ;;
    fold)
      run_cell "fold" fold run.test=fold run.verbose=true
      ;;
    quasistatic)
      for n in $FOLD_STEP_COUNTS; do
        run_cell "qs_${n}steps" fold run.test=fold run.verbose=true "run.fold_steps=$n"
      done
      ;;
    negatives)
      # 和 fold 共用同一套测量, 所以三行数字可以直接并排比。
      for m in drag crumple; do
        run_cell "neg_$m" fold run.test=fold run.verbose=true "run.motion=$m"
      done
      ;;
    friction)
      for pair in $FRICTIONS; do
        kin="${pair%%:*}"; sta="${pair##*:}"
        run_cell "fric_${kin}_${sta}" fold run.test=fold run.verbose=true           "task.cloth.tabletop_friction.kinetic_mu=$kin"           "task.cloth.tabletop_friction.static_mu=$sta"
        # 同一档再确认布没被粘死: 从 5cm 放手, 该落平就要落平。
        run_cell "fric_${kin}_${sta}_settle" settle run.test=settle run.verbose=true           "task.cloth.z=$SETTLE_DROP_Z"           "task.cloth.tabletop_friction.kinetic_mu=$kin"           "task.cloth.tabletop_friction.static_mu=$sta"
      done
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
echo "  grip        看 follow_ratio：接近 1 才算抓住了（2026-08-19 默认那种只有 0.4）。"
echo "              同时看 worst_edge_strain：抓得越死，材料要拉伸得越多。"
echo "              选那个「跟得上、又没拉伸太多」的；link_single 还要在 viewer 里"
echo "              确认布角不会绕着那一个点乱转。"
echo "  quasistatic speed_ratio 接近 1 的那一档就是准静态的; 远大于 1 说明布有一段"
echo "              在自己塌下去, 那是动态操作, 本类要避开。选定后钉死写进配置。"
echo "  negatives   把 drag / crumple 两行与 fold 那行并排比: 哪几个量把它们分开了,"
echo "              阈值就卡在中间。覆盖面积单独一个是分不开揉成一团的。"
echo "  friction    抓得住: anchor_shift_mm / far_half_shift_mm 降到几毫米, two_layer_frac 上到 0.8+;"
echo "              没粘死: 同档的 _settle 行 gravity=fell 且 flatness_var 接近 0。"
echo "              两条都满足的那一档才是要写回配置的值。"
echo "  fold        **最关键的一行**: self_contact_gap_mm 接近 particle_size_mm 说明"
echo "              两层是叠着的; 接近 0 说明穿模了, 层数类判据在 PBD 下做不出来。"
echo "              配合 two_layer_frac (对折后应有可观比例的双层) 与"
echo "              far_edge_shift_mm (不为 0 说明布在桌上滑了, 折线会落错位置)。"
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
