"""Mouse-driven 3D viewer for the Hedgehog, Horseshoe and Slotted Post Ring scenes.

For understanding the puzzles only: MuJoCo here is not the simulator's physics
(Genesis is), and nothing it shows is evidence or a success label.
"""
import os

# Before numpy loads: otherwise ~11 idle OpenBLAS threads spin (1.35 cores measured).
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
