#!/usr/bin/env python3
"""Measure each RoboPaint pair's reference solution with the process-rule quantities (the source of rules.json's
reference_path_mm and reference_mark_width_mm). Runs in the base image (SAPIEN needs the GPU to build the scene), from
the repository root:

    docker run --rm --gpus all -v "$PWD:/repo:ro" -w /repo ghcr.io/mll-lab-nu/eai-robopaint:0.2.0 \
        python scripts/robopaint_strict/measure_reference.py [robopaint-<family>-<target>-i<NN> ...] > reference.jsonl

Per pair, in a fresh process: replay solution/oracle_qpos.npy from the graders' copy of the instance (tests/) with
rcb_brush_strict's Session and print one JSON line: path_mm (the brush tip's path pressed on the main sheet with ink or paint),
mark_width_mm (calligraphy and lettering: the strokes' own mark area / path_mm), longest_stroke_mm, scribble_max, the strokes and
the picture rule's verdict. rules.json takes path_mm as reference_path_mm and mark_width_mm as reference_mark_width_mm.
For a family whose rule counts strokes (rules.json families: stroke_gap_mm, mark_min_width_mm; the calligraphy families), the
replay is scored with those two and no limit on a stroke's length, and longest_counted_stroke_mm (the reference's longest marked
piece) is rules.json's reference_longest_stroke_mm.
"""

import json, os, pathlib, re, subprocess, sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
CHILD = r"""
import json, sys
import numpy as np
tests, here, oracle, fam = sys.argv[1:5]
sys.path[:0] = [tests, here]
import rcb_brush_strict as S
F = json.load(open(here + "/rules.json"))["families"][fam]
s = S.Session(instance=tests + "/instance.json", render=False)
if "stroke_gap_mm" in F:  # the counted strokes: the marked pieces, without a length limit
    s.inst["target"]["success"].update(stroke_gap_mm=F["stroke_gap_mm"], mark_min_width_mm=F["mark_min_width_mm"], max_stroke_path_mm=1e12)
st = s.replay(np.load(oracle, allow_pickle=False).astype(np.float32))
keys = ("path_mm", "mark_width_mm", "longest_stroke_mm", "scribble_max", "n_strokes", "n_marked_pieces", "n_strokes_counted",
        "longest_counted_stroke_mm", "scribble_share", "image_success", "success", "final_reward")
print(json.dumps({k: st.get(k) for k in keys}))
"""


def main() -> int:
    pairs = sys.argv[1:] or sorted(
        p.name[: -len("-privileged")]
        for p in (ROOT / "tasks").glob("robopaint-*-i[0-9][0-9]-privileged")
        if re.match(r"^robopaint-(kaishu|xingshu|caoshu|lettering|acrylic|oil)-", p.name)
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
                base.split("-")[1],
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
