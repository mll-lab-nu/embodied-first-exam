"""Replay a certified oversized-ring control in the common lab; no dynamics."""
import hashlib
import json
from pathlib import Path

import hydra
import numpy as np
from omegaconf import OmegaConf
from PIL import Image
from scipy.spatial.transform import Rotation

from .witness_motion import fold_transforms, interpolate

GROUPS = (("horseshoe_left", "chain_upper_1", "chain_lower_1"),
          ("chain_upper_2", "chain_lower_2"),
          ("horseshoe_right", "chain_upper_3", "chain_lower_3"), ("target_ring",))


@hydra.main(version_base="1.3", config_path=str(Path(__file__).resolve().parents[3]/"configs"),
            config_name="horseshoe_ring_witness")
def main(cfg):
    import genesis as gs
    import imageio.v2 as imageio
    from .scene import build_scene

    folder, output = Path(cfg.run.witness_dir), Path(cfg.run.output)
    certificate = json.loads((folder/"certificate.json").read_text())
    path = json.loads((folder/"witness_path.json").read_text())
    template = json.loads(Path(cfg.task.template_path).read_text())
    if not certificate["passed"] or certificate["scale"] != cfg.task.scale:
        raise ValueError("Replay requires a successful geometric extraction certificate at the same scale")
    if hashlib.sha256(json.dumps(path).encode()).hexdigest() != certificate["path_sha256"]:
        raise ValueError("Witness path differs from the certified path")
    if hashlib.sha256(json.dumps(template, sort_keys=True).encode()).hexdigest() != certificate["template_sha256"]:
        raise ValueError("Scene template differs from the certified geometry")
    if cfg.run.video_seconds <= 0 or cfg.run.fps <= 0:
        raise ValueError("Video duration and frame rate must be positive")
    output.mkdir(parents=True, exist_ok=True)
    cfg.env.cameras = OmegaConf.create({n: OmegaConf.to_container(cfg.env.cameras[n], resolve=True)
                                       for n in ("room", "overview", "video")})
    OmegaConf.save(cfg, output/"config.yaml", resolve=True)
    gs.init(backend=gs.cuda if cfg.env.genesis.backend == "cuda" else gs.cpu,
            logging_level="warning", seed=int(cfg.task.seed))
    task = build_scene(cfg, output/"assets")
    if cfg.run.include_robot:
        from topogym.utils.franka import initialize_franka_controller
        initialize_franka_controller(scene=task.scene, manifest=task.manifest,
                                     robot_cfg=cfg.robot_control, settle_steps=0)
    origins = {b["name"]: np.asarray(b["origin_m"]) for b in task.asset_report["bodies"]}
    pivot = template["chain"]["link_radii"][0]*task.assembly.unit

    def pose(state):
        for names, (r, p) in zip(GROUPS, fold_transforms(state, pivot)):
            rotation = task.rotation*Rotation.from_matrix(r)
            for name in names:
                body = task.bodies[name]
                body.set_pos(task.origin+task.rotation.apply(r@origins[name]+p))
                body.set_quat(rotation.as_quat()[[3, 0, 1, 2]])
        # Pose writes do not advance simulation time, so invalidate the visual
        # cache explicitly; otherwise a camera can keep rendering the reset pose.
        task.scene.visualizer.update_visual_states(force_render=True)

    pose(path[0])
    Image.fromarray(task.cameras["room"].render(force_render=True)[0]).save(output/"room.png")
    Image.fromarray(task.cameras["overview"].render(force_render=True)[0]).save(output/"initial.png")
    count = round(cfg.run.video_seconds*cfg.run.fps)
    with imageio.get_writer(output/"preview.mp4", fps=cfg.run.fps, codec="libx264", quality=8,
                           macro_block_size=1, ffmpeg_log_level="error") as writer:
        for i in range(count):
            progress = np.clip((i/max(count-1, 1)-.1)/.8, 0, 1)*(len(path)-1)
            segment = min(int(progress), len(path)-2)
            pose(interpolate(path[segment], path[segment+1], progress-segment))
            writer.append_data(task.cameras["video"].render(force_render=True)[0])
            if i % 20 == 0:
                print(f"Geometric pose replay {i}/{count}", flush=True)
    pose(path[-1])
    Image.fromarray(task.cameras["overview"].render(force_render=True)[0]).save(output/"extracted.png")
    report = dict(scope="oversized_control_geometric_pose_replay", physics_steps=0,
        pose_writes_after_reset=True, inter_body_joints=False, dynamic_execution_verified=False,
        robot_execution_verified=False, lab_obstacle_collision_verified=False,
        certificate=certificate, source_witness_dir=str(folder), frames=count,
        backend=str(cfg.env.genesis.backend), renderer=str(cfg.env.renderer.type))
    (output/"replay_report.json").write_text(json.dumps(report, indent=2)+"\n")
    inner_mm = 2*cfg.task.scale*(template["target_ring"]["centerline_radius"]-template["target_ring"]["wire_radius"])
    (output/"index.html").write_text(f'''<!doctype html><html lang="zh-CN"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Horseshoe Ring 大环正对照</title>
<style>body{{max-width:1100px;margin:32px auto;padding:0 22px;font:17px/1.7 system-ui;background:#f4f5f7;color:#24313c}}
section{{background:white;border-radius:12px;padding:24px;margin:22px 0}}img,video{{width:100%}}a{{color:#14699a}}</style>
<p><a href="../lab_initial/index.html">原尺寸实验室初态</a> ·
<a href="../../../environment-solvability/horseshoe_ring/index.html">尺寸对照与验证结果</a></p>
<h1>大环正对照：几何路径回放</h1><p>场景圆环内径 {inner_mm:.1f} mm，已经大于马蹄外宽。
它能直接滑出，因此用于检查验证流程，不能作为马蹄环谜题解法。</p>
<section><video controls loop preload="metadata" src="preview.mp4" poster="initial.png"></video>
<p>按通过碰撞检查的路径逐帧设置零件位姿；物理步数为 0。机械臂保持初始姿态，未执行抓取。</p></section>
<section><img src="room.png" alt="共用实验室中的大环对照"><p>共用实验室、桌面和机械臂背景。
路径证据只覆盖谜题零件之间的碰撞；场景背景碰撞和动力学不在本次证据范围内。</p></section>
<section><img src="extracted.png" alt="圆环已移到装配之外"><p>终态圆环完全移出装配包围盒。
<a href="replay_report.json">回放与路径检查报告</a> · <a href="assets/template.json">完整尺寸模板</a></p></section></html>''')
    print(f"Review: {output/'index.html'}", flush=True)


if __name__ == "__main__":
    main()
