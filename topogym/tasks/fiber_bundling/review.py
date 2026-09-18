"""Render measured load/release states from the passive wire diagnostic."""
import argparse
import json
from pathlib import Path

import numpy as np

from .geometry import COLORS, shape_in_root_frame


def write_review(output):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    output = Path(output)
    report = json.loads((output/"report.json").read_text())
    with np.load(output/"states.npz") as data:
        shapes = [shape_in_root_frame(data[key][0])*1000
                  for key in ("initial", "final", "released")]
    bounds = np.concatenate(shapes).reshape(-1, 3)
    lo, hi = bounds.min(axis=0)-5, bounds.max(axis=0)+5
    fig = plt.figure(figsize=(14, 5), layout="constrained")
    titles = ["Initial: axial exit, outward bend", "After ring contact",
              f"After {report['release_seconds']:g} s without ring contact"]
    for i, (shape, title) in enumerate(zip(shapes, titles)):
        ax = fig.add_subplot(1, 3, i+1, projection="3d")
        for j, strand in enumerate(shape):
            ax.plot(*strand.T, color=COLORS[j % len(COLORS)][:3], linewidth=3)
        roots = np.concatenate((shape[:, 0], shape[:1, 0]))
        ax.plot(*roots.T, color="#66717e", linewidth=1)
        ax.set(xlim=(lo[0], hi[0]), ylim=(lo[1], hi[1]), zlim=(lo[2], hi[2]),
               xlabel="Axial (mm)", ylabel="Lateral (mm)", zlabel="Lateral (mm)", title=title)
        ax.set_box_aspect(hi-lo)
        ax.view_init(elev=22, azim=-65)
        ax.tick_params(labelsize=8)
    fig.suptitle("Measured wire centerlines in cable-end frame | identical scale in all panels", fontsize=13)
    fig.savefig(output/"shape_retention.png", dpi=160)
    plt.close(fig)

    release = report["release_trace"]
    fig, ax = plt.subplots(figsize=(9, 3.3), layout="constrained")
    ax.plot([0]+[row["step"]*report["dt"] for row in release],
            [report["ring_vs_control_fiber_bending_in_root_frame_m"]*1000]+
            [row["retained_bending_m"]*1000 for row in release], marker="o", color="#217888")
    ax.set(xlabel="Time after ring removal (s)", ylabel="Maximum bending difference (mm)",
           title="Residual deformation relative to the identical no-ring control", ylim=(0, None))
    ax.grid(alpha=.2)
    fig.savefig(output/"release_trace.png", dpi=160)
    plt.close(fig)

    status = "通过" if report["passed"] else "未通过"
    rows = "".join(f"<tr><td>{key}</td><td>{'通过' if value else '未通过'}</td></tr>"
                   for key, value in report["checks"].items())
    (output/"index.html").write_text(f'''<!doctype html><html lang="zh-CN"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>电线碰撞与卸载验证</title>
<style>body{{max-width:1200px;margin:36px auto;padding:0 24px;background:#f4f6f8;color:#203143;font:17px/1.7 system-ui}}
img{{width:100%;background:white;border-radius:12px}}td{{padding:4px 20px 4px 0}}a{{color:#126995}}</style>
<h1>碰撞变形能否保留：{status}</h1>
<p>两套相同电缆接受相同的粗绳根部运动，一套接触环口、一套无环。
加载结束后，仅把环平移至空处，再被动模拟 {report['release_seconds']:g} 秒；不写入电线位置，不清零速度。
下图使用电缆端面坐标系，排除粗绳整体平移和转动。</p>
<img src="shape_retention.png" alt="实际模拟中的初态、受环口碰撞后的形态、撤去环口后的形态">
<p>卸载后最大残余弯曲差 {report['residual_bending_after_release_m']*1000:.2f} mm，
为加载结束时的 {report['retained_bending_ratio']*100:.1f}%；
最后 {report['late_release_window_seconds']:g} 秒形状漂移不超过 {report['max_shape_drift_late_release_m']*1000:.3f} mm。
卸载阶段与环接触步数为 {report['release_ring_contact_steps']}。</p>
<img src="release_trace.png" alt="卸载后残余形变随时间变化">
<p>当前是零刚度、带阻尼关节产生的塑性形状保持近似；没有初态回弹目标，
也没有铜材的屈服、弹性恢复或硬化本构。局部夹具试验不代表机器人完整穿环成功。</p>
<table>{rows}</table>
<p><a href="report.json">实际数值报告</a> · <a href="states.npz">原始状态</a> ·
<a href="../branched_initial/index.html">电缆场景预览</a></p></html>''')


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    write_review(parser.parse_args().output)
