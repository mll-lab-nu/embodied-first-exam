#!/usr/bin/env bash
# ============================================================================
# swap H5 -> pi0.5 (OpenPI) 数据加载冒烟：一次跑完，分阶段逐段检验是否跑通。
# 目标 = 证明一条 swap H5 能进 OpenPI 的数据加载 + 训练循环，不报 shape/格式错。
# 不是训 baseline。完整说明 + 手动 config diff（stage 3）见：
#   docs/develop/il_adaptation/swap_to_pi05_smoke_zh.md
#
# 阶段（每段独立日志 <SMOKE_DIR>/stage<N>.log + PASS/FAIL）：
#   0 openpi 可导入自检              (OpenPI uv env)
#   1 录一条 swap H5                 (topogym Genesis venv；复用 verify_dataset_recording.sh)
#   2 H5 -> LeRobot 数据集           (OpenPI uv env)
#   3 确保 pi05_topogym_swap 已注册进 config.py       (默认自动追加；AUTO_CONFIG=0 则改手动)
#   4 compute_norm_stats            (第一个硬门，不加载模型，最能暴露格式错)
#   5 train 几个 step               (首次拉 pi05_base checkpoint 数 GB + 需 GPU)
#
# 用法：
#   bash bash_scripts/tests/swap_pi05_smoke.sh               # 一条命令跑 0..5（stage 3 自动注册 config）
#   TO_STAGE=4 bash bash_scripts/tests/swap_pi05_smoke.sh    # 只到便宜的数据门，不 train
#   FROM_STAGE=4 bash bash_scripts/tests/swap_pi05_smoke.sh  # 只重跑 norm_stats + train
#
# 可调环境变量（都有默认值）：
#   FROM_STAGE=0 TO_STAGE=5        跑哪几段（闭区间）
#   SEED=0 EVERY=10 BACKEND=gpu    录制参数（透传给 verify_dataset_recording.sh）
#   CONFIG_NAME=pi05_topogym_swap  REPO_ID=topogym/swap_smoke  EXP_NAME=swap_smoke
#   AUTO_CONFIG=1                  stage 3 自动追加 config（幂等）；=0 则改回手动粘 diff
#   WANDB_MODE=disabled            冒烟默认关 wandb；想上传设 online 并先 wandb login
#   SMOKE_DIR=runs/pi05_smoke      固定产物目录（H5 落这里，跨段/续跑可复用）
#   OPENPI_DIR=.external/openpi    OpenPI 安装目录
#   TOPOGYM_VENV=.venv             录制用的 topogym venv（未激活时 verify 脚本自动 source）
# ============================================================================
set -uo pipefail   # 故意不加 -e：失败要落到本脚本的汇总里，不是裸退出

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$REPO"

FROM_STAGE="${FROM_STAGE:-0}"
TO_STAGE="${TO_STAGE:-5}"
SEED="${SEED:-0}"
EVERY="${EVERY:-10}"
BACKEND="${BACKEND:-gpu}"
CONFIG_NAME="${CONFIG_NAME:-pi05_topogym_swap}"
REPO_ID="${REPO_ID:-topogym/swap_smoke}"
EXP_NAME="${EXP_NAME:-swap_smoke}"
SMOKE_DIR="${SMOKE_DIR:-runs/pi05_smoke}"
OPENPI_DIR="${OPENPI_DIR:-$REPO/.external/openpi}"
AUTO_CONFIG="${AUTO_CONFIG:-1}"       # stage 3：1=自动注册 config，0=保持手动
H5="$SMOKE_DIR/swap_seed${SEED}.h5"   # verify_dataset_recording.sh 的命名约定

# 冒烟不上传 wandb —— train.py 默认开 wandb，无 TTY/无 api_key 时会在训练前报错退出。
# disabled 让 wandb.init 变成 no-op（想上传就设 WANDB_MODE=online 并先 wandb login）。
export WANDB_MODE="${WANDB_MODE:-disabled}"

mkdir -p "$SMOKE_DIR"

# OpenPI 命令跑在它自己的 uv 环境里；清掉外层 VIRTUAL_ENV，免得 uv 被激活着的
# topogym venv 干扰（uv 会用 .external/openpi 的项目环境）。
openpi_run() { ( unset VIRTUAL_ENV; cd "$OPENPI_DIR" && uv run "$@" ); }

# uv 常被 env_setup_vla_openpi.sh 装到 ~/.local/bin 或 ~/.cargo/bin，而那次 PATH 改动
# 只在它自己那次运行里生效——非交互 shell 跑本脚本时可能找不到 uv。这里补进 PATH。
ensure_uv() {
  command -v uv >/dev/null 2>&1 && return 0
  local d
  for d in "$HOME/.local/bin" "$HOME/.cargo/bin"; do
    [ -x "$d/uv" ] && { PATH="$d:$PATH"; export PATH; }
  done
  command -v uv >/dev/null 2>&1
}

want() { [ "$1" -ge "$FROM_STAGE" ] && [ "$1" -le "$TO_STAGE" ]; }

declare -A RESULT
ORDER=(0 1 2 3 4 5)

finish() {
  echo
  echo "==================== 汇总 ===================="
  local fail=0 s st
  for s in "${ORDER[@]}"; do
    st="${RESULT[$s]:-skipped}"
    printf '  stage %s  %s\n' "$s" "$st"
    [[ "$st" == FAIL* || "$st" == NEEDS* ]] && fail=1
  done
  echo "产物目录: $SMOKE_DIR   日志: $SMOKE_DIR/stage*.log"
  exit "$fail"
}

echo "[smoke] stages ${FROM_STAGE}..${TO_STAGE} | seed=$SEED backend=$BACKEND config=$CONFIG_NAME"

# 需要 OpenPI 的阶段先确认它装了、且 uv 找得到
if want 0 || want 2 || want 3 || want 4 || want 5; then
  if [[ ! -d "$OPENPI_DIR" ]]; then
    echo "[error] 找不到 OpenPI: $OPENPI_DIR —— 先跑 bash env_setup_vla_openpi.sh" >&2
    exit 1
  fi
  if ! ensure_uv; then
    echo "[error] 找不到 uv（openpi 步骤需要）。它一般被 env_setup_vla_openpi.sh 装在 ~/.local/bin。" >&2
    echo "        执行： export PATH=\"\$HOME/.local/bin:\$HOME/.cargo/bin:\$PATH\"（或 source ~/.bashrc / 开新终端）后重跑。" >&2
    exit 1
  fi
fi

# ---------------- Stage 0: openpi 可导入 ----------------
if want 0; then
  echo; echo "==================== stage 0: openpi import 自检 ===================="
  if openpi_run python -c "from openpi.training import config; print('ok')" 2>&1 \
       | tee "$SMOKE_DIR/stage0.log" | grep -q '^ok$'; then
    echo "[ok] openpi 可导入"; RESULT[0]="ok"
  else
    echo "[fail] openpi 导入失败（见 stage0.log）"; RESULT[0]="FAIL(import)"; finish
  fi
fi

# ---------------- Stage 1: 录 swap H5 ----------------
if want 1; then
  echo; echo "==================== stage 1: 录 swap H5 ===================="
  OUTDIR="$SMOKE_DIR" SEED="$SEED" EVERY="$EVERY" BACKEND="$BACKEND" \
    bash "$REPO/bash_scripts/tests/verify_dataset_recording.sh" swap 2>&1 | tee "$SMOKE_DIR/stage1.log"
  code=${PIPESTATUS[0]}
  if [[ $code -eq 0 && -s "$H5" ]]; then
    echo "[ok] H5 -> $H5"; RESULT[1]="ok"
  else
    echo "[fail] 录制失败或无 H5（code=$code, $H5）"; RESULT[1]="FAIL(record)"; finish
  fi
fi

# ---------------- Stage 2: H5 -> LeRobot ----------------
if want 2; then
  echo; echo "==================== stage 2: H5 -> LeRobot 数据集 ===================="
  if [[ ! -s "$H5" ]]; then
    echo "[fail] 找不到 H5：$H5（先跑 stage 1，或对齐 SEED/SMOKE_DIR）"; RESULT[2]="FAIL(no h5)"; finish
  fi
  openpi_run python "$REPO/scripts/export_swap_lerobot.py" "$REPO/$H5" --repo-id "$REPO_ID" \
    2>&1 | tee "$SMOKE_DIR/stage2.log"
  code=${PIPESTATUS[0]}
  ds_dir="$(grep -oE 'wrote LeRobot dataset -> .*' "$SMOKE_DIR/stage2.log" | tail -1 | sed 's/wrote LeRobot dataset -> //')"
  if [[ $code -eq 0 && -n "$ds_dir" && -d "$ds_dir" ]]; then
    echo "[ok] LeRobot 数据集 -> $ds_dir"; RESULT[2]="ok"
  else
    echo "[fail] 转换失败（code=$code, dir=${ds_dir:-?}）"; RESULT[2]="FAIL(convert)"; finish
  fi
fi

# ---------------- Stage 3: config 是否已注册（可自动注册）----------------
config_registered() {
  openpi_run python -c "import openpi.training.config as c; c.get_config('$CONFIG_NAME')" >/dev/null 2>&1
}
if want 3; then
  echo; echo "==================== stage 3: 检查 $CONFIG_NAME 是否已注册 ===================="
  if config_registered; then
    echo "[ok] $CONFIG_NAME 已注册"; RESULT[3]="ok"
  elif [[ "$AUTO_CONFIG" != "0" ]]; then
    echo "[auto] 未注册 -> 追加 TrainConfig 到 openpi config.py（幂等，AUTO_CONFIG=0 可关）"
    openpi_run python "$REPO/scripts/register_openpi_swap_config.py" \
      --openpi-dir "$OPENPI_DIR" --config-name "$CONFIG_NAME" --repo-id "$REPO_ID" \
      2>&1 | tee "$SMOKE_DIR/stage3.log"
    if config_registered; then
      echo "[ok] 已自动注册 $CONFIG_NAME"; RESULT[3]="ok(auto)"
    else
      echo "[fail] 自动注册后仍读不到 $CONFIG_NAME（见 stage3.log）"; RESULT[3]="FAIL(auto-register)"; finish
    fi
  else
    echo "[NEEDS-MANUAL] $CONFIG_NAME 未注册（AUTO_CONFIG=0）。把 TrainConfig 粘进"
    echo "  $OPENPI_DIR/src/openpi/training/config.py 的 _CONFIGS（diff 见文档第 3 节），"
    echo "  或去掉 AUTO_CONFIG=0 让脚本自动注册；改完 FROM_STAGE=3 续跑："
    echo "    docs/develop/il_adaptation/swap_to_pi05_smoke_zh.md"
    RESULT[3]="NEEDS-MANUAL(config)"; finish
  fi
fi

# ---------------- Stage 4: compute_norm_stats（数据格式硬门）----------------
if want 4; then
  echo; echo "==================== stage 4: compute_norm_stats（数据格式硬门）===================="
  openpi_run scripts/compute_norm_stats.py --config-name "$CONFIG_NAME" 2>&1 | tee "$SMOKE_DIR/stage4.log"
  code=${PIPESTATUS[0]}
  if [[ $code -eq 0 ]]; then
    ns="$(find "$OPENPI_DIR/assets/$CONFIG_NAME" -name 'norm_stats.json' 2>/dev/null | head -1)"
    [[ -n "$ns" ]] && echo "[ok] norm_stats -> $ns" || echo "[ok] compute_norm_stats 退出 0（未定位 norm_stats.json，非硬错）"
    RESULT[4]="ok"
  else
    echo "[fail] compute_norm_stats 失败（code=$code）—— 大概率就是数据 schema 缺口，见 stage4.log"
    RESULT[4]="FAIL(norm_stats)"; finish
  fi
fi

# ---------------- Stage 5: train 几个 step ----------------
if want 5; then
  echo; echo "==================== stage 5: train 几个 step（首次拉 checkpoint + 需 GPU）===================="
  openpi_run scripts/train.py "$CONFIG_NAME" --exp-name="$EXP_NAME" --overwrite 2>&1 | tee "$SMOKE_DIR/stage5.log"
  code=${PIPESTATUS[0]}
  if [[ $code -eq 0 ]] && grep -qiE 'loss|step' "$SMOKE_DIR/stage5.log"; then
    echo "[ok] train 跑通了几步"; RESULT[5]="ok"
  else
    echo "[fail] train 失败或没跨出训练步（code=$code），见 stage5.log"; RESULT[5]="FAIL(train)"; finish
  fi
fi

finish
