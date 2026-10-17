"""iSpatialGym's standard grading without a simulator (numpy only): the verifier's grade.py on synthetic final.json, the
collect hook finalize.sh on a stub service end (it writes final.json from the live episode and replays nothing), and the
live video recorder on a stub encoder. The standard mode is graded by the live episode (owner 2026-10-17, board 0151).
    python3 scripts/ispatialgym/tests/test_grading.py"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parents[1]
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE / "shared"))
import grade as G  # noqa: E402
import rcb_ispatialgym as RI  # noqa: E402

LIVE = {"success": True, "live_success": True, "finalized": True, "graded_by": "live", "replays": 0, "reason": "success",
        "n_actions": 900, "control_steps": 900, "max_steps": 2000, "video": True, "video_source": "live", "sim_startups": 1}


def g(**kw):
    ok, out = G.grade({**LIVE, **kw})
    assert all(isinstance(v, (int, float)) for v in out.values()), out          # reward.json: numbers only
    assert "replay_success" not in out and "deterministic" not in out, out
    return ok, out


def test_grade() -> None:
    ok, out = g()
    assert ok and out["success"] == 1 and out["live_success"] == 1 and out["graded_by_live"] == 1 and out["replays"] == 0
    assert out["infra_error"] == 0 and out["video_live"] == 1
    ok, out = g(success=False, live_success=False, reason="failed: the episode's control steps ran out")
    assert not ok and out["infra_error"] == 0                                 # live failure (incl. a settle that never held)
    ok, out = g(success=False, live_success=False, reason="timeout")
    assert not ok and out["infra_error"] == 0
    ok, out = g(video=False)                                                  # a failed video never changes the verdict
    assert ok and out["video_rendered"] == 0
    ok, out = g(success=False, live_success=False, reason="error")            # a sim error the agent's actions raised: 0
    assert not ok and out["infra_error"] == 0 and out["sim_error"] == 1
    give = {"success": False, "done": True, "finalized": True, "gave_up": True}
    ok, out = G.grade({**give, "reason": "sim_crashed_on_call"})                  # every crash inside the agent's calls
    assert not ok and out["infra_error"] == 0 and out["sim_crashed_on_call"] == 1
    for r in ("sim_crashed", "resume_failed: journal shorter than the log"):       # crashes between calls: no verdict
        ok, out = G.grade({**give, "reason": r, "infra_error": 1})
        assert not ok and out["infra_error"] == 1, r
    ok, out = G.grade({**give, "reason": "instance_mismatch: the frozen start state did not rebuild here", "infra_error": 1})
    assert not ok and out["infra_error"] == 1 and out["instance_ok"] == 0
    ok, out = g(finalized=False)
    assert not ok and out["infra_error"] == 1
    ok, out = g(success=True, gave_up=True)                                       # a give-up never scores
    assert not ok


def test_grade_main() -> None:
    with tempfile.TemporaryDirectory() as td:
        data, log = Path(td) / "out", Path(td) / "log"; data.mkdir()
        env = {**os.environ, "RCB_DATA": str(data), "RCB_VERIFIER_LOG_DIR": str(log)}
        run = lambda: subprocess.run([sys.executable, str(HERE / "shared/grade.py")], env=env, capture_output=True, text=True, check=True)  # noqa: E731
        run()                                                                     # no final.json: infra, missing_log
        r = json.loads((log / "reward.json").read_text())
        assert r["infra_error"] == 1 and r["missing_log"] == 1 and r["success"] == 0 and (log / "reward.txt").read_text() == "0\n"
        (data / "final.json").write_text("{not json")
        run(); r = json.loads((log / "reward.json").read_text())
        assert r["infra_error"] == 1 and r["grader_error"] == 1
        (data / "final.json").write_text(json.dumps(LIVE)); (data / "live.mp4").write_bytes(b"x")
        run(); r = json.loads((log / "reward.json").read_text())
        assert r["success"] == 1 and (log / "reward.txt").read_text() == "1\n" and (log / "live.mp4").exists()


STUB = """import importlib.util, os, sys
sys.path.append({std!r})            # rcb1, beside the real rcb_limited
_spec = importlib.util.spec_from_file_location("_real_rcb_limited", os.path.join({std!r}, "rcb_limited.py"))
_real = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(_real)
final_verdict, _read_json, _write_json = _real.final_verdict, _real._read_json, _real._write_json   # the real helpers
if __name__ == "__main__":
    open(os.path.join(os.environ["RCB_DATA"], "end_called"), "w").write(" ".join(sys.argv[1:]))
    sys.exit(int(os.environ["STUB_END_RC"]))
"""


def finalize(rc: int, episode: dict | None, final: dict | None = None, video: bytes | None = None, render: bytes | None = None,
             budget: int = 4200) -> tuple[dict, list]:
    td = Path(tempfile.mkdtemp())
    data, srv, bindir = td / "out", td / "srv", td / "bin"
    for p in (data, srv, bindir):
        p.mkdir()
    (srv / "rcb_limited.py").write_text(STUB.format(std=str(ROOT / "scripts/eai_standard")))
    tool = srv / "tool.py"        # the replay CLI: logs its arguments; with --video writes `render` there (if given)
    (td / "render.bin").write_bytes(render or b"")
    tool.write_text("import sys\n"
                    f"open({str(td / 'REPLAYED')!r}, 'a').write(' '.join(sys.argv[1:]) + '\\n')\n"
                    "if '--video' in sys.argv and " + repr(render is not None) + ":\n"
                    f"    open(sys.argv[sys.argv.index('--video') + 1], 'wb').write(open({str(td / 'render.bin')!r}, 'rb').read())\n")
    py = bindir / "python"                         # `python` in finalize.sh: this interpreter (a wrapper, not a symlink:
    py.write_text(f"#!/bin/sh\nexec {sys.executable} \"$@\"\n"); py.chmod(0o755)   # a venv's python resolves by its path)
    if episode is not None:
        (data / "episode.json").write_text(json.dumps(episode))
        np.savez(data / "trajectory.npz", actions=np.zeros((3, 23), np.float32))
    if final is not None:
        (data / "final.json").write_text(json.dumps(final))
    if video is not None:
        (data / "live.mp4").write_bytes(video)
    env = {**os.environ, "RCB_DATA": str(data), "RCB_SRV": str(srv), "STUB_END_RC": str(rc), "RCB_TOOL": str(tool),
           "RCB_INSTANCE": str(srv), "RCB_COLLECT_BUDGET_S": str(budget), "PATH": f"{bindir}:{os.environ['PATH']}"}
    r = subprocess.run(["sh", str(HERE / "shared/finalize.sh")], env=env, capture_output=True, text=True, timeout=600)
    assert r.returncode == 0, r.stderr
    calls = (td / "REPLAYED").read_text().splitlines() if (td / "REPLAYED").exists() else []
    assert len(calls) <= 1 and all("--video" in c for c in calls), calls      # never a grading replay; one video-only render at most
    assert (data / "end_called").read_text().split()[-1] == "3600"
    fin = json.loads((data / "final.json").read_text())
    assert "replay_success" not in fin and "deterministic" not in fin, fin
    shutil.rmtree(td)
    return fin, calls


def tiny_mp4() -> bytes | None:
    if not shutil.which("ffmpeg"):
        return None
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "v.mp4"
        v = RI._Video(str(p), size=64, fps=10)
        for i in range(5):
            v.add(np.full((128, 128, 3), 40 * i, np.uint8))
        v.close()
        return p.read_bytes() if v.error is None and p.exists() else None


def test_finalize() -> None:
    ep = {"success": True, "reason": "success", "live_sha": "abc", "n_actions": 10, "control_steps": 10, "graded_by": "live", "replays": 0}
    mp4 = tiny_mp4()
    fin, calls = finalize(0, ep, video=mp4)
    assert fin["success"] is True and fin["live_success"] is True and fin["finalized"] and fin["graded_by"] == "live"
    assert fin["replays"] == 0 and fin["state_sha"] == "abc" and fin["video_pending"] is False and not fin.get("infra_error")
    if mp4 is not None:                                                 # a playable live video: no render at all
        assert fin["video"] is True and fin["video_source"] == "live" and calls == [], (fin, calls)
    ok, _ = G.grade(fin); assert ok
    for v in (None, b"not an mp4"):                                     # no playable live video: one render, the verdict stands
        fin, calls = finalize(0, ep, video=v, render=mp4)
        assert len(calls) == 1 and fin["success"] is True and fin["video_pending"] is False and G.grade(fin)[0], (fin, calls)
        assert fin["video"] is (mp4 is not None) and fin["video_source"] == ("render" if mp4 else None)
        fin, calls = finalize(0, ep, video=v)                           # ... and the render fails too: only the video is lost
        assert fin["success"] is True and fin["video"] is False and not fin.get("infra_error") and G.grade(fin)[0]
    fin, calls = finalize(0, ep, video=None, render=mp4, budget=300)    # no time left for a render: skipped, verdict stands
    assert calls == [] and fin["video"] is False and fin["video_pending"] is False and G.grade(fin)[0]
    fin, _ = finalize(0, {**ep, "success": False, "reason": "failed: the episode's control steps ran out"}, video=mp4, render=mp4)
    assert fin["success"] is False and not fin.get("infra_error") and not G.grade(fin)[0]
    give = {"success": False, "finalized": True, "gave_up": True, "reason": "sim_crashed", "infra_error": 1}
    fin, _ = finalize(2, None, final=give)                              # a give-up on disk is kept as it is
    assert fin == give
    fin, _ = finalize(1, None, final={"success": True, "finalized": False})   # the service never ended the episode
    assert fin["infra_error"] == 1 and fin["success"] is False and G.grade(fin)[1]["infra_error"] == 1
    fin, calls = finalize(1, ep, video=None, render=mp4)               # dumped, then did not exit in time: still the live verdict
    assert fin["success"] is True and not fin.get("infra_error") and fin["end_timed_out"] is True and calls == [], (fin, calls)
    assert fin["video_pending"] is False and G.grade(fin)[0]
    fin, _ = finalize(0, None)                                          # no episode.json: infra
    assert fin["infra_error"] == 1 and G.grade(fin)[1]["infra_error"] == 1


class StubVideo:
    def __init__(self, fail_at: int | None = None):
        self.p, self.error, self.n, self.fail_at, self.closed = object(), None, 0, fail_at, False

    def _fail(self, where, exc):
        self.error = f"{where}: {exc!r}"; self.p = None

    def add(self, frame):
        if self.p is None:
            return
        if self.fail_at is not None and self.n == self.fail_at:
            return self._fail("frame", RuntimeError("encoder died"))
        assert frame.shape == (4, 4, 3); self.n += 1

    def close(self, wait_s=900.0):
        self.closed = True


def test_live_video() -> None:
    v = StubVideo(); lv = RI.LiveVideo("unused", video=v)
    for n in range(0, 31):
        lv.offer(n, lambda: np.zeros((4, 4, 3), np.uint8))
    info = lv.close(timeout=30)
    assert v.closed and info["video_frames"] == 11 and info["video_dropped_frames"] == 0 and "video_error" not in info
    v = StubVideo(fail_at=2); lv = RI.LiveVideo("unused", video=v)               # the encoder dies: no exception, an error
    for n in range(0, 31):
        lv.offer(n, lambda: np.zeros((4, 4, 3), np.uint8))
    info = lv.close(timeout=30)
    assert info["video_frames"] == 2 and "video_error" in info
    v = StubVideo(); lv = RI.LiveVideo("unused", video=v)

    def boom():
        raise RuntimeError("no frame")
    lv.offer(0, boom); lv.offer(3, lambda: np.zeros((4, 4, 3), np.uint8))     # a frame that cannot be read is skipped, counted
    info = lv.close(timeout=30)
    assert info["video_frames"] == 1 and info["video_bad_frames"] == 1 and "video_frame_error" in info and "video_error" not in info, info
    import inspect                                                    # close() is bounded well inside the hook's 3600 s wait
    sig = inspect.signature(RI.LiveVideo.close).parameters
    assert 2 * sig["timeout"].default + sig["encoder_wait_s"].default <= 300


def test_service_texts() -> None:
    s = (HERE / "shared/server.py").read_text()
    assert "instance_mismatch" in s and "LiveVideo" in s and "fresh-process replays\"" not in s
    t = (HERE / "templates/task.toml").read_text()
    assert "replay1.log" not in t and "/out/live.mp4" in t and "kill -9 -1" in t


if __name__ == "__main__":
    test_grade(); test_grade_main(); test_finalize(); test_live_video(); test_service_texts()
    print("ok: iSpatialGym standard grading is the live episode's; finalize.sh replays nothing; the video never decides")
