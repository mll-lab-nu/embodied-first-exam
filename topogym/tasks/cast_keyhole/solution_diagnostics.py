"""Plot the rejected interval without presenting it as an executable demo."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from .solution import load_solution, source_fingerprints


def draw(solution, certificate, output):
    report = json.loads(Path(certificate).read_text())
    if report["fingerprint"] != source_fingerprints(solution):
        raise ValueError("Stale diagnostic certificate")
    _, meshes, _, motions = load_solution(solution)
    failed = [(m, s) for m, s in zip(motions, report["segments"]) if not s["passed"]]
    if not failed:
        raise ValueError("No rejected interval to illustrate")
    motion, evidence = failed[0]
    poses = [motion.pose(u) for u in (0., evidence["witness_u"], 1.)]
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.collections import PolyCollection

    fig, axes = plt.subplots(3, 3, figsize=(12, 10))
    all_points = np.concatenate([meshes[0].vertices] + [meshes[1].vertices@r.T+t for r, t in poses])*1000
    low, high = all_points.min(0)-5, all_points.max(0)+5
    for row, (i, j, label) in enumerate(((0, 1, "XY / top"), (0, 2, "XZ / front"), (1, 2, "YZ / side"))):
        for column, (r, t) in enumerate(poses):
            ax = axes[row, column]
            for mesh, rotation, position, color in (
                (meshes[0], np.eye(3), np.zeros(3), "#bc953c"),
                (meshes[1], r, t, "#d05858" if column == 1 else "#7895ae"),
            ):
                v = (mesh.vertices@rotation.T+position)*1000
                ax.add_collection(PolyCollection(v[mesh.faces][..., [i, j]],
                                  facecolor=color, edgecolor=color, linewidth=.15, alpha=.7))
            ax.set(xlim=(low[i], high[i]), ylim=(low[j], high[j]), xlabel=label+" (scene mm)", aspect="equal")
            if row == 0:
                ax.set_title(("Clear start", "REJECTED: intermediate collision", "Clear endpoint")[column])
    fig.suptitle("Cast Keyhole: missing middle connection\n"
                 f"SAT overlap witness {-evidence['gap_m']*1000:.3f} mm; diagnostic only, not a demo")
    fig.tight_layout()
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output, dpi=150)
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("solution", "certificate", "output"):
        parser.add_argument("--"+name, type=Path, required=True)
    args = parser.parse_args()
    draw(args.solution, args.certificate, args.output)


if __name__ == "__main__":
    main()
