# AdaIvy repository checks.
#
# `make check` is the single documented offline entrypoint. It needs no network,
# no model provider, no container runtime, and no third-party package.
#
# Targets that need more than that are separate and named for what they need:
#   check-sealed  requires the ADR-0016 v5 container image
#   check-gate    requires the disposable Draft 2020-12 validator environment
#   check-all     runs everything available

PY ?= python3
export PYTHONDONTWRITEBYTECODE := 1
export PYTHONPATH := src

# Frozen instants. The acceptance paths are deterministic, so these are inputs,
# never `date` output; a moving clock would break byte-reproducibility.
PHASE5_INSTANT ?= 2026-08-20T12:00:00Z
PHASE6_INSTANT ?= 2026-08-20T14:00:00Z

TMPROOT ?= $(shell printf '%s' "$${TMPDIR:-/tmp}")

.PHONY: check check-all check-sealed check-gate check-phase4b-oci test phase0 \
        phase1 phase2 phase3a phase3b phase4a phase4b phase4c phase5 phase6 \
        synthesis clean help

help:
	@printf 'Targets:\n'
	@printf '  check         offline suite: tests + phases 0,1,2,3A,4A,4B,4C,5,6 and synthesis\n'
	@printf '  check-sealed  phase 3B Lean formal checking (requires the ADR-0016 v5 image)\n'
	@printf '  check-gate    phase 4 gate tests (requires the disposable jsonschema env)\n'
	@printf '  check-phase4b-oci strict Phase 4B parser gate (requires exact pinned image)\n'
	@printf '  check-all     check + check-sealed\n'
	@printf '  clean         remove __pycache__ and stray sqlite journals\n'

check: test phase0 phase1 phase2 phase3a phase4a phase4b phase4c phase5 phase6 synthesis
	@printf '\n== offline check complete ==\n'

check-all: check check-sealed
	@printf '\n== full check complete ==\n'

test:
	@printf '\n== unit/integration/adversarial suite ==\n'
	$(PY) -m unittest discover -s tests

phase0:
	@printf '\n== phase 0 adoption harness ==\n'
	$(PY) -m phase0_harness.cli check

phase1:
	@printf '\n== phase 1 manual trust core ==\n'
	@d=$$(mktemp -d "$(TMPROOT)/adaivy-p1.XXXXXX") && \
	  $(PY) -m math_research.cli demo --output-dir "$$d" >/dev/null && \
	  $(PY) -m math_research.cli inspect "$$d/manual-dossier.json" >/dev/null && \
	  rm -rf "$$d" && printf 'phase 1 ok\n'

phase2:
	@printf '\n== phase 2 durable baseline loop ==\n'
	@d=$$(mktemp -d "$(TMPROOT)/adaivy-p2.XXXXXX") && \
	  $(PY) -m math_research.cli phase2 report reports/phase-2 run.phase2.demo.fake.v1 \
	    --output "$$d/traceable-report.md" >/dev/null && \
	  rm -rf "$$d" && printf 'phase 2 ok\n'

phase3a:
	@printf '\n== phase 3A bounded research memory ==\n'
	@d=$$(mktemp -d "$(TMPROOT)/adaivy-p3a.XXXXXX") && \
	  $(PY) -m math_research.cli phase3a demo "$$d/workspace" --output-dir "$$d/out" >/dev/null && \
	  $(PY) -m math_research.cli phase3a inspect "$$d/out/research-memory.json" >/dev/null && \
	  rm -rf "$$d" && printf 'phase 3A ok\n'

# Separate from `check`: needs the exact ADR-0016 v5 container image. Without it
# the adapter fails closed and this target reports a failed status by design.
phase3b check-sealed:
	@printf '\n== phase 3B sealed Lean runtime (requires ADR-0016 v5 image) ==\n'
	@d=$$(mktemp -d "$(TMPROOT)/adaivy-p3b.XXXXXX") && \
	  $(PY) -m math_research.cli phase3b demo "$$d/workspace" --output-dir "$$d/out" >/dev/null && \
	  $(PY) -m math_research.cli phase3b inspect "$$d/out/formal-checking.json" >/dev/null && \
	  rm -rf "$$d" && printf 'phase 3B ok\n'

phase4a:
	@printf '\n== phase 4A local rights and applicability ==\n'
	@d=$$(mktemp -d "$(TMPROOT)/adaivy-p4a.XXXXXX") && \
	  $(PY) -m math_research.phase4a_cli init "$$d/workspace" \
	    fixtures/phase4a-production/empty-workspace-spec-v1.json >/dev/null && \
	  $(PY) -m math_research.phase4a_cli export "$$d/workspace" \
	    "$$d/phase4a-export.json" $(PHASE5_INSTANT) >/dev/null && \
	  $(PY) -m math_research.phase4a_cli inspect "$$d/phase4a-export.json" >/dev/null && \
	  rm -rf "$$d" && printf 'phase 4A ok\n'

phase4b:
	@printf '\n== phase 4B offline acquisition/parsing metadata ==\n'
	@d=$$(mktemp -d "$(TMPROOT)/adaivy-p4b.XXXXXX") && \
	  $(PY) -m math_research.cli phase4b init "$$d/workspace" >/dev/null && \
	  $(PY) -m math_research.cli phase4b export "$$d/workspace" \
	    "$$d/phase4b-export.json" >/dev/null && \
	  $(PY) -m math_research.cli phase4b inspect "$$d/phase4b-export.json" >/dev/null && \
	  $(PY) -m math_research.cli phase4b replay "$$d/replay" \
	    "$$d/phase4b-export.json" >/dev/null && \
	  $(PY) -m math_research.cli phase4b gate . "$$d/gate" \
	    --output "$$d/phase4b-feasible-gate.json" >/dev/null && \
	  rm -rf "$$d" && printf 'phase 4B ok\n'

# Phase 4C meets all seven gates under ADR-0046. ADR-0031 shipped it as a
# measured partial with applicability_precision_at_5 at 0.6 against a gate of
# 1.0, for two recorded causes: a demotion-only signal cannot move a metric
# whose candidate sets already sit inside the top-k cutoff, and the frozen
# same-sentence scope unit never fired on applicability-selfadjoint. ADR-0046
# replaces demotion with removal and the sentence with the anaphor-resolved
# scope block; the 0.6 survives as the non-gated disclosure metric
# applicability_precision_at_5_pre_suppression, so this target's report still
# contains the pre-improvement number. Both commands now exit 0, so no status is
# tolerated: a nonzero exit fails this target. The recorded outcome is asserted
# in BOTH directions, because a silent improvement is an unreviewed change to a
# frozen benchmark and a silent regression is a regression. `verified` covers
# the canonical report hash, so a failing gate is never counted as a pass and a
# broken hash is never ignored.
phase4c:
	@printf '\n== phase 4C benchmark-scoped hybrid retrieval ==\n'
	@d=$$(mktemp -d "$(TMPROOT)/adaivy-p4c.XXXXXX") && \
	  $(PY) -m math_research.cli phase4c benchmark --fixtures fixtures/phase4c \
	    --output "$$d/phase4c-report.json" >/dev/null && \
	  $(PY) -m math_research.cli phase4c inspect "$$d/phase4c-report.json" \
	    > "$$d/phase4c-verified.json" && \
	  $(PY) -c 'import json,sys; r=json.load(open(sys.argv[1])); s=r["gate_summary"]; f=r["failing_gates"]; m=r["metrics"]; assert r.get("verified") is True, "phase 4C canonical report hash did not verify"; assert (s["pass"], s["fail"], s["undetermined"]) == (7, 0, 0), "phase 4C gate summary moved: %s" % s; assert s["overall"] == "pass", "phase 4C overall gate status moved: %s" % s; assert f == [], "phase 4C failing gates moved: %s" % f; assert m["applicability_precision_at_5"] == 1.0, "phase 4C applicability precision moved: %s" % m; assert m["applicability_precision_at_5_pre_suppression"] == 0.6, "phase 4C pre-suppression disclosure moved: %s" % m' \
	    "$$d/phase4c-verified.json" && \
	  rm -rf "$$d" && \
	  printf 'phase 4C ok (7 gates hold; pre-suppression applicability precision disclosed at 0.6)\n'

phase5:
	@printf '\n== phase 5 exact adaptive quantum benchmark ==\n'
	@d=$$(mktemp -d "$(TMPROOT)/adaivy-p5.XXXXXX") && \
	  $(PY) -m math_research.cli phase5 run "$$d/workspace" \
	    fixtures/phase5/quantum-diagonal-v1.json $(PHASE5_INSTANT) \
	    --output "$$d/run.json" >/dev/null && \
	  $(PY) -m math_research.cli phase5 list-results "$$d/workspace" >/dev/null && \
	  rm -rf "$$d" && printf 'phase 5 ok\n'

phase6:
	@printf '\n== phase 6 confirmatory evaluation and release ==\n'
	@d=$$(mktemp -d "$(TMPROOT)/adaivy-p6.XXXXXX") && \
	  $(PY) -m math_research.cli phase6 demo "$$d/workspace" \
	    fixtures/phase6/confirmatory-protocol-v1.json \
	    fixtures/phase5/quantum-diagonal-v1.json \
	    $(PHASE5_INSTANT) $(PHASE6_INSTANT) --output-dir "$$d/out" >/dev/null && \
	  $(PY) -m math_research.cli phase6 inspect "$$d/out/phase6-export.json" >/dev/null && \
	  rm -rf "$$d" && printf 'phase 6 ok\n'

synthesis:
	@printf '\n== bounded exploratory synthesis ==\n'
	@d=$$(mktemp -d "$(TMPROOT)/adaivy-synthesis.XXXXXX") && \
	  $(PY) -m math_research.synthesis_cli validate-budget \
	    fixtures/synthesis/budget-policy-v1.json >/dev/null && \
	  $(PY) -m math_research.synthesis_cli export "$$d/workspace" \
	    "$$d/synthesis-export.json" >/dev/null && \
	  $(PY) -m math_research.synthesis_cli inspect \
	    "$$d/synthesis-export.json" >/dev/null && \
	  rm -rf "$$d" && printf 'synthesis ok\n'

# The 15 gate tests skip themselves unless `jsonschema` is importable. They are
# meant to run inside the disposable environment described in
# docs/phase-4/DEPENDENCY_LICENSE_ASSESSMENT.md -- never the ordinary .venv.
# Acquisition needs network, so this target never installs anything; point PY at
# an interpreter that already has the pinned validator.
check-gate:
	@printf '\n== phase 4 gate tests (disposable validator environment) ==\n'
	@$(PY) -c 'import importlib.util,sys; sys.exit(0 if importlib.util.find_spec("jsonschema") else 1)' \
	  || { \
	    printf 'jsonschema is not importable for %s, so all 15 gate tests would skip.\n' '$(PY)'; \
	    printf 'Build the disposable environment from the pinned manifest first:\n'; \
	    printf '  requirements-phase4-gate-py314-macos-arm64.txt\n'; \
	    printf 'then re-run: make check-gate PY=/path/to/gate-venv/bin/python\n'; \
	    exit 1; \
	  }
	$(PY) -m unittest tests.test_phase4_gate \
	  tests.test_phase4a_schema_conformance tests.test_material_partial_result_contract

# Separate from `check`: this executes untrusted-parser fixtures inside the
# exact no-pull OCI runtime locked in config/phase4b-oci-image-linux-arm64-v1.json.
check-phase4b-oci:
	@docker_bin=$$(command -v docker) && \
	  docker_host=$$(docker context inspect --format '{{.Endpoints.docker.Host}}') && \
	  ADAIVY_PHASE4B_OCI_DOCKER="$$docker_bin" \
	  ADAIVY_PHASE4B_OCI_DAEMON="$$docker_host" \
	  ADAIVY_PHASE4B_OCI_IMAGE='docker.io/library/python@sha256:6b8f06d04d5305c1d1288435388df9165ab41e681fae6439d6349d8053cc3f83' \
	  $(PY) -m unittest tests.test_phase4b_oci_parser_sandbox

clean:
	find . -name __pycache__ -type d -prune -exec rm -rf {} + 2>/dev/null || true
	find . -name '*.sqlite3-shm' -o -name '*.sqlite3-wal' | xargs rm -f 2>/dev/null || true
