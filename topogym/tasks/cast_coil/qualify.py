"""Produce a Cast Coil readiness report and reproducible candidate variants.

Use --run-physics for both nominal and half-timestep bench runs. Without that
flag, aggregate existing reports; missing checks cannot qualify a demo.
"""
from __future__ import annotations

import argparse
import hashlib
from html import escape
import json
from pathlib import Path
import subprocess
import sys

import numpy as np
from omegaconf import OmegaConf
from scipy.spatial.transform import Rotation

from .geometry import CoilAssembly
from .physics_probe import specifications, target_at
from .verification import VARIANTS, prototype_route, shape_sensitivity_audit, write_geometric_audit

ROOT = Path(__file__).resolve().parents[3]


def compare_profiles(nominal, refined):
    names = {c["name"] for c in nominal["cases"]}
    matches = {c["name"]: c for c in refined["cases"]}
    expected = {c["name"] for c in specifications()}
    if names != expected or set(matches) != expected:
        return dict(passed=False, reason="Incomplete qualification case set", cases=[])
    if abs(nominal["config"]["dt"]/2-refined["config"]["dt"]) > 1e-12:
        return dict(passed=False, reason="Second profile does not halve the timestep", cases=[])
    for key in ("substeps", "iterations", "friction", "constraint_timeconst", "duration_s", "controller", "variants", "cases"):
        if nominal["config"][key] != refined["config"][key]:
            return dict(passed=False, reason=f"Profile changed {key} as well as dt", cases=[])
    cases = []
    for a in nominal["cases"]:
        b = matches[a["name"]]
        position = float(np.linalg.norm(np.array(a["final_relative_translation_m"])-b["final_relative_translation_m"]))
        qa, qb = (Rotation.from_quat(c["final_relative_quaternion_xyzw"]) for c in (a, b))
        angle = float((qa.inv()*qb).magnitude())
        agrees = bool(position < .0005 and angle < .01)
        checks_passed = bool(a["passed"] and b["passed"])
        cases.append(dict(name=a["name"], position_delta_m=position, rotation_delta_rad=angle,
            final_state_agreement=agrees, both_profiles_passed=checks_passed,
            passed=agrees and checks_passed))
    return dict(passed=all(c["passed"] for c in cases), position_tolerance_m=.0005,
                rotation_tolerance_rad=.01,
                final_states_agree=all(c["final_state_agreement"] for c in cases), cases=cases)


def failure_diagnostics(profiles):
    """Explain failed criteria without reclassifying or relaxing the probe."""
    failures = []
    for profile, result in profiles.items():
        if result is None:
            continue
        for c in result["cases"]:
            if c["passed"]:
                continue
            reasons = []
            if not c["contact_reliable"]:
                reasons.append("接触穿透或实际位姿的几何重叠超限")
            if c["kind"] in ("route", "allowed"):
                if c["max_position_error_m"] >= .0005:
                    reasons.append(f'最大位置跟踪误差 {c["max_position_error_m"]*1000:.3f} mm ≥ 0.5 mm')
                if c["max_rotation_error_rad"] >= .01:
                    reasons.append(f'最大姿态偏差（含撤去驱动后）{np.degrees(c["max_rotation_error_rad"]):.3f}° ≥ {np.degrees(.01):.3f}°')
                if c["kind"] == "route" and c["final_separating_plane_gap_m"] <= .01:
                    reasons.append("最终分离面间距不足 10 mm")
            elif not c["expected_behavior_verified"]:
                if c["kind"] == "blocked":
                    reasons.append("受力后发生偏转，未满足固定方向的停止位置/姿态判据；不能据此断言发生穿模")
                else:
                    reasons.append("静置或反向转动的预设行为判据未满足")
            if c["tail_max_speed_m_s"] >= .01:
                reasons.append("撤去驱动后末段速度仍超过 10 mm/s")
            failures.append(dict(profile=profile, case=c["name"], reasons=reasons,
                contact_reliable=c["contact_reliable"],
                max_rotation_error_deg=float(np.degrees(c["max_rotation_error_rad"]))))
    return failures


def release_rotation_diagnostics(output, profiles):
    """Report angular drift after drive release from stored physical poses.

    These are finite differences of 25 ms samples, not solver angular speeds.
    Gold is fixed for these motion cases, so relative rotation is sufficient.
    """
    results = []
    for profile, report in profiles.items():
        if report is None:
            continue
        for c in report["cases"]:
            if c["kind"] == "settle":
                continue
            path = output/profile/f'{c["name"]}_trace.json'
            if not path.exists():
                continue
            trace = json.loads(path.read_text())
            times = np.array([r["time_s"] for r in trace])
            rotations = Rotation.from_quat([r["quaternion_xyzw"] for r in trace])
            rates = (rotations[:-1].inv()*rotations[1:]).magnitude()/np.diff(times)
            mask = times[:-1] >= report["simulated_seconds"]-.3
            results.append(dict(profile=profile, case=c["name"],
                max_sampled_tail_angular_rate_rad_s=float(rates[mask].max()),
                method="25 ms pose finite differences over final 0.3 s; not instantaneous angular velocity"))
    return results


def export_variants(output):
    config = OmegaConf.load(ROOT/"configs/cast_coil_preview.yaml")
    variants = []
    for name, values in VARIANTS.items():
        cfg = OmegaConf.create(OmegaConf.to_container(config))
        cfg.task.scale, cfg.task.yaw_deg = values["scale"], values["yaw_deg"]
        cfg.run.output = f"runs/environment_bootstrap/cast_coil/variants/{name}"
        # A Hydra config outside the repository tree still imports the same
        # shared configuration groups through this explicit search path.
        cfg.hydra.searchpath = [f"file://{ROOT/'configs'}"]
        path = output/"variants"/f"{name}.yaml"
        path.parent.mkdir(parents=True, exist_ok=True)
        OmegaConf.save(cfg, path)
        variants.append(dict(id=name, **values, geometry_changes=False,
            config=str(path.relative_to(output)), robot_qualified=False, official_route_qualified=False))
    return variants


def evidence_matches_geometry(output, profiles, geometry):
    """Reject cached physics evidence for a different template or preset set."""
    for profile, report in profiles.items():
        if report is None or report["config"]["variants"] != VARIANTS:
            return False
        for variant, audit in geometry.items():
            path = output/profile/"assets"/variant/"template.json"
            if not path.exists():
                return False
            template = json.loads(path.read_text())
            digest = hashlib.sha256(json.dumps(template, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
            if digest != audit["template_sha256"]:
                return False
    return True


def write_review(output, report):
    local = report["local_physics_passed"]
    status = "通过" if local else "未通过或未完成"
    rows = []
    profiles = report["profiles"]
    for profile, result in profiles.items():
        if result is None:
            continue
        for c in result["cases"]:
            rows.append(f'<tr><td>{escape(profile)}</td><td>{escape(c["name"])}</td>'
                f'<td>{"通过" if c["passed"] else "未通过"}</td>'
                f'<td>{1000*c["max_penetration_m"]:.4f}</td>'
                f'<td>{1000*c["min_observed_sat_gap_m"]:.4f}</td></tr>')
    variant_rows = ''.join(f'<tr><td>{escape(v["id"])}</td><td>{v["scale"]:g}</td>'
        f'<td>{v["yaw_deg"]:g}°</td><td>{"通过" if v["local_physics_verified"] else "未通过或未完成"}</td>'
        f'<td>{"通过" if v["timestep_verified"] else "未通过或未完成"}</td>'
        f'<td><a href="{v["config"]}">配置</a></td></tr>' for v in report["variants"])
    failure_rows = ''.join(f'<li><code>{escape(f["profile"])}/{escape(f["case"])}</code>：'
        f'{escape("；".join(f["reasons"]))}</li>' for f in report["failed_checks"])
    release_rows = ''.join(f'<tr><td>{escape(d["profile"])}</td><td>{escape(d["case"])}</td>'
        f'<td>{d["max_sampled_tail_angular_rate_rad_s"]:.6f}</td></tr>'
        for d in report["release_rotation_diagnostics"] if d["case"].endswith("_route"))
    comparison_rows = ''.join(f'<tr><td>{escape(c["name"])}</td>'
        f'<td>{c["position_delta_m"]*1000:.4f}</td><td>{np.degrees(c["rotation_delta_rad"]):.4f}</td>'
        f'<td>{"通过" if c["final_state_agreement"] else "未通过"}</td>'
        f'<td>{"通过" if c["both_profiles_passed"] else "未通过"}</td></tr>'
        for c in report["timestep_comparison"]["cases"] if not c["passed"])
    page = f'''<!doctype html><html lang="zh-CN"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Cast Coil · 物理可靠性与可解性检查</title>
<style>body{{max-width:1140px;margin:32px auto;padding:0 22px;background:#f3f5f7;color:#24313d;font:16px/1.7 system-ui}}
section{{background:white;padding:24px;margin:20px 0;border:1px solid #dce2e7;border-radius:10px}}
table{{width:100%;border-collapse:collapse}}td,th{{padding:9px;text-align:left;border-bottom:1px solid #ddd}}
a{{color:#176d9a}}img{{width:100%}}code{{font-size:14px}}</style>
<p><a href="../../../environment_bootstrap/index.html">← 环境汇总</a></p>
<h1>Cast Coil：当前原型的可靠性与可解性</h1>
<section><h2>结论</h2><p>连续几何路径：{"通过" if report["prototype_geometry_solvable"] else "未通过"}。
局部物理台架：{status}。时间步减半对照：{"通过" if report["timestep_comparison"]["passed"] else "未通过或未完成"}。</p>
<p><strong>当前不能发布基于官方教程的正式机器人 demo。</strong>官方八步尚未映射为经过验证的连续位姿；
原型的内侧槽口是近似，且本次没有验证机器人抓持。</p>
<p><a href="result.json">汇总结果</a> · <a href="geometry_audit.json">连续几何证书</a> ·
<a href="nominal/report.json">默认时间步物理报告</a> · <a href="half_dt/report.json">半时间步物理报告</a></p></section>
<section><h2>未通过项</h2><ul>{failure_rows or '<li>现有报告没有失败项；缺失检查仍不能视为通过。</li>'}</ul>
<p>接触可靠性、控制器跟踪、受阻姿态和时间步一致性分别记录。台架判据失败不等于证明谜题无解或物理解算器必然不可靠。</p>
<p>撤去驱动后还需看转动：下列数值由最后 0.3 秒的 25 ms 位姿采样差分得到，不能当作瞬时角速度上界；质心稳定也不代表转动已停。</p>
<table><tr><th>时间步</th><th>路径</th><th>末段最大采样角速率 rad/s</th></tr>{release_rows}</table>
<h3>时间步对照中未通过项</h3><p>最终位姿差阈值为 0.5 mm / {np.degrees(.01):.3f}°；
重复得到相近的失败状态也不代表行为判据通过。</p>
<table><tr><th>检查</th><th>位置差 mm</th><th>角度差 °</th><th>最终状态一致性</th><th>两轮行为检查</th></tr>{comparison_rows}</table></section>
<section><h2>官方教程与本地路径</h2>
<p><a href="https://www.eureka-puzzle.eu/wp-content/uploads/2022/09/515056-Huzzle-Cast-Coil-Oct-2017.pdf">Eureka 发布的 Hanayama 八步示意</a>
给出相对滑动、五次四分之一圈转动和最终退出，但没有尺寸、转轴坐标或连续轨迹。
本次查到一条不同的三段原型路径：左移、绕局部 y 轴转动 −90°、向右移出。</p>
<p>该路径不是官方教程复现，也不证明商业实物存在同样的较短解法。原型的可解性与实物一致性分别记账。</p>
<p>尺寸敏感性对照：将截面宽由 7 mm 增至 7.5 / 8 / 9 mm，并相应缩短侧桥后，
三种初态均合法，但现有转动路径均碰撞。因此这些变化未列入可靠变体；这也不等于证明它们完全无解。</p>
<img src="route_diagnostics.png" alt="原型物理路径的位移、转角和间隙诊断"></section>
<section><h2>物理台架范围</h2><p>静置项中两件均自由、受重力；运动项明确固定金件，银件保持 6 自由度，
以有限外力和力矩驱动，并在末段撤去驱动力。全过程不覆写运动件位姿。运动台架对银件补偿重力；这不等价于夹爪操作。</p>
<p>检查包含自由静置、两个方向允许滑动、六个方向强拉阻挡、反向转动阻挡、完整三段原型路径，以及缩放/朝向变体。
SAT 间隙为正表示分离，为负表示几何重叠；接触穿透另外从物理解算器读取。</p>
<table><tr><th>时间步</th><th>检查</th><th>结果</th><th>最大穿透 mm</th><th>最小 SAT 间隙 mm</th></tr>{''.join(rows)}</table></section>
<section><h2>候选变体及验证状态</h2><p>整体旋转与等比例缩放保持零件和槽口结构，但缩放也改变质量和惯量。
配置可用于复现失败；列出配置不代表通过物理验收。下表物理/时间步状态仅指各自静置和完整路径两项，不包含全部基线负对照。</p>
<table><tr><th>ID</th><th>倍率</th><th>桌面 yaw</th><th>局部物理</th><th>时间步对照</th><th>复现配置</th></tr>{variant_rows}</table>
<p>三个正式视角仍为 <code>agentview / wrist / front_oblique</code>。
需先核实八步路线及夹爪控制，才能将它们用于正式拆解录制；本次没有把位姿回放或台架力控标成正式 demo。</p></section></html>'''
    (output/"index.html").write_text(page)


def plot_diagnostics(output):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(4, 1, figsize=(11, 12), sharex=True, layout="constrained")
    for profile, style in (("nominal", "-"), ("half_dt", "--")):
        path = output/profile/"baseline_3x_route_trace.json"
        if not path.exists():
            continue
        records = json.loads(path.read_text())
        ts = np.array([v["time_s"] for v in records])
        xyz = np.array([v["translation_m"] for v in records])*1000
        angle = Rotation.from_quat([v["quaternion_xyzw"] for v in records]).magnitude()*180/np.pi
        for axis, label in ((0, "x"), (2, "z")):
            axes[0].plot(ts, xyz[:, axis], style, label=f"{profile} {label}")
        axes[1].plot(ts, angle, style, label=profile)
        axes[2].plot(ts, [v["sat_gap_m"]*1000 for v in records], style, label=profile)
        config = json.loads((output/profile/"config.json").read_text())
        for variant in ("baseline_3x", "compact_2x"):
            trace = output/profile/f"{variant}_route_trace.json"
            if not trace.exists():
                continue
            route = prototype_route(CoilAssembly(scale=VARIANTS[variant]["scale"]))
            records = json.loads(trace.read_text())
            times, errors = [], []
            for record in records:
                R, *_ = target_at(route, record["time_s"]-.5-config["dt"])
                observed = Rotation.from_quat(record["quaternion_xyzw"])
                errors.append(np.degrees((Rotation.from_matrix(R)*observed.inv()).magnitude()))
                times.append(record["time_s"])
            axes[3].plot(times, errors, style, label=f"{profile} {variant}")
    for ax in axes:
        ax.grid(alpha=.25)
        ax.legend()
        for t in (.5, 2., 5., 7.5, 8.):
            ax.axvline(t, color="gray", alpha=.25, lw=.7)
    axes[0].set_ylabel("Relative translation (mm)")
    axes[1].set_ylabel("Relative rotation (degrees)")
    axes[2].set_ylabel("SAT separation bound (mm)")
    axes[3].set_ylabel("Rotation deviation from target (degrees)")
    axes[3].set_yscale("symlog", linthresh=.1)
    axes[3].set_ylim(bottom=0)
    axes[3].axhline(np.degrees(.01), color="red", lw=.8)
    axes[3].set_xlabel("Physical time (s)")
    axes[2].axhline(0, color="red", lw=.8)
    fig.suptitle("Cast Coil authored prototype: external-wrench bench, not official robot demo")
    fig.savefig(output/"route_diagnostics.png", dpi=140)
    plt.close(fig)


def summarize(output):
    output = Path(output).resolve()
    geometry = write_geometric_audit(output)
    profiles = {}
    for name in ("nominal", "half_dt"):
        path = output/name/"report.json"
        profiles[name] = json.loads(path.read_text()) if path.exists() else None
    comparison = (compare_profiles(*profiles.values()) if all(profiles.values()) else
                  dict(passed=False, reason="Missing physics profile", cases=[]))
    expected_names = {c["name"] for c in specifications()}
    complete = all(p is not None and {c["name"] for c in p["cases"]} == expected_names for p in profiles.values())
    matches_geometry = evidence_matches_geometry(output, profiles, geometry)
    variants = export_variants(output)
    result = dict(task_id="cast_coil", scope="photo_reference_v1_geometry_and_local_contact_audit",
        prototype_geometry_solvable=all(r["prototype_route_certified"] for r in geometry.values()),
        local_physics_passed=complete and matches_geometry and all(p["passed"] for p in profiles.values()),
        evidence_matches_current_geometry=matches_geometry,
        timestep_comparison=comparison, profiles=profiles, variants=variants,
        failed_checks=failure_diagnostics(profiles),
        release_rotation_diagnostics=release_rotation_diagnostics(output, profiles),
        shape_sensitivity=shape_sensitivity_audit(),
        official_route_verified=False, robot_grasp_verified=False, formal_demo_qualified=False,
        formal_demo_generated=False, formal_camera_names=["agentview", "wrist", "front_oblique"],
        formal_demo_blockers=["official_eight_step_metric_route_not_verified", "real_robot_grasp_and_motion_not_verified"],
        no_global_unsolvability_claim=True)
    for v in variants:
        names = {f"{v['id']}_{kind}" for kind in ("route", "settle")}
        v["local_physics_verified"] = matches_geometry and all(p is not None and names <= {c["name"] for c in p["cases"]} and
            all(c["passed"] for c in p["cases"] if c["name"] in names) for p in profiles.values())
        v["continuous_geometry_verified"] = geometry[v["id"]]["prototype_route_certified"]
        compared = [c for c in comparison["cases"] if c["name"] in names]
        v["timestep_verified"] = matches_geometry and len(compared) == len(names) and all(c["passed"] for c in compared)
    if not result["local_physics_passed"]:
        result["formal_demo_blockers"].append("local_physics_checks_incomplete_or_failed")
    if not comparison["passed"]:
        result["formal_demo_blockers"].append("timestep_comparison_incomplete_or_failed")
    if not matches_geometry:
        result["formal_demo_blockers"].append("physics_evidence_missing_or_geometry_mismatch")
    (output/"result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False)+"\n")
    plot_diagnostics(output)
    write_review(output, result)
    manifest = {str(p.relative_to(output)): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in sorted(output.rglob("*")) if p.is_file() and p.name != "artifact_manifest.json"}
    (output/"artifact_manifest.json").write_text(json.dumps(manifest, indent=2)+"\n")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("runs/environment-solvability/cast_coil/photo_reference_v1"))
    parser.add_argument("--run-physics", action="store_true")
    args = parser.parse_args()
    if args.run_physics:
        for name, dt in (("nominal", .001), ("half_dt", .0005)):
            # A crashed rerun must not silently reuse a previous passing report.
            (args.output/name/"report.json").unlink(missing_ok=True)
            subprocess.run([sys.executable, "-m", "topogym.tasks.cast_coil.physics_probe",
                "--dt", str(dt), "--output", str(args.output/name)], check=False)
    result = summarize(args.output)
    print(json.dumps({k: result[k] for k in ("prototype_geometry_solvable", "local_physics_passed", "formal_demo_qualified")}, indent=2))
    print(args.output/"index.html")


if __name__ == "__main__":
    main()
