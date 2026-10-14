FROM docker.io/library/python:3.12.14-slim@sha256:f77ac9e44ae96ef2c90b8053ea08c31f8be030f824196b0ae4db6d462c84e51f
LABEL roboengineer.verifier_inputs_sha256="0b37fb793fef315774705496431690d3588783695e3ec80ae8e3d9c63b569264"
LABEL roboengineer.instance_sha256="9f128b0771abe4fa133157b2233b1ec8945afe5af70fda9931583d8b7f94ccf0"
COPY grade.py test.sh instance.json rcb_limits.py rcb_limits.json /tests/
RUN echo '9f128b0771abe4fa133157b2233b1ec8945afe5af70fda9931583d8b7f94ccf0  /tests/instance.json' | sha256sum -c - && chmod +x /tests/test.sh
RUN echo 'e2459a0520c1072df9daf2d6a6caccb3695b5589464eeacd18dccf1c09f18273  /tests/grade.py' | sha256sum -c - && echo '98c0880bb8118c172f768073271254c7210eb71855bab44b86b28af139490a28  /tests/test.sh' | sha256sum -c - && echo '9f128b0771abe4fa133157b2233b1ec8945afe5af70fda9931583d8b7f94ccf0  /tests/instance.json' | sha256sum -c - && echo '68e07a860bf218cd7c9c2bfe1aaa4801d0ee68e7f8c789aefa3b1ebc4740d809  /tests/rcb_limits.py' | sha256sum -c - && echo 'eca4b1bddfc05051b383e46b02f265cd53507198beb5dc80267c9d8ea111f00d  /tests/rcb_limits.json' | sha256sum -c -
# resource limits: the verifier step and its copy of the limits (docs/PROTOCOL.md §2.10) # rcb-monitor
COPY rcb_limits.py rcb_limits.json /tests/
