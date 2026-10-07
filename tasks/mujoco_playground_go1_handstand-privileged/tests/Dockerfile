# Separate verifier sandbox (PROTOCOL §4): the same image with the verifier's own copies of the tooling and the frozen
# instance. Nothing the agent did in its container reaches this one: Harbor uploads only the declared artifacts.
FROM ghcr.io/mll-lab-nu/eai-mujoco:0.1.3
COPY grade.py instance.json rcb_quadruped.py test.sh /tests/
RUN chmod +x /tests/test.sh && mkdir -p /app/output /logs/verifier
ENV PYTHONPATH=/tests
WORKDIR /tests
