#!/usr/bin/env bash
# ============================================================================
# 批量渲染是否真的被 n_envs 打开（回答 reviewer 的 "can we do batch rendering"）。
#
# 切换本身在 StandardTabletopSceneBuilder._select_renderer：n_envs=0 返回 None，
# Genesis 用默认光栅化器，单环境路径原样不动；>0 选 Madrona 批量渲染器。
# 本脚本逐档验证三件事：能不能建起来、返回的图有没有环境维、每个环境的成本。
#
# 预期：per_env（每环境每帧毫秒）随 n_envs 上升而下降。render_bench.py 测出一帧
# 主要是固定开销（1.75ms + 0.65~1.0ms/兆像素），而固定开销正是批量能摊薄的部分。
# 如果 per_env 不降，说明瓶颈不在这里，那条路就不值得投入。
#
# 需要 CUDA 与 gs_madrona（Linux x86-64）。缺任何一个，builder 会带原因报错——
# 那是预期结果，不是崩溃。
#
# 用法：
#   bash bash_scripts/tests/batch_render_probe.sh
#   N_ENVS="0 8 32" bash bash_scripts/tests/batch_render_probe.sh
# ============================================================================
set -uo pipefail

N_ENVS="${N_ENVS:-0 4 16 64}"
FRAMES="${FRAMES:-40}"
CAMERA="${CAMERA:-base_camera}"

STAMP="$(date +%Y%m%d_%H%M%S)"
OUT_DIR="runs/batch_render_probe/${STAMP}"
mkdir -p "${OUT_DIR}"
echo "输出目录: ${OUT_DIR}"
echo

for N in ${N_ENVS}; do
  LOG="${OUT_DIR}/n_envs_${N}.log"
  echo "=== n_envs=${N} frames=${FRAMES} ==="
  python -B -m tests.batch_render_probe \
    run.n_envs_sweep="[${N}]" \
    run.bench_frames="${FRAMES}" \
    run.camera="${CAMERA}" \
    > "${LOG}" 2>&1
  if [ $? -ne 0 ]; then
    echo "  [失败] 见 ${LOG}"
    grep -iE "ValueError|requires|Error" "${LOG}" | head -3
    continue
  fi
  grep -E "^batch_probe|^\[warn\]" "${LOG}" || echo "  [警告] 没抓到测量行，见 ${LOG}"
  echo
done

echo "============================================================"
echo "汇总"
echo "============================================================"
grep -h "^batch_probe" "${OUT_DIR}"/*.log 2>/dev/null | sed 's/^batch_probe //' || echo "（无数据）"
echo
echo "看 per_env 这一列：随 n_envs 上升而下降 = 批量渲染确实在摊薄固定开销。"
echo "日志: ${OUT_DIR}/"
