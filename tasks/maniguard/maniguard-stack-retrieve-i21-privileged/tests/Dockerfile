# Separate verifier sandbox (PROTOCOL §2.6): the same simulator image with the verifier's own copies of the tooling and the
# frozen instance baked in. Nothing the agent did in its container reaches this one: Harbor uploads only the declared
# artifacts (/app/output/), so a patched monitor, goal check or interpreter in the agent container cannot change the verdict.
FROM ghcr.io/mll-lab-nu/efe-private:maniguard-0.1.0
COPY test.sh /tests/
COPY --from=ghcr.io/mll-lab-nu/efe-private:maniguard-files-0.1.0@sha256:c3f228906c44d58cdbb2dfef6a0adaf989f1be969d227e1c9db9e060f5b3f6cf /privileged/environment/rcb_maniguard.py /privileged/tests/grade.py /tests/
COPY instance /tests/instance
RUN chmod +x /tests/test.sh && mkdir -p /app/output /logs/verifier
ENV PYTHONPATH=/tests
WORKDIR /tests
# resource limits: the verifier step (from the monitor image) and its copy of the limits (docs/protocol/README.md §2.10) # rcb-monitor
COPY --from=ghcr.io/mll-lab-nu/efe:monitor-0.2.0@sha256:65442d9e9eeb493d785a59d48a321345e2b48186946cc9d55beb684182514b4b /opt/rcb_monitor/rcb_limits.py /tests/rcb_limits.py
COPY rcb_limits.json /tests/rcb_limits.json
