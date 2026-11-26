# Separate verifier sandbox: grades the sim service's own artifacts; needs nothing but python.
FROM docker.io/library/python:3.12-slim
COPY test.sh /tests/
COPY --from=ghcr.io/mll-lab-nu/efe:dextoolbench-files-0.6.0@sha256:3a06c3f2689f1b13c088bfd0d4588c0799ed908d983604865e5265376c9415bf /standard/tests/grade.py /tests/grade.py
RUN chmod +x /tests/test.sh
# resources (PROTOCOL §6) # rcb-monitor
COPY --from=ghcr.io/mll-lab-nu/efe:monitor-0.5.0@sha256:ecc5f24f1516ca11711d7c2d3ac07c89f79cd9220812c1244498ec71e352402a /opt/rcb_monitor/rcb_limits.py /tests/rcb_limits.py
COPY rcb_limits.json /tests/rcb_limits.json
