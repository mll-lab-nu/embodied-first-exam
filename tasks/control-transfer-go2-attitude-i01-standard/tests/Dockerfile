FROM docker.io/library/python:3.12.14-slim@sha256:f77ac9e44ae96ef2c90b8053ea08c31f8be030f824196b0ae4db6d462c84e51f
LABEL roboengineer.instance_sha256="866c961f574758f7bf6cf3b64e9d0c595a1fba052777ac0be2893e3b1a56c76f"
COPY grade.py test.sh instance.json /tests/
RUN echo '866c961f574758f7bf6cf3b64e9d0c595a1fba052777ac0be2893e3b1a56c76f  /tests/instance.json' | sha256sum -c - && chmod +x /tests/test.sh
# resource limits: the verifier step and its copy of the limits (docs/PROTOCOL.md §2.10) # rcb-monitor
COPY rcb_limits.py rcb_limits.json /tests/
