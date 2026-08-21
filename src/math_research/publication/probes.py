"""Falsifiability probes for the render rules.

ADR-0034 established the standard: a rule that cannot be made to fail proves
nothing. A probe is a *single named field* of the manuscript set to a different
value, together with the outcome that mutation must produce -- either a refusal
carrying a named code, or a named demotion of one claim's evidence class.

A probe *flips* only when the mutated manuscript produces the stated outcome and
the unmutated manuscript does not. ``probes_flipped == probes_total`` gates the
offline target, so a render rule with no reachable failure is a suite failure.
"""

from __future__ import annotations

import copy
import re
from dataclasses import dataclass
from typing import Any, Mapping

from .errors import PublicationValidationError
from .evidence import EVIDENCE_CLASSES
from .manuscript import Manuscript, load_manuscript
from .render import render_manuscript

_INDEXED = re.compile(r"^([a-z_]+)\[([^\]]+)\]\.(.+)$")
_PLAIN = re.compile(r"^([a-z_]+)(?:\.([a-z_]+))?$")
#: One list step, ``name[N]``, and only inside a record. Amendment B8.
_LIST_STEP = re.compile(r"^([a-z_]+)\[(\d+)\]$")

_COLLECTION_KEYS = {
    "sources": "source_id",
    "citations": "citation_id",
    "attestations": "attestation_id",
    "certificates": "certificate_id",
    "claims": "claim_id",
    "obligations": "obligation_id",
    # Schema 1.4.0 records. Without these three the convention, verdict and
    # replay rules are unaddressable, and an unaddressable rule has no probe.
    "conventions": "convention_id",
    "verdict_matrices": "matrix_id",
    "counter_candidate_replays": "replay_id",
}


@dataclass(frozen=True, slots=True)
class ProbeResult:
    probe_id: str
    field: str
    flipped: bool
    observed: str
    detail: str


def _resolve(
    value: dict[str, Any], path: str
) -> tuple[dict[str, Any] | list[Any], str | int]:
    indexed = _INDEXED.match(path)
    if indexed:
        collection, identifier, remainder = indexed.groups()
        if collection == "blocks":
            for section in value["sections"]:
                for block in section["blocks"]:
                    if str(block["block_id"]) == identifier:
                        return _descend(block, remainder, path)
            raise PublicationValidationError("probe_field_unresolved", path)
        if collection not in _COLLECTION_KEYS:
            raise PublicationValidationError("probe_field_unresolved", path)
        key = _COLLECTION_KEYS[collection]
        for item in value[collection]:
            if str(item[key]) == identifier:
                return _descend(item, remainder, path)
        raise PublicationValidationError("probe_field_unresolved", path)
    plain = _PLAIN.match(path)
    if not plain:
        raise PublicationValidationError("probe_field_unresolved", path)
    head, tail = plain.groups()
    if head not in value:
        raise PublicationValidationError("probe_field_unresolved", path)
    if tail is None:
        return value, head
    container = value[head]
    if not isinstance(container, dict) or tail not in container:
        raise PublicationValidationError("probe_field_unresolved", path)
    return container, tail


def _descend(
    item: dict[str, Any], remainder: str, path: str
) -> tuple[dict[str, Any] | list[Any], str | int]:
    """Walk a dotted path inside one record, allowing one ``name[N]`` list step.

    Amendment B8. Passages, verdicts and replay readings live in lists inside a
    record, so before this step roughly fourteen 1.4.0 rules had unit tests and no
    reachable falsification. A rule that cannot be made to fail proves nothing
    (ADR-0034), so the probe language had to reach them.
    """

    container: Any = item
    parts = remainder.split(".")
    for index, part in enumerate(parts):
        last = index == len(parts) - 1
        step = _LIST_STEP.match(part)
        if step is not None:
            name, position = step.group(1), int(step.group(2))
            if not isinstance(container, dict) or name not in container:
                raise PublicationValidationError("probe_field_unresolved", path)
            sequence = container[name]
            if not isinstance(sequence, list) or not 0 <= position < len(sequence):
                raise PublicationValidationError("probe_field_unresolved", path)
            if last:
                return sequence, position
            container = sequence[position]
            continue
        if not isinstance(container, dict) or part not in container:
            raise PublicationValidationError("probe_field_unresolved", path)
        if last:
            return container, part
        container = container[part]
    raise PublicationValidationError("probe_field_unresolved", path)


def apply_probe(value: Mapping[str, Any], probe: Mapping[str, Any]) -> dict[str, Any]:
    mutated = copy.deepcopy(dict(value))
    container, key = _resolve(mutated, str(probe["field"]))
    if container[key] == probe["value"]:
        raise PublicationValidationError(
            "probe_value_unchanged",
            f"probe {probe['probe_id']} sets {probe['field']} to the value it already has",
        )
    container[key] = probe["value"]
    return mutated


def _observe(value: Mapping[str, Any]) -> tuple[str, str, dict[str, str]]:
    try:
        manuscript = load_manuscript(value)
        document = render_manuscript(manuscript)
    except PublicationValidationError as error:
        return "refusal", error.code, {}
    classes = {
        classification.claim_id: classification.evidence_class
        for classification in document.classifications
    }
    return "rendered", "", classes


def run_probes(manuscript: Manuscript) -> dict[str, Any]:
    baseline_outcome, baseline_code, baseline_classes = _observe(manuscript.value)
    if baseline_outcome != "rendered":
        raise PublicationValidationError(
            "baseline_manuscript_refused",
            f"the unmutated manuscript is refused with {baseline_code}, so no probe can flip",
        )
    results: list[ProbeResult] = []
    for probe in manuscript.value["render_probes"]:
        expected = probe["expected"]
        if not isinstance(expected, dict):
            raise PublicationValidationError(
                "probe_expectation_malformed", f"probe {probe['probe_id']}.expected"
            )
        mutated = apply_probe(manuscript.value, probe)
        outcome, code, classes = _observe(mutated)
        if probe["expected_outcome"] == "refusal":
            flipped = outcome == "refusal" and code == expected.get("code")
            observed = f"{outcome}:{code}" if outcome == "refusal" else outcome
            detail = (
                f"expected refusal {expected.get('code')!r}, observed {observed!r}"
            )
        else:
            claim_id = str(expected.get("claim_id"))
            target = expected.get("evidence_class")
            if target not in EVIDENCE_CLASSES:
                raise PublicationValidationError(
                    "probe_expectation_malformed",
                    f"probe {probe['probe_id']} names evidence class {target!r}",
                )
            observed_class = classes.get(claim_id, "")
            was = baseline_classes.get(claim_id, "")
            weaker = (
                bool(was)
                and bool(observed_class)
                and EVIDENCE_CLASSES.index(observed_class) > EVIDENCE_CLASSES.index(was)
            )
            flipped = outcome == "rendered" and observed_class == target and weaker
            observed = observed_class or (f"{outcome}:{code}" if code else outcome)
            detail = f"{claim_id} was {was!r}, observed {observed!r}, expected {target!r}"
        results.append(
            ProbeResult(
                probe_id=str(probe["probe_id"]), field=str(probe["field"]), flipped=flipped,
                observed=observed, detail=detail,
            )
        )
    return {
        "probes_total": len(results),
        "probes_flipped": sum(1 for result in results if result.flipped),
        "baseline_evidence_classes": dict(sorted(baseline_classes.items())),
        "probes": [
            {
                "probe_id": result.probe_id, "field": result.field, "flipped": result.flipped,
                "observed": result.observed, "detail": result.detail,
            }
            for result in results
        ],
    }
