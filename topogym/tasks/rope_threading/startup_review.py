"""CPU report for controlled startup/elasticity experiments."""
import argparse
import csv
import html
import json
from pathlib import Path

import numpy as np
from omegaconf import OmegaConf

from .startup_study import summarize


LABELS = {"baseline":"原参数：100 kPa / 间距 0.3 mm", "soft50":"50 kPa / 间距 0.3 mm",
          "soft20":"20 kPa / 间距 0.3 mm", "gap12":"100 kPa / 间距 1.2 mm",
          "contact02":"100 kPa / 接触距离 0.2 mm", "gap12_soft50":"50 kPa / 间距 1.2 mm"}


def build(root):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib import font_manager
    result = summarize(root)
    variants = json.loads((root/"plan.json").read_text())["variants"]
    single_variant = len(variants) == 1
    font=Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc")
    font_manager.fontManager.addfont(str(font))
    plt.rcParams.update({"font.family":font_manager.FontProperties(fname=font).get_name(),
                        "axes.unicode_minus":False,"font.size":11})
    fig, axes = plt.subplots(2, 2, figsize=(15,9), constrained_layout=True)
    colors = dict(zip(LABELS, ("#b44f40", "#ee9633", "#9d58a8", "#258968", "#267ac0", "#756c43")))
    rows=[]
    for variant in variants:
        for suffix,style in (("_dt","-"),("_halfdt","--")):
            name=variant+suffix
            p=root/name
            if not (p/"startup_trace.json").exists():
                continue
            native=json.loads((p/"startup_trace.json").read_text())
            case=result["cases"][name]
            cfg=OmegaConf.load(p/"config.yaml")
            dt=float(cfg.env.sim.dt)/int(cfg.env.sim.substeps)
            group=0 if variant in ("baseline","soft50","soft20") else 1
            groups=(0,1) if variant=="baseline" or single_variant else (group,)
            t=np.r_[0.,[s["time_s"] for s in native]]*1000
            lift=np.r_[0.,[s["mean_centerline_lift_m"] for s in native]]*1000
            vz=np.r_[0.,[s["center_of_mass_vz_m_s"] for s in native]]
            for col in groups:
                label=f"{LABELS[variant]} · {dt*1000:g} ms"
                axes[0,col].plot(t,lift,style,color=colors[variant],label=label,lw=1.8)
                axes[1,col].plot(t,vz,style,color=colors[variant],lw=1.4)
            mesh=result["controlled_mesh_checks"].get(name,{})
            rows.append(dict(case=name,E_kPa=float(cfg.task.rope.fem.E)/1000,
                gap_mm=case["startup"]["initial_table_gap_m"]*1000,
                contact_distance_mm=float(cfg.task.rope.fem.contact_d_hat)*1000,
                native_step_ms=dt*1000,peak_mean_lift_mm=float(lift.max()),
                first_com_vz_m_s=native[0]["center_of_mass_vz_m_s"],
                maximum_length_change_pct=case["extrema"]["max_total_length_relative_change"]*100,
                maximum_local_strain_pct=case["extrema"]["max_local_axial_strain"]*100,
                min_J=case["min_J"],startup_checks_passed=case["short_checks_passed"],
                full_probe_passed=json.loads((p/"report.json").read_text()).get("passed",False),
                same_mesh=mesh.get("identical_connectivity_and_material_indices"),
                mesh_residual_m=mesh.get("maximum_vertex_residual_m")))
    titles = ("组合参数：启动前 0.2 秒", "组合参数：完整静置过程") if single_variant else (
        "只降低绳体弹性", "只改变初始间距或接触距离")
    for col,title in enumerate(titles):
        axes[0,col].set_title(title)
        axes[0,col].set_ylabel("相对各自初态的平均抬升 / mm")
        axes[1,col].set_ylabel("质心竖直速度 / m/s")
        axes[0,col].legend(fontsize=8)
        for row in range(2):
            axes[row,col].set_xlabel("实际物理时间 / ms")
            axes[row,col].grid(alpha=.2)
            axes[row,col].axhline(0,color="gray",lw=.7)
            if single_variant and col == 0:
                axes[row,col].set_xlim(0,200)
    fig.suptitle("绳子启动参数对照 · 每个原生子步的真实状态\n无机器人动作；短时诊断不等于完整物理验收",fontsize=17)
    fig.savefig(root/"comparison.png",dpi=150)
    plt.close(fig)
    if rows:
        with (root/"metrics.csv").open("w") as f:
            w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    table="".join(f'<tr><td><a href="{r["case"]}/report.json">{html.escape(r["case"])}</a></td>'
        f'<td>{r["E_kPa"]:g}</td><td>{r["gap_mm"]:.3f}</td><td>{r["native_step_ms"]:g}</td>'
        f'<td>{r["peak_mean_lift_mm"]:.3f}</td><td>{r["first_com_vz_m_s"]:.4f}</td>'
        f'<td>{r["maximum_length_change_pct"]:.3f}%</td><td>{r["maximum_local_strain_pct"]:.3f}%</td>'
        f'<td>{"通过" if r["startup_checks_passed"] else "未通过"}</td>'
        f'<td>{"通过" if r["full_probe_passed"] else "未通过"}</td></tr>' for r in rows)
    pairs="".join(f'<tr><td>{html.escape(LABELS[k])}</td><td>{v["maximum_frame_rms_m"]*1000:.3f}</td>'
        f'<td>{v["maximum_point_distance_m"]*1000:.3f}</td><td>{"范围内" if v["passed"] else "超差"}</td></tr>'
        for k,v in result["timestep_comparisons"].items())
    page=f'''<!doctype html><html lang="zh"><meta charset="utf-8"><title>绳子启动与弹性对照</title>
<style>body{{max-width:1400px;margin:32px auto;padding:0 20px;font:16px system-ui;color:#203348}}img{{width:100%}}table{{border-collapse:collapse;width:100%;font-size:14px}}td,th{{border:1px solid #d8dfe6;padding:9px;text-align:left}}th{{background:#edf3f7}}.note{{background:#fff2d8;padding:15px;line-height:1.7}}</style>
<h1>绳子启动与弹性参数对照</h1><p class="note">范围：启动后 {result["seconds"]:g} 秒，没有机器人动作。曲线来自每个原生子步；RMS 使用相同实际保存时刻的 81 个材料点，不做时间插值。
本页报告自由静置的碰撞、形变与时间步敏感性；两秒静置门槛保留不变，未满两秒的短跑在原始 report.json 中仍标记整体未通过。
单项静置检查通过也不代表穿环接触、网格细化或机器人抓取通过。这里没有完整 demo 或全套物理验收通过的结论。</p>
<img src="comparison.png" alt="启动抬升和质心速度对照"><h2>运动与形变</h2>
<table><tr><th>试验</th><th>E / kPa</th><th>初始间距 / mm</th><th>子步 / ms</th><th>最大抬升 / mm</th><th>首步向上速度 / m/s</th><th>绳长变化</th><th>最大局部应变</th><th>短时机械检查</th><th>含静置门槛</th></tr>{table}</table>
<h2>相同参数下，时间步减半的差异</h2><table><tr><th>参数</th><th>最大 RMS / mm</th><th>最大单点差 / mm</th><th>2 / 5 mm 门槛</th></tr>{pairs}</table>
<p><a href="summary.json">完整指标、网格一致性与哈希</a> · <a href="metrics.csv">CSV</a> · <a href="plan.json">试验参数</a></p></html>'''
    (root/"index.html").write_text(page)
    return rows


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folder",type=Path)
    print(json.dumps(build(parser.parse_args().folder.resolve()),indent=2))
