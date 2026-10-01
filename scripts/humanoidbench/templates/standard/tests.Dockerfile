# Separate verifier sandbox: grades the sim service's own artifacts; needs nothing but Python.
FROM {{client_image}}
COPY test.sh grade.py /tests/
RUN chmod +x /tests/test.sh
