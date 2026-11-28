# Separate verifier sandbox: grades the sim service's own artifacts; needs nothing but python.
FROM docker.io/library/python:3.12-slim
COPY test.sh /tests/
COPY --from=ghcr.io/mll-lab-nu/efe:dextoolbench-files-0.9.0@sha256:29efa37afe2d55d9c35b6791d4e73fcb79eb35ca88bfc7f0756ee4c9ffd90a57 /standard/tests/grade.py /tests/grade.py
RUN chmod +x /tests/test.sh
# resources (docs/protocol/resources.md) # rcb-monitor
COPY --from=ghcr.io/mll-lab-nu/efe:monitor-0.5.0@sha256:ecc5f24f1516ca11711d7c2d3ac07c89f79cd9220812c1244498ec71e352402a /opt/rcb_monitor/rcb_limits.py /tests/rcb_limits.py
COPY rcb_limits.json /tests/rcb_limits.json
