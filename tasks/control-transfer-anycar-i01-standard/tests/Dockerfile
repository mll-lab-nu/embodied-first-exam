FROM docker.io/library/python:3.12.14-slim@sha256:f77ac9e44ae96ef2c90b8053ea08c31f8be030f824196b0ae4db6d462c84e51f
LABEL roboengineer.verifier_inputs_sha256="88a48ca6963068cc63bb7df67e834c6ddbdfd0fcee3e02b255a4fa523c3e7760"
LABEL roboengineer.instance_sha256="e3f5b217dac1434bdcfb99d69b997a9a3099ba55ac30224178f19e4bab7bc2fb"
COPY grade.py test.sh instance.json rcb_limits.py rcb_limits.json /tests/
RUN echo 'e3f5b217dac1434bdcfb99d69b997a9a3099ba55ac30224178f19e4bab7bc2fb  /tests/instance.json' | sha256sum -c - && chmod +x /tests/test.sh
RUN echo 'e2459a0520c1072df9daf2d6a6caccb3695b5589464eeacd18dccf1c09f18273  /tests/grade.py' | sha256sum -c - && echo '98c0880bb8118c172f768073271254c7210eb71855bab44b86b28af139490a28  /tests/test.sh' | sha256sum -c - && echo 'e3f5b217dac1434bdcfb99d69b997a9a3099ba55ac30224178f19e4bab7bc2fb  /tests/instance.json' | sha256sum -c - && echo '68e07a860bf218cd7c9c2bfe1aaa4801d0ee68e7f8c789aefa3b1ebc4740d809  /tests/rcb_limits.py' | sha256sum -c - && echo '737120bed19271d99b89951fc6fc58f9929e4faf6a90e315966a632f59c8bb78  /tests/rcb_limits.json' | sha256sum -c -
# resource limits: the verifier step and its copy of the limits (docs/PROTOCOL.md §2.10) # rcb-monitor
COPY rcb_limits.py rcb_limits.json /tests/
