FROM docker.io/library/python:3.12.14-slim@sha256:f77ac9e44ae96ef2c90b8053ea08c31f8be030f824196b0ae4db6d462c84e51f
LABEL roboengineer.instance_sha256="28d31f773eeb7d4b85a44ed89051eaac3a7a91b7c028d5643eae87bf8eb69015"
COPY test.sh instance.json /tests/
COPY --from=ghcr.io/mll-lab-nu/efe:roboengineer-files-0.3.0-abl@sha256:a6cc6825562f3c119805f700dcceb7f2cc106eff44bf0873960856de5ab119de /standard/tests/grade.py /tests/grade.py
RUN echo '28d31f773eeb7d4b85a44ed89051eaac3a7a91b7c028d5643eae87bf8eb69015  /tests/instance.json' | sha256sum -c - && chmod +x /tests/test.sh
# resources (PROTOCOL §6) # rcb-monitor
COPY --from=ghcr.io/mll-lab-nu/efe:monitor-0.5.0@sha256:ecc5f24f1516ca11711d7c2d3ac07c89f79cd9220812c1244498ec71e352402a /opt/rcb_monitor/rcb_limits.py /tests/rcb_limits.py
COPY rcb_limits.json /tests/rcb_limits.json
