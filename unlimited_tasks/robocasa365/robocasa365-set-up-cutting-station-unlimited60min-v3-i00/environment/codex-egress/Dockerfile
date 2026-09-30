FROM python:3.10.18-slim-bookworm@sha256:445b9efb2c047a7ccdb30d293fd6b1aa0f62a55062dc2b69051df91e10848749
COPY egress.py /egress.py
USER 65532:65532
CMD ["python","-u","/egress.py"]
