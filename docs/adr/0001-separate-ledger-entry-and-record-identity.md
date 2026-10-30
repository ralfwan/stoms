---
status: accepted
---

# Separate ledger-entry and record identity

Every ledger owns its local SQLite ledger-entry IDs, which are not part of
immutable record data. Each record instead has a portable opaque UUID that is
preserved during promotion, while a deterministic fingerprint of all other
immutable record data verifies transfer integrity. This keeps target storage
independent without losing cross-ledger identity, reference integrity, or safe
idempotent promotion.

## Considered Options

Using a transferred record UUID as the SQLite primary key was rejected because
it conflates local storage identity with immutable data identity. Deriving
record identity from a deterministic hash was rejected because independently
created but equal records must remain distinct provenance events.
