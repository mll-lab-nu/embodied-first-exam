"""Batched MuJoCo Warp training physics; never imports CPU deployment evaluator."""

import numpy as np
import torch
import mujoco_warp as mw
import warp as wp
from .models import Robot, verify
from .task import Reference, BALANCED_MODES, DT, DURATION


class WarpEnv:
    def __init__(
        self, robot, num_envs=128, device="cuda:2", seed=42, noise=0.003, motor_range=0.1, delay_steps=2, bank_size=12
    ):
        if not device.startswith("cuda:"):
            raise ValueError("Training physics requires CUDA")
        self.robot = robot
        self.nenv = num_envs
        self.device = device
        self.r = Robot(robot)
        self.archive_hash = verify(robot)
        self.noise = noise
        self.delay_steps = delay_steps
        self.gen = torch.Generator(device=device).manual_seed(seed)
        self.rng = np.random.default_rng(seed)
        self.steps = round(DURATION / DT)
        self.n = self.r.n
        torch.cuda.set_device(device)
        wp.init()
        wp.config.quiet = True
        self.stream = wp.Stream(device)
        self.torch_stream = torch.cuda.ExternalStream(self.stream.cuda_stream, device=device)
        torch.cuda.synchronize(device)
        torch.cuda.set_stream(self.torch_stream)

        def tensor(x, dtype=torch.float32):
            return torch.as_tensor(x, dtype=dtype, device=device)

        self.tensor = tensor
        r = self.r
        self.qids = tensor(r.qids, torch.long)
        self.vids = tensor(r.vids, torch.long)
        self.aids = tensor(r.aids, torch.long)
        self.home = tensor(r.home)
        self.speed = tensor(r.speed)
        self.siteids = tensor([r.m.site(n).id for n in ["left_hand", "right_hand"]], torch.long)
        self.actq = tensor(r.m.jnt_qposadr[r.m.actuator_trnid[:, 0]], torch.long)
        self.actv = tensor(r.m.jnt_dofadr[r.m.actuator_trnid[:, 0]], torch.long)
        self.kp = tensor(r.m.actuator_gainprm[:, 0])
        self.kd = tensor(-r.m.actuator_biasprm[:, 2])
        self.bounds = tensor(r.m.actuator_ctrlrange)
        self.train_trajectory_seeds = [int(x) for x in self.rng.integers(0, 2**31, size=bank_size)]
        bank = []
        for i, s in enumerate(self.train_trajectory_seeds):
            ref = Reference(robot, s, BALANCED_MODES[i % len(BALANCED_MODES)])
            rows = []
            for k in range(self.steps + 1):
                target, twist = ref.sample(k * DT)
                rows.append(np.r_[target[0], *[np.r_[p, rot.reshape(-1)] for p, rot in target[1]], twist])
            bank.append(rows)
        self.bank = tensor(np.asarray(bank))
        self.bank_size = bank_size
        with wp.ScopedDevice(device), wp.ScopedStream(self.stream):
            self.m = mw.put_model(r.m)
            self.nom = mw.put_model(r.m)
            # Per-world actuator randomization. Nominal observation model stays unchanged.
            from mjlab.sim.randomization import expand_model_fields

            expand_model_fields(self.m, num_envs, ["actuator_gainprm", "actuator_biasprm", "actuator_forcerange"])
            scale = 1 + (torch.rand((num_envs, 1), device=device, generator=self.gen) * 2 - 1) * motor_range
            self.motor_scales = scale.clone()
            wp.to_torch(self.m.actuator_gainprm)[:, :, 0] *= scale
            wp.to_torch(self.m.actuator_biasprm)[:, :, 1] *= scale
            wp.to_torch(self.m.actuator_forcerange)[:] *= scale[:, :, None]
            self.d = mw.put_data(r.m, r.d, nworld=num_envs, nconmax=64, njmax=256)
            self.nd = mw.put_data(r.m, r.d, nworld=num_envs, nconmax=64, njmax=256)
            self.q = wp.to_torch(self.d.qpos)
            self.v = wp.to_torch(self.d.qvel)
            self.ctrl = wp.to_torch(self.d.ctrl)
            self.nq = wp.to_torch(self.nd.qpos)
            self.nv = wp.to_torch(self.nd.qvel)
            self.npos = wp.to_torch(self.nd.site_xpos)
            self.nrot = wp.to_torch(self.nd.site_xmat)
            self.bias = wp.to_torch(self.nd.qfrc_bias)
            self.pos = wp.to_torch(self.d.site_xpos)
            self.rot = wp.to_torch(self.d.site_xmat)
            # Compile before capture; captured calls integrate actual rigid-body dynamics.
            mw.forward(self.nom, self.nd)
            mw.step(self.m, self.d)
            wp.synchronize_device(device)
            with wp.ScopedCapture(device=device) as capture:
                for _ in range(10):
                    mw.step(self.m, self.d)
                mw.kinematics(self.m, self.d)
            self.step_graph = capture.graph
            with wp.ScopedCapture(device=device) as capture:
                mw.forward(self.nom, self.nd)
            self.observe_graph = capture.graph
        self.ids = torch.arange(num_envs, device=device)
        self.ticks = torch.zeros(num_envs, device=device, dtype=torch.long)
        self.trajectory = torch.zeros_like(self.ticks)
        self.delays = torch.randint(0, delay_steps + 1, (num_envs,), device=device, generator=self.gen)
        self.encoder_bias = torch.zeros_like(self.q)
        self.history = torch.zeros((num_envs, delay_steps + 1, r.m.nu), device=device)
        self.previous = torch.zeros((num_envs, self.n), device=device)
        self.reset(torch.ones(num_envs, device=device, dtype=torch.bool))
        self.obs = self.observe()

    def reset(self, mask):
        self.q[mask] = self.home
        self.v[mask] = 0
        self.ctrl[mask] = self.home[self.actq]
        wp.to_torch(self.d.qacc_warmstart)[mask] = 0
        wp.to_torch(self.d.time)[mask] = 0
        self.ticks[mask] = 0
        new = torch.randint(self.bank_size, (self.nenv,), device=self.device, generator=self.gen)
        self.trajectory[mask] = new[mask]
        bias = torch.randn(self.q.shape, device=self.device, generator=self.gen) * self.noise * 0.5
        self.encoder_bias[mask] = bias[mask]
        self.history[mask] = self.home[self.actq]
        self.previous[mask] = 0

    def target(self):
        return self.bank[self.trajectory, self.ticks]

    @staticmethod
    def pose_error(q, pos, rot, target):
        left = target[:, 3:15]
        right = target[:, 15:27]
        goals = torch.stack([left, right], dim=1)
        gp = goals[:, :, :3]
        gr = goals[:, :, 3:].reshape(-1, 2, 3, 3)
        angle = 0.5 * torch.cross(rot, gr, dim=-2).sum(dim=-1)
        hand = torch.cat([gp - pos, angle], dim=-1).reshape(-1, 12)
        return torch.cat([target[:, :3] - q[:, :3], hand], dim=-1)

    def observe(self):
        self.nq.copy_(
            self.q + self.encoder_bias + torch.randn(self.q.shape, device=self.device, generator=self.gen) * self.noise
        )
        self.nv.copy_(self.v + torch.randn(self.v.shape, device=self.device, generator=self.gen) * 0.015)
        with wp.ScopedDevice(self.device), wp.ScopedStream(self.stream):
            wp.capture_launch(self.observe_graph)
        target = self.target()
        err = self.pose_error(self.nq[:, self.qids], self.npos[:, self.siteids], self.nrot[:, self.siteids], target)
        return torch.cat(
            [self.nq[:, self.qids] - self.home[self.qids], self.nv[:, self.vids], err, target[:, 27:]], dim=-1
        )

    def step(self, action, action_penalty=0.01):
        action = action.clamp(-1, 1)
        vel = action * self.speed
        command = self.home[self.actq] + self.bias[:, self.actv] / self.kp
        command[:, self.aids] = (
            self.nq[:, self.qids]
            + self.kd[self.aids] / self.kp[self.aids] * vel
            + self.bias[:, self.vids] / self.kp[self.aids]
        )
        command = command.clamp(self.bounds[:, 0], self.bounds[:, 1])
        self.history = torch.cat([self.history[:, 1:], command[:, None]], dim=1)
        self.ctrl.copy_(self.history[self.ids, self.delay_steps - self.delays])
        with wp.ScopedDevice(self.device), wp.ScopedStream(self.stream):
            wp.capture_launch(self.step_graph)
        self.ticks += 1
        err = self.pose_error(self.q[:, self.qids], self.pos[:, self.siteids], self.rot[:, self.siteids], self.target())
        # Training reward uses six component tolerances and SO(3) geodesic orientation errors.
        goal = self.target()
        gr = torch.stack([goal[:, 6:15], goal[:, 18:27]], dim=1).reshape(-1, 2, 3, 3)
        rel = gr @ self.rot[:, self.siteids].transpose(-1, -2)
        angles = torch.acos(((rel.diagonal(dim1=-2, dim2=-1).sum(-1) - 1) / 2).clamp(-1, 1))
        yaw = torch.atan2(torch.sin(err[:, 2]), torch.cos(err[:, 2])).abs()
        parts = torch.stack(
            [
                err[:, :2].norm(dim=-1) / 0.06,
                yaw / 0.12,
                err[:, 3:6].norm(dim=-1) / 0.07,
                err[:, 9:12].norm(dim=-1) / 0.07,
                angles[:, 0] / 0.2,
                angles[:, 1] / 0.2,
            ],
            dim=-1,
        )
        reward = torch.exp(-parts).mean(dim=-1) - action_penalty * (action - self.previous).square().mean(dim=-1)
        self.previous = action.clone()
        unstable = (
            ~torch.isfinite(self.q).all(dim=-1)
            | ~torch.isfinite(self.v).all(dim=-1)
            | (self.v.abs().amax(dim=-1) > 100)
        )
        done = (self.ticks >= self.steps) | unstable
        reward = torch.where(unstable, torch.full_like(reward, -1), reward)
        terminal = {"tracking_reward": reward.detach(), "terminated": unstable, "truncated": self.ticks >= self.steps}
        self.reset(done)
        self.obs = self.observe()
        return self.obs, reward, done, terminal
