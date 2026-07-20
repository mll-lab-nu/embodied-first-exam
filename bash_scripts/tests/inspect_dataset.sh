#!/usr/bin/env bash
# ============================================================================
# 对一个已录好的 episode 数据集（H5）做"值级"完整性检查——不重新跑仿真。
# 与 verify_dataset_recording.sh 的区别：那个负责"录 + 结构存在性"，本脚本负责
# 对一个已有 H5 做更深的"值是否正确"断言（末帧 is_completed、action==下一帧
# eef、status 一致、子目标边界等），并打印可读 dump。通用，不依赖具体任务。
#
# 用法：
#   bash bash_scripts/tests/inspect_dataset.sh <path/to.h5>
#   bash bash_scripts/tests/inspect_dataset.sh        # 不给路径则取 runs/dataset_tests 下最新的 *.h5
#
# 环境变量：
#   TOPOGYM_VENV=.venv    未激活 venv 时自动 source 的路径
#
# 有硬错误则退出码非 0（适合 CI）。
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

H5="${1:-}"
if [[ -z "$H5" ]]; then
  H5="$(ls -t runs/dataset_tests/*/*.h5 2>/dev/null | head -1 || true)"
  if [[ -z "$H5" ]]; then
    echo "[error] 未给 H5 路径，且 runs/dataset_tests 下也没有 *.h5。" >&2
    echo "  用法: bash bash_scripts/tests/inspect_dataset.sh <path/to.h5>" >&2
    exit 2
  fi
  echo "[inspect] 未给路径，取最新: $H5"
fi
if [[ ! -s "$H5" ]]; then
  echo "[error] 文件不存在或为空: $H5" >&2
  exit 2
fi
if ! python -c "import h5py" 2>/dev/null; then
  echo "[error] 无法 import h5py。请先在 venv 里安装：pip install h5py" >&2
  exit 1
fi

python - "$H5" <<'PY'
import sys
import numpy as np
import h5py

path = sys.argv[1]
errors, warnings = [], []

def req(cond, msg):
    if not cond:
        errors.append(msg)

def _dec(v):
    return v.decode() if isinstance(v, bytes) else v

with h5py.File(path, "r") as f:
    print("schema_version:", _dec(f.attrs.get("schema_version")))
    req("episode_0" in f, "缺 episode_0 组")
    ep = f["episode_0"]

    # ---------- setup ----------
    req("setup" in ep, "缺 setup")
    s = ep["setup"]
    print("\n--- setup attrs ---")
    for k, v in s.attrs.items():
        v = _dec(v)
        if isinstance(v, np.ndarray):
            v = [_dec(x) for x in v.tolist()]
        print(f"  {k} = {v}")
    print("--- setup datasets ---")
    for k in s.keys():
        d = s[k][()]
        if isinstance(d, np.ndarray):
            d = [_dec(x) for x in d.tolist()]
        print(f"  {k} = {d}")
    setup_status = _dec(s.attrs.get("status"))
    setup_success = bool(s.attrs.get("success", False))

    # ---------- timesteps ----------
    ts = sorted((k for k in ep if k.startswith("timestep_")),
                key=lambda x: int(x.split("_")[1]))
    req(len(ts) >= 1, "没有任何 timestep_*")
    print(f"\nframes = {len(ts)}")

    if ts:
        t0 = ep[ts[0]]
        print("\n--- timestep_0 ---")
        for k in t0["obs"]:
            d = t0["obs"][k]
            print(f"  obs/{k}: shape={d.shape} dtype={d.dtype}")
        print("  obs/eef_state   =", t0["obs/eef_state"][:])
        print("  obs/joint_state =", t0["obs/joint_state"][:])
        print("  obs/gripper_state =", t0["obs/gripper_state"][:],
              "is_gripper_close =", bool(t0["obs/is_gripper_close"][()]))
        print("  action/ee_pose_action =", t0["action/ee_pose_action"][:])
        print("  info:", {k: _dec(v) for k, v in t0["info"].attrs.items()})

        tl = ep[ts[-1]]
        print("\n--- last timestep info ---")
        print("  ", {k: _dec(v) for k, v in tl["info"].attrs.items()})

        # ---------- 值级断言 ----------
        req(t0["obs/eef_state"].shape == (7,), f"eef_state 应为 (7,)，实际 {t0['obs/eef_state'].shape}")
        req(t0["action/ee_pose_action"].shape == (7,),
            f"ee_pose_action 应为 (7,)，实际 {t0['action/ee_pose_action'].shape}")

        boundary = [int(ep[k]["info"].attrs["is_subgoal_boundary"]) for k in ts]
        completed = [int(ep[k]["info"].attrs["is_completed"]) for k in ts]
        statuses = {_dec(ep[k]["info"].attrs["status"]) for k in ts}

        # 子目标边界：首帧与末帧应为边界
        req(boundary[0] == 1, "首帧 is_subgoal_boundary 应为 True")
        req(boundary[-1] == 1, "末帧 is_subgoal_boundary 应为 True")
        req(sum(boundary) >= 2, f"is_subgoal_boundary==True 帧数应 >=2，实际 {sum(boundary)}")

        # is_completed：成功时应且仅有末帧为 True；失败时应全 False
        expect_completed = 1 if setup_success else 0
        req(sum(completed) == expect_completed,
            f"is_completed==True 帧数应为 {expect_completed}，实际 {sum(completed)}")
        if setup_success:
            req(completed[-1] == 1, "成功 episode 的末帧 is_completed 应为 True")
            req(sum(completed[:-1]) == 0, "只有末帧可以 is_completed==True")

        # status 一致性
        req(len(statuses) == 1, f"info.status 应全程一致，实际取到 {statuses}")
        req(statuses == {setup_status}, f"info.status {statuses} 应与 setup.status {setup_status!r} 一致")

        # action[t] == eef[t+1]（写入器的设计不变量）
        eefs = np.stack([ep[k]["obs/eef_state"][:] for k in ts])
        acts = np.stack([ep[k]["action/ee_pose_action"][:] for k in ts])
        req(np.allclose(acts[:-1], eefs[1:], atol=1e-5),
            "ee_pose_action[t] 应等于 eef_state[t+1]")

        # rgb 非全黑
        for rk in [k for k in t0["obs"] if k.endswith("_rgb")]:
            nz = sum(int(np.any(ep[k]["obs"][rk][()])) for k in ts)
            if nz == 0:
                errors.append(f"所有帧 {rk} 全黑（渲染没出图）")
            elif nz < len(ts):
                warnings.append(f"{rk} 有 {len(ts)-nz}/{len(ts)} 帧全黑（可能 warmup）")

        # proprio 退化检测：整段全零多半是读取坏了（如 CUDA 张量转 numpy 失败）
        joints_all = np.stack([ep[k]["obs/joint_state"][:] for k in ts])
        if not np.any(joints_all):
            errors.append("joint_state 全程全零（多半是 proprio 读取坏了，如 CUDA 张量转 numpy 失败）")
        eef_all = np.stack([ep[k]["obs/eef_state"][:] for k in ts])
        if not np.any(eef_all):
            errors.append("eef_state 全程全零")

        print(f"\nis_subgoal_boundary==True 帧数 = {sum(boundary)}")
        print(f"is_completed==True 帧数 = {sum(completed)} (期望 {expect_completed})")
        print(f"info.status = {statuses}  setup.status = {setup_status!r}  success = {setup_success}")
        print(f"ee_pose_action[t]==eef_state[t+1] ? {np.allclose(acts[:-1], eefs[1:], atol=1e-5)}")

for w in warnings:
    print(f"[warn] {w}")
if errors:
    print()
    for e in errors:
        print(f"[FAIL] {e}")
    sys.exit(1)
print("\n[值级检查全部通过]")
PY
rc=$?
echo
if [[ $rc -eq 0 ]]; then
  echo "[ok] 值级完整性检查通过: $H5"
else
  echo "[fail] 值级完整性检查未通过（详见上方 [FAIL] 行）: $H5"
fi
exit $rc
