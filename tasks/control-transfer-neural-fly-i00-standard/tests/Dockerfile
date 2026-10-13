FROM docker.io/library/python:3.12.14-slim@sha256:f77ac9e44ae96ef2c90b8053ea08c31f8be030f824196b0ae4db6d462c84e51f
LABEL roboengineer.instance_sha256="f87e623e5379e42742a35527a5b3ded902da84fa8990507500888fac6b5b3dc3"
COPY grade.py test.sh instance.json /tests/
RUN echo 'f87e623e5379e42742a35527a5b3ded902da84fa8990507500888fac6b5b3dc3  /tests/instance.json' | sha256sum -c - && chmod +x /tests/test.sh
# resource limits: the verifier step and its copy of the limits (docs/PROTOCOL.md §2.10) # rcb-monitor
COPY rcb_limits.py rcb_limits.json /tests/
