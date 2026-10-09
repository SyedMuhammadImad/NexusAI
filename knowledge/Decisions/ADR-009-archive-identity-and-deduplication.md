# ADR-009 — Archive Identity and Deduplication

Status: **ACCEPTED**  
Accepted during P0 governance review.

## Decision

Historical import identity is layered. ZIP/container bytes alone are not the identity of the underlying dataset.

Preserve:

1. original archive identity and SHA-256;
2. deterministic normalized transcript fingerprint;
3. stable message-level identity with raw evidence retained;
4. canonical signal identity/provenance;
5. explicit duplicate/re-import relationships.

Repacking the same underlying transcript must not silently create duplicate canonical observations merely because ZIP metadata/compression changed.

## Rules

- Raw archive/message evidence is preserved.
- Normalization is for deterministic identity matching, not evidence destruction.
- Duplicate imports remain auditable as separate import events linked to the same underlying transcript/content identity.
- Similar messages must not be silently merged into one economic trade without explicit deterministic evidence/rules.
- Fuzzy similarity may flag `POSSIBLE_DUPLICATE`, but it cannot silently merge or delete records.
- Archive hash alone is insufficient for dataset uniqueness.

## Implementation consequence

The known archive-idempotency weakness is a FIX item. Implementation and tests must distinguish byte-identical archive replay from transcript-equivalent repackaging.
