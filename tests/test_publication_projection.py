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
    verify_ledger_closure,
    write_bundle,
)
from math_research.publication.bibliography import build_bibliography  # noqa: E402
from math_research.publication.bundle import verify_bundle  # noqa: E402
from math_research.publication.evidence import EVIDENCE_CLASSES  # noqa: E402
from math_research.publication.latexsafe import escape_prose, validate_math  # noqa: E402
from math_research.publication.render import (  # noqa: E402
    TEMPLATE_HASH,
    LedgerBlock,
    RenderedDocument,
)
from math_research.publication.production import produce_publication  # noqa: E402
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

MANUSCRIPT_PATH = REPO_ROOT / "fixtures/publication/manuscript-v1.json"
TOOLCHAIN_PATH = REPO_ROOT / "config/publication-typeset-toolchain-v1.json"
PHASE5_FIXTURE = REPO_ROOT / "fixtures/phase5/quantum-diagonal-v1.json"
PUBLICATION_ROOT = SRC_ROOT / "math_research/publication"


def _sha(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _fixture_value() -> dict:
    return json.loads(MANUSCRIPT_PATH.read_text(encoding="utf-8"))


# A deliberately synthetic manuscript. It exists to exercise the attestation
# ladder, which no offline path can reach: `make check` excludes the sealed
# ADR-0016 Lean runtime, so the shipped fixture carries no attestation and the
# rendered bundle carries no theorem. Nothing here is a recorded kernel result.
SYNTHETIC_LEAN = "theorem ada_synthetic : 1 + 1 = 2 := by norm_num"


def _synthetic_manuscript(outcome: str, *, unapproved: list[str], representation: str) -> dict:
    lean_hash = _sha(SYNTHETIC_LEAN.encode("utf-8"))
    return {
        "schema_version": "1.3.0",
        "manuscript_id": "ms.synthetic-attestation-ladder.v1",
        "title": "Synthetic attestation ladder",
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
            }
        ],
        "obligations": [],
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
        "render_probes": [],
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
        self.assertNotIn(str(self.manuscript.value["title"]), template)
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


if __name__ == "__main__":
    unittest.main()
