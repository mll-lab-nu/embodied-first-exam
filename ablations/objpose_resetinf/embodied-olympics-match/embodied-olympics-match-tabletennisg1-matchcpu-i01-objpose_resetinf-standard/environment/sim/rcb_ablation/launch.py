"""The sim container's launcher in an ablation's task dir: core/launch.py unchanged (its metering proxies, its checks),
except that the match service runs as `python -m rcb_ablation.serve` (core.serve with the ablation's routes)."""
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))         # /srv: core/ and rcb_ablation/
sys.path.insert(0, ROOT)


class _Subprocess:
    """core.launch's `subprocess`: the match service's command replaced, every other call unchanged."""

    def __getattr__(self, name):
        return getattr(subprocess, name)

    @staticmethod
    def Popen(args, *a, **kw):
        if list(args[1:]) == ["-m", "core.serve"]:
            args = [args[0], "-m", "rcb_ablation.serve"]
        return subprocess.Popen(args, *a, **kw)


if __name__ == "__main__":
    import core.launch as L
    L.subprocess = _Subprocess()
    L.main()
