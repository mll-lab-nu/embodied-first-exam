# Separate verifier sandbox (docs/PROTOCOL.md §2.6): the same base image, plus the verifier's own copies of the
# tooling and the frozen instance. Nothing the agent did in its container reaches this one: Harbor uploads only the
# declared artifacts (/app/output/).
# Generated from scripts/kinder/templates/tests.Dockerfile -- edit the template, not this copy.
FROM ghcr.io/embodied-agent-interface-v2-internal/eai-kinder:0.1.6
COPY grade.py instance.json rcb_kinder.py test.sh /tests/
RUN chmod +x /tests/test.sh && mkdir -p /app/output /logs/verifier
WORKDIR /tests
