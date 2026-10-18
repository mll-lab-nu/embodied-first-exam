"""Meaningful whole-video sampling, worker timeout and client transport regressions."""

import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from scripts.control_transfer.specs import spec
from scripts.control_transfer.trusted.runtime_limits import runtime_limits
from scripts.control_transfer.trusted.adapter import feedback
from scripts.control_transfer.trusted.session import Session
from scripts.control_transfer.control_public.client import Client


class LapRuntime(unittest.TestCase):
    @unittest.skip("full-lap tasks are not shipped (their cutoff exceeds 14400 s); the 128-frame select fails on ffmpeg 7")
    def test_sample_spans_video_and_retains_every_noisy_row(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            subprocess.run(
                [
                    "ffmpeg",
                    "-v",
                    "error",
                    "-f",
                    "lavfi",
                    "-i",
                    "testsrc=size=32x24:rate=10",
                    "-frames:v",
                    "1001",
                    "-c:v",
                    "libx264",
                    "-threads",
                    "1",
                    "-pix_fmt",
                    "yuv420p",
                    str(root / "video.mp4"),
                ],
                check=True,
                timeout=30,
            )
            rows = [dict(t=i / 10, values=[0.0] * 18) for i in range(1001)]
            record = dict(feedback=dict(telemetry=rows), metrics=dict(private_metric=123), dynamics=dict(secret=42))
            limits = runtime_limits(spec("anycar-circuit-lap-v2-silverstone-8", 0))
            delivered = feedback("anycar", record, root, sampling=limits)
            self.assertEqual(set(delivered), {"telemetry", "images"})
            self.assertEqual(delivered["telemetry"], rows)
            self.assertEqual(len(delivered["images"]), 128)
            times = [im["time_s"] for im in delivered["images"]]
            self.assertEqual(times[0], 0)
            self.assertEqual(times[-1], 100)
            self.assertEqual(times, sorted(set(times)))
            legacy = feedback("anycar", record, root)
            self.assertEqual(len(legacy["images"]), 48)
            self.assertEqual(legacy["images"][-1]["time_s"], 47)

    def test_episode_uses_operator_render_and_replay_deadlines(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            s = spec("anycar-circuit-lap-v2-monaco-6", 0)
            session = Session(root / "session", s)
            policy = root / "policy"
            policy.write_text("{}")
            observed = []

            class Worker:   # stands in for the episode worker process (session.episode uses Popen: killable at the cutoff)
                def __init__(self, cmd, **kwargs):
                    request = json.loads(Path(cmd[-1]).read_text())
                    out = Path(request["out"])
                    out.mkdir()
                    (out / "record.json").write_text("{}")

                def wait(self, timeout=None):
                    observed.append(timeout)
                    return 0

            with patch("scripts.control_transfer.trusted.session.subprocess.Popen", Worker):
                for render in (True, False):
                    session.episode(policy, s["bank"]["adaptation"][0], root / str(render), render)
            self.assertEqual(observed, [session.limits["worker_seconds"], session.limits["replay_seconds"]])
            self.assertIn(
                "error",
                session.call("deploy", dict(policy=s["public"]["default_policy"], diagnosis="", worker_seconds=999999)),
            )
            self.assertEqual(session.state["rounds"], [])

    def test_client_timeout_tracks_public_environment(self):
        with tempfile.TemporaryDirectory() as td:
            for env, want in [({}, 1800), ({"CONTROL_DEPLOY_TIMEOUT_S": "6000"}, 6000)]:
                with (
                    patch.dict(os.environ, env, clear=True),
                    patch("urllib.request.urlopen", return_value=io.BytesIO(b"{}")) as request,
                ):
                    Client(out=td).describe()
                    self.assertEqual(request.call_args.kwargs["timeout"], want)


if __name__ == "__main__":
    unittest.main()
