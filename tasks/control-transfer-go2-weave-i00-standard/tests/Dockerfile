FROM docker.io/library/python:3.12.14-slim@sha256:f77ac9e44ae96ef2c90b8053ea08c31f8be030f824196b0ae4db6d462c84e51f
LABEL roboengineer.instance_sha256="fe9c4090785a13e72a420d8382e7e488f48c9b496ad9b885a1dc93ef27185f4f"
COPY grade.py test.sh instance.json /tests/
RUN echo 'fe9c4090785a13e72a420d8382e7e488f48c9b496ad9b885a1dc93ef27185f4f  /tests/instance.json' | sha256sum -c - && chmod +x /tests/test.sh
# resource limits: the verifier step and its copy of the limits (docs/PROTOCOL.md §2.10) # rcb-monitor
COPY rcb_limits.py rcb_limits.json /tests/
