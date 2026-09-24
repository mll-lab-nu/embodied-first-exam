# Dedicated verifier image (separate sandbox): only needs python; grading reads the sidecar's artifacts uploaded to /data.
FROM docker.io/library/python:3.12-slim
COPY test.sh /tests/test.sh
RUN chmod +x /tests/test.sh
