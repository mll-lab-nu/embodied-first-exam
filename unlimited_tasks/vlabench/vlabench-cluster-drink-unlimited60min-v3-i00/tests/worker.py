"""Run with python -I; ignore agent cwd and PYTHONPATH."""
from pathlib import Path
import sys
import traceback
import tarfile
import tempfile
here = Path(__file__).resolve().parent
backend = Path("/opt/VLABench")
archive_path = here / "backend.tar.gz"
temporary = None
if archive_path.exists():
    temporary = tempfile.TemporaryDirectory(prefix="vlabench-verifier-")
    backend = Path(temporary.name)
    # Archive is the trusted task author's source bundle, never a submission.
    with tarfile.open(archive_path) as archive:
        archive.extractall(backend, filter="data")
    (backend / "VLABench/assets").symlink_to("/opt/VLABench/VLABench/assets", target_is_directory=True)
sys.path[:0] = [str(here), str(backend), "/opt/rrt-algorithms"]
from vlb_traj import main
try:
    main()
except (ValueError, KeyError) as exc:
    traceback.print_exc()
    sys.exit(2)
except Exception:
    traceback.print_exc()
    sys.exit(3)
finally:
    if temporary: temporary.cleanup()
