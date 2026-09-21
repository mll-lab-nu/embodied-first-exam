"""Motion-first lock proposals: object route, inferred slots/stops, and arm IK.

This is an inspection tool, not a replacement physical oracle. The saved
successful run supplies the robot, grasp convention, placement and IK seed.
Only the aligned solving phase is synthesized; pickup/release are not rerun.

    .venv-gs121-nyx/bin/python -m topogym.tasks.lock_picking.inverse_variants
"""
from __future__ import annotations

import argparse
from dataclasses import asdict, replace
import hashlib
import json
from pathlib import Path

import mujoco
import numpy as np
from omegaconf import OmegaConf
from scipy.spatial.transform import Rotation

from topogym.robot.assets import robot_asset
from ._staged_lock_geometry import LockGeometry, write_disc, write_endpoint, write_key, DISC_COLORS, ENDPOINT_COLOR
from ._aperture_outline import paint_aperture_outline, disc_colors
from .certificate import certificate
from .grasp import hand_pose

ROOT = Path(__file__).resolve().parents[3]
SOURCE = ROOT / "runs/environment_bootstrap/lock_picking/handle_clearance"
OUTPUT = ROOT / "runs/environment-solvability/lock_picking/inverse_variants_v1"
SPECS = (
    ("one_retreat", "一次回退 · 缩短解锁", [30.], 15.),
    ("two_unequal", "两次回退 · 不等角复位", [28., 32.], 16.),
    ("three_retreats", "三次回退 · 四槽递进", [24., 24., 24.], 12.),
)


def dump(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def motion_variant(resets, first_turn):
    """Edit the successful action grammar before deriving any new geometry."""
    total = sum(resets)
    states = []
    d, theta, alpha, beta = 0., 0., 0., 0.

    def append(phase):
        states.append(dict(phase=phase, depth=d, key_deg=theta,
                           disc_deg=[alpha, beta, 0.]))

    append("对轴起点")
    theta = -total
    append("盘外转至入口方向")
    d = 1.
    append("进入 D1")
    d = 2.
    append("进入 D2")
    theta += first_turn; alpha += first_turn; beta += first_turn
    append("联动至 D1 上限")
    for i, delta in enumerate(resets):
        d = 1.
        append(f"第 {i + 1} 次回退到 D1")
        theta -= delta; alpha -= delta
        append(f"仅 D1 复位 {delta:g}°")
        d = 1.5
        append("前进到盘间空隙")
        theta += delta
        append(f"空隙中钥匙转回 {delta:g}°")
        d = 2.
        append("重新进入 D2")
        turn = delta if i < len(resets) - 1 else -alpha
        theta += turn; alpha += turn; beta += turn
        append("联动至 D1 上限" if i < len(resets) - 1 else "联动对准 D3 / END")
    d = 3.
    append("进入 D3")
    d = 4.
    append("进入固定终点")
    return states


def infer_geometry(seed, states, source_stops):
    # While two discs are engaged, theta = alpha + s1 = beta + s2.
    coupled = [s for s in states if s["depth"] == 2]
    slots = sorted({round(s["key_deg"] - s["disc_deg"][0], 8) for s in coupled})
    second = {round(s["key_deg"] - s["disc_deg"][1], 8) for s in coupled}
    if len(second) != 1:
        raise ValueError("The proposed motion requires multiple D2 slots")
    angles = np.array([s["disc_deg"] for s in states])
    stops = OmegaConf.create(OmegaConf.to_container(source_stops, resolve=True))
    stops[0].bounds_deg = [float(angles[:, 0].min()), float(angles[:, 0].max())]
    stops[1].bounds_deg = [-10., float(angles[:, 1].max() + 15.)]
    g = replace(seed, slots=(tuple(slots), tuple(second), (0.,)),
                initial_disc_deg=(0., 0., 0.), initial_key_deg=0., endpoint_deg=0.)
    g.validate()
    return g, stops


def analytic_route_check(g, stops, states):
    """Check affine angles over every exact axial-overlap interval.

    Each active key tab/disc pair must remain inside ONE slot band for the
    entire interval, so the endpoint bounds certify the intervening angles.
    This covers the coaxial aperture model, not arbitrary mesh collisions.
    """
    half = (g.tab_thickness + g.disc_thickness) / (2 * g.pitch)
    checked = 0
    minimum_margin = float("inf")
    for a, b in zip(states, states[1:]):
        lo_d, hi_d = a["depth"], b["depth"]
        cuts = {0., 1.}
        if hi_d != lo_d:
            for tab in range(3):
                for disc in range(4):
                    for sign in (-1, 1):
                        u = (disc + tab + 1 + sign * half - lo_d) / (hi_d - lo_d)
                        if 0 < u < 1:
                            cuts.add(float(u))
        cuts = sorted(cuts)
        for angle, stop in zip(zip(a["disc_deg"], b["disc_deg"]), stops):
            assert min(angle) >= stop.bounds_deg[0] - 1e-8
            assert max(angle) <= stop.bounds_deg[1] + 1e-8
        for left, right in zip(cuts, cuts[1:]):
            mid_d = lo_d + (hi_d - lo_d) * (left + right) / 2
            for tab in range(3):
                for disc in range(4):
                    if abs(mid_d - tab - disc - 1) >= half:
                        continue
                    disc_a = a["disc_deg"][disc] if disc < 3 else 0.
                    disc_b = b["disc_deg"][disc] if disc < 3 else 0.
                    x = a["key_deg"] - disc_a
                    y = b["key_deg"] - disc_b
                    angles = [x + (y - x) * u for u in (left, right)]
                    slots = g.slots[disc] if disc < 3 else [g.endpoint_deg]
                    margin = max(g.slot_half_deg - g.tab_half_deg -
                                 max(abs(v - slot - 360 * k) for v in angles)
                                 for slot in slots for k in (-1, 0, 1))
                    assert margin >= -1e-8, (a, b, tab, disc, margin)
                    minimum_margin = min(minimum_margin, margin)
                    checked += 1
    return dict(passed=True, method="Exact axial overlap intervals and affine angular bounds",
                checked_tab_disc_intervals=checked,
                minimum_angular_clearance_deg=minimum_margin,
                scope="Coaxial aperture geometry and rotor angle limits; no contact dynamics")


class ArmIK:
    def __init__(self, cfg, seed_frames):
        self.model = mujoco.MjModel.from_xml_path(robot_asset(cfg.robot_control))
        self.data = mujoco.MjData(self.model)
        self.hand = self.model.body("hand").id
        self.base = np.asarray(cfg.env.robot_mount.pos)
        self.mount_r = Rotation.from_euler("xyz", cfg.env.robot_mount.euler, degrees=True)
        self.bias = float(cfg.task.motion.grasp_roll_bias_deg)
        self.arm_q = np.array([self.model.joint(n).qposadr[0]
                              for n in cfg.robot_control.robot.joint_names[:7]])
        self.arm_d = np.array([self.model.joint(n).dofadr[0]
                              for n in cfg.robot_control.robot.joint_names[:7]])
        self.bounds = np.array([self.model.joint(n).range
                               for n in cfg.robot_control.robot.joint_names[:7]])
        self.seed = next(s for s in reversed(seed_frames) if s["phase"] == "entry_align")
        errors = []
        for frame in seed_frames:
            self.data.qpos[:] = frame["robot_qpos"]
            mujoco.mj_kinematics(self.model, self.data)
            p = self.base + self.mount_r.apply(self.data.xpos[self.hand])
            errors.append(float(np.linalg.norm(p - frame["hand_pos"])))
        self.seed_fk_error = max(errors)
        assert self.seed_fk_error < 1e-5, self.seed_fk_error

    def solve(self, pos, quat):
        target_p = self.mount_r.inv().apply(pos - self.base)
        target_r = self.mount_r.inv() * Rotation.from_quat(quat[[1, 2, 3, 0]])
        jac_p = np.zeros((3, self.model.nv)); jac_r = np.zeros_like(jac_p)
        for _ in range(100):
            mujoco.mj_kinematics(self.model, self.data)
            mujoco.mj_comPos(self.model, self.data)
            p = self.data.xpos[self.hand]
            r = Rotation.from_matrix(self.data.xmat[self.hand].reshape(3, 3))
            ep = target_p - p
            er = (target_r * r.inv()).as_rotvec()
            if np.linalg.norm(ep) < 2e-6 and np.linalg.norm(er) < 2e-5:
                return float(np.linalg.norm(ep)), float(np.linalg.norm(er))
            mujoco.mj_jacBody(self.model, self.data, jac_p, jac_r, self.hand)
            jac = np.vstack((jac_p[:, self.arm_d], .15 * jac_r[:, self.arm_d]))
            error = np.r_[ep, .15 * er]
            dq = jac.T @ np.linalg.solve(jac @ jac.T + 1e-7 * np.eye(6), error)
            dq *= min(1., .06 / max(np.max(np.abs(dq)), 1e-12))
            self.data.qpos[self.arm_q] = np.clip(self.data.qpos[self.arm_q] + dq,
                                                 self.bounds[:, 0] + 1e-6,
                                                 self.bounds[:, 1] - 1e-6)
        raise RuntimeError(f"IK failed: position {np.linalg.norm(ep)}, rotation {np.linalg.norm(er)}")

    def route(self, g, states):
        self.data.qpos[:] = self.seed["robot_qpos"]
        frames, errors = [], []
        for segment, (a, b) in enumerate(zip(states, states[1:])):
            steps = max(1, int(np.ceil(abs(b["depth"] - a["depth"]) * g.pitch / .002)),
                        int(np.ceil(abs(b["key_deg"] - a["key_deg"]))))
            for u in np.linspace(0., 1., steps + 1)[0 if segment == 0 else 1:]:
                depth = a["depth"] + u * (b["depth"] - a["depth"])
                angle = a["key_deg"] + u * (b["key_deg"] - a["key_deg"])
                discs = np.array(a["disc_deg"]) + u * (np.array(b["disc_deg"]) - a["disc_deg"])
                pos, quat = hand_pose(g, depth, angle, self.bias)
                errors.append(self.solve(pos, quat))
                assert not g.clearance(depth, angle, discs)
                frames.append(dict(segment=segment, u=float(u), depth=float(depth),
                    key_deg=float(angle), disc_deg=discs.tolist(),
                    hand_pos_m=pos.tolist(), hand_quat_wxyz=quat.tolist(),
                    robot_qpos=self.data.qpos.tolist()))
        q = np.array([f["robot_qpos"] for f in frames])[:, self.arm_q]
        report = dict(passed=True, samples=len(frames), max_position_error_m=max(x[0] for x in errors),
            max_rotation_error_rad=max(x[1] for x in errors),
            minimum_arm_joint_limit_margin_rad=float(np.minimum(q-self.bounds[:, 0], self.bounds[:, 1]-q).min()),
            maximum_adjacent_arm_joint_change_rad=float(np.abs(np.diff(q, axis=0)).max()),
            source_fk_max_position_error_m=self.seed_fk_error,
            sample_spacing="At most 2 mm axial travel and 1 degree key rotation",
            scope="Aligned solving phase; arm IK and joint limits only",
            robot_scene_collision_verified=False, physical_execution_verified=False,
            pickup_release_rerun=False)
        return frames, report


def export_assets(g, stops, cfg, folder):
    colors = disc_colors(cfg.task)
    finish = cfg.task.get('visual', {}).get('plate_finish')
    outline = cfg.task.get('visual', {}).get('aperture_outline')
    floor = float(cfg.env.frames.table_surface.origin[2])
    for i in range(3):
        path = write_disc(g, g.slots[i], folder / f"disc{i}", float(cfg.task.physics.disc_mass),
                   float(cfg.task.physics.disc_damping), colors[i], stop=stops[i],
                   mount_z=floor + .028 - g.axis_z)
        paint_aperture_outline(path, g, g.slots[i], colors[i], outline, finish=finish)
    write_key(g, folder / "key", float(cfg.task.physics.key_mass))
    path = write_endpoint(g, folder / "endpoint")
    paint_aperture_outline(path, g, (g.endpoint_deg,), ENDPOINT_COLOR, outline, goal_plate=True)


def build(source=SOURCE, output=OUTPUT):
    source, output = Path(source), Path(output)
    if (output / "summary.json").exists():
        raise FileExistsError(f"Choose a new output directory: {output}")
    output.mkdir(parents=True, exist_ok=True)
    cfg = OmegaConf.load(source / "config.yaml")
    seed = LockGeometry.from_config(json.loads((source / "layout.json").read_text()))
    saved = json.loads((source / "frames.json").read_text())
    source_report = json.loads((source / "report.json").read_text())
    assert source_report["success"] and source_report["observed_retreat_count"] == 2
    arm = ArmIK(cfg, saved)
    results = []
    for name, title, resets, first_turn in SPECS:
        states = motion_variant(resets, first_turn)
        g, stops = infer_geometry(seed, states, cfg.task.rotor_stops)
        proof = certificate(g, stops)
        assert proof["minimum_required_decoupling_retreats"] == len(resets)
        assert proof["unique_shortest_branch_sequence"]
        geometry_check = analytic_route_check(g, stops, states)
        frames, ik_report = arm.route(g, states)
        folder = output / name
        folder.mkdir(exist_ok=True)
        export_assets(g, stops, cfg, folder / "assets")
        instance = OmegaConf.create(OmegaConf.to_container(cfg, resolve=True))
        # aligned_entry preserves explicitly supplied geometry; limited_two_retreats overwrites it.
        instance.task.variant = "aligned_entry"
        instance.task.geometry = asdict(g)
        instance.task.rotor_stops = stops
        instance.run.output = str(folder / "inspection")
        instance.run.inspect_only = True
        instance.run.build_only = False
        dump(folder / "layout.json", asdict(g))
        dump(folder / "keyframes.json", states)
        dump(folder / "certificate.json", proof)
        dump(folder / "ik_trace.json", dict(scope=ik_report["scope"], frames=frames))
        OmegaConf.save(instance, folder / "inspection_config.yaml")
        result = dict(name=name, title=title, reset_angles_deg=resets,
            first_coupled_turn_deg=first_turn, necessary_retreats=len(resets),
            geometry=asdict(g), rotor_stops=OmegaConf.to_container(stops, resolve=True),
            keyframes=states, geometry_check=geometry_check, certificate=proof, ik=ik_report,
            key_angle_range_deg=[min(s["key_deg"] for s in states), max(s["key_deg"] for s in states)],
            note="Inspection config only. The existing physical oracle explicitly requires two retreats; these candidates need a generalized feedback policy and physical qualification.")
        dump(folder / "result.json", result)
        results.append(result)
        print(json.dumps(dict(name=name, retreats=len(resets), ik=ik_report), ensure_ascii=False), flush=True)
    summary = dict(source=str(source), source_success=True, source_retreats=2,
        source_frames_sha256=hashlib.sha256((source / "frames.json").read_bytes()).hexdigest(),
        provenance="Edit the successful action grammar, infer slots from theta-alpha/theta-beta, then warm-start continuous-branch sampled IK from the recorded entry state.",
        variants=results)
    dump(output / "summary.json", summary)
    template = Path(__file__).with_name("inverse_variants_review.html").read_text()
    (output / "index.html").write_text(template.replace("__VARIANT_DATA__", json.dumps(results, ensure_ascii=False)))
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=SOURCE)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    build(args.source, args.output)
