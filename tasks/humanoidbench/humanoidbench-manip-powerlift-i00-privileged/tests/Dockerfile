# Separate verifier sandbox (docs/protocol/README.md §2.6): the same base image, plus the verifier's own copies of the
# tooling, this task's reward and the frozen instance. Nothing the agent did in its container reaches this one:
# Harbor uploads only the declared artifacts (/app/output/).
# Generated from scripts/humanoidbench/templates/tests.Dockerfile -- edit the template, not this copy.
FROM ghcr.io/mll-lab-nu/efe:humanoidbench-0.2.0
COPY instance.npz rewards.json test.sh /tests/
COPY --from=ghcr.io/mll-lab-nu/efe:humanoidbench-files-0.2.0@sha256:ef65887f840ebe1298af7fec87bba55ab2484a8d2fe9c9886b9c54832ef55ba0 /privileged/environment/rcb_hb.py /privileged/tests/grade.py /privileged/tests/rcb_rewards.py /tests/
RUN chmod +x /tests/test.sh && mkdir -p /app/output /logs/verifier
WORKDIR /tests
# resource limits: the verifier step (from the monitor image) and its copy of the limits (docs/protocol/README.md §2.10) # rcb-monitor
COPY --from=ghcr.io/mll-lab-nu/efe:monitor-0.2.0@sha256:65442d9e9eeb493d785a59d48a321345e2b48186946cc9d55beb684182514b4b /opt/rcb_monitor/rcb_limits.py /tests/rcb_limits.py
COPY rcb_limits.json /tests/rcb_limits.json
