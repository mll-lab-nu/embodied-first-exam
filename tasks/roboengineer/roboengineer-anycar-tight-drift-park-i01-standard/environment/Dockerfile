FROM ghcr.io/mll-lab-nu/efe:control-transfer-0.2.0-nominal
WORKDIR /app
COPY public/ /app/
COPY --from=ghcr.io/mll-lab-nu/efe:roboengineer-files-0.4.0@sha256:8dc6a958bd2b65394d7b4af4ffb6e20b106a2adea1af43fef2cd9ec1677ab696 /anycarbench/LICENSE.anycar /anycarbench/model.py /anycarbench/drift_v3.py /app/anycarbench/
COPY --from=ghcr.io/mll-lab-nu/efe:roboengineer-files-0.4.0@sha256:8dc6a958bd2b65394d7b4af4ffb6e20b106a2adea1af43fef2cd9ec1677ab696 /anycarbench/LICENSE.anycar /anycarbench/model.py /anycarbench/drift_v3.py /app/scripts/control_transfer/components/anycarbench/
COPY --from=ghcr.io/mll-lab-nu/efe:roboengineer-files-0.4.0@sha256:8dc6a958bd2b65394d7b4af4ffb6e20b106a2adea1af43fef2cd9ec1677ab696 /standard/environment/public/control_public/client.py /standard/environment/public/control_public/weights.py /standard/environment/public/control_public/anycar_drift_feedback.py /standard/environment/public/control_public/anycar_drift_v3.py /standard/environment/public/control_public/anycar_drift_v3_nominal.py /app/control_public/
COPY --from=ghcr.io/mll-lab-nu/efe:roboengineer-files-0.4.0@sha256:8dc6a958bd2b65394d7b4af4ffb6e20b106a2adea1af43fef2cd9ec1677ab696 /standard/environment/public/control_public/client.py /standard/environment/public/control_public/weights.py /standard/environment/public/control_public/anycar_drift_feedback.py /standard/environment/public/control_public/anycar_drift_v3.py /standard/environment/public/control_public/anycar_drift_v3_nominal.py /app/scripts/control_transfer/control_public/
ENV PYTHONPATH=/app OPENBLAS_NUM_THREADS=1 MUJOCO_GL=osmesa
RUN mkdir -p /app/output
