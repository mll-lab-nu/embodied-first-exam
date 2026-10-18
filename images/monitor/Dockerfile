# eai-monitor: the runtime of the resource-limits monitor sidecar (service `rcb_monitor` in every task;
# docs/protocol/README.md §2.10). Python and nothing else: the monitor's code is not in the image, it is mounted read-only from
# the task directory (environment/rcb_monitor/, part of the task digest). NVIDIA_DRIVER_CAPABILITIES=utility makes the
# NVIDIA runtime / CDI inject libnvidia-ml when the task reserves a GPU. Public. Tag = images/monitor/VERSION; tasks pin
# the digest (scripts/rcb_monitor/inject.py).
FROM python:3.12-slim-bookworm
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 NVIDIA_DRIVER_CAPABILITIES=utility
WORKDIR /var/rcb-monitor
