# Separate verifier sandbox (PROTOCOL §4): the same simulator image with the verifier's own copies of the tooling and the
# frozen instance. Nothing the agent did in its container reaches this one: Harbor uploads only /app/output/.
FROM ghcr.io/mll-lab-nu/efe:molmospaces-0.2.5
COPY instance.json test.sh /tests/
COPY --from=ghcr.io/mll-lab-nu/efe:molmospaces-files-0.1.1@sha256:6a9e3baaf42a25af19d5969171a86ba3cb3a5eea01e9d3e23f49f252049514b6 /privileged/environment/rcb_molmospaces.py /privileged/tests/grade.py /tests/
RUN chmod +x /tests/test.sh && mkdir -p /app/output /logs/verifier
ENV PYTHONPATH=/tests
WORKDIR /tests
# resource limits: the verifier step (from the monitor image) and its copy of the limits (docs/protocol/README.md §2.10) # rcb-monitor
COPY --from=ghcr.io/mll-lab-nu/efe:monitor-0.2.0@sha256:65442d9e9eeb493d785a59d48a321345e2b48186946cc9d55beb684182514b4b /opt/rcb_monitor/rcb_limits.py /tests/rcb_limits.py
COPY rcb_limits.json /tests/rcb_limits.json
