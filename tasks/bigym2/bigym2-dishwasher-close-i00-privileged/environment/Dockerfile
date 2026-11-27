# Base image = BiGym 2.0 (bigym 1.0.0, MuJoCo 3.8.1, GR00T-WBC) (images/bigym2/). Everything task-specific is copied here.
FROM ghcr.io/mll-lab-nu/efe:bigym2-0.1.1
COPY instance.json /app/instance.json
COPY --from=ghcr.io/mll-lab-nu/efe:bigym2-files-0.7.0@sha256:c689fc0786107d0ef1d41b9aeb76c087215c9b3de60dc84028861818fdf4399c /privileged/environment/rcb_bigym2.py /opt/tools/rcb_bigym2.py
ENV PYTHONPATH=/opt/tools
RUN mkdir -p /app/output
WORKDIR /app
