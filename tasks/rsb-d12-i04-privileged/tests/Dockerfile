# Separate verifier sandbox (PROTOCOL §2.6): the same simulator image, unscrubbed, with the verifier's own copies of the
# tooling and the frozen instance baked in. Nothing the agent did in its container reaches this one: Harbor uploads only
# the declared artifacts (/app/output/).
FROM ghcr.io/mll-lab-nu/eai-robosafe:0.5.4
COPY test.sh grade.py rcb_rsb.py candidate_identity.py rcb_rsb_privileged.py instance.json /tests/
RUN chmod +x /tests/test.sh && mkdir -p /app/output /logs/verifier
ENV PYTHONPATH=/tests RCB_RSB_INSTANCE=/tests/instance.json
WORKDIR /tests
# resource limits: the verifier step (from the monitor image) and its copy of the limits (docs/protocol/README.md §2.10) # rcb-monitor
COPY --from=ghcr.io/mll-lab-nu/eai-monitor:0.2.0@sha256:65442d9e9eeb493d785a59d48a321345e2b48186946cc9d55beb684182514b4b /opt/rcb_monitor/rcb_limits.py /tests/rcb_limits.py
COPY rcb_limits.json /tests/rcb_limits.json
