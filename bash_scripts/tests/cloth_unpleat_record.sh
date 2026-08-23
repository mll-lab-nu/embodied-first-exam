#!/usr/bin/env bash
# ============================================================================
# cloth_unpleat（docx 1.2「展开单个褶皱」）的一次完整录制跑，给有 GPU 的机器用。
#
# 五格，由便宜到贵，**前面的格子不过就不跑后面的**：后面的失败会是前面那个原因的
# 回声，一起跑只会得到三份同样的错误。
#
#   check     免 GPU 的判据单测。改过阈值或褶皱几何之后必跑，秒级。
#   settle    褶皱静置 400 步：放手之后它还算不算一个褶皱（材料还收着、三层还叠着）。
#             判的东西与 demo 的起始护栏完全相同，所以这一格过了 demo 就不会在
#             同一处停下。双机位录制。
#   unfold    **任务本体**，三视角录制。这一格的视频就是要交付的东西。
#             夹爪抓布带的自由端，贴着桌面往远离褶皱的方向拉，靠桌面摩擦按住
#             另一端把褶皱抽平。褶皱本身不碰。
#   shove     往**反方向**拉（朝着褶皱推），三视角录制。搬动了同样多的布料却
#             什么也没展开，应当 unpleated=false。
#   overpull  拉过头，整条布带开始滑。两条门槛都会过，看的是 band_shift_mm ——
#             抓端头拉之后，「整条布带被拖走」是这个任务的首要失败模式。
#             不录像：它是个数字，不是画面。
#
# 用法：
#   bash bash_scripts/tests/cloth_unpleat_record.sh              # 全部五格
#   bash bash_scripts/tests/cloth_unpleat_record.sh settle       # 只跑闸口
#   bash bash_scripts/tests/cloth_unpleat_record.sh unfold press # 只跑两段录制
#
# 可调环境变量（都有默认值）：
#   BACKEND=gpu                   计算后端（gpu/cuda/cpu）
#   CAMERAS=[oblique,front,wrist] 任务录制的机位（本仓检查视频的固定三视角）
#   RES=960                       录制边长（像素，正方形）
#   EVERY_N=3                     每几步抓一帧
#   SETTLE_STEPS=400              settle 那一格静置多少步
#   TIMEOUT_S=1800                单格墙钟超时（秒）
#   KEEP_GOING=0                  置 1 则前一格失败也继续跑（默认不继续）
#   OUTDIR=runs/videos/cloth_unpleat/<时间戳>
#   TOPOGYM_VENV=.venv
#
# 产出：<OUTDIR>/ 下每格一个 .log，加上
#   settle_oblique.mp4 / settle_front.mp4
#   unpleat_oblique.mp4 / unpleat_front.mp4 / unpleat_wrist.mp4
#   press_oblique.mp4 / press_front.mp4 / press_wrist.mp4
# 跑完打一张汇总表并指出该看哪几行。
# 退出码：任何一格 TIMEOUT / RAISED / 非零即非 0。
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
CAMERAS="${CAMERAS:-[oblique,front,wrist]}"
RES="${RES:-960}"
EVERY_N="${EVERY_N:-3}"
SETTLE_STEPS="${SETTLE_STEPS:-400}"
TIMEOUT_S="${TIMEOUT_S:-1800}"
KEEP_GOING="${KEEP_GOING:-0}"
OUTDIR="${OUTDIR:-runs/videos/cloth_unpleat/$(date +%Y%m%d_%H%M%S)}"
mkdir -p "$OUTDIR"

# 早失败：venv 没对就别一格一格地各错一次。
if ! python -c "import topogym" 2>/dev/null; then
  echo "[error] 无法 import topogym。请先激活正确的 venv（或设 TOPOGYM_VENV）。" >&2
  exit 1
fi
if ! python -c "import genesis" 2>/dev/null; then
  echo "[error] 无法 import genesis。除 check 之外每一格都要跑真物理。" >&2
  exit 1
fi

ORDER=(check settle unfold shove overpull)
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

declare -a ROWS=()
FAIL=0
BLOCKED=""

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

# 从 stdout 抓这一格的结论行。抓不到就退回状态本身。
summarize() {
  local cell="$1" log="$2" state="$3"
  local line=""
  case "$cell" in
    check)  line="$(grep -E '^== (通过|失败)' "$log" | tail -1)" ;;
    settle) line="$(grep -E '^pleat_settle_spike verdict=' "$log" | tail -1)" ;;
    *)      line="$(grep -E '^cloth_unpleat result ' "$log" | tail -1)" ;;
  esac
  if [[ -z "$line" ]]; then
    # 没有结论行时报最后一条自己打的进度，比只报 RAISED 有用。
    line="$(grep -E '^(cloth_unpleat|pleat_settle_spike) ' "$log" | tail -1)"
  fi
  [[ -z "$line" ]] && line="$state（未找到结论行，见日志）"
  echo "$line"
}

run_cell() {
  local cell="$1"; shift
  local log="$OUTDIR/$cell.log"
  if [[ -n "$BLOCKED" && "$KEEP_GOING" != "1" ]]; then
    ROWS+=("$cell|-|跳过（$BLOCKED 没过；KEEP_GOING=1 可强跑）")
    return
  fi
  echo
  echo "==================== $cell ===================="
  local start; start=$(date +%s)
  timeout "${TIMEOUT_S}s" "$@" 2>&1 | tee "$log"
  local code=${PIPESTATUS[0]}
  local dur=$(( $(date +%s) - start ))
  local state; state="$(verdict "$code" "$log")"
  ROWS+=("$cell|${dur}s|$(summarize "$cell" "$log" "$state")")
  if [[ "$state" != "ok" ]]; then
    FAIL=1
    # check 与 settle 是闸口：它们不过，后面跑出来的失败只是同一个原因的回声。
    if [[ "$cell" == "check" || "$cell" == "settle" ]]; then
      BLOCKED="$cell"
    fi
  fi
}

# 一次任务录制的公共 hydra 覆盖。写成数组，避免续行反斜杠。
demo_args() {
  local motion="$1" stem="$2"
  printf '%s\n' \
    "recording=hq" \
    "recording.path=$OUTDIR/$stem.mp4" \
    "recording.camera=$CAMERAS" \
    "recording.res=[$RES,$RES]" \
    "recording.every_n_steps=$EVERY_N" \
    "run.motion=$motion" \
    "run.verbose=true" \
    "env.genesis.backend=$BACKEND"
}

echo "outdir=$OUTDIR  backend=$BACKEND  cameras=$CAMERAS  res=${RES}x${RES}"
echo "顺序: ${SELECTED[*]}（check / settle 是闸口，不过就跳过后面的）"

for name in "${SELECTED[@]}"; do
  case "$name" in
    check)
      run_cell check python -B tests/check_cloth_unpleat_geometry.py
      ;;
    settle)
      mapfile -t args < <(printf '%s\n' \
        "recording=hq" \
        "recording.path=$OUTDIR/settle.mp4" \
        "recording.camera=[oblique,front]" \
        "recording.res=[$RES,$RES]" \
        "recording.every_n_steps=$EVERY_N" \
        "run.settle_steps=$SETTLE_STEPS" \
        "run.verbose=true" \
        "env.genesis.backend=$BACKEND")
      run_cell settle python -B -m tests.pleat_settle_spike "${args[@]}"
      ;;
    unfold)
      mapfile -t args < <(demo_args unfold unpleat)
      run_cell unfold python -B -m demos.deformation.cloth_unpleat_physical_demo "${args[@]}"
      ;;
    shove)
      mapfile -t args < <(demo_args shove shove)
      run_cell shove python -B -m demos.deformation.cloth_unpleat_physical_demo "${args[@]}"
      ;;
    overpull)
      # 不录像：这一格要的是一个数字（band_shift_mm），不是画面。
      run_cell overpull python -B -m demos.deformation.cloth_unpleat_physical_demo \
        run.motion=overpull run.verbose=true "env.genesis.backend=$BACKEND"
      ;;
  esac
done

echo
echo "==================== 汇总 ===================="
printf '%-10s %-7s %s\n' "格" "墙钟" "结论行"
for row in "${ROWS[@]}"; do
  IFS='|' read -r a b c <<< "$row"
  printf '%-10s %-7s %s\n' "$a" "$b" "$c"
done

echo
echo "该看哪几行："
echo "  settle    verdict=intact 才往下跑。released = 材料已经自己放出来了,"
echo "            layers_lost = 三层散了, diverged = 发散(优先于其余三种)。"
echo "            判的东西与 demo 的起始护栏相同, 所以这一格过了 demo 不会再卡。"
echo "  unfold    unpleated=true 且 diverged=false 才算成功。两条门槛按顺序读:"
echo "            single_layer_frac(回到一层) 与 spread_ratio(材料还回来了)。"
echo "            gates= 后面列的是没过的那几条。"
echo "            **band_shift_mm 要一起看**: 抓端头拉之后, 整条布带被拖走是首要"
echo "            失败模式, 而它两条门槛都过得了 —— 只有这个读数分得出来。"
echo "  shove     应当 unpleated=false, gates= 里两条都在。它搬动了与 unfold 同样多"
echo "            的布料却什么也没展开, 用来确认判据读的不是位移。"
echo "  overpull  两条门槛都会过。看 band_shift_mm 比 unfold 大多少 —— 这两格并排"
echo "            读, 就能决定 band_shift 要不要从诊断量升格为门槛。"
echo "  全部      start_state 那行是动作前的护栏读数(材料还收着/三层还在);"
echo "            grasp_after_settle 的 moved_mm 应当接近 0(布带静置时不动);"
echo "            stretch_tracking=off 说明 Genesis 的重网格化不是干净的细分,"
echo "            拉伸诊断量因此关闭 —— 两条门槛都不需要它。"
echo
echo "视频: $OUTDIR"
echo "日志: $OUTDIR/*.log"
exit $FAIL
