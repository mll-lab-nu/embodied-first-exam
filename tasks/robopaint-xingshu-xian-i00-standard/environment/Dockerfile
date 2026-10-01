# Standard mode: the agent container has NO simulator, no brush model and no tooling — only Python, the client, the target picture
# (target.png) and its licence notice. Base image and pip pins: the one client base of every standard task
# (scripts/eai_standard/client.env, client-requirements.txt; written by the generator).
FROM docker.io/library/python:3.12-slim@sha256:2f17fc044b579bab302c2e8054d3a686e2cb9a83de48e70534b94cd8ebbe06a9
RUN pip install --no-cache-dir certifi==2026.7.22 charset-normalizer==3.5.2 idna==3.20 numpy==2.5.3 pillow==12.3.0 requests==2.34.2 scipy==1.18.1 urllib3==2.8.0
COPY rcb_client.py rcb1.py /opt/tools/
COPY target.png NOTICE-exemplar.md /app/
ENV PYTHONPATH=/opt/tools
RUN mkdir -p /app/output
WORKDIR /app
