FROM docker.io/library/python:3.12.14-slim@sha256:f77ac9e44ae96ef2c90b8053ea08c31f8be030f824196b0ae4db6d462c84e51f
LABEL roboengineer.instance_sha256="7378e849108a925c248393e73d1515f689cbb8953156f18bc332d26011a98de8"
COPY grade.py test.sh instance.json /tests/
RUN echo '7378e849108a925c248393e73d1515f689cbb8953156f18bc332d26011a98de8  /tests/instance.json' | sha256sum -c - && chmod +x /tests/test.sh
# resource limits: the verifier step and its copy of the limits (docs/PROTOCOL.md §2.10) # rcb-monitor
COPY rcb_limits.py rcb_limits.json /tests/
