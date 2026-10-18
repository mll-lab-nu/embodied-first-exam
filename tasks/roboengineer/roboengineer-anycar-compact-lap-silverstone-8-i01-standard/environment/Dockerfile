FROM ghcr.io/mll-lab-nu/eai-control-transfer:0.2.0-nominal
WORKDIR /app
COPY public/ /app/
COPY --from=ghcr.io/mll-lab-nu/eai-control-transfer-anycar-files:0.1.0@sha256:5b4f9dab86b3d77decba4d0199646c3c1cd8e02adde165abfecbb9943997b373 /circuits.json /app/anycarbench/circuits.json
COPY --from=ghcr.io/mll-lab-nu/eai-control-transfer-anycar-files:0.1.0@sha256:5b4f9dab86b3d77decba4d0199646c3c1cd8e02adde165abfecbb9943997b373 /compact_routes.json /app/anycarbench/compact_routes.json
COPY --from=ghcr.io/mll-lab-nu/eai-control-transfer-anycar-files:0.1.0@sha256:5b4f9dab86b3d77decba4d0199646c3c1cd8e02adde165abfecbb9943997b373 /circuits.json /app/scripts/control_transfer/components/anycarbench/circuits.json
COPY --from=ghcr.io/mll-lab-nu/eai-control-transfer-anycar-files:0.1.0@sha256:5b4f9dab86b3d77decba4d0199646c3c1cd8e02adde165abfecbb9943997b373 /compact_routes.json /app/scripts/control_transfer/components/anycarbench/compact_routes.json
ENV PYTHONPATH=/app OPENBLAS_NUM_THREADS=1 MUJOCO_GL=osmesa CONTROL_DEPLOY_TIMEOUT_S=1200
RUN mkdir -p /app/output
