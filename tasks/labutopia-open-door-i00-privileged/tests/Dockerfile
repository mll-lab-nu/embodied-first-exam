# Separate verifier sandbox (PROTOCOL §2.6): the same image with the verifier's own copies of the tooling and the frozen
# instance. Nothing the agent did in its container reaches this one: Harbor uploads only the declared artifacts.
FROM ghcr.io/mll-lab-nu/eai-labutopia:0.1.0
COPY grade.py instance.json rcb_labutopia.py test.sh /tests/
RUN chmod +x /tests/test.sh && mkdir -p /app/output /logs/verifier
ENV PYTHONPATH=/tests
WORKDIR /tests
