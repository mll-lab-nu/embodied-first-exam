FROM docker.io/library/python:3.12.14-slim@sha256:f77ac9e44ae96ef2c90b8053ea08c31f8be030f824196b0ae4db6d462c84e51f
LABEL roboengineer.instance_sha256="152a84149ec699b4d852a29cf17b9527b73e14dbf47a6b20b912ab45a5247230"
COPY test.sh instance.json /tests/
COPY --from=ghcr.io/mll-lab-nu/efe-private:roboengineer-files-0.1.0@sha256:7ffc4213019f7d88bd5072a8c1d56936a2b3f78cad7c7aea920a33794749d040 /standard/tests/grade.py /tests/grade.py
RUN echo '152a84149ec699b4d852a29cf17b9527b73e14dbf47a6b20b912ab45a5247230  /tests/instance.json' | sha256sum -c - && chmod +x /tests/test.sh
# resource limits: the verifier step (from the monitor image) and its copy of the limits (docs/protocol/README.md §2.10) # rcb-monitor
COPY --from=ghcr.io/mll-lab-nu/efe:monitor-0.2.0@sha256:65442d9e9eeb493d785a59d48a321345e2b48186946cc9d55beb684182514b4b /opt/rcb_monitor/rcb_limits.py /tests/rcb_limits.py
COPY rcb_limits.json /tests/rcb_limits.json
