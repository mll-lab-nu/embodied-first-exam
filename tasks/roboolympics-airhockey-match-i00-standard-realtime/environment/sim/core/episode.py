"""Contract ③ (docs/framework_zh.md §4.3): the episode log (episode.jsonl) and the fresh-process replay.

episode.jsonl is append-only, one JSON object per line. Rows the replay reads (everything else is information):
  {"ev": "header", "cfg": MatchConfig, "sport", "revision", "protocol", "source_sha", "versions"}
  {"ev": "cmd", "k": K, "seat": S, "cmd": LOW_LEVEL_COMMAND}   applied before control step K (turn: as action K);
                                                               a delayed command is logged at its effect step
  {"ev": "resume", "k": K}                                     a review ended before step K
  {"ev": "forfeit", "k": K, "seat": S, "why": W}               a core decision that ends the match
  {"ev": "retire", "k": K, "seat": S, "side": D, "why": W}     a side leaves, the match goes on (N sides)
  {"ev": "end", "k": K, "reason": R}
Replay (python -m core.episode PLUGIN DIR) rebuilds the match from the header, re-applies the rows at their steps and
writes DIR/replay_check.json: state_sha, scores, winner, ranking, k, commands_sha, source_sha.
Reply images are a pure function of the replayed match (core 0.2.8): python -m core.episode PLUGIN DIR --reply N
draws the reply image of the N-th command row (1-based) into DIR/reply_N.png (+ reply_N.json: the tiles).
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import sys
import threading
import time
from pathlib import Path

from .outcome import decide
from .sport import FINISHED, MatchConfig, sha_json

REPLAYED = ("header", "cmd", "resume", "forfeit", "retire", "end")


def source_sha(*dirs) -> str:
    """Every file under the given directories (path + bytes), so a changed simulator invalidates old episodes."""
    h = hashlib.sha256()
    for d in dirs:
        d = Path(d)
        for p in sorted(x for x in d.rglob("*") if x.is_file() and "__pycache__" not in x.parts):
            h.update(str(p.relative_to(d)).encode())
            h.update(p.read_bytes())
    return h.hexdigest()


def load_plugin(path: str):
    """The plugin module at `path` (its directory goes first on sys.path, so its simulator modules import)."""
    path = os.path.abspath(path)
    sys.path.insert(0, os.path.dirname(path))
    spec = importlib.util.spec_from_file_location("ro_plugin", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.SPORT


class Episode:
    def __init__(self, path):
        self.path = Path(path)
        self.lock = threading.Lock()
        self.t0 = time.monotonic()
        self.commands = []                   # the replayed rows, for commands_sha

    def write(self, ev: str, **row):
        rec = {"ev": ev, "ts": round(time.time(), 3), "wall": round(time.monotonic() - self.t0, 4), **row}
        with self.lock:
            if ev in REPLAYED and ev != "header":
                self.commands.append({k: v for k, v in rec.items() if k not in ("ts", "wall")})
            with self.path.open("a") as f:
                f.write(json.dumps(rec, default=float) + "\n")

    def commands_sha(self) -> str:
        with self.lock:
            return sha_json(self.commands)


def _dispatch(match, row, forfeits, retired, on_cmd=None):
    if row["ev"] == "cmd":
        info = match.apply(row["seat"], row["cmd"]) or {}
        if on_cmd is not None:
            on_cmd(match, row, info)
    elif row["ev"] == "resume":
        match.resume()
    elif row["ev"] == "forfeit":
        match.forfeit(row["seat"], row["why"])
        forfeits.append(row)
    elif row["ev"] == "retire":
        match.retire(row["side"], row["why"])
        retired.append(row["side"])


def replay(sport, rows: list[dict], observer=None, on_cmd=None) -> dict:
    """observer(match): called with the initial state, after every turn-protocol row and after every realtime step
    (spectator video; it must not change the match). on_cmd(match, row, info): right after each command row took
    effect, with what Match.apply returned (reply images; it must not change the match either)."""
    head = next(r for r in rows if r["ev"] == "header")
    cfg = MatchConfig.from_json(head["cfg"])
    match = sport.build(cfg)
    rep = [r for r in rows if r["ev"] in REPLAYED and r["ev"] != "header"]
    end = next((r for r in rep if r["ev"] == "end"), None)
    forfeits: list[dict] = []
    retired: list[str] = []
    seen = observer or (lambda m: None)
    seen(match)
    if sport.protocol == "turn":
        for r in rep:
            _dispatch(match, r, forfeits, retired, on_cmd)
            if r["ev"] == "cmd":
                seen(match)
    else:
        at: dict[int, list] = {}
        for r in rep:
            at.setdefault(int(r["k"]), []).append(r)
        k_end = int(end["k"]) if end else max(at, default=0)
        while True:
            for r in at.pop(match.k, []):
                _dispatch(match, r, forfeits, retired, on_cmd)
            if match.phase().state == FINISHED or match.k >= k_end:
                break
            match.step()
            seen(match)
        if at:
            raise ValueError(f"rows after the end of the match at steps {sorted(at)[:5]}")
    fo = forfeits[0] if forfeits else None
    out = decide(match, fo["seat"] if fo else None, fo["why"] if fo else None, cfg.side_list(), cfg.side_of,
                 retired)
    return {"state_sha": match.state_digest(), "scores": match.scores(), "winner": out.winner,
            "ranking": out.ranking, "decided_by": out.decided_by, "k": match.k,
            "finished": match.phase().state == FINISHED,
            "commands_sha": sha_json([{k: v for k, v in r.items() if k not in ("ts", "wall")} for r in rep]),
            "source_sha": head.get("source_sha"), "revision": head.get("revision"), "cfg": head["cfg"]}


def read_rows(path) -> list[dict]:
    return [json.loads(x) for x in Path(path).read_text().splitlines() if x.strip()]


def reply_image(plugin: str, rows: list[dict], n: int) -> dict | None:
    """The reply image of the n-th command row (1-based), drawn from the replayed match as the live service drew it
    (the same job, the task's renderer of the header's cfg, the players' scene): {"png", "tiles", ...} or None."""
    from . import spec as spec_mod
    from .observe import CameraWorker, players_scene, reply_job
    sport = load_plugin(plugin)
    columns = int((spec_mod.load(plugin).get("observation") or {}).get("columns", 2))
    got, count = [], [0]

    def on_cmd(match, row, info):
        count[0] += 1
        if count[0] == n and hasattr(match, "reply_views"):
            got.append(reply_job(match, match.reply_views(row["seat"], row["cmd"], info), columns))
    replay(sport, rows, on_cmd=on_cmd)
    if not got or got[0] is None:
        return None
    cfg = MatchConfig.from_json(next(r for r in rows if r["ev"] == "header")["cfg"])
    return CameraWorker(players_scene(sport, plugin, cfg), cfg.renderer).draw_job(got[0])


def main(argv):
    plugin, d = argv[0], Path(argv[1])
    if "--reply" in argv:
        n = int(argv[argv.index("--reply") + 1])
        img = reply_image(plugin, read_rows(d / "episode.jsonl"), n)
        if img is None:
            print(json.dumps({"reply": n, "image": False}))
            return
        (d / f"reply_{n}.png").write_bytes(img["png"])
        (d / f"reply_{n}.json").write_text(json.dumps({k: v for k, v in img.items() if k != "png"}))
        print(json.dumps({"reply": n, "image": str(d / f"reply_{n}.png"), "tiles": len(img["tiles"])}))
        return
    sport = load_plugin(plugin)
    out = replay(sport, read_rows(d / "episode.jsonl"))
    (d / "replay_check.json").write_text(json.dumps(out, default=float))
    print(json.dumps({k: out[k] for k in ("state_sha", "scores", "winner", "k")}, default=float))


if __name__ == "__main__":
    main(sys.argv[1:])
