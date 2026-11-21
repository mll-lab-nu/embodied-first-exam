# Standard mode: the agent container has no simulator, no referee and no Embodied Olympics code -- only Python and the client.
FROM docker.io/library/python:3.12.14-slim@sha256:f77ac9e44ae96ef2c90b8053ea08c31f8be030f824196b0ae4db6d462c84e51f
COPY client-requirements.txt /tmp/
RUN pip install --no-cache-dir -r /tmp/client-requirements.txt
COPY --from=ghcr.io/mll-lab-nu/efe:standard-files-0.4.0-resetpose@sha256:90a9bd8fd47f66371cba9378ccc5954544457eab8dc60efe8d25dfb58ac329aa /rcb1.py /v2_1/rcb_client.py /opt/tools/
ENV PYTHONPATH=/opt/tools
RUN mkdir -p /app/output
WORKDIR /app
