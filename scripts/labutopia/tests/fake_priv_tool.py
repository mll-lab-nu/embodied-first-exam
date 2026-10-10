"""Fake `rcb_<bench>.py replay` for the privileged graders: behaviour from FAKE_MODE (ok|fail|die|hang|inst|sha|ok_crash),
`sha`: a different final state in each process (the pid)."""
import json, os, sys, time
a = sys.argv[1:]; out = a[a.index("--out") + 1]; mode = os.environ.get("FAKE_MODE", "ok")
video = "--video" in a
if video and os.environ.get("FAKE_VIDEO") == "hang": time.sleep(600)
if video and os.environ.get("FAKE_VIDEO") == "die": sys.exit(139)
if mode == "die": sys.exit(139)
if mode == "hang": time.sleep(600)
import numpy as np
d = np.load(a[a.index("--traj") + 1], allow_pickle=False); assert set(d.files) == {"actions", "task"}, d.files
r = {"success": mode != "fail", "score": 1.0 if mode != "fail" else 0.3, "state_sha": str(os.getpid()) if mode == "sha" else "aaa",
     "instance_ok": mode != "inst", "start_exact": True, "steps": int(len(d["actions"])), "reason": "success"}
if video:
    open(a[a.index("--video") + 1], "wb").write(b"mp4"); r["video"] = True
json.dump(r, open(out, "w"))
sys.exit(139 if mode == "ok_crash" else 0)
