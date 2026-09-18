#!/usr/bin/env bash
# ============================================================================
# cloth_unpleat 变体生成实验（variation_axes_plain_zh.md §6.2 第 9 步）。
#
# 每个 seed 两格：
#   oracle   physical demo 全程（run.motion=unfold）：抓布带自由端、贴桌面拉出褶里存的料、松手
#            → 必须 unpleated=True 且 diverged=False。同时录斜视机位 visual_s<seed>.mp4：
#            布带位置、褶宽、自由端在 +y 还是 −y 端（pull_side 镜像）应逐 seed 不同。
#            PBD 布一格便宜，所以不单设 visual 组，视频就是 oracle 格的副产品。
#   shove    对照组：run.motion=shove，往褶的方向推同样距离 → 只记录；预期 unpleated=False
#   single_pull  对照组：两道褶时只拉第一段 → 只记录；两道褶的格预期 unpleated=False
#            （回收比 ≈ 0：搬动了同样多的布却什么也没展开）。
#
# 变体参数来自 task 配置末尾的 variation 块，由 run.randomize_layout=true run.seed=<seed>
# 触发；demo 打印一行
#   cloth_unpleat variant seed=… layout=… pleats=… gap=… lead=… tail=… L=…
#     center_x=… center_y=… inset=… pull_scale=… flip=… stored_mm=… pull_mm=… end_y=…
# 与一行 `cloth_unpleat checks …`（七行可行性判据读数）。本脚本解析 variant 行进汇总表。
#
# **成本随抽到的构型差一个数量级**（GPU 实测，oracle 组带录像）：
#   单褶 / 平行褶  3.5k 粒子、4 子步     21–31 s 一格
#   十字          ~60k 粒子、16 子步    280–315 s 一格（09-13，布 22–24.5 cm 见方；
#                                        09-11 布更小时是 102–213 s）
# 十字要 1 mm 粒径 + 16 子步才能让九层叠层立得住（理由与实测表见任务 yaml 的
# cloth.cross.solver）。三种构型等概率抽，十个 seed 的 oracle 组约 20 分钟，三组约 40 分钟。
# **默认无头。** VIEWER=1 可开窗。
#
# 用法：
#   bash bash_scripts/tests/cloth_unpleat_variation_sweep.sh oracle          # seed 0–9
#   SEEDS="0 1 2" bash bash_scripts/tests/cloth_unpleat_variation_sweep.sh shove
#   bash bash_scripts/tests/cloth_unpleat_variation_sweep.sh                 # 两组
#
# 可调环境变量：
#   SEEDS="0 1 2 3 4 5 6 7 8 9"
#   BACKEND=gpu
#   TIMEOUT_S=2400   一格的上限。十字格实测最长 315 s，留足余量。
#   VIEWER=0
#   OUTDIR=runs/cloth_unpleat_variation/<时间戳>
#   TOPOGYM_VENV=.venv-gs121-nyx
#   SKIP_OFFLINE=1  跳过离线门（13–14 分钟）。只在你刚跑过 tests/check_variant_rng.py
#                   与本任务几何门时用；默认 0，照跑。
#
# 产出：<OUTDIR>/<group>_s<seed>.log、visual_s<seed>.mp4、summary.csv。
# 退出码：任一 oracle 格非 unpleated=True，或任一格 RAISED/TIMEOUT，即非 0。
# shove 格不计入退出码。刻意不用 set -e。
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
TIMEOUT_S="${TIMEOUT_S:-2400}"
VIEWER="${VIEWER:-0}"
OUTDIR="${OUTDIR:-runs/cloth_unpleat_variation/$(date +%Y%m%d_%H%M%S)}"

VIEWER_ARGS=()
[[ "$VIEWER" == "1" ]] && VIEWER_ARGS=(run.viewer=true)

SUITES=(oracle shove single_pull)
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

# 离线门先过：变体块的包络、派生、拒绝率；判据两侧、192 角点七行。约半分钟。
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
if [[ "${SKIP_OFFLINE:-0}" != "1" ]] && ! python -B tests/check_cloth_unpleat_geometry.py >> "$OUTDIR/offline.log" 2>&1; then
  echo "[error] tests/check_cloth_unpleat_geometry.py 未通过，见 $OUTDIR/offline.log" >&2
  exit 1
fi

FAIL=0
declare -A VARIANT ORACLE SHOVE SINGLEPULL SINGLE RECOVERED SHIFT ACROSS

run_state() {
  local code="$1" log="$2"
  if [[ "$code" == "124" ]]; then echo "TIMEOUT"; return; fi
  grep -qaiE "^Traceback" "$log" && { echo "RAISED"; return; }
  echo "ok"
}

variant_line() { grep -aF "cloth_unpleat variant seed=" "$1" | tail -1; }
result_line()  { grep -aF "cloth_unpleat result" "$1" | tail -1; }
field()        { grep -aoE "$2=[^ ]+" <<< "$1" | head -1 | sed "s/$2=//"; }

run_cell() {
  local group="$1" seed="$2"; shift 2
  local tag="${group}_s${seed}" log="$OUTDIR/${group}_s${seed}.log"
  echo
  echo "==================== $tag ===================="
  local start; start=$(date +%s)
  local common=(python -B -m demos.deformation.cloth_unpleat_physical_demo
                env.genesis.backend="$BACKEND" run.viewer=false "${VIEWER_ARGS[@]}"
                run.randomize_layout=true "run.seed=$seed")
  local cmd=()
  case "$group" in
    oracle)
      cmd=("${common[@]}" run.motion=unfold
           # every_n_steps=3：dt 0.01 × 3 = 每帧 30 ms，30 fps 就是真实时间回放。默认的 1 是
           # 3.3 倍慢放，十字格视频 2–3 分钟（2026-09-13）。抽帧不改物理和判据。
           recording=default "recording.path=$OUTDIR/visual_s${seed}.mp4" recording.camera=oblique
           recording.every_n_steps=3) ;;
    shove)
      cmd=("${common[@]}" run.motion=shove) ;;
    single_pull)
      cmd=("${common[@]}" run.motion=single_pull) ;;
  esac
  timeout "${TIMEOUT_S}s" "${cmd[@]}" "$@" 2>&1 | tee "$log"
  local code=${PIPESTATUS[0]}
  local dur=$(( $(date +%s) - start ))
  local state; state="$(run_state "$code" "$log")"
  local v; v="$(variant_line "$log")"
  [[ -n "$v" ]] && VARIANT[$seed]="${v#cloth_unpleat variant }"
  local r; r="$(result_line "$log")"

  local verdict=""
  case "$group" in
    oracle)
      if [[ "$state" != "ok" ]]; then verdict="FAIL $state"; FAIL=1
      elif grep -qaF "unpleated=True" <<< "$r" && grep -qaF "diverged=False" <<< "$r"; then verdict="PASS"
      elif grep -qaF "aborted reason=" "$log"; then verdict="FAIL $(grep -aoE 'aborted reason=[a-z_]+' "$log" | tail -1 | sed 's/aborted reason=//')"; FAIL=1
      else verdict="FAIL gates=$(field "$r" gates) diverged=$(field "$r" diverged)"; FAIL=1; fi
      ORACLE[$seed]="$verdict"
      SINGLE[$seed]="$(field "$r" single_layer_frac)"
      RECOVERED[$seed]="$(field "$r" recovered_frac)"
      SHIFT[$seed]="$(field "$r" band_shift_mm)"
      ACROSS[$seed]="$(field "$r" across_excess_mm)" ;;
    shove)
      if [[ "$state" != "ok" ]]; then verdict="$state"
      elif grep -qaF "unpleated=True" <<< "$r"; then verdict="success(!)"
      else verdict="failed recovered=$(field "$r" recovered_frac)"; fi
      SHOVE[$seed]="$verdict" ;;
    single_pull)
      # 只拉第一段。两道褶时另一道没打开，单层格占比过不了 → 应判失败；
      # 一道褶时它就是任务本身，记 same-as-oracle，不进成败统计。
      # 十字不等于 single，会照常当对照组：只拉一条边，另一条轴的料还收着。
      if [[ "$state" != "ok" ]]; then verdict="$state"
      elif [[ "$(field "$(variant_line "$log")" layout)" == "single" ]]; then verdict="n/a(1 pleat)"
      elif grep -qaF "unpleated=True" <<< "$r"; then verdict="success(!)"
      else verdict="failed single=$(field "$r" single_layer_frac)"; fi
      SINGLEPULL[$seed]="$verdict" ;;
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
echo "seed,layout,pleats,gap,lead,tail,L,center_x,center_y,inset,pull_scale,flip,stored_mm,pull_mm,end_y,single_layer_frac,recovered_frac,band_shift_mm,across_excess_mm,oracle,shove,single_pull" > "$csv"
n_shove=0; n_shove_failed=0; n_sp=0; n_sp_failed=0
for seed in $SEEDS; do
  v="${VARIANT[$seed]:-}"
  f() { field "$v" "$1"; }
  printf '  seed %-3s %-9s pleats=%-13s gap=%-5s L=%-5s center=(%s,%s) ps=%s flip=%s stored=%s pull=%s | single=%s recovered=%s shift=%s across=%s | oracle=%s shove=%s single_pull=%s\n' \
    "$seed" "$(f layout)" "$(f pleats)" "$(f gap)" "$(f L)" \
    "$(f center_x)" "$(f center_y)" "$(f pull_scale)" "$(f flip)" "$(f stored_mm)" "$(f pull_mm)" \
    "${SINGLE[$seed]:--}" "${RECOVERED[$seed]:--}" "${SHIFT[$seed]:--}" "${ACROSS[$seed]:--}" \
    "${ORACLE[$seed]:--}" "${SHOVE[$seed]:--}" "${SINGLEPULL[$seed]:--}"
  echo "$seed,$(f layout),$(csv_field "$(f pleats)"),$(f gap),$(f lead),$(f tail),$(f L),$(f center_x),$(f center_y),$(f inset),$(f pull_scale),$(f flip),$(csv_field "$(f stored_mm)"),$(csv_field "$(f pull_mm)"),$(csv_field "$(f end_y)"),${SINGLE[$seed]:-},${RECOVERED[$seed]:-},${SHIFT[$seed]:-},${ACROSS[$seed]:-},$(csv_field "${ORACLE[$seed]:-}"),$(csv_field "${SHOVE[$seed]:-}"),$(csv_field "${SINGLEPULL[$seed]:-}")" >> "$csv"
  if [[ -n "${SHOVE[$seed]:-}" ]]; then
    n_shove=$((n_shove + 1)); [[ "${SHOVE[$seed]}" == failed* ]] && n_shove_failed=$((n_shove_failed + 1))
  fi
  if [[ "${SINGLEPULL[$seed]:-}" == failed* || "${SINGLEPULL[$seed]:-}" == success* ]]; then
    n_sp=$((n_sp + 1)); [[ "${SINGLEPULL[$seed]}" == failed* ]] && n_sp_failed=$((n_sp_failed + 1))
  fi
done
if [[ $n_shove -gt 0 ]]; then
  echo "  shove 判失败: $n_shove_failed / $n_shove（预期全部：往褶推不放料，回收比 ≈ 0）"
fi
if [[ $n_sp -gt 0 ]]; then
  echo "  single_pull 判失败: $n_sp_failed / $n_sp（只统计两道褶与十字的格；预期全部：另一道褶／另一条轴没打开）"
fi
echo
echo "怎么读："
echo "  oracle   全部 PASS 才说明 oracle 覆盖了包络；FAIL 的 seed 看其 log 的 result 行（gates、attach_error_mm、"
echo "           arm_pos_err_mm）与 variant 行（side=−1、center_x 大、end_y 接近可达门的格最可能出问题）；"
echo "           aborted reason=material_already_released / layers_came_apart 是起始态守卫，褶在静置时自己散了。"
echo "  视频     打开 $OUTDIR/visual_s*.mp4：布带位置、褶宽、自由端在哪一端应逐 seed 不同，且无穿模。"
echo "  shove    应全部 failed；success(!) 说明往褶推也判成功，判据有问题。"
echo "  single_pull  两道褶的格应全部 failed —— 它是取代 pull_side 的防捷径证据（2026-09-08 会上把"
echo "           「从哪一端拉」移出任务之后，「要做几步」成了必须读场景才知道的东西）。"
echo "           success(!) 说明第二道褶没有真的增加要做的事，回头看它是不是太小或太靠边，不是调门槛。"
echo "summary: $csv"
echo "日志: $OUTDIR"
exit $FAIL
