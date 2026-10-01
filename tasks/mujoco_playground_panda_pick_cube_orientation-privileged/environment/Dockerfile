FROM ghcr.io/jameskrw/rcb-mujoco:0.1.2
COPY instance.json /app/instance.json
COPY rcb_panda.py /opt/tools/rcb_panda.py
ENV PYTHONPATH=/opt/tools
RUN mkdir -p /app/output
WORKDIR /app
