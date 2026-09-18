#!/usr/bin/env bash
# ============================================================================
# linkbar_rotate_to_zone（docx 4.4 改造版）的验收跑法。
#
# 八格，四组，由便宜到关键：
#   offline   两个无物理的门：规划器对照（oracle 6/6、nearest_zone 3/6）、布局几何
#             （区域边界翻转、无重叠、非法布局被拒）。几秒钟，先跑。
#   sweep     位置控制把梁驱到 color_1 → init → color_2 → init，验梁能真的到两块区域
#             （直接写关节会穿过挡路的东西并报告成功）。
#   seat      写关节到三个相位再沉降，验判据读出的与画面一致：none → 区外，
#             color_2 → 同色区成功，color_1 → 异色区 wrong_zone。同时读沉降后的角速度，
#             这是 success.max_angular_speed 阈值的实测依据。
#   physical  带机械臂的完整 episode 三条：oracle 成功；nearest_zone 在默认布局
#             （target=color_2 在 +55°，比 color_1 的 −45° 更远）转错判 wrong_zone；oracle + 过转 12° 判
#             outside_zone（区域半宽 8°）。
#
# **默认无头。** 判据全部在日志里。VIEWER=1 可开窗，但不会加 run.keep_open ——
# 那会让进程等人关窗，并以「Viewer closed」非零码退出。
#
# 用法：
#   bash bash_scripts/tests/linkbar_rotate_to_zone_check.sh                 # 全部
#   bash bash_scripts/tests/linkbar_rotate_to_zone_check.sh offline seat    # 只跑几组
#   VIEWER=1 bash bash_scripts/tests/linkbar_rotate_to_zone_check.sh physical
#
# 可调环境变量（都有默认值）：
#   BACKEND=gpu                    计算后端。physical 组带 Franka，cpu 上一格要几分钟
#   OFFSET_DEG=12                  过转对照格的偏移量（度），须 > 区域半宽 8°
#   TIMEOUT_S=900                  单格墙钟超时（秒）
#   VIEWER=0                       置 1 开 viewer
#   OUTDIR=runs/linkbar_zone/<时间戳>
#   TOPOGYM_VENV=.venv-gs121-nyx
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
  for candidate in "${TOPOGYM_VENV:-}" "$REPO/.venv-gs121-nyx" "$REPO/.venv-gs110" "$REPO/.venv"; do
    [[ -z "$candidate" ]] && continue
    if [[ -f "$candidate/bin/activate" ]]; then
      # shellcheck disable=SC1091
      source "$candidate/bin/activate"
      break
    fi
  done
fi

BACKEND="${BACKEND:-gpu}"
OFFSET_DEG="${OFFSET_DEG:-12}"
TIMEOUT_S="${TIMEOUT_S:-900}"
VIEWER="${VIEWER:-0}"
OUTDIR="${OUTDIR:-runs/linkbar_zone/$(date +%Y%m%d_%H%M%S)}"

VIEWER_ARGS=()
if [[ "$VIEWER" == "1" ]]; then
  VIEWER_ARGS=(run.viewer=true)
fi

SUITES=(offline sweep seat physical)
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
# 登记表自检。只警告不退出：它检查的是全部类别，别的类别漏登记（2026-08-27 见
# deformation 少了 cloth_unpleat / cloth_unroll）不该挡住本任务的格子。本任务那行
# 单独查，不过才退出。
python topogym/core/taxonomy.py > "$OUTDIR/taxonomy.log" 2>&1 \
  || echo "[warn] topogym/core/taxonomy.py 有类别未通过，见 $OUTDIR/taxonomy.log" >&2
if ! grep -qaF "linkbar_rotate_to_zone" "$OUTDIR/taxonomy.log"; then
  echo "[error] linkbar_rotate_to_zone 未登记在 taxonomy.CATEGORIES，见 $OUTDIR/taxonomy.log" >&2
  exit 1
fi

declare -a ROWS=()
FAIL=0

run_state() {
  local code="$1" log="$2"
  if [[ "$code" == "124" ]]; then echo "TIMEOUT"; return; fi
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

grade() {
  local tag="$1" log="$2" state="$3"
  if [[ "$state" != "ok" ]]; then
    printf '%s' "$state"
    return 1
  fi
  case "$tag" in
    offline_planner)
      expect_all "$log" "nearest_zone succeeded on 2/4" "oracle on 4/4"
      ;;
    offline_geometry)
      expect_all "$log" "overlap angles=0" "ok"
      ;;
    offline_variant)
      expect_all "$log" "[PASS] layout_randomization" "PASS"
      ;;
    sweep)
      expect_all "$log" "reached_both=True"
      ;;
    seat_none)
      expect_all "$log" "pin_zone=None" "failure_label=outside_zone"
      ;;
    seat_color_2)
      expect_all "$log" "pin_zone=color_2" "in_target=True" "at_rest=True" "terminal=True"
      ;;
    seat_color_1)
      expect_all "$log" "pin_zone=color_1" "in_target=False" "failure_label=wrong_zone"
      ;;
    physical_oracle)
      expect_all "$log" "task_success=True"
      ;;
    physical_nearest)
      expect_all "$log" "task_success=False" "failure=wrong_zone"
      ;;
    physical_offset)
      expect_all "$log" "task_success=False" "failure=outside_zone"
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
    offline_*)  grep -aE 'succeeded on|^ok$|rejection rate|skipped\(validate\)' "$log" | tail -1 ;;
    sweep)      grep -aF 'linkbar_rotate_to_zone sweep' "$log" | tail -1 ;;
    seat_*)     grep -aF 'linkbar_rotate_to_zone seat' "$log" | tail -1 ;;
    physical_*) grep -aF 'linkbar_rotate_to_zone result' "$log" | tail -1 ;;
  esac
}

run_cell() {
  local tag="$1"; shift
  local log="$OUTDIR/$tag.log"
  echo
  echo "==================== $tag ===================="
  local start; start=$(date +%s)
  # timeout 是外部程序，跑不了 shell 函数，所以 demo 名在这里展开成真命令。
  local cmd=()
  case "$1" in
    inspect)  shift; cmd=(python -B -m demos.connectivity.linkbar_rotate_to_zone_inspect_demo
                          env.genesis.backend="$BACKEND" "${VIEWER_ARGS[@]}") ;;
    physical) shift; cmd=(python -B -m demos.connectivity.linkbar_rotate_to_zone_physical_demo
                          env.genesis.backend="$BACKEND" "${VIEWER_ARGS[@]}") ;;
  esac
  timeout "${TIMEOUT_S}s" "${cmd[@]}" "$@" 2>&1 | tee "$log"
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
    offline)
      run_cell offline_planner  python -B tests/check_linkbar_planner.py
      run_cell offline_geometry python -B tests/check_linkbar_zone_geometry.py
      run_cell offline_variant  python -B tests/check_variant_rng.py
      ;;
    sweep)
      run_cell sweep inspect run.sweep_joint=true run.verbose=true
      ;;
    seat)
      run_cell seat_none  inspect run.seat_phase=none
      run_cell seat_color_2 inspect run.seat_phase=color_2
      run_cell seat_color_1 inspect run.seat_phase=color_1
      ;;
    physical)
      run_cell physical_oracle  physical run.oracle_mode=oracle
      run_cell physical_nearest physical run.oracle_mode=nearest_zone
      run_cell physical_offset  physical run.oracle_mode=oracle "run.target_offset_deg=$OFFSET_DEG"
      ;;
  esac
done

echo
echo "==================== 汇总 ===================="
for row in "${ROWS[@]}"; do
  IFS='|' read -r tag dur verdict <<< "$row"
  printf '  %-18s %-6s %s\n' "$tag" "$dur" "$verdict"
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
echo "  offline_*          不过说明代码层就坏了，后面的格子不用看。"
echo "  sweep              reached_both=True 才说明梁能到两块区域；worst_error_deg 大于"
echo "                     1° 先看 touching= 是什么挡住了它。"
echo "  seat_*             判据与相位必须一一对应。seat 行的 speed= 是沉降 30 步后的关节"
echo "                     角速度：若接近或超过 0.05，先看 touching=，再调 settle_steps，"
echo "                     最后才调 success.max_angular_speed。"
echo "  physical_oracle    task_success=True。rotate 行的 max_lag / release_drift 若触门，"
echo "                     先回退 steps_per_phase / arc_settle / release_hold，不降 steps_arc。"
echo "  physical_nearest   failure=wrong_zone 是期望结果：对照策略转错了颜色。"
echo "  physical_offset    failure=outside_zone 是期望结果：过转 ${OFFSET_DEG}° 出了 8° 的区。"
echo
echo "验收清单与实测值记录见 docs/develop/tasks/linkbar_rotate_to_zone_zh.md §7 / §8。"
echo "日志: $OUTDIR"
exit $FAIL
