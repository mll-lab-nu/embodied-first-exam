"""Build a local review page from the recorded sensors and measured timeline."""

import argparse
import html
import json
from pathlib import Path


def write_review(output, names):
    output = Path(output)
    report = json.loads((output / "report.json").read_text())
    frames = json.loads((output / "frames.json").read_text())
    starts = {}
    for frame in frames:
        starts.setdefault(frame["phase"], frame["time_s"])
    events = [
        ("pickup_lift", "抓起钥匙"),
        ("enter_second_layer", "首次进入第二层"),
        ("coupled_prepare_1", "联合旋转，为第一次换孔准备"),
        ("retreat_1_to_first", "第一次回退至第一层"),
        ("reset_first_rotor_1", "仅转第一片"),
        ("change_entry_slot_1", "换入第一片的 −30° 孔"),
        ("coupled_prepare_2", "联合旋转，为第二次换孔准备"),
        ("retreat_2_to_first", "第二次回退至第一层"),
        ("reset_first_rotor_2", "再次仅转第一片"),
        ("change_entry_slot_2", "换入第一片的 0° 孔"),
        ("enter_third_layer", "进入第三层"),
        ("insert_fixed_goal", "插入固定目标板"),
        ("release", "松手与退出"),
    ]
    # Frame 0 is the first sampled state, not time_s=0.
    origin = frames[0]["time_s"] if frames else 0.0
    buttons = []
    for phase, label in events:
        if phase in starts:
            when = max(0.0, starts[phase] - origin)
            buttons.append(
                f'<button data-time="{when:.2f}">{when:.1f}s · {label}</button>'
            )
    labels = {
        "agentview": "主外部视角 · agentview",
        "front_oblique": "第二外部视角 · front_oblique",
        "wrist": "腕部视角 · wrist",
    }
    cards = []
    for name in names:
        safe = html.escape(name, quote=True)
        cards.append(
            f'<article><h2>{labels.get(name, safe)}</h2>'
            f'<video controls preload="metadata" poster="initial_{safe}.png" '
            f'src="{safe}.mp4"></video><a href="{safe}.mp4">单独打开 MP4</a></article>'
        )
    proof = report["retreat_certificate"]
    outcome = "物理执行通过" if report["success"] else "物理执行未通过"
    page = '''<!doctype html>
<html lang="zh-CN"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Staged Lock · 两次必要回退</title>
<style>
body{margin:24px auto;padding:0 20px;max-width:1440px;background:#14212b;color:#edf3f7;font:16px/1.6 system-ui}
h1{font-size:28px}h2{font-size:19px}a{color:#97d7fa}video{width:100%;background:#111}
.grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:20px}
article{padding:16px;background:#21323e;border-radius:12px}
button,select{padding:8px 12px;margin:4px;border:1px solid #607782;border-radius:7px;background:#263f4e;color:#fff;cursor:pointer}
.controls{position:sticky;top:0;background:#14212bf5;padding:8px 0;z-index:1}
table{border-collapse:collapse}td,th{border:1px solid #607782;padding:7px 16px;text-align:left}
.note{max-width:1000px;color:#c4d5df}@media(max-width:800px){.grid{grid-template-columns:1fr}}
</style>
<h1>三片锁片：两次必要回退与换孔</h1>
<p>Genesis 接触物理 + Nyx 渲染；Franka + Robotiq 2F-85。三路是同一次执行的独立相机视频，画面内没有状态示意图。</p>
'''
    page += (
        f'<p><strong>{outcome}</strong> · 实测回退 {report["observed_retreat_count"]} 次'
        f' · {report["seconds"]:.1f} 秒 · 模型内最少 '
        f'{proof["minimum_required_decoupling_retreats"]} 次</p>'
    )
    page += '''<table><tr><th>部件</th><th>转角范围</th><th>盘内锁孔中心角</th></tr>
<tr><td>D1 / 入口锁片</td><td>−15° ～ +15°</td><td>−60°、−30°、0°</td></tr>
<tr><td>D2 / 蓝色</td><td>−10° ～ +75°</td><td>−60°</td></tr>
<tr><td>D3 / 棕色</td><td>360° 连续转动</td><td>0°</td></tr></table>
<p class="note">前两片的固定外环各有一个带端点的弧槽；第三片使用完整环槽。
两次回退均从第二层退回第一层，重新排列孔位后再前进。
最少次数与唯一最短换孔顺序的结论限定于同轴、准静态、钥匙侧壁驱动锁片的模型；任意偏轴楔入、冲击或直接拨盘的全局最优性尚未证明。
oracle 使用模拟器状态反馈，不代表视觉 policy 已能解题。</p>
<p><a href="report.json">物理执行报告</a> · <a href="retreat_certificate.json">回退次数证书</a> ·
<a href="camera_rig.json">相机标定</a> · <a href="frames.json">逐帧状态</a> ·
<a href="../two_retreats_stop_qualification/report.json">关闭软件限位的实体槽端测试</a></p>
<div class="controls"><button id="play">三路一起播放</button><button id="pause">全部暂停</button>
<label>速度 <select id="speed"><option value="0.5">0.5×</option><option value="1" selected>1×</option><option value="2">2×</option></select></label></div>
<details open><summary>跳转到关键动作（三路同时定位并暂停）</summary>
'''
    page += "".join(buttons) + '</details><div class="grid">' + "".join(cards) + "</div>"
    page += '''<script>
const videos=[...document.querySelectorAll('video')];
document.querySelector('#play').onclick=()=>{const t=videos[0].currentTime;videos.forEach(v=>{v.currentTime=t;v.play().catch(()=>{});});};
document.querySelector('#pause').onclick=()=>videos.forEach(v=>v.pause());
document.querySelector('#speed').onchange=e=>videos.forEach(v=>v.playbackRate=Number(e.target.value));
document.querySelectorAll('[data-time]').forEach(b=>b.onclick=()=>videos.forEach(v=>{v.pause();v.currentTime=Number(b.dataset.time);}));
</script></html>'''
    (output / "index.html").write_text(page, encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    report = json.loads((args.output / "report.json").read_text())
    write_review(args.output, report["recorded_cameras"])
