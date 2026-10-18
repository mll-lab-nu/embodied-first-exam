import json
from pathlib import Path
import numpy as np
from control_public.weights import Network


class Policy(Network):
    def __init__(self, path):
        super().__init__(path, "g1")
        metadata = json.loads((Path(__file__).parent / "actuator_abi.json").read_text())
        self.joints = metadata["joint_names"].split(",")
        for key, attr in [
            ("joint_stiffness", "kp"),
            ("joint_damping", "kd"),
            ("default_joint_pos", "default"),
            ("action_scale", "scale"),
        ]:
            setattr(self, attr, np.array([float(x) for x in metadata[key].split(",")]))
