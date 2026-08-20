# Phase 4B Entry-Gate Report

Status: **owner accepted; implementation evidence pending**

Date: 2026-08-20

Scope: authorized HTTPS acquisition and isolated rich parsing only

## Gate result

The owner accepted the architecture gate and bounded implementation is in
progress. The feasible offline harness executes the acquisition policy engine,
fixture parser oracle, all six lifecycle/integration fixtures through production
service and persistence paths, preservation checks, and deterministic replay,
but it is not the complete Phase 4B gate. Production activation remains
blocked until the acceptance suite supplies machine-readable evidence for every
threshold and control.

The accepted delivery dependency is Phase 4A -> Phase 4B -> Phase 4C. Phase 4B
must not implement hybrid retrieval or allow its parser choices to determine a
future index design.

## Baseline

- Phase 4A rights, human applicability, deletable content, and protected
  evidence remain authoritative.
- Phase 3A canonical memory and FTS5 are unchanged.
- Phase 3B's v5 runtime, Phase 5, Phase 6, and synthesis are sealed inputs.
- `make check` is the ordinary offline baseline; live network is never part of
  documented acceptance.
- ADR-0027, not the stale blueprint header/C17 label, is authoritative for the
  implemented synthesis status.

## Authorized capability

1. A human creates a bounded acquisition run containing no more than four
   exact normalized HTTPS origins and 100 requested resources.
2. Current terms, robots, and Phase 4A acquisition and retention rights are
   checked before each fetch.
3. An outward adapter validates DNS, connected address, redirect, headers,
   content type, compressed/raw bytes, decoded bytes, rate, retry, and total-run
   budgets.
4. Bytes are stored only in a source-specific Phase 4 content object.
5. A format-selected isolated worker proposes structured HTML, bounded TeX, or
   born-digital PDF segments with exact source anchors. Dependency-free strict
   candidates now cover HTML, non-expanding TeX, and a narrow classic,
   uncompressed PDF subset through source-bound Darwin workers. They remain
   pre-activation; the standard-library fallback remains a fixture oracle only.
6. Policy admits the proposal or quarantines it. No parser result receives
   applicability or mathematical authority.

## Gate conditions

The gate passes only when all are true:

- the 30-fixture manifest and expected outcomes are content-hashed;
- all `P4B-AT-001` through `P4B-AT-040` pass exactly;
- all `P4B-SC-001` through `P4B-SC-030` are exercised on the actual boundary;
- the dependency closure, licenses, hashes, imports, and offline installation
  match the accepted dependency assessment;
- initial run, three repeats, restart, replay, and reverse-order rebuild produce
  the required identical semantic outputs;
- the acceptance transport proves zero socket/DNS/network/API/model activity;
- deletion removes source and reconstructive parse plaintext from every managed
  store while preserving immutable non-content audit identity;
- every earlier offline check stays green and protected evidence is unchanged.

## Parallel work permitted before activation

The acquisition adapter/fake transport, individual parser spikes, and fixture
construction may proceed independently after their shared schemas and bounds
are frozen. Persistence integration, deletion projection, and the final
end-to-end path must be reviewed together. Phase 4C implementation, live corpus
acquisition, and benchmark use remain blocked until this gate passes. The
feasible report also records a passing named-Darwin denial probe without
counting it as parser-sandbox activation. The disposable exact-hash dependency
inventory passed, but neither preferred parser met the activation probes;
all three strict in-repo candidates are connected to the Darwin resource runner.
The actual-corpus authorization harness now exercises all twelve parser fixtures
through those workers and records exact media/profile/content bindings and
semantic hashes. Current named-Darwin evidence records twelve exact disposition
matches out of twelve and zero false admissions. The positive PDF fixtures are
now deterministic valid strict-subset PDFs; adversarial negatives are unchanged.
The versioned worker protocol distinguishes parser content rejection, which
becomes a content-free `quarantined/rejected` result, from infrastructure or
worker failure, which remains `failed`. This clears the actual-corpus
parser-profile authorization measurement without configuring or activating a
production worker. Strict transient-memory enforcement, portable enforcement,
and the external live HTTPS operator gate remain incomplete.
Acquisition attempt traces and non-reconstructive rich-proposal
metadata now replay canonically in the v2 audit export; source and parsed prose
remain outside immutable exports so deletion stays meaningful.

The live gate now has a content-hashed plan, redacted evidence schema, and CLI.
Plan verification performs no network operation; execution additionally
requires the exact `I_ACKNOWLEDGE_PHASE4B_LIVE_NETWORK` acknowledgement. No
external gate has been run by the ordinary offline suite.
