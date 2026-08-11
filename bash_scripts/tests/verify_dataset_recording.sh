#!/usr/bin/env bash
# ============================================================================
# 验证"逐帧数据集录制"（路线图 W3/W4）：录一条 H5，再检查其结构与字段健全性。
# 通用脚本——为以后其它任务的数据集验证也做准备（一个任务的 demo 接上
# run.record_dataset 后，只需在下面 TASKS 里加一行即可复用）。
#
# 用法：
#   bash bash_scripts/tests/verify_dataset_recording.sh              # 全部任务
#   bash bash_scripts/tests/verify_dataset_recording.sh untangle     # 指定任务
#
# 可调环境变量（都有默认值）：
#   BACKEND=gpu           计算后端（gpu/cuda/cpu）
#   SEED=0                episode seed
#   EVERY=10              每 N 个物理步录一帧（run.dataset_every_n_steps）
#   OUTDIR=runs/dataset_tests/<时间戳>   输出目录
#   TOPOGYM_VENV=.venv    未激活 venv 时自动 source 的路径
#
# 每个任务产出 <OUTDIR>/<task>_seed<seed>.h5 + <OUTDIR>/<task>.log，
# 然后用 h5py 断言检查结构；跑完打印 PASS/FAIL 汇总（有 FAIL 则退出码非 0）。
# ============================================================================
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$REPO"

# 未激活 venv 时自动 source（沿用项目里 .venv）
if [[ -z "${VIRTUAL_ENV:-}" ]]; then
  VENV="${TOPOGYM_VENV:-$REPO/.venv}"
  if [[ -f "$VENV/bin/activate" ]]; then
    # shellcheck disable=SC1091
    source "$VENV/bin/activate"
  fi
fi

BACKEND="${BACKEND:-gpu}"
SEED="${SEED:-0}"
EVERY="${EVERY:-10}"
OUTDIR="${OUTDIR:-runs/dataset_tests/$(date +%Y%m%d_%H%M%S)}"
mkdir -p "$OUTDIR"

# task 名 -> demo 模块（+ 该任务特有的 Hydra 覆盖）。只列已接数据集录制的任务；
# 其它任务接上 W4 后在此追加一行即可。
declare -A TASKS=(
  [untangle]="demos.entangle.untangle_physical_handle_demo"
  [untangle_continuous]="demos.entangle.untangle_continuous_physical_pinch_demo"
  [cable_routing]="demos.routing.cable_routing_physical_handle_demo run.allow_target_lag=true"
)
ORDER=(untangle untangle_continuous cable_routing)

if [[ $# -gt 0 ]]; then
  SELECTED=("$@")
else
  SELECTED=("${ORDER[@]}")
fi

# 早失败：venv 没对就别一个任务一个任务地各错一次
if ! python -c "import topogym" 2>/dev/null; then
  echo "[error] 无法 import topogym。请先激活正确的 venv（或设 TOPOGYM_VENV），再跑本脚本。" >&2
  exit 1
fi
if ! python -c "import h5py" 2>/dev/null; then
  echo "[error] 无法 import h5py。请先在 venv 里安装：pip install h5py" >&2
  exit 1
fi

echo "[verify] backend=$BACKEND seed=$SEED every=$EVERY outdir=$OUTDIR"
echo "[verify] tasks: ${SELECTED[*]}"

# H5 结构/字段断言检查器：参数 = h5 路径 + 任务名。硬错误 → 退出码 1。
check_h5() {
  python - "$1" "$2" <<'PY'
import sys
import numpy as np
import h5py

path, task = sys.argv[1], sys.argv[2]
errors, warnings = [], []

def req(cond, msg):
    if not cond:
        errors.append(msg)

with h5py.File(path, "r") as f:
    req("schema_version" in f.attrs, "缺 root attr schema_version")
    req("episode_0" in f, "缺 episode_0 组")
    if "episode_0" in f:
        ep = f["episode_0"]
        # ---- setup ----
        req("setup" in ep, "缺 episode_0/setup")
        if "setup" in ep:
            s = ep["setup"]
            for a in ("stable_id", "task_id", "seed", "status", "task_goal"):
                req(a in s.attrs, f"setup 缺 attr {a}")
            if "task_id" in s.attrs:
                got = s.attrs["task_id"]
                got = got.decode() if isinstance(got, bytes) else got
                req(got == task, f"setup.task_id={got!r} 与任务 {task!r} 不符")
        # ---- timesteps ----
        ts_keys = sorted(k for k in ep.keys() if k.startswith("timestep_"))
        req(len(ts_keys) >= 1, "没有任何 timestep_*")
        if ts_keys:
            t0 = ep[ts_keys[0]]
            for grp in ("obs", "action", "info"):
                req(grp in t0, f"{ts_keys[0]} 缺 {grp} 组")
            # obs 形状/dtype
            if "obs" in t0:
                o = t0["obs"]
                rgb_keys = [k for k in o.keys() if k.endswith("_rgb")]
                req(len(rgb_keys) >= 1, "obs 里没有任何 *_rgb")
                for rk in rgb_keys:
                    d = o[rk]
                    req(d.ndim == 3 and d.shape[-1] == 3, f"{rk} 形状应为 HxWx3，实际 {d.shape}")
                    req(d.dtype == np.uint8, f"{rk} dtype 应为 uint8，实际 {d.dtype}")
                req("eef_state" in o and o["eef_state"].shape == (7,),
                    f"eef_state 应为 (7,)，实际 {o['eef_state'].shape if 'eef_state' in o else '缺失'}")
                for k in ("gripper_state", "is_gripper_close", "joint_state"):
                    req(k in o, f"obs 缺 {k}")
            # action
            if "action" in t0:
                a = t0["action"]
                req("ee_pose_action" in a and a["ee_pose_action"].shape == (7,),
                    f"ee_pose_action 应为 (7,)，实际 {a['ee_pose_action'].shape if 'ee_pose_action' in a else '缺失'}")
            # info
            if "info" in t0:
                ig = t0["info"]
                for a in ("task_goal", "simple_subgoal", "is_subgoal_boundary", "is_completed", "status"):
                    req(a in ig.attrs, f"info 缺 attr {a}")
            # 全黑检测（渲染是否真的出了图）：全部帧的第一路 rgb 都全 0 才算硬错
            if rgb_keys:
                rk = rgb_keys[0]
                nonzero = sum(int(np.any(ep[k]["obs"][rk][()])) for k in ts_keys)
                if nonzero == 0:
                    errors.append(f"所有帧的 {rk} 都全黑（渲染没出图）")
                elif nonzero < len(ts_keys):
                    warnings.append(f"{rk} 有 {len(ts_keys)-nonzero}/{len(ts_keys)} 帧全黑（可能渲染 warmup）")

            # 摘要
            print(f"  frames={len(ts_keys)} rgb={rgb_keys}")
            s = ep["setup"]
            def _a(x):
                v = s.attrs.get(x, b"?"); return v.decode() if isinstance(v, bytes) else v
            print(f"  stable_id={_a('stable_id')} status={_a('status')} task_goal={_a('task_goal')}")

for w in warnings:
    print(f"  [warn] {w}")
if errors:
    for e in errors:
        print(f"  [FAIL] {e}")
    sys.exit(1)
print("  [checks passed]")
PY
}

declare -A RESULT
for name in "${SELECTED[@]}"; do
  module="${TASKS[$name]:-}"
  if [[ -z "$module" ]]; then
    echo "[skip] 未知或未接 --record-dataset 的 task: $name（可选：${ORDER[*]}）" >&2
    RESULT[$name]="unknown"
    continue
  fi
  read -ra parts <<< "$module"
  mod="${parts[0]}"
  extra=("${parts[@]:1}")
  h5="$OUTDIR/${name}_seed${SEED}.h5"

  echo
  echo "==================== verify: $name ===================="
  start=$(date +%s)
  # EXTRA_ARGS：附加的 Hydra 覆盖，例如
  #   EXTRA_ARGS="env_configs@env=world_tabletop_fem_v1 task.rope.model=fem_ipc_tube"
  read -ra extra_env <<< "${EXTRA_ARGS:-}"
  python -m "$mod" "${extra[@]}" "${extra_env[@]}" \
    "run.seed=$SEED" \
    "env.genesis.backend=$BACKEND" \
    "run.record_dataset=$h5" \
    "run.dataset_every_n_steps=$EVERY" \
    2>&1 | tee "$OUTDIR/$name.log"
  code=${PIPESTATUS[0]}
  dur=$(( $(date +%s) - start ))

  if [[ $code -ne 0 ]]; then
    echo "[fail] $name 录制退出码=$code 用时 ${dur}s（详见 $OUTDIR/$name.log）"
    RESULT[$name]="FAIL(record code=$code)"
    continue
  fi
  if [[ ! -s "$h5" ]]; then
    echo "[fail] $name 未生成 H5 文件：$h5"
    RESULT[$name]="FAIL(no h5)"
    continue
  fi
  echo "[check] $name -> $h5"
  if check_h5 "$h5" "$name"; then
    echo "[ok] $name 录制+检查通过 用时 ${dur}s"
    RESULT[$name]="ok(${dur}s)"
  else
    echo "[fail] $name H5 检查未通过（详见上方 [FAIL] 行）"
    RESULT[$name]="FAIL(h5 checks)"
  fi
done

echo
echo "==================== 汇总 ===================="
fail=0
for name in "${SELECTED[@]}"; do
  status="${RESULT[$name]:-?}"
  printf '  %-20s %s\n' "$name" "$status"
  [[ "$status" == FAIL* ]] && fail=1
done
echo "输出目录: $OUTDIR"
exit $fail
