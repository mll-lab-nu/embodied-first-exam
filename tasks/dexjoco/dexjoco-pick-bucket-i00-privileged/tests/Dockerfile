# Separate verifier sandbox (PROTOCOL §2.6): the same simulator image with the verifier's own copies of the tooling and
# the frozen instance baked in. Nothing the agent did in its container reaches this one: Harbor uploads only the declared
# artifacts (/app/output/), so a patched success check in the agent container cannot count.
FROM ghcr.io/mll-lab-nu/efe:dexjoco-0.1.2
COPY instance.npz test.sh /tests/
COPY --from=ghcr.io/mll-lab-nu/efe:dexjoco-files-0.1.1@sha256:7976cf6afa2103ded00826a3e82239e7e5e84fcc9a9380640ef40f8d9bcd80b2 /privileged/environment/rcb_dexjoco.py /privileged/tests/grade.py /tests/
RUN chmod +x /tests/test.sh && mkdir -p /app/output /logs/verifier
ENV PYTHONPATH=/tests
# the thread count the instances and references were made with; it needs 4 CPUs visible to this container, which
# grade.py checks before it replays (tasks/dexjoco/README.md, Threads)
ENV OPENBLAS_NUM_THREADS=4
WORKDIR /tests
# resource limits: the verifier step (from the monitor image) and its copy of the limits (docs/protocol/README.md §2.10) # rcb-monitor
COPY --from=ghcr.io/mll-lab-nu/efe:monitor-0.3.0@sha256:53154417782408df8309194971b08b18c3682d2b337e2e3b2eb4c88fe025ab85 /opt/rcb_monitor/rcb_limits.py /tests/rcb_limits.py
COPY rcb_limits.json /tests/rcb_limits.json
