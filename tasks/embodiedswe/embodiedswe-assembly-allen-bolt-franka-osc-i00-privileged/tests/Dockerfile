# Separate verifier sandbox (docs/protocol/invariants.md H.1): the same base image, the verifier's own copy of the frozen instance and the
# task's grader (EmbodiedSWE's, unchanged, at the pinned commit). /tests is root-only: the solution process (nobody)
# cannot read it.
FROM ghcr.io/mll-lab-nu/efe-private:embodiedswe-0.3.0
COPY --from=ghcr.io/mll-lab-nu/efe:embodiedswe-files-0.4.0@sha256:b35b3e41cf2f48d48c0b7e92d82a41beedb1e015e5d31bebef542506cf6300dd /rcb_embodiedswe.py /esw_proxy.py /opt/efe/
COPY grade.py instance.json test.sh /tests/
COPY grader/ /tests/grader/
RUN chmod 700 /tests && chmod +x /tests/test.sh && mkdir -p /app/output /logs/verifier
WORKDIR /tests
# resources (docs/protocol/resources.md) # rcb-monitor
COPY --from=ghcr.io/mll-lab-nu/efe:monitor-0.5.0@sha256:ecc5f24f1516ca11711d7c2d3ac07c89f79cd9220812c1244498ec71e352402a /opt/rcb_monitor/rcb_limits.py /tests/rcb_limits.py
COPY rcb_limits.json /tests/rcb_limits.json
