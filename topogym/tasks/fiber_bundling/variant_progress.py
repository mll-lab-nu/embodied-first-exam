"""Summarize the actual recorded state of the finite variant demo collection."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path


def live_progress(run):
    """Prefer the latest progress heartbeat over the last completed phase."""
    candidates=[]
    if (run/"bundle_metrics.json").exists():
        candidates.append(json.loads((run/"bundle_metrics.json").read_text())[-1])
    for name in (f"{run.name}.log",f"{run.name}_parallel.log"):
        path=run.parent/name
        if not path.exists():
            continue
        with path.open("rb") as stream:
            stream.seek(max(0,path.stat().st_size-16384))
            lines=stream.read().decode(errors="replace").splitlines()
        for line in reversed(lines):
            try:
                item=json.loads(line)
            except (ValueError,TypeError):
                continue
            if isinstance(item,dict) and "time_s" in item and "phase" in item:
                candidates.append(item)
                break
    if candidates:
        item=max(candidates,key=lambda x:x["time_s"])
        return dict(finished=False,time_s=item["time_s"],phase=item["phase"])
    return dict(finished=False,phase="building_or_initializing")


def summarize(root):
    plan=json.loads((root/"variants.json").read_text())
    rows=[]
    for item in plan["variants"]:
        row=dict(item)
        if item["status"] == "archived_complete":
            rows.append(row)
            continue
        instance=root/"instances"/item["variant_id"]
        gate=instance/"stability/result.json"
        row["stability_passed"]=json.loads(gate.read_text())["stability_passed"] if gate.exists() else None
        row["loading_checks"]={p.parent.name:dict(passed=(r:=json.loads(p.read_text()))["stability_passed"],
            precision=r.get("precision","32"),constraint_solver=r.get("constraint_solver","Newton"))
            for p in sorted(instance.glob("stability*/result.json"))}
        attempts=[]
        for folder in sorted(instance.glob("hybrid_*")):
            attempt=dict(name=folder.name,runs={})
            workflow=folder/"workflow_status.json"
            if workflow.exists():
                attempt["workflow"]=json.loads(workflow.read_text())
            parallel=folder/"parallel_recheck.json"
            if parallel.exists():
                attempt["parallel_recheck"]=json.loads(parallel.read_text())
            for name in ("baseline","half_step"):
                run=folder/name
                if (run/"report.json").exists():
                    report=json.loads((run/"report.json").read_text())
                    attempt["runs"][name]=dict(finished=True,passed=report["passed"],
                        full_threading_verified=report["full_threading_verified"],
                        time_s=report["simulated_seconds"],phase=report["stopped_phase"],failure=report["failure"])
                elif (run/"interruption.json").exists():
                    attempt["runs"][name]=dict(live_progress(run),interrupted=True,
                        interruption=json.loads((run/"interruption.json").read_text()))
                elif run.exists():
                    attempt["runs"][name]=live_progress(run)
            attempts.append(attempt)
        row["attempts"]=attempts
        archived=next((a for a in attempts if a.get("workflow",{}).get("status")=="archived_complete"),None)
        if archived:
            row.update(status="archived_complete",metadata=archived["workflow"]["metadata_directory"],
                strict_timestep_convergence_passed=archived["workflow"]["strict_timestep_convergence_passed"])
        elif attempts:
            latest=attempts[-1]
            row["status"]=latest.get("workflow",{}).get("status","physics_in_progress")
            if latest.get("parallel_recheck",{}).get("status")=="running":
                row["status"]="parallel_recheck_running"
        if attempts:
            active=(archived or attempts[-1]).get("workflow",{}).get("stability_directory")
            if active and Path(active).name in row["loading_checks"]:
                row["stability_passed"]=row["loading_checks"][Path(active).name]["passed"]
        elif row["stability_passed"]:
            row["status"]="load_gate_passed"
        elif (instance/"stability").exists():
            row["status"]="load_gate_in_progress"
        rows.append(row)
    result=dict(updated_at_utc=datetime.now(timezone.utc).isoformat(),variants=rows,
                archived_complete_count=sum(r["status"]=="archived_complete" for r in rows),total=len(rows))
    (root/"status.json").write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n")
    lines=["# 光纤收束：各变体完整穿环记录", "", "旧版完整执行计为一个独立变体；新铜杆版逐实例求解、复核并录制。",
        "正式视频目录：`runs/demos/fiber_bundling/`。每个前缀提供合成、agentview、front_oblique、wrist 四个 MP4。",
        "",f"当前已有完整归档 **{result['archived_complete_count']} / {result['total']}**。详细运行状态见 `status.json`。",
        "", "| 实例 | 线数 | 环内半径 mm | 支柱 | 状态 | 严格时间步对照 | 合成视频 |", "| --- | ---: | ---: | --- | --- | --- | --- |"]
    for row in rows:
        label=row["variant_id"]
        if row.get("metadata"):
            label=f"[{label}](../../../../{row['metadata']}/README.md)"
        else:
            label=f"[{label}](instances/{row['variant_id']}/)"
        convergence=row.get("strict_timestep_convergence_passed")
        result_label="通过" if convergence is True else "未通过" if convergence is False else "待完成"
        video=(f"[MP4](../../../../runs/demos/fiber_bundling/{Path(row['metadata']).name}_composite.mp4)"
               if row.get("metadata") else "待完成")
        lines.append(f"| {label} | {row['fiber_count']} | {row['ring_inner_radius_m']*1000:g} | {row['support']} | {row['status']} | {result_label} | {video} |")
    lines += ["", "完整归档要求从初态真实抓取、全程禁碰与固定连接检查、全部细线和前端护套通过；使用接触后辅助夹持时明确标注。",
        "两种时间步均完成与严格线形收敛是独立结论；严格对照未通过时保留报告，不放宽阈值。",
        "加载检查只认证该实例的静置／轻载范围，完整接触过程由机器人执行记录单独检查。"]
    (root/"README.md").write_text("\n".join(lines)+"\n")
    return result


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root",type=Path)
    result=summarize(parser.parse_args().root)
    print(json.dumps({k:v for k,v in result.items() if k != "variants"},indent=2))
