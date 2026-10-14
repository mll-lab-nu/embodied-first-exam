FROM docker.io/library/python:3.12.14-slim@sha256:f77ac9e44ae96ef2c90b8053ea08c31f8be030f824196b0ae4db6d462c84e51f
LABEL roboengineer.verifier_inputs_sha256="4f820e868e6c1bea1f8a5ad250f14fadc70c44f2af0c0549495845618da5fa99"
LABEL roboengineer.instance_sha256="a0893ae14a94331e85e07992d14e870ebd24c2d62cb30090a02e55c3407f57c6"
COPY grade.py test.sh instance.json rcb_limits.py rcb_limits.json /tests/
RUN echo 'a0893ae14a94331e85e07992d14e870ebd24c2d62cb30090a02e55c3407f57c6  /tests/instance.json' | sha256sum -c - && chmod +x /tests/test.sh
RUN echo 'e2459a0520c1072df9daf2d6a6caccb3695b5589464eeacd18dccf1c09f18273  /tests/grade.py' | sha256sum -c - && echo '98c0880bb8118c172f768073271254c7210eb71855bab44b86b28af139490a28  /tests/test.sh' | sha256sum -c - && echo 'a0893ae14a94331e85e07992d14e870ebd24c2d62cb30090a02e55c3407f57c6  /tests/instance.json' | sha256sum -c - && echo '68e07a860bf218cd7c9c2bfe1aaa4801d0ee68e7f8c789aefa3b1ebc4740d809  /tests/rcb_limits.py' | sha256sum -c - && echo '737120bed19271d99b89951fc6fc58f9929e4faf6a90e315966a632f59c8bb78  /tests/rcb_limits.json' | sha256sum -c -
# resource limits: the verifier step and its copy of the limits (docs/PROTOCOL.md §2.10) # rcb-monitor
COPY rcb_limits.py rcb_limits.json /tests/
