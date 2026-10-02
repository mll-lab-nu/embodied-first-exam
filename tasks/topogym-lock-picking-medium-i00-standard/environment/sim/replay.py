"""Fresh-process replay of a TopoGym standard-mode episode, run by environment/sim/finalize.sh after the service exited.

    python /srv/replay.py --data /data --task <family> --instance /srv/instance.json [--video /data/replay.mp4]

Builds the frozen instance in this new process, replays the rows the live episode executed (episode.json `live_rows`; rows
recorded after the live end were never commanded live) once, and renders the human-viewable video DURING that replay: the
grading needs two passes, the live episode and this replay, not a third pass for the video. A failed video never costs the
verdict: the replay is then run again without it. Prints one JSON line (replays[0] = Session.status() of the replay)."""
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
    traj = np.load(os.path.join(a.data, "trajectory.npz"), allow_pickle=False)
    if str(traj["task"]) != a.task:
        print(json.dumps({"error": f"trajectory task {traj['task']} != {a.task}"}), flush=True); return 2
    acts = np.asarray(traj["actions"], dtype=np.float32)
    n_live = dump.get("live_rows")
    live = acts if n_live is None else acts[:int(n_live)]
    s = M.Session(a.task, instance=a.instance, strict=True)     # strict: a rebuilt scene off the frozen poses refuses to grade
    t0 = time.time(); video = False; video_error = None
    try:
        if a.video:
            s.start_video(a.video, fps=a.fps)
        st = s.replay(live)
        if a.video:
            s.stop_video(); video = os.path.isfile(a.video)
    except Exception as exc:  # noqa: BLE001 — rendering (or the replay itself) failed: retry the verdict without the video
        traceback.print_exc(); video_error = repr(exc)[:300]
        try:
            s.stop_video()
        except Exception:  # noqa: BLE001
            pass
        st = s.replay(live)
    out = {"replays": [st], "n_actions": int(len(acts)), "live_rows": int(len(live)), "instance_sha": s.instance_sha,
           "live_instance_sha": str(traj["instance_sha"]),
           "instance_exact": bool(s.instance_exact), "instance_matches": bool(s.instance_matches), "wall_s": round(time.time() - t0, 1),
           "video": bool(video), "video_error": video_error}
    print(json.dumps(out), flush=True)
    s.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
