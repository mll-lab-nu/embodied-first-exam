FROM docker.io/library/python:3.12.14-slim@sha256:f77ac9e44ae96ef2c90b8053ea08c31f8be030f824196b0ae4db6d462c84e51f
LABEL roboengineer.verifier_inputs_sha256="8b8dbcbb03287a72223f1708819c5ca024ccfa50dd1d7740522d0da7242cd781"
LABEL roboengineer.instance_sha256="4813dd409ccb75eb82d35bf26a620fd9d300ed8ba89a9896de9195477c292f23"
COPY payload-8b8dbcbb03287a72223f1708819c5ca024ccfa50dd1d7740522d0da7242cd781/ /tests/
RUN echo '4813dd409ccb75eb82d35bf26a620fd9d300ed8ba89a9896de9195477c292f23  /tests/instance.json' | sha256sum -c - && chmod +x /tests/test.sh
RUN echo 'e2459a0520c1072df9daf2d6a6caccb3695b5589464eeacd18dccf1c09f18273  /tests/grade.py' | sha256sum -c - && echo '98c0880bb8118c172f768073271254c7210eb71855bab44b86b28af139490a28  /tests/test.sh' | sha256sum -c - && echo '4813dd409ccb75eb82d35bf26a620fd9d300ed8ba89a9896de9195477c292f23  /tests/instance.json' | sha256sum -c - && echo '68e07a860bf218cd7c9c2bfe1aaa4801d0ee68e7f8c789aefa3b1ebc4740d809  /tests/rcb_limits.py' | sha256sum -c - && echo '3aa69bf999477e26291d1a3fffac53f3eff1db3e558ef9d24ff41e2f1f6cc979  /tests/rcb_limits.json' | sha256sum -c -
# resource limits: the verifier step and its copy of the limits (docs/PROTOCOL.md §2.10) # rcb-monitor
COPY rcb_limits.py rcb_limits.json /tests/
