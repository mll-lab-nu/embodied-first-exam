FROM ghcr.io/jameskrw/rcb-metaworldplus:0.1.0
RUN python -c "import pathlib,metaworld,shutil; shutil.rmtree(pathlib.Path(metaworld.__file__).parent/'policies')"
COPY mw_runtime.py archive.py /opt/tools/
COPY instance.npz /app/instance.npz
ENV PYTHONPATH=/opt/tools
RUN mkdir -p /app/output
WORKDIR /app

COPY warm_session.py /opt/rcb-setup/warm_session.py
COPY warm_session.py /app/warm_session.py
ENV RCB_WARM_CLIENT=1
ENV PYTHONPATH=/opt/rcb-setup:/opt/tools
