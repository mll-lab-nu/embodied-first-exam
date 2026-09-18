"""Compare independent stability runs and publish their actual acceptance gate."""
import argparse
import json
import os
from pathlib import Path

import numpy as np

from .geometry import FiberLayout, shape_in_root_frame
from .validation import LIMITS, pair_clearances


def assess(folder):
    reports = {name: json.loads((folder/name/"report.json").read_text())
               for name in ("baseline", "half_step", "free_hold")}
    arrays = {name: np.load(folder/name/"trajectory.npz") for name in ("baseline", "half_step")}
    shapes = {name: np.array([shape_in_root_frame(p) for p in data["fibers"]])
              for name, data in arrays.items()}
    errors = np.linalg.norm(shapes["baseline"][-1]-shapes["half_step"][-1], axis=-1)
    max_error, rms_error = float(errors.max()), float(np.sqrt(np.mean(errors**2)))
    matching = []
    for i, t in enumerate(arrays["baseline"]["times"]):
        j = np.argmin(np.abs(arrays["half_step"]["times"]-t))
        if abs(arrays["half_step"]["times"][j]-t) < 1e-6:
            delta = np.linalg.norm(shapes["baseline"][i]-shapes["half_step"][j], axis=-1)
            matching.append([float(t), float(delta.max()), float(np.sqrt(np.mean(delta**2)))])
    checks = {f"{name}_bounded_and_settled": r["passed"] for name, r in reports.items()}
    checks.update(same_discrete_model=all(r["layout"] == reports["baseline"]["layout"] for r in reports.values()),
                  same_backend=all(r["backend"] == reports["baseline"]["backend"] for r in reports.values()),
                  same_substeps=all(r["substeps"] == reports["baseline"]["substeps"] for r in reports.values()),
                  timestep_halved=bool(np.isclose(reports["baseline"]["dt"], 2*reports["half_step"]["dt"])),
                  free_base_control=reports["free_hold"]["free"])
    checks.update(timestep_final_max=max_error < LIMITS["timestep_max_shape_difference_m"],
                  timestep_final_rms=rms_error < LIMITS["timestep_rms_shape_difference_m"],
                  same_target_fit=reports["baseline"]["final_metrics"][0]["fits_aperture_projection"] ==
                                  reports["half_step"]["final_metrics"][0]["fits_aperture_projection"])
    layout = FiberLayout(**reports["baseline"]["layout"])
    straight = np.asarray(layout.fibers()).copy()
    straight[:, :, 0] = layout.trunk_length_m+np.linspace(0, layout.fiber_length_m, layout.fiber_segments+1)
    straight[:, :, 1:] = straight[:, :1, 1:]
    clearance = float(pair_clearances(straight, layout.fiber_radius_m).min())
    fiber_envelope = float(np.linalg.norm(straight[:, :, 1:], axis=-1).max()+layout.fiber_radius_m)
    goal = dict(straight_bundle_radius_m=fiber_envelope, trunk_radius_m=layout.trunk_radius_m,
                minimum_ring_aperture_radius_m=layout.minimum_aperture_radius,
                inter_wire_surface_clearance_m=clearance,
                collision_free_goal_configuration_exists=bool(clearance > 0 and
                    max(fiber_envelope, layout.trunk_radius_m) < layout.minimum_aperture_radius),
                reachable_by_trunk_only_contact_control_verified=False,
                description="An admissible straight goal configuration is a geometric witness, not a controlled path.")
    result = dict(scope="declared_discrete_model_numerical_stability_and_goal_geometry", checks=checks,
        stability_passed=all(checks.values()), thresholds=LIMITS,
        timestep_final_max_shape_difference_m=max_error, timestep_final_rms_shape_difference_m=rms_error,
        timestep_comparison=matching, runs={n:{k:v for k,v in r.items() if k != "final_metrics"} for n,r in reports.items()},
        goal_geometry=goal, full_bundle_solution_verified=False,
        limits="One seed and contact trajectory; finite-radius articulated rods. No copper yield model, spatial convergence, robot grasp or universal stability proof.")
    full_page = Path(__file__).resolve().parents[3]/"runs/environment_bootstrap/fiber_bundling/full_bundle_demo/index.html"
    full_link = ""
    if full_page.is_file():
        url = os.path.relpath(full_page, folder.resolve())
        result["separate_full_process_evidence"] = url
        full_link = f'<p>后续独立执行结果：<a href="{url}">逐根整理与整束穿环 demo</a>。此处的 full_bundle_solution_verified 仅描述本组稳定性试验。</p>'
    (folder/"result.json").write_text(json.dumps(result, indent=2)+"\n")
    np.savez_compressed(folder/"straight_goal_witness.npz", centerlines=straight)
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    trace = np.array(matching)
    fig, ax = plt.subplots(figsize=(10, 3.6), layout="constrained")
    ax.plot(trace[:,0], trace[:,1]*1000, label="Maximum point difference")
    ax.plot(trace[:,0], trace[:,2]*1000, label="RMS point difference")
    ax.set(xlabel="Simulation time (s)", ylabel="Shape difference in cable frame (mm)",
           title="Identical trunk commands: 2 ms vs 1 ms outer time step")
    ax.axvline(4.3, color="grey", linestyle="--", alpha=.6, label="End of motion")
    ax.legend(); ax.grid(alpha=.2)
    fig.savefig(folder/"timestep_comparison.png", dpi=160)
    plt.close(fig)
    status = "通过当前测试范围的稳定性检查" if result["stability_passed"] else "尚未通过稳定性验收"
    rows = "".join(f"<tr><td>{key}</td><td>{'通过' if value else '未通过'}</td></tr>" for key,value in checks.items())
    (folder/"index.html").write_text(f'''<!doctype html><html lang="zh-CN"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>光纤收束物理稳定性</title>
<style>body{{max-width:1080px;margin:36px auto;padding:0 24px;font:17px/1.7 system-ui;background:#f4f6f8;color:#203143}}
img{{width:100%}}table{{border-collapse:collapse}}td{{padding:8px 20px;border-bottom:1px solid #ccd}}a{{color:#126995}}</style>
<h1>{status}</h1><p>自由电缆静置 10 秒；相同粗绳整理动作分别以 2 ms 和 1 ms 时间步运行，
动作后继续静置 5 秒。检查真实根部误差、节长误差、求解器穿透、独立线段间距、每步位移、末期速度和漂移。
阈值在运行前写入各目录的 validation_spec.json。</p><table>{rows}</table>
<p>两种时间步的末态差异：最大 {max_error*1000:.3f} mm，RMS {rms_error*1000:.3f} mm。
验收阈值分别为 {LIMITS['timestep_max_shape_difference_m']*1000:g} mm 和 {LIMITS['timestep_rms_shape_difference_m']*1000:g} mm。</p>
<img src="timestep_comparison.png" alt="相同动作在两种时间步下的形状差异">
<h2>几何可行与实际可解</h2><p>8 根线平行收拢时外包络半径为 {fiber_envelope*1000:.2f} mm，
粗绳半径 {layout.trunk_radius_m*1000:g} mm，环的实际最小净孔半径 {layout.minimum_aperture_radius*1000:.3f} mm；
收拢后的线间净距为 {clearance*1000:.3f} mm。存在不相交、能容入孔径的目标形态。
仅凭这个目标形态，尚不能证明只控制粗绳就一定能到达；实际完整路径须另外通过仿真验证。</p>
{full_link}
<p>本报告只覆盖当前离散杆模型、seed=7 与测试动作，不包含真实铜材精度、空间分段收敛或机械臂实际抓取认证。</p>
<p><a href="result.json">汇总数值</a> · <a href="baseline/report.json">标准步长</a> ·
<a href="half_step/report.json">步长减半</a> · <a href="free_hold/report.json">10 秒自由静置</a> ·
<a href="straight_goal_witness.npz">几何目标形态</a></p></html>''')
    print(json.dumps({k:v for k,v in result.items() if k not in ("runs", "timestep_comparison")}, indent=2))
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folder", type=Path)
    result = assess(parser.parse_args().folder)
    if not result["stability_passed"]:
        raise SystemExit(1)
