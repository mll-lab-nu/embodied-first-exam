"""Independent full-tool geometric witness; never a robot execution certificate."""

import argparse
from dataclasses import asdict, replace
import json
from pathlib import Path
import shutil

import numpy as np
from omegaconf import OmegaConf
from scipy.optimize import minimize
from scipy.spatial.transform import Rotation

from .family_plan import construct, handle_guide
from .geometry import BuzzWireLayout, SpatialWire
from .physics import save
from .verification import ClearanceOracle, verify_route


def witness(family, output, samples=1401, smoothing_m=0.0, reference_path=None):
    output = Path(output).resolve()
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(output)
    output.mkdir(parents=True, exist_ok=True)
    shutil.copy2(__file__, output / "witness_source.py")
    save(
        output / "settings.json",
        dict(
            family=family,
            samples=samples,
            smoothing_m=smoothing_m,
            reference_path=str(reference_path) if reference_path else None,
        ),
    )
    cfg, layout, _ = construct(family, smoothing_m)
    OmegaConf.save(cfg, output / "config.yaml", resolve=True)
    route = SpatialWire(layout)
    reference = None
    if reference_path:
        source_cfg = OmegaConf.load(reference_path)
        source_layout = BuzzWireLayout(
            **OmegaConf.to_container(source_cfg.task.geometry, resolve=True)
        )
        if json.dumps(
            asdict(replace(source_layout, orientation_knots_wxyz=())), sort_keys=True
        ) != json.dumps(asdict(layout), sort_keys=True):
            raise ValueError("Reference must have identical physical geometry")
        reference = SpatialWire(source_layout)
    oracle = ClearanceOracle(route, spacing=layout.clearance_cover_m)
    us = np.linspace(0, 1, samples)
    ps = np.array([route.pose(float(u))[0] for u in us])
    ts = np.gradient(ps, axis=0)
    ts /= np.linalg.norm(ts, axis=1)[:, None]
    previous = route.rotations[0]
    rows, failure = [], None
    for i, (u, p, tangent) in enumerate(zip(us, ps, ts)):
        guide = handle_guide(route, family, u)
        guide -= (guide @ tangent) * tangent
        if np.linalg.norm(guide) < 0.1:
            guide = previous.apply([1, 0, 0])
            guide -= (guide @ tangent) * tangent
        guide /= np.linalg.norm(guide)
        target = Rotation.from_matrix(
            np.column_stack([guide, np.cross(tangent, guide), tangent])
        )
        if reference is not None:
            target = Rotation.from_quat(reference.pose(float(u))[1][[1, 2, 3, 0]])

        def evaluate(v):
            r = Rotation.from_rotvec(v) * previous
            return r, oracle.clearance(p, r)

        def objective(v):
            r, _ = evaluate(v)
            return float(
                (0.03 if reference is not None else 3.0) * np.sum(v**2)
                + (r.inv() * target).magnitude() ** 2
            )

        def constraint(v):
            r, c = evaluate(v)
            return np.array(
                [
                    100 * (c - 0.0035),
                    r.apply([0, 0, 1]) @ tangent - 0.4,
                    (0.18**2 - np.sum(v**2)) if i else 1.0,
                ]
            )

        starts = [np.zeros(3), (target * previous.inv()).as_rotvec()]
        for start in starts:
            opt = minimize(
                objective,
                start,
                method="SLSQP",
                constraints=[dict(type="ineq", fun=constraint)],
                options=dict(maxiter=100, ftol=1e-10),
            )
            r, c = evaluate(opt.x)
            # At most 20 micrometres around the conservative search margin;
            # the continuous certificate below still requires >1 mm everywhere.
            if constraint(opt.x).min() > -0.002 and (
                i == 0 or np.linalg.norm(opt.x) < 0.3
            ):
                previous = r
                rows.append(
                    dict(
                        progress=float(u),
                        quaternion_wxyz=r.as_quat()[[3, 0, 1, 2]].tolist(),
                        clearance_m=float(c),
                    )
                )
                break
        else:
            failure = dict(
                index=i,
                progress=float(u),
                clearance_m=c,
                angular_step_rad=float(np.linalg.norm(opt.x)),
                message=opt.message,
            )
            break
        if i % 100 == 0:
            print(
                f"{family} fixture witness {i}/{samples} clearance={c:.5f}", flush=True
            )
    save(output / "witness_rows.json", rows)
    result = dict(passed=False, failure=failure, robot_execution_verified=False)
    if failure is None:
        layout = replace(
            layout,
            orientation_knots_wxyz=[
                [r["progress"], *r["quaternion_wxyz"]] for r in rows
            ],
        )
        cfg.task.geometry = asdict(layout)
        OmegaConf.save(cfg, output / "config.yaml", resolve=True)
        result = verify_route(SpatialWire(layout))
    save(output / "clearance.json", result)
    print(result, flush=True)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--family", choices=["F1", "F2", "F3"], required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--smoothing-m", type=float, default=0.0)
    parser.add_argument("--samples", type=int, default=1401)
    parser.add_argument("--reference-path", type=Path)
    args = parser.parse_args()
    if not witness(**vars(args))["passed"]:
        raise SystemExit(1)
