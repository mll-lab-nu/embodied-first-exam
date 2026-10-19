FROM docker.io/library/python:3.12.14-slim@sha256:f77ac9e44ae96ef2c90b8053ea08c31f8be030f824196b0ae4db6d462c84e51f
LABEL roboengineer.instance_sha256="1f2172617d54b68fa6ca18544b58dd8e8295f6c8e9870606b281e8dd8cdc431b"
COPY test.sh instance.json /tests/
COPY --from=ghcr.io/mll-lab-nu/efe:roboengineer-files-0.2.0@sha256:ba990671b5b877a27996906464cb06c07bd0e237c0ec5762053a2540c4af0e6b /standard/tests/grade.py /tests/grade.py
RUN echo '1f2172617d54b68fa6ca18544b58dd8e8295f6c8e9870606b281e8dd8cdc431b  /tests/instance.json' | sha256sum -c - && chmod +x /tests/test.sh
# resource limits: the verifier step (from the monitor image) and its copy of the limits (docs/protocol/README.md §2.10) # rcb-monitor
COPY --from=ghcr.io/mll-lab-nu/efe:monitor-0.2.0@sha256:65442d9e9eeb493d785a59d48a321345e2b48186946cc9d55beb684182514b4b /opt/rcb_monitor/rcb_limits.py /tests/rcb_limits.py
COPY rcb_limits.json /tests/rcb_limits.json
