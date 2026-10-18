# Separate verifier sandbox (PROTOCOL §2.6): the same simulator image, unscrubbed, with the verifier's own copies of the
# tooling and the frozen instance baked in. Nothing the agent did in its container reaches this one: Harbor uploads only
# the declared artifacts (/app/output/).
FROM ghcr.io/mll-lab-nu/eai-robosafe:0.5.4
COPY test.sh grade.py rcb_rsb.py candidate_identity.py rcb_rsb_privileged.py instance.json /tests/
RUN chmod +x /tests/test.sh && mkdir -p /app/output /logs/verifier
ENV PYTHONPATH=/tests RCB_RSB_INSTANCE=/tests/instance.json
WORKDIR /tests
# resource limits: the verifier step and its copy of the limits (docs/protocol/README.md §2.10) # rcb-monitor
COPY rcb_limits.py rcb_limits.json /tests/
