# Separate verifier sandbox: the same image with the verifier's own copies of the tooling and the frozen instance, and
# the request's label; only the declared artifacts (/app/output/) arrive from the agent.
FROM ghcr.io/mll-lab-nu/eai-hazardarena:0.1.0
COPY test.sh grade.py ha_tool.py instance.json label.json /tests/
RUN chmod +x /tests/test.sh && mkdir -p /app/output /logs/verifier
ENV PYTHONPATH=/tests:/opt/HazardArena:/opt/rrt-algorithms
WORKDIR /tests
