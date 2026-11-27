# Separate verifier sandbox: the same image with the verifier's own copies of the tooling and the frozen instance;
# only the declared artifacts (/app/output/) arrive from the agent.
FROM ghcr.io/mll-lab-nu/efe:robocasa365-0.1.0
COPY test.sh instance.npz /tests/
COPY --from=ghcr.io/mll-lab-nu/efe:robocasa365-files-0.7.0@sha256:0dad1b28d16dd1311ed627d7b1c78fa05cea481a4ed507ba835efcd9c552394e /privileged/environment/casa_tool.py /tests/casa_tool.py
COPY --from=ghcr.io/mll-lab-nu/efe:robocasa-files-0.6.0@sha256:a0fd0e294af7e2f6140d08f31fca13dc32c8186d4086ceabfa406290b0dbde88 /privileged/tests/grade.py /tests/grade.py
RUN chmod +x /tests/test.sh && mkdir -p /app/output /logs/verifier
ENV PYTHONPATH=/tests
WORKDIR /tests
# resources (PROTOCOL §6) # rcb-monitor
COPY --from=ghcr.io/mll-lab-nu/efe:monitor-0.5.0@sha256:ecc5f24f1516ca11711d7c2d3ac07c89f79cd9220812c1244498ec71e352402a /opt/rcb_monitor/rcb_limits.py /tests/rcb_limits.py
COPY rcb_limits.json /tests/rcb_limits.json
