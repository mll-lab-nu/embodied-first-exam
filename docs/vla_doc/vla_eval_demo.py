"""最小 VLA 评测示例：make → reset(seed) → act(obs) → step(action)，逐 episode 记录结果。

模型调用是占位函数 VLAPolicy._infer：它把当前关节状态重复成一个动作块，机器人只是保持姿态，
用来验证 obs → 模型输入 → 动作块 → action 字典 → env.step 这条链路能跑通。
接入真实模型时只需替换 _infer。

从仓库根目录运行（需要 CUDA；输出目录必须尚不存在）：
    export TOPOGYM_VISUAL_ASSET_ROOT="$PWD/.external/nyx-assets"
    .venv-gs121-nyx/bin/python docs/vla_doc/vla_eval_demo.py --task cast_coil --seeds 0 1 \
        --max-control-steps 40 --output runs/vla_eval/demo_01
加 --record 改走 SegmentRunner，每个 episode 额外写出多视角 MP4 和逐 tick 日志。
"""
import argparse
from collections import deque
import hashlib
import json
from pathlib import Path
import time

import numpy as np
from PIL import Image

import topogym

# 夹爪原生坐标的（全开, 全闭）值。来源：
#   aloha:         robot_control_configs/aloha_position_ik.yaml 的 gripper.open_qpos / closed_qpos，单位米（手指导轨位置）
#   panda_robotiq: robot/panda_robotiq/description.py 的 GraspDescription，单位弧度（Robotiq 驱动关节角）
GRIPPER_OPEN_CLOSED = {"aloha": (0.037, 0.002), "panda_robotiq": (0.0, 0.8)}

# 喂给模型的相机及顺序；名字来自 config/profiles/camera_configs/*_observation.yaml
CAMERAS = {"aloha": ("cam_high", "cam_left_wrist", "cam_right_wrist"),
           "panda_robotiq": ("agentview", "wrist")}

# 示例文字，不是项目的正式任务指令；项目目前没有逐任务的语言指令字段，评测方需要自己定并固定下来
PROMPTS = {"cast_coil": "Assemble the two metal pieces into the four-layer coil, then release them."}


class VLAPolicy:
    """act(obs) 每次返回一个控制步的 action 字典。

    模型的扁平向量约定（本示例自定，接真实模型时按模型的训练约定改）：
    按 action_spec["arms"] 的顺序，每条臂 = 各关节角(rad) + 1 个归一化夹爪开度（0 全闭，1 全开）。
    ALOHA 是 [左 6 + 左夹爪, 右 6 + 右夹爪] 共 14 维；Panda 是 7 + 1 共 8 维。
    """

    def __init__(self, prompt, image_size=(224, 224), execute_steps=10):
        self.prompt = prompt
        self.image_size = image_size
        self.execute_steps = execute_steps   # 每个动作块执行前几步后重新推理
        self.queue = deque()

    def initialize(self, context):
        # 普通循环和 SegmentRunner 都会在 episode 开始时调用；context 里有 action_spec
        spec = context["action_spec"]
        self.arms = tuple(spec["arms"])
        self.groups = spec["groups"]
        self.open_m, self.closed_m = GRIPPER_OPEN_CLOSED[spec["robot_id"]]
        self.cameras = CAMERAS[spec["robot_id"]]
        self.queue.clear()

    def act(self, obs):
        if not self.queue:
            chunk = self._infer(self.images(obs), self.state(obs), self.prompt)
            self.queue.extend(chunk[:self.execute_steps])
        return self.to_action(self.queue.popleft())

    def images(self, obs):
        # obs["rgb"][cam] 是 480×848×3 uint8
        return {cam: np.asarray(Image.fromarray(np.asarray(obs["rgb"][cam])).resize(self.image_size, Image.BILINEAR))
                for cam in self.cameras}

    def state(self, obs):
        parts = []
        for arm in self.arms:
            robot = obs["robot"][arm]
            fingers = robot["finger_position_m"] if "finger_position_m" in robot else robot["finger_position_rad"]
            parts += [np.asarray(robot["joint_position_rad"]), [self.opening(fingers[0])]]
        return np.concatenate(parts).astype(np.float32)

    def opening(self, native):
        return float(np.clip((native - self.closed_m) / (self.open_m - self.closed_m), 0., 1.))

    def to_action(self, row):
        action, i = {}, 0
        for arm in self.arms:
            group = self.groups[arm]
            n = len(group["arm_joint_names"])
            limits = np.asarray(group["joint_limits_rad"])
            q = np.clip(row[i:i + n], limits[:, 0], limits[:, 1])
            g = float(np.clip(row[i + n], 0., 1.))
            action[arm] = {"joint_position_rad": q.tolist(),
                           group["gripper_field"]: self.closed_m + g * (self.open_m - self.closed_m)}
            i += n + 1
        return action

    def _infer(self, images, state, prompt):
        # 占位：真实实现把 images / state / prompt 发给模型服务，返回 (H, D) 的动作块
        return np.tile(state, (10, 1))


def classify(info):
    """把 step 返回的公开 info 归成一种结果。"""
    if info["task_outcome"] == "success":
        return "success"
    if info["task_outcome"] == "failure":
        return "task_failure"
    if info["termination_reason"] == "time_limit":
        return "time_limit" if info["evaluation_status"] == "available" else "unevaluated"
    return "unfinished"


def run_episode(env, policy, seed):
    start = time.monotonic()
    env.reset(seed=seed)                     # 管理方：重建场景
    reset_s = time.monotonic() - start
    actor = env.interaction()                # 操作方句柄；reset 后旧句柄失效
    policy.initialize({"action_spec": actor.action_spec})
    obs = actor.observe()
    steps, info = 0, None

    def finish(**row):
        return dict(row, reset_wall_s=round(reset_s, 2),
                    rollout_wall_s=round(time.monotonic() - start - reset_s, 2))

    while True:
        try:
            action = policy.act(obs)
        except Exception as error:           # 策略自身出错
            return finish(outcome="policy_error", control_steps=steps, error=repr(error))
        try:
            obs, reward, terminated, truncated, info = actor.step(action)
        except ValueError as error:          # 非法动作：物理未推进，episode 仍可用；这里直接判负
            return finish(outcome="invalid_action", control_steps=steps, error=str(error))
        except RuntimeError as error:        # 环境故障：Env 已 faulted，只能 reset
            return finish(outcome="env_error", control_steps=steps, error=str(error))
        steps += 1
        if terminated or truncated:
            return finish(outcome=classify(info), control_steps=steps, task_success=info["task_success"],
                          failure_code=info.get("failure_code"), sim_time_s=info["sim_time_s"])


def run_episode_recorded(env, policy, seed, output, source_sha256):
    from topogym.simulator import SegmentRunner
    start = time.monotonic()
    env.reset(seed=seed)
    reset_s = time.monotonic() - start
    # 输出目录必须尚不存在；SegmentRunner 接管这个 episode 的 step，并写录像与日志
    with SegmentRunner(env, output / f"seed_{seed}") as runner:
        result = runner.run_policy(request_id=f"seed-{seed}", policy=policy,
                                   submission_hash=source_sha256, mode="limited")
    feedback = result["feedback"]
    outcome = (classify(feedback) if result["reason"] in {"env_terminal", "env_time_limit"}
               else result["reason"])
    # 每个相机一个 MP4，另有横向拼接的 combined.mp4
    videos = output / f"seed_{seed}" / "segments" / f"segment_{result['segment_id']}" / "videos"
    return dict(outcome=outcome, control_steps=result["control_steps"], task_success=feedback.get("task_success"),
                failure_code=feedback.get("failure_code"), segment_status=result["status"],
                reset_wall_s=round(reset_s, 2), rollout_wall_s=round(time.monotonic() - start - reset_s, 2),
                videos=sorted(p.relative_to(output).as_posix() for p in videos.glob("*.mp4")))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--task", default="cast_coil")
    parser.add_argument("--variation", default="base")
    parser.add_argument("--seeds", type=int, nargs="+", default=[0])
    parser.add_argument("--max-control-steps", type=int, default=400)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--record", action="store_true")
    args = parser.parse_args()
    args.output.mkdir(parents=True)          # 已存在就报错，不覆盖旧结果

    control_decimation = 10                  # 每个控制步 10 个物理 tick（2.5 ms）= 25 ms
    policy = VLAPolicy(PROMPTS[args.task])
    source_sha256 = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    rows = []
    with topogym.make(args.task, variation_id=args.variation,
                      control_mode="JOINT_ABS", observation_mode="JOINT",
                      control_decimation=control_decimation,
                      max_physics_steps=args.max_control_steps * control_decimation) as env:
        for seed in args.seeds:
            start = time.monotonic()
            row = (run_episode_recorded(env, policy, seed, args.output, source_sha256) if args.record
                   else run_episode(env, policy, seed))
            row.update(task=args.task, variation=args.variation, seed=seed,
                       wall_time_s=round(time.monotonic() - start, 2))
            rows.append(row)
            print(json.dumps(row, ensure_ascii=False), flush=True)
            with open(args.output / "results.jsonl", "a") as f:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")

    outcomes = [row["outcome"] for row in rows]
    summary = dict(task=args.task, variation=args.variation, episodes=len(rows),
                   success_rate=outcomes.count("success") / len(rows),
                   outcomes={name: outcomes.count(name) for name in sorted(set(outcomes))},
                   source_sha256=source_sha256)
    (args.output / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False))
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
