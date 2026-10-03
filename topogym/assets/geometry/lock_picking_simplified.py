"""Two-rotor, two-tab geometry using the original lock's mesh constructors."""
from dataclasses import dataclass
from typing import ClassVar

from .lock_picking import LockGeometry


@dataclass(frozen=True)
class TwoDiscLockGeometry(LockGeometry):
    disc_count: ClassVar[int] = 2
    tab_count: ClassVar[int] = 2
    pitch: float = .150
    grip_offset: float = .345
    slots: tuple = ((0.,), (0.,))
    initial_disc_deg: tuple = (0., 0.)
