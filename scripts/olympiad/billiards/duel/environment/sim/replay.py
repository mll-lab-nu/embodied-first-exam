"""Fresh-process replay of a recorded duel: python3 replay.py DATA_DIR [--video]
Reads DATA_DIR/trajectory.json and writes DATA_DIR/replay_check.json (score, winner, state hash, source fingerprint),
or, with --video, DATA_DIR/replay.mp4."""
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


def main(directory: str, video: bool = False) -> None:
    path = Path(directory)
    tr = json.loads((path / "trajectory.json").read_text())
    import duel_core as D
    if video:
        D.render_video(int(tr["seed"]), tr["first_player"], tr["decisions"], str(path / "replay.mp4"))
        return
    if tr["source_sha"] != source_sha() or tr["revision"] != D.REVISION:
        raise ValueError("simulator fingerprint mismatch")
    m = D.Duel(int(tr["seed"]), tr["first_player"])
    m.replay(tr["decisions"])
    if tr.get("tiebreak"):                 # a tie at the cap, decided by the recorded chess clocks
        m.resolve_tie(tr["tiebreak"]["winner"], tr["tiebreak"]["clock_left_s"])
    import sport
    out = {"state_sha": m.state_sha(), "score": sport.scores(m), "winner": m.winner, "done": m.done,
           "n_shots": len(m.decisions),
           "seed": m.seed, "first_player": m.first, "source_sha": tr["source_sha"], "revision": D.REVISION}
    (path / "replay_check.json").write_text(json.dumps(out))


if __name__ == "__main__":
    main(sys.argv[1], "--video" in sys.argv[2:])
