#!/usr/bin/env bash
# ============================================================================
# diverter_route_ball（docx 4.3）场景与判据的验收跑法，不含机械臂动作。
#
# 七格，三组，由便宜到关键：
#   sweep     关节限位。命令值故意越过限位 10°，验分流板停在 ±30°。步骤 3 的拨杆
#             原语靠限位吃掉圆弧过冲，这是它成立的前提。
#   classify  三个相位下**几何判据与物理结果对表**。本轮的核心：flood-fill 说哪边
#             通、球实际从哪边出去，两者必须给同一个答案。半开那一格同时复验球
#             卡住后会停下——2026-08-18 实测过一次卡住但以 18mm/s 永远倒退
#             （HeadingDrive 受阻后没交给滑行），已修。
#   speed     三个球速下导流都成立，证明导流是几何性质而不是某一组参数的巧合。
#
# **默认无头。** 判据全部在日志里：2026-08-18 那轮 viewer 看着「没什么问题」，而两处
# 缺陷（球永远倒退、跑偏指标量错对象）都只有日志能看出来。VIEWER=1 可开窗，但不会
# 加 run.keep_open —— 那会让进程等人关窗，并以「Viewer closed」非零码退出。
#
# 用法：
#   bash bash_scripts/tests/diverter_route_ball_scene_check.sh                 # 全部
#   bash bash_scripts/tests/diverter_route_ball_scene_check.sh classify        # 只跑一组
#   bash bash_scripts/tests/diverter_route_ball_scene_check.sh sweep classify
#   VIEWER=1 bash bash_scripts/tests/diverter_route_ball_scene_check.sh classify
#
# 可调环境变量（都有默认值）：
#   BACKEND=cpu                    计算后端（本任务全刚体，cpu 够用）
#   SPEEDS="0.08 0.12 0.18"        speed 组扫哪些球速（米/秒）
#   JAM_X=-0.056  JAM_TOL=0.020    半开态球应停在哪（米）及容差；见 grade_classify
#   TIMEOUT_S=600                  单格墙钟超时（秒）
#   VIEWER=0                       置 1 开 viewer
#   OUTDIR=runs/diverter_scene/<时间戳>
#   TOPOGYM_VENV=.venv-gs110
#
# 每格产出 <OUTDIR>/<tag>.log，跑完打印汇总表并逐格给 PASS/FAIL。
# 退出码：任何一格非 PASS 即非 0。刻意不用 set -e —— 一格失败后剩下的格子仍要跑完，
# 汇总表才有意义。
# ============================================================================
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$REPO"

if [[ -z "${VIRTUAL_ENV:-}" ]]; then
  for candidate in "${TOPOGYM_VENV:-}" "$REPO/.venv-gs110" "$REPO/.venv"; do
    [[ -z "$candidate" ]] && continue
    if [[ -f "$candidate/bin/activate" ]]; then
      # shellcheck disable=SC1091
      source "$candidate/bin/activate"
      break
    fi
  done
fi

BACKEND="${BACKEND:-cpu}"
SPEEDS="${SPEEDS:-0.08 0.12 0.18}"
# 板尖在 x=-0.0299，球半径 0.026，故接触时球心在 -0.0559。修好滑行交接后球应当
# 停在这附近；坏掉的那一版最终停在 -0.1265，容差 0.020 足以把两者分开。
JAM_X="${JAM_X:--0.056}"
JAM_TOL="${JAM_TOL:-0.020}"
TIMEOUT_S="${TIMEOUT_S:-600}"
VIEWER="${VIEWER:-0}"
OUTDIR="${OUTDIR:-runs/diverter_scene/$(date +%Y%m%d_%H%M%S)}"

VIEWER_ARGS=()
if [[ "$VIEWER" == "1" ]]; then
  VIEWER_ARGS=(run.viewer=true)
fi

SUITES=(sweep classify speed)
if [[ $# -gt 0 ]]; then
  SELECTED=("$@")
else
  SELECTED=("${SUITES[@]}")
fi
for name in "${SELECTED[@]}"; do
  case " ${SUITES[*]} " in
    *" $name "*) ;;
    *) echo "[error] 未知组 '$name'；可选：${SUITES[*]}" >&2; exit 1 ;;
  esac
done

# 早失败：venv 没对就别一格一格地各错一次。
if ! python -c "import topogym" 2>/dev/null; then
  echo "[error] 无法 import topogym。请先激活项目 venv（或设 TOPOGYM_VENV），再跑本脚本。" >&2
  exit 1
fi
if ! python -c "import genesis" 2>/dev/null; then
  echo "[error] 无法 import genesis。本脚本要跑真物理，必须在项目 venv 里跑。" >&2
  exit 1
fi
mkdir -p "$OUTDIR"
# 表与目录一致性。不花钱，且它不过就说明登记漏了，后面的格子读数没有意义。
if ! python topogym/core/taxonomy.py > "$OUTDIR/taxonomy.log" 2>&1; then
  echo "[error] topogym/core/taxonomy.py 未通过，见 $OUTDIR/taxonomy.log" >&2
  exit 1
fi

declare -a ROWS=()
FAIL=0

# 一格的运行状态。与判据无关，只看进程是怎么结束的。
run_state() {
  local code="$1" log="$2"
  if [[ "$code" == "124" ]]; then echo "TIMEOUT"; return; fi
  # VIEWER=1 时关窗会抛 GenesisException: Viewer closed.，那是正常结束不是缺陷。
  if [[ "$code" != "0" ]]; then
    grep -qaF "Viewer closed." "$log" && { echo "ok"; return; }
    grep -qaiE "^Traceback" "$log" && { echo "RAISED"; return; }
    echo "code$code"; return
  fi
  echo "ok"
}

# 判据：要求日志里出现全部给定的字面串。
expect_all() {
  local log="$1"; shift
  local missing=()
  local pattern
  for pattern in "$@"; do
    grep -qaF -- "$pattern" "$log" || missing+=("$pattern")
  done
  if [[ ${#missing[@]} -gt 0 ]]; then
    printf 'FAIL 缺少: %s' "${missing[*]}"
    return 1
  fi
  printf 'PASS'
}

# 半开那一格额外要求：球停在板尖前，而不是一路倒退回释放点。
expect_jam_rest() {
  local log="$1"
  local final
  final="$(grep -aF 'diverter_route_ball inspect' "$log" | tail -1 \
    | sed -n 's/.*final=(\([-+0-9.]*\),.*/\1/p')"
  if [[ -z "$final" ]]; then
    printf 'FAIL 读不到 final='
    return 1
  fi
  awk -v x="$final" -v want="$JAM_X" -v tol="$JAM_TOL" 'BEGIN{
    d = x - want; if (d < 0) d = -d;
    if (d <= tol) printf "PASS final_x=%s", x;
    else printf "FAIL final_x=%s 偏离 %s 超过 %s（球没停住？）", x, want, tol;
    exit (d <= tol) ? 0 : 1
  }'
}

grade() {
  local tag="$1" log="$2" state="$3"
  if [[ "$state" != "ok" ]]; then
    printf '%s' "$state"
    return 1
  fi
  case "$tag" in
    sweep)
      expect_all "$log" "seated_both_ends=True"
      ;;
    classify_seal_left)
      expect_all "$log" "agrees=True" "open_side=right" "observed_exit=right" \
        "routed_correctly=True"
      ;;
    classify_seal_right)
      expect_all "$log" "agrees=True" "open_side=left" "observed_exit=left" \
        "routed_correctly=True"
      ;;
    classify_half)
      # 两条判据同时要：判据说两侧都不通、物理上球确实没出去，且球停住了。
      local head_result
      head_result="$(expect_all "$log" "agrees=True" "open_side=None" \
        "observed_exit=None" "jammed=True" "label=flap_not_seated")" || {
          printf '%s' "$head_result"; return 1; }
      local rest_result
      rest_result="$(expect_jam_rest "$log")" || { printf '%s' "$rest_result"; return 1; }
      printf '%s / %s' "$head_result" "$rest_result"
      ;;
    speed_*)
      expect_all "$log" "routed_correctly=True"
      ;;
    *)
      printf 'FAIL 没有为 %s 定义判据' "$tag"
      return 1
      ;;
  esac
}

# 从日志里抓这一格的结论行，放进汇总表。
summary_line() {
  local tag="$1" log="$2"
  case "$tag" in
    sweep)     grep -aF 'diverter_route_ball sweep' "$log" | tail -1 ;;
    classify_*) grep -aF 'diverter_route_ball classify' "$log" | tail -1 ;;
    *)         grep -aF 'diverter_route_ball inspect' "$log" | tail -1 ;;
  esac
}

run_cell() {
  local tag="$1"; shift
  local log="$OUTDIR/$tag.log"
  echo
  echo "==================== $tag ===================="
  local start; start=$(date +%s)
  timeout "${TIMEOUT_S}s" python -B -m demos.connectivity.diverter_route_ball_inspect_demo \
    env.genesis.backend="$BACKEND" "${VIEWER_ARGS[@]}" "$@" 2>&1 | tee "$log"
  local code=${PIPESTATUS[0]}
  local dur=$(( $(date +%s) - start ))
  local state; state="$(run_state "$code" "$log")"
  local verdict
  verdict="$(grade "$tag" "$log" "$state")" || FAIL=1
  ROWS+=("$tag|${dur}s|$verdict")
  echo "---- $tag: $verdict"
}

echo "outdir=$OUTDIR  backend=$BACKEND  viewer=$VIEWER  timeout=${TIMEOUT_S}s"
echo "组: ${SELECTED[*]}"

for name in "${SELECTED[@]}"; do
  case "$name" in
    sweep)
      run_cell sweep run.sweep_joint=true run.verbose=true
      ;;
    classify)
      run_cell classify_seal_left  run.classify=true run.flap_phase=seal_left
      run_cell classify_seal_right run.classify=true run.flap_phase=seal_right
      # verbose 只给半开这一格：卡住之后的轨迹采样是判断球有没有停住的原始证据。
      run_cell classify_half run.classify=true run.flap_phase=half run.verbose=true
      ;;
    speed)
      for speed in $SPEEDS; do
        run_cell "speed_$speed" run.flap_phase=seal_left "task.ball.speed=$speed"
      done
      ;;
  esac
done

echo
echo "==================== 汇总 ===================="
for row in "${ROWS[@]}"; do
  IFS='|' read -r tag dur verdict <<< "$row"
  printf '  %-20s %-6s %s\n' "$tag" "$dur" "$verdict"
done

echo
echo "结论行："
for row in "${ROWS[@]}"; do
  IFS='|' read -r tag _ _ <<< "$row"
  line="$(summary_line "$tag" "$OUTDIR/$tag.log")"
  [[ -n "$line" ]] && printf '  %s\n' "$line"
done

echo
echo "怎么读："
echo "  sweep              seated_both_ends=True 才说明限位吃住了越程 10° 的命令；"
echo "                     False 则步骤 3 的拨杆原语不能靠限位定落座位置。"
echo "  classify_seal_*    agrees=True 是核心：flood-fill 的 open_side 与球实际的"
echo "                     observed_exit 必须一致。不一致时错的是判据，不是场景——"
echo "                     先查障碍矩形与出口平面截断，别去调几何。"
echo "  classify_half      两侧都不可达 + 球没出去 + 球停在板尖前。final_x 若落在"
echo "                     -0.10 之外，说明受阻后没交给滑行，球又在永久倒退。"
echo "  speed_*            三档全 PASS 才能说导流是几何性质；某一档失败就记下它的"
echo "                     速度，那是球速旋钮的边界。"
echo
echo "本轮验收的完整判据见 docs/develop/tasks/diverter_route_ball_zh.md §8 步骤 2。"
echo "日志: $OUTDIR"
exit $FAIL
