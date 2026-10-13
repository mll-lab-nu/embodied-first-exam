FROM docker.io/library/python:3.12.14-slim@sha256:f77ac9e44ae96ef2c90b8053ea08c31f8be030f824196b0ae4db6d462c84e51f
LABEL roboengineer.verifier_inputs_sha256="47d50ede104f8977a92da8d0701629701c52f274e85ab15241b3e0712ced8074"
LABEL roboengineer.instance_sha256="40aabfd2384578e89198c3de357bc56c768b60bea0041372b55cee5ea9a8f373"
COPY grade.py test.sh instance.json rcb_limits.py rcb_limits.json /tests/
RUN echo '40aabfd2384578e89198c3de357bc56c768b60bea0041372b55cee5ea9a8f373  /tests/instance.json' | sha256sum -c - && chmod +x /tests/test.sh
RUN echo 'e2459a0520c1072df9daf2d6a6caccb3695b5589464eeacd18dccf1c09f18273  /tests/grade.py' | sha256sum -c - && echo '98c0880bb8118c172f768073271254c7210eb71855bab44b86b28af139490a28  /tests/test.sh' | sha256sum -c - && echo '40aabfd2384578e89198c3de357bc56c768b60bea0041372b55cee5ea9a8f373  /tests/instance.json' | sha256sum -c - && echo '68e07a860bf218cd7c9c2bfe1aaa4801d0ee68e7f8c789aefa3b1ebc4740d809  /tests/rcb_limits.py' | sha256sum -c - && echo '402a9f579ecd2be41b744fb4d274170dbd85ecc1139cb9760544f616a1ac2630  /tests/rcb_limits.json' | sha256sum -c -
# resource limits: the verifier step and its copy of the limits (docs/PROTOCOL.md §2.10) # rcb-monitor
COPY rcb_limits.py rcb_limits.json /tests/
