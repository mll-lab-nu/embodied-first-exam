FROM ghcr.io/mll-lab-nu/efe:control-transfer-0.2.0-nominal
WORKDIR /app
COPY public/ /app/
COPY --from=ghcr.io/mll-lab-nu/efe:roboengineer-files-0.2.1@sha256:b340b9c99d3c46a9461d01667ccd2a580ac5f5cda0fdab114c09c8591eabbda1 /standard/environment/public/control_public/client.py /standard/environment/public/control_public/weights.py /standard/environment/public/control_public/go2.py /standard/environment/public/control_public/go2_data.py /standard/environment/public/control_public/go2_nominal.py /standard/environment/public/control_public/go2_train.py /app/control_public/
COPY --from=ghcr.io/mll-lab-nu/efe:roboengineer-files-0.2.1@sha256:b340b9c99d3c46a9461d01667ccd2a580ac5f5cda0fdab114c09c8591eabbda1 /standard/environment/public/control_public/client.py /standard/environment/public/control_public/weights.py /standard/environment/public/control_public/go2.py /standard/environment/public/control_public/go2_data.py /standard/environment/public/control_public/go2_nominal.py /standard/environment/public/control_public/go2_train.py /app/scripts/control_transfer/control_public/
ENV PYTHONPATH=/app OPENBLAS_NUM_THREADS=1 MUJOCO_GL=osmesa
RUN mkdir -p /app/output
