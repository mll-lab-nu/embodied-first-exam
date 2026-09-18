#!/usr/bin/env bash
# ============================================================================
# 绳↔绳接触屏障取值扫描（测量器，不带机械臂运动）。
#
# 要回答的问题：两根叠放的绳静止时中心线应该相距 2*radius + particle_size = 12mm，
# 实测只有 2.5mm，即两根互相嵌进去 5.5mm。重叠的两根绳永久处于接触状态，抬一根会
# 把另一根带走，"谁在上面"的判定也只剩不到一个绳半径的裕度。
#
# 屏障的洞有多大由 rope.mesh.segment_length（沿绳的圈间距）和 radial_segments
# （环向间距 2*radius*sin(pi/n)）决定，而 PBD 只在粒子中心距小于 particle_size
# 时才排斥。洞比排斥半径大，另一根绳的粒子就能从两圈之间滑进去。
#
# 把网格加密能堵洞，但会让绳自己的粒子对进入碰撞检测：静止距离大于 particle_size
# 的同体粒子对参与检测，绳弯曲时内侧间距按 (R-r)/R 收缩，收缩到阈值以下就产生
# 本不应存在的排斥。两者相互制约，所以这里扫的是这两个参数的组合。
#
# 每格只做「生成 + 沉降 + 打印」，用 untangle_continuous_inspect_demo，不跑机械臂，
# 因此比 stability_sweep.sh 快很多。
#
# 用法：
#   bash bash_scripts/tests/rope_contact_sweep.sh
#   SEGMENTS="0.004 0.009" RADIALS="6 8" SEEDS="0 1" bash bash_scripts/tests/rope_contact_sweep.sh
#
# demo 已迁 Hydra，这里的三重循环也可以直接用 multirun 代替：
#   python -m demos.entangle.untangle_continuous_inspect_demo -m #     task.rope.mesh.segment_length=0.004,0.005,0.006,0.009 #     task.rope.mesh.radial_segments=6,8 run.seed=0,1,2,3
# 保留本脚本是因为它还负责从 stdout 抓那四个指标并排版成表。
#
# 可调环境变量：
#   SEGMENTS="0.004 0.005 0.006 0.009"   扫哪些 segment_length（米）
#   RADIALS="6 8"                        扫哪些 radial_segments
#   SEEDS="0 1 2 3"                      扫哪些 seed
#   STRANDS=2                            绳数
#   BACKEND=gpu
#   TIMEOUT_S=600                        单格墙钟超时（秒）
#   OUTDIR=runs/rope_contact/<时间戳>
#   TOPOGYM_VENV=.venv-gs121-nyx
# ============================================================================
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$REPO"

if [[ -z "${VIRTUAL_ENV:-}" ]]; then
  VENV="${TOPOGYM_VENV:-$REPO/.venv-gs121-nyx}"
  [[ -f "$VENV/bin/activate" ]] && source "$VENV/bin/activate"
fi

SEGMENTS="${SEGMENTS:-0.004 0.005 0.006 0.009}"
RADIALS="${RADIALS:-6 8}"
SEEDS="${SEEDS:-0 1 2 3}"
STRANDS="${STRANDS:-2}"
BACKEND="${BACKEND:-gpu}"
TIMEOUT_S="${TIMEOUT_S:-600}"
OUTDIR="${OUTDIR:-runs/rope_contact/$(date +%Y%m%d_%H%M%S)}"
mkdir -p "$OUTDIR"

if ! python -c "import topogym" 2>/dev/null; then
  echo "[error] 无法 import topogym。先激活正确 venv（或设 TOPOGYM_VENV）。" >&2
  exit 1
fi

# 一格的结果：交叉处最小 z_gap、最大互嵌深度、粒子间距是否自带违反、检测器是否对上 GT。
# 全部从 inspect demo 的 stdout 里抓，格式见 supervision/untangle_continuous.py。
summarize() {
  local code="$1" log="$2"
  if [[ "$code" == "124" ]]; then echo "TIMEOUT"; return; fi
  if [[ "$code" == "139" ]] || grep -qiE "Segmentation fault|core dumped" "$log"; then echo "SEGV"; return; fi
  if [[ "$code" != "0" ]]; then
    grep -qiE "Traceback" "$log" && { echo "RAISED"; return; }
    echo "code$code"; return
  fi
  local gap overlap viol gt
  # "z_gap=2.5mm (resting apart = 12.0mm)" -> 取所有交叉里最小的 z_gap
  gap="$(grep -oE 'z_gap=[0-9.]+mm' "$log" | grep -oE '[0-9.]+' | sort -g | head -1)"
  overlap="$(grep -oE 'INTERPENETRATING by [0-9.]+mm' "$log" | grep -oE '[0-9.]+' | sort -g | tail -1)"
  viol="$(grep -cE 'SELF-COLLISION ALWAYS VIOLATED' "$log")"
  gt="$(grep -oE 'gt_match=(True|False)' "$log" | head -1 | cut -d= -f2)"
  [[ -z "$gap" ]] && gap="-"
  [[ -z "$overlap" ]] && overlap="0"
  [[ -z "$gt" ]] && gt="?"
  echo "gap=${gap}mm overlap=${overlap}mm self_viol=${viol} gt=${gt}"
}

echo "outdir=$OUTDIR  strands=$STRANDS  backend=$BACKEND"
echo "目标：gap 越接近 12.0mm 越好（= 2*radius + particle_size）；overlap 越接近 0 越好；"
echo "     self_viol 应为 0（不为 0 表示网格自带的间距已经违反碰撞约束）。"
echo

for radial in $RADIALS; do
  for segment in $SEGMENTS; do
    for seed in $SEEDS; do
      tag="n${radial}_s${segment}_seed${seed}"
      log="$OUTDIR/$tag.log"
      # Hydra 覆盖语法（demo 于 2026-08-10 迁移）。物理参数走 task. 路径，
      # 运行模式走 run.，后端是 env.genesis.backend —— 它本来就是配置键。
      timeout "${TIMEOUT_S}s" python -m demos.entangle.untangle_continuous_inspect_demo \
        env.genesis.backend="$BACKEND" \
        run.seed="$seed" \
        run.verbose=true \
        task.braid.n_strands="$STRANDS" \
        task.rope.mesh.radial_segments="$radial" \
        task.rope.mesh.segment_length="$segment" \
        >"$log" 2>&1
      code=$?
      printf '%-24s %s\n' "$tag" "$(summarize "$code" "$log")"
    done
  done
  echo
done

echo "日志：$OUTDIR"
