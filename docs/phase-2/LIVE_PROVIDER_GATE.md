# Phase 2 Live-Provider Gate Configuration

The live-gate CLI loads `OPENAI_API_KEY` from the repository-root `.env` file
when the process environment does not already contain it. Copy `.env.example`
to `.env`, replace the blank value, and restrict the file to the current user:

```bash
cp .env.example .env
chmod 600 .env
```

The populated file is ignored by Git. It accepts only `OPENAI_API_KEY`, performs
no interpolation or command substitution, and never overrides a credential
already present in the process environment. The key must never appear in
versioned configuration, artifacts, events, database fields, logs, or reports.

Provider/model selection is explicit non-secret run configuration. Required
keys are:

- `schema_version`
- `configuration_id`
- `provider`
- `model_identifier`
- `pricing_snapshot_id`
- `call_timeout_milliseconds`
- `per_call_input_token_reserve`
- `per_call_output_token_reserve`
- `budget.max_input_tokens`
- `budget.max_output_tokens`
- `budget.max_cost_microusd`
- `budget.max_wall_milliseconds`
- `budget.max_attempts`
- `content_hash`

The versioned pricing snapshot is non-secret and must be created explicitly.
Required keys are:

- `schema_version`
- `snapshot_id`
- `provider`
- `model_identifier`
- `source`
- `captured_at`
- `currency`
- `units`
- `input_microusd_per_million_tokens`
- `output_microusd_per_million_tokens`
- `content_hash`

The creation commands take operator-supplied values and never fetch pricing:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m math_research.cli phase2 pricing-create <pricing-snapshot.json> --snapshot-id <opaque-id> --provider openai --model <model-id> --source <pricing-source> --captured-at <ISO-8601-timestamp> --currency USD --input-microusd-per-million-tokens <integer> --output-microusd-per-million-tokens <integer>

PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m math_research.cli phase2 live-config-create <live-run-config.json> --configuration-id <opaque-id> --provider openai --model <model-id> --pricing-snapshot-id <opaque-id> --call-timeout-milliseconds <integer> --per-call-input-token-reserve <integer> --per-call-output-token-reserve <integer> --max-input-tokens <integer> --max-output-tokens <integer> --max-cost-microusd <integer> --max-wall-milliseconds <integer> --max-attempts <integer>
```

Run the non-mutating preflight, then the exact two-call gate:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m math_research.cli phase2 live-preflight --config <live-run-config.json> --pricing-snapshot <pricing-snapshot.json>

PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m math_research.cli phase2 live-gate <workspace> <run-id> --config <live-run-config.json> --pricing-snapshot <pricing-snapshot.json>
```

The gate uses the small known-valid even-sum fixture. A same-model, same-provider
verifier is recorded as a separate, context-isolated call and is not labeled
provider-independent or fully independent.

## Recorded provider-boundary acceptance

The failed v1 and v2 attempts are immutable history. In particular, never reuse
`run.phase2.live.openai.gpt5-mini.v2` or
`reports/phase-2/live-openai-gpt5-mini-v2`. The v2 diagnostic identified a
provider-only missing-type defect on scalar const/enum terminals. ADR-0011
records the bounded repair and numeric inference policy. The v3 run subsequently
passed. Never reuse its run ID or workspace either. Install the pinned optional
SDK explicitly for any separately authorized future run:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-phase2-provider.txt
```

Generate the deterministic provider schema, transformation manifests, and both
machine/human compatibility reports without network access:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m math_research.cli phase2 provider-schema-report reports/phase-2/provider-compatibility
```

The provider projection follows the current official
[OpenAI Structured Outputs documentation](https://developers.openai.com/api/docs/guides/structured-outputs).
It is only a request compatibility schema. It is not the canonical interchange
or trust schema. Every response must still pass the unchanged canonical schema,
target/reference checks, and proposal-only policy.

The exact commands below are retained only as the v3 historical execution
record. Do not rerun them:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python -m math_research.cli phase2 live-preflight --config config/phase2-live-gpt5-mini-v3.json --pricing-snapshot config/openai-gpt5-mini-pricing-2026-08-19.json

PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python -m math_research.cli phase2 live-gate reports/phase-2/live-openai-gpt5-mini-v3 run.phase2.live.openai.gpt5-mini.v3 --config config/phase2-live-gpt5-mini-v3.json --pricing-snapshot config/openai-gpt5-mini-pricing-2026-08-19.json
```

The v3 run recorded two successful calls, proposal-only imports, isolated
verifier context, API usage and snapshot-based estimated cost, restart replay,
and zero credential-leak matches. Any future live attempt requires a new
configuration identifier, workspace, and run ID.
