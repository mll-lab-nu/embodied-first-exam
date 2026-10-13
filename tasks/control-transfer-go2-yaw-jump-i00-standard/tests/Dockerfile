FROM docker.io/library/python:3.12.14-slim@sha256:f77ac9e44ae96ef2c90b8053ea08c31f8be030f824196b0ae4db6d462c84e51f
LABEL roboengineer.instance_sha256="a3eeac70b3cd0b330a4995e810ed1c8ab36597814c88abcbd9ef9852a00e7397"
COPY grade.py test.sh instance.json /tests/
RUN echo 'a3eeac70b3cd0b330a4995e810ed1c8ab36597814c88abcbd9ef9852a00e7397  /tests/instance.json' | sha256sum -c - && chmod +x /tests/test.sh
# resource limits: the verifier step and its copy of the limits (docs/PROTOCOL.md §2.10) # rcb-monitor
COPY rcb_limits.py rcb_limits.json /tests/
