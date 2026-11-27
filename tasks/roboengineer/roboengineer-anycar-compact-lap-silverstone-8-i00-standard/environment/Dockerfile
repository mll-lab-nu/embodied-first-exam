FROM ghcr.io/mll-lab-nu/efe:control-transfer-0.2.0-nominal
WORKDIR /app
COPY public/ /app/
COPY --from=ghcr.io/mll-lab-nu/efe:roboengineer-files-0.3.1@sha256:ec2520f7855f520bc032f24960306f290263adcf5c7d24e9083526d6584d2e7a /anycarbench/LICENSE.anycar /anycarbench/LICENSE.f1db /anycarbench/NOTICE /anycarbench/model.py /anycarbench/route_lengths.json /anycarbench/tracks.py /app/anycarbench/
COPY --from=ghcr.io/mll-lab-nu/efe:roboengineer-files-0.3.1@sha256:ec2520f7855f520bc032f24960306f290263adcf5c7d24e9083526d6584d2e7a /anycarbench/LICENSE.anycar /anycarbench/LICENSE.f1db /anycarbench/NOTICE /anycarbench/model.py /anycarbench/route_lengths.json /anycarbench/tracks.py /app/scripts/control_transfer/components/anycarbench/
COPY --from=ghcr.io/mll-lab-nu/efe:roboengineer-files-0.3.1@sha256:ec2520f7855f520bc032f24960306f290263adcf5c7d24e9083526d6584d2e7a /standard/environment/public/control_public/anycar.py /standard/environment/public/control_public/anycar_nominal.py /standard/environment/public/control_public/client.py /standard/environment/public/control_public/weights.py /app/control_public/
COPY --from=ghcr.io/mll-lab-nu/efe:roboengineer-files-0.3.1@sha256:ec2520f7855f520bc032f24960306f290263adcf5c7d24e9083526d6584d2e7a /standard/environment/public/control_public/anycar.py /standard/environment/public/control_public/anycar_nominal.py /standard/environment/public/control_public/client.py /standard/environment/public/control_public/weights.py /app/scripts/control_transfer/control_public/
COPY --from=ghcr.io/mll-lab-nu/efe:roboengineer-files-0.3.1@sha256:ec2520f7855f520bc032f24960306f290263adcf5c7d24e9083526d6584d2e7a /anycarbench/circuits.json /app/anycarbench/circuits.json
COPY --from=ghcr.io/mll-lab-nu/efe:roboengineer-files-0.3.1@sha256:ec2520f7855f520bc032f24960306f290263adcf5c7d24e9083526d6584d2e7a /anycarbench/compact_routes.json /app/anycarbench/compact_routes.json
COPY --from=ghcr.io/mll-lab-nu/efe:roboengineer-files-0.3.1@sha256:ec2520f7855f520bc032f24960306f290263adcf5c7d24e9083526d6584d2e7a /anycarbench/circuits.json /app/scripts/control_transfer/components/anycarbench/circuits.json
COPY --from=ghcr.io/mll-lab-nu/efe:roboengineer-files-0.3.1@sha256:ec2520f7855f520bc032f24960306f290263adcf5c7d24e9083526d6584d2e7a /anycarbench/compact_routes.json /app/scripts/control_transfer/components/anycarbench/compact_routes.json
ENV PYTHONPATH=/app OPENBLAS_NUM_THREADS=1 MUJOCO_GL=osmesa CONTROL_DEPLOY_TIMEOUT_S=1200
RUN mkdir -p /app/output
