# AdaIvy repository checks.
#
# `make check` is the single documented offline entrypoint. It needs no network,
# no model provider, no container runtime, and no third-party package.
#
# Targets that need more than that are separate and named for what they need:
#   check-sealed  requires the ADR-0016 v5 container image
#   check-gate    requires the disposable Draft 2020-12 validator environment
#   setup-typeset installs the pinned BasicTeX toolchain under work/ (ADR-0053)
#   check-typeset requires that pinned TeX Live engine (ADR-0036, ADR-0053)
#   check-all     runs everything available

PY ?= python3
export PYTHONDONTWRITEBYTECODE := 1
export PYTHONPATH := src

# Frozen instants. The acceptance paths are deterministic, so these are inputs,
# never `date` output; a moving clock would break byte-reproducibility.
PHASE5_INSTANT ?= 2026-08-20T12:00:00Z
PHASE6_INSTANT ?= 2026-08-20T14:00:00Z
INTAKE_INSTANT ?= 2026-08-21T00:00:00Z
CAMPAIGN_RECHECK_INSTANT ?= 2026-08-22T00:00:00Z
CAMPAIGN_INSTANT ?= 2026-08-22T00:10:00Z

TMPROOT ?= $(shell printf '%s' "$${TMPDIR:-/tmp}")
TYPESET_BIN ?= $(CURDIR)/work/toolchains/basictex-2026.0301/bin/universal-darwin

# `make report` filing. The two stamps below name a directory and stamp an index;
# they are the ONLY clock reads in this file. Every command in the target runs on
# frozen fixtures at the frozen instants above, so two runs with the same stamps
# produce byte-identical output with exactly two measured exceptions, both of them
# properties of the phases rather than of this target:
#
#   phase1/demo-summary.json  echoes its own output paths, so it changes with OUT.
#   phase4c/...-report.json   carries `operational.elapsed_ms` and the derived
#                             `operational_hash`. Phase 4C separates those from
#                             `content_hash` deliberately; the content hash is
#                             stable and the operational one is a timing.
#
# Everything else -- phase 5, phase 6, synthesis and the publication bundle --
# is byte-identical. Override both stamps to reproduce an earlier run.
REPORT_STAMP ?= $(shell date -u +%Y%m%dT%H%M%SZ)
REPORT_INSTANT ?= $(shell date -u +%Y-%m-%dT%H:%M:%SZ)
OUT ?= reports/local/run-$(REPORT_STAMP)
WORK ?= work/$(REPORT_STAMP)

.PHONY: check check-all check-sealed check-gate setup-typeset check-typeset publication-build check-phase4b-oci \
        spike-phase5-sdp test phase0 phase1 problem-intake phase2 phase3a phase3b phase4a phase4b \
        phase4c phase4d phase5 phase6 synthesis campaign publication report clean help

help:
	@printf 'Targets:\n'
	@printf '  check         offline suite: tests + phases 0,1,2,3A,4A,4B,4C,4D,5,6, problem intake, synthesis, campaign, publication\n'
	@printf '  check-sealed  phase 3B Lean formal checking (requires the ADR-0016 v5 image)\n'
	@printf '  check-gate    phase 4 gate tests (requires the disposable jsonschema env)\n'
	@printf '  setup-typeset acquire and hash-check BasicTeX under work/toolchains\n'
	@printf '  check-typeset publication PDF build (requires the pinned TeX Live engine)\n'
	@printf '  publication-build automatically emit a complete TeX/Lean/PDF bundle\n'
	@printf '  check-phase4b-oci strict Phase 4B parser gate (requires exact pinned image)\n'
	@printf '  spike-phase5-sdp  ADR-0045 noncommuting-SDP comparison (engines optional)\n'
	@printf '  check-all     check + check-sealed\n'
	@printf '  report        write every readable artifact and compile its publication PDF\n'
	@printf '                default OUT=reports/local/run-<stamp> (gitignored)\n'
	@printf '  clean         remove __pycache__ and stray sqlite journals\n'

check: test phase0 phase1 problem-intake phase2 phase3a phase4a phase4b phase4c phase4d phase5 phase6 synthesis campaign publication
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

# ADR-0039. The intake instant is an explicit input, never `date` output, so the
# dossier is byte-reproducible. The recorded outcome is asserted rather than the
# exit status alone: a problem file that asserts in its own prose that its target
# is already proved, formally verified, warranted, novel, and significant must
# still MEASURE `unknown` with zero warrants, and an invalid file must fail
# closed with exit code 2. A silent move in either direction fails this target.
problem-intake:
	@printf '\n== declarative problem intake ==\n'
	@d=$$(mktemp -d "$(TMPROOT)/adaivy-intake.XXXXXX") && \
	  $(PY) -m math_research.cli problem validate \
	    fixtures/problem-intake/graph-cycle-edge-bound-v1.json >/dev/null && \
	  $(PY) -m math_research.cli problem demo \
	    fixtures/problem-intake/odd-perfect-number-search-v1.json $(INTAKE_INSTANT) \
	    --output-dir "$$d/out" > "$$d/existential.json" && \
	  $(PY) -m math_research.cli inspect "$$d/out/intake-dossier.json" >/dev/null && \
	  $(PY) -m math_research.cli problem create \
	    fixtures/problem-intake/asserts-its-own-proof-v1.json $(INTAKE_INSTANT) \
	    "$$d/overclaimed.json" > "$$d/overclaimed-summary.json" && \
	  $(PY) -c 'import json,sys; a=json.load(open(sys.argv[1])); b=json.load(open(sys.argv[2])); t=b["measured_trust"]; assert a["rederived_hash_identical"] is True and a["round_trip_hash_preserved"] is True, "intake replay/re-derivation moved"; assert t["logical_status"] == "unknown", "a problem file asserting its own proof produced logical_status %s" % t["logical_status"]; assert t["warrant_kinds"] == [], "the intake created warrant kinds %s" % t["warrant_kinds"]; assert (t["novelty_status"], t["significance_status"], t["contribution_status"]) == ("not_assessed", "not_assessed", "unattributed"), "the intake set an epistemic assessment: %s" % t; assert b["counts"]["warrants"] == b["counts"]["evidence"] == b["counts"]["verification_records"] == b["counts"]["source_applicability"] == b["counts"]["representation_maps"] == 0, "the intake created trust-bearing records: %s" % b["counts"]; assert b["counts"]["obligations_open"] == 2, "the intake stopped opening its obligations: %s" % b["counts"]' \
	    "$$d/existential.json" "$$d/overclaimed-summary.json" && \
	  if $(PY) -m math_research.cli problem create \
	      fixtures/problem-intake/invalid/forbidden-field-warrants.json $(INTAKE_INSTANT) \
	      "$$d/must-not-exist.json" >/dev/null 2>&1; then \
	    printf 'a problem file declaring warrants was accepted\n'; exit 1; \
	  fi && \
	  test ! -e "$$d/must-not-exist.json" && \
	  rm -rf "$$d" && \
	  printf 'problem intake ok (declared proof measured unknown; warrant declaration rejected)\n'


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
	  $(PY) -m math_research.cli phase4b public-acquire "$$d/public-dry-run" \
	    source.phase4b.public-dry-run fixtures/phase4b/public-acquisition-plan-v1.json \
	    --activation config/phase4b-public-acquisition-activation-v1.json \
	    --activation-evidence reports/phase-4b-activation/activation-evidence.json \
	    --output "$$d/public-acquisition-dry-run.json" >/dev/null && \
	  $(PY) -c 'import json,sys; r=json.load(open(sys.argv[1])); assert r["execution_status"] == "not_executed" and r["candidate_count"] == 0; assert not __import__("pathlib").Path(sys.argv[2]).exists()' \
	    "$$d/public-acquisition-dry-run.json" "$$d/public-dry-run" && \
	  rm -rf "$$d" && printf 'phase 4B ok\n'

# Phase 4C measures all seven gates as passing under ADR-0032, on the third
# fixture extension: 19 documents, 17 queries, six of them applicability. The
# ADR-0031 residual closed because the self-disclaimer signal now EXCLUDES a
# candidate rather than demoting it, and because its cues are composed from two
# frozen vocabularies rather than enumerated. The recorded outcome is asserted
# rather than the exit status alone, so this target fails if the result moves in
# EITHER direction: a silent improvement is an unreviewed change to a frozen
# benchmark and a silent regression is a regression. `verified` covers the
# canonical report hash, so a failing gate is never counted as a pass and a
# broken hash is never ignored.
phase4c:
	@printf '\n== phase 4C benchmark-scoped hybrid retrieval ==\n'
	@d=$$(mktemp -d "$(TMPROOT)/adaivy-p4c.XXXXXX") && \
	  $(PY) -m math_research.cli phase4c benchmark --fixtures fixtures/phase4c \
	    --output "$$d/phase4c-report.json" >/dev/null && \
	  $(PY) -m math_research.cli phase4c inspect "$$d/phase4c-report.json" \
	    > "$$d/phase4c-verified.json" && \
	  $(PY) -c 'import json,sys; r=json.load(open(sys.argv[1])); s=r["gate_summary"]; m=r["metrics"]; assert r.get("verified") is True, "phase 4C canonical report hash did not verify"; assert (s["pass"], s["fail"], s["undetermined"]) == (7, 0, 0), "phase 4C gate summary moved: %s" % s; assert r["failing_gates"] == [] and r["undetermined_gates"] == [], "phase 4C gate status moved: %s" % r["gate_status"]; assert r["queries"] == 17, "phase 4C query count moved: %s" % r["queries"]; assert m["applicability_precision_at_5"] == 1.0, "phase 4C applicability precision moved: %s" % m["applicability_precision_at_5"]; assert r["metric_support"]["duplicate_rate_at_5"] == {"numerator": 1, "denominator": 50, "defined": True}, "phase 4C duplicate support moved: %s" % r["metric_support"]["duplicate_rate_at_5"]' \
	    "$$d/phase4c-verified.json" && \
	  rm -rf "$$d" && \
	  printf 'phase 4C ok (7 gates hold; applicability precision 1.0 by exclusion)\n'

# ADR-0051 keeps the offline entrypoint inert: it validates the pinned public
# provider and grounded query, emits a not-executed report, and performs zero
# DNS or HTTPS calls. Live execution always needs two explicit confirmations.
phase4d:
	@printf '\n== phase 4D grounded public scholarly discovery (dry run) ==\n'
	@d=$$(mktemp -d "$(TMPROOT)/adaivy-p4d.XXXXXX") && \
	  $(PY) -m math_research.cli phase4d search \
	    fixtures/phase4d/grounded-terminology-v1.txt \
	    --term 'quantum state discrimination' --term 'spectral projector' \
	    --config config/phase4d-crossref-public-discovery-v1.json \
	    --observed-at-epoch 0 --output "$$d/discovery.json" >/dev/null && \
	  $(PY) -m math_research.cli phase4d inspect "$$d/discovery.json" >/dev/null && \
	  $(PY) -c 'import json,sys; r=json.load(open(sys.argv[1])); assert r["status"] == "not_executed" and r["network_requests"] == 0 and r["candidate_count"] == 0 and r["inspiration_only"] is True' "$$d/discovery.json" && \
	  rm -rf "$$d" && printf 'phase 4D ok (network not executed)\n'

# Phase 5 has three scopes and the target states all of them honestly.
#
# The sealed scope is exact scalar/diagonal QD-FS-01: commuting cases, computed
# results, deterministic tier-0 branches (ADR-0023).
#
# The noncommuting scope (ADR-0035) VERIFIES certificates supplied by an
# authorized human and never DISCOVERS them. It closes the ADR-0033 `1/4` gap to
# exactly zero over one measured quadratic extension per case, with no
# dependency, no float and no tolerance -- and it covers only two-outcome
# ensembles whose optimum a human already derived in closed form. It does not
# answer general noncommuting JRF convergence. The retained
# `real-noncommuting-irreducible-cubic-boundary` case is a genuine noncommuting
# ensemble this design provably cannot close, and it must stay visible in every
# run. Search tiers 2--4 stay disabled.
#
# ADR-0049 adds a bounded exact solver for exactly two outcomes in dimension
# two. It constructs a candidate over one measured quadratic extension and the
# ADR-0035 exact checker remains the final authority. It does not cover the
# retained dimension-three cubic boundary or general noncommuting convergence.
#
# The recorded outcome is asserted, not the exit status, so this fails if the
# result moves in EITHER direction: a coverage status that changes, a boundary
# case that disappears, a discovered optimum, or a rendered report that claims
# general capability is a failure, and so is a silent improvement.
phase5:
	@printf '\n== phase 5 exact adaptive quantum benchmark ==\n'
	@d=$$(mktemp -d "$(TMPROOT)/adaivy-p5.XXXXXX") && \
	  $(PY) -m math_research.cli phase5 run "$$d/workspace" \
	    fixtures/phase5/quantum-diagonal-v1.json $(PHASE5_INSTANT) \
	    --output "$$d/run.json" >/dev/null && \
	  $(PY) -m math_research.cli phase5 list-results "$$d/workspace" >/dev/null && \
	  $(PY) -m math_research.cli phase5 verify-noncommuting "$$d/noncommuting" \
	    fixtures/phase5/noncommuting-certificates-v1.json $(PHASE5_INSTANT) \
	    --output "$$d/noncommuting-run.json" \
	    --report "$$d/noncommuting-report.md" >/dev/null && \
	  $(PY) -c 'import json,sys; r=json.load(open(sys.argv[1])); c=r["coverage_status_counts"]; t=open(sys.argv[2],encoding="utf-8").read(); assert r["schema_version"] == "adaivy.phase5-noncommuting-run-result.v1", "phase 5 noncommuting run schema moved: %s" % r["schema_version"]; assert c == {"certificate_supplied_and_verified": 4, "certificate_supplied_gap_not_closed": 2, "certificate_supplied_outside_represented_field": 1, "certificate_supplied_and_refuted": 0, "unresolved_no_certificate_supplied": 1}, "phase 5 noncommuting coverage moved: %s" % c; assert r["field_boundary_case_ids"] == ["real-noncommuting-irreducible-cubic-boundary"], "phase 5 lost its measured cubic field boundary: %s" % r["field_boundary_case_ids"]; assert r["unresolved_case_ids"] == ["real-noncommuting-certificate-withheld"], "phase 5 noncommuting unresolved set moved: %s" % r["unresolved_case_ids"]; assert r["discovery_performed"] is False and r["general_noncommuting_convergence_answered"] is False, "phase 5 noncommuting claimed discovery or general coverage"; assert r["unproducible_coverage_status"] == "optimum_discovered" and "optimum_discovered" not in r["coverage_status_vocabulary"], "phase 5 made a discovered optimum producible"; assert r["tolerance"] is None and r["radicands_used"] == [1, 2, 5], "phase 5 noncommuting field or tolerance moved: %s %s" % (r["tolerance"], r["radicands_used"]); assert all(r["search_tiers"][k] == "disabled_no_measured_cost_adjusted_gain" for k in ("tier_2","tier_3","tier_4")), "phase 5 enabled a higher search tier"; assert set(r["case_coverage_status"].values()) <= set(r["coverage_status_vocabulary"]), "phase 5 reported a coverage status outside the frozen vocabulary"; assert "## Coverage (read this before any gap)" in t and t.index("## Coverage") < t.index("gap:"), "phase 5 report must present coverage before the gap"; assert "NOT answered by this slice" in t, "phase 5 report dropped its coverage disclaimer"' \
	    "$$d/noncommuting-run.json" "$$d/noncommuting-report.md" && \
	  $(PY) -m math_research.cli phase5 solve-noncommuting \
	    fixtures/phase5/noncommuting-certificates-v1.json \
	    --output "$$d/noncommuting-solver.json" >/dev/null && \
	  $(PY) -c 'import json,sys; r=json.load(open(sys.argv[1])); c=r["status_counts"]; assert r["schema_version"] == "adaivy.phase5-noncommuting-exact-solver-report.v1"; assert c["discovered_and_exactly_verified"] == 7 and c["unresolved_unsupported_shape"] == 1, c; assert r["exact_verifier_is_final_authority"] is True; assert r["general_noncommuting_convergence_answered"] is False; assert r["tolerance"] is None and r["uses_floating_point"] is False and r["uses_model"] is False and r["uses_network"] is False' "$$d/noncommuting-solver.json" && \
	  rm -rf "$$d" && \
	  printf 'phase 5 ok (diagonal QD-FS-01 computed; supplied certificates verified; bounded exact solver discovered 7 certificates; cubic boundary unresolved)\n'

# Separate, spike-only numerical comparison. The forced fail-closed leg is the
# offline assertion: absent engines are recorded and never counted as a pass.
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
	    printf 'That is the expected offline result and is NOT a pass.\n'; \
	    printf 'Use requirements-phase5-sdp-comparison-py314-macos-arm64.txt in a disposable environment.\n'; \
	  fi

# ADR-0034: the recorded generality outcome is asserted, not just the exit
# status. The suite it replaced was a literal table whose pass count could not
# move, so a silent drop from 13 executed controls to 12, an unflipped
# falsifiability probe, a lost positive control, or a suite edited after freezing
# must fail this target rather than pass quietly.
#
# `inspect` and `replay` only read an envelope back; `verify` is the clean-room
# re-derivation added by ADR-0044. It reruns the held-out case, re-derives every
# record and release identity, and refuses a bundle it cannot reproduce, so a
# re-sealed tamper fails here rather than being ingested. It writes nothing.
phase6:
	@printf '\n== phase 6 confirmatory evaluation and release ==\n'
	@d=$$(mktemp -d "$(TMPROOT)/adaivy-p6.XXXXXX") && \
	  $(PY) -m math_research.cli phase6 demo "$$d/workspace" \
	    fixtures/phase6/confirmatory-protocol-v1.json \
	    fixtures/phase5/quantum-diagonal-v1.json \
	    $(PHASE5_INSTANT) $(PHASE6_INSTANT) --output-dir "$$d/out" >/dev/null && \
	  $(PY) -m math_research.cli phase6 inspect "$$d/out/phase6-export.json" >/dev/null && \
	  $(PY) -c 'import json,sys; r=json.load(open(sys.argv[1])); p=json.load(open(sys.argv[2])); s=r["confirmatory_result"]["generality_controls"]; assert r["confirmatory_result"]["status"] == "passed", "phase 6 confirmatory status moved: %s" % r["confirmatory_result"]["status"]; assert (r["controls_total"], r["controls_passed"]) == (13, 13), "phase 6 generality control count moved: %s" % [r["controls_total"], r["controls_passed"]]; assert (r["probes_total"], r["probes_flipped"]) == (13, 13), "phase 6 falsifiability probe count moved: %s" % [r["probes_total"], r["probes_flipped"]]; assert r["positive_control_admitted"] is True, "phase 6 lost its positive control"; assert r["control_corpus_provenance"] == "project_authored", "phase 6 control corpus provenance moved"; assert r["baseline_comparison"]["is_generality_measure"] is False, "phase 6 baseline comparison must not claim to measure generality"; assert (r["heldout_accesses"], r["adaptations_after_access"]) == (1, 0), "phase 6 held-out access ledger moved: %s" % [r["heldout_accesses"], r["adaptations_after_access"]]; assert r["generality_suite_hash"] == p["generality_suite_hash"] == s["suite_hash"], "phase 6 executed a suite the protocol did not freeze"; assert set(s["categories_covered"]) >= {"cross_representation_problems","false_conjectures","inapplicable_citations","known_theorems","missing_assumption_traps","semantic_mistranslations"}, "phase 6 suite dropped a section 18.4 category: %s" % s["categories_covered"]' \
	    "$$d/out/release.json" fixtures/phase6/confirmatory-protocol-v1.json && \
	  $(PY) -m math_research.cli phase5 export "$$d/workspace" \
	    "$$d/out/phase5-export.json" >/dev/null && \
	  $(PY) -m math_research.cli phase6 verify "$$d/out/phase6-export.json" \
	    "$$d/out/phase5-export.json" fixtures/phase5/quantum-diagonal-v1.json \
	    > "$$d/out/phase6-verified.json" && \
	  $(PY) -c 'import json,sys; v=json.load(open(sys.argv[1])); assert v["verified"] is True, "phase 6 clean-room replay did not verify"; assert len(v["checks"]) == 15, "phase 6 replay check count moved: %d" % len(v["checks"]); assert [i["field"] for i in v["unverifiable"]] == ["semantic_fidelity", "negative_and_superseded_attempts_retained"], "phase 6 unverifiable set moved: %s" % v["unverifiable"]; assert [i["field"] for i in v["not_derived"]] == ["baseline_comparison", "baseline_comparison.simplest_baseline_passed"], "phase 6 not_derived set moved: %s" % v["not_derived"]; assert not any(i["counted_as_evidence"] for i in v["unverifiable"] + v["not_derived"]), "a named gap was counted as evidence"' \
	    "$$d/out/phase6-verified.json" && \
	  rm -rf "$$d" && \
	  printf 'phase 6 ok (13 generality controls executed; 13 probes flipped; clean-room replay verified, 2 unverifiable + 2 not-derived fields named)\n'

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

# ADR-0065 gives the ADR-0057 campaign the operator entrypoint it never had.
# This target exercises ONLY the zero-network fixture dry path: a scripted
# planner that holds no gateway and calls nothing, an experiment runner that
# executes nothing, and a verifier that records its own absence. It needs no
# network, no model provider, no container runtime and no third-party package,
# it renders into a mktemp directory it deletes, and it never writes into a
# tracked path.
#
# The recorded outcome is asserted rather than the exit status, so nine things
# must fail here rather than pass quietly: a fixture run that names a provider
# other than `fixture`, a program that executes before the ADR-0066
# experiment-sandbox gate passes, a verification that completes while no
# isolated verifier is wired, a guardrail that turns true, a live provider that
# starts without `--execute`, a fixture run that silently accepts a live
# activation flag, a replay whose effect counters were not actually measured, a
# recorded campaign that exceeded one of its own configured bounds, and a ledger
# whose bytes move between two runs on identical inputs. The two frozen instants
# above are inputs, never clock reads; a moving hash means the campaign is no
# longer reproducible from its inputs.
#
# The five replay effect counters below are MEASURED by a CPython audit hook and
# by the injected ports. They used to be literal zeroes compared here against a
# literal zero tuple, which proves nothing; `audit_hook_installed` is asserted
# too, because an unmeasured zero must not read as a measured one.
campaign:
	@printf '\n== ADR-0065 campaign operator entrypoint (offline fixture dry path) ==\n'
	@d=$$(mktemp -d "$(TMPROOT)/adaivy-campaign.XXXXXX") && \
	  $(PY) -m math_research.cli campaign config-create "$$d/config.json" \
	    --campaign-configuration-id config.campaign.offline.v1 \
	    --allowed-tool exact_python \
	    --max-actions 8 --max-tool-runs 3 --max-model-calls 8 \
	    --max-input-tokens 20000 --max-output-tokens 20000 \
	    --max-cost-microusd 1000000 --max-program-bytes 4096 \
	    --max-artifact-bytes 65536 --max-context-bytes 65536 \
	    --max-cpu-milliseconds 1000 --max-wall-milliseconds 2000 \
	    --max-memory-bytes 67108864 --max-output-bytes 65536 \
	    --max-process-count 1 >/dev/null && \
	  $(PY) -m math_research.cli campaign target "$$d/target.json" >/dev/null && \
	  pid=$$($(PY) -c 'import json,sys; print(json.load(open(sys.argv[1]))["problem_id"])' "$$d/target.json") && \
	  shash=$$($(PY) -c 'import json,sys; print(json.load(open(sys.argv[1]))["dossier_content_hash"])' "$$d/target.json") && \
	  ehash=$$($(PY) -c 'import hashlib,sys; print("sha256:" + hashlib.sha256(open(sys.argv[1],"rb").read()).hexdigest())' "$$d/target.json") && \
	  $(PY) -m math_research.cli novelty create before_research "$$pid" "$$shash" \
	    campaign.offline.fixture.v1 operator.repository-owner \
	    $(CAMPAIGN_RECHECK_INSTANT) "$$d/novelty-recheck.json" \
	    --recheck-id recheck.campaign.offline.v1 \
	    --protocol-id protocol.offline.no-search.v1 \
	    --query-term 'even sum' \
	    --searched-source 'none: the offline fixture path performs no search' \
	    --equivalence-check 'none: the offline fixture path performs no equivalent-formulation check' \
	    --evidence-ref evidence.campaign.frozen-target "$$ehash" \
	    --outcome inconclusive --prior-art-relationship unresolved \
	    --prior-resolution unresolved --prior-resolution-verification unresolved \
	    --limitation 'No literature search was performed; this record binds the offline acceptance run and asserts no novelty.' >/dev/null && \
	  $(PY) -m math_research.cli campaign run "$$d/first" campaign.offline.fixture.v1 \
	    --config "$$d/config.json" --recorded-at $(CAMPAIGN_INSTANT) \
	    --novelty-recheck "$$d/novelty-recheck.json" >/dev/null && \
	  $(PY) -m math_research.cli campaign run "$$d/second" campaign.offline.fixture.v1 \
	    --config "$$d/config.json" --recorded-at $(CAMPAIGN_INSTANT) \
	    --novelty-recheck "$$d/novelty-recheck.json" >/dev/null && \
	  cmp -s "$$d/first/campaign.json" "$$d/second/campaign.json" && \
	  cmp -s "$$d/first/campaign-facts.json" "$$d/second/campaign-facts.json" && \
	  $(PY) -m math_research.cli campaign run "$$d/program" campaign.offline.fixture.v1 \
	    --config "$$d/config.json" --recorded-at $(CAMPAIGN_INSTANT) \
	    --novelty-recheck "$$d/novelty-recheck.json" \
	    --fixture-script program-sandbox-refusal >/dev/null && \
	  $(PY) -m math_research.cli campaign inspect "$$d/first" >/dev/null && \
	  $(PY) -m math_research.cli campaign replay "$$d/first" > "$$d/first-replay.json" && \
	  $(PY) -m math_research.cli campaign replay "$$d/program" > "$$d/program-replay.json" && \
	  $(PY) -m math_research.cli campaign export "$$d/first" "$$d/campaign-export.json" >/dev/null && \
	  cmp -s "$$d/first/campaign.json" "$$d/campaign-export.json" && \
	  { $(PY) -m math_research.cli campaign run "$$d/live" campaign.offline.fixture.v1 \
	      --config "$$d/config.json" --recorded-at $(CAMPAIGN_INSTANT) \
	      --novelty-recheck "$$d/novelty-recheck.json" \
	      --provider azure_openai > "$$d/live-refusal.json" || true; } && \
	  { $(PY) -m math_research.cli campaign run "$$d/unbound" campaign.offline.fixture.v1 \
	      --config "$$d/config.json" --recorded-at $(CAMPAIGN_INSTANT) \
	      > "$$d/unbound-refusal.json" || true; } && \
	  { $(PY) -m math_research.cli campaign run "$$d/fixture-live" campaign.offline.fixture.v1 \
	      --config "$$d/config.json" --recorded-at $(CAMPAIGN_INSTANT) \
	      --novelty-recheck "$$d/novelty-recheck.json" --execute \
	      > "$$d/fixture-live-refusal.json" || true; } && \
	  $(PY) -c 'import json,sys; r=json.load(open(sys.argv[1])); p=json.load(open(sys.argv[2])); l=json.load(open(sys.argv[3])); u=json.load(open(sys.argv[4])); x=json.load(open(sys.argv[5])); f=r["facts"]; g=p["facts"]; assert r["verified"] is True and p["verified"] is True, "campaign replay did not verify"; assert (r["model_calls_made"], r["provider_requests_made"], r["tool_calls_made"], r["subprocesses_opened"], r["network_requests"]) == (0, 0, 0, 0, 0), "campaign replay performed work: %s" % r; assert r["effect_measurement"]["audit_hook_installed"] is True and r["effect_measurement"]["mechanism"] == "sys.addaudithook", "campaign replay effect counters were not measured: %s" % r["effect_measurement"]; assert [i["passed"] for i in r["checks"]] == [True] * 10, "campaign replay check set moved: %s" % r["checks"]; assert f["providers"] == ["fixture"], "the offline campaign path named a provider: %s" % f["providers"]; assert f["measurement_status"] == "unavailable", "a scripted campaign reported measured usage: %s" % f["measurement_status"]; assert f["bound_compliance"]["status"] == "within_bounds" and f["bound_compliance"]["exceeded_bounds"] == [] and g["bound_compliance"]["status"] == "within_bounds", "a recorded campaign exceeded its own configured bounds: %s" % f["bound_compliance"]; assert f["action_types"] == ["derive", "inspect_result", "verify", "report"] and f["terminal_action_type"] == "report", "campaign action ledger moved: %s" % f["action_types"]; assert f["isolated_verifier"] == {"status": "absent", "reason": "isolated_campaign_verifier_not_wired", "verifications_completed": 0, "verification_refusals_recorded": 1}, "campaign verified something with no isolated verifier: %s" % f["isolated_verifier"]; assert g["action_types"] == ["derive", "write_program", "run_program", "report"], "campaign program ledger moved: %s" % g["action_types"]; assert g["experiment_sandbox"] == {"status": "pending_gate", "blocking_decision": "ADR-0066", "reason": "experiment_sandbox_gate_not_passed_adr_0066", "programs_recorded": 1, "programs_executed": 0, "execution_refusals_recorded": 1}, "campaign executed generated code or lost its ADR-0066 refusal: %s" % g["experiment_sandbox"]; assert all(v is False or v == 0 for v in f["guardrails"].values()) and all(v is False or v == 0 for v in g["guardrails"].values()), "a campaign guardrail was set"; assert l["status"] == "refused" and l["reason"] == "live_campaign_requires_explicit_execute", "a live campaign started without --execute: %s" % l; assert u["status"] == "refused" and u["reason"] == "fresh_novelty_recheck_required_before_research", "a campaign started without a bound novelty re-check: %s" % u; assert x["status"] == "refused" and x["reason"] == "fixture_provider_refuses_live_activation_flags", "the fixture provider silently accepted a live activation flag: %s" % x' \
	    "$$d/first-replay.json" "$$d/program-replay.json" "$$d/live-refusal.json" \
	    "$$d/unbound-refusal.json" "$$d/fixture-live-refusal.json" && \
	  rm -rf "$$d" && \
	  printf 'campaign ok (4-action ledger closed and byte-reproducible; 0 programs executed pending ADR-0066; 0 verifications; replay MEASURED 0 model/tool/network/subprocess calls via an audit hook; recorded usage within every configured bound)\n'

# ADR-0036: the publication projection renders the manuscript record set into a
# content-addressed bundle and asserts the recorded outcome rather than the exit
# status. Four things must fail this target rather than pass quietly: a claim
# promoted to a theorem the records do not support, a render rule whose
# falsifiability probe stops flipping, a typeset status reported as anything
# other than `not_typeset` when no compile has run, and -- since ADR-0058 -- a
# displayed title that either lost its derived qualifier or gained one the
# records do not support. The counts below are whatever the fixtures produce; a
# fixture is never adjusted to match a number here, the number is moved.
# The first fixture is expected to render ZERO theorems on this path, because
# `make check` deliberately excludes the sealed ADR-0016 Lean runtime, so a
# nonzero theorem count here means the renderer invented one.
publication:
	@printf '\n== publication projection (records -> tex -> bundle) ==\n'
	@d=$$(mktemp -d "$(TMPROOT)/adaivy-pub.XXXXXX") && \
	  $(PY) -m math_research.cli publication render \
	    fixtures/publication/manuscript-v1.json --output-dir "$$d/bundle" >/dev/null && \
	  $(PY) -m math_research.cli publication render \
	    fixtures/publication/manuscript-v1.json --output-dir "$$d/replay" >/dev/null && \
	  $(PY) -m math_research.cli publication inspect "$$d/bundle" \
	    > "$$d/inspect.json" && \
	  diff -r "$$d/bundle" "$$d/replay" >/dev/null && \
	  $(PY) -c 'import json,sys; m=json.load(open(sys.argv[1])); c=m["evidence_class_counts"]; h=m["headline"]; t=open(sys.argv[2],encoding="utf-8").read(); assert m["verified"] is True, "publication bundle did not verify"; assert c["kernel_checked_theorem"] == 0, "publication rendered a theorem with no attestation: %s" % c; assert (c["exact_certificate_proposition"], c["convention_relative_proposition"], c["proposal"]) == (3, 0, 2), "publication evidence class counts moved: %s" % c; assert m["probes_flipped"] == m["probes_total"] and m["probes_total"] >= 27, "publication probes moved: %s of %s" % (m["probes_flipped"], m["probes_total"]); assert h["displayed_title"] == h["title_stem"] and h["qualifiers"] == [], "publication qualified a headline for a manuscript that resolves nothing: %s" % h; assert h["displayed_title"] in t, "the composed headline is not the displayed title"; assert m["typeset_status"] == "not_typeset" and m["pdf_sha256"] is None, "publication reported a typeset PDF without a compile"; assert "no fully Lean-verified Theorems" in t, "publication status block stopped naming the absent fully verified theorems"; assert "no convention-relative Propositions" in t, "publication status block stopped counting the convention-relative rung"; assert "No linked formal artifact has a recorded successful Lean kernel check" in t, "publication status block stopped stating the Lean result"; assert "\\begin{adatheorem}" not in t, "publication emitted a theorem environment"; assert "\\begin{adaconditional}" not in t, "publication emitted a convention-relative environment with no verdict matrix"' \
	    "$$d/inspect.json" "$$d/bundle/paper.tex" && \
	  $(PY) -m math_research.cli publication render \
	    fixtures/publication/manuscript-graffiti-322-v1.json --output-dir "$$d/g322" >/dev/null && \
	  $(PY) -m math_research.cli publication inspect "$$d/g322" \
	    > "$$d/g322-inspect.json" && \
	  $(PY) -c 'import json,sys; m=json.load(open(sys.argv[1])); c=m["evidence_class_counts"]; h=m["headline"]; t=open(sys.argv[2],encoding="utf-8").read(); p=json.load(open(sys.argv[3])); assert m["verified"] is True, "the Graffiti 322 rebuild did not verify"; assert (c["kernel_checked_theorem"], c["exact_certificate_proposition"], c["convention_relative_proposition"], c["proposal"]) == (0, 0, 1, 0), "the rebuild evidence class counts moved: %s" % c; assert "\\begin{adaconditional}" in t, "a convention-relative claim rendered outside adaconditional"; assert "Candidate Counterexample to Graffiti 322" in h["displayed_title"], "the derived headline lost its computed resolution phrase: %s" % h; assert "convention-relative" in h["qualifiers"] and "prior art relationship unresolved" in h["qualifiers"], "the derived headline lost a qualifier the records require: %s" % h; assert h["displayed_title"] != h["title_stem"] and h["displayed_title"] in t, "the derived headline is not the displayed title"; assert "vm.graffiti-322-g14-18.v1" in h["record_refs"] and "recheck.graffiti-322.prior-candidate.v1" in h["record_refs"], "the headline left the ledger without resolving refs: %s" % h; assert m["probes_flipped"] == m["probes_total"] and m["probes_total"] >= 18, "the rebuild probes moved: %s of %s" % (m["probes_flipped"], m["probes_total"]); assert p["status"] == "recorded" and p["source"] == "prior_art_engagement" and p["report_classification"] == "prior_art_relationship_unresolved", "records/prior-art.json reverted to the approval-only key: %s" % p; assert "even\\_excludes\\_v, range\\_distinct\\_count} & \\texttt{4} & \\texttt{3} & \\texttt{refutes}" in t, "the C4 replay row stopped refuting under even_excludes_v"; assert "even\\_includes\\_v, range\\_distinct\\_count} & \\texttt{2} & \\texttt{3} & \\texttt{does\\_not\\_refute}" in t, "the C4 replay row stopped standing under even_includes_v"; assert "source-asserted reading" in t, "the rebuild stopped naming its weakest reading"; assert "No claim in this document is described as source-faithful" in t, "the rebuild stopped disclaiming source fidelity it has not earned"' \
	    "$$d/g322-inspect.json" "$$d/g322/paper.tex" "$$d/g322/records/prior-art.json" && \
	  rm -rf "$$d" && \
	  printf 'publication ok (0 theorems, 3 exact propositions, 2 proposals, 27 probes flipped; rebuild: 1 convention-relative proposition, derived headline, 18 probes flipped; not typeset)\n'

# Explicit networked setup for the separate publication toolchain. The normal
# offline gate never calls this target. Installation stays under gitignored
# `work/`; no system package or application dependency is created.
setup-typeset:
	@printf '\n== install pinned publication typesetter ==\n'
	$(PY) tools/install_publication_typesetter.py

# Separate from `check`: needs the pinned TeX Live engine named in
# config/publication-typeset-toolchain-v1.json. Absent the engine this target
# reports what is missing and exits non-zero by design -- a skipped typeset step
# is never a pass. The compile is bounded, offline, no-shell-escape, and runs
# twice from clean; unless both runs hash identically the PDF is refused.
check-typeset:
	@printf '\n== publication typesetting (requires the pinned TeX Live engine) ==\n'
	@export PATH="$(TYPESET_BIN):$$PATH"; \
	  d=$$(mktemp -d "$(TMPROOT)/adaivy-typeset.XXXXXX") && \
	  $(PY) -m math_research.cli publication render \
	    fixtures/publication/manuscript-v1.json --output-dir "$$d/bundle" >/dev/null && \
	  $(PY) -m math_research.cli publication typeset "$$d/bundle" > "$$d/typeset.json"; \
	  status=$$?; \
	  if [ $$status -ne 0 ]; then \
	    cat "$$d/typeset.json"; \
	    printf 'typeset gate NOT satisfied; its absence is not a pass.\n'; \
	    rm -rf "$$d"; exit $$status; \
	  fi; \
	  $(PY) -c 'import json,sys; m=json.load(open(sys.argv[1])); assert m["typeset_status"] == "typeset" and m["pdf_sha256"], "typeset gate reported no PDF"' \
	    "$$d/typeset.json" && \
	  cp "$$d/bundle/paper.pdf" "$${PUBLICATION_PDF:-./paper.pdf}" && \
	  rm -rf "$$d" && \
	  printf 'typeset ok (byte-reproducible across two clean compiles)\n'

# One supported command for a reader-facing publication report. It always
# projects the records, emits every required Lean source, and typesets the PDF;
# a missing/mismatched engine or incomplete artifact is a hard failure.
MANUSCRIPT ?= fixtures/publication/manuscript-v1.json
PUBLICATION_OUT ?= output/pdf/publication
CAMPAIGN_EXPORT ?=
CAMPAIGN_LINK ?=
publication-build:
	@printf '\n== automatic publication report -> $(PUBLICATION_OUT) ==\n'
	@export PATH="$(TYPESET_BIN):$$PATH"; \
	  $(PY) -m math_research.cli publication build "$(MANUSCRIPT)" \
	    --output-dir "$(PUBLICATION_OUT)" \
	    $(if $(CAMPAIGN_EXPORT),--campaign-export "$(CAMPAIGN_EXPORT)") $(if $(CAMPAIGN_LINK),--campaign-link "$(CAMPAIGN_LINK)")

# `make report` is the durable counterpart to `make check`. The phase targets are
# GATES: they render into a mktemp directory and delete it, because writing into a
# tracked path on every check would churn the repo. This target does the same work
# and KEEPS it.
#
# Output lands in reports/local/, which .gitignore excludes. That subtree is the
# boundary: a path under reports/local/ is a local run, and a path anywhere else
# under reports/ is recorded evidence that an ADR may cite. Never move a local run
# into the evidence tree -- promote it by copying it to reports/<phase>/<version>/
# and committing it deliberately.
#
# Workspaces go to work/, also gitignored. They are append-only sqlite state that
# a run needs and no reader does, and a fresh directory per run is required
# because replaying an identical record into an existing workspace is refused by
# design. Reader-facing publication output is different: it is automatically
# projected and compiled here and therefore requires the pinned typesetter.
report:
	@printf '\n== local report -> $(OUT) ==\n'
	@out="$(OUT)"; work="$(WORK)"; \
	  mkdir -p "$$out/phase2" "$$out/phase4c" "$$out/phase4d" "$$out/phase5" "$$out/synthesis" "$$work" && \
	  $(PY) -m math_research.cli demo --output-dir "$$out/phase1" >/dev/null && \
	  $(PY) -m math_research.cli phase2 report reports/phase-2 run.phase2.demo.fake.v1 \
	    --output "$$out/phase2/traceable-report.md" >/dev/null && \
	  $(PY) -m math_research.cli phase3a demo "$$work/p3a" \
	    --output-dir "$$out/phase3a" >/dev/null && \
	  $(PY) -m math_research.cli phase4c benchmark --fixtures fixtures/phase4c \
	    --output "$$out/phase4c/hybrid-retrieval-report.json" >/dev/null && \
	  $(PY) -m math_research.cli phase4d search \
	    fixtures/phase4d/grounded-terminology-v1.txt \
	    --term 'quantum state discrimination' --term 'spectral projector' \
	    --config config/phase4d-crossref-public-discovery-v1.json \
	    --observed-at-epoch 0 \
	    --output "$$out/phase4d/public-discovery-dry-run.json" >/dev/null && \
	  $(PY) -m math_research.cli phase5 run "$$work/p5" \
	    fixtures/phase5/quantum-diagonal-v1.json $(PHASE5_INSTANT) \
	    --output "$$out/phase5/diagonal-run.json" >/dev/null && \
	  $(PY) -m math_research.cli phase5 verify-noncommuting "$$work/p5nc" \
	    fixtures/phase5/noncommuting-certificates-v1.json $(PHASE5_INSTANT) \
	    --output "$$out/phase5/noncommuting-run.json" \
	    --report "$$out/phase5/report.md" >/dev/null && \
	  $(PY) -m math_research.cli phase5 solve-noncommuting \
	    fixtures/phase5/noncommuting-certificates-v1.json \
	    --output "$$out/phase5/noncommuting-solver.json" >/dev/null && \
	  $(PY) -m math_research.cli phase6 demo "$$work/p6" \
	    fixtures/phase6/confirmatory-protocol-v1.json \
	    fixtures/phase5/quantum-diagonal-v1.json \
	    $(PHASE5_INSTANT) $(PHASE6_INSTANT) --output-dir "$$out/phase6" >/dev/null && \
	  $(PY) -m math_research.synthesis_cli export "$$work/synthesis" \
	    "$$out/synthesis/synthesis-export.json" >/dev/null && \
	  export PATH="$(TYPESET_BIN):$$PATH" && \
	  $(PY) -m math_research.cli publication build \
	    fixtures/publication/manuscript-v1.json --output-dir "$$out/publication" >/dev/null && \
	  $(PY) -m math_research.report_index "$$out" --recorded-at "$(REPORT_INSTANT)" && \
	  printf '\nreport written to %s -- open %s/INDEX.md\n' "$$out" "$$out"

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

# ADR-0066 campaign experiment sandbox for model-authored code.
#
# Deliberately NOT part of `check`. The offline probes in the same test module
# already run under `make check` and need no runtime; this target adds only the
# KERNEL enforcement claims, which require both a container runtime and an
# owner-pinned digest in config/campaign-experiment-oci-image-*.json.
#
# The shipped pin carries `digest_status: unresolved`, so this target FAILS
# loudly today rather than skipping: an unpinned digest is a refusal, never a
# fallback. It turns green only after the owner resolves the digest.
#
# It is a distinct image and a distinct profile from check-phase4b-oci; ADR-0057
# section 2 forbids reusing the parser sandbox for generated code, and pinning
# the parser digest here is itself a refusal.
.PHONY: check-campaign-experiment-oci
check-campaign-experiment-oci:
	@printf '\n== ADR-0066 campaign experiment sandbox (needs the owner-pinned image) ==\n'
	@docker_bin=$$(command -v docker) && \
	  docker_host=$$(docker context inspect --format '{{.Endpoints.docker.Host}}') && \
	  ADAIVY_CAMPAIGN_EXPERIMENT_OCI_DOCKER="$$docker_bin" \
	  ADAIVY_CAMPAIGN_EXPERIMENT_OCI_DAEMON="$$docker_host" \
	  ADAIVY_CAMPAIGN_EXPERIMENT_OCI_LOCK='config/campaign-experiment-oci-image-linux-arm64-v1.json' \
	  $(PY) -m unittest tests.test_campaign_experiment_sandbox

clean:
	find . -name __pycache__ -type d -prune -exec rm -rf {} + 2>/dev/null || true
	find . -name '*.sqlite3-shm' -o -name '*.sqlite3-wal' | xargs rm -f 2>/dev/null || true
