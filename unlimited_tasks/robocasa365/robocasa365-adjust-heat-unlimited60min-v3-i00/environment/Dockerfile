FROM ghcr.io/jameskrw/rcb-robocasa365:0.1.0
COPY casa_runtime.py casa_contract.py archive.py /opt/tools/
COPY instance.npz action_spec.json /app/
ENV PYTHONPATH=/opt/tools
RUN mkdir -p /app/output
WORKDIR /app

COPY warm_session.py /opt/rcb-setup/warm_session.py
COPY warm_session.py /app/warm_session.py
ENV RCB_WARM_CLIENT=1
ENV PYTHONPATH=/opt/rcb-setup:/opt/tools
