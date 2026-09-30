"""Credential-free HTTPS CONNECT allowlist; no URL paths, headers or bodies logged."""
import asyncio
import ipaddress
import json
import socket
from datetime import datetime, timezone

ALLOWED = frozenset({'chatgpt.com', 'auth.openai.com'})


def destination(line):
    parts = line.decode('ascii').strip().split()
    if len(parts) != 3 or parts[0] != 'CONNECT' or parts[2] not in ('HTTP/1.0', 'HTTP/1.1'):
        raise ValueError('CONNECT required')
    host, port = parts[1].rsplit(':', 1)
    if host not in ALLOWED or port != '443':
        raise ValueError('destination rejected')
    return host


def audit(host, status):
    print(json.dumps({'at': datetime.now(timezone.utc).isoformat(), 'host': host, 'port': 443, 'status': status}), flush=True)


async def handle(reader, writer):
    upstream = None
    host = None
    try:
        headers = await asyncio.wait_for(reader.readuntil(b'\r\n\r\n'), 10)
        if len(headers) > 8192:
            raise ValueError('headers too long')
        host = destination(headers.split(b'\r\n', 1)[0])
        addresses = await asyncio.get_running_loop().getaddrinfo(host, 443, type=socket.SOCK_STREAM)
        public = [a for a in addresses if ipaddress.ip_address(a[4][0]).is_global]
        if not public or len(public) != len(addresses):
            raise ValueError('non-public destination')
        # Connect to the validated address, without a second DNS lookup.
        last = None
        for address in public:
            try:
                remote_reader, upstream = await asyncio.wait_for(asyncio.open_connection(address[4][0], 443), 15)
                break
            except OSError as exc:
                last = exc
        if upstream is None:
            raise ConnectionError('upstream unavailable') from last
        writer.write(b'HTTP/1.1 200 Connection Established\r\n\r\n')
        await writer.drain()
        audit(host, 'connected')
        async def relay(source, target):
            while chunk := await source.read(65536):
                target.write(chunk)
                await target.drain()
        tasks = [asyncio.create_task(relay(reader, upstream)), asyncio.create_task(relay(remote_reader, writer))]
        try:
            await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED, timeout=3700)
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
    except Exception:
        audit(host if host in ALLOWED else None, 'rejected_or_unavailable')
        writer.write(b'HTTP/1.1 403 Forbidden\r\nContent-Length: 0\r\nConnection: close\r\n\r\n')
    finally:
        if upstream:
            upstream.close()
        writer.close()


async def main():
    server = await asyncio.start_server(handle, '0.0.0.0', 3128, limit=8192)
    async with server:
        await server.serve_forever()


if __name__ == '__main__':
    asyncio.run(main())
