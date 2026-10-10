"""Fake `rcb_<bench>.py replay`: behaviour per replay number from FAKE_<n> (ok|fail|die|hang|ok_crash|garbage|sha2|inst)."""
import json, os, re, sys, time
a = sys.argv[1:]; out = a[a.index("--out") + 1]; n = re.search(r"replay(\d)\.json", out).group(1)
mode = os.environ.get(f"FAKE_{n}", "ok")
if mode == "die": sys.exit(139)
if mode == "hang": time.sleep(600)
if mode == "garbage": open(out, "w").write('{"success": tr'); sys.exit(0)
r = {"success": mode != "fail", "score": 1.0 if mode != "fail" else 0.2, "state_sha": "bbb" if mode == "sha2" else "aaa",
     "instance_ok": mode != "inst", "start_exact": True}
if "--video" in a:
    open(a[a.index("--video") + 1], "wb").write(b"mp4"); r["video"] = True
json.dump(r, open(out, "w"))
sys.exit(139 if mode == "ok_crash" else 0)
