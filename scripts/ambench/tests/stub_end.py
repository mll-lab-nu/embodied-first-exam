"""Stand-in for `rcb_limited.py end` in test_standard_grading.py: exits with $STUB_END_RC (0: the episode was dumped)."""
import os, sys
sys.exit(int(os.environ.get("STUB_END_RC", "0")))
