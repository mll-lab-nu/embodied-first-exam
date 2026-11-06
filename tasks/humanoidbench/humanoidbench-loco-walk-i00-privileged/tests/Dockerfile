# Separate verifier sandbox (docs/protocol/README.md Appendix H.1): the same base image, plus the verifier's own copies of the
# tooling, this task's reward and the frozen instance. Nothing the agent did in its container reaches this one:
# Harbor uploads only the declared artifacts (/app/output/).
# One template for every HumanoidBench verifier (the tooling that renders it is kept outside this repository): keep the copies identical.
FROM ghcr.io/mll-lab-nu/efe:humanoidbench-0.2.0
COPY instance.npz rewards.json test.sh /tests/
COPY --from=ghcr.io/mll-lab-nu/efe:humanoidbench-files-0.4.1@sha256:1a7fcffe473eaf01597596e7c4f6442d2ab4dfa80bd2b1797893a555514efe38 /privileged/environment/rcb_hb.py /privileged/tests/grade.py /privileged/tests/rcb_rewards.py /tests/
RUN chmod +x /tests/test.sh && mkdir -p /app/output /logs/verifier
WORKDIR /tests
# resources (PROTOCOL §6) # rcb-monitor
COPY --from=ghcr.io/mll-lab-nu/efe:monitor-0.5.0@sha256:ecc5f24f1516ca11711d7c2d3ac07c89f79cd9220812c1244498ec71e352402a /opt/rcb_monitor/rcb_limits.py /tests/rcb_limits.py
COPY rcb_limits.json /tests/rcb_limits.json
