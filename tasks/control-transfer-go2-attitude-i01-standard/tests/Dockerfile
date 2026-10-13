FROM docker.io/library/python:3.12.14-slim@sha256:f77ac9e44ae96ef2c90b8053ea08c31f8be030f824196b0ae4db6d462c84e51f
LABEL roboengineer.verifier_inputs_sha256="5854b879e915573497237c724e6aee9160702d9c706e94800dc6ff8676327c62"
LABEL roboengineer.instance_sha256="866c961f574758f7bf6cf3b64e9d0c595a1fba052777ac0be2893e3b1a56c76f"
COPY grade.py test.sh instance.json rcb_limits.py rcb_limits.json /tests/
RUN echo '866c961f574758f7bf6cf3b64e9d0c595a1fba052777ac0be2893e3b1a56c76f  /tests/instance.json' | sha256sum -c - && chmod +x /tests/test.sh
RUN echo 'e2459a0520c1072df9daf2d6a6caccb3695b5589464eeacd18dccf1c09f18273  /tests/grade.py' | sha256sum -c - && echo '98c0880bb8118c172f768073271254c7210eb71855bab44b86b28af139490a28  /tests/test.sh' | sha256sum -c - && echo '866c961f574758f7bf6cf3b64e9d0c595a1fba052777ac0be2893e3b1a56c76f  /tests/instance.json' | sha256sum -c - && echo '68e07a860bf218cd7c9c2bfe1aaa4801d0ee68e7f8c789aefa3b1ebc4740d809  /tests/rcb_limits.py' | sha256sum -c - && echo 'df7a39fad2d626a3dad95ade45ef9bd6a6a461b27fade45f9ed28f71d4e9b29c  /tests/rcb_limits.json' | sha256sum -c -
# resource limits: the verifier step and its copy of the limits (docs/PROTOCOL.md §2.10) # rcb-monitor
COPY rcb_limits.py rcb_limits.json /tests/
