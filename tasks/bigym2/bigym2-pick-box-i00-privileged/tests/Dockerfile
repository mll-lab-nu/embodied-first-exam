# Separate verifier sandbox (PROTOCOL §2.6): the same simulator image with the verifier's own copies of the tooling and
# the frozen instance. Nothing the agent did in its container reaches this one: Harbor uploads only /app/output/.
FROM ghcr.io/mll-lab-nu/efe:bigym2-0.1.1
COPY instance.json test.sh /tests/
COPY --from=ghcr.io/mll-lab-nu/efe:bigym2-files-0.2.0@sha256:37d88fba01634b8f482fa245dc00f0e8202e97a021838a197d2dcc3544ca86c6 /privileged/environment/rcb_bigym2.py /privileged/tests/grade.py /tests/
RUN chmod +x /tests/test.sh && mkdir -p /app/output /logs/verifier
ENV PYTHONPATH=/tests
WORKDIR /tests
# resource limits: the verifier step (from the monitor image) and its copy of the limits (docs/protocol/README.md §2.10) # rcb-monitor
COPY --from=ghcr.io/mll-lab-nu/efe:monitor-0.2.0@sha256:65442d9e9eeb493d785a59d48a321345e2b48186946cc9d55beb684182514b4b /opt/rcb_monitor/rcb_limits.py /tests/rcb_limits.py
COPY rcb_limits.json /tests/rcb_limits.json
