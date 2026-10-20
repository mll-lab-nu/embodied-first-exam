"""Public data-only G1 policy submission. Contains no deployment cases or hidden dynamics."""

import base64

from .weights import Network


def validate(policy):
    if (
        not isinstance(policy, dict)
        or set(policy) != {"npz_base64"}
        or not isinstance(policy["npz_base64"], str)
        or len(policy["npz_base64"]) > 12 * 1024**2
    ):
        raise ValueError("Policy payload")
    raw = base64.b64decode(policy["npz_base64"], validate=True)
    Network(raw, "g1")
    return raw
