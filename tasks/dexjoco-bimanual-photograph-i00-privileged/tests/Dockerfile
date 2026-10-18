# Separate verifier sandbox (PROTOCOL §2.6): the same simulator image with the verifier's own copies of the tooling and
# the frozen instance baked in. Nothing the agent did in its container reaches this one: Harbor uploads only the declared
# artifacts (/app/output/), so a patched success check in the agent container cannot count.
FROM ghcr.io/mll-lab-nu/eai-dexjoco:0.1.2
COPY grade.py instance.npz rcb_dexjoco.py test.sh /tests/
RUN chmod +x /tests/test.sh && mkdir -p /app/output /logs/verifier
ENV PYTHONPATH=/tests
# the thread count the instances and references were made with; it needs 4 CPUs visible to this container, which
# grade.py checks before it replays (docs/benchmarks/dexjoco.md, Threads)
ENV OPENBLAS_NUM_THREADS=4
WORKDIR /tests
# resource limits: the verifier step and its copy of the limits (docs/protocol/README.md §2.10) # rcb-monitor
COPY rcb_limits.py rcb_limits.json /tests/
