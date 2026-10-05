#!/usr/bin/env python3
"""Measure each RoboPaint pair's reference solution with the process-rule quantities (the source of rules.json's
reference_path_mm and reference_mark_width_mm). Runs in the base image (SAPIEN needs the GPU to build the scene), from
the repository root:

    docker run --rm --gpus all -v "$PWD:/repo:ro" -w /repo ghcr.io/mll-lab-nu/eai-robopaint:0.2.0 \
        python scripts/robopaint_strict/measure_reference.py [robopaint-<family>-<target>-i00 ...] > reference.jsonl

Per pair, in a fresh process: replay solution/oracle_qpos.npy from the graders' copy of the RoboPaint instance (tests/) with
rcb_brush_strict's Session and print one JSON line: path_mm (the brush tip's path pressed on the main sheet with ink or paint),
mark_width_mm (calligraphy and lettering: the strokes' own mark area / path_mm), longest_stroke_mm, scribble_max, the strokes and
the picture rule's verdict. rules.json takes path_mm as reference_path_mm and mark_width_mm as reference_mark_width_mm.
"""

import json, os, pathlib, re, subprocess, sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
CHILD = r"""
import json, sys
import numpy as np
tests, here, oracle = sys.argv[1:4]
sys.path[:0] = [tests, here]
import rcb_brush_strict as S
s = S.Session(instance=tests + "/instance.json", render=False)
st = s.replay(np.load(oracle, allow_pickle=False).astype(np.float32))
keys = ("path_mm", "mark_width_mm", "longest_stroke_mm", "scribble_max", "n_strokes", "image_success", "success", "final_reward")
print(json.dumps({k: st.get(k) for k in keys}))
"""


def main() -> int:
    pairs = sys.argv[1:] or sorted(
        p.name[: -len("-privileged")]
        for p in (ROOT / "tasks").glob("robopaint-*-i00-privileged")
        if re.match(r"^robopaint-(kaishu|xingshu|lettering|acrylic|oil)-", p.name)
    )
    for base in pairs:
        t = ROOT / "tasks" / f"{base}-privileged"
        p = subprocess.run(
            [
                sys.executable,
                "-c",
                CHILD,
                str(t / "tests"),
                str(ROOT / "scripts" / "robopaint_strict"),
                str(t / "solution" / "oracle_qpos.npy"),
            ],
            capture_output=True,
            text=True,
            env={**os.environ, "RCB_SESSION_LOG": "", "RCB_RENDER": "0", "PYTHONDONTWRITEBYTECODE": "1"},
        )
        lines = [l for l in p.stdout.splitlines() if l.startswith("{")]
        rec = json.loads(lines[-1]) if lines else {"error": f"rc={p.returncode}: {p.stderr[-300:]}"}
        print(json.dumps({"pair": base, **rec}), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
