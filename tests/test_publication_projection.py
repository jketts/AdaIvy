"""Acceptance suite for the ADR-0036 publication projection.

Under ADR-0026 this file is the sole executable record of the slice's
thresholds, so it asserts the properties rather than the happy path: that the
fixture renders no theorem and says so, that every render rule can be made to
fail by a single-field mutation, that no single-field mutation can *promote* a
claim, that the ledger cannot be forged, that the bibliography's content hashes
match the actual repository bytes, that the certificates match what the live
engine computes, and that the renderer reads no clock, no randomness and no
environment.
"""

from __future__ import annotations

import ast
import copy
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from math_research.publication import (  # noqa: E402
    PublicationValidationError,
    build_bundle,
    classify_claim,
    load_manuscript,
    render_manuscript,
    run_probes,
    verify_headline_closure,
    verify_ledger_closure,
    write_bundle,
)
from math_research.publication.bibliography import build_bibliography  # noqa: E402
from math_research.publication.bundle import verify_bundle  # noqa: E402
from math_research.publication.evidence import (  # noqa: E402
    ENVIRONMENTS,
    EVIDENCE_CLASSES,
    HEADINGS,
)
from math_research.publication.latexsafe import escape_prose, validate_math  # noqa: E402
from math_research.publication.probes import _resolve  # noqa: E402
from math_research.publication.render import (  # noqa: E402
    TEMPLATE_HASH,
    TEMPLATE_HEAD,
    TEMPLATE_TAIL,
    LedgerBlock,
    RenderedDocument,
    counter_candidate_rows,
    ledger_payload,
    reading_verdict_rows,
    subject_label,
)
from math_research.publication.production import (  # noqa: E402
    _headline_probe_present,
    _require_prior_art_classification,
    produce_publication,
)
from math_research.publication.typeset import (  # noqa: E402
    ToolchainStatus,
    build_command,
    build_environment,
    load_toolchain,
    toolchain_status,
    typeset_bundle,
)
from math_research.campaign import (  # noqa: E402
    ActionRecord, ActionType, ActorType, ModelCallRecord, RecordStatus,
    UsageSource, build_campaign_export,
)
from math_research.publication.campaign import (  # noqa: E402
    ClaimContribution, build_publication_campaign_link,
)
from math_research.publication.manuscript import (  # noqa: E402
    RESOLUTION_LEXICON,
    _announcement_subject_hash,
    _unqualified_lexicon_hits,
    passage_effective_reading_status,
)
from math_research.conventions import (  # noqa: E402
    ContestedTerm,
    ConventionRecord,
    Reading,
    ReadingVerdict,
    VerdictMatrix,
)
from math_research.novelty import NoveltyRecheck  # noqa: E402

#: Sentinel for "delete this key" in the passage and replay mutation helpers. A
#: deleted field and a null field are different records under ADR-0060.
_DELETE = object()

MANUSCRIPT_PATH = REPO_ROOT / "fixtures/publication/manuscript-v1.json"
GRAFFITI_322_PATH = REPO_ROOT / "fixtures/publication/manuscript-graffiti-322-v1.json"
TOOLCHAIN_PATH = REPO_ROOT / "config/publication-typeset-toolchain-v1.json"
PHASE5_FIXTURE = REPO_ROOT / "fixtures/phase5/quantum-diagonal-v1.json"
PUBLICATION_ROOT = SRC_ROOT / "math_research/publication"


def _sha(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _fixture_value() -> dict:
    return json.loads(MANUSCRIPT_PATH.read_text(encoding="utf-8"))


def _g322_value() -> dict:
    return json.loads(GRAFFITI_322_PATH.read_text(encoding="utf-8"))


# A deliberately synthetic manuscript. It exists to exercise the attestation
# ladder, which no offline path can reach: `make check` excludes the sealed
# ADR-0016 Lean runtime, so the shipped fixture carries no attestation and the
# rendered bundle carries no theorem. Nothing here is a recorded kernel result.
SYNTHETIC_LEAN = "theorem ada_synthetic : 1 + 1 = 2 := by norm_num"


def _synthetic_manuscript(outcome: str, *, unapproved: list[str], representation: str) -> dict:
    lean_hash = _sha(SYNTHETIC_LEAN.encode("utf-8"))
    return {
        "schema_version": "1.4.0",
        "manuscript_id": "ms.synthetic-attestation-ladder.v1",
        "title_stem": "Synthetic attestation ladder",
        "authors": [{"name": "Acceptance suite", "role": "synthetic"}],
        "abstract": "Synthetic. Exercises the attestation ladder only.",
        "corpus_provenance": "project_authored",
        "novelty": {"status": "not_assessed", "inferred_from_warrant": False},
        "significance": {"status": "not_assessed", "inferred_from_warrant": False},
        "publication_approval": None,
        "run_disclosure": {
            "run_id": "run.synthetic-publication.v1",
            "usage_scope": "synthetic acceptance fixture",
            "measurement_status": "complete",
            "models": [{
                "provider": "none", "model": "none", "calls": 0,
                "outcome": "no model invoked",
            }],
            "model_calls": 0,
            "cost_usd": "0",
            "budget_cap_usd": "0",
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
            "note": "Synthetic acceptance record; no external run usage.",
        },
        "toolchain": {
            "elan_version": "v4.2.1",
            "lean_version": "v4.32.1",
            "lean_commit": "f054605aea4b840552cca2e725580bffd1e1b704",
            "mathlib_version": "v4.32.1",
            "mathlib_commit": "520045ab14e26149ee970e2e617ca04b09bde5d6",
        },
        "sources": [
            {
                "source_id": "src.synthetic-original-problem",
                "content_hash": _sha(b"synthetic original problem"),
                "authority": "human_final",
                "rights": {"publication": "permitted", "excerpting": "permitted"},
                "bibliographic": {
                    "entry_type": "unpublished",
                    "author": "Acceptance suite",
                    "title": "Synthetic original problem",
                    "container": "AdaIvy acceptance fixtures",
                    "year": "2026",
                    "identifier": "tests/test_publication_projection.py",
                },
                "passages": [
                    {
                        "passage_id": "psg.synthetic-original-problem",
                        "anchor": "synthetic fixture",
                        "content_hash": _sha(b"one plus one problem"),
                        "quotation_permitted": True,
                        "extraction_method": "text_layer",
                        "reading_status": "verbatim_confirmed",
                        "verbatim_text": "One plus one is two.",
                        "verbatim_hash": _sha("One plus one is two.".encode("utf-8")),
                        "publication_restricted": False,
                    }
                ],
            }
        ],
        "citations": [
            {
                "citation_id": "cite.synthetic-original-problem",
                "citation_class": "source_record",
                "source_id": "src.synthetic-original-problem",
                "passage_id": "psg.synthetic-original-problem",
                "cited_object": "problem",
                "intended_use": "publication",
                "target_exclusion": None,
            }
        ],
        "attestations": [
            {
                "attestation_id": "att.synthetic",
                "finding_id": "finding.synthetic",
                "declaration_name": "Ada.Synthetic.one_add_one",
                "outcome": outcome,
                "approved_axioms": ["propext"],
                "unapproved_assumptions": unapproved,
                "target_statement_hash": lean_hash,
                "wrapper_hash": _sha(b"wrapper"),
                "runtime_hash": _sha(b"runtime"),
                "lean_source": SYNTHETIC_LEAN,
            }
        ],
        "certificates": [],
        "claims": [
            {
                "claim_id": "cl.synthetic",
                "authorship": {
                    "ai_generated": True,
                    "generator": "AdaIvy project",
                },
                "prose_statement": "One and one are two.",
                "latex_statement": r"1 + 1 = 2",
                "lean_statement": SYNTHETIC_LEAN,
                "lean_artifact": {
                    "artifact_id": "lean.synthetic",
                    "declaration_name": "Ada.Synthetic.one_add_one",
                    "source": SYNTHETIC_LEAN,
                    "source_hash": lean_hash,
                    "verification_status": (
                        "kernel_checked" if outcome.startswith("kernel_checked") else "failed"
                    ),
                    "finding_id": "finding.synthetic",
                },
                "representation_id": "rep.synthetic",
                "representation_status": representation,
                "attestation_id": "att.synthetic",
                "certificate_id": None,
                "certificate_role": None,
                "citations": [],
                "original_problem_citation_id": "cite.synthetic-original-problem",
                "derivation": {
                    "status": "included",
                    "summary": "Normalize the closed arithmetic expression and compare both sides.",
                    "citations": ["cite.synthetic-original-problem"],
                },
                "resolution_target": None,
                "verdict_matrix_id": None,
            }
        ],
        "obligations": [],
        "conventions": [],
        "verdict_matrices": [],
        "counter_candidate_replays": [],
        "prior_art_engagement": None,
        "novelty_rechecks": [],
        "sections": [
            {
                "section_id": "sec.synthetic",
                "title": "Synthetic",
                "blocks": [
                    {
                        "block_id": "blk.synthetic",
                        "kind": "claim",
                        "record_refs": ["cl.synthetic", "att.synthetic"],
                        "claim_id": "cl.synthetic",
                    }
                ],
            }
        ],
        # One probe on reader-facing text, because ``produce_publication``
        # refuses a publication without one (ADR-0058). It is never executed by
        # the tests that patch ``run_probes``; it is here so the synthetic
        # manuscript satisfies the same rule the shipped fixtures do.
        "render_probes": [
            {
                "probe_id": "pr.synthetic.abstract-must-not-overclaim",
                "field": "abstract",
                "value": "This synthetic note proves the target conjecture.",
                "expected_outcome": "refusal",
                "expected": {"code": "abstract_overclaims_evidence"},
                "rationale": "No record here earns resolution language.",
            }
        ],
    }


class FixtureProjectionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.manuscript = load_manuscript(MANUSCRIPT_PATH.read_bytes())
        self.document = render_manuscript(self.manuscript)

    def test_the_fixture_reports_formal_artifacts_separately_from_full_theorems(self) -> None:
        counts = self.document.statistics["evidence_class_counts"]
        self.assertEqual(counts["kernel_checked_theorem"], 0)
        self.assertEqual(counts["exact_certificate_proposition"], 3)
        self.assertEqual(counts["proposal"], 2)
        self.assertIn(
            "No linked formal artifact has a recorded successful Lean kernel check",
            self.document.tex,
        )
        self.assertIn("no fully Lean-verified Theorems", self.document.tex)
        self.assertIn("3 exact-certificate Propositions", self.document.tex)
        self.assertEqual(counts["convention_relative_proposition"], 0)
        self.assertIn("no convention-relative Propositions", self.document.tex)
        self.assertNotIn(r"\begin{adaconditional}", self.document.tex)
        self.assertNotIn("Claims by computed evidence class", self.document.tex)
        self.assertNotIn(r"\begin{adatheorem}", self.document.tex)

    def test_the_status_block_is_emitted_by_the_renderer_and_not_by_a_section(self) -> None:
        status = [block for block in self.document.ledger if block.block_id == "derived.status"]
        self.assertEqual(len(status), 1)
        self.assertEqual(status[0].origin, "derived")
        self.assertNotIn("derived.status", {str(block_id) for block_id in self.manuscript.blocks})
        for field in (
            r"not\_assessed", r"project\_authored",
            "No human publication approval record exists",
            "Automated checks alone do not make this an endorsed AdaIvy result",
        ):
            self.assertIn(field, status[0].tex)

    def test_every_ledger_block_carries_a_record_reference_that_resolves(self) -> None:
        namespace = set(self.manuscript.record_ids) | {self.manuscript.manuscript_id}
        self.assertTrue(self.document.ledger)
        for block in self.document.ledger:
            self.assertTrue(block.record_refs, block.block_id)
            for ref in block.record_refs:
                self.assertIn(ref, namespace, f"{block.block_id} -> {ref}")

    def test_ledger_closure_is_byte_exact_and_a_forged_document_is_refused(self) -> None:
        verify_ledger_closure(self.document)
        forged = RenderedDocument(
            manuscript_id=self.document.manuscript_id,
            manuscript_hash=self.document.manuscript_hash,
            template_hash=self.document.template_hash,
            document_hash=self.document.document_hash,
            headline=self.document.headline,
            tex=self.document.tex + "\n% smuggled in after the ledger closed\n",
            ledger=self.document.ledger,
            classifications=self.document.classifications,
            bibliography=self.document.bibliography,
            cite_keys=self.document.cite_keys,
            statistics=self.document.statistics,
        )
        with self.assertRaises(PublicationValidationError) as caught:
            verify_ledger_closure(forged)
        self.assertEqual(caught.exception.code, "ledger_closure_broken")

        misrecorded = RenderedDocument(
            manuscript_id=self.document.manuscript_id,
            manuscript_hash=self.document.manuscript_hash,
            template_hash=self.document.template_hash,
            document_hash="sha256:" + "0" * 64,
            headline=self.document.headline,
            tex=self.document.tex,
            ledger=self.document.ledger,
            classifications=self.document.classifications,
            bibliography=self.document.bibliography,
            cite_keys=self.document.cite_keys,
            statistics=self.document.statistics,
        )
        with self.assertRaises(PublicationValidationError) as caught:
            verify_ledger_closure(misrecorded)
        self.assertEqual(caught.exception.code, "document_hash_mismatch")

        unbacked = RenderedDocument(
            manuscript_id=self.document.manuscript_id,
            manuscript_hash=self.document.manuscript_hash,
            template_hash=self.document.template_hash,
            document_hash=self.document.document_hash,
            headline=self.document.headline,
            tex=self.document.tex,
            ledger=self.document.ledger
            + (LedgerBlock(block_id="blk.unbacked", origin="manuscript", record_refs=(), tex=""),),
            classifications=self.document.classifications,
            bibliography=self.document.bibliography,
            cite_keys=self.document.cite_keys,
            statistics=self.document.statistics,
        )
        with self.assertRaises(PublicationValidationError) as caught:
            verify_ledger_closure(unbacked)
        self.assertEqual(caught.exception.code, "block_without_record_ref")

    def test_the_document_is_byte_identical_across_calls_and_a_fresh_process(self) -> None:
        again = render_manuscript(load_manuscript(MANUSCRIPT_PATH.read_bytes()))
        self.assertEqual(again.tex, self.document.tex)
        self.assertEqual(again.document_hash, self.document.document_hash)
        script = (
            "import json,sys;"
            f"sys.path.insert(0, {str(SRC_ROOT)!r});"
            "from math_research.publication import load_manuscript, render_manuscript;"
            f"d=render_manuscript(load_manuscript(open({str(MANUSCRIPT_PATH)!r},'rb').read()));"
            "print(d.document_hash)"
        )
        completed = subprocess.run(
            [sys.executable, "-c", script], capture_output=True, text=True, check=True,
            cwd=str(REPO_ROOT),
        )
        self.assertEqual(completed.stdout.strip(), self.document.document_hash)

    def test_the_template_carries_no_manuscript_data(self) -> None:
        from math_research.publication.render import TEMPLATE_HEAD, TEMPLATE_TAIL

        template = TEMPLATE_HEAD + TEMPLATE_TAIL
        self.assertNotIn(self.manuscript.manuscript_id, template)
        self.assertNotIn(str(self.manuscript.value["title_stem"]), template)
        self.assertEqual(self.document.template_hash, TEMPLATE_HASH)

    def test_every_publication_uses_the_classic_graffiti_197_layout(self) -> None:
        tex = self.document.tex
        self.assertIn(r"\documentclass[11pt]{article}", tex)
        self.assertNotIn("a4paper", tex)
        for setting in (
            r"\setlength{\textwidth}{6.35in}",
            r"\setlength{\textheight}{8.9in}",
            r"\setlength{\oddsidemargin}{0.05in}",
            r"\setlength{\topmargin}{-0.35in}",
            r"\setlength{\parskip}{0.65em}",
        ):
            self.assertIn(setting, tex)

    def test_the_document_cannot_contain_its_own_hash(self) -> None:
        self.assertNotIn(self.document.document_hash, self.document.tex)
        self.assertIn(self.document.manuscript_hash, self.document.tex)


class ProbeSuiteTests(unittest.TestCase):
    def setUp(self) -> None:
        self.manuscript = load_manuscript(MANUSCRIPT_PATH.read_bytes())

    def test_every_probe_flips(self) -> None:
        result = run_probes(self.manuscript)
        unflipped = [item for item in result["probes"] if not item["flipped"]]
        self.assertEqual(unflipped, [], f"{len(unflipped)} probes did not flip")
        self.assertEqual(result["probes_flipped"], result["probes_total"])
        self.assertGreaterEqual(result["probes_total"], 17)

    def test_a_probe_that_cannot_flip_fails_the_bundle(self) -> None:
        value = _fixture_value()
        value["render_probes"].append({
            "probe_id": "pr.unflippable",
            "field": "claims[cl.cubic-optimum-degree].representation_status",
            "value": "partially_verified",
            "expected_outcome": "demotion",
            "expected": {"claim_id": "cl.cubic-optimum-degree", "evidence_class": "proposal"},
            "rationale": "This claim is already a proposal, so nothing can demote it further.",
        })
        manuscript = load_manuscript(value)
        result = run_probes(manuscript)
        self.assertLess(result["probes_flipped"], result["probes_total"])
        with self.assertRaises(PublicationValidationError) as caught:
            build_bundle(manuscript)
        self.assertEqual(caught.exception.code, "probe_did_not_flip")

    def test_a_probe_that_changes_nothing_is_refused(self) -> None:
        value = _fixture_value()
        value["render_probes"] = [{
            "probe_id": "pr.no-change",
            "field": "certificates[cert.orthogonal-2d-optimum].gap",
            "value": "0",
            "expected_outcome": "demotion",
            "expected": {"claim_id": "cl.orthogonal-2d-optimum", "evidence_class": "proposal"},
            "rationale": "Sets the field to the value it already has.",
        }]
        with self.assertRaises(PublicationValidationError) as caught:
            run_probes(load_manuscript(value))
        self.assertEqual(caught.exception.code, "probe_value_unchanged")

    def test_a_probe_naming_a_field_that_does_not_exist_is_refused(self) -> None:
        value = _fixture_value()
        value["render_probes"] = [{
            "probe_id": "pr.no-such-field",
            "field": "certificates[cert.orthogonal-2d-optimum].not_a_field",
            "value": "x",
            "expected_outcome": "refusal",
            "expected": {"code": "certificate_not_exact"},
            "rationale": "Names a field the certificate does not own.",
        }]
        with self.assertRaises(PublicationValidationError) as caught:
            run_probes(load_manuscript(value))
        self.assertEqual(caught.exception.code, "probe_field_unresolved")


class PromotionImpossibilityTests(unittest.TestCase):
    """No single-field mutation may make a claim stronger than its records allow."""

    CANDIDATES = (
        True, False, None, 0, 1, "0", "kernel_checked", "kernel_checked_theorem", "verified",
        "adatheorem", "Theorem", "determines_optimum", "separates_values", "theorem",
        "fractions-exact", "permitted", [], {},
    )

    def test_no_single_field_mutation_promotes_a_claim_to_a_theorem(self) -> None:
        baseline_value = _fixture_value()
        baseline = load_manuscript(baseline_value)
        baseline_classes = {
            item.claim_id: item.evidence_class
            for item in render_manuscript(baseline).classifications
        }
        self.assertNotIn("kernel_checked_theorem", set(baseline_classes.values()))
        checked = 0
        for collection in ("claims", "certificates"):
            for index, item in enumerate(baseline_value[collection]):
                for field in item:
                    for candidate in self.CANDIDATES:
                        mutated = copy.deepcopy(baseline_value)
                        if mutated[collection][index][field] == candidate:
                            continue
                        mutated[collection][index][field] = candidate
                        checked += 1
                        try:
                            document = render_manuscript(load_manuscript(mutated))
                        except PublicationValidationError:
                            continue
                        for classification in document.classifications:
                            self.assertNotEqual(
                                classification.evidence_class, "kernel_checked_theorem",
                                f"{collection}[{index}].{field}={candidate!r} promoted "
                                f"{classification.claim_id}",
                            )
                            was = baseline_classes.get(classification.claim_id)
                            if was is not None and classification.claim_id != item.get("claim_id"):
                                continue
        self.assertGreater(checked, 200)


class AttestationLadderTests(unittest.TestCase):
    """The theorem rung is reachable, and every step below it demotes."""

    def _class_of(self, manuscript_value: dict) -> str:
        manuscript = load_manuscript(manuscript_value)
        return classify_claim(manuscript, "cl.synthetic").evidence_class

    def test_bare_kernel_checked_on_a_verified_representation_is_a_theorem(self) -> None:
        value = _synthetic_manuscript("kernel_checked", unapproved=[], representation="verified")
        self.assertEqual(self._class_of(value), "kernel_checked_theorem")
        document = render_manuscript(load_manuscript(value))
        self.assertIn(r"\begin{adatheorem}", document.tex)
        self.assertIn("Lean verification.} Passed for one linked formal artifact", document.tex)
        self.assertIn("one fully Lean-verified Theorem", document.tex)
        self.assertIn(r"theorem ada\_synthetic : 1 + 1 = 2 := by norm\_num", document.tex)
        self.assertIn("AI-generated by AdaIvy project", document.tex)
        self.assertIn("Auditable derivation", document.tex)
        self.assertIn("Original problem:", document.tex)
        self.assertIn(r"\cite{src:synthetic-original-problem}", document.tex)
        self.assertNotIn(r"\cite[", document.tex)
        self.assertIn("https://github.com/jketts/AdaIvy", document.tex)
        self.assertIn("Run disclosure", document.tex)
        self.assertIn("0 request(s) attempted; no model invoked", document.tex)
        self.assertIn("Recorded tokens: 0 input, 0 output, 0 total", document.tex)
        self.assertIn(
            r"\adaformalartifact{status \texttt{kernel\_checked}}"
            r"{lean/Ada_Synthetic_one_add_one.lean}",
            document.tex,
        )

    def test_partial_lean_check_does_not_erase_an_independent_exact_certificate(self) -> None:
        value = _synthetic_manuscript(
            "kernel_checked", unapproved=[], representation="partially_verified"
        )
        value["certificates"] = [{
            "certificate_id": "cert.synthetic-separation",
            "case_id": "synthetic-case",
            "run_id": "run.synthetic-publication.v1",
            "engine": "exact-test-engine",
            "arithmetic": "integer-exact",
            "float_used": False,
            "primal_value": "2",
            "dual_value": "1",
            "gap": "1",
            "classification": "values_separated",
            "result_hash": _sha(b"synthetic exact certificate"),
        }]
        value["claims"][0]["certificate_id"] = "cert.synthetic-separation"
        value["claims"][0]["certificate_role"] = "separates_values"
        self.assertEqual(
            self._class_of(value), "exact_certificate_proposition"
        )
        document = render_manuscript(load_manuscript(value))
        self.assertIn("Lean verification.} Passed for one linked formal artifact", document.tex)
        self.assertIn("no fully Lean-verified Theorems", document.tex)
        self.assertIn("one exact-certificate Proposition", document.tex)

    def test_an_unverified_representation_demotes_a_kernel_checked_claim(self) -> None:
        for status in ("proposed", "partially_verified", "refuted"):
            value = _synthetic_manuscript("kernel_checked", unapproved=[], representation=status)
            self.assertEqual(self._class_of(value), "proposal", status)

    def test_approved_standard_axioms_is_a_proposition_and_never_a_theorem(self) -> None:
        value = _synthetic_manuscript(
            "kernel_checked_approved_standard_axioms", unapproved=[], representation="verified"
        )
        self.assertEqual(self._class_of(value), "exact_certificate_proposition")

    def test_an_unapproved_assumption_demotes_to_a_proposal(self) -> None:
        value = _synthetic_manuscript(
            "kernel_checked", unapproved=["sorryAx"], representation="verified"
        )
        self.assertEqual(self._class_of(value), "proposal")
        classification = classify_claim(load_manuscript(value), "cl.synthetic")
        self.assertIn("sorryAx", classification.reason)

    def test_every_non_kernel_outcome_demotes_to_a_proposal(self) -> None:
        for outcome in (
            "policy_rejection", "elaboration_failure", "meaning_test_failure", "timeout",
            "output_limit", "sandbox_failure",
        ):
            value = _synthetic_manuscript(outcome, unapproved=[], representation="verified")
            self.assertEqual(self._class_of(value), "proposal", outcome)

    def test_a_lean_statement_the_attestation_does_not_cover_is_refused(self) -> None:
        value = _synthetic_manuscript("kernel_checked", unapproved=[], representation="verified")
        value["claims"][0]["lean_statement"] = SYNTHETIC_LEAN + " -- edited after checking"
        with self.assertRaises(PublicationValidationError) as caught:
            load_manuscript(value)
        self.assertEqual(caught.exception.code, "lean_statement_hash_mismatch")

    def test_an_attestation_without_a_lean_statement_is_refused(self) -> None:
        value = _synthetic_manuscript("kernel_checked", unapproved=[], representation="verified")
        value["claims"][0]["lean_statement"] = None
        with self.assertRaises(PublicationValidationError) as caught:
            load_manuscript(value)
        self.assertEqual(caught.exception.code, "attestation_without_lean_statement")

    def test_an_unknown_attestation_outcome_is_refused_rather_than_demoted(self) -> None:
        value = _synthetic_manuscript("kernel_checked", unapproved=[], representation="verified")
        value["attestations"][0]["outcome"] = "kernel_checked_probably"
        with self.assertRaises(PublicationValidationError) as caught:
            load_manuscript(value)
        self.assertEqual(caught.exception.code, "attestation_outcome_unknown")


class LatexSafetyTests(unittest.TestCase):
    DANGEROUS = {
        r"\write18{id}": "unsafe_latex_primitive",
        r"\input{/etc/passwd}": "unsafe_latex_primitive",
        r"\openout1=x": "unsafe_latex_primitive",
        r"\immediate\write16{x}": "unsafe_latex_primitive",
        r"\directlua{os.execute('id')}": "unsafe_latex_primitive",
        r"\catcode`\%=12": "unsafe_latex_primitive",
        r"\csname relax\endcsname": "unsafe_latex_primitive",
        r"\def\x{y}": "unsafe_latex_primitive",
        r"\usepackage{shellesc}": "unsafe_latex_primitive",
        r"\jobname": "unsafe_latex_primitive",
        r"\makeatletter\@gobble": "unsafe_latex_primitive",
        r"\special{ps: x}": "unsafe_latex_primitive",
        r"\notarealmacro{x}": "unknown_latex_macro",
        r"\frac{1}{2": "latex_unbalanced_braces",
        r"x$y": "math_shift_in_fragment",
        r"x % comment": "comment_in_math_fragment",
        r"\begin{verbatim}x\end{verbatim}": "unsafe_latex_environment",
        r"\begin{tikzpicture}\end{tikzpicture}": "unsafe_latex_environment",
    }

    def test_the_allowlist_refuses_by_class(self) -> None:
        for fragment, code in self.DANGEROUS.items():
            with self.subTest(fragment=fragment):
                with self.assertRaises(PublicationValidationError) as caught:
                    validate_math(fragment, "field")
                self.assertEqual(caught.exception.code, code)

    def test_legitimate_mathematics_is_admitted(self) -> None:
        for fragment in (
            r"\mathrm{val}(\mathcal{E}) = \tfrac{2}{3}",
            r"\sum_{i=1}^{n} \langle \psi_i, \Gamma \psi_i \rangle \leq 1",
            r"\deg_{\mathbb{Q}} \alpha = 3",
            r"\begin{pmatrix} 1 & 0 \\ 0 & 1 \end{pmatrix}",
            r"\lim_{n \to \infty} x_n = \sup_{k} y_k",
        ):
            with self.subTest(fragment=fragment):
                self.assertEqual(validate_math(fragment, "field"), fragment)

    def test_prose_escaping_leaves_no_control_sequence(self) -> None:
        escaped = escape_prose(r"\write18{id} costs 100% & $5 #1 _x ^y ~z", "field")
        self.assertNotIn(r"\write", escaped)
        self.assertEqual(escaped.count("$"), escaped.count(r"\$"))
        for character in ("{", "}", "%", "&", "#", "_", "^", "~"):
            self.assertNotIn(character + "unescaped", escaped)
        self.assertIn(r"\textbackslash{}", escaped)

    def test_a_control_character_is_refused(self) -> None:
        with self.assertRaises(PublicationValidationError) as caught:
            escape_prose("bell\x07", "field")
        self.assertEqual(caught.exception.code, "control_character_in_field")

    def test_no_unsafe_primitive_reaches_the_rendered_document(self) -> None:
        document = render_manuscript(load_manuscript(MANUSCRIPT_PATH.read_bytes()))
        body = document.tex.split(r"\begin{document}", 1)[1]
        for forbidden in (r"\write", r"\input{", r"\openout", r"\directlua", r"\csname", r"\def"):
            self.assertNotIn(forbidden, body, forbidden)


class BibliographyClosureTests(unittest.TestCase):
    def setUp(self) -> None:
        self.manuscript = load_manuscript(MANUSCRIPT_PATH.read_bytes())
        self.document = render_manuscript(self.manuscript)

    def test_every_cited_key_has_an_entry_and_every_entry_is_cited(self) -> None:
        keys = {entry.key for entry in self.document.bibliography}
        self.assertEqual(keys, set(self.document.cite_keys))
        self.assertEqual(len(keys), len(self.manuscript.sources))

    def test_source_citations_are_plain_numbers_and_details_stay_in_references(self) -> None:
        self.assertNotIn(r"\cite[", self.document.tex)
        self.assertNotIn(r"[\cite", self.document.tex)
        self.assertIn(r"\cite{src:adr-0023-exact-commuting}", self.document.tex)
        bibliography = self.document.tex.split(r"\begin{thebibliography}", 1)[1]
        self.assertIn("ADR-0023: Exact commuting quantum slice", bibliography)
        self.assertIn("located passage", bibliography)
        self.assertIn("content hash sha256:", bibliography)

    def test_an_uncited_source_record_is_refused(self) -> None:
        value = _fixture_value()
        value["sources"].append(copy.deepcopy(value["sources"][0]))
        value["sources"][-1]["source_id"] = "src.never-cited"
        value["sources"][-1]["passages"] = []
        with self.assertRaises(PublicationValidationError) as caught:
            build_bibliography(load_manuscript(value))
        self.assertEqual(caught.exception.code, "bibliography_entry_uncited")

    def test_a_mathlib_citation_produces_no_bibliography_entry(self) -> None:
        for entry in self.document.bibliography:
            self.assertNotIn("mathlib", entry.key)
        self.assertIn(r"\texttt{Rat.num\_div\_den}", self.document.tex)
        self.assertIn(r"(mathlib \texttt{520045ab14e2})", self.document.tex)

    def test_unrecorded_background_appears_as_an_obligation_and_never_as_a_citation(self) -> None:
        bundle = build_bundle(self.manuscript)
        bib = bundle.files["refs.bib"].decode("utf-8")
        self.assertNotIn("folklore", bib)
        self.assertNotIn("jrf-general-convergence", bib)
        self.assertIn("obl.jrf-general-convergence", self.document.tex)
        self.assertIn("Open obligations", self.document.tex)

    def test_bibliography_entries_carry_the_source_content_hash(self) -> None:
        for entry in self.document.bibliography:
            fields = dict(entry.fields)
            self.assertIn("addendum", fields)
            self.assertIn("sha256:", fields["addendum"])


class SourceRecordFidelityTests(unittest.TestCase):
    """The recorded hashes must match the actual bytes, or they are decoration."""

    def setUp(self) -> None:
        self.manuscript = load_manuscript(MANUSCRIPT_PATH.read_bytes())

    def test_every_source_content_hash_matches_the_named_repository_file(self) -> None:
        self.assertTrue(self.manuscript.sources)
        for source_id, source in self.manuscript.sources.items():
            path = REPO_ROOT / str(source["bibliographic"]["identifier"])
            self.assertTrue(path.exists(), f"{source_id} names {path}")
            self.assertEqual(_sha(path.read_bytes()), source["content_hash"], source_id)

    def test_every_passage_hash_matches_the_named_line_range(self) -> None:
        for source_id, source in self.manuscript.sources.items():
            path = REPO_ROOT / str(source["bibliographic"]["identifier"])
            lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
            for passage in source["passages"]:
                anchor = str(passage["anchor"])
                start, end = (int(part.lstrip("L")) for part in anchor.split("-"))
                extracted = "".join(lines[start - 1:end]).encode("utf-8")
                self.assertEqual(
                    _sha(extracted), passage["content_hash"],
                    f"{source_id} {passage['passage_id']} {anchor}",
                )
                self.assertTrue(extracted.strip(), "an empty passage is not a citation")


class CertificateFidelityTests(unittest.TestCase):
    """Certificates in the manuscript must match what the live engine computes."""

    def test_every_certificate_matches_the_exact_engine_result(self) -> None:
        from math_research.phase5.quantum import DiagonalCase, run_case

        fixture = json.loads(PHASE5_FIXTURE.read_text(encoding="utf-8"))
        results = {}
        for case in fixture["cases"]:
            outcome = run_case(DiagonalCase.from_value(case))
            results[str(case["case_id"])] = outcome
        manuscript = load_manuscript(MANUSCRIPT_PATH.read_bytes())
        self.assertTrue(manuscript.certificates)
        for certificate_id, certificate in manuscript.certificates.items():
            case_id = str(certificate["case_id"])
            self.assertIn(case_id, results, certificate_id)
            outcome = results[case_id]
            self.assertEqual(certificate["result_hash"], outcome["result_hash"], certificate_id)
            self.assertEqual(certificate["arithmetic"], outcome["arithmetic"], certificate_id)
            self.assertEqual(
                certificate["dual_value"], outcome["independent_dual_optimum"], certificate_id
            )
            self.assertEqual(certificate["primal_value"], outcome["final_objective"], certificate_id)
            self.assertEqual(certificate["gap"], outcome["primal_dual_gap"], certificate_id)


class CertificateRoleTests(unittest.TestCase):
    def test_a_certificate_and_a_role_must_be_named_together(self) -> None:
        value = _fixture_value()
        for claim in value["claims"]:
            if claim["certificate_id"] is not None:
                claim["certificate_role"] = None
                break
        with self.assertRaises(PublicationValidationError) as caught:
            load_manuscript(value)
        self.assertEqual(caught.exception.code, "certificate_role_unpaired")

    def test_both_role_mismatches_demote(self) -> None:
        value = _fixture_value()
        for claim in value["claims"]:
            if claim["certificate_role"] == "determines_optimum":
                claim["certificate_role"] = "separates_values"
        document = render_manuscript(load_manuscript(value))
        classes = {item.claim_id: item.evidence_class for item in document.classifications}
        self.assertEqual(classes["cl.orthogonal-2d-optimum"], "proposal")

        value = _fixture_value()
        for claim in value["claims"]:
            if claim["certificate_role"] == "separates_values":
                claim["certificate_role"] = "determines_optimum"
        document = render_manuscript(load_manuscript(value))
        classes = {item.claim_id: item.evidence_class for item in document.classifications}
        self.assertEqual(classes["cl.scalar-iterate-separation"], "proposal")
        self.assertEqual(classes["cl.nonoptimal-fixed-point"], "proposal")

    def test_a_floating_point_certificate_is_refused_at_load(self) -> None:
        for field, replacement in (("float_used", True), ("arithmetic", "float64")):
            value = _fixture_value()
            value["certificates"][0][field] = replacement
            with self.assertRaises(PublicationValidationError) as caught:
                load_manuscript(value)
            self.assertEqual(caught.exception.code, "certificate_not_exact", field)

    def test_a_decimal_value_is_not_an_exact_rational(self) -> None:
        value = _fixture_value()
        value["certificates"][0]["gap"] = "0.0"
        with self.assertRaises(PublicationValidationError) as caught:
            load_manuscript(value)
        self.assertEqual(caught.exception.code, "rational_not_exact")


class BundleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.manuscript = load_manuscript(MANUSCRIPT_PATH.read_bytes())
        self.bundle = build_bundle(
            self.manuscript, toolchain=load_toolchain(TOOLCHAIN_PATH)
        )

    def test_the_bundle_carries_the_records_the_projection_read(self) -> None:
        for path in (
            "paper.tex", "refs.bib", "records/manuscript.json", "records/ledger.json",
            "records/evidence.json", "records/prior-art.json", "records/probes.json",
            "build.json", "README.md",
        ):
            self.assertIn(path, self.bundle.files, path)
        recorded = json.loads(self.bundle.files["records/manuscript.json"])
        self.assertEqual(recorded, self.manuscript.value)

    def test_verified_campaign_records_can_be_manifested_with_the_bundle(self) -> None:
        campaign = b'{"campaign":"verified"}\n'
        link = b'{"link":"verified"}\n'
        bundle = build_bundle(
            self.manuscript,
            record_files={
                "records/campaign.json": campaign,
                "records/publication-campaign-link.json": link,
            },
        )
        self.assertEqual(campaign, bundle.files["records/campaign.json"])
        self.assertEqual(link, bundle.files["records/publication-campaign-link.json"])
        manifested = {item["path"] for item in bundle.manifest["files"]}
        self.assertIn("records/campaign.json", manifested)
        self.assertIn("records/publication-campaign-link.json", manifested)

    def test_additional_publication_record_cannot_escape_records_directory(self) -> None:
        with self.assertRaises(PublicationValidationError) as caught:
            build_bundle(self.manuscript, record_files={"records/../paper.tex": b"forged"})
        self.assertEqual(caught.exception.code, "publication_record_file_invalid")

    def test_unapproved_bundle_cannot_imply_that_prior_resolution_was_assessed(self) -> None:
        prior_art = json.loads(self.bundle.files["records/prior-art.json"])
        self.assertEqual("not_assessed", prior_art["report_classification"])
        self.assertEqual("not_assessed", prior_art["target_resolution_status"])
        self.assertFalse(prior_art["creates_mathematical_warrant"])
        self.assertIn("Prior-result classification", self.bundle.document.tex)

    def test_the_manifest_hashes_every_file_and_itself(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "bundle"
            manifest = write_bundle(self.bundle, output)
            verified = verify_bundle(output)
            self.assertEqual(verified["bundle_hash"], manifest["bundle_hash"])
            paths = {str(entry["path"]) for entry in manifest["files"]}
            self.assertEqual(paths, set(self.bundle.files))

    def test_a_tampered_bundle_file_is_detected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "bundle"
            write_bundle(self.bundle, output)
            (output / "paper.tex").write_text("tampered", encoding="utf-8")
            with self.assertRaises(PublicationValidationError) as caught:
                verify_bundle(output)
            self.assertEqual(caught.exception.code, "bundle_file_hash_mismatch")

    def test_a_tampered_manifest_is_detected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "bundle"
            write_bundle(self.bundle, output)
            manifest = json.loads((output / "MANIFEST.json").read_text(encoding="utf-8"))
            manifest["evidence_class_counts"]["kernel_checked_theorem"] = 3
            (output / "MANIFEST.json").write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaises(PublicationValidationError) as caught:
                verify_bundle(output)
            self.assertEqual(caught.exception.code, "bundle_hash_mismatch")

    def test_the_bundle_records_that_nothing_has_been_typeset(self) -> None:
        build = json.loads(self.bundle.files["build.json"])
        self.assertEqual(build["typeset_status"], "not_typeset")
        self.assertIsNone(build["pdf_sha256"])
        self.assertEqual(self.bundle.manifest["typeset_status"], "not_typeset")
        self.assertIsNone(self.bundle.manifest["pdf_sha256"])
        self.assertIn("never a pass", build["note"])

    def test_every_solved_claim_automatically_writes_a_linked_lean_file(self) -> None:
        solved = [
            item for item in self.bundle.document.classifications
            if item.evidence_class != "proposal"
        ]
        lean_paths = sorted(path for path in self.bundle.files if path.startswith("lean/"))
        self.assertEqual(len(lean_paths), len(solved))
        tex = self.bundle.files["paper.tex"].decode("utf-8")
        for path in lean_paths:
            self.assertIn("{" + path + "}", tex)
        self.assertIn("pending status", tex)

    def test_removing_a_solved_claim_artifact_is_refused(self) -> None:
        value = _fixture_value()
        value["claims"][0]["lean_artifact"] = None
        manuscript = load_manuscript(value)
        with self.assertRaises(PublicationValidationError) as caught:
            render_manuscript(manuscript)
        self.assertEqual(caught.exception.code, "solved_claim_without_lean_artifact")

    def test_removing_a_solved_claim_original_problem_citation_is_refused(self) -> None:
        value = _fixture_value()
        value["claims"][0]["original_problem_citation_id"] = None
        manuscript = load_manuscript(value)
        with self.assertRaises(PublicationValidationError) as caught:
            render_manuscript(manuscript)
        self.assertEqual(caught.exception.code, "solved_claim_without_original_problem_citation")

    def test_removing_a_solved_claim_derivation_is_refused(self) -> None:
        value = _fixture_value()
        value["claims"][0]["derivation"]["status"] = "unavailable"
        manuscript = load_manuscript(value)
        with self.assertRaises(PublicationValidationError) as caught:
            render_manuscript(manuscript)
        self.assertEqual(caught.exception.code, "solved_claim_without_derivation")

    def test_run_token_totals_must_close(self) -> None:
        value = _fixture_value()
        value["run_disclosure"]["total_tokens"] = 1
        with self.assertRaises(PublicationValidationError) as caught:
            load_manuscript(value)
        self.assertEqual(caught.exception.code, "token_total_mismatch")

    def test_complete_run_usage_cannot_hide_a_missing_value(self) -> None:
        value = _fixture_value()
        value["run_disclosure"]["cost_usd"] = None
        with self.assertRaises(PublicationValidationError) as caught:
            load_manuscript(value)
        self.assertEqual(caught.exception.code, "complete_usage_has_missing_value")

    def test_project_explanation_is_the_final_ledger_block(self) -> None:
        document = render_manuscript(load_manuscript(MANUSCRIPT_PATH.read_bytes()))
        self.assertEqual(document.ledger[-1].block_id, "derived.project-footnote")
        self.assertIn("https://github.com/jketts/AdaIvy", document.ledger[-1].tex)

    def test_tampering_with_lean_source_without_updating_its_hash_is_refused(self) -> None:
        value = _fixture_value()
        value["claims"][0]["lean_artifact"]["source"] += "\n-- changed"
        with self.assertRaises(PublicationValidationError) as caught:
            load_manuscript(value)
        self.assertEqual(caught.exception.code, "lean_artifact_hash_mismatch")

    def test_ai_generator_is_fixed_when_ai_generated_is_true(self) -> None:
        value = _synthetic_manuscript("kernel_checked", unapproved=[], representation="verified")
        value["claims"][0]["authorship"]["generator"] = "anonymous system"
        with self.assertRaises(PublicationValidationError) as caught:
            load_manuscript(value)
        self.assertEqual(caught.exception.code, "ai_generator_mismatch")

    def test_a_synthetic_attestation_writes_its_verbatim_lean_source(self) -> None:
        value = _synthetic_manuscript("kernel_checked", unapproved=[], representation="verified")
        bundle = build_bundle(load_manuscript(value))
        self.assertIn("lean/Ada_Synthetic_one_add_one.lean", bundle.files)
        source = bundle.files["lean/Ada_Synthetic_one_add_one.lean"].decode("utf-8")
        self.assertEqual(SYNTHETIC_LEAN, source)

    def test_theorem_artifact_must_bind_the_same_finding_as_its_attestation(self) -> None:
        value = _synthetic_manuscript("kernel_checked", unapproved=[], representation="verified")
        value["claims"][0]["lean_artifact"]["finding_id"] = "finding.someone-else"
        with self.assertRaises(PublicationValidationError) as caught:
            load_manuscript(value)
        self.assertEqual(caught.exception.code, "lean_artifact_finding_mismatch")


class TypesetGateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.toolchain = load_toolchain(TOOLCHAIN_PATH)

    def test_the_descriptor_disables_shell_escape_and_bounds_the_run(self) -> None:
        self.assertIn("-no-shell-escape", self.toolchain["flags"])
        self.assertIn("-halt-on-error", self.toolchain["flags"])
        self.assertIn("-interaction=nonstopmode", self.toolchain["flags"])
        self.assertLessEqual(int(self.toolchain["wall_seconds"]), 600)
        self.assertGreaterEqual(int(self.toolchain["passes"]), 2)

    def test_a_descriptor_that_enables_shell_escape_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "toolchain.json"
            value = dict(self.toolchain)
            value["flags"] = ["-shell-escape"]
            path.write_text(json.dumps(value), encoding="utf-8")
            with self.assertRaises(PublicationValidationError) as caught:
                load_toolchain(path)
            self.assertEqual(caught.exception.code, "toolchain_shell_escape_not_disabled")

    def test_the_command_is_a_fixed_argv_with_no_shell(self) -> None:
        command = build_command(self.toolchain, "/usr/bin/pdflatex", "paper.tex")
        self.assertEqual(command[0], "/usr/bin/pdflatex")
        self.assertEqual(command[-1], "paper.tex")
        self.assertIn("-no-shell-escape", command)
        for element in command:
            self.assertNotIn(";", element)
            self.assertNotIn("|", element)
            self.assertNotIn("&", element)

    def test_an_engine_with_the_wrong_version_is_not_available(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            engine = Path(directory) / "pdflatex"
            engine.write_text("#!/bin/sh\necho 'pdfTeX wrong version'\n", encoding="utf-8")
            engine.chmod(0o755)
            with mock.patch(
                "math_research.publication.typeset.shutil.which", return_value=str(engine)
            ):
                status = toolchain_status(self.toolchain)
        self.assertFalse(status.available)
        self.assertIn("version mismatch", status.reason)

    def test_the_environment_is_an_allowlist_carrying_a_frozen_epoch(self) -> None:
        environment = build_environment(self.toolchain, 1_577_836_800)
        self.assertEqual(environment["SOURCE_DATE_EPOCH"], "1577836800")
        self.assertEqual(environment["FORCE_SOURCE_DATE"], "1")
        self.assertTrue(set(environment) <= set(self.toolchain["environment_allowlist"]))

    def test_an_absent_toolchain_is_reported_and_never_counted_as_a_pass(self) -> None:
        status = toolchain_status(self.toolchain)
        if status.available:
            self.skipTest("a TeX engine is installed on this host")
        self.assertFalse(status.available)
        self.assertIn("not on PATH", status.reason)
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "bundle"
            write_bundle(build_bundle(load_manuscript(MANUSCRIPT_PATH.read_bytes())), output)
            with self.assertRaises(PublicationValidationError) as caught:
                typeset_bundle(output, self.toolchain)
            self.assertEqual(caught.exception.code, "typeset_toolchain_absent")
            manifest = json.loads((output / "MANIFEST.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["typeset_status"], "not_typeset")
            self.assertIsNone(manifest["pdf_sha256"])
            self.assertFalse((output / "paper.pdf").exists())


class AutomaticPublicationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.toolchain = load_toolchain(TOOLCHAIN_PATH)
        self.manuscript = load_manuscript(MANUSCRIPT_PATH.read_bytes())

    def test_nonempty_output_directory_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "bundle"
            output.mkdir()
            (output / "stale.txt").write_text("stale", encoding="utf-8")
            with self.assertRaises(PublicationValidationError) as caught:
                produce_publication(self.manuscript, output, self.toolchain)
            self.assertEqual(caught.exception.code, "publication_output_not_empty")

    def test_ai_authored_publication_requires_campaign_export_and_link(self) -> None:
        value = _fixture_value()
        value["claims"][0]["authorship"] = {
            "ai_generated": True,
            "generator": "AdaIvy project",
        }
        available = ToolchainStatus(True, "pdflatex", "/pinned/pdflatex", "available")
        with tempfile.TemporaryDirectory() as directory, mock.patch(
            "math_research.publication.production.toolchain_status", return_value=available
        ):
            with self.assertRaises(PublicationValidationError) as caught:
                produce_publication(
                    load_manuscript(value), Path(directory) / "bundle", self.toolchain,
                )
        self.assertEqual(caught.exception.code, "publication_campaign_provenance_required")

    def test_ai_publication_bundles_the_verified_campaign_and_link(self) -> None:
        manuscript = load_manuscript(
            _synthetic_manuscript("kernel_checked", unapproved=[], representation="verified")
        )
        proposal = _sha(b"synthetic campaign proposal")
        target = _sha(b"synthetic campaign target")
        configuration_hash = _sha(b"synthetic campaign configuration")
        call = ModelCallRecord(
            call_id="call.synthetic", campaign_id="campaign.synthetic.publication",
            action_id="action.synthetic", purpose="research", provider="openai",
            model_identifier="gpt-5.6-sol", live_configuration_hash=_sha(b"live"),
            pricing_snapshot_hash=_sha(b"pricing"), request_hash=_sha(b"request"),
            result_hash=proposal, status=RecordStatus.COMPLETED,
            usage_source=UsageSource.API_REPORTED, input_tokens=4, output_tokens=2,
            estimated_cost_microusd=10, provider_request_id="provider-synthetic",
            recorded_at="2026-08-21T00:00:00Z",
        )
        action_record = ActionRecord(
            action_id="action.synthetic", campaign_id="campaign.synthetic.publication",
            sequence=1, branch_id="branch.main", action_type=ActionType.DERIVE,
            actor_type=ActorType.MODEL, actor_id="model.central-lead",
            parent_action_ids=(), input_artifact_hashes=(target,),
            source_record_ids=(call.call_id,), output_artifact_hashes=(proposal,),
            status=RecordStatus.COMPLETED, declared_rationale="synthetic acceptance",
            recorded_at="2026-08-21T00:00:00Z",
        )
        campaign = build_campaign_export(
            campaign_id="campaign.synthetic.publication", target_hash=target,
            configuration_hash=configuration_hash, actions=(action_record,),
            model_calls=(call,),
        )
        link = build_publication_campaign_link(
            campaign,
            claims=(ClaimContribution(
                claim_id="cl.synthetic", discovery_action_ids=("action.synthetic",),
                contribution_action_ids=("action.synthetic",), artifact_hashes=(proposal,),
            ),),
            certificates=(),
        )
        available = ToolchainStatus(True, "pdflatex", "/pinned/pdflatex", "available")
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "bundle"

            def fake_typeset(bundle_dir: Path, toolchain: object) -> dict:
                self.assertTrue((bundle_dir / "records/campaign.json").is_file())
                self.assertTrue(
                    (bundle_dir / "records/publication-campaign-link.json").is_file()
                )
                (bundle_dir / "paper.pdf").write_bytes(b"%PDF-1.4\n")
                return {"bundle_hash": "sha256:" + "1" * 64}

            verified = {
                "bundle_hash": "sha256:" + "1" * 64,
                "typeset_status": "typeset", "pdf_sha256": "sha256:" + "2" * 64,
            }
            with mock.patch(
                "math_research.publication.production.toolchain_status", return_value=available
            ), mock.patch(
                "math_research.publication.production.typeset_bundle", side_effect=fake_typeset
            ), mock.patch(
                "math_research.publication.production.verify_bundle", return_value=verified
            ), mock.patch(
                "math_research.publication.bundle.run_probes",
                return_value={"probes_flipped": 1, "probes_total": 1, "probes": []},
            ):
                produce_publication(
                    manuscript, output, self.toolchain,
                    campaign_value=campaign, campaign_link=link,
                )

    def test_automatic_path_emits_projection_lean_and_pdf_as_one_operation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "bundle"

            def fake_typeset(bundle_dir: Path, toolchain: object) -> dict:
                self.assertTrue((bundle_dir / "paper.tex").is_file())
                self.assertTrue(any((bundle_dir / "lean").glob("*.lean")))
                (bundle_dir / "paper.pdf").write_bytes(b"%PDF-1.4\n% acceptance stub\n")
                return {"bundle_hash": "sha256:" + "1" * 64}

            verified = {
                "bundle_hash": "sha256:" + "1" * 64,
                "typeset_status": "typeset",
                "pdf_sha256": "sha256:" + "2" * 64,
            }
            available = ToolchainStatus(True, "pdflatex", "/pinned/pdflatex", "available")
            with mock.patch(
                "math_research.publication.production.toolchain_status", return_value=available
            ), mock.patch(
                "math_research.publication.production.typeset_bundle", side_effect=fake_typeset
            ), mock.patch(
                "math_research.publication.production.verify_bundle", return_value=verified
            ):
                result = produce_publication(self.manuscript, output, self.toolchain)
            self.assertEqual(result["typeset_status"], "typeset")
            for name in ("paper.tex", "paper.pdf", "MANIFEST.json", "build.json"):
                self.assertTrue((output / name).is_file(), name)

    def test_automatic_path_refuses_a_manuscript_without_probes(self) -> None:
        value = _fixture_value()
        value["render_probes"] = []
        available = ToolchainStatus(True, "pdflatex", "/pinned/pdflatex", "available")
        with tempfile.TemporaryDirectory() as directory, mock.patch(
            "math_research.publication.production.toolchain_status", return_value=available
        ):
            with self.assertRaises(PublicationValidationError) as caught:
                produce_publication(load_manuscript(value), Path(directory) / "bundle", self.toolchain)
        self.assertEqual(caught.exception.code, "publication_has_no_falsifiability_probe")

    def test_source_tree_has_no_alternative_pdf_renderer(self) -> None:
        forbidden = ("import reportlab", "from reportlab", "import weasyprint", "from weasyprint")
        for path in SRC_ROOT.rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            self.assertFalse(any(token in text for token in forbidden), path)


class ModulePurityTests(unittest.TestCase):
    """The projection is a function of the manuscript alone."""

    FORBIDDEN = frozenset({"os", "time", "random", "datetime", "socket", "subprocess", "secrets"})
    DRIVER_MODULES = frozenset({"typeset.py"})

    def _imports(self, path: Path) -> set[str]:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        names: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names.update(alias.name.split(".", 1)[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                names.add(node.module.split(".", 1)[0])
        return names

    def test_no_projection_module_reads_a_clock_randomness_or_the_environment(self) -> None:
        checked = 0
        for path in sorted(PUBLICATION_ROOT.glob("*.py")):
            if path.name in self.DRIVER_MODULES:
                continue
            checked += 1
            offenders = self._imports(path) & self.FORBIDDEN
            self.assertEqual(offenders, set(), f"{path.name} imports {sorted(offenders)}")
        self.assertGreaterEqual(checked, 8)

    def test_the_projection_imports_no_third_party_module(self) -> None:
        for path in sorted(PUBLICATION_ROOT.glob("*.py")):
            for name in self._imports(path):
                self.assertTrue(
                    name in sys.stdlib_module_names or name in {"math_research", ""},
                    f"{path.name} imports {name}",
                )

    def test_the_projection_depends_on_no_phase_module(self) -> None:
        for path in sorted(PUBLICATION_ROOT.glob("*.py")):
            text = path.read_text(encoding="utf-8")
            for phase in ("phase2", "phase3a", "phase3b", "phase4a", "phase4b", "phase4c", "phase5", "phase6"):
                self.assertNotIn(f"..{phase}", text, f"{path.name} imports {phase}")

    def test_the_evidence_classes_are_ordered_strongest_first(self) -> None:
        self.assertEqual(EVIDENCE_CLASSES[0], "kernel_checked_theorem")
        self.assertEqual(EVIDENCE_CLASSES[-1], "proposal")


# ---------------------------------------------------------------------------
# Schema 1.4.0: convention records, prior-art engagement, reading provenance.
#
# The field is ``title_stem`` (amendment B9): a noun phrase carrying no earned
# resolution verb. The renderer composes the displayed title from it plus a
# derived qualifier, so the lexicon rule here is what stops the stem from doing
# the qualifier's job.
# ---------------------------------------------------------------------------

G322_CLAIM = "cl.graffiti-322-counterexample"
FIXTURE_CLAIM = "cl.orthogonal-2d-optimum"
FIXTURE_PASSAGE = "psg.adr-0023.diagonal-reduction"
FIXTURE_CERT_HASH = "sha256:24cf1beb9917a21af6675bbf61c417e23195f2fd12d984b563791176af9e7d4b"
FIXTURE_EXCLUDED = (
    "cite.adr-0023.diagonal-reduction",
    "cite.adr-0033.cubic-boundary",
    "cite.adr-0035.verification-only",
)


def _reading(reading_id: str, passage_id: str, status: str, restricted: bool) -> Reading:
    return Reading(
        reading_id=reading_id,
        statement=f"Synthetic reading {reading_id} of the contested term.",
        source_passage_ref=passage_id, reading_status=status,
        attributed_to=None, publication_restricted=restricted,
    )


def _convention(
    *,
    statuses: tuple[str, str] = ("verbatim_confirmed", "verbatim_confirmed"),
    passages: tuple[str, str] = (FIXTURE_PASSAGE, FIXTURE_PASSAGE),
    restricted: tuple[bool, bool] = (False, False),
) -> ConventionRecord:
    """A two-reading convention over the fixture's own passages."""

    return ConventionRecord(
        convention_id="conv.synthetic-readings.v1",
        subject_ids=("problem.synthetic-target",),
        coupled_subject_ids=(),
        terms=(
            ContestedTerm(
                term_id="term_under_test", term="X",
                readings=(
                    _reading("reads_narrow", passages[0], statuses[0], restricted[0]),
                    _reading("reads_wide", passages[1], statuses[1], restricted[1]),
                ),
            ),
        ),
    ).finalized()


def _matrix(
    convention: ConventionRecord, *, claim_id: str = FIXTURE_CLAIM,
    verdicts: tuple[str, ...] = ("refutes", "refutes"),
    evidence_ref: str | None = FIXTURE_CERT_HASH,
    convention_hash: str | None = None,
) -> VerdictMatrix:
    tuples = convention.reading_tuples()
    return VerdictMatrix(
        matrix_id="vm.synthetic-readings.v1", claim_id=claim_id,
        convention_id=convention.convention_id,
        convention_hash=convention_hash or convention.content_hash,
        verdicts=tuple(
            ReadingVerdict(
                reading_tuple=reading_tuple, verdict=verdict,
                evidence_ref=None if verdict == "not_evaluated" else evidence_ref,
                detail=f"Synthetic verdict for {list(reading_tuple)}.",
            )
            for reading_tuple, verdict in zip(tuples, verdicts)
        ),
    ).finalized()


def _recheck(subject_id: str = "problem.synthetic-target") -> dict:
    return NoveltyRecheck(
        recheck_id="recheck.synthetic.engagement", checkpoint="before_research",
        subject_id=subject_id, subject_hash=_sha(b"synthetic subject"),
        next_action_id="run.synthetic.publication", performed_by="researcher.repository-owner",
        performed_at="2026-08-20T00:00:00Z", protocol_id="protocol.synthetic.prior-art",
        query_terms=("synthetic target",), searched_sources=("acquired local corpus",),
        equivalence_checks=("same statement under a renamed formulation",),
        evidence_refs=(("source.synthetic", _sha(b"synthetic evidence")),),
        outcome="inconclusive", prior_art_relationship="unresolved",
        prior_resolution="unresolved", prior_resolution_verification="unresolved",
        limitations=("A bounded search cannot establish the absence of prior art.",),
    ).finalized().payload()


def _attach(
    convention: ConventionRecord | None, matrix: VerdictMatrix | None, *,
    claim_id: str = FIXTURE_CLAIM, engagement: bool = True, reading_tag: bool = True,
    exclusions: tuple[str, ...] = FIXTURE_EXCLUDED,
) -> dict:
    """Fixture 1 with one claim made resolution-typed under a synthetic reading set."""

    value = _fixture_value()
    value["conventions"] = [convention.payload()] if convention else []
    value["verdict_matrices"] = [matrix.payload()] if matrix else []
    for citation in value["citations"]:
        if citation["citation_id"] in exclusions:
            citation["target_exclusion"] = {
                "reason": "cited_for_method_only", "excluded_by": "researcher.repository-owner",
            }
    for claim in value["claims"]:
        if claim["claim_id"] != claim_id:
            continue
        claim["resolution_target"] = {
            "subject_id": "problem.synthetic-target",
            "citation_id": claim["original_problem_citation_id"],
            "kind": "refutation",
        }
        claim["verdict_matrix_id"] = matrix.matrix_id if matrix else None
    if engagement:
        value["prior_art_engagement"] = {"recheck": _recheck()}
    if reading_tag:
        value["obligations"].append({
            "obligation_id": "obl.synthetic-unreproduced-reading",
            "statement": "Re-extract the passage behind the reads_narrow reading.",
            "status": "open",
            "reason": "The reading rests on text nobody outside the run re-extracted.",
            "tags": ["reading"],
        })
    return value


def _passages(value: dict) -> list[dict]:
    return [passage for source in value["sources"] for passage in source["passages"]]


def _refusal(test: unittest.TestCase, value: dict) -> str:
    with test.assertRaises(PublicationValidationError) as caught:
        load_manuscript(value)
    return caught.exception.code


class SchemaVersionTests(unittest.TestCase):
    def test_the_previous_schema_version_is_refused(self) -> None:
        value = _fixture_value()
        value["schema_version"] = "1.3.0"
        self.assertEqual("manuscript_schema_unsupported", _refusal(self, value))

    def test_the_new_record_ids_join_the_one_reference_namespace(self) -> None:
        manuscript = load_manuscript(GRAFFITI_322_PATH.read_bytes())
        for record_id in (
            "conv.graffiti-322-readings.v2", "vm.graffiti-322-g14-18.v1",
            "replay.graffiti-322.c4-candidate.v1", "recheck.graffiti-322.prior-candidate.v1",
            "recheck.graffiti-322.before-research.v1",
        ):
            self.assertIn(record_id, manuscript.record_ids)


class GraffitiRebuildFixtureTests(unittest.TestCase):
    """The rebuild of the shipped report is the slice's regression fixture."""

    def setUp(self) -> None:
        self.manuscript = load_manuscript(GRAFFITI_322_PATH.read_bytes())

    def test_the_rebuilt_report_is_convention_relative_and_source_asserted(self) -> None:
        self.assertEqual((G322_CLAIM,), self.manuscript.resolution_claim_ids())
        self.assertEqual("convention_relative", self.manuscript.derived_scope(G322_CLAIM))
        self.assertEqual("asserted", self.manuscript.weakest_reading_status_for(G322_CLAIM))
        self.assertIsNotNone(self.manuscript.prior_art_recheck())
        self.assertFalse(self.manuscript.every_reading_is_confirmed())

    def test_the_prior_candidate_is_engaged_and_the_definition_is_excluded(self) -> None:
        engagement = self.manuscript.target_engagement()
        self.assertEqual("addresses_target", engagement["cite.roucairol-cazenave.graffiti-322"])
        self.assertEqual("excluded_by_record", engagement["cite.wow.even-definition"])
        replay = self.manuscript.replays["replay.graffiti-322.c4-candidate.v1"]
        self.assertEqual("cite.roucairol-cazenave.graffiti-322", replay["citation_id"])

    def test_the_c4_replay_reproduces_the_external_review_finding(self) -> None:
        replay = self.manuscript.replays["replay.graffiti-322.c4-candidate.v1"]
        verdicts = {
            tuple(item["reading"]): (item["inverse_even"], item["range_value"], item["verdict"])
            for item in replay["readings"]
        }
        self.assertEqual(
            ("2", "3", "does_not_refute"),
            verdicts[("even_includes_v", "range_distinct_count")],
        )
        self.assertEqual(
            ("4", "3", "refutes"),
            verdicts[("even_excludes_v", "range_distinct_count")],
        )
        for reading in (("even_includes_v", "range_extent"), ("even_excludes_v", "range_extent")):
            self.assertEqual("does_not_refute", verdicts[reading][2])

    def test_every_rebuild_probe_flips(self) -> None:
        result = run_probes(self.manuscript)
        unflipped = [item for item in result["probes"] if not item["flipped"]]
        self.assertEqual(unflipped, [], f"{len(unflipped)} probes did not flip")
        self.assertGreaterEqual(result["probes_total"], 18)

    def test_the_shipped_headline_is_now_refused(self) -> None:
        value = _g322_value()
        value["title_stem"] = "An Exact Counterexample to Graffiti 322"
        self.assertEqual("title_stem_asserts_resolution", _refusal(self, value))
        value = _g322_value()
        value["abstract"] = (
            "We give an exact counterexample to the formulation of Graffiti 322."
        )
        self.assertEqual("abstract_overclaims_evidence", _refusal(self, value))


class ResolutionClaimGateTests(unittest.TestCase):
    def test_a_resolution_typed_claim_without_a_matrix_is_refused(self) -> None:
        convention = _convention()
        value = _attach(convention, _matrix(convention))
        for claim in value["claims"]:
            if claim["claim_id"] == FIXTURE_CLAIM:
                claim["verdict_matrix_id"] = None
        self.assertEqual("resolution_claim_without_verdict_matrix", _refusal(self, value))

    def test_a_malformed_resolution_target_is_one_named_refusal(self) -> None:
        convention = _convention()
        for mutation in (
            {"subject_id": "problem.x", "citation_id": "cite.adr-0023.original-problem"},
            {"subject_id": "problem.x", "citation_id": "cite.adr-0023.original-problem",
             "kind": "clarification"},
            {"subject_id": "", "citation_id": "cite.adr-0023.original-problem",
             "kind": "refutation"},
            "refutation",
        ):
            value = _attach(convention, _matrix(convention))
            for claim in value["claims"]:
                if claim["claim_id"] == FIXTURE_CLAIM:
                    claim["resolution_target"] = mutation
            self.assertEqual("resolution_target_malformed", _refusal(self, value), mutation)

    def test_a_matrix_naming_another_claim_is_refused(self) -> None:
        convention = _convention()
        matrix = _matrix(convention, claim_id="cl.scalar-iterate-separation")
        value = _attach(convention, matrix)
        self.assertEqual("verdict_matrix_claim_mismatch", _refusal(self, value))

    def test_a_matrix_naming_no_claim_at_all_is_refused(self) -> None:
        convention = _convention()
        matrix = _matrix(convention, claim_id="cl.does-not-exist")
        value = _attach(convention, matrix)
        self.assertEqual("record_ref_unresolved", _refusal(self, value))

    def test_every_derived_scope_is_recomputed_from_the_verdicts(self) -> None:
        convention = _convention()
        for verdicts, scope in (
            (("refutes", "refutes"), "unconditional"),
            (("refutes", "does_not_refute"), "convention_relative"),
            (("refutes", "not_evaluated"), "contested_unevaluated"),
            (("does_not_refute", "does_not_refute"), "no_reading_refutes"),
        ):
            value = _attach(convention, _matrix(convention, verdicts=verdicts))
            manuscript = load_manuscript(value)
            self.assertEqual(scope, manuscript.derived_scope(FIXTURE_CLAIM), verdicts)

    def test_a_partial_matrix_does_not_read_as_full_coverage(self) -> None:
        """The coverage rule is checked before the record's own content hash.

        Every single-field mutation of a content-hashed record also breaks its
        hash. Verifying the hash first would collapse every semantic rule in the
        record onto one bookkeeping code and leave the coverage rule with no
        reachable falsification, so coverage is judged on the payload as supplied.
        """

        convention = _convention()
        matrix = _matrix(convention)
        payload = matrix.payload()
        payload["verdicts"] = payload["verdicts"][:1]
        value = _attach(convention, matrix)
        value["verdict_matrices"] = [payload]
        self.assertEqual("verdict_matrix_incomplete", _refusal(self, value))

    def test_a_matrix_bound_to_the_wrong_reading_set_is_refused(self) -> None:
        convention = _convention()
        matrix = _matrix(convention, convention_hash=_sha(b"a different reading set"))
        value = _attach(convention, matrix)
        self.assertEqual("convention_hash_mismatch", _refusal(self, value))

    def test_a_convention_record_the_manuscript_does_not_carry_is_refused(self) -> None:
        convention = _convention()
        value = _attach(None, _matrix(convention))
        self.assertEqual("record_ref_unresolved", _refusal(self, value))

    def test_a_malformed_convention_record_is_refused_by_class(self) -> None:
        convention = _convention()
        payload = convention.payload()
        payload["terms"][0]["readings"] = payload["terms"][0]["readings"][:1]
        value = _attach(convention, _matrix(convention))
        value["conventions"] = [payload]
        self.assertEqual("convention_record_invalid", _refusal(self, value))


class ReadingProvenanceClosureTests(unittest.TestCase):
    """A reading resolves to a passage, and never out-claims it."""

    def test_a_reading_drawn_from_no_passage_is_refused(self) -> None:
        convention = _convention(passages=("psg.does-not-exist", FIXTURE_PASSAGE))
        value = _attach(convention, _matrix(convention))
        self.assertEqual("reading_passage_unresolved", _refusal(self, value))

    def test_a_reading_cannot_be_better_attested_than_its_passage(self) -> None:
        convention = _convention(statuses=("verbatim_confirmed", "verbatim_confirmed"))
        value = _attach(convention, _matrix(convention))
        for passage in _passages(value):
            if passage["passage_id"] == FIXTURE_PASSAGE:
                passage["extraction_method"] = "unextractable"
                passage["reading_status"] = "asserted"
                passage.pop("verbatim_text")
                passage["verbatim_hash"] = None
        self.assertEqual("reading_status_exceeds_passage", _refusal(self, value))

    def test_a_transcribed_reading_of_an_asserted_passage_is_refused(self) -> None:
        convention = _convention(statuses=("transcribed", "transcribed"))
        value = _attach(convention, _matrix(convention))
        for passage in _passages(value):
            if passage["passage_id"] == FIXTURE_PASSAGE:
                passage["extraction_method"] = "ocr"
                passage["reading_status"] = "asserted"
                passage.pop("verbatim_text")
                passage["verbatim_hash"] = None
        self.assertEqual("reading_status_exceeds_passage", _refusal(self, value))

    def test_an_unquotable_passage_cannot_support_a_confirmed_reading(self) -> None:
        """Amendment A5. The record keeps the reading; the reader cannot see it."""

        convention = _convention(statuses=("verbatim_confirmed", "verbatim_confirmed"))
        value = _attach(convention, _matrix(convention))
        for passage in _passages(value):
            if passage["passage_id"] == FIXTURE_PASSAGE:
                passage["quotation_permitted"] = False
                passage["publication_restricted"] = True
        self.assertEqual("reading_status_exceeds_passage", _refusal(self, value))
        # The same passage supports a reading that declares the same restriction.
        convention = _convention(
            statuses=("verbatim_confirmed", "verbatim_confirmed"), restricted=(True, True)
        )
        value = _attach(convention, _matrix(convention))
        for passage in _passages(value):
            if passage["passage_id"] == FIXTURE_PASSAGE:
                passage["quotation_permitted"] = False
                passage["publication_restricted"] = True
        manuscript = load_manuscript(value)
        self.assertEqual("asserted", manuscript.weakest_reading_status_for(FIXTURE_CLAIM))

    def test_an_asserted_reading_forces_an_open_reading_obligation(self) -> None:
        convention = _convention(statuses=("asserted", "asserted"))
        value = _attach(convention, _matrix(convention), reading_tag=False)
        for passage in _passages(value):
            if passage["passage_id"] == FIXTURE_PASSAGE:
                passage["extraction_method"] = "unextractable"
                passage["reading_status"] = "asserted"
                passage.pop("verbatim_text")
                passage["verbatim_hash"] = None
        self.assertEqual("asserted_reading_without_obligation", _refusal(self, value))

    def test_a_verdict_may_not_cite_evidence_that_does_not_exist(self) -> None:
        convention = _convention()
        matrix = _matrix(convention, evidence_ref="sha256:" + "0" * 64)
        value = _attach(convention, matrix)
        self.assertEqual("verdict_evidence_ref_unresolved", _refusal(self, value))
        matrix = _matrix(convention, evidence_ref="replay.absent.v1")
        value = _attach(convention, matrix)
        self.assertEqual("verdict_evidence_ref_unresolved", _refusal(self, value))

    def test_a_verdict_may_cite_a_certificate_or_a_replay_this_manuscript_carries(self) -> None:
        convention = _convention()
        value = _attach(convention, _matrix(convention, evidence_ref=FIXTURE_CERT_HASH))
        self.assertEqual("unconditional", load_manuscript(value).derived_scope(FIXTURE_CLAIM))
        replay = _g322_value()["counter_candidate_replays"][0]
        replay["citation_id"] = None
        for evidence_ref in (replay["replay_id"], replay["result_hash"]):
            value = _attach(convention, _matrix(convention, evidence_ref=evidence_ref))
            value["counter_candidate_replays"] = [replay]
            self.assertEqual("unconditional", load_manuscript(value).derived_scope(FIXTURE_CLAIM))


class PassageReadingRecordTests(unittest.TestCase):
    """ADR-0060: what bytes we hold and how well we read them are two axes."""

    def _mutate(self, **changes: object) -> dict:
        value = _fixture_value()
        for passage in _passages(value):
            if passage["passage_id"] == FIXTURE_PASSAGE:
                for key, item in changes.items():
                    if item is _DELETE:
                        passage.pop(key, None)
                    else:
                        passage[key] = item
        return value

    def test_a_passage_without_a_recorded_reading_is_refused(self) -> None:
        for field in ("reading_status", "extraction_method"):
            self.assertEqual(
                "passage_reading_unrecorded", _refusal(self, self._mutate(**{field: _DELETE}))
            )

    def test_a_non_asserted_passage_must_carry_its_text(self) -> None:
        self.assertEqual(
            "passage_verbatim_missing", _refusal(self, self._mutate(verbatim_text=_DELETE))
        )
        self.assertEqual(
            "passage_verbatim_missing", _refusal(self, self._mutate(verbatim_text=""))
        )

    def test_one_changed_character_breaks_the_verbatim_hash(self) -> None:
        value = _fixture_value()
        for passage in _passages(value):
            if passage["passage_id"] == FIXTURE_PASSAGE:
                passage["verbatim_text"] = passage["verbatim_text"] + "."
        self.assertEqual("passage_verbatim_hash_mismatch", _refusal(self, value))

    def test_an_asserted_passage_carries_neither_text_nor_a_text_hash(self) -> None:
        self.assertEqual(
            "passage_asserted_carries_text",
            _refusal(self, self._mutate(extraction_method="ocr", reading_status="asserted")),
        )
        self.assertEqual(
            "passage_verbatim_hash_mismatch",
            _refusal(self, self._mutate(
                extraction_method="unextractable", reading_status="asserted",
                verbatim_text=_DELETE,
            )),
        )

    def test_the_method_and_status_matrix_is_enforced_in_both_directions(self) -> None:
        """Amendment A8 as corrected by amendment B2, exhaustively.

        ``manual_transcription`` admits ``transcribed`` or ``asserted`` and never
        ``verbatim_confirmed``: a hand transcription cannot be re-derived from the
        file, so calling it byte-confirmed overclaims the one distinction ADR-0060
        exists to draw. Only ``text_layer`` admits every status.
        """

        admitted = {
            "unextractable": {"asserted"},
            "ocr": {"transcribed", "asserted"},
            "text_layer": {"verbatim_confirmed", "transcribed", "asserted"},
            "manual_transcription": {"transcribed", "asserted"},
        }
        for method, statuses in sorted(admitted.items()):
            for status in ("verbatim_confirmed", "transcribed", "asserted"):
                changes: dict[str, object] = {
                    "extraction_method": method, "reading_status": status,
                }
                if status == "asserted":
                    changes["verbatim_text"] = _DELETE
                    changes["verbatim_hash"] = None
                value = self._mutate(**changes)
                if status in statuses:
                    load_manuscript(value)
                    continue
                self.assertEqual(
                    "passage_extraction_inconsistent", _refusal(self, value), (method, status)
                )

    def test_published_text_the_rights_forbid_quoting_is_refused(self) -> None:
        self.assertEqual(
            "passage_verbatim_rights_conflict",
            _refusal(self, self._mutate(quotation_permitted=False, publication_restricted=False)),
        )
        # The coherent restricted case is retained rather than refused, and it
        # reads as asserted for the reader.
        value = self._mutate(quotation_permitted=False, publication_restricted=True)
        manuscript = load_manuscript(value)
        passage = next(
            item for item in _passages(dict(manuscript.value))
            if item["passage_id"] == FIXTURE_PASSAGE
        )
        self.assertEqual("asserted", passage_effective_reading_status(passage))

    def test_an_unknown_method_or_status_is_refused_rather_than_defaulted(self) -> None:
        self.assertEqual(
            "passage_extraction_method_unknown",
            _refusal(self, self._mutate(extraction_method="guess")),
        )
        self.assertEqual(
            "passage_reading_status_unknown",
            _refusal(self, self._mutate(reading_status="probably")),
        )

    def test_the_fixture_reading_is_the_repository_text_it_claims(self) -> None:
        manuscript = load_manuscript(MANUSCRIPT_PATH.read_bytes())
        for source in manuscript.sources.values():
            path = REPO_ROOT / str(source["bibliographic"]["identifier"])
            lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
            for passage in source["passages"]:
                start, end = (int(part.lstrip("L")) for part in str(passage["anchor"]).split("-"))
                extracted = "".join(lines[start - 1:end])
                self.assertEqual(extracted, passage["verbatim_text"], passage["passage_id"])
                self.assertEqual(
                    _sha(extracted.encode("utf-8")), passage["verbatim_hash"],
                    passage["passage_id"],
                )


class TargetEngagementTests(unittest.TestCase):
    """Amendment A1: engagement is derived and fails closed."""

    def test_silence_leaves_a_cited_work_addressing_the_target(self) -> None:
        convention = _convention()
        value = _attach(convention, _matrix(convention), exclusions=FIXTURE_EXCLUDED[1:])
        self.assertEqual(
            "resolution_claim_without_prior_art_engagement", _refusal(self, value)
        )

    def test_an_unjustified_exclusion_excludes_nothing(self) -> None:
        for exclusion in (
            {"reason": "not_applicable", "excluded_by": "researcher.repository-owner"},
            {"reason": "", "excluded_by": "researcher.repository-owner"},
            {"reason": "cited_for_method_only"},
            {"reason": "cited_for_method_only", "excluded_by": ""},
            {"reason": "cited_for_method_only", "excluded_by": "researcher.repository-owner",
             "note": "extra"},
            "cited_for_method_only",
        ):
            value = _fixture_value()
            for citation in value["citations"]:
                if citation["citation_id"] == FIXTURE_EXCLUDED[0]:
                    citation["target_exclusion"] = exclusion
            self.assertEqual("target_exclusion_unjustified", _refusal(self, value), exclusion)

    def test_a_prior_resolution_candidate_can_never_be_excluded(self) -> None:
        value = _g322_value()
        for citation in value["citations"]:
            if citation["citation_id"] == "cite.roucairol-cazenave.graffiti-322":
                citation["target_exclusion"] = {
                    "reason": "different_conjecture",
                    "excluded_by": "researcher.repository-owner",
                }
        self.assertEqual("prior_candidate_cannot_be_excluded", _refusal(self, value))

    def test_a_prior_candidate_needs_a_replay_naming_its_citation(self) -> None:
        value = _g322_value()
        value["counter_candidate_replays"] = [
            item for item in value["counter_candidate_replays"]
            if item["citation_id"] is None
        ]
        for section in value["sections"]:
            for block in section["blocks"]:
                block["record_refs"] = [
                    ref for ref in block["record_refs"]
                    if ref != "replay.graffiti-322.c4-candidate.v1"
                ]
        self.assertEqual(
            "resolution_claim_without_prior_art_engagement", _refusal(self, value)
        )

    def test_the_engagement_gate_is_silent_without_a_resolution_typed_claim(self) -> None:
        value = _fixture_value()
        value["citations"] = [dict(item) for item in value["citations"]]
        load_manuscript(value)


class CounterCandidateReplayRecordTests(unittest.TestCase):
    def _replay_value(self, **changes: object) -> dict:
        value = _g322_value()
        for replay in value["counter_candidate_replays"]:
            if replay["replay_id"] == "replay.graffiti-322.c4-candidate.v1":
                for key, item in changes.items():
                    if item is _DELETE:
                        replay.pop(key, None)
                    else:
                        replay[key] = item
        return value

    def test_a_floating_point_replay_is_refused_outright(self) -> None:
        self.assertEqual(
            "replay_used_floating_point", _refusal(self, self._replay_value(float_used=True))
        )

    def test_an_inexact_reading_value_is_refused(self) -> None:
        value = _g322_value()
        for replay in value["counter_candidate_replays"]:
            for reading in replay["readings"]:
                reading["inverse_even"] = "9.0119"
        self.assertEqual("replay_value_not_exact", _refusal(self, value))
        value = _g322_value()
        for replay in value["counter_candidate_replays"]:
            for reading in replay["readings"]:
                reading["range_value"] = "about 9"
        self.assertEqual("replay_value_not_exact", _refusal(self, value))

    def test_a_replay_of_an_unknown_schema_or_engine_shape_is_refused(self) -> None:
        self.assertEqual(
            "counter_candidate_replay_invalid",
            _refusal(self, self._replay_value(schema_version="adaivy.something-else.v1")),
        )
        self.assertEqual(
            "counter_candidate_replay_invalid",
            _refusal(self, self._replay_value(creates_mathematical_warrant=True)),
        )
        self.assertEqual(
            "counter_candidate_replay_invalid",
            _refusal(self, self._replay_value(arithmetic="float64")),
        )
        self.assertEqual(
            "manuscript_field_set_mismatch", _refusal(self, self._replay_value(citation_id=_DELETE))
        )

    def test_a_duplicated_replay_identifier_is_refused(self) -> None:
        value = _g322_value()
        value["counter_candidate_replays"].append(
            dict(value["counter_candidate_replays"][0])
        )
        self.assertEqual("identifier_not_unique", _refusal(self, value))


class PriorArtEngagementRecordTests(unittest.TestCase):
    def test_a_recheck_can_be_carried_without_any_approval(self) -> None:
        manuscript = load_manuscript(GRAFFITI_322_PATH.read_bytes())
        self.assertIsNone(manuscript.value["publication_approval"])
        recheck = manuscript.prior_art_recheck()
        self.assertIsNotNone(recheck)
        self.assertEqual("before_announcement", recheck.checkpoint)
        self.assertEqual(
            "prior_art_relationship_unresolved", recheck.classification().report_classification
        )
        self.assertIn("recheck.graffiti-322.before-research.v1", manuscript.rechecks)

    def test_the_engagement_recheck_is_bound_to_this_manuscript_subject(self) -> None:
        """Amendment A4's subject binding is already satisfiable at load time."""

        manuscript = load_manuscript(GRAFFITI_322_PATH.read_bytes())
        recheck = manuscript.prior_art_recheck()
        self.assertEqual(manuscript.manuscript_id, recheck.subject_id)
        self.assertEqual(_announcement_subject_hash(manuscript), recheck.subject_hash)

    def test_a_malformed_engagement_record_is_refused(self) -> None:
        value = _g322_value()
        value["prior_art_engagement"]["recheck"]["performer_kind"] = "model"
        self.assertEqual("prior_art_engagement_invalid", _refusal(self, value))
        value = _g322_value()
        value["prior_art_engagement"] = {"recheck": _recheck(), "note": "extra"}
        self.assertEqual("manuscript_field_set_mismatch", _refusal(self, value))
        value = _g322_value()
        value["novelty_rechecks"][0]["outcome"] = "novel"
        self.assertEqual("novelty_recheck_invalid", _refusal(self, value))


class ProseSearchAssertionTests(unittest.TestCase):
    def test_an_asserted_search_with_no_recheck_record_is_refused(self) -> None:
        value = _fixture_value()
        value["sections"][0]["blocks"].append({
            "block_id": "blk.scope.literature",
            "kind": "prose",
            "record_refs": ["obl.jrf-general-convergence"],
            "runs": [{
                "t": "text",
                "v": (
                    "A pre-research review of the surrounding literature found no earlier "
                    "statement of this boundary."
                ),
            }],
            "citations": [],
        })
        self.assertEqual("prose_asserts_unrecorded_search", _refusal(self, value))

    def test_the_same_prose_is_admitted_once_a_recheck_record_backs_it(self) -> None:
        value = _fixture_value()
        recheck = _recheck()
        value["novelty_rechecks"] = [recheck]
        value["sections"][0]["blocks"].append({
            "block_id": "blk.scope.literature",
            "kind": "prose",
            "record_refs": [recheck["recheck_id"]],
            "runs": [{
                "t": "text",
                "v": (
                    "A bounded prior art search over the acquired corpus returned an "
                    "inconclusive outcome."
                ),
            }],
            "citations": [],
        })
        load_manuscript(value)


class HeadlineLexiconTests(unittest.TestCase):
    def test_resolution_language_is_refused_while_the_records_do_not_earn_it(self) -> None:
        for key, code in (
            ("title_stem", "title_stem_asserts_resolution"),
            ("abstract", "abstract_overclaims_evidence"),
        ):
            for phrase in ("counterexample", "Refutation", "settles", "proof of"):
                value = _fixture_value()
                value[key] = f"A {phrase} for the QD-FS-01 diagonal benchmark"
                self.assertEqual(code, _refusal(self, value), (key, phrase))

    def test_the_records_can_earn_resolution_language(self) -> None:
        convention = _convention()
        value = _attach(convention, _matrix(convention, verdicts=("refutes", "refutes")))
        for obligation in value["obligations"]:
            if obligation["obligation_id"] == "obl.jrf-general-convergence":
                obligation["tags"] = []
        value["title_stem"] = "An exact counterexample for the QD-FS-01 diagonal benchmark"
        manuscript = load_manuscript(value)
        self.assertEqual("unconditional", manuscript.derived_scope(FIXTURE_CLAIM))
        self.assertEqual((), manuscript.unearned_resolution_reasons())

    def test_an_open_novelty_obligation_alone_withdraws_the_language(self) -> None:
        convention = _convention()
        value = _attach(convention, _matrix(convention, verdicts=("refutes", "refutes")))
        value["title_stem"] = "An exact counterexample for the QD-FS-01 diagonal benchmark"
        self.assertEqual("title_stem_asserts_resolution", _refusal(self, value))

    def test_source_fidelity_is_its_own_refusal_computed_from_reading_statuses(self) -> None:
        """Amendment A2. One code per rule; the author is told which they broke."""

        value = _fixture_value()
        value["abstract"] = "A source-faithful reading of the QD-FS-01 benchmark is recorded."
        self.assertEqual("source_fidelity_overclaimed", _refusal(self, value))
        convention = _convention(statuses=("asserted", "asserted"))
        attached = _attach(convention, _matrix(convention))
        for passage in _passages(attached):
            if passage["passage_id"] == FIXTURE_PASSAGE:
                passage["extraction_method"] = "unextractable"
                passage["reading_status"] = "asserted"
                passage.pop("verbatim_text")
                passage["verbatim_hash"] = None
        attached["abstract"] = "A source-faithful reading of the QD-FS-01 benchmark is recorded."
        self.assertEqual("source_fidelity_overclaimed", _refusal(self, attached))
        # Confirmed readings earn the phrase; nothing else does.
        earned = _attach(_convention(), _matrix(_convention()))
        earned["abstract"] = "A source-faithful reading of the QD-FS-01 benchmark is recorded."
        self.assertTrue(load_manuscript(earned).every_reading_is_confirmed())


class ObligationTagTests(unittest.TestCase):
    def test_an_unknown_tag_is_refused_rather_than_ignored(self) -> None:
        value = _fixture_value()
        value["obligations"][0]["tags"] = ["novel"]
        self.assertEqual("obligation_tag_unknown", _refusal(self, value))

    def test_a_duplicated_tag_is_refused(self) -> None:
        value = _fixture_value()
        value["obligations"][0]["tags"] = ["novelty", "novelty"]
        self.assertEqual("tag_duplicated", _refusal(self, value))

    def test_open_tags_are_read_from_the_records(self) -> None:
        manuscript = load_manuscript(GRAFFITI_322_PATH.read_bytes())
        self.assertEqual(
            frozenset({"reading", "prior_art", "novelty", "human_review", "formalization"}),
            manuscript.open_obligation_tags(),
        )


class NoPromotionByNewFieldTests(unittest.TestCase):
    """No 1.4.0 field may make a claim or a headline stronger."""

    def test_no_single_field_mutation_of_the_rebuild_promotes_a_claim(self) -> None:
        manuscript = load_manuscript(GRAFFITI_322_PATH.read_bytes())
        baseline = {
            item.claim_id: item.evidence_class
            for item in render_manuscript(manuscript).classifications
        }
        candidates = (
            True, False, None, "unconditional", "refutes", "verbatim_confirmed",
            "addresses_target", "kernel_checked", [], {},
        )
        for claim in manuscript.value["claims"]:
            for field in ("resolution_target", "verdict_matrix_id"):
                for candidate in candidates:
                    value = _g322_value()
                    for item in value["claims"]:
                        if item["claim_id"] == claim["claim_id"]:
                            item[field] = candidate
                    try:
                        document = render_manuscript(load_manuscript(value))
                    except PublicationValidationError:
                        continue
                    for item in document.classifications:
                        self.assertGreaterEqual(
                            EVIDENCE_CLASSES.index(item.evidence_class),
                            EVIDENCE_CLASSES.index(baseline[item.claim_id]),
                            f"{field}={candidate!r} promoted {item.claim_id}",
                        )


if __name__ == "__main__":
    unittest.main()


# ---------------------------------------------------------------------------
# ADR-0058 section 5: the consumers. Evidence-class cap, derived headline,
# derived tables, and the production gates that used to hang off an approval.
# ---------------------------------------------------------------------------

G322_EXPECTED_TITLE = (
    "Inverse Even and the distance spectrum of the triangle-free family G(r,t): "
    "Candidate Counterexample to Graffiti 322 (convention-relative; prior art "
    "relationship unresolved; open novelty and prior-art obligations)"
)


def _earned(**overrides: object) -> dict:
    """Fixture 1 with every headline input at its strongest.

    This is the only shape that loses the qualifier: an unconditional sweep of
    the enumerated readings, a recorded bounded search that found nothing, and no
    open obligation tagged novelty or prior_art.
    """

    convention = _convention()
    value = _attach(convention, _matrix(convention, verdicts=("refutes", "refutes")))
    for obligation in value["obligations"]:
        obligation["tags"] = []
    recheck = NoveltyRecheck(
        recheck_id="recheck.synthetic.clean", checkpoint="before_research",
        subject_id="problem.synthetic-target", subject_hash=_sha(b"synthetic subject"),
        next_action_id="run.synthetic.publication", performed_by="researcher.repository-owner",
        performed_at="2026-08-20T00:00:00Z", protocol_id="protocol.synthetic.prior-art",
        query_terms=("synthetic target",), searched_sources=("acquired local corpus",),
        equivalence_checks=("same statement under a renamed formulation",),
        evidence_refs=(("source.synthetic", _sha(b"synthetic evidence")),),
        outcome="not_found_under_protocol", prior_art_relationship="not_applicable",
        prior_resolution="not_applicable", prior_resolution_verification="not_applicable",
        limitations=("A bounded search cannot establish the absence of prior art.",),
    ).finalized().payload()
    value["prior_art_engagement"] = {"recheck": recheck}
    value.update(overrides)
    return value


def _without_engagement() -> dict:
    """The rebuild with its prior-art record removed, references and all.

    Dropping the record alone is refused by reference closure, which is the
    correct behaviour and not what this shape is testing: the point is what the
    headline does when no classification exists anywhere.
    """

    value = _g322_value()
    value["prior_art_engagement"] = None
    removed = "recheck.graffiti-322.prior-candidate.v1"
    for section in value["sections"]:
        for block in section["blocks"]:
            if "record_refs" in block:
                block["record_refs"] = [
                    ref for ref in block["record_refs"] if ref != removed
                ]
    value["render_probes"] = [
        probe for probe in value["render_probes"]
        if probe["field"] != "prior_art_engagement.recheck"
    ]
    return value


def _earned_theorem() -> dict:
    """The synthetic ladder, made resolution-typed with every input at its best.

    This shape exists to prove the unhedged headline is reachable at all. A hedge
    that no record set can remove is a constant, and a constant proves nothing.
    """

    value = _synthetic_manuscript("kernel_checked", unapproved=[], representation="verified")
    passage = "psg.synthetic-original-problem"
    convention = ConventionRecord(
        convention_id="conv.synthetic-earned.v1",
        subject_ids=("problem.synthetic-target",),
        coupled_subject_ids=(),
        terms=(
            ContestedTerm(
                term_id="term_under_test", term="X",
                readings=(
                    _reading("reads_narrow", passage, "verbatim_confirmed", False),
                    _reading("reads_wide", passage, "verbatim_confirmed", False),
                ),
            ),
        ),
    ).finalized()
    # A refuting verdict must cite evidence that exists, so the sweep is backed
    # by the rebuild's own-witness replay (``citation_id`` null: our witness,
    # which discharges no engagement obligation).
    replay = _g322_value()["counter_candidate_replays"][1]
    assert replay["citation_id"] is None
    matrix = VerdictMatrix(
        matrix_id="vm.synthetic-earned.v1", claim_id="cl.synthetic",
        convention_id=convention.convention_id, convention_hash=convention.content_hash,
        verdicts=tuple(
            ReadingVerdict(
                reading_tuple=reading_tuple, verdict="refutes",
                evidence_ref=replay["result_hash"],
                detail=f"Synthetic sweep for {list(reading_tuple)}.",
            )
            for reading_tuple in convention.reading_tuples()
        ),
    ).finalized()
    value["counter_candidate_replays"] = [replay]
    value["conventions"] = [convention.payload()]
    value["verdict_matrices"] = [matrix.payload()]
    value["claims"][0]["resolution_target"] = {
        "subject_id": "problem.synthetic-target",
        "citation_id": "cite.synthetic-original-problem",
        "kind": "refutation",
    }
    value["claims"][0]["verdict_matrix_id"] = matrix.matrix_id
    value["prior_art_engagement"] = _earned()["prior_art_engagement"]
    return value


class ConventionScopeCapTests(unittest.TestCase):
    """The scope cap is a second demotion axis, and it only ever demotes."""

    def test_the_new_class_is_inserted_between_the_two_it_separates(self) -> None:
        self.assertEqual(
            (
                "kernel_checked_theorem", "exact_certificate_proposition",
                "convention_relative_proposition", "proposal",
            ),
            EVIDENCE_CLASSES,
        )
        self.assertEqual("adaconditional", ENVIRONMENTS["convention_relative_proposition"])
        self.assertEqual(
            "Proposition (convention-relative)", HEADINGS["convention_relative_proposition"]
        )
        self.assertIn(
            r"\newtheorem{adaconditional}[adatheorem]{Proposition (convention-relative)}",
            TEMPLATE_HEAD,
        )

    def test_each_derived_scope_caps_the_class_it_names(self) -> None:
        convention = _convention()
        for verdicts, scope, expected in (
            (("refutes", "refutes"), "unconditional", "exact_certificate_proposition"),
            (
                ("refutes", "does_not_refute"), "convention_relative",
                "convention_relative_proposition",
            ),
            (("refutes", "not_evaluated"), "contested_unevaluated", "proposal"),
            (("does_not_refute", "does_not_refute"), "no_reading_refutes", "proposal"),
        ):
            value = _attach(convention, _matrix(convention, verdicts=verdicts))
            manuscript = load_manuscript(value)
            self.assertEqual(scope, manuscript.derived_scope(FIXTURE_CLAIM), verdicts)
            self.assertEqual(
                expected, classify_claim(manuscript, FIXTURE_CLAIM).evidence_class, verdicts
            )

    def test_the_cap_cannot_be_shed_by_dropping_the_resolution_target(self) -> None:
        """A claim keeps the cap of the matrix it names, target or no target."""

        convention = _convention()
        value = _attach(convention, _matrix(convention, verdicts=("refutes", "does_not_refute")))
        for claim in value["claims"]:
            if claim["claim_id"] == FIXTURE_CLAIM:
                claim["resolution_target"] = None
        manuscript = load_manuscript(value)
        self.assertEqual((), manuscript.resolution_claim_ids())
        self.assertEqual(
            "convention_relative_proposition",
            classify_claim(manuscript, FIXTURE_CLAIM).evidence_class,
        )

    def test_the_cap_never_promotes_a_weaker_claim(self) -> None:
        convention = _convention()
        value = _attach(convention, _matrix(convention, verdicts=("refutes", "refutes")))
        for certificate in value["certificates"]:
            if certificate["certificate_id"] == "cert.orthogonal-2d-optimum":
                certificate["gap"] = "1/4"
        manuscript = load_manuscript(value)
        self.assertEqual("unconditional", manuscript.derived_scope(FIXTURE_CLAIM))
        self.assertEqual(
            "proposal", classify_claim(manuscript, FIXTURE_CLAIM).evidence_class
        )

    def test_the_rebuilt_report_renders_in_the_conditional_environment(self) -> None:
        manuscript = load_manuscript(GRAFFITI_322_PATH.read_bytes())
        classification = classify_claim(manuscript, G322_CLAIM)
        self.assertEqual("convention_relative_proposition", classification.evidence_class)
        self.assertEqual("adaconditional", classification.environment)
        for record_id in ("vm.graffiti-322-g14-18.v1", "conv.graffiti-322-readings.v2"):
            self.assertIn(record_id, classification.record_refs)
        document = render_manuscript(manuscript)
        self.assertIn(r"\begin{adaconditional}", document.tex)
        self.assertNotIn(r"\begin{adaproposition}", document.tex)
        self.assertEqual(
            1, document.statistics["evidence_class_counts"]["convention_relative_proposition"]
        )


class DerivedHeadlineTests(unittest.TestCase):
    """The displayed title is computed, and no manuscript field can compose it."""

    def test_the_rebuild_composes_the_qualified_title(self) -> None:
        document = render_manuscript(load_manuscript(GRAFFITI_322_PATH.read_bytes()))
        self.assertEqual(G322_EXPECTED_TITLE, document.headline.displayed_title)
        self.assertEqual(
            (
                "convention-relative", "prior art relationship unresolved",
                "open novelty and prior-art obligations",
            ),
            document.headline.qualifiers,
        )
        self.assertIn(escape_prose(G322_EXPECTED_TITLE, "title"), document.tex)

    def test_a_manuscript_that_resolves_nothing_carries_no_qualifier(self) -> None:
        document = render_manuscript(load_manuscript(MANUSCRIPT_PATH.read_bytes()))
        self.assertEqual((), document.headline.qualifiers)
        self.assertEqual(document.headline.title_stem, document.headline.displayed_title)
        self.assertEqual("", document.headline.resolution_phrase)

    def test_records_that_clear_every_qualifier_still_hedge_below_a_theorem(self) -> None:
        """The two derived labels must not disagree with each other.

        An exact certificate renders as a Proposition, so the headline says
        "Candidate". Defect 3 was a headline that out-claimed its own body; the
        hedge is what keeps the composed title and the environment name in step.
        """

        document = render_manuscript(load_manuscript(_earned()))
        self.assertEqual((), document.headline.qualifiers)
        self.assertEqual(
            "Candidate Counterexample to Synthetic Target",
            document.headline.resolution_phrase,
        )
        self.assertEqual(
            "exact_certificate_proposition", document.classifications[0].evidence_class
        )

    def test_a_kernel_checked_theorem_earns_the_unhedged_headline(self) -> None:
        document = render_manuscript(load_manuscript(_earned_theorem()))
        self.assertEqual((), document.headline.qualifiers)
        self.assertEqual(
            "Counterexample to Synthetic Target", document.headline.resolution_phrase
        )
        self.assertNotIn("Candidate", document.headline.displayed_title)
        self.assertEqual(
            "Synthetic attestation ladder: Counterexample to Synthetic Target",
            document.headline.displayed_title,
        )

    def test_the_qualifier_is_empty_exactly_when_the_records_earn_it(self) -> None:
        """The biconditional the composition rests on, checked in both directions."""

        convention = _convention()
        for verdicts in (
            ("refutes", "refutes"), ("refutes", "does_not_refute"),
            ("refutes", "not_evaluated"), ("does_not_refute", "does_not_refute"),
        ):
            for engagement in (True, False):
                for tagged in (True, False):
                    value = _earned() if engagement else _attach(
                        convention, _matrix(convention, verdicts=verdicts), engagement=False
                    )
                    if engagement:
                        matrix = _matrix(convention, verdicts=verdicts)
                        value["verdict_matrices"] = [matrix.payload()]
                    if tagged:
                        value["obligations"].append({
                            "obligation_id": "obl.synthetic-open-novelty",
                            "statement": "Classify this result against the prior candidate.",
                            "status": "open",
                            "reason": "Priority is undecided.",
                            "tags": ["novelty"],
                        })
                    manuscript = load_manuscript(value)
                    headline = render_manuscript(manuscript).headline
                    self.assertEqual(
                        bool(manuscript.unearned_resolution_reasons()),
                        bool(headline.qualifiers),
                        (verdicts, engagement, tagged, headline.qualifiers),
                    )

    def test_a_subject_identifier_may_not_smuggle_resolution_into_the_title(self) -> None:
        value = _g322_value()
        for claim in value["claims"]:
            if claim["claim_id"] == G322_CLAIM:
                claim["resolution_target"] = {
                    "subject_id": "problem.refutation-of-graffiti-322",
                    "citation_id": "cite.wow.graffiti-322",
                    "kind": "refutation",
                }
        manuscript = load_manuscript(value)
        with self.assertRaises(PublicationValidationError) as caught:
            render_manuscript(manuscript)
        self.assertEqual(
            "resolution_subject_label_asserts_resolution", caught.exception.code
        )

    def test_the_subject_label_is_a_function_of_the_identifier_alone(self) -> None:
        for subject_id, expected in (
            ("problem.graffiti-322", "Graffiti 322"),
            ("conjecture.graffiti-197", "Graffiti 197"),
            ("problem.qd-fs-01-diagonal", "Qd Fs 01 Diagonal"),
            ("unnamespaced-subject", "Unnamespaced Subject"),
            ("problem", "Problem"),
        ):
            self.assertEqual(expected, subject_label(subject_id))

    def test_no_single_field_mutation_buys_an_unearned_headline(self) -> None:
        """Promotion impossibility for the headline, not just for the claim.

        A mutation may make the headline *say less* -- dropping the resolution
        target withdraws the resolution phrase entirely -- but no mutation may
        leave the document asserting a resolution its records do not earn.
        """

        candidates = (
            True, False, None, "", "unconditional", "refutes", "no_prior_art_found_under_protocol",
            "not_assessed", "closed", [], {},
        )
        checked = 0
        for collection in ("claims", "obligations", "verdict_matrices"):
            for index, item in enumerate(_g322_value()[collection]):
                for field in item:
                    for candidate in candidates:
                        value = _g322_value()
                        if value[collection][index][field] == candidate:
                            continue
                        value[collection][index][field] = candidate
                        checked += 1
                        try:
                            manuscript = load_manuscript(value)
                            headline = render_manuscript(manuscript).headline
                        except PublicationValidationError:
                            continue
                        where = f"{collection}[{index}].{field}={candidate!r}"
                        if not headline.resolution_phrase:
                            self.assertEqual((), headline.qualifiers, where)
                            continue
                        if not headline.resolution_phrase.startswith("Candidate "):
                            self.assertEqual(
                                (), manuscript.unearned_resolution_reasons(),
                                f"{where} dropped the hedge while the records were unearned",
                            )
                        self.assertEqual(
                            bool(manuscript.unearned_resolution_reasons()),
                            bool(headline.qualifiers), where,
                        )
        self.assertGreater(checked, 200)

    def test_a_null_prior_art_record_weakens_the_headline_rather_than_clearing_it(self) -> None:
        headline = render_manuscript(load_manuscript(_without_engagement())).headline
        self.assertIn("prior art not assessed", headline.qualifiers)
        self.assertIn("Candidate", headline.resolution_phrase)

    def test_a_claim_the_document_never_displays_cannot_buy_a_rung(self) -> None:
        """An undisplayed resolution claim counts as the weakest class, not the best."""

        value = _g322_value()
        for section in value["sections"]:
            section["blocks"] = [
                block for block in section["blocks"] if block["kind"] != "claim"
            ]
        headline = render_manuscript(load_manuscript(value)).headline
        self.assertIn("unresolved on these records", headline.qualifiers)
        self.assertTrue(headline.resolution_phrase.startswith("Candidate "))

    def test_the_composed_headline_is_byte_stable_across_processes(self) -> None:
        script = (
            "import sys;"
            f"sys.path.insert(0, {str(SRC_ROOT)!r});"
            "from math_research.publication import load_manuscript, render_manuscript;"
            f"d=render_manuscript(load_manuscript(open({str(GRAFFITI_322_PATH)!r},'rb').read()));"
            "print(d.headline.displayed_title);print(d.document_hash)"
        )
        completed = subprocess.run(
            [sys.executable, "-c", script], capture_output=True, text=True, check=True,
            cwd=str(REPO_ROOT),
        )
        document = render_manuscript(load_manuscript(GRAFFITI_322_PATH.read_bytes()))
        self.assertEqual(
            [G322_EXPECTED_TITLE, document.document_hash],
            completed.stdout.splitlines(),
        )

    def test_the_bundle_manifest_hashes_the_headline_it_displayed(self) -> None:
        bundle = build_bundle(load_manuscript(GRAFFITI_322_PATH.read_bytes()))
        self.assertEqual(
            G322_EXPECTED_TITLE, bundle.manifest["headline"]["displayed_title"]
        )
        self.assertFalse(bundle.manifest["headline"]["creates_mathematical_warrant"])
        ledger = json.loads(bundle.files["records/ledger.json"].decode("utf-8"))
        self.assertEqual(G322_EXPECTED_TITLE, ledger["headline"]["displayed_title"])
        self.assertIn(
            "vm.graffiti-322-g14-18.v1", ledger["headline"]["record_refs"]
        )


class HeadlineLedgerClosureTests(unittest.TestCase):
    """Amendment A6. The composed headline is a ledger block, not a slot."""

    def setUp(self) -> None:
        self.manuscript = load_manuscript(GRAFFITI_322_PATH.read_bytes())
        self.document = render_manuscript(self.manuscript)
        self.block = next(
            block for block in self.document.ledger if block.block_id == "derived.title"
        )

    def test_the_headline_block_cites_every_record_that_composed_it(self) -> None:
        self.assertEqual("derived", self.block.origin)
        for record_id in (
            "cl.graffiti-322-counterexample", "vm.graffiti-322-g14-18.v1",
            "conv.graffiti-322-readings.v2", "recheck.graffiti-322.prior-candidate.v1",
            "obl.graffiti-322-prior-candidate-priority",
        ):
            self.assertIn(record_id, self.block.record_refs)
        namespace = set(self.manuscript.record_ids) | {self.manuscript.manuscript_id}
        for ref in self.block.record_refs:
            self.assertIn(ref, namespace)

    def test_the_headline_is_inside_byte_exact_ledger_closure(self) -> None:
        recomputed = TEMPLATE_HEAD + "".join(
            block.tex for block in self.document.ledger
        ) + TEMPLATE_TAIL
        self.assertEqual(self.document.tex, recomputed)
        self.assertIn(
            escape_prose(self.document.headline.displayed_title, "title"), self.block.tex
        )
        verify_headline_closure(self.document)

    def _forged(self, **changes: object) -> RenderedDocument:
        fields = {
            "manuscript_id": self.document.manuscript_id,
            "manuscript_hash": self.document.manuscript_hash,
            "template_hash": self.document.template_hash,
            "document_hash": self.document.document_hash,
            "headline": self.document.headline,
            "tex": self.document.tex,
            "ledger": self.document.ledger,
            "classifications": self.document.classifications,
            "bibliography": self.document.bibliography,
            "cite_keys": self.document.cite_keys,
            "statistics": self.document.statistics,
        }
        fields.update(changes)
        return RenderedDocument(**fields)  # type: ignore[arg-type]

    def test_a_headline_the_ledger_does_not_carry_is_refused(self) -> None:
        stripped = tuple(
            LedgerBlock(
                block_id=block.block_id, origin=block.origin,
                record_refs=block.record_refs,
                tex=block.tex.replace(
                    escape_prose(self.document.headline.displayed_title, "title"),
                    escape_prose(self.document.headline.title_stem, "title"),
                ),
            )
            if block.block_id == "derived.title" else block
            for block in self.document.ledger
        )
        forged = self._forged(ledger=stripped)
        with self.assertRaises(PublicationValidationError) as caught:
            verify_headline_closure(forged)
        self.assertEqual("headline_not_in_ledger", caught.exception.code)

    def test_a_document_with_no_headline_block_is_refused(self) -> None:
        without = tuple(
            block for block in self.document.ledger if block.block_id != "derived.title"
        )
        with self.assertRaises(PublicationValidationError) as caught:
            verify_headline_closure(self._forged(ledger=without))
        self.assertEqual("headline_not_in_ledger", caught.exception.code)

    def test_a_headline_block_missing_a_composing_reference_is_refused(self) -> None:
        thinned = tuple(
            LedgerBlock(
                block_id=block.block_id, origin=block.origin,
                record_refs=(self.manuscript.manuscript_id,), tex=block.tex,
            )
            if block.block_id == "derived.title" else block
            for block in self.document.ledger
        )
        with self.assertRaises(PublicationValidationError) as caught:
            verify_headline_closure(self._forged(ledger=thinned))
        self.assertEqual("headline_record_refs_incomplete", caught.exception.code)

    def test_the_ledger_payload_records_the_composition(self) -> None:
        payload = ledger_payload(self.document)
        self.assertEqual(G322_EXPECTED_TITLE, payload["headline"]["displayed_title"])
        self.assertFalse(payload["headline"]["creates_mathematical_warrant"])
        self.assertEqual(
            list(self.document.headline.record_refs), payload["headline"]["record_refs"]
        )


class DerivedTableTests(unittest.TestCase):
    """The fork and the prior candidate's fate are computed blocks, not prose."""

    def setUp(self) -> None:
        self.manuscript = load_manuscript(GRAFFITI_322_PATH.read_bytes())
        self.document = render_manuscript(self.manuscript)

    def test_the_reading_verdict_rows_are_the_exact_recorded_values(self) -> None:
        self.assertEqual(
            (
                (G322_CLAIM, "even_excludes_v, range_distinct_count",
                 "8772568/953095", "9", "refutes"),
                (G322_CLAIM, "even_excludes_v, range_extent",
                 "8772568/953095", "greater_than:8772568/953095", "does_not_refute"),
                (G322_CLAIM, "even_includes_v, range_distinct_count",
                 "40049/4444", "9", "refutes"),
                (G322_CLAIM, "even_includes_v, range_extent",
                 "40049/4444", "greater_than:40049/4444", "does_not_refute"),
            ),
            reading_verdict_rows(self.manuscript),
        )

    def test_the_replay_table_shows_c4_refuting_only_under_even_excludes_v(self) -> None:
        rows = counter_candidate_rows(self.manuscript)
        self.assertEqual(4, len(rows))
        self.assertEqual({"C4"}, {row[0] for row in rows})
        refuting = {row[1] for row in rows if row[4] == "refutes"}
        self.assertEqual({"even_excludes_v, range_distinct_count"}, refuting)
        self.assertEqual(
            ("C4", "even_excludes_v, range_distinct_count", "4", "3", "refutes"),
            next(row for row in rows if row[4] == "refutes"),
        )

    def test_our_own_witness_is_not_a_prior_candidate(self) -> None:
        self.assertIn("replay.graffiti-322.g14-18-witness.v1", self.manuscript.replays)
        self.assertNotIn(
            "G(14,18)", {row[0] for row in counter_candidate_rows(self.manuscript)}
        )

    def test_both_tables_are_derived_ledger_blocks_with_resolving_refs(self) -> None:
        blocks = {block.block_id: block for block in self.document.ledger}
        for block_id, expected_ref in (
            ("derived.reading-verdicts", "vm.graffiti-322-g14-18.v1"),
            ("derived.counter-candidate-replays", "replay.graffiti-322.c4-candidate.v1"),
        ):
            self.assertIn(block_id, blocks)
            self.assertEqual("derived", blocks[block_id].origin)
            self.assertIn(expected_ref, blocks[block_id].record_refs)
        self.assertIn(r"\section*{Readings and their verdicts}", self.document.tex)
        self.assertIn(r"\section*{Previously published candidates, replayed}", self.document.tex)

    def test_a_manuscript_with_no_reading_records_carries_no_tables(self) -> None:
        document = render_manuscript(load_manuscript(MANUSCRIPT_PATH.read_bytes()))
        ids = {block.block_id for block in document.ledger}
        self.assertNotIn("derived.reading-verdicts", ids)
        self.assertNotIn("derived.counter-candidate-replays", ids)

    def test_a_verdict_with_no_replay_behind_it_reads_as_not_recorded(self) -> None:
        convention = _convention()
        value = _attach(convention, _matrix(convention, evidence_ref=FIXTURE_CERT_HASH))
        rows = reading_verdict_rows(load_manuscript(value))
        self.assertTrue(rows)
        for row in rows:
            self.assertEqual(("not recorded", "not recorded"), (row[2], row[3]))

    def test_the_document_states_the_enumeration_limit(self) -> None:
        self.assertIn(
            "unconditional over the readings this record enumerates", self.document.tex
        )
        self.assertIn("truth-conditional axis and not a priority axis", self.document.tex)


class DerivedFidelityWordingTests(unittest.TestCase):
    """ADR-0060 wording is derived from reading statuses, never asserted."""

    def test_an_asserted_reading_renders_as_source_asserted(self) -> None:
        document = render_manuscript(load_manuscript(GRAFFITI_322_PATH.read_bytes()))
        self.assertIn("source-asserted reading", document.tex)
        self.assertNotIn("source-verbatim reading", document.tex)
        self.assertIn(
            "No claim in this document is described as source-faithful", document.tex
        )

    def test_a_confirmed_reading_renders_as_source_verbatim(self) -> None:
        document = render_manuscript(load_manuscript(_earned()))
        self.assertIn("source-verbatim reading", document.tex)
        self.assertNotIn("source-asserted reading", document.tex)
        self.assertIn("every reading this document enumerates is", document.tex)

    def test_the_coupled_subject_is_named_beside_the_claim(self) -> None:
        document = render_manuscript(load_manuscript(GRAFFITI_322_PATH.read_bytes()))
        self.assertIn("problem.graffiti-197", document.tex)
        self.assertIn("whose recorded status this document does not change", document.tex)


class ClaimProseScreenTests(unittest.TestCase):
    """Amendment B6. Claim prose is reader-facing text with no derivation."""

    def _prose(self, text: str) -> dict:
        value = _g322_value()
        for claim in value["claims"]:
            if claim["claim_id"] == G322_CLAIM:
                claim["prose_statement"] = text
        return value

    def test_an_unhedged_resolution_assertion_beside_a_claim_is_refused(self) -> None:
        for text in (
            "The graph G(14,18) refutes Graffiti 322.",
            "This is a counterexample to Graffiti 322.",
            "The construction settles Graffiti 322.",
        ):
            self.assertEqual(
                "claim_prose_overclaims_evidence", _refusal(self, self._prose(text)), text
            )

    def test_the_fidelity_phrase_beside_a_claim_has_its_own_code(self) -> None:
        self.assertEqual(
            "source_fidelity_overclaimed",
            _refusal(self, self._prose(
                "Under the frozen source-faithful conventions the value exceeds nine."
            )),
        )

    def test_a_hedged_or_denied_mention_is_not_a_claim(self) -> None:
        """Both forms appear in the shipped fixtures, and both are honest."""

        for text in (
            "Under the enumerated reading it is a candidate counterexample to Graffiti 322.",
            "This repository holds no proof of the statement.",
            "No reading refutes Graffiti 322 unconditionally.",
        ):
            load_manuscript(self._prose(text))

    def test_the_discount_window_is_two_tokens_and_no_wider(self) -> None:
        self.assertEqual(
            (),
            _unqualified_lexicon_hits(
                "a candidate counterexample to Graffiti 322", RESOLUTION_LEXICON
            ),
        )
        self.assertEqual(
            ("counterexample",),
            _unqualified_lexicon_hits(
                "no reading changes that this is an exact counterexample", RESOLUTION_LEXICON
            ),
        )

    def test_one_unqualified_occurrence_is_enough_to_refuse(self) -> None:
        self.assertEqual(
            "claim_prose_overclaims_evidence",
            _refusal(self, self._prose(
                "It is a candidate counterexample, and in fact a counterexample."
            )),
        )

    def test_the_headline_fields_stay_strict(self) -> None:
        """The stem and abstract get no discount: a headline is what a summary keeps."""

        value = _g322_value()
        value["title_stem"] = "A candidate counterexample to Graffiti 322"
        self.assertEqual("title_stem_asserts_resolution", _refusal(self, value))


def _recheck_from_payload(payload: dict, **overrides: object) -> dict:
    """Re-derive a re-check record from its payload with one field changed.

    The record is content-hashed, so a mutated field has to be re-finalized or
    the load refuses for the wrong reason.
    """

    fields = dict(
        recheck_id=payload["recheck_id"], checkpoint=payload["checkpoint"],
        subject_id=payload["subject_id"], subject_hash=payload["subject_hash"],
        next_action_id=payload["next_action_id"], performed_by=payload["performed_by"],
        performed_at=payload["performed_at"],
        protocol_id=payload["search_protocol"]["protocol_id"],
        query_terms=tuple(payload["search_protocol"]["query_terms"]),
        searched_sources=tuple(payload["search_protocol"]["searched_sources"]),
        equivalence_checks=tuple(payload["search_protocol"]["equivalence_checks"]),
        evidence_refs=tuple(
            (item["ref_id"], item["content_hash"]) for item in payload["evidence_refs"]
        ),
        outcome=payload["outcome"],
        prior_art_relationship=payload["prior_art"]["relationship"],
        prior_resolution=payload["prior_art"]["resolution"],
        prior_resolution_verification=payload["prior_art"]["verification_status"],
        limitations=tuple(payload["limitations"]),
        previous_recheck_id=payload["previous_recheck_id"],
        previous_recheck_hash=payload["previous_recheck_hash"],
    )
    fields.update(overrides)
    return NoveltyRecheck(**fields).finalized().payload()  # type: ignore[arg-type]


class ProductionGateTests(unittest.TestCase):
    """The teeth move from the announcement act to the artifact (amendment A4)."""

    def setUp(self) -> None:
        self.toolchain = load_toolchain(TOOLCHAIN_PATH)
        self.available = ToolchainStatus(True, "pdflatex", "/pinned/pdflatex", "available")

    def _produce(self, value: dict) -> str:
        with tempfile.TemporaryDirectory() as directory, mock.patch(
            "math_research.publication.production.toolchain_status",
            return_value=self.available,
        ):
            with self.assertRaises(PublicationValidationError) as caught:
                produce_publication(
                    load_manuscript(value), Path(directory) / "bundle", self.toolchain,
                )
        return caught.exception.code

    def test_a_resolution_claim_without_a_classification_cannot_be_produced(self) -> None:
        self.assertEqual(
            "resolution_claim_without_prior_art_classification",
            self._produce(_without_engagement()),
        )

    def test_a_classification_of_some_other_subject_classifies_nothing_here(self) -> None:
        value = _g322_value()
        value["prior_art_engagement"] = {
            "recheck": _recheck_from_payload(
                value["prior_art_engagement"]["recheck"],
                subject_hash=_sha(b"a different manuscript"),
            )
        }
        self.assertEqual("prior_art_recheck_subject_mismatch", self._produce(value))

    def test_freshness_is_deliberately_not_enforced_at_render_time(self) -> None:
        """A named boundary. Yesterday's bundle must stay rebuildable.

        ADR-0055's 24-hour window is a property of the announcement act. Applying
        it here would mean a bundle stops being regenerable from ``records/``
        alone the day after it was written, which is exactly the ADR-0036
        guarantee this repository sells. Subject binding is time-invariant, so it
        is what this gate requires instead: a six-year-old classification of
        *these statements* still passes, and a fresh classification of some other
        statement does not.
        """

        value = _g322_value()
        value["prior_art_engagement"] = {
            "recheck": _recheck_from_payload(
                value["prior_art_engagement"]["recheck"],
                performed_at="2020-01-01T00:00:00Z",
            )
        }
        manuscript = load_manuscript(value)
        self.assertEqual(
            "2020-01-01T00:00:00Z", manuscript.prior_art_recheck().performed_at
        )
        _require_prior_art_classification(manuscript)
        source = (PUBLICATION_ROOT / "production.py").read_text(encoding="utf-8")
        body = source[source.index("def produce_publication"):]
        self.assertNotIn("require_checkpoint", body)
        self.assertNotIn("MAX_FRESHNESS", source)
        self.assertNotIn("from ..novelty import", source)

    @staticmethod
    def _without_reader_facing_probes() -> dict:
        value = _fixture_value()
        value["render_probes"] = [
            probe for probe in value["render_probes"]
            if probe["field"] not in {"title_stem", "abstract"}
            and not probe["field"].endswith((".prose_statement", ".resolution_target"))
        ]
        assert not _headline_probe_present(load_manuscript(value))
        return value

    def test_a_publication_with_no_probe_on_reader_facing_text_is_refused(self) -> None:
        self.assertEqual(
            "publication_has_no_headline_probe",
            self._produce(self._without_reader_facing_probes()),
        )

    def test_a_claim_prose_probe_satisfies_the_reader_facing_requirement(self) -> None:
        value = self._without_reader_facing_probes()
        value["render_probes"].append({
            "probe_id": "pr.prose-must-not-overclaim",
            "field": f"claims[{FIXTURE_CLAIM}].prose_statement",
            "value": "This refutes the QD-FS-01 conjecture.",
            "expected_outcome": "refusal",
            "expected": {"code": "claim_prose_overclaims_evidence"},
            "rationale": "Claim prose is reader-facing text with no derivation.",
        })
        self.assertTrue(_headline_probe_present(load_manuscript(value)))

    def test_the_shipped_fixtures_both_satisfy_the_reader_facing_requirement(self) -> None:
        for path in (MANUSCRIPT_PATH, GRAFFITI_322_PATH):
            self.assertTrue(
                _headline_probe_present(load_manuscript(path.read_bytes())), path.name
            )


class PriorArtRecordTests(unittest.TestCase):
    """Amendment B7. The bundle's prior-art record follows the manuscript."""

    def test_a_draft_with_a_classification_no_longer_reports_not_assessed(self) -> None:
        bundle = build_bundle(load_manuscript(GRAFFITI_322_PATH.read_bytes()))
        record = json.loads(bundle.files["records/prior-art.json"].decode("utf-8"))
        self.assertIsNone(bundle.document.classifications[0].claim_id and None)
        self.assertEqual("recorded", record["status"])
        self.assertEqual("prior_art_engagement", record["source"])
        self.assertEqual("prior_art_relationship_unresolved", record["report_classification"])
        self.assertEqual("recheck.graffiti-322.prior-candidate.v1", record["recheck_id"])
        self.assertFalse(record["creates_mathematical_warrant"])
        self.assertEqual(record, bundle.manifest["prior_art"])

    def test_no_record_at_all_still_reads_not_assessed(self) -> None:
        bundle = build_bundle(load_manuscript(MANUSCRIPT_PATH.read_bytes()))
        record = json.loads(bundle.files["records/prior-art.json"].decode("utf-8"))
        self.assertEqual("not_assessed", record["status"])
        self.assertEqual("absent", record["source"])
        self.assertIsNone(record["recheck_id"])

    def test_the_status_block_reports_the_engagement_without_an_approval(self) -> None:
        document = render_manuscript(load_manuscript(GRAFFITI_322_PATH.read_bytes()))
        self.assertIn("prior_art_relationship_unresolved", document.tex)
        self.assertIn("No human publication approval record exists", document.tex)


class ProbeAddressingTests(unittest.TestCase):
    """Amendment B8. A rule that cannot be addressed cannot be falsified."""

    def test_the_new_collections_are_addressable(self) -> None:
        value = _g322_value()
        for path, expected in (
            (
                "counter_candidate_replays[replay.graffiti-322.c4-candidate.v1].float_used",
                False,
            ),
            (
                "verdict_matrices[vm.graffiti-322-g14-18.v1].convention_hash",
                "sha256:4e78ca62cbd067d5d78b1ff55eb34c05f91d64ee39c0d6c4c8e2bc08205ec738",
            ),
            (
                "conventions[conv.graffiti-322-readings.v2].coupled_subject_ids",
                ["problem.graffiti-197"],
            ),
        ):
            container, key = _resolve(copy.deepcopy(value), path)
            self.assertEqual(expected, container[key], path)

    def test_one_list_step_reaches_a_passage_a_verdict_and_a_reading(self) -> None:
        value = _g322_value()
        for path, expected in (
            (
                "sources[src.fajtlowicz.written-on-wall-2004].passages[1].reading_status",
                "asserted",
            ),
            (
                "verdict_matrices[vm.graffiti-322-g14-18.v1].verdicts[0].verdict",
                "refutes",
            ),
            (
                "verdict_matrices[vm.graffiti-322-g14-18.v1].verdicts[0].reading_tuple",
                ["even_excludes_v", "range_distinct_count"],
            ),
            (
                "counter_candidate_replays[replay.graffiti-322.c4-candidate.v1]"
                ".readings[2].verdict",
                "refutes",
            ),
        ):
            container, key = _resolve(copy.deepcopy(value), path)
            self.assertEqual(expected, container[key], path)

    def test_a_whole_list_element_is_addressable(self) -> None:
        container, key = _resolve(
            _g322_value(),
            "sources[src.fajtlowicz.written-on-wall-2004].passages[0]",
        )
        self.assertIsInstance(container, list)
        self.assertEqual(0, key)

    def test_an_index_that_does_not_exist_is_refused(self) -> None:
        for path in (
            "sources[src.fajtlowicz.written-on-wall-2004].passages[7].reading_status",
            "verdict_matrices[vm.graffiti-322-g14-18.v1].verdicts[9].verdict",
            "counter_candidate_replays[replay.graffiti-322.c4-candidate.v1].order[0]",
            "sources[src.fajtlowicz.written-on-wall-2004].passages[0].not_a_field",
        ):
            with self.assertRaises(PublicationValidationError) as caught:
                _resolve(_g322_value(), path)
            self.assertEqual("probe_field_unresolved", caught.exception.code, path)

    def test_every_new_rule_named_by_the_adrs_has_a_probe_that_flips(self) -> None:
        manuscript = load_manuscript(GRAFFITI_322_PATH.read_bytes())
        result = run_probes(manuscript)
        self.assertEqual(result["probes_total"], result["probes_flipped"])
        codes = {
            probe["expected"]["code"]
            for probe in manuscript.value["render_probes"]
            if probe["expected_outcome"] == "refusal"
        }
        for code in (
            "replay_used_floating_point", "passage_verbatim_missing",
            "passage_extraction_inconsistent", "verdict_matrix_incomplete",
            "convention_hash_mismatch", "claim_prose_overclaims_evidence",
            "resolution_subject_label_asserts_resolution",
            "title_stem_asserts_resolution", "abstract_overclaims_evidence",
            "source_fidelity_overclaimed", "prose_asserts_unrecorded_search",
            "prior_candidate_cannot_be_excluded", "asserted_reading_without_obligation",
            "resolution_claim_without_prior_art_engagement",
            "resolution_claim_without_verdict_matrix", "prior_art_engagement_invalid",
        ):
            self.assertIn(code, codes)
        demotions = {
            probe["expected"]["evidence_class"]
            for probe in manuscript.value["render_probes"]
            if probe["expected_outcome"] == "demotion"
        }
        self.assertIn("proposal", demotions)
