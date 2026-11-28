FROM docker.io/library/python:3.12.14-slim@sha256:f77ac9e44ae96ef2c90b8053ea08c31f8be030f824196b0ae4db6d462c84e51f
LABEL roboengineer.instance_sha256="fc5c536e5585e7adf7c781ef8d714473bfb3e5fc77da801d5828b7b28cee978c"
COPY test.sh instance.json /tests/
COPY --from=ghcr.io/mll-lab-nu/efe:roboengineer-files-0.4.0@sha256:710f5232e0c81ad59397c1612cc015a471cb3f0fe12a1599ad11d888b80d3609 /standard/tests/grade.py /tests/grade.py
RUN echo 'fc5c536e5585e7adf7c781ef8d714473bfb3e5fc77da801d5828b7b28cee978c  /tests/instance.json' | sha256sum -c - && chmod +x /tests/test.sh
# resources (docs/protocol/resources.md) # rcb-monitor
COPY --from=ghcr.io/mll-lab-nu/efe:monitor-0.5.0@sha256:ecc5f24f1516ca11711d7c2d3ac07c89f79cd9220812c1244498ec71e352402a /opt/rcb_monitor/rcb_limits.py /tests/rcb_limits.py
COPY rcb_limits.json /tests/rcb_limits.json
