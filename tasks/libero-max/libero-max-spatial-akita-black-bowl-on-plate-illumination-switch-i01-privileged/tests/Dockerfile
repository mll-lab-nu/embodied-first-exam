# Separate verifier sandbox: the same image with the verifier's own copies of the tooling and the frozen instance;
# only the declared artifacts (/app/output/) arrive from the agent.
FROM ghcr.io/mll-lab-nu/efe:libero-max-0.1.1
COPY test.sh instance.json /tests/
COPY --from=ghcr.io/mll-lab-nu/efe:libero-max-files-0.7.0@sha256:d86ed6487b22d8a3ee255667a7bf9fb53accbf916cc81db2a62c88261269c6b8 /privileged/environment/lmx_tool.py /privileged/tests/grade.py /tests/
RUN chmod +x /tests/test.sh && mkdir -p /app/output /logs/verifier
ENV PYTHONPATH=/tests:/opt/libero-max/overlay:/opt/libero-max/src
WORKDIR /tests
# resources (docs/protocol/resources.md) # rcb-monitor
COPY --from=ghcr.io/mll-lab-nu/efe:monitor-0.5.0@sha256:ecc5f24f1516ca11711d7c2d3ac07c89f79cd9220812c1244498ec71e352402a /opt/rcb_monitor/rcb_limits.py /tests/rcb_limits.py
COPY rcb_limits.json /tests/rcb_limits.json
