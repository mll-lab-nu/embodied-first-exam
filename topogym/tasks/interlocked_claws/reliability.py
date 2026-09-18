"""Assemble the review page without hiding failed or incomplete experiments."""
import argparse
from html import escape
import json
from pathlib import Path
import shutil

from .verification import compare, validate_physical, reference_tracking


def assemble(output, first, second, reference, probes, attempts):
    output=Path(output);evidence=output/"evidence";evidence.mkdir(exist_ok=True,parents=True)
    a,_=validate_physical(first);b,_=validate_physical(second)
    convergence=compare(first,second,evidence/"timestep_comparison.json")
    tracking=reference_tracking(first,evidence/"reference_tracking.json")
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig,axes=plt.subplots(2,1,figsize=(10,5.5),sharex=True,layout="constrained")
    for i,(label,color) in enumerate((("Orange piece","#bc653e"),("Blue piece","#33889c"))):
        t=[s["time_s"] for s in tracking["samples"]]
        axes[0].plot(t,[s["errors"][i]["position_m"]*1000 for s in tracking["samples"]],color=color,label=label)
        axes[1].plot(t,[s["errors"][i]["rotation_rad"]*180/3.141592653589793 for s in tracking["samples"]],color=color)
    axes[0].set_ylabel("Position difference (mm)");axes[1].set_ylabel("Orientation difference (deg)")
    axes[1].set_xlabel("Reference time (s)");axes[0].legend();axes[0].set_title("Integrated physical state vs. original recorded motion (10 Hz)")
    for ax in axes:
        ax.grid(alpha=.2);ax.axvline(105.117,color="gray",ls="--",lw=.8);ax.axvline(144.292,color="gray",ls="--",lw=.8)
    fig.savefig(output/"reference_tracking.png",dpi=160);plt.close(fig)
    for name,source in (("physical",first),("physical_half_step",second),("reference_geometry",reference)):
        target=evidence/name
        if not target.exists():shutil.copytree(source,target)
    controls=[]
    for source in probes:
        source=Path(source);target=evidence/"contact_controls"/source.name
        shutil.copytree(source,target,dirs_exist_ok=True)
        p=source/"report.json"
        if p.exists():
            r=json.loads(p.read_text())
            controls.append(dict(name=source.name,passed=r["passed"],report=str((target/"report.json").relative_to(output)),
                cases=[{k:v for k,v in c.items() if k!="trace"} for c in r["cases"]]))
        else:
            controls.append(dict(name=source.name,passed=None,report=str((target/"incomplete.json").relative_to(output)),cases=[]))
    failures=[]
    for source in attempts:
        source=Path(source)
        r=json.loads((source/"result.json").read_text())
        if r["success"]:continue
        target=evidence/"earlier_attempts"/source.name;target.mkdir(parents=True,exist_ok=True)
        for name in ("result.json","states.jsonl","config.yaml","execution_source.py"):
            if (source/name).exists():shutil.copy2(source/name,target/name)
        failures.append(dict(name=source.name,time_s=r["simulated_seconds"],reason=r["failed"],
                             report=str((target/"result.json").relative_to(output))))
    geometry=json.loads((Path(reference)/"reference_audit.json").read_text())
    generic=bool(controls and all(c["passed"] is True for c in controls))
    report=dict(reference_geometry_passed=geometry["passed"],complete_physical_demo_passed=a["success"] and b["success"],
        timestep_comparison_passed=convergence["passed"],generic_contact_robustness_passed=generic,
        friction_only_grasp_verified=False,qualification="reference_execution_with_ideal_grasp_only",
        main_stats=a["stats"],half_step_stats=b["stats"],convergence=convergence,contact_controls=controls,
        reference_tracking={k:v for k,v in tracking.items() if k!="samples"},
        earlier_attempts=failures,assumptions=["Source pregrasped start; ideal rigid welds are assumed immediately, not inferred from finger contacts",
            "Welds removed at recorded release times; both objects then rest without constraints",
            "Robot gravity compensation; original actuator force limits; tuned stiff position/velocity controller",
            "Original visual/collision triangles; Genesis nonconvex contacts use sampled SDF",
            "Assumed density 600 kg/m^3 and friction 0.3, not measured from physical hardware"],
        limitations=["Independent surface clearance checks every 20 ms on dynamic states; this is not a continuous exact dynamic collision certificate",
            "Source joint interpolation has a separate continuous interpiece clearance certificate",
            "No friction-only grasp, hardware calibration, or general contact robustness claim"])
    (output/"reliability_report.json").write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n")
    contact_rows="".join(f'<tr><td>{escape(c["name"])}</td><td>{"通过" if c["passed"] else "未完成" if c["passed"] is None else "未通过"}</td><td><a href="{c["report"]}">原始报告</a></td></tr>' for c in controls)
    failure_rows="".join(f'<tr><td>{escape(c["name"])}</td><td>{c["time_s"]:.2f} s</td><td>{escape(str(c["reason"]))}</td><td><a href="{c["report"]}">记录</a></td></tr>' for c in failures)
    (output/"reliability.html").write_text(f'''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Claw 物理可靠性验收</title>
<style>body{{max-width:1100px;margin:35px auto;padding:0 20px;color:#25333d;font:16px/1.8 system-ui;background:#eef2f4}}section{{background:white;padding:24px;margin:20px 0;border-radius:12px}}table{{border-collapse:collapse;width:100%;font-size:14px}}td,th{{border:1px solid #ccd3d7;padding:9px;text-align:left}}a{{color:#146a94}}.note{{background:#fff0ce;padding:18px}}code{{word-break:break-all}}</style>
<a href="index.html">← 完整流程五路视频</a><h1>Claw：物理可靠性验收</h1>
<p class="note">完整参考动作在预抓取、理想刚性辅助抓持条件下完成。通用接触可靠性仍未通过：向下直拉的独立受力试验发生数值失稳。该 demo 可用于检查原动作与场景；当前碰撞配置尚不能作为任意接触策略的可靠训练基准。</p>
<section><h2>原始模型与参考动作</h2><p>原始两件分别 14,780 / 14,480 个三角面，未凸化、未简化。独立 FK 检查及导入顶点检查通过。原视频 3,084 个关节状态、12 个阶段和 156.513 秒时序均保留。</p>
<p>3,083 个原始插值区间完成连续两件间隙界检查；采样最小间隙 {geometry['minimum_sampled_clearance_m']*1000:.6f} mm。该几何证明仅适用于参考插值，不替代受力验证。六个坐标轴直拉方向均出现几何阻挡。</p>
<p>初次接入时共享机器人降低了 20 mm，使原动作碰桌。现用 20 mm 实体垫座恢复源坐标系；支架接触点、零件、双手和桌面的相对关系与来源一致。</p><a href="evidence/reference_geometry/reference_audit.json">连续几何检查</a></section>
<section><h2>完整动力学执行</h2><p>一次从互锁初态开始的连续运行：双臂协同脱困 → 两件分别搬运落架 → 分别解除抓持、张爪、撤回 → 无约束静置。共 {a['physics_steps']:,} 个物理步，{a['simulated_seconds']:.3f} 秒；保存 10 Hz 实际状态用于五路同步渲染。物理执行初始化后没有重写物体或关节位姿。</p>
<table><tr><th>量</th><th>主运行</th><th>半时间步</th></tr>
<tr><td>物理步长 / 子步</td><td>{a['dt']*1000:g} / {a['dt']/a['substeps']*1000:g} ms</td><td>{b['dt']*1000:g} / {b['dt']/b['substeps']*1000:g} ms</td></tr>
<tr><td>最大物体跟踪位置误差</td><td>{a['stats']['max_held_position_error_m']*1000:.4f} mm</td><td>{b['stats']['max_held_position_error_m']*1000:.4f} mm</td></tr>
<tr><td>引擎最大两件穿透</td><td>{a['stats']['max_interpiece_penetration_m']*1000:.5f} mm</td><td>{b['stats']['max_interpiece_penetration_m']*1000:.5f} mm</td></tr>
<tr><td>独立三角形接触深度诊断</td><td>{a['stats']['max_triangle_contact_depth_m']*1000:.5f} mm</td><td>{b['stats']['max_triangle_contact_depth_m']*1000:.5f} mm</td></tr>
<tr><td>最终两件距离</td><td>{a['final_separation_m']*1000:.2f} mm</td><td>{b['final_separation_m']*1000:.2f} mm</td></tr></table>
<p>两次末态均无残余抓持约束，支架提供向上承托力。物理步长减半后，10 Hz 对齐状态最大位置差 {convergence['max_position_difference_m']*1000:.4f} mm，最大姿态差 {convergence['max_rotation_difference_rad']:.6f} rad；比较结果：{'通过' if convergence['passed'] else '未通过'}。</p>
<p><a href="evidence/physical/result.json">主运行</a> · <a href="evidence/physical_half_step/result.json">半时间步复测</a> · <a href="evidence/timestep_comparison.json">时间步敏感性</a></p>
<h3>与原视频同一时刻的位姿对照</h3><p>抓持期间，保存状态与参考动作同一时刻的最大位置偏差 {tracking['max_held_position_error_m']*1000:.4f} mm，最大姿态偏差 {tracking['max_held_rotation_error_rad']:.6f} rad。释放后的偏差来自实际自由落稳。</p><img style="width:100%" src="reference_tracking.png"><a href="evidence/reference_tracking.json">逐帧对照数据</a></section>
<section><h2>接触对照与失败证据</h2><p>自由方向短移与重力落地通过。向上直拉虽然产生阻挡，但加入独立三角网格审计后，接触深度诊断约 0.954 mm，超过 0.15 mm 阈值；因此也未通过。向下直拉发生异常大反力及物体飞离。提高姿态刚度、降低外力及放软约束均未解决。更细 SDF 的试跑停在预处理阶段，不能计为通过或失败。失败记录没有被删除，也未通过扩大验收阈值变成通过。</p>
<table><tr><th>试验</th><th>结论</th><th>证据</th></tr>{contact_rows}</table>
<h3>早期轨迹试跑</h3><table><tr><th>版本</th><th>终止时间</th><th>原因</th><th>证据</th></tr>{failure_rows}</table></section>
<section><h2>验证边界</h2><p>起点直接采用作者的预抓取与理想抓持假设；两件与夹爪的刚性约束不是由双指接触检测建立。因此未验证纯摩擦抓取，也没有模拟从桌面寻找并夹起两件的过程。保留原电机力矩上限，机器人采用重力补偿和较高位置控制刚度。密度 600 kg/m³、摩擦系数 0.3 是假设参数。</p><p>动态精确网格检查每 20 ms 一次，引擎接触每物理步监测；三角形接触深度是局部诊断值，不是完整体积穿透距离或连续动态证明。真实硬件可执行性与通用接触鲁棒性尚未验证。</p><a href="reliability_report.json">完整机器可读验收报告</a></section></html>''')
    return report


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    for key in ("output","first","second","reference"):p.add_argument("--"+key,required=True)
    p.add_argument("--probe",action="append",default=[]);p.add_argument("--attempt",action="append",default=[])
    a=p.parse_args();assemble(a.output,a.first,a.second,a.reference,a.probe,a.attempt)
