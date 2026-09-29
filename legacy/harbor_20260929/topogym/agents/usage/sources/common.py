import hashlib
import json
from ..types import UsageEvent, token_count


class ReceiptSource:
    name = ""

    def __init__(self, request_id):
        self.request_id = request_id
        self.sequence = 0
        self.done = False
        self.values = {}
        self.seen = {}
        self.receipt_details = {}
        self.provider_event_at = None

    def event(self, *, input_tokens=None, output_tokens=None, final=False, details=None):
        for key, value in (("input_tokens", input_tokens), ("output_tokens", output_tokens)):
            token_count(value, key, optional=True)
            if value is not None:
                self.values[key] = value
        payload = dict(**self.values, final=final, details={**self.receipt_details, **(details or {})},
                       provider_event_at=self.provider_event_at)
        identity = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
        if identity in self.seen:
            return self.seen[identity]
        event = UsageEvent(self.request_id, identity, self.sequence, self.name, **payload)
        self.seen[identity] = event
        self.sequence += 1
        self.done = final
        return event
