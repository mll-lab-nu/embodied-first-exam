FROM docker.io/library/python:3.12.14-slim@sha256:f77ac9e44ae96ef2c90b8053ea08c31f8be030f824196b0ae4db6d462c84e51f
LABEL roboengineer.instance_sha256="95085e812ca4f37c9cc9e05005fe83a47cc72a72f59b35c66f48d5dd8ab022cb"
COPY grade.py test.sh instance.json /tests/
RUN echo '95085e812ca4f37c9cc9e05005fe83a47cc72a72f59b35c66f48d5dd8ab022cb  /tests/instance.json' | sha256sum -c - && chmod +x /tests/test.sh
# resource limits: the verifier step and its copy of the limits (docs/PROTOCOL.md §2.10) # rcb-monitor
COPY rcb_limits.py rcb_limits.json /tests/
