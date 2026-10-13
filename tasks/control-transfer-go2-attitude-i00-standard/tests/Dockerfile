FROM docker.io/library/python:3.12.14-slim@sha256:f77ac9e44ae96ef2c90b8053ea08c31f8be030f824196b0ae4db6d462c84e51f
LABEL roboengineer.verifier_inputs_sha256="8d45fcb0e40802c1bd53628934c37c74671c890a0d685db6806de96eb86a8a4d"
LABEL roboengineer.instance_sha256="5d5b14230447b301ea94e2b8309a7c8249df8f8cb5730e71869a9d520162fbce"
COPY grade.py test.sh instance.json rcb_limits.py rcb_limits.json /tests/
RUN echo '5d5b14230447b301ea94e2b8309a7c8249df8f8cb5730e71869a9d520162fbce  /tests/instance.json' | sha256sum -c - && chmod +x /tests/test.sh
RUN echo 'e2459a0520c1072df9daf2d6a6caccb3695b5589464eeacd18dccf1c09f18273  /tests/grade.py' | sha256sum -c - && echo '98c0880bb8118c172f768073271254c7210eb71855bab44b86b28af139490a28  /tests/test.sh' | sha256sum -c - && echo '5d5b14230447b301ea94e2b8309a7c8249df8f8cb5730e71869a9d520162fbce  /tests/instance.json' | sha256sum -c - && echo '68e07a860bf218cd7c9c2bfe1aaa4801d0ee68e7f8c789aefa3b1ebc4740d809  /tests/rcb_limits.py' | sha256sum -c - && echo 'aebf87d363548ffa8a3cd3a66e13d17e1e9f5bc4994e0111891d9e39a4eaa4e4  /tests/rcb_limits.json' | sha256sum -c -
# resource limits: the verifier step and its copy of the limits (docs/PROTOCOL.md §2.10) # rcb-monitor
COPY rcb_limits.py rcb_limits.json /tests/
