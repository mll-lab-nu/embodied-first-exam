# Separate verifier sandbox (PROTOCOL §4): the same simulator image with the verifier's own copies of the tooling and the
# frozen instance baked in. Nothing the agent did in its container reaches this one — Harbor uploads only the declared
# artifacts (/app/output/), so a patched success check or a swapped interpreter in the agent container cannot influence
# the verdict.
FROM ghcr.io/mll-lab-nu/efe-private:yamlab-0.1.0
COPY instance.json test.sh /tests/
COPY --from=ghcr.io/mll-lab-nu/efe:yamlab-files-0.2.0@sha256:dcf2cdbd2b6dc96201e6c66f15fdb65a44098e8e27abc7a316375ceb1168cf85 /privileged/environment/rcb_yamlab.py /privileged/tests/grade.py /tests/
RUN chmod +x /tests/test.sh && mkdir -p /app/output /logs/verifier
ENV PYTHONPATH=/tests
WORKDIR /tests
# resource limits: the verifier step (from the monitor image) and its copy of the limits (docs/protocol/README.md §2.10) # rcb-monitor
COPY --from=ghcr.io/mll-lab-nu/efe:monitor-0.2.0@sha256:65442d9e9eeb493d785a59d48a321345e2b48186946cc9d55beb684182514b4b /opt/rcb_monitor/rcb_limits.py /tests/rcb_limits.py
COPY rcb_limits.json /tests/rcb_limits.json
