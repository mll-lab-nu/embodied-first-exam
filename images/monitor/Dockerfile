# monitor: the resource-limits monitor sidecar (service `rcb_monitor` in every task; docs/protocol/README.md §2.10) and
# the verifier step's code. The runtime is Python only (BASE: python:3.12-slim-bookworm with PYTHONUNBUFFERED=1,
# PYTHONDONTWRITEBYTECODE=1, NVIDIA_DRIVER_CAPABILITIES=utility, so the NVIDIA runtime / CDI inject libnvidia-ml when the
# task reserves a GPU; WORKDIR /var/rcb-monitor). On top: the monitor's code at /opt/rcb_monitor/, from its one source,
# images/monitor/rcb_monitor/ (staged as the build context, images/monitor/BUILD_CONTEXT). A task mounts only its limits.json there, and its
# verifier image takes rcb_limits.py from this image (`COPY --from`). Public. Tag = images/monitor/VERSION; tasks pin the
# digest and images/monitor/rcb_monitor/inject.py CONTENTS the files' sha256 (`inject.py verify-image` checks an image).
# Build: `python3 images/monitor/rcb_monitor/inject.py stage-context` (images/monitor/context/, gitignored: the three files with
# the content-derived mtimes of scripts/stamp_mtimes.py, which every deployed task file gets), then scripts/build_images.sh
# (it skips this image while context/ is missing) or
#   docker build --no-cache -t ghcr.io/mll-lab-nu/efe:monitor-$(cat images/monitor/VERSION) -f images/monitor/Dockerfile images/monitor/context
ARG BASE=ghcr.io/mll-lab-nu/efe:monitor-0.1.0@sha256:f2c910f53f79c2bfa4a71298b10c78383cae3afc40720ca562cc845b8d20fb0c
FROM ${BASE}
COPY monitor.py rcb_limits.py selftest.py /opt/rcb_monitor/
