"""Provider protocol operations shared by all harnesses using that protocol."""
from dataclasses import dataclass
from urllib.parse import urlsplit


def validate_url(url):
    if not isinstance(url, str) or any(c.isspace() or ord(c) < 32 for c in url):
        raise ValueError("Invalid provider base URL")
    try:
        parsed = urlsplit(url)
        _ = parsed.port
    except ValueError:
        raise ValueError("Invalid provider base URL") from None
    if (parsed.scheme not in {"https", "http"} or not parsed.hostname or parsed.query
            or parsed.fragment or parsed.username is not None or parsed.password is not None):
        raise ValueError("Invalid provider base URL")
    if parsed.scheme == "http" and parsed.hostname not in {"127.0.0.1", "localhost"}:
        raise ValueError("Remote providers require HTTPS")
    return parsed


@dataclass(frozen=True)
class PreparedRequest:
    path: str
    body: dict
    output_bound: int
    input_bound: int | None = None


class ProviderProtocol:
    route = ""
    output_field = "max_tokens"
    receipt_type = None
    allowed_tools = frozenset({"function"})
    default_tool = None

    def validate_route(self, route):
        validate_url(route["url"])

    def request_path(self, path):
        parsed = urlsplit(path)
        route = parsed.path.removeprefix("/v1")
        if parsed.query or parsed.fragment or route != self.route:
            raise ValueError("Unsupported model endpoint")
        return route

    def prepare_request(self, path, body, remaining, *, default_output_cap=8192):
        route = self.request_path(path)
        if not isinstance(body, dict) or not isinstance(body.get("model"), str) or not body["model"]:
            raise ValueError("A model is required")
        if body.get("background") or body.get("n", 1) != 1:
            raise ValueError("Background generation and n != 1 are unsupported")
        for tool in body.get("tools", []):
            if tool.get("type", self.default_tool) not in self.allowed_tools:
                raise ValueError("Provider-hosted tools need a verified accounting adapter")
        if route.endswith("/compact"):
            if body.get("stream"):
                raise ValueError("Streaming compaction is unsupported")
            return PreparedRequest(route, body, 0)
        field = self.cap_field(body)
        requested = body.get(field, default_output_cap)
        if type(requested) is not int or requested < 1:
            raise ValueError("Maximum output must be a positive integer")
        cap = min(requested, max(0, remaining))
        body[field] = cap
        self.prepare_stream(body)
        return PreparedRequest(route, body, cap)

    def cap_field(self, body):
        return self.output_field

    def prepare_stream(self, body):
        pass

    def build_headers(self, credential, allowed_headers):
        return {"Content-Type": "application/json", "Accept-Encoding": "identity",
                "Authorization": "Bearer " + credential}

    def new_receipt_source(self, request_id):
        return self.receipt_type(request_id)
