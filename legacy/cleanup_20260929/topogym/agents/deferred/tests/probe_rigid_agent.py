"""Opt-in live adapter probe using public actions; no solving trajectory."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

from topogym.agent_bridge.client import Client


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task", choices=("cast_keyhole", "horseshoe_ring", "hedgehog_in_cage", "lock_picking", "interlocked_claws", "buzz_wire_3d"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = args.output.resolve()
    root.mkdir(parents=True, exist_ok=False)
    package = root/"solver"
    subprocess.run([sys.executable, "-m", "topogym.agent_bridge.local", "--task", args.task,
                    "--output", str(root/"episode"), "--package", str(package), "--no-allow-internet"], check=True)
    client = Client(json.loads((package/"bridge_config.json").read_text())["url"])
    report = dict(task=args.task, scope="Short joint-motion and grasp-release probe, NOT a solution", checks={})
    try:
        initial = client.state()
        assert initial["state"] == "ready" and initial["tick"] == 0, initial["reason"]
        assert set(initial["observation"]) == {"robot", "grasp_assistance", "camera_poses"}
        manifest = client.request("/artifacts/initial/manifest.json")
        camera_count = len(initial["task"]["cameras"])
        assert len(manifest["frames"][0]["cameras"]) == camera_count
        assert all((package/"feedback"/v["path"]).is_file() for v in manifest["frames"][0]["cameras"].values())
        report["checks"]["initial_all_views_no_physics"] = True
        if args.task not in ("horseshoe_ring", "interlocked_claws"):
            assert not any(v["active"] for v in initial["observation"]["grasp_assistance"].values())
        else:
            assert all(v["active"] for v in initial["observation"]["grasp_assistance"].values())
        try:
            client.submit('env.step({"right": {"gripper": 10}})', request_id="invalid", expected_segment=1)
            raise AssertionError("Illegal action accepted")
        except ValueError:
            assert client.state()["tick"] == 0
        report["checks"]["invalid_action_no_motion"] = True
        pickup = args.task == "lock_picking"
        friction = args.task == "buzz_wire_3d"
        single = args.task in ("hedgehog_in_cage", "lock_picking", "buzz_wire_3d")
        side, dofs = ("arm", 7) if single else ("left", 6)
        counts = [80, 20, 1] if single else [50, 50, 50]
        if args.task == "interlocked_claws":
            counts = [50, 50, 1]  # Release check only; no unsupported free fall.
        delta, opening = (.0003, .04) if single else (.003, .037)
        values = ", ".join([f"q[0]+{delta}*i/{counts[1]}"]+[f"q[{j}]" for j in range(1, dofs)])
        codes = [f"env.step({{}}, steps={counts[0]})",
            f'q = obs["robot"]["{side}"]["arm_qpos"]\nfor i in range(1, {counts[1]+1}):\n'
            f'    env.step({{"{side}": {{"qpos": [{values}]}}}})',
            f'env.step({{"{side}": {{"gripper": {opening}}}}}, steps={counts[2]})']
        previous, before_motion = manifest["frames"][0], None
        for segment, code in enumerate(codes, 1):
            result = client.submit(code, request_id=f"probe{segment}", expected_segment=segment)
            assert result["state"] == "ready", result
            assert result == client.submit(code, request_id=f"probe{segment}", expected_segment=segment)
            state = client.state()
            assert state["tick"] == sum(counts[:segment])
            m = client.request("/artifacts/"+result["manifest"])
            assert len(m["frames"]) == counts[segment-1]+1
            assert all(len(f["cameras"]) == camera_count for f in m["frames"])
            first = m["frames"][0]
            assert previous["tick"] == first["tick"] and previous["observation"] == first["observation"]
            assert [v["sha256"] for v in previous["cameras"].values()] == [v["sha256"] for v in first["cameras"].values()]
            previous = m["frames"][-1]
            assistance = state["observation"]["grasp_assistance"]
            if segment == 1:
                assert all(v["active"] != (pickup or friction) for v in assistance.values())
                before_motion = state["observation"]["robot"][side]["arm_qpos"]
                if friction:
                    rows = [json.loads(line) for line in (root/"episode/private_assets/adapter_evaluation.jsonl").read_text().splitlines()]
                    assert len(rows[-1]["finger_contact_links"]) == 2
                    assert all(not row["assist_active"] for row in rows)
                report["checks"]["bilateral_friction_contact_without_assistance" if friction else
                    "no_attachment_at_home" if pickup else "bilateral_contact_attachment_or_pregrasp_hold"] = True
            if segment == 2:
                assert state["observation"]["robot"][side]["arm_qpos"] != before_motion
                report["checks"]["actual_joint_motion"] = True
            if segment == 3:
                assert not assistance[side]["active"]
                if not single:
                    assert assistance["right"]["active"]
                report["checks"]["open_command_without_attachment" if pickup or friction else "opening_releases_only_one_hand"] = True
        report["checks"]["idempotency_all_views_and_segment_continuity"] = True
        report.update(physics_ticks=sum(counts), simulated_seconds=sum(counts)*initial["task"]["control_dt_s"],
                      source_sha256={str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in [
                          Path(f"topogym/tasks/{args.task}/agent_adapter.py"),
                          Path("topogym/agent_bridge/robot_adapter.py")]})
        (root/"probe_report.json").write_text(json.dumps(report, indent=2)+"\n")
        print(json.dumps(report), flush=True)
    finally:
        client.request("/v1/shutdown", dict(reason="Operator short adapter probe complete; not a solving attempt"))


if __name__ == "__main__":
    main()
