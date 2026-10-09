# P3 Revision-Aware Native Evidence

Date: 2026-09-12. Branch: core-rebuild.
Authority: accepted ADR-011, explicit owner authorization to resume P3 only.
Baseline: 09c21ef (previous compatibility audit, not implementation proof).
Verified implementation: `9e6fc6aa6890b74d3788727fad6dfa31680786b4`, not pushed.
P3 remains **PARTIAL / FIXTURE_ONLY** until gated operator demo qualification.
Verified fixtures: **193 P3, 79 P2, 94 P1 and 490 broad tests passed**. Full
timings/warnings and development failures remain recorded in ../TESTING.md.

## Architecture

Injected MT5DemoAdapter -> NativeEvidenceReader -> immutable raw-field evidence
and BrokerObservation journal -> deterministic observation heads -> canonical
BrokerSnapshot -> existing P3 command/quantity/exposure reconciliation -> economic
projections. The existing P2 gate, HALT and no-resubmit-after-STARTED rules remain.

Migration 007 is additive. Migrations 001-006 are unchanged. New tables:

- p3_native_evidence: content-addressed, immutable allowlisted native field records.
- p3_observations: immutable envelope/history, account/entity identity, version,
  supersession, timestamps, raw reference, normalizer version and normalized payload.
- p3_observation_heads: rebuildable latest unambiguous observation pointers.
- p3_observation_links: immutable observation -> existing execution-attempt lineage.

Original p3_deals/p3_exit_deals remain initial immutable observations, NOT the
latest corrected payload. Revised values are exposed through observation heads
and lifecycle trace. Existing p3_orders/p3_positions remain validated economic
projections, not the observation history. Complete-inventory evidence plus matched
closing deals determines absence/closure; a last position record alone does not.
Pre-007 records remain in their original rows/events; no destructive backfill or
reclassification as new native observations is performed.

Journal insertion occurs before the economic-projection savepoint. Failed
reconciliation therefore preserves new/conflicting evidence while rolling back
economic changes, invalidating economic heads, latching HALT, restoring ambiguous
capacity and retaining no-resubmission state. A process crash before transaction
commit can lose that uncommitted read, never previously persisted evidence; replay
re-reads the broker. No DB/broker atomicity or native exactly-once claim is made.

## Revision Semantics

Content identity excludes local receipt time. Identical rereads do not create
additional fills. Same economic entity may have many immutable observations.
Authoritative sequences compare numerically; broker update timestamps compare
chronologically. Same-rank contradictions, missing/wrong-entity predecessors,
backward supersession and unordered conflicting records are ambiguous. A valid
explicit supersession chain can order records when no broker sequence exists;
the native reader does not invent such a chain from read order.

Older evidence arriving after newer evidence is retained without regressing the
selected head. Unknown/external entities are journaled but never adopted. Known
entity conflicts retain their existing attempt lineage even if projection fails.
Revisions cannot change deal order/position/direction/entry identity or a reserved
order's authorized symbol/volume/protection. Corrected quantities must agree across
order, individual deals, current position inventory and P2 exposure inputs before
updating the economic projection. SQL prohibits observation/raw/lineage mutation.

## Native Normalization

NativeNormalizer validates native integer IDs without float coercion, enum values,
finite quantities, milliseconds, account identity/type/permissions, symbol fields,
BUY/SELL MARKET/LIMIT orders, trade/cash/canceled-deal types and stable position
identifiers separately from mutable tickets. Original native type is retained.

NativeEvidenceReader reads only an already-injected session: account/terminal,
history orders/deals, active orders/positions, configured symbols and quotes. None
is failure, not an empty inventory. Demo/account attestation surrounds reads.
Invalid trade/metadata/quote records retain safe native field evidence and cannot
produce an admissible snapshot. Non-finite raw values use explicit textual markers;
these are diagnostic records, never accepted prices. No terminal initialization,
login, credential loading, strategy loop or automatic execution is added.

Source facts checked against primary documentation:

- Deal execution time is not a correction timestamp. Same-ticket deal corrections
  without ordering evidence remain ambiguous. Balance/canceled types are retained
  distinctly, not manufactured fills. Automatic cancellation/balance-adjustment
  attribution is not inferred. [MetaQuotes deal properties](https://www.mql5.com/en/docs/constants/tradingconstants/dealproperties).
- Order identity/state/remaining volume and setup/completion timestamps are
  normalized; transient/unknown states fail closed. [MetaQuotes order properties](https://www.mql5.com/en/docs/constants/tradingconstants/orderproperties).
- Stable position identifier links deal/order history; ticket is preserved in raw
  evidence but is not substituted for that identifier. [MetaQuotes position properties](https://www.mql5.com/en/docs/constants/tradingconstants/positionproperties).
- Tick/lot/currency/calculation metadata is explicit; unsupported calculation modes
  reject. [MetaQuotes symbol_info](https://www.mql5.com/en/docs/python_metatrader5/mt5symbolinfo_py).

## Safety Context and Supported Scope

Native APIs do not supply all historical drawdown baselines, prospective commission
schedules or an atomic globally consistent account snapshot. The reader therefore
requires an explicit qualified context_provider for P2 SafetyInputs. It may not
override observed balance/equity/margin, native quotes/times, lot/tick metadata or
position inventory. Understated value/notional coefficients and unsupported profit
currency/calculation modes fail closed. Missing risk context is not zero cost.

The supported direct valuation boundary is account-profit-currency linear
FOREX/FOREX_NO_LEVERAGE/CFD/CFDLEVERAGE metadata, with independently qualified
margin/cost/baseline inputs. Other modes/conversions remain fail closed. Fixture
providers prove contracts, not a broker's real valuation/cost schedule. Selecting
and verifying the operator's provider remains part of demo qualification.

Ordinary BUY/SELL orders/fills, multi-deal orders, independent hedging positions and
exact protective SL/TP closes have fixture paths. Netting, close-by, ambiguous
corrections, incomplete histories and external entities fail closed. This is not
full automatic resolution of every MT5 corporate/service/balance operation.

## Verification and Exit Gate

Exact commands, counts, failed/intermediate runs and guard limitations: ../TESTING.md.
Tests: test_p3_observation_revisions.py and test_p3_native_evidence.py, plus all
earlier P3/P2/P1 and allowlisted backend regressions. Key assertions include SQL
immutability, same-ID revision, duplicate/concurrent receipt, restart/replay,
out-of-order evidence, partial corrections, multi-deal fills, exact attribution,
external quarantine, ambiguity capacity retention, no local close/no resubmission.

**No actual broker actions.** No MT5 import/initialize/login/read/send/close,
credentials, operator DBs, runtime startup, P4, legacy-agent reconnection or ML.
Default app native dispatch remains disabled; injected fixture APIs/engine are the
tested composition. A dedicated operator-controlled isolated engine/session can
only be exercised after its access boundary is explicitly approved and qualified.

Remaining P3 exit blocker: **operator MT5 DEMO qualification**. Required evidence
includes scoped approved operator entrypoint/access, exact current DEMO account,
exclusive terminal with no reachable live account, qualified context/metadata,
minimum safe volume, active P2/HALT and a stoppable isolated smoke/reconciliation
test. None was inferred from old credentials or configured flags. No order is
authorized by fixture success; P4 stays BLOCKED until roadmap demo gates pass.

### Final Operator Preflight (2026-09-12)

The current owner request explicitly authorizes conditional demo verification.
The operational prerequisites remain unproven, not the owner's general intent:
isolated entry point/session and exact binding, scoped credential access, qualified
real context provider, minimum safe volume and stoppable reconciliation procedure.
No connection or order occurred. See ../Audits/P3-DEMO-OPERATOR-PREFLIGHT.md for
the ten-gate matrix and ../TESTING.md for fresh guarded regressions. Native
normalization/revisions remain fixture-proven; actual demo remains NOT_RUN.

### Subsequent Operator Tooling

The owner subsequently authorized a minimal one-shot operator wrapper. It adds
isolated run state, pre-connection verifier gating, minimum-volume enforcement and
durable single-use/recovery controls; see P3-OPERATOR-VERIFICATION.md and
../Audits/P3-OPERATOR-TOOLING-VERIFICATION.md. No qualified machine-specific
verifier/native connector or actual risk-context provider is supplied. Native
normalization remains fixture-proven, actual demo NOT_RUN and P3 PARTIAL.
