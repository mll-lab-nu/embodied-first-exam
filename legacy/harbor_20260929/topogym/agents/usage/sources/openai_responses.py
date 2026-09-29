from .common import ReceiptSource
from .base import ProviderProtocol
from urllib.parse import urlsplit


class ResponsesUsage(ReceiptSource):
    name = "openai.responses.v1"

    def feed(self, payload, *, streaming=True):
        kind = payload.get("type", "")
        response = payload.get("response", payload)
        if response.get("created_at") is not None:
            self.provider_event_at = str(response["created_at"])
        usage = response.get("usage")
        final = not streaming or kind in {"response.completed", "response.incomplete", "response.failed"}
        if not usage and not final:
            return None
        usage = usage or {}
        details = {key: usage[key] for key in ("input_tokens_details", "output_tokens_details") if key in usage}
        # Cached inputs and reasoning outputs are INCLUDED in these totals.
        return self.event(input_tokens=usage.get("input_tokens"), output_tokens=usage.get("output_tokens"),
                          final=final, details=details)


class ResponsesProtocol(ProviderProtocol):
    route = "/responses"
    output_field = "max_output_tokens"
    receipt_type = ResponsesUsage

    def request_path(self, path):
        parsed = urlsplit(path)
        route = parsed.path.removeprefix("/v1")
        if parsed.query or parsed.fragment or route not in {self.route, self.route + "/compact"}:
            raise ValueError("Unsupported model endpoint")
        return route
