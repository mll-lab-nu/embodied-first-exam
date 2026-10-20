FROM ghcr.io/mll-lab-nu/efe:control-transfer-0.2.0-nominal
WORKDIR /app
COPY public/ /app/
COPY --from=ghcr.io/mll-lab-nu/efe:roboengineer-files-0.2.1@sha256:b340b9c99d3c46a9461d01667ccd2a580ac5f5cda0fdab114c09c8591eabbda1 /standard/environment/public/anycarbench/LICENSE.anycar /standard/environment/public/anycarbench/model.py /standard/environment/public/anycarbench/drift_v3.py /app/anycarbench/
COPY --from=ghcr.io/mll-lab-nu/efe:roboengineer-files-0.2.1@sha256:b340b9c99d3c46a9461d01667ccd2a580ac5f5cda0fdab114c09c8591eabbda1 /standard/environment/public/anycarbench/LICENSE.anycar /standard/environment/public/anycarbench/model.py /standard/environment/public/anycarbench/drift_v3.py /app/scripts/control_transfer/components/anycarbench/
COPY --from=ghcr.io/mll-lab-nu/efe:roboengineer-files-0.2.1@sha256:b340b9c99d3c46a9461d01667ccd2a580ac5f5cda0fdab114c09c8591eabbda1 /standard/environment/public/control_public/client.py /standard/environment/public/control_public/weights.py /standard/environment/public/control_public/anycar_drift_feedback.py /standard/environment/public/control_public/anycar_drift_v3.py /standard/environment/public/control_public/anycar_drift_v3_nominal.py /app/control_public/
COPY --from=ghcr.io/mll-lab-nu/efe:roboengineer-files-0.2.1@sha256:b340b9c99d3c46a9461d01667ccd2a580ac5f5cda0fdab114c09c8591eabbda1 /standard/environment/public/control_public/client.py /standard/environment/public/control_public/weights.py /standard/environment/public/control_public/anycar_drift_feedback.py /standard/environment/public/control_public/anycar_drift_v3.py /standard/environment/public/control_public/anycar_drift_v3_nominal.py /app/scripts/control_transfer/control_public/
ENV PYTHONPATH=/app OPENBLAS_NUM_THREADS=1 MUJOCO_GL=osmesa
RUN mkdir -p /app/output
