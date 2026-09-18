"""Build a review page from saved contact and partial-route evidence."""
from __future__ import annotations

import argparse
from html import escape
import json
from pathlib import Path

from .qualify import qualify
from .solution import source_fingerprints
from .instance_solution import require_current_instance_certificate


def build_review(root):
    root = Path(root)
    result = qualify(root/"float64_nominal/report.json",root/"float64_refined/report.json",
                     root/"contact_qualification.json")
    rows = []
    run_names = ("weak_orientation_nominal", "weak_orientation_refined", "fixed_gain_nominal",
                 "nominal", "refined", "quarter_ms", "float64_nominal", "float64_refined")
    for name in run_names:
        path = root/name/"report.json"
        if not path.exists():
            continue
        r = json.loads(path.read_text())
        cases = r["cases"]
        rows.append(f'<tr><td><a href="{name}/report.json">{name}</a></td>'
            f'<td>{r["config"].get("precision","32")} bit / {r["config"]["dt"]*1000:g} ms</td>'
            f'<td>{sum(c["passed"] for c in cases)} / {len(cases)}</td>'
            f'<td>{max(c["max_contact_penetration_m"] for c in cases)*1000:.3f} mm</td></tr>')
    comparison = "".join(f'<tr><td>{escape(c["name"])}</td>'
        f'<td>{c["translation_difference_m"]*1000:.4f} mm</td>'
        f'<td>{c["rotation_difference_rad"]:.5f} rad</td><td>{"通过" if c["passed"] else "未通过"}</td></tr>'
        for c in result["comparison"])
    route = json.loads((root/"route_probe/report.json").read_text())
    instance_section=""
    instance_path=root/"current_instance/certificate.json"
    if instance_path.exists():
        candidate=Path("assets/tasks/cast_keyhole/diagram_reference_v1/baseline_solution.json")
        verified=require_current_instance_certificate(candidate,instance_path)
        instance_section=f'''<section><h2>当前下部孔道初态：完整解已验证</h2>
<p>从实际场景 perpendicular_lower_bore_v1 起点出发，28 段连续验证全部通过，未修改板厚、槽形或碰撞体。
连续间隙至少 0.15 mm，终态分离下界 {verified['final_separation_lower_bound_m']*1000:.1f} mm。
这是当前工程初态的解，不等于商品出厂初态的官方 16 图复现。</p>
<p><a href="current_instance/certificate.json">当前实例几何证书</a> ·
<a href="current_instance/physics_dt1ms/report.json">完整路径 1 ms 力控台架</a> ·
<a href="current_instance/physics_dt05ms/report.json">完整路径 0.5 ms 力控台架</a> ·
<a href="../../../environment_bootstrap/cast_keyhole/aloha_current_instance/index.html">完整双臂 IK 预演</a></p>
<p>两个时间步的台架均无穿透；台架固定金件、有界力／力矩驱动银件。完整双臂 IK 270 帧及 971 个关节插值点通过采样检查。
机器人受力执行另行验收，不能用台架或运动学预演替代。</p></section>'''
        physical_path=root/"current_instance/robot_physics/audit.json"
        if physical_path.exists():
            physical=json.loads(physical_path.read_text())
            if physical.get("passed"):
                instance_section+='''<section><h2>当前实例双臂物理执行已通过</h2>
<p>预抓取开始，双指同刻接触后辅助抓持；连续执行 23,917 步，运行中没有写入机器人或零件位姿。
2,391 个实际状态的独立碰撞审查通过，终态分离约 55.45 mm 且稳定；末态双臂仍保持辅助抓持。</p>
<p><a href="current_instance/robot_physics/report.json">执行报告</a> ·
<a href="current_instance/robot_physics/audit.json">实际轨迹独立复核</a> ·
<a href="../../../demo_metadata/cast_keyhole/2026-09-17_current_instance_physical/index.html">四路同步物理执行视频</a></p>
<p>视频从同一次连续物理执行的实际保存状态渲染，保留原物理步号；不包含桌面拾取或解除辅助后的自由抓取验收。</p></section>'''
    full_section = ""
    full_path = root/"full_route_candidate/certificate.json"
    if full_path.exists():
        full = json.loads(full_path.read_text())
        candidate = Path("assets/tasks/cast_keyhole/diagram_reference_v1/official_milestones_candidate.json")
        current = full.get("fingerprint") == source_fingerprints(candidate)
        stage_rows = []
        for stage in full["stages"]:
            items = [s for s in full["segments"] if s["stage"] == stage]
            stage_rows.append(f'<tr><td>{escape(stage)}</td><td>{sum(s["passed"] for s in items)} / {len(items)}</td></tr>')
        full_section = f'''<section><h2>历史顶部候选路线：逐段审查（不同初态）</h2>
<p>证据与当前源码：{"一致" if current else "不一致，需重新验证"}。
共 {len(full['segments'])} 段，{sum(s['passed'] for s in full['segments'])} 段通过；
整条几何路径：{"通过" if current and full['full_geometric_path_verified'] else "未通过"}。
这是按教程关键阶段构造的工程候选，并非官方 16 幅图的精确位姿复现。</p>
<p>三维倾斜连接已通过第一槽到第二槽、倒数第二槽到最后一槽的连续检查。
第二槽到倒数第二槽的直接连接仍碰撞；两侧各自通过的片段不能跨越这个缺口拼成完整演示。
几何未改板厚或槽形，场景间隙门槛为 0.15 mm。有限搜索失败不证明模型无解。</p>
<table><tr><th>教程阶段</th><th>通过段数</th></tr>{''.join(stage_rows)}</table>
<p><a href="full_route_candidate/certificate.json">逐段证书与失败位置</a> ·
<a href="full_route_candidate/search_attempts.json">搜索记录</a></p>
<img src="full_route_candidate/witness_views.png" alt="中段连接起点、碰撞位置、终点的三正交诊断投影">
<p>该历史候选完整路径未通过，不允许执行其失败连接；当前场景初态的完整解见页面上方。
轨迹台架入口会拒绝失败、不完整或源码已变化的证书。</p></section>'''
    html = f'''<!doctype html><html lang="zh-CN"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Cast Keyhole 物理与路径检查</title>
<style>body{{max-width:1120px;margin:36px auto;padding:0 22px;background:#f4f5f7;color:#24313e;font:16px/1.7 system-ui}}
section{{background:white;padding:24px;border:1px solid #dce1e5;border-radius:12px;margin:22px 0}}
table{{width:100%;border-collapse:collapse}}th,td{{padding:9px;text-align:left;border-bottom:1px solid #dce1e5}}
img{{max-width:100%}}a{{color:#146b98}}.status{{font-size:21px;font-weight:650}}</style>
<h1>Cast Keyhole：接触稳定性与解法准备</h1>
<p class="status">接触台架：{"通过" if result["contact_bench_qualified"] else "未通过完整验收"}；当前实例解法见以下最新证据。</p>
<p><a href="../../../environment_bootstrap/cast_keyhole/precision64_scene/index.html">64 位 Nyx 基础场景复核</a></p>
{instance_section}
<section><h2>本轮检查范围</h2><p>每组包含 3 个自由重力静置、2 个允许移动、6 个受阻拉动，均运行 5 秒。
移动台架固定银件、金件重力补偿，以限幅力和力矩驱动；静置台架两件均自由。物理运行中没有写入零件位姿。
碰撞求解器每步检查，独立凸体 SAT 每 5 ms 采样。此台架不代表机器人抓持或官方路线。</p>
<table><tr><th>运行记录</th><th>精度 / 时间步</th><th>单项通过</th><th>最大接触穿透</th></tr>{''.join(rows)}</table>
<p>保留失败记录：较弱姿态控制出现偏转；直接提高固定力矩增益导致细长板振荡。
当前控制按世界坐标惯量计算角加速度对应的力矩，并施加 20 N / 3 N·m 限幅。</p></section>
<section><h2>64 位精度：1 ms 与 0.5 ms 复核</h2>
<p>门槛保持为最终相对位置差 &lt; 1 mm、姿态差 &lt; 0.02 rad。
<a href="contact_qualification.json">完整验收与源文件哈希</a></p>
<table><tr><th>场景</th><th>位置差</th><th>姿态差</th><th>结果</th></tr>{comparison}</table>
<p>{escape('; '.join(result['errors']))}</p>
<p>此前 32 位 1 / 0.5 ms 的一项最终位置差约 1.37 mm，0.5 / 0.25 ms 的一项约 1.56 mm。
这些运行虽通过单项接触测试，仍不满足时间步一致性要求。</p></section>
<section><h2>官方路线候选的几何检查</h2>
<p>顶部穿插候选初态、四分之一圈转动及到第一槽的 {len(route['segments'])} 段连续动作：
{"通过" if route['partial_approach_certified'] else "未通过"}。正间隙下界要求 0.15 mm（3 倍场景）。
第一槽到第二槽的直接插值在中途碰撞，不能由两个无碰撞端点推断路径有效。
此处保留早期起始段证据；后续完整候选的当前状态见下面逐段审查。</p>
<img src="route_probe/partial_route_views.png" alt="候选起始动作的三正交投影，非物理或机器人演示">
<p><a href="route_probe/report.json">连续间隙证据及缺失阶段</a> ·
<a href="https://www.logicagiochi.com/pub/media/wysiwyg/pdf/473743-Cast-Keyhole-Japan.pdf">Hanayama 解法图</a></p></section>
{full_section}
<section><h2>机器人与同步录制</h2><p>选用双臂 ALOHA。一臂支撑金件，另一臂操纵银件；单臂加夹具在运动学上可行，
但会增加夹具避让与换抓要求。完整 IK、采样机器人碰撞和当前实例辅助抓持物理执行已验证，具体范围见上方记录。</p>
<p>按 ALOHA 规范录制 cam_high、cam_low、cam_left_wrist、cam_right_wrist 四路同步视角，保存相同物理步号与帧时间。
物理执行录制门槛为：接触台架通过、当前实例完整连续路线通过、实际接触抓持通过、全程机器人运动无超限穿透且最终分离。
运动学预演必须明确标注 physics_steps=0。</p></section></html>'''
    (root/"index.html").write_text(html)
    print(root/"index.html")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root",type=Path,default=Path("runs/environment-solvability/cast_keyhole/diagram_reference_v1"))
    build_review(parser.parse_args().root)


if __name__ == "__main__":
    main()
