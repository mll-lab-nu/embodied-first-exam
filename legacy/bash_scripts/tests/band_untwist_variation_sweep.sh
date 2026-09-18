#!/usr/bin/env bash
# ============================================================================
# band_untwist 变体生成实验（variation_axes_plain_zh.md §6.2 第 4 步；band_untwist_zh.md §8）。
#
# 绳出生时自己压过自己 1 或 2 次，四种形态（task.band.shape）：8 字、6 字（1 个交叉），
# 麻花、O|-|O（2 个交叉）。oracle 开局在沉降后的实测绳上规划整条序列，步数预算 = 序列长度。
#
# 四组：
#   visual    inspect demo 建场景不沉降，录几帧静态画面 → 人眼看 visual_s<seed>.mp4：
#             形态、朝向、位置、上下关系逐 seed 可分，有无穿模。
#   oracle    physical demo，每步抓某个交叉处压在上面那股的插头 → 必须 success=True，
#             且 off_plan=None（每步之后实测交叉序列 = 规划预测的）。
#   wrong_end physical demo，在 oracle 要解的那个交叉上抓下股那一侧的插头 → 只记录；
#             预期判失败，多数 crossing_added。下股那侧插头够不着（抬升超顶）的格没有动作，
#             记 n/a（不适用），不算成功也不算失败。
#   one_move  oracle 只给一步 → 开局规划 1 步的格成功，2 步的格 crossing_left
#             （量出「全部解开才算成功」在起作用）。与预期不符计入退出码。
#
# **seed 怎么选**：默认不用固定的 0–9，而是先离线把 seed 0–199 逐个随机化，按形态各取前几个
# （seed_table.tsv 写进 OUTDIR，确定性）：visual / oracle 每形态 PER_SHAPE 个，
# wrong_end 每形态 WRONG_PER_SHAPE 个，one_move 取两个 2 交叉形态各 PER_SHAPE 个。
# 设了 SEEDS 则四组都用 SEEDS。
#
# demo 打印一行（supervision/band_untwist.py 的 variant_line，两个 demo 共用）
#   band_untwist variant seed=… shape=… heading=… cx=… cy=… <该形态的叶子> crossings=… planned=… lift_pred=…
# 其中 planned 是出生形状上直线模型的步数；结果行的 planned 是沉降后实测绳上的步数。本脚本两个都记。
#
# **成本**：FEM 绳，随机化后的绳长 47–91 cm（节点数随之涨）。4090 独占显卡时（2026-09-13 实测）：
# visual 38–156 s；oracle 一步的格 4–6 min，两步的 O|-|O 10–11 min，20 格约 2.3 h。
# **卡被别的进程分掉时慢 4 倍**（同一格 O|-|O 在另一用户占 5.3 GB 时只有 0.76 FPS、超过 2400 s），
# 所以 TIMEOUT_S 默认 5400。默认四组（20 + 20 + 8 + 10 格）独占约 5–6 h。
# **默认无头。** VIEWER=1 可开窗，但不加 run.keep_open。
#
# 用法：
#   bash bash_scripts/tests/band_untwist_variation_sweep.sh visual oracle
#   PER_SHAPE=2 bash bash_scripts/tests/band_untwist_variation_sweep.sh oracle one_move
#   SEEDS="0 1 2" bash bash_scripts/tests/band_untwist_variation_sweep.sh wrong_end
#   bash bash_scripts/tests/band_untwist_variation_sweep.sh                       # 全部四组
#
# 可调环境变量：
#   SEEDS=""             空 = 按 seed 表分层取
#   PER_SHAPE=5  WRONG_PER_SHAPE=2
#   BACKEND=gpu
#   TIMEOUT_S=5400
#   VIEWER=0
#   OUTDIR=runs/band_untwist_variation/<时间戳>
#   TOPOGYM_VENV=.venv-gs121-nyx
#   SKIP_OFFLINE=1  跳过离线门（13–14 分钟）。只在你刚跑过 tests/check_variant_rng.py
#                   与本任务两个离线门时用；默认 0，照跑。
#
# 产出：<OUTDIR>/seed_table.tsv、<group>_s<seed>.log、visual_s<seed>.mp4、summary.csv。
# 退出码：任一 oracle 格非 success=True，或 one_move 与预期不符，或任一格 RAISED/TIMEOUT，即非 0。
# wrong_end 格不计入退出码。刻意不用 set -e。
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

SEEDS="${SEEDS:-}"
PER_SHAPE="${PER_SHAPE:-5}"
WRONG_PER_SHAPE="${WRONG_PER_SHAPE:-2}"
BACKEND="${BACKEND:-gpu}"
TIMEOUT_S="${TIMEOUT_S:-5400}"
VIEWER="${VIEWER:-0}"
OUTDIR="${OUTDIR:-runs/band_untwist_variation/$(date +%Y%m%d_%H%M%S)}"

VIEWER_ARGS=()
[[ "$VIEWER" == "1" ]] && VIEWER_ARGS=(run.viewer=true)

SUITES=(visual oracle wrong_end one_move)
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

# 离线门先过：变体块的包络、派生区间、拒绝率；形态几何、计数、交叉序列、规划器；直线模型。
# SKIP_OFFLINE=1 跳过这一段（2026-09-09）。默认仍然跑：不知情的调用方保持原来的安全性。
# 实测这一段 13–14 分钟（13 个任务的包络全跑一遍）；调用方刚手工跑过同一个门时，
# 重复跑就是纯等待。跳过时把原因写进 offline.log，免得事后看目录以为门没跑过。
if [[ "${SKIP_OFFLINE:-0}" == "1" ]]; then
  echo "SKIP_OFFLINE=1：调用方声明已跑过 tests/check_variant_rng.py 与本任务两个离线门，本轮跳过" \
    > "$OUTDIR/offline.log"
elif ! python -B tests/check_variant_rng.py > "$OUTDIR/offline.log" 2>&1; then
  echo "[error] tests/check_variant_rng.py 未通过，见 $OUTDIR/offline.log" >&2
  exit 1
fi
if [[ "${SKIP_OFFLINE:-0}" != "1" ]]; then
  for gate in tests/check_band_untwist_geometry.py tests/check_band_untwist_sequence.py; do
    if ! python -B "$gate" >> "$OUTDIR/offline.log" 2>&1; then
      echo "[error] $gate 未通过，见 $OUTDIR/offline.log" >&2
      exit 1
    fi
  done
fi

# seed 表：seed、形态、交叉数、出生形状上的规划步数。随机化与 demo 用同一个函数，
# 所以表里的形态就是 demo 会建的形态。
python -B - > "$OUTDIR/seed_table.tsv" <<'PY'
from omegaconf import OmegaConf

from topogym.generation.layout_randomization import randomize_task_cfg
from topogym.tasks_legacy.entangle.band_untwist import BandUntwistLayout

base = OmegaConf.create({"task": OmegaConf.load("configs/task_configs/band_untwist_topogym_tabletop_v1.yaml")})
print("seed\tshape\tcrossings\tplanned")
for seed in range(200):
    task = randomize_task_cfg(base, "band_untwist", seed).task
    layout = BandUntwistLayout(task)
    print(f"{seed}\t{task.band.shape}\t{len(layout.declared_sequence()) // 2}\t{len(layout.plan().moves)}")
PY
if [[ ! -s "$OUTDIR/seed_table.tsv" ]]; then
  echo "[error] seed 表没生成（见上面的 Python 报错）" >&2
  exit 1
fi

# 按形态取 seed 表里最前面的 n 个。
seeds_for() {
  local n="$1"; shift
  local shape out=()
  for shape in "$@"; do
    out+=($(awk -F'\t' -v s="$shape" -v n="$n" 'NR > 1 && $2 == s && c < n { print $1; c++ }' "$OUTDIR/seed_table.tsv"))
  done
  printf '%s\n' "${out[@]}" | sort -n | tr '\n' ' '
}
group_seeds() {
  if [[ -n "$SEEDS" ]]; then echo "$SEEDS"; return; fi
  case "$1" in
    visual|oracle) seeds_for "$PER_SHAPE" eight six twist curls ;;
    wrong_end)     seeds_for "$WRONG_PER_SHAPE" eight six twist curls ;;
    one_move)      seeds_for "$PER_SHAPE" twist curls ;;
  esac
}

FAIL=0
declare -A VARIANT RESULT GRASPED LIFTS PLANNED GT
ALL_SEEDS=()

run_state() {
  local code="$1" log="$2"
  if [[ "$code" == "124" ]]; then echo "TIMEOUT"; return; fi
  grep -qaiE "^Traceback" "$log" && { echo "RAISED"; return; }
  # physical demo 用退出码表达 solved 与否（wrong_end 预期非 0），不算异常
  echo "ok"
}

variant_line() { grep -aF "band_untwist variant seed=" "$1" | tail -1; }
result_line()  { grep -aF "band_untwist_result" "$1" | tail -1; }
# 每一步一行；取全部（2 交叉的格有两步）。
move_field()   { grep -aF "band_untwist_move " "$1" | grep -aoE " $2=[^ ]+" | sed "s/ $2=//" | paste -sd, -; }
field()        { echo "$1" | grep -aoE "(^| )$2=[^ ]+" | sed -E "s/^ ?$2=//"; }

run_cell() {
  local group="$1" seed="$2"; shift 2
  local tag="${group}_s${seed}" log="$OUTDIR/${group}_s${seed}.log"
  echo
  echo "==================== $tag ===================="
  local start; start=$(date +%s)
  local cmd=()
  case "$group" in
    visual)
      cmd=(python -B -m demos.entangle.band_untwist_inspect_demo
           env.genesis.backend="$BACKEND" "${VIEWER_ARGS[@]}"
           run.randomize_layout=true "run.seed=$seed" run.static_only=true
           recording=default "recording.path=$OUTDIR/visual_s${seed}.mp4" recording.camera=oblique) ;;
    oracle|wrong_end|one_move)
      cmd=(python -B -m demos.entangle.band_untwist_physical_pinch_demo
           env.genesis.backend="$BACKEND" "${VIEWER_ARGS[@]}"
           run.randomize_layout=true "run.seed=$seed" "run.oracle_mode=$group") ;;
  esac
  timeout "${TIMEOUT_S}s" "${cmd[@]}" "$@" 2>&1 | tee "$log"
  local code=${PIPESTATUS[0]}
  local dur=$(( $(date +%s) - start ))
  local state; state="$(run_state "$code" "$log")"
  local v; v="$(variant_line "$log")"
  [[ -n "$v" ]] && VARIANT[$seed]="${v#band_untwist variant }"
  case " ${ALL_SEEDS[*]} " in *" $seed "*) ;; *) ALL_SEEDS+=("$seed") ;; esac

  local r; r="$(result_line "$log")"
  local success; success="$(field "$r" success)"
  local label; label="$(field "$r" failure_label)"
  local planned; planned="$(field "$r" planned)"
  local verdict=""
  case "$group" in
    visual)
      if [[ "$state" == "ok" && -s "$OUTDIR/visual_s${seed}.mp4" ]]; then verdict="ok (看 mp4)"; else verdict="FAIL $state"; FAIL=1; fi ;;
    oracle)
      if [[ "$state" != "ok" ]]; then verdict="FAIL $state"; FAIL=1
      elif [[ "$success" == "True" ]]; then verdict="PASS"
      else verdict="FAIL $label"; FAIL=1; fi
      [[ "$(field "$r" off_plan)" != "None" && -n "$r" ]] && verdict="$verdict off_plan=$(field "$r" off_plan)"
      [[ "$(field "$r" ceiling_exceeded)" == "True" ]] && verdict="$verdict ceiling_exceeded"
      PLANNED[$seed]="$planned"
      GT[$seed]="$(grep -aF "band_untwist_start" "$log" | grep -aoE "gt_match=[A-Za-z]+" | sed 's/gt_match=//')"
      GRASPED[$seed]="$(move_field "$log" end)"
      LIFTS[$seed]="$(move_field "$log" lift)" ;;
    wrong_end)
      if [[ "$state" != "ok" ]]; then verdict="$state"
      elif [[ "$(field "$r" moves)" == "0/0" ]]; then verdict="n/a"
      elif [[ "$success" == "True" ]]; then verdict="success(!)"
      else verdict="$label"; fi ;;
    one_move)
      if [[ "$state" != "ok" ]]; then verdict="FAIL $state"; FAIL=1
      elif [[ "$planned" == "1" && "$success" == "True" ]]; then verdict="PASS (1 步)"
      elif [[ "$planned" != "1" && "$label" == "crossing_left" ]]; then verdict="crossing_left (预期，规划 $planned 步)"
      else verdict="FAIL planned=$planned success=$success $label"; FAIL=1; fi ;;
  esac
  RESULT[$group,$seed]="$verdict"
  echo "---- $tag (${dur}s): $verdict"
}

for group in "${SELECTED[@]}"; do
  echo "$group seeds=[$(group_seeds "$group")]"
done
echo "outdir=$OUTDIR backend=$BACKEND groups=[${SELECTED[*]}]"

for group in "${SELECTED[@]}"; do
  for seed in $(group_seeds "$group"); do
    run_cell "$group" "$seed"
  done
done

echo
echo "==================== 汇总 ===================="
csv="$OUTDIR/summary.csv"
echo "seed,shape,heading,cx,cy,leaves,crossings,planned_spawn,planned_settled,lift_pred,gt_match,grasped,lifts_mm,visual,oracle,wrong_end,one_move" > "$csv"
declare -A N_ORACLE N_ORACLE_OK N_WRONG N_WRONG_FAIL N_ONE N_ONE_OK
n_planned_diff=0
for seed in $(printf '%s\n' "${ALL_SEEDS[@]}" | sort -n); do
  v="${VARIANT[$seed]:-}"
  shape="$(field "$v" shape)"
  # 形态自己的叶子：cy= 之后、crossings= 之前的那一段。
  leaves="$(echo "$v" | sed -E 's/.* cy=[^ ]+ (.*) crossings=.*/\1/' | tr ' ' ';')"
  printf '  seed %-3s %-6s heading=%-6s planned=%s/%s grasped=%-4s lifts=%-8s | visual=%s oracle=%s wrong_end=%s one_move=%s\n' \
    "$seed" "$shape" "$(field "$v" heading)" "$(field "$v" planned)" "${PLANNED[$seed]:--}" \
    "${GRASPED[$seed]:--}" "${LIFTS[$seed]:--}" \
    "${RESULT[visual,$seed]:--}" "${RESULT[oracle,$seed]:--}" "${RESULT[wrong_end,$seed]:--}" "${RESULT[one_move,$seed]:--}"
  echo "$seed,$shape,$(field "$v" heading),$(field "$v" cx),$(field "$v" cy),$leaves,$(field "$v" crossings),$(field "$v" planned),${PLANNED[$seed]:-},$(field "$v" lift_pred),${GT[$seed]:-},\"${GRASPED[$seed]:-}\",\"${LIFTS[$seed]:-}\",${RESULT[visual,$seed]:-},${RESULT[oracle,$seed]:-},${RESULT[wrong_end,$seed]:-},${RESULT[one_move,$seed]:-}" >> "$csv"
  if [[ -n "${RESULT[oracle,$seed]:-}" ]]; then
    N_ORACLE[$shape]=$(( ${N_ORACLE[$shape]:-0} + 1 ))
    [[ "${RESULT[oracle,$seed]}" == PASS* ]] && N_ORACLE_OK[$shape]=$(( ${N_ORACLE_OK[$shape]:-0} + 1 ))
    [[ -n "${PLANNED[$seed]:-}" && "${PLANNED[$seed]}" != "$(field "$v" planned)" ]] && n_planned_diff=$((n_planned_diff + 1))
  fi
  if [[ -n "${RESULT[wrong_end,$seed]:-}" && "${RESULT[wrong_end,$seed]}" != "n/a" ]]; then
    N_WRONG[$shape]=$(( ${N_WRONG[$shape]:-0} + 1 ))
    [[ "${RESULT[wrong_end,$seed]}" == crossing_* ]] && N_WRONG_FAIL[$shape]=$(( ${N_WRONG_FAIL[$shape]:-0} + 1 ))
  fi
  if [[ -n "${RESULT[one_move,$seed]:-}" ]]; then
    N_ONE[$shape]=$(( ${N_ONE[$shape]:-0} + 1 ))
    [[ "${RESULT[one_move,$seed]}" != FAIL* ]] && N_ONE_OK[$shape]=$(( ${N_ONE_OK[$shape]:-0} + 1 ))
  fi
done
for shape in eight six twist curls; do
  line=""
  [[ -n "${N_ORACLE[$shape]:-}" ]] && line="$line oracle ${N_ORACLE_OK[$shape]:-0}/${N_ORACLE[$shape]} 成功"
  [[ -n "${N_WRONG[$shape]:-}" ]] && line="$line; wrong_end ${N_WRONG_FAIL[$shape]:-0}/${N_WRONG[$shape]} 判失败（n/a 格不计）"
  [[ -n "${N_ONE[$shape]:-}" ]] && line="$line; one_move ${N_ONE_OK[$shape]:-0}/${N_ONE[$shape]} 符合开局步数"
  [[ -n "$line" ]] && echo "  $shape:$line"
done
[[ $n_planned_diff -gt 0 ]] && echo "  出生形状与沉降后实测绳上的规划步数不同：$n_planned_diff 格（只记录；demo 按实测的执行）"
echo
echo "怎么读："
echo "  visual    打开 $OUTDIR/visual_s*.mp4：形态、朝向、位置、上下关系应逐 seed 可分，且无穿模。"
echo "  oracle    全部 PASS 才说明 oracle 覆盖了包络；off_plan=<步> 表示那一步之后实测交叉序列不是规划预测的，"
echo "            看 log 的 band_untwist_off_plan / band_untwist_after_move 行与 variant 行（lift_pred 大的格抬得最高）。"
echo "  wrong_end 应全部 crossing_added / crossing_left；success(!) 说明抓错端也解开了，判据或几何有问题。"
echo "  one_move  规划 1 步的格成功、2 步的格 crossing_left；不符说明判据或 oracle 的步数有问题。"
echo "summary: $csv"
echo "日志: $OUTDIR"
exit $FAIL
