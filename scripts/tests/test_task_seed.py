#!/usr/bin/env python3
"""Seeds (PROTOCOL §2): ci_checks/check-seeds.py and scripts/task_seed.py on a real task pair given a second
allowed seed (in a temporary copy of the repository's task directories). Standard library only."""
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PAIR = "embodied-olympics-fun-sprint-i00"
PINNED = "metaworldplus-basketball-i00"         # a pair whose sidecar compose pins the instance's hashes, with a solution
CHECK = [sys.executable, str(ROOT / "ci_checks/check-seeds.py")]
SEED = [sys.executable, str(ROOT / "scripts/task_seed.py")]
sys.path.insert(0, str(ROOT / "scripts"))
import task_conventions as tc  # noqa: E402  (task_dir: the task tree)


def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    return r.returncode, r.stdout + r.stderr


def with_seeds(toml: Path, allowed: str) -> None:
    """`[metadata.seeds] allowed = <allowed>` (the table appended when the task has none; its other keys kept)."""
    s = toml.read_text()
    if re.search(r"(?m)^\[metadata\.seeds\]$", s):
        s = re.sub(r"(?m)^allowed = .*$", f"allowed = {allowed}", s, count=1)
    else:
        s = s.rstrip("\n") + f"\n\n[metadata.seeds]\nallowed = {allowed}\n"
    toml.write_text(s)


def with_build(toml: Path, build: str | None) -> None:
    s = re.sub(r'(?m)^build = ".*"\n', "", toml.read_text())
    if build:
        s = re.sub(r"(?m)^(allowed = .*)$", rf'\1\nbuild = "{build}"', s, count=1)
    toml.write_text(s)


def pinned_pair() -> None:
    """A seed's other files: a per-instance file in every instance place, a file further down at its path (the seed's
    solution), and seed.toml's text replacements (the hashes compose pins, a sentence of the instruction)."""
    with tempfile.TemporaryDirectory() as td:
        tasks = Path(td) / "tasks"
        tasks.mkdir()
        priv, std = tasks / f"{PINNED}-privileged", tasks / f"{PINNED}-standard"
        for t in (priv, std):
            shutil.copytree(tc.task_dir(t.name), t, symlinks=True)
            with_seeds(t / "task.toml", "[0, 5]")
        compose = (std / "environment" / "docker-compose.yaml").read_text()
        start = re.search(r'RCB_START_SHA: "([0-9a-f]+)"', compose).group(1)
        line = "Pick up the ball and place it through the basketball hoop."   # in both instructions
        d = priv / "tests" / "seeds" / "5"
        (d / "solution").mkdir(parents=True)
        (d / "instance.npz").write_bytes(b"seed 5 instance")
        (d / "solution" / "oracle.npz").write_bytes(b"seed 5 oracle")
        (d / "seed.toml").write_text(f'[[replace]]\nold = "{start}"\nnew = "{"5" * 64}"\n\n'
                                     f'[[replace]]\nold = {line!r}\nnew = "seed five"\n'.replace("'", '"'))
        rc, out = run(CHECK + [str(priv), str(std)])
        assert rc == 0, out
        out_dir = Path(td) / "run"
        for t, places in ((priv, ["environment", "tests"]), (std, ["environment/sim"])):
            rc, out = run(SEED + ["materialize", str(t), "--seed", "5", "--out", str(out_dir)])
            assert rc == 0, out
            m = out_dir / t.name
            for p in places:
                assert (m / p / "instance.npz").read_bytes() == b"seed 5 instance", (t.name, p)
            assert (m / "solution" / "oracle.npz").read_bytes() == b"seed 5 oracle", t.name
            text = (m / "instruction.md").read_text()
            assert "seed five" in text and line not in text, t.name
            assert start not in "".join(f.read_text(errors="replace") for f in m.rglob("*.yaml")), t.name
        assert f'RCB_START_SHA: "{"5" * 64}"' in (out_dir / std.name / "environment" / "docker-compose.yaml").read_text()
        rc, out = run(SEED + ["materialize", str(std), "--seed", "0", "--out", str(Path(td) / "run0")])
        assert rc == 0 and start in (Path(td) / "run0" / std.name / "environment" / "docker-compose.yaml").read_text(), out
        # files that would land nowhere, text that is in no file, a seed.toml with anything but replacements
        for rel, body, msg in (("goal.png", b"x", "in an instance place"),
                               ("solution/other.npz", b"x", "has solution/other.npz to replace"),
                               ("tests/seeds/1/x", b"x", "not a per-seed file")):
            (d / rel).parent.mkdir(parents=True, exist_ok=True)
            (d / rel).write_bytes(body)
            rc, out = run(CHECK + [str(priv)])
            assert rc != 0 and msg in out, (rel, out)
            (d / rel).unlink()
        shutil.rmtree(d / "tests", ignore_errors=True)
        good = (d / "seed.toml").read_text()
        for bad, msg in (('[[replace]]\nold = "no such text anywhere"\nnew = "x"\n', "is in no text file of the pair"),
                         ('[[replace]]\nold = "a"\nnew = "a"\n', "only [[replace]] tables"),
                         ('build = "runtime"\n', "only [[replace]] tables")):
            (d / "seed.toml").write_text(bad)
            rc, out = run(CHECK + [str(priv)])
            assert rc != 0 and msg in out, (bad, out)
        (d / "seed.toml").write_text(good)
        (d / "instance.npz").unlink()
        rc, out = run(CHECK + [str(priv)])
        assert rc != 0 and "allowed seed 5 has no frozen instance" in out, out


def main() -> int:
    with tempfile.TemporaryDirectory() as td:
        tasks = Path(td) / "tasks"
        tasks.mkdir()
        priv, std = tasks / f"{PAIR}-privileged", tasks / f"{PAIR}-standard"
        for t in (priv, std):
            shutil.copytree(tc.task_dir(t.name), t, symlinks=True)
        rc, out = run(CHECK + [str(priv), str(std)])
        assert rc == 0, out
        # a second seed: its frozen instance under the privileged task's tests/seeds/7/
        d = priv / "tests" / "seeds" / "7"
        d.mkdir(parents=True)
        inst = (priv / "tests" / "instance.json").read_text()
        (d / "instance.json").write_text(inst.replace('"seed": 0', '"seed": 7', 1))
        for t in (priv, std):
            with_seeds(t / "task.toml", "[0, 7]")
        rc, out = run(CHECK + [str(priv), str(std)])
        assert rc == 0, out
        rc, out = run(SEED + ["pick", str(std), "--rng", "1"])
        assert rc == 0 and out.strip() in ("0", "7"), out
        # materialize: the seed's instance in every place the task runs and grades from, the seed recorded
        out_dir = Path(td) / "run"
        for t, places in ((priv, ["environment", "tests"]), (std, ["environment/sim"])):
            rc, out = run(SEED + ["materialize", str(t), "--seed", "7", "--out", str(out_dir)])
            assert rc == 0, out
            m = out_dir / t.name
            for p in places:
                assert (m / p / "instance.json").read_text() == (d / "instance.json").read_text(), (t.name, p)
            assert not (m / "tests" / "seeds").exists()
            assert re.search(r"(?m)^instance_seed = 7$", (m / "task.toml").read_text()), t.name
        rc, out = run(SEED + ["materialize", str(priv), "--seed", "3", "--out", str(Path(td) / "run3")])
        assert rc != 0 and "not allowed" in out, out
        # the rules: a missing instance, a stale one, a seeds directory in the agent's build context, default not allowed
        with_seeds(priv / "task.toml", "[0, 7, 9]")
        with_seeds(std / "task.toml", "[0, 7, 9]")
        rc, out = run(CHECK + [str(std)])
        assert rc != 0 and "allowed seed 9 has no frozen instance" in out, out
        with_seeds(priv / "task.toml", "[0]")
        rc, out = run(CHECK + [str(priv)])
        assert rc != 0 and "is not the instance of an allowed non-default seed" in out, out
        with_seeds(priv / "task.toml", "[0, 7]")
        (priv / "environment" / "seeds").mkdir()
        rc, out = run(CHECK + [str(priv)])
        assert rc != 0 and "a `seeds` directory where the agent's image is built from" in out, out
        (priv / "environment" / "seeds").rmdir()
        with_seeds(priv / "task.toml", "[7]")
        rc, out = run(CHECK + [str(priv)])
        assert rc != 0 and "(instance_seed) 0 is not in seeds.allowed" in out, out
        # a range and "any": only for a task that builds a seed's instance itself (build = "runtime")
        shutil.rmtree(priv / "tests" / "seeds")
        for allowed in ("{ from = 0, to = 100 }", '"any"'):
            for t in (priv, std):
                with_seeds(t / "task.toml", allowed)
            rc, out = run(CHECK + [str(priv), str(std)])
            assert rc != 0 and 'build = "runtime"' in out, (allowed, out)
            for t in (priv, std):
                with_build(t / "task.toml", "runtime")
            rc, out = run(CHECK + [str(priv), str(std)])
            assert rc == 0, (allowed, out)
            rc, out = run(SEED + ["pick", str(priv), "--rng", "3"])
            seed = int(out)
            assert rc == 0 and (allowed.startswith('"any"') or 0 <= seed <= 100), out
            o = Path(td) / f"run-{seed}-{len(allowed)}"
            for t, places in ((priv, ["environment", "tests"]), (std, ["environment/sim"])):
                rc, out = run(SEED + ["materialize", str(t), "--seed", str(seed), "--out", str(o)])
                assert rc == 0, out
                for p in places:                            # the seed where the task builds its instance from
                    assert (o / t.name / p / "seed").read_text() == f"{seed}\n", (t.name, p)
            for t in (priv, std):                           # back to frozen for the next form
                with_build(t / "task.toml", None)
        with_seeds(priv / "task.toml", "{ from = 5, to = 100 }")
        with_build(priv / "task.toml", "runtime")
        rc, out = run(CHECK + [str(priv)])
        assert rc != 0 and "is not in seeds.allowed" in out, out
    pinned_pair()
    print("task seeds: check-seeds.py and task_seed.py hold on a pair with two seeds, a range and \"any\"")
    return 0


if __name__ == "__main__":
    sys.exit(main())
