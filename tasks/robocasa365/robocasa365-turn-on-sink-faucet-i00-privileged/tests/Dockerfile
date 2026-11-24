# Separate verifier sandbox: the same image with the verifier's own copies of the tooling and the frozen instance;
# only the declared artifacts (/app/output/) arrive from the agent.
FROM ghcr.io/mll-lab-nu/efe:robocasa365-0.1.0
COPY test.sh instance.npz /tests/
COPY --from=ghcr.io/mll-lab-nu/efe:robocasa365-files-0.5.2@sha256:7531148ffc0e1e3294c87ce6974fca06ef33f7e85efdb4727a116ca83aba1531 /privileged/environment/casa_tool.py /tests/casa_tool.py
COPY --from=ghcr.io/mll-lab-nu/efe:robocasa-files-0.4.2@sha256:61c6aa697fe85938f47792236af2b88bb1e027945d62100bf6edc53ed34feb8a /privileged/tests/grade.py /tests/grade.py
RUN chmod +x /tests/test.sh && mkdir -p /app/output /logs/verifier
ENV PYTHONPATH=/tests
WORKDIR /tests
# resources (PROTOCOL §6) # rcb-monitor
COPY --from=ghcr.io/mll-lab-nu/efe:monitor-0.5.0@sha256:ecc5f24f1516ca11711d7c2d3ac07c89f79cd9220812c1244498ec71e352402a /opt/rcb_monitor/rcb_limits.py /tests/rcb_limits.py
COPY rcb_limits.json /tests/rcb_limits.json
