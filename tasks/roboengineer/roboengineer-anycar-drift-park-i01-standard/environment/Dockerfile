FROM ghcr.io/mll-lab-nu/efe-private:control-transfer-0.2.0-nominal
WORKDIR /app
COPY public/ /app/
COPY --from=ghcr.io/mll-lab-nu/efe-private:roboengineer-files-0.1.0@sha256:7ffc4213019f7d88bd5072a8c1d56936a2b3f78cad7c7aea920a33794749d040 /standard/environment/public/anycarbench/LICENSE.anycar /standard/environment/public/anycarbench/model.py /standard/environment/public/anycarbench/drift.py /app/anycarbench/
COPY --from=ghcr.io/mll-lab-nu/efe-private:roboengineer-files-0.1.0@sha256:7ffc4213019f7d88bd5072a8c1d56936a2b3f78cad7c7aea920a33794749d040 /standard/environment/public/anycarbench/LICENSE.anycar /standard/environment/public/anycarbench/model.py /standard/environment/public/anycarbench/drift.py /app/scripts/control_transfer/components/anycarbench/
COPY --from=ghcr.io/mll-lab-nu/efe-private:roboengineer-files-0.1.0@sha256:7ffc4213019f7d88bd5072a8c1d56936a2b3f78cad7c7aea920a33794749d040 /standard/environment/public/control_public/client.py /standard/environment/public/control_public/weights.py /standard/environment/public/control_public/anycar_drift.py /standard/environment/public/control_public/anycar_drift_nominal.py /app/control_public/
COPY --from=ghcr.io/mll-lab-nu/efe-private:roboengineer-files-0.1.0@sha256:7ffc4213019f7d88bd5072a8c1d56936a2b3f78cad7c7aea920a33794749d040 /standard/environment/public/control_public/client.py /standard/environment/public/control_public/weights.py /standard/environment/public/control_public/anycar_drift.py /standard/environment/public/control_public/anycar_drift_nominal.py /app/scripts/control_transfer/control_public/
ENV PYTHONPATH=/app OPENBLAS_NUM_THREADS=1 MUJOCO_GL=osmesa
RUN mkdir -p /app/output
