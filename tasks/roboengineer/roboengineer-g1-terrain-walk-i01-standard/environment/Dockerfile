FROM ghcr.io/mll-lab-nu/efe:control-transfer-0.2.0-train
WORKDIR /app
COPY public/ /app/
COPY --from=ghcr.io/mll-lab-nu/efe:roboengineer-files-0.2.0@sha256:ba990671b5b877a27996906464cb06c07bd0e237c0ec5762053a2540c4af0e6b /standard/environment/public/control_public/client.py /standard/environment/public/control_public/weights.py /standard/environment/public/control_public/g1_training.py /app/control_public/
COPY --from=ghcr.io/mll-lab-nu/efe:roboengineer-files-0.2.0@sha256:ba990671b5b877a27996906464cb06c07bd0e237c0ec5762053a2540c4af0e6b /standard/environment/public/control_public/client.py /standard/environment/public/control_public/weights.py /standard/environment/public/control_public/g1_training.py /app/scripts/control_transfer/control_public/
ENV PYTHONPATH=/app OPENBLAS_NUM_THREADS=1 MUJOCO_GL=osmesa
RUN mkdir -p /app/output
