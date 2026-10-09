# P2 Safety Policy: Initial Demo Policy

Recorded: 2026-09-11. Policy version: **P2-DEMO-1.0**.
Human policy authorization: **ACCEPTED**, ADR-010.
Overall policy gate: **LOCKED**; C01-C03 explicitly approved on 2026-09-11.
Repository: `D:/project`; branch: `core-rebuild`.
Inspected baseline: `d2876ca4e315f732ec3acafa61a231567f90c99a`.
P1 remains VERIFIED_COMPLETE; M2 remains COMPLETE_WITH_RECORDED_INCIDENT.
**P2 IMPLEMENTATION: VERIFIED_COMPLETE in fixture/non-executing scope. Trading: HALTED / NOT QUALIFIED.**
Implementation evidence: `P2-SAFETY-ENGINE.md`; policy rules below are unchanged.

## Authority and Scope

The owner's P2 POLICY LOCK request explicitly approves the 21 clauses reproduced
below. They supersede the prior D01-D21 OPEN recommendations wherever the owner
made a decision. They are requirements, not evidence of working enforcement.
Legacy values remain evidence only. The original policy-recording task changed
no application code/tests; subsequent authorized P2 implementation has separate
evidence in `P2-SAFETY-ENGINE.md`.

ADR-010 supplements ADR-003; it does not weaken the final veto, finite/action
validation, persistent HALT, demo-only boundary or historical execution firewall.
ADR-001/004/008 remain binding; ADR-005/006 remain DEFERRED. ADR-002's 10-minute
live WhatsApp source window remains separate from broker-data ages in clause 15.
This policy lock does not authorize P4 ingestion or resolve its deferred source
timestamp details implicitly.

All percentages below are explicit percent points: 0.25% = decimal fraction
0.0025 and 0.50% = 0.005. Never infer units from magnitude. Missing sizing alone
selects the approved default; an invalid supplied value does not become missing.
All required values must be finite, meaningful and reliably convertible.
Existing OPEN geometry remains BUY: 0 < SL < entry < every active TP;
SELL: 0 < every active TP < entry < SL, revalidated at admission.
Unknown or unsupported actions reject; initial scope retains P1 OPEN admission,
not automatic MODIFY/CLOSE/ADOPT or broker dispatch.

## Accepted Policy Clauses

The following numbered policy is reproduced verbatim from the human request.
All previously missing numerical limits addressed here are now approved; none
are inferred from legacy code.

1. Risk sizing
- Default target risk when source provides no sizing request: 0.25% of capital basis.
- Maximum risk per trade: 0.50%.
- Requested risk above 0.50% is rejected, not silently reduced.
- Modeled risk includes stop distance plus admission-time transaction-cost allowances.
- No arbitrary dollar-risk fallback.
- No separate currency cap initially; percentage/exposure/margin caps are authoritative.

2. Capital basis
- Use MIN(valid equity, valid balance).
- External deposits/withdrawals adjust daily/weekly/high-water baselines only when supported by reliable broker evidence.
- Ambiguous capital/cash-flow state fails closed.

3. Broker units
- Use broker-reported account currency and validated instrument metadata only.
- No hardcoded tick-value/contract-size fallback.
- Risk-derived volume rounds DOWN to broker volume step.
- Below broker minimum lot => reject.
- No independent hard lot cap initially: broker maximum + risk + exposure + margin caps apply.
- Projected total margin utilization must remain <=25%.

4. Concurrent exposure
- Maximum 3 open/pending/reserved positions account-wide.
- Pending/reserved/ambiguous openings count toward the cap.

5. Same-direction entries
- No stacking on the same instrument initially.
- Independent signal identities remain preserved.

6. Opposite-direction entries
- Reject while an exposure already exists on the same instrument.
- No automatic hedge, reversal or netting behavior.

7. Exposure caps
- Per-instrument stop-risk: <=0.75% of capital basis.
- Portfolio stop-risk: <=1.50%.
- Per-instrument gross notional: <=150% of capital basis.
- Portfolio gross notional: <=300%.
- Total margin utilization after reservation: <=25%.
- Reservations count toward all projected limits.

8. Daily loss
- Block new risk at >=2.0% cash-flow-adjusted daily equity loss.
- Include realized and floating PnL.
- Day boundary: 00:00 UTC.
- Baseline must persist across restart.

9. Weekly loss
- Block new risk at >=4.0%.
- Week begins Monday 00:00 UTC.
- Cash-flow adjusted.
- Persistent rollover/baseline required.

10. Maximum drawdown
- >=8.0% decline from cash-flow-adjusted equity high-water mark triggers latched HALT.
- No automatic reset.

11. Correlation
Initial static buckets:
- PRECIOUS_METALS = XAUUSDm + XAGUSDm
- ENERGY = USOILm

Caps:
- precious-metals combined stop-risk <=1.00%
- energy stop-risk <=0.75%
- total portfolio cap remains 1.50%
- no hedge/correlation credit.

12. Reward:risk
- Minimum cost-adjusted R:R = 1.50.
- Exactly 1.50 passes.
- Use nearest active TP for admission.
- Reject below threshold.
- Never move SL/TP to manufacture compliance.

13. Stops / targets / order admission
- Explicit SL mandatory.
- At least one explicit TP mandatory.
- No ATR/default/fabricated fallback.
- Support MARKET and LIMIT admission semantics only during initial P2.
- LIMIT requires explicit entry.
- MARKET risk uses current validated quote plus configured adverse execution allowance.
- Normalize prices to broker tick size conservatively; normalization must never improve apparent R:R.

14. Execution-quality allowance
For XAUUSDm, XAGUSDm and USOILm initially:
- observed spread <=10% of stop distance;
- modeled adverse slippage allowance = 5% of stop distance;
- maximum quote deviation = 5% of stop distance;
- total modeled entry friction must be included in risk/R:R calculations.
- known commission must be included when validated configuration/evidence exists.
- never invent missing broker cost metadata.

15. Required data freshness
- quote: <=3 seconds old
- account/equity: <=5 seconds
- positions/orders: <=5 seconds
- conversion data: <=10 seconds
- instrument metadata: <=1 hour
- tolerated clock/future skew: <=2 seconds
- stale/unknown required evidence => reject.

16. Reservations
- Atomic reservation before approval capacity is consumed.
- Idempotent retries reuse the same reservation.
- Pre-submission reservation TTL: 60 seconds.
- TTL release only if broker submission has definitely NOT begun.
- Once submission begins, never time-release without terminal broker/reconciliation evidence.
- Ambiguous submission retains full reservation.
- Partial fills convert proportional reservation into position exposure; unresolved remainder stays reserved until terminal evidence.

17. Source treatment
- WHATSAPP_HUMAN, MANUAL and qualified NEXUSAI_STRATEGY use the same account-level limits.
- No source receives looser risk limits.
- Stricter future source overrides are allowed only through versioned policy.
- HISTORICAL_WHATSAPP and SCREENSHOT remain execution-ineligible.
- Execution-capable source identities must be explicitly allowlisted/configured.

18. HALT
- HALT overrides all admission.
- No automatic resume.
- Reset requires explicit operator action after reconciliation and documented reason.
- P2 does not automatically flatten positions or cancel broker orders.

19. Compliance
- Remove PDT/wash-sale concepts from authoritative P2 policy unless separately proven applicable.
- Initial compliance is technical/policy enforcement:
  approved demo account,
  allowed instrument,
  authorized source,
  broker reports instrument tradable/market available,
  no explicit restricted-list violation.
- No jurisdiction-specific legal rule is invented.
- No blackout/session restriction beyond reliable broker tradability evidence unless later approved.

20. Instrument allowlist
Only:
- XAUUSDm
- XAGUSDm
- USOILm

Aliases may map only through deterministic validated broker/config mapping.
Unknown symbols reject.
Empty allowlist denies all.

21. Policy versioning
- Every safety decision stores immutable policy version/hash.
- Changing policy creates a new version.
- Unused approvals/reservations created under superseded policy must be revalidated before economic action.
- Maximum-cap comparisons permit equality and reject projected values above the cap.
- Loss/drawdown thresholds block at or above the limit.
- R:R passes at >=1.50.
- Use deterministic decimal arithmetic for money/risk.
- Volume always rounds down.
- Price rounding must be conservative and cannot improve apparent safety.

## Decision Register Disposition

D01-D21 have accepted owner decisions in the clauses above and the authoritative
C01-C03 clarification below. No policy decision remains open for this initial
P2 implementation scope. Implementation and verification remain separate work.
Earlier optional lot/currency caps, Kelly/VIX adjustments, statistical correlation
and blackout proposals are not additional requirements: the owner chose no
independent lot/currency cap, static buckets and no extra blackout policy.

## Accepted C01-C03 Clarifications (2026-09-11)

The owner explicitly assigns these clarifications to **P2-DEMO-1.0**. They close
the previously blocked initial policy before implementation; they do not rewrite
runtime decisions. This supersedes the earlier recommendation to use a new version
for these clarifications. Subsequent policy changes still require a new version.

### C01 - Margin Utilization: ACCEPTED

`projected_margin_utilization = projected_used_margin / current_equity`.
Use current valid account EQUITY, not MIN(equity, balance), for this ratio.
Stale, missing, zero, negative or non-finite equity rejects. The cap is <=25%.
The separate sizing/stop-risk/notional capital basis remains MIN(equity, balance).
Projected margin includes reservations under the existing aggregate policy.

### C02 - Existing-Position Stop-Risk: ACCEPTED

Measure remaining aggregate stop-risk from CURRENT MARKET PRICE to the active
protective stop for both BUY and SELL, using conservative executable-side pricing.
Original-entry risk is historical attribution only, not current exposure risk.
Missing/invalid protective stop fails closed and requires reconciliation.
A stale quote rejects new admission. If price suggests the stop should already
have triggered but broker state disagrees, retain risk and classify reconciliation
ambiguity; never turn the disagreement into zero risk or released capacity.

### C03 - Execution-Quality References: ACCEPTED

- Spread = ASK - BID.
- MARKET BUY base entry = current ASK; adverse modeled entry moves upward.
- MARKET SELL base entry = current BID; adverse modeled entry moves downward.
- Execution-quality stop-distance anchor is the absolute distance between the
  BASE executable-side entry reference and validated SL, before adverse allowance.
- Spread cap = 10%, modeled adverse slippage = 5%, and maximum quote deviation =
  5% of that stop distance. These are distinct checks, not interchangeable units.
- Missing source entry is allowed only for MARKET: use the current executable-side
  quote, preserve the missing entry/source evidence as provenance, and compute
  risk/R from the conservative modeled entry after adverse allowance.
- For MARKET with a source entry, that entry is provenance only. Admission uses
  the current executable-side quote, not a source-entry deviation veto.
- LIMIT requires an explicit limit entry. Risk/R geometry uses that explicit price;
  current BID/ASK remain mandatory for spread, freshness and tradability checks.
- LIMIT quote deviation is measured between the current executable-side quote
  and explicit limit entry. Contradictory LIMIT semantics reject, never reinterpret.

The original 21 clauses remain preserved above; these owner-approved references
control their interpretation. No SL/TP fabrication, metadata fallback, source
eligibility expansion or broker execution is authorized. MARKET source-entry
absence support is an intended P2 contract change, not a claim P1 supports it now.

## Implementation and Operational Boundaries

- Separate P2 implementation authorization was subsequently received and its
  fixture scope verified; see P2-SAFETY-ENGINE.md. This policy record does not
  authorize P3, broker dispatch, operator migration or runtime activation.
- Atomic approval/reservation, consistent input snapshots, persistent baselines,
  replay/crash recovery, decimal math and boundary tests are implementation work,
  not additional permission to select risk numbers.
- No commission value is fabricated. Validated costs must be included; if cost
  evidence required for trustworthy risk/R:R is unknown, ADR-003 rejects admission.
  Do not treat absent metadata as evidence of zero commission.
- Initial baseline creation and cash-flow updates require reliable evidence.
  Missing/ambiguous baseline or cash-flow state rejects; restart is not a reset.
  Daily/weekly period blocks are not permission to clear a latched HALT.
- Account identities, authorized source IDs, aliases and supported valuation
  metadata remain explicit configuration/evidence prerequisites for future
  operation. They are not credentials needed for fixture-only engine development.
  Unsupported/unknown metadata rejects. No new netting allocation is authorized.
- Later execution must revalidate unused superseded approvals/reservations without
  rewriting old decisions or reversing a final veto on the same request.
- The 60-second pre-submission TTL is not proof of safe release after submission
  ambiguity and is not a guarantee of fresh data at future broker submission.
- Stop-risk is a modeled admission measure, not a guaranteed maximum realized loss.

## Original Policy-Recording Evidence and Limits

Documentation-only inspection against the baseline above. All 21 accepted clauses
are checked against the supplied request; references/status consistency and Git
whitespace/scope are checked. No application tests were rerun: no implementation
changed and existing P1 results do not verify P2 policy enforcement.
No secrets, operator database, broker, live ingestion or runtime startup accessed.
No commit or push is performed by this policy-recording task.

The following source findings are retained from the 2026-09-10 pre-implementation
inspection at the same baseline. They are not newly reproduced runtime findings.

## Legacy Values and Reliability

References below are repository-relative at the inspected commit. Trustworthy
means verified source evidence, never automatically approved or operationally safe.

| Evidence | Value/behavior found | Disposition |
|---|---|---|
| `backend/agents/risk_agent.py:30` | max_portfolio_risk_pct=0.02, described/used per trade | 2% candidate only; name misleading, not aggregate portfolio stop-risk |
| `risk_agent.py:31` | max_total_exposure_pct=0.20 | 20% candidate; denominator capital, numerator mixes incompatible meanings |
| `risk_agent.py:32` | max_single_position_pct=0.05 | 5% cap on confidence-derived deployed notional, not 5% SL risk or aggregate instrument exposure |
| `risk_agent.py:33` | max_sector_exposure_pct=0.25 | 25% declared; no enforcement use found in inspected backend Python sources |
| `risk_agent.py:36,477` | Daily hard loss 0.05; admission blocks at 75% of it | 5% hard / 3.75% early block candidates; no calendar-day rollover mechanism in RiskManagementAgent |
| `risk_agent.py:37,483` | Maximum drawdown 0.15; admission blocks at 80% of it | 15% hard / 12% early block candidates; peak is mutable/non-durable in legacy state |
| `risk_agent.py:493` | Reject if symbol already in positions | Not a numeric portfolio position-count cap; directions and tickets collapsed |
| Legacy risk/compliance/configuration search | No weekly drawdown policy/limit or week boundary; no implemented correlation risk policy | Absent in legacy; now supplied by accepted policy clauses 9 and 11 |
| `risk_agent.py:40` | min_risk_reward_ratio=1.5 | Value agrees with ADR-003; legacy execution path still unsafe |
| `risk_agent.py:41,503`; `execution_agent.py:114` | 50 bps used as spread limit and separately paper slippage cap | Candidate only; spread and execution slippage are different controls |
| `risk_agent.py:225,310,327,515` | Missing ATR becomes 1.5% of price; stop=2 ATR; half-Kelly; VIX multipliers at 25/30/40 | Heuristic candidates, not approved safety policy; missing input is fabricated |
| `risk_agent.py:78,129`; `legacy_application.py:163,170` | Initial capital 100,000; ComplianceAgent independent default balance 100,000 | Synthetic starting defaults; not actual account balance/equity |
| `backend/.env.example:6`; `legacy_application.py:163` | MAX_PORTFOLIO_RISK_PCT=0.02 template; risk agent instantiated with defaults | No consumer of this environment variable found in inspected backend Python; template is not proof of effective configuration |
| `backend/brokers/exness_mt5.py:89` | Demo orders disabled; minimum-lot round-up false; max volume 0.01 lots; risk fallback 2.0 labeled USD; deviation 20 points | Legacy defaults only; 2.0 is fallback, NOT a hard cap when order supplies positive risk |
| `exness_mt5.py:100`; `.env.example:33` | Watchlist XAUUSDm, EURUSDm, BTCUSDm, USOILm | Observation list, not approved execution allowlist |
| `exness_mt5.py:102`; `.env.example:34` | Code trade list EURUSDm, USOILm; template also includes XAUUSDm | Contradictory candidates; active environment intentionally uninspected |
| `exness_mt5.py:442` | Empty trade_symbols skips allowlist check | Unsafe fail-open configuration behavior; recommend empty means deny all |
| `backend/agents/advanced_agents.py:51,89,94` | Balance 100,000; PDT-labelled threshold 25,000/3 trades; wash-sale-labelled 30-day BUY block | Equity-oriented legacy candidates, applicability UNVERIFIED; not accepted CFD compliance rules |

## Unsafe or Contradictory Legacy Behavior

These are source-level findings about inactive legacy paths, not claims that the
current P1 application is trading or that this task reproduced live incidents.

1. **Risk unit discontinuity.** `risk_agent.py:456` divides by 100 only when the
   value exceeds 1. Parser `signal_parser.py:173` retains the number from RISK text,
   and validates up to 100 at line 228. Thus parser `RISK 0.5%` becomes 0.5, which
   legacy sizing treats as a 50% fraction before capping at 2%, not 0.5%. Its test
   (`test_risk_agent.py:84`) instead supplies 0.005 and expects 500 on 100,000.
   Invalid/missing requested risk can silently select the maximum.
2. **Latched HALT not checked.** `_check_kill_switch_conditions` at line 468 only
   checks loss/drawdown, not `_kill_switch_active`. A previously latched switch
   alone does not reject admission. Execution listens for a kill event to cancel
   pending work but has no durable admission latch (`execution_agent.py:124`).
3. **Unknown/non-finite values.** `risk_agent.py:217` tests price <= 0, not finite;
   line 229 makes any action without BUY a SELL; line 503 passes missing spread.
   NaN comparison behavior defeats several simple comparisons. Invalid explicit
   levels can become None at line 423 and fall into ATR stop generation if both
   disappear. P1 strict models are safer, but do not repair this legacy code.
4. **Exposures are not projected or reserved.** Risk checks existing deployed
   exposure before sizing (lines 177/488), then awaits publication. No atomic
   reservation includes the new request. Simultaneous requests can each observe
   the same headroom. Margin-or-notional at line 635 makes the denominator ratio
   inconsistent; position dictionaries overwrite independent same-symbol tickets.
5. **Reported risk differs from actual sized risk.** Kelly/notional caps reduce
   quantity after the budget is computed (lines 336/380); risk_amount_usd still
   reports that original budget. It is not recomputed loss at SL after sizing.
6. **Broker adapter is not currency-safe risk calculation.** Risk is absolute
   price difference times quantity (`exness_mt5.py:746`), always labeled USD;
   contract size falls back to 1 and volume metadata to defaults (line 714).
   Missing/wrong-side SL returns None; line 473 skips risk comparison when None.
   Quote changes are not followed by the common R:R gate. Positive supplied risk
   replaces, rather than intersects, the 2.0 fallback budget (line 472).
7. **Staleness and empty-state ambiguity.** Broker quote contains tick time, but
   market_data_payload stamps local time (line 389); admission does not enforce
   original quote age. positions_get None becomes empty (line 297); legacy sync
   also accepts empty positions and uses equity-or-balance (legacy_application.py:1487).
   Failed observation is not distinguishable from a verified flat account.
8. **Loss baselines are unsafe.** Risk state is in memory; update_capital resets
   peak/day baselines whenever no positions exist (line 600), not at a documented
   day/week boundary. Marked-to-market equity reconciliation and local realized
   close accounting are not one authoritative drawdown ledger. No weekly state.
9. **Compliance is advisory and incomplete.** Both agents subscribe to
   ORDER_REQUESTED; execution consumes risk approval without a compliance token
   (`advanced_agents.py:67`, `risk_agent.py:144`, `execution_agent.py:117`). A later
   violation cannot undo prior submission. The advertised five-day counter is
   today's closes (advanced_agents.py:133), not evidenced round trips; rule
   enabled flags, market-hours and position-limit declarations do not implement
   those controls in `_check_order_compliance`. Jurisdiction applicability is unknown.
10. **Mutable policy without validation/version.** Retired RiskUpdateRequest has
    unconstrained optional floats and directly assigns them to params
    (`legacy_application.py:508,631`). No approved numeric schema, effective-time
    snapshot or replay policy follows from that endpoint. Do not reactivate it.


## Historical Abstraction and Test Gaps Before Implementation

`DemoAccount` (`ledger.py:56`) supplies immutable identity/currency/mode, not equity,
balance, margin, timestamps or a coherent risk snapshot. P1's transaction helper
and lineage are reusable, not a risk engine. `001_lifecycle.sql:32` has reservation
columns and RESERVED/CONVERTED/RELEASED states but no active reservation writer,
expiry/version/input evidence or tested allocation semantics. Existing
`SafetyDecision` allows only FIXTURE/P1_DISABLED and P1 defaults reject.
These are intentional P1 boundaries, not grounds to relabel P1 incomplete.

Legacy `test_risk_agent.py` covers capital reset, missing/zero price, flat price,
explicit levels and hard-loss activation. It does not establish calendar rollover,
units consistency, latched-HALT admission, full NaN cases, projected aggregate caps
or atomic reservations. Broker tests use fakes for quotes/positions/demo flags,
volume risk and modify paths; they do not establish cross-currency valuation,
stale/incomplete snapshots or actual account eligibility. P1 tests cover identity,
strict contracts, firewall and recovery, not numerical P2 policy.

For a subsequently authorized engine, minimum planned acceptance cases (not implemented/run here):
percent/fraction ambiguity; cap boundary below/equal/above; missing/zero/NaN/Inf;
BUY/SELL and every TP with costs/rounding; mixed currency and volume steps;
two requests racing for final headroom; retry/crash before/after reservation;
partial-fill/ambiguous evidence with no premature release; identical versus
independent same-symbol sources; daily/weekly rollover/restart/cash flows;
HALT while approval is pending; stale/failed-empty/mismatched-account snapshots;
empty allowlist; synchronous compliance veto; no source-specific override.

## External Semantics Checked Without Broker Access

MetaQuotes documents profit estimation in account currency and a None failure
result. This supports requiring explicit valuation evidence rather than assuming
price-distance times quantity is always USD. No example code was executed.
[order_calc_profit reference](https://www.mql5.com/en/docs/python_metatrader5/mt5ordercalcprofit_py).

Instrument metadata exposes tick size/value, calculation mode, currency fields,
stop/freeze constraints and volume min/max/step. Those example values are not this
account's specifications or proposed risk limits.
[symbol_info reference](https://www.mql5.com/en/docs/python_metatrader5/mt5symbolinfo_py).

The order request deviation field is expressed in points, not basis points; it
does not replace admission risk calculation. No order request was sent.
[order_send reference](https://www.mql5.com/en/docs/python_metatrader5/mt5ordersend_py).
