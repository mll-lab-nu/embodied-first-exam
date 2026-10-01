# Standard mode: the agent container has no simulator and no KinDER code -- only Python and the client.
FROM {{client_image}}
RUN pip install --no-cache-dir requests==2.34.2 numpy==2.5.3 pillow==12.3.0 scipy==1.18.1
COPY rcb_client.py rcb1.py /opt/tools/
ENV PYTHONPATH=/opt/tools
RUN mkdir -p /app/output
WORKDIR /app
