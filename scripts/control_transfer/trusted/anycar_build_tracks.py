"""Offline F1DB SVG conversion. Requires PyYAML/svgpathtools only for rebuilding assets."""

import argparse
import datetime
import hashlib
import json
from pathlib import Path
import subprocess
import xml.etree.ElementTree as ET


def build(source, output, cutoff):
    import numpy as np
    import yaml
    from svgpathtools import Document, Path as SVGPath, Line

    layouts = {}
    for file in sorted(source.glob("src/data/seasons/*/races/*/race.yml")):
        race = yaml.safe_load(file.read_text())
        if datetime.date.fromisoformat(str(race["date"])) > cutoff:
            continue
        entry = layouts.setdefault(race["circuitLayoutId"], dict(circuit_id=race["circuitId"], years=[]))
        entry["years"].append(int(str(race["date"])[:4]))
    result = {}
    for layout, meta in sorted(layouts.items()):
        path = source / f"src/assets/circuits/black/{layout}.svg"
        xml = ET.parse(path).getroot()
        elements = list(xml.iter("{http://www.w3.org/2000/svg}path"))
        if len(elements) != 1:
            raise ValueError(f"Unsupported SVG structure: {layout}")
        (curve,) = Document(str(path), strict_transform_parsing=True).paths()
        bridges = []
        parts = curve.continuous_subpaths()
        ordered = list(parts.pop(0))
        while parts:
            choices = [
                (abs(ordered[-1].end - point), i, reverse)
                for i, part in enumerate(parts)
                for reverse, point in ((False, part.start), (True, part.end))
            ]
            gap, i, reverse = min(choices)
            part = parts.pop(i)
            if reverse:
                part = part.reversed()
            if gap > 0.02 * curve.length():
                raise ValueError(f"Unrepairable SVG gap: {layout}")
            if gap:
                bridges.append(gap)
                ordered.append(Line(ordered[-1].end, part.start))
            ordered.extend(part)
        gap = abs(ordered[-1].end - ordered[0].start)
        if gap > 0.02 * curve.length():
            raise ValueError(f"Unrepairable closure: {layout}")
        if gap:
            bridges.append(gap)
            ordered.append(Line(ordered[-1].end, ordered[0].start))
        curve = SVGPath(*ordered)
        # Dense per-segment sampling followed by uniform arc-length resampling.
        dense = []
        for segment in curve:
            for t in np.linspace(0, 1, max(8, int(segment.length() * 4)), endpoint=False):
                z = segment.point(t)
                dense.append([z.real, -z.imag])
        xy = np.asarray(dense + dense[:1])
        distance = np.r_[0, np.cumsum(np.linalg.norm(np.diff(xy, axis=0), axis=1))]
        sample = np.linspace(0, distance[-1], 1024, endpoint=False)
        points = np.column_stack([np.interp(sample, distance, xy[:, k]) for k in (0, 1)])
        # Gaussian smoothing at 0.2% of perimeter removes SVG join artifacts.
        weights = np.exp(-0.5 * (np.arange(-8, 9) / 2.0) ** 2)
        points = sum(w * np.roll(points, j, axis=0) for j, w in zip(range(-8, 9), weights)) / weights.sum()
        points -= (points.min(axis=0) + points.max(axis=0)) / 2
        length = np.linalg.norm(np.roll(points, -1, axis=0) - points, axis=1).sum()
        points /= length
        info = yaml.safe_load((source / f"src/data/circuits/{meta['circuit_id']}.yml").read_text())
        geometry = next(x for x in info["layouts"] if x["id"] == layout)
        # This source asset is disjoint/overlapping, unlike the other complete
        # outlines. Preserve provenance but do not silently invent a drivable loop.
        available = layout != "buenos-aires-1"
        result[layout] = dict(
            available=available,
            unavailable_reason=None if available else "Disjoint overlapping SVG strokes; requires curated centerline",
            circuit_id=meta["circuit_id"],
            name=info["fullName"],
            years=sorted(set(meta["years"])),
            source_length_m=float(geometry["length"]) * 1000,
            source_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
            svg_join_bridges=bridges,
            source_path=str(path.relative_to(source)),
            points=np.round(points, 9).tolist() if available else None,
        )
    document = dict(
        schema="anycar-circuit-catalog/1",
        source="https://github.com/f1db/f1db",
        revision=subprocess.check_output(["git", "-C", str(source), "rev-parse", "HEAD"], text=True).strip(),
        license="CC-BY-4.0",
        cutoff=str(cutoff),
        geometry="SVG-derived planar schematic; smoothed and arc-length resampled; not surveyed geometry",
        circuits=result,
    )
    output.write_text(json.dumps(document, separators=(",", ":"), ensure_ascii=False) + "\n")
    print(json.dumps(dict(venues=len({v["circuit_id"] for v in result.values()}), layouts=len(result))))


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--source", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--cutoff", type=datetime.date.fromisoformat, default=datetime.date(2026, 10, 13))
    a = p.parse_args()
    build(a.source, a.output, a.cutoff)
