"""Fresh-process replay of a TopoGym standard-mode episode, run by environment/sim/finalize.sh after the service exited.

    python /srv/replay.py --data /data --task <family> --instance /srv/instance.json [--video /data/replay.mp4]

Builds the frozen instance in this new process, replays the rows the live episode executed (episode.json `live_rows`; rows
recorded after the live end were never commanded live) once, and renders the human-viewable video DURING that replay: the
grading needs two passes, the live episode and this replay, not a third pass for the video. After a live success it is a
grading replay (Session.replay(grading=True), tooling v16): for the GPU families the rows run with the instance's own
thresholds and, if the episode has not ended after the last row, the final targets are held for up to 2 s with the replay
tolerances (rcb_topogym.REPLAY_TOLERANCES); replays[0]["grading"] records it. After a live failure the replay is plain
(the instance's thresholds, no hold): a live failure is final, and a tolerant replay must never look like a success.
The verdict is committed before video finalization; a finalization failure does not rerun physics. After a live success
whose live episode or replay had a review event (a deep task contact, rcb_topogym.CONTACT_RULE: the success is held for
review), one more pass renders frames around the events and the forcing events into <data>/review_frames/
(`review_frames`). Prints one JSON line (replays[0] = Session.status())."""
from __future__ import annotations
import argparse, json, os, sys, time, traceback

import numpy as np


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=os.environ.get("RCB_DATA", "/data")); ap.add_argument("--task", required=True)
    ap.add_argument("--instance", required=True); ap.add_argument("--video", default=""); ap.add_argument("--fps", type=int, default=15)
    a = ap.parse_args()
    os.environ["RCB_SESSION_LOG"] = ""              # as the sim service: no agent-side interaction log
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))     # the task's own tooling copy (environment/sim/)
    import rcb_topogym as M
    dump = json.load(open(os.path.join(a.data, "episode.json")))
    inst = json.load(open(a.instance))
    acts, ticks = M.load_trajectory(os.path.join(a.data, "trajectory.npz"), a.task, int(inst["action_dim"]), trusted=True, layout=inst["action_layout"])
    n_live = dump.get("live_rows")
    live = acts if n_live is None else acts[:int(n_live)]
    if ticks is not None:
        ticks = ticks[:len(live)]
    try:
        s = M.Session(a.task, instance=a.instance, strict=True)
    except M.InstanceMismatch as exc:
        M.atomic_json(os.path.join(a.data, "replay.verdict.json"), {"instance_mismatch": True, "error": str(exc)})
        return 2
    t0 = time.time(); video_error = None
    try:
        if a.video:
            try:
                s.start_video(a.video, fps=a.fps)
            except Exception as exc:
                video_error = repr(exc)
        grading = bool(dump.get("success"))       # the tolerant grading replay only confirms a live success
        st = s.replay(live, physics_steps=ticks, grading=grading)
        out = {"replays": [st], "grading_replay": grading, "n_actions": int(len(acts)), "live_rows": int(len(live)),
               "instance_sha": s.instance_sha, "runtime_binding": s.runtime_binding,
               "instance_exact": bool(s.instance_exact), "instance_matches": bool(s.instance_matches),
               "instance_generated": bool(getattr(s, "instance_generated", False)), "initial_state": getattr(s, "initial_state", None),
               "instance_realized": bool(getattr(s, "instance_realized", False)), "assets_exact": bool(getattr(s, "assets_exact", True)),
               "wall_s": round(time.time() - t0, 1), "video": False, "media_status": "pending" if a.video else "disabled"}
        M.atomic_json(os.path.join(a.data, "replay.verdict.json"), out)
        if a.video:
            try:
                s.stop_video()
                out["video"] = os.path.isfile(a.video)
            except Exception as exc:
                traceback.print_exc(); video_error = repr(exc)[:300]
            out.update(media_status="error" if video_error else "complete", video_error=video_error)
            M.atomic_json(os.path.join(a.data, "replay.verdict.json"), out)
        review = st.get("review") or dump.get("review")
        if grading and review:               # a live success held for review: frames around its events and forcing events
            try:
                forcing = (st.get("forcing") or dump.get("forcing") or {}).get("events") or []
                files = s.render_review_frames(live, review["events"] + forcing, os.path.join(a.data, "review_frames"),
                                               physics_steps=ticks)
                out["review_frames"] = [os.path.relpath(f, a.data) for f in files]
            except Exception as exc:
                traceback.print_exc(); out["review_frames_error"] = repr(exc)[:300]
            M.atomic_json(os.path.join(a.data, "replay.verdict.json"), out)
        print(json.dumps(out), flush=True)
    finally:
        s.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
