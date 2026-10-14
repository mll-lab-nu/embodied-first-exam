"""A stand-in for rcb_pandadyn.py in the grader tests (copied next to the grader under that name): the grader imports
MAX_ROWS from it and runs its `replay` CLI in a fresh process per replay. What each replay process does is the next entry
of STUB_PLAN (comma-separated, one per process, the counter in STUB_STATE):
  ok / fail      the replay succeeds / fails, ending in state "A"
  diff           succeeds, ending in state "B"
  mismatch       succeeds, but the rebuilt start differs from the instance's record (instance_matches false)
  die            exits 1 without a result        error   prints a result line without `replays`
  sleep          sleeps past any limit           novideo succeeds; a --video call writes no video"""
import json, os, sys, time

MAX_ROWS = 4500


def main() -> int:
    if len(sys.argv) < 2 or sys.argv[1] != "replay":
        return 2
    state = os.environ["STUB_STATE"]
    n = int(open(state).read()) if os.path.exists(state) else 0
    open(state, "w").write(str(n + 1))
    plan = os.environ.get("STUB_PLAN", "ok").split(",")
    video = sys.argv[sys.argv.index("--video") + 1] if "--video" in sys.argv else None
    if video:                                  # the filmed replay after the verdict: it never changes it
        if "novideo" not in plan:
            open(video, "wb").write(b"\x00" * 64)
        print(json.dumps({"replays": [{"success": True, "state_sha": "A"}], "instance_matches": True, "video_ok": True}))
        return 0
    what = plan[min(n, len(plan) - 1)]
    if what == "die":
        return 1
    if what == "sleep":
        time.sleep(30); return 0
    if what == "error":
        print(json.dumps({"error": "bad trajectory: stub"})); return 2
    rep = {"success": what in ("ok", "diff", "mismatch", "novideo"), "state_sha": "B" if what == "diff" else "A", "end_reason": "success",
           "control_steps": 5, "executed_rows": 5, "phase": 5, "phase_name": "complete", "sim_time_s": 0.05, "valid": True}
    print("Warning: noise a simulator prints")
    print(json.dumps({"task": "S00-Stub", "instance_matches": what != "mismatch", "initial_sha": "I", "replays": [rep]}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
