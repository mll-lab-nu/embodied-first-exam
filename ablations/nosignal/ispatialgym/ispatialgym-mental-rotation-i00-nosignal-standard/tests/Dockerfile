# Separate verifier sandbox: grades the sim service's own artifacts; needs nothing but python (the shared eai-standard
# client base, embodied_first_exam/standard/client.env; it installs nothing).
FROM docker.io/library/python:3.12.14-slim@sha256:f77ac9e44ae96ef2c90b8053ea08c31f8be030f824196b0ae4db6d462c84e51f
COPY test.sh /tests/test.sh
COPY --from=ghcr.io/mll-lab-nu/efe:ispatialgym-files-0.4.0-nosignal@sha256:f4c546c82c2682776259d8a8366838ae6098892561b4a19f33ad2c49ef9a6cee /standard/tests/grade.py /tests/grade.py
RUN chmod +x /tests/test.sh
# resources (PROTOCOL §6) # rcb-monitor
COPY --from=ghcr.io/mll-lab-nu/efe:monitor-0.5.0@sha256:ecc5f24f1516ca11711d7c2d3ac07c89f79cd9220812c1244498ec71e352402a /opt/rcb_monitor/rcb_limits.py /tests/rcb_limits.py
COPY rcb_limits.json /tests/rcb_limits.json
