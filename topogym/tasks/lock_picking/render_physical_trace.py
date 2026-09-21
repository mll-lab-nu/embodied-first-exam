"""Three clean camera views of the measured, successful 150 mm lock rollout.

This is offline rendering, with zero simulation steps. Arm joints, key poses,
and rotor angles come from the physical state log. The old logger saved pad
aperture, not all passive Robotiq joints: linkage poses are reconstructed with
the shared calibration and their pad-centre error is reported explicitly.
"""
from __future__ import annotations

import argparse
from contextlib import ExitStack
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import time
import xml.etree.ElementTree as ET

import numpy as np
from omegaconf import OmegaConf
from PIL import Image
from scipy.spatial.transform import Rotation

ROOT = Path(__file__).resolve().parents[3]
SOURCE = ROOT / "runs/environment-solvability/lock_picking/spaced_initial/attempt06"
CAMERAS = ("agentview", "front_oblique", "wrist")


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, data):
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")


def load_source(source):
    cfg = OmegaConf.load(source / "source_config.yaml")
    result = json.loads((source / "result.json").read_text())
    frames = [json.loads(line) for line in (source / "states.jsonl").read_text().splitlines()]
    if not all(result.get(k) for k in ("success", "reached_endpoint", "at_rest", "grasp_released", "execution_ok")):
        raise ValueError("Source execution did not finish successfully and release the key")
    if not frames or [f["step"] for f in frames] != list(range(0, frames[-1]["step"] + 1, 10)):
        raise ValueError("Expected complete, uniformly sampled physical states")
    if frames[0]["grasp_active"] or frames[-1]["grasp_active"]:
        raise ValueError("Source must start before grasp and end after release")
    if any(f["force_stop"] or f["geometry_error_steps"] for f in frames):
        raise ValueError("Source contains an execution violation")
    for key in ("key_tip_pos", "key_quat", "disc_deg"):
        if not np.allclose(frames[-1][key], result["state"][key], atol=1e-10, rtol=0):
            raise ValueError(f"Source result disagrees with final recorded {key}")
    if abs(float(cfg.task.geometry.pitch) - .150) > 1e-12:
        raise ValueError("Expected the standard 150 mm spacing")
    return cfg, result, frames


def physics_signature(path):
    """Compare inertials, joints and collision meshes, excluding visual assets."""
    tree = ET.parse(path)
    for link in tree.findall('.//link'):
        for visual in link.findall('visual'):
            link.remove(visual)
    hashes = {}
    for mesh in tree.findall('.//collision/geometry/mesh'):
        p = Path(mesh.get('filename'))
        # Archived URDF filenames are relative to the archived asset directory.
        if not p.is_absolute():
            p = path.parent / p
        hashes[p.name] = sha(p)
        mesh.set('filename', p.name)
    return ET.tostring(tree.getroot()).decode(), hashes


def render(source, output, preview_only=False, preview_frames=None, resume=False):
    from hydra import compose, initialize_config_dir
    import genesis as gs
    from topogym.robot.franka import FrankaPositionIKController
    from topogym.robot.gripper import robotiq_joint_targets
    from .scene import LockPickingSceneBuilder, numpy

    source, output = Path(source).resolve(), Path(output).resolve()
    cfg, physical_result, frames = load_source(source)
    if preview_frames is not None and (not preview_only or not preview_frames or
            any(i < 0 or i >= len(frames) for i in preview_frames)):
        raise ValueError('Preview frame indices require --preview-only and must lie within the source')
    if resume and (preview_only or not output.is_dir() or
            json.loads((output/'report.json').read_text()).get('complete')):
        raise ValueError('Only an incomplete full rendering can be resumed')
    output.mkdir(parents=True, exist_ok=resume)
    evidence = output / 'source_evidence'
    evidence.mkdir(exist_ok=resume)
    for name in ('source_config.yaml', 'result.json', 'states.jsonl', 'commands.jsonl'):
        if resume:
            if sha(source/name) != sha(evidence/name):
                raise ValueError('Physical source changed before resume: '+name)
        else:
            shutil.copy2(source / name, evidence / name)
    if not resume:
        shutil.copy2(source.parent / 'control.py', evidence / 'physical_controller.py')
    previous_records = []
    if resume:
        for line in (output/'camera_poses.jsonl').read_text().splitlines():
            record = json.loads(line)
            if record['frame'] != len(previous_records):
                raise ValueError('Non-contiguous saved camera records')
            previous_records.append(record)
        attempts = output/'render_attempts'
        attempts.mkdir(exist_ok=True)
        shutil.copy2(output/'render_source.py', attempts/f'attempt_{len(list(attempts.glob("*.py"))):02d}.py')
    # Redraw the last complete frame to verify the restart boundary.
    resume_start = max(0, len(previous_records)-1)
    for index in range(resume_start):
        for name in CAMERAS:
            with Image.open(output/'frames'/name/f'{index:05d}.jpg') as im:
                im.verify()
    shutil.copy2(__file__, output / 'render_source.py')
    with initialize_config_dir(config_dir=str(ROOT / 'configs'), version_base='1.3'):
        current = compose(config_name='lock_picking_spaced_preview')
    if OmegaConf.to_container(cfg.task, resolve=True) != OmegaConf.to_container(current.task, resolve=True):
        raise ValueError('Current task differs from the recorded physical task')
    cfg.env.genesis.backend = 'cpu'
    cfg.env.renderer.type = 'rasterizer'
    cfg.env.appearance = current.env.appearance
    cfg.env.cameras = OmegaConf.create({
        n: OmegaConf.to_container(cfg.env.cameras[n] if n in cfg.env.cameras else current.env.cameras[n], resolve=True)
        for n in CAMERAS})
    # Keep the complete long fixture in the exterior view. Aim the wrist at
    # the actual Robotiq pad plane rather than beyond the short gripper.
    cfg.env.cameras.front_oblique.pos = [1.05, -.8, 1.68]
    cfg.env.cameras.front_oblique.lookat = [.05, .15, 1.12]
    cfg.env.cameras.front_oblique.fov = 55
    cfg.env.cameras.wrist.attach.offset_lookat = [0., 0., .105]
    cfg.env.cameras.wrist.res = [960, 540]
    cfg.run.output = str(output)
    cfg.run.record_cameras = list(CAMERAS)
    if resume and OmegaConf.to_container(cfg, resolve=True) != OmegaConf.to_container(
            OmegaConf.load(output/'render_config.yaml'), resolve=True):
        raise ValueError('Render configuration changed before resume')
    OmegaConf.save(cfg, output / 'render_config.yaml', resolve=True)
    save(output / 'report.json', dict(complete=False, stage='building', preview_only=preview_only))
    gs.init(backend=gs.cpu, precision='32', logging_level='warning', seed=int(cfg.task.seed))
    task = LockPickingSceneBuilder(cfg.env, cfg.task, cfg.robot_control).build(asset_dir=output / 'assets')
    compared = []
    for p in sorted((source / 'assets').rglob('*.urdf')):
        relative = p.relative_to(source / 'assets')
        if physics_signature(p) != physics_signature(output / 'assets' / relative):
            raise ValueError(f'Physical asset changed: {relative}')
        compared.append(str(relative))
    save(output / 'physics_equivalence.json', dict(passed=True, urdfs=compared,
         scope='Same collision mesh bytes, mass, inertia and joints; task config unchanged; visual materials changed'))
    robot = task.manifest.get('robot')
    controller = FrankaPositionIKController(task.scene, robot, cfg.robot_control)
    template = numpy(robot.get_qpos()).reshape(-1).copy()
    mapping = {}
    for name in robotiq_joint_targets(.04):
        joint_name = {'right_driver_joint':'finger_joint1', 'left_driver_joint':'finger_joint2'}.get(name, 'r85_' + name)
        mapping[name] = robot.get_joint(joint_name).qs_idx_local[0]
    fps = 1. / (10 * float(cfg.env.sim.dt))
    peaks = dict(arm_qpos_rad=0., hand_position_m=0., hand_rotation_rad=0., key_position_m=0.,
                 key_rotation_rad=0., disc_angle_deg=0., reconstructed_grip_center_m=0., reconstructed_half_gap_m=0.)
    selected = sorted({0, len(frames)-1, *range(0, len(frames), 400)}) if preview_only else range(len(frames))
    if preview_frames is not None:
        selected = sorted(set(preview_frames))
    start = time.monotonic()
    stages = set()
    camera_records = (output / 'camera_poses.jsonl').open('w', buffering=1)
    for record in previous_records[:resume_start]:
        camera_records.write(json.dumps(record)+'\n')
    boundary_errors = {}
    def rotation_error(a, b):
        return float((Rotation.from_quat(np.asarray(a)[[1,2,3,0]]).inv() * Rotation.from_quat(np.asarray(b)[[1,2,3,0]])).magnitude())
    with ExitStack() as stack:
        stack.enter_context(camera_records)
        frame_dirs = {} if preview_only else {n:output/'frames'/n for n in CAMERAS}
        for folder in frame_dirs.values():
            folder.mkdir(parents=True, exist_ok=resume)
        for index in selected:
            frame = frames[index]
            q = template.copy()
            q[:7] = frame['arm_qpos']
            half_gap = float(np.mean(frame['gripper']))
            for name, value in robotiq_joint_targets(half_gap).items():
                q[mapping[name]] = value
            robot.set_qpos(q, zero_velocity=True)
            task.key.set_qpos([*frame['key_tip_pos'], *frame['key_quat']], zero_velocity=True)
            for disc, angle in zip(task.discs, frame['disc_deg']):
                disc.set_qpos([np.radians(angle)], zero_velocity=True)
            state = task.state()
            errors = dict(arm_qpos_rad=float(np.max(np.abs(controller.arm_qpos()-frame['arm_qpos']))),
                hand_position_m=float(np.linalg.norm(controller.hand_pos()-frame['hand_pos'])),
                hand_rotation_rad=rotation_error(controller.hand_quat(), frame['hand_quat']),
                key_position_m=float(np.linalg.norm(np.array(state['key_tip_pos'])-frame['key_tip_pos'])),
                key_rotation_rad=rotation_error(state['key_quat'],frame['key_quat']),
                disc_angle_deg=float(np.max(np.abs(np.array(state['disc_deg'])-frame['disc_deg']))),
                reconstructed_grip_center_m=float(np.linalg.norm(controller.grasp_center_pos()-frame['grip_pos'])),
                reconstructed_half_gap_m=float(np.max(np.abs(controller.gripper_qpos()-frame['gripper']))))
            for key,value in errors.items():
                peaks[key]=max(peaks[key],value)
            if errors['hand_position_m']>1e-5 or errors['hand_rotation_rad']>1e-4 or errors['key_position_m']>1e-6 or errors['disc_angle_deg']>1e-4:
                raise ValueError(f'Rendered state differs from measured physics: {errors}')
            if index < resume_start:
                stages.add(frame['stage'])
                continue
            task.scene.visualizer.update_visual_states(force_render=True)
            task.cameras['wrist'].move_to_attach()
            transforms = {}
            for name in CAMERAS:
                camera=task.cameras[name]
                # No scene.step() advances Genesis' render cache timestamp.
                # Force refresh after pose assignments, including wrist motion.
                rgb=camera.render(force_render=True)[0]
                if resume and index == resume_start and previous_records:
                    old = np.asarray(Image.open(frame_dirs[name]/f'{index:05d}.jpg')).astype(float)
                    difference = float(np.mean(np.abs(rgb.astype(float)-old)))
                    boundary_errors[name] = difference
                    if difference > 3.0 or not np.allclose(camera.transform,
                            previous_records[index]['cameras'][name], atol=1e-6, rtol=0):
                        raise ValueError(f'Render changed across resume boundary: {name}, {difference}')
                # Separate rendering from encoding: concurrent ffmpeg stdin
                # pipes can block when the CPU renderer is also active.
                if frame_dirs:
                    Image.fromarray(rgb).save(frame_dirs[name]/f'{index:05d}.jpg',quality=95)
                if preview_only or frame['stage'] not in stages or index==len(frames)-1:
                    Image.fromarray(rgb).save(output / f'frame_{index:05d}_{name}.jpg',quality=90)
                transforms[name]=np.asarray(camera.transform).tolist()
            camera_records.write(json.dumps(dict(frame=index,step=frame['step'],time_s=index/fps,cameras=transforms))+'\n')
            stages.add(frame['stage'])
            if preview_only or index%25==0:
                print(json.dumps(dict(frame=index,total=len(frames),elapsed_s=round(time.monotonic()-start,1),errors=peaks)),flush=True)
    report=dict(complete=not preview_only, preview_only=preview_only, source_success=True,
        task_id='lock_picking',variant='standard_150mm_three_teeth_two_retreats',
        source_directory=str(source),source_sha256={n:sha(evidence/n) for n in ('source_config.yaml','result.json','states.jsonl','commands.jsonl')},
        cameras=list(CAMERAS),fps=fps,source_frame_count=len(frames),rendered_frame_count=len(selected),
        duration_s=len(frames)/fps,recording_range_s=[0.,frames[-1]['step']*float(cfg.env.sim.dt)],
        source_simulation_dt=float(cfg.env.sim.dt),render_simulation_steps=0,
        classification='physical_trace_rerender_with_calibrated_gripper_reconstruction',
        exact_recorded_quantities=['arm_qpos','key_tip_pos','key_quat','disc_deg'],
        gripper_reconstruction='Measured pad aperture mapped to calibrated symmetric linkage; passive joint positions were not logged by the source. This is not an exact full-joint replay.',
        max_reconstruction_errors=peaks,renderer='Genesis CPU rasterizer / Mesa',ui_overlays=False,
        assisted_grasp_in_source=True,source_grasp_released=True,new_physics_execution=False,
        resumed_from_frame=resume_start, resume_boundary_pixel_mean_error=boundary_errors,
        source_result=physical_result)
    if not preview_only:
        save(output/'report.json',{**report,'complete':False,'stage':'encoding'})
        for name in CAMERAS:
            print('ENCODING '+name,flush=True)
            subprocess.run(['ffmpeg','-nostdin','-y','-v','error','-xerror',
                '-framerate',str(fps),'-start_number','0','-i',str(frame_dirs[name]/'%05d.jpg'),
                '-frames:v',str(len(frames)),'-an','-c:v','libx264','-preset','fast','-crf','18',
                '-threads','2','-filter_threads','1','-pix_fmt','yuv420p','-movflags','+faststart',
                str(output/f'{name}.mp4')],check=True)
        report['video_sha256']={n:sha(output/f'{n}.mp4') for n in CAMERAS}
    save(output/'report.json',report)
    print('FINISHED '+str(output),flush=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,default=SOURCE)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--preview-only',action='store_true')
    parser.add_argument('--preview-frames',type=int,nargs='+')
    parser.add_argument('--resume',action='store_true',help='Continue an interrupted full rendering using its saved frames')
    args=parser.parse_args()
    render(args.source,args.output,args.preview_only,args.preview_frames,args.resume)


if __name__=='__main__':
    main()
