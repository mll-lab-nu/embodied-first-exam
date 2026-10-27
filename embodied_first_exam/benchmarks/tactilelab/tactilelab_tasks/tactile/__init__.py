"""Tactile sensing: taxel raycast (warp) + Taxim rendering for the GelSight Mini.

Modules:

* :mod:`.raycast`: ``TaxelGrid`` and ``MeshTarget`` (gel pose + meshes -> height map);
* :mod:`.taxim`: ``TaximRenderer`` (height map -> RGB), MIT-licensed port;
* :mod:`.sensor`: ``GelSightMini`` combining the two;
* :mod:`.mesh_sources`: meshes from USD prims (lazy ``pxr``) and procedural shapes.

Importing the package pulls in torch and warp; ``mesh_sources`` needs ``pxr``
only when a USD helper is called.
"""

from .raycast import MeshTarget, TaxelGrid
from .sensor import GelSightMini
from .taxim import TaximRenderer, default_calib_dir

__all__ = ["GelSightMini", "MeshTarget", "TaxelGrid", "TaximRenderer", "default_calib_dir"]


def sensor_device(physics_device: str) -> str:
    """Device of the tactile raycast / Taxim render: the physics device, except that CPU physics (bit-exact replays)
    still renders on the first GPU when one is available. The tactile path never feeds back into the physics."""
    if str(physics_device).startswith("cpu"):
        try:
            import torch

            if torch.cuda.is_available():
                return "cuda:0"
        except Exception:
            pass
    return physics_device
