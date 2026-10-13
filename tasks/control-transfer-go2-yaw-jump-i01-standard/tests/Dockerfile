FROM docker.io/library/python:3.12.14-slim@sha256:f77ac9e44ae96ef2c90b8053ea08c31f8be030f824196b0ae4db6d462c84e51f
LABEL roboengineer.verifier_inputs_sha256="ceea30bfd8d8a21a6b61f463f1194c330374b6f57a84f671d70e105753d272cd"
LABEL roboengineer.instance_sha256="e9299425526778f9921c5557746c3edbb74c2245ab76df8c6836c8c94fcff081"
COPY grade.py test.sh instance.json rcb_limits.py rcb_limits.json /tests/
RUN echo 'e9299425526778f9921c5557746c3edbb74c2245ab76df8c6836c8c94fcff081  /tests/instance.json' | sha256sum -c - && chmod +x /tests/test.sh
RUN echo 'e2459a0520c1072df9daf2d6a6caccb3695b5589464eeacd18dccf1c09f18273  /tests/grade.py' | sha256sum -c - && echo '98c0880bb8118c172f768073271254c7210eb71855bab44b86b28af139490a28  /tests/test.sh' | sha256sum -c - && echo 'e9299425526778f9921c5557746c3edbb74c2245ab76df8c6836c8c94fcff081  /tests/instance.json' | sha256sum -c - && echo '68e07a860bf218cd7c9c2bfe1aaa4801d0ee68e7f8c789aefa3b1ebc4740d809  /tests/rcb_limits.py' | sha256sum -c - && echo 'bfceb805e1d072191c1ad55a405fe63194dbeddfe4c4a856bfc19a4527d64a57  /tests/rcb_limits.json' | sha256sum -c -
# resource limits: the verifier step and its copy of the limits (docs/PROTOCOL.md §2.10) # rcb-monitor
COPY rcb_limits.py rcb_limits.json /tests/
