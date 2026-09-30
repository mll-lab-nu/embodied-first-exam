FROM ghcr.io/jameskrw/rcb-vlabench:0.1.1
COPY strip_experts.py /tmp/strip_experts.py
RUN python /tmp/strip_experts.py /opt/VLABench/VLABench && \
    python -c "import pathlib, shutil; p=pathlib.Path('/usr/local/lib/python3.10/site-packages/VLABench'); shutil.rmtree(p) if p.exists() else None; [shutil.rmtree(p) for p in [pathlib.Path('/opt/VLABench/.git'), pathlib.Path('/opt/VLABench/scripts')] if p.exists()]"
COPY vlb_traj.py /opt/tools/vlb_traj.py
COPY instance.json /app/instance.json
COPY API.md /app/API.md
COPY versions.json /app/versions.json
ENV PYTHONPATH=/opt/tools:/opt/VLABench:/opt/rrt-algorithms
RUN mkdir -p /app/output
WORKDIR /app

COPY warm_session.py /opt/rcb-setup/warm_session.py
COPY warm_session.py /app/warm_session.py
ENV RCB_WARM_CLIENT=1
ENV PYTHONPATH=/opt/rcb-setup:/opt/tools:/opt/VLABench:/opt/rrt-algorithms
