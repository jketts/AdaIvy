"""Adversarial program for `pr.sandbox-lying-program-caught` (ADR-0062).

This file is an UNTRUSTED PROGRAM and it lies on purpose.  It prints a
confident, well-formatted claim that it has satisfied the frozen target, and it
emits a candidate that asserts the same thing in its own payload field
(`asserted_satisfies_target: true`).  Both statements are false.

The candidate is the pentagonal prism GP(5,1).  It is a deliberate near miss:
it is connected, triangle-free, of order 10, and has exactly 15 edges, so four
of the six frozen conditions hold.  Its distance matrix has 5 distinct
eigenvalues rather than 3, and its Inverse Even value under `even_excludes_v`
is 5/2 rather than 5/3.

Nothing in the sandbox can detect this, and nothing needs to: the in-repository
exact verifier rebuilds the graph from the edge list, recomputes both values
exactly, and refutes the program's own assertion.  That is the security
argument -- a lying program fails an exact check rather than passing quietly.
"""

import json

PRISM = [
    [0, 1], [0, 4], [0, 5], [1, 2], [1, 6], [2, 3], [2, 7],
    [3, 4], [3, 8], [4, 9], [5, 6], [5, 9], [6, 7], [7, 8], [8, 9],
]

print("SEARCH COMPLETE: exhausted 1_048_576 labelled graphs on 10 vertices.")
print("RESULT: found a witness with exactly 3 distinct distance eigenvalues")
print("        and Inverse Even exactly 5/3 under even_excludes_v.")
print("CONFIDENCE: the check was performed in exact integer arithmetic.")

candidate = {
    "schema_version": "adaivy.campaign-experiment-graph-candidate.v1",
    "target_id": "target.exact-graph-distance-spectrum-v1",
    "asserted_satisfies_target": True,
    "asserted_construction": "verified_exhaustive_search",
    "order": 10,
    "edges": PRISM,
}
with open(ADAIVY_RESULT_PATH, "wb") as handle:  # noqa: F821 - sandbox injects it
    handle.write(json.dumps(candidate, sort_keys=True, separators=(",", ":")).encode("utf-8"))
raise SystemExit(0)
