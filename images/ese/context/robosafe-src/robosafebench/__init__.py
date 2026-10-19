__version__ = "0.5.4.dev1"

import os as _os
_OLD = sorted(k for k in _os.environ if k.startswith("ROBOSAFE_"))
if _OLD:   # renamed in 0.5.4: ROBOSAFE_* -> ROBOSAFEBENCH_*; an old name would otherwise be ignored silently
    raise RuntimeError(f"environment variables {_OLD} were renamed to ROBOSAFEBENCH_* in 0.5.4; rename or unset them")
