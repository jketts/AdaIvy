# ADR-0068: Following discovery results (machine-selected fetch origins)

- **Status:** accepted but not implemented, by owner decision on 2026-08-22,
  **over a recorded recommendation against it**. The recommendation and the
  residual risk are retained below rather than removed, because an overridden
  objection that disappears from the record cannot be revisited. Superseded in
  part by ADR-0072: the "does not license query generation" boundary, the
  `pr.follow-query-not-generated` probe, and the machine-generated-queries
  revisit item are superseded; all six controls and every other clause stand.
  Implemented by ADR-0081 (2026-08-22) in
  `src/math_research/phase4d/following.py` with all six controls enforced.
- **Date:** 2026-08-22
- **Blueprint requirement:** Section 7.1 (crawlers produce candidates, not
  trusted documents); Section 15 (`:1801` prompt injection inside retrieved
  documents; `:1817-1818` treat all retrieved content as untrusted data);
  ADR-0050 (exact-URL human-planned acquisition); ADR-0051 (bounded discovery,
  which states "does not follow results"); ADR-0067 (corpus at volume)
- **Decision owners:** repository owner

## Context

ADR-0051 permits one Crossref metadata query returning at most ten DOI
candidates and states that the capability "does not follow results, crawl,
traverse citations, generate queries, use credentials, schedule work, or call a
model." ADR-0050 pins `autonomous_origin_selection: false`.

This ADR removes the first clause of that sentence: a URL appearing in a
discovery result may become a fetch target chosen by the machine rather than by
a human.

### The recommendation against, retained

The clause being removed is load-bearing prompt-injection defence, not
bookkeeping. `TECHNICAL_BLUEPRINT.md:1801` names prompt injection inside
retrieved documents as a threat; `:1817-1818` requires all retrieved content be
treated as untrusted data. While origins are human-chosen, an attacker must
first persuade a human to type their URL. Once origins are machine-chosen from
metadata, publishing a record whose URL field points at attacker-controlled
content is sufficient, and the content reaches a system that makes model calls.

The owner has weighed this against the breadth it buys and decided to proceed.
That is a legitimate call about their own research system. What follows is the
containment that makes it implementable rather than reckless, and an honest
statement of what containment does not cover.

## Decision

Permit depth-one following of discovery results, under six controls. Every one is
a hard gate, not a default.

1. **Pinned origin allowlist.** A followed URL is fetched only if its host is on
   an explicit, content-hashed allowlist of scholarly origins. A hostile metadata
   record therefore cannot name an arbitrary host; it can only point somewhere we
   already decided to trust. **This is the decisive control** — the others narrow
   the blast radius, this one bounds the attacker's reach.
2. **Depth one, absolutely.** A document acquired by following a result never
   produces a further fetch target. Nothing inside a followed document — link,
   citation, redirect, reference list — is a candidate. This is the entire
   difference between following and crawling, and `:1129-1130` forbids the
   latter in the trusted core.
3. **No credentials, ever.** A followed fetch carries no credential, no
   caller-supplied header, and no cookie. Unchanged from ADR-0050.
4. **No redirects, no query strings.** Unchanged from ADR-0050. A redirect is a
   second origin the allowlist never approved.
5. **Pinned fan-out.** At most `max_followed_per_run` fetches per run, pinned in
   the activation record, with the discovery query hash bound to the run.
6. **Machine selection is recorded as such.** Every followed acquisition records
   `origin_selected_by: "automation"`, the discovery record id, and the exact
   metadata field the URL was read from. No report may present a machine-selected
   origin as human-planned, and `autonomous_origin_selection` becomes a recorded
   per-run value rather than a global `false`.

### Named boundaries

- **A followed document is untrusted data, and its class does not improve by
  being fetched.** It remains an `untrusted_inspiration_candidate`: relevance,
  applicability, novelty, and significance stay `not_assessed`, and it creates no
  premise, no warrant, and no graph admission. Acquiring a document is not
  reading it, and reading it is not believing it.
- **Followed content is rendered inside a delimited untrusted region** wherever
  it reaches a model context, with system policy outside that region, per
  `:1817-1818`. Content inside the region is never treated as instruction.
- **Rights are not inherited from discovery.** A discovery hit authorizes
  nothing. Each followed document needs its own Phase 4A acquisition, retention,
  and parsing decisions, and its own ADR-0064 processor decision before it may be
  embedded.
- **This does not license query generation.** The machine may follow a result; it
  may not invent the query that produced it. ADR-0051's operator-supplied,
  locally-substring-checked query terms are unchanged.

## Residual risk, not covered by the above

- An allowlisted publisher hosting hostile content still reaches the model. The
  allowlist is only as good as its membership, and membership is a human
  judgement that will decay as the list grows. A list long enough to be useful
  is long enough to contain something compromised.
- The controls bound *reach*, not *content*. Nothing here detects an injection
  attempt; it only limits who can attempt one.
- Every prior record asserting `autonomous_origin_selection: false` now describes
  a configuration that is no longer the only one available. Those records remain
  true of their own runs, but the property is no longer a global invariant of the
  system, and anything that read it as one must be re-read.

## Consequences

- ADR-0051's "does not follow results" is superseded in that one clause and
  otherwise stands. ADR-0051's text must carry a pointer here, or it will be read
  as current.
- The activation record gains the allowlist hash, `max_followed_per_run`, and the
  per-run `autonomous_origin_selection` value. Existing activation records do not
  acquire the capability by default.
- The injection-containment work I recommended as a prerequisite is not
  abandoned; controls 1, 2, and 6 are the part of it that fits in this slice.
  Detection — as opposed to containment — remains unbuilt.

## Blueprint deviation

**Yes, and stated rather than buried.** ADR-0050's `autonomous_origin_selection:
false` and ADR-0051's "does not follow results" are both narrowed. The blueprint
itself permits candidate-producing acquisition at `:1129-1130` provided it is not
in the trusted core and passes validation and ingestion, and the six controls keep
followed documents outside the trusted core. The deviation is from the two ADRs'
tighter posture, not from the blueprint's, and the tighter posture existed for the
injection reason recorded above.

## Falsifiability probes

- `pr.follow-offlist-origin-refused` — a discovery result naming a host outside
  the allowlist must refuse, not fetch.
- `pr.follow-depth-two-refused` — a link inside a followed document must never
  become a fetch target.
- `pr.follow-redirect-refused` — a followed URL that redirects must refuse.
- `pr.follow-credential-refused` — any credential on a followed fetch must refuse.
- `pr.follow-fanout-bound` — exceeding `max_followed_per_run` must refuse.
- `pr.follow-records-automation` — a followed acquisition whose record claims
  `origin_selected_by: "human"` must refuse.
- `pr.follow-grants-no-rights` — a followed document without its own Phase 4A
  decisions must not be parseable or embeddable.
- `pr.follow-class-unchanged` — a followed document must remain
  `untrusted_inspiration_candidate` with all four assessments `not_assessed`.
- `pr.follow-query-not-generated` — a machine-composed query term must refuse.

## Validation and revisit trigger

Valid while: the allowlist is content-hashed and human-maintained; depth stays
one; no credential reaches a followed fetch; fan-out stays pinned; machine
selection is recorded per run; and every probe flips.

**Revisit immediately if** any followed document is ever found to have influenced
a model's output in a way the operator did not intend — that is the failure this
ADR accepts the risk of, and the first occurrence should reopen the decision
rather than be handled as a bug.

Revisit with a new ADR before: raising depth above one; adding an origin to the
allowlist without human review; permitting machine-generated queries; or letting
a followed document carry any assessment other than `not_assessed`.
