"""Authoring-only negative / robustness checks for picture_hang (writes trajectories + replay JSONs)."""
import json
import sys
from pathlib import Path

sys.path[:0] = [str(Path(__file__).resolve().parents[1]), str(Path(__file__).resolve().parent)]
import numpy as np  # noqa: E402

import controller as C  # noqa: E402
import replay as R  # noqa: E402
from runtime import Session  # noqa: E402

out = Path(sys.argv[1])
out.mkdir(parents=True, exist_ok=True)
oracle, hand, _ = R.load_trajectory(Path(__file__).resolve().parents[1] / "solution/trajectory.npz")
s = Session()
cases = {}
cases["float32_rows"] = oracle.astype(np.float32).astype(np.float64)
cases["nop_800"] = np.repeat(s.initial_targets[None], 800, 0)
cases["nop_3000"] = np.repeat(s.initial_targets[None], 3000, 0)
success_step = R.replay(Path(__file__).resolve().parents[1] / "solution/trajectory.npz")["steps"]
cases["truncated_before_release_530"] = oracle[:530]
cases[f"truncated_one_row_short_of_success_{success_step - 1}"] = oracle[: success_step - 1]
# Drop: open the squeeze (both stages back out) in mid-carry at row 250 and keep everything else.
drop = oracle.copy()
drop[250:, 1] = s.initial_targets[1] + 0.02   # left stage y outward
drop[250:, 7] = s.initial_targets[7] - 0.02   # right stage y outward
cases["drop_mid_carry_row250"] = drop
lo, hi = s.model.actuator_ctrlrange.T


def opened(rows, delta=0.04):
    r = np.array(rows, copy=True)
    r[:, 1] += delta   # left stage outward (+y)
    r[:, 7] -= delta   # right stage outward (-y)
    return np.clip(r, lo, hi)


# Insert k "opened" rows (both stages 4 cm outward) at row 250, then resume the oracle (review PH-1 cases): any free
# fall must fail at the drop.
for k in (1, 2, 3, 4, 5, 8, 40):
    cases[f"drop{k}_resume_oracle_row250"] = np.concatenate([oracle[:250], opened(np.repeat(oracle[249:250], k, 0)),
                                                              oracle[250:]])
cases["midair_release_row440"] = np.concatenate([oracle[:440], opened(oracle[440:])])
cases["open40_at_hooks_row470_resume"] = np.concatenate([oracle[:470], opened(np.repeat(oracle[469:470], 40, 0)),
                                                         oracle[470:]])
# Release before engagement: open the hands at row 420 (rings still 1 cm in front of the hooks).
early = oracle.copy()
early[420:, 1] = s.initial_targets[1] + 0.02
early[420:, 7] = s.initial_targets[7] - 0.02
cases["release_before_hooks_row420"] = early


def controller_rows(params):
    sess = Session()
    c = C.Controller(sess, params)
    c.run()
    rows = np.array(c.rows)
    return np.concatenate([rows, np.repeat(rows[-1:], 100, 0)])


# Sloppy height: rings carried 7 mm too high, they ride over the hook lips; the frame rests on the lips, unthreaded.
cases["sloppy_rings_over_lips"] = controller_rows({"x0": -0.03, "thumb_fe": 0.5, "window_z": 1.3827})
# One hook only: the right side 8 mm higher (roll) so only the left ring threads.
one = controller_rows({"x0": -0.03, "thumb_fe": 0.5, "k_roll": 0.0})
cases["one_hook_only_roll"] = one


def knock_rows():
    """Hang the frame, open the hands, then (before the 1 s hold completes) grab it again, lift it 3 cm off the
    saddles, pull it 3 cm away from the wall and let go: the rings leave the hooks and the frame falls."""
    sess = Session()
    c = C.Controller(sess, {"x0": -0.03, "thumb_fe": 0.5})
    p = c.p
    c.ramp(1.0, "approach", squeeze=p["open_in"], thumb=1.0)
    c.ramp(1.0, "squeeze", squeeze=p["squeeze_in"], curl=p["curl"])
    c.ramp(1.0, "lift", z=c.cmd["z"] + p["lift"])
    c.ramp(3.0, "carry", x=p["x0"] + 0.15, z=p["z0"] + 0.195)
    c.servo(2.0, "align", z_target=p["window_z"], until=c.aligned)
    c.servo(6.0, "insert", z_target=p["window_z"], x_target=p["insert_ring_x"], until=c.inserted, max_rate=0.0004)
    c.servo(3.0, "lower", z_target=p["window_z"] - p["rest_drop"], x_target=p["insert_ring_x"], pitch_lock=False,
            until=c.loaded, max_rate=0.0004)
    c.ramp(0.6, "release", squeeze=0.03)
    c.ramp(0.2, "regrasp", squeeze=p["squeeze_in"])
    c.ramp(0.5, "knock", z=c.cmd["z"] + 0.03)
    c.ramp(0.5, "knock", x=c.cmd["x"] - 0.04)
    c.ramp(0.3, "let go", squeeze=0.0)
    c.ramp(2.0, "after")
    return np.array(c.rows)


cases["knock_off_hooks_before_hold"] = knock_rows()


def drop_recatch_rows(n, opening=0.045):
    """The closed-loop controller with an inserted n-control free fall mid-carry and a re-catch (review PH-1)."""
    sess = Session()
    c = C.Controller(sess)
    p = c.p
    c.ramp(1.0, "approach", squeeze=p["open_in"], thumb=1.0)
    c.ramp(1.0, "squeeze", squeeze=p["squeeze_in"], curl=p["curl"])
    c.ramp(1.0, "lift", z=c.cmd["z"] + p["lift"])
    c.ramp(3.0, "carry", x=p["x0"] + 0.15, z=p["z0"] + 0.195)
    squeeze = c.cmd["squeeze"]
    c.cmd["squeeze"] = squeeze - opening
    for _ in range(n):
        c.send("drop")
    c.cmd["squeeze"] = squeeze
    for _ in range(10):
        c.send("recatch")
    c.ramp(1.0, "settle")
    c.servo(2.0, "align", z_target=p["window_z"], until=c.aligned)
    c.servo(6.0, "insert", z_target=p["window_z"], x_target=p["insert_ring_x"], until=c.inserted, max_rate=0.0004)
    c.servo(3.0, "lower", z_target=p["window_z"] - p["rest_drop"], x_target=p["insert_ring_x"], pitch_lock=False,
            until=c.loaded, max_rate=0.0004)
    c.ramp(1.0, "release", squeeze=p["release_out"], curl=0.0)
    c.ramp(1.0, "withdraw", x=c.cmd["x"] - 0.08, z=c.cmd["z"] - 0.05)
    c.ramp(4.0, "hold")
    return np.array(c.rows)


cases["drop_recatch_3_controls_closed_loop"] = drop_recatch_rows(3)
results = {}
for name, rows in cases.items():
    if name == "one_hook_only_roll":
        rows = rows.copy()
        rows[300:, 8] += 0.008  # right stage z offset after the carry
        away = np.repeat(rows[-1:], 150, 0)
        away[:, 1] += np.linspace(0, 0.12, 150)   # left stage further out (+y)
        away[:, 7] -= np.linspace(0, 0.12, 150)   # right stage further out (-y)
        rows = np.concatenate([rows, away])
    path = out / f"{name}.npz"
    s.save_trajectory(rows, path)
    r = R.replay(path)
    results[name] = {k: r[k] for k in ("success", "reason", "steps", "stage", "n_actions", "state_sha")}
    results[name]["failure_detail"] = r.get("failure_detail")
    print(name, results[name], flush=True)
(out / "negatives.json").write_text(json.dumps(results, indent=2) + "\n")
