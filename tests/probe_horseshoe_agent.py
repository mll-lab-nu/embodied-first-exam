"""Opt-in live CPU/Genesis adapter probe; never runs a solving trajectory."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

from topogym.agent_bridge.client import Client


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    root = args.output.resolve()
    root.mkdir(parents=True, exist_ok=False)
    package = root/"solver"
    subprocess.run([sys.executable, "-m", "topogym.agent_bridge.local", "--task", "horseshoe_ring",
                    "--output", str(root/"episode"), "--package", str(package), "--no-allow-internet"], check=True)
    client = Client(json.loads((package/"bridge_config.json").read_text())["url"])
    checks = {}
    try:
        initial = client.state()
        assert initial["state"] == "ready" and initial["tick"] == 0, initial["reason"]
        assert set(initial["observation"]) == {"robot", "grasp_assistance", "camera_poses"}
        first_images = client.request("/artifacts/initial/manifest.json")
        assert len(first_images["frames"][0]["cameras"]) == 4
        checks["initial_four_views_at_tick_zero"] = True
        try:
            client.submit('env.step({"left": {"gripper": 99}})', request_id="invalid", expected_segment=1)
            raise AssertionError("Invalid action accepted")
        except ValueError:
            assert client.state()["tick"] == 0
        checks["invalid_action_no_motion"] = True
        code = ('q = obs["robot"]["left"]["arm_qpos"]\n'
                'for i in range(1, 51):\n'
                '    env.step({"left": {"qpos": [q[0]+0.005*i/50, q[1], q[2], q[3], q[4], q[5]]}})')
        result = client.submit(code, request_id="small_motion", expected_segment=1)
        assert result["state"] == "ready", result
        assert result == client.submit(code, request_id="small_motion", expected_segment=1)
        after = client.state()
        assert after["tick"] == 50
        assert after["observation"]["robot"]["left"]["arm_qpos"] != initial["observation"]["robot"]["left"]["arm_qpos"]
        checks["joint_motion_and_idempotent_retry"] = True
        # Open one hand; other hand must retain its real solver weld.
        result = client.submit('env.step({"left": {"gripper": 0.037}}, steps=50)',
                               request_id="open_left", expected_segment=2)
        assert result["state"] == "ready", result
        after = client.state()
        assert after["tick"] == 100
        assert not after["observation"]["grasp_assistance"]["left"]["active"]
        assert after["observation"]["grasp_assistance"]["right"]["active"]
        checks["opening_releases_only_commanded_hand"] = True
        previous = None
        for n in (1, 2):
            manifest = client.request(f"/artifacts/segment_{n:03d}/manifest.json")
            assert len(manifest["frames"]) == 51
            assert all(len(f["cameras"]) == 4 for f in manifest["frames"])
            if previous:
                assert previous["tick"] == manifest["frames"][0]["tick"]
                assert previous["observation"] == manifest["frames"][0]["observation"]
                assert {k:v["sha256"] for k,v in previous["cameras"].items()} == {
                    k:v["sha256"] for k,v in manifest["frames"][0]["cameras"].items()}
            previous = manifest["frames"][-1]
        checks["every_tick_four_frames_and_segment_continuity"] = True
        checks["scope"] = "100 physics ticks / 0.2 s; small joint motion and one-hand release, NOT a solve"
        (root/"probe_report.json").write_text(json.dumps(checks, indent=2)+"\n")
        print(json.dumps(checks), flush=True)
    finally:
        client.request("/v1/shutdown", dict(reason="Operator adapter probe complete; not a solving attempt"))


if __name__ == "__main__":
    main()
