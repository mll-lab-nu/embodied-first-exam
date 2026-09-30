FROM ghcr.io/jameskrw/rcb-robocasa-gr1:0.1.1
COPY . /private/
ENV PYTHONPATH=/private
WORKDIR /private
RUN mkdir -p /recorded /run/limited
CMD ["python","-u","server.py"]
