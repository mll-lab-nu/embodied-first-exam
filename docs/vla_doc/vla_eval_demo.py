"""π0.5 → Harbor Session：图像/状态 → 动作块 → 在线录像和 trajectory.npz。

前提：openpi 服务已适配 TopoGym ALOHA 的关节顺序、符号和米制夹爪宽度，
返回绝对关节目标 (H, 14)。不能直接套用任意官方 ALOHA/DROID/LIBERO checkpoint。
完整服务配置约定和运行命令见同目录 README.md。本脚本不训练或下载模型。
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import time

import numpy as np


CAMERAS = ("cam_high", "cam_left_wrist", "cam_right_wrist")
ACTION_LAYOUT = [
    f"{arm}/{joint}" if joint != "gripper" else f"{arm}_gripper"
    for arm in ("left", "right")
    for joint in ("waist", "shoulder", "elbow", "forearm_roll", "wrist_angle", "wrist_rotate", "gripper")
]


def write_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_session(adapter):
    """使用选中 Harbor task 自带的实现，不复制 Session 或创建新 Env 接口。"""
    spec = importlib.util.spec_from_file_location("vla_harbor_adapter", adapter)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module.Session


def observation(session, prompt):
    from openpi_client import image_tools

    # AlohaInputs 接收 CHW uint8；取图不推进物理。模型只收到 RGB、本体状态和指令。
    images = {
        camera: np.ascontiguousarray(
            image_tools.resize_with_pad(session.render_frame(camera), 224, 224).transpose(2, 0, 1)
        )
        for camera in CAMERAS
    }
    return {
        "images": images,
        "state": np.asarray(session.joint_positions(), dtype=np.float32),
        "prompt": prompt,
    }


def action_chunk(response):
    actions = np.asarray(response["actions"], dtype=np.float32)
    if actions.ndim != 2 or actions.shape[0] == 0 or actions.shape[1] != 14:
        raise ValueError(f"Expected non-empty (H, 14) actions, got {actions.shape}")
    if not np.isfinite(actions).all():
        raise ValueError("Model actions contain NaN or infinity")
    # 不自行归一化或将 delta 当 absolute；单位转换由已适配的模型服务完成。
    return actions


def run_episode(session, policy, *, prompt, execute_steps, max_control_steps, output, record):
    """使用当前冻结实例运行一次闭环；Session 构造时已经恢复起点。"""
    started = time.monotonic()
    calls, steps = 0, 0
    phase = "setup"
    result = {"stop_reason": "control_step_limit", "error": None}
    session.record_start()  # 记录动作，与是否录像独立
    try:
        policy.reset()
        if record:
            # Harbor 已有在线录像；不重放，不增加额外 step。
            # every=1 保留每个控制步（含终止步），视频 fps 与控制频率一致。
            session.start_video(output / "live.mp4", fps=round(session.control_hz), every=1)
        while steps < max_control_steps:
            phase = "observation"
            obs = observation(session, prompt)
            phase = "inference"
            calls += 1
            response = policy.infer(obs)
            phase = "action_validation"
            actions = action_chunk(response)
            count = min(execute_steps, len(actions), max_control_steps - steps)
            phase = "execution"
            for action in actions[:count]:
                guard_reached = session.step(action)
                steps += 1
                # step() 的布尔返回值是 runaway guard，不是任务成功/失败。
                if session.episode_end is not None or guard_reached:
                    result["stop_reason"] = session.episode_end or "session_step_guard"
                    break
            if session.episode_end is not None or guard_reached:
                break
            # 丢弃 chunk 剩余部分，重新取观测并推理。
    except Exception as error:
        result.update(stop_reason="error", error=repr(error), error_phase=phase)
    finally:
        # 推理/动作出错也尽量封口视频、保留已提交轨迹。清理错误同样写入结果。
        cleanup_errors = []
        if record:
            try:
                session.stop_video()
            except Exception as error:
                cleanup_errors.append(f"stop_video: {error!r}")
        try:
            actions = session.record_stop()
            session.save_trajectory(actions, output / "trajectory.npz", meta={"prompt": prompt})
            result["recorded_action_rows"] = len(actions)
        except Exception as error:
            cleanup_errors.append(f"save_trajectory: {error!r}")
        try:
            result["harbor_status"] = session.status()
        except Exception as error:
            cleanup_errors.append(f"status: {error!r}")
        result.update(control_steps=steps, inference_calls=calls,
                      rollout_wall_s=round(time.monotonic() - started, 3), cleanup_errors=cleanup_errors)
        write_json(output / "result.json", result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task-dir", type=Path, required=True,
                        help="Harbor unlimited task 目录，使用其 environment/rcb_topogym.py 和 instance.json")
    parser.add_argument("--policy-host", default="localhost")
    parser.add_argument("--policy-port", type=int, default=8001)
    parser.add_argument("--policy-id", required=True, help="模型配置、checkpoint 标识/哈希，用于复现")
    parser.add_argument("--policy-hz", type=float, required=True, help="模型动作行的训练/适配频率，须等于 Session 控制频率")
    parser.add_argument("--prompt", help="默认使用冻结 instance.json 的 text")
    parser.add_argument("--execute-steps", type=int, default=10)
    parser.add_argument("--max-control-steps", type=int, default=400)
    parser.add_argument("--record", action="store_true", help="调用 Harbor start_video/stop_video 在线录像")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.execute_steps < 1 or args.max_control_steps < 1:
        parser.error("execute-steps and max-control-steps must be positive")
    if not np.isfinite(args.policy_hz) or args.policy_hz <= 0:
        parser.error("policy-hz must be finite and positive")

    environment = args.task_dir.resolve() / "environment"
    adapter, instance_path = environment / "rcb_topogym.py", environment / "instance.json"
    if not adapter.is_file() or not instance_path.is_file():
        parser.error(f"Missing Harbor adapter/instance in {environment}; select an unlimited task directory")
    instance = json.loads(instance_path.read_text())
    if instance.get("action_layout") != ACTION_LAYOUT:
        parser.error("This π0.5 example supports the ALOHA 14-dimensional action layout only")
    if not np.isclose(args.policy_hz, instance["control_hz"], rtol=0, atol=1e-6):
        parser.error("policy-hz differs from the frozen instance; adapt the model timing first")
    prompt = args.prompt if args.prompt is not None else instance.get("text")
    if not isinstance(prompt, str) or not prompt.strip():
        parser.error("Supply --prompt or an instance with non-empty text")

    from openpi_client import websocket_client_policy

    args.output.mkdir(parents=True, exist_ok=False)
    # Session 在 import 时读取日志位置，保持本次运行产物在 output 下。
    os.environ["RCB_SESSION_LOG"] = str(args.output.resolve() / "rcb_session_log.jsonl")
    os.environ["RCB_SESSION_LOG_KEEP"] = ""
    Session = load_session(adapter)
    run = {
        "task_dir": str(args.task_dir.resolve()), "task": instance["task"],
        "instance_sha256": sha256(instance_path), "adapter_sha256": sha256(adapter),
        "demo_sha256": sha256(__file__), "policy_id": args.policy_id, "policy_hz": args.policy_hz,
        "policy_host": args.policy_host, "policy_port": args.policy_port,
        "prompt": prompt, "execute_steps": args.execute_steps, "max_control_steps": args.max_control_steps,
        "record": args.record, "model_cameras": CAMERAS,
        "model_contract": "ALOHA CHW uint8 RGB; state/actions in Harbor layout, rad + gripper width m; absolute targets",
    }
    write_json(args.output / "run.json", run)
    (args.output / "instance.json").write_bytes(instance_path.read_bytes())
    # 先连接模型再建场景，避免等待模型时占用仿真显存。
    policy = websocket_client_policy.WebsocketClientPolicy(host=args.policy_host, port=args.policy_port)
    write_json(args.output / "policy_metadata.json", policy.get_server_metadata())
    session = Session(instance["task"], instance=instance_path, strict=True)
    try:
        if session.action_layout != ACTION_LAYOUT or not np.isclose(
            session.control_hz, args.policy_hz, rtol=0, atol=1e-6
        ):
            raise ValueError("Live Session layout/timing differs from the declared policy contract")
        if args.record and not np.isclose(session.control_hz, round(session.control_hz), rtol=0, atol=1e-6):
            raise ValueError("This example's every-step video requires an integer control_hz")
        missing = set(CAMERAS) - set(session.VIDEO_CAMERAS)
        if missing:
            raise ValueError(f"Missing ALOHA cameras: {sorted(missing)}")
        write_json(args.output / "session.json", {
            "config": session.config, "action_layout": session.action_layout, "control_hz": session.control_hz,
            "instance_sha": session.instance_sha, "instance_exact": session.instance_exact,
            "instance_matches": session.instance_matches,
        })
        result = run_episode(session, policy, prompt=prompt, execute_steps=args.execute_steps,
                             max_control_steps=args.max_control_steps, output=args.output, record=args.record)
    finally:
        session.close()
    print(json.dumps(result, ensure_ascii=False))
    return 1 if result["error"] or result["cleanup_errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
