# Base image = MolmoSpaces (molmo-spaces 0.2.9, MuJoCo 3.5.0) + the assets of the frozen instances (images/molmospaces/).
FROM ghcr.io/mll-lab-nu/efe:molmospaces-0.2.5
COPY instance.json /app/instance.json
COPY --from=ghcr.io/mll-lab-nu/efe:molmospaces-files-0.8.0@sha256:585b6553aef9333a610c08b03e880c56c7e756820e9870c62fce3a46a7e8cad4 /privileged/environment/rcb_molmospaces.py /opt/tools/rcb_molmospaces.py
ENV PYTHONPATH=/opt/tools
RUN mkdir -p /app/output
WORKDIR /app
