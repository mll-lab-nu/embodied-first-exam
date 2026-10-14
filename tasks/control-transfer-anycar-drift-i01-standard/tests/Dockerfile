FROM docker.io/library/python:3.12.14-slim@sha256:f77ac9e44ae96ef2c90b8053ea08c31f8be030f824196b0ae4db6d462c84e51f
LABEL roboengineer.verifier_inputs_sha256="65d807cd16ecde561ead903f5839488b6089314f3d1ae8e701b03781c9a60d1f"
LABEL roboengineer.instance_sha256="05040d3473e89d78933f2ef1cf98934bc39409afa5436038c6ad7c61983a8be0"
COPY payload-65d807cd16ecde561ead903f5839488b6089314f3d1ae8e701b03781c9a60d1f/ /tests/
RUN echo '05040d3473e89d78933f2ef1cf98934bc39409afa5436038c6ad7c61983a8be0  /tests/instance.json' | sha256sum -c - && chmod +x /tests/test.sh
RUN echo 'e2459a0520c1072df9daf2d6a6caccb3695b5589464eeacd18dccf1c09f18273  /tests/grade.py' | sha256sum -c - && echo '98c0880bb8118c172f768073271254c7210eb71855bab44b86b28af139490a28  /tests/test.sh' | sha256sum -c - && echo '05040d3473e89d78933f2ef1cf98934bc39409afa5436038c6ad7c61983a8be0  /tests/instance.json' | sha256sum -c - && echo '68e07a860bf218cd7c9c2bfe1aaa4801d0ee68e7f8c789aefa3b1ebc4740d809  /tests/rcb_limits.py' | sha256sum -c - && echo '350e8feb66210f885666e386484677daa92793183b44598ce691f1fb7cc9f065  /tests/rcb_limits.json' | sha256sum -c -
# resource limits: the verifier step and its copy of the limits (docs/PROTOCOL.md §2.10) # rcb-monitor
COPY rcb_limits.py rcb_limits.json /tests/
