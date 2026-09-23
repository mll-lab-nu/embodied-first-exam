# Limited mode: the agent container has NO simulator and no HumanoidBench code — only Python and the client.
FROM docker.io/library/python:3.12-slim
RUN pip install --no-cache-dir requests numpy pillow scipy
COPY rcb_client.py /opt/tools/rcb_client.py
ENV PYTHONPATH=/opt/tools
RUN mkdir -p /app/output
WORKDIR /app
