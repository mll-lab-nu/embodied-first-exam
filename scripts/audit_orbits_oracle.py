#!/usr/bin/env python3
"""ALOHA IK and two-arm timeline audit of a recorded Orbits oracle run, plus per-phase cord stretch.

  python scripts/audit_orbits_oracle.py easy runs/oracle_dev/orbits_easy_01 --fixed-arms
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

if __name__ == "__main__":
    from topogym.planning.orbits.ik_audit import main
    from topogym.planning.orbits.stretch import stretch_by_phase
    main()
    variant, run = sys.argv[1], Path(sys.argv[2])
    stretch = stretch_by_phase(run/"frames.npz", variant)
    (run/"stretch_by_phase.json").write_text(json.dumps(stretch, indent=1))
    print(json.dumps(stretch))
