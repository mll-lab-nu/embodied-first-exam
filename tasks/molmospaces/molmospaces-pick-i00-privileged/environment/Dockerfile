# Base image = MolmoSpaces (molmo-spaces 0.2.9, MuJoCo 3.5.0) + the assets of the frozen instances (images/molmospaces/).
FROM ghcr.io/mll-lab-nu/efe:molmospaces-0.2.5
COPY instance.json /app/instance.json
COPY --from=ghcr.io/mll-lab-nu/efe:molmospaces-files-0.5.0@sha256:ea993336748fd6f3c8801d15d275ec90fd7a0e89ff0d1dadc07663f722b81800 /privileged/environment/rcb_molmospaces.py /opt/tools/rcb_molmospaces.py
ENV PYTHONPATH=/opt/tools
RUN mkdir -p /app/output
WORKDIR /app
