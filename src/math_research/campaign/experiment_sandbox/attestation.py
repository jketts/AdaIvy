"""The release condition the ADR-0066 sandbox runner refuses to run without."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

ACTIVATION_SCHEMA = "adaivy.campaign-experiment-sandbox-activation.v1"
ACTIVATION_STATUSES = ("activated", "blocked")


@dataclass(frozen=True, slots=True, kw_only=True)
class SandboxActivation:
    """Every falsifiability probe flipped against the real digest-pinned runtime.

    Constructing one of these directly is diagnostic measurement, not
    authorization.  A production caller obtains it from
    :func:`~math_research.campaign.experiment_sandbox.activation.verify_campaign_experiment_activation`
    over a stored, content-hashed activation record.
    """

    schema_version: str
    status: str
    environment_hash: str
    policy_hash: str
    bootstrap_hash: str
    campaign_lock_sha256: str
    phase4b_lock_sha256: str
    target_hash: str
    probes_total: int
    probes_flipped: int
    probes_blocked: int
    content_hash: str
    epistemic_warrant_created: bool = False

    def __post_init__(self) -> None:
        if self.schema_version != ACTIVATION_SCHEMA:
            raise ValueError("campaign sandbox activation schema differs")
        if self.status not in ACTIVATION_STATUSES:
            raise ValueError("campaign sandbox activation status is outside the vocabulary")
        if self.epistemic_warrant_created is not False:
            raise ValueError("a sandbox activation may never create warrant")
        if self.probes_total < 1 or self.probes_flipped < 0 or self.probes_blocked < 0:
            raise ValueError("campaign sandbox probe counts are invalid")
        if self.probes_flipped + self.probes_blocked > self.probes_total:
            raise ValueError("campaign sandbox probe counts do not close")
        if self.status == "activated" and self.probes_flipped != self.probes_total:
            raise ValueError("activation requires probes_flipped == probes_total")
        if self.status == "activated" and self.probes_blocked != 0:
            raise ValueError("activation requires no blocked probe")

    @property
    def activated(self) -> bool:
        return self.status == "activated" and self.probes_flipped == self.probes_total

    def to_record(self) -> dict[str, Any]:
        return {
            name: getattr(self, name) for name in sorted(self.__dataclass_fields__)
        }


__all__ = ["ACTIVATION_SCHEMA", "ACTIVATION_STATUSES", "SandboxActivation"]
