"""Compare two independently simulated full-bundle executions at different dt."""
import argparse
import json
from pathlib import Path
import re

import numpy as np

from .geometry import shape_in_root_frame
from .validation import LIMITS


def publish_summary(output):
    """Keep the video page's verification summary reproducible without re-rendering."""
    output = Path(output)
    if not (output/"index.html").is_file() or not (output/"timestep_validation.json").is_file():
        return
    result = json.loads((output/"timestep_validation.json").read_text())
    worst = max(c["max_m"] for c in result["checkpoints"])*1000
    rms = max(c["rms_m"] for c in result["checkpoints"])*1000
    status = "通过" if result["passed"] else "未通过"
    section = (f'<section id="timestep-validation"><h2>全流程减半时间步复核：{status}</h2>'
        f'<p>独立运行 2 ms 与 1 ms 时间步；检查逐根整理结束、推进前及最终状态。'
        f'这些检查点的最大形状差异为 {worst:.3f} mm，最大 RMS 为 {rms:.3f} mm。'
        '结果与两次完整穿环验收见 <a href="timestep_validation.json">复核记录</a>。'
        '验证限定于当前 seed 和离散模型；尚未标定铜材力学或执行机械臂抓取。</p></section>')
    page = (output/"index.html").read_text()
    if 'id="timestep-validation"' in page:
        page = re.sub(r'<section id="timestep-validation">.*?</section>', lambda _: section, page, flags=re.S)
    else:
        page = page.replace('<table><tr><th>电线', section+'\n<table><tr><th>电线')
    (output/"index.html").write_text(page)


def assess(baseline, half_step):
    reports = [json.loads((p/"report.json").read_text()) for p in (baseline, half_step)]
    trajectories = [np.load(p/"trajectory.npz") for p in (baseline, half_step)]
    comparisons = []
    for phase in [f"wire_{i}_inspect" for i in reports[0]["plan"]["order"]]+["before_push", "final_hold"]:
        states = []
        for data in trajectories:
            indices = np.flatnonzero(data["phases"] == phase)
            if not len(indices):
                raise ValueError(f"Missing completed phase: {phase}")
            states.append(shape_in_root_frame(data["fibers"][indices[-1]]))
        distances = np.linalg.norm(states[0]-states[1], axis=-1)
        comparisons.append(dict(phase=phase, max_m=float(distances.max()),
                                rms_m=float(np.sqrt(np.mean(distances**2)))))
    checks = dict(both_full_executions_pass=all(r["passed"] for r in reports),
        same_model=reports[0]["layout"] == reports[1]["layout"],
        same_backend=reports[0]["backend"] == reports[1]["backend"],
        same_substeps=reports[0]["substeps"] == reports[1]["substeps"],
        same_order=reports[0]["plan"]["order"] == reports[1]["plan"]["order"],
        same_press_radius=reports[0]["plan"]["press_radius_m"] == reports[1]["plan"]["press_radius_m"],
        timestep_halved=bool(np.isclose(reports[0]["dt"], 2*reports[1]["dt"])),
        checkpoint_max_bounded=max(c["max_m"] for c in comparisons) < LIMITS["timestep_max_shape_difference_m"],
        checkpoint_rms_bounded=max(c["rms_m"] for c in comparisons) < LIMITS["timestep_rms_shape_difference_m"])
    holds = []
    for report, data in zip(reports, trajectories):
        indices = np.flatnonzero(data["times"] >= data["times"][-1]-.3)
        reference = shape_in_root_frame(data["fibers"][indices[0]])
        drift = max(float(np.linalg.norm(shape_in_root_frame(data["fibers"][i])-reference, axis=-1).max())
                    for i in indices)
        holds.append(dict(dt=report["dt"], final_hold_shape_drift_m=drift))
    checks["both_settled_shapes"] = all(h["final_hold_shape_drift_m"] < LIMITS["final_hold_shape_drift_m"] for h in holds)
    result = dict(passed=all(checks.values()), checks=checks, baseline=str(baseline), half_step=str(half_step),
        checkpoints=comparisons, final_holds=holds, thresholds=LIMITS,
        note="Same seed and articulated model; checks contact control and timestep sensitivity, not calibrated copper mechanics or robot grasp.")
    (baseline/"timestep_validation.json").write_text(json.dumps(result, indent=2)+"\n")
    publish_summary(baseline)
    print(json.dumps(result, indent=2))
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("baseline", type=Path)
    parser.add_argument("half_step", type=Path)
    args = parser.parse_args()
    if not assess(args.baseline, args.half_step)["passed"]:
        raise SystemExit(1)
