"""Authoring negative example: the open hand sweeps through the mug at mid height (knock-off, cup_moved).

Usage: python tools/knock.py <out.npz> [sharpa|wuji]
"""
import argparse
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np

import demo
from runtime import Session


def knock_rows(hand="sharpa"):
    s = Session(hand=hand)
    c = demo.Controller(s, argparse.Namespace())
    beside = c.target.copy()
    beside[:3] = [0.30, 0.015, 1.02]
    c.move(beside, 60, "move beside the cup")
    low = beside.copy()
    low[2] = 0.97
    c.move(low, 40, "lower")
    sweep = low.copy()
    sweep[0] = 0.62
    c.move(sweep, 80, "sweep through the cup")
    while not s.done and len(c.rows) < 400:
        c.send(c.target, "hold")
    return s, np.asarray(c.rows)


if __name__ == "__main__":
    session, rows = knock_rows(sys.argv[2] if len(sys.argv) > 2 else "sharpa")
    st = session.status()
    print(st["reason"], st["steps"], st["failure_detail"])
    session.save_trajectory(rows, sys.argv[1])
