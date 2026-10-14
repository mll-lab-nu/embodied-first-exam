FROM docker.io/library/python:3.12.14-slim@sha256:f77ac9e44ae96ef2c90b8053ea08c31f8be030f824196b0ae4db6d462c84e51f
LABEL roboengineer.verifier_inputs_sha256="febf3ad90635bd7066e96723f79a8f8e2d4533c5993a9be5e1daf89da4ed0ba0"
LABEL roboengineer.instance_sha256="9c4f580cb17732ddb0dd6c3303dd16d869eb30086044b5b9eb2bce9465a8559f"
COPY grade.py test.sh instance.json rcb_limits.py rcb_limits.json /tests/
RUN echo '9c4f580cb17732ddb0dd6c3303dd16d869eb30086044b5b9eb2bce9465a8559f  /tests/instance.json' | sha256sum -c - && chmod +x /tests/test.sh
RUN echo 'e2459a0520c1072df9daf2d6a6caccb3695b5589464eeacd18dccf1c09f18273  /tests/grade.py' | sha256sum -c - && echo '98c0880bb8118c172f768073271254c7210eb71855bab44b86b28af139490a28  /tests/test.sh' | sha256sum -c - && echo '9c4f580cb17732ddb0dd6c3303dd16d869eb30086044b5b9eb2bce9465a8559f  /tests/instance.json' | sha256sum -c - && echo '68e07a860bf218cd7c9c2bfe1aaa4801d0ee68e7f8c789aefa3b1ebc4740d809  /tests/rcb_limits.py' | sha256sum -c - && echo '5294e669018d828f37812fa5f1293f06575f7474b16633a236dfc1478a3762d1  /tests/rcb_limits.json' | sha256sum -c -
# resource limits: the verifier step and its copy of the limits (docs/PROTOCOL.md §2.10) # rcb-monitor
COPY rcb_limits.py rcb_limits.json /tests/
