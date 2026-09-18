"""Summarize independent IK/contact attempts without promoting partial success."""
import argparse
import json
from pathlib import Path

import numpy as np

from .anchored_verifier import CONTRACT_REVISION
from .contact_precision import CONTACT_MODEL


def summarize(folder):
    rows = []
    pending = []
    interrupted = []
    for run in sorted(folder.iterdir()):
        if not run.is_dir() or not (run/"plan.json").exists():
            continue
        if not (run/"report.json").exists():
            if (run/"interruption.json").exists():
                interrupted.append(dict(run=run.name,
                    **json.loads((run/"interruption.json").read_text())))
            else:
                pending.append(run.name)
            continue
        report = json.loads((run/"report.json").read_text())
        plan = report["plan"]
        commands = json.loads((run/"robot_commands.json").read_text())
        residuals = [c["ik_error"] for c in commands if "ik_error" in c]
        command_steps = [c["ik_joint_command_step_rad"] for c in commands
                         if "ik_joint_command_step_rad" in c]
        model = plan.get("contact_model", "genesis_default")
        contract = plan.get("success_contract_revision", "legacy_tips_before_front_jacket")
        rows.append(dict(run=run.name, mode=plan.get("policy_parameters", {}).get("mode"),
            seconds=report["simulated_seconds"], passed=report["passed"],
            full_threading_verified=report["full_threading_verified"],
            contact_model=model, success_contract=contract,
            current_model_and_contract=model == CONTACT_MODEL and contract == CONTRACT_REVISION,
            dt_s=plan["dt"], grasp_link=plan["grasp_link"],
            grasp_assist=plan["grasp_assist"], grasp_executed=report["robot_grasp_executed"],
            failure=report["failure"], stopped_phase=report["stopped_phase"],
            gripper_fine_contact=report["contact_rule"]["failed"],
            maximum_fine_penetration_mm=1000*max(report["maxima"]["fine_penetration_m"],
                                                 report["maxima"]["fine_pair_penetration_m"]),
            max_accepted_ik_position_error_m=max((float(np.linalg.norm(e[:3])) for e in residuals), default=None),
            max_accepted_ik_rotation_error=max((float(np.linalg.norm(e[3:])) for e in residuals), default=None),
            max_accepted_ik_joint_command_step_rad=max(command_steps, default=None),
            report=f"{run.name}/report.json"))
    result = dict(scope="independent whole-bundle robot IK/contact trials; not a solvability proof",
        completed_trials=len(rows), pending_trials=pending,
        interrupted_trials=interrupted,
        verified_complete_trials=[r["run"] for r in rows if r["full_threading_verified"]],
        current_model_and_contract_trials=[r["run"] for r in rows if r["current_model_and_contract"]],
        trials=rows)
    (folder/"summary.json").write_text(json.dumps(result, ensure_ascii=False, indent=2)+"\n")
    lines = ["# 整束 IK 探索记录", "",
        f"已结束 {len(rows)} 次试验；完整穿环通过 {len(result['verified_complete_trials'])} 次。"
        + (f"仍有 {len(pending)} 个目录尚未形成最终报告。" if pending else ""), "",
        "每个目录都是一次从场景初态开始的连续物理执行。不同接触模型和任务判定的试验分开标注，失败记录不追溯改为成功。",
        "", "当前模型允许邻线改变形状，不要求逐根顺序或事先全部捋直；最终仍要求八根细线和至少 30 mm 前端护套合法穿孔，固定终端及圆环不动，夹爪从未碰细线。",
        ""]
    review = folder/"review.json"
    if review.exists():
        selection = json.loads(review.read_text())
        lines += ["## 直接查看", "", selection["conclusion_zh"], ""]
        for movie in selection["videos"]:
            lines.append(f"- [{movie['label']}]({movie['path']})：{movie['description_zh']}")
        lines += ["", "视频按实际采样物理状态回放，末尾保持 2 s 便于观察；回放不插值生成线形。辅助夹持只在真实双侧接触后启用，画面中已标注。", ""]
    lines += ["| 试验 | 当前接触模型及判定 | 时间 s | 完整穿环 | 停止原因 |",
        "|---|---|---:|---|---|"]
    for r in rows:
        reason = (r["failure"] or "通过").split(":", 1)[0].replace("|", "/")
        lines.append(f"| [{r['run']}]({r['report']}) | {'是' if r['current_model_and_contract'] else '历史版本'} | "
                     f"{r['seconds']:.3f} | {'是' if r['full_threading_verified'] else '否'} | {reason} |")
    lines.extend(["", "辅助夹持与纯接触夹持、时间步、IK 残差及接触检查详见 summary.json 和每个试验的 plan.json。",
                  "这些结果证明已执行动作的情况；没有找到完整解不等于任务无解。", ""])
    if pending:
        lines += ["未形成最终报告的目录："+", ".join(pending), ""]
    if interrupted:
        lines += ["进程中断、没有最终任务结论："+", ".join(r["run"] for r in interrupted)
                  +"。详见各目录 interruption.json；不计为完成或物理失败。", ""]
    (folder/"README.md").write_text("\n".join(lines))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folder", type=Path)
    args = parser.parse_args()
    result = summarize(args.folder)
    print(json.dumps({k:v for k,v in result.items() if k != "trials"}, indent=2))


if __name__ == "__main__":
    main()
