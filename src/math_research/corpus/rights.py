"""Per-document Phase 4A rights decisions for a corpus tranche.

ADR-0067: "Per-document rights do not become per-archive rights.  One licence
decision over the archive establishes the *ceiling*; each document still needs
its Phase 4A decisions."  CC0 is therefore the recorded BASIS of each decision,
not a substitute for it.

Three uses are recorded per document -- acquisition, storage/retention and
parsing.  All three are non-disclosing, so ADR-0064 requires ``processor:
null``; :func:`assert_non_disclosing` refuses any use that would disclose text
to a named processor, so this module can never write an embedding or
model-context authorization by accident.  Embedding a corpus document is a
separate human decision under ADR-0064 and is not reachable from here.

**Sharding, and why it exists.**  ``phase4a/__init__.py`` pins
``MAX_RECORDS = 256`` per workspace and ``Phase4Workspace.append`` enforces it.
One document needs three decisions and a workspace needs one policy snapshot, so
85 documents exactly fill a workspace.  A tranche is therefore written across
deterministic shards rather than into one workspace, and the tranche bound in
:mod:`constants` is derived from that arithmetic.  ADR-0067 does not mention
this collision; see the slice report.
"""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterable, Iterator, Mapping, Sequence

from ..phase4a.records import (
    DISCLOSING_RIGHTS_USES, ApplicabilityOutcome, RecordType, RightsReason,
    RightsUse, RightsValue,
)
from ..phase4a.service import Phase4Service, RightsBlocked
from ..phase4a.workspace import Phase4Workspace
from .constants import (
    ARXIV_API_TERMS_URL, IDENTIFIER_PATTERN, MAX_RIGHTS_SHARDS, METADATA_LICENCE,
    RIGHTS_SHARD_MAX_DOCUMENTS, TRANCHE_MAX_RECORDS,
)
from .errors import (
    DisclosingRightsUseForbiddenError, DocumentRightsAbsentError,
    RightsShardBoundExceededError,
)

#: Exactly the three non-disclosing Phase 4A uses this slice ever records.
CORPUS_RIGHTS_USES = (
    RightsUse.ACQUISITION, RightsUse.STORAGE_AND_RETENTION, RightsUse.PARSING,
)

RIGHTS_DIRNAME = "rights"
RIGHTS_REASON_DETAIL = (
    "arXiv API Terms of Use reviewed under ADR-0067: descriptive metadata is "
    "CC0 1.0 and may be retrieved, stored and transformed. E-prints are "
    "excluded, so no full text is acquired, retained or parsed."
)


def assert_non_disclosing(use: Any) -> RightsUse:
    """Refuse any rights use that would disclose source text to a processor."""

    try:
        resolved = RightsUse(use)
    except ValueError as error:
        raise DisclosingRightsUseForbiddenError(f"unknown rights use {use!r}") from error
    if resolved in DISCLOSING_RIGHTS_USES:
        raise DisclosingRightsUseForbiddenError(
            f"{resolved.value} discloses source text to a named processor and is "
            "a separate ADR-0064 decision; this slice records only "
            + ", ".join(item.value for item in CORPUS_RIGHTS_USES)
        )
    if resolved not in CORPUS_RIGHTS_USES:
        raise DisclosingRightsUseForbiddenError(
            f"{resolved.value} is not one of the corpus rights uses"
        )
    return resolved


def shard_plan(source_ids: Sequence[str]) -> tuple[tuple[str, tuple[str, ...]], ...]:
    """Deterministic (shard name, source ids) partition of a tranche."""

    ordered = sorted(set(source_ids))
    if len(ordered) != len(list(source_ids)):
        raise DocumentRightsAbsentError("a tranche repeats a document identity")
    if len(ordered) > TRANCHE_MAX_RECORDS:
        raise RightsShardBoundExceededError(
            f"a tranche of {len(ordered)} documents exceeds the pinned "
            f"{TRANCHE_MAX_RECORDS}"
        )
    for source_id in ordered:
        if IDENTIFIER_PATTERN.fullmatch(source_id) is None:
            raise DocumentRightsAbsentError(f"not a Phase 4A source identity: {source_id!r}")
    shards: list[tuple[str, tuple[str, ...]]] = []
    for index in range(0, len(ordered), RIGHTS_SHARD_MAX_DOCUMENTS):
        chunk = tuple(ordered[index: index + RIGHTS_SHARD_MAX_DOCUMENTS])
        shards.append((f"shard-{len(shards):03d}", chunk))
    if len(shards) > MAX_RIGHTS_SHARDS:
        raise RightsShardBoundExceededError(
            f"a tranche needs {len(shards)} rights shards; the pinned maximum is "
            f"{MAX_RIGHTS_SHARDS}"
        )
    return tuple(shards)


class Phase4CorpusRightsWriter:
    """Writes and reads the per-document Phase 4A decisions for one tranche."""

    def __init__(self, root: Path, declaration: Mapping[str, Any]) -> None:
        self.root = Path(root).joinpath(RIGHTS_DIRNAME)
        self.actor_id = str(declaration["actor_id"])
        self.valid_from = str(declaration["valid_from"])
        self.valid_until = declaration["valid_until"]
        self.evidence_refs = tuple(sorted(set(declaration["evidence_refs"])))
        if declaration["licence_basis"] != METADATA_LICENCE:
            raise DocumentRightsAbsentError(
                f"the recorded rights basis must be {METADATA_LICENCE}"
            )
        if declaration["terms_url"] != ARXIV_API_TERMS_URL:
            raise DocumentRightsAbsentError("the recorded terms are not the arXiv API terms")
        self.shard_names: dict[str, str] = {}
        self.decisions: dict[str, tuple[str, ...]] = {}

    def shard_root(self, shard_name: str) -> Path:
        return self.root.joinpath(shard_name)

    @contextmanager
    def _service(self, shard_name: str, *, recorded_at: str) -> Iterator[Phase4Service]:
        root = self.shard_root(shard_name)
        root.mkdir(parents=True, exist_ok=True)
        with Phase4Workspace(root) as workspace:
            service = Phase4Service(workspace)
            if workspace.next_sequence == 0:
                service.initialize_policy(actor_id=self.actor_id, recorded_at=recorded_at)
            yield service

    def write_tranche_rights(
        self, source_ids: Sequence[str], *, recorded_at: str,
    ) -> dict[str, tuple[str, ...]]:
        """Append one decision per (document, non-disclosing use). Idempotent."""

        result: dict[str, tuple[str, ...]] = {}
        for shard_name, chunk in shard_plan(source_ids):
            with self._service(shard_name, recorded_at=recorded_at) as service:
                existing = {
                    (record["subject_id"], record["payload"]["intended_use"]): record["id"]
                    for record in service.workspace.records()
                    if record["record_type"] == RecordType.RIGHTS_DECISION.value
                }
                for source_id in chunk:
                    self.shard_names[source_id] = shard_name
                    ids: list[str] = []
                    for use in CORPUS_RIGHTS_USES:
                        assert_non_disclosing(use)
                        key = (source_id, use.value)
                        if key in existing:
                            ids.append(existing[key])
                            continue
                        record = service.append_rights(
                            source_id=source_id,
                            intended_use=use,
                            value=RightsValue.ALLOWED,
                            reason_code=RightsReason.PERMITTED,
                            reason_detail=RIGHTS_REASON_DETAIL,
                            evidence_refs=self.evidence_refs,
                            actor_id=self.actor_id,
                            valid_from=self.valid_from,
                            valid_until=self.valid_until,
                            recorded_at=recorded_at,
                            lifecycle_id="lifecycle." + source_id,
                            processor=None,
                        )
                        ids.append(record.id)
                    result[source_id] = tuple(sorted(ids))
        self.decisions.update(result)
        return result

    def require_document_rights(self, source_id: str, *, at: str) -> tuple[str, ...]:
        """Every corpus use must be permitted for THIS document, or refuse."""

        shard_name = self.shard_names.get(source_id)
        if shard_name is None:
            shard_name = next(
                (
                    name for name, chunk in shard_plan([source_id])
                    if source_id in chunk
                ),
                None,
            )
        if shard_name is None or not self.shard_root(shard_name).exists():
            raise DocumentRightsAbsentError(
                f"no Phase 4A rights shard holds {source_id}; the archive licence "
                "is a ceiling and never a per-document decision"
            )
        ids: list[str] = []
        with Phase4Workspace(self.shard_root(shard_name)) as workspace:
            service = Phase4Service(workspace)
            for use in CORPUS_RIGHTS_USES:
                assert_non_disclosing(use)
                try:
                    evaluation = service.require_rights(source_id, use, at=at)
                except RightsBlocked as error:
                    raise DocumentRightsAbsentError(
                        f"{source_id} has no permitted {use.value} decision: "
                        f"{error.evaluation.outcome.value}"
                    ) from error
                if evaluation.decision_id is None:
                    raise DocumentRightsAbsentError(
                        f"{source_id} {use.value} decision carries no identity"
                    )
                ids.append(evaluation.decision_id)
        return tuple(sorted(ids))

    def shard_names_written(self) -> tuple[str, ...]:
        if not self.root.exists():
            return ()
        return tuple(sorted(
            path.name for path in self.root.iterdir()
            if path.is_dir() and path.name.startswith("shard-")
        ))

    def rights_record_count(self) -> int:
        total = 0
        for shard_name in self.shard_names_written():
            with Phase4Workspace(self.shard_root(shard_name)) as workspace:
                total += sum(
                    1 for record in workspace.records()
                    if record["record_type"] == RecordType.RIGHTS_DECISION.value
                )
        return total

    def applicability_source_ids(self) -> tuple[str, ...]:
        """Documents carrying a Phase 4A applicability review with an outcome.

        Computed from durable records rather than declared.  ADR-0067 requires
        every report to separate corpus size from this count, because
        applicability is human attention and that is the real ceiling.
        """

        found: set[str] = set()
        for shard_name in self.shard_names_written():
            with Phase4Workspace(self.shard_root(shard_name)) as workspace:
                for record in workspace.records():
                    if record["record_type"] != RecordType.APPLICABILITY_REVIEW.value:
                        continue
                    outcome = record["payload"].get("outcome")
                    if outcome == ApplicabilityOutcome.APPLICABLE.value:
                        found.add(str(record["subject_id"]))
        return tuple(sorted(found))


def evidence_refs_for(activation: Mapping[str, Any], extra: Iterable[str] = ()) -> tuple[str, ...]:
    """Evidence identifiers linking a decision to the activation record."""

    digest = str(activation["content_hash"]).removeprefix("sha256:")[:24]
    refs = {f"evidence.corpus-activation.{digest}", *extra}
    return tuple(sorted(refs))


__all__ = [
    "CORPUS_RIGHTS_USES",
    "RIGHTS_DIRNAME",
    "RIGHTS_REASON_DETAIL",
    "Phase4CorpusRightsWriter",
    "assert_non_disclosing",
    "evidence_refs_for",
    "shard_plan",
]
