#!/usr/bin/env bash
# ============================================================================
# cloth_unpleat 的褶皱起始状态稳不稳：扫材料参数，一次跑完，打一张对照表。
#
# 2026-08-23 实测：按 1.1 的材料参数（bending_compliance=1e-5，布↔布摩擦 0.15）
# 建出来的褶皱，放手之后有两个毛病，根因都是「布不记折痕」：
#
#   塌   顶缘 22.0mm -> 8.1mm，发生在前 25 步（四分之一秒）之内，之后不再变。
#        不是发散（全程最大速度 0.06 m/s，最低点恒为 +2.0mm）。
#   爬   俯视跨度每 25 步涨约 1.2mm，400 步涨了 17mm 而且没有变慢的迹象。
#        跨度变大只能来自材料从褶皱里自己往外放。
#
# **「爬」比「塌」严重。** 躺平的褶皱仍然是三层、仍然收着材料，任务还成立；
# 但一直在爬意味着 (1) 起始状态取决于静置多少步，不可复现；(2) 重力在替机械臂
# 干活——一个 episode 约 350 步，光靠重力就会再放出约 17mm，占机械臂本该拿回来的
# 61mm 的四分之一到三分之一，判据分不清哪部分是动作做的。
#
# 所以这个脚本的主要读数是**跨度在采样区间里涨了多少**，不是顶缘高度。
#
# 两组旋钮，分别对应两种可能的机制：
#   bend  弯曲柔度。**已实测为死参数，留着只为复核。**
#         2026-08-23：1e-1 到 1e-8 跨七个数量级，读数一位没变，而 material 行
#         证明覆盖确实到了材质构造函数。是 Genesis 不用它，不是没传进去。
#   relax 弯曲松弛率。**这才是活的旋钮，而且它是「爬」的成因不是解药。**
#         Genesis 的 PBD 弯曲约束把**平面**当静止角，relax 决定每子步把折痕往
#         平面推多用力。实测 0.02/0.1/0.5/1.0 的爬是 +3.3/+6.3/+49.0/+61.8mm，
#         1.0 那档跨度 266.9mm 已超过材料全长 260mm（布被拉长了）。
#         所以要往**小**调，不是往大调。
#   mu    布↔布摩擦。0.15/0.4/0.8/1.5 的爬是 +6.3/+5.8/+4.3/+1.2mm，
#         但 1.5 的峰值速度到了 0.746（基线 0.07），3.0 直接把布甩到空中。
#   combo relax × mu 的笛卡尔积 —— 这两个才是活的那一对。
#
# 用法：
#   bash bash_scripts/tests/pleat_stability_sweep.sh            # bend + mu
#   bash bash_scripts/tests/pleat_stability_sweep.sh bend       # 只扫弯曲柔度
#   bash bash_scripts/tests/pleat_stability_sweep.sh relax      # 只扫弯曲松弛率
#   bash bash_scripts/tests/pleat_stability_sweep.sh combo      # 笛卡尔积
#
# 可调环境变量（都有默认值）：
#   BENDINGS="1e-1 1e-3 1e-5 1e-8"   扫哪些弯曲柔度（跨软硬两侧）
#   BENDING_RELAXATIONS="0.02 0.1 0.5 1.0"  扫哪些弯曲松弛率
#   FRICTIONS="0.15 0.4 0.8"         扫哪些布↔布摩擦（静摩擦与动摩擦取同值）
#   SETTLE_STEPS=200                 每格静置多少步（塌陷 25 步内就发生完，200 够看爬）
#   SAMPLE_EVERY=25                  每几步采一次样
#   BACKEND=                         留空则用 env 配置里的后端（当前是 cpu）
#   TIMEOUT_S=600                    单格墙钟超时（秒）
#   OUTDIR=runs/pleat_stability/<时间戳>
#   TOPOGYM_VENV=.venv
#
# 每格产出 <OUTDIR>/<tag>.log。退出码：任何一格 TIMEOUT / RAISED 即非 0；
# **verdict=collapsed 不算脚本失败**，它是这次要测的结果本身。
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

BENDINGS="${BENDINGS:-1e-1 1e-3 1e-5 1e-8}"
BENDING_RELAXATIONS="${BENDING_RELAXATIONS:-0.02 0.1 0.5 1.0}"
FRICTIONS="${FRICTIONS:-0.15 0.4 0.8}"
SETTLE_STEPS="${SETTLE_STEPS:-200}"
SAMPLE_EVERY="${SAMPLE_EVERY:-25}"
BACKEND="${BACKEND:-}"
TIMEOUT_S="${TIMEOUT_S:-600}"
OUTDIR="${OUTDIR:-runs/pleat_stability/$(date +%Y%m%d_%H%M%S)}"
mkdir -p "$OUTDIR"

if ! python -c "import genesis" 2>/dev/null; then
  echo "[error] 无法 import genesis。本扫参要跑真物理，必须在项目 venv 里跑。" >&2
  exit 1
fi

ORDER=(bend relax mu combo)
if [[ $# -gt 0 ]]; then
  SELECTED=("$@")
else
  SELECTED=(bend mu)
fi
for name in "${SELECTED[@]}"; do
  case " ${ORDER[*]} " in
    *" $name "*) ;;
    *) echo "[error] 未知项 '$name'；可选：${ORDER[*]}" >&2; exit 1 ;;
  esac
done

declare -a ROWS=()
FAIL=0

# 从一行 key=value 里取一个字段。前导空格而不是 \b，避免 sed 方言差异。
field() {
  sed -n "s/.* $2=\([^ ]*\).*/\1/p" <<< "$1"
}

run_cell() {
  local tag="$1"; shift
  local log="$OUTDIR/$tag.log"
  echo
  echo "==================== $tag ===================="
  local start; start=$(date +%s)
  local backend_args=()
  [[ -n "$BACKEND" ]] && backend_args+=("env.genesis.backend=$BACKEND")
  timeout "${TIMEOUT_S}s" python -B -m tests.pleat_settle_spike \
    "run.settle_steps=$SETTLE_STEPS" "run.sample_every=$SAMPLE_EVERY" \
    "${backend_args[@]}" "$@" 2>&1 | tee "$log"
  local code=${PIPESTATUS[0]}
  local dur=$(( $(date +%s) - start ))

  # TIMEOUT / 异常算脚本失败；collapsed(退出码 1) 不算，它是结果。
  local state="ok"
  if [[ "$code" == "124" ]]; then state="TIMEOUT"; FAIL=1
  elif grep -qiE "Traceback" "$log"; then state="RAISED"; FAIL=1
  fi

  local first last verdict
  first="$(grep -E '^pleat_settle_spike settle ' "$log" | head -1)"
  last="$(grep -E '^pleat_settle_spike settle ' "$log" | tail -1)"
  verdict="$(field "$(grep -E '^pleat_settle_spike verdict=' "$log" | tail -1)" verdict)"

  if [[ -z "$first" || -z "$last" ]]; then
    ROWS+=("$tag|${dur}s|$state（没有采样行，见日志）")
    return
  fi

  # 「爬」的读数：跨度在采样区间里涨了多少，以及每秒多少毫米（dt=0.01）。
  local row
  row="$(awk -v tag="$tag" -v dur="${dur}s" -v state="$state" -v verdict="${verdict:-?}" \
    -v s0="$(field "$first" step)"        -v s1="$(field "$last" step)" \
    -v c0="$(field "$first" crest_mm)"    -v c1="$(field "$last" crest_mm)" \
    -v p0="$(field "$first" span_mm)"     -v p1="$(field "$last" span_mm)" \
    -v v="$(field "$last" max_speed)"     -v lo="$(field "$last" lowest_mm)" \
    -v sl="$(field "$last" single_layer_frac)" \
    'BEGIN {
       secs = (s1 - s0) / 100.0;
       creep = p1 - p0;
       rate = (secs > 0) ? creep / secs : 0;
       printf "%s|%s|%s 顶缘 %.1f->%.1fmm  跨度 %.1f->%.1fmm  爬 %+.1fmm (%+.1f mm/s)  单层 %s  v %s  低点 %s  %s",
              tag, dur, state, c0, c1, p0, p1, creep, rate, sl, v, lo, verdict;
     }')"
  ROWS+=("$row")
}

echo "outdir=$OUTDIR  settle_steps=$SETTLE_STEPS  sample_every=$SAMPLE_EVERY"
echo "backend=${BACKEND:-<env 配置默认>}   组: ${SELECTED[*]}"

for name in "${SELECTED[@]}"; do
  case "$name" in
    bend)
      for bc in $BENDINGS; do
        run_cell "bend_$bc" "task.cloth.bending_compliance=$bc"
      done
      ;;
    relax)
      for br in $BENDING_RELAXATIONS; do
        run_cell "relax_$br" "task.cloth.bending_relaxation=$br"
      done
      ;;
    mu)
      for mu in $FRICTIONS; do
        run_cell "mu_$mu" \
          "task.cloth.static_friction=$mu" "task.cloth.kinetic_friction=$mu"
      done
      ;;
    combo)
      for br in $BENDING_RELAXATIONS; do
        for mu in $FRICTIONS; do
          run_cell "combo_${br}_${mu}" \
            "task.cloth.bending_relaxation=$br" \
            "task.cloth.static_friction=$mu" "task.cloth.kinetic_friction=$mu"
        done
      done
      ;;
  esac
done

echo
echo "==================== 汇总 ===================="
for row in "${ROWS[@]}"; do
  IFS='|' read -r a b c <<< "$row"
  printf '%-22s %-6s %s\n' "$a" "$b" "$c"
done

echo
echo "怎么读："
echo "  **主读数是「爬」那一列**，不是顶缘高度。爬 ≈ 0 的那一档就是要的:"
echo "  起始状态不再随静置步数漂移, 重力也不再替机械臂放料。"
echo "  基线 (bend_1e-5 + mu_0.15) 是 +1.2mm/25 步 ≈ +4.8 mm/s, 400 步涨 17mm。"
echo
echo "  顶缘那一列是次要的: 躺平的褶皱仍然是三层、仍然收着材料, 任务还成立。"
echo "  立住 (verdict=stands) 是加分项 —— 它让高度那条判据和 docx 点名的"
echo "  「压塌」捷径重新有意义, 但不是必要条件。"
echo
echo "  排除项: v (max_speed) 跳到 1 以上, 或 低点 变负, 说明那一档 PBD 收敛不了,"
echo "  数字不可信, 往回退一档。基线的 v 是 0.06 左右。"
echo
echo "  bend 已实测为死参数 (七个数量级零变化), 不要再往那个方向调。"
echo "  活的是 relax, 而且它是成因不是解药: 弯曲约束把平面当静止角, 一直在把"
echo "  折痕往平推。所以 relax 要往**小**调; 大了褶皱会自己弹开甚至把布拉长。"
echo "  代价要说清: relax 调到很小等于这块布几乎没有弯曲约束作用, 这是比改一个"
echo "  柔度数值更大的偏离, 写回配置时要如实记下。"
echo
echo "  verdict=diverged 优先于其余三种: 峰值速度超线、顶缘高过建模值太多、或者"
echo "  整块布离开桌面, 都算发散。摩擦 3.0 那次布飞到 76 m/s 而旧判据报了 stands,"
echo "  这条就是为它加的。"
echo
echo "  选定之后写回 configs/task_configs/cloth_unpleat_topogym_tabletop_v1.yaml,"
echo "  并在注释里记下**偏离 cloth_fold 官方默认值的理由**: 1.1 是一张平铺的方布,"
echo "  1.2 是一条要靠折痕维持形状的带子。"
echo
echo "日志: $OUTDIR"
exit $FAIL
