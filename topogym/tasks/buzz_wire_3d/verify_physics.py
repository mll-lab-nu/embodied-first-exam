"""Compare complete physical fixture rollouts at two integration timesteps."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from scipy.spatial.transform import Rotation

from .physics import save
from .render import physics_signature, sha


def plot_results(paths, reports, output):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(2, 2, figsize=(12, 7), layout="constrained")
    for name, label in (
        ("nominal", "4 ms control / 0.25 ms integration"),
        ("refined", "2 ms control / 0.125 ms integration"),
    ):
        rows = json.loads((paths[name] / "frames.json").read_text())
        rows = [r for r in rows if r["phase"] != "release"]
        t = [r["time_s"] for r in rows]
        axes[0, 0].plot(
            t, [1000 * r["tracking_error_m"] for r in rows], label=label, lw=1
        )
        axes[0, 1].plot(
            t, [np.degrees(r["angular_error_rad"]) for r in rows], label=label, lw=1
        )
    rows = json.loads((paths["contact"] / "frames.json").read_text())
    axes[1, 0].plot(
        [r["time_s"] for r in rows], [r["wire_force_N"] for r in rows], color="#d78228"
    )
    rows = json.loads((paths["gravity"] / "frames.json").read_text())
    axes[1, 1].plot(
        [r["time_s"] for r in rows],
        [1000 * r["penetration_m"] for r in rows],
        color="#277d99",
    )
    peak = 1000 * reports["gravity"]["maximum_penetration_m"]
    axes[1, 1].axhline(
        0.5, color="#b44545", linestyle="--", label="0.5 mm acceptance limit"
    )
    axes[1, 1].text(
        0.04,
        0.75,
        f"Peak checked every control tick: {peak:.3f} mm",
        transform=axes[1, 1].transAxes,
    )
    for ax, title, unit in zip(
        axes.flat,
        (
            "Full route: position tracking",
            "Full route: orientation tracking",
            "Deliberate wire contact and return",
            "Gravity release: contact penetration",
        ),
        ("Error (mm)", "Error (degrees)", "Wire reaction (N)", "Penetration (mm)"),
    ):
        ax.set(title=title, xlabel="Simulation time (s)", ylabel=unit)
        ax.grid(alpha=0.2)
    axes[0, 0].legend(fontsize=8)
    axes[1, 1].legend(fontsize=8)
    fig.suptitle("3D Buzz Wire — measured rigid-body fixture dynamics (no robot)")
    fig.savefig(output, dpi=160)
    plt.close(fig)


def verify(gravity, contact, nominal, refined, output):
    paths = {
        name: Path(path).resolve()
        for name, path in dict(
            gravity=gravity, contact=contact, nominal=nominal, refined=refined
        ).items()
    }
    reports = {n: json.loads((p / "report.json").read_text()) for n, p in paths.items()}
    frames = {
        n: json.loads((paths[n] / "frames.json").read_text())
        for n in ("nominal", "refined")
    }
    expected = dict(
        gravity="gravity", contact="contact", nominal="traverse", refined="traverse"
    )
    checks = {
        n + "_passed": r["passed"] and r["case"] == expected[n]
        for n, r in reports.items()
    }
    checks["same_physical_geometry"] = all(
        physics_signature(p / "assets" / asset)
        == physics_signature(paths["nominal"] / "assets" / asset)
        for p in paths.values()
        for asset in ("wire.urdf", "wand.urdf")
    )
    checks["same_task_configuration"] = all(
        r["geometry"]["layout"] == reports["nominal"]["geometry"]["layout"]
        for r in reports.values()
    )
    a, b = reports["nominal"]["settings"], reports["refined"]["settings"]
    checks["halved_control_and_integration_step"] = (
        np.isclose(b["dt"], a["dt"] / 2)
        and b["substeps"] == a["substeps"]
        and all(a[k] == b[k] for k in a if k != "dt")
    )
    checks["no_physics_pose_overwrites"] = all(
        r["pose_writes_after_reset"] == 0 for r in reports.values()
    )
    checks["matching_timestamps"] = len(frames["nominal"]) == len(
        frames["refined"]
    ) and np.allclose(
        [s["time_s"] for s in frames["nominal"]],
        [s["time_s"] for s in frames["refined"]],
        atol=1e-9,
        rtol=0,
    )
    max_position, max_orientation = 0.0, 0.0
    if checks["matching_timestamps"]:
        for x, y in zip(frames["nominal"], frames["refined"]):
            if x["phase"] == "release":
                continue  # Release has its own settling/contact acceptance.
            max_position = max(
                max_position,
                float(np.linalg.norm(np.array(x["position_m"]) - y["position_m"])),
            )
            rx = Rotation.from_quat(np.array(x["quaternion_wxyz"])[[1, 2, 3, 0]])
            ry = Rotation.from_quat(np.array(y["quaternion_wxyz"])[[1, 2, 3, 0]])
            max_orientation = max(max_orientation, float((rx * ry.inv()).magnitude()))
    checks["controlled_trace_convergence"] = (
        checks["matching_timestamps"]
        and max_position < 0.002
        and max_orientation < 0.03
    )
    result = dict(
        passed=all(checks.values()),
        checks=checks,
        task_id="buzz_wire_3d",
        variant=reports["nominal"]["variant"],
        scope="Rigid fixed toy, dynamic six-DOF wand, bounded external wrench; no robot grasp or flexible-wire/electrical validation",
        robot_present=False,
        full_robot_task_verified=False,
        measurement_scope="Contacts, penetration and topology checked after each outer step; internal substeps unrecorded; saved pose trace is 50 Hz",
        maximum_controlled_position_difference_m=max_position
        if checks["matching_timestamps"]
        else None,
        maximum_controlled_orientation_difference_rad=max_orientation
        if checks["matching_timestamps"]
        else None,
        comparison_limits=dict(position_m=0.002, orientation_rad=0.03),
        runs={
            n: dict(
                directory=str(p),
                report_sha256=sha(p / "report.json"),
                frames_sha256=sha(p / "frames.json"),
            )
            for n, p in paths.items()
        },
        reports=reports,
    )
    save(output, result)
    plot_results(paths, reports, Path(output).with_suffix(".png"))
    print(json.dumps({k: v for k, v in result.items() if k != "reports"}, indent=2))
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("gravity", "contact", "nominal", "refined", "output"):
        p.add_argument("--" + name, type=Path, required=True)
    result = verify(**vars(p.parse_args()))
    if not result["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
