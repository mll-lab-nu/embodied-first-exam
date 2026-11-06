# Separate verifier sandbox (docs/protocol/README.md Appendix H.1): the same base image, plus the verifier's own copies of the
# tooling and the frozen instance. Nothing the agent did in its container reaches this one: Harbor uploads only the
# declared artifacts (/app/output/).
FROM ghcr.io/mll-lab-nu/efe:kinder-0.1.6
COPY instance.json test.sh /tests/
COPY --from=ghcr.io/mll-lab-nu/efe:kinder-files-0.4.1@sha256:6b28cc6adfd2a09667a2ae3b270a507be7eabcc56f450e6e66f818bb20d5dca4 /privileged/environment/rcb_kinder.py /privileged/tests/grade.py /tests/
RUN chmod +x /tests/test.sh && mkdir -p /app/output /logs/verifier
WORKDIR /tests
# resources (PROTOCOL §6) # rcb-monitor
COPY --from=ghcr.io/mll-lab-nu/efe:monitor-0.5.0@sha256:ecc5f24f1516ca11711d7c2d3ac07c89f79cd9220812c1244498ec71e352402a /opt/rcb_monitor/rcb_limits.py /tests/rcb_limits.py
COPY rcb_limits.json /tests/rcb_limits.json
