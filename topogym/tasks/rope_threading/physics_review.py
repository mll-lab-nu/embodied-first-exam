"""Build a review page from completed or explicitly incomplete physics evidence."""
import argparse
import html
import json
from pathlib import Path

import numpy as np

from .qualification import summarize, paired_material_samples


def build(folder):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    folder = Path(folder).resolve()
    qualification = summarize(folder)
    (folder/"qualification.json").write_text(json.dumps(qualification, indent=2)+"\n")
    rows, curves = [], []
    for root in sorted(folder.iterdir()):
        if not root.is_dir() or not (root/"validation_spec.json").exists():
            continue
        report = json.loads((root/"report.json").read_text()) if (root/"report.json").exists() else {}
        trace = root/("trace.json" if (root/"trace.json").exists() else "partial_trace.json")
        status = "通过" if report.get("passed") else "未通过" if report else "未完成"
        error = report.get("error") or ", ".join(k for k, v in report.get("checks", {}).items() if not v)
        if "OutOfMemoryError" in (error or ""):
            status = "运行中断"
            error = "CUDA 显存不足；已保存中断前原生状态，完整错误见报告"
        elif report.get("failure_category") == "runtime_initialization":
            status = "初始化失败"
        action = ", ".join(k for k, v in report.get("actuation", {}).get("checks", {}).items() if not v)
        link = f'{root.name}/report.json' if report else f'{root.name}/process.log'
        rows.append(f'<tr><td><a href="{link}">{html.escape(root.name)}</a></td><td>{status}</td>'
            f'<td>{report.get("simulated_seconds", 0):.3f}</td><td>{html.escape(error or "")}'
            f'{html.escape("; "+action if action else "")}</td></tr>')
        if trace.exists():
            samples = json.loads(trace.read_text())
            if samples:
                curves.append((root.name, samples))
    if curves:
        fig, axes = plt.subplots(2, 2, figsize=(12, 7), constrained_layout=True)
        fields = [("rms_speed_m_s", "RMS speed (mm/s)", 1000),
                  ("max_total_length_relative_change", "Total length change (%)", 100),
                  ("max_local_axial_strain", "Maximum local axial strain (%)", 100),
                  ("min_J", "Minimum volume ratio J", 1)]
        for axis, (field, label, scale) in zip(axes.flat, fields):
            for name, samples in curves:
                axis.plot([s["time_s"] for s in samples], [s[field]*scale for s in samples], label=name, lw=1.4)
            axis.set(xlabel="Physical time (s)", ylabel=label)
            axis.grid(alpha=.2)
        axes[0, 0].set_yscale("symlog", linthresh=.1)
        axes[0, 0].legend(fontsize=8)
        fig.savefig(folder/"physics_metrics.png", dpi=160)
        plt.close(fig)
    ring_root = folder/qualification["case_directories"]["ring_contact"]
    trajectory_path = ring_root/("trajectory.npz" if (ring_root/"trajectory.npz").exists() else "partial_trajectory.npz")
    if trajectory_path.exists():
        from omegaconf import OmegaConf
        from .geometry import ThreadingLayout
        cfg = OmegaConf.load(ring_root/"config.yaml")
        floor = float(cfg.env.world.table.pos[2]+cfg.env.world.table.size[2]/2)
        layout = ThreadingLayout(translation_m=(*cfg.task.origin_xy_m, floor+.0009))
        with np.load(trajectory_path) as data:
            times, centerlines = data["times"], data["centerlines"]
        fig = plt.figure(figsize=(12, 7), constrained_layout=True)
        requested = [0., 3., 7., 11., 12.7, float(times[-1])]
        for j, target in enumerate(requested):
            axis = fig.add_subplot(2, 3, j+1, projection="3d")
            i = int(np.argmin(abs(times-target)))
            line = centerlines[i]
            axis.plot(*line.T, color="#eb812d", lw=2.5)
            for ring in layout.rings():
                theta = np.linspace(0, 2*np.pi, 129)
                points = (np.asarray(ring["center_m"])+ring["radius_m"]*(
                    np.cos(theta)[:, None]*ring["basis_u"]+np.sin(theta)[:, None]*ring["basis_v"]))
                axis.plot(*points.T, color=ring["rgba"][:3], lw=2)
            axis.set(xlim=(-.7, .3), ylim=(-.2, .45), zlim=(floor-.01, floor+.43),
                title=f"Native centerline: {times[i]:.2f} s", xlabel="X (m)", ylabel="Y (m)")
            axis.set_box_aspect((1., .65, .44))
            axis.view_init(elev=27, azim=-57)
        fig.savefig(folder/"ring_contact_states.png", dpi=160)
        plt.close(fig)
    free_a = folder/qualification["case_directories"]["free_baseline"]/"trajectory.npz"
    free_b = folder/qualification["case_directories"]["free_halfdt"]/"trajectory.npz"
    compared = free_a.is_file() and free_b.is_file()
    if compared:
        with np.load(free_a) as data:
            ta, ca = data["times"], data["centerlines"][:, ::4]
        with np.load(free_b) as data:
            tb, cb = data["times"], data["centerlines"][:, ::4]
        times, aa, bb = paired_material_samples(free_a.parent, free_b.parent)
        distances = np.linalg.norm(aa-bb, axis=2)*1000
        rms = np.sqrt(np.mean(distances**2, axis=1))
        fig, axes = plt.subplots(2, 1, figsize=(10, 7), constrained_layout=True)
        origin = float(ca[0, :, 2].mean())
        axes[0].plot(ta, (ca[:, :, 2].mean(1)-origin)*1000, 'o-', ms=3, label="Native dt = 1.25 ms")
        axes[0].plot(tb, (cb[:, :, 2].mean(1)-origin)*1000, 'o-', ms=3, label="Native dt = 0.625 ms")
        axes[0].set(xlim=(0, .3), xlabel="Physical time (s)", ylabel="Mean centerline height change (mm)",
                    title="Initialization contact response: same scene, halved time step")
        axes[0].legend()
        axes[1].plot(times, rms, label="81 material nodes: RMS difference")
        axes[1].plot(times, distances.max(1), label="Largest material-point difference", alpha=.7)
        axes[1].axhline(2, ls="--", color="#bc4848", label="RMS gate: 2 mm")
        axes[1].axhline(5, ls=":", color="#8e4444", label="Point gate: 5 mm")
        axes[1].set(xlabel="Physical time (s)", ylabel="Position difference (mm)")
        axes[1].legend()
        for axis in axes:
            axis.grid(alpha=.2)
        fig.savefig(folder/"time_step_comparison.png", dpi=160)
        plt.close(fig)
    missing = [name for name, case in qualification["cases"].items() if not case["passed"]]
    status = "局部物理资格检查通过；完整执行另见录像报告" if qualification["passed"] else "物理验收尚未通过，不能开始正式完整 demo"
    body = '''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>绳穿三环 · 物理验收</title><style>body{font:16px/1.7 system-ui;max-width:1200px;margin:30px auto;padding:24px;background:#f4f6f8;color:#203040}
table{border-collapse:collapse;width:100%;background:white}th,td{border:1px solid #d4dde3;padding:10px;text-align:left}img{width:100%}a{color:#1265a0}</style>
<h1>绳穿三环 · 物理验收</h1>'''
    body += '<p><strong>'+status+'</strong></p><p>尚未通过的必需项目：'+html.escape(", ".join(missing) or "无")+'</p>'
    for name, comparison in qualification["comparisons"].items():
        if comparison.get("numerical_difference_within_limits") is False:
            body += ('<p><strong>已发现数值超差：</strong>'+html.escape(name)
                +f' 在 {comparison["maximum_rms_time_s"]:.3f} s 的逐帧 RMS 差异为 '
                +f'{comparison["maximum_frame_rms_m"]*1000:.3f} mm（门槛 2 mm），'
                +f'最大单点差异 {comparison["maximum_point_distance_m"]*1000:.3f} mm（门槛 5 mm）。')
            if not comparison["both_runs_completed_and_passed"]:
                body += (f'对照使用已保存的共同前 {comparison["sampled_seconds"]:.2f} s；'
                         '至少一组运行未完成或未通过，不能据此宣称完整对照通过。已保存前缀的超差足以拒绝当前资格。</p>')
            else:
                body += '</p>'
    body += '''<p>静置、环接触、步长减半、网格细化和机器人抓取分别保留证据。
每个原生 IPC 子步核对表面连续碰撞、四面体体积、绳长、局部应变和桌面穿透。
静置末两秒要求漂移 &lt; 2 mm，最大速度 &lt; 5 mm/s、RMS 速度 &lt; 1 mm/s。
加载绳长变化 &lt; 5%，局部轴向应变 &lt; 20%；数值比较要求逐帧 RMS &lt; 2 mm、任一点 &lt; 5 mm。</p>
<p>已修复初态底座法兰与绳端穿插：恢复参考机器人/桌面相对高度，增加 20.9 mm 实体垫座。
原 10 mm/s 摩擦速度正则化在五秒静置中产生 2.567 mm 尾窗漂移；改用已校验的 1 mm/s 参数后
静置尾窗漂移为 0.416 mm。此处的通过仅限数值测试，不等于真实绳材或硬件实验验证。</p>
<table><thead><tr><th>测试证据</th><th>状态</th><th>实际模拟秒数</th><th>失败 / 未完成原因</th></tr></thead><tbody>'''
    body += ''.join(rows)+'</tbody></table>'
    body += '<h2>数值对照</h2><table><tr><th>对照</th><th>状态</th><th>逐帧最大 RMS</th><th>任一点最大差异</th></tr>'
    for name, comparison in qualification["comparisons"].items():
        computed = "comparison_samples" in comparison
        status = "通过" if comparison["passed"] else "未通过" if computed else "等待完整测试"
        if computed and not comparison.get("both_runs_completed_and_passed", False):
            status = "已观测前缀超差" if not comparison["numerical_difference_within_limits"] else "前缀在限值内；未完成"
        rms = f'{comparison["maximum_frame_rms_m"]*1000:.3f} mm' if computed else "—"
        maximum = f'{comparison["maximum_point_distance_m"]*1000:.3f} mm' if computed else "—"
        body += f'<tr><td>{html.escape(name)}</td><td>{status}</td><td>{rms}</td><td>{maximum}</td></tr>'
    body += '</table>'
    if compared:
        body += '<h2>时间步对照的起始接触响应</h2><p>相同场景、相同物理参数，仅减半子步。上图放大初始 0.3 s；下图按相同物理时间比较 81 个材料节点。</p><img src="time_step_comparison.png" alt="两种时间步的竖直弹起与绳形误差">'
    if curves:
        body += '<h2>原生物理状态曲线</h2><img src="physics_metrics.png" alt="物理时间对应的速度、绳长、局部应变和体积比曲线">'
    if trajectory_path.exists():
        body += '<h2>加载测试的实际绳中心线</h2><p>从本次原生 FEM 状态读取；下图不是原视频绳轨迹的回放。</p><img src="ring_contact_states.png" alt="抬升、穿环、滑动和释放的实际绳中心线">'
    body += '''<p><a href="qualification.json">资格检查及证据哈希</a> ·
<a href="../reference_motion_v1/reference_summary.json">公开参考动作的 51 个阶段</a> ·
<a href="../physics_v4/free_baseline/report.json">修正摩擦前的失败静置报告</a></p>
<p>公开参考仅提供控制目标。绳体不得按原轨迹回写；接触后辅助抓持、释放和失败均须如实记录。
初态相机环绕、局部加载试验和参考轨迹自身都不算完整机器人 demo。</p></html>'''
    (folder/"index.html").write_text(body)
    return qualification


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folder", type=Path)
    args = parser.parse_args()
    result = build(args.folder)
    print(json.dumps(dict(passed=result["passed"], page=str(args.folder/"index.html"))))


if __name__ == "__main__":
    main()
