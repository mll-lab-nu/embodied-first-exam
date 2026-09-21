"""Build a Markdown review from completed or explicitly incomplete physics evidence."""
import argparse
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
        progress = json.loads((root/"progress.json").read_text()) if (root/"progress.json").exists() else {}
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
        reason = ((error or "")+("; "+action if action else "")).replace("|", "/").replace("\n", " ")
        rows.append(f'| [{root.name}]({link}) | {status} | '
                    f'{report.get("simulated_seconds", progress.get("time_s", 0)):.3f} | {reason} |')
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
        actuation = json.loads((ring_root/"validation_spec.json").read_text()).get("actuation") or {}
        requested = [0., 3., 7., 11., float(actuation.get("release_s", 12.))+.7, float(times[-1])]
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
            ca = data["centerlines"]
            ta, ca = data["times"], ca[:, np.rint(np.linspace(0, ca.shape[1]-1, 81)).astype(int)]
        with np.load(free_b) as data:
            cb = data["centerlines"]
            tb, cb = data["times"], cb[:, np.rint(np.linspace(0, cb.shape[1]-1, 81)).astype(int)]
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
    lines = ["# 绳穿三环 · 物理验收", "", status, "",
        "尚未通过的必需项目："+(", ".join(missing) or "无"), "",
        "每个原生 IPC 子步核对表面连续碰撞、四面体体积、绳长、局部应变和桌面穿透。"
        "静置末两秒要求漂移 < 2 mm、最大速度 < 5 mm/s、RMS 速度 < 1 mm/s。"
        "加载绳长变化 < 5%、局部轴向应变 < 20%；数值比较逐帧 RMS < 2 mm、任一点 < 5 mm。", "",
        "| 测试证据 | 状态 | 实际模拟秒数 | 失败 / 未完成原因 |",
        "|---|---|---:|---|", *rows, "",
        "| 数值对照 | 状态 | 逐帧最大 RMS | 任一点最大差异 | 共同区间 |",
        "|---|---|---:|---:|---:|"]
    for name, comparison in qualification["comparisons"].items():
        computed = "comparison_samples" in comparison
        status = "通过" if comparison["passed"] else "未通过" if computed else "等待完整测试"
        if computed and not comparison.get("both_runs_completed_and_passed", False):
            status = "已观测前缀超差" if not comparison["numerical_difference_within_limits"] else "前缀在限值内；未完成"
        rms = f'{comparison["maximum_frame_rms_m"]*1000:.3f} mm' if computed else "—"
        maximum = f'{comparison["maximum_point_distance_m"]*1000:.3f} mm' if computed else "—"
        duration = f'{comparison["sampled_seconds"]:g} s' if computed else "—"
        lines += [f'| {name} | {status} | {rms} | {maximum} | {duration} |']
    lines += [""]
    for name, comparison in qualification["comparisons"].items():
        if max(comparison.get('unpaired_tail_seconds', [0.])) > 1e-8:
            lines += [f"{name} 仅对照共同前 {comparison['sampled_seconds']:g} s；分别观察至 "
                + " / ".join(f"{t:g} s" for t in comparison['trajectory_end_times_s'])
                + "。额外静置尾段只检验该次稳定性，未计为配对数值对照。", ""]
    for filename, label in (("time_step_comparison.png", "时间步对照"),
                            ("physics_metrics.png", "原生物理状态曲线"),
                            ("ring_contact_states.png", "实际绳中心线")):
        if (folder/filename).is_file():
            lines += [f"![{label}]({filename})", ""]
    lines += ["[资格检查及证据哈希](qualification.json)。每次运行的参数、限制和完整失败记录保存在各自目录。", "",
        "公开参考仅提供控制目标，绳体未按原轨迹回写；双指接触后采用辅助抓持。"
        "材料和耗散参数未经实物标定。局部加载与前段动作通过不等于完整机器人执行通过。", ""]
    (folder/"README.md").write_text("\n".join(lines))
    return qualification


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folder", type=Path)
    args = parser.parse_args()
    result = build(args.folder)
    print(json.dumps(dict(passed=result["passed"], review=str(args.folder/"README.md"))))


if __name__ == "__main__":
    main()
