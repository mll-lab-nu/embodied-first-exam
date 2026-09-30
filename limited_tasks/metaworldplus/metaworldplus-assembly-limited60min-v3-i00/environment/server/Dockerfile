FROM ghcr.io/jameskrw/rcb-metaworldplus:0.1.0
COPY . /private/
ENV PYTHONPATH=/private
RUN mkdir -p /recorded /run/limited && chown 65532:65532 /recorded /run/limited
WORKDIR /private
USER 65532:65532
CMD ["python", "server.py"]
