# Base image = KinDER (images/kinder/). Everything task-specific is copied here.
# Generated from scripts/kinder/templates/Dockerfile -- edit the template, not this copy.
FROM {{image}}
COPY instance.json /app/instance.json
COPY rcb_kinder.py /opt/tools/rcb_kinder.py
ENV PYTHONPATH=/opt/tools
RUN mkdir -p /app/output
WORKDIR /app
