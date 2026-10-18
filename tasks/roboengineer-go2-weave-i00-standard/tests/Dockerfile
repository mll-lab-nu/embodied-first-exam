FROM docker.io/library/python:3.12.14-slim@sha256:f77ac9e44ae96ef2c90b8053ea08c31f8be030f824196b0ae4db6d462c84e51f
LABEL roboengineer.instance_sha256="781fd8671eadb96cc8a265f2f660ce3c293828ae9f187090c67ba1d080794abf"
COPY grade.py test.sh instance.json /tests/
RUN echo '781fd8671eadb96cc8a265f2f660ce3c293828ae9f187090c67ba1d080794abf  /tests/instance.json' | sha256sum -c - && chmod +x /tests/test.sh
# resource limits: the verifier step and its copy of the limits (docs/protocol/README.md §2.10) # rcb-monitor
COPY rcb_limits.py rcb_limits.json /tests/
