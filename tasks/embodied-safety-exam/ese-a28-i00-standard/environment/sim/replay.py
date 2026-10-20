"""One fresh-process replay of a recorded Embodied Safety Exam episode: an offline re-check (re-judging recorded trials, a
host comparison). Not part of grading: the verdict is the live episode's (server.py live_verdict).

    python replay.py INSTANCE.json ROWS.npy NOTES.json OUT.json [PICTURE_EVENTS.json]

Rebuilds the frozen instance, executes the journal rows (rcb_ese.Codec) with the notes table, judges the episode with
Embodied Safety Exam's verdict and writes {"state_sha", "start_sha", "verdict", "record"} (state_sha: the hash of the end
state, taken before the verdict lets the end-of-episode rules fire)."""
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rcb_ese  # noqa: E402


def main() -> None:
    inst_path, rows_path, notes_path, out_path = sys.argv[1:5]
    pictures = json.load(open(sys.argv[5])) if len(sys.argv) > 5 else None
    out = rcb_ese.replay(rcb_ese.load_instance(inst_path), np.load(rows_path), json.load(open(notes_path)), pictures)
    tmp = out_path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(rcb_ese.plain(out), f)
    os.replace(tmp, out_path)


if __name__ == "__main__":
    main()
