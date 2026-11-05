# Separate verifier sandbox: grades the sim service's own artifacts; needs nothing but Python (the sim service judged the live episode).
FROM docker.io/library/python:3.12.14-slim@sha256:f77ac9e44ae96ef2c90b8053ea08c31f8be030f824196b0ae4db6d462c84e51f
COPY test.sh /tests/
COPY --from=ghcr.io/mll-lab-nu/efe:ese-files-0.7.0@sha256:64c28a8e7146e8509acf292d4b0478150536af66933c4af7bb36f69070d29e45 /realtime/grade.py /tests/grade.py
COPY --from=ghcr.io/mll-lab-nu/efe:ese-files-0.7.0@sha256:64c28a8e7146e8509acf292d4b0478150536af66933c4af7bb36f69070d29e45 /standard/grade.py /tests/grade_ese.py
RUN chmod +x /tests/test.sh
# resources (PROTOCOL §6) # rcb-monitor
COPY --from=ghcr.io/mll-lab-nu/efe:monitor-0.5.0@sha256:ecc5f24f1516ca11711d7c2d3ac07c89f79cd9220812c1244498ec71e352402a /opt/rcb_monitor/rcb_limits.py /tests/rcb_limits.py
COPY rcb_limits.json /tests/rcb_limits.json
