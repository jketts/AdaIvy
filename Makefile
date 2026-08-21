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

.PHONY: check check-all check-sealed check-gate check-phase4b-oci \
        spike-phase5-sdp test phase0 \
        phase1 phase2 phase3a phase3b phase4a phase4b phase4c phase5 phase6 \
        synthesis clean help

help:
	@printf 'Targets:\n'
	@printf '  check         offline suite: tests + phases 0,1,2,3A,4A,4B,4C,5,6 and synthesis\n'
	@printf '  check-sealed  phase 3B Lean formal checking (requires the ADR-0016 v5 image)\n'
	@printf '  check-gate    phase 4 gate tests (requires the disposable jsonschema env)\n'
	@printf '  check-phase4b-oci strict Phase 4B parser gate (requires exact pinned image)\n'
	@printf '  spike-phase5-sdp  ADR-0045 noncommuting-SDP comparison (engines optional)\n'
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

# Phase 4C is a measured PARTIAL, not a pass: six gates hold and
# applicability_precision_at_5 fails at 0.6 against a gate of 1.0. ADR-0031
# records why a demotion-only signal cannot reach it -- every applicability
# query's candidate set is at or below the top-k cutoff, so no reordering can
# move the metric at all. Both commands exit 1 by design while a gate fails, so
# their status is tolerated and the recorded outcome is asserted instead: this
# target fails if the result moves in EITHER direction, because a silent
# improvement is an unreviewed change to a frozen benchmark and a silent
# regression is a regression. `verified` covers the canonical report hash, so a
# failing gate is never counted as a pass and a broken hash is never ignored.
phase4c:
	@printf '\n== phase 4C benchmark-scoped hybrid retrieval ==\n'
	@d=$$(mktemp -d "$(TMPROOT)/adaivy-p4c.XXXXXX") && \
	  { $(PY) -m math_research.cli phase4c benchmark --fixtures fixtures/phase4c \
	      --output "$$d/phase4c-report.json" >/dev/null || true; } && \
	  { $(PY) -m math_research.cli phase4c inspect "$$d/phase4c-report.json" \
	      > "$$d/phase4c-verified.json" || true; } && \
	  $(PY) -c 'import json,sys; r=json.load(open(sys.argv[1])); s=r["gate_summary"]; f=r["failing_gates"]; assert r.get("verified") is True, "phase 4C canonical report hash did not verify"; assert (s["pass"], s["fail"], s["undetermined"]) == (6, 1, 0), "phase 4C gate summary moved: %s" % s; assert f == ["applicability_precision_at_5"], "phase 4C failing gates moved: %s" % f' \
	    "$$d/phase4c-verified.json" && \
	  rm -rf "$$d" && \
	  printf 'phase 4C ok (6 gates hold; applicability_precision_at_5 fails as recorded)\n'

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

# ADR-0045 noncommuting-SDP engine comparison. Deliberately NOT part of `check`:
# `check` is the pinned offline entrypoint and this target's engine-present path
# needs the disposable environment built from
# requirements-phase5-sdp-comparison-py314-macos-arm64.txt -- never the ordinary
# .venv. The library and CLI are already covered by the offline suite in
# tests/test_phase5_noncommuting_sdp_comparison.py.
#
# The forced fail-closed leg always runs and always exits 1 by design, because a
# comparison with fewer than two engines is INCOMPLETE, not a pass. Its recorded
# outcome is asserted instead, so this target fails if the result moves in either
# direction: a silent completion would mean an engine got loaded on the offline
# path, and a lost certificate would be a regression.
spike-phase5-sdp:
	@printf '\n== ADR-0045 noncommuting-SDP comparison: forced fail-closed leg ==\n'
	@d=$$(mktemp -d "$(TMPROOT)/adaivy-p5sdp.XXXXXX") && \
	  { PYTHONPATH=src:. $(PY) -m spikes.phase5_noncommuting_sdp.comparison_cli run \
	      --no-engines --output "$$d/closed.json" >/dev/null || true; } && \
	  $(PY) -c 'import json,sys; r=json.load(open(sys.argv[1])); assert r["experiment_status"]=="incomplete_engines_absent_or_refused", r["experiment_status"]; assert r["minimum_independent_engines_executed"]==0; assert len(r["missing_tool_records"])==6, r["missing_tool_records"]; assert r["all_cases_exactly_certified"] is True; assert r["guardrails"]["warrant_created"] is False; assert r["guardrails"]["search_tiers_enabled"] is False; assert r["guardrails"]["phase5_integrated"] is False' \
	    "$$d/closed.json" && \
	  rm -rf "$$d" && \
	  printf 'fail-closed leg ok (2 engines absent, 6 missing-tool records, 3 exact certificates)\n'
	@printf '\n== engine-present leg (requires the disposable pinned environment) ==\n'
	@if $(PY) -c 'import importlib.util,sys; sys.exit(0 if importlib.util.find_spec("clarabel") and importlib.util.find_spec("cvxpy") else 1)'; then \
	    PYTHONPATH=src:. $(PY) -m spikes.phase5_noncommuting_sdp.comparison_cli run \
	      >/dev/null && printf 'two-engine comparison complete\n'; \
	  else \
	    printf 'clarabel/cvxpy are not importable for %s, so no engine ran.\n' '$(PY)'; \
	    printf 'That is the expected offline result and is NOT a pass for the\n'; \
	    printf 'two-engine clause. To run it, build the disposable environment:\n'; \
	    printf '  requirements-phase5-sdp-comparison-py314-macos-arm64.txt\n'; \
	    printf 'then: make spike-phase5-sdp PY=/path/to/sdp-venv/bin/python\n'; \
	  fi

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
