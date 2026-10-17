"""Run named test functions of a sport's tests/test_*.py in its image (tools/check stage 6: the [modes] b9_test,
robot and mode rule 2; the generic suite of core/testkit.py runs only the exploit tests).

    python3 -m skilleval.runtest /srv/sport/plugin.py TEST_NAME [...] --json OUT"""

from __future__ import annotations

import importlib.util
import json
import sys
import traceback
from pathlib import Path


def main(argv):
    plugin, names = Path(argv[0]), [a for a in argv[1:] if not a.startswith("--")]
    out = argv[argv.index("--json") + 1] if "--json" in argv else None
    names = [n for n in names if n != out]
    sys.path[:0] = [str(plugin.parent), str(plugin.parent.parent)]
    funcs = {}
    for p in sorted((plugin.parent / "tests").glob("test_*.py")):
        spec = importlib.util.spec_from_file_location(f"sport_test_{p.stem}", p)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        funcs.update({k: v for k, v in vars(mod).items() if k.startswith("test_") and callable(v)})
    rows = []
    for n in names:
        try:
            funcs[n]()
            rows.append({"name": n, "ok": True, "detail": (funcs[n].__doc__ or "").strip().split("\n")[0]})
        except Exception:  # noqa: BLE001
            rows.append({"name": n, "ok": False, "detail": traceback.format_exc()[-600:]})
    if out:
        Path(out).write_text(json.dumps(rows, indent=1))
    for r in rows:
        print(f"{'ok  ' if r['ok'] else 'FAIL'} {r['name']}: {r['detail']}")
    return 0 if all(r["ok"] for r in rows) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
