# Standard-realtime mode: the agent container has no simulator and no RoboOlympics code -- only Python, the client and
# OpenCV (RoboOlympics' player image).
FROM {{client_image}}
COPY client-requirements.txt /tmp/
RUN pip install --no-cache-dir -r /tmp/client-requirements.txt
RUN pip install --no-cache-dir -c /tmp/client-requirements.txt opencv-python-headless==5.0.0.93 && pip check
COPY rcb_client.py rcb1.py /opt/tools/
ENV PYTHONPATH=/opt/tools
RUN mkdir -p /app/output
WORKDIR /app
