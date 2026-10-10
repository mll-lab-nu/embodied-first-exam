# Separate verifier sandbox (docs/PROTOCOL.md §2.6): the same base image, plus the verifier's own copies of the
# tooling, this task's reward and the frozen instance. Nothing the agent did in its container reaches this one:
# Harbor uploads only the declared artifacts (/app/output/).
# Generated from scripts/humanoidbench/templates/tests.Dockerfile -- edit the template, not this copy.
FROM ghcr.io/mll-lab-nu/eai-humanoidbench:0.2.0
COPY grade.py instance.npz rcb_hb.py rcb_rewards.py rewards.json test.sh /tests/
RUN chmod +x /tests/test.sh && mkdir -p /app/output /logs/verifier
WORKDIR /tests
