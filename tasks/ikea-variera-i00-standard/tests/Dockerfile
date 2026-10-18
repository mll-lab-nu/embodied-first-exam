# Separate verifier sandbox: grades the sim service's own artifacts (/data/final.json, the live episode's verdict);
# needs nothing but python (no simulator: nothing is replayed, board 0151).
FROM docker.io/library/python:3.12.14-slim@sha256:f77ac9e44ae96ef2c90b8053ea08c31f8be030f824196b0ae4db6d462c84e51f
COPY grade.py test.sh /tests/
RUN chmod +x /tests/test.sh && mkdir -p /logs/verifier
WORKDIR /tests
# resource limits: the verifier step and its copy of the limits (docs/protocol/README.md §2.10) # rcb-monitor
COPY rcb_limits.py rcb_limits.json /tests/
