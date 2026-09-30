FROM ghcr.io/jameskrw/rcb-robocasa:0.1.0
COPY . /private/
ENV PYTHONPATH=/private
WORKDIR /private
RUN mkdir -p /recorded /run/limited
CMD ["python","-u","server.py"]
