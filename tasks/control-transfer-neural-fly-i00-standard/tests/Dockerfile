FROM docker.io/library/python:3.12.14-slim@sha256:f77ac9e44ae96ef2c90b8053ea08c31f8be030f824196b0ae4db6d462c84e51f
LABEL roboengineer.verifier_inputs_sha256="12d21da0bf625e88b3d05549d8e13cd3e1da8aceb27233fccd7375a7d9fd0098"
LABEL roboengineer.instance_sha256="f87e623e5379e42742a35527a5b3ded902da84fa8990507500888fac6b5b3dc3"
COPY grade.py test.sh instance.json rcb_limits.py rcb_limits.json /tests/
RUN echo 'f87e623e5379e42742a35527a5b3ded902da84fa8990507500888fac6b5b3dc3  /tests/instance.json' | sha256sum -c - && chmod +x /tests/test.sh
RUN echo 'e2459a0520c1072df9daf2d6a6caccb3695b5589464eeacd18dccf1c09f18273  /tests/grade.py' | sha256sum -c - && echo '98c0880bb8118c172f768073271254c7210eb71855bab44b86b28af139490a28  /tests/test.sh' | sha256sum -c - && echo 'f87e623e5379e42742a35527a5b3ded902da84fa8990507500888fac6b5b3dc3  /tests/instance.json' | sha256sum -c - && echo '68e07a860bf218cd7c9c2bfe1aaa4801d0ee68e7f8c789aefa3b1ebc4740d809  /tests/rcb_limits.py' | sha256sum -c - && echo '7f27fcfa28766b5402b0c43f1f5370724da6ecca05d5fbf7781a9fe51265c33a  /tests/rcb_limits.json' | sha256sum -c -
# resource limits: the verifier step and its copy of the limits (docs/PROTOCOL.md §2.10) # rcb-monitor
COPY rcb_limits.py rcb_limits.json /tests/
