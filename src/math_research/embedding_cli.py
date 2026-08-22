"""CLI for ADR-0069 vector partitions.

Two disjoint surfaces, on purpose. `author`, `replay` and `probes` are OFFLINE:
they touch no provider, hold no credential and open no socket. `ingest` is the
live surface and refuses to act without `--execute` and the exact
acknowledgement string, because a provider seeing the text is irreversible.

Ingestion and retrieval never share a process, so `replay` constructs no gateway
at all -- there is nothing here for a credential to reach.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .embedding.authoring import author_partition, load_authoring_spec
from .embedding.constants import (
    DEFAULT_NORMALIZATION,
    LIVE_EMBEDDING_ACKNOWLEDGEMENT,
    PARTITION_PROVIDERS,
)
from .embedding.errors import EmbeddingError
from .embedding.gateways import (
    ForbiddingEmbeddingGateway,
    azure_openai_embedding_config,
    openai_embedding_config,
)
from .embedding.ingestion import (
    DocumentRequest,
    ingest_partition,
    ingestion_record_payload,
    plan_ingestion,
    write_ingestion_record,
)
from .embedding.partition import PartitionKey
from .embedding.probes import run_probes
from .embedding.replay import replay_partition
from .embedding.rights import DirectorySourceTextReader, Phase4ProcessorRightsGate
from .embedding.run_config import load_embedding_run_configuration
from .phase2.pricing import load_pricing_snapshot


def _emit(payload: object, output: Path | None) -> None:
    rendered = json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")


def _key(args: argparse.Namespace) -> PartitionKey:
    return PartitionKey(
        provider=args.provider,
        model_identifier=args.model_identifier,
        dimension=args.dimension,
        normalization=args.normalization,
    )


def _add_key_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--provider", required=True, choices=sorted(PARTITION_PROVIDERS))
    parser.add_argument("--model-identifier", required=True)
    parser.add_argument("--dimension", required=True, type=int)
    parser.add_argument("--normalization", default=DEFAULT_NORMALIZATION)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="embedding", description="ADR-0069 exact vector partition commands",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    author = subparsers.add_parser(
        "author", help="write a fixture_synthetic partition from an authoring spec",
    )
    author.add_argument("spec", type=Path)
    author.add_argument("--root", type=Path, required=True)
    author.add_argument("--output", type=Path)

    replay = subparsers.add_parser(
        "replay", help="verify a partition from bytes; makes no provider call",
    )
    _add_key_arguments(replay)
    replay.add_argument("--root", type=Path, required=True)
    replay.add_argument("--expect-manifest-hash")
    replay.add_argument("--output", type=Path)

    probes = subparsers.add_parser(
        "probes", help="run the thirteen ADR-0069 falsifiability probes",
    )
    probes.add_argument("--output", type=Path)

    ingest = subparsers.add_parser(
        "ingest", help="LIVE: embed sources through a provider (requires credentials)",
    )
    ingest.add_argument("config", type=Path, help="embedding run configuration")
    ingest.add_argument("pricing", type=Path, help="pinned pricing snapshot")
    ingest.add_argument("documents", type=Path, help="JSON array of {document_id, source_id}")
    ingest.add_argument("--corpus-root", type=Path, required=True)
    ingest.add_argument("--phase4a-workspace", type=Path, required=True)
    ingest.add_argument("--root", type=Path, required=True)
    ingest.add_argument("--run-id", required=True)
    ingest.add_argument("--recorded-at", required=True)
    ingest.add_argument("--execute", action="store_true")
    ingest.add_argument("--confirm-live-embedding", default="")
    ingest.add_argument("--output", type=Path)

    args = parser.parse_args(argv)

    if args.command == "author":
        spec = load_authoring_spec(args.spec)
        partition = author_partition(args.root, spec)
        _, report = replay_partition(
            args.root, spec.key, gateway=ForbiddingEmbeddingGateway(),
            expected_manifest_hash=partition.manifest_hash,
        )
        report["fixture_license"] = spec.fixture_license
        report["hash_rule"] = partition.hash_rule
        report["corpus_document_ids"] = list(partition.corpus_document_ids())
        report["query_ids"] = list(partition.query_ids())
        _emit(report, args.output)
        return 0

    if args.command == "replay":
        _, report = replay_partition(
            args.root, _key(args), gateway=ForbiddingEmbeddingGateway(),
            expected_manifest_hash=args.expect_manifest_hash,
        )
        _emit(report, args.output)
        return 0

    if args.command == "probes":
        result = run_probes()
        _emit(result, args.output)
        return 0 if result["probes_flipped"] == result["probes_total"] else 1

    configuration = load_embedding_run_configuration(args.config)
    pricing = load_pricing_snapshot(args.pricing)
    entries = json.loads(args.documents.read_text(encoding="utf-8"))
    if not isinstance(entries, list):
        raise EmbeddingError("documents file must be a JSON array",
                             code="ingestion_documents_invalid")
    documents = tuple(
        DocumentRequest(
            document_id=str(item["document_id"]), source_id=str(item["source_id"]),
        )
        for item in entries
    )
    if not args.execute:
        _emit(
            plan_ingestion(
                configuration=configuration, pricing=pricing, documents=documents,
            ),
            args.output,
        )
        return 0
    if args.confirm_live_embedding != LIVE_EMBEDDING_ACKNOWLEDGEMENT:
        parser.error(
            "--execute requires --confirm-live-embedding "
            + LIVE_EMBEDDING_ACKNOWLEDGEMENT
        )
    if configuration.provider == "azure_openai":
        gateway_config = azure_openai_embedding_config(
            model_identifier=configuration.model_identifier,
            dimension=configuration.dimension,
        )
    else:
        gateway_config = openai_embedding_config(
            model_identifier=configuration.model_identifier,
            dimension=configuration.dimension,
        )
    from .embedding.gateways import OpenAIEmbeddingGateway
    from .phase4a.service import Phase4Service
    from .phase4a.workspace import Phase4Workspace

    with Phase4Workspace(args.phase4a_workspace) as workspace:
        record = ingest_partition(
            root=args.root,
            configuration=configuration,
            pricing=pricing,
            gateway=OpenAIEmbeddingGateway(gateway_config),
            rights=Phase4ProcessorRightsGate(Phase4Service(workspace)),
            corpus=DirectorySourceTextReader(args.corpus_root),
            documents=documents,
            run_id=args.run_id,
            recorded_at=args.recorded_at,
            execute=True,
            acknowledgement=args.confirm_live_embedding,
        )
    payload = ingestion_record_payload(record)
    if args.output is not None:
        write_ingestion_record(record, args.output)
    _emit(payload, None)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
