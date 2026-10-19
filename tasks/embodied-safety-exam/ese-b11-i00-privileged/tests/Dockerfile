# Separate verifier sandbox (PROTOCOL §2.6): the same simulator image, unscrubbed, with the verifier's own copies of the
# tooling (from the files-only image ese-files) and the frozen instance baked in. Nothing the agent did in its
# container reaches this one: Harbor uploads only the declared artifacts (/app/output/).
FROM ghcr.io/mll-lab-nu/efe-private:ese-0.5.4
COPY test.sh instance.json /tests/
COPY --from=ghcr.io/mll-lab-nu/efe-private:ese-files-0.1.0@sha256:03813f0484542de85c6c80fbc16d39787333c359ae036dd1d7d88c637a4480d1 /privileged/grade.py /tests/grade.py
COPY --from=ghcr.io/mll-lab-nu/efe-private:ese-files-0.1.0@sha256:03813f0484542de85c6c80fbc16d39787333c359ae036dd1d7d88c637a4480d1 /standard/rcb_rsb.py /tests/rcb_rsb.py
COPY --from=ghcr.io/mll-lab-nu/efe-private:ese-files-0.1.0@sha256:03813f0484542de85c6c80fbc16d39787333c359ae036dd1d7d88c637a4480d1 /standard/candidate_identity.py /tests/candidate_identity.py
COPY --from=ghcr.io/mll-lab-nu/efe-private:ese-files-0.1.0@sha256:03813f0484542de85c6c80fbc16d39787333c359ae036dd1d7d88c637a4480d1 /privileged/rcb_rsb_privileged.py /tests/rcb_rsb_privileged.py
RUN chmod +x /tests/test.sh && mkdir -p /app/output /logs/verifier
ENV PYTHONPATH=/tests RCB_RSB_INSTANCE=/tests/instance.json
WORKDIR /tests
# resource limits: the verifier step (from the monitor image) and its copy of the limits (docs/protocol/README.md §2.10) # rcb-monitor
COPY --from=ghcr.io/mll-lab-nu/efe:monitor-0.2.0@sha256:65442d9e9eeb493d785a59d48a321345e2b48186946cc9d55beb684182514b4b /opt/rcb_monitor/rcb_limits.py /tests/rcb_limits.py
COPY rcb_limits.json /tests/rcb_limits.json
