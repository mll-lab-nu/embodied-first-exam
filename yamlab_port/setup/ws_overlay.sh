#!/bin/bash
# Runs INSIDE the eai-robolab container (via run_in_container.sh): installs yamlab's import-time deps
# into /data/pylib without touching the image venv (no-deps, explicit pins so numpy stays 1.26).
set -eux
python -c "import numpy, torch, isaaclab, gymnasium; print(numpy.__version__, torch.__version__)"
python -m pip --version || true
uv pip install --python /opt/robolab/.venv/bin/python --target /data/pylib --no-deps \
  "datasets==3.6.0" "pyarrow==18.1.0" "dill==0.3.8" "multiprocess==0.70.16" xxhash "fsspec==2025.3.0" \
  /work/lerobot
PYTHONPATH=/data/pylib:/work/yamlab python - <<'PY'
import importlib
for m in ["lerobot.common.datasets.lerobot_dataset", "datasets", "pyarrow", "numpy"]:
    try:
        mod = importlib.import_module(m); print("OK", m, getattr(mod, "__version__", ""))
    except Exception as e:
        print("FAIL", m, repr(e))
PY
echo OVERLAY_DONE
