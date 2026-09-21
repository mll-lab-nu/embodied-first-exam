"""Synchronous camera capture after completed physical steps."""
from contextlib import ExitStack
import hashlib
import json

import numpy as np
from omegaconf import OmegaConf, open_dict


def configure_cameras(cfg, resolution):
    from topogym.world.aloha_cameras import configure_aloha_rig
    metadata = configure_aloha_rig(cfg, keep=(), resolution=resolution, low_pitch_offset_deg=12.)
    # A steep external view keeps the loop visible behind the front forearm
    # and covers the leftward draw plus the optional right-hand spreading.
    target = np.array([float(cfg.task.origin_xy_m[0])-.17, float(cfg.task.origin_xy_m[1])-.07, .94])
    with open_dict(cfg.env.cameras):
        cfg.env.cameras['detail'] = OmegaConf.create(dict(res=list(resolution),
            pos=(target+[0., -.10, .85]).tolist(), lookat=target.tolist(),
            up=[0, 0, 1], fov=50, near=.005, far=12.))
    cfg.env.renderer.type = 'nyx'
    return metadata


def validate_recording(output):
    """Decode every stream and check its frames against the physical clock."""
    import imageio.v2 as imageio
    rig = json.loads((output/'camera_rig.json').read_text())
    frames = json.loads((output/'frames.json').read_text())
    times = np.array([frame['physics_time_s'] for frame in frames])
    expected_times = np.arange(1, len(frames)+1)/rig['fps']
    clock_matches = bool(len(frames) and np.allclose(times, expected_times, atol=1e-8, rtol=0))
    streams = {}
    for name in rig['cameras']:
        path = output/f'{name}.mp4'
        try:
            with imageio.get_reader(path) as reader:
                metadata = reader.get_meta_data()
                count = sum(1 for _ in reader)
            streams[name] = dict(decoded_frames=count, fps=metadata['fps'],
                duration_s=count/metadata['fps'], sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                passed=count == len(frames) and abs(metadata['fps']-rig['fps']) < 1e-8)
        except Exception as exc:
            streams[name] = dict(passed=False, error=f'{type(exc).__name__}: {exc}')
    checks = dict(physical_clock=clock_matches,
        all_camera_transforms=all(set(frame['cameras']) == set(rig['cameras']) for frame in frames),
        continuous_capture=rig['same_continuous_rollout'] and rig['steps_between_camera_captures'] == 0,
        videos=bool(streams) and all(stream['passed'] for stream in streams.values()))
    result = dict(scope='recording_integrity_only; does not certify task or physics success',
                  checks=checks, passed=all(checks.values()), streams=streams,
                  metadata_sha256={name: hashlib.sha256((output/name).read_bytes()).hexdigest()
                                   for name in ('camera_rig.json', 'frames.json')})
    (output/'video_validation.json').write_text(json.dumps(result, indent=2)+'\n')
    return result


class PhysicalRecorder:
    def __init__(self, task, output, *, fps, dt, metadata):
        import imageio.v2 as imageio
        self.task, self.output, self.fps, self.metadata = task, output, fps, metadata
        self.stride = round(1/(fps*dt))
        if self.stride < 1 or abs(self.stride*dt*fps-1) > 1e-8:
            raise ValueError('Recording FPS must divide the physical control rate')
        self.frames, self.stack = [], ExitStack()
        self.writers = {name: self.stack.enter_context(imageio.get_writer(output/f'{name}.mp4',
            fps=fps, codec='libx264', quality=7, macro_block_size=1,
            ffmpeg_params=['-threads', '2'], ffmpeg_log_level='error'))
            for name in task.cameras}
        self.checkpoint()

    def checkpoint(self):
        """Preserve camera evidence if a native crash bypasses Python cleanup."""
        metadata = dict(self.metadata, fps=self.fps, frames=len(self.frames),
            cameras=list(self.writers), same_continuous_rollout=True,
            steps_between_camera_captures=0, untying_verified=False,
            incomplete_capture=True)
        (self.output/'partial_camera_rig.json').write_text(json.dumps(metadata, indent=2)+'\n')
        (self.output/'partial_frames.json').write_text(json.dumps(self.frames)+'\n')

    def capture(self, step, time_s, actions):
        if step % self.stride:
            return
        from PIL import Image
        self.task.scene.visualizer.update_visual_states(force_render=True)
        transforms = {}
        for name, camera in self.task.cameras.items():
            if getattr(camera, '_attached_link', None) is not None:
                camera.move_to_attach()
            # Physical stepping already marks the sensors stale. Nyx refreshes
            # the whole camera batch on the first read; forcing each camera
            # would render the same batch repeatedly at this timestamp.
            rgb = camera.render(force_render=False)[0].copy()
            self.writers[name].append_data(rgb)
            if not self.frames:
                Image.fromarray(rgb).save(self.output/f'initial_{name}.png')
            transforms[name] = dict(transform=np.asarray(camera.transform).tolist(),
                                    intrinsics=np.asarray(camera.intrinsics).tolist())
        self.frames.append(dict(frame=len(self.frames), physics_time_s=time_s,
                                stage=getattr(actions, 'stage', 'free_settle'), cameras=transforms))

    def close(self, report):
        self.stack.close()
        self.metadata.update(fps=self.fps, frames=len(self.frames), cameras=list(self.writers),
                             same_continuous_rollout=True, steps_between_camera_captures=0,
                             untying_verified=bool(report.get('untying_verified', False)))
        (self.output/'camera_rig.json').write_text(json.dumps(self.metadata, indent=2)+'\n')
        (self.output/'frames.json').write_text(json.dumps(self.frames)+'\n')
        validation = validate_recording(self.output)
        status = ('实际机器人解结与释放完成；完整物理套件状态另见报告。'
                  if report.get('untying_verified') else '本次未完成并验证机器人解结。')
        content = ['# 解绳结实际录像', '', status,
                   f"模拟时长：{report.get('simulated_seconds', 0.):.3f} s。",
                   '各相机来自同一次连续执行。接触后辅助抓持的范围以 report.json 为准。', '',
                   '[实际报告](report.json) · [相机](camera_rig.json) · [逐帧状态](frames.json)', '',
                   '| 视角 | MP4 |', '| --- | --- |']
        if report.get('initial_robot_pose'):
            content.insert(4, '起点为双手张爪准备位；未录制中立位到准备位的移动。')
        if report.get('error'):
            content.insert(4, f"执行异常：{report['error']}")
        content += [f'| {name} | [本次录像]({name}.mp4) |' for name in self.writers]
        content += ['', f"录像完整性检查：{validation['passed']}；这不等于任务通过。", '',
                    '| 阶段 | 物理时间 s |', '| --- | --- |']
        content += [f"| {frame['stage']} | {frame['physics_time_s']:.3f} |"
                    for i, frame in enumerate(self.frames)
                    if i == 0 or frame['stage'] != self.frames[i-1]['stage']]
        (self.output/'README.md').write_text('\n'.join(content)+'\n')
