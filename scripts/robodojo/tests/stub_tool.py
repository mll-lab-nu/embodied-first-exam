"""Stand-in for `rcb_robodojo.py` in the grading tests (test_standard_grading.py: the collect hook's replay CLI;
test_privileged_grading.py: copied next to the grader as rcb_robodojo.py, which the grader imports and runs).
STUB_PLAN = comma list, one entry per invocation (counted in $STUB_DIR/stub_calls, default $RCB_DATA; the argument list of
every invocation is appended to stub_argv): ok | fail | diff | die | error | inexact | inexact_fail | inst2 | novideo | partvideo | ok_crash | slow | die_slow | sleep."""
import json, os, sys
ACTION_DIM, MAX_ACTIONS = 14, 15000    # what the privileged grader imports


def main() -> None:
    d = os.environ.get("STUB_DIR") or os.environ["RCB_DATA"]; cf = os.path.join(d, "stub_calls")
    n = int(open(cf).read()) if os.path.exists(cf) else 0
    open(cf, "w").write(str(n + 1))
    open(os.path.join(d, "stub_argv"), "a").write(json.dumps(sys.argv[1:]) + "\n")
    plan = os.environ.get("STUB_PLAN", "ok").split(","); what = plan[min(n, len(plan) - 1)]
    video = sys.argv[sys.argv.index("--video") + 1] if "--video" in sys.argv else None
    print("[rcb_robodojo] simulator chatter on stdout"); print("{not json")

    def result(success=True, sha="aa", exact=True, instance_sha="ii", film=True):
        if video and film: open(video, "w").write("mp4")
        print("\n" + json.dumps({"n_actions": 5, "instance_sha": instance_sha, "instance_exact": exact, "instance_matches": exact,
                                 "replays": [{"success": success, "state_sha": sha, "sim_steps": 5,
                                              "end_reason": "success" if success else "failed_check"}], "video": video,
                                 "video_ok": (bool(film) if video else None)}), flush=True)
    if what == "ok": result()
    elif what == "fail": result(success=False, sha="zz")              # the end state of a failed episode
    elif what == "diff": result(sha=f"s{n}")                          # succeeds, in another end state
    elif what == "inexact": result(exact=False, instance_sha="other")           # the layout rebuilt to another state
    elif what == "inexact_fail": result(success=False, sha="zz", exact=False, instance_sha="other")
    elif what == "inst2": result(instance_sha=f"i{n}")                # exact by its own account, another start state
    elif what == "novideo": result(film=False)                        # the replay stands, the video could not be written
    elif what == "partvideo":                                         # ... and a part of it was left behind
        if video: open(video, "w").write("part")
        result(film=False)
    elif what == "ok_crash": result(); sys.stdout.flush(); os._exit(139)   # the result line, then a crash at Isaac's shutdown
    elif what == "slow":                                              # a result after 10 s
        import time
        time.sleep(10); result()
    elif what == "sleep":                                             # never returns in the test's time (a hung Isaac)
        import time
        time.sleep(600)
    elif what == "die": sys.stderr.write("Segmentation fault (stub)\n"); os._exit(139)
    elif what == "die_slow":                                          # dies after 5 s
        import time
        time.sleep(5); sys.stderr.write("Segmentation fault (stub)\n"); os._exit(139)
    elif what == "error": print(json.dumps({"error": "trajectory task x != y"})); sys.exit(2)


if __name__ == "__main__":
    main()
