# Separate verifier sandbox (docs/protocol/README.md §2.6): the same base image, plus the verifier's own copies of the
# tooling, this task's reward and the frozen instance. Nothing the agent did in its container reaches this one:
# Harbor uploads only the declared artifacts (/app/output/).
# Generated from scripts/humanoidbench/templates/tests.Dockerfile -- edit the template, not this copy.
FROM {{image}}
COPY {{tests_files}} /tests/
RUN chmod +x /tests/test.sh && mkdir -p /app/output /logs/verifier
WORKDIR /tests
