# Standard mode: the agent container has no simulator and no task code -- only Python and the client.
FROM docker.io/library/python:3.12.14-slim@sha256:f77ac9e44ae96ef2c90b8053ea08c31f8be030f824196b0ae4db6d462c84e51f
COPY client-requirements.txt /tmp/
RUN pip install --no-cache-dir -r /tmp/client-requirements.txt
COPY --from=ghcr.io/mll-lab-nu/efe:standard-files-0.1.0@sha256:9c2e0818bfffddb463167566942af946862a60bf260f1400468f0d6f3ffd32b1 /rcb1.py /opt/tools/rcb1.py
COPY --from=ghcr.io/mll-lab-nu/efe:ese-files-0.3.0@sha256:246599a45785ef8a3d1ca6967f90f22780ec7003d2a5e3bde01b7ce841942ffb /standard/rcb_client.py /opt/tools/rcb_client.py
ENV PYTHONPATH=/opt/tools
RUN mkdir -p /app/output
WORKDIR /app
