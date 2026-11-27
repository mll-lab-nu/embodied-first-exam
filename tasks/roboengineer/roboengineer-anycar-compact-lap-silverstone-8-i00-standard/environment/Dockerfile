FROM ghcr.io/mll-lab-nu/efe:control-transfer-0.2.0-nominal
WORKDIR /app
COPY public/ /app/
COPY --from=ghcr.io/mll-lab-nu/efe:roboengineer-files-0.4.0@sha256:8dc6a958bd2b65394d7b4af4ffb6e20b106a2adea1af43fef2cd9ec1677ab696 /anycarbench/LICENSE.anycar /anycarbench/LICENSE.f1db /anycarbench/NOTICE /anycarbench/model.py /anycarbench/route_lengths.json /anycarbench/tracks.py /app/anycarbench/
COPY --from=ghcr.io/mll-lab-nu/efe:roboengineer-files-0.4.0@sha256:8dc6a958bd2b65394d7b4af4ffb6e20b106a2adea1af43fef2cd9ec1677ab696 /anycarbench/LICENSE.anycar /anycarbench/LICENSE.f1db /anycarbench/NOTICE /anycarbench/model.py /anycarbench/route_lengths.json /anycarbench/tracks.py /app/scripts/control_transfer/components/anycarbench/
COPY --from=ghcr.io/mll-lab-nu/efe:roboengineer-files-0.4.0@sha256:8dc6a958bd2b65394d7b4af4ffb6e20b106a2adea1af43fef2cd9ec1677ab696 /standard/environment/public/control_public/anycar.py /standard/environment/public/control_public/anycar_nominal.py /standard/environment/public/control_public/client.py /standard/environment/public/control_public/weights.py /app/control_public/
COPY --from=ghcr.io/mll-lab-nu/efe:roboengineer-files-0.4.0@sha256:8dc6a958bd2b65394d7b4af4ffb6e20b106a2adea1af43fef2cd9ec1677ab696 /standard/environment/public/control_public/anycar.py /standard/environment/public/control_public/anycar_nominal.py /standard/environment/public/control_public/client.py /standard/environment/public/control_public/weights.py /app/scripts/control_transfer/control_public/
COPY --from=ghcr.io/mll-lab-nu/efe:roboengineer-files-0.4.0@sha256:8dc6a958bd2b65394d7b4af4ffb6e20b106a2adea1af43fef2cd9ec1677ab696 /anycarbench/circuits.json /app/anycarbench/circuits.json
COPY --from=ghcr.io/mll-lab-nu/efe:roboengineer-files-0.4.0@sha256:8dc6a958bd2b65394d7b4af4ffb6e20b106a2adea1af43fef2cd9ec1677ab696 /anycarbench/compact_routes.json /app/anycarbench/compact_routes.json
COPY --from=ghcr.io/mll-lab-nu/efe:roboengineer-files-0.4.0@sha256:8dc6a958bd2b65394d7b4af4ffb6e20b106a2adea1af43fef2cd9ec1677ab696 /anycarbench/circuits.json /app/scripts/control_transfer/components/anycarbench/circuits.json
COPY --from=ghcr.io/mll-lab-nu/efe:roboengineer-files-0.4.0@sha256:8dc6a958bd2b65394d7b4af4ffb6e20b106a2adea1af43fef2cd9ec1677ab696 /anycarbench/compact_routes.json /app/scripts/control_transfer/components/anycarbench/compact_routes.json
ENV PYTHONPATH=/app OPENBLAS_NUM_THREADS=1 MUJOCO_GL=osmesa CONTROL_DEPLOY_TIMEOUT_S=1200
RUN mkdir -p /app/output
