#!/usr/bin/env python3
"""Freeze the selected YAMLab instances into the repository (scripts/yamlab/instances.json + scripts/yamlab/frozen/).

    python3 scripts/yamlab/freeze.py /data/yamlab-select          # the --out directory of select_instances.py

Per family, the accepted object pairs of the selection in file order become i00, i01, ...: frozen/<family>-iNN/ gets the
candidate's instance.json (written by `rcb_yamlab.py make-instance` in the image) and oracle_actions.npy (the (T, 14) actions
of its live oracle run, up to the first success); instances.json records the source demonstration, the assets and the
hashes of the three runs (live, two fresh-process replays). Needs numpy (reads the live run's trajectory.npz).

Only the instances in KEEP are frozen and listed (each with its id NN): the 2026-10-10 prune (owner) kept five of the 25 per
family, chosen among those GPT-6 Luna's standard run had graded, mixing its successes and failures
(docs/benchmarks/yamlab.md, Instances); instances.json's `pruned` records the removed ids."""
import json, pathlib, shutil, sys
import numpy as np

HERE = pathlib.Path(__file__).resolve().parent
FAMILIES = ("put_pot_on_cooktop", "hang_mug_on_tree")
PER_FAMILY = 25
KEEP = {"put_pot_on_cooktop": [0, 3, 4, 7, 8], "hang_mug_on_tree": [10, 13, 15, 20, 21]}   # the 2026-10-10 prune
PRUNE_RULE = ("2026-10-10 (owner): five instances per family kept, chosen among those whose standard task GPT-6 Luna's "
              "run (codex-gpt6_luna-xhigh) had graded, mixing its successes and failures and spreading over the placement "
              "schedule; the other twenty and their task dirs (both modes) removed")


def main() -> int:
    sel_dir = pathlib.Path(sys.argv[1]).resolve()
    sel = json.loads((sel_dir / "selection.json").read_text())
    out = {"source": {"dataset": "yamlab/yamlab_datasets", "revision": "fc6be973b8645cca50c0e9236bfbd64afa42696f",
                      "rule": "teleoperation files in order (one object pair each); inside the k-th file, demos from k mod n on, "
                              "wrapping (demo j = entry j of YAMLab's placement schedule); the first demo "
                              "whose oracle (30-step ramp from the home pose + the recorded actions) succeeds live and in two "
                              "fresh-process replays, all three ending in the same state, is the pair's instance"},
           "pruned": {"rule": PRUNE_RULE}, "families": {}, "tried": {}}
    (HERE / "frozen").mkdir(exist_ok=True)
    for fam in FAMILIES:
        if fam not in sel:
            print(f"WARNING {fam}: not selected yet"); out["families"][fam] = []; out["tried"][fam] = {}; continue
        chosen = sel[fam]["chosen"]
        names = sorted(chosen)[:PER_FAMILY]
        if len(names) < PER_FAMILY:
            print(f"WARNING {fam}: only {len(names)} accepted pairs")
        rows = []
        for i, name in enumerate(names):
            if i not in KEEP[fam]:
                continue
            v = chosen[name]
            cand = sel_dir / fam / f"{pathlib.Path(name).stem}_d{v['demo']}"
            dst = HERE / "frozen" / f"{fam}-i{i:02d}"
            dst.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(cand / "instance.json", dst / "instance.json")
            acts = np.load(cand / "trajectory.npz")["actions"].astype(np.float32)
            np.save(dst / "oracle_actions.npy", acts)
            assert len(acts) == v["n_actions"], (name, len(acts), v["n_actions"])
            rows.append({"id": i, "file": name, "demo": v["demo"], "assets": v["assets"], "instance_sha": v["instance_sha"],
                         "n_actions": v["n_actions"], "oracle_sha": v["live"]["state_sha"], "replay_shas": v["replay_shas"]})
        out["families"][fam] = rows
        out["pruned"][fam] = [i for i in range(len(names)) if i not in KEEP[fam]]
        tried = sel[fam]["tried"]
        out["tried"][fam] = {"candidates": len(tried), "accepted": sum(1 for t in tried if t.get("accepted")),
                             "rejected": [{"file": t["file"], "demo": t["demo"], "rc": t.get("rc"), "live_success": (t.get("live") or {}).get("success"),
                                           "replay_success": t.get("replay_success"), "live_sha": (t.get("live") or {}).get("state_sha"),
                                           "replay_shas": t.get("replay_shas")} for t in tried if not t.get("accepted")]}
    (HERE / "instances.json").write_text(json.dumps(out, indent=1) + "\n")
    print(json.dumps({f: len(r) for f, r in out["families"].items()}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
