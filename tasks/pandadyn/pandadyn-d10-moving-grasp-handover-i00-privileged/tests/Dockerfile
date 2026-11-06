# Separate verifier sandbox (PROTOCOL §4): the same simulator image with the verifier's own copies of the tooling and the
# frozen instance baked in. Nothing the agent did in its container reaches this one -- Harbor uploads only the declared
# artifacts (/app/output/), so a patched success check or a swapped interpreter in the agent container cannot influence
# the verdict.
FROM ghcr.io/mll-lab-nu/efe:pandadyn-0.2.0
COPY instance.json test.sh /tests/
COPY --from=ghcr.io/mll-lab-nu/efe:pandadyn-files-0.5.1@sha256:f232befeaba85b7423da532377e5836a09eb2ac5a2f4a65962ce6ac8e76b07e1 /privileged/environment/rcb_pandadyn.py /privileged/tests/grade.py /tests/
RUN chmod +x /tests/test.sh && mkdir -p /app/output /logs/verifier
ENV PYTHONPATH=/tests:/opt/pandadyn
WORKDIR /tests
# resources (PROTOCOL §6) # rcb-monitor
COPY --from=ghcr.io/mll-lab-nu/efe:monitor-0.5.0@sha256:ecc5f24f1516ca11711d7c2d3ac07c89f79cd9220812c1244498ec71e352402a /opt/rcb_monitor/rcb_limits.py /tests/rcb_limits.py
COPY rcb_limits.json /tests/rcb_limits.json
