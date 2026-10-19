# Base image = MolmoSpaces (molmo-spaces 0.2.9, MuJoCo 3.5.0) + the assets of the frozen instances (images/molmospaces/).
FROM ghcr.io/mll-lab-nu/efe:molmospaces-0.2.5
COPY instance.json /app/instance.json
COPY --from=ghcr.io/mll-lab-nu/efe:molmospaces-files-0.1.0@sha256:75e95b38326e03705b89d95bdfb2dafcaf2b9105e9e52d4ac2d65bc3f568a93d /privileged/environment/rcb_molmospaces.py /opt/tools/rcb_molmospaces.py
ENV PYTHONPATH=/opt/tools
RUN mkdir -p /app/output
WORKDIR /app
