FROM docker.io/library/python:3.12.14-slim@sha256:f77ac9e44ae96ef2c90b8053ea08c31f8be030f824196b0ae4db6d462c84e51f
LABEL roboengineer.verifier_inputs_sha256="ddbd6024dd81c51020ada25e0a620de28d51bb7de8f53289475e3677a0493252"
LABEL roboengineer.instance_sha256="6b6a2f26816e6f11bf586036ef9d429a5f1d8d59b997a589abd8576a34726325"
COPY payload-ddbd6024dd81c51020ada25e0a620de28d51bb7de8f53289475e3677a0493252/ /tests/
RUN echo '6b6a2f26816e6f11bf586036ef9d429a5f1d8d59b997a589abd8576a34726325  /tests/instance.json' | sha256sum -c - && chmod +x /tests/test.sh
RUN echo 'e2459a0520c1072df9daf2d6a6caccb3695b5589464eeacd18dccf1c09f18273  /tests/grade.py' | sha256sum -c - && echo '98c0880bb8118c172f768073271254c7210eb71855bab44b86b28af139490a28  /tests/test.sh' | sha256sum -c - && echo '6b6a2f26816e6f11bf586036ef9d429a5f1d8d59b997a589abd8576a34726325  /tests/instance.json' | sha256sum -c - && echo '68e07a860bf218cd7c9c2bfe1aaa4801d0ee68e7f8c789aefa3b1ebc4740d809  /tests/rcb_limits.py' | sha256sum -c - && echo '72d453319e10272d81747c65291bc492425cfa633e44f8efa569e42bfbb06e3a  /tests/rcb_limits.json' | sha256sum -c -
# resource limits: the verifier step and its copy of the limits (docs/PROTOCOL.md §2.10) # rcb-monitor
COPY rcb_limits.py rcb_limits.json /tests/
