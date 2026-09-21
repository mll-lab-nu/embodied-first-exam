"""Real detached worker and standalone solver client, without HTTP sockets."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from topogym.agent_bridge.client import Client
from topogym.agent_bridge.session import write_json

ROOT = Path(__file__).resolve().parents[1]


class LocalChecks(unittest.TestCase):
    def test_persistent_episode_clean_package_retry_and_shutdown(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            package = root/"solver"
            launch = [sys.executable, "-m", "topogym.agent_bridge.local", "--task", "counter",
                      "--output", str(root/"episode"), "--package", str(package), "--no-allow-internet"]
            subprocess.run(launch, cwd=ROOT, check=True, capture_output=True, timeout=30)
            config = json.loads((package/"bridge_config.json").read_text())
            client = Client(config["url"])
            try:
                self.assertTrue(config["url"].startswith("local://"))
                self.assertFalse(config["tool_policy"]["allow_internet"])
                self.assertEqual(client.state()["tick"], 0)
                # Native CUDA compilation can hold the worker's GIL for >60 s.
                # Its independent interpreter must keep RPC liveness intact.
                queue = Path(config["url"][len("local://"):])
                deadline = time.monotonic()+5
                while not (queue/"heartbeat.json").exists() and time.monotonic()<deadline:
                    time.sleep(.02)
                self.assertTrue((queue/"heartbeat.json").is_file())
                owner = json.loads((queue/"owner.json").read_text())
                owner["heartbeat"] = 0
                write_json(queue/"owner.json", owner)
                self.assertEqual(client.state()["tick"], 0)
                with patch("os.kill", side_effect=ProcessLookupError("worker in another PID namespace")):
                    self.assertEqual(client.state()["tick"], 0)
                manifest = json.loads((package/"feedback/initial/manifest.json").read_text())
                self.assertEqual(set(manifest["frames"][0]["cameras"]), {"front", "top"})
                self.assertEqual(len(list((package/"feedback/initial").rglob("*.png"))), 2)

                def cli(*args):
                    result = subprocess.run([sys.executable, "bridge_client.py", *args], cwd=package,
                                            check=True, capture_output=True, text=True, timeout=10)
                    return json.loads(result.stdout)

                observation = cli("observe")
                self.assertEqual(len(observation["images"]), 2)
                (package/"action.py").write_text('env.step({"dx": 1})')
                first = cli("submit", "action.py", "--expected-segment", "1", "--request-id", "a")
                self.assertEqual(cli("retry", "--request-id", "a"), first)
                self.assertEqual(client.state()["tick"], 1)
                cli("submit", "action.py", "--expected-segment", "2", "--request-id", "b")
                self.assertEqual(client.state()["observation"]["x"], 2)
                with self.assertRaisesRegex(ValueError, "Stale"):
                    client.submit('env.step({"dx": 1})', request_id="stale", expected_segment=1)
                with self.assertRaises(ValueError):
                    client.request("/artifacts/session.json", raw=True)
                self.assertEqual(client.state()["tick"], 2)
                client.submit('env.step({"dx": 1})', request_id="c", expected_segment=3)
                self.assertEqual(client.state()["state"], "succeeded")
            finally:
                client.request("/v1/shutdown", dict(reason="test complete"))
            with self.assertRaises(ValueError):
                client.state()
            rerun = subprocess.run(launch, cwd=ROOT, capture_output=True, timeout=10)
            self.assertNotEqual(rerun.returncode, 0)


if __name__ == "__main__":
    unittest.main()
