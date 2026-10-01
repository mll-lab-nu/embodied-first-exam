FROM ghcr.io/jameskrw/rcb-mujoco:0.1.1
COPY instance.json /app/instance.json
COPY rcb_aloha.py /opt/tools/rcb_aloha.py
ENV PYTHONPATH=/opt/tools
RUN mkdir -p /app/output
WORKDIR /app
