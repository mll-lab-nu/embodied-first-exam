# Base image = cap-x robosuite environment (see images/robosuite/). Everything task-specific is copied here.
FROM ghcr.io/mll-lab-nu/eai-robosuite:0.1.1
COPY instance.npz /app/instance.npz
COPY rcb_traj.py /opt/tools/rcb_traj.py
ENV PYTHONPATH=/opt/tools
RUN mkdir -p /app/output
WORKDIR /app
