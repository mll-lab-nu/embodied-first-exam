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
#   对照     linkbar: nearest；diverter: fixed；gate: greedy fixed；band_untwist: wrong_end；
#            unlink_c_ring: no_align；bar_through_hole: bypass；swap_crossing_sign: restack_same。只记录，不计入退出码
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
# 规模（每格约 10 s）：linkbar 20 格、gate 64 格、diverter 256 格（8 种离散组合 × 32）；
#   band_untwist 256 格但每格 6–13 min（FEM 绳），只跑 CORNERS= 子集；unlink_c_ring 32 格（纯刚体）全跑；
#   bar_through_hole 64 格（纯刚体）全跑；rope_unwinding 1536 格、每格 8–18 min（FEM 绳），只跑 CORNERS= 子集；
#   ring_transfer 256 格、每格 5–10 min（FEM 闭合环），只跑 CORNERS= 子集；
#   cloth_unpleat 192 格、每格分钟级（PBD 布），只跑 CORNERS= 子集。
#   cloth_fold 96 格、每格预期 20–40 s（PBD 布，4225 粒子），全跑；对照 drag / fixed_corner。
#   swap_crossing_sign 32 格、每格预计 8–10 min（FEM 绳两步），先跑 CORNERS= 子集；对照 restack_same。
# ============================================================================
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$REPO"

TASK="${1:-}"
[[ -n "$TASK" ]] && shift
# visual 组给 inspect demo 的额外参数；没有 inspect demo 的任务把 INSPECT 指向 physical demo
# 并用它自己的静态检查开关。
INSPECT_ARGS=(run.static_only=true)
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
  band_untwist)
    # FEM 绳：oracle 一格 ≈ 6 min、wrong_end ≈ 13 min。256 个角点不要全跑，用 CORNERS= 选子集。
    PHYS=demos.entangle.band_untwist_physical_pinch_demo
    INSPECT=demos.entangle.band_untwist_inspect_demo
    ORACLE_ARG=run.oracle_mode=oracle
    CONTROLS=(wrong_end); CONTROL_ARGS=(run.oracle_mode=wrong_end)
    RESULT_KEY="band_untwist_result"; SUCCESS_TOKEN="terminal=True" ;;
  swap_crossing_sign)
    # FEM 绳、两步（separate + cover）：每格预计 8–10 min。32 个角点先用 CORNERS= 选子集。
    # 没有 inspect demo：visual 组就是带录像的 oracle 格（两步走完，视频即证据）。
    # 对照 restack_same：第二步把同一根放回去，预期 terminal=False（sign_flipped=False）。
    PHYS=demos.entangle.swap_crossing_sign_physical_pinch_demo
    INSPECT=$PHYS; INSPECT_ARGS=(run.oracle_mode=oracle run.viewer=false)
    ORACLE_ARG=run.oracle_mode=oracle
    CONTROLS=(restack_same); CONTROL_ARGS=(run.oracle_mode=restack_same)
    RESULT_KEY="swap_crossing_sign_result"; SUCCESS_TOKEN="terminal=True" ;;
  unlink_c_ring)
    # 纯刚体，32 格，每格秒级到 1–2 min，全跑。
    PHYS=demos.entangle.unlink_c_ring_physical_extract_demo
    INSPECT=demos.entangle.unlink_c_ring_inspect_demo
    ORACLE_ARG=run.oracle_mode=gateway
    CONTROLS=(no_align); CONTROL_ARGS=(run.oracle_mode=no_align)
    RESULT_KEY="unlink_c_ring_physical_extract_demo result"; SUCCESS_TOKEN=" success=True" ;;
  bar_through_hole)
    # 纯刚体，64 格，每格 10–60 s，全跑。没有 inspect demo：visual 组走 physical demo 的 inspect_only。
    PHYS=demos.routing.bar_through_hole_physical_insert_demo
    INSPECT=$PHYS; INSPECT_ARGS=(run.inspect_only=true)
    ORACLE_ARG=run.oracle_mode=insert
    CONTROLS=(bypass); CONTROL_ARGS=(run.oracle_mode=bypass)
    RESULT_KEY="bar_through_hole_physical_insert_demo result"; SUCCESS_TOKEN=" success=True" ;;
  rope_unwinding)
    # FEM 绳：一格 8–18 min（随 start_turns）。1536 个角点不要全跑，用 CORNERS= 选子集。
    # 没有 inspect demo：visual 组走 physical demo 只抓起插头（max_waypoints=1）。
    PHYS=demos.routing.rope_unwinding_physical_handle_demo
    INSPECT=$PHYS; INSPECT_ARGS=(run.max_waypoints=1 run.viewer=false)
    ORACLE_ARG=run.viewer=false
    CONTROLS=(wrong_way); CONTROL_ARGS=(task.winding.orbit_direction=same)
    RESULT_KEY="rope_winding_physical_handle_demo result"; SUCCESS_TOKEN="task_success=True" ;;
  ring_transfer)
    # FEM 闭合环：carry 一格约 2000 步、5–10 min。256 个角点不要全跑，用 CORNERS= 选子集。
    # 没有 inspect demo：visual 组走 physical demo 抬离到 clear 就停（run.stop_after=clear，exit 2）。
    PHYS=demos.routing.ring_transfer_physical_demo
    INSPECT=$PHYS; INSPECT_ARGS=(run.stop_after=clear run.viewer=false)
    ORACLE_ARG=run.motion=carry
    CONTROLS=(lift_only); CONTROL_ARGS=(run.motion=lift_only)
    RESULT_KEY="ring_transfer result"; SUCCESS_TOKEN="success=True" ;;
  cloth_unpleat)
    # PBD 布：一格分钟级（首格实测后写回）。192 个角点不要全跑，用 CORNERS= 选子集。
    # 没有 inspect demo：visual 组就是带录像的 oracle 格（unfold 走完，视频即证据）。
    # 对照 shove：往褶的方向推同样距离，预期 unpleated=False。
    PHYS=demos.deformation.cloth_unpleat_physical_demo
    INSPECT=$PHYS; INSPECT_ARGS=(run.motion=unfold run.viewer=false)
    ORACLE_ARG=run.motion=unfold
    CONTROLS=(shove); CONTROL_ARGS=(run.motion=shove)
    RESULT_KEY="cloth_unpleat result"; SUCCESS_TOKEN="unpleated=True" ;;
  cloth_unroll)
    # PBD 布：cloth_unpleat 实测一格 19–29 s，本任务行程长一倍，预期半分钟级。96 个角点可以全跑。
    # 没有 inspect demo：visual 组就是带录像的 oracle 格（unroll 走完，视频即证据）。
    # 对照 shove：朝横梁推、走满可用余量，预期 unrolled=False；对照 overpull：多拉 1.6 倍，
    # 预期尾端被扯断（torn=True）判失败。
    PHYS=demos.deformation.cloth_unroll_physical_demo
    INSPECT=$PHYS; INSPECT_ARGS=(run.motion=unroll run.viewer=false)
    ORACLE_ARG=run.motion=unroll
    CONTROLS=(shove overpull); CONTROL_ARGS=(run.motion=shove run.motion=overpull)
    RESULT_KEY="cloth_unroll result"; SUCCESS_TOKEN="unrolled=True" ;;
  cloth_fold)
    # PBD 布：cloth_unpleat 实测一格 14–29 s，本任务粒子 4225（两倍）、步数相近，预期 20–40 s。96 个角点可以全跑。
    # 没有 inspect demo：visual 组就是带录像的 oracle 格（fold 走完，视频即证据）。
    # 对照 drag：同一条弧线贴桌面拖、不抬，预期 folded=False；对照 fixed_corner：无视指令永远折 far_left，
    # 预期只有 corner=far_left 的格 folded=True（96 格里 24 格）；对照 fixed_fold：无视指令的折痕位置永远
    # 角对角折，预期只有 fold_fraction=1.0 的格 folded=True（96 格里 32 格）。
    PHYS=demos.deformation.cloth_fold_physical_demo
    INSPECT=$PHYS; INSPECT_ARGS=(run.motion=fold run.viewer=false)
    ORACLE_ARG=run.motion=fold
    CONTROLS=(drag fixed_corner fixed_fold)
    CONTROL_ARGS=(run.motion=drag run.motion=fixed_corner run.motion=fixed_fold)
    RESULT_KEY="cloth_fold result"; SUCCESS_TOKEN="folded=True" ;;
  rope_winding)
    # FEM 绳：一格 10–40 min（随 turns）。1536 个角点不要全跑，用 CORNERS= 选子集。
    # 没有 inspect demo：visual 组走 physical demo 只抓起插头（max_waypoints=1）。
    PHYS=demos.routing.rope_winding_physical_handle_demo
    INSPECT=$PHYS; INSPECT_ARGS=(run.max_waypoints=1 run.viewer=false)
    ORACLE_ARG=run.viewer=false
    CONTROLS=(wrong_way); CONTROL_ARGS=(task.winding.orbit_direction=opposite)
    RESULT_KEY="rope_winding_physical_handle_demo result"; SUCCESS_TOKEN="task_success=True" ;;
  *)
    echo "用法：$0 <linkbar_rotate_to_zone|diverter_route_ball|gate_cage_ball|band_untwist|swap_crossing_sign|unlink_c_ring|bar_through_hole|rope_unwinding|ring_transfer|rope_winding|cloth_unpleat|cloth_unroll|cloth_fold> [oracle visual 对照组...]" >&2
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
      cmd=(python -B -m "$INSPECT" "${common[@]}" "${INSPECT_ARGS[@]}"
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
      else verdict="FAIL $(result_line "$log" | grep -aoE 'failure(_reason|_label)?=[A-Za-z_]+')"; FAIL=1; fi ;;
    *)
      if [[ "$state" != "ok" ]]; then verdict="$state"
      elif result_line "$log" | grep -qaF "$SUCCESS_TOKEN"; then verdict="success"
      else verdict="$(result_line "$log" | grep -aoE 'failure(_reason|_label)?=[A-Za-z_]+' | sed 's/failure[a-z_]*=//')"; fi ;;
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
# CSV 字段按 RFC 4180 加引号。**必须加**：`name` 是逗号分隔的轴取值串
# （grasp.corner=far_left,goal.fold_fraction=1.0,…），不加引号时表头 7 列、数据行 11 列，
# 任何按列解析的读者拿到的都是错位的值（2026-09-08 实测：cloth_fold 的 fixed_fold 列
# 按列读是 30/96，按每格日志重数是 32/96）。verdict 也可能含逗号——判定器的
# `gates=` 在多条门同时挂时是逗号连接的。
csv_field() { printf '"%s"' "${1//\"/\"\"}"; }
{
  printf 'id,name,margins'
  for group in "${SELECTED[@]}"; do printf ',%s' "$group"; done
  printf '\n'
  for id in "${IDS[@]}"; do
    printf '%s,%s,%s' "$id" "$(csv_field "${NAME[$id]}")" "$(csv_field "${MARGINS[$id]}")"
    for group in "${SELECTED[@]}"; do printf ',%s' "$(csv_field "${VERDICT[${group}_${id}]:-}")"; done
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
