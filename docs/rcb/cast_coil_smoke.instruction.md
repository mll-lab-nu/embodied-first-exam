# Cast Coil rollout pipeline smoke check

This run checks model access, the simulator, rendering, trajectory collection and
the separate Harbor verifier. This appended instruction replaces the puzzle-solving
objective for this diagnostic run. A task reward of zero is expected and acceptable.

Create `/app/output/gen.py` with the exact Python program below, run it once using
the container's `python`, then finish your turn. Wait for that process to complete.
Do not search for a solution, explore the repository, optimize the score, install
dependencies, change simulator or verifier code, or run your own replay. Harbor
will replay and grade the saved trajectory after your turn. If the program fails,
report the actual error and finish; do not fabricate output files or retry indefinitely.

```python
from pathlib import Path

import imageio.v3 as iio
from rcb_topogym import Session

output = Path("/app/output")
output.mkdir(parents=True, exist_ok=True)
session = Session("cast_coil", instance="/app/instance.json")
try:
    iio.imwrite(output / "smoke.initial.png", session.render_frame("cam_high"))
    session.record_start()
    for _ in range(8):
        session.step(session.hold_action())
    actions = session.record_stop()
    session.save_trajectory(actions, str(output / "trajectory.npz"))
    print("SMOKE_ACTIONS", len(actions), flush=True)
    print("SMOKE_STATUS", session.status(), flush=True)
finally:
    session.close()
```

The eight hold actions must go through the real simulator. They are a short rollout
at the initial robot pose, not a manipulation solution. Keep the real task score
unchanged; report only whether the program completed and where its artifacts are.
