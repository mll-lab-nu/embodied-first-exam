"""Fresh-process replay of a recorded 8-ball game against the scripted opponent (program play, eai-standard-turn/1.0).

    python3 replay.py trajectory.json [video.mp4]

Prints one JSON line (the replayed result, state hash, shot count); with a video path it also renders the top-view
replay video. The service plays a game in the same two steps used here: `shot()` (the player's shot) and, after the
player's review, `follow()` (the opponent's turn, if the turn passed). `followed` in the trajectory says whether the
last shot was followed (a game that ended during a review was not).
"""
import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))


def source_sha() -> str:
    """Fingerprint of the simulator code (every .py file of this directory)."""
    h = hashlib.sha256()
    for p in sorted(HERE.glob("*.py")):
        h.update(p.name.encode()); h.update(p.read_bytes())
    return h.hexdigest()


def shot(m, dec: dict) -> dict:
    return m.shot(dec)


def follow(m) -> list:
    return m.follow()


def replay(tr: dict, keep_systems: bool = False):
    import eightball
    m = eightball.Match(int(tr["level"]), int(tr["seed"]), keep_systems=keep_systems)
    decs = tr["decisions"]
    for i, d in enumerate(decs):
        if m.g.done:
            break
        shot(m, {k: v for k, v in d.items() if k != "player"})
        if i < len(decs) - 1 or tr.get("followed", True):
            follow(m)
    if tr.get("tiebreak"):                     # a tie at the shot limit, decided by the recorded chess clocks
        m.g.resolve_tiebreak(tr["tiebreak"]["winner"], tr["tiebreak"]["clock_left_s"])
    return m


def video(tr: dict, path: str) -> None:
    import render
    m = replay(tr, keep_systems=True)
    g = m.g
    by_k = {s["k"]: s for s in g.shots}
    clips = []
    for k, p, pos0, s in g.systems:
        rec = by_k[k]
        what = ("BREAK " if rec["break"] else "") + ("FOUL: " + rec["foul"] if rec["foul"] else
                                                     "potted " + (",".join(rec["potted"]) or "nothing"))
        clips.append((f"shot {k + 1}: {'YOU' if p == 0 else 'opponent'} | {what}", pos0, s))
    res = ("you win" if g.winner == 0 else "opponent wins" if g.winner == 1 else "draw") if g.done else "not finished"
    render.render_video(clips, dict(g.pos), f"final: {res} ({g.result or ''})", path)


if __name__ == "__main__":
    tr = json.load(open(sys.argv[1]))
    m = replay(tr)
    print(json.dumps({"replay_winner": m.g.winner, "replay_done": m.g.done, "replay_result": m.g.result,
                      "replay_sha": m.state_sha(), "replay_n_shots": m.g.k, "source_sha": source_sha()}), flush=True)
    if len(sys.argv) > 2:
        video(tr, sys.argv[2])
        print(json.dumps({"video": sys.argv[2]}), flush=True)
