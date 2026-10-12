"""Stand-in for `rcb_robodojo.py replay` in test_standard_grading.py. STUB_PLAN = comma list, one entry per invocation
(counted in $RCB_DATA/stub_calls): ok | fail | diff | die | error."""
import json, os, sys
d = os.environ["RCB_DATA"]; cf = os.path.join(d, "stub_calls")
n = int(open(cf).read()) if os.path.exists(cf) else 0
open(cf, "w").write(str(n + 1))
plan = os.environ.get("STUB_PLAN", "ok").split(","); what = plan[min(n, len(plan) - 1)]
video = sys.argv[sys.argv.index("--video") + 1] if "--video" in sys.argv else None
print("[rcb_robodojo] simulator chatter on stdout"); print("{not json")
def result(success=True, sha="aa"):
    if video: open(video, "w").write("mp4")
    print("\n" + json.dumps({"n_actions": 5, "instance_sha": "ii", "instance_exact": True, "instance_matches": True,
                             "replays": [{"success": success, "state_sha": sha, "sim_steps": 5}], "video": video,
                             "video_ok": True if video else None}), flush=True)
if what == "ok": result()
elif what == "fail": result(success=False)
elif what == "diff": result(sha=f"s{n}")
elif what == "die": sys.stderr.write("Segmentation fault (stub)\n"); os._exit(139)
elif what == "error": print(json.dumps({"error": "trajectory task x != y"})); sys.exit(2)
