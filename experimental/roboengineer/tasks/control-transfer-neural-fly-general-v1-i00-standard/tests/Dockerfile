FROM docker.io/library/python:3.12.14-slim@sha256:f77ac9e44ae96ef2c90b8053ea08c31f8be030f824196b0ae4db6d462c84e51f
LABEL roboengineer.verifier_inputs_sha256="6dadaae8a9963499c877aca94ee1f67df037f146e916e1ce185922f1bdc9d871"
LABEL roboengineer.instance_sha256="1298af441952d93158751444af26045896ced504d865818f298adcd80235dc5e"
COPY payload-6dadaae8a9963499c877aca94ee1f67df037f146e916e1ce185922f1bdc9d871/ /tests/
RUN echo '1298af441952d93158751444af26045896ced504d865818f298adcd80235dc5e  /tests/instance.json' | sha256sum -c - && chmod +x /tests/test.sh
RUN echo 'e2459a0520c1072df9daf2d6a6caccb3695b5589464eeacd18dccf1c09f18273  /tests/grade.py' | sha256sum -c - && echo '98c0880bb8118c172f768073271254c7210eb71855bab44b86b28af139490a28  /tests/test.sh' | sha256sum -c - && echo '1298af441952d93158751444af26045896ced504d865818f298adcd80235dc5e  /tests/instance.json' | sha256sum -c - && echo '68e07a860bf218cd7c9c2bfe1aaa4801d0ee68e7f8c789aefa3b1ebc4740d809  /tests/rcb_limits.py' | sha256sum -c - && echo '4076bba2546ef9415691464dd22f526f4a87b61fe84858b08b500ac152d8e733  /tests/rcb_limits.json' | sha256sum -c -
# resource limits: the verifier step and its copy of the limits (docs/PROTOCOL.md §2.10) # rcb-monitor
COPY rcb_limits.py rcb_limits.json /tests/
