# Base image = MolmoSpaces (molmo-spaces 0.2.9, MuJoCo 3.5.0) + the assets of the frozen instances (images/molmospaces/).
FROM ghcr.io/mll-lab-nu/efe:molmospaces-0.2.5
COPY instance.json /app/instance.json
COPY --from=ghcr.io/mll-lab-nu/efe:molmospaces-files-0.7.0@sha256:d3bf0ca2fad858799ca5c39206072d180db36421a76cd6f00596aefa46183b8e /privileged/environment/rcb_molmospaces.py /opt/tools/rcb_molmospaces.py
ENV PYTHONPATH=/opt/tools
RUN mkdir -p /app/output
WORKDIR /app
