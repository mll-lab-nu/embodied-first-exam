"""Reproducible ring-size controls; passing a control does not qualify a puzzle.

Run with .venv-gs121/bin/python -m topogym.tasks.horseshoe_ring.experiments.
These deliberately simple motions measure the oversized-ring failure mode.
An unsuccessful prescribed motion is never interpreted as global insolvability.
"""
from __future__ import annotations

import argparse
from html import escape
import json
from pathlib import Path

from scipy.spatial.transform import Rotation

from .geometry import load_template
from .solvability import WitnessModel, certify_path, write_artifacts

OFFICIAL_VIDEO = "https://www.youtube.com/watch?v=LAE1w1VNIZg"


def tutorial_section(output):
    certificate = Path(output)/"tutorial_solvable_v3/certificate.json"
    if not certificate.is_file():
        return ""
    report = json.loads(certificate.read_text())
    if not report["passed"]:
        return ""
    return ('<section id="tutorial-v3"><h2>五刚体教程原型：完整几何取环已验证</h2>'
        '<p>2 只马蹄、2 只中间链环、1 只目标环。场景环内径 118.4 mm，马蹄外宽约 132 mm；'
        '需要翻转、折合和调整，初态直线拉出路径失败。</p>'
        f'<p>完整路径的连续间隙下界 {report["minimum_clearance_lower_bound_m"]*1000:.4f} mm，'
        f'终态包围盒分离 {report["goal"]["separation_m"]*1000:.2f} mm。'
        '这些名义尺寸不是商品实测 CAD。ALOHA 演示为运动学预演，尚未验证力驱动抓取。</p>'
        '<p><a href="../../environment_bootstrap/horseshoe_ring/aloha_full/index.html"><strong>打开 ALOHA 全过程与四路相机</strong></a> · '
        '<a href="tutorial_solvable_v3/certificate.json">完整几何证书</a> · '
        '<a href="tutorial_solvable_v3/body_poses.json">全部路径数据</a></p>'
        + ('<p><a href="trace_scene_variants_v1/index.html">新 IK 轨迹与反推可解场景</a></p>'
           if (Path(output)/"trace_scene_variants_v1/index.html").is_file() else '') + '</section>')


def straight_path(tilt_deg=55.):
    q = Rotation.from_euler("y", 90.-tilt_deg, degrees=True).as_quat().tolist()
    return [[0., 0., 0., 0., 0., 0., 0., 1.], [0., 0., 0., 0., *q], [.0, .34, .0, .0, *q]]


def run_sweep(output, radii=(29., 31., 33., 34., 35., 36.), scale=2.):
    output = Path(output)
    rows = []
    for radius in radii:
        template = load_template()
        template["target_ring"]["centerline_radius"] = radius
        model = WitnessModel(template, scale=scale)
        path = straight_path(template["target_ring"]["initial_tilt_deg"])
        result = certify_path(model, path)
        folder = f"straight_r{radius:g}"
        write_artifacts(output/folder, model, path, result)
        rows.append(dict(radius_template_mm=radius,
            ring_inner_diameter_scene_mm=2*scale*(radius-template["target_ring"]["wire_radius"]),
            ring_wire_diameter_scene_mm=2*scale*template["target_ring"]["wire_radius"],
            passed=result["passed"], folder=folder,
            interpretation="oversized_ring_control; does not require puzzle manipulation" if result["passed"]
                else "this prescribed route failed; global solvability unknown",
            first_failure=result["failures"][:1]))
        print(f"R={radius:g} mm: straight extraction {result['passed']}", flush=True)
    summary = dict(scope="ring-size controls, not a complete search over puzzle motions", scale=scale,
        official_source=dict(title="Puzzle and Perplex - Horseshoes Solution", author="Professor Puzzle Ltd",
            url=OFFICIAL_VIDEO, observed_sequence="turn and bring horseshoes together; move ring over the approaching curved ends; remove ring",
            dimension_source=False, exact_product_match_confirmed=False),
        results=rows, photo_prototype_extraction_verified=False, robot_execution_verified=False,
        dynamic_execution_verified=False,
        geometry_guarantee="Positive numerical separation bounds for each interval of the declared path and conservative collision covers only.")
    (output/"result.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False)+"\n")
    table = "\n".join(f'<tr><td>{r["radius_template_mm"]:g}</td><td>{r["ring_inner_diameter_scene_mm"]:.1f}</td>'
        f'<td>{"通过：大环直接滑出" if r["passed"] else "此直线路径失败；整体可解性未知"}</td>'
        f'<td><a href="{r["folder"]}/certificate.json">检查详情</a> · '
        f'<a href="{r["folder"]}/witness_path.json">路径</a></td></tr>' for r in rows)
    partial = ""
    certificate = output/"fold_candidate_r29/certificate.json"
    if certificate.exists():
        c = json.loads(certificate.read_text())
        partial = ('<section><h2>原尺寸折叠候选</h2><p>只尝试两轴收拢和圆环随动，没有完成厂家视频中的取环动作。'
            f'连续无碰撞：{escape(str(c["continuous_collision_free"]))}；完整取出：{escape(str(c["passed"]))}。'
            '终态圆环仍与装配包围盒重叠，不能作为有解证明。</p>'
            '<p><a href="fold_candidate_r29/certificate.json">候选路径复核</a> · '
            '<a href="fold_candidate_r29/witness_path.json">候选关键帧</a></p></section>')
    page = f'''<!doctype html><html lang="zh-CN"><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Horseshoe Ring 可解性对照</title>
<style>body{{max-width:1080px;margin:32px auto;padding:0 24px;font:17px/1.7 system-ui;background:#f4f5f7;color:#24313c}}
section{{background:white;padding:24px;margin:22px 0;border:1px solid #dde2e8;border-radius:12px}}
table{{border-collapse:collapse;width:100%}}td,th{{text-align:left;padding:12px;border-bottom:1px solid #ddd}}
a{{color:#14699a}}video{{width:100%}}</style>
<h1>Horseshoe Ring：哪些尺寸已经有证据？</h1>
<p><a href="../../environment_bootstrap/horseshoe_ring/lab_initial/index.html">打开共用实验室初始场景</a> ·
<a href="../../environment_bootstrap/horseshoe_ring/oversized_control/index.html">大环取出对照演示</a></p>
{tutorial_section(output)}
<section><h2>早期九刚体照片原型对照</h2><p>该旧原型尚未通过完整取环验证。已验证能直接滑出的大环只用作正对照，不能据此验收真实谜题。</p>
<p>厂家 <a href="{OFFICIAL_VIDEO}">Professor Puzzle 官方解法视频</a> 展示先转动并收拢马蹄、将环移过靠拢的弯曲端，再取下。
本原型的尺寸和每条链三个链节仍为设计假设；视频没有提供可直接复制的尺寸保证。</p></section>
<section><h2>仅改变圆环半径的对照</h2><p>统一放大 {scale:g} 倍；下表内径为场景实际毫米。
马蹄最大外宽约 {model.assembly.bodies[0].visual.extents[1]*1000:.2f} mm，环线径 {rows[0]['ring_wire_diameter_scene_mm']:.1f} mm。
动作是将圆环转至与长轴垂直，然后沿长轴滑出；两只马蹄和六个链节保持原位。</p>
<table><tr><th>模板中心线半径 / mm</th><th>场景环内径 / mm</th><th>结果</th><th>证据</th></tr>{table}</table>
<p>失败只排除此处指定的动作，没有穷尽所有动作，不能判定无解。</p></section>{partial}
<section><h2>检查范围</h2><p>使用实际 URDF 碰撞几何的保守外包络，逐段以表面运动上界扣除端点间隙；
接受的整段必须保持至少 0.2 mm 的正间隙。起点必须与模板一致，终点圆环必须完全移到装配包围盒之外。
这是数值几何路径的验证；尚未验证摩擦、重力下的执行、抓取或机器人可达性。正对照视频按这些位姿回放。</p>
<p><a href="result.json">汇总 JSON</a></p></section></html>'''
    (output/"index.html").write_text(page)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("runs/environment-solvability/horseshoe_ring"))
    args = parser.parse_args()
    run_sweep(args.output)


if __name__ == "__main__":
    main()
