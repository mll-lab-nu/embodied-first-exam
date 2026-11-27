FROM docker.io/library/python:3.12.14-slim@sha256:f77ac9e44ae96ef2c90b8053ea08c31f8be030f824196b0ae4db6d462c84e51f
LABEL roboengineer.instance_sha256="826ea04a1eb08af9c955e329e8e992e7b807cba9a01ddda7c8eaecb3c372e5b6"
COPY test.sh instance.json /tests/
COPY --from=ghcr.io/mll-lab-nu/efe:roboengineer-files-0.4.0@sha256:8dc6a958bd2b65394d7b4af4ffb6e20b106a2adea1af43fef2cd9ec1677ab696 /standard/tests/grade.py /tests/grade.py
RUN echo '826ea04a1eb08af9c955e329e8e992e7b807cba9a01ddda7c8eaecb3c372e5b6  /tests/instance.json' | sha256sum -c - && chmod +x /tests/test.sh
# resources (PROTOCOL §6) # rcb-monitor
COPY --from=ghcr.io/mll-lab-nu/efe:monitor-0.5.0@sha256:ecc5f24f1516ca11711d7c2d3ac07c89f79cd9220812c1244498ec71e352402a /opt/rcb_monitor/rcb_limits.py /tests/rcb_limits.py
COPY rcb_limits.json /tests/rcb_limits.json
