"""Stand-in for `rcb_<sim>.py replay` in the finalize.sh test. STUB_PLAN = comma list, one entry per invocation (kept in
$RCB_DATA/stub_calls): ok | fail | diff | die | crash_after | sleep | error | noise."""
import json, os, sys, time
d = os.environ["RCB_DATA"]; cf = os.path.join(d, "stub_calls")
n = int(open(cf).read()) if os.path.exists(cf) else 0
open(cf, "w").write(str(n + 1))
plan = os.environ.get("STUB_PLAN", "ok").split(","); what = plan[min(n, len(plan) - 1)]
video = sys.argv[sys.argv.index("--video") + 1] if "--video" in sys.argv else None
assert os.path.exists(sys.argv[sys.argv.index("--traj") + 1]) or what == "die", "no trajectory"
print("some simulator chatter on stdout"); print("{not json at all")
def result(success=True, sha="aa", video_ok=True):
    if video and video_ok: open(video, "w").write("mp4")
    print(json.dumps({"n_actions": 5, "instance_matches": True, "replays": [{"success": success, "state_sha": sha, "sim_steps": 5}],
                      "video": video, "video_ok": (video_ok if video else None)}), flush=True)
if what == "ok": result()
elif what == "fail": result(success=False)
elif what == "diff": result(sha="bb")
elif what == "novideo": result(video_ok=False)
elif what == "kill9": import signal; os.kill(os.getpid(), signal.SIGKILL)
elif what == "die": sys.stderr.write("Segmentation fault (stub)\n"); os._exit(139)
elif what == "crash_after": result(); os._exit(139)          # Isaac crashing at shutdown, after the result line
elif what == "sleep": time.sleep(600)
elif what == "error": print(json.dumps({"error": "trajectory task x != y"})); sys.exit(2)
