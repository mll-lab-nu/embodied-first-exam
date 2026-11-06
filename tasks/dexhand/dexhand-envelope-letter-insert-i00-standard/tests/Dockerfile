FROM docker.io/library/python:3.12.14-slim@sha256:f77ac9e44ae96ef2c90b8053ea08c31f8be030f824196b0ae4db6d462c84e51f
COPY test.sh /tests/
COPY --from=ghcr.io/mll-lab-nu/efe:dexhand-files-0.6.0@sha256:76ecdba39db6329198383e5fa6c89613bd95185ab974a2895521d32237900b24 /standard/tests/grade.py /tests/grade.py
RUN chmod +x /tests/test.sh
WORKDIR /tests
# resources (PROTOCOL §6) # rcb-monitor
COPY --from=ghcr.io/mll-lab-nu/efe:monitor-0.5.0@sha256:ecc5f24f1516ca11711d7c2d3ac07c89f79cd9220812c1244498ec71e352402a /opt/rcb_monitor/rcb_limits.py /tests/rcb_limits.py
COPY rcb_limits.json /tests/rcb_limits.json
