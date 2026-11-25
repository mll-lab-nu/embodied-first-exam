FROM ghcr.io/mll-lab-nu/efe:control-transfer-0.2.0-nominal
WORKDIR /app
COPY public/ /app/
COPY --from=ghcr.io/mll-lab-nu/efe:roboengineer-files-0.3.1@sha256:ec2520f7855f520bc032f24960306f290263adcf5c7d24e9083526d6584d2e7a /standard/environment/public/anycarbench/LICENSE.anycar /standard/environment/public/anycarbench/model.py /standard/environment/public/anycarbench/drift.py /app/anycarbench/
COPY --from=ghcr.io/mll-lab-nu/efe:roboengineer-files-0.3.1@sha256:ec2520f7855f520bc032f24960306f290263adcf5c7d24e9083526d6584d2e7a /standard/environment/public/anycarbench/LICENSE.anycar /standard/environment/public/anycarbench/model.py /standard/environment/public/anycarbench/drift.py /app/scripts/control_transfer/components/anycarbench/
COPY --from=ghcr.io/mll-lab-nu/efe:roboengineer-files-0.3.1@sha256:ec2520f7855f520bc032f24960306f290263adcf5c7d24e9083526d6584d2e7a /standard/environment/public/control_public/client.py /standard/environment/public/control_public/weights.py /standard/environment/public/control_public/anycar_drift.py /standard/environment/public/control_public/anycar_drift_nominal.py /app/control_public/
COPY --from=ghcr.io/mll-lab-nu/efe:roboengineer-files-0.3.1@sha256:ec2520f7855f520bc032f24960306f290263adcf5c7d24e9083526d6584d2e7a /standard/environment/public/control_public/client.py /standard/environment/public/control_public/weights.py /standard/environment/public/control_public/anycar_drift.py /standard/environment/public/control_public/anycar_drift_nominal.py /app/scripts/control_transfer/control_public/
ENV PYTHONPATH=/app OPENBLAS_NUM_THREADS=1 MUJOCO_GL=osmesa
RUN mkdir -p /app/output
