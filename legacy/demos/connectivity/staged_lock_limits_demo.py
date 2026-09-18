"""Visible mechanical stop qualification, with small applied test torques.

This is a fixture bench test, not robot key manipulation or a retreat oracle.
The mechanism is stepped by Genesis; no rotor poses are assigned after reset.
"""
from contextlib import ExitStack
import json
from pathlib import Path
import hydra
import genesis as gs
import imageio.v2 as imageio
import numpy as np
from omegaconf import OmegaConf
from PIL import Image

from topogym.tasks_legacy.connectivity.staged_lock import StagedLockSceneBuilder, numpy
from topogym.utils.franka import initialize_franka_controller


@hydra.main(version_base='1.3', config_path='../../configs', config_name='staged_lock_limits')
def main(cfg):
    output = Path(cfg.run.output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    names = list(cfg.run.record_cameras)
    cfg.env.cameras = OmegaConf.create({name: OmegaConf.to_container(
        cfg.env.cameras[name], resolve=True) for name in names})
    gs.init(backend=gs.cuda, logging_level='warning', seed=int(cfg.task.seed))
    task = StagedLockSceneBuilder(cfg.env, cfg.task, cfg.robot_control).build(
        show_viewer=False, asset_dir=output/'assets')
    controller = initialize_franka_controller(scene=task.scene, manifest=task.manifest,
        robot_cfg=cfg.robot_control, settle_steps=int(cfg.task.initialization.settle_steps))
    # Park the actual arm clear of the apparatus before the fixture test.
    # This is a controlled robot motion, not hiding or deleting its visuals.
    from demos.connectivity.staged_lock_physical_demo import move
    move(controller,controller.hand_pos()+np.array([0,0,.23]),controller.hand_quat(),200)
    move(controller,np.array([-.24,-.15,1.48]),controller.hand_quat(),240)
    OmegaConf.save(cfg, output/'config.yaml', resolve=True)

    def render(name):
        return task.cameras[name].render()[0]

    def snapshot(label):
        if bool(cfg.recording.enabled):
            for name in names:
                Image.fromarray(render(name)).save(output/f'{label}_{name}.png')

    def framing():
        vertices = numpy(controller.robot.get_vverts()).reshape(-1, 3)
        margins = {}
        for name in cfg.run.exterior_cameras:
            cam = task.cameras[name]
            matrix = cam.transform.copy(); matrix[:3, 1:3] *= -1
            inv = np.linalg.inv(matrix)
            p = vertices@inv[:3, :3].T+inv[:3, 3]
            pixel = p@cam.intrinsics.T
            pixel = pixel[:, :2]/pixel[:, 2:3]
            margins[name] = float(min(pixel.min(), (cam.res[0]-1-pixel[:, 0]).min(),
                                      (cam.res[1]-1-pixel[:, 1]).min()))
        return margins

    rotor_links = [[link.idx for link in disc.links] for disc in task.discs]
    stop_links = [[link.idx for link in task.manifest.get(f'lock_stop_frame_{i+1}').links]
                  for i in range(3)]
    frames = []; measurements = []; phase_results = {}
    # Constant torque continues at the end stops, visibly demonstrating arrest.
    bounds = np.array([list(stop.bounds_deg) for stop in cfg.task.rotor_stops])
    continuous = np.diff(bounds,axis=1).ravel() >= 360.-1e-8
    torque_nm = .030 if np.any(continuous) else .012
    phases = ([('initial',1.,0.),('upper_stop',8.,torque_nm),('lower_stop',8.,-torque_nm),('rest',1.,0.)]
              if np.any(continuous) else [('initial',1.,0.),('upper_stop',3.,torque_nm),
                  ('lower_stop',4.5,-torque_nm),('reverse',1.5,torque_nm),('rest',1.,0.)])
    fps = int(cfg.recording.fps)
    every = int(cfg.recording.every_n_steps)
    dt = float(cfg.env.sim.dt)
    snapshot('initial')
    with ExitStack() as stack:
        writers = {name: stack.enter_context(imageio.get_writer(
            output/f'{name}.mp4', fps=fps, codec='libx264', quality=8,
            macro_block_size=1, ffmpeg_params=['-movflags', '+faststart']))
            for name in names} if bool(cfg.recording.enabled) else {}
        step = 0
        for phase, seconds, torque in phases:
            for disc in task.discs:
                disc.control_dofs_force([torque])
            phase_measurements = []
            for _ in range(round(seconds/dt)):
                controller.step(1); step += 1
                state = task.state()
                contact = task.last_contacts
                a, b = numpy(contact['link_a']), numpy(contact['link_b'])
                forces = []
                for moving, fixed in zip(rotor_links, stop_links):
                    mask = (np.isin(a, moving)&np.isin(b, fixed)) | (np.isin(b, moving)&np.isin(a, fixed))
                    forces.append(float(np.linalg.norm(numpy(contact['force'])[mask], axis=-1).sum()))
                row = dict(step=step, time_s=step*dt, phase=phase, test_torque_nm=torque,
                           disc_deg=state['disc_deg'], disc_speed=state['disc_speed'],
                           stop_contact_force_n=forces)
                measurements.append(row); phase_measurements.append(row)
                if step % every == 0:
                    frames.append(row)
                    for name, writer in writers.items(): writer.append_data(render(name))
            phase_results[phase] = dict(final_deg=state['disc_deg'],
                final_speed=state['disc_speed'],
                late_peak_stop_force_n=np.max([r['stop_contact_force_n'] for r in phase_measurements[-100:]], axis=0).tolist())
            snapshot(phase)
            print(phase, phase_results[phase], flush=True)
    angles = np.array([row['disc_deg'] for row in measurements])
    overshoot = np.maximum(bounds[:, 0]-angles.min(axis=0), angles.max(axis=0)-bounds[:, 1])
    finite=~continuous
    endpoint_error = max(np.max(np.abs(np.array(phase_results['upper_stop']['final_deg'])[finite]-bounds[finite, 1]),initial=0),
                         np.max(np.abs(np.array(phase_results['lower_stop']['final_deg'])[finite]-bounds[finite, 0]),initial=0))
    max_overshoot=float(np.max(overshoot[finite],initial=0))
    travel=angles.max(axis=0)-angles.min(axis=0)
    free_ok=bool(np.all(travel[continuous]>360.))
    report = dict(demo='visible mechanical stops: torque bench', robot_performs_task=False,
        mechanism_pose_writes_after_reset=False, applied_test_torque_nm=torque_nm,
        joint_limit_solver_enabled=bool(cfg.task.physics.enable_joint_limit),
        bounds_deg=bounds.tolist(), measured_min_deg=angles.min(axis=0).tolist(),
        measured_max_deg=angles.max(axis=0).tolist(), max_overshoot_deg=max(0.,max_overshoot),
        continuous_rotors=continuous.tolist(),angle_travel_deg=travel.tolist(),continuous_rotation_check_passed=free_ok,
        max_endpoint_error_deg=float(endpoint_error),
        stop_check_passed=bool(endpoint_error < 1 and max_overshoot < 1 and free_ok),
        phases=phase_results, arm_margin_px=framing(),
        max_contact_penetration_m=task.max_contact_penetration,
        seconds=step*dt, video_frames=len(frames), fps=fps, renderer=str(cfg.env.renderer.type),
        necessary_retreat_count_verified=False, unique_solution_verified=False)
    (output/'report.json').write_text(json.dumps(report, indent=2)+'\n')
    (output/'frames.json').write_text(json.dumps(frames, indent=2)+'\n')
    (output/'measurements.json').write_text(json.dumps(measurements, indent=2)+'\n')
    (output/'index.html').write_text('''<!doctype html><meta charset="utf-8">
<title>实体转角限位展示</title><style>body{background:#17212a;color:#eee;font:18px sans-serif;margin:28px}
video,img{max-width:100%}a{color:#8cddff}</style><h1>可见的实体转角限位</h1>
<p>灰色完整外环与支架固定；每环只有一个贯通弧槽。圆盘同色连接耳带动银色销沿槽运动，槽的封闭端面负责限位。</p>
<p>Genesis 接触物理台架测试，机械臂未执行钥匙任务。实际力矩、持续时间和逐阶段数据见运行报告。
没有逐帧指定圆盘角度；本台架不验证必要回退次数或唯一解。连续槽的转盘没有关节角限位。</p>
<p><a href="report.json">物理报告</a></p>
<p><a href="initial_limit_detail.png">初态</a> · <a href="upper_stop_limit_detail.png">抵住一端</a> ·
<a href="lower_stop_limit_detail.png">抵住另一端</a></p>'''+''.join(
        f'<h2>{name}</h2><video controls src="{name}.mp4"></video>'
        for name in sorted(names,key=lambda name:name!='limit_detail')))
    print(json.dumps(report, indent=2), flush=True)
    if not report['stop_check_passed']:
        raise RuntimeError('Visible stop qualification failed; inspect the report')


if __name__ == '__main__': main()
