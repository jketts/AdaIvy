"""Bounded exact search for the frozen ADR-0062 campaign experiment target.

This file is an UNTRUSTED PROGRAM.  It is not imported by the repository, it is
never executed on the host, and nothing it prints is a result.  It runs inside
the digest-pinned OCI sandbox with no network, no writable path outside a
bounded noexec tmpfs, and no credential, and it writes exactly one candidate to
``ADAIVY_RESULT_PATH``.  The candidate is re-derived by the in-repository exact
verifier, which never sees this file.

Arithmetic is exact: ``int`` and ``fractions.Fraction`` only.  The distinct
distance-eigenvalue count is computed from the squarefree part of the exact
characteristic polynomial, deliberately by a different route than the
verifier's confirmed minimal polynomial, so agreement is a cross-check.
"""

import json
from fractions import Fraction

TARGET_ID = "target.exact-graph-distance-spectrum-v1"
ORDER = 10
EDGE_COUNT = 15
DISTINCT_DISTANCE_EIGENVALUES = 3
INVERSE_EVEN = Fraction(5, 3)


def normalise(order, pairs):
    edges = set()
    for u, v in pairs:
        if u == v or not (0 <= u < order) or not (0 <= v < order):
            return None
        edges.add((min(u, v), max(u, v)))
    return tuple(sorted(edges))


def adjacency(order, edges):
    table = [set() for _ in range(order)]
    for u, v in edges:
        table[u].add(v)
        table[v].add(u)
    return table


def distances(order, table, source):
    seen = [-1] * order
    seen[source] = 0
    frontier = [source]
    while frontier:
        nxt = []
        for v in frontier:
            for w in table[v]:
                if seen[w] < 0:
                    seen[w] = seen[v] + 1
                    nxt.append(w)
        frontier = nxt
    return seen


def distance_matrix(order, table):
    rows = []
    for v in range(order):
        row = distances(order, table, v)
        if any(item < 0 for item in row):
            return None
        rows.append(row)
    return rows


def triangle_free(order, table):
    for u in range(order):
        for v in table[u]:
            if v <= u:
                continue
            if table[u] & table[v]:
                return False
    return True


def characteristic_polynomial(matrix):
    """Faddeev-LeVerrier, exact over the rationals; ascending coefficients."""

    n = len(matrix)
    coefficients = [Fraction(1)]
    current = [[Fraction(0)] * n for _ in range(n)]
    for k in range(1, n + 1):
        if k == 1:
            product = [[Fraction(matrix[i][j]) for j in range(n)] for i in range(n)]
        else:
            shifted = [row[:] for row in current]
            for i in range(n):
                shifted[i][i] += coefficients[-1]
            product = [
                [
                    sum(Fraction(matrix[i][t]) * shifted[t][j] for t in range(n))
                    for j in range(n)
                ]
                for i in range(n)
            ]
        current = product
        trace = sum(current[i][i] for i in range(n))
        coefficients.append(-trace / k)
    return list(reversed(coefficients))


def trim(poly):
    out = list(poly)
    while len(out) > 1 and out[-1] == 0:
        out.pop()
    return out


def derivative(poly):
    return trim([poly[i] * i for i in range(1, len(poly))]) if len(poly) > 1 else [Fraction(0)]


def poly_mod(a, b):
    a = trim(a)
    b = trim(b)
    if len(b) == 1 and b[0] == 0:
        return None
    while len(a) >= len(b) and not (len(a) == 1 and a[0] == 0):
        factor = a[-1] / b[-1]
        offset = len(a) - len(b)
        for i in range(len(b)):
            a[offset + i] -= factor * b[i]
        a = trim(a)
        if len(a) == 1 and a[0] == 0:
            break
    return a


def poly_gcd(a, b):
    a = trim(a)
    b = trim(b)
    while not (len(b) == 1 and b[0] == 0):
        remainder = poly_mod(a[:], b[:])
        if remainder is None:
            return None
        a, b = b, remainder
    return a


def distinct_root_count(poly):
    poly = trim(poly)
    common = poly_gcd(poly[:], derivative(poly))
    if common is None:
        return None
    return (len(poly) - 1) - (len(common) - 1)


def inverse_even_excluding_v(order, table):
    total = Fraction(0)
    for v in range(order):
        row = distances(order, table, v)
        if any(item < 0 for item in row):
            return None
        count = sum(1 for item in row if item % 2 == 0) - 1
        if count == 0:
            return None
        total += Fraction(1, count)
    return total


def circulant(order, offsets):
    pairs = []
    for v in range(order):
        for offset in offsets:
            pairs.append((v, (v + offset) % order))
    return normalise(order, pairs)


def generalized_petersen(n, k):
    pairs = []
    for i in range(n):
        pairs.append((i, (i + 1) % n))
        pairs.append((n + i, n + ((i + k) % n)))
        pairs.append((i, n + i))
    return normalise(2 * n, pairs)


def kneser(n, k):
    subsets = []

    def build(start, chosen):
        if len(chosen) == k:
            subsets.append(frozenset(chosen))
            return
        for item in range(start, n):
            build(item + 1, chosen + [item])

    build(0, [])
    subsets.sort(key=lambda item: sorted(item))
    pairs = []
    for i in range(len(subsets)):
        for j in range(i + 1, len(subsets)):
            if not subsets[i] & subsets[j]:
                pairs.append((i, j))
    return normalise(len(subsets), pairs)


def constructions():
    """Deterministic construction inventory, in a fixed enumeration order."""

    found = []
    for mask in range(1, 32):
        offsets = tuple(item for item in range(1, 6) if mask & (1 << (item - 1)))
        found.append(("circulant(10,%s)" % ",".join(str(i) for i in offsets), circulant(10, offsets)))
    for n in range(3, 8):
        for k in range(1, (n + 1) // 2 + 1):
            if k >= n:
                continue
            found.append(("generalized_petersen(%d,%d)" % (n, k), generalized_petersen(n, k)))
    for n, k in ((5, 2), (6, 2), (6, 3), (7, 3)):
        found.append(("kneser(%d,%d)" % (n, k), kneser(n, k)))
    return found


def evaluate(order, edges):
    if order != ORDER or len(edges) != EDGE_COUNT:
        return None
    table = adjacency(order, edges)
    matrix = distance_matrix(order, table)
    if matrix is None or not triangle_free(order, table):
        return None
    count = distinct_root_count(characteristic_polynomial(matrix))
    if count != DISTINCT_DISTANCE_EIGENVALUES:
        return None
    if inverse_even_excluding_v(order, table) != INVERSE_EVEN:
        return None
    return edges


def main():
    examined = 0
    for name, edges in constructions():
        if edges is None:
            continue
        examined += 1
        order = max((v for pair in edges for v in pair), default=-1) + 1
        if evaluate(order, edges) is None:
            continue
        candidate = {
            "schema_version": "adaivy.campaign-experiment-graph-candidate.v1",
            "target_id": TARGET_ID,
            "asserted_satisfies_target": True,
            "asserted_construction": name,
            "order": order,
            "edges": [[u, v] for u, v in edges],
        }
        payload = json.dumps(candidate, sort_keys=True, separators=(",", ":")).encode("utf-8")
        with open(ADAIVY_RESULT_PATH, "wb") as handle:  # noqa: F821 - sandbox injects it
            handle.write(payload)
        print("examined %d constructions; emitted one candidate from %s" % (examined, name))
        return 0
    print("examined %d constructions; no candidate satisfies the frozen target" % examined)
    return 1


raise SystemExit(main())
