"""Oracle (privileged mode): re-save the validated actuator trajectory as the deliverable.

solution/ holds only actuator rows and the hand: `trajectory.npz`, or `trajectory.json` + `trajectory.partNN.npz`
(each part below 2 MB; concatenated in order and checked against the manifest's sha256 before use). The isolated
verifier replays the rows from the frozen start in two fresh processes, exactly as it replays an agent's submission.
"""

from pathlib import Path

import numpy as np

from solution_parts import load

TARGET = Path("/app/output/trajectory.npz")

actions, hand = load(Path(__file__).resolve().parent)
TARGET.parent.mkdir(parents=True, exist_ok=True)
np.savez_compressed(TARGET, actions=actions, hand=np.array(hand))
print(f"saved {len(actions)} {hand} rows of width {actions.shape[1]} to {TARGET}")
