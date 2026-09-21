"""Resolved, uniformly scaled scene revisions; old robot qualifications stay pinned."""

import argparse
from dataclasses import asdict, replace
import json
from pathlib import Path

import numpy as np
from omegaconf import OmegaConf

from .geometry import BuzzWireLayout, generate_assets
from .physics import save
from .robot_plan import config
from .verification import verify_route


def scaled_layout(layout, scale):
    """Scale physical lengths, including the tool and sampling cover, about the base origin."""
    if not np.isfinite(scale) or not 0.5 <= scale <= 1:
        raise ValueError("Compact scene scale must be in [0.5, 1]")
    lengths = (
        "clearance_cover_m",
        "vertical_valley_lift_m",
        "wire_radius_m",
        "loop_radius_m",
        "loop_tube_radius_m",
        "stem_length_m",
        "grip_length_m",
        "grip_radius_m",
        "grip_half_thickness_m",
        "end_stop_radius_m",
        "end_stop_thickness_m",
        "rail_segment_m",
        "witness_step_m",
        "end_reserve_m",
        "post_radius_m",
        "post_height_m",
    )
    changes = {key: getattr(layout, key) * scale for key in lengths}
    changes["base_size_m"] = (np.asarray(layout.base_size_m) * scale).tolist()
    changes["mount_size_m"] = (np.asarray(layout.mount_size_m) * scale).tolist()
    for key in ("horizontal_scale", "depth_scale", "height_scale"):
        changes[key] = getattr(layout, key) * scale
    if layout.authored_controls_m:
        changes["authored_controls_m"] = (
            np.asarray(layout.authored_controls_m) * scale
        ).tolist()
    if layout.center_offset_knots_m:
        offsets = np.asarray(layout.center_offset_knots_m).copy()
        offsets[:, 1:] *= scale
        changes["center_offset_knots_m"] = offsets.tolist()
    return replace(layout, **changes)


def prepare(output, family="baseline", scale=0.7, source_seed=None):
    if family != "baseline" and source_seed is None:
        raise ValueError("F1/F2/F3 require their own authored source seed")
    output = Path(output).resolve()
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(output)
    output.mkdir(parents=True, exist_ok=True)
    cfg = config()
    if source_seed:
        source = json.loads(Path(source_seed).read_text())
        original = BuzzWireLayout(**source["layout"])
        cfg.task.origin_xy_m = source["origin"][:2]
        cfg.task.yaw_deg = source["yaw"]
        cfg.robot_demo.grasp_roll_deg = source["grip_roll_deg"]
    else:
        original = BuzzWireLayout(
            **OmegaConf.to_container(cfg.task.geometry, resolve=True)
        )
    layout = replace(
        scaled_layout(original, scale),
        finish="wood_metal",
        post_radius_m=0.011,
        post_height_m=0.040,
    )
    cfg.task.geometry = asdict(layout)
    cfg.task.variant = layout.template_id
    cfg.robot_demo.instance_id = f"{family}_compact_wood_s{round(scale * 100)}_v1"
    cfg.robot_demo.grip_inset_m = (
        float(
            source.get("grip_inset_m", cfg.robot_demo.grip_inset_m)
            if source_seed
            else cfg.robot_demo.grip_inset_m
        )
        * scale
    )
    cfg.env.appearance = [
        rule for rule in cfg.env.appearance if rule.pattern != "buzz_base"
    ]
    cfg.run.output = str(output)
    OmegaConf.save(cfg, output / "config.yaml", resolve=True)
    route, geometry = generate_assets(output / "assets", layout)
    proof = verify_route(route)
    report = dict(
        task_id="buzz_wire_3d",
        family=family,
        instance_id=cfg.robot_demo.instance_id,
        scope="compact scene geometry and materials; no inherited robot or dynamics qualification",
        source_seed=str(Path(source_seed).resolve())
        if source_seed
        else "configs/buzz_wire_3d_robot.yaml",
        scale=scale,
        area_ratio=scale**2,
        previous_base_size_m=list(original.base_size_m),
        geometry=geometry,
        clearance=proof,
        passed=proof["passed"],
        physical_execution_verified=False,
        robot_reachability_verified=False,
        stage_order=list(route.sections),
    )
    save(output / "report.json", report)
    print(
        json.dumps(
            dict(
                family=family,
                passed=proof["passed"],
                base=layout.base_size_m,
                length=route.length,
                clearance=proof["minimum_continuous_clearance_lower_bound_m"],
            )
        ),
        flush=True,
    )
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--family", choices=["baseline", "F1", "F2", "F3"], default="baseline"
    )
    parser.add_argument("--scale", type=float, default=0.7)
    parser.add_argument("--source-seed", type=Path)
    args = parser.parse_args()
    report = prepare(args.output, args.family, args.scale, args.source_seed)
    if not report["passed"]:
        raise SystemExit("Scaled tool route needs adjustment; see report.json")


if __name__ == "__main__":
    main()
