FROM docker.io/library/python:3.12-slim
RUN pip install --no-cache-dir requests
COPY client.py /opt/tools/client.py
ENV PYTHONPATH=/opt/tools
WORKDIR /app
