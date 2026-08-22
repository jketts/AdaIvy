# ADR-0081: Literature discovery at scale — paginated policy-authorized search, depth-one following, batch acquisition

- **Status:** accepted 2026-08-22
- **Date:** 2026-08-22
- **Blueprint requirement:** Phase 4 terminology expansion and literature
  discovery at volume; `docs/CAMPAIGN_DEPTH_AND_BREADTH_PLAN.md` Slice 14
- **Decision owners:** repository owner
- **Supersedes:** ADR-0051's per-search human acknowledgement, per-query
  operator-confirmed hash, hash-pinned single-request configuration, ten-result
  cap, and Crossref-only provider scope — for the new v2 capability only. Every
  ADR-0051 v1 record, and the v1 code path that produced it, remains valid and
  untouched. ADR-0051's untrusted-candidate status, transport controls, exact
  substring grounding, and no-inference-from-rank rules all stand in v2.
- **Implements:** ADR-0068 (depth-one discovery-result following), which was
  accepted but unimplemented. All six ADR-0068 controls are enforced here.

## Context

ADR-0051 activated discovery as one human-acknowledged Crossref request
returning at most ten candidates, each query hash confirmed live by an
operator. That posture proved the transport and grounding discipline but makes
literature coverage for a hard target structurally unreachable: hundreds of
relevant works cannot be found ten at a time with a human keystroke per
request. ADR-0068 separately accepted depth-one following of discovery results
but no implementation existed (`max_followed_per_run` appeared nowhere in
`src/`). Phase 4B public acquisition likewise permitted exactly one
human-typed URL per run.

The Slice 14 stance is the plan's general one: freedom inside the boundary,
rigor at the boundary. Wider search is a budgeted cost, not a trust event.

## Decision

### 1. Paginated, budgeted v2 discovery (new capability alongside v1)

`capability.phase4d.public-scholarly-discovery.v2`, pinned in
`config/phase4d-public-discovery-v2.json` and enforced field-for-field by
`math_research.phase4d.discovery_v2.load_config_v2`:

- three credential-free providers behind one transport port
  (`phase4d/ports.py`): Crossref (cursor), arXiv Atom API (start/max_results,
  stdlib XML with DOCTYPE/ENTITY refusal), OpenAlex (cursor);
- cursor/offset pagination with a hard per-run budget in **requests and
  response bytes**, plus candidate, query, and page caps, all pinned;
- per-provider minimum request intervals recorded in every ledger entry and
  enforced through an injected clock/sleeper port; waits are operational data,
  hashed into `operational_hash`, never into `content_hash`;
- every request — including the refused over-budget one — ledgered with
  provider, query hash, cursor, URL, byte count, response hash, and outcome;
- results deduplicated per `(provider, provider_id)`, ranked by arrival order,
  and always `untrusted_inspiration_candidate` with
  `acquisition_authorized: false` and every assessment `not_assessed`;
- `verify_report_v2` recomputes hashes, candidate identities, exact request
  and byte accounting, budget bounds, and refuses any float anywhere in the
  report.

The v1 module, config, CLI path, and acceptance tests are untouched; v1
reports remain verifiable under their own pinned hash.

### 2. Query-policy authorization replaces per-query acknowledgement

One human-final operator authorization now covers a content-hashed **query
policy** (`phase4d/policy.py`): the grounding sources (content-addressed), the
term-expansion rule, the provider allowlist, the run budget, and the query
cap. The authorization is recorded once per policy hash.

Term expansion may propose any candidate term, but a term survives only as an
exact NFKC-casefolded substring of an authorized grounding source — no free
generation. Every generated query is ledgered with its grounding evidence:
source id, source hash, and the exact character span in the normalized source.
An ungrounded term refuses the whole query before any DNS resolution.

Discovery grants **inspection authority only**. Acquisition authorization
remains a separate rights-checked Phase 4A/4B step; no discovery output can
set `acquisition_authorized` true.

### 3. Depth-one result following (implements ADR-0068)

`phase4d/following.py` enqueues references/DOIs/links from *already acquired*
document metadata as discovery candidates, never fetching here, under the six
ADR-0068 controls:

1. content-hashed human-maintained host allowlist, checked per reference;
2. depth exactly one — any record carrying a followed-provenance marker is
   refused as an origin (`pr.follow-depth-two-refused`);
3. no credentials exist on this path at all;
4. DOI targets resolve only to `https://doi.org/...`; URL targets must be
   HTTPS with no query string or fragment;
5. `max_followed_per_run` is pinned per call and overflow is retained as
   machine-readable `refused_fanout_bound` records, not silently dropped;
6. every followed candidate records `origin_selected_by: "automation"` and its
   provenance edge (origin document, reference field, index, value); a record
   claiming human selection fails verification
   (`pr.follow-records-automation`).

Followed candidates stay `untrusted_inspiration_candidate` with all
assessments `not_assessed` and no acquisition authorization
(`pr.follow-grants-no-rights`, `pr.follow-class-unchanged`).

### 4. Batch public acquisition under one plan-level approval

`config/phase4b-public-acquisition-activation-v2.json` activates
`capability.phase4b.live.batch` (`phase4b/batch_acquisition.py`): up to 32
allowlisted exact URLs across at most 4 origins per run, under pinned
request/byte/time budgets. The human final approval moves to the **plan**
level — one acknowledgement and one confirmed content hash cover the batch —
while the per-URL discipline is unchanged from ADR-0050: HTTPS only, no
redirects (a 3xx is a per-URL `redirect_refused` failure), no query strings,
no request headers, no credentials, per-URL rights decisions inside the
approved plan, and one ledger record per URL with byte count and body hash.
`origin_selected_by` is recorded per URL; automation-selected URLs must carry
their ADR-0068 provenance edge. The v1 single-URL activation remains valid.

### 5. Verification

`verify_report_v2`, `verify_followed`, and `verify_batch_report` mirror the v1
`verify_report` posture: schema and pinned-identity checks, exact accounting,
candidate caps, trust-promotion detection under rehashing, and float refusal.
`make check` remains fully offline; all acceptance tests run against fake
transports.

## What this does not change

- No model call, scheduling, personalization, crawling beyond depth one,
  credentialed provider, or general web engine.
- No inference from search rank or retrieval volume to relevance,
  applicability, novelty, significance, or warrant.
- Live network execution still requires the explicit opt-in permit, transport,
  and named operator gates; nothing here activates a live effect by default.
- ADR-0068's residual-risk section stands unedited: the allowlist bounds
  reach, not content, and the first unintended model influence from a followed
  document reopens that decision.

## Consequences

- A campaign can discover and rank several hundred candidates per run under an
  attributable budget, with every request traceable to a ledgered query and
  every query traceable to grounding spans in an authorized source.
- The operator's per-search keystroke is gone; the operator's authority is
  not. It moved to the policy hash, the follow allowlist, and the batch plan
  hash — fewer, better-audited decisions.
- Two capabilities now exist side by side in Phase 4D; reports name their
  schema and config hash, so provenance never confuses v1 and v2 output.

## Validation and revisit trigger

Offline acceptance requires: a multi-page sweep across multiple fake providers
accumulating several hundred ranked candidates under budget; a ledgered
refused over-budget request; a refused ungrounded query term; recorded and
enforced per-provider intervals; depth-one following with an enforced cap and
retained refusals; a batch plan whose single approval covers N URLs with
per-URL records; and rehashed trust-promotion detection in every verifier.

Revisit with a new ADR before: adding a provider, credentials, or model-issued
*authorization* (as opposed to model-proposed terms); raising follow depth
above one; letting discovery output authorize acquisition; widening any pinned
budget ceiling; or removing the plan-level human approval from batch
acquisition.
