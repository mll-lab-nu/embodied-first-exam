# Separate verifier sandbox (PROTOCOL H.1): the same simulator image with the verifier's own copies of the tooling and
# the frozen instance baked in. Nothing the agent did in its container reaches this one: Harbor uploads only the declared
# artifacts (/app/output/), so a patched success check in the agent container cannot count.
FROM ghcr.io/mll-lab-nu/efe:dexjoco-0.1.2
COPY instance.npz test.sh /tests/
COPY --from=ghcr.io/mll-lab-nu/efe:dexjoco-files-0.2.2@sha256:d2c2e975297082263874534f00c30d164a41a1418ce447955ddbb87aea25a5a7 /privileged/environment/rcb_dexjoco.py /privileged/tests/grade.py /tests/
RUN chmod +x /tests/test.sh && mkdir -p /app/output /logs/verifier
ENV PYTHONPATH=/tests
# the thread count the instances and references were made with; it needs 4 CPUs visible to this container, which
# grade.py checks before it replays (tasks/dexjoco/README.md, Threads)
ENV OPENBLAS_NUM_THREADS=4
WORKDIR /tests
# resources (PROTOCOL §6) # rcb-monitor
COPY --from=ghcr.io/mll-lab-nu/efe:monitor-0.5.0@sha256:ecc5f24f1516ca11711d7c2d3ac07c89f79cd9220812c1244498ec71e352402a /opt/rcb_monitor/rcb_limits.py /tests/rcb_limits.py
COPY rcb_limits.json /tests/rcb_limits.json
