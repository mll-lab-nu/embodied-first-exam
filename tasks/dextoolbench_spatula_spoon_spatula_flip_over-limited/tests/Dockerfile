# Separate verifier sandbox: grades the sim service's own artifacts; needs nothing but python.
FROM docker.io/library/python:3.12-slim
COPY test.sh grade.py /tests/
RUN chmod +x /tests/test.sh
