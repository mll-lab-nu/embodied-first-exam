"""Stand-in for the tooling module next to tests/grade.py (copied as rcb_robolab.py / rcb_yamlab.py): the constants the
grader imports, and a `replay` CLI steered by STUB_PLAN (one entry per invocation, counted in $STUB_DIR/calls). The real
_load_traj is exercised separately (test_tooling_units.py)."""
import json, os, sys, time
MAX_STEPS = 100_000
ACTION_DIM = int(os.environ.get("STUB_DIM", "8"))
if __name__ == "__main__":
    d = os.environ["STUB_DIR"]; cf = os.path.join(d, "calls")
    n = int(open(cf).read()) if os.path.exists(cf) else 0
    open(cf, "w").write(str(n + 1))
    plan = os.environ.get("STUB_PLAN", "ok").split(","); what = plan[min(n, len(plan) - 1)]
    video = sys.argv[sys.argv.index("--video") + 1] if "--video" in sys.argv else None
    print("isaac chatter"); print("{broken")
    def result(success=True, sha="aa", inst=True):
        if video: os.makedirs(os.path.dirname(video), exist_ok=True); open(video, "w").write("mp4")
        print(json.dumps({"instance_matches": inst, "instance_exact": inst, "replays": [{"success": success, "state_sha": sha, "sim_steps": 7, "progress": 1.0}]}), flush=True)
    if what == "ok": result()
    elif what == "fail": result(success=False)
    elif what == "diff": result(sha="bb")
    elif what == "inst": result(inst=False)
    elif what == "die": os._exit(139)
    elif what == "crash_after": result(); os._exit(139)
    elif what == "sleep": time.sleep(120)
