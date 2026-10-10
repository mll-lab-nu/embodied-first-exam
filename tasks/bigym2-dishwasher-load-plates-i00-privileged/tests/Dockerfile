# Separate verifier sandbox (PROTOCOL §2.6): the same simulator image with the verifier's own copies of the tooling and
# the frozen instance. Nothing the agent did in its container reaches this one: Harbor uploads only /app/output/.
FROM ghcr.io/mll-lab-nu/eai-bigym2:0.1.1
COPY grade.py instance.json rcb_bigym2.py test.sh /tests/
RUN chmod +x /tests/test.sh && mkdir -p /app/output /logs/verifier
ENV PYTHONPATH=/tests
WORKDIR /tests
