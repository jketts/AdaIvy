# ADR-0050: Activate public unauthenticated Phase 4B acquisition

- **Status:** accepted and implemented 21 August 2026
- **Date:** 2026-08-21
- **Blueprint requirement:** Section 7 acquisition adapters; ADR-0028 final
  activation condition
- **Decision owners:** repository owner

## Context

ADR-0028 implemented an opt-in HTTPS adapter but deliberately left production
activation to a later owner action. The exact Linux/arm64 OCI parser gate now
passes and the separately acknowledged live HTTPS observation has executed.
`reports/phase-4b-activation/activation-evidence.json` strictly combines those
results and has status `evidence_complete_pending_owner_activation` with no
activation effect of its own.

The owner has now requested live fetching so AdaIvy can begin investigations,
while limiting the first operating scope to work reachable without journal or
repository credentials. Public reachability is not a licence determination:
ADR-0017 remains authoritative that possession or accessibility does not imply
rights. Acquisition and storage therefore still require explicit human-final
per-use decisions.

## Options considered

| Option | Evidence | Benefits | Costs/risks | Hard gates |
|---|---|---|---|---|
| Keep the live adapter pending | Complete activation evidence | No new live operation | Prevents direct acquisition | None |
| Activate unrestricted browsing or crawling | None | Broad discovery | Autonomous origin selection, rights and traffic scope are unmeasured | Rejected |
| Activate credentialed repositories | Existing provider credential patterns only | Access to subscription sources | New secret, session and publisher-policy surface | Rejected for this slice |
| Activate exact-URL public unauthenticated GET | Complete ADR-0028 evidence | Enables controlled source fetching now | Human plans and rights decisions remain a throughput constraint | Selected |

## Decision

Activate the existing Phase 4B HTTPS port under the content-hashed owner record
`config/phase4b-public-acquisition-activation-v1.json`. The activated scope is
exactly:

- one exact URL and one exact origin per invocation;
- HTTPS `GET`, public unauthenticated access, no query string, redirect,
  caller-supplied request header, or retry;
- no credentials in URLs, headers, cookies, proxies, or configuration, and no
  credential reads from the ambient environment;
- no crawling, link following, discovery, scheduling, or autonomous origin
  selection;
- one content-hashed, human-final plan and an exact operator acknowledgement on
  every executed invocation; the plan time must be within five minutes of the
  execution clock;
- current terms, robots, acquisition-right and storage/retention-right evidence;
- Phase 4A append-only rights records and the Phase 4B source-specific deletable
  content boundary for every retained byte.

Every invocation appends Phase 4A rights records that durably retain the full
activation and exact-plan hashes, including when an older allowed decision
already exists. The candidate links to those current rights decisions; failures
are retained in the same source-scoped workspace and timestamp. A replayed
workspace therefore retains the authorization chain even if CLI output is lost.

`phase4b public-acquire` is a non-mutating dry run unless `--execute`, the exact
network acknowledgement, and the exact plan hash are all supplied. A plan's
human-final rights declarations append invocation-specific Phase 4A acquisition
and storage/retention decisions. An existing decision is never overwritten: any
existing blocking decision fails before DNS or transport construction can have
an effect.

The live result is still an untrusted acquisition candidate. It creates no
applicability decision, graph admission, mathematical warrant, novelty or
significance assessment, publication right, or redistribution right. Parsing
remains a separate operation through the digest-pinned no-network OCI boundary.

## Consequences

AdaIvy can persist openly reachable exact sources without credentials while
keeping `make check` completely offline. The activation record is bound to the
existing combined evidence hash, so replacing or weakening that evidence does
not silently preserve activation.

This does not make AdaIvy a crawler and does not discover literature. A human or
separately approved discovery adapter must still select each URL and supply the
terms, robots and rights evidence. “Public unauthenticated” describes transport
access only; it does not mean open licence, permission to redistribute, or
permission to publish excerpts.

## Blueprint deviation

None. This is the explicit final owner action reserved by ADR-0028. It narrows
the already approved adapter and does not add an acquisition adapter, media
type, dependency, or autonomous selector.

## Validation and revisit trigger

The activation remains valid while:

- the activation record verifies against the exact combined Phase 4B evidence;
- dry run performs no network operation and creates no workspace;
- credential-bearing, header-bearing, retrying, stale, or multi-request plans,
  and existing blocking rights, all fail before I/O;
- execution persists candidate bytes only in the deletable content boundary and
  keeps them out of canonical exports; and
- `make check` remains network-free and green.

Revisit with a new ADR before admitting credentials, cookies, proxy state,
publisher sessions, autonomous discovery, crawling, more than one request per
invocation, scheduled acquisition, a larger bound, or a new rights inference.
