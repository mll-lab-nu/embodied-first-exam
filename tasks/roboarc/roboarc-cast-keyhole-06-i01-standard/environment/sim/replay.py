"""Video-only pass of a TopoGym standard-mode episode, run by environment/sim/finalize.sh after the service exited and
after final.json holds the live episode's verdict (owner 2026-10-17: no grading replay).

    python /srv/replay.py --data /data --task <family> --instance /srv/instance.json --video /data/replay.mp4

Builds the frozen instance in this new process, replays the rows the live episode executed (episode.json `live_rows`;
rows recorded after the live end were never commanded live) once, plainly (the instance's own thresholds, no grading
hold), and renders the human-viewable video during that replay. Nothing it computes is a verdict: it records no success
and compares no state with the live one. After a live success with live review events (deep task contacts,
rcb_topogym.CONTACT_RULE: the success is held for human review), it renders frames around those events and the live
forcing events into <data>/review_frames/ (`review_frames`), evidence for the reviewer. Writes <data>/replay.video.json
(the video's record) as it goes and prints it as one JSON line at the end."""
from __future__ import annotations
import argparse, json, os, sys, time, traceback


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=os.environ.get("RCB_DATA", "/data")); ap.add_argument("--task", required=True)
    ap.add_argument("--instance", required=True); ap.add_argument("--video", required=True); ap.add_argument("--fps", type=int, default=15)
    a = ap.parse_args()
    os.environ["RCB_SESSION_LOG"] = ""              # as the sim service: no agent-side interaction log
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))     # the task's own tooling copy (environment/sim/)
    import rcb_topogym as M
    rec = os.path.join(a.data, "replay.video.json")
    dump = json.load(open(os.path.join(a.data, "episode.json")))
    inst = json.load(open(a.instance))
    acts, ticks = M.load_trajectory(os.path.join(a.data, "trajectory.npz"), a.task, int(inst["action_dim"]), trusted=True, layout=inst["action_layout"])
    n_live = dump.get("live_rows")
    live = acts if n_live is None else acts[:int(n_live)]
    if ticks is not None:
        ticks = ticks[:len(live)]
    try:
        s = M.Session(a.task, instance=a.instance, strict=True)
    except M.InstanceMismatch as exc:   # this host cannot rebuild the instance: no video, the verdict stands
        M.atomic_json(rec, {"video": False, "media_status": "error", "video_error": f"instance_mismatch: {exc}"[:300]})
        return 2
    t0 = time.time(); video_error = None
    out = {"video": False, "media_status": "pending", "live_rows": int(len(live)), "n_actions": int(len(acts))}
    try:
        M.atomic_json(rec, out)
        s.start_video(a.video, fps=a.fps)
        s.replay(live, physics_steps=ticks, grading=False)
        try:
            s.stop_video()
            out["video"] = os.path.isfile(a.video)
        except Exception as exc:
            traceback.print_exc(); video_error = repr(exc)[:300]
        out.update(media_status="error" if video_error else "complete", video_error=video_error, wall_s=round(time.time() - t0, 1))
        M.atomic_json(rec, out)
        review = dump.get("review")
        if dump.get("success") and review:   # a live success held for review: frames around its live events and forcing events
            try:
                forcing = (dump.get("forcing") or {}).get("events") or []
                files = s.render_review_frames(live, review["events"] + forcing, os.path.join(a.data, "review_frames"),
                                               physics_steps=ticks)
                out["review_frames"] = [os.path.relpath(f, a.data) for f in files]
            except Exception as exc:
                traceback.print_exc(); out["review_frames_error"] = repr(exc)[:300]
            M.atomic_json(rec, out)
    except Exception as exc:                 # a video failure loses the video only
        traceback.print_exc()
        out.update(media_status="error", video_error=repr(exc)[:300], wall_s=round(time.time() - t0, 1))
        M.atomic_json(rec, out)
    finally:
        s.close()
    print(json.dumps(out), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
