"""The evaluator owns this interface; agent code never receives the adapter."""
from typing import Protocol


class TaskAdapter(Protocol):
    def describe(self) -> dict:
        """Public goal, robot/scene facts, action schema and camera calibration.

        Optional adapter.public_assets maps filenames to basic JSON/Markdown
        metadata. No object reference images, geometry, target transforms,
        implementation source, demos or solutions; infer shapes from observations.
        """

    def validate_action(self, action: dict) -> None:
        """Pure validation, before any part of a segment is executed."""

    def step(self, action: dict) -> None:
        """Advance exactly one control tick; never reset or restore state."""

    def observe(self) -> dict:
        """Public JSON observation (e.g. proprioception); no privileged state."""

    def render(self) -> dict[str, bytes]:
        """All declared cameras as PNG bytes, without advancing the simulator."""

    def evaluate(self) -> dict:
        """Trusted verdict: status is running, succeeded or failed; optional reason."""
