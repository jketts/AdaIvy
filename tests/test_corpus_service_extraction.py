"""ADR-0080 extraction toolchain: identity, LaTeX, pinned tool, fixture PDF.

Spans stay exact character offsets, now over the EXTRACTED text, with the
extractor identity recorded in each document's provenance chain.  Unknown
media types quarantine; a pinned external tool is the exact pinned binary or
a coded refusal.
"""

from __future__ import annotations

import json
import os
import stat
import tempfile
import unittest
from pathlib import Path

from math_research.corpus_service import (
    ARCHIVE_MANIFEST_SCHEMA_VERSION,
    TRANCHE_CONFIG_SCHEMA_VERSION,
)
from math_research.corpus_service.constants import PROVIDER
from math_research.corpus_service.dataroot import initialize_data_root, read_object
from math_research.corpus_service.errors import (
    ExtractorNotPinnedError,
    ExtractorRegistryInvalidError,
)
from math_research.corpus_service.extraction import (
    ExtractorRegistry,
    FixtureExtractor,
    IdentityTextExtractor,
    LatexSourceExtractor,
    PinnedBinaryExtractor,
    default_registry,
    sha256_file,
)
from math_research.corpus_service.generation import load_generation
from math_research.corpus_service.policy import validate_policy
from math_research.corpus_service.serialization import sealed, sha256_bytes
from math_research.corpus_service.service import ingest_tranche
from math_research.corpus_service.snapshot import validate_tranche_config
from math_research.corpus_service.spans import verify_spans, verify_spans_against_source

T0 = "2026-08-22T00:00:00Z"
T1 = "2026-08-22T01:00:00Z"

HUMAN = {
    "actor_id": "human.repository-owner",
    "actor_kind": "human",
    "authority": "human_final",
}
OPEN_LICENCE = "LicenseRef-AdaIvy-Synthetic-OpenAccess"
OPEN_LICENCE_URL = "https://example.invalid/licenses/adaivy-synthetic-open-access"

LATEX_SOURCE = b"""% preamble comment
\\documentclass{article}
\\begin{document}
\\section{Exact results}
The bound is 50\\% sharp.  % trailing comment
See \\emph{the appendix} for the proof.

Second paragraph stands alone.
\\end{document}
"""

PDF_BODY = b"%PDF-1.7 synthetic-not-really-a-pdf \x00\x01\x02 binary payload"
PDF_EXTRACTED = "Extracted PDF text about exact graphs.\n\nA second extracted paragraph.\n"

PDF_FIXTURE_IDENTITY = {
    "tool": "pdftotext-fixture",
    "version": "24.02.0",
    "binary_sha256": "sha256:" + "ab" * 32,
}


def _archive(documents: list[tuple[str, bytes, str]]) -> tuple[dict, dict[str, bytes]]:
    entries = []
    bodies: dict[str, bytes] = {}
    for document_id, body, media_type in documents:
        relative_path = f"documents/{document_id}"
        bodies[relative_path] = body
        entries.append({
            "document_id": document_id.split(".")[0],
            "relative_path": relative_path,
            "media_type": media_type,
            "byte_count": len(body),
            "sha256": sha256_bytes(body),
            "licence": {"licence": OPEN_LICENCE, "licence_url": OPEN_LICENCE_URL},
        })
    entries.sort(key=lambda item: item["document_id"])
    manifest = sealed({
        "schema_version": ARCHIVE_MANIFEST_SCHEMA_VERSION,
        "provider": PROVIDER,
        "archive_id": "archive.adaivy-extraction-fixture",
        "archive_version": "v1",
        "documents": entries,
        "document_count": len(entries),
        "total_bytes": sum(item["byte_count"] for item in entries),
        "content_hash": None,
    })
    return manifest, bodies


class MappingArchive:
    def __init__(self, manifest: dict, bodies: dict[str, bytes]) -> None:
        self.manifest = manifest
        self.bodies = bodies

    def manifest_bytes(self) -> bytes:
        from math_research.corpus_service.serialization import canonical_bytes
        return canonical_bytes(self.manifest) + b"\n"

    def document_bytes(self, relative_path: str) -> bytes:
        return self.bodies[relative_path]


def _policy() -> dict:
    return validate_policy(sealed({
        "schema_version": "adaivy.corpus-service-source-rights-policy.v1",
        "policy_id": "policy.adaivy-extraction-fixture-v1",
        "archive": {
            "archive_id": "archive.adaivy-extraction-fixture",
            "archive_version": "v1",
        },
        "authored_by": dict(HUMAN),
        "terms_reviewed_at": "2026-08-22",
        "licence_diligence_adr": "adr-0067",
        "default_action": "quarantine",
        "rules": [{
            "rule_id": "rule.synthetic-open-access",
            "licence": OPEN_LICENCE,
            "licence_url": OPEN_LICENCE_URL,
            "acquisition": "allowed",
            "storage_and_retention": "allowed",
            "parsing": "allowed",
            "full_text": True,
            "embedding": {
                "value": "allowed",
                "processor": {
                    "processor_id": "processor.openai.synthetic-fixture-embedding",
                    "provider": "openai",
                    "model_identifier": "synthetic-fixture-embedding-v1",
                    "disclosure_kind": "text_stays_local",
                },
            },
            "model_context": {"value": "prohibited", "processor": None},
        }],
        "content_hash": None,
    }))


def _tranche(manifest: dict, policy: dict) -> dict:
    return validate_tranche_config(sealed({
        "schema_version": TRANCHE_CONFIG_SCHEMA_VERSION,
        "tranche_id": "tranche.adaivy-extraction-fixture-v1",
        "archive_manifest_hash": manifest["content_hash"],
        "policy_content_hash": policy["content_hash"],
        "max_documents": 16,
        "max_total_bytes": 65_536,
        "max_document_bytes": 16_384,
        "selected_by": dict(HUMAN),
        "content_hash": None,
    }))


def _pdf_registry() -> ExtractorRegistry:
    return ExtractorRegistry((
        IdentityTextExtractor(),
        LatexSourceExtractor(),
        FixtureExtractor(
            tool=PDF_FIXTURE_IDENTITY["tool"],
            version=PDF_FIXTURE_IDENTITY["version"],
            binary_sha256=PDF_FIXTURE_IDENTITY["binary_sha256"],
            accepted_media_types=frozenset({"application/pdf"}),
            texts_by_source_sha256={sha256_bytes(PDF_BODY): PDF_EXTRACTED},
        ),
    ))


class ExtractionIngestTests(unittest.TestCase):
    def _ingest(self, root: Path, documents, registry=None) -> dict:
        manifest, bodies = _archive(documents)
        policy = _policy()
        initialize_data_root(root, data_root_id="dataroot.extract", initialized_at=T0)
        return ingest_tranche(
            root, policy=policy, archive=MappingArchive(manifest, bodies),
            tranche_config=_tranche(manifest, policy),
            run_id="run.extract", recorded_at=T1, extractors=registry,
        )

    def test_identity_extraction_records_identity_and_keeps_source_hash(self) -> None:
        body = b"Plain text paragraph.\n\nAnother paragraph.\n"
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            report = self._ingest(root, [("doc-plain.txt", body, "text/plain")])
            self.assertEqual(1, report["documents_admitted"])
            entry = load_generation(root, report["generation_id"])["entries"][0]
            self.assertTrue(entry["full_text_stored"])
            self.assertEqual(entry["source_sha256"], entry["extracted_sha256"])
            self.assertEqual("adaivy.identity-text-extractor", entry["extraction"]["tool"])
            self.assertEqual("v1", entry["extraction"]["version"])
            self.assertIsNone(entry["extraction"]["binary_sha256"])

    def test_latex_source_extracts_deterministically_with_exact_spans(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            report = self._ingest(root, [("doc-tex.tex", LATEX_SOURCE, "text/x-tex")])
            self.assertEqual(1, report["documents_admitted"])
            entry = load_generation(root, report["generation_id"])["entries"][0]
            self.assertTrue(entry["full_text_stored"])
            self.assertNotEqual(entry["source_sha256"], entry["extracted_sha256"])
            self.assertEqual("adaivy.latex-source-extractor", entry["extraction"]["tool"])
            extracted = read_object(root, entry["extracted_sha256"])
            text = extracted.decode("utf-8")
            self.assertIn("The bound is 50% sharp.", text)
            self.assertIn("Second paragraph stands alone.", text)
            self.assertNotIn("%", text.replace("50%", ""))
            self.assertNotIn("\\emph", text)
            self.assertNotIn("documentclass", text)
            # Spans verify against the EXTRACTED bytes, not the source.
            spans_doc = verify_spans(json.loads(
                read_object(root, entry["spans_sha256"]).decode("utf-8")
            ))
            self.assertEqual(entry["extracted_sha256"], spans_doc["source_sha256"])
            verify_spans_against_source(spans_doc, extracted)
            # Determinism: a second extraction is byte-identical.
            again = LatexSourceExtractor().extract(LATEX_SOURCE, media_type="text/x-tex")
            self.assertEqual(text, again)

    def test_pdf_fixture_extraction_records_pinned_identity(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            report = self._ingest(
                root, [("doc-pdf.pdf", PDF_BODY, "application/pdf")],
                registry=_pdf_registry(),
            )
            self.assertEqual(1, report["documents_admitted"])
            entry = load_generation(root, report["generation_id"])["entries"][0]
            self.assertEqual(PDF_FIXTURE_IDENTITY, entry["extraction"])
            self.assertEqual(
                PDF_EXTRACTED,
                read_object(root, entry["extracted_sha256"]).decode("utf-8"),
            )

    def test_unknown_media_type_quarantines_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            report = self._ingest(
                root, [("doc-pdf.pdf", PDF_BODY, "application/pdf")],
            )  # default registry: no PDF path
            self.assertEqual(0, report["documents_admitted"])
            self.assertEqual(1, report["documents_quarantined"])
            self.assertEqual(
                "unsupported_media_type",
                report["quarantine_reasons"]["doc-pdf"],
            )


class PinnedBinaryExtractorTests(unittest.TestCase):
    def test_absent_binary_refuses(self) -> None:
        extractor = PinnedBinaryExtractor(
            binary_path=Path("/nonexistent/pdftotext"),
            expected_sha256="sha256:" + "0" * 64,
            expected_version="24.02.0",
        )
        with self.assertRaises(ExtractorNotPinnedError):
            extractor.identity()

    def test_hash_mismatch_refuses(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            binary = Path(temporary) / "faketool"
            binary.write_bytes(b"#!/bin/sh\nexit 0\n")
            extractor = PinnedBinaryExtractor(
                binary_path=binary,
                expected_sha256="sha256:" + "0" * 64,
                expected_version="24.02.0",
            )
            with self.assertRaises(ExtractorNotPinnedError):
                extractor.identity()

    def test_pinned_tool_runs_bounded_and_version_checked(self) -> None:
        script = (
            "#!/bin/sh\n"
            'if [ "$1" = "-v" ]; then echo "faketool 24.02.0" 1>&2; exit 0; fi\n'
            "cat -\n"
        ).encode("utf-8")
        with tempfile.TemporaryDirectory() as temporary:
            binary = Path(temporary) / "faketool"
            binary.write_bytes(script)
            os.chmod(binary, os.stat(binary).st_mode | stat.S_IXUSR)
            extractor = PinnedBinaryExtractor(
                binary_path=binary,
                expected_sha256=sha256_file(binary),
                expected_version="24.02.0",
            )
            identity = extractor.identity()
            self.assertEqual("pdftotext", identity["tool"])
            self.assertEqual(sha256_file(binary), identity["binary_sha256"])
            text = extractor.extract(
                b"Extracted paragraph.\n", media_type="application/pdf",
            )
            self.assertEqual("Extracted paragraph.\n", text)
            wrong_version = PinnedBinaryExtractor(
                binary_path=binary,
                expected_sha256=sha256_file(binary),
                expected_version="25.00.0",
            )
            with self.assertRaises(ExtractorNotPinnedError):
                wrong_version.extract(b"x\n", media_type="application/pdf")


class RegistryTests(unittest.TestCase):
    def test_default_registry_covers_text_and_latex_only(self) -> None:
        registry = default_registry()
        self.assertEqual(
            frozenset({
                "text/plain", "text/markdown", "application/x-latex",
                "text/x-tex",
            }),
            registry.media_types(),
        )
        self.assertIsNone(registry.extractor_for("application/pdf"))

    def test_duplicate_media_type_claims_refuse(self) -> None:
        with self.assertRaises(ExtractorRegistryInvalidError):
            ExtractorRegistry((IdentityTextExtractor(), IdentityTextExtractor()))


if __name__ == "__main__":
    unittest.main()
