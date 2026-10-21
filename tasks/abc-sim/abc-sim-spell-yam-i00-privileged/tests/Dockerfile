# Separate verifier sandbox: the same image with the verifier's own copy of the frozen instance (the grader is the
# image's /opt/abc-tools/grade.py). Nothing the agent did in its container reaches this one: Harbor uploads only the
# declared artifacts.
FROM ghcr.io/mll-lab-nu/efe:abc-sim-0.1.0
COPY instance.npz test.sh /tests/
RUN chmod +x /tests/test.sh && mkdir -p /app/output /logs/verifier
WORKDIR /tests
# resource limits: the verifier step (from the monitor image) and its copy of the limits (docs/protocol/README.md §2.10) # rcb-monitor
COPY --from=ghcr.io/mll-lab-nu/efe:monitor-0.3.0@sha256:53154417782408df8309194971b08b18c3682d2b337e2e3b2eb4c88fe025ab85 /opt/rcb_monitor/rcb_limits.py /tests/rcb_limits.py
COPY rcb_limits.json /tests/rcb_limits.json
