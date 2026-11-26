# Base image = KinDER (images/kinder/). Everything task-specific is copied here.
FROM ghcr.io/mll-lab-nu/efe:kinder-0.1.6
COPY instance.json /app/instance.json
COPY --from=ghcr.io/mll-lab-nu/efe:kinder-files-0.5.0@sha256:d6c9a27447f2915facc2ddbe9ae226e839d028786d44c39e697985486d733522 /privileged/environment/rcb_kinder.py /opt/tools/rcb_kinder.py
ENV PYTHONPATH=/opt/tools
RUN mkdir -p /app/output
WORKDIR /app
