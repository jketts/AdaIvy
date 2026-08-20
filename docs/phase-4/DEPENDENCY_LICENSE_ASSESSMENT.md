# Phase 4A Dependency and License Assessment

Status: owner-approved gate-only amendment; no production authorization
Date: 2026-08-20
Owner-approval SHA-256: `98244f19de93af73e220dd0d57b0a9b70921f0b8381e0e7b2cc2c2fa47b8846b`

## Production and ordinary-development boundary

Phase 4A adds **zero production dependencies**. The five packages below exist
only in a newly created disposable gate virtual environment. They are not
installed into the repository `.venv`, system Python, user site, ordinary
development environment, or a production import path. The Phase 2 provider
requirements remain unchanged. Unsupported Python, ABI, OS, or architecture
fails closed.

## Approved platform and acquisition observation

- Python: CPython 3.14.4; ABI `cpython-314-darwin`
- OS/architecture: macOS 26.5.2 ARM64, satisfying macOS 11.0+
- pip: 26.0.1
- Manifest: `requirements-phase4-gate-py314-macos-arm64.txt`
- Manifest SHA-256: `5467b0a521e823b183622961ad4a18aa8536a9172afd2c3ecffb10ffc5436295`
- Canonical wheel-inventory SHA-256:
  `ee7e03544b123fd6a647bd0d8e5f87b0a2fcff25442fe216aee02677eb431962`

Acquisition used only `pypi.org` and `files.pythonhosted.org`, binary-only
resolution, hash enforcement, and no cache. Exactly five files were returned;
there were no additional files or source distributions. Every official PyPI
provenance endpoint returned HTTP 200 with one attestation bundle.

| Package/version | Exact wheel | Bytes | SHA-256 | License | Role |
|---|---|---:|---|---|---|
| jsonschema 4.26.0 | `jsonschema-4.26.0-py3-none-any.whl` | 90,630 | `d489f15263b8d200f8387e64b4c3a75f06629559fb73deb8fdfb525f2dab50ce` | MIT | Direct Draft 2020-12 gate validator |
| attrs 26.1.0 | `attrs-26.1.0-py3-none-any.whl` | 67,548 | `c647aa4a12dfbad9333ca4e71fe62ddc36f4e63b2d260a37a8b83d2f043ac309` | MIT | Transitive runtime dependency |
| jsonschema-specifications 2025.9.1 | `jsonschema_specifications-2025.9.1-py3-none-any.whl` | 18,437 | `98802fee3a11ee76ecaca44429fda8a41bff98b00a0f2838151b113f210cc6fe` | MIT | Transitive local metaschemas/vocabularies |
| referencing 0.37.0 | `referencing-0.37.0-py3-none-any.whl` | 26,766 | `381329a9f99628c9069361716891d34ad94af76e461dcb0335825aecc7692231` | MIT | Transitive local reference resolution |
| rpds-py 2026.6.3 | `rpds_py-2026.6.3-cp314-cp314-macosx_11_0_arm64.whl` | 339,495 | `d7469697dce35be237db177d42e2a2ee26e6dcc5fc052078a6fefabd288c6edd` | MIT | Transitive compiled persistent structures |

No format extras were selected, so their optional dependency graph is absent.
Binary-only selection avoids Rust/build-system dependencies from the rpds-py
source distribution.

## Offline installation and validation

After independent filename, count, byte-length, and SHA-256 checks, network use
stopped. Installation used `--no-index`, `--find-links` pointing only at the
verified disposable wheel directory, `--require-hashes`, and
`--only-binary=:all:`. `importlib.metadata` returned exactly the five versions
above. All schema and gate execution then ran in the disposable environment
under the restricted command sandbox, with zero remote schema retrievals.

The validator is explicitly
`jsonschema.validators.Draft202012Validator`. The gate calls `check_schema`,
rejects any draft other than Draft 2020-12, rejects every non-internal `$ref`
before constructing the validator, enumerates errors deterministically, and
performs matching standard-library timestamp/domain validation. No `format`
behavior is assumed.

## Other artifacts and deferrals

The 16 evaluation fixtures and 31 contract/adversarial cases are project-
authored under `LicenseRef-AdaIvy-Synthetic-Fixture`; local contract testing and
redistribution are allowed. No real research corpus is included. The deferred
embedding model, parser, crawler, archive, vector, scheduler, and provider
packages remain unapproved and absent.

Removal consists of deleting the disposable environment and wheel directory;
the repository retains only the requirements manifest and documentary hashes.
