"""Rigid assembly tasks: annotation geometry, scene build, task base class and the
grasp / insert / screw skills shared by the assembly tasks.

Only :mod:`.geometry` is importable without a simulator; :mod:`.task`, :mod:`.scene`
and :mod:`.skills` import Isaac Lab lazily inside the methods that need it.
"""

from .geometry import HeldAxis, Slot, load_grasp_candidates, load_held_axis, load_slot  # noqa: F401

try:
    from .policy import RigidAssemblyPolicy  # noqa: F401
except ImportError:  # not part of this copy
    pass
try:
    from .skills import GraspSkill, InsertSkill, ReachSkill, ScrewSkill  # noqa: F401
except ImportError:  # not part of this copy
    pass
from .task import PartSpec, RigidAssemblyTask  # noqa: F401
