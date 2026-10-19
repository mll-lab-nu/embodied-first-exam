__version__ = "0.5.4.dev1"

import os as _os
_OLD = sorted(k for k in _os.environ if k.startswith(("ROBOSAFE_", "ROBOSAFEBENCH_")))
if _OLD:   # renamed: ROBOSAFE_* -> ROBOSAFEBENCH_* (0.5.4) -> ESE_* (Embodied Safety Exam); an old name would otherwise be ignored silently
    raise RuntimeError(f"environment variables {_OLD} were renamed to ESE_*; rename or unset them")
