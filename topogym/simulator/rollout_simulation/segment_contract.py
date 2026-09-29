"""Public, numerical segment records. Robot actions retain their existing schema."""
from collections.abc import Mapping
import json
import math

import numpy as np

from topogym.utils.io import to_jsonable
from topogym.utils.snapshots import freeze
from ..interaction import public_info


class SegmentError(RuntimeError):
    """Public failure code; engine details belong in the owner's evidence."""


def action_copy(action):
    """Validate the transport shape without resolving state-dependent IK/deltas."""
    if not isinstance(action, Mapping):
        raise ValueError("An action must be a mapping")
    def check(value):
        if isinstance(value, Mapping):
            if any(not isinstance(key, str) for key in value):
                raise ValueError("Action keys must be strings")
            return {key: check(child) for key, child in value.items()}
        if isinstance(value, (tuple, list, np.ndarray)):
            return [check(child) for child in value]
        if isinstance(value, (bool, np.bool_)) or not isinstance(value, (int, float, np.integer, np.floating)):
            raise ValueError("Action values must be finite numbers")
        if not math.isfinite(value):
            raise ValueError("Action values must be finite numbers")
        return value.item() if isinstance(value, np.generic) else value
    return check(action)


def fingerprint(value):
    from hashlib import sha256
    return sha256(json.dumps(to_jsonable(value), sort_keys=True, separators=(",", ":"),
                             allow_nan=False).encode()).hexdigest()


def request_id(value):
    if not isinstance(value, str) or not value or len(value) > 256:
        raise ValueError("request_id must be a nonempty string of at most 256 characters")
    return value


def validate_policy_output(value):
    if value is not None and not isinstance(value, Mapping):
        raise ValueError("act(obs) must return an action mapping or None")
    return value


def make_execution_state(*, control_steps, previous, observation_state_ref,
                         current_state_ref, error_code=None):
    return freeze(dict(control_steps=control_steps, previous=previous,
        observation_state_ref=observation_state_ref,
        observation_is_current=observation_state_ref == current_state_ref,
        error_code=error_code))
