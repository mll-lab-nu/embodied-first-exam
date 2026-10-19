#!/usr/bin/env python3
"""Seeds (PROTOCOL §2.13): ci_checks/check-seeds.py and scripts/task_seed.py on a real task pair given a second
allowed seed (in a temporary copy of the repository's task directories). Standard library only."""
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PAIR = "roboolympics-fun-sprint-i00"
CHECK = [sys.executable, str(ROOT / "ci_checks/check-seeds.py")]
SEED = [sys.executable, str(ROOT / "scripts/task_seed.py")]
sys.path.insert(0, str(ROOT / "scripts"))
import task_conventions as tc  # noqa: E402  (task_dir: the task tree)


def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    return r.returncode, r.stdout + r.stderr


def with_seeds(toml: Path, allowed: str) -> None:
    s = toml.read_text()
    toml.write_text(re.sub(r"(?m)^allowed = .*$", f"allowed = {allowed}", s, count=1))


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
            assert re.search(r"(?m)^default = 7$", (m / "task.toml").read_text()), t.name
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
        assert rc != 0 and "seeds.default 0 is not in seeds.allowed" in out, out
        # a range and "any": only for a task that builds a seed's instance itself (build = "runtime")
        shutil.rmtree(priv / "tests" / "seeds")
        for allowed in ("{ from = 0, to = 100 }", '"any"'):
            for t in (priv, std):
                with_seeds(t / "task.toml", allowed)
            rc, out = run(CHECK + [str(priv), str(std)])
            assert rc != 0 and 'build = "runtime"' in out, (allowed, out)
            for t in (priv, std):
                s = (t / "task.toml").read_text()
                (t / "task.toml").write_text(re.sub(r"(?m)^(oracle = \[.*\])$", r'\1\nbuild = "runtime"', s, count=1))
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
                s = (t / "task.toml").read_text()
                (t / "task.toml").write_text(s.replace('build = "runtime"\n', ""))
        with_seeds(priv / "task.toml", "{ from = 5, to = 100 }")
        s = (priv / "task.toml").read_text()
        (priv / "task.toml").write_text(re.sub(r"(?m)^(oracle = \[.*\])$", r'\1\nbuild = "runtime"', s, count=1))
        rc, out = run(CHECK + [str(priv)])
        assert rc != 0 and "is not in seeds.allowed" in out, out
    print("task seeds: check-seeds.py and task_seed.py hold on a pair with two seeds, a range and \"any\"")
    return 0


if __name__ == "__main__":
    sys.exit(main())
