FROM ghcr.io/mll-lab-nu/efe:control-transfer-0.2.0-nominal
WORKDIR /app
COPY public/ /app/
COPY --from=ghcr.io/mll-lab-nu/efe:roboengineer-files-0.3.0-abl@sha256:a6cc6825562f3c119805f700dcceb7f2cc106eff44bf0873960856de5ab119de /standard/environment/public/control_public/client.py /standard/environment/public/control_public/weights.py /standard/environment/public/control_public/fly.py /app/control_public/
COPY --from=ghcr.io/mll-lab-nu/efe:roboengineer-files-0.3.0-abl@sha256:a6cc6825562f3c119805f700dcceb7f2cc106eff44bf0873960856de5ab119de /standard/environment/public/control_public/client.py /standard/environment/public/control_public/weights.py /standard/environment/public/control_public/fly.py /app/scripts/control_transfer/control_public/
COPY --from=ghcr.io/mll-lab-nu/efe:roboengineer-files-0.3.0-abl@sha256:a6cc6825562f3c119805f700dcceb7f2cc106eff44bf0873960856de5ab119de /standard/environment/public/neuralfly_nominal.py /standard/environment/public/variants/0ef344f0f7/neuralfly_video.py /standard/environment/public/neuralfly_visual.py /app/
COPY --from=ghcr.io/mll-lab-nu/efe:roboengineer-files-0.3.0-abl@sha256:a6cc6825562f3c119805f700dcceb7f2cc106eff44bf0873960856de5ab119de /standard/environment/public/neuralfly_nominal.py /app/nominal_fly.py
COPY --from=ghcr.io/mll-lab-nu/efe:roboengineer-files-0.3.0-abl@sha256:a6cc6825562f3c119805f700dcceb7f2cc106eff44bf0873960856de5ab119de /standard/environment/public/neuralfly_nominal.py /standard/environment/public/variants/0ef344f0f7/neuralfly_video.py /standard/environment/public/neuralfly_visual.py /app/scripts/control_transfer/
ENV PYTHONPATH=/app OPENBLAS_NUM_THREADS=1 MUJOCO_GL=osmesa NEURALFLY_VISUAL_STYLE=skydio-x2/1
RUN mkdir -p /app/output
