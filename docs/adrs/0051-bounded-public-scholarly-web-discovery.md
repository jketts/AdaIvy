# ADR-0051: Bounded public scholarly web discovery

- **Status:** accepted and implemented 21 August 2026
- **Date:** 2026-08-21
- **Blueprint requirement:** Phase 4 terminology expansion and literature
  discovery; ADR-0050 revisit trigger
- **Decision owners:** repository owner

## Context

ADR-0050 activated public unauthenticated acquisition only after a human had
selected one exact URL. That boundary supports faithful acquisition but leaves
no way to discover an unknown work. The owner has now explicitly authorized web
search to aid discovery, on the understanding that results can be inspiring
even when they are irrelevant or unusable.

Search and acquisition have different risks. A search result is not the source
it describes, does not establish that source's claims, and does not determine
whether the source applies to the research problem. Automatically following
results would also combine discovery, rights review, and acquisition into one
authority. This slice therefore activates search while keeping those stages
separate.

## Options considered

| Option | Benefit | Cost/risk | Decision |
|---|---|---|---|
| Keep discovery fully manual | No new network surface | AdaIvy cannot help locate unfamiliar work | Rejected |
| General search-engine scraping and result crawling | Broad coverage | Unstable markup, unknown terms, autonomous traversal, broad traffic and rights surface | Rejected |
| One bounded query to a public scholarly metadata API | Useful terminology-led literature discovery with a narrow auditable surface | Crossref coverage and ranking are incomplete | Selected |
| Credentialed journal search | Subscription coverage | Secrets, sessions, provider contracts, and paywalled content | Deferred |

## Decision

Add Phase 4D public scholarly discovery through the pinned Crossref REST API
configuration in `config/phase4d-crossref-public-discovery-v1.json`.

The activated scope is exactly:

- public unauthenticated Crossref metadata search at one pinned HTTPS origin;
- one operator-initiated request per invocation, at most ten returned
  candidates, twelve query terms, 256 query bytes, a 1 MiB response, and a
  fifteen-second transport deadline;
- every query term must be an NFKC-normalized, case-folded exact substring of a
  supplied local problem or research-context file, making the terminology's
  origin content-addressable and inspectable;
- execution requires a human actor identifier, the exact acknowledgement
  `I_ACKNOWLEDGE_PUBLIC_WEB_DISCOVERY`, and confirmation of the exact grounded
  query hash displayed by the dry run;
- the reviewed provider terms must be no more than thirty days old at execution;
- DNS answers must be globally routable and the existing opt-in TLS transport
  binds the connected peer to the permitted resolution;
- only DOI, title, publisher, and work type survive the untrusted provider
  boundary; the raw response is hashed but not persisted in the report.

The output status is `untrusted_inspiration_candidate`. Relevance,
applicability, novelty, and significance are all `not_assessed`; acquisition is
unauthorized; mathematical warrant is `none`; and graph admission is absent.
An irrelevant result is therefore a valid search observation, not a false
claim. Selecting a result for inspection or source retention requires a new
ADR-0050 Phase 4B plan, terms/robots review, and explicit rights decisions.

This slice performs no result-link fetch, citation traversal, page parsing,
recursive query, query generation, scheduling, personalization, model call, or
credential access. It is search, not crawling. Crossref is the only provider;
adding a general web engine or another scholarly index requires a later ADR and
its own provider-policy review.

## Consequences

AdaIvy can now turn terminology already present in a problem statement or
research note into a small list of publicly discoverable scholarly leads. The
result may broaden a researcher's vocabulary or reveal adjacent work without
being treated as evidence.

The constraint deliberately sacrifices recall. Exact grounding prevents an
untraceable query expansion; one request prevents autonomous search loops; and
the Crossref-only provider excludes ordinary web pages and works missing from
its metadata. Those are recorded coverage limits, not indications that no
other work exists.

`make check` remains fully offline. Its Phase 4D acceptance path performs a dry
run with `network_requests == 0`; a missing or failed live observation cannot be
counted as a successful search.

## Blueprint deviation

This is the explicit owner-approved activation required by ADR-0050 before
adding discovery. It implements a narrow part of the blueprint's terminology
expansion and literature-discovery plan. It does not implement the deferred
crawler or citation traversal.

## Validation and revisit trigger

Acceptance requires executable checks that:

- reject any term not grounded in the supplied local source before DNS;
- require both live acknowledgement and exact query-hash confirmation;
- reject private, loopback, multicast, or otherwise non-global resolution
  before transport;
- enforce one request and every byte, term, result, time, credential, and terms
  review bound;
- discard malformed provider items and keep all surviving candidates
  inspiration-only with no acquisition or trust effect;
- detect a self-consistently rehashed attempt to promote trust; and
- keep the ordinary repository check network-free.

Revisit with a new ADR before adding another provider, credentials, ambient
proxy/session state, model-generated terms, semantic query expansion, result
fetching, crawling, citation traversal, scheduling, personalization, more than
one request, broader bounds, or any inference from search rank to relevance,
applicability, novelty, significance, or warrant.
