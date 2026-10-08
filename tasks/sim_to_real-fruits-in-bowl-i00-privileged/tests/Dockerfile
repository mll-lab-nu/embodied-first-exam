# Separate verifier sandbox (PROTOCOL §2.6): the base image with the verifier's own copies of the tooling and the
# frozen instance; only the declared artifacts (/app/output/, /logs/agent/rcb/) arrive from the agent.
FROM ghcr.io/mll-lab-nu/eai-sim_to_real:0.2.0
COPY grade.py instance.json rcb_yam.py test.sh /tests/
RUN chmod +x /tests/test.sh && mkdir -p /app/output /logs/verifier
ENV PYTHONPATH=/tests
WORKDIR /tests
