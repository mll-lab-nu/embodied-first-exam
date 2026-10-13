FROM docker.io/library/python:3.12.14-slim@sha256:f77ac9e44ae96ef2c90b8053ea08c31f8be030f824196b0ae4db6d462c84e51f
LABEL roboengineer.instance_sha256="e3f5b217dac1434bdcfb99d69b997a9a3099ba55ac30224178f19e4bab7bc2fb"
COPY grade.py test.sh instance.json /tests/
RUN echo 'e3f5b217dac1434bdcfb99d69b997a9a3099ba55ac30224178f19e4bab7bc2fb  /tests/instance.json' | sha256sum -c - && chmod +x /tests/test.sh
# resource limits: the verifier step and its copy of the limits (docs/PROTOCOL.md §2.10) # rcb-monitor
COPY rcb_limits.py rcb_limits.json /tests/
