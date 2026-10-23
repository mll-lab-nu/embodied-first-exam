# Separate verifier sandbox: grades the sim service's own artifacts (/data/final.json, the live episode's verdict);
# needs nothing but python (no simulator: nothing is replayed).
FROM docker.io/library/python:3.12.14-slim@sha256:f77ac9e44ae96ef2c90b8053ea08c31f8be030f824196b0ae4db6d462c84e51f
COPY test.sh /tests/
COPY --from=ghcr.io/mll-lab-nu/efe:ikea-mujoco-files-0.2.1@sha256:093737b0eb56d3f157606377c7bd6f31cd30f4cc7bf2044bb5a799238714b927 /standard/tests/grade.py /tests/grade.py
RUN chmod +x /tests/test.sh && mkdir -p /logs/verifier
WORKDIR /tests
# resource limits: the verifier step (from the monitor image) and its copy of the limits (docs/protocol/README.md §2.10) # rcb-monitor
COPY --from=ghcr.io/mll-lab-nu/efe:monitor-0.3.0@sha256:53154417782408df8309194971b08b18c3682d2b337e2e3b2eb4c88fe025ab85 /opt/rcb_monitor/rcb_limits.py /tests/rcb_limits.py
COPY rcb_limits.json /tests/rcb_limits.json
