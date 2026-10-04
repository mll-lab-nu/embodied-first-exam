# Standard mode: the agent container has no simulator and no HumanoidBench code -- only Python and the client.
FROM {{client_image}}
COPY client-requirements.txt /tmp/
RUN pip install --no-cache-dir -r /tmp/client-requirements.txt
COPY rcb_client.py rcb1.py /opt/tools/
ENV PYTHONPATH=/opt/tools
RUN mkdir -p /app/output
WORKDIR /app
