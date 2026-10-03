"""Append-only development evidence; never issues a robot qualification."""
import json
import os
from pathlib import Path
import time

from topogym.utils.io import sha256_file, write_json_atomic
from .contracts import json_value


class Evidence:
    def __init__(self, output, session_id):
        self.output = Path(output)
        self.session_id = session_id
        self.exploration = False
        self.costs = {}
        self.stream = (self.output / "events.jsonl").open("x", buffering=1)
        root = Path(__file__).resolve().parents[3]
        self.source = {str(p.relative_to(root)): sha256_file(p)
                       for p in sorted((root / "topogym").rglob("*.py"))}
        write_json_atomic(self.output / "source_manifest.json", self.source, mode=0o600)

    def event(self, kind, *, intervention=False, **values):
        self.exploration |= intervention
        row = json_value(dict(kind=kind, session_id=self.session_id, time=time.time(),
                              exploration=self.exploration, **values))
        self.stream.write(json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n")
        self.stream.flush()
        os.fsync(self.stream.fileno())

    def timing(self, stage, seconds):
        row = self.costs.setdefault(stage, dict(calls=0, seconds=0.))
        row["calls"] += 1
        row["seconds"] += seconds

    def report(self, **values):
        report = dict(session_id=self.session_id, exploration=self.exploration,
                      formal_qualification=False, robot_success_certified=False,
                      detailed_timing_file="timings.json", timing_trace="profile.jsonl",
                      timing=self.costs, source_manifest="source_manifest.json", **values)
        path = self.output / "report.json"
        write_json_atomic(path, report, mode=0o600)
        return dict(report=str(path), **report)

    def close(self):
        self.stream.close()
