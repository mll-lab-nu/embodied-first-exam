#!/usr/bin/env python3
"""Generate the YAMLab tasks: tasks/yamlab-<family>-iNN-privileged and tasks/yamlab-<family>-iNN-standard (standard mode,
eai-standard/2.2) for every frozen instance in scripts/yamlab/instances.json (docs/benchmarks/yamlab.md).

    python3 scripts/yamlab/mk_tasks.py              # (re)write every YAMLab task dir; `git diff tasks/` stays empty
    python3 scripts/yamlab/mk_tasks.py --check      # write nothing; exit 1 if a task dir differs from the generator's
Then `cd tasks && harbor add --scan .` when a digest changed. Needs only Python 3 (no simulator).

Inputs, all in the repository:
  scripts/yamlab/instances.json          per family: the frozen instances (id NN = task iNN), each with its YAMLab teleoperation
                                         source, its assets and the hashes of its oracle runs (scripts/yamlab/freeze.py writes it
                                         from the selection, scripts/yamlab/select_instances.py)
  scripts/yamlab/frozen/<family>-iNN/    instance.json (the frozen scene: assets + full state + hash + success thresholds) and
                                         oracle_actions.npy (the oracle's (T, 14) actions as executed, up to its first success)
  scripts/yamlab/shared/rcb_yamlab.py    the tooling (privileged environment/ + tests/, standard environment/sim/)
  scripts/yamlab/template/<mode>/        every other task file; a *.tmpl file is filled with the instance's values (@@KEY@@)
  scripts/eai_standard/                  the eai-standard/2.2 layer, copied unchanged (rcb_client.py, rcb1.py; sim/
                                         rcb_limited.py, rcb1.py, run.sh) and the standard client: client.env (the base image)
                                         + client-requirements.txt (the pip pins, copied into environment/)
  images/yamlab/VERSION                  the base image tag
Both twins of an instance are written to a scratch directory, passed through scripts/task_conventions.py's normalize()
(PROTOCOL v1.0 conventions) and then synced into tasks/: a task dir holds exactly what the generator writes."""
from __future__ import annotations
import argparse, json, os, pathlib, sys, tempfile

ROOT = pathlib.Path(__file__).resolve().parents[2]
HERE = ROOT / "scripts/yamlab"
LAYER = ROOT / "scripts/eai_standard"
REGISTRY = "ghcr.io/mll-lab-nu"
CLIENT = dict(l.split("=", 1) for l in (LAYER / "client.env").read_text().splitlines() if "=" in l and not l.startswith("#"))
DATASET_REV = "fc6be97"

FAMILIES = {
    "put_pot_on_cooktop": {
        "env": "PutPotOnCooktop-v0",
        "goal": "lift the pot with **both** arms (both grippers holding it), put it down on the cooktop, upright, and let go "
                "with both grippers.",
        "goal_toml": "Task: lift the pot with both arms (both grippers holding it), put it down upright on the cooktop and let go.",
        "readme_goal": "Two I2RT YAM arms on a workstation table lift a pot together (both grippers must hold it) and put it "
                       "down upright on a cooktop, then let go: YAMLab's PutPotOnCooktop.",
        "difficulty": "A two-arm lift: both grippers must hold the pot at once while it rises 5 cm, so the two grasps (one per "
                      "handle or rim side) and the two arms' motions must be coordinated, and the pot must be carried and set "
                      "down upright within 2 cm of its resting height on the cooktop, then released without knocking it over.",
        "standard_goal": "lift the pot with **both** arms (both grippers holding it), put it down on the cooktop, upright, and "
                         "let go with both grippers. The scene has the pot and the cooktop on the table.",
    },
    "hang_mug_on_tree": {
        "env": "HangMugOnTree-v0",
        "goal": "pick up the mug with the **left** arm, hand it over to the **right** arm (the right gripper takes it, then "
                "the left one lets go, with the mug kept lifted), and hang the mug on the mug tree, released by both grippers.",
        "goal_toml": "Task: pick up the mug with the left arm, hand it over to the right arm, and hang it on the mug tree.",
        "readme_goal": "Two I2RT YAM arms on a workstation table pass a mug from the left gripper to the right one in the air "
                       "and hang it on a mug tree: YAMLab's HangMugOnTree.",
        "difficulty": "Three ordered stages with an in-air handover: the left gripper must lift the mug, the right gripper must "
                      "take it while it stays lifted and the left must let go (both conditions held for a full second), and "
                      "the mug must end up hanging on one of the tree's branches by its handle, steady and released by both "
                      "grippers; a mug dropped on the way is hard to recover.",
        "standard_goal": "pick up the mug with the **left** arm, hand it over to the **right** arm (the right gripper takes it, "
                         "then the left one lets go, with the mug kept lifted), and hang the mug on the mug tree, released by "
                         "both grippers. The scene has the mug and the mug tree on the table.",
    },
}


def toml_str(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"', '\\"')


def base(fam: str, i: int) -> str:
    return f"yamlab-{fam.replace('_', '-')}-i{i:02d}"


def normalizer():
    sys.path.insert(0, str(ROOT / "scripts"))
    from task_conventions import normalize
    return normalize


def fill(text: str, values: dict) -> str:
    for k, v in values.items():
        text = text.replace(f"@@{k}@@", v)
    if "@@" in text:
        raise RuntimeError(f"unfilled placeholder near {text[text.index('@@'):][:40]!r}")
    return text


def cm(x: float) -> str:
    return f"{100 * x:.1f}"


def placement(I: dict, demo: int) -> str:
    """The moved object's placement on YAMLab's teleoperation schedule (demo j = entry j; the base object never moves)."""
    import math
    obj = list(I["assets"])[0]
    p = I["objects"][obj]["position"]; w, x, y, z = I["objects"][obj]["orientation_wxyz"]
    yaw = math.degrees(math.atan2(2 * (w * z + x * y), 1 - 2 * (y * y + z * z)))
    return f"placement-schedule entry {demo}: the {obj.replace('_', ' ')} at x = {p[0]:.3f} m, y = {p[1]:.3f} m, yaw {yaw:.0f}°"


def objects_block(I: dict) -> str:
    names = list(I["assets"])
    parts = [f"`{n}` (YAMLab asset `{I['assets'][n]}`, {' × '.join(cm(v) for v in I['objects'][n]['size'])} cm)" for n in names]
    return (f"The scene's two task objects are {parts[0]} and {parts[1]}: `s.objects()` gives their poses, sizes (in their own "
            f"frames: x × y × z, the root at the box centre) and bounding boxes, `p[\"get_object_points\"](name)` their mesh "
            f"points.\n")


def success_block(fam: str, P: dict, standard: bool) -> str:
    grasp = ("(YAMLab's grasp detection: both fingers of that gripper touch the {o} with at least 0.1 N, on their pads)")
    if fam == "put_pot_on_cooktop":
        up = "" if standard else f" (z > {P['pot_rest_z'] + P['pick_lift_m']:.4f} m)"
        return (f"1. **pick**: the pot's centre is more than 5 cm above its resting height{up} while **both** grippers grasp it "
                f"{grasp.format(o='pot')}, for {P['pick_steps']} consecutive control steps;\n"
                f"2. **place**: the pot rests on the cooktop: its centre within {P['place_xy_tol_m']:.3f} m (horizontally) of the "
                f"cooktop's centre, its centre's height within 2 cm of the cooktop's centre + half the cooktop's height "
                f"({cm(P['cooktop_height'] / 2)} cm) + half the pot's height ({cm(P['pot_height'] / 2)} cm), upright (its z axis "
                f"within 0.2 rad of vertical), and **neither** gripper grasping it, for {P['place_steps']} consecutive control steps.\n")
    up = "" if standard else f" (z > {P['mug_rest_z'] + P['pick_lift_m']:.4f} m)"
    hang = "" if standard else f" (z > {P['hang_min_z']:.4f} m)"
    return (f"1. **pick**: the **left** gripper grasps the mug {grasp.format(o='mug')} and the mug's centre is more than 5 cm "
            f"above its resting height{up}, for {P['pick_steps']} consecutive control steps;\n"
            f"2. **handover**: the **right** gripper grasps the mug, the left gripper does not, and the mug's centre stays more "
            f"than 5 cm above its resting height, for {P['handover_steps']} consecutive control steps (as in YAMLab, the left "
            f"fingers' friction is raised when the left gripper first grasps the mug and lowered again when both grippers hold "
            f"it: YAMLab's own handover aid);\n"
            f"3. **hang**: the mug's centre within {P['hang_xy_tol_m']:.3f} m (horizontally) of the mug tree's centre and more "
            f"than 5 cm above the height it would rest at on the table{hang}, **neither** gripper grasping it, and its height "
            f"steady (within {cm(P['hang_z_stability_m'])} cm of where this stage started), for {P['hang_steps']} consecutive "
            f"control steps.\n")


def plan_instance(fam: str, i: int, R: dict, version: str) -> dict[str, dict[str, tuple[bytes, int]]]:
    F = FAMILIES[fam]
    fz = HERE / "frozen" / f"{fam}-i{i:02d}"
    inst_b = (fz / "instance.json").read_bytes(); I = json.loads(inst_b)
    oracle_b = (fz / "oracle_actions.npy").read_bytes()
    if I.get("task") != fam or I.get("state_sha") != R["instance_sha"] or I["assets"] != R["assets"]:
        raise RuntimeError(f"{fz}: instance.json does not match instances.json (task, state_sha, assets)")
    tool = (HERE / "shared/rcb_yamlab.py").read_bytes()
    image = f"{REGISTRY}/eai-yamlab:{version}"
    names = list(I["assets"])
    assets_text = " and ".join(f"`{n}` = `{I['assets'][n]}`" for n in names)
    common = {"FAMILY": fam, "PRIV": f"{base(fam, i)}-privileged", "STD": f"{base(fam, i)}-standard", "INST": f"i{i:02d}",
              "ENV": F["env"], "IMAGE": image, "CLIENT_IMAGE": CLIENT["CLIENT_IMAGE"].strip(), "ASSETS_TEXT": assets_text,
              "ASSETS_SHORT": " + ".join(I["assets"][n].split("/")[1] for n in names), "SOURCE": f"{R['file']} demo_{R['demo']}",
              "GOAL_TOML": toml_str(F["goal_toml"]), "ORACLE_SHA": R["oracle_sha"]}
    priv = {"GOAL": F["goal"][0].upper() + F["goal"][1:], "OBJECTS_BLOCK": objects_block(I), "SUCCESS_BLOCK": success_block(fam, I["success_params"], False),
            "README_GOAL": F["readme_goal"], "DIFFICULTY": F["difficulty"], "N_ORACLE": str(R["n_actions"]),
            "FROZEN": f"{fam}-i{i:02d}", "PLACEMENT": placement(I, R["demo"])}
    std = {"STANDARD_GOAL": F["standard_goal"][0].upper() + F["standard_goal"][1:],
           "STANDARD_SUCCESS": success_block(fam, I["success_params"], True)}
    out: dict[str, dict[str, tuple[bytes, int]]] = {}
    for mode, extra in (("privileged", priv), ("standard", std)):
        files: dict[str, tuple[bytes, int]] = {}
        tdir = HERE / "template" / mode
        for p in sorted(tdir.rglob("*")):
            if not p.is_file() or "__pycache__" in p.parts:
                continue
            rel = p.relative_to(tdir).as_posix()
            if rel.endswith(".tmpl"):
                rel = rel[:-5]; data = fill(p.read_text(), {**common, **extra}).encode()
            else:
                data = p.read_bytes()
            files[rel] = (data, 0o755 if rel.endswith(".sh") else 0o644)
        if mode == "privileged":
            for rel in ("environment/rcb_yamlab.py", "tests/rcb_yamlab.py"):
                files[rel] = (tool, 0o644)
            for rel in ("environment/instance.json", "tests/instance.json"):
                files[rel] = (inst_b, 0o644)
            files["solution/oracle_actions.npy"] = (oracle_b, 0o644)
        else:
            files["environment/sim/rcb_yamlab.py"] = (tool, 0o644)
            files["environment/sim/instance.json"] = (inst_b, 0o644)
            for rel, src in (("environment/rcb_client.py", "rcb_client.py"), ("environment/rcb1.py", "rcb1.py"),
                             ("environment/sim/rcb_limited.py", "rcb_limited.py"), ("environment/sim/rcb1.py", "rcb1.py"),
                             ("environment/sim/run.sh", "run.sh")):
                files[rel] = ((LAYER / src).read_bytes(), 0o755 if rel.endswith(".sh") else 0o644)
            req = CLIENT.get("CLIENT_REQUIREMENTS", "client-requirements.txt").strip()
            files["environment/client-requirements.txt"] = ((LAYER / req).read_bytes(), 0o644)
            files["solution/oracle_qpos.npy"] = (oracle_b, 0o644)          # one row per control step, streamed with `hold`
            files["solution/oracle_meta.json"] = (json.dumps({"K": 1, "interpolate": "hold", "source": "the privileged oracle's actions"}, indent=1).encode() + b"\n", 0o644)
        out[f"{base(fam, i)}-{mode}"] = files
    return out


def normalized(planned: dict[str, dict[str, tuple[bytes, int]]], normalize) -> dict[str, dict[str, tuple[bytes, int]]]:
    out = {}
    with tempfile.TemporaryDirectory(prefix="yamlab_mk_") as td:
        for name, files in planned.items():
            for rel, (data, mode) in files.items():
                p = pathlib.Path(td) / name / rel; p.parent.mkdir(parents=True, exist_ok=True); p.write_bytes(data)
                os.chmod(p, 0o755 if mode & 0o100 else 0o644)
        for name in planned:
            normalize(pathlib.Path(td) / name)
        for name in planned:
            t = pathlib.Path(td) / name
            out[name] = {p.relative_to(t).as_posix(): (p.read_bytes(), 0o755 if p.stat().st_mode & 0o100 else 0o644)
                         for p in sorted(t.rglob("*")) if p.is_file() and "__pycache__" not in p.parts}
    return out


def sync(task: pathlib.Path, files: dict, check: bool) -> list[str]:
    diffs = []
    have = {p.relative_to(task).as_posix() for p in task.rglob("*") if p.is_file() or p.is_symlink()} if task.exists() else set()
    have = {h for h in have if "__pycache__" not in h.split("/")}
    for rel in sorted(have - set(files)):
        diffs.append(f"remove {task.name}/{rel}")
        if not check:
            (task / rel).unlink()
    for rel, (data, mode) in sorted(files.items()):
        p = task / rel
        same = p.is_file() and not p.is_symlink() and p.read_bytes() == data and bool(p.stat().st_mode & 0o100) == bool(mode & 0o100)
        if not same:
            diffs.append(f"write  {task.name}/{rel}")
            if not check:
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_bytes(data)
                m = p.stat().st_mode & 0o777
                os.chmod(p, m | 0o111 if mode & 0o100 else m & ~0o111)
    if not check and task.exists():
        for d in sorted((p for p in task.rglob("*") if p.is_dir()), key=lambda p: -len(p.parts)):
            if not any(d.iterdir()):
                d.rmdir()
    return diffs


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    inst = json.loads((HERE / "instances.json").read_text())["families"]
    version = (ROOT / "images/yamlab/VERSION").read_text().strip()
    normalize = normalizer()
    diffs, made = [], set()
    for fam in FAMILIES:
        for R in inst[fam]:
            i = R["id"]                  # the instance keeps its index (the 2026-10-10 prune left gaps; PROTOCOL §2.8)
            for name, files in normalized(plan_instance(fam, i, R, version), normalize).items():
                made.add(name); diffs += sync(ROOT / "tasks" / name, files, a.check)
    for t in sorted((ROOT / "tasks").glob("yamlab-*")):
        if t.is_dir() and t.name not in made:
            diffs.append(f"stale  {t.name} (not in instances.json)")
    for d in diffs:
        print(d)
    print(f"{'checked' if a.check else 'generated'} {len(made)} YAMLab task dirs: {len(diffs)} difference(s)")
    return 1 if (a.check and diffs) else 0


if __name__ == "__main__":
    sys.exit(main())
