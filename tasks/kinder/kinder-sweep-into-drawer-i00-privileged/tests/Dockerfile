# Separate verifier sandbox (docs/protocol/README.md §2.6): the same base image, plus the verifier's own copies of the
# tooling and the frozen instance. Nothing the agent did in its container reaches this one: Harbor uploads only the
# declared artifacts (/app/output/).
FROM ghcr.io/mll-lab-nu/efe:kinder-0.1.6
COPY instance.json test.sh /tests/
COPY --from=ghcr.io/mll-lab-nu/efe:kinder-files-0.2.0@sha256:008137c8694c3137cf2d14a5204d1ad8ea204515c820e6dacef4ccdaa20d99e9 /privileged/environment/rcb_kinder.py /privileged/tests/grade.py /tests/
RUN chmod +x /tests/test.sh && mkdir -p /app/output /logs/verifier
WORKDIR /tests
# resource limits: the verifier step (from the monitor image) and its copy of the limits (docs/protocol/README.md §2.10) # rcb-monitor
COPY --from=ghcr.io/mll-lab-nu/efe:monitor-0.3.0@sha256:53154417782408df8309194971b08b18c3682d2b337e2e3b2eb4c88fe025ab85 /opt/rcb_monitor/rcb_limits.py /tests/rcb_limits.py
COPY rcb_limits.json /tests/rcb_limits.json
