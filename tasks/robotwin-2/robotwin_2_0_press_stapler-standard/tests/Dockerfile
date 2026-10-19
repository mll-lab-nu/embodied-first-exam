# Separate verifier sandbox: grades the sim service's own artifacts; needs nothing but python.
FROM docker.io/library/python:3.12-slim
COPY test.sh /tests/test.sh
COPY --from=ghcr.io/mll-lab-nu/efe-robotwin-2-files:0.1.0@sha256:58ec9516a73ac0d2bd49e6104ab529c089d6800a3f0572f46711a5f012770d64 /standard/tests/grade.py /tests/grade.py
RUN chmod +x /tests/test.sh
COPY --from=ghcr.io/mll-lab-nu/efe-monitor:0.2.0@sha256:65442d9e9eeb493d785a59d48a321345e2b48186946cc9d55beb684182514b4b /opt/rcb_monitor/rcb_limits.py /tests/rcb_limits.py
# resource limits: the verifier step (from the monitor image) and its copy of the limits (docs/protocol/README.md §2.10) # rcb-monitor
COPY --from=ghcr.io/mll-lab-nu/efe-monitor:0.2.0@sha256:65442d9e9eeb493d785a59d48a321345e2b48186946cc9d55beb684182514b4b /opt/rcb_monitor/rcb_limits.py /tests/rcb_limits.py
COPY rcb_limits.json /tests/rcb_limits.json
