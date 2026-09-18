"""Synchronous camera capture after completed physical steps."""
from contextlib import ExitStack
import html
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
                  checks=checks, passed=all(checks.values()), streams=streams)
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
        cards=''.join(f'<figure><video controls class="sync" src="{name}.mp4" poster="initial_{name}.png"></video>'
                      f'<figcaption>{name}</figcaption></figure>' for name in self.writers)
        labels = dict(settle='初始静置', left_approach='左手接近', right_approach='右手接近',
            left_lower='左手下降', right_lower='右手下降', left_close='左手闭爪', right_close='右手闭爪',
            left_lift='左手抬升', right_clearance='支撑段让位', pin_pull='抽绳', pin_pull_extra='补充抽绳',
            spread_loop='展开回环', lower='放回',
            transfer='交接', right_lower_to_table='右手放回', release='松手', withdraw='退出',
            release_withdraw='松手并退出', free_settle='释放后静置')
        phases = [(i, frame) for i, frame in enumerate(self.frames)
                  if i == 0 or frame['stage'] != self.frames[i-1]['stage']]
        jumps = ''.join(f'<button onclick="seek({i/self.fps})">'
                        f'{html.escape(labels.get(frame["stage"], frame["stage"]))} '
                        f'· {frame["physics_time_s"]:.1f}s</button>' for i, frame in phases)
        status = ('本次完成了实际机器人解结与释放；网格收敛等完整物理验收状态仍须另查。'
                  if report.get('untying_verified') else '本次尚未完成并验证机器人解结。')
        status += f" 本次实际模拟 {report.get('simulated_seconds', 0.):.3f} 秒。"
        if report.get('initial_robot_pose'):
            status += ' 起点为夹爪张开的预抓取准备位；初始中立位到准备位的运动未录制。'
        status += ' 双指接触后启用显式辅助抓持约束，松手时解除。'
        if report.get('error'):
            status += ' 停止原因：'+html.escape(report['error'])
        if not validation['passed']:
            status += ' 视频完整性检查未通过，详见录制核对。'
        (self.output/'index.html').write_text('''<!doctype html><meta charset="utf-8"><title>Knot physical recording</title>
<style>body{font:16px system-ui;max-width:1280px;margin:32px auto;padding:20px;background:#f3f5f7;color:#203040}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:16px}figure{margin:0}video{width:100%}button{padding:12px}</style>
<h1>解绳结 · 实际物理试跑录像</h1><p>'''+status+''' 各视角来自同一次连续物理执行。</p>
<p><a href="report.json">实际结果</a> · <a href="frames.json">逐帧物理时间与阶段</a> ·
<a href="camera_rig.json">相机标定</a> · <a href="video_validation.json">录制核对</a></p><button onclick="toggle()">同步播放 / 暂停</button>
<p>阶段跳转（标注物理时间）：</p><nav>'''+jumps+'''</nav><div class="grid">'''+cards+'''</div>
<script>const streams=[...document.querySelectorAll('.sync')];function toggle(){let play=streams[0].paused,t=streams[0].currentTime;
streams.forEach(v=>{v.currentTime=t;play?v.play():v.pause()})}
function seek(t){streams.forEach(v=>{v.pause();v.currentTime=t})}
streams[0].addEventListener('seeked',()=>streams.slice(1).forEach(v=>{if(Math.abs(v.currentTime-streams[0].currentTime)>.1)v.currentTime=streams[0].currentTime}));</script>''')
