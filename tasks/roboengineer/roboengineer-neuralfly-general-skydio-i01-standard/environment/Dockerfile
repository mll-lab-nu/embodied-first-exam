FROM ghcr.io/mll-lab-nu/efe-private:control-transfer-0.2.0-nominal
WORKDIR /app
COPY public/ /app/
COPY --from=ghcr.io/mll-lab-nu/efe-private:roboengineer-files-0.1.0@sha256:7ffc4213019f7d88bd5072a8c1d56936a2b3f78cad7c7aea920a33794749d040 /standard/environment/public/control_public/client.py /standard/environment/public/control_public/weights.py /standard/environment/public/control_public/fly.py /app/control_public/
COPY --from=ghcr.io/mll-lab-nu/efe-private:roboengineer-files-0.1.0@sha256:7ffc4213019f7d88bd5072a8c1d56936a2b3f78cad7c7aea920a33794749d040 /standard/environment/public/control_public/client.py /standard/environment/public/control_public/weights.py /standard/environment/public/control_public/fly.py /app/scripts/control_transfer/control_public/
COPY --from=ghcr.io/mll-lab-nu/efe-private:roboengineer-files-0.1.0@sha256:7ffc4213019f7d88bd5072a8c1d56936a2b3f78cad7c7aea920a33794749d040 /standard/environment/public/neuralfly_nominal.py /standard/environment/public/variants/0ef344f0f7/neuralfly_video.py /standard/environment/public/neuralfly_visual.py /app/
COPY --from=ghcr.io/mll-lab-nu/efe-private:roboengineer-files-0.1.0@sha256:7ffc4213019f7d88bd5072a8c1d56936a2b3f78cad7c7aea920a33794749d040 /standard/environment/public/neuralfly_nominal.py /app/nominal_fly.py
COPY --from=ghcr.io/mll-lab-nu/efe-private:roboengineer-files-0.1.0@sha256:7ffc4213019f7d88bd5072a8c1d56936a2b3f78cad7c7aea920a33794749d040 /standard/environment/public/neuralfly_nominal.py /standard/environment/public/variants/0ef344f0f7/neuralfly_video.py /standard/environment/public/neuralfly_visual.py /app/scripts/control_transfer/
ENV PYTHONPATH=/app OPENBLAS_NUM_THREADS=1 MUJOCO_GL=osmesa NEURALFLY_VISUAL_STYLE=skydio-x2/1
RUN mkdir -p /app/output
