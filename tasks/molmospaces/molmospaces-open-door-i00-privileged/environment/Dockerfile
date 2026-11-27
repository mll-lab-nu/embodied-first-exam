# Base image = MolmoSpaces (molmo-spaces 0.2.9, MuJoCo 3.5.0) + the assets of the frozen instances (images/molmospaces/).
FROM ghcr.io/mll-lab-nu/efe:molmospaces-0.2.5
COPY instance.json /app/instance.json
COPY --from=ghcr.io/mll-lab-nu/efe:molmospaces-files-0.8.0@sha256:ccb4e9a60c9a404271f1de1bd7796895d943884d2c0113e7387c66b2072156d2 /privileged/environment/rcb_molmospaces.py /opt/tools/rcb_molmospaces.py
ENV PYTHONPATH=/opt/tools
RUN mkdir -p /app/output
WORKDIR /app
