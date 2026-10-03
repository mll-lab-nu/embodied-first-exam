"""Fresh-process replay of a recorded curling match (program play, eai-standard-turn/1.0).

    python3 replay.py trajectory.json [video.mp4]

Prints one JSON line (the replayed score, state hash, throws); with a video path it also renders the replay video.
The service plays a match in the same steps used here: the opponent's throws until the player's turn (`follow()`),
then the player's throw (`throw()`), then, after the player's review, `follow()` again. `followed` in the trajectory
says whether the last throw was followed (a match that ended during a review was not).
"""
import hashlib
import json
import os
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


def throw(m, dec: dict) -> dict:
    return m.player_throw(dec["v"], dec["angle"], dec["spin"])


def follow(m) -> list:
    """The opponent's throws until it is the player's turn again (across ends) or the match is over."""
    return m.run_to_decision()


def replay(tr: dict):
    os.environ["MATCH_SEED"] = str(tr["seed"])
    import curling
    m = curling.Match(int(tr["level"]))
    follow(m)
    decs = tr["decisions"]
    for i, d in enumerate(decs):
        if m.done:
            break
        throw(m, d)
        if i < len(decs) - 1 or tr.get("followed", True):
            follow(m)
    if tr.get("tiebreak"):                     # a tie after the last extra end, decided by the recorded chess clocks
        m.resolve_tiebreak(tr["tiebreak"]["winner"], tr["tiebreak"]["clock_left_s"])
    return m


if __name__ == "__main__":
    tr = json.load(open(sys.argv[1]))
    m = replay(tr)
    print(json.dumps({"replay_score": list(m.score), "replay_done": m.done, "replay_sha": m.state_sha(),
                      "replay_throws": m.n_throws, "source_sha": source_sha()}), flush=True)
    if len(sys.argv) > 2:
        import render
        render.render_match_video(int(tr["level"]), tr["decisions"], sys.argv[2])
        print(json.dumps({"video": sys.argv[2]}), flush=True)
