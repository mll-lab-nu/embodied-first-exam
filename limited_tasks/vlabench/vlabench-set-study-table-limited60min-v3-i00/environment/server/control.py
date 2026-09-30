"""Trusted management over a Unix socket that only exists inside sim."""
import json
import socket
import sys
with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as sock:
    sock.settimeout(90)
    sock.connect('/run/limited/control.sock')
    sock.sendall((sys.argv[1]+'\n').encode())
    reply=json.loads(sock.makefile().readline())
    if 'error' in reply: raise SystemExit('Trusted management command rejected')
    print(json.dumps(reply))
