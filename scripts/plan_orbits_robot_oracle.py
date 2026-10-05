#!/usr/bin/env python3
"""Robot-aware Orbits oracle in a MuJoCo rope model (planning witness, not a Genesis run).

Each pass searches fresh bights that delete one stopper-ball letter of the exact word, checks ALOHA
IK and arm collisions before simulating, then executes carry, aperture hand-over and two-arm hook.
Arguments are those of ``topogym.planning.orbits.robot_oracle``; the output directory must not exist.

  python scripts/plan_orbits_robot_oracle.py easy runs/oracle_dev/orbits_easy_01 --plumb --plumb-first
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

if __name__ == "__main__":
    from topogym.planning.orbits.robot_oracle import main
    main()
