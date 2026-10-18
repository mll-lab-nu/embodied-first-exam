"""Real local HTTP process check; no container-isolation claim."""

import json, os, signal, socket, subprocess, sys, tempfile, time, unittest, urllib.request, urllib.error
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from scripts.control_transfer.specs import spec
from scripts.control_transfer.control_public.client import Client


class HttpTests(unittest.TestCase):
    def test_routes_and_trusted_shutdown(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            instance = td / "instance.json"
            instance.write_text(json.dumps(spec("spacecraft", 0)))
            sock = socket.socket()
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
            sock.close()
            env = {
                **os.environ,
                "PYTHONPATH": str(ROOT),
                "RCB_DATA": str(td / "data"),
                "RCB_INSTANCE": str(instance),
                "RCB_PORT": str(port),
                "RCB_WALL_CLOCK_S": "60",
            }
            with (td / "server.log").open("w") as log:
                p = subprocess.Popen(
                    [sys.executable, "-m", "scripts.control_transfer.trusted.service"], env=env, stdout=log, stderr=log
                )
                try:
                    for _ in range(100):
                        try:
                            with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=1) as r:
                                self.assertTrue(json.load(r)["ready"])
                            break
                        except OSError:
                            time.sleep(0.05)
                    else:
                        self.fail((td / "server.log").read_text())
                    state = lambda: json.loads((td / "data/state.json").read_text())
                    self.assertIsNone(state()["deadline"])
                    # A real private artifact must remain unreachable, not merely an absent path.
                    (td / "data/wind.npz").write_bytes(b"private wind canary")
                    for path in ["/instance.json", "/data/final.json", "/weights", "/wind.npz", "/data/wind.npz", "/../instance.json"]:
                        with self.assertRaises(urllib.error.HTTPError) as err:
                            urllib.request.urlopen(f"http://127.0.0.1:{port}" + path)
                        self.assertEqual(err.exception.code, 404)
                    req = urllib.request.Request(
                        f"http://127.0.0.1:{port}/describe", data=b"{}", headers={"Content-Type": "application/json"}
                    )
                    with urllib.request.urlopen(req) as response:
                        result = json.load(response)
                    self.assertNotIn("bank", result)
                    self.assertNotIn("private_asset", result)
                    self.assertIn("channels", result)
                    for body in [b'{"policy":NaN}', b'{"a":1,"a":2}', b"[]"]:
                        req = urllib.request.Request(f"http://127.0.0.1:{port}/deploy", data=body)
                        with self.assertRaises(urllib.error.HTTPError) as err:
                            urllib.request.urlopen(req)
                        self.assertEqual(err.exception.code, 400)
                    client = Client(f"http://127.0.0.1:{port}", td / "client-trace")
                    with self.assertRaises(urllib.error.HTTPError):
                        client.call("private", {})
                    self.assertEqual((td / "client-trace/000-private.request.json").read_bytes(), b"{}")
                    self.assertEqual(   # every non-protocol path is 404 (PROTOCOL H.3), POST too
                        json.loads((td / "client-trace/000-private.error.json").read_text())["http_status"], 404
                    )
                    self.assertEqual(
                        json.loads((td / "client-trace/000-private.response.json").read_bytes()),
                        {"error": "Unknown route"},
                    )
                    client.describe()
                    self.assertTrue((td / "client-trace/001-describe.response.json").exists())
                    p.send_signal(signal.SIGUSR1)
                    for _ in range(100):
                        if (td / "data/final.json").exists():
                            break
                        time.sleep(0.05)
                    final = json.loads((td / "data/final.json").read_text())
                    self.assertTrue(final["no_submission"])
                    self.assertFalse(final["infra_error"])
                finally:
                    p.terminate()
                    p.wait(timeout=10)


if __name__ == "__main__":
    unittest.main()
