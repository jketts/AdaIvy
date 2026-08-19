"""Append-only in-memory repositories for the manual Phase 1 slice."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Generic, Iterable, TypeVar

from .entities import AuditEvent, Entity, OpaqueId, ResearchDossier

T = TypeVar("T", bound=Entity)


@dataclass(slots=True)
class AppendOnlyRepository(Generic[T]):
    _items: dict[OpaqueId, T] = field(default_factory=dict)
    _order: list[OpaqueId] = field(default_factory=list)

    def append(self, entity: T) -> T:
        existing = self._items.get(entity.id)
        if existing is not None:
            if existing == entity:
                return existing
            raise ValueError(f"entity ID already has different immutable content: {entity.id}")
        self._items[entity.id] = entity
        self._order.append(entity.id)
        return entity

    def get(self, entity_id: OpaqueId) -> T:
        try:
            return self._items[entity_id]
        except KeyError as error:
            raise KeyError(f"unknown entity: {entity_id}") from error

    def all(self) -> tuple[T, ...]:
        return tuple(self._items[item_id] for item_id in self._order)

    def __len__(self) -> int:
        return len(self._order)


@dataclass(slots=True)
class EventStore:
    _events: AppendOnlyRepository[AuditEvent] = field(default_factory=AppendOnlyRepository)
    _by_idempotency_key: dict[str, OpaqueId] = field(default_factory=dict)

    def append_once(self, event: AuditEvent) -> AuditEvent:
        existing_id = self._by_idempotency_key.get(event.idempotency_key)
        if existing_id is not None:
            existing = self._events.get(existing_id)
            if (
                existing.aggregate_id != event.aggregate_id
                or existing.event_type != event.event_type
                or existing.payload != event.payload
            ):
                raise ValueError("idempotency key reused for a different semantic event")
            return existing
        self._events.append(event)
        self._by_idempotency_key[event.idempotency_key] = event.id
        return event

    def all(self) -> tuple[AuditEvent, ...]:
        return self._events.all()

    def for_aggregate(self, aggregate_id: OpaqueId) -> tuple[AuditEvent, ...]:
        return tuple(event for event in self.all() if event.aggregate_id == aggregate_id)


def append_all(repository: AppendOnlyRepository[T], entities: Iterable[T]) -> tuple[T, ...]:
    return tuple(repository.append(entity) for entity in entities)


@dataclass(slots=True)
class InMemoryTrustStore:
    """Append-only storage used by the manual vertical slice."""

    entities: AppendOnlyRepository[Entity] = field(default_factory=AppendOnlyRepository)
    dossiers: AppendOnlyRepository[ResearchDossier] = field(default_factory=AppendOnlyRepository)
    events: EventStore = field(default_factory=EventStore)

    def append_dossier(self, dossier: ResearchDossier) -> ResearchDossier:
        nested: tuple[Entity, ...] = (
            dossier.problem,
            dossier.formalization,
            dossier.semantic_alignment,
            *dossier.claims,
            *dossier.warrants,
            *dossier.evidence,
            *dossier.source_applicability,
            *dossier.obligations,
            *dossier.representation_maps,
            *dossier.verification_records,
            dossier.evaluation_protocol,
        )
        append_all(self.entities, nested)
        for event in dossier.audit_events:
            self.events.append_once(event)
        return self.dossiers.append(dossier)
