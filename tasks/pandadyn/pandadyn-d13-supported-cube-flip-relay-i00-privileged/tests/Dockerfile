# Separate verifier sandbox (docs/protocol/tasks.md#grading): the same simulator image with the verifier's own copies of the tooling and the
# frozen instance baked in. Nothing the agent did in its container reaches this one -- Harbor uploads only the declared
# artifacts (/app/output/), so a patched success check or a swapped interpreter in the agent container cannot influence
# the verdict.
FROM ghcr.io/mll-lab-nu/efe:pandadyn-0.2.0
COPY instance.json test.sh /tests/
COPY --from=ghcr.io/mll-lab-nu/efe:pandadyn-files-0.8.0@sha256:2aa10cd376d829a5365ab2f5caf82d592401a238686dfe4b5bef6b8efc7a0df5 /privileged/environment/rcb_pandadyn.py /privileged/tests/grade.py /tests/
RUN chmod +x /tests/test.sh && mkdir -p /app/output /logs/verifier
ENV PYTHONPATH=/tests:/opt/pandadyn
WORKDIR /tests
# resources (docs/protocol/resources.md) # rcb-monitor
COPY --from=ghcr.io/mll-lab-nu/efe:monitor-0.5.0@sha256:ecc5f24f1516ca11711d7c2d3ac07c89f79cd9220812c1244498ec71e352402a /opt/rcb_monitor/rcb_limits.py /tests/rcb_limits.py
COPY rcb_limits.json /tests/rcb_limits.json
