"""Release gate: building and running an episode is deterministic, whether it is built once per process, twice in a row,
or next to another live episode, and under both clocks.

    python tools/double_build_check.py [--jobs 10] [--families ...] [--think 2.0] [--out FILE]

For every realtime task of 0.5.0.1 (the D families d01 to d05, hazard members and benign twins, and every member of
a_pet_appliance, `hazard_hidden` in its tier `closer`), seed 0, control interface, under the clock `paused` and the clock
`realtime` (a synthetic think time of `--think` s before every call but the first), one worker process per task and
clock runs:

  (a) two builds one after the other in the same process: each one's start hash, then the scripted reference run in
      each (`verify.run` with the same think schedule): each one's final hash;
  (b) two live episodes at once: a first one built and kept alive (stepped five ticks under realtime), a second one
      built next to it that runs the reference: its start and final hash;
  (c) a fresh process: `python -m robosafe verify` replays (a)'s first record.

It checks, per task and clock: the start hashes of every build agree; the final hashes of (a), (a) again, (b) and (c)
agree. Paused and realtime start hashes differ by design and are not compared with each other: the state hash of a
realtime episode includes the plan the robot still has to run (`Episode.state_hash`: `state["plan"]`, the digest of
the planned rows, empty at the start) and is otherwise the paused one. It prints one JSON line per task and clock and
exits non-zero on any mismatch.
"""
from __future__ import annotations

import argparse
import json
import multiprocessing
import os
import subprocess
import sys
import tempfile
from concurrent.futures import ProcessPoolExecutor

D_FAMILIES = ("d_hand_enters", "d_label_revealed", "d_machine_red_light", "d_pan_smoke", "d_spill_toward_strip")
AB05 = "a_pet_appliance"


def tasks(families=None, robot: str = "ur5e_2f85", movers: str = "scripted") -> list:
    from robosafe import families as F
    out = []
    for fid in (families or D_FAMILIES + (AB05,)):
        fam = F.get(fid)
        # (the room robots have no `hazard_hidden` member on their room families)
        hidden = "hazard_hidden" in getattr(fam, "roles", {}) and "hazard_hidden" not in fam.members and robot not in ("tidybot", "g1_wbc")
        for member in fam.members + (("hazard_hidden",) if hidden else ()):
            levels = fam.evidence_levels(member) or (None,)
            for lv in levels:
                key = {"family": fid, "member": member, "seed": 0, "robot": robot, "interface": "control"}
                if lv:
                    key["evidence"] = lv
                if movers != "scripted":          # 0.5.1 (B2): the reactive-movers condition, in the key
                    key["movers"] = movers
                # a room family (0.5.1, the TidyBot under control): under each of its camera conditions
                for cam in tuple(getattr(fam, "camera_conditions", ()) or ()) or (None,):
                    out.append({**key, **({"cameras": cam} if cam else {})})
    return out


def check(job) -> dict:
    key, clock, think = job
    from robosafe import verify
    k = dict(key, **({"clock": "realtime"} if clock == "realtime" else {}))
    sched = think if clock == "realtime" else None
    row = {"key": key, "clock": clock}
    try:
        # (a) two builds one after the other
        starts, finals, recs = [], [], []
        for _ in range(2):
            f, inst, ep = verify.start(k)
            starts.append(ep.state_hash())
            ep.world.close()
            rec = verify.run(k, "reference", sched)
            finals.append(rec["final_hash"])
            recs.append(rec)
        # (b) two live episodes at once: the first stays alive (and moves a little under realtime)
        f0, i0, ep0 = verify.start(k)
        starts.append(ep0.state_hash())
        if clock == "realtime":
            for _ in range(5):
                ep0.execute({"tool": "joint_position", "args": {"row": ep0.command("joint_position").tolist()}}, think_ticks=1)
        f1, i1, ep1 = verify.start(k)
        starts.append(ep1.state_hash())
        ep1.world.close()
        rec_b = verify.run(k, "reference", sched)
        finals.append(rec_b["final_hash"])
        ep0.world.close()
        # (c) a fresh process replays (a)'s first record
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
            json.dump(recs[0], fh)
            path = fh.name
        out = subprocess.run([sys.executable, "-m", "robosafe", "verify", path, "--json"], capture_output=True, text=True, timeout=1800)
        os.unlink(path)
        if out.returncode != 0:
            raise RuntimeError(f"fresh-process verify failed: {out.stderr[-500:]}")
        ver = json.loads(out.stdout)
        finals.append(ver["replay"]["hash"])
        row.update({"start": starts[0][:16], "starts_equal": len(set(starts)) == 1, "final": finals[0][:16],
                    "finals_equal": len(set(finals)) == 1, "finals": [h[:16] for h in finals], "starts": [h[:16] for h in starts],
                    "outcome": ver.get("outcome")})
        row["ok"] = row["starts_equal"] and row["finals_equal"]
    except Exception as e:                      # noqa: BLE001
        row.update({"ok": False, "error": f"{type(e).__name__}: {e}"[:400]})
    return row


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="python tools/double_build_check.py")
    p.add_argument("--families", nargs="*")
    p.add_argument("--robot", default="ur5e_2f85", help="0.5.1: e.g. tidybot or g1_wbc (room families, both camera conditions; paused clock only)")
    p.add_argument("--clocks", nargs="*", default=["paused", "realtime"])
    p.add_argument("--think", type=float, default=2.0)
    p.add_argument("--jobs", type=int, default=8)
    p.add_argument("--movers", default="scripted", choices=("scripted", "reactive"), help="0.5.1 (B2): the movers' condition of every task")
    p.add_argument("--out")
    a = p.parse_args(argv)
    jobs = [(key, clock, a.think) for key in tasks(a.families, a.robot, a.movers) for clock in a.clocks]
    bad = 0
    fh = open(a.out, "w") if a.out else None
    with ProcessPoolExecutor(a.jobs, mp_context=multiprocessing.get_context("spawn"), max_tasks_per_child=1) as pool:
        for r in pool.map(check, jobs):
            line = json.dumps(r)
            print(line, flush=True)
            if fh:
                fh.write(line + "\n")
                fh.flush()
            bad += not r.get("ok")
    print(f"{len(jobs) - bad} of {len(jobs)} task-clock pairs deterministic; {bad} mismatches", flush=True)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
