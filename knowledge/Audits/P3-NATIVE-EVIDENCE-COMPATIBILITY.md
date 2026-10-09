# P3 Native Evidence Compatibility Gate

## Subsequent Human Disposition (2026-09-12)

The owner approved revision-aware append-only observations. ADR-011 records the
decision and resolves the human-decision blocker below. The prior investigation
and its test results are preserved as history, not the current approval status.
Implementation/current scope: ../Components/P3-NATIVE-EVIDENCE.md.
This decision does not authorize a broker connection or prove demo isolation.

Evidence date: 2026-09-12 (inspection began 2026-09-11).
Branch: `core-rebuild`.
Inspected implementation: `6f805872e592b7b67885027b787decc408e450c5`, containing
P3 implementation `87229215534c00ae5f16997af7bff16df1e512fb`.
Characterization/evidence commit: `38d89bb72bd5d81fe1c8ea26a67c63a840151e0c`
(local only; not pushed). This reference was added in a documentation-only follow-up.
Disposition: **P3 PARTIAL; native implementation stopped at the explicitly
requested semantic-conflict gate. P4 remains BLOCKED.**

## Documented Native Semantics

MT5 supports BUY_CANCELED and SELL_CANCELED deal types. A previously executed
deal can change type under its existing identity, its recorded profit becomes
zero, and a separate balance operation accounts for the earlier profit/loss.
Native deal type is distinct from direction and entry/exit classification.
Source: [MetaQuotes deal properties](https://www.mql5.com/en/docs/constants/tradingconstants/dealproperties).

This is a documented API capability, NOT evidence that such a correction occurred
on the operator's account. No account was inspected. Frequency and applicability
to this broker/account are UNKNOWN.

Native position tickets can change through server operations; POSITION_IDENTIFIER
is the stable history-link identity used by orders/deals. A future normalizer must
preserve both where required, not assume position ticket equals opening order.
Source: [MetaQuotes position properties](https://www.mql5.com/en/docs/constants/tradingconstants/positionproperties).

## Exact Existing Contract Conflict

| Repository evidence | Current behavior / consequence |
|---|---|
| `backend/core/rebuild/execution_contracts.py:50`, DealObservation | BUY/SELL direction and entry classification, positive trade volume/price, no native cancellation/revision carrier |
| `backend/core/rebuild/safety_contracts.py:13`, Evidence | Extra fields forbidden; ad hoc revision fields cannot be retained in this contract |
| `backend/core/rebuild/execution.py:290` and `:312` | Changed payload for an already recorded deal ID raises immutable-deal conflict |
| `backend/core/rebuild/migrations/006_p3_execution.sql:34` and `:49` | One stored entry/exit deal payload per broker deal ID |
| Same migration `:37` and `:54` | Update triggers preserve immutable deal evidence |
| `backend/core/rebuild/execution.py:222` | Failed snapshot construction cannot supply a normalized snapshot to quarantine; raw native evidence retention is not established |
| `backend/core/rebuild/mt5_demo.py:20` and `:46` | Snapshot reader must be injected; no native reader supplied |
| `backend/core/rebuild/application.py:20` | Default operational native composition is not enabled; explicit execution injection is FIXTURE-only |

Current immutable storage and fail-safe rejection are correct safeguards. The gap
is representing broker revisions as current authoritative evidence while retaining
the prior observation and exact lineage. Overwriting old rows, dropping the native
cancellation type, manufacturing a new trade ID or giving balance adjustments fake
positive trade quantities would silently reinterpret native evidence.

Severity: HIGH compatibility/availability gap; a CRITICAL qualification risk if
ignored or represented as fully supported native reconciliation.

## Reproduction and Scope

`backend/tests/test_p3_native_semantic_gate.py` adds five characterization cases:

- BUY and SELL: after a fixture protective close, a changed profit under the same
  deal ID causes RECONCILIATION_REQUIRED, latched HALT, AMBIGUOUS reservation and
  RECOVERY_REQUIRED position projection. Original payload remains unchanged, revised
  common-field evidence is quarantined, no outcome is fabricated and retry does
  not send again. SQL mutation is independently rejected.
- Two cases prove proposed native type/revision carrier fields are forbidden by
  the existing contract. These names are test inputs, not claimed native API keys.
- A zero-volume/zero-price balance adjustment is rejected as a trade deal.

The profit-change fixture isolates only the common-field portion of the documented
revision. It does NOT normalize a canceled native type to BUY/SELL. These are
contract-characterization tests, NOT a native reader or native normalization proof.
Detailed completed regression evidence is in `../TESTING.md`.

## Required Human Disposition

**NEEDS_HUMAN_DECISION**, before native implementation resumes:

1. Explicitly bound P3 support: canceled/revised native deals remain unsupported,
   are preserved as raw evidence, quarantined and HALTed for operator resolution.
   This requires an approved qualification limitation and a proven lossless failure
   path; it cannot be described as complete native revision reconciliation.
2. Approve a revision-aware append-only observation contract/current projection
   and explicit balance-adjustment attribution. Prior observations remain immutable;
   a reviewed additive migration and reconciliation rules would be required.

Recommendation: option 2 for complete current broker-truth support; option 1 only
as an explicitly accepted bounded qualification. Neither decision was made here.
No ADR, policy, application contract or migration was changed.

## Isolated Demo Gate

| Required condition | Evidence / disposition |
|---|---|
| Approved operator entrypoint and exact access scope | UNVERIFIED; AGENTS.md/SECURITY.md exclude credentials from ordinary coding. No reviewed path/scope established for this smoke test |
| Current account positively DEMO and exact allowed identity | UNVERIFIED; no terminal/account connection attempted |
| No route to any real-money account | UNVERIFIED; isolated terminal ownership/account-switch exclusion not demonstrated |
| Secrets stay in approved boundary | No secrets accessed; operational credential boundary not qualified |
| HALT/P2 remain authoritative | Fixture regression evidence only; native end-to-end proof absent |
| Minimum safe broker-permitted volume | UNVERIFIED without qualified native metadata/valuation |
| Immediate stop on mismatch | Fixture fail-closed behavior proven; actual session behavior UNVERIFIED |

Result: **DEMO NOT_RUN**. No native import, initialization, login, evidence read,
order submission, cancellation or close was attempted. No credentials/operator
database were accessed. Fake-object method calls are not broker actions.

## Change Boundary and Next Step

This follow-up contains only characterization tests and documentation. Existing
application code, migrations and accepted ADRs remain unchanged. Unrelated
untracked `README_SETUP.md` is excluded. Nothing is pushed.

Resolve the native revision support disposition, then implement/qualify the native
reader with the required full fixture matrix. Only after the operator conditions
are evidenced may the separately bounded demo verification proceed. P3 cannot be
marked VERIFIED_COMPLETE on these characterization results.
