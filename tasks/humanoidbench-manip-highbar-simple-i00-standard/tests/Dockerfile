# Separate verifier sandbox: grades the sim service's own artifacts; needs nothing but Python.
FROM docker.io/library/python:3.12.14-slim@sha256:f77ac9e44ae96ef2c90b8053ea08c31f8be030f824196b0ae4db6d462c84e51f
COPY test.sh grade.py /tests/
RUN chmod +x /tests/test.sh
