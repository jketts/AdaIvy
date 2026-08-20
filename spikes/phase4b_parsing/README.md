# Phase 4B parser adoption spike

Status: quarantined evaluation only; no production parser or dependency adopted.

This spike freezes the custody contract before selecting parser libraries. Its
executable path uses only the Python standard library and synthetic fixtures.
It accepts deliberately restricted profiles for structured HTML, non-executing
TeX, and uncompressed born-digital PDF. OCR output can be captured but is always
quarantined because recognized text has no exact original-text byte span.

Run the focused offline suite:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest -v tests.test_phase4b_parser_spike
```

## Contract exercised

Every result binds `source_id`, `representation_id`, media type, original byte
length, and original SHA-256. Extracted non-OCR segments bind an exact
half-open original-byte span and a SHA-256 of those bytes. Normalization never
replaces the original representation.

All successful parses have status `accepted_candidate`; parsing is not a
warrant, applicability decision, or evidence acceptance. Rejected inputs retain
their original lineage and a stable quarantine reason. Captured OCR carries
both original and candidate-output lineage but no invented source span.

The fixed bounds cover input bytes, candidate bytes, serialized output bytes,
markup tokens, segments, formulas, individual segment bytes, and warnings.
Tests force each relevant bound closed and reject active HTML, expanding or I/O
TeX commands, and active/embedded PDF features. Formula text from two
representations is compared explicitly; agreement remains candidate agreement,
while disagreement requires quarantine.

## Deliberate limitations

- The HTML profile is not an HTML5 conformance implementation.
- The TeX profile lexes a small allowlist and never expands macros, loads files,
  locates packages, invokes TeX, or renders.
- The PDF profile handles only small synthetic, uncompressed literal text. It
  is not a general PDF parser.
- No OCR executable, model, language data, parser wheel, subprocess, network
  call, or production import is present.
- The spike does not edit or supersede Phase 4A rights/applicability records.

See `DEPENDENCY_LICENSE_ASSESSMENT.md` for staged candidate findings and the
gates required before any dependency is proposed for adoption.

