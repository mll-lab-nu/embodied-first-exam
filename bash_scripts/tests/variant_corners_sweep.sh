#!/usr/bin/env bash
# ============================================================================
# 变体包络角点 sweep：把 tests/check_variant_corners.py 构造出的角点逐个送进物理。
#
# 随机 sweep（<task>_variation_sweep.sh）跑的是包络内部的随机点，可解性判据最紧的
# 顶点（可达上限、时序富余 0、旁通间隙最窄……）抽不到；这里按边界值测试的做法，
# 把每条连续轴的两个端点、每条离散轴的全部取值做全组合，每个角点一格。
#
# 每格走 demo 的固定布局路径：run.randomize_layout=false 加 task.<路径>=<值> 覆盖，
# 派生量（fork_origin_x、release_y、init_angle_deg……）也一并覆盖成离线算好的值。
# 不碰 layout_randomization.py，随机化路径与 seed→变体映射完全不受影响。
#
# 组（默认只跑 oracle）：
#   oracle   oracle 规则 → 每格必须 success=True，这是「oracle 覆盖包络边界」的直接证据
#   visual   inspect demo 建场景不步进，录一帧 → 人眼看极端几何有无穿模
#   对照     linkbar: nearest；diverter: fixed；gate: greedy fixed。只记录，不计入退出码
#
# 用法：
#   bash bash_scripts/tests/variant_corners_sweep.sh diverter_route_ball            # oracle 组
#   bash bash_scripts/tests/variant_corners_sweep.sh gate_cage_ball oracle greedy
#   CORNERS="c000 c017" bash bash_scripts/tests/variant_corners_sweep.sh linkbar_rotate_to_zone oracle visual
#   DRY_RUN=1 bash bash_scripts/tests/variant_corners_sweep.sh gate_cage_ball        # 只打印命令
#
# 可调环境变量：CORNERS（角点 id 列表，默认全部）、BACKEND=gpu、TIMEOUT_S=900、VIEWER=0、
#   OUTDIR=runs/<task>_corners/<时间戳>、TOPOGYM_VENV、DRY_RUN=0
#
# 产出：<OUTDIR>/corners.tsv（角点清单：id、名字、Hydra 覆盖、离线各判据读数）、
#   <group>_<id>.log、visual_<id>.mp4、summary.csv。
# 退出码：任一 oracle 格非 success，或任一格 RAISED/TIMEOUT，即非 0。刻意不用 set -e。
# 规模（每格约 10 s）：linkbar 20 格、gate 64 格、diverter 256 格（8 种离散组合 × 32）。
# ============================================================================
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$REPO"

TASK="${1:-}"
[[ -n "$TASK" ]] && shift
case "$TASK" in
  linkbar_rotate_to_zone)
    PHYS=demos.connectivity.linkbar_rotate_to_zone_physical_demo
    INSPECT=demos.connectivity.linkbar_rotate_to_zone_inspect_demo
    ORACLE_ARG=run.oracle_mode=oracle
    CONTROLS=(nearest); CONTROL_ARGS=(run.oracle_mode=nearest_zone)
    RESULT_KEY="linkbar_rotate_to_zone result"; SUCCESS_TOKEN="task_success=True" ;;
  diverter_route_ball)
    PHYS=demos.connectivity.diverter_route_ball_physical_route_demo
    INSPECT=demos.connectivity.diverter_route_ball_inspect_demo
    ORACLE_ARG=run.oracle_mode=oracle
    CONTROLS=(fixed); CONTROL_ARGS=(run.oracle_mode=fixed_direction)
    RESULT_KEY="diverter_route_ball_physical_route_demo result"; SUCCESS_TOKEN="success=True" ;;
  gate_cage_ball)
    PHYS=demos.connectivity.gate_cage_ball_physical_gate_demo
    INSPECT=demos.connectivity.gate_cage_ball_inspect_demo
    ORACLE_ARG=run.trigger=oracle
    CONTROLS=(greedy fixed); CONTROL_ARGS=(run.trigger=greedy run.trigger=fixed_delay)
    RESULT_KEY="gate_cage_ball_physical_gate_demo result"; SUCCESS_TOKEN="success=True" ;;
  *)
    echo "用法：$0 <linkbar_rotate_to_zone|diverter_route_ball|gate_cage_ball> [oracle visual 对照组...]" >&2
    exit 1 ;;
esac

SUITES=(oracle visual "${CONTROLS[@]}")
if [[ $# -gt 0 ]]; then SELECTED=("$@"); else SELECTED=(oracle); fi
for name in "${SELECTED[@]}"; do
  case " ${SUITES[*]} " in
    *" $name "*) ;;
    *) echo "[error] 未知组 '$name'；$TASK 可选：${SUITES[*]}" >&2; exit 1 ;;
  esac
done

control_arg() {  # 组名 -> 该对照规则的 Hydra 参数
  local i
  for i in "${!CONTROLS[@]}"; do
    [[ "${CONTROLS[$i]}" == "$1" ]] && { echo "${CONTROL_ARGS[$i]}"; return; }
  done
}

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

BACKEND="${BACKEND:-gpu}"
TIMEOUT_S="${TIMEOUT_S:-900}"
VIEWER="${VIEWER:-0}"
DRY_RUN="${DRY_RUN:-0}"
OUTDIR="${OUTDIR:-runs/${TASK}_corners/$(date +%Y%m%d_%H%M%S)}"

VIEWER_ARGS=()
[[ "$VIEWER" == "1" ]] && VIEWER_ARGS=(run.viewer=true)

if ! python -c "import topogym" 2>/dev/null; then
  echo "[error] 无法 import topogym。请先激活项目 venv（或设 TOPOGYM_VENV）。" >&2
  exit 1
fi
if [[ "$DRY_RUN" != "1" ]] && ! python -c "import genesis" 2>/dev/null; then
  echo "[error] 无法 import genesis。本脚本要建真实场景，必须在项目 venv 里跑。" >&2
  exit 1
fi
mkdir -p "$OUTDIR"

# 离线门先过，同时产出角点清单：每个角点经派生、校验、各判据读数，并经 Hydra compose
# 复现一致。任一角点被拒或判据不过，这里就停。
MANIFEST="$OUTDIR/corners.tsv"
if ! python -B tests/check_variant_corners.py --task "$TASK" --manifest "$MANIFEST" > "$OUTDIR/offline.log" 2>&1; then
  echo "[error] tests/check_variant_corners.py 未通过，见 $OUTDIR/offline.log" >&2
  exit 1
fi

# 读清单：id -> 名字 / 覆盖 / 读数。CORNERS 过滤 id。
declare -A NAME OVERRIDES MARGINS
IDS=()
while IFS=$'\t' read -r _task id name overrides margins; do
  [[ -z "$id" ]] && continue
  if [[ -n "${CORNERS:-}" ]]; then
    case " $CORNERS " in *" $id "*) ;; *) continue ;; esac
  fi
  IDS+=("$id"); NAME[$id]="$name"; OVERRIDES[$id]="$overrides"; MARGINS[$id]="$margins"
done < "$MANIFEST"
if [[ ${#IDS[@]} -eq 0 ]]; then
  echo "[error] 清单里没有可跑的角点（CORNERS='${CORNERS:-}'）" >&2
  exit 1
fi

FAIL=0
declare -A VERDICT

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

result_line() { grep -aF "$RESULT_KEY" "$1" | tail -1; }

run_cell() {
  local group="$1" id="$2"
  local tag="${group}_${id}" log="$OUTDIR/${group}_${id}.log"
  echo
  echo "==================== $tag  ${NAME[$id]} ===================="
  local start; start=$(date +%s)
  # shellcheck disable=SC2206  # 覆盖串是空格分隔的 Hydra 令牌，需要分词
  local overrides=(${OVERRIDES[$id]})
  local common=(env.genesis.backend="$BACKEND" "${VIEWER_ARGS[@]}"
                run.randomize_layout=false "run.variant_id=corner_${id}" "${overrides[@]}")
  local cmd=()
  case "$group" in
    visual)
      cmd=(python -B -m "$INSPECT" "${common[@]}" run.static_only=true
           recording=default "recording.path=$OUTDIR/visual_${id}.mp4" recording.camera=oblique) ;;
    oracle)
      cmd=(python -B -m "$PHYS" "${common[@]}" "$ORACLE_ARG") ;;
    *)
      cmd=(python -B -m "$PHYS" "${common[@]}" "$(control_arg "$group")") ;;
  esac
  if [[ "$DRY_RUN" == "1" ]]; then
    echo "${cmd[*]}"
    VERDICT[$tag]="dry"
    return
  fi
  timeout "${TIMEOUT_S}s" "${cmd[@]}" 2>&1 | tee "$log"
  local code=${PIPESTATUS[0]}
  local dur=$(( $(date +%s) - start ))
  local state; state="$(run_state "$code" "$log")"

  local verdict=""
  case "$group" in
    visual)
      if [[ "$state" == "ok" && -s "$OUTDIR/visual_${id}.mp4" ]]; then verdict="ok (看 mp4)"; else verdict="FAIL $state"; FAIL=1; fi ;;
    oracle)
      if [[ "$state" != "ok" ]]; then verdict="FAIL $state"; FAIL=1
      elif result_line "$log" | grep -qaF "$SUCCESS_TOKEN"; then verdict="PASS"
      else verdict="FAIL $(result_line "$log" | grep -aoE 'failure=[A-Za-z_]+')"; FAIL=1; fi ;;
    *)
      if [[ "$state" != "ok" ]]; then verdict="$state"
      elif result_line "$log" | grep -qaF "$SUCCESS_TOKEN"; then verdict="success"
      else verdict="$(result_line "$log" | grep -aoE 'failure=[A-Za-z_]+' | sed 's/failure=//')"; fi ;;
  esac
  VERDICT[$tag]="$verdict"
  echo "---- $tag (${dur}s): $verdict"
}

echo "task=$TASK outdir=$OUTDIR backend=$BACKEND corners=${#IDS[@]} groups=[${SELECTED[*]}]"

for group in "${SELECTED[@]}"; do
  for id in "${IDS[@]}"; do
    run_cell "$group" "$id"
  done
done

echo
echo "==================== 汇总 ===================="
csv="$OUTDIR/summary.csv"
{
  printf 'id,name,margins'
  for group in "${SELECTED[@]}"; do printf ',%s' "$group"; done
  printf '\n'
  for id in "${IDS[@]}"; do
    printf '%s,%s,%s' "$id" "${NAME[$id]}" "${MARGINS[$id]}"
    for group in "${SELECTED[@]}"; do printf ',%s' "${VERDICT[${group}_${id}]:-}"; done
    printf '\n'
  done
} > "$csv"

for group in "${SELECTED[@]}"; do
  n=0; n_ok=0; bad=()
  for id in "${IDS[@]}"; do
    v="${VERDICT[${group}_${id}]:-}"
    [[ -z "$v" || "$v" == "dry" ]] && continue
    n=$((n + 1))
    case "$group" in
      oracle) [[ "$v" == "PASS" ]] && n_ok=$((n_ok + 1)) || bad+=("$id ${NAME[$id]} -> $v") ;;
      visual) [[ "$v" == ok* ]] && n_ok=$((n_ok + 1)) || bad+=("$id ${NAME[$id]} -> $v") ;;
      *)      [[ "$v" == "success" ]] && n_ok=$((n_ok + 1)) ;;
    esac
  done
  [[ $n -eq 0 ]] && continue
  echo "  $group: $n_ok / $n"
  for b in "${bad[@]}"; do echo "      $b"; done
done
echo
echo "怎么读："
echo "  oracle   全部 PASS 才说明 oracle 覆盖到包络的顶点；FAIL 的角点看 name 里哪几条轴在端点、"
echo "           margins 里哪条判据贴 0，再看其 log 的 result 行。处置按 09-02 的原则：收窄该轴区间、"
echo "           或修 oracle 的执行参数（如 approach_z），不是加重试。"
echo "  对照     成功率远离 1/2 只说明角点集合不是均匀样本，不据此回调包络。"
echo "summary: $csv"
echo "清单: $MANIFEST"
echo "日志: $OUTDIR"
exit $FAIL
