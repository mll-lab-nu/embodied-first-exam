FROM docker.io/library/python:3.12.14-slim@sha256:f77ac9e44ae96ef2c90b8053ea08c31f8be030f824196b0ae4db6d462c84e51f
LABEL roboengineer.instance_sha256="80590ad4cdf02479a092974d3c40b94fb25190aee49f47f66de2f71f72163c2a"
COPY grade.py test.sh instance.json /tests/
RUN echo '80590ad4cdf02479a092974d3c40b94fb25190aee49f47f66de2f71f72163c2a  /tests/instance.json' | sha256sum -c - && chmod +x /tests/test.sh
# resource limits: the verifier step and its copy of the limits (docs/protocol/README.md §2.10) # rcb-monitor
COPY rcb_limits.py rcb_limits.json /tests/
