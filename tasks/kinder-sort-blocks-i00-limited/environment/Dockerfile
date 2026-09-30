# Limited mode: the agent container has NO simulator and no KinDER code -- only Python and the client.
FROM docker.io/library/python:3.12.14-slim
RUN pip install --no-cache-dir requests==2.34.2 numpy==2.5.3 pillow==12.3.0 scipy==1.18.1
COPY rcb_client.py /opt/tools/rcb_client.py
ENV PYTHONPATH=/opt/tools
RUN mkdir -p /app/output
WORKDIR /app
