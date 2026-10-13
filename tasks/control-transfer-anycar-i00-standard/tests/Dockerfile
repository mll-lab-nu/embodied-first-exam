FROM docker.io/library/python:3.12.14-slim@sha256:f77ac9e44ae96ef2c90b8053ea08c31f8be030f824196b0ae4db6d462c84e51f
LABEL roboengineer.verifier_inputs_sha256="b263d4951b6e3c87c8f5deba423969312d0f366d0daa6ed2d1aa5630b6b388b5"
LABEL roboengineer.instance_sha256="b3600a615c4dbb59919b64f041bcddd81ba7b11c69b42781a0fe1d8ee4b50c81"
COPY grade.py test.sh instance.json rcb_limits.py rcb_limits.json /tests/
RUN echo 'b3600a615c4dbb59919b64f041bcddd81ba7b11c69b42781a0fe1d8ee4b50c81  /tests/instance.json' | sha256sum -c - && chmod +x /tests/test.sh
RUN echo 'e2459a0520c1072df9daf2d6a6caccb3695b5589464eeacd18dccf1c09f18273  /tests/grade.py' | sha256sum -c - && echo '98c0880bb8118c172f768073271254c7210eb71855bab44b86b28af139490a28  /tests/test.sh' | sha256sum -c - && echo 'b3600a615c4dbb59919b64f041bcddd81ba7b11c69b42781a0fe1d8ee4b50c81  /tests/instance.json' | sha256sum -c - && echo '68e07a860bf218cd7c9c2bfe1aaa4801d0ee68e7f8c789aefa3b1ebc4740d809  /tests/rcb_limits.py' | sha256sum -c - && echo '72d453319e10272d81747c65291bc492425cfa633e44f8efa569e42bfbb06e3a  /tests/rcb_limits.json' | sha256sum -c -
# resource limits: the verifier step and its copy of the limits (docs/PROTOCOL.md §2.10) # rcb-monitor
COPY rcb_limits.py rcb_limits.json /tests/
