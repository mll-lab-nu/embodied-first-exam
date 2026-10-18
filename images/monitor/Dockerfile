# eai-monitor: the resource-limits monitor sidecar (service `rcb_monitor` in every task; docs/protocol/README.md §2.10) and
# the verifier step's code. The runtime is Python only (BASE: python:3.12-slim-bookworm with PYTHONUNBUFFERED=1,
# PYTHONDONTWRITEBYTECODE=1, NVIDIA_DRIVER_CAPABILITIES=utility, so the NVIDIA runtime / CDI inject libnvidia-ml when the
# task reserves a GPU; WORKDIR /var/rcb-monitor). On top: the monitor's code at /opt/rcb_monitor/, from its one source,
# scripts/rcb_monitor/ (the build context, images/monitor/BUILD_CONTEXT). A task mounts only its limits.json there, and its
# verifier image takes rcb_limits.py from this image (`COPY --from`). Public. Tag = images/monitor/VERSION; tasks pin the
# digest and scripts/rcb_monitor/inject.py CONTENTS the files' sha256 (`inject.py verify-image` checks an image).
# Build from a copy of the three files with content-derived mtimes (scripts/stamp_mtimes.py, the stamp every deployed
# task file gets), so the files carry the mtimes their task-dir copies had:
#   d=$(mktemp -d); cp scripts/rcb_monitor/{monitor,rcb_limits,selftest}.py $d/
#   python3 -c "import sys; sys.path.insert(0, 'scripts'); import stamp_mtimes as s; s.stamp_tree('$d', True)"
#   docker build --no-cache -t ghcr.io/mll-lab-nu/eai-monitor:$(cat images/monitor/VERSION) -f images/monitor/Dockerfile $d
ARG BASE=ghcr.io/mll-lab-nu/eai-monitor:0.1.0@sha256:f2c910f53f79c2bfa4a71298b10c78383cae3afc40720ca562cc845b8d20fb0c
FROM ${BASE}
COPY monitor.py rcb_limits.py selftest.py /opt/rcb_monitor/
