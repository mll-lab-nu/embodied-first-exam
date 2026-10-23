"""Wall clock -> graded-replay time, so a click on an event can seek the replay. The replay shows simulated time; the
service log (verifier/episode.jsonl) says how many physics steps each call ran and when. Video time at wall time w =
duration * (physics steps run by w) / (all physics steps). Only the last episode is in the replay: steps before the
last reset map to nothing. A map whose step total disagrees with the log's `end` record by more than 2% is not written.
usage: python -m pipeline sync [--fetch] [--keys K ...]   -> videomap/K.json (needs service/K/episode.jsonl)
       BEL_TOKEN=<board token> python -m pipeline sync --fetch   downloads service/K/episode.jsonl first
       python -m pipeline sync --check <viz dir> <raw dir>       compare with a live_timeline.jsonl the board made"""
from __future__ import annotations
import argparse, bisect, json, os, subprocess
from .paths import DATA, RAW, keys, jdump
from .logs import agent_t0

RESET = {"reset", "episode_start", "new_episode"}


def duration(mp4: str) -> float | None:
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", mp4], capture_output=True, text=True)
    try:
        return float(r.stdout.strip())
    except ValueError:
        return None


def steps_curve(episode: list[dict]) -> tuple[list[float], list[int], int | None]:
    """(absolute times, cumulative physics steps after each call) for the last episode, and the log's own total."""
    ts, cum, total, n = [float(episode[0]["ts"])], [0], None, 0
    for e in episode:
        ev = e.get("ev")
        if ev in RESET:
            ts, cum, n = [float(e["ts"])], [0], 0
        elif ev == "end":
            total = e.get("physics_steps")
        elif ev != "observe" and isinstance(e.get("physics_steps"), int):
            n += e["physics_steps"]
            ts.append(float(e["ts"]))
            cum.append(n)
    return ts, cum, total


def video_map(episode: list[dict], dur: float) -> dict | None:
    ts, cum, total = steps_curve(episode)
    if not cum or cum[-1] == 0 or (total and abs(total - cum[-1]) > 0.02 * total):
        return None
    return {"duration": dur, "episode_start_abs": ts[0], "points": [[round(t, 2), round(dur * c / cum[-1], 3)] for t, c in zip(ts, cum)]}


def video_at(vmap: dict, wall_abs: float) -> float | None:
    """Video seconds for an absolute wall time; None before the replayed episode started."""
    pts = vmap["points"]
    if wall_abs < vmap["episode_start_abs"]:
        return None
    i = bisect.bisect_right([p[0] for p in pts], wall_abs) - 1
    return pts[i][1] if i >= 0 else 0.0


def check(viz: str, raw: str):
    ep = [json.loads(l) for l in open(f"{viz}/service/episode.jsonl")]
    lt = [json.loads(l) for l in open(f"{viz}/service/live_timeline.jsonl")]
    dur = duration(f"{raw}/verifier/replay.mp4")
    vm = video_map(ep, dur)
    start, last = float(ep[0]["ts"]), lt[-1]["frame"]
    err = sorted(abs(video_at(vm, start + r["wall_s"]) - dur * r["frame"] / last) for r in lt[1:])
    print(f"{len(err)} 帧；视频 {dur:.1f} s；误差中位 {err[len(err) // 2]:.2f} s，最大 {err[-1]:.2f} s")


def fetch(ks: list[str]):
    import bel                                    # tools/bel.py; the token comes from $BEL_TOKEN
    for k in ks:
        t = json.load(open(f"{RAW}/{k}/trial.json"))
        p = next((p for p in ("verifier/episode.jsonl", "artifacts/data/episode.jsonl") if p in (t["detail"].get("files") or [])), None)
        if p:
            os.makedirs(f"{DATA}/service/{k}", exist_ok=True)
            open(f"{DATA}/service/{k}/episode.jsonl", "wb").write(bel.get_file(t["row"]["id"], p))


def main(argv=None):
    ap = argparse.ArgumentParser(prog="pipeline sync")
    ap.add_argument("--check", nargs=2)
    ap.add_argument("--fetch", action="store_true")
    ap.add_argument("--keys", nargs="*")
    a = ap.parse_args(argv)
    if a.check:
        return check(*a.check)
    ks = keys(a.keys)
    if a.fetch:
        fetch(ks)
    for k in ks:
        p, mp4 = f"{DATA}/service/{k}/episode.jsonl", f"{RAW}/{k}/verifier/replay.mp4"
        if not (os.path.exists(p) and os.path.exists(mp4)):
            continue
        vm = video_map([json.loads(l) for l in open(p)], duration(mp4))
        if vm:
            vm["agent_t0_abs"] = agent_t0(k)
            jdump(vm, f"{DATA}/videomap/{k}.json")
        print(f"{'对时可用' if vm else '步数对不上，不用'}  {k}")
