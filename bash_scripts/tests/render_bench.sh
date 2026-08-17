#!/usr/bin/env bash
# ============================================================================
# 渲染速度测量（回答 reviewer 的 "what is the rendering speed"）。
#
# 要回答的问题：日志里那些 `Running at N FPS` 是 scene.step() 的速率，而 runs/ 下
# 所有长跑都是无头、不开相机的，所以渲染成本从来没被单独量过。本脚本分别量
# step / render / step+render 三项，给出 render_over_step 比值。
#
# 比值是决定训练吞吐的量：一次 rollout 每帧付 step + N*render（N = 相机数）。
# 比值远小于 1 说明物理是瓶颈，远大于 1 说明渲染是瓶颈、批量渲染才有意义。
#
# 每档分辨率一个进程：相机分辨率在构造时固定，扫描要重建场景，而在同一进程里反复
# destroy/init Genesis 是不必要的风险。
#
# **务必同时看输出里的 renderer 与是否出现 libEGL 警告。** Rasterizer 走 OpenGL，
# EGL 拿不到设备时会静默退回软件渲染（WSL 上实测慢约一个数量级），软件路径量出来
# 的数不能用来回答 reviewer。
#
# 用法：
#   bash bash_scripts/tests/render_bench.sh
#   RESOLUTIONS="256 512" CAMERAS="[base_camera]" bash bash_scripts/tests/render_bench.sh
#   BACKEND=gpu bash bash_scripts/tests/render_bench.sh
#
# 可调环境变量：
#   RESOLUTIONS="256 512 960"   扫哪些分辨率（正方形）
#   CAMERAS="[base_camera,wrist,oblique]"   量哪些相机（Hydra 列表语法，勿留空格）
#   FRAMES=40                   每档计时帧数
#   BACKEND=cpu                 env.genesis.backend
# ============================================================================
set -uo pipefail

RESOLUTIONS="${RESOLUTIONS:-256 512 960}"
CAMERAS="${CAMERAS:-[base_camera,wrist,oblique]}"
FRAMES="${FRAMES:-100}"
BACKEND="${BACKEND:-cpu}"

STAMP="$(date +%Y%m%d_%H%M%S)"
OUT_DIR="runs/render_bench/${STAMP}"
mkdir -p "${OUT_DIR}"
echo "输出目录: ${OUT_DIR}"
echo

SOFTWARE_SEEN=0
for RES in ${RESOLUTIONS}; do
  LOG="${OUT_DIR}/res_${RES}.log"
  echo "=== res=${RES} backend=${BACKEND} frames=${FRAMES} ==="
  python -B -m tests.render_bench \
    run.res="${RES}" \
    run.bench_frames="${FRAMES}" \
    run.cameras="${CAMERAS}" \
    env.genesis.backend="${BACKEND}" \
    > "${LOG}" 2>&1
  STATUS=$?
  if [ ${STATUS} -ne 0 ]; then
    echo "  [失败] 退出码 ${STATUS}，见 ${LOG}"
    tail -5 "${LOG}"
    continue
  fi
  if grep -q "Software rendering context detected" "${LOG}"; then
    SOFTWARE_SEEN=1
  fi
  grep "^render_bench res=" "${LOG}" || echo "  [警告] 没抓到测量行，见 ${LOG}"
  echo
done

echo "============================================================"
echo "汇总（step / render / both 单位毫秒）"
echo "============================================================"
grep -h "^render_bench res=" "${OUT_DIR}"/*.log 2>/dev/null \
  | sed 's/^render_bench //' \
  || echo "（无数据）"
echo

if [ ${SOFTWARE_SEEN} -eq 1 ]; then
  echo "[警告] 至少一档命中软件渲染（日志里有 'Software rendering context detected'）。"
  echo "       这些数字不能用来回答 reviewer——它们量的是 CPU 逐像素画图。"
  echo "       检查 /dev/dri 权限，或换一台 EGL 可用的机器重跑。"
else
  echo "未检测到软件渲染回退。"
fi
echo "日志: ${OUT_DIR}/"
