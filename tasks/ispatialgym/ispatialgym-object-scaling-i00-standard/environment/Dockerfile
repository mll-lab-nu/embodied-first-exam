# Standard mode: the agent container has NO simulator and no iSpatialGym code — only Python, the client and the goal
# image. The base image and the pip pins are the shared eai-standard client (scripts/eai_standard/client.env,
# client-requirements.txt).
FROM docker.io/library/python:3.12.14-slim@sha256:f77ac9e44ae96ef2c90b8053ea08c31f8be030f824196b0ae4db6d462c84e51f
COPY client-requirements.txt /tmp/client-requirements.txt
RUN pip install --no-cache-dir -r /tmp/client-requirements.txt
COPY --from=ghcr.io/mll-lab-nu/efe:standard-files-0.1.0@sha256:9c2e0818bfffddb463167566942af946862a60bf260f1400468f0d6f3ffd32b1 /rcb_client.py /rcb1.py /opt/tools/
ENV PYTHONPATH=/opt/tools
COPY goal.png /app/goal.png
RUN mkdir -p /app/output
WORKDIR /app
