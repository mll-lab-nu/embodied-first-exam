# Base image = the RoboOlympics simulator (MuJoCo 3.3.7 on the CPU, the robot library with its Unitree G1 and H1-2, the walking
# and running policies; images/robofunolympics/). Everything task-specific is copied here: the frozen instance, the
# tooling, the world package and this family's rules.
FROM ghcr.io/mll-lab-nu/eai-robofunolympics:0.2.0
COPY instance.json /app/instance.json
COPY rcb_rfo.py rfo_task.py /opt/tools/
COPY rfo /opt/tools/rfo
ENV PYTHONPATH=/opt/tools
RUN mkdir -p /app/output
WORKDIR /app
