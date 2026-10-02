"""Interactive 3D design aid for task variants (MuJoCo Web Viewer + FCL checks).

Design intuition only: nothing here is physics evidence, qualification or a
success label. Genesis remains the only physics path of the simulator.
"""

import os

# Before numpy loads: the viewer's small matrix products otherwise keep ~11 OpenBLAS
# threads spinning (measured 1.35 cores while idle; 0.08 with one thread).
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
