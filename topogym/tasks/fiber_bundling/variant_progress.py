"""Summarize the actual recorded state of the finite variant demo collection."""
import argparse
from datetime import datetime, timezone
import json
import os
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
    historical_complete_count=sum(r["status"]=="archived_complete" for r in rows)
    repo=Path(__file__).resolve().parents[3]
    current_archives={}
    for path in sorted((repo/"runs/demo_metadata/fiber_bundling").glob("*/archive_manifest.json")):
        item=json.loads(path.read_text())
        if item.get("counts_as_complete_robotics_demo") and all(
                camera in item.get("videos",{}) and (path.parent/item["videos"][camera]["path"]).is_file()
                for camera in ("agentview","front_oblique","wrist")):
            key=(item["fiber_count"],item["ring_inner_radius_m"],item["support"])
            current_archives[key]=path
    for row in rows:
        if not row.get("metadata"):
            continue
        metadata=repo/row["metadata"]
        manifest_path=metadata/"archive_manifest.json"
        replacement=current_archives.get((row["fiber_count"],row["ring_inner_radius_m"],row["support"]))
        if replacement is not None and replacement != manifest_path:
            row["historical_metadata"]=row["metadata"]
            metadata=replacement.parent
            manifest_path=replacement
            row["metadata"]=str(metadata.relative_to(repo))
        if not manifest_path.exists():
            row["historical_metadata"]=row.pop("metadata")
            row["video_files"]={}
            if row["status"]=="archived_complete":
                row["status"]="historical_execution_only"
            continue
        manifest=json.loads(manifest_path.read_text())
        if manifest.get("replacement_metadata"):
            row["historical_metadata"]=row["metadata"]
            row["metadata"]=manifest["replacement_metadata"]
            metadata=repo/row["metadata"]
            manifest=json.loads((metadata/"archive_manifest.json").read_text())
        row["video_files"]={camera:str((metadata/video["path"]).resolve().relative_to(repo))
            for camera,video in manifest.get("videos",{}).items() if (metadata/video["path"]).is_file()}
        if row["video_files"]:
            row["strict_timestep_convergence_passed"]=manifest.get("strict_timestep_convergence_passed")
        if not row["video_files"] and manifest.get("video_retention",{}).get("status")=="removed_by_user_request":
            row["status"]="historical_execution_only"
    result=dict(updated_at_utc=datetime.now(timezone.utc).isoformat(),variants=rows,
                historical_archived_complete_count=historical_complete_count,
                archived_complete_count=sum(r["status"]=="archived_complete" for r in rows),total=len(rows))
    (root/"status.json").write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n")
    lines=["# 光纤收束：各变体完整穿环记录", "", "旧版完整执行计为一个独立变体；新铜杆版逐实例求解、复核并录制。",
        "当前正式视频目录：`demos/fiber_bundling/varaition_<实例名>/<视角>/`；各密度家族代表分别保留 agentview、front_oblique、wrist 三路无 UI 完整视频，每个相机叶子目录一份 MP4。",
        "",f"历史完整执行 **{historical_complete_count} / {result['total']}**；当前提供视频的实例 **{result['archived_complete_count']}**。其余旧录像按用户要求移除，物理证据保留。详细状态见 `status.json`。",
        "", "| 实例 | 线数 | 环内半径 mm | 支柱 | 状态 | 严格时间步对照 | 视频 |", "| --- | ---: | ---: | --- | --- | --- | --- |"]
    for row in rows:
        label=row["variant_id"]
        if row.get("metadata"):
            label=f"[{label}](../../../../{row['metadata']}/README.md)"
        elif (root/"instances"/row["variant_id"]).is_dir():
            label=f"[{label}](instances/{row['variant_id']}/)"
        convergence=row.get("strict_timestep_convergence_passed")
        result_label="通过" if convergence is True else "未通过" if convergence is False else "待完成"
        names=dict(agentview="全景",front_oblique="近景",wrist="腕部",composite="合成")
        video=" · ".join(f"[{names.get(camera,camera)}]({os.path.relpath(repo/path,root.resolve())})"
                         for camera,path in row.get("video_files",{}).items())
        if not video:
            video="旧录像已移除" if row["status"]=="historical_execution_only" else "待完成"
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
