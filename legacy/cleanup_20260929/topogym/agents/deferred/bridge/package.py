"""Operator: export a clean solver package from a fresh bridge, without actions."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import shutil
from urllib.parse import quote

from .client import Client
from .session import write_json


def export_package(client, output, run_id):
    state = client.state()
    if state["state"] != "ready" or state["tick"] != 0 or state["segments"]:
        raise ValueError("Export a fresh ready episode at tick 0; never reuse a previous attempt")
    if "tool_policy" not in state:
        raise ValueError("This bridge predates the task/tool policy update")
    task = state["task"]
    if task.get("goal_reference") or any(PurePosixPath(a["path"]).suffix not in (".json", ".md")
                                         for a in task.get("public_assets", [])):
        raise ValueError("This bridge exposes object reference assets; create a fresh run with the current adapter")
    template = Path(__file__).resolve().parents[2]/"docs/develop/modules/agent_solver_prompt_zh.md"
    instructions = template.read_text(encoding="utf-8")
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    config = dict(run_id=run_id, package_revision=4, url=client.base_url,
        transport="local_files" if client.base_url.startswith("local://") else "http_loopback",
        task_id=task["task_id"], objective=task.get("objective"),
        token_budget_target=state["budget"]["limit"], usage_mode=state["budget"]["mode"],
        usage_measured=state["budget"]["mode"] == "metered",
        access_mode="tools_open_reference_restricted_pilot", tool_policy=state["tool_policy"],
        task_spec="task_spec.json", task_brief="TASK_BRIEF.md", solver_instructions="SOLVER_INSTRUCTIONS.md")
    write_json(output/"bridge_config.json", config)
    write_json(output/"task_spec.json", task)
    (output/"SOLVER_INSTRUCTIONS.md").write_text(instructions, encoding="utf-8")
    shutil.copyfile(Path(__file__).with_name("client.py"), output/"bridge_client.py")
    for asset in task.get("public_assets", []):
        relative = PurePosixPath(asset["path"])
        if relative.is_absolute() or ".." in relative.parts or relative.parts[0] != "public_assets":
            raise ValueError("Expected an explicitly published public_assets path")
        data = client.request("/artifacts/"+quote(asset["path"], safe="/"), raw=True)
        if hashlib.sha256(data).hexdigest() != asset["sha256"]:
            raise ValueError("Public asset checksum mismatch")
        target = output.joinpath(*relative.parts)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    brief = (f"# {task['task_id']} · 公开任务说明\n\n"
             f"{task.get('task_goal', task.get('goal', 'Read task_spec.json for the goal.'))}\n\n"
             "只使用本包基础说明、本轮观测和通用知识；不得读取已有 demo、源码、解法或其他试验。\n\n")
    brief += "不提供物体参考图、几何模型或目标相对变换；请根据本轮实时多视角图像和动作反馈判断构型。\n\n"
    brief += "完整机械臂/动作/坐标系/相机参数见 [task_spec.json](task_spec.json)。初始和每段现场通过 `python bridge_client.py observe` 获取。\n\n"
    brief += "```json\n"+json.dumps(task, ensure_ascii=False, indent=2)+"\n```\n"
    (output/"TASK_BRIEF.md").write_text(brief, encoding="utf-8")
    # These are observations from THIS episode, not reference/goal imagery.
    manifest = client.request("/artifacts/initial/manifest.json")
    if (len(manifest["frames"]) != 1 or manifest["frames"][0]["tick"] != 0
            or set(manifest["frames"][0]["cameras"]) != set(task["cameras"])):
        raise ValueError("Expected synchronized initial images from every declared camera")
    for name, item in manifest["frames"][0]["cameras"].items():
        relative = PurePosixPath(item["path"])
        if (relative.is_absolute() or ".." in relative.parts or len(relative.parts) != 3
                or relative.parts[:2] != ("initial", name) or relative.suffix != ".png"):
            raise ValueError("Invalid initial camera artifact path")
        data = client.request("/artifacts/"+quote(item["path"], safe="/"), raw=True)
        if hashlib.sha256(data).hexdigest() != item["sha256"]:
            raise ValueError("Initial image checksum mismatch")
        target = output/"feedback"/item["path"]
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    write_json(output/"feedback/initial/manifest.json", manifest)
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8765")
    parser.add_argument("--output", required=True)
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args()
    print(export_package(Client(args.url), args.output, args.run_id))


if __name__ == "__main__":
    main()
