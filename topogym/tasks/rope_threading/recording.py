"""Synchronized views of this run's physical state, with task-specific labels."""
import html
import json

from topogym.tasks.knot_untying.recording import PhysicalRecorder, validate_recording

PHASE_LABELS = (
    "初始静置", "右手接近绳端", "右手抓取", "抬升绳端", "绳端对齐", "左手接近另一端", "左手抓取",
    "抬升左端", "双手抬绳", "接近第一环", "第一环前调姿", "向第一环穿入", "左端前送", "左端绕行",
    "继续绕行", "左手制动", "松开左端", "自由端静置", "左手撤离", "左手接近换抓点", "左手换抓",
    "准备右手释放", "微调左抓位置", "收紧左夹爪", "右手解除抓持", "左手稳住绳子", "右手撤离",
    "接近第二环", "抬高接近姿态", "绕行至第二环", "第二环前调姿", "向第二环穿入", "右手接近出口",
    "右手出口换抓", "左手松手", "左手退出第二环", "接近第三环", "向第三环穿入", "沿切向移动",
    "右夹爪转动", "左手接近转交点", "左手接取", "右手松手", "右手后撤", "右手继续后撤",
    "重新接近绳端", "再次抓取绳端", "拉过第三环出口", "左手松手", "将绳端放回桌面", "最后松手、撤离与静置")


def stage_label(stage):
    if stage.startswith("reference_"):
        try:
            return PHASE_LABELS[int(stage.split("_")[-1])]
        except (ValueError, IndexError):
            pass
    return stage


class ThreadingRecorder(PhysicalRecorder):
    def close(self, report):
        self.stack.close()
        self.metadata.update(fps=self.fps, frames=len(self.frames), cameras=list(self.writers),
            same_continuous_rollout=True, steps_between_camera_captures=0,
            full_threading_verified=bool(report.get("full_threading_verified")),
            reference_speed=report.get("reference_speed"), physical_state_replay=False)
        (self.output/"camera_rig.json").write_text(json.dumps(self.metadata, indent=2)+"\n")
        (self.output/"frames.json").write_text(json.dumps(self.frames)+"\n")
        validation = validate_recording(self.output)
        cards = "".join(f'<figure><video controls class="sync" src="{name}.mp4" poster="initial_{name}.png"></video>'
                        f'<figcaption>{name}</figcaption></figure>' for name in self.writers)
        status = "完整穿环执行通过" if report.get("full_threading_verified") else "物理试跑；尚未通过完整穿环验收"
        phases = [(i, frame) for i, frame in enumerate(self.frames)
                  if i == 0 or frame["stage"] != self.frames[i-1]["stage"]]
        jumps = "".join(f'<button onclick="seek({i/self.fps})">{html.escape(stage_label(frame["stage"]))} '
                        f'· {frame["physics_time_s"]:.1f}s</button>' for i, frame in phases)
        reason = html.escape(report.get("error") or "")
        (self.output/"index.html").write_text('''<!doctype html><html lang="zh-CN"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>绳穿三环 · 物理执行</title>
<style>body{font:16px/1.7 system-ui;max-width:1280px;margin:32px auto;padding:20px;background:#f3f5f7;color:#203040}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:16px}figure{margin:0}video{width:100%}button{padding:10px;margin:3px}</style>
<h1>绳穿三环 · 实际物理执行</h1><p>'''+status+f'。实际模拟 {report.get("simulated_seconds", 0):.3f} s。</p>'
            +'<p>机械臂沿公开动作参考执行位置控制；绳子由 FEM+IPC 重新模拟。双指实际接触后启用显式辅助抓持，'
             '约束跟随机械臂的实际位姿，松手后解除。各视角来自同一次连续执行。</p>'
            + f'<p>{reason}</p><p>视频核对：{"通过" if validation["passed"] else "未通过"}</p>'
            + '<p><a href="report.json">物理报告</a> · <a href="contact_trace.json">机器人与抓持状态</a> · '
              '<a href="frames.json">逐帧物理时间</a> · <a href="video_validation.json">视频核对</a></p>'
            + '<button onclick="toggle()">同步播放 / 暂停</button><nav>'+jumps+'</nav><div class="grid">'+cards+'''</div>
<script>const streams=[...document.querySelectorAll('.sync')];function toggle(){let play=streams[0].paused,t=streams[0].currentTime;
streams.forEach(v=>{v.currentTime=t;play?v.play():v.pause()})}function seek(t){streams.forEach(v=>{v.pause();v.currentTime=t})}
streams[0].addEventListener('seeked',()=>streams.slice(1).forEach(v=>{if(Math.abs(v.currentTime-streams[0].currentTime)>.1)v.currentTime=streams[0].currentTime}));</script></html>''')
