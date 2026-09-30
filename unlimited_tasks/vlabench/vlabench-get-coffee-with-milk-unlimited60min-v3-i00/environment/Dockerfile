FROM ghcr.io/jameskrw/rcb-vlabench:0.1.1
COPY strip_experts.py /tmp/strip_experts.py
RUN python /tmp/strip_experts.py /opt/VLABench/VLABench
COPY vlb_traj.py /opt/tools/vlb_traj.py
COPY instance* /app/
COPY API.md /app/API.md
ENV PYTHONPATH=/opt/tools:/opt/VLABench:/opt/rrt-algorithms
RUN mkdir -p /app/output
WORKDIR /app

COPY warm_session.py /opt/rcb-setup/warm_session.py
COPY warm_session.py /app/warm_session.py
ENV RCB_WARM_CLIENT=1
ENV PYTHONPATH=/opt/rcb-setup:/opt/tools:/opt/VLABench:/opt/rrt-algorithms
