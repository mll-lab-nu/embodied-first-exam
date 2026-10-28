"""Public Internet/source reading and content-addressed discovery evidence."""
from __future__ import annotations

import hashlib
from html.parser import HTMLParser
import ipaddress
import json
import mimetypes
from pathlib import Path
import re
import socket
import time
from urllib.parse import unquote, urljoin, urlsplit, urlencode
from urllib.request import build_opener, ProxyHandler, HTTPRedirectHandler, Request

from .broker import digest, encoded


class PublicHTML(HTMLParser):
    """Extract readable documentation and ordinary hyperlinks without executing a page."""

    def __init__(self):
        """Start a small text projection while retaining original bytes separately."""
        super().__init__()
        self.text, self.links, self.skip = [], [], 0

    def handle_starttag(self, tag, attrs):
        """Skip scripts/styles and collect public links."""
        if tag in {"script", "style"}:
            self.skip += 1
        for name, value in attrs:
            if name == "href" and value:
                self.links.append(value)

    def handle_endtag(self, tag):
        """Resume readable text after non-document content."""
        if tag in {"script", "style"} and self.skip:
            self.skip -= 1

    def handle_data(self, data):
        """Collect human-readable text, including XML search result text."""
        if not self.skip and data.strip():
            self.text.append(data.strip())


def pointer(value, path):
    """Resolve an RFC 6901 pointer in an independently read public document."""
    if path == "":
        return value
    if not path.startswith("/"):
        raise ValueError("Expected a JSON pointer starting with /")
    for token in path[1:].split("/"):
        key = token.replace("~1", "/").replace("~0", "~")
        value = value[int(key)] if isinstance(value, list) else value[key]
    return value


def within(uri, root):
    """Compare canonical file roots or HTTP origins and path boundaries."""
    u, r = urlsplit(uri), urlsplit(root)
    if u.scheme == r.scheme == "file":
        return Path(unquote(u.path)).resolve().is_relative_to(Path(unquote(r.path)).resolve())
    path = unquote(u.path)
    if ".." in path.split("/") or "\\" in path:
        return False
    return (u.scheme, u.netloc) == (r.scheme, r.netloc) and (
        path == r.path.rstrip("/") or path.startswith(r.path.rstrip("/") + "/"))


class NoRedirect(HTTPRedirectHandler):
    """Return redirects to the caller so every destination uses the same access check."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        """Prevent automatic credential or permission forwarding to another origin."""
        return None


def http_request(uri, *, method="GET", body=None, headers=None, timeout=30):
    """Perform one bounded HTTP exchange without inherited proxy settings."""
    request = Request(uri, data=body, method=method,
                      headers={"User-Agent": "HumanCLAW-PublicDiscovery/1", **(headers or {})})
    with build_opener(ProxyHandler({}), NoRedirect()).open(request, timeout=timeout) as response:
        data = response.read(32 * 1024 * 1024 + 1)
        if len(data) > 32 * 1024 * 1024:
            raise ValueError("Public resource exceeds 32 MiB per read")
        return data, dict(response.headers)


class Discovery:
    """Read public docs, schemas, clients and resources before a target tool exists."""

    def __init__(self, directory, spec, broker):
        """Initialize task-persistent sources and ordinary Internet access."""
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.spec, self.broker = spec, broker
        self.records, self.current = {}, {}
        self.on_change = None
        self.mcp = {}

    def mcp_access(self, ident):
        """Reuse an ordinary MCP session for a declared generic transport handle."""
        from .transports import MCPAccess
        if ident not in self.mcp:
            handle = next((h for h in self.spec["transports"] if h["id"] == ident and h["kind"] == "mcp"), None)
            if not handle:
                raise ValueError("Unknown MCP transport handle")
            self.mcp[ident] = MCPAccess(handle, self.broker.deadline)
        return self.mcp[ident]

    def allowed(self, uri):
        """Allow declared local sources and public Internet documentation."""
        parsed = urlsplit(uri)
        if parsed.username or parsed.password:
            raise ValueError("Use an access handle, not credentials in a URI")
        if any(within(uri, root) for root in self.spec.get("source_roots", [])):
            return
        if parsed.scheme in {"http", "https"} and self.spec.get("internet", True):
            addresses = socket.getaddrinfo(parsed.hostname, parsed.port or 443, type=socket.SOCK_STREAM)
            if addresses and all(ipaddress.ip_address(item[4][0]).is_global for item in addresses):
                return
        raise ValueError("Source outside public Internet or declared source roots: " + uri)

    def fetch(self, uri):
        """Retrieve exact public bytes, checking references and redirects alike."""
        from urllib.error import HTTPError
        parsed = urlsplit(uri)
        if parsed.scheme == "mcp":
            from urllib.parse import parse_qs
            methods = {"/tools": "tools/list", "/resources": "resources/list", "/templates": "resources/templates/list", "/resource": "resources/read"}
            if parsed.path not in methods:
                raise ValueError("MCP discovery paths are tools, resources, templates or resource?uri=...")
            args = {"uri": parse_qs(parsed.query)["uri"][0]} if parsed.path == "/resource" else {}
            result = self.mcp_access(parsed.netloc).call(methods[parsed.path], args)
            if parsed.path == "/resource" and len(result.get("contents", [])) == 1:
                import base64
                item = result["contents"][0]
                data = base64.b64decode(item["blob"], validate=True) if "blob" in item else item["text"].encode()
                return data, item.get("mimeType", "application/octet-stream"), uri
            return encoded(result).encode(), "application/json", uri
        for _ in range(6):
            self.allowed(uri)
            if urlsplit(uri).scheme == "file":
                path = Path(unquote(urlsplit(uri).path)).resolve()
                if path.stat().st_size > 32 * 1024 * 1024:
                    raise ValueError("Public resource exceeds 32 MiB per read")
                return path.read_bytes(), mimetypes.guess_type(path.name)[0] or "application/octet-stream", uri
            try:
                data, headers = http_request(uri, timeout=max(.01, min(30, self.broker.deadline - time.monotonic())))
                return data, next((v for k, v in headers.items() if k.lower() == "content-type"), "application/octet-stream"), uri
            except HTTPError as exc:
                if exc.code not in {301, 302, 303, 307, 308} or not exc.headers.get("Location"):
                    raise
                uri = urljoin(uri, exc.headers["Location"])
        raise ValueError("Too many public document redirects")

    def read(self, uri, question, *, offset=0, length=24000):
        """Record immutable content identities; unchanged reads are not new progress."""
        if not question.strip():
            raise ValueError("Discovery needs a concrete interface question")
        started = time.monotonic()
        data, mime, resolved = self.fetch(uri)
        content_hash = hashlib.sha256(data).hexdigest()
        ident = "source:" + digest({"uri": uri, "sha256": content_hash})
        old = self.current.get(uri)
        reused = ident in self.records
        if not reused:
            name = Path(unquote(urlsplit(resolved).path)).name or "index.txt"
            record_directory = self.directory / ident.split(":")[1]
            destination = record_directory / "files" / name
            destination.parent.mkdir(parents=True)
            destination.write_bytes(data)
            text = data.decode("utf-8", errors="replace")
            refs = re.findall(r'(?:href=["\']([^"\']+)|\]\(([^) ]+)\)|["\'](?:\$ref|url)["\']\s*:\s*["\']([^"\']+))', text)
            references = sorted({urljoin(resolved, next(x for x in group if x)) for group in refs})
            if "html" in mime or "xml" in mime:
                page = PublicHTML()
                page.feed(text)
                references = sorted(set(references) | {urljoin(resolved, link) for link in page.links} |
                                    set(re.findall(r"https?://[^\s<>]+", " ".join(page.text))))
                text = "\n".join(page.text)
            (record_directory / "readable.txt").write_text(text)
            record = {"schema": "discovery-record-v1", "id": ident, "uri": uri, "resolved_uri": resolved,
                      "sha256": content_hash, "mime_type": mime, "bytes": len(data), "path": str(destination),
                      "text_path": str(record_directory / "readable.txt"),
                      "question": question, "references": references, "previous": old,
                      "elapsed_seconds": time.monotonic() - started, "provenance": "public_source"}
            self.records[ident] = record
            (record_directory / "record.json").write_text(encoded(record))
            self.broker.record("discovery.source", record)
        self.current[uri] = ident
        if old and old != ident and self.on_change:
            self.on_change(old, ident)
        record = self.records[ident]
        text = Path(record["text_path"]).read_text()
        self.broker.record("discovery.read", {"source": ident, "reused": reused, "bytes": len(data),
                                             "elapsed_seconds": time.monotonic() - started})
        return {**record, "reused": reused, "text": text[offset:offset + length],
                "offset": offset, "next_offset": offset + length if offset + length < len(text) else None}

    def search(self, query):
        """Search the public Web and retain the result page as ordinary source evidence."""
        base = self.spec.get("search_url", "https://www.bing.com/search?format=rss")
        return self.read(base + ("&" if "?" in base else "?") + urlencode({"q": query}),
                         "Find public documentation: " + query)

    def value(self, ident, path=""):
        """Read a public JSON value by immutable source identity and pointer."""
        record = self.records[ident]
        if self.current[record["uri"]] != ident:
            raise ValueError("Source changed; rediscover before using its old claims")
        return pointer(json.loads(Path(record["path"]).read_text()), path)

    def snapshot(self):
        """Expose compact source identities and unresolved bootstrap work to Pi."""
        return {"entries": self.spec["entries"], "sources": list(self.current.values()),
                "records": [{k: r[k] for k in ("id", "uri", "sha256", "question")}
                            for r in self.records.values() if self.current[r["uri"]] == r["id"]]}
