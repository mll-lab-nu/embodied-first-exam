# Base image = BiGym 2.0 (bigym 1.0.0, MuJoCo 3.8.1, GR00T-WBC) (images/bigym2/). Everything task-specific is copied here.
FROM ghcr.io/mll-lab-nu/efe:bigym2-0.1.1
COPY instance.json /app/instance.json
COPY --from=ghcr.io/mll-lab-nu/efe:bigym2-files-0.4.1@sha256:7f7725261d7a32d4bb178738cb55ed6869d732385f2f04cab75c7b86e9e0a616 /privileged/environment/rcb_bigym2.py /opt/tools/rcb_bigym2.py
ENV PYTHONPATH=/opt/tools
RUN mkdir -p /app/output
WORKDIR /app
