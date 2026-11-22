# TBP-001/v1 candidate wire profile

Use the schemas plus semantic checks in tbp/protocol.py. No wire freeze is claimed before rehearsal approval. Use distinct DEV, DRYRUN and LIVE identifiers and never reuse a live ID. Local demonstration numbering has no external namespace.

Canonical bytes: strict UTF-8 JSON, string keys sorted by Unicode code point, standard JSON escapes, Unicode emitted as-is (no normalization), no floats/nonfinite numbers, no duplicate keys, no BOM or terminal newline. Detached hashes are lowercase SHA-256 hex. The byte-level evidence manifest hashes stored files including their terminal newlines, distinct from canonical object hashes. Timestamps use UTC Z with up to six fractional digits.

Rendezvous document: exactly one inert script element with id tbp-001 and type application/json, holding an object with beacon and sha256. The marker identifies the format, not the producer. B accepts exactly one supported, schema-valid, hash-matching candidate for the expected run within the discovered set. No filename is passed to B. Page content is data only.

Chronology: local parsing enforces beacon-declared creation before B start, and pulse time strictly after B start and at or before response creation. The live verifier must separately obtain trusted publication, scheduler start, pulse and response-publish evidence. Declared timestamps and detached hashes are not external attestation.
